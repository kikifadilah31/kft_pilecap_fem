"""Data model mesh -- compute once, lookup selamanya (PRD Cond A).

Topologi, luas, centroid, dan orientasi elemen dihitung SEKALI per run lalu di-lookup
untuk seluruh kombinasi pembebanan. Untuk mesh 5.000-50.000 elemen, menghitung ulang
per kombinasi berarti kerja O(N x n_combo) yang sepenuhnya mubazir.

Seluruh perhitungan di sini vektor (NumPy), tanpa loop Python per elemen (Core 9).
Satuan: SI (meter, m^2, radian).
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from pilecap_fem import config
from pilecap_fem.mesh_engine import RawMesh

_log = config.get_logger("mesh_model")


@dataclass(frozen=True, eq=False)
class MeshModel:
    """Mesh siap pakai untuk FEM dan post-processing.

    Konektivitas memakai **indeks 0-based ke `node_xy`**, bukan tag gmsh. Tag asli
    disimpan di `node_tags` / `elem_tags` untuk penelusuran ke file `.msh`.
    """

    node_tags: np.ndarray  # (N,) int64 -- tag gmsh
    node_xy: np.ndarray  # (N, 2) float64 [m]
    elem_tags: np.ndarray  # (M,) int64 -- tag gmsh
    elem_conn: np.ndarray  # (M, 4) int64 -- indeks 0-based ke node_xy
    elem_area: np.ndarray  # (M,) float64 [m^2]
    elem_centroid: np.ndarray  # (M, 2) float64 [m]
    elem_theta: np.ndarray  # (M,) float64 [rad] -- lihat catatan di bawah
    elem_group: np.ndarray  # (M,) int32 -- indeks ke group_names
    group_names: tuple[str, ...]

    # -- properti dasar ----------------------------------------------------

    @property
    def n_nodes(self) -> int:
        return int(self.node_xy.shape[0])

    @property
    def n_elements(self) -> int:
        return int(self.elem_conn.shape[0])

    @property
    def total_mesh_area(self) -> float:
        """Jumlah luas SELURUH elemen mesh [m^2].

        Nilai ini sedikit berbeda dari luas polygon eksak untuk area lengkung (lingkaran
        pile terdiskretisasi). Untuk cek "tidak ada elemen hilang" gunakan luas OCC di
        `RawMesh.surface_area_by_group`; nilai ini dipakai untuk perhitungan beban
        (PRD Bagian 7.3).
        """
        return float(self.elem_area.sum())

    @property
    def area_uniformity_cv(self) -> float:
        """`std(A_e) / mean(A_e)` atas SELURUH elemen (PRD Bagian 15.1).

        Nilai ini selalu tinggi (0.35-0.45 pada ketiga contoh) karena didominasi cincin
        elemen transisi di sekeliling disk pile dan tepi pier: batas lengkung memaksa
        elemen yang lebih kecil, berapa pun ukuran target. Untuk menilai keseragaman mesh
        gunakan `area_uniformity_cv_cap`.
        """
        return _cv(self.elem_area)

    @property
    def area_uniformity_cv_cap(self) -> float:
        """`std/mean` luas elemen pada group CAP saja -- kriteria keseragaman yang dipakai.

        Group CAP adalah bagian pelat yang jauh dari batas lengkung, sehingga inilah yang
        benar-benar mencerminkan apakah mesh mode `uniform` menghasilkan elemen seragam.
        Dipakai sebagai kriteria test (PRD Bagian 15.1 & Bagian 17 item 15).
        """
        if config.GROUP_CAP not in self.group_names:
            return float("nan")
        return _cv(self.elem_area[self.group_mask(config.GROUP_CAP)])

    # -- lookup group (O(1) setelah dibangun) ------------------------------

    def group_index(self, name: str) -> int:
        try:
            return self.group_names.index(name)
        except ValueError as exc:
            raise KeyError(
                f"Physical group {name!r} tidak ada. Tersedia: {list(self.group_names)}"
            ) from exc

    def group_mask(self, name: str) -> np.ndarray:
        """Mask boolean elemen yang termasuk physical group `name`."""
        return np.asarray(self.elem_group == self.group_index(name), dtype=bool)

    def group_area(self, name: str) -> float:
        """Jumlah luas elemen mesh dalam satu group [m^2].

        Inilah `A_disk` yang dipakai `fem_engine` untuk menghitung tekanan pile
        (PRD Bagian 7.3): memakai jumlah luas elemen -- bukan pi*r^2 analitis --
        menjamin Sigma(p x A_e) persis sama dengan P_z.
        """
        return float(self.elem_area[self.group_mask(name)].sum())

    def group_element_counts(self) -> dict[str, int]:
        counts = np.bincount(self.elem_group, minlength=len(self.group_names))
        return {name: int(counts[i]) for i, name in enumerate(self.group_names)}

    def nodes_in_group(self, name: str) -> np.ndarray:
        """Indeks node unik yang menjadi simpul elemen-elemen suatu group.

        Dipakai `fem_engine` untuk menjepit seluruh node area pier (PRD Bagian 3.2).
        """
        return np.unique(self.elem_conn[self.group_mask(name)].ravel())

    def pile_groups(self) -> tuple[str, ...]:
        return tuple(n for n in self.group_names if n.startswith(config.GROUP_PILE_PREFIX))

    def pier_groups(self) -> tuple[str, ...]:
        return tuple(n for n in self.group_names if n.startswith(config.GROUP_PIER_PREFIX))

    # -- ekspor ------------------------------------------------------------

    def write_nodes_csv(self, path: Path) -> None:
        """`nodes.csv` -- tag, x, y, z dalam SI (PRD Bagian 9.1 & 9.2)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["node_tag", "x [m]", "y [m]", "z [m]"])
            for tag, (x, y) in zip(self.node_tags, self.node_xy, strict=True):
                writer.writerow([int(tag), f"{x:.9f}", f"{y:.9f}", "0.000000000"])

    def write_elements_csv(self, path: Path) -> None:
        """`elements.csv` -- tag, n1..n4 (tag node), luas, theta, group."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(
                [
                    "elem_tag",
                    "n1",
                    "n2",
                    "n3",
                    "n4",
                    "area [m^2]",
                    "centroid_x [m]",
                    "centroid_y [m]",
                    "theta [deg]",
                    "group",
                ]
            )
            node_tag_of = self.node_tags
            for i in range(self.n_elements):
                conn = self.elem_conn[i]
                writer.writerow(
                    [
                        int(self.elem_tags[i]),
                        *(int(node_tag_of[j]) for j in conn),
                        f"{self.elem_area[i]:.9e}",
                        f"{self.elem_centroid[i, 0]:.9f}",
                        f"{self.elem_centroid[i, 1]:.9f}",
                        f"{np.degrees(self.elem_theta[i]):.6f}",
                        self.group_names[int(self.elem_group[i])],
                    ]
                )


# ---------------------------------------------------------------------------
# Perhitungan vektor
# ---------------------------------------------------------------------------


def _cv(values: np.ndarray) -> float:
    """Koefisien variasi `std/mean`. NaN bila kosong atau rata-ratanya nol."""
    if values.size == 0:
        return float("nan")
    mean = float(values.mean())
    return float(values.std() / mean) if mean > 0.0 else float("nan")


def _quad_areas_and_centroids(coords: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Luas (shoelace) dan centroid geometris untuk (M, 4, 2) koordinat quad.

    Luas dikembalikan sebagai nilai absolut agar tidak bergantung pada orientasi
    penomoran node yang dihasilkan gmsh.
    """
    x = coords[:, :, 0]
    y = coords[:, :, 1]
    x_next = np.roll(x, -1, axis=1)
    y_next = np.roll(y, -1, axis=1)

    cross = x * y_next - x_next * y
    signed = 0.5 * cross.sum(axis=1)
    area = np.abs(signed)

    with np.errstate(divide="ignore", invalid="ignore"):
        cx = np.sum((x + x_next) * cross, axis=1) / (6.0 * signed)
        cy = np.sum((y + y_next) * cross, axis=1) / (6.0 * signed)

    degenerate = area <= 0.0
    if degenerate.any():
        cx = np.where(degenerate, x.mean(axis=1), cx)
        cy = np.where(degenerate, y.mean(axis=1), cy)

    return area, np.stack([cx, cy], axis=1)


