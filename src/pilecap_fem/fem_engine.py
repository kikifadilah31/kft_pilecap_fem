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

    @property
    def discrepancy(self) -> float:
        return self.applied_total - self.pz


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
        fixed: set[int] = set()
        for pier in geom.piers:
            nodes = mesh.nodes_in_group(pier.group_name)
            if nodes.size == 0:
                raise AnalysisError(
                    f"Physical group {pier.group_name} tidak punya node -- tumpuan akan "
                    "HILANG dari model. Perkecil ukuran mesh."
                )
            fixed.update(int(n) for n in nodes)
            _log.debug("Pier %s: %d node dijepit", pier.pier_id, nodes.size)

        # fix() dipanggil SEKALI per node: OpenSees menolak SP_Constraint ganda pada
        # DOF yang sama, dan dua pier bisa berbagi node bila bersentuhan.
        ordered = np.array(sorted(fixed), dtype=np.int64)
        for index in ordered:
            ops.fix(int(index) + 1, 1, 1, 1, 1, 1, 1)
        _log.info("Node jepit (PIER): %d", ordered.size)
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
    #: Indeks elemen mesh dalam physical group pile ini.
    element_index: np.ndarray
    pz: float  # N, positif = pile mendorong pilecap ke ATAS
    a_disk: float  # m^2 -- jumlah luas elemen mesh, BUKAN pi r^2 analitis
    pressure: float  # Pa, positif = ke atas

    @property
    def n_elements(self) -> int:
        return int(self.element_index.size)


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
    """
    result: list[PilePressure] = []
    for pile in geom.piles:
        mask = mesh.group_mask(pile.group_name)
        index = np.flatnonzero(mask)
        if index.size == 0:
            raise AnalysisError(
                f"Physical group {pile.group_name} tidak punya elemen -- beban pile "
                "akan HILANG dari model. Perkecil ukuran mesh."
            )
        a_disk = float(mesh.elem_area[mask].sum())
        pz = float(pz_by_pile[pile.pile_id])
        result.append(
            PilePressure(
                pile_id=pile.pile_id,
                group_name=pile.group_name,
                element_index=index,
                pz=pz,
                a_disk=a_disk,
                pressure=pz / a_disk,
            )
        )
    return tuple(result)


class PileLoadStrategy(Protocol):
    def apply(
        self, mesh: MeshModel, geom: GeometryModel | None, pz_by_pile: dict[str, float]
    ) -> tuple[np.ndarray, tuple[PileLoadTrace, ...]]:
        """Kembalikan (beban nodal Fz per node [N], jejak per pile)."""


class _PileAreaLoadBase:
    """Basis kedua skema PRD Bagian 7.3: keduanya bertumpu pada `A_disk` dari mesh."""

    name = "base"

    def _node_factors(self, coords: np.ndarray, areas: np.ndarray) -> np.ndarray:
        raise NotImplementedError

    def apply(
        self, mesh: MeshModel, geom: GeometryModel | None, pz_by_pile: dict[str, float]
    ) -> tuple[np.ndarray, tuple[PileLoadTrace, ...]]:
        if geom is None:
            raise AnalysisError(
                "Strategi beban pile membutuhkan GeometryModel untuk mengetahui area pile."
            )
        nodal = np.zeros(mesh.n_nodes, dtype=np.float64)
        traces: list[PileLoadTrace] = []
        nominal_area = {p.pile_id: p.nominal_area for p in geom.piles}

        for load in pile_pressures(mesh, geom, pz_by_pile):
            conn = mesh.elem_conn[load.element_index]
            coords = mesh.node_xy[conn]
            factors = self._node_factors(coords, mesh.elem_area[load.element_index])
            # Tekanan positif -> gaya ke ATAS pada pilecap (+Z), sesuai PRD Bagian 7.1.
            np.add.at(nodal, conn.ravel(), (load.pressure * factors).ravel())

            traces.append(
                PileLoadTrace(
                    pile_id=load.pile_id,
                    pz=load.pz,
                    a_disk_mesh=load.a_disk,
                    a_disk_nominal=nominal_area[load.pile_id],
                    pressure=load.pressure,
                    n_elements=load.n_elements,
                    applied_total=float((load.pressure * factors).sum()),
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

    nodal_fz, traces = load_strategy.apply(mesh, geom, pz_by_pile)
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
            "  Kemungkinan penyebab: ada beban pile yang jatuh pada node jepit, "
            "physical group pile bertumpang tindih dengan pier, atau solver tidak "
            "menyelesaikan sistem dengan benar.\n"
            "  Run yang gagal VC-0 TIDAK menghasilkan output desain (PRD Bagian 1.3 poin 3)."
        )
