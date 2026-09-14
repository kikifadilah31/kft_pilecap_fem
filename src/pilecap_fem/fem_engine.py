"""Model & analisis FEM di OpenSeesPy (PRD Bagian 3.2, 7.3, 8.1).

Tumpuan dan pembebanan dipisahkan menjadi **strategi eksplisit** (`SupportStrategy`,
`LoadStrategy`). v1.0 hanya punya satu implementasi masing-masing -- pier jepit dan pile
sebagai beban -- tetapi skema alternatif yang mungkin dibutuhkan kelak (pile sebagai
PEGAS, pier sebagai BEBAN; PRD Bagian 17 item 11) cukup menambah satu kelas, bukan
membongkar modul ini.

.. rubric:: Penerapan beban tekanan pile

PRD Bagian 7.3(a) menuliskan tekanan pile diterapkan lewat ``eleLoad``. **Diukur pada
openseespy 3.8.0.0: ShellMITC4 MENOLAK seluruh tipe eleLoad** (`-surfaceLoad`,
`-shellSurface`, `-beamUniform`, `-Pressure`) dengan pesan
``ShellMITC4::addLoad() - ele ... does not deal with load type: 9``, dan Sigma reaksi
tetap NOL. Karena itu tekanan diterapkan sebagai **beban nodal** dari tekanan yang sama:

.. math:: p_i = \\frac{P_{z,i}}{A_{disk,i}}, \\qquad A_{disk,i} = \\sum_{e \\in PILE_i} A_e

Matematika PRD dipakai persis; hanya jalur penerapannya yang berbeda. Karena
``A_disk`` diambil dari **jumlah luas elemen mesh** (bukan pi r^2 analitis) dan kedua
skema distribusi menjaga :math:`\\sum f_i = p A_e` per elemen, total beban selalu
**persis** sama dengan :math:`P_z` -- itulah yang membuat VC-0 eksak.

Seluruh modul bekerja murni SI (N, m, Pa).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np
import openseespy.opensees as ops

from pilecap_fem import config, math_engine
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel
from pilecap_fem.validators import AnalysisError, InputError

_log = config.get_logger("fem_engine")

#: Titik Gauss 2x2 pada koordinat natural.
_GAUSS_1D = (-1.0 / np.sqrt(3.0), 1.0 / np.sqrt(3.0))

SUPPORTED_SHELL_ELEMENTS = ("ShellMITC4", "ShellDKGQ", "ShellNLDKGQ")
SUPPORTED_SECTIONS = ("PlateFiber", "LayeredShell")


# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaterialProperties:
    """Properti material dalam SI. `E` WAJIB berasal dari user (PRD Bagian 7.4)."""

    E: float
    nu: float
    thickness: float
    density: float = 0.0
    E_source: str = ""

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> MaterialProperties:
        material = cfg["material"]
        return cls(
            E=float(material["E"]),
            nu=float(material["poisson"]),
            thickness=float(cfg["pilecap"]["thickness"]),
            density=float(material.get("density") or 0.0),
            E_source=str(material.get("E_source", "")),
        )

    @property
    def flexural_rigidity(self) -> float:
        return math_engine.plate_flexural_rigidity(self.E, self.thickness, self.nu)


@dataclass(frozen=True)
class AnalysisOptions:
    shell_element: str = "ShellMITC4"
    section: str = "PlateFiber"
    n_layers: int = 10
    include_self_weight: bool = False
    equilibrium_rtol: float = config.EQUILIBRIUM_RTOL_DEFAULT

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> AnalysisOptions:
        analysis = cfg.get("analysis") or {}
        return cls(
            shell_element=analysis.get("shell_element", "ShellMITC4"),
            section=analysis.get("section", "PlateFiber"),
            n_layers=int(analysis.get("n_layers", 10)),
            include_self_weight=bool(analysis.get("include_self_weight", False)),
        )

    def validate(self) -> None:
        if self.shell_element not in SUPPORTED_SHELL_ELEMENTS:
            raise InputError(
                f"`analysis.shell_element` = {self.shell_element!r} tidak dikenal. "
                f"Pilihan: {list(SUPPORTED_SHELL_ELEMENTS)}."
            )
        if self.section not in SUPPORTED_SECTIONS:
            raise InputError(
                f"`analysis.section` = {self.section!r} tidak dikenal. "
                f"Pilihan: {list(SUPPORTED_SECTIONS)}."
            )
        if self.section == "LayeredShell" and self.n_layers < 2:
            raise InputError(f"`analysis.n_layers` = {self.n_layers} harus >= 2.")


# ---------------------------------------------------------------------------
# Hasil
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PileLoadTrace:
    """Jejak pembebanan satu pile -- baris tabel Bagian 3 `calc_sheet.md`."""

    pile_id: str
    pz: float
    a_disk_mesh: float
    a_disk_nominal: float
    pressure: float
    n_elements: int
    applied_total: float
    #: Luas bagian cakram di dalam footprint pier [m^2]; 0 bila tanpa overlap.
    a_lens: float = 0.0
    #: Beban yang mendarat pada node JEPIT dan karena itu tidak melenturkan pelat [N].
    #: DIUKUR, bukan diperkirakan: jumlah `nodal_fz` pada himpunan node terjepit.
    absorbed_total: float = 0.0

    @property
    def discrepancy(self) -> float:
        return self.applied_total - self.pz

    @property
    def overlap_fraction(self) -> float:
        return self.a_lens / self.a_disk_mesh if self.a_disk_mesh else 0.0

    @property
    def pz_strut(self) -> float:
        """KOMPONEN GEOMETRI: `p x A_lensa`. Mesh-independen.

        Gaya yang tersalur langsung pile->pier menembus tebal pilecap (aksi strut). Tool
        TIDAK menghitung kapasitas strut ini; wajib dicek terpisah sebagai tumpu/strut.
        """
        return self.pressure * self.a_lens

    @property
    def pz_bocor_mesh(self) -> float:
        """KOMPONEN DISKRETISASI: sisa yang terserap di luar lensa. Mesh-dependen.

        Berasal dari elemen bulan sabit yang bersentuhan dengan potongan pile pada muka
        pier: sebagian beban konsistennya mendarat di node yang dijepit. Besarnya sebanding
        `L x h / (2 A)` -- orde `h`, jadi mengecil saat mesh diperhalus. Dipisahkan dari
        `pz_strut` supaya angka geometri tidak tercampur angka meshing.
        """
        return self.absorbed_total - self.pz_strut

    @property
    def pz_ke_pelat(self) -> float:
        """Bagian `Pz` yang benar-benar melenturkan pelat."""
        return self.pz - self.absorbed_total


@dataclass(frozen=True)
class EquilibriumCheck:
    """VC-0 -- dijalankan pada SETIAP run, bukan hanya saat testing (PRD Bagian 1.3)."""

    total_applied_fz: float
    total_reaction_fz: float
    force_residual_rel: float
    moment_residual_x: float
    moment_residual_y: float
    moment_residual_rel: float
    force_rtol: float
    moment_rtol: float
    reference_point: tuple[float, float]

    @property
    def force_passed(self) -> bool:
        return self.force_residual_rel <= self.force_rtol

    @property
    def moment_passed(self) -> bool:
        return self.moment_residual_rel <= self.moment_rtol

    @property
    def passed(self) -> bool:
        return self.force_passed and self.moment_passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": "PASS" if self.passed else "FAIL",
            "total_applied_fz_N": self.total_applied_fz,
            "total_reaction_fz_N": self.total_reaction_fz,
            "force_residual_rel": self.force_residual_rel,
            "force_rtol": self.force_rtol,
            "force_status": "PASS" if self.force_passed else "FAIL",
            "moment_residual_x_Nm": self.moment_residual_x,
            "moment_residual_y_Nm": self.moment_residual_y,
            "moment_residual_rel": self.moment_residual_rel,
            "moment_rtol": self.moment_rtol,
            "moment_status": "PASS" if self.moment_passed else "FAIL",
            "reference_point_m": list(self.reference_point),
        }


@dataclass(frozen=True)
class ComboResult:
    """Hasil MENTAH satu kombinasi. Transformasi ke sumbu global = tugas postproc."""

    combo: str
    displacements: np.ndarray  # (N, 6) -- ux, uy, uz, rx, ry, rz [m, rad]
    reaction_nodes: np.ndarray  # (n_fixed,) indeks node
    reactions: np.ndarray  # (n_fixed, 6) [N, N.m]
    local_resultants: np.ndarray  # (M, n_gauss, 8) -- APA ADANYA dari OpenSees
    equilibrium: EquilibriumCheck
    load_traces: tuple[PileLoadTrace, ...]
    applied_nodal_fz: np.ndarray  # (N,) [N]
    self_weight_total: float = 0.0
    warnings: tuple[str, ...] = field(default=())

    @property
    def max_deflection(self) -> float:
        """Lendutan vertikal terbesar (nilai absolut) [m]."""
        return float(np.max(np.abs(self.displacements[:, 2])))


# ---------------------------------------------------------------------------
# Strategi tumpuan
# ---------------------------------------------------------------------------


class SupportStrategy(Protocol):
    """Kontrak penerapan kondisi batas. Menambah skema baru = menambah kelas.

    `geom` boleh `None` bagi strategi yang menurunkan tumpuannya langsung dari mesh
    (mis. tumpuan tepi pada validation case).
    """

    def apply(self, mesh: MeshModel, geom: GeometryModel | None) -> np.ndarray:
        """Terapkan tumpuan; kembalikan indeks node yang tertahan."""


def fixed_support_nodes(mesh: MeshModel, geom: GeometryModel) -> np.ndarray:
    """Node yang dijepit: seluruh node area pier DITAMBAH node setiap group LENSA.

    Group lensa disebut **eksplisit dari `geom.overlaps`**, bukan lewat kecocokan awalan
    nama. Lensa dijepit karena ia berada di dalam footprint pier, dan pier diidealkan kaku
    (KNOWN_LIMITATIONS #2) -- itu keputusan pemodelan, dan keputusan tidak boleh bergantung
    pada kebetulan penamaan group.

    Dipakai bersama oleh `FixedPierSupport` dan `exporters.mct._constraint_section`. Tanpa
    sumber tunggal ini, model Midas yang diekspor akan punya himpunan tumpuan berbeda dari
    model OpenSees -- dan VC-6 membandingkan keduanya.
    """
    fixed: set[int] = set()
    for pier in geom.piers:
        nodes = mesh.nodes_in_group(pier.group_name)
        if nodes.size == 0:
            raise AnalysisError(
                f"Physical group {pier.group_name} tidak punya node -- tumpuan akan "
                "HILANG dari model. Perkecil ukuran mesh."
            )
        fixed.update(int(n) for n in nodes)

    for overlap in geom.overlaps:
        nama = overlap.lens_group_name
        if not mesh.has_group(nama):
            raise AnalysisError(
                f"Group lensa {nama} terdaftar di geometri tetapi tidak ada di mesh. "
                "Irisan pile-pier kemungkinan lebih kecil daripada satu elemen; perkecil "
                "`mesh.size_global`."
            )
        fixed.update(int(n) for n in mesh.nodes_in_group(nama))

    return np.array(sorted(fixed), dtype=np.int64)


class FixedPierSupport:
    """v1.0 -- seluruh node di area pier dijepit sempurna 6 DOF (PRD Bagian 5.1(a)).

    Keterbatasannya nyata dan wajib muncul di laporan: tumpuan jepit mengabaikan
    fleksibilitas pier dan menimbulkan singularitas tegangan di tepi zona jepit
    (PRD Bagian 8.3 keterbatasan #2).
    """

    def apply(self, mesh: MeshModel, geom: GeometryModel | None) -> np.ndarray:
        if geom is None:
            raise AnalysisError(
                "FixedPierSupport membutuhkan GeometryModel untuk mengetahui area pier."
            )
        ordered = fixed_support_nodes(mesh, geom)
        # fix() dipanggil SEKALI per node: OpenSees menolak SP_Constraint ganda pada
        # DOF yang sama, dan dua pier bisa berbagi node bila bersentuhan.
        for index in ordered:
            ops.fix(int(index) + 1, 1, 1, 1, 1, 1, 1)
        _log.info("Node jepit (PIER%s): %d", " + LENS" if geom.overlaps else "", ordered.size)
        return ordered


# ---------------------------------------------------------------------------
# Strategi pembebanan
# ---------------------------------------------------------------------------


def consistent_quad_load_factors(coords: np.ndarray) -> np.ndarray:
    """Vektor beban konsisten per satuan tekanan untuk quad bilinear: (M, 4) [m^2].

    Integrasi Gauss 2x2 dari :math:`\\int N_i |J| d\\xi d\\eta`. Untuk quad persegi
    hasilnya tepat `A/4` per node; untuk quad sembarang berbeda, tetapi jumlahnya
    SELALU sama dengan luas elemen -- itulah yang menjaga Sigma beban = P_z persis.
    """
    factors = np.zeros((coords.shape[0], 4), dtype=np.float64)
    x = coords[:, :, 0]
    y = coords[:, :, 1]
    for xi in _GAUSS_1D:
        for eta in _GAUSS_1D:
            n = 0.25 * np.array(
                [
                    (1 - xi) * (1 - eta),
                    (1 + xi) * (1 - eta),
                    (1 + xi) * (1 + eta),
                    (1 - xi) * (1 + eta),
                ]
            )
            dn_dxi = 0.25 * np.array([-(1 - eta), (1 - eta), (1 + eta), -(1 + eta)])
            dn_deta = 0.25 * np.array([-(1 - xi), -(1 + xi), (1 + xi), (1 - xi)])

            dx_dxi = x @ dn_dxi
            dx_deta = x @ dn_deta
            dy_dxi = y @ dn_dxi
            dy_deta = y @ dn_deta
            det_j = dx_dxi * dy_deta - dx_deta * dy_dxi

            factors += np.abs(det_j)[:, None] * n[None, :]
    return factors


def _lumped_quad_load_factors(areas: np.ndarray) -> np.ndarray:
    """Distribusi merata `A_e / 4` ke tiap node: (M, 4) [m^2]."""
    return np.repeat((areas / 4.0)[:, None], 4, axis=1)


@dataclass(frozen=True)
class PilePressure:
    """Tekanan merata satu pile beserta elemen yang memikulnya. Seluruh nilai SI."""

    pile_id: str
    group_name: str
    #: Indeks elemen mesh SELURUH cakram pile -- group `PILE_*` ditambah group `LENS_*`
    #: miliknya bila ada. Keduanya dibebani; lensa juga kebetulan dijepit.
    element_index: np.ndarray
    pz: float  # N, positif = pile mendorong pilecap ke ATAS
    a_disk: float  # m^2 -- jumlah luas elemen mesh SELURUH cakram, BUKAN pi r^2 analitis
    pressure: float  # Pa, positif = ke atas
    #: Luas bagian cakram yang berada di dalam footprint pier [m^2]. 0 bila tanpa overlap.
    a_lens: float = 0.0
    #: Nama group lensa milik pile ini (bisa lebih dari satu bila menindih dua pier).
    lens_group_names: tuple[str, ...] = ()

    @property
    def n_elements(self) -> int:
        return int(self.element_index.size)

    @property
    def overlap_fraction(self) -> float:
        """`f_mesh` -- fraksi cakram yang berada di dalam pier, dari LUAS ELEMEN MESH.

        Ini yang dipakai seluruh pelaporan. Jangan tertukar dengan
        `PileOverlap.fraction_geom` (shapely, poligon 64 segmen), yang hanya dipakai
        membandingkan terhadap ambang `pier.max_pile_overlap_fraction`.
        """
        return self.a_lens / self.a_disk if self.a_disk else 0.0

    @property
    def pz_strut(self) -> float:
        """Bagian `Pz` yang berada di dalam footprint pier -- KOMPONEN GEOMETRI.

        Mesh-independen (mengikuti `f_mesh`, yang konvergen ke fraksi geometrinya). Inilah
        gaya yang tersalur langsung pile->pier menembus tebal pilecap (aksi strut) dan
        TIDAK melenturkan pelat.
        """
        return self.pressure * self.a_lens


def pile_pressures(
    mesh: MeshModel, geom: GeometryModel, pz_by_pile: dict[str, float]
) -> tuple[PilePressure, ...]:
    """`p = Pz / A_disk` per pile, dengan `A_disk` dari LUAS ELEMEN MESH (PRD Bagian 7.3).

    Satu-satunya tempat tekanan pile dihitung. Dipakai dua konsumen yang sangat berbeda:
    strategi beban OpenSees di modul ini, dan penulis `*PRESSURE` pada ekspor Midas MCT
    (`exporters.mct`). Menghitungnya dua kali berarti membuka peluang model FEM dan model
    yang diekspor membawa beban yang berbeda tanpa ada yang menyadarinya.

    `A_disk` sengaja diambil dari jumlah luas elemen, bukan `pi r^2`: itulah yang menjamin
    `Sigma(p x A_e)` persis sama dengan `Pz`.

    Bila pile tumpang tindih dengan pier, group `LENS_*` miliknya **ikut** dihitung sebagai
    bagian cakram. Akibatnya `A_disk` tetap bermakna "luas cakram penuh" dan rumus
    `p = Pz / A_disk` tidak berubah sama sekali -- seluruh cakram dibebani, termasuk bagian
    yang berada di dalam pier. Bagian itu kemudian terserap ke reaksi karena node-nya
    dijepit; besarnya diukur dan dilaporkan, tidak dibiarkan senyap (KNOWN_LIMITATIONS #10).
    """
    lens_by_pile: dict[str, list[str]] = {}
    for overlap in geom.overlaps:
        lens_by_pile.setdefault(overlap.pile_id, []).append(overlap.lens_group_name)

    result: list[PilePressure] = []
    for pile in geom.piles:
        lens_names = tuple(lens_by_pile.get(pile.pile_id, ()))
        # Pile yang SELURUH cakramnya berada di dalam pier tidak punya bagian di luar pier,
        # sehingga gmsh tidak membuat group `PILE_*` untuknya -- hanya group lensanya. Itu
        # batas yang sah dari rumus di atas, bukan kerusakan: seluruh cakram adalah lensa,
        # seluruh `Pz` terserap ke reaksi pier, dan pelat tidak menerima lentur dari pile ini.
        # Beban tidak dapat hilang diam-diam karenanya: pemeriksaan `index.size == 0` di
        # bawah tetap menolak pile yang tidak punya group pile MAUPUN lensa.
        if mesh.has_group(pile.group_name):
            mask = mesh.group_mask(pile.group_name)
        elif lens_names:
            mask = np.zeros(mesh.elem_group.shape, dtype=bool)
        else:
            mask = mesh.group_mask(pile.group_name)  # raise dengan pesan group yang tersedia
        for nama in lens_names:
            if not mesh.has_group(nama):
                raise AnalysisError(
                    f"Group lensa {nama} terdaftar di geometri tetapi tidak ada di mesh. "
                    "Perkecil `mesh.size_global`."
                )
            mask = mask | mesh.group_mask(nama)

        index = np.flatnonzero(mask)
        if index.size == 0:
            raise AnalysisError(
                f"Physical group {pile.group_name} tidak punya elemen -- beban pile "
                "akan HILANG dari model. Perkecil ukuran mesh."
            )
        a_disk = float(mesh.elem_area[mask].sum())
        a_lens = float(sum(mesh.group_area(n) for n in lens_names))
        pz = float(pz_by_pile[pile.pile_id])
        result.append(
            PilePressure(
                pile_id=pile.pile_id,
                group_name=pile.group_name,
                element_index=index,
                pz=pz,
                a_disk=a_disk,
                pressure=pz / a_disk,
                a_lens=a_lens,
                lens_group_names=lens_names,
            )
        )
    return tuple(result)


class PileLoadStrategy(Protocol):
    def apply(
        self,
        mesh: MeshModel,
        geom: GeometryModel | None,
        pz_by_pile: dict[str, float],
        fixed_nodes: np.ndarray | None = None,
    ) -> tuple[np.ndarray, tuple[PileLoadTrace, ...]]:
        """Kembalikan (beban nodal Fz per node [N], jejak per pile).

        `fixed_nodes` diteruskan dari strategi tumpuan yang BARU SAJA dijalankan, bukan
        disimpulkan sendiri: dengan begitu pengukuran beban terserap tidak bergantung pada
        asumsi strategi tumpuan mana yang dipakai.
        """


class _PileAreaLoadBase:
    """Basis kedua skema PRD Bagian 7.3: keduanya bertumpu pada `A_disk` dari mesh."""

    name = "base"

    def _node_factors(self, coords: np.ndarray, areas: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def apply(
        self,
        mesh: MeshModel,
        geom: GeometryModel | None,
        pz_by_pile: dict[str, float],
        fixed_nodes: np.ndarray | None = None,
    ) -> tuple[np.ndarray, tuple[PileLoadTrace, ...]]:
        if geom is None:
            raise AnalysisError(
                "Strategi beban pile membutuhkan GeometryModel untuk mengetahui area pile."
            )
        nodal = np.zeros(mesh.n_nodes, dtype=np.float64)
        traces: list[PileLoadTrace] = []
        nominal_area = {p.pile_id: p.nominal_area for p in geom.piles}

        terjepit = np.zeros(mesh.n_nodes, dtype=bool)
        if fixed_nodes is not None:
            terjepit[np.asarray(fixed_nodes, dtype=np.int64)] = True

        for load in pile_pressures(mesh, geom, pz_by_pile):
            conn = mesh.elem_conn[load.element_index]
            coords = mesh.node_xy[conn]
            factors = self._node_factors(coords, mesh.elem_area[load.element_index])
            gaya = load.pressure * factors
            # Tekanan positif -> gaya ke ATAS pada pilecap (+Z), sesuai PRD Bagian 7.1.
            np.add.at(nodal, conn.ravel(), gaya.ravel())

            # DIUKUR per pile, bukan diperkirakan: gaya yang mendarat di node terjepit
            # tidak menghasilkan perpindahan, jadi tidak melenturkan pelat sama sekali.
            # Dipisah jadi komponen geometri & diskretisasi lewat properti `PileLoadTrace`.
            absorbed = float(gaya[terjepit[conn]].sum())

            traces.append(
                PileLoadTrace(
                    pile_id=load.pile_id,
                    pz=load.pz,
                    a_disk_mesh=load.a_disk,
                    a_disk_nominal=nominal_area[load.pile_id],
                    pressure=load.pressure,
                    n_elements=load.n_elements,
                    applied_total=float(gaya.sum()),
                    a_lens=load.a_lens,
                    absorbed_total=absorbed,
                )
            )

        return nodal, tuple(traces)


class PilePressureLoad(_PileAreaLoadBase):
    """`pile.modeling = "pressure"` (default) -- vektor beban KONSISTEN dari tekanan."""

    name = "pressure"

    def _node_factors(self, coords: np.ndarray, areas: np.ndarray) -> np.ndarray:
        return consistent_quad_load_factors(coords)


class PileNodalLoad(_PileAreaLoadBase):
    """`pile.modeling = "nodal"` -- distribusi tributari merata `A_e/4` per node.

    Untuk quad persegi hasilnya identik dengan `pressure`; bedanya hanya muncul pada
    quad yang tidak persegi. Disediakan sebagai pembanding (PRD Bagian 11).
    """

    name = "nodal"

    def _node_factors(self, coords: np.ndarray, areas: np.ndarray) -> np.ndarray:
        return _lumped_quad_load_factors(areas)


def make_load_strategy(modeling: str) -> PileLoadStrategy:
    if modeling == "pressure":
        return PilePressureLoad()
    if modeling == "nodal":
        return PileNodalLoad()
    raise InputError(
        f"`pile.modeling` = {modeling!r} tidak dikenal. Pilih 'pressure' atau 'nodal'."
    )


# ---------------------------------------------------------------------------
# Guard bocoran mesh (KNOWN_LIMITATIONS #10)
# ---------------------------------------------------------------------------


def leak_traces(
    mesh: MeshModel, geom: GeometryModel, *, load_strategy: PileLoadStrategy | None = None
) -> tuple[PileLoadTrace, ...]:
    """Jejak beban dengan `Pz = 1 N` per pile -- menghasilkan FRAKSI, bukan gaya.

    Bocoran sebanding tekanan, dan tekanan sebanding `Pz`, sehingga fraksinya tidak
    bergantung besar `Pz` sama sekali. Karena itu ia dapat diukur **saat mesh**, sebelum
    satu pun kombinasi dibaca -- yang berarti mesh yang terlalu kasar ditolak lebih awal,
    bukan setelah solver berjalan.
    """
    strategy = load_strategy or PilePressureLoad()
    _, traces = strategy.apply(
        mesh,
        geom,
        {p.pile_id: 1.0 for p in geom.piles},
        fixed_nodes=fixed_support_nodes(mesh, geom),
    )
    return traces


def _h_efektif(mesh: MeshModel, trace: PileLoadTrace) -> float:
    """Ukuran elemen yang BENAR-BENAR berlaku di cakram pile [m].

    Diambil dari luas elemen mesh, bukan dari `mesh.size_*` di config: yang menentukan
    besarnya bocoran adalah elemen yang sungguh terbentuk, dan pada mode graded keduanya
    bisa berbeda jauh.
    """
    return math.sqrt(trace.a_disk_mesh / trace.n_elements) if trace.n_elements else float("nan")


def check_mesh_leak(
    mesh: MeshModel, geom: GeometryModel, traces: Sequence[PileLoadTrace]
) -> tuple[str, ...]:
    """Batasi bocoran mesh; kembalikan peringatan, atau lempar `AnalysisError`.

    Diperiksa **per pile**, bukan agregat: bocoran berdampak lokal, tepat di tempat momen
    lajur pile itu dihitung, sehingga rata-rata lintas pile akan menyamarkannya.

    Arah galatnya yang membuat ini perlu dibatasi, bukan sekadar dilaporkan: beban yang
    mendarat di node jepit TIDAK melenturkan pelat, sehingga momen -- dan tulangan --
    menjadi lebih kecil daripada seharusnya.
    """
    melewati: list[tuple[str, float, float]] = []  # (pile_id, bocor, h_saran)
    for trace in traces:
        if trace.a_lens <= 0.0 or trace.pz == 0.0:
            continue
        bocor = trace.pz_bocor_mesh / trace.pz
        if bocor <= config.OVERLAP_LEAK_WARN:
            continue

        h_now = _h_efektif(mesh, trace)
        # Penskalaan linear (bocoran ~ h). DIUKUR eksponennya 0,76-0,93, jadi angka ini
        # BATAS BAWAH -- disebut apa adanya di pesannya, bukan disajikan sebagai jaminan.
        h_saran = h_now * config.OVERLAP_LEAK_WARN / bocor

        if bocor > config.OVERLAP_LEAK_ERROR:
            raise AnalysisError(
                f"BOCORAN MESH MELEBIHI BATAS ({config.OVERLAP_LEAK_ERROR:.0%}) -- pile "
                f"{trace.pile_id}: {bocor:.2%} dari Pz mendarat di node JEPIT karena "
                f"kehalusan mesh (di luar {trace.overlap_fraction:.2%} yang memang berada "
                "di dalam footprint pier).\n"
                f"  Akibatnya pelat menerima {bocor:.2%} LEBIH KECIL daripada seharusnya, "
                "sehingga momen dan tulangan yang dihitung ikut mengecil -- arah galat "
                "yang TIDAK aman.\n"
                f"  Ukuran elemen di cakram pile sekarang ~{h_now * 1e3:.0f} mm; perkecil "
                f"ke <= {h_saran * 1e3:.0f} mm (perkiraan penskalaan linear, BATAS BAWAH: "
                "peluruhan terukur lebih lambat pada irisan yang terpotong dua sisi). "
                "Jalankan ulang -- guard ini mengukurnya lagi.\n"
                "  Batas ini diturunkan dari pengukuran (lihat komentar "
                "`config.OVERLAP_LEAK_ERROR`), bukan ditebak."
            )
        melewati.append((trace.pile_id, bocor, h_saran))

    if not melewati:
        return ()

    # SATU baris untuk seluruh pile, bukan satu per pile. Peringatan ini ikut ke kop SETIAP
    # gambar; empat baris prosa per pile membuat kop mendominasi gambarnya sendiri, dan pada
    # pilecap dengan banyak pile overlap ia menjadi tidak terbaca sama sekali. Rinciannya
    # tetap lengkap per pile di `calc_sheet.md` bagian 3a dan di log.
    return (
        "BOCORAN MESH {rentang} pada {pile} (> {ambang:.0%}): pelat menerima sebesar itu "
        "LEBIH KECIL daripada seharusnya, sehingga momen & tulangan ikut mengecil -- arah "
        "galat TIDAK aman. Perkecil elemen di cakram pile ke <= {h:.0f} mm. Rincian per "
        "pile di calc_sheet.md bagian 3a.".format(
            rentang=(
                f"{min(b for _, b, _ in melewati):.2%}-{max(b for _, b, _ in melewati):.2%}"
                if len(melewati) > 1
                else f"{melewati[0][1]:.2%}"
            ),
            pile=", ".join(pid for pid, _, _ in melewati),
            ambang=config.OVERLAP_LEAK_WARN,
            h=min(h for _, _, h in melewati) * 1e3,
        ),
    )


# ---------------------------------------------------------------------------
# Pembangunan & analisis model
# ---------------------------------------------------------------------------


def _define_section(material: MaterialProperties, options: AnalysisOptions) -> None:
    ops.nDMaterial("ElasticIsotropic", 1, material.E, material.nu)
    if options.section == "PlateFiber":
        ops.section("PlateFiber", 1, 1, material.thickness)
        return
    layer_t = material.thickness / options.n_layers
    args: list[Any] = []
    for _ in range(options.n_layers):
        args.extend([1, layer_t])
    ops.section("LayeredShell", 1, options.n_layers, *args)


def _self_weight_nodal(mesh: MeshModel, material: MaterialProperties) -> np.ndarray:
    """Berat sendiri sebagai beban nodal ke BAWAH [N] per node.

    `density` dalam N/m^3, sehingga beban per satuan luas = density x tebal.
    Diterapkan lewat beban nodal karena `eleLoad -shellSelfWeight` tidak bekerja pada
    ShellMITC4 versi ini (lihat catatan modul).
    """
    per_area = material.density * material.thickness
    coords = mesh.node_xy[mesh.elem_conn]
    factors = consistent_quad_load_factors(coords)
    nodal = np.zeros(mesh.n_nodes, dtype=np.float64)
    np.add.at(nodal, mesh.elem_conn.ravel(), (-per_area * factors).ravel())
    return nodal


def _check_equilibrium(
    mesh: MeshModel,
    applied_fz: np.ndarray,
    reaction_nodes: np.ndarray,
    reactions: np.ndarray,
    *,
    force_rtol: float,
) -> EquilibriumCheck:
    """VC-0 -- kesetimbangan gaya vertikal dan momen (PRD Bagian 8.1).

    Titik acuan momen = titik asal global (0, 0). Nilainya dicatat di
    `equilibrium_check.json` agar checker dapat menghitung ulang.
    """
    total_applied = float(applied_fz.sum())
    total_reaction = float(reactions[:, 2].sum())
    scale = max(abs(total_applied), 1.0)
    force_residual = abs(total_applied + total_reaction) / scale

    # Momen terhadap titik asal: gaya vertikal x lengan + momen nodal.
    lx = mesh.node_xy[:, 0]
    ly = mesh.node_xy[:, 1]
    mx = float(np.sum(ly * applied_fz))
    my = float(-np.sum(lx * applied_fz))

    rx = mesh.node_xy[reaction_nodes, 0]
    ry = mesh.node_xy[reaction_nodes, 1]
    mx += float(np.sum(ry * reactions[:, 2]) + np.sum(reactions[:, 3]))
    my += float(-np.sum(rx * reactions[:, 2]) + np.sum(reactions[:, 4]))

    # Skala momen: total gaya x dimensi terbesar model -- memberi ukuran relatif yang
    # bermakna tanpa bergantung pada letak titik asal.
    span = float(
        max(
            mesh.node_xy[:, 0].max() - mesh.node_xy[:, 0].min(),
            mesh.node_xy[:, 1].max() - mesh.node_xy[:, 1].min(),
            1e-9,
        )
    )
    moment_scale = max(abs(total_applied) * span, 1.0)
    moment_residual = max(abs(mx), abs(my)) / moment_scale

    return EquilibriumCheck(
        total_applied_fz=total_applied,
        total_reaction_fz=total_reaction,
        force_residual_rel=force_residual,
        moment_residual_x=mx,
        moment_residual_y=my,
        moment_residual_rel=moment_residual,
        force_rtol=force_rtol,
        moment_rtol=config.EQUILIBRIUM_MOMENT_RTOL,
        reference_point=(0.0, 0.0),
    )


def analyze_combo(
    mesh: MeshModel,
    geom: GeometryModel | None,
    material: MaterialProperties,
    options: AnalysisOptions,
    *,
    combo: str,
    pz_by_pile: dict[str, float],
    load_strategy: PileLoadStrategy | None = None,
    support_strategy: SupportStrategy | None = None,
) -> ComboResult:
    """Bangun model, analisis satu kombinasi, dan kembalikan hasil MENTAH.

    `ops.wipe()` dipanggil di awal SETIAP pemanggilan: OpenSees punya state global, dan
    model sisa dari kombinasi sebelumnya adalah sumber bug halus yang klasik
    (PRD Bagian 13.4).

    `geom` boleh `None` bila strategi tumpuan & pembebanan yang diberikan tidak
    membutuhkannya (dipakai validation case, yang memasang tumpuan tepi dan tekanan
    merata langsung dari mesh). Strategi bawaan v1.0 MEMBUTUHKAN `geom`.
    """
    options.validate()
    load_strategy = load_strategy or PilePressureLoad()
    support_strategy = support_strategy or FixedPierSupport()

    ops.wipe()
    ops.model("basic", "-ndm", 3, "-ndf", 6)
    _define_section(material, options)

    for index, (x, y) in enumerate(mesh.node_xy):
        ops.node(index + 1, float(x), float(y), 0.0)

    for etag, conn in enumerate(mesh.elem_conn, start=1):
        ops.element(options.shell_element, etag, *(int(n) + 1 for n in conn), 1)

    fixed_nodes = support_strategy.apply(mesh, geom)

    nodal_fz, traces = load_strategy.apply(mesh, geom, pz_by_pile, fixed_nodes=fixed_nodes)

    # Jaring pengaman: geometri bilang tidak ada tumpang tindih, tetapi ada beban pile yang
    # tetap mendarat di node jepit. Penyebab yang mungkin: celah pile-pier jauh lebih kecil
    # daripada ukuran elemen sehingga mesher menyatukan node-nya. Menguji KONDISI YANG
    # SEBENARNYA -- bukan proksi geometrinya -- sehingga menangkap setiap jalur, termasuk
    # mesh yang dimuat ulang dari CSV.
    #
    # TIDAK bisa diserahkan ke VC-0: gaya pada DOF terjepit terserap ke reaksi, sehingga
    # `Sigma beban` dan `Sigma reaksi` sama-sama memuatnya dan residunya NOL.
    if geom is not None and not geom.overlaps:
        terserap = float(np.abs(nodal_fz[fixed_nodes]).sum())
        if terserap > 0.0:
            raise AnalysisError(
                f"Ada beban pile sebesar {terserap / 1e3:,.4f} kN yang mendarat pada node "
                "JEPIT, padahal geometri tidak mencatat satu pun tumpang tindih pile-pier.\n"
                "  Gaya pada DOF terjepit menghasilkan perpindahan NOL, jadi beban itu "
                "TIDAK melenturkan pelat -- dan VC-0 tetap lulus karena kedua sisi "
                "neracanya memuat gaya yang sama.\n"
                "  Kemungkinan penyebab: celah antara pile dan pier jauh lebih kecil "
                "daripada ukuran elemen, sehingga mesher menyatukan node keduanya.\n"
                "  Perbaiki geometrinya (perbesar celah), atau perkecil `mesh.size_global`."
            )
    # Batasi bocoran mesh SEBELUM solver berjalan: hasil yang bocorannya berlebih
    # un-konservatif, jadi tidak ada gunanya menghitungnya sampai selesai.
    peringatan_bocor: tuple[str, ...] = ()
    if geom is not None and geom.overlaps:
        peringatan_bocor = check_mesh_leak(mesh, geom, traces)
        for baris in peringatan_bocor:
            _log.warning("%s", baris)

    self_weight_total = 0.0
    if options.include_self_weight:
        self_weight = _self_weight_nodal(mesh, material)
        self_weight_total = float(self_weight.sum())
        nodal_fz = nodal_fz + self_weight
        _log.info("Berat sendiri diaktifkan: %.1f kN", self_weight_total / 1e3)

    # Node yang dijepit tidak perlu dibebani -- bebannya langsung masuk ke tumpuan.
    ops.timeSeries("Linear", 1)
    ops.pattern("Plain", 1, 1)
    loaded = np.nonzero(np.abs(nodal_fz) > 0.0)[0]
    for loaded_index in loaded:
        ops.load(int(loaded_index) + 1, 0.0, 0.0, float(nodal_fz[loaded_index]), 0.0, 0.0, 0.0)

    _log.info(
        "Beban: Sigma Fz terpasang = %.1f kN pada %d pile | node terbebani %d",
        float(nodal_fz.sum()) / 1e3,
        len(traces),
        loaded.size,
    )

    ops.system("UmfPack")
    ops.numberer("RCM")
    ops.constraints("Plain")
    ops.integrator("LoadControl", 1.0)
    ops.algorithm("Linear")
    ops.analysis("Static")

    status = ops.analyze(1)
    if status != 0:
        raise AnalysisError(
            f"Analisis kombinasi {combo!r} tidak konvergen (kode {status}).\n"
            "  Kemungkinan penyebab: model tidak terkekang (physical group pier kosong), "
            "elemen terdistorsi, atau properti material tidak wajar.\n"
            "  Periksa boundary_load_check.png dan mesh_summary.md."
        )
    _log.info("analyze(1) -> OK")

    displacements = np.array([ops.nodeDisp(i + 1) for i in range(mesh.n_nodes)], dtype=np.float64)

    ops.reactions()
    reactions = np.array([ops.nodeReaction(int(i) + 1) for i in fixed_nodes], dtype=np.float64)

    local = _extract_local_resultants(mesh)

    equilibrium = _check_equilibrium(
        mesh,
        nodal_fz,
        fixed_nodes,
        reactions,
        force_rtol=options.equilibrium_rtol,
    )
    _report_equilibrium(combo, equilibrium)

    return ComboResult(
        combo=combo,
        displacements=displacements,
        reaction_nodes=fixed_nodes,
        reactions=reactions,
        local_resultants=local,
        equilibrium=equilibrium,
        load_traces=traces,
        applied_nodal_fz=nodal_fz,
        self_weight_total=self_weight_total,
        warnings=peringatan_bocor,
    )


def _extract_local_resultants(mesh: MeshModel) -> np.ndarray:
    """Ambil stress resultant lokal (M, n_gauss, 8) APA ADANYA dari OpenSees.

    Nama response-nya `'stresses'`, BUKAN `'forces'` seperti tertulis di PRD
    Bagian 7.2(2) -- `'forces'` mengembalikan 24 gaya nodal global. Lihat
    `config.SHELL_RESULTANT_RESPONSE`.
    """
    expected = config.SHELL_N_GAUSS * config.SHELL_N_RESULTANT_COMPONENTS
    out = np.empty(
        (mesh.n_elements, config.SHELL_N_GAUSS, config.SHELL_N_RESULTANT_COMPONENTS),
        dtype=np.float64,
    )
    for i in range(mesh.n_elements):
        response = ops.eleResponse(i + 1, config.SHELL_RESULTANT_RESPONSE)
        if len(response) != expected:
            raise AnalysisError(
                f"eleResponse(elemen {i + 1}, {config.SHELL_RESULTANT_RESPONSE!r}) "
                f"mengembalikan {len(response)} nilai, diharapkan "
                f"{config.SHELL_N_GAUSS} x {config.SHELL_N_RESULTANT_COMPONENTS} = "
                f"{expected}.\n"
                "  Struktur response OpenSees berubah antar versi; seluruh transformasi "
                "di postproc_engine bergantung padanya."
            )
        out[i] = np.asarray(response, dtype=np.float64).reshape(
            config.SHELL_N_GAUSS, config.SHELL_N_RESULTANT_COMPONENTS
        )
    return out


def _report_equilibrium(combo: str, check: EquilibriumCheck) -> None:
    verdict = "LULUS" if check.passed else "GAGAL"
    _log.info(
        "VC-0 Keseimbangan [%s]: Sigma beban = %.1f kN | Sigma R = %.1f kN | "
        "residu gaya %.2e (rtol %.0e) | residu momen %.2e (rtol %.0e)  -> %s",
        combo,
        check.total_applied_fz / 1e3,
        check.total_reaction_fz / 1e3,
        check.force_residual_rel,
        check.force_rtol,
        check.moment_residual_rel,
        check.moment_rtol,
        verdict,
    )
    if not check.passed:
        raise AnalysisError(
            f"CEK KESEIMBANGAN VC-0 GAGAL untuk kombinasi {combo!r}.\n"
            f"  Sigma beban Fz  = {check.total_applied_fz / 1e3:,.4f} kN\n"
            f"  Sigma reaksi Fz = {check.total_reaction_fz / 1e3:,.4f} kN\n"
            f"  Residu gaya  = {check.force_residual_rel:.3e} (toleransi "
            f"{check.force_rtol:.1e}) -> {'OK' if check.force_passed else 'GAGAL'}\n"
            f"  Residu momen = {check.moment_residual_rel:.3e} (toleransi "
            f"{check.moment_rtol:.1e}) -> {'OK' if check.moment_passed else 'GAGAL'}\n"
            f"    M_x = {check.moment_residual_x:,.4f} N.m, "
            f"M_y = {check.moment_residual_y:,.4f} N.m terhadap titik "
            f"{check.reference_point}\n"
            # "beban pile jatuh pada node jepit" SENGAJA TIDAK disebut di sini: kondisi itu
            # justru TIDAK PERNAH membuat VC-0 gagal -- gayanya terserap ke reaksi sehingga
            # kedua sisi neraca memuatnya dan residunya nol. Menyebutnya sebagai dugaan
            # penyebab hanya mengarahkan pembaca ke tempat yang salah. Kondisi itu punya
            # penjaganya sendiri di `analyze_combo`, dan bila disengaja ia dilaporkan
            # terpisah sebagai transfer langsung (KNOWN_LIMITATIONS #10).
            "  Kemungkinan penyebab: beban nodal tidak lengkap terpasang, tumpuan tidak "
            "terbentuk seperti yang diharapkan, atau solver tidak menyelesaikan sistem "
            "dengan benar.\n"
            "  Run yang gagal VC-0 TIDAK menghasilkan output desain (PRD Bagian 1.3 poin 3)."
        )
