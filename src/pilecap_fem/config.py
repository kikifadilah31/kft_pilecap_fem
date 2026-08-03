"""Single Source of Truth (PRD Core 6).

Modul ini HANYA berisi konstanta, tabel, dan setup logging. Tidak ada logika rekayasa
dan tidak ada perhitungan. Setiap angka yang mempengaruhi hasil analisis WAJIB punya
rujukan pasal PRD atau standar; angka yang belum dikonfirmasi user ditandai eksplisit
dan modul yang membutuhkannya harus RAISE (PRD Bagian 1.3 poin 2).
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Final

# ---------------------------------------------------------------------------
# Sistem satuan (PRD Bagian 4)
# ---------------------------------------------------------------------------

#: Deskripsi sistem satuan internal, dicatat apa adanya di run_manifest.json.
SI_UNIT_SYSTEM: Final[str] = "SI (N, m, Pa)"

#: Satuan file input default bila blok `units` tidak ada di config JSON.
#: Dikonfirmasi user (PRD Bagian 17 item 12 & 14): workflow Excel memakai mm / kN / MPa.
DEFAULT_INPUT_UNITS: Final[dict[str, str]] = {
    "length": "mm",
    "force": "kN",
    "stress": "MPa",
}

#: Faktor konversi satuan input -> SI. INI SATU-SATUNYA TABEL KONVERSI DI SELURUH TOOL
#: (PRD Bagian 4.2). Dipakai eksklusif oleh io_utils.py.
LENGTH_TO_SI: Final[dict[str, float]] = {"mm": 1e-3, "cm": 1e-2, "m": 1.0}
FORCE_TO_SI: Final[dict[str, float]] = {"N": 1.0, "kN": 1e3, "MN": 1e6}
STRESS_TO_SI: Final[dict[str, float]] = {"Pa": 1.0, "kPa": 1e3, "MPa": 1e6, "GPa": 1e9}

#: Satuan tampilan (SI -> display) beserta faktornya (PRD Bagian 4.3).
#: Dipakai eksklusif oleh io_utils.to_display(), yang hanya boleh dipanggil dari
#: renderer.py dan reporter.py.
DISPLAY_UNITS: Final[dict[str, tuple[str, float]]] = {
    "length": ("mm", 1e3),
    "length_m": ("m", 1.0),
    "area": ("m^2", 1.0),
    "moment_per_width": ("kNm/m", 1e-3),
    "moment": ("kNm", 1e-3),
    "shear_per_width": ("kN/m", 1e-3),
    "force": ("kN", 1e-3),
    "deflection": ("mm", 1e3),
    "stress": ("MPa", 1e-6),
    "pressure": ("kPa", 1e-3),
    "force_density": ("kN/m^3", 1e-3),
}

# ---------------------------------------------------------------------------
# Auto-detection file input (PRD Bagian 5.2, Core 10)
# ---------------------------------------------------------------------------

#: Kunci -> pola glob. >1 file cocok => RAISE (jangan pernah ambil yang pertama).
FILE_PATTERNS: Final[dict[str, str]] = {
    "config": "*config*.json",
    "reactions": "*react*.csv",
    "pile_coords": "*pile*coord*.csv",
    "pilecap_polygon": "*cap*polygon*.csv",
    "pier_polygon": "*pier*polygon*.csv",
}

#: File yang wajib ada untuk command yang membutuhkannya.
REQUIRED_FILES: Final[frozenset[str]] = frozenset({"config", "reactions"})

#: Entitas geometri yang sumbernya diresolusi per-entitas (PRD Bagian 5.2.1).
GEOMETRY_ENTITIES: Final[tuple[str, str, str]] = ("pilecap", "pile", "pier")

#: Field JSON yang DIABAIKAN bila CSV terkait ada (PRD Bagian 5.2.1, tabel override).
#: `pier.centerline` masuk daftar pier karena keputusan multi-pier: untuk pier dari CSV,
#: centerline tiap pier diturunkan dari centroid polygon-nya (satu nilai JSON tidak dapat
#: melayani N pier).
OVERRIDDEN_JSON_KEYS: Final[dict[str, tuple[str, ...]]] = {
    "pilecap": ("pilecap.length_x", "pilecap.length_y", "pilecap.origin"),
    "pile": (
        "pile.n_col",
        "pile.n_row",
        "pile.spacing_x",
        "pile.spacing_y",
        "pile.grid_origin",
    ),
    "pier": ("pier.shape", "pier.width_x", "pier.width_y", "pier.diameter", "pier.centerline"),
}

# ---------------------------------------------------------------------------
# Ambang validasi geometri & mesh (PRD Bagian 5.3)
# ---------------------------------------------------------------------------

#: Minimum jumlah elemen sepanjang diameter pile sebelum validator RAISE.
#: DIKONFIRMASI USER (PRD Bagian 17 item 13): nilai 6, sesuai rekomendasi awal PRD Bagian 5.1(f).
MIN_ELEM_PER_PILE_DIAMETER: Final[float] = 6.0

#: Rule 7: size_global tidak boleh melebihi fraksi ini dari dimensi terkecil pilecap.
MESH_SIZE_MAX_FRACTION: Final[float] = 0.25

#: Ambang keseragaman luas elemen pada mode `uniform`, dipakai sebagai KRITERIA TEST
#: (PRD Bagian 15.1), bukan angka desain. DIKONFIRMASI USER (PRD Bagian 17 item 15).
#:
#: PENTING -- ambang ini berlaku untuk `MeshModel.area_uniformity_cv_cap` (group CAP saja),
#: BUKAN untuk seluruh elemen. Pengukuran pada ketiga contoh menunjukkan:
#:
#:     contoh   std/mean (semua)   std/mean (CAP saja)
#:     ex01           0.346               0.131
#:     ex03           0.417               0.171
#:     ex02           0.403               0.200
#:
#: Nilai "semua elemen" didominasi cincin transisi di sekeliling disk pile dan tepi pier:
#: batas lengkung memaksa elemen lebih kecil berapa pun ukuran target, sehingga metrik itu
#: mengukur kelengkungan geometri, bukan keseragaman mesh. Group CAP mencerminkan yang
#: dimaksud PRD. Rekomendasi awal PRD (0.35) dipertahankan, hanya definisinya dipertajam.
MESH_UNIFORMITY_MAX_CV: Final[float] = 0.35

#: Di atas jumlah ini, keluarkan WARNING durasi analisis (PRD Bagian 5.3).
MESH_ELEMENT_WARN_LIMIT: Final[int] = 50_000

#: Toleransi relatif cek luas: Sigma luas sub-face hasil fragment == luas pilecap.
AREA_RTOL: Final[float] = 1e-9

#: Toleransi perbandingan golden file hasil FEM (PRD Bagian 8.2).
VALIDATION_RTOL: Final[float] = 1e-3

#: Toleransi default cek keseimbangan VC-0 (PRD Bagian 6.2, --equilibrium-rtol).
EQUILIBRIUM_RTOL_DEFAULT: Final[float] = 1e-3

#: Rentang Poisson yang sah untuk material isotropik (PRD Bagian 5.3 rule 6).
POISSON_MIN: Final[float] = 0.0
POISSON_MAX: Final[float] = 0.5

# ---------------------------------------------------------------------------
# Opsi gmsh (PRD Bagian 5.1(f), R6)
# ---------------------------------------------------------------------------
# Penomoran di bawah DIVERIFIKASI terhadap gmsh 4.15.2 (versi yang di-pin di
# pyproject.toml). mesh_engine.py WAJIB membaca balik opsi dengan getNumber() dan
# membandingkannya dengan config -- ini menangkap perubahan penomoran antar versi gmsh.

GMSH_VERSION_PINNED: Final[str] = "4.15.2"

#: Mesh.Algorithm = 11 -> Quasi-structured Quad.
GMSH_ALGORITHM_DEFAULT: Final[int] = 11
#: Mesh.RecombinationAlgorithm = 3 -> Blossom full-quad.
GMSH_RECOMB_ALGORITHM_DEFAULT: Final[int] = 3

#: Nilai Mesh.Algorithm 2D yang sah pada gmsh 4.x (rule 7d).
GMSH_VALID_ALGORITHMS: Final[frozenset[int]] = frozenset({1, 2, 3, 5, 6, 7, 8, 9, 11})
#: Nilai Mesh.RecombinationAlgorithm yang sah pada gmsh 4.x (rule 7d).
GMSH_VALID_RECOMB_ALGORITHMS: Final[frozenset[int]] = frozenset({0, 1, 2, 3})

#: Tipe elemen gmsh yang dipakai untuk klasifikasi hasil mesh.
GMSH_ELEMTYPE_TRIANGLE: Final[int] = 2
GMSH_ELEMTYPE_QUAD: Final[int] = 3

#: Order elemen yang didukung v1.0. Nilai lain -> RAISE (PRD Bagian 5.3 rule 7c).
SUPPORTED_ELEMENT_ORDERS: Final[frozenset[int]] = frozenset({1})

#: Mode `graded`: jarak transisi dari tepi area refinement, dinyatakan sebagai kelipatan
#: `size_global`. Ini parameter MESHING murni (mengatur seberapa cepat ukuran elemen
#: membesar menjauhi pile/pier), bukan angka desain. Kepekaan hasil terhadap kehalusan
#: mesh diperiksa terpisah lewat VC-4 (PRD Bagian 8.1).
GRADED_TRANSITION_FACTOR: Final[float] = 3.0

#: Prefiks nama physical group. Prioritas klaim fragment: PIER > PILE > CAP.
GROUP_CAP: Final[str] = "CAP"
GROUP_PILE_PREFIX: Final[str] = "PILE_"
GROUP_PIER_PREFIX: Final[str] = "PIER_"

# ---------------------------------------------------------------------------
# Konvensi FEM (PRD Bagian 7.1)
# ---------------------------------------------------------------------------

#: Faktor koreksi tanda momen OpenSees terhadap konvensi PRD Bagian 7.1.
#:
#: SENGAJA `None`. Nilainya HANYA boleh ditetapkan setelah Validation Case VC-1
#: dijalankan dan tandanya terbukti (PRD Bagian 7.1: "Agent DILARANG menebak tanda
#: tanpa menjalankan VC-1"). postproc_engine.py WAJIB RAISE selama nilainya masih None.
MOMENT_SIGN_FACTOR: Final[float | None] = None

#: Jumlah titik Gauss ShellMITC4 dan jumlah komponen resultant per titik.
#: Dipakai untuk assertion di postproc_engine (PRD Bagian 7.2(2)). Nilai ini WAJIB
#: diverifikasi terhadap OpenSees versi terpasang pada Fase 2 sebelum dipakai.
SHELL_N_GAUSS: Final[int] = 4
SHELL_N_RESULTANT_COMPONENTS: Final[int] = 8

# ---------------------------------------------------------------------------
# Output & visualisasi (PRD Bagian 9)
# ---------------------------------------------------------------------------

RUN_DIR_FORMAT: Final[str] = "pilecap_%Y%m%d_%H%M%S"
MODEL_SUBDIR: Final[str] = "00_Model"
OUTPUT_DPI: Final[int] = 300

#: Diverging, dinormalisasi simetris terhadap nol (PRD Bagian 9.3).
CMAP_MOMENT: Final[str] = "RdBu_r"
#: Sequential untuk magnitudo.
CMAP_MAGNITUDE: Final[str] = "viridis"
#: Warna netral untuk nilai NaN, dengan entri legenda eksplisit.
COLOR_NAN: Final[str] = "#9e9e9e"
LABEL_NAN: Final[str] = "NaN - tidak terdefinisi"

#: Bahasa laporan & plot. DIKONFIRMASI USER (PRD Bagian 17 item 9):
#: narasi Indonesia, istilah teknis dibiarkan Inggris.
REPORT_LANGUAGE: Final[str] = "id"

# ---------------------------------------------------------------------------
# Blok teks tetap laporan (PRD Bagian 8.3 & 9.4)
# ---------------------------------------------------------------------------

#: PRD Bagian 17 item 18 masih TERBUKA -- redaksi final ditetapkan user/kantor.
#: Sampai itu dipakai redaksi PRD Bagian 9.4 poin 9 apa adanya, ditandai DRAFT.
DISCLAIMER_IS_DRAFT: Final[bool] = True
DISCLAIMER_TEXT: Final[str] = (
    "Hasil perhitungan ini dihasilkan secara otomatis oleh pilecap-fem v{version} dan "
    "merupakan ALAT BANTU. Hasil wajib diperiksa dan disetujui oleh engineer yang "
    "bertanggung jawab. Pengecekan di luar ruang lingkup PRD Bagian 1.4 TIDAK dilakukan "
    "oleh tool ini."
)

#: PRD Bagian 8.3 -- WAJIB direproduksi apa adanya di setiap SUMMARY.md dan calc_sheet.md.
KNOWN_LIMITATIONS: Final[str] = """\
1. **Model pelat lentur, bukan strut-and-tie.** Pilecap dengan rasio bentang geser terhadap
   tinggi efektif yang kecil (*deep pile cap*) berperilaku sebagai *deep member* dengan
   mekanisme strut-and-tie, bukan lentur pelat. Hasil tool ini **tidak sah sebagai
   satu-satunya dasar desain** untuk kasus tersebut.

