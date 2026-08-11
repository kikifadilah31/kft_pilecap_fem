"""Meshing all-quad via gmsh Python API (PRD Bagian 3.2 langkah 1-8, Bagian 5.1(f)).

Strategi yang ditetapkan PRD dan TIDAK boleh diimprovisasi:

* `Mesh.Algorithm = 11` (Quasi-structured Quad)
* `Mesh.RecombinationAlgorithm = 3` (Blossom full-quad)
* mode `uniform`: `MeshSizeMin = MeshSizeMax = h` -> ukuran elemen seragam
* `setRecombine` dipanggil untuk SETIAP face hasil `occ.fragment`, bukan sekali

Hasil pengukuran pada gmsh 4.15.2 (lihat `tests/test_mesh_engine.py`): `Mesh.Algorithm = 11`
sudah menghasilkan mesh 100% quad SENDIRI, bahkan tanpa `setRecombine`. Jadi
`RecombinationAlgorithm = 3` + `setRecombine` berfungsi sebagai lapis pengaman kedua,
bukan satu-satunya mekanisme. Verifikasi `n_tri == 0` setelah `generate(2)` tetap WAJIB --
itulah yang membuktikan hasilnya, bukan asumsi tentang opsi mana yang bekerja.

Seluruh siklus gmsh dibungkus `try/finally` dengan `gmsh.finalize()` agar state gmsh tidak
bocor antar run (PRD Bagian 13.4).

Modul ini bekerja murni SI (meter) -- `Mesh.MeshSizeMin/Max` diberikan dalam satuan
geometri model, yaitu meter. Konversi dari mm dilakukan di `io_utils.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import gmsh
import numpy as np

from pilecap_fem import config, validators
from pilecap_fem.geometry_builder import GeometryModel, Pier, Polygon2D
from pilecap_fem.validators import MeshError

_log = config.get_logger("mesh_engine")


@dataclass(frozen=True)
class MeshOptions:
    """Opsi meshing efektif, sudah dalam SI. Dibaca dari config + override CLI."""

    size_mode: str
    size_global: float
    size_local_pile: float | None
    size_local_pier: float | None
    algorithm: int
    recombination_algorithm: int
    recombine: bool
    require_all_quad: bool
    element_order: int

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> MeshOptions:
        mesh = cfg["mesh"]
        return cls(
            size_mode=mesh.get("size_mode", "uniform"),
            size_global=float(mesh["size_global"]),
            size_local_pile=(
                None if mesh.get("size_local_pile") is None else float(mesh["size_local_pile"])
            ),
            size_local_pier=(
                None if mesh.get("size_local_pier") is None else float(mesh["size_local_pier"])
            ),
            algorithm=int(mesh.get("algorithm", config.GMSH_ALGORITHM_DEFAULT)),
            recombination_algorithm=int(
                mesh.get("recombination_algorithm", config.GMSH_RECOMB_ALGORITHM_DEFAULT)
            ),
            recombine=bool(mesh.get("recombine", True)),
            require_all_quad=bool(mesh.get("require_all_quad", True)),
            element_order=int(mesh.get("element_order", 1)),
        )


@dataclass(frozen=True)
class RawMesh:
    """Hasil mentah gmsh, sudah diklasifikasi per physical group.

    Konektivitas masih memakai **tag node gmsh**; pemetaan ke indeks 0-based dilakukan
    di `mesh_model.py` (satu kali per run -- Cond A).
    """

    node_tags: np.ndarray  # (N,) int64
    node_xy: np.ndarray  # (N, 2) float64, meter
    quad_tags: np.ndarray  # (M,) int64
    quad_conn: np.ndarray  # (M, 4) int64, berisi TAG node
    quad_group: np.ndarray  # (M,) int32, indeks ke `group_names`
    group_names: tuple[str, ...]
    tri_tags: np.ndarray  # (K,) int64 -- hanya terisi bila --allow-tri
    tri_centroids: np.ndarray  # (K, 2) float64
    surface_area_by_group: dict[str, float]  # luas OCC eksak per group [m^2]
    n_surfaces: int
    effective_options: dict[str, float]
    gmsh_version: str
    warnings: tuple[str, ...] = field(default=())

    @property
    def n_quad(self) -> int:
        return int(self.quad_tags.shape[0])

    @property
    def n_tri(self) -> int:
        return int(self.tri_tags.shape[0])

    @property
    def n_nodes(self) -> int:
        return int(self.node_tags.shape[0])

    @property
    def total_surface_area(self) -> float:
        return float(sum(self.surface_area_by_group.values()))

    def element_count_by_group(self) -> dict[str, int]:
        counts = dict.fromkeys(self.group_names, 0)
        for idx in np.asarray(self.quad_group):
            counts[self.group_names[int(idx)]] += 1
        return counts


# ---------------------------------------------------------------------------
# Pembangunan entitas OCC
# ---------------------------------------------------------------------------


def _add_polygon_surface(polygon: Polygon2D) -> int:
    """Bangun plane surface dari titik-titik polygon (CCW, terbuka)."""
    occ = gmsh.model.occ
    point_tags = [occ.addPoint(float(x), float(y), 0.0) for x, y in polygon.vertices]
    line_tags = [
        occ.addLine(point_tags[i], point_tags[(i + 1) % len(point_tags)])
        for i in range(len(point_tags))
    ]
    loop = occ.addCurveLoop(line_tags)
    return int(occ.addPlaneSurface([loop]))


def _add_pier_surface(pier: Pier) -> int:
    occ = gmsh.model.occ
    if pier.shape == "polygon":
        assert pier.polygon is not None
        return _add_polygon_surface(pier.polygon)
    cx, cy = pier.centerline
    if pier.shape == "rectangular":
        assert pier.width_x is not None and pier.width_y is not None
        return int(
            occ.addRectangle(
                cx - pier.width_x / 2.0, cy - pier.width_y / 2.0, 0.0, pier.width_x, pier.width_y
            )
        )
    assert pier.diameter is not None
    radius = pier.diameter / 2.0
    return int(occ.addDisk(cx, cy, 0.0, radius, radius))


# ---------------------------------------------------------------------------
# Opsi gmsh
# ---------------------------------------------------------------------------


def _apply_and_verify_options(options: MeshOptions, surfaces: list[int]) -> dict[str, float]:
    """Set opsi gmsh, lalu BACA BALIK dan bandingkan (PRD Bagian 15.1).

    Read-back ini yang menangkap salah nama opsi atau perubahan penomoran antar versi
    gmsh -- justru kelas bug yang paling berbahaya karena tidak menghasilkan error apa pun,
    hanya mesh yang berbeda diam-diam.
    """
    expected: dict[str, float] = {
        "Mesh.Algorithm": float(options.algorithm),
        "Mesh.RecombinationAlgorithm": float(options.recombination_algorithm),
    }

    if options.size_mode == "uniform":
        expected["Mesh.MeshSizeMin"] = options.size_global
        expected["Mesh.MeshSizeMax"] = options.size_global
    else:
        locals_ = [v for v in (options.size_local_pile, options.size_local_pier) if v is not None]
        expected["Mesh.MeshSizeMin"] = min(locals_)
        expected["Mesh.MeshSizeMax"] = options.size_global

    for name, value in expected.items():
        gmsh.option.setNumber(name, value)

    # Field ukuran mesh hanya berpengaruh bila sumber ukuran lain dimatikan.
    for name in (
        "Mesh.MeshSizeFromPoints",
        "Mesh.MeshSizeFromCurvature",
        "Mesh.MeshSizeExtendFromBoundary",
    ):
        gmsh.option.setNumber(name, 0)

    mismatched = {
        name: (value, gmsh.option.getNumber(name))
        for name, value in expected.items()
        if not np.isclose(gmsh.option.getNumber(name), value, rtol=1e-12, atol=1e-15)
    }
    if mismatched:
        detail = "\n".join(
            f"    {name}: diminta {want}, terbaca {got}" for name, (want, got) in mismatched.items()
        )
        raise MeshError(
            "Opsi gmsh tidak ter-set sebagaimana diminta (read-back tidak cocok):\n"
            f"{detail}\n"
            f"  Versi gmsh terpasang: {gmsh.option.getString('General.Version')} "
            f"(dipin: {config.GMSH_VERSION_PINNED})."
        )

    if options.recombine:
        for tag in surfaces:
            gmsh.model.mesh.setRecombine(2, tag)
        _log.info("setRecombine diterapkan pada %d surface", len(surfaces))
    else:
        _log.warning(
            "mesh.recombine = false -- rekombinasi quad DIMATIKAN. Mesh akan berisi segitiga."
        )

    _log.info(
        "Opsi: Algorithm=%d | RecombinationAlgorithm=%d | MeshSize %.4f-%.4f m",
        options.algorithm,
        options.recombination_algorithm,
        expected["Mesh.MeshSizeMin"],
        expected["Mesh.MeshSizeMax"],
    )
    return expected


def _apply_graded_fields(
    options: MeshOptions, pile_surfaces: list[int], pier_surfaces: list[int]
) -> None:
    """Distance + Threshold field untuk mode `graded` (PRD Bagian 5.1(f))."""
    threshold_ids: list[int] = []
    transition = config.GRADED_TRANSITION_FACTOR * options.size_global

    for surfaces, local_size, label in (
        (pile_surfaces, options.size_local_pile, "pile"),
        (pier_surfaces, options.size_local_pier, "pier"),
    ):
        if local_size is None or not surfaces:
            continue
        curves = sorted(
            {
                abs(tag)
                for _, tag in gmsh.model.getBoundary(
                    [(2, s) for s in surfaces], oriented=False, combined=False
                )
            }
        )
        distance = gmsh.model.mesh.field.add("Distance")
        gmsh.model.mesh.field.setNumbers(distance, "CurvesList", curves)
        gmsh.model.mesh.field.setNumber(distance, "Sampling", 100)

        threshold = gmsh.model.mesh.field.add("Threshold")
        gmsh.model.mesh.field.setNumber(threshold, "InField", distance)
        gmsh.model.mesh.field.setNumber(threshold, "SizeMin", local_size)
        gmsh.model.mesh.field.setNumber(threshold, "SizeMax", options.size_global)
        gmsh.model.mesh.field.setNumber(threshold, "DistMin", 0.0)
        gmsh.model.mesh.field.setNumber(threshold, "DistMax", transition)
        threshold_ids.append(threshold)
        _log.info(
            "Refinement lokal %s: %.4f m pada %d curve, transisi %.4f m",
            label,
            local_size,
            len(curves),
            transition,
        )

    if not threshold_ids:
        raise MeshError("Mode graded diminta tetapi tidak ada field refinement yang terbentuk.")

    minimum = gmsh.model.mesh.field.add("Min")
    gmsh.model.mesh.field.setNumbers(minimum, "FieldsList", threshold_ids)
    gmsh.model.mesh.field.setAsBackgroundMesh(minimum)


# ---------------------------------------------------------------------------
# Orkestrasi
# ---------------------------------------------------------------------------


def generate_mesh(
    geom: GeometryModel,
    options: MeshOptions,
    *,
    allow_tri: bool = False,
    export_msh: Path | None = None,
    gmsh_terminal: bool = False,
) -> RawMesh:
    """Bangun geometri OCC, fragment, mesh all-quad, dan klasifikasikan per physical group."""
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 1 if gmsh_terminal else 0)
        gmsh.model.add("pilecap")
        occ = gmsh.model.occ

        cap_tag = _add_polygon_surface(geom.pilecap)
        pile_tags = [
            occ.addDisk(float(p.x), float(p.y), 0.0, p.radius, p.radius) for p in geom.piles
        ]
        pier_tags = [_add_pier_surface(pier) for pier in geom.piers]

        tools = [(2, t) for t in pile_tags] + [(2, t) for t in pier_tags]
        out_dimtags, out_map = occ.fragment([(2, cap_tag)], tools)
        occ.synchronize()
        surfaces = [tag for dim, tag in out_dimtags if dim == 2]
        _log.info("occ.fragment: %d sub-face terbentuk", len(surfaces))

        owner = _assign_groups(geom, out_map, surfaces)
        area_by_group = _create_physical_groups(owner)

        total_area = sum(area_by_group.values())
        if not np.isclose(total_area, geom.pilecap_area, rtol=config.AREA_RTOL, atol=0.0):
            raise MeshError(
                f"Jumlah luas sub-face hasil fragment = {total_area:.9f} m^2 tidak sama dengan "
                f"luas polygon pilecap = {geom.pilecap_area:.9f} m^2 "
                f"(selisih {abs(total_area - geom.pilecap_area):.3e} m^2, "
                f"rtol = {config.AREA_RTOL:g}).\n"
                "  Indikasi entitas geometri tidak menyatu (coherence gagal)."
            )
        _log.info("Cek luas: Sigma sub-face = %.6f m2 = luas pilecap  OK", total_area)

        if options.size_mode == "graded":
            # Lensa ikut dihaluskan bersama pile: ia BAGIAN dari cakram pile, dan justru di
            # tepinya (potongan pile pada muka pier) letak komponen diskretisasi yang
            # mengecil orde `h` -- lihat KNOWN_LIMITATIONS #10.
            pile_surfaces = [
                s
                for s, name in owner.items()
                if name.startswith((config.GROUP_PILE_PREFIX, config.GROUP_LENS_PREFIX))
            ]
            pier_surfaces = [
                s for s, name in owner.items() if name.startswith(config.GROUP_PIER_PREFIX)
            ]
            _apply_graded_fields(options, pile_surfaces, pier_surfaces)

        effective = _apply_and_verify_options(options, surfaces)

        gmsh.model.mesh.generate(2)
        gmsh.model.mesh.setOrder(options.element_order)

        raw = _extract_mesh(
            owner,
            area_by_group,
            len(surfaces),
            effective,
            gmsh.option.getString("General.Version"),
        )

        if export_msh is not None:
            export_msh.parent.mkdir(parents=True, exist_ok=True)
            gmsh.write(str(export_msh))
            _log.info("Mesh diekspor ke %s", export_msh)

    finally:
        gmsh.finalize()

    warnings = validators.validate_mesh_result(
        n_quad=raw.n_quad,
        n_tri=raw.n_tri,
        tri_centroids=raw.tri_centroids,
        require_all_quad=options.require_all_quad and not allow_tri,
        group_element_counts=raw.element_count_by_group(),
        total_group_area=raw.total_surface_area,
        pilecap_area=geom.pilecap_area,
        n_ungrouped=0,
    )
    for message in warnings:
        _log.warning("%s", message)

    status = "ALL-QUAD OK" if raw.n_tri == 0 else f"ADA {raw.n_tri} SEGITIGA"
    _log.info(
        "Mesh: %d node | quad = %d | tri = %d  -> %s",
        raw.n_nodes,
        raw.n_quad,
        raw.n_tri,
        status,
    )
    return replace(raw, warnings=tuple(warnings))


def _assign_groups(
    geom: GeometryModel, out_map: list[list[tuple[int, int]]], surfaces: list[int]
) -> dict[int, str]:
    """Petakan setiap sub-face hasil fragment ke satu physical group.

    `out_map[0]` adalah fragment dari objek pilecap (yang mencakup SELURUH sub-face);
    `out_map[1:]` adalah fragment dari tool, urut pile lalu pier. Prioritas klaim
    **PIER > PILE > CAP**: sub-face yang diklaim pile diklaim ulang oleh pier bila
    keduanya menunjuk sub-face yang sama.

    Perkecualian: bila pasangan (pile, pier) itu TERDAFTAR di `geom.overlaps` -- artinya
    user sudah mengizinkannya lewat `pier.max_pile_overlap_fraction` -- sub-face irisannya
    menjadi group LENSA tersendiri, bukan milik pier maupun pile. Lensa itulah yang nanti
    ikut dibebani (bersama pile) sekaligus ikut dijepit (bersama pier).

    `MeshError` di bawah TETAP berlaku untuk klaim ganda yang TIDAK terdaftar: selain
    menjadi jaring pengaman rule 14, ia kini juga menangkap ketidakcocokan antara irisan
    versi shapely (yang dipakai validator) dan versi OCC (yang dipakai mesher).
    """
    owner: dict[int, str] = {}
    lensa = {(o.pile_id, o.pier_id): o.lens_group_name for o in geom.overlaps}

    n_piles = len(geom.piles)
    pemilik_pile: dict[int, str] = {}
    for i, pile in enumerate(geom.piles):
        for _, tag in out_map[1 + i]:
            owner[tag] = pile.group_name
            pemilik_pile[tag] = pile.pile_id

    for j, pier in enumerate(geom.piers):
        for _, tag in out_map[1 + n_piles + j]:
            previous = owner.get(tag)
            if previous is not None and previous != pier.group_name:
                nama_lensa = lensa.get((pemilik_pile.get(tag, ""), pier.pier_id))
                if nama_lensa is None:
                    raise MeshError(
                        f"Sub-face {tag} diklaim oleh {previous} dan {pier.group_name} "
                        "sekaligus. Area pier dan pile bertumpang tindih tanpa terdaftar di "
                        "`geom.overlaps` (seharusnya sudah tertangkap validators rule 14)."
                    )
                owner[tag] = nama_lensa
                continue
            owner[tag] = pier.group_name

    for tag in surfaces:
        owner.setdefault(tag, config.GROUP_CAP)

    return owner


def _create_physical_groups(owner: dict[int, str]) -> dict[str, float]:
    """Daftarkan physical group per nama dan kembalikan luas OCC eksak tiap group."""
    by_name: dict[str, list[int]] = {}
    for tag, name in owner.items():
        by_name.setdefault(name, []).append(tag)

    areas: dict[str, float] = {}
    for name, tags in sorted(by_name.items()):
        group = gmsh.model.addPhysicalGroup(2, sorted(tags))
        gmsh.model.setPhysicalName(2, group, name)
        areas[name] = float(sum(gmsh.model.occ.getMass(2, t) for t in tags))
    _log.debug("Physical group: %s", {k: len(v) for k, v in sorted(by_name.items())})
    return areas


def _extract_mesh(
    owner: dict[int, str],
    area_by_group: dict[str, float],
    n_surfaces: int,
    effective_options: dict[str, float],
    gmsh_version: str,
) -> RawMesh:
    """Ambil node & elemen dari gmsh (in-memory, tanpa file perantara)."""
    node_tags_raw, node_coords, _ = gmsh.model.mesh.getNodes()
    node_tags = np.asarray(node_tags_raw, dtype=np.int64)
    node_xyz = np.asarray(node_coords, dtype=np.float64).reshape(-1, 3)
    node_xy = node_xyz[:, :2].copy()

    tag_to_xy = {int(t): node_xy[i] for i, t in enumerate(node_tags)}

    group_names = tuple(sorted(set(owner.values())))
    group_index = {name: i for i, name in enumerate(group_names)}

    quad_tags: list[int] = []
    quad_conn: list[list[int]] = []
    quad_group: list[int] = []
    tri_tags: list[int] = []
    tri_centroids: list[list[float]] = []

    for surface_tag, group_name in sorted(owner.items()):
        etypes, etags, enodes = gmsh.model.mesh.getElements(2, surface_tag)
        for etype, tags, nodes in zip(etypes, etags, enodes, strict=True):
            if int(etype) == config.GMSH_ELEMTYPE_QUAD:
                conn = np.asarray(nodes, dtype=np.int64).reshape(-1, 4)
                quad_tags.extend(int(t) for t in tags)
                quad_conn.extend(conn.tolist())
                quad_group.extend([group_index[group_name]] * len(tags))
            elif int(etype) == config.GMSH_ELEMTYPE_TRIANGLE:
                conn = np.asarray(nodes, dtype=np.int64).reshape(-1, 3)
                tri_tags.extend(int(t) for t in tags)
                for row in conn:
                    pts = np.array([tag_to_xy[int(t)] for t in row])
                    tri_centroids.append(pts.mean(axis=0).tolist())
            else:
                raise MeshError(
                    f"Tipe elemen gmsh tak terduga pada surface {surface_tag}: {int(etype)}. "
                    "Hanya quad (3) dan triangle (2) yang ditangani."
                )

    return RawMesh(
        node_tags=node_tags,
        node_xy=node_xy,
        quad_tags=np.asarray(quad_tags, dtype=np.int64),
        quad_conn=np.asarray(quad_conn, dtype=np.int64).reshape(-1, 4),
        quad_group=np.asarray(quad_group, dtype=np.int32),
        group_names=group_names,
        tri_tags=np.asarray(tri_tags, dtype=np.int64),
        tri_centroids=np.asarray(tri_centroids, dtype=np.float64).reshape(-1, 2),
        surface_area_by_group=area_by_group,
        n_surfaces=n_surfaces,
        effective_options=effective_options,
        gmsh_version=gmsh_version,
    )
