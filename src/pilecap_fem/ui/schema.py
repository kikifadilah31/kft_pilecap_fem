"""Deskripsi formulir `pilecap-ui` dan pembangun `pilecap_config.json`.

**TIDAK mengimpor streamlit.** Modul ini berisi satu-satunya bagian UI yang dapat salah
secara diam-diam -- menghasilkan config yang ditolak engine -- sehingga ia harus dapat
diuji pada lingkungan yang hanya memasang paket inti.

.. rubric:: Mengapa formulir dijalankan dari daftar, bukan ditulis satu per satu

`pilecap-fem` menerima ~45 field config. Menulis satu widget per field berarti ~45 tempat
yang harus disinkronkan manual dengan `validators.py` setiap kali skema berubah. Dengan
daftar `Field`, `app.py` cukup melakukan loop, dan pilihan enum diambil **dari sumbernya**
(`validators.REBAR_MODES`, `config.THEMES`, `fem_engine.SUPPORTED_*`, tabel kode
`shell-kit`) sehingga tidak ada salinan yang dapat basi.

.. rubric:: Satuan

Config ditulis dalam **satuan tampilan user** (blok `units`), persis seperti config yang
ditulis tangan -- bukan SI. Konversi ke SI tetap satu-satunya urusan `io_utils`
(PRD Bagian 4.2).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pilecap_fem import config, validators

#: Subfolder tempat config hasil formulir ditulis.
#:
#: TIDAK ditulis ke folder input, dan itu bukan selera. `io_utils.autodetect` memakai glob
#: `*config*.json` dan **RAISE bila menemukan lebih dari satu**. Menumpuk config
#: bertimestamp di folder input akan merusak `pilecap-run` tanpa `--config` bagi siapa pun
#: yang menjalankannya kemudian dari CLI. Glob itu tidak rekursif, sehingga subfolder aman.
CONFIG_SUBDIR = "ui_configs"
CONFIG_PREFIX = "pilecap_config_"


def _shell_elements() -> tuple[str, ...]:
    """Diimpor lambat: `fem_engine` menarik openseespy, yang tidak dibutuhkan UI.

    UI hanya menyusun argumen; solver dijalankan di proses lain. Memuat DLL OpenSees ke
    dalam proses Streamlit hanya untuk membaca dua tuple konstanta adalah biaya tanpa
    manfaat.
    """
    from pilecap_fem import fem_engine

    return tuple(fem_engine.SUPPORTED_SHELL_ELEMENTS)


def _sections() -> tuple[str, ...]:
    from pilecap_fem import fem_engine

    return tuple(fem_engine.SUPPORTED_SECTIONS)


def _config_codes() -> tuple[str, ...]:
    from shell_kit import rebar as sk_rebar

    return tuple(sk_rebar.get_available_config_codes())


def _stirrup_diameters() -> tuple[float, ...]:
    from shell_kit import rebar as sk_rebar

    return tuple(float(d) for d in sk_rebar.SHEAR_DIAMETERS)


@dataclass(frozen=True)
class Field:
    """Satu field formulir yang dipetakan ke satu kunci config bertitik."""

    key: str  # "pilecap.thickness"
    label: str
    kind: str  # number | int | text | select | multiselect | bool | pair
    default: Any = None
    unit: str = ""  # "length" | "force" | "stress" | teks bebas
    choices: tuple[Any, ...] = ()
    choices_fn: Callable[[], tuple[Any, ...]] | None = None
    help: str = ""
    #: Boleh bernilai null. Field wajib TIDAK boleh punya bawaan yang tampak sah bila
    #: engine menuntut user menetapkannya sendiri (mis. `E_source`, `fy_source`).
    optional: bool = False
    #: Ditampilkan hanya bila predikat ini benar terhadap nilai formulir saat ini.
    visible_when: Callable[[dict[str, Any]], bool] | None = None
    min_value: float | None = None
    max_value: float | None = None

    @property
    def block(self) -> str:
        return self.key.split(".", 1)[0]

    @property
    def name(self) -> str:
        return self.key.split(".", 1)[1]

    def options(self) -> tuple[Any, ...]:
        return self.choices_fn() if self.choices_fn is not None else self.choices


@dataclass(frozen=True)
class Section:
    """Kelompok field yang tampil sebagai satu container di formulir."""

    title: str
    icon: str
    fields: tuple[Field, ...] = field(default_factory=tuple)
    help: str = ""
    #: Entitas geometri yang di-override CSV; dipakai app.py untuk menandai bagian ini
    #: "akan diabaikan" ketika CSV terkait terdeteksi.
    override_entity: str | None = None


# ---------------------------------------------------------------------------
# Predikat visibilitas -- mencerminkan cabang wajib di validators.py
# ---------------------------------------------------------------------------


def _is_rectangular(v: dict[str, Any]) -> bool:
    return v.get("pier.shape") == "rectangular"


def _is_circular(v: dict[str, Any]) -> bool:
    return v.get("pier.shape") == "circular"


def _is_graded(v: dict[str, Any]) -> bool:
    return v.get("mesh.size_mode") == "graded"


def _is_spacing_fixed(v: dict[str, Any]) -> bool:
    return v.get("design.rebar_mode") == "spacing_fixed"


def _is_diameter_fixed(v: dict[str, Any]) -> bool:
    return v.get("design.rebar_mode") == "diameter_fixed"


def _is_layered(v: dict[str, Any]) -> bool:
    return v.get("analysis.section") == "LayeredShell"


# ---------------------------------------------------------------------------
# Skema formulir
# ---------------------------------------------------------------------------

SECTIONS: tuple[Section, ...] = (
    Section(
        title="Proyek",
        icon=":material/description:",
        fields=(
            Field("project.name", "Nama proyek", "text", ""),
            Field("project.engineer", "Engineer", "text", ""),
            Field("project.date", "Tanggal", "text", datetime.now().strftime("%Y-%m-%d")),
        ),
    ),
    Section(
        title="Satuan masukan",
        icon=":material/straighten:",
        help="Seluruh angka di formulir ini ditulis dalam satuan yang dipilih di sini.",
        fields=(
            Field(
                "units.length",
                "Panjang",
                "select",
                "mm",
                choices=tuple(config.LENGTH_TO_SI),
            ),
            Field("units.force", "Gaya", "select", "kN", choices=tuple(config.FORCE_TO_SI)),
            Field(
                "units.stress",
                "Tegangan",
                "select",
                "MPa",
                choices=tuple(config.STRESS_TO_SI),
            ),
        ),
    ),
    Section(
        title="Pilecap",
        icon=":material/crop_square:",
        override_entity="pilecap",
        fields=(
            Field("pilecap.thickness", "Tebal", "number", 1200.0, unit="length", min_value=0.0),
            Field("pilecap.length_x", "Panjang arah X", "number", 4800.0, unit="length"),
            Field("pilecap.length_y", "Panjang arah Y", "number", 4800.0, unit="length"),
            Field("pilecap.origin", "Titik asal [x, y]", "pair", [0.0, 0.0], unit="length"),
        ),
    ),
    Section(
        title="Pile",
        icon=":material/circle:",
        override_entity="pile",
        fields=(
            Field(
                "pile.diameter",
                "Diameter",
                "number",
                800.0,
                unit="length",
                help="Selalu dibutuhkan -- juga sebagai bawaan bila CSV koordinat pile "
                "tidak punya kolom diameter.",
            ),
            Field("pile.n_col", "Jumlah kolom", "int", 2, min_value=1),
            Field("pile.n_row", "Jumlah baris", "int", 2, min_value=1),
            Field("pile.spacing_x", "Spasi arah X", "number", 2400.0, unit="length"),
            Field("pile.spacing_y", "Spasi arah Y", "number", 2400.0, unit="length"),
            Field("pile.grid_origin", "Pusat grid [x, y]", "pair", [0.0, 0.0], unit="length"),
            Field(
                "pile.modeling",
                "Pemodelan beban",
                "select",
                "pressure",
                choices=("pressure", "nodal"),
            ),
        ),
    ),
    Section(
        title="Pier",
        icon=":material/view_column:",
        override_entity="pier",
        fields=(
            Field(
                "pier.shape",
                "Bentuk",
                "select",
                "rectangular",
                choices=("rectangular", "circular"),
            ),
            Field(
                "pier.width_x",
                "Lebar arah X",
                "number",
                1200.0,
                unit="length",
                visible_when=_is_rectangular,
            ),
            Field(
                "pier.width_y",
                "Lebar arah Y",
                "number",
                1200.0,
                unit="length",
                visible_when=_is_rectangular,
            ),
            Field(
                "pier.diameter",
                "Diameter",
                "number",
                1800.0,
                unit="length",
                visible_when=_is_circular,
            ),
            Field("pier.centerline", "Titik pusat [x, y]", "pair", [0.0, 0.0], unit="length"),
            Field(
                "pier.support",
                "Tumpuan",
                "select",
                "fixed",
                choices=("fixed",),
                help="Hanya jepit 6 DOF yang tersedia di v1.0.",
            ),
        ),
    ),
    Section(
        title="Material",
        icon=":material/layers:",
        fields=(
            Field("material.fc", "f'c", "number", 30.0, unit="stress", min_value=0.0),
            Field(
                "material.E",
                "Modulus elastisitas E",
                "number",
                25000.0,
                unit="stress",
                min_value=0.0,
                help="Tool TIDAK menghitung E dari f'c: rumusnya belum dikonfirmasi "
                "pasalnya, dan angka tanpa sumber dilarang.",
            ),
            Field(
                "material.E_source",
                "Asal nilai E",
                "text",
                "",
                help="WAJIB. Dicetak apa adanya di calc_sheet.md dan run_manifest.json "
                'agar checker dapat menelusurinya. Mis. "SNI 2847:2019 Ps. X.Y" atau '
                '"hasil uji lab 2026-01-15".',
            ),
            Field(
                "material.poisson",
                "Rasio Poisson",
                "number",
                0.2,
                min_value=config.POISSON_MIN,
                max_value=config.POISSON_MAX - 1e-9,
            ),
            Field(
                "material.density",
                "Berat jenis",
                "number",
                24.0,
                unit="kN/m^3",
                optional=True,
                min_value=0.0,
            ),
        ),
    ),
    Section(
        title="Mesh",
        icon=":material/grid_on:",
        fields=(
            Field(
                "mesh.size_mode",
                "Mode ukuran",
                "select",
                "uniform",
                choices=("uniform", "graded"),
            ),
            Field("mesh.size_global", "Ukuran global", "number", 130.0, unit="length"),
            Field(
                "mesh.size_local_pile",
                "Ukuran lokal di pile",
                "number",
                None,
                unit="length",
                optional=True,
                visible_when=_is_graded,
                help="Wajib salah satu (pile atau pier) pada mode graded, dan harus "
                "<= ukuran global.",
            ),
            Field(
                "mesh.size_local_pier",
                "Ukuran lokal di pier",
                "number",
                None,
                unit="length",
                optional=True,
                visible_when=_is_graded,
            ),
            Field(
                "mesh.algorithm",
                "Mesh.Algorithm",
                "select",
                config.GMSH_ALGORITHM_DEFAULT,
                choices=tuple(sorted(config.GMSH_VALID_ALGORITHMS)),
                help="11 = Quasi-structured Quad, bagian dari kontrak numerik tool ini.",
            ),
            Field(
                "mesh.recombination_algorithm",
                "Mesh.RecombinationAlgorithm",
                "select",
                config.GMSH_RECOMB_ALGORITHM_DEFAULT,
                choices=tuple(sorted(config.GMSH_VALID_RECOMB_ALGORITHMS)),
                help="3 = Blossom full-quad.",
            ),
            Field("mesh.recombine", "Recombine jadi quad", "bool", True),
            Field("mesh.require_all_quad", "Tolak bila ada elemen segitiga", "bool", True),
            Field(
                "mesh.element_order",
                "Orde elemen",
                "select",
                1,
                choices=tuple(sorted(config.SUPPORTED_ELEMENT_ORDERS)),
            ),
        ),
    ),
    Section(
        title="Analisis",
        icon=":material/functions:",
        fields=(
            Field(
                "analysis.shell_element",
                "Elemen shell",
                "select",
                "ShellMITC4",
                choices_fn=_shell_elements,
            ),
            Field(
                "analysis.section",
                "Section",
                "select",
                "PlateFiber",
                choices_fn=_sections,
            ),
            Field(
                "analysis.n_layers",
                "Jumlah lapis",
                "int",
                10,
                min_value=2,
                visible_when=_is_layered,
            ),
            Field(
                "analysis.include_self_weight",
                "Sertakan berat sendiri pilecap",
                "bool",
                False,
                help="Pastikan Pz pada CSV reaksi BELUM memuatnya (PRD Bagian 17 item 6 "
                "masih terbuka).",
            ),
        ),
    ),
    Section(
        title="Desain - umum",
        icon=":material/architecture:",
        fields=(
            Field("design.code", "Standar", "text", "SNI 2847:2019 (lewat shell-kit)"),
            Field("design.cover", "Selimut beton", "number", 75.0, unit="length"),
            Field("design.fy", "fy baja tulangan", "number", 420.0, unit="stress"),
            Field(
                "design.fy_source",
                "Asal nilai fy",
                "text",
                "",
                help="WAJIB. shell-kit menyediakan DEFAULT_FY = 420 tetapi tool ini tidak "
                "memakainya diam-diam: mutu baja menentukan seluruh luas tulangan.",
            ),
            Field(
                "design.phi_flexure",
                "phi lentur",
                "number",
                None,
                optional=True,
                min_value=0.0,
                max_value=1.0,
                help="Kosongkan untuk memakai nilai SNI bawaan shell-kit (0,90); asalnya "
                "tetap dicetak di calc sheet.",
            ),
            Field(
                "design.phi_shear",
                "phi geser",
                "number",
                None,
                optional=True,
                min_value=0.0,
                max_value=1.0,
                help="Kosongkan untuk memakai 0,75 dari shell-kit.",
            ),
            Field(
                "design.as_min_surface_zone",
                "Batas zona permukaan As_min",
                "number",
                None,
                unit="length",
                optional=True,
                help="Kosong = murni SNI 2847:2019. Diisi (mis. 300) = judgement mengikuti "
                "ACI 350-06 Ps. 7.12.2.1 untuk elemen tebal; nilainya dicatat di manifest "
                "sebagai keputusan Anda. Pada pilecap tebal ini mengubah hampir seluruh "
                "hasil lentur.",
            ),
        ),
    ),
    Section(
        title="Desain - pemilihan tulangan",
        icon=":material/linear_scale:",
        fields=(
            Field(
                "design.rebar_mode",
                "Mode",
                "select",
                "spacing_fixed",
                choices=validators.REBAR_MODES,
                help="spacing_fixed: Anda tetapkan spasi, tool memilih diameter. "
                "diameter_fixed: Anda tetapkan batang, tool menghitung spasi.",
            ),
            Field(
                "design.rebar_spacing",
                "Spasi tulangan",
                "number",
                150.0,
                unit="length",
                visible_when=_is_spacing_fixed,
            ),
            Field(
                "design.rebar_config",
                "Konfigurasi batang",
                "select",
                "2D25",
                choices_fn=_config_codes,
                visible_when=_is_diameter_fixed,
            ),
            Field(
                "design.rebar_select_codes",
                "Batasi pilihan ke kode ini",
                "multiselect",
                None,
                choices_fn=_config_codes,
                optional=True,
                help="Kosongkan untuk memakai seluruh diameter standar. Bila diisi, plot "
                "tulangan menjadi kategorikal berlabel kode.",
            ),
            Field("design.strips_x", "Jumlah lajur arah X", "int", 5, min_value=1),
            Field("design.strips_y", "Jumlah lajur arah Y", "int", 5, min_value=1),
            Field(
                "design.moment_at",
                "Lokasi momen desain",
                "select",
                "pier_face",
                choices=("pier_face", "peak", "both"),
                help="Nilai `peak` ditandai SINGULAR dan bukan momen desain.",
            ),
        ),
    ),
    Section(
        title="Desain - sengkang",
        icon=":material/grid_4x4:",
        help="Kedua spasi menentukan luas per kaki, sehingga keduanya wajib.",
        fields=(
            Field(
                "design.stirrup_spacing_long",
                "Spasi memanjang",
                "number",
                200.0,
                unit="length",
            ),
            Field(
                "design.stirrup_spacing_trans",
                "Spasi melintang",
                "number",
                200.0,
                unit="length",
            ),
            Field(
                "design.stirrup_select_diameters",
                "Batasi diameter sengkang",
                "multiselect",
                None,
                choices_fn=_stirrup_diameters,
                optional=True,
                help="Kosongkan untuk memakai daftar bawaan shell-kit.",
            ),
        ),
    ),
)

#: Seluruh field, datar. Dipakai `build_config` dan test.
ALL_FIELDS: tuple[Field, ...] = tuple(f for s in SECTIONS for f in s.fields)


def default_values() -> dict[str, Any]:
    """Nilai awal formulir, berkunci bertitik seperti `Field.key`."""
    return {f.key: f.default for f in ALL_FIELDS}


def visible_fields(values: dict[str, Any]) -> tuple[Field, ...]:
    """Field yang relevan terhadap pilihan saat ini (mis. cabang `rebar_mode`)."""
    return tuple(f for f in ALL_FIELDS if f.visible_when is None or f.visible_when(values))


def build_config(values: dict[str, Any]) -> dict[str, Any]:
    """Susun dict `pilecap_config.json` dari nilai formulir.

    Dua perlakuan berbeda, mengikuti konvensi contoh bawaan:

    * **Field yang tidak berlaku pada cabang aktif DIHILANGKAN**, bukan ditulis `null`.
      `examples/ex02` (pier lingkaran) memang tidak memuat `pier.width_x`/`width_y` sama
      sekali. Ini bukan soal selera: `fem_engine.AnalysisOptions.from_config` memakai
      ``int(analysis.get("n_layers", 10))``, dan `dict.get` mengembalikan `None` yang
      *ada* alih-alih bawaannya -- config ber-`"n_layers": null` membuatnya `int(None)`
      dan meledak. Kunci yang hilang aman; kunci bernilai null belum tentu.

    * **Field opsional yang sedang tampil tetapi dikosongkan ditulis `null`**, sama seperti
      `mesh.size_local_pile` dan `design.phi_flexure` di seluruh contoh. Di sana `null`
      adalah nilai yang bermakna: "pakai bawaan, dan itu keputusan sadar".
    """
    visible = {f.key for f in visible_fields(values)}
    out: dict[str, dict[str, Any]] = {}

    for f in ALL_FIELDS:
        if f.key not in visible:
            continue
        value = values.get(f.key, f.default)
        if isinstance(value, str):
            value = value.strip() or None
        if f.kind == "multiselect" and not value:
            value = None
        out.setdefault(f.block, {})[f.name] = value

    return out


def write_config(cfg: dict[str, Any], workdir: Path, *, now: datetime | None = None) -> Path:
    """Tulis config ke `<workdir>/ui_configs/pilecap_config_<timestamp>.json`.

    Selalu berkas BARU -- tidak pernah menimpa, sehingga setiap run punya config yang
    persis dipakainya dan dapat dijalankan ulang lewat CLI apa adanya.
    """
    import json

    stamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S")
    folder = workdir / CONFIG_SUBDIR
    folder.mkdir(parents=True, exist_ok=True)

    path = folder / f"{CONFIG_PREFIX}{stamp}.json"
    suffix = 1
    while path.exists():  # dua run dalam detik yang sama
        suffix += 1
        path = folder / f"{CONFIG_PREFIX}{stamp}_{suffix}.json"

    path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


__all__ = [
    "ALL_FIELDS",
    "CONFIG_PREFIX",
    "CONFIG_SUBDIR",
    "SECTIONS",
    "Field",
    "Section",
    "build_config",
    "default_values",
    "visible_fields",
    "write_config",
]