2. **Pier dimodelkan sebagai jepit sempurna.** Ini mengabaikan fleksibilitas pier dan
   menimbulkan singularitas tegangan di tepi zona jepit. Momen puncak di titik tersebut
   **bukan** momen desain. Tumpuan jepit juga cenderung **lebih kaku dari kondisi nyata**,
   sehingga momen di daerah pier bisa **over-estimate** dan momen lapangan **under-estimate**.

3. **Reaksi pile adalah input, bukan hasil.** Tool tidak memverifikasi apakah distribusi
   reaksi pile yang diinput konsisten dengan kekakuan pilecap. Jika `Pz` berasal dari asumsi
   pilecap kaku sempurna, sedangkan model FEM ini pilecap lentur, terdapat inkonsistensi
   konseptual yang **tanggung jawab user** untuk menilai.

4. **Pile hanya memberi gaya vertikal.** `Hx`, `Hy`, dan momen kepala pile diabaikan di v1.0.

5. **Kekakuan pile diabaikan** - pile dimodelkan sebagai beban, bukan sebagai pegas/tumpuan
   elastis. Model alternatif (pile sebagai pegas, pier sebagai beban) memberi hasil berbeda
   dan **tidak** didukung di v1.0.

6. **Material elastis linier isotropik.** Tidak ada retak, tidak ada redistribusi momen
   akibat retak. Momen elastis di daerah tumpuan cenderung lebih tinggi daripada momen
   setelah redistribusi.

