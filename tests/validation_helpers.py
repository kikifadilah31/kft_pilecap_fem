"""Perkakas bersama untuk validation case VC-0..VC-5 (PRD Bagian 8.1).

Berisi:
  * pembangun mesh terstruktur dengan orientasi yang DIKETAHUI PERSIS,
  * pembangun mesh gmsh all-quad pada persegi panjang polos (orientasi elemen
    tersebar -- inilah yang membuat VC-2 bermakna),
  * strategi tumpuan & pembebanan khusus validasi,
  * pembaca ekspor Midas Civil beserta rekonsiliasi konvensinya (VC-6).

Strategi khusus di bawah adalah bukti bahwa abstraksi `SupportStrategy` /
`PileLoadStrategy` di `fem_engine` memang dapat diperluas tanpa membongkar modul.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import gmsh
import numpy as np
import openseespy.opensees as ops
import pandas as pd

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
        self,
        mesh: MeshModel,
        geom: GeometryModel | None = None,
        pz_by_pile: dict | None = None,
        fixed_nodes: np.ndarray | None = None,
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


# ---------------------------------------------------------------------------
# Pembaca ekspor Midas Civil (VC-6)
# ---------------------------------------------------------------------------
#
# Seluruh keanehan format yang ditangani di bawah terdokumentasi beserta buktinya di
# `tests/data/vc6/SUMBER.md`. Ringkasnya: berkas ber-BOM UTF-8, memakai U+00B7 pada
# `kN·m/m`, punya kolom `Angle([deg])` ganda, dan berkas reaksi menyisipkan baris teks
# beserta blok TOTAL tanpa nomor node.

#: Nama kolom momen & geser pada ekspor resultan. `·` di sini U+00B7, BUKAN titik ASCII --
#: mengetiknya sebagai titik biasa membuat seluruh pembacaan gagal dengan `KeyError`.
MIDAS_MOMENT_COLUMNS = ("Mxx(kN\u00b7m/m)", "Myy(kN\u00b7m/m)", "Mxy(kN\u00b7m/m)")
MIDAS_SHEAR_COLUMNS = ("Vxx(kN/m)", "Vyy(kN/m)")

#: Konvensi geser melintang Midas berlawanan dengan konvensi PRD Bagian 7.1.
#:
#: BUKAN faktor penyetel. Diukur pada SELURUH elemen ketiga contoh x dua kombinasi: rasio
#: `-q_midas / q_kami` tidak menyimpang tandanya pada satu pun dari ~5.500 elemen. Yang
#: menguatkan: pembalikan ini tetap muncul pada ekspor sumbu GLOBAL, yang tidak melewati
#: rotasi apa pun -- jadi ia sifat Midas, bukan artefak aritmetika kita. Momen tidak ikut
#: dibalik. Lihat SUMBER.md Bagian 4.1.
MIDAS_SHEAR_SIGN = -1.0

_KN = 1e3  # kN -> N, dan kNm/m -> Nm/m


def _read_midas_csv(path: Path) -> pd.DataFrame:
    """Baca CSV ekspor Midas apa adanya, hanya menangani BOM dan spasi nama kolom."""
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def load_midas_centroid(path: Path, combo_slug: str) -> pd.DataFrame:
    """Resultan elemen Midas pada CENTROID, terindeks `elem_tag` dan terurut.

    Ekspor memuat 5 baris per elemen per kombinasi: satu `Node=Cent` diikuti 4 baris per
    simpul sudut. Hanya baris centroid yang sebanding dengan resultan kami, yang memang
    satu nilai per elemen.
    """
    frame = _read_midas_csv(path)
    rows = frame[
        (frame["Node"].astype(str).str.strip() == "Cent")
        & (frame["Load"].astype(str).str.strip() == combo_slug)
    ].copy()
    if rows.empty:
        raise ValueError(
            f"{path.name} tidak memuat baris centroid untuk kombinasi {combo_slug!r}. "
            f"Kombinasi yang ada: {sorted(frame['Load'].astype(str).str.strip().unique())}"
        )
    rows["Elem"] = rows["Elem"].astype(int)
    return rows.set_index("Elem").sort_index()


def midas_resultants_si(rows: pd.DataFrame) -> dict[str, np.ndarray]:
    """Momen & geser Midas dalam SI, tanda geser SUDAH direkonsiliasi.

    Dipakai untuk ekspor sumbu GLOBAL, sehingga hasilnya langsung sebanding dengan
    `m_xx/m_yy/m_xy/q_x/q_y` milik `postproc_engine` tanpa rotasi apa pun.
    """
    m_xx, m_yy, m_xy = (rows[c].to_numpy(dtype=np.float64) * _KN for c in MIDAS_MOMENT_COLUMNS)
    v_xx, v_yy = (rows[c].to_numpy(dtype=np.float64) * _KN for c in MIDAS_SHEAR_COLUMNS)
    return {
        "m_xx": m_xx,
        "m_yy": m_yy,
        "m_xy": m_xy,
        "q_x": MIDAS_SHEAR_SIGN * v_xx,
        "q_y": MIDAS_SHEAR_SIGN * v_yy,
    }


def rotate_moment_tensor(
    rows: pd.DataFrame, theta: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Putar tensor momen Midas dari sumbu LOKAL ke sumbu global, sudut `theta` [rad].

    Dipakai HANYA untuk cek-silang: hasilnya dibandingkan dengan ekspor global Midas
    sendiri. Bila keduanya cocok, terbukti `theta` kami adalah sudut sumbu material yang
    sama dengan yang dipakai Midas DAN rumus rotasi kami sama dengan rumusnya.
    """
    m_11, m_22, m_12 = (rows[c].to_numpy(dtype=np.float64) for c in MIDAS_MOMENT_COLUMNS)
    cos, sin = np.cos(theta), np.sin(theta)
    m_xx = m_11 * cos**2 + m_22 * sin**2 - 2.0 * m_12 * sin * cos
    m_yy = m_11 * sin**2 + m_22 * cos**2 + 2.0 * m_12 * sin * cos
    m_xy = (m_11 - m_22) * sin * cos + m_12 * (cos**2 - sin**2)
    return m_xx, m_yy, m_xy


