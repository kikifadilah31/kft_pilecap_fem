"""Perkakas bersama untuk validation case VC-0..VC-5 (PRD Bagian 8.1).

Berisi:
  * pembangun mesh terstruktur dengan orientasi yang DIKETAHUI PERSIS,
  * pembangun mesh gmsh all-quad pada persegi panjang polos (orientasi elemen
    tersebar -- inilah yang membuat VC-2 bermakna),
  * strategi tumpuan & pembebanan khusus validasi.

Strategi khusus di bawah adalah bukti bahwa abstraksi `SupportStrategy` /
`PileLoadStrategy` di `fem_engine` memang dapat diperluas tanpa membongkar modul.
"""

from __future__ import annotations

from dataclasses import dataclass

import gmsh
import numpy as np
import openseespy.opensees as ops

from pilecap_fem import config, fem_engine, math_engine, mesh_model
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel

# ---------------------------------------------------------------------------
# Pembangun mesh
# ---------------------------------------------------------------------------


def structured_plate(
    Lx: float, Ly: float, nx: int, ny: int, *, angle: float = 0.0, shift: int = 0
) -> MeshModel:
    """Grid quad terstruktur, opsional diputar `angle` [rad] terhadap titik asal.

    `shift` menggeser titik awal konektivitas tiap elemen (0..3), sehingga sumbu lokal
    elemen berputar kelipatan 90 derajat tanpa mengubah geometri fisiknya.
    """
    xs = np.linspace(0.0, Lx, nx + 1)
    ys = np.linspace(0.0, Ly, ny + 1)
    grid_x, grid_y = np.meshgrid(xs, ys)
    flat = np.column_stack([grid_x.ravel(), grid_y.ravel()])

    if angle:
        c, s = np.cos(angle), np.sin(angle)
        rotation = np.array([[c, -s], [s, c]])
        flat = flat @ rotation.T

    def index(i: int, j: int) -> int:
        return j * (nx + 1) + i

    conn = []
    for j in range(ny):
        for i in range(nx):
            nodes = [index(i, j), index(i + 1, j), index(i + 1, j + 1), index(i, j + 1)]
            conn.append(nodes[shift:] + nodes[:shift])

    return mesh_model.from_arrays(flat, np.array(conn, dtype=np.int64))


def gmsh_plate(Lx: float, Ly: float, h: float, *, disk_radius: float = 0.0) -> MeshModel:
    """Persegi panjang di-mesh all-quad dengan opsi produksi (Algorithm 11).

    `disk_radius > 0` menambahkan **partisi lingkaran internal** di tengah pelat --
    persis seperti area pile pada model sungguhan. Partisi itu tidak mengubah geometri
    fisik pelat (luas dan tepinya tetap sama, mesh tetap konform menutupi seluruh
    persegi panjang), tetapi MEMAKSA orientasi elemen di sekelilingnya tersebar.

    Itulah yang membuat VC-2 menguji transformasi tensor secara sungguhan: pada
    persegi panjang polos, Algorithm 11 menghasilkan grid yang praktis sejajar sumbu
    sehingga `m12` lokal nol di mana-mana dan suku `m12` pada transformasi tidak
    teruji sama sekali.
    """
    gmsh.initialize()
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("plate")
        rect = gmsh.model.occ.addRectangle(0.0, 0.0, 0.0, Lx, Ly)
        if disk_radius > 0.0:
            disk = gmsh.model.occ.addDisk(Lx / 2, Ly / 2, 0.0, disk_radius, disk_radius)
            out, _ = gmsh.model.occ.fragment([(2, rect)], [(2, disk)])
            surfaces = [tag for dim, tag in out if dim == 2]
        else:
            surfaces = [rect]
        gmsh.model.occ.synchronize()
        gmsh.option.setNumber("Mesh.Algorithm", config.GMSH_ALGORITHM_DEFAULT)
        gmsh.option.setNumber("Mesh.RecombinationAlgorithm", config.GMSH_RECOMB_ALGORITHM_DEFAULT)
        gmsh.option.setNumber("Mesh.MeshSizeMin", h)
        gmsh.option.setNumber("Mesh.MeshSizeMax", h)
        for tag in surfaces:
            gmsh.model.mesh.setRecombine(2, tag)
        gmsh.model.mesh.generate(2)

        tags, coords, _ = gmsh.model.mesh.getNodes()
        node_tags = np.asarray(tags, dtype=np.int64)
        node_xy = np.asarray(coords, dtype=np.float64).reshape(-1, 3)[:, :2]

        blocks = []
        for tag in surfaces:
            etypes, _, enodes = gmsh.model.mesh.getElements(2, tag)
            for etype, nodes in zip(etypes, enodes, strict=True):
                if int(etype) == config.GMSH_ELEMTYPE_QUAD:
                    blocks.append(np.asarray(nodes, dtype=np.int64).reshape(-1, 4))
                elif int(etype) == config.GMSH_ELEMTYPE_TRIANGLE:
                    raise AssertionError("gmsh_plate menghasilkan segitiga -- harus all-quad")
        assert blocks, "gmsh_plate tidak menghasilkan elemen quad"
        quad = np.vstack(blocks)
    finally:
        gmsh.finalize()

    lookup = {int(t): i for i, t in enumerate(node_tags)}
    conn = np.vectorize(lookup.__getitem__)(quad).astype(np.int64)
    return mesh_model.from_arrays(node_xy, conn, node_tags=node_tags)