7. **Geser pons (punching) dari keseimbangan, bukan dari model shell.** Elemen shell 2D
   tidak memodelkan mekanisme keruntuhan pons tiga dimensi.

8. **Berat sendiri opsional dan default OFF** - user harus sadar apakah `Pz` yang diinput
   sudah memperhitungkan berat pilecap atau belum. Tool tidak bisa mendeteksi ini.
"""

#: Item PRD Bagian 17 yang masih terbuka. Ditampilkan di laporan agar checker tahu
#: cek mana yang BELUM dilakukan tool (PRD Bagian 1.3 poin 5 & 6).
OPEN_BLOCKERS: Final[dict[str, str]] = {
    "#2": "Standar desain & tahun (SNI gedung vs jembatan)",
    "#3": "Pasal: penampang kritis momen, b_o & d punching, V_c, phi",
    "#5": "Kriteria batas deep pile cap + pasal",
    "#6": "Apakah Pz input sudah termasuk berat sendiri pilecap",
    "#7": "Sumber & angka koefisien VC-1 (Timoshenko, tabel mana)",
    "#8": "Ketersediaan model pembanding SAP2000/Midas untuk VC-6",
    "#10": "Skala data realistis (jumlah elemen & kombinasi)",
    "#18": "Redaksi disclaimer/pernyataan tanggung jawab",
}

# ---------------------------------------------------------------------------
# Logging (PRD Bagian 13.3, Core 11)
# ---------------------------------------------------------------------------

# `%(module)s` dipakai (bukan `%(name)s`) agar formatnya persis contoh PRD Bagian 16A:
#   INFO    [io_utils]      Config: ...
LOG_FORMAT_CONSOLE: Final[str] = "%(levelname)-7s [%(module)s] %(message)s"
LOG_FORMAT_FILE: Final[str] = "%(asctime)s %(levelname)-7s [%(module)s] %(message)s"
LOG_FILENAME: Final[str] = "run.log"


def setup_logging(output_dir: Path | None = None, level: str = "INFO") -> logging.Logger:
    """Pasang handler konsol (level user) + file `run.log` (DEBUG) di folder output.

    Dipanggil sekali per run oleh CLI. Idempoten: handler lama pada logger root paket
    dibuang lebih dulu agar pemanggilan berulang (mis. di dalam test) tidak menggandakan
    baris log.
    """
    logger = logging.getLogger("pilecap_fem")
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(getattr(logging, level.upper()))
    console.setFormatter(logging.Formatter(LOG_FORMAT_CONSOLE))
    logger.addHandler(console)

    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(output_dir / LOG_FILENAME, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT_FILE))
        logger.addHandler(file_handler)

    return logger


def get_logger(module_name: str) -> logging.Logger:
    """Logger per modul. `module_name` adalah nama pendek, mis. "io_utils"."""
    return logging.getLogger(f"pilecap_fem.{module_name}")