def _shell_local_x_angle(coords: np.ndarray) -> np.ndarray:
    """Sudut sumbu lokal-x elemen shell terhadap sumbu global X [rad].

    Sumbu lokal ShellMITC4 dibentuk dari geometri elemen, bukan dari satu sisi saja:

        v1 = 0.5 * (r2 + r3 - r1 - r4)

    yaitu arah RATA-RATA sisi node1->node2 dan node4->node3. Ini berbeda dari
    penyederhanaan "local-x ~ arah node1->node2" yang tertulis di PRD Bagian 7.2(3),
    dan bedanya nyata untuk quad yang tidak persegi.

    .. warning::
       **Nilai ini BELUM diverifikasi terhadap OpenSees.** Rumus di atas diambil dari
       konstruksi basis elemen ShellMITC4, tetapi PRD Bagian 7.1 melarang menebak
       konvensi tanpa bukti. Sampai **VC-2** (invariansi orientasi mesh, PRD Bagian 8.1)
       dijalankan pada Fase 2 dan terbukti, `postproc_engine` TIDAK boleh memakai theta
       ini untuk menghasilkan momen desain.
    """
    v1 = 0.5 * (coords[:, 1, :] + coords[:, 2, :] - coords[:, 0, :] - coords[:, 3, :])
    return np.asarray(np.arctan2(v1[:, 1], v1[:, 0]), dtype=np.float64)


