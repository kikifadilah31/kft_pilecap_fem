# Changelog

Format mengikuti template PRD Bagian 16C.

## [0.2.0] — 2026-08-04 — Fase 2: analisis FEM + validation case

### Added
- `math_engine.py` — transformasi tensor momen & vektor geser, integrasi strip,
  kekakuan pelat. Tidak mengimpor gmsh/openseespy/matplotlib (Core 7, dijaga test).
- `fem_engine.py` — `SupportStrategy` / `PileLoadStrategy` sebagai kontrak eksplisit,
  `ops.wipe()` per kombinasi, cek keseimbangan **VC-0 di setiap run**.
- `postproc_engine.py` — rata-rata Gauss → koreksi tanda → transformasi global,
  `traceability_sample()` (rantai telusur satu elemen), `strip_moments()`.
- `io_utils.load_reactions()` + `ReactionTable`; `validators.validate_reactions()`.
- `cli_pilecap_analyze.py` — CLI `pilecap-analyze` dengan `--combo`, `--element`,
  `--self-weight`, `--equilibrium-rtol`, `--no-save-raw`.
- Output per kombinasi: `Combo_<slug>/element_resultants.csv`, `reactions.csv`,
  `equilibrium_check.json`.
- 307 test; coverage 96% (`math_engine` 99%, `postproc_engine` 99% — target PRD
  Bagian 15.4 adalah ≥90% untuk kedua modul itu).

### Standards — hasil SPIKE, diukur bukan ditebak
PRD Bagian 7.1 melarang menebak konvensi OpenSees. Empat besaran berikut diukur lebih
dulu, lalu dikodekan sebagai konstanta bersumber di `config.py`:

| Konstanta | Nilai | Dasar |
|-----------|-------|-------|
| `SHELL_RESULTANT_RESPONSE` | `"stresses"` | `'forces'` mengembalikan 24 nilai (4 node × 6 DOF, gaya nodal global); `'stresses'` mengembalikan 32 = 4 titik Gauss × 8 komponen |
| `MOMENT_SIGN_FACTOR` | `-1.0` | Statika eksak pelat satu arah: +4.000,0 N·m vs OpenSees −3.986,1 N·m |
| `SHEAR_SIGN_FACTOR` | `-1.0` | Diukur **terpisah** dari momen, bukan diwarisi |
| `SHELL_SURFACE_PRESSURE_SUPPORTED` | `False` | ShellMITC4 menolak semua tipe `eleLoad`; ΣR tetap nol |

Kalibrasi tanda **tidak memakai koefisien buku**: pelat satu arah bertumpuan sederhana
bersifat statis tertentu, sehingga momen & gesernya mengikuti kesetimbangan saja. Karena
itu PRD Bagian 17 item 7 yang masih terbuka tidak menghambat penetapan kedua faktor ini.

### Deviations from PRD — beserta alasannya
5. **`eleResponse` memakai `'stresses'`, bukan `'forces'`.** PRD Bagian 7.2(2) menyebut
   `'forces'`; pada openseespy 3.8.0.0 itu mengembalikan gaya nodal global (24 nilai) dan
   tidak dapat dibentuk ulang menjadi `(n_gauss, 8)`.
6. **Tekanan pile diterapkan sebagai beban nodal konsisten**, bukan lewat `eleLoad`
   (PRD Bagian 7.3a). Matematikanya identik — `p_i = P_z,i / A_disk,i` dengan `A_disk`
   dari jumlah luas elemen mesh — dan Σ beban tetap **persis** `P_z`, sehingga VC-0 eksak.
7. **Integrasi strip memilih elemen secara geometris** (yang benar-benar dipotong garis),
   bukan berdasarkan kedekatan centroid. Pemilihan centroid memilih nol atau dua kolom
   tergantung posisi potongan relatif terhadap mesh, tanpa memunculkan error apa pun.
8. **Lebar kontribusi default `"exact"`** (kliping garis–quad, PRD Bagian 7.2(4) opsi a).
   Metode bounding box melebihkan 34% pada mesh quasi-structured quad; ketiga metode
   setara pada mesh terstruktur dan dibandingkan di VC-3.

