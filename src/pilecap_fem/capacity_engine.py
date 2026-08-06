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
    spacing: float  # m
    phi_flexure: float
    phi_shear: float
    phi_source: str
    fy_source: str

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

        return cls(
            fc=float(material["fc"]),
            fy=float(design["fy"]),
            thickness=float(cfg["pilecap"]["thickness"]),
            cover=float(design["cover"]),
            spacing=float(design["rebar_spacing"]),
            phi_flexure=phi_flexure,
            phi_shear=phi_shear,
            phi_source=phi_source,
            fy_source=str(design.get("fy_source") or "TIDAK DICATAT"),
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
    """Desain lentur per elemen memakai `shell_kit.rebar.solve_rebar_iterative`.

    Dipakai solver iteratif, bukan `calc_as_required` langsung, karena kedalaman efektif
    bergantung pada diameter batang yang terpilih dan sebaliknya.
    """
    if direction not in ("x", "y"):
        raise ValueError(f"direction = {direction!r} harus 'x' atau 'y'.")

    mu_si = _face_moments(moments_si, face)
    # SI (N.m/m) -> kN.m/m yang diminta shell-kit.
    mu_knm = mu_si * config.DISPLAY_UNITS["moment_per_width"][1]

    as_mm2, d_mm, diameter_mm, _ = sk_rebar.solve_rebar_iterative(
        np.nan_to_num(mu_knm, nan=0.0),
        inputs.fc_mpa,
        inputs.fy_mpa,
        inputs.thickness_mm,
        inputs.cover_mm,
        direction,
        layer,
        inputs.spacing_mm,
        phi=inputs.phi_flexure,
    )
    as_mm2 = np.asarray(as_mm2, dtype=np.float64)
    d_mm = np.asarray(d_mm, dtype=np.float64)
    diameter_mm = np.asarray(diameter_mm, dtype=np.float64)

    as_min_mm2 = float(sk_rebar.calc_as_min_per_face(inputs.fy_mpa, inputs.thickness_mm))

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
