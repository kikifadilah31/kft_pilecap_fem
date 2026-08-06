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
    # Luas tulangan per satuan lebar. SI-nya m^2/m; angka SI-nya sangat kecil
    # (1.080 mm^2/m = 1,08e-3 m^2/m) tetapi invariant "internal selalu SI" tetap
    # dipegang, dan konversi tampilan tetap hanya terjadi lewat to_display().
    "steel_area": ("mm^2/m", 1e6),
    # Av/s -- luas sengkang per satuan jarak. SI-nya juga m^2/m, tetapi satuan
    # tampilannya berbeda, sehingga butuh kunci besaran tersendiri.
    "shear_steel_ratio": ("mm^2/mm", 1e3),
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

#: Toleransi default cek keseimbangan gaya VC-0 (PRD Bagian 6.2, --equilibrium-rtol).
#: PRD Bagian 8.1 menetapkan rtol=1e-6 untuk gaya; nilai 1e-3 di sini adalah default CLI
#: yang lebih longgar dan dapat diperketat lewat flag. VC-0 di test memakai 1e-6.
EQUILIBRIUM_RTOL_DEFAULT: Final[float] = 1e-3

#: Toleransi residu MOMEN pada VC-0 (PRD Bagian 8.1: rtol 1e-4).
EQUILIBRIUM_MOMENT_RTOL: Final[float] = 1e-4

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

#: Nama response OpenSees yang mengembalikan STRESS RESULTANT per titik Gauss.
#:
#: DIUKUR, bukan diasumsikan (openseespy 3.8.0.0, ShellMITC4):
#:   eleResponse(tag, 'forces')   -> 24 nilai = 4 node x 6 DOF, gaya nodal GLOBAL
#:   eleResponse(tag, 'stresses') -> 32 nilai = 4 titik Gauss x 8 komponen  <-- INI
#:
#: PRD Bagian 7.2(2) menyebut `'forces'`; itu KELIRU untuk versi ini dan akan
#: menghasilkan array 24 elemen yang tidak dapat dibentuk ulang menjadi (n_gauss, 8).
#: Dibuktikan otomatis oleh `tests/test_validation_cases.py::test_vc3_*`.
SHELL_RESULTANT_RESPONSE: Final[str] = "stresses"

#: Response gaya nodal (4 node x 6 DOF, koordinat global). Bukan stress resultant.
SHELL_NODAL_FORCE_RESPONSE: Final[str] = "forces"

#: Jumlah titik Gauss ShellMITC4 dan jumlah komponen resultant per titik.
#: DIVERIFIKASI: len(eleResponse(tag, 'stresses')) == 4 * 8 == 32.
SHELL_N_GAUSS: Final[int] = 4
SHELL_N_RESULTANT_COMPONENTS: Final[int] = 8

#: Urutan komponen dalam tiap blok 8-nilai. DIVERIFIKASI lewat pelat satu arah:
#: hanya indeks 3 (m11) dan 6 (q1) yang tak nol saat lentur satu arah sepanjang
#: sumbu lokal-1, dan besarnya cocok dengan statika eksak.
RESULTANT_COMPONENT_ORDER: Final[tuple[str, ...]] = (
    "p11",
    "p22",
    "p12",
    "m11",
    "m22",
    "m12",
    "q1",
    "q2",
)

#: Faktor koreksi tanda MOMEN OpenSees terhadap konvensi PRD Bagian 7.1
#: ("positif = serat bawah tertarik").
#:
#: DITETAPKAN = -1.0 berdasarkan kalibrasi terhadap **statika eksak**, bukan tebakan:
#: pelat satu arah bertumpuan sederhana dengan beban merata ke bawah -- kondisi yang
#: jelas membuat serat bawah tertarik, sehingga menurut PRD Bagian 7.1 momennya POSITIF.
#: Hasil pengukuran (Lx=4 m, Ly=2 m, t=0.1 m, q=1 kPa, mesh 24x12):
#:
#:     M statika eksak (q L^2 B / 8) = +4.000,0 N.m
#:     Sigma m11 OpenSees x lebar    = -3.986,1 N.m   (selisih 0,35% = diskretisasi)
#:
#: Tandanya berlawanan -> faktor -1.0. Dibuktikan otomatis oleh VC-3 di
#: `tests/test_validation_cases.py`; test itu GAGAL bila nilai ini diubah keliru.
#:
#: Catatan: kalibrasi ini TIDAK memakai koefisien Timoshenko dari VC-1 (PRD Bagian 17
#: item 7 masih terbuka). Pelat satu arah bertumpuan sederhana adalah kasus statis
#: tertentu -- momennya mengikuti kesetimbangan saja, tanpa perlu tabel dari buku.
MOMENT_SIGN_FACTOR: Final[float] = -1.0

