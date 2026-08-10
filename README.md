# kft_pilecap_fem — `pilecap-fem`

FEM berbasis OpenSees untuk analisis pilecap, sekaligus pilecap mesh generator berbasis
gmsh Python API. Spesifikasi lengkap ada di [`PRD_pilecap_fem.md`](PRD_pilecap_fem.md).

> **Status: Fase 3 selesai — keempat command berfungsi.** Rantai penuh
> **input → geometri → mesh all-quad → FEM → momen & geser → kontur, envelope, dan
> laporan auditable**, dengan cek keseimbangan VC-0 di setiap run.

> **Tingkat liabilitas: desain nyata yang dibangun di lapangan** (PRD Bagian 1.3).
> Tool ini **alat bantu**, bukan pengganti engineer. Setiap hasil wajib diperiksa dan
> disetujui oleh *engineer of record*. Tidak ada angka tanpa sumber: nilai yang belum
> dikonfirmasi membuat tool **berhenti dengan pesan jelas**, bukan memakai default diam-diam.

---

## Instalasi

Satu-satunya prasyarat adalah [`uv`](https://docs.astral.sh/uv/). Tidak perlu meng-clone
repo, dan tidak perlu menyiapkan Python sendiri. **Git TIDAK dibutuhkan** — baik `uv`
maupun kedua dependency direct-reference (`shell-kit`, dan `pilecap-fem` itu sendiri bila
dipasang dari wheel rilis) diambil lewat HTTPS biasa.

**PC tanpa git — pasang dari wheel rilis, disematkan ke versi tertentu:**

```bash
uv tool install --python 3.12 https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.7.1/pilecap_fem-0.7.1-py3-none-any.whl
```

**PC yang sudah punya git — jalankan langsung dari sumber, tanpa memasang apa pun:**

```bash
uvx --python 3.12 --from git+https://github.com/kikifadilah31/kft_pilecap_fem pilecap-run --help
```

Setelah dipasang, kelima command (`pilecap-mesh`, `pilecap-analyze`, `pilecap-report`,
`pilecap-run`, `pilecap-ui`) tersedia langsung di terminal.

Lima hal yang perlu diketahui:

- **`--python 3.12` wajib** di kedua jalur. `uv` memilih interpreter *sebelum* mengetahui
  `requires-python` paket — terukur memakai Python 3.14 dan tetap memasangnya.
  `openseespy` hanya menyediakan binary untuk CPython 3.12: pada versi lain ia terpasang
  tetapi **gagal diimpor**. Bila flag ini terlupa, tool berhenti dengan pesan yang
  menyebutkan persoalannya dan perintah yang benar — bukan error DLL yang membingungkan.
- **Jalur wheel selalu tersemat ke satu versi** — nomor versinya ada di URL sendiri, jadi
  tidak perlu (dan tidak bisa) "selalu ambil terbaru" lewat jalur ini. Untuk versi lain,
  ganti `v0.7.1` dan nama berkasnya menjadi versi yang dituju di
  [halaman Releases](https://github.com/kikifadilah31/kft_pilecap_fem/releases).
- **`--from` wajib** pada `uvx` karena nama paket (`pilecap-fem`) berbeda dari nama
  command yang dijalankan.
- **Sematkan tag versi** (`@v0.7.1`) pada jalur git untuk pekerjaan yang hasilnya akan
  diperiksa kemudian. `run_manifest.json` merekam `tool_version`; dengan tag, versi itu
  dapat ditarik kembali persis. Tanpa tag, instalasi selalu mengambil `main` terbaru.
- **Unduhan pertama ~60 MB** (gmsh saja 40 MB), lalu di-cache `uv`.

### Mencoba tanpa menyiapkan data sendiri

```bash
uvx --python 3.12 --from git+https://github.com/kikifadilah31/kft_pilecap_fem pilecap-mesh --init-example .
```

Menyalin ketiga contoh bawaan ke folder saat ini. Berkas yang disalin adalah berkas yang
**sama persis** dengan yang dipakai test regresi, jadi tidak bisa basi diam-diam. Pada PC
tanpa git, jalankan perintah yang sama dengan mengganti `--from git+...` menjadi
`--from <URL wheel rilis>` seperti pada instalasi permanen di atas.

### Untuk pengembangan

```bash
git clone https://github.com/kikifadilah31/kft_pilecap_fem && cd kft_pilecap_fem && uv sync --dev
```

Lalu jalankan lewat `uv run <command>`.

## Antarmuka grafis (opsional) — untuk yang tidak terbiasa CLI

```bash
uv sync --extra ui
```
```bash
uv run pilecap-ui
```

Formulir terbuka di `http://localhost:8501` — **offline, hanya mesin ini**. Isi seluruh
masukan, tekan **Jalankan analisis**, selesai. Tidak perlu menulis `pilecap_config.json`
maupun menghafal satu pun flag.

Yang tersedia di formulir:

* **Penjelasan pada setiap field.** Seluruh 58 field dan 11 bagian punya tooltip yang
  ditulis untuk pembaca yang tidak akrab dengan FEM: apa yang diisi, satuannya, dan akibat
  memilih salah. Cakupannya dijaga test — field baru tanpa penjelasan akan menggagalkan
  suite.
* **Muat `pilecap_config.json` yang sudah ada.** Isi path-nya di kotak paling atas lalu
  tekan **Muat**; seluruh formulir terisi dan tetap dapat disunting. Kunci yang tidak
  dikenal formulir dilaporkan, tidak dibuang diam-diam.
* **Pratinjau geometri.** Tombol **Perbarui pratinjau** menggambar denah pilecap, pile,
  dan pier sebelum apa pun dijalankan. Tidak menyentuh gmsh maupun OpenSees, jadi selesai
  seketika, dan override CSV ikut diperhitungkan sehingga yang tergambar memang yang akan
  dianalisis.

Tiga hal yang perlu diketahui:

* **UI menjalankan `pilecap-run` yang sama persis** lewat subprocess — bukan salinan
  enginenya. Setiap validasi, setiap opsi, dan setiap pesan error otomatis ikut, dan
  hasilnya identik dengan menjalankannya dari terminal.
* **Perintah yang dijalankan ditampilkan** sebelum dan sesudah run, siap disalin ke
  terminal. Cara paling mudah mempelajari CLI-nya adalah memakai formulir ini beberapa kali.
* **Berkas input ditunjuk lewat path folder**, bukan diunggah. Dengan begitu `inputs` di
  `run_manifest.json` menunjuk berkas asli Anda, bukan salinan sementara.

Config yang dihasilkan formulir ditulis ke `<folder kerja>/ui_configs/` dengan nama
bertimestamp — bukan ke folder input, agar auto-detect config tidak menjadi ambigu bagi
siapa pun yang kemudian menjalankan CLI tanpa `--config`.

`streamlit` sengaja **opsional**: pengguna CLI tidak ikut memasangnya.

## Pemakaian

Contoh di bawah memakai `uv run` (jalur pengembangan). Bila memasang lewat
`uv tool install`, hilangkan awalan `uv run`.

```bash
uv run pilecap-mesh --config examples/ex01_standard_4pile/pilecap_config.json --input-dir examples/ex01_standard_4pile --export-msh
```

Dengan folder `input/` berisi file-file yang cocok pola auto-detect, cukup:

```bash
uv run pilecap-mesh
```

Untuk rantai penuh — mesh, analisis FEM, kontur, envelope, dan laporan — dalam satu
perintah dan satu folder (butuh `pile_reactions.csv`):

```bash
uv run pilecap-run --config examples/ex03_custom_polygon/pilecap_config.json --input-dir examples/ex03_custom_polygon
```

Membuat ulang laporan dari run yang sudah ada, tanpa mengulang analisis FEM:

```bash
uv run pilecap-report --result-dir output/pilecap_20260804_144133 --strips-x 7
```

Hasil ditulis ke `output/pilecap_YYYYMMDD_HHMMSS/` — **setiap run folder baru, tidak pernah
menimpa**:

```
output/pilecap_20260804_093148/
├── run_manifest.json      # provenance: sha256 input, versi dependency, resolusi geometri
├── run.log
├── 00_Model/
│   ├── mesh_summary.md    # statistik mesh, opsi gmsh efektif, tabel resolusi geometri
│   ├── mesh_plan.png      # denah mesh + label pile & pier
│   ├── nodes.csv          # tag, x, y, z  [SI]
│   ├── elements.csv       # tag, n1..n4, luas, centroid, theta, group
│   ├── model.mct          # model siap impor Midas Civil, lengkap dengan pembebanan
│   └── model.msh          # opsional (--export-msh), untuk dibuka di GUI gmsh
├── SUMMARY.md             # ringkasan lintas kombinasi + governing + Known Limitations
├── Combo_<nama>/          # satu folder per kombinasi
│   ├── calc_sheet.md            # 10 bagian auditable, termasuk rantai telusur 1 elemen
│   ├── element_resultants.csv   # m11/m22/m12 lokal + m_x/m_y/m_xy/q_x/q_y global
│   ├── strip_moments_x.csv      # momen per lajur di muka pier
│   ├── rebar_design.csv         # As perlu per elemen, 4 kombinasi arah x muka (shell-kit)
│   ├── shear_checks.csv         # demand geser satu arah & pons (pons: NOT_EVALUATED)
│   ├── reactions.csv            # reaksi tiap node jepit + baris TOTAL
│   ├── node_displacements.csv   # sumber contour_deflection.png
│   ├── equilibrium_check.json   # VC-0 + jejak beban tiap pile
│   ├── traceability_sample.json # nilai per titik Gauss untuk calc sheet bagian 5
│   ├── shear_rebar.csv          # Av/s (dengan & tanpa Av,min) + diameter sengkang
│   ├── contour_mx.png … contour_deflection.png
│   ├── contour_As_x_bawah.png … contour_As_y_atas.png
│   ├── contour_diameter_x_bawah.png …   # atau _spasi_/_konfigurasi_ menurut rebar_mode
│   ├── contour_Avs_x.png, contour_Avs_y.png
│   ├── contour_Dsengkang_x.png, contour_Dsengkang_y.png
│   └── deformed_opsvis.png
└── Envelope/              # nilai ekstrem lintas kombinasi + governing_combo
    ├── envelope_values.csv
    ├── rebar_design_envelope.csv   # As pakai governing + governing_combo per elemen
    ├── envelope_summary.md
    └── envelope_*_max.png / _min.png
```

### Tema plot

Semua plot mengikuti gaya `shell-kit` dan tersedia dalam dua tema:

```bash
uv run pilecap-run --config input/pilecap_config.json --input-dir input --theme dark
```

Anotasi khas pilecap — lingkaran pile bertanda `Pz`, arsir pier `JEPIT`, outline pilecap —
**tetap ada di seluruh plot**, termasuk plot tulangan. Ini yang tidak dimiliki `shell-kit`,
dan alasan gaya visualnya direplikasi alih-alih memanggil plotter-nya (yang tidak
menyediakan hook untuk menambah gambar).

`--contour-method average-nodal` menghaluskan kontur seperti tampilan `shell-kit` yang
paling rapi. Bawaannya `element-center` (satu warna datar per elemen) karena nilai
resultant memang dihitung per elemen; penghalusan menyiratkan kehalusan yang tidak pernah
dihitung, dan paling menyesatkan di singularitas tepi zona jepit pier.

### Visualisasi

| Berkas | Isi |
|--------|-----|
| `mesh_plan.png` | Denah mesh, label pile & pier |
| `boundary_load_check.png` | Peta node jepit & elemen terbeban — cek visual bahwa tumpuan dan beban menempel di tempat yang benar |
| `contour_m*.png` | Momen per elemen, colormap diverging berpusat nol (`TwoSlopeNorm`) |
| `contour_q*.png`, `contour_deflection.png` | Geser transversal dan lendutan |
| `model_opsvis.png`, `deformed_opsvis.png` | `opsv.plot_model()` / `plot_defo()` |

Setiap plot berjudul **dua baris** — nama besaran lalu kombinasi — dan membawa **kop gambar
teknik bertepi di kiri-bawah, di luar area gambar**, berisi identitas proyek, asumsi desain
(f'c, fy, tebal, selimut, mode tulangan, φ beserta sumbernya), catatan cara baca, dan
peringatan override geometri. Dengan begitu gambar yang dicetak dan ditempel ke laporan
tidak pernah beredar tanpa asumsi yang melahirkan angkanya.

Nilai maks/min sengaja **tidak** ada di kop: keduanya sudah ditandai langsung di atas
elemennya beserta koordinat, dan colorbar membawa rentangnya. Menyalinnya ke kop hanya
menciptakan tempat kedua yang bisa berbeda dari gambarnya.

Kontur digambar **datar per elemen**, tidak dihaluskan: nilai resultant memang per
elemen, dan interpolasi nodal akan menyiratkan kehalusan yang tidak pernah dihitung —
paling menyesatkan justru di daerah singularitas tepi zona jepit.

Plot opsvis **dilewati otomatis** di atas 3.000 elemen (dengan WARNING yang menyebut
alasannya), karena `opsv.plot_defo` tumbuh lebih cepat dari linier — terukur 5,1 detik
untuk 1.200 elemen. Paksa dengan `--opsvis`.

### Ekspor ke Midas Civil (`model.mct`)

Setiap run menulis `00_Model/model.mct`, model teks siap impor Midas Civil: node, elemen
PLATE, grup (`CAP`, `PILE_*`, `PIER_*` — grup yang sama dengan `elements.csv`), material,
tebal, tumpuan jepit di pier, dan **pembebanan lengkap** — satu load case per kombinasi
plus satu `*LOADCOMB` envelope. `pilecap-mesh` juga menulisnya, tetapi tanpa pembebanan:
perintah itu memang tidak pernah membaca `pile_reactions.csv`.

Tekanan pile pada `*PRESSURE` diambil dari fungsi yang **sama** dengan yang dipakai model
OpenSees (`fem_engine.pile_pressures`), bukan dihitung ulang — sehingga model yang Anda
impor memikul beban yang persis sama dengan yang dianalisis. Test membuktikan
`Σ(p × A_elemen) = Σ Pz` pada berkas hasil, bukan pada model internal.

Setiap berkas diawali blok komentar `;` berisi versi tool, perintah, waktu, jumlah entitas,
dan pemetaan nama kombinasi → nama load case MCT. Tiga penyimpangan sengaja terhadap berkas
rujukan, masing-masing dijelaskan di dalam berkas itu sendiri: `*UNIT` ditulis eksplisit,
arah tekanan `GZ` (bukan `LZ`, yang bergantung pada urutan simpul), dan `*GROUP` selalu
bentuk elemen-saja.

> **Perlu satu kali diperiksa saat impor pertama.** Bagian `*CONSTRAINT` dan varian
> user-defined `*MATERIAL` **tidak ada** di berkas rujukan yang tersedia, sehingga
> sintaksnya ditulis menurut konvensi MCT dan belum tervalidasi terhadap contoh nyata.
> Statusnya dinyatakan di header setiap berkas. Pastikan tumpuan dan material terbaca benar
> sebelum memakai hasilnya.

Format berbasis teks lain (mis. SAP2000 `.s2k`) dapat menyusul sebagai modul sejajar di
`src/pilecap_fem/exporters/`; hanya MCT yang tersedia sekarang.

### Argumen penting

| Argumen | Berlaku di | Keterangan |
|---------|------------|------------|
| `--config`, `--input-dir`, `--output-dir` | keduanya | Lokasi input & output |
| `--pilecap-polygon` / `--pile-coords` / `--pier-polygon` | keduanya | Tunjuk CSV geometri secara eksplisit |
| `--no-custom` | keduanya | Abaikan seluruh CSV geometri hasil auto-detect; paksa parameter JSON |
| `--size` | keduanya | Override ukuran mesh global, dalam satuan input (default mm) |
| `--size-mode uniform\|graded` | keduanya | `graded` mengaktifkan refinement lokal di pile/pier |
| `--allow-tri` | keduanya | Izinkan segitiga lolos — **diagnostik saja**, model FEM akan menolaknya |
| `--preview` | `mesh` | Tampilkan plot mesh interaktif |
| `--reactions` | `analyze` | CSV reaksi pile (default auto-detect) |
| `--combo NAMA` | `analyze` | Analisis hanya kombinasi tertentu (boleh diulang) |
| `--element ShellMITC4\|ShellDKGQ\|ShellNLDKGQ` | `analyze` | Mode perbandingan elemen (PRD §11) |
| `--self-weight` | `analyze` | Aktifkan berat sendiri pilecap |
| `--equilibrium-rtol` | `analyze` | Toleransi cek keseimbangan VC-0 |
| `--opsvis` | `analyze` | Paksa plot opsvis meski di atas ambang elemen |
| `--result-dir` | `report` | Folder hasil analisis (default: run terakhir) |
| `--strips-x` / `--strips-y` | `report`, `run` | Jumlah lajur integrasi momen |
| `--moment-at pier_face\|peak\|both` | `report`, `run` | Lokasi momen desain |
| `--no-envelope` | `report`, `run` | Lewati envelope |
| `--wood-armer` | `report`, `run` | **Belum tersedia** — menolak dengan pesan sumber primer |
| `--init-example DIR` | `mesh`, `analyze`, `run` | Salin contoh bawaan ke DIR lalu keluar |
| `--export-msh`, `--dpi`, `--log-level` | semua | Output tambahan & verbositas |

### Cek keseimbangan VC-0

`pilecap-analyze` menjalankan cek kesetimbangan gaya & momen pada **setiap** kombinasi,
bukan hanya saat testing (PRD §1.3 poin 3). Kombinasi yang gagal menghentikan run;
`run_manifest.json` ditandai `FAILED` dan **tidak ada output desain yang dihasilkan**.
Pada ketiga contoh residunya berada di kisaran 1e-14 sampai 1e-16.

## Satuan

Internal **SI murni** (N, m, Pa). File input default **mm / kN / MPa**, dapat di-override
lewat blok `units` di config. Konversi terjadi **hanya** di `io_utils.py`; tabel faktornya
**hanya** di `config.py`.

## Contoh

| Folder | Isi |
|--------|-----|
| `examples/ex01_standard_4pile/` | Pilecap persegi 4 pile, pier persegi — kasus paling umum |
| `examples/ex02_standard_12pile/` | Grid 4×3, pier lingkaran |
| `examples/ex03_custom_polygon/` | Pilecap poligon L, pile custom non-grid, **dua** pier poligon. Sekaligus acuan format ketiga CSV geometri. |

Jalankan `ex03` untuk melihat mekanisme **override geometri**: setiap entitas yang datang
dari CSV diteriakkan sebagai WARNING 5 baris, dicatat di `run_manifest.json`, dan muncul
sebagai baris PERINGATAN berwarna di kop setiap gambar.

## Pengembangan

```bash
uv run pytest -q
```
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/pilecap_fem
```

Test yang menjalankan meshing sungguhan ditandai `slow`; lewati dengan `pytest -m "not slow"`.

**Release gate:** `n_tri == 0` untuk ketiga contoh. Bila test itu gagal, rilis diblokir —
`ShellMITC4` tidak menerima elemen 3-node.

### Golden file

Regresi numerik lintas versi dibandingkan terhadap `tests/golden/*.json`.

```bash
uv run pytest tests/test_golden.py -q
```

Yang dibandingkan bukan koordinat node — **mesh gmsh tidak reproducible bit demi bit**
(lihat "Yang perlu diketahui" di bawah). Yang dibandingkan adalah luas per physical group
(`rtol` 1e-6), jumlah node/elemen (toleransi 2%), nilai medan hasil rata-rata lokal
berbobot luas, dan `As` per lajur.

Regenerasi hanya lewat `--regen-golden`, dan **wajib** disertai catatan alasan di
`CHANGELOG.md`:

```bash
uv run pytest tests/test_golden.py --regen-golden
```

## Nilai yang WAJIB Anda tetapkan sendiri

Tool ini menolak berjalan bila salah satu di bawah kosong. Tidak ada nilai default:
angka-angka ini menentukan seluruh hasil, dan angka tanpa sumber dilarang
(PRD Bagian 1.3 poin 2).

| Field | Satuan | Keterangan |
|-------|--------|-----------|
| `material.E` + `material.E_source` | MPa | Tool **tidak pernah** menghitung `E` dari `f'c` |
| `design.fy` + `design.fy_source` | MPa | `shell_kit.rebar.DEFAULT_FY = 420` **tidak** dipakai diam-diam |
| `design.rebar_mode` | – | `"spacing_fixed"` atau `"diameter_fixed"` — lihat di bawah |
| `design.rebar_spacing` | mm | Wajib pada `spacing_fixed`; menentukan diameter terpilih |
| `design.rebar_config` | – | Wajib pada `diameter_fixed`, mis. `"2D25"` |
| `design.stirrup_spacing_long` + `_trans` | mm | Grid sengkang; keduanya menentukan luas per kaki |
| `design.cover` | mm | — |

`design.phi_flexure` dan `design.phi_shear` boleh `null`; artinya memakai konstanta SNI
bawaan `shell-kit` (0,90 / 0,75), dan **asalnya dicetak** di calc sheet.

### Mode pemilihan tulangan

| `rebar_mode` | Anda tetapkan | Tool hitung | Plot yang dihasilkan |
|--------------|---------------|-------------|----------------------|
| `spacing_fixed` | `rebar_spacing` | **diameter** | kategorikal berlabel `D13`…`D32` |
| `diameter_fixed` | `rebar_config` | **spasi** | kontinu dalam mm, dibatasi `min(2h, 450)` |

Isi `design.rebar_select_codes` (mis. `["16", "22", "2D25"]`) untuk mempersempit pilihan
ke konfigurasi tertentu; plot berubah menjadi kategorikal berlabel kode tersebut.

### `design.as_min_surface_zone` — opsional, tetapi berdampak besar

`As_min` mendominasi hasil pilecap tebal. DIUKUR pada `ex01`: **18 dari 20 lajur**
dikendalikan `As_min`, bukan momen.

| tebal | `As_min` tanpa batas | dengan `as_min_surface_zone: 300` |
|-------|----------------------|-----------------------------------|
| 1.200 mm | 1.080 mm²/m | 540 mm²/m |
| 1.500 mm | 1.350 mm²/m | 540 mm²/m |

**ACI 350-06 Ps. 7.12.2.1** membatasi 300 mm per muka untuk elemen >600 mm; **SNI 2847:2019
tidak menyatakan batas ini**. Karena itu field ini **opsional** (`null` = murni SNI), dan
bila diisi, nilainya beserta sitasinya dicetak di `run_manifest.json` — keputusan itu
tercatat sebagai milik engineer yang menetapkannya.

## Yang BELUM dilakukan tool ini

Sejak v0.4.0 kapasitas **lentur** dan **geser satu arah** dihitung `shell-kit` v3.3.0
menurut SNI 2847:2019, lengkap dengan sitasi pasal di `calc_sheet.md` bagian 7 & 7a.

Yang tetap **`NOT_EVALUATED`**:

- **Kapasitas geser pons.** `shell-kit` hanya menyediakan geser satu arah
  (`calc_Vc` = `b_w × d_v`). `V_u` dan `b_o` pons sudah dihitung dari keseimbangan gaya —
  yang belum ada hanya kapasitasnya.
- **Vonis deep pile cap.** `a/d` dilaporkan tanpa vonis; ambang & pasalnya belum
  dikonfirmasi. Bila pilecap berperilaku *deep member*, `As` dari model lentur pelat ini
  **tidak sah**.
- **Koreksi Wood-Armer.** `m_xy` dihitung dan dikontur, tetapi tidak dipakai mengoreksi
  momen desain.

Lihat `config.OPEN_BLOCKERS` dan PRD Bagian 17 — item **3b, 5, 6, 7, 10, 18** masih
terbuka.

## Divalidasi silang terhadap Midas Civil (VC-6)

Sejak v0.8.0 `VC-6` berjalan sebagai **release gate**: ketiga contoh bawaan dimodelkan
ulang di Midas Civil — diimpor dari `model.mct` yang ditulis tool ini sendiri, sehingga
penomoran node & elemennya identik 1:1 — lalu hasilnya dibandingkan elemen demi elemen.

Kesesuaian yang terukur (RMS terhadap nilai puncak, 3 contoh × 2 kombinasi):

| Besaran | RMS terburuk | Korelasi minimum |
|---------|-------------:|-----------------:|
| Momen `m_xx`, `m_yy`, `m_xy` | 0,144% | 0,99991 |
| Geser `q_x`, `q_y` | 0,265% | 0,99993 |
| Lendutan per node `uz` | 0,216% | 0,999986 |
| Reaksi tumpuan `Rz` | 0,539% | 0,999596 |
| Momen **puncak** (penentu tulangan) | 0,515% | — |

Dua hal yang perlu dibaca jujur:

- **Konvensi tanda geser Midas berlawanan** dengan konvensi tool ini, dan itu
  direkonsiliasi secara eksplisit — bukan disembunyikan. Buktinya seragam: tidak ada satu
  pun dari ~5.500 elemen yang menyimpang.
- **Lendutan ex01 dibatasi resolusi ekspor Midas** (1 µm = 0,44% dari skala), yang lebih
  besar daripada selisih terukur. Untuk contoh itu yang terbukti hanyalah "tidak berbeda
  sejauh yang dapat diukur".

Sebagai efek samping, `Σ FZ` reaksi Midas sama dengan `Σ Pz` masukan sampai ~9 angka
berarti — ini memvalidasi **ekspor `model.mct`** secara end-to-end, satu-satunya cek yang
menyentuh sisi Midas yang sesungguhnya. Rincian lengkap: `tests/data/vc6/SUMBER.md`.

## Yang perlu diketahui: mesh tidak reproducible bit demi bit

DIUKUR pada gmsh 4.15.2, dua run dengan input dan versi yang sama: jumlah node & elemen
selalu identik, tetapi posisi node dapat berbeda hingga **33 mm** pada model 12 pile.
`General.NumThreads = 1` **tidak** menghilangkannya — penyebabnya ada pada algoritma
Quasi-structured Quad itu sendiri.

Dampaknya pada angka desain terukur kecil: momen lajur dan `As` bergeser paling banyak
**0,02%** antar run. Konsekuensi praktisnya:

- `As`, momen lajur, dan lendutan **dapat** dibandingkan antar run.
- Nilai **per elemen di satu titik tidak** — dua run dapat memberi angka berbeda di lokasi
  yang sama karena elemennya memang bukan elemen yang sama.
- Untuk mereproduksi angka secara persis, simpan `00_Model/nodes.csv` dan `elements.csv`;
  keduanya memuat mesh yang benar-benar dipakai, dan `pilecap-report` membacanya kembali.
