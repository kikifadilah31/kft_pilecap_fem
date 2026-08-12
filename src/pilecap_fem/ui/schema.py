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
    #: Nama berkas SVG di `config.illustrations_dir()` yang menjelaskan bagian ini.
    #:
    #: Data, bukan cabang `if` di `app.py`: menempatkannya di sini berarti menambah
    #: ilustrasi untuk bagian baru tidak menyentuh kode formulir sama sekali. Berkas yang
    #: ditunjuk WAJIB ada -- dijaga `test_setiap_illustration_section_ada_berkasnya`,
    #: karena tautan yang putus baru terlihat saat formulir dibuka pengguna.
    illustration: str = ""
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


def _is_strip_basis(v: dict[str, Any]) -> bool:
    """Field lajur hanya relevan bila angka desain memang diambil dari lajur.

    Menyembunyikannya pada mode elemen bukan sekadar kerapian: `strips_x` yang terlihat
    dan dapat diisi padahal tidak dibaca sama sekali adalah tombol palsu -- user berhak
    mengira setelannya berpengaruh.
    """
    return bool(v.get("design.rebar_basis", config.REBAR_BASIS_DEFAULT) == "strip")


# ---------------------------------------------------------------------------
# Skema formulir
# ---------------------------------------------------------------------------

SECTIONS: tuple[Section, ...] = (
    Section(
        title="Proyek",
        icon=":material/description:",
        help="Identitas run. Tidak memengaruhi satu pun angka hasil, tetapi ikut tercetak di "
        "judul setiap gambar, di `calc_sheet.md`, dan di `run_manifest.json` -- itulah yang "
        "membuat berkas hasil dapat ditelusuri kembali ke pekerjaan dan orangnya.",
        fields=(
            Field(
                "project.name",
                "Nama proyek",
                "text",
                "",
                help="Muncul sebagai judul di setiap plot dan di kepala laporan. "
                'Contoh: "Jembatan A - Pilecap P3".',
            ),
            Field(
                "project.engineer",
                "Engineer",
                "text",
                "",
                help="Nama Anda atau tim perencana. Dicetak di laporan sebagai penanggung "
                "jawab perhitungan.",
            ),
            Field(
                "project.date",
                "Tanggal",
                "text",
                datetime.now().strftime("%Y-%m-%d"),
                help="Tanggal desain, bukan tanggal run (waktu run dicatat terpisah dan "
                "otomatis). Format bebas; YYYY-MM-DD memudahkan pengurutan folder.",
            ),
        ),
    ),
    Section(
        title="Satuan masukan",
        icon=":material/straighten:",
        help="Seluruh angka di formulir ini ditulis dalam satuan yang dipilih di sini, dan "
        "label tiap field langsung ikut berubah. Di dalam mesin hitung semuanya diubah ke SI "
        "(N, m, Pa); Anda tidak perlu mengonversi apa pun sendiri. Yang WAJIB Anda pastikan: "
        "pilihan di sini harus cocok dengan angka yang benar-benar Anda ketik -- salah pilih "
        "adalah satu-satunya kesalahan di formulir ini yang tidak dapat dideteksi tool, "
        "karena 1200 mm dan 1200 m sama-sama angka yang sah.",
        fields=(
            Field(
                "units.length",
                "Panjang",
                "select",
                "mm",
                choices=tuple(config.LENGTH_TO_SI),
                help="Satuan untuk semua ukuran: tebal, panjang, diameter, spasi, selimut. "
                "Berlaku juga untuk CSV geometri di folder input.",
            ),
            Field(
                "units.force",
                "Gaya",
                "select",
                "kN",
                choices=tuple(config.FORCE_TO_SI),
                help="Satuan untuk reaksi pile `Pz` di `pile_reactions.csv` dan untuk berat "
                "jenis beton (kN/m3).",
            ),
            Field(
                "units.stress",
                "Tegangan",
                "select",
                "MPa",
                choices=tuple(config.STRESS_TO_SI),
                help="Satuan untuk f'c, E, dan fy. 1 MPa = 1 N/mm2 -- itulah satuan yang "
                "dipakai SNI 2847:2019.",
            ),
        ),
    ),
    Section(
        title="Pilecap",
        icon=":material/crop_square:",
        illustration="sistem-koordinat.svg",
        override_entity="pilecap",
        help="Pelat beton yang menyatukan kepala tiang. Dimodelkan sebagai pelat datar di "
        "bidang XY dengan tebal seragam. Bila Anda menaruh CSV poligon di folder input, "
        "bentuknya diambil dari sana dan panjang X/Y di bawah diabaikan.",
        fields=(
            Field(
                "pilecap.thickness",
                "Tebal",
                "number",
                1200.0,
                unit="length",
                min_value=0.0,
                help="Tebal pelat, dipakai untuk kekakuan lentur, tinggi efektif tulangan, "
                "dan kapasitas geser. Ini besaran paling berpengaruh di seluruh model: "
                "kekakuan lentur pelat sebanding dengan tebal PANGKAT TIGA, sehingga tebal "
                "yang meleset 10% menggeser lendutan sekitar 30%.",
            ),
            Field(
                "pilecap.length_x",
                "Panjang arah X",
                "number",
                4800.0,
                unit="length",
                help="Ukuran pilecap arah memanjang (sumbu X). Dipakai hanya bila bentuknya "
                "persegi -- yaitu bila tidak ada CSV poligon pilecap di folder input.",
            ),
            Field(
                "pilecap.length_y",
                "Panjang arah Y",
                "number",
                4800.0,
                unit="length",
                help="Ukuran pilecap arah melintang (sumbu Y). Sama seperti panjang X: "
                "diabaikan bila bentuknya diambil dari CSV poligon.",
            ),
            Field(
                "pilecap.origin",
                "Titik asal [x, y]",
                "pair",
                [0.0, 0.0],
                unit="length",
                help="Koordinat TITIK PUSAT pilecap persegi, bukan sudutnya. Titik ini "
                "menentukan letak pilecap terhadap grid pile dan pier, jadi ketiganya harus "
                "memakai sistem koordinat yang sama. Biarkan [0, 0] bila Anda menempatkan "
                "semuanya relatif terhadap pusat pilecap.",
            ),
        ),
    ),
    Section(
        title="Pile",
        icon=":material/circle:",
        illustration="skema-tumpuan-beban.svg",
        override_entity="pile",
        help="Tiang pancang/bor yang memikul pilecap. Di model ini pile BUKAN tumpuan: "
        "reaksinya (`Pz` dari `pile_reactions.csv`) diterapkan sebagai BEBAN KE ATAS pada "
        "daerah lingkaran kepala tiang, sementara pier-lah yang dijepit. Karena reaksi pile "
        "sudah Anda ketahui dari analisis struktur atas, cara ini membuat keseimbangan gaya "
        "dapat diperiksa persis -- itulah cek VC-0 yang dijalankan setiap run.",
        fields=(
            Field(
                "pile.diameter",
                "Diameter",
                "number",
                800.0,
                unit="length",
                help="Diameter kepala tiang. Menentukan luas lingkaran tempat reaksi pile "
                "disebar; diameter yang lebih kecil memusatkan beban dan menaikkan momen "
                "lokal. Selalu dibutuhkan -- juga sebagai bawaan bila CSV koordinat pile "
                "tidak punya kolom diameter.",
            ),
            Field(
                "pile.n_col",
                "Jumlah kolom",
                "int",
                2,
                min_value=1,
                help="Banyaknya pile pada arah X untuk susunan grid teratur. Total pile = "
                "kolom x baris. Untuk susunan tidak teratur, pakai CSV koordinat pile di "
                "folder input dan abaikan field grid ini.",
            ),
            Field(
                "pile.n_row",
                "Jumlah baris",
                "int",
                2,
                min_value=1,
                help="Banyaknya pile pada arah Y untuk susunan grid teratur.",
            ),
            Field(
                "pile.spacing_x",
                "Spasi arah X",
                "number",
                2400.0,
                unit="length",
                help="Jarak antar sumbu pile pada arah X. Praktik umum menuntut jarak >= 3x "
                "diameter pile; tool memperingatkan bila pile saling tumpang tindih, tetapi "
                "kecukupan jarak terhadap standar tetap keputusan Anda.",
            ),
            Field(
                "pile.spacing_y",
                "Spasi arah Y",
                "number",
                2400.0,
                unit="length",
                help="Jarak antar sumbu pile pada arah Y. Boleh berbeda dari spasi X; "
                "susunan yang tidak seragam sama sekali dibuat lewat CSV koordinat pile.",
            ),
            Field(
                "pile.grid_origin",
                "Pusat grid [x, y]",
                "pair",
                [0.0, 0.0],
                unit="length",
                help="Titik pusat susunan pile. Grid dibangun simetris terhadap titik ini, "
                "sehingga [0, 0] menempatkannya tepat di tengah bila pilecap juga berpusat "
                "di [0, 0].",
            ),
            Field(
                "pile.modeling",
                "Pemodelan beban",
                "select",
                "pressure",
                choices=("pressure", "nodal"),
                help="Cara reaksi pile masuk ke model. `pressure` (disarankan) menyebarkan "
                "Pz merata pada seluruh lingkaran kepala tiang -- mendekati kenyataan dan "
                "menghasilkan momen yang halus. `nodal` menempatkannya sebagai gaya titik "
                "di node-node yang sama; totalnya identik, tetapi momen tepat di kepala "
                "tiang menjadi lebih runcing. Keduanya lulus cek keseimbangan.",
            ),
        ),
    ),
    Section(
        title="Pier",
        icon=":material/view_column:",
        illustration="tumpang-tindih-pile-pier.svg",
        override_entity="pier",
        help="Kolom/pilar yang berdiri di atas pilecap. Di model ini pier menjadi TUMPUAN: "
        "seluruh node di dalam daerah pier dijepit penuh (6 derajat kebebasan), menahan "
        "beban yang didorong pile dari bawah. Momen desain dibaca di MUKA pier, sesuai "
        "praktik SNI, karena momen tepat di sumbu tumpuan bersifat singular pada model pelat.",
        fields=(
            Field(
                "pier.shape",
                "Bentuk",
                "select",
                "rectangular",
                choices=("rectangular", "circular"),
                help="Penampang pier di bidang pilecap. `rectangular` meminta lebar X dan Y; "
                "`circular` meminta satu diameter. Pilihan ini mengubah field yang tampil di "
                "bawah dan menentukan letak muka pier tempat momen desain dibaca.",
            ),
            Field(
                "pier.width_x",
                "Lebar arah X",
                "number",
                1200.0,
                unit="length",
                visible_when=_is_rectangular,
                help="Ukuran pier searah sumbu X. Semakin lebar, semakin luas daerah jepit "
                "dan semakin kecil momen di mukanya -- jadi angka ini harus ukuran pier yang "
                "sebenarnya, bukan perkiraan yang dibulatkan ke atas.",
            ),
            Field(
                "pier.width_y",
                "Lebar arah Y",
                "number",
                1200.0,
                unit="length",
                visible_when=_is_rectangular,
                help="Ukuran pier searah sumbu Y. Bersama lebar X menentukan daerah yang "
                "dijepit dan letak muka pier tempat momen desain arah Y dibaca.",
            ),
            Field(
                "pier.diameter",
                "Diameter",
                "number",
                1800.0,
                unit="length",
                visible_when=_is_circular,
                help="Diameter pier bulat. Daerah jepitnya berupa lingkaran dengan diameter ini.",
            ),
            Field(
                "pier.centerline",
                "Titik pusat [x, y]",
                "pair",
                [0.0, 0.0],
                unit="length",
                help="Koordinat sumbu pier, dalam sistem koordinat yang sama dengan pilecap "
                "dan pile. Untuk lebih dari satu pier, pakai CSV poligon pier di folder "
                "input -- formulir ini hanya menampung satu pier.",
            ),
            Field(
                "pier.support",
                "Tumpuan",
                "select",
                "fixed",
                choices=("fixed",),
                help="Jenis tumpuan di daerah pier. Hanya jepit penuh 6 DOF yang tersedia di "
                "v1.0; tumpuan pegas (pile sebagai pegas, pier sebagai beban) belum "
                "diimplementasikan dan sengaja tidak ditawarkan agar tidak ada pilihan yang "
                "tampak ada tetapi tidak berfungsi.",
            ),
            Field(
                "pier.max_pile_overlap_fraction",
                "Batas tumpang tindih pile-pier",
                "number",
                None,
                optional=True,
                min_value=0.0,
                max_value=1.0,
                help="Kosongkan (bawaan) bila pile TIDAK boleh menindih pier — run akan "
                "ditolak bila ternyata menindih. Diisi = Anda mengizinkannya sampai fraksi "
                "ini (mis. 0,15 = paling banyak 15% luas pile berada di dalam pier). "
                "KONSEKUENSI: bagian yang berada di dalam pier TIDAK melenturkan pelat — "
                "pier dimodelkan jepit sempurna, jadi gaya di sana tersalur langsung ke "
                "pier (aksi strut) dan kapasitasnya HARUS Anda cek terpisah; tool tidak "
                "menghitungnya. Untuk geometri seperti ini angka desain juga menjadi "
                "sensitif terhadap kehalusan mesh. Besarnya dilaporkan terpisah di calc "
                "sheet (komponen strut vs komponen diskretisasi).",
            ),
        ),
    ),
    Section(
        title="Material",
        icon=":material/layers:",
        help="Properti beton pilecap. Pelat dimodelkan elastis linier: satu nilai E dan satu "
        "Poisson untuk seluruh pelat. Retak, rangkak, dan susut TIDAK dimodelkan -- bila Anda "
        "ingin memperhitungkan penurunan kekakuan akibat retak, turunkan sendiri nilai E yang "
        "Anda isi dan tuliskan alasannya di kolom asal nilai E.",
        fields=(
            Field(
                "material.fc",
                "f'c",
                "number",
                30.0,
                unit="stress",
                min_value=0.0,
                help="Kuat tekan beton yang disyaratkan pada umur 28 hari (silinder). "
                "Dipakai untuk kapasitas lentur dan geser menurut SNI 2847:2019, dan untuk "
                "menamai material pada berkas ekspor Midas. TIDAK dipakai menghitung E -- "
                "E Anda isi sendiri di bawah.",
            ),
            Field(
                "material.E",
                "Modulus elastisitas E",
                "number",
                25000.0,
                unit="stress",
                min_value=0.0,
                help="Modulus elastisitas beton -- ukuran kekakuannya. Menentukan besar "
                "lendutan, tetapi hampir tidak memengaruhi momen desain pada model ini "
                "karena tumpuannya statis tertentu terhadap beban yang sudah diketahui. "
                "Tool TIDAK menghitung E dari f'c: rumusnya belum dikonfirmasi pasalnya, "
                "dan angka tanpa sumber dilarang. Nilai lazim beton normal fc30: sekitar "
                "25.000-27.000 MPa.",
            ),
            Field(
                "material.E_source",
                "Asal nilai E",
                "text",
                "",
                help="WAJIB DIISI -- run akan ditolak bila kosong. Tuliskan dari mana angka E "
                "di atas berasal, karena inilah satu-satunya jejak yang membuat nilai itu "
                "dapat diperiksa orang lain. Dicetak apa adanya di calc_sheet.md dan "
                'run_manifest.json. Mis. "SNI 2847:2019 Ps. 19.2.2.1 untuk wc=2400" atau '
                '"hasil uji lab 2026-01-15" atau "0,5 Ec untuk memperhitungkan retak".',
            ),
            Field(
                "material.poisson",
                "Rasio Poisson",
                "number",
                0.2,
                min_value=config.POISSON_MIN,
                max_value=config.POISSON_MAX - 1e-9,
                help="Perbandingan regangan melintang terhadap regangan searah beban. Untuk "
                "beton lazimnya 0,15-0,20. Pada pelat, angka ini ikut menentukan seberapa "
                "besar momen di satu arah membangkitkan momen di arah tegak lurusnya; "
                "pengaruhnya nyata tetapi jauh lebih kecil daripada tebal pelat.",
            ),
            Field(
                "material.density",
                "Berat jenis",
                "number",
                24.0,
                unit="kN/m^3",
                optional=True,
                min_value=0.0,
                help="Berat beton per satuan volume, lazimnya 24 kN/m3. HANYA dipakai bila "
                'Anda mencentang "Sertakan berat sendiri pilecap" di bagian Analisis; bila '
                "tidak, angka ini tidak memengaruhi hasil sama sekali. Boleh dikosongkan.",
            ),
        ),
    ),
    Section(
        title="Mesh",
        icon=":material/grid_on:",
        help="Pelat dipotong menjadi ribuan elemen kecil segi empat; di setiap elemen momen "
        "dan geser dihitung. Semakin kecil elemennya semakin teliti hasilnya, tetapi semakin "
        "lama analisisnya -- dan hubungannya tidak linier: memperkecil ukuran jadi setengah "
        "membuat jumlah elemen menjadi empat kali. Bawaan di sini sudah menghasilkan mesh "
        "yang halus untuk pilecap berukuran lazim. Kontrak numerik tool ini menuntut seluruh "
        "elemen berupa SEGI EMPAT; bila gmsh terpaksa menyisipkan segitiga, run dihentikan "
        "alih-alih diam-diam memakai elemen bermutu lebih rendah.",
        fields=(
            Field(
                "mesh.size_mode",
                "Mode ukuran",
                "select",
                "uniform",
                choices=("uniform", "graded"),
                help="`uniform` memakai satu ukuran elemen di seluruh pelat -- paling mudah "
                "diprediksi dan paling sering tepat. `graded` memperhalus mesh hanya di "
                "sekitar pile dan/atau pier, tempat tegangan berubah paling cepat, sehingga "
                "hasil sama telitinya dengan jumlah elemen lebih sedikit.",
            ),
            Field(
                "mesh.size_global",
                "Ukuran global",
                "number",
                130.0,
                unit="length",
                help="Panjang sisi elemen di seluruh pelat. Patokan praktis: ambil sekitar "
                "1/6 diameter pile atau lebih kecil, supaya lingkaran kepala tiang terwakili "
                "oleh cukup banyak elemen. Terlalu besar membuat beban pile tampak kotak dan "
                "momen puncaknya meleset; terlalu kecil hanya memperpanjang waktu hitung.",
            ),
            Field(
                "mesh.size_local_pile",
                "Ukuran lokal di pile",
                "number",
                None,
                unit="length",
                optional=True,
                visible_when=_is_graded,
                help="Ukuran elemen di daerah kepala tiang pada mode graded. Wajib diisi "
                "salah satu (pile atau pier), dan harus <= ukuran global -- mengisinya lebih "
                "besar berarti memperkasar mesh justru di tempat yang paling butuh halus.",
            ),
            Field(
                "mesh.size_local_pier",
                "Ukuran lokal di pier",
                "number",
                None,
                unit="length",
                optional=True,
                visible_when=_is_graded,
                help="Ukuran elemen di daerah pier pada mode graded. Di sinilah momen desain "
                "dibaca, sehingga memperhalusnya langsung memperbaiki ketelitian angka yang "
                "Anda pakai.",
            ),
            Field(
                "mesh.algorithm",
                "Mesh.Algorithm",
                "select",
                config.GMSH_ALGORITHM_DEFAULT,
                choices=tuple(sorted(config.GMSH_VALID_ALGORITHMS)),
                help="Algoritma pembentuk mesh di gmsh. 11 = Quasi-structured Quad, yang "
                "menghasilkan segi empat rapi dan menjadi bagian kontrak numerik tool ini. "
                "Ubah hanya bila mesh gagal terbentuk dan Anda paham konsekuensinya; nilai "
                "yang dipakai selalu tercatat di run_manifest.json.",
            ),
            Field(
                "mesh.recombination_algorithm",
                "Mesh.RecombinationAlgorithm",
                "select",
                config.GMSH_RECOMB_ALGORITHM_DEFAULT,
                choices=tuple(sorted(config.GMSH_VALID_RECOMB_ALGORITHMS)),
                help="Cara gmsh menggabungkan segitiga menjadi segi empat. 3 = Blossom "
                "full-quad, yang memaksa hasil 100% segi empat. Bersama Mesh.Algorithm di "
                "atas, inilah yang membuat syarat all-quad dapat dipenuhi.",
            ),
            Field(
                "mesh.recombine",
                "Recombine jadi quad",
                "bool",
                True,
                help="Menyalakan penggabungan segitiga menjadi segi empat. Harus tetap "
                "menyala: elemen shell yang dipakai tool ini (ShellMITC4) hanya menerima "
                "segi empat 4 titik.",
            ),
            Field(
                "mesh.require_all_quad",
                "Tolak bila ada elemen segitiga",
                "bool",
                True,
                help="Menghentikan run bila gmsh tetap menyisakan segitiga. Biarkan menyala. "
                "Mematikannya membuat run berlanjut dengan mesh yang tidak sepenuhnya dapat "
                "dianalisis -- kesalahan yang tidak terlihat di gambar mana pun.",
            ),
            Field(
                "mesh.element_order",
                "Orde elemen",
                "select",
                1,
                choices=tuple(sorted(config.SUPPORTED_ELEMENT_ORDERS)),
                help="Orde 1 = elemen bersimpul di keempat sudut saja (linier). Hanya orde 1 "
                "yang didukung, karena ShellMITC4 memang elemen 4 titik.",
            ),
        ),
    ),
    Section(
        title="Analisis",
        icon=":material/functions:",
        help="Pilihan pemodelan numerik. Bawaannya sudah tepat untuk pilecap pada umumnya; "
        "ubah hanya bila Anda punya alasan spesifik. Apa pun pilihannya, setiap run "
        "menjalankan cek keseimbangan VC-0: jumlah beban yang terpasang dibandingkan dengan "
        "jumlah reaksi tumpuan, dan run digagalkan bila keduanya tidak cocok.",
        fields=(
            Field(
                "analysis.shell_element",
                "Elemen shell",
                "select",
                "ShellMITC4",
                choices_fn=_shell_elements,
                help="Rumusan matematis tiap elemen pelat. `ShellMITC4` adalah elemen 4 "
                "titik berformulasi MITC yang memperhitungkan DEFORMASI GESER MELINTANG "
                "(teori pelat tebal Mindlin-Reissner). Dipilih sebagai bawaan karena pilecap "
                "umumnya tebal terhadap bentangnya; teori pelat tipis (Kirchhoff) mengabaikan "
                "geser melintang dan akan MEREMEHKAN lendutan pada pelat setebal ini. "
                "`ShellDKGQ` adalah elemen pelat tipis tersebut, dan `ShellNLDKGQ` versinya "
                "dengan nonlinieritas geometri -- keduanya tidak diperlukan pada analisis "
                "elastis linier di sini.",
            ),
            Field(
                "analysis.section",
                "Section",
                "select",
                "PlateFiber",
                choices_fn=_sections,
                help="Cara penampang setebal pelat diwakili. `PlateFiber` memakai satu "
                "material elastis yang terintegrasi pada tebal penuh -- itu yang sesuai untuk "
                "analisis elastis linier di sini. `LayeredShell` membagi tebal menjadi "
                "beberapa lapis dan baru bermanfaat bila tiap lapis diberi material berbeda; "
                "pada model elastis satu material, hasilnya sama tetapi lebih lambat.",
            ),
            Field(
                "analysis.n_layers",
                "Jumlah lapis",
                "int",
                10,
                min_value=2,
                visible_when=_is_layered,
                help="Banyaknya lapis penampang pada `LayeredShell`. Lebih banyak lapis "
                "berarti integrasi tegangan pada tebal lebih halus, dengan biaya waktu "
                "hitung. Minimal 2.",
            ),
            Field(
                "analysis.include_self_weight",
                "Sertakan berat sendiri pilecap",
                "bool",
                False,
                help="Menambahkan berat pilecap sendiri (tebal x berat jenis) sebagai beban "
                "merata ke bawah. HATI-HATI dengan hitungan ganda: pada banyak alur kerja, "
                "reaksi pile yang keluar dari analisis struktur atas SUDAH memuat berat "
                "pilecap. Centang hanya bila Anda yakin Pz pada CSV reaksi belum memuatnya, "
                "dan ingat bahwa mencentangnya membuat jumlah beban tidak lagi sama dengan "
                "jumlah Pz (PRD Bagian 17 item 6 masih terbuka).",
            ),
        ),
    ),
    Section(
        title="Desain - umum",
        icon=":material/architecture:",
        help="Dari momen dan geser hasil analisis, tool menghitung kebutuhan tulangan "
        "menurut SNI 2847:2019 lewat pustaka shell-kit. Bagian ini menetapkan mutu bahan dan "
        "faktor reduksi yang dipakai perhitungan tersebut.",
        fields=(
            Field(
                "design.code",
                "Standar",
                "text",
                "SNI 2847:2019 (lewat shell-kit)",
                help="Label standar yang dicetak di laporan. Ini CATATAN, bukan sakelar: "
                "mengubah teksnya tidak mengubah rumus mana pun -- perhitungannya selalu "
                "mengikuti SNI 2847:2019 sebagaimana diterapkan shell-kit.",
            ),
            Field(
                "design.cover",
                "Selimut beton",
                "number",
                75.0,
                unit="length",
                help="Tebal beton dari permukaan sampai sisi luar tulangan. Menentukan tinggi "
                "efektif d, yang langsung menentukan kebutuhan tulangan: selimut yang lebih "
                "tebal berarti d lebih kecil dan tulangan lebih banyak. SNI menuntut 75 mm "
                "untuk beton yang dicor langsung di atas tanah -- kondisi lazim pilecap.",
            ),
            Field(
                "design.fy",
                "fy baja tulangan",
                "number",
                420.0,
                unit="stress",
                help="Tegangan leleh baja tulangan. BjTS 420 (setara ulir mutu 420 MPa) "
                "adalah yang paling umum. Berbanding terbalik dengan luas tulangan yang "
                "dibutuhkan, jadi salah mengisinya langsung menggeser seluruh hasil.",
            ),
            Field(
                "design.fy_source",
                "Asal nilai fy",
                "text",
                "",
                help="WAJIB DIISI -- run ditolak bila kosong. shell-kit menyediakan "
                "DEFAULT_FY = 420 tetapi tool ini tidak memakainya diam-diam: mutu baja "
                'menentukan seluruh luas tulangan. Mis. "BjTS 420B, SNI 2052:2017" atau '
                '"sertifikat mill pabrik X".',
            ),
            Field(
                "design.phi_flexure",
                "phi lentur",
                "number",
                None,
                optional=True,
                min_value=0.0,
                max_value=1.0,
                help="Faktor reduksi kekuatan untuk lentur: kapasitas rencana = phi x "
                "kapasitas nominal, cara standar memberi margin keamanan. Kosongkan untuk "
                "memakai nilai SNI bawaan shell-kit (0,90 untuk penampang terkendali tarik); "
                "asalnya tetap dicetak di calc sheet. Isi hanya bila standar Anda menuntut "
                "angka lain.",
            ),
            Field(
                "design.phi_shear",
                "phi geser",
                "number",
                None,
                optional=True,
                min_value=0.0,
                max_value=1.0,
                help="Faktor reduksi kekuatan untuk geser. Kosongkan untuk memakai 0,75 dari "
                "shell-kit sesuai SNI. Lebih kecil daripada phi lentur karena keruntuhan "
                "geser bersifat getas dan lebih sulit diprediksi.",
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
        illustration="mode-desain-tulangan.svg",
        help="Dari luas tulangan yang dibutuhkan (As), tool memilih batang yang benar-benar "
        "dapat dipasang. Anda menetapkan SATU dari dua hal -- spasi atau batangnya -- dan "
        "tool menghitung sisanya. Hasilnya digambar sebagai peta diameter dan peta spasi per "
        "elemen, bukan hanya angka As.",
        fields=(
            Field(
                "design.rebar_basis",
                "Metode hitung angka desain",
                "select",
                config.REBAR_BASIS_DEFAULT,
                choices=config.REBAR_BASES,
                help="Dari mana angka desain diambil. Berlaku untuk SELURUH kombinasi "
                "sekaligus, termasuk envelope. "
                "`element` (bawaan) memakai nilai tiap elemen apa adanya -- algoritma asli "
                "shell-kit. Kontur menjadi deliverable utamanya, dan Anda yang menentukan "
                "pembagian zona penulangan saat mendetail. Nilai puncaknya di tepi pier "
                "bersifat SINGULAR: membesar terus setiap mesh diperhalus (terukur ~16% "
                "saat mesh 300 -> 150 mm), jadi hasilnya bergantung ukuran mesh yang Anda "
                "pilih. Arahnya konservatif -- tulangan bertambah, bukan berkurang. "
                "`strip` mengintegrasi momen sepanjang potongan di muka pier: konvergen "
                "dan dapat dicek tangan, tetapi hasilnya bergantung jumlah lajur yang Anda "
                "tetapkan. Terukur pada ex01: memakai 1 lajur alih-alih 5 mengencerkan "
                "puncak 556 -> 283 kNm/m.",
            ),
            Field(
                "design.rebar_mode",
                "Mode",
                "select",
                "spacing_fixed",
                choices=validators.REBAR_MODES,
                help="spacing_fixed: Anda tetapkan spasi, tool memilih diameter. "
                "diameter_fixed: Anda tetapkan batang, tool menghitung spasi. "
                "Sumbu yang BERBEDA dari metode hitung di atas: yang ini menentukan batang "
                "yang dipasang, bukan dari mana angka As berasal.",
            ),
            Field(
                "design.rebar_spacing",
                "Spasi tulangan",
                "number",
                150.0,
                unit="length",
                visible_when=_is_spacing_fixed,
                help="Jarak antar batang yang Anda tetapkan; tool memilih diameter terkecil "
                "dari daftar standar yang masih memenuhi As pada spasi ini. Spasi lebih rapat "
                "berarti diameter lebih kecil dan retak lebih terkendali, tetapi pemasangan "
                "lebih padat. 150-200 mm lazim untuk pilecap.",
            ),
            Field(
                "design.rebar_config",
                "Konfigurasi batang",
                "select",
                "2D25",
                choices_fn=_config_codes,
                visible_when=_is_diameter_fixed,
                help="Susunan batang yang Anda tetapkan; tool menghitung spasi yang "
                "dibutuhkan untuk memenuhi As. Kode dibaca sebagai <jumlah>D<diameter>: "
                '"2D25" berarti dua batang D25 per titik pemasangan (mis. dipasang '
                "berpasangan), "
                '"1D22" berarti satu batang D22. Daftarnya datang langsung dari shell-kit.',
            ),
            Field(
                "design.rebar_select_codes",
                "Batasi pilihan ke kode ini",
                "multiselect",
                None,
                choices_fn=_config_codes,
                optional=True,
                help="Membatasi pilihan tool pada kode-kode tertentu saja, mis. bila di "
                "lapangan hanya tersedia D22 dan D25. Kosongkan untuk memakai seluruh "
                "diameter standar. Bila diisi, plot tulangan menjadi kategorikal berlabel "
                "kode -- setiap warna satu kode, bukan gradasi.",
            ),
            Field(
                "design.strips_x",
                "Jumlah lajur arah X",
                "int",
                5,
                min_value=1,
                visible_when=_is_strip_basis,
                help="Pilecap dibagi menjadi beberapa lajur (strip) sejajar sumbu X; di tiap "
                "lajur momen dirata-ratakan menjadi satu momen desain, sesuai cara "
                "penulangan pelat dikerjakan di lapangan. Lebih banyak lajur berarti "
                "penulangan lebih mengikuti sebaran momen tetapi gambar kerjanya lebih rumit. "
                "5 lajur lazim.",
            ),
            Field(
                "design.strips_y",
                "Jumlah lajur arah Y",
                "int",
                5,
                min_value=1,
                visible_when=_is_strip_basis,
                help="Banyaknya lajur sejajar sumbu Y, dengan cara kerja yang sama seperti "
                "lajur arah X. Tulangan kedua arah dihitung terpisah, jadi jumlah lajurnya "
                "boleh berbeda.",
            ),
            Field(
                "design.moment_at",
                "Lokasi momen desain",
                "select",
                "pier_face",
                choices=("pier_face", "peak", "both"),
                visible_when=_is_strip_basis,
                help="Di titik mana momen desain dibaca. `pier_face` = di muka pier, sesuai "
                "praktik SNI dan pilihan yang benar untuk desain. `peak` = nilai terbesar di "
                "mana pun, yang pada model pelat muncul tepat di tumpuan dan bersifat "
                "SINGULAR: angkanya membesar terus setiap kali mesh diperhalus, sehingga "
                "bukan momen desain -- tool menandainya demikian di laporan. `both` mencetak "
                "keduanya untuk perbandingan.",
            ),
        ),
    ),
    Section(
        title="Desain - sengkang",
        icon=":material/grid_4x4:",
        help="Sengkang adalah tulangan VERTIKAL yang menembus tebal pilecap untuk menahan "
        "geser, dipasang sebagai kisi dengan dua spasi: memanjang dan melintang. Tool "
        "menghitung kebutuhan Av/s dari geser hasil analisis, lalu menerjemahkannya menjadi "
        "diameter sengkang pada kisi yang Anda tetapkan. Kedua spasi bersama-sama menentukan "
        "luas yang harus dipikul satu kaki sengkang, sehingga keduanya wajib diisi. Pada "
        "banyak pilecap tebal, geser terpenuhi oleh beton saja dan tool akan melaporkan "
        '"tanpa sengkang" di sebagian besar luasan -- itu hasil yang sah.',
        fields=(
            Field(
                "design.stirrup_spacing_long",
                "Spasi memanjang",
                "number",
                200.0,
                unit="length",
                help="Jarak antar sengkang searah sumbu X. Bersama spasi melintang menentukan "
                "luas tributari satu kaki sengkang; kisi lebih rapat berarti diameter "
                "sengkang lebih kecil untuk geser yang sama.",
            ),
            Field(
                "design.stirrup_spacing_trans",
                "Spasi melintang",
                "number",
                200.0,
                unit="length",
                help="Jarak antar sengkang searah sumbu Y. Luas tributari satu kaki "
                "sengkang adalah hasil kali kedua spasi, sehingga keduanya sama-sama "
                "menentukan diameter yang dibutuhkan.",
            ),
            Field(
                "design.stirrup_select_diameters",
                "Batasi diameter sengkang",
                "multiselect",
                None,
                choices_fn=_stirrup_diameters,
                optional=True,
                help="Membatasi pilihan pada diameter tertentu saja, mis. bila di lapangan "
                "hanya tersedia D13 dan D16. Kosongkan untuk memakai daftar bawaan shell-kit "
                "(D10 sampai D25). Daerah yang butuh lebih besar daripada diameter terbesar "
                "yang diizinkan ditandai TIDAK MEMADAI di plot, bukan dibulatkan diam-diam.",
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


def values_from_config(raw: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Kebalikan `build_config`: isi nilai formulir dari `pilecap_config.json` yang ada.

    Mengembalikan `(nilai, kunci_tak_dikenal)`. Kunci yang tidak ada di skema
    **dilaporkan**, tidak dibuang diam-diam: config tulisan tangan boleh memuat field yang
    belum diwakili formulir, dan pengguna yang menyimpan hasil formulir menimpa berkas itu
    akan kehilangan field tersebut tanpa tanda apa pun.

    Dipakai `if f.name in block`, **bukan** `block.get(...)`. Keduanya berbeda arti dan
    perbedaan itu penting (lihat `build_config`): kunci yang HILANG berarti "pakai bawaan
    skema", sedangkan kunci bernilai `null` yang tertulis adalah keputusan sadar user dan
    harus dipertahankan.

    Satuan tidak dikonversi. `raw` dan formulir sama-sama dalam satuan tampilan; blok
    `units` ikut termuat sehingga label formulir langsung menyesuaikan.

    Satu normalisasi: field teks bernilai `null` dipulangkan sebagai `""`. `build_config`
    menulis teks kosong sebagai `null`, dan keduanya berarti sama -- belum diisi -- tetapi
    hanya `""` yang dapat dimuat `st.text_input`.
    """
    values = default_values()
    known: dict[str, set[str]] = {}
    for f in ALL_FIELDS:
        known.setdefault(f.block, set()).add(f.name)
        block = raw.get(f.block)
        if isinstance(block, dict) and f.name in block:
            value = block[f.name]
            values[f.key] = "" if f.kind == "text" and value is None else value

    unknown: list[str] = []
    for block_name, block in raw.items():
        if not isinstance(block, dict):
            unknown.append(block_name)
            continue
        unknown.extend(f"{block_name}.{k}" for k in block if k not in known.get(block_name, ()))
    return values, tuple(sorted(unknown))


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
    "values_from_config",
    "visible_fields",
    "write_config",
]