### Validation
| VC | Status | Catatan |
|----|--------|---------|
| VC-0 | **PASS** | Kesetimbangan gaya & momen; residu 1e-14…1e-16 pada ketiga contoh. Terbukti MEMBLOKIR: toleransi mustahil → `AnalysisError`, manifest `FAILED`, tanpa output desain. |
| VC-1 | SKIP | Butuh koefisien Timoshenko + nomor tabel (PRD Bagian 17 item 7 terbuka) |
| VC-2 | **PASS** | Tiga jalur: pergeseran konektivitas, model diputar 30°/45°, dan mesh gmsh berorientasi tersebar (m12 lokal tak-nol pada 39% elemen) |
| VC-3 | **PASS** | Kalibrasi tanda momen & geser terhadap statika eksak |
| VC-4 | **PASS** | Konvergensi mesh h, h/2, h/4; perubahan dua mesh terhalus < 2% |
| VC-5 | **PASS** | Kelebihan lendutan terhadap Kirchhoff berskala (t/L)² |
| VC-6 | SKIP | Butuh model pembanding SAP2000/Midas (PRD Bagian 17 item 8 terbuka) |
| VC-7 | SKIP | Butuh referensi contoh soal metode konvensional |

Golden file: **belum dibuat** — dijadwalkan Fase 4 bersama `pytest --regen-golden`.

### Resolved
- Penyimpangan #4 rilis 0.1.0 (sudut theta "belum terverifikasi") kini **TERBUKTI**:
  pergeseran konektivitas 0/1/2/3 memindahkan momen bentang persis seperti prediksi
  `v1 = 0.5·(r₂ + r₃ − r₁ − r₄)`, dan VC-2 mengonfirmasinya pada sudut sembarang.
- Bug: rule 7a memakai `size_global` juga pada mode `graded`, sehingga menolak
  konfigurasi yang justru sudah memenuhi maksud aturannya.

### Masih terbuka
PRD Bagian 17 item 2, 3, 5, 6, 7, 8, 10, 18. Cek kapasitas tetap `NOT_EVALUATED`.
`math_engine.wood_armer()` sengaja RAISE sampai aturan koreksinya disalin dari sumber
primer Wood (1968) — rumus dasarnya saja tidak konservatif pada daerah momen
berlawanan tanda.

---

## [0.1.0] — 2026-08-04 — Fase 1: geometri + mesh generator

### Added
- `config.py` — Single Source of Truth: tabel konversi satuan, pola auto-detect, ambang
  validasi, opsi gmsh, blok teks disclaimer & Known Limitations, `setup_logging()`.
- `io_utils.py` — satu-satunya titik konversi satuan; auto-detect input; pembacaan CSV
  polygon/pile/pier; **resolusi sumber geometri PRD Bagian 5.2.1** lengkap dengan WARNING
  override 5 baris.
- `validators.py` — implementasi aturan fail-fast PRD Bagian 5.3 + hierarki exception tool.
- `geometry_builder.py` — data model (`Polygon2D`, `Pile`, `Pier`, `GeometryModel`,
  `GeometryResolution`) dan generator grid pile / polygon.
- `mesh_engine.py` — gmsh OCC + `fragment` + physical group (prioritas PIER > PILE > CAP) +
  mesh all-quad + verifikasi hasil.
- `mesh_model.py` — cache Cond A: luas, centroid, theta, dan lookup group O(1).
- `provenance.py` — `run_manifest.json`.
- `renderer.py` / `reporter.py` — subset Fase 1: `mesh_plan.png` & `mesh_summary.md`.
- `cli_pilecap_mesh.py` — CLI `pilecap-mesh`; tiga CLI lain berupa stub berpesan jelas.
- `examples/` — tiga kasus sesuai PRD Bagian 5.4 (folder `expected/` menyusul di Fase 2–3).
- 186 test; coverage 96%.

### Standards
Item PRD Bagian 17 yang **dikonfirmasi user** pada rilis ini:

| # | Item | Keputusan |
|---|------|-----------|
| 4 | `E` beton | Wajib diisi user; `E: null` → RAISE. Tool tidak pernah menghitung E dari `f'c`. Ditambah field wajib `material.E_source`. |
| 9 | Bahasa laporan | Indonesia, istilah teknis dibiarkan Inggris. |
| 11 | Pile sebagai pegas | Belum diperlukan; `fem_engine` akan dirancang dengan abstraksi strategy (Fase 2). |
| 12, 14 | Satuan input | mm / kN / MPa. `Mesh.MeshSize` dalam meter. |
| 13 | `MIN_ELEM_PER_PILE_DIAMETER` | **6** |
| 15 | Ambang keseragaman mesh | **0.35**, diterapkan pada group CAP (lihat Deviations) |
| 16 | Versi gmsh | **4.15.2**, di-pin eksak |
| 17 | Multi-pier | Didukung. JSON tetap satu pier; lebih dari satu pier hanya lewat `pier_polygon.csv` berkolom `pier_id`. |

Masih **terbuka** (memblokir Fase 3): item 2, 3, 5, 6, 7, 8, 10, 18. Selama itu, cek
kapasitas berstatus `NOT_EVALUATED`.

### Deviations from PRD — beserta alasannya
1. **Ambang keseragaman mesh (item 15) berlaku pada group CAP, bukan seluruh elemen.**
   Pengukuran pada ketiga contoh: `std/mean` seluruh elemen 0.346 / 0.403 / 0.417, sedangkan
   pada group CAP 0.131 / 0.200 / 0.171. Nilai "seluruh elemen" didominasi cincin transisi di
   sekeliling disk pile — metrik itu mengukur kelengkungan geometri, bukan keseragaman mesh.
   Angka 0.35 dipertahankan; hanya definisinya dipertajam.
2. **Rule 7a (`D_pile / h ≥ 6`) memakai `size_local_pile` bila `size_mode = "graded"`.**
   PRD menuliskannya terhadap `size_global`, rumusan yang ditulis dengan asumsi mode
   `uniform`. Pada mode graded, area pile justru di-mesh dengan `size_local_pile`, sehingga
   membandingkan terhadap `size_global` akan menolak konfigurasi yang justru memenuhi maksud
   aturannya.
3. **`pier.centerline` masuk daftar field yang di-override bila ada `pier_polygon.csv`.**
   PRD Bagian 5.2.1 menyatakan centerline tidak pernah di-override — aturan itu ditulis saat
   asumsinya masih satu pier. Dengan multi-pier, satu nilai JSON tidak dapat melayani N pier;
   centerline tiap pier diambil dari centroid polygon-nya dan override-nya diteriakkan
   seperti override lain.
4. **`mesh_model.elem_theta` dihitung dari geometri elemen** (`v1 = ½(r₂+r₃−r₁−r₄)`), bukan
   dari penyederhanaan "local-x ≈ arah node1→node2" di PRD Bagian 7.2(3). Nilai ini
   **ditandai belum terverifikasi** dan tidak boleh dipakai menghasilkan momen desain sampai
   VC-2 dijalankan (Fase 2).

### Findings — hasil pengukuran, bukan asumsi
- **`Mesh.Algorithm = 11` menghasilkan mesh 100% quad sendiri**, bahkan tanpa
  `setRecombine`. `RecombinationAlgorithm = 3` + `setRecombine` berfungsi sebagai lapis
  pengaman kedua. Verifikasi `n_tri == 0` setelah `generate(2)` tetap wajib — itulah yang
  membuktikan hasilnya.
- **OpenSees tidak menyediakan `eleLoad` tekanan permukaan sembarang untuk elemen shell.**
  Berdampak pada Fase 2: mode `pressure` (PRD Bagian 7.3a) akan diterapkan sebagai beban
  nodal konsisten per elemen. Matematikanya identik (`p_i = P_z,i / A_disk,i` dengan
  `A_disk` = jumlah luas elemen mesh), Σ beban tetap persis `P_z,i` sehingga VC-0 tetap eksak.

### Validation
- VC-0 s/d VC-7: **belum dijalankan** — seluruhnya membutuhkan model FEM (Fase 2+).
  `pilecap-mesh` mencatat `equilibrium_VC0: NOT_RUN` di `run_manifest.json`.
- Golden file: **belum dibuat** — dibuat setelah hasil FEM tersedia (Fase 2–3).
- `config.MOMENT_SIGN_FACTOR` sengaja bernilai `None`; ditetapkan hanya setelah VC-1.