def midas_nodal(path: Path, combo_slug: str) -> tuple[str, pd.DataFrame]:
    """Baca ekspor per-node; kembalikan `("displacement"|"reaction", tabel)`.

    Jenisnya ditentukan DARI HEADER, bukan dari nama berkas. Arsip yang disediakan memuat
    satu berkas bernama `*_output_displacement.csv` yang isinya justru reaksi (lihat
    SUMBER.md Bagian 5.1); menebak dari nama berarti membandingkan besaran yang sama
    sekali berbeda tanpa satu pun tanda. Header yang tidak dikenal DITOLAK, tidak ditebak.

    Baris non-numerik (`SUMMATION OF REACTION FORCES PRINTOUT`) dan blok TOTAL yang
    kolom `Node`-nya kosong ikut disaring.
    """
    frame = _read_midas_csv(path)
    if "DZ(m)" in frame.columns:
        jenis = "displacement"
    elif "FZ(kN)" in frame.columns:
        jenis = "reaction"
    else:
        raise ValueError(
            f"{path.name}: header tidak dikenali sebagai lendutan (`DZ(m)`) maupun reaksi "
            f"(`FZ(kN)`). Kolom yang ada: {list(frame.columns)}"
        )

    node = pd.to_numeric(frame["Node"], errors="coerce")
    rows = frame[node.notna() & (frame["Load"].astype(str).str.strip() == combo_slug)].copy()
    rows["Node"] = node[rows.index].astype(int)
    return jenis, rows.set_index("Node").sort_index()


def midas_max_translation(path: Path) -> tuple[float, ...]:
    """`MAXIMUM TRANSLATION` [m] per subcase dari `.log`, URUT sesuai `*STLDCASE`.

    Urutannya dijamin oleh `midas_solver.out`, yang mencetak `SUBCASE : <nama>` dengan
    urutan yang sama.
    """
    nilai: list[float] = []
    for baris in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "MAXIMUM TRANSLATION" not in baris:
            continue
        potong = baris.split("MAXIMUM TRANSLATION", 1)[1].split(":", 1)[1]
        nilai.append(abs(float(potong.split("(")[0].strip())))
    if not nilai:
        raise ValueError(f"{path.name} tidak memuat satu pun baris MAXIMUM TRANSLATION")
    return tuple(nilai)