# ---------------------------------------------------------------------------
# Strategi khusus validasi
# ---------------------------------------------------------------------------


@dataclass
class EdgeSupport:
    """Tumpuan sederhana (UZ) pada dua tepi yang tegak lurus arah bentang.

    Sengaja TIDAK menahan rotasi: kasus ini harus tetap statis tertentu sehingga
    momennya mengikuti kesetimbangan saja, tanpa perlu koefisien dari buku mana pun.
    """

    span_axis: int = 0
    span_start: float = 0.0
    span_end: float = 4.0
    tol: float = 1e-6

    def apply(self, mesh: MeshModel, geom: GeometryModel | None = None) -> np.ndarray:
        along = mesh.node_xy[:, self.span_axis]
        on_edge = (np.abs(along - self.span_start) < self.tol) | (
            np.abs(along - self.span_end) < self.tol
        )
        indices = np.where(on_edge)[0]
        if indices.size == 0:
            raise AssertionError("Tidak ada node di tepi tumpuan -- periksa toleransi.")

        # Mask dikumpulkan dulu: OpenSees menolak SP_Constraint ganda pada DOF yang sama.
        masks = {int(i): [0, 0, 1, 0, 0, 0] for i in indices}
        edge_sorted = sorted(masks, key=lambda i: tuple(mesh.node_xy[i]))
        masks[edge_sorted[0]][0] = 1
        masks[edge_sorted[0]][1] = 1
        masks[edge_sorted[-1]][1] = 1
        for index, dofs in masks.items():
            ops.fix(index + 1, *dofs)
        return np.array(sorted(masks), dtype=np.int64)


@dataclass
class UniformPressure:
    """Tekanan merata pada SELURUH elemen. `pressure` positif = ke atas (+Z)."""

    pressure: float

    def apply(
        self, mesh: MeshModel, geom: GeometryModel | None = None, pz_by_pile: dict | None = None
    ) -> tuple[np.ndarray, tuple]:
        coords = mesh.node_xy[mesh.elem_conn]
        factors = fem_engine.consistent_quad_load_factors(coords)
        nodal = np.zeros(mesh.n_nodes, dtype=np.float64)
        np.add.at(nodal, mesh.elem_conn.ravel(), (self.pressure * factors).ravel())
        return nodal, ()


# ---------------------------------------------------------------------------
# Integrasi hasil
# ---------------------------------------------------------------------------


def integrate_column(
    mesh: MeshModel, values: np.ndarray, *, cut_axis: int, cut_position: float, h: float
) -> tuple[float, float, int]:
    """Integrasikan `values` pada satu kolom elemen di garis potong.

    Kembalikan (total, posisi kolom aktual, jumlah elemen).
    """
    coords = mesh.node_xy[mesh.elem_conn]
    mask = math_engine.select_elements_crossing_cut(
        coords, cut_axis=cut_axis, cut_position=cut_position
    )
    widths = math_engine.cut_element_widths(
        coords, mesh.elem_area, cut_axis=cut_axis, cut_position=cut_position
    )
    total = math_engine.integrate_strip(values, widths, mask)
    actual = math_engine.cut_column_position(mesh.elem_centroid, mask, cut_axis)
    return total, actual, int(mask.sum())


def elastic_material(
    E: float = 25e9, nu: float = 0.0, t: float = 0.1
) -> fem_engine.MaterialProperties:
    return fem_engine.MaterialProperties(E=E, nu=nu, thickness=t, E_source="validation case")