#: Faktor koreksi tanda GESER TRANSVERSAL. DIUKUR TERPISAH, tidak diwarisi dari
#: faktor momen: pada kolom elemen x = 1,9167 m dari kasus yang sama, geser statika
#: eksak per lebar V = q (L/2 - x) memberi +166,7 N setelah dikali lebar, sedangkan
#: q1 OpenSees memberi -166,7 N. Diverifikasi juga oleh VC-3.
SHEAR_SIGN_FACTOR: Final[float] = -1.0

#: Gaya membran (p11, p22, p12) TIDAK diberi faktor koreksi: v1.0 tidak memiliki
#: pembebanan dalam bidang, sehingga tandanya tidak pernah menentukan hasil desain.
#: Bila kelak ada beban lateral pile (Hx, Hy), tandanya WAJIB dikalibrasi terpisah.
MEMBRANE_SIGN_FACTOR: Final[float] = 1.0

#: DIUKUR: ShellMITC4 MENOLAK seluruh tipe eleLoad yang dicoba
#: (`-surfaceLoad`, `-shellSurface`, `-beamUniform`, `-Pressure`, `-shellSelfWeight`),
#: dengan pesan "ShellMITC4::addLoad() - ele ... does not deal with load type: 9",
#: dan Sigma reaksi tetap NOL. Karena itu tekanan pile (PRD Bagian 7.3a) diterapkan
#: sebagai beban NODAL KONSISTEN per elemen. Matematikanya identik dan Sigma beban
#: tetap persis P_z, sehingga VC-0 tetap eksak.
SHELL_SURFACE_PRESSURE_SUPPORTED: Final[bool] = False

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

#: Batas jumlah elemen sebelum plot opsvis DILEWATI otomatis.
#:
#: DIUKUR: `opsv.plot_model` 0,67 s dan `opsv.plot_defo` 5,1 s untuk 1.200 elemen,
#: dengan `plot_defo` tumbuh lebih cepat dari linier. Pada contoh ex02 (6.844 elemen)
#: biayanya akan berlipat dan bertabrakan dengan target PRD Bagian 13.1
#: (< 60 detik untuk ~5.000 elemen x 5 kombinasi).
#:
#: Melewati plot BUKAN mengabaikan parameter diam-diam: setiap kali dilewati, alasannya
#: muncul sebagai WARNING di konsol, `run.log`, dan laporan. Flag `--opsvis` memaksa
#: plot tetap dibuat berapa pun ukurannya.
OPSVIS_MAX_ELEMENTS: Final[int] = 3_000

#: Nama berkas keluaran (PRD Bagian 9.1). Dikumpulkan di sini agar tidak tersebar
#: sebagai string literal di renderer, reporter, dan CLI.
FILE_MESH_PLAN: Final[str] = "mesh_plan.png"
FILE_MODEL_OPSVIS: Final[str] = "model_opsvis.png"
FILE_BOUNDARY_CHECK: Final[str] = "boundary_load_check.png"
FILE_GEOMETRY_JSON: Final[str] = "geometry.json"
FILE_DEFORMED_OPSVIS: Final[str] = "deformed_opsvis.png"
FILE_NODE_DISPLACEMENTS: Final[str] = "node_displacements.csv"
FILE_CALC_SHEET: Final[str] = "calc_sheet.md"
FILE_TRACEABILITY: Final[str] = "traceability_sample.json"
FILE_SUMMARY: Final[str] = "SUMMARY.md"
ENVELOPE_SUBDIR: Final[str] = "Envelope"

#: Peta field hasil -> (nama berkas kontur, besaran satuan, judul).
CONTOUR_FIELDS: Final[dict[str, tuple[str, str, str]]] = {
    "m_xx": ("contour_mx.png", "moment_per_width", "Momen m_x (tulangan arah X)"),
    "m_yy": ("contour_my.png", "moment_per_width", "Momen m_y (tulangan arah Y)"),
    "m_xy": ("contour_mxy.png", "moment_per_width", "Momen puntir m_xy"),
    "q_x": ("contour_qx.png", "shear_per_width", "Geser transversal q_x"),
    "q_y": ("contour_qy.png", "shear_per_width", "Geser transversal q_y"),
}
FILE_CONTOUR_DEFLECTION: Final[str] = "contour_deflection.png"
FILE_REBAR_DESIGN: Final[str] = "rebar_design.csv"
FILE_REBAR_ENVELOPE: Final[str] = "rebar_design_envelope.csv"

#: Empat kombinasi arah x muka yang didesain. Kunci = (arah, muka); nilai = (berkas, judul).
#: Muka BAWAH lahir dari momen POSITIF dan muka ATAS dari momen NEGATIF -- pemisahan itu
#: dilakukan `capacity_engine._face_moments`, bukan di sini.
REBAR_FACES: Final[dict[tuple[str, str], tuple[str, str]]] = {
    ("x", "bawah"): ("contour_As_x_bawah.png", "As perlu arah X - muka BAWAH (m_x > 0)"),
    ("x", "atas"): ("contour_As_x_atas.png", "As perlu arah X - muka ATAS (m_x < 0)"),
    ("y", "bawah"): ("contour_As_y_bawah.png", "As perlu arah Y - muka BAWAH (m_y > 0)"),
    ("y", "atas"): ("contour_As_y_atas.png", "As perlu arah Y - muka ATAS (m_y < 0)"),
}
#: Field ElementResults yang menjadi sumber momen tiap arah.
REBAR_MOMENT_FIELD: Final[dict[str, str]] = {"x": "m_xx", "y": "m_yy"}

