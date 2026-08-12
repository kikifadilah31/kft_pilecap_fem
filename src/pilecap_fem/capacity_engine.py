"""Cek kapasitas SNI 2847:2019 lewat `shell-kit` (PRD Bagian 7.2(6), 7.2(7)).

**Modul ini adalah SATU-SATUNYA batas satuan menuju `shell-kit`**, persis seperti
`io_utils.py` menjadi satu-satunya batas satuan untuk masukan. `shell_kit.rebar` bekerja
dalam satuan teknik (kN.m/m, kN/m, MPa, mm), sedangkan seluruh `pilecap-fem` bekerja murni
SI (PRD Bagian 4.1, Core 2). Menyebar konversi itu ke `postproc_engine` atau `reporter`
akan merusak aturan yang menjadi dasar seluruh proyek ini; di sini konversinya terkumpul
di satu tempat, memakai faktor yang sama dari `config.DISPLAY_UNITS`, dan hasilnya
dikembalikan ke SI.

.. rubric:: Mengapa mengimpor, bukan menyalin

Rumus dan pasal SNI hidup di `shell-kit` dan **hanya** di sana. Menyalinnya ke sini
berarti dua salinan yang dapat menyimpang diam-diam -- hal terakhir yang boleh terjadi
pada tool yang angkanya dipakai untuk desain (PRD Bagian 1.3). `pilecap-fem` tidak pernah
menuliskan satu pun rumus kapasitas.

.. rubric:: Tiga hal yang WAJIB ditangani adapter ini

1. **`shell_kit.rebar.calc_as_required` TIDAK mengambil nilai mutlak.** Diuji langsung:
   ``Mu = -200 kN.m/m`` menghasilkan ``As = -1.571 mm^2/m``. Momen bertanda harus
   dipisahkan lebih dulu menjadi muka BAWAH (dari momen positif, sesuai konvensi
   PRD Bagian 7.1) dan muka ATAS (dari nilai mutlak momen negatif).
2. **`np.nan` dari `shell-kit` berarti "penampang tidak memadai"**, sedangkan di
   `pilecap-fem` `NaN` berarti "tidak terdefinisi" (Core 3). Dua makna itu tidak boleh
   bercampur di laporan, sehingga diterjemahkan menjadi kolom `status` eksplisit.
3. **Kedalaman efektif berbeda per arah.** Diuji: `h=1200, cover=75, D=16` memberi
   `d_x = 1.117 mm` dan `d_y = 1.101 mm` -- arah X lapis luar, Y lapis dalam.

.. warning::
   `shell-kit` adalah alat desain **pelat per lajur 1 m**. Penerapannya pada pilecap sah
   untuk bagian yang berperilaku lentur pelat, TETAPI tidak untuk *deep member*
   (PRD Bagian 8.3 keterbatasan #1), dan ambang deep pile cap masih terbuka
   (PRD Bagian 17 item 5). Peringatan itu WAJIB muncul di atas setiap tabel `As`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from shell_kit import rebar as sk_rebar

from pilecap_fem import config
from pilecap_fem.validators import validate_design

if TYPE_CHECKING:  # hanya untuk anotasi -- menghindari impor melingkar saat runtime
    from pilecap_fem.mesh_model import MeshModel
    from pilecap_fem.postproc_engine import ShearCheck

_log = config.get_logger("capacity_engine")

#: Status hasil desain. Memisahkan "gagal" dari "tidak ada data" -- `shell-kit`
#: memakai `np.nan` untuk keduanya.
STATUS_OK = "OK"
STATUS_SECTION_INADEQUATE = "PENAMPANG_TIDAK_MEMADAI"
STATUS_WEB_CRUSHED = "BADAN_HANCUR"
STATUS_UNDEFINED = "TIDAK_TERDEFINISI"
STATUS_NO_MOMENT = "TANPA_MOMEN"

#: Pasal yang dirujuk `shell-kit`, dicetak apa adanya di calc sheet supaya checker
#: dapat menelusuri asal setiap angka kapasitas.
SNI_CLAUSES: dict[str, str] = {
    "beta1": "SNI 2847:2019 Ps. 22.2.2.4.3 (faktor tinggi blok tegangan)",
    "epsilon_cu": "SNI 2847:2019 Ps. 22.2.2.1 (regangan tekan ultimit 0,003)",
    "Es": "SNI 2847:2019 Ps. 20.2.2.2 (modulus elastisitas baja 200.000 MPa)",
    "lambda": "SNI 2847:2019 Ps. 19.2.4 (faktor beton berat normal)",
    "Vc": "SNI 2847:2019 Ps. 22.5.5.1 (Vc = 0,17 lambda sqrt(f'c) bw d)",
    "Av_min": "SNI 2847:2019 Ps. 9.6.3.4 (tulangan geser minimum)",
    "spacing": "SNI 2847:2019 Ps. 25.2.1 (spasi bersih minimum)",
}


# ---------------------------------------------------------------------------
# Masukan
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapacityInputs:
    """Seluruh masukan cek kapasitas, dalam SI. Konversi terjadi saat memanggil."""

    fc: float  # Pa
    fy: float  # Pa
    thickness: float  # m
    cover: float  # m
    spacing: float  # m -- spasi tulangan lentur (mode spacing_fixed)
    phi_flexure: float
    phi_shear: float
    phi_source: str
    fy_source: str
    #: Mode seleksi batang: mana yang ditetapkan user, mana yang dihitung tool.
    rebar_mode: str = "spacing_fixed"
    #: Kode konfigurasi batang yang ditetapkan user (mode diameter_fixed).
    rebar_config: str | None = None
    #: Daftar kode yang boleh dipilih; mengaktifkan seleksi KATEGORIKAL.
    rebar_select_codes: tuple[str, ...] = ()
    #: Grid sengkang [m]. Keduanya menentukan luas per kaki, karena itu wajib.
    stirrup_spacing_long: float = 0.0
    stirrup_spacing_trans: float = 0.0
    #: Diameter sengkang yang diizinkan [m]; kosong = daftar bawaan shell-kit.
    stirrup_diameters: tuple[float, ...] = ()
    #: Batas tebal per muka untuk `As_min` [m]. `None` = murni SNI (tanpa batas).
    as_min_surface_zone: float | None = None

    # -- satuan shell-kit ---------------------------------------------------

    @property
    def fc_mpa(self) -> float:
        return float(config.DISPLAY_UNITS["stress"][1] * self.fc)

    @property
    def fy_mpa(self) -> float:
        return float(config.DISPLAY_UNITS["stress"][1] * self.fy)

    @property
    def thickness_mm(self) -> float:
        return float(config.DISPLAY_UNITS["length"][1] * self.thickness)

    @property
    def cover_mm(self) -> float:
        return float(config.DISPLAY_UNITS["length"][1] * self.cover)

    @property
    def spacing_mm(self) -> float:
        return float(config.DISPLAY_UNITS["length"][1] * self.spacing)

    @property
    def stirrup_long_mm(self) -> float:
        return float(config.DISPLAY_UNITS["length"][1] * self.stirrup_spacing_long)

    @property
    def stirrup_trans_mm(self) -> float:
        return float(config.DISPLAY_UNITS["length"][1] * self.stirrup_spacing_trans)

    @property
    def stirrup_diameters_mm(self) -> list[float] | None:
        """Daftar diameter sengkang dalam mm, atau `None` untuk bawaan shell-kit."""
        if not self.stirrup_diameters:
            return None
        factor = config.DISPLAY_UNITS["length"][1]
        return [float(factor * d) for d in self.stirrup_diameters]

    @property
    def surface_zone_mm(self) -> float | None:
        if self.as_min_surface_zone is None:
            return None
        return float(config.DISPLAY_UNITS["length"][1] * self.as_min_surface_zone)

    @property
    def config_diameter_mm(self) -> float:
        """Diameter batang pada mode `diameter_fixed`, dari tabel konfigurasi shell-kit."""
        if not self.rebar_config:
            raise ValueError("rebar_config kosong; hanya berlaku pada mode diameter_fixed.")
        return float(sk_rebar.REBAR_CONFIG_TABLE[self.rebar_config.upper().strip()][0])

    @property
    def config_area_mm2(self) -> float:
        """Luas satu konfigurasi batang [mm^2], mis. `2D25` -> 982."""
        if not self.rebar_config:
            raise ValueError("rebar_config kosong; hanya berlaku pada mode diameter_fixed.")
        return float(sk_rebar.get_config_area(self.rebar_config))

    @classmethod
    def from_config(cls, cfg: dict[str, Any]) -> CapacityInputs:
        """Bangun dari config yang SUDAH dalam SI (hasil `io_utils.load_config`).

        `validators.validate_design` dipanggil DI SINI, bukan diserahkan ke pemanggil:
        dengan begitu tidak ada jalur mana pun yang bisa menghasilkan `As` dari config
        yang belum tervalidasi (Core 6 -- satu sumber kebenaran untuk aturan masukan).
        """
        validate_design(cfg)
        design = cfg.get("design") or {}
        material = cfg.get("material") or {}

        phi_flexure = design.get("phi_flexure")
        phi_shear = design.get("phi_shear")
        if phi_flexure is None and phi_shear is None:
            phi_source = f"shell-kit v{_shell_kit_version()} (SNI 2847:2019)"
            phi_flexure = float(sk_rebar.PHI_FLEXURE)
            phi_shear = float(sk_rebar.PHI_SHEAR)
        else:
            phi_source = "config user"
            phi_flexure = float(phi_flexure if phi_flexure is not None else sk_rebar.PHI_FLEXURE)
            phi_shear = float(phi_shear if phi_shear is not None else sk_rebar.PHI_SHEAR)

        codes = design.get("rebar_select_codes") or ()
        diameters = design.get("stirrup_select_diameters") or ()
        surface_zone = design.get("as_min_surface_zone")

        return cls(
            fc=float(material["fc"]),
            fy=float(design["fy"]),
            thickness=float(cfg["pilecap"]["thickness"]),
            cover=float(design["cover"]),
            # Pada mode diameter_fixed spasi bukan masukan; 0.0 menandainya tidak dipakai.
            spacing=float(design.get("rebar_spacing") or 0.0),
            phi_flexure=phi_flexure,
            phi_shear=phi_shear,
            phi_source=phi_source,
            fy_source=str(design.get("fy_source") or "TIDAK DICATAT"),
            rebar_mode=str(design["rebar_mode"]),
            rebar_config=(
                str(design["rebar_config"]).upper().strip() if design.get("rebar_config") else None
            ),
            rebar_select_codes=tuple(str(c).upper().strip() for c in codes),
            stirrup_spacing_long=float(design["stirrup_spacing_long"]),
            stirrup_spacing_trans=float(design["stirrup_spacing_trans"]),
            stirrup_diameters=tuple(float(d) for d in diameters),
            as_min_surface_zone=(None if surface_zone is None else float(surface_zone)),
        )


def _shell_kit_version() -> str:
    import shell_kit

    return str(getattr(shell_kit, "__version__", "?"))


# ---------------------------------------------------------------------------
# Desain lentur
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FlexureDesign:
    """Hasil desain lentur satu arah pada satu muka. Seluruh nilai SI."""

    direction: str  # "x" | "y"
    face: str  # "bawah" | "atas"
    mu: np.ndarray  # N.m/m, sudah |.| dan hanya sisi yang relevan
    as_required: np.ndarray  # m^2/m
    as_min: float  # m^2/m
    d_effective: np.ndarray  # m
    bar_diameter: np.ndarray  # m
    status: np.ndarray  # (M,) str

    @property
    def n_inadequate(self) -> int:
        return int(np.count_nonzero(self.status == STATUS_SECTION_INADEQUATE))

    @property
    def as_governing(self) -> float:
        """`As` terbesar yang terdefinisi [m^2/m]."""
        finite = self.as_required[np.isfinite(self.as_required)]
        return float(finite.max()) if finite.size else float("nan")


def _face_moments(moments_si: np.ndarray, face: str) -> np.ndarray:
    """Pisahkan momen bertanda menjadi besaran untuk satu muka [N.m/m].

    Konvensi PRD Bagian 7.1: momen POSITIF = serat bawah tertarik = tulangan BAWAH.
    Momen negatif menarik serat atas, jadi tulangan ATAS memakai nilai mutlaknya.

    Pemisahan ini WAJIB: `shell_kit.rebar.calc_as_required` tidak mengambil nilai
    mutlak dan akan mengembalikan luas tulangan NEGATIF bila diberi momen bertanda.
    """
    values = np.asarray(moments_si, dtype=np.float64)
    if face == "bawah":
        return np.where(np.isfinite(values), np.maximum(values, 0.0), np.nan)
    if face == "atas":
        return np.where(np.isfinite(values), np.maximum(-values, 0.0), np.nan)
    raise ValueError(f"face = {face!r} harus 'bawah' atau 'atas'.")


def flexure_design(
    moments_si: np.ndarray,
    inputs: CapacityInputs,
    *,
    direction: str,
    face: str,
    layer: int = 1,
) -> FlexureDesign:
    """Desain lentur per elemen, bercabang menurut `inputs.rebar_mode`.

    * ``spacing_fixed`` -- spasi ditetapkan user, DIAMETER dihitung. Dipakai
      `solve_rebar_iterative` (bukan `calc_as_required` langsung) karena kedalaman efektif
      bergantung pada diameter terpilih dan sebaliknya.
    * ``diameter_fixed`` -- batang ditetapkan user, jadi `d` adalah SATU skalar dan tidak
      perlu diiterasi; spasinya yang kemudian dihitung (lihat `select_flexure_bars`).
    """
    if direction not in ("x", "y"):
        raise ValueError(f"direction = {direction!r} harus 'x' atau 'y'.")

    mu_si = _face_moments(moments_si, face)
    # SI (N.m/m) -> kN.m/m yang diminta shell-kit.
    mu_knm = np.nan_to_num(mu_si * config.DISPLAY_UNITS["moment_per_width"][1], nan=0.0)
    surface_zone = inputs.surface_zone_mm

    if inputs.rebar_mode == "diameter_fixed":
        diameter = inputs.config_diameter_mm
        d_scalar = float(
            sk_rebar.calc_effective_depth(
                inputs.thickness_mm, inputs.cover_mm, diameter, direction, layer
            )
        )
        as_mm2 = np.asarray(
            sk_rebar.calc_as_required(
                mu_knm, inputs.fc_mpa, inputs.fy_mpa, d_scalar, phi=inputs.phi_flexure
            ),
            dtype=np.float64,
        )
        as_mm2 = np.asarray(
            sk_rebar.apply_as_min(
                as_mm2, inputs.fy_mpa, inputs.thickness_mm, surface_zone=surface_zone
            ),
            dtype=np.float64,
        )
        d_mm = np.full(as_mm2.shape, d_scalar, dtype=np.float64)
        diameter_mm = np.full(as_mm2.shape, diameter, dtype=np.float64)
    else:
        as_mm2, d_mm, diameter_mm, _ = sk_rebar.solve_rebar_iterative(
            mu_knm,
            inputs.fc_mpa,
            inputs.fy_mpa,
            inputs.thickness_mm,
            inputs.cover_mm,
            direction,
            layer,
            inputs.spacing_mm,
            phi=inputs.phi_flexure,
            surface_zone=surface_zone,
        )
        as_mm2 = np.asarray(as_mm2, dtype=np.float64)
        d_mm = np.asarray(d_mm, dtype=np.float64)
        diameter_mm = np.asarray(diameter_mm, dtype=np.float64)

    as_min_mm2 = float(
        sk_rebar.calc_as_min_per_face(inputs.fy_mpa, inputs.thickness_mm, surface_zone=surface_zone)
    )

    # `shell-kit` memakai NaN untuk "penampang tidak memadai". Di sini dipisahkan dari
    # "tidak terdefinisi" supaya pembaca laporan tidak mengira datanya hilang.
    status = np.full(as_mm2.shape, STATUS_OK, dtype=object)
    status[~np.isfinite(mu_si)] = STATUS_UNDEFINED
    status[np.isfinite(mu_si) & ~np.isfinite(as_mm2)] = STATUS_SECTION_INADEQUATE
    status[np.isfinite(mu_si) & (mu_si <= 0.0)] = STATUS_NO_MOMENT

    n_bad = int(np.count_nonzero(status == STATUS_SECTION_INADEQUATE))
    if n_bad:
        _log.warning(
            "Desain lentur arah %s muka %s: %d elemen PENAMPANG TIDAK MEMADAI "
            "(momen melampaui batas kendali tarik pada tebal yang ada).",
            direction,
            face,
            n_bad,
        )

    to_si_area = 1.0 / config.DISPLAY_UNITS["steel_area"][1]
    to_si_len = 1.0 / config.DISPLAY_UNITS["length"][1]
    return FlexureDesign(
        direction=direction,
        face=face,
        mu=mu_si,
        as_required=as_mm2 * to_si_area,
        as_min=as_min_mm2 * to_si_area,
        d_effective=d_mm * to_si_len,
        bar_diameter=diameter_mm * to_si_len,
        status=status,
    )


# ---------------------------------------------------------------------------
# Seleksi batang -- "pakai D berapa, spasi berapa"
# ---------------------------------------------------------------------------

SELECTION_DIAMETER = "diameter"
SELECTION_SPACING = "spasi"
SELECTION_CONFIG = "konfigurasi"


@dataclass(frozen=True)
class RebarSelection:
    """Batang yang terpilih per elemen. Nilai SI kecuali `kind == "konfigurasi"`.

    `As perlu` menjawab "berapa luas baja", bukan "pakai batang apa". Kelas ini menjawab
    yang kedua -- dan itulah yang dibaca pelaksana di lapangan.
    """

    kind: str  # SELECTION_DIAMETER | SELECTION_SPACING | SELECTION_CONFIG
    direction: str
    face: str
    #: Diameter [m], spasi [m], atau indeks 1-basis ke `labels` bila kategorikal.
    values: np.ndarray
    #: Label kategori untuk colorbar diskret; kosong bila besaran kontinu.
    labels: tuple[str, ...]
    #: Besaran tampilan untuk `io_utils.display_unit` (kosong bila kategorikal).
    quantity: str
    status: np.ndarray

    @property
    def is_categorical(self) -> bool:
        return bool(self.labels)

    @property
    def n_inadequate(self) -> int:
        return int(np.count_nonzero(self.status == STATUS_SECTION_INADEQUATE))


def select_flexure_bars(design: FlexureDesign, inputs: CapacityInputs) -> RebarSelection:
    """Terjemahkan `As perlu` menjadi batang nyata, menurut `inputs.rebar_mode`.

    Tiga jalur, seluruhnya memakai fungsi `shell_kit.rebar` -- tidak satu pun rumus
    seleksi ditulis di sini:

    1. ``spacing_fixed`` + `rebar_select_codes` -> `select_config_from_As`, hasilnya
       indeks konfigurasi (kategorikal, mis. `2D25`).
    2. ``spacing_fixed`` tanpa daftar kode -> diameter yang SUDAH dipilih
       `solve_rebar_iterative` saat menghitung `As`. Memanggil ulang pemilih di sini akan
       memberi jawaban yang bisa berbeda dari `d` yang dipakai menghitung `As` itu sendiri.
    3. ``diameter_fixed`` -> `calc_spacing_from_diameter` lalu `check_spacing_limits`,
       sehingga spasi yang melanggar batas SNI muncul sebagai NaN, bukan sebagai angka
       yang tampak wajar.
    """
    as_design_mm2 = as_design_array(design) * config.DISPLAY_UNITS["steel_area"][1]
    to_si_len = 1.0 / config.DISPLAY_UNITS["length"][1]

    if inputs.rebar_mode == "diameter_fixed":
        diameter = inputs.config_diameter_mm
        spacing_mm = np.asarray(
            sk_rebar.calc_spacing_from_diameter(as_design_mm2, diameter), dtype=np.float64
        )
        spacing_mm = np.asarray(
            sk_rebar.check_spacing_limits(spacing_mm, inputs.thickness_mm, diameter),
            dtype=np.float64,
        )
        status = _selection_status(design.status, spacing_mm, no_need=np.isinf(spacing_mm))
        # `inf` berarti "tidak perlu tulangan"; dibiarkan inf agar tidak tertukar dengan
        # NaN yang di sini berarti spasi melanggar batas.
        return RebarSelection(
            kind=SELECTION_SPACING,
            direction=design.direction,
            face=design.face,
            values=spacing_mm * to_si_len,
            labels=(),
            quantity="length",
            status=status,
        )

    if inputs.rebar_select_codes:
        index, sorted_codes, _ = sk_rebar.select_config_from_As(
            as_design_mm2, list(inputs.rebar_select_codes), inputs.spacing_mm
        )
        index = np.asarray(index, dtype=np.float64)
        status = _selection_status(design.status, index, no_need=index == 0.0)
        return RebarSelection(
            kind=SELECTION_CONFIG,
            direction=design.direction,
            face=design.face,
            values=index,
            labels=tuple(sorted_codes),
            quantity="",
            status=status,
        )

    diameter_mm = design.bar_diameter * config.DISPLAY_UNITS["length"][1]
    status = _selection_status(design.status, diameter_mm, no_need=diameter_mm == 0.0)
    return RebarSelection(
        kind=SELECTION_DIAMETER,
        direction=design.direction,
        face=design.face,
        values=design.bar_diameter,
        labels=tuple(f"D{int(d)}" for d in sk_rebar.AVAILABLE_DIAMETERS),
        quantity="length",
        status=status,
    )


def _selection_status(
    base_status: np.ndarray, values: np.ndarray, *, no_need: np.ndarray
) -> np.ndarray:
    """Status seleksi, memisahkan "tidak perlu" dari "tidak ada batang yang muat".

    `shell-kit` memakai NaN untuk keduanya-berbeda: NaN pada `As` berarti penampang tidak
    memadai, sedangkan NaN pada hasil seleksi berarti `As` tercapai tetapi tidak ada batang
    dalam daftar yang cukup besar. Dua sebab itu menuntut tindakan berbeda -- menebalkan
    pelat versus memperbesar daftar batang -- sehingga tidak boleh dilaporkan sama.
    """
    status = np.array(base_status, dtype=object, copy=True)
    unresolved = ~np.isfinite(values) & (status == STATUS_OK)
    status[unresolved] = STATUS_SECTION_INADEQUATE
    status[no_need & (status == STATUS_OK)] = STATUS_NO_MOMENT
    return status


def design_all_faces(
    moments_by_direction: dict[str, np.ndarray],
    inputs: CapacityInputs,
) -> dict[tuple[str, str], FlexureDesign]:
    """Keempat kombinasi arah x muka sekaligus, siap ditulis ke CSV dan kontur."""
    out: dict[tuple[str, str], FlexureDesign] = {}
    for direction, face in config.REBAR_FACES:
        out[(direction, face)] = flexure_design(
            moments_by_direction[direction], inputs, direction=direction, face=face
        )
    return out


def strip_flexure_design(
    strip_rows: list[dict[str, Any]],
    inputs: CapacityInputs,
) -> list[dict[str, Any]]:
    """`As perlu` dari momen LAJUR di muka pier -- inilah angka desain sesungguhnya.

    Kontur `As` per elemen adalah peta, bukan angka desain: di tepi zona jepit pier
    terdapat singularitas tegangan (PRD Bagian 8.3 keterbatasan #2) yang menghasilkan
    `As` sangat besar dan tidak bermakna. Momen lajur sudah terintegrasi sepanjang
    potongan sehingga singularitas itu terata-rata -- itulah sebabnya baris inilah yang
    dipakai, bukan puncak per elemen.

    Momen lajur bertanda. Tandanya menentukan muka: positif -> tulangan BAWAH.
    """
    rows: list[dict[str, Any]] = []
    for row in strip_rows:
        width = float(row.get("width_m") or 0.0)
        m_total = float(row["M_total_Nm"])
        usable = width > 0.0 and np.isfinite(m_total)
        mu_per_m = m_total / width if usable else float("nan")
        face = "bawah" if mu_per_m >= 0.0 else "atas"
        design = flexure_design(
            np.array([mu_per_m]), inputs, direction=str(row["direction"]), face=face
        )
        rows.append(
            {
                **row,
                "face": face,
                "Mu_per_m_Nm": float(design.mu[0]),
                "d_eff_m": float(design.d_effective[0]),
                "bar_diameter_m": float(design.bar_diameter[0]),
                "As_required_m2_per_m": float(design.as_required[0]),
                "As_min_m2_per_m": design.as_min,
                "As_design_m2_per_m": _as_design(design.as_required[0], design.as_min),
                "status": str(design.status[0]),
            }
        )
    return rows


def governing_element_design(
    designs_by_combo: dict[str, dict[tuple[str, str], FlexureDesign]],
    mesh: MeshModel,
) -> list[dict[str, Any]]:
    """`As pakai` terbesar per (arah, muka) lintas kombinasi, BESERTA lokasinya.

    Ringkasan desain pada `design.rebar_basis = "element"`. Satu baris per arah x muka,
    mengikuti pola `shell-kit`: konturnya deliverable, angka maksimum ringkasannya.

    **Lokasi wajib ikut, dan itu bukan kelengkapan kosmetik.** Tanpa koordinatnya, pembaca
    tidak dapat membedakan puncak yang jatuh di sudut pier -- singularitas tumpuan jepit,
    yang membesar terus setiap mesh diperhalus dan bukan kebutuhan nyata -- dari puncak di
    tempat lain, yang memang harus dipenuhi. Itu satu-satunya cara membaca angka maksimum
    mode ini secara bertanggung jawab.

    `n_inadequate` dibawa apa adanya: elemen yang penampangnya tidak memadai menghasilkan
    `As` = NaN, sehingga ia TIDAK akan pernah muncul sebagai maksimum. Tanpa hitungannya,
    kegagalan penampang justru tersembunyi di balik angka yang terlihat wajar.

    `as_min_governs` menandai muka yang maksimumnya jatuh tepat di `As_min`. Di sana
    SELURUH elemen seri, sehingga koordinat yang dilaporkan hanyalah elemen pertama yang
    kebetulan ditemui -- bukan lokasi istimewa. Menyajikannya seolah bermakna akan
    menyesatkan justru pada muka yang paling sering terjadi di pilecap tebal.
    """
    if not designs_by_combo:
        raise ValueError("designs_by_combo kosong; ringkasan per elemen tidak dapat dibuat.")

    rows: list[dict[str, Any]] = []
    for direction, face in config.REBAR_FACES:
        terbaik: dict[str, Any] | None = None
        n_inadequate = 0
        for combo, designs in designs_by_combo.items():
            design = designs[(direction, face)]
            n_inadequate += design.n_inadequate
            values = as_design_array(design)
            if not np.any(np.isfinite(values)):
                continue
            index = int(np.nanargmax(values))
            value = float(values[index])
            if terbaik is not None and value <= float(terbaik["As_design_m2_per_m"]):
                continue
            terbaik = {
                "direction": direction,
                "face": face,
                "combo": combo,
                "elem_tag": int(mesh.elem_tags[index]),
                "centroid_x_m": float(mesh.elem_centroid[index, 0]),
                "centroid_y_m": float(mesh.elem_centroid[index, 1]),
                "group": str(mesh.group_names[int(mesh.elem_group[index])]),
                "Mu_per_m_Nm": float(design.mu[index]),
                "d_eff_m": float(design.d_effective[index]),
                "As_required_m2_per_m": float(design.as_required[index]),
                "As_min_m2_per_m": design.as_min,
                "As_design_m2_per_m": value,
                "status": str(design.status[index]),
            }
        if terbaik is not None:
            as_min = float(terbaik["As_min_m2_per_m"])
            rows.append(
                {
                    **terbaik,
                    "n_inadequate": n_inadequate,
                    "as_min_governs": float(terbaik["As_design_m2_per_m"]) <= as_min * (1.0 + 1e-9),
                }
            )
    return rows


def governing_strip_design(
    strip_design_by_combo: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Baris lajur dengan `As pakai` terbesar untuk tiap kombinasi arah x muka.

    Inilah angka yang layak muncul di `SUMMARY.md`: satu baris per arah dan muka, lengkap
    dengan kombinasi serta lajur asalnya, sehingga setiap angka dapat dilacak balik ke
    baris di `calc_sheet.md` kombinasi tersebut.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for combo, rows in strip_design_by_combo.items():
        for row in rows:
            # Nilai `peak` ditandai SINGULAR dan bukan momen desain -- tidak boleh menjadi
            # governing (PRD Bagian 7.2(5)).
            if row.get("singular"):
                continue
            key = (str(row["direction"]), str(row["face"]))
            value = float(row["As_design_m2_per_m"])
            if not np.isfinite(value):
                continue
            current = best.get(key)
            if current is None or value > float(current["As_design_m2_per_m"]):
                best[key] = {**row, "combo": combo}
    return [best[key] for key in sorted(best)]


def envelope_strip_design(
    strip_design_by_combo: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """`As pakai` terbesar per LAJUR lintas kombinasi -- bukan diciutkan jadi 4 baris.

    `governing_strip_design` menjawab "berapa maksimum keseluruhan"; fungsi ini menjawab
    "apa yang saya pasang di lajur ini". Untuk mendetailkan tulangan, yang kedua itulah
    yang dibutuhkan -- tanpanya angka per lajur hanya bisa didapat dengan membuka calc
    sheet setiap kombinasi satu per satu.

    **`face` ikut menjadi kunci, bukan diturunkan sesudahnya.** Tanda momen satu lajur
    dapat berbalik antar kombinasi, sehingga satu lajur bisa menuntut tulangan BAWAH dari
    satu kombinasi dan tulangan ATAS dari kombinasi lain. Mengunci satu muka per lajur
    akan menghilangkan salah satunya tanpa jejak.
    """
    best: dict[tuple[str, str, str, int, str], dict[str, Any]] = {}
    for combo, rows in strip_design_by_combo.items():
        for row in rows:
            if row.get("singular"):
                continue
            value = float(row["As_design_m2_per_m"])
            if not np.isfinite(value):
                continue
            key = (
                str(row.get("pier_id", "-")),
                str(row.get("sisi", "-")),
                str(row["direction"]),
                int(row["strip"]),
                str(row["face"]),
            )
            current = best.get(key)
            if current is None or value > float(current["As_design_m2_per_m"]):
                best[key] = {**row, "combo": combo}
    return [best[key] for key in sorted(best)]


def _as_design(as_required: float, as_min: float) -> float:
    """`As` yang dipakai = maks(perlu, minimum). NaN tetap NaN -- tidak diam-diam jadi min."""
    if not np.isfinite(as_required):
        return float("nan")
    return max(float(as_required), float(as_min))


def as_design_array(design: FlexureDesign) -> np.ndarray:
    """`maks(As perlu, As min)` per elemen [m^2/m], NaN dipertahankan."""
    return np.where(
        np.isfinite(design.as_required),
        np.maximum(design.as_required, design.as_min),
        np.nan,
    )


# ---------------------------------------------------------------------------
# Kapasitas geser satu arah
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OneWayShearCapacity:
    """Kapasitas geser satu arah pada satu penampang. Seluruh nilai SI."""

    label: str
    v_u: float  # N/m
    d_effective: float  # m
    v_c: float  # N/m
    phi_v_c: float  # N/m
    v_s_max: float  # N/m
    av_per_s: float  # m^2/m
    status: str
    clause: str

    @property
    def demand_capacity_ratio(self) -> float:
        return abs(self.v_u) / self.phi_v_c if self.phi_v_c > 0 else float("nan")

    @property
    def needs_shear_steel(self) -> bool:
        return abs(self.v_u) > self.phi_v_c


def one_way_shear_capacity(
    v_u_si: float,
    d_effective: float,
    inputs: CapacityInputs,
    *,
    label: str,
) -> OneWayShearCapacity:
    """`V_c`, `phi V_c`, dan `Av/s` untuk satu penampang geser satu arah.

    `v_u_si` dalam N/m (geser per satuan lebar), `d_effective` dalam m.
    Perhitungan per lajur 1 m, sesuai `shell_kit.rebar.STRIP_WIDTH_MM`.
    """
    if not np.isfinite(v_u_si) or not np.isfinite(d_effective) or d_effective <= 0.0:
        return OneWayShearCapacity(
            label=label,
            v_u=float(v_u_si),
            d_effective=float(d_effective),
            v_c=float("nan"),
            phi_v_c=float("nan"),
            v_s_max=float("nan"),
            av_per_s=float("nan"),
            status=STATUS_UNDEFINED,
            clause=SNI_CLAUSES["Vc"],
        )

    d_mm = d_effective * config.DISPLAY_UNITS["length"][1]
    bw_mm = float(sk_rebar.STRIP_WIDTH_MM)

    v_c_n = float(sk_rebar.calc_Vc(inputs.fc_mpa, bw_mm, d_mm))
    v_s_max_n = float(sk_rebar.calc_Vs_max(inputs.fc_mpa, bw_mm, d_mm))
    vu_kn_per_m = abs(v_u_si) * config.DISPLAY_UNITS["shear_per_width"][1]
    av_per_s_mm = float(
        sk_rebar.calc_shear_Av_per_s(vu_kn_per_m, inputs.fc_mpa, inputs.fy_mpa, d_mm)
    )

    status = STATUS_OK if np.isfinite(av_per_s_mm) else STATUS_WEB_CRUSHED
    if status == STATUS_WEB_CRUSHED:
        _log.warning(
            "Geser satu arah %s: BADAN HANCUR -- V_u melampaui batas V_s maksimum. "
            "Tebal pelat atau mutu beton harus ditinjau ulang.",
            label,
        )

    # V_c dan V_s_max dari shell-kit dalam newton untuk lajur 1 m -> N/m dalam SI.
    return OneWayShearCapacity(
        label=label,
        v_u=float(v_u_si),
        d_effective=float(d_effective),
        v_c=v_c_n,
        phi_v_c=inputs.phi_shear * v_c_n,
        v_s_max=v_s_max_n,
        av_per_s=av_per_s_mm / config.DISPLAY_UNITS["shear_steel_ratio"][1],
        status=status,
        clause=SNI_CLAUSES["Vc"],
    )


# ---------------------------------------------------------------------------
# Peta sengkang per elemen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShearRebarMap:
    """Kebutuhan sengkang per elemen untuk satu arah. Seluruh nilai SI.

    .. warning::
       Ini **peta orientasi**, bukan angka desain -- sama seperti peta `As` per elemen.
       Geser satu arah pilecap didesain pada penampang `d` dari muka pier
       (`one_way_shear_capacity`), bukan per elemen.
    """

    direction: str
    v_u: np.ndarray  # N/m
    d_shear: float  # m
    phi_v_c: float  # N/m
    #: `Av/s` [m^2/m] SETELAH `Av,min` diterapkan -- ini yang dipakai memilih diameter.
    av_per_s: np.ndarray
    #: `Av/s` [m^2/m] TANPA `Av,min`; > 0 hanya bila beton memang tidak cukup.
    av_per_s_no_min: np.ndarray
    stirrup_diameter: np.ndarray  # m
    status: np.ndarray
    #: Diameter sengkang yang BOLEH dipilih [m], terurut menaik.
    #:
    #: Ada di sini karena `stirrup_diameter` adalah besaran **diskret**: setiap nilainya
    #: pasti 0, anggota persis daftar ini, atau NaN. Tanpa daftarnya ikut dibawa, hilir
    #: tidak punya apa pun untuk membedakan besaran diskret dari besaran kontinu -- dan
    #: itulah yang dulu membuat plot diameter sengkang digambar sebagai gradasi mulus
    #: sementara plot diameter lentur sudah bertingkat.
    available_diameters: tuple[float, ...] = ()

    @property
    def labels(self) -> tuple[str, ...]:
        """Label kategori untuk colorbar diskret, mis. `("D10", "D13", ...)`."""
        factor = config.DISPLAY_UNITS["length"][1]
        return tuple(f"D{d * factor:.0f}" for d in self.available_diameters)

    @property
    def is_categorical(self) -> bool:
        return bool(self.available_diameters)

    @property
    def n_needs_stirrup(self) -> int:
        """Elemen yang beton-nya BENAR-BENAR tidak cukup (`V_u > phi V_c`).

        Sengaja BUKAN `av_per_s > 0`: dengan `Av,min` aktif, jumlah itu jauh lebih besar
        dan terbaca seolah sebagian besar pelat butuh sengkang. DIUKUR pada ex01: 31
        elemen di sini versus 307 bila memakai `av_per_s > 0`.
        """
        return int(np.count_nonzero(np.abs(self.v_u) > self.phi_v_c))

    @property
    def n_av_min_only(self) -> int:
        """Elemen yang hanya terkena `Av,min` -- beton cukup, tetapi kode minta minimum."""
        return int(np.count_nonzero((self.av_per_s > 0.0) & (self.av_per_s_no_min <= 0.0)))

    @property
    def n_web_crushed(self) -> int:
        return int(np.count_nonzero(self.status == STATUS_WEB_CRUSHED))


def shear_rebar_map(
    v_u_si: np.ndarray,
    inputs: CapacityInputs,
    *,
    direction: str,
) -> ShearRebarMap:
    """`Av/s` dan diameter sengkang per elemen dari geser transversal `q`.

    `dv` mengikuti konvensi `shell-kit`: kedalaman efektif untuk **asumsi D16 di muka
    bawah**, TIDAK diiterasi terhadap diameter sengkang yang nanti terpilih. Asumsi itu
    dicetak di laporan karena ia memengaruhi `V_c` dan tidak dapat dibaca dari hasil.

    `calc_shear_Av_per_s` dipanggil DUA KALI, dengan dan tanpa `Av,min`. Tanpa itu
    "beton tidak cukup" dan "kode minta minimum" tidak dapat dibedakan di hilir -- dan
    keduanya menuntut kesimpulan yang sangat berbeda dari pembaca.
    """
    if direction not in ("x", "y"):
        raise ValueError(f"direction = {direction!r} harus 'x' atau 'y'.")

    values = np.asarray(v_u_si, dtype=np.float64)
    dv_mm = float(
        sk_rebar.calc_effective_depth(
            inputs.thickness_mm, inputs.cover_mm, _SHEAR_DEPTH_DIAMETER_MM, direction, "bottom"
        )
    )
    vu_kn_per_m = np.abs(values) * config.DISPLAY_UNITS["shear_per_width"][1]

    av_mm = np.asarray(
        sk_rebar.calc_shear_Av_per_s(vu_kn_per_m, inputs.fc_mpa, inputs.fy_mpa, dv_mm),
        dtype=np.float64,
    )
    av_no_min_mm = np.asarray(
        sk_rebar.calc_shear_Av_per_s(
            vu_kn_per_m, inputs.fc_mpa, inputs.fy_mpa, dv_mm, apply_av_min=False
        ),
        dtype=np.float64,
    )
    # Daftar diameter yang benar-benar dipakai shell-kit; ikut dibawa ke hasil supaya
    # hilir tahu besaran ini diskret (lihat `ShearRebarMap.available_diameters`).
    allowed_mm = inputs.stirrup_diameters_mm
    if allowed_mm is None:
        allowed_mm = [float(d) for d in sk_rebar.SHEAR_DIAMETERS]

    diameter_mm = np.asarray(
        sk_rebar.calc_shear_diameter(
            av_mm,
            inputs.stirrup_long_mm,
            inputs.stirrup_trans_mm,
            available_diameters=inputs.stirrup_diameters_mm,
        ),
        dtype=np.float64,
    )

    status = np.full(values.shape, STATUS_OK, dtype=object)
    status[~np.isfinite(values)] = STATUS_UNDEFINED
    status[np.isfinite(values) & ~np.isfinite(av_mm)] = STATUS_WEB_CRUSHED
    # Diameter NaN sementara Av/s terdefinisi = tidak ada sengkang yang cukup besar.
    status[np.isfinite(av_mm) & ~np.isfinite(diameter_mm)] = STATUS_SECTION_INADEQUATE

    v_c_n = float(sk_rebar.calc_Vc(inputs.fc_mpa, float(sk_rebar.STRIP_WIDTH_MM), dv_mm))
    to_si_area = 1.0 / config.DISPLAY_UNITS["shear_steel_ratio"][1]
    to_si_len = 1.0 / config.DISPLAY_UNITS["length"][1]

    result = ShearRebarMap(
        direction=direction,
        v_u=values,
        d_shear=dv_mm * to_si_len,
        phi_v_c=inputs.phi_shear * v_c_n,
        av_per_s=av_mm * to_si_area,
        av_per_s_no_min=av_no_min_mm * to_si_area,
        stirrup_diameter=diameter_mm * to_si_len,
        status=status,
        available_diameters=tuple(sorted(d * to_si_len for d in allowed_mm)),
    )
    if result.n_web_crushed:
        _log.warning(
            "Peta geser arah %s: %d elemen BADAN HANCUR (V_u melampaui V_s maksimum).",
            direction,
            result.n_web_crushed,
        )
    return result


#: Diameter yang diasumsikan untuk menghitung `dv` geser. Mengikuti `shell-kit`, yang
#: TIDAK mengiterasi kedalaman geser terhadap diameter sengkang terpilih.
_SHEAR_DEPTH_DIAMETER_MM: float = 16.0


def one_way_shear_from_checks(
    checks: list[ShearCheck],
    inputs: CapacityInputs,
) -> dict[str, OneWayShearCapacity]:
    """Kapasitas untuk setiap penampang geser SATU ARAH dari `postproc_engine`.

    Penampang **pons** sengaja dilewati: `shell_kit.rebar.calc_Vc` adalah geser satu arah
    (`bw x dv`), bukan dua arah. Memakainya untuk pons berarti menerapkan rumus di luar
    lingkupnya -- persis jenis kesalahan yang tidak boleh terjadi pada tool desain.
    Pons tetap `NOT_EVALUATED` (PRD Bagian 17 item 3, bagian pons).
    """
    out: dict[str, OneWayShearCapacity] = {}
    for check in checks:
        if not check.kind.startswith("one_way"):
            continue
        width = check.b_o_m
        v_u_per_m = (
            float(check.V_u_N) / width
            if width and width > 0.0 and np.isfinite(check.V_u_N)
            else float("nan")
        )
        key = f"{check.pier_id}|{check.kind}"
        out[key] = one_way_shear_capacity(v_u_per_m, check.d_m, inputs, label=key)
    return out


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def provenance_block(inputs: CapacityInputs) -> dict[str, Any]:
    """Asal-usul setiap angka kapasitas, untuk calc sheet & `run_manifest.json`.

    Tanpa blok ini, angka kapasitas di laporan tidak dapat ditelusuri ke pasal mana pun --
    dan itulah yang membedakan hasil yang dapat diperiksa dari angka yang muncul begitu
    saja (PRD Core 4).
    """
    return {
        "engine": "shell-kit",
        "engine_version": _shell_kit_version(),
        "standard": "SNI 2847:2019",
        "functions": [
            "shell_kit.rebar.solve_rebar_iterative",
            "shell_kit.rebar.calc_as_min_per_face",
            "shell_kit.rebar.calc_Vc",
            "shell_kit.rebar.calc_Vs_max",
            "shell_kit.rebar.calc_shear_Av_per_s",
        ],
        "clauses": dict(SNI_CLAUSES),
        "phi_flexure": inputs.phi_flexure,
        "phi_shear": inputs.phi_shear,
        "phi_source": inputs.phi_source,
        "fy_MPa": inputs.fy_mpa,
        "fy_source": inputs.fy_source,
        "strip_width_mm": float(sk_rebar.STRIP_WIDTH_MM),
        "rebar_mode": inputs.rebar_mode,
        "rebar_spacing_mm": inputs.spacing_mm or None,
        "rebar_config": inputs.rebar_config,
        "rebar_select_codes": list(inputs.rebar_select_codes) or None,
        "stirrup_grid_mm": [inputs.stirrup_long_mm, inputs.stirrup_trans_mm],
        "dv_assumed_bar_mm": _SHEAR_DEPTH_DIAMETER_MM,
        "catatan_dv": (
            f"dv geser dihitung untuk asumsi batang D{_SHEAR_DEPTH_DIAMETER_MM:.0f} di muka "
            "bawah dan TIDAK diiterasi terhadap diameter sengkang terpilih (mengikuti "
            "shell-kit). Asumsi ini memengaruhi V_c."
        ),
        "as_min_surface_zone_mm": inputs.surface_zone_mm,
        "catatan_as_min": (
            "As_min dihitung pada setengah tebal penuh (murni SNI 2847:2019)."
            if inputs.surface_zone_mm is None
            else (
                f"As_min dibatasi pada zona permukaan {inputs.surface_zone_mm:.0f} mm per "
                "muka. SNI 2847:2019 TIDAK menyatakan batas ini; nilainya engineering "
                "judgement mengikuti ACI 350-06 Ps. 7.12.2.1 (300 mm untuk elemen >600 mm) "
                "dan merupakan TANGGUNG JAWAB engineer yang menetapkannya."
            )
        ),
        "catatan_pons": (
            "shell-kit TIDAK menyediakan cek geser dua arah (pons). calc_Vc adalah geser "
            "SATU ARAH (bw x dv). Kapasitas pons tetap NOT_EVALUATED; V_u dan b_o pons "
            "sudah dihitung pilecap-fem dari keseimbangan gaya."
        ),
        "peringatan_deep_pilecap": (
            "shell-kit adalah alat desain PELAT per lajur 1 m. Bila pilecap berperilaku "
            "deep member, desain lentur pelat ini TIDAK SAH (PRD Bagian 8.3 keterbatasan "
            "#1). Ambang deep pile cap belum dikonfirmasi (PRD Bagian 17 item 5)."
        ),
    }