def build_mesh_model(raw: RawMesh) -> MeshModel:
    """Bangun `MeshModel` dari hasil mentah gmsh. Dipanggil SEKALI per run (Cond A)."""
    tag_to_index = {int(tag): i for i, tag in enumerate(raw.node_tags)}
    try:
        conn = np.vectorize(tag_to_index.__getitem__)(raw.quad_conn).astype(np.int64)
    except KeyError as exc:  # pragma: no cover - hanya bila gmsh tidak konsisten
        raise KeyError(f"Elemen merujuk tag node yang tidak ada di daftar node: {exc}") from exc

    coords = raw.node_xy[conn]  # (M, 4, 2)
    area, centroid = _quad_areas_and_centroids(coords)
    theta = _shell_local_x_angle(coords)

    model = MeshModel(
        node_tags=raw.node_tags,
        node_xy=raw.node_xy,
        elem_tags=raw.quad_tags,
        elem_conn=conn,
        elem_area=area,
        elem_centroid=centroid,
        elem_theta=theta,
        elem_group=raw.quad_group,
        group_names=raw.group_names,
    )

    counts = model.group_element_counts()
    pile_counts = [counts[n] for n in model.pile_groups()]
    pier_counts = [counts[n] for n in model.pier_groups()]
    if pile_counts:
        _log.info(
            "Group CAP: %d elemen | PILE (%d group): %d-%d elemen | PIER (%d group): %d-%d elemen",
            counts.get(config.GROUP_CAP, 0),
            len(pile_counts),
            min(pile_counts),
            max(pile_counts),
            len(pier_counts),
            min(pier_counts, default=0),
            max(pier_counts, default=0),
        )
    _log.info(
        "Keseragaman elemen: std/mean luas = %.3f (CAP saja %.3f, ambang test %.2f)",
        model.area_uniformity_cv,
        model.area_uniformity_cv_cap,
        config.MESH_UNIFORMITY_MAX_CV,
    )
    return model