#: Rasio geometri deep pile cap DILAPORKAN tanpa vonis: ambangnya (PRD Bagian 17 item 5)
#: belum dikonfirmasi. Menuliskan angka batas tanpa pasal berarti tool memberi kesimpulan
#: yang tidak dapat dipertanggungjawabkan -- justru yang dilarang PRD Bagian 1.3 poin 2.
DEEP_PILECAP_RATIO_REPORTED_ONLY: Final[bool] = True

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

9. **Mesh gmsh TIDAK reproducible bit demi bit.** DIUKUR pada gmsh 4.15.2, dua run dengan
   input dan versi yang sama: jumlah node & elemen selalu identik, tetapi posisi node dapat
   berbeda hingga **33 mm** pada model 12 pile. Menyetel `General.NumThreads = 1` **tidak**
   menghilangkannya - penyebabnya ada di algoritma Quasi-structured Quad itu sendiri.
   Dampaknya pada angka desain DIUKUR kecil: momen lajur dan `As` bergeser paling banyak
   **0,02%** antar run. Konsekuensi praktisnya: `As` dan momen lajur dapat dibandingkan
   antar run, tetapi **nilai per elemen di satu titik tidak** - dua run dapat memberi
   angka berbeda di lokasi yang sama karena elemennya memang bukan elemen yang sama.
   Untuk mereproduksi angka secara persis, simpan `00_Model/nodes.csv` dan
   `elements.csv`; keduanya memuat mesh yang benar-benar dipakai.
"""

#: Sebaran relatif maksimum besaran DESAIN antar run berulang dengan kode & input sama.
#: DIUKUR pada 3 run: ex01 0,000%, ex02 0,021%, ex03 0,000% (lihat KNOWN_LIMITATIONS #9).
#: Dipakai `tests/test_golden.py` untuk menetapkan toleransi dari data, bukan dari tebakan.
MESH_NONDETERMINISM_DESIGN_SPREAD: Final[float] = 2.1e-4

#: Item PRD Bagian 17 yang masih terbuka. Ditampilkan di laporan agar checker tahu
#: cek mana yang BELUM dilakukan tool (PRD Bagian 1.3 poin 5 & 6).
OPEN_BLOCKERS: Final[dict[str, str]] = {
    # #2 (standar & tahun) dan #3 (pasal V_c, phi, penampang kritis) DITUTUP pada v0.4.0:
    # keduanya terjawab oleh shell-kit, yang mengimplementasikan SNI 2847:2019 beserta
    # sitasi pasalnya (lihat capacity_engine.SNI_CLAUSES). Yang TIDAK ikut tertutup adalah
    # b_o & d untuk geser PONS -- shell-kit hanya menyediakan geser satu arah -- sehingga
    # bagian itu tetap terbuka dan dicatat terpisah di bawah.
    "#3b": "Pasal kapasitas geser PONS: V_c dua arah, definisi b_o & d, phi",
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


# ---------------------------------------------------------------------------
# Contoh bawaan (PRD Bagian 5.4)
# ---------------------------------------------------------------------------

#: Nama ketiga folder contoh yang WAJIB ada (PRD Bagian 5.4).
EXAMPLE_NAMES: Final[tuple[str, ...]] = (
    "ex01_standard_4pile",
    "ex02_standard_12pile",
    "ex03_custom_polygon",
)


def examples_dir() -> Path:
    """Folder contoh bawaan.

    Dicari di dua tempat: salinan yang ikut terkemas di dalam paket (jalur pengguna
    `uvx`, yang tidak meng-clone repo), lalu `examples/` di akar repo (jalur
    pengembangan).

    Fallback ke repo diperlukan agar test tetap berjalan sebelum paket dibangun, TETAPI
    fallback itu juga dapat menutupi kesalahan pengemasan -- karena itu isi wheel
    diperiksa terpisah, bukan hanya perilaku di repo
    (`tests/test_packaging.py::test_wheel_memuat_contoh`).
    """
    packaged = Path(__file__).parent / "examples"
    if packaged.is_dir():
        return packaged
    repo = Path(__file__).resolve().parents[2] / "examples"
    if repo.is_dir():
        return repo
    raise FileNotFoundError(
        "Folder contoh tidak ditemukan, baik di dalam paket "
        f"({packaged}) maupun di akar repo ({repo}). "
        "Instalasi kemungkinan tidak lengkap."
    )
