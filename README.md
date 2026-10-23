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
uv tool install --python 3.12 https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.14.1/pilecap_fem-0.14.1-py3-none-any.whl
```

**Dengan antarmuka grafis** — tambahkan extra-nya pada nama paket. Keduanya terpisah dan
dapat dipasang bersamaan (`pilecap-fem[gui,ui]`):

```bash
uv tool install --python 3.12 "pilecap-fem[gui] @ https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.14.1/pilecap_fem-0.14.1-py3-none-any.whl"
```
```bash
uv tool install --python 3.12 "pilecap-fem[ui] @ https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.14.1/pilecap_fem-0.14.1-py3-none-any.whl"
```

Baris pertama memasang **jendela aplikasi** (`pilecap-gui`, wxPython), baris kedua **formulir peramban** (`pilecap-ui`, Streamlit). Tanpa extra, kedua perintah itu tetap terdaftar tetapi hanya mencetak petunjuk pemasangan.

**PC yang sudah punya git — jalankan langsung dari sumber, tanpa memasang apa pun:**

```bash
uvx --python 3.12 --from git+https://github.com/kikifadilah31/kft_pilecap_fem pilecap-run --help
```

Setelah dipasang, keenam command (`pilecap-mesh`, `pilecap-analyze`, `pilecap-report`,
`pilecap-run`, `pilecap-ui`, `pilecap-gui`) tersedia langsung di terminal.

Lima hal yang perlu diketahui:

- **`--python 3.12` wajib** di kedua jalur. `uv` memilih interpreter *sebelum* mengetahui
  `requires-python` paket — terukur memakai Python 3.14 dan tetap memasangnya.
  `openseespy` hanya menyediakan binary untuk CPython 3.12: pada versi lain ia terpasang
  tetapi **gagal diimpor**. Bila flag ini terlupa, tool berhenti dengan pesan yang
  menyebutkan persoalannya dan perintah yang benar — bukan error DLL yang membingungkan.
- **Jalur wheel selalu tersemat ke satu versi** — nomor versinya ada di URL sendiri, jadi
  tidak perlu (dan tidak bisa) "selalu ambil terbaru" lewat jalur ini. Untuk versi lain,
  ganti `v0.14.1` dan nama berkasnya menjadi versi yang dituju di
  [halaman Releases](https://github.com/kikifadilah31/kft_pilecap_fem/releases) — lihat
  juga "Upgrade ke versi terbaru" di bawah.
- **`--from` wajib** pada `uvx` karena nama paket (`pilecap-fem`) berbeda dari nama
  command yang dijalankan.
- **Sematkan tag versi** (`@v0.14.1`) pada jalur git untuk pekerjaan yang hasilnya akan
  diperiksa kemudian. `run_manifest.json` merekam `tool_version`; dengan tag, versi itu
  dapat ditarik kembali persis. Tanpa tag, instalasi selalu mengambil `main` terbaru.
- **Unduhan pertama ~60 MB** (gmsh saja 40 MB), lalu di-cache `uv`.

### Upgrade ke versi terbaru

Cek versi yang terpasang:

```bash
pilecap-run --version
```

**PC tanpa git (jalur wheel):** setiap rilis punya URL wheel sendiri (lihat langkah di atas
"Jalur wheel selalu tersemat ke satu versi") — upgrade berarti memasang ulang dari URL rilis
yang lebih baru, dengan `--force` karena nama tool-nya (`pilecap-fem`) sudah terpasang:

```bash
uv tool install --python 3.12 --force https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.14.1/pilecap_fem-0.14.1-py3-none-any.whl
```

Ganti `v0.14.1` dan nama berkasnya sesuai versi yang dituju di
[halaman Releases](https://github.com/kikifadilah31/kft_pilecap_fem/releases). Tanpa
`--force`, `uv` menolak memasang di atas tool dengan nama yang sama.

Bila sebelumnya Anda memasang antarmuka grafis, **sertakan extra-nya lagi** (`"pilecap-fem[gui] @ <URL wheel>"`): memasang ulang tanpa extra menghapus wxPython dari tool tersebut, dan `pilecap-gui` kembali hanya mencetak petunjuk pemasangan.

**PC yang sudah punya git (jalur `uvx`):** setiap pemanggilan tanpa tag versi (`@vX.Y.Z`)
sudah otomatis mengambil `main` terbaru — tidak ada langkah upgrade terpisah. Bila perintah
Anda menyematkan tag (mis. `@v0.11.2`), ganti tagnya ke versi yang dituju.

**Jalur pengembangan (clone git):**

```bash
git pull && uv sync --dev
```

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

## Panduan mandiri untuk diedarkan (`pilecap-manual`)

README ini mengandaikan pembacanya nyaman dengan GitHub. Untuk yang tidak — calon pengguna
di kantor lain, atau eksekutif yang menilai apakah perusahaannya akan memakai tool ini —
tersedia **satu dokumen PDF yang berdiri sendiri**:

```bash
uv run pilecap-manual --out docs/manual
```

Isinya: ringkasan eksekutif yang tuntas dalam ±5 halaman (apa yang dikerjakan, apa yang
**tidak**, tingkat pertanggungjawaban, bukti validasi, kebutuhan penerapan), pemasangan
langkah demi langkah untuk orang yang belum pernah membuka terminal, referensi lengkap
seluruh field config, dasar teori, keluaran, dan keterbatasan.

Dokumen itu **dihasilkan dari kode**, bukan ditulis tangan: versi, daftar field, pasal SNI,
keterbatasan, dan pin dependency ditarik hidup-hidup saat dibangun, sehingga tidak dapat
basi diam-diam terhadap versi yang benar-benar terpasang. `pilecap-manual` ikut di dalam
wheel justru supaya penerima wheel dapat membuat panduan yang cocok dengan versinya
sendiri.

Sumber `.typ` dan ilustrasinya di-commit di `docs/manual/`; PDF-nya tidak — ia dilampirkan
sebagai release asset di samping wheel.

## Antarmuka grafis (opsional) — untuk yang tidak terbiasa CLI

Tersedia **tiga** antarmuka grafis yang berdiri sendiri: jendela wxPython, formulir
peramban Streamlit, dan jendela Qt (PySide6) yang masih **eksperimental** — disediakan untuk
dibandingkan sebelum salah satunya dipilih. Ketiganya memakai daftar field, pembangun config,
dan pembangun argv yang sama, lalu memanggil `pilecap-run` sebagai subprocess — sehingga
ketiganya **tidak dapat** menghasilkan masukan analisis yang berbeda. Kesetaraan itu
diverifikasi dengan membandingkan `pilecap_config.json` yang benar-benar ditulis
masing-masing untuk masukan yang sama.

**Jendela aplikasi** (wxPython) — tanpa server dan tanpa peramban.

Pasang dari wheel rilis, lalu buka:

```bash
uv tool install --python 3.12 --force "pilecap-fem[gui] @ https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.14.1/pilecap_fem-0.14.1-py3-none-any.whl"
```
```bash
pilecap-gui
```

Dari clone lokal (pengembangan):

```bash
uv sync --extra gui
```
```bash
uv run pilecap-gui
```

**Formulir di peramban** (Streamlit):

```bash
uv tool install --python 3.12 --force "pilecap-fem[ui] @ https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.14.1/pilecap_fem-0.14.1-py3-none-any.whl"
```
```bash
pilecap-ui
```

Dari clone lokal (pengembangan):

```bash
uv sync --extra ui
```
```bash
uv run pilecap-ui
```

**Jendela Qt** (PySide6) — **eksperimental**, untuk dibandingkan dengan jendela wxPython.
Saat ini hanya dari clone lokal; wheel rilis v0.14.1 belum memuatnya, jadi jalur pemasangan
dari wheel baru tersedia pada rilis berikutnya.

```bash
uv sync --extra qt
```
```bash
uv run pilecap-qt
```

Extra `qt` memasang `pyside6-essentials`, bukan paket `pyside6` utuh: paket utuh ikut
menarik WebEngine dan modul lain yang tidak dipakai (unduhan ±244 MB berbanding ±79 MB).

Formulir peramban terbuka di `http://localhost:8501` — **offline, hanya mesin ini**. Isi
seluruh masukan, tekan **Jalankan analisis**, selesai. Tidak perlu menulis
`pilecap_config.json` maupun menghafal satu pun flag.

Yang tersedia di formulir:

* **Penjelasan pada setiap field.** Seluruh 60 field dan 11 bagian punya tooltip yang
  ditulis untuk pembaca yang tidak akrab dengan FEM: apa yang diisi, satuannya, dan akibat
  memilih salah. Cakupannya dijaga test — field baru tanpa penjelasan akan menggagalkan
  suite. Penjelasan versi panjang beserta ilustrasinya ada di
  [Panduan lengkap `pilecap_config.json`](#panduan-lengkap-pilecap_configjson).
* **Muat `pilecap_config.json` yang sudah ada.** Isi path-nya di kotak paling atas lalu
  tekan **Muat**; seluruh formulir terisi dan tetap dapat disunting. Kunci yang tidak
  dikenal formulir dilaporkan, tidak dibuang diam-diam.
* **Pratinjau geometri.** Tombol pratinjau menggambar denah pilecap, pile, dan pier
  sebelum apa pun dijalankan. Tidak menyentuh gmsh maupun OpenSees, jadi selesai seketika,
  dan override CSV ikut diperhitungkan sehingga yang tergambar memang yang akan dianalisis.
  Pada jendela aplikasi, pratinjau terbuka di jendela terpisah yang dapat diubah ukuran dan
  dibiarkan terbuka sambil masukannya disunting.

Perbedaan yang ada hanya pada penyajian, bukan pada hasil:

| | Jendela aplikasi | Formulir peramban | Jendela Qt (eksperimental) |
|---|---|---|---|
| Extra | `gui` (wxPython) | `ui` (Streamlit) | `qt` (PySide6) |
| Perintah | `pilecap-gui` | `pilecap-ui` | `pilecap-qt` |
| Port jaringan | tidak ada | `localhost:8501` | tidak ada |
| Susunan 60 field | 12 halaman berseksi | satu kolom bergulir | 12 halaman berseksi |
| Teks bantuan | teks polos (tanda `**` tampil mentah) | markdown dirender | markdown dirender |
| Ilustrasi | PNG hasil rasterisasi Typst | SVG langsung | PNG hasil rasterisasi Typst |

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

`streamlit`, `wxpython`, dan `pyside6-essentials` sengaja **opsional**, dan terpisah satu
sama lain: pengguna CLI tidak ikut memasang satu pun, dan pemakai salah satu jendela tidak
ikut menarik toolkit yang lain maupun server Streamlit.

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
├── laporan_pilecap.pdf    # opsional (--pdf): satu dokumen lengkap seluruh run
├── laporan_pilecap.typ    # sumber Typst-nya, ikut disimpan agar dapat diperiksa & di-diff
├── _figur_pdf/            # salinan gambar berukuran cetak untuk PDF (asli tidak diubah)
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
    ├── strip_design_envelope.csv   # As maks per LAJUR + combo penentu (mode strip saja)
    ├── envelope_summary.md
    ├── envelope_*_max.png / _min.png        # 10 plot gaya (momen & geser)
    ├── envelope_As_*.png                    # 4 — As envelope per muka
    ├── envelope_diameter_*.png              # 4 — batang terpilih dari As envelope
    └── envelope_Avs_*.png, envelope_Dsengkang_*.png   # 4 — geser envelope
```

### Laporan PDF (`--pdf`)

```bash
uv run pilecap-run --config input/pilecap_config.json --input-dir input --pdf
```

Menghasilkan **satu dokumen lengkap untuk seluruh run** — bukan satu PDF per kombinasi —
dengan seluruh diagram yang sudah dibuat menjadi gambar bernomor:

| Bagian | Isi |
|---|---|
| Sampul | proyek, engineer, tanggal, perintah, versi tool, status run, pernyataan tanggung jawab |
| Daftar isi | termasuk daftar gambar dan daftar tabel |
| 1. Ringkasan eksekutif | hasil tiap kombinasi, tulangan governing lintas kombinasi, daftar tegas yang **tidak** dinilai |
| 2. Dasar teori | idealisasi, konvensi tanda, `D = E t³/(12(1−ν²))`, transformasi tensor, integrasi lajur, `V_c` SNI, basis elemen vs lajur, status VC-0..VC-7 — **tiap rumus menyebut sumber dan fungsi yang menghitungnya** |
| 3. Data masukan | provenance + sha256 input, resolusi geometri, geometri, material beserta asal nilainya, pembebanan, mesh |
| 4..N. Per kombinasi | keseimbangan VC-0, gaya dalam + kontur, rantai telusur satu elemen, momen lajur, geser, desain lentur, sengkang, daftar berkas CSV rinci |
| N+1. Envelope | nilai ekstrem + kombinasi penentu, 22 gambar envelope |
| N+2. Keterbatasan | `KNOWN_LIMITATIONS` dan item PRD Bagian 17 yang masih terbuka, **apa adanya** |
| N+3. Tanggung jawab | disclaimer + blok tanda tangan (dibuat / diperiksa / disetujui) |
| Lampiran A | provenance kapasitas: engine, versi, φ, fy beserta sumbernya, fungsi `shell-kit` yang dipanggil, dan pasal SNI yang dipakai |

Yang perlu diketahui:

- **Kompilasi terjadi di dalam Python.** Typst dipanggil lewat binding native yang sudah
  ikut terpasang — **tidak ada biner luar yang perlu Anda pasang**.
- **Sumber `.typ` ikut disimpan** di samping PDF-nya. Ia yang membuat kegagalan kompilasi
  dapat didiagnosis, dan satu-satunya bentuk laporan yang dapat di-diff antar run.
- **Data per elemen tidak dicetak.** Tabel memuat nilai governing dan ekstrem **beserta
  lokasinya**; data lengkap tetap di CSV, yang namanya disebut di dokumen. Mencetak ribuan
  elemen menghasilkan dokumen yang tidak terbaca.
- **Gambar yang tidak ada tidak pernah dihilangkan diam-diam** — ia muncul sebagai kotak
  yang menyebutkan berkasnya, alasannya, dan cara memunculkannya. Itu terjadi bila dipakai
  `--no-rebar-plots`, `--no-envelope`, `--no-save-raw`, atau bila opsvis dilewati.
- **Ukuran berkas.** DIUKUR pada `ex02` (12 pile, 2 kombinasi, 39 halaman, DPI bawaan):
  **22,6 MB, 54 detik** untuk tahap PDF-nya saja. Gambar diperkecil ke
  `config.PDF_IMAGE_MAX_PX` = 1.200 px sebelum ditanam — kontur ditempatkan pada grid dua
  kolom selebar ~8 cm, sehingga itu setara **~381 dpi di tempatnya**, di atas standar cetak
  300 dpi. PNG aslinya tidak pernah diubah. Turunkan konstanta itu bila berkasnya masih
  terlalu besar: 800 px memberi 10 MB dan masih ~254 dpi.
- Angka di PDF berasal dari objek yang **sama persis** dengan `calc_sheet.md` — bukan
  dihitung ulang, bukan dibaca balik dari CSV yang sudah dibulatkan.

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
| `--pdf` | `report`, `run` | Buat laporan PDF lengkap satu run (Typst, dikompilasi di dalam Python) |
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

---

## Panduan lengkap `pilecap_config.json`

Seluruh masukan selain **geometri CSV** dan **reaksi pile** ada di satu berkas JSON ini.
Bagian di bawah menjelaskan **setiap** field: apa artinya, ke mana efeknya, dan apa
akibatnya bila salah.

**Daftar isi:** [Gambaran model](#gambaran-model--siapa-menumpu-siapa) ·
[Sistem koordinat](#sistem-koordinat--satu-titik-untuk-tiga-blok) ·
[`project`](#project--identitas-run) · [`units`](#units--satuan-yang-anda-ketik) ·
[`pilecap`](#pilecap--pelatnya) · [`pile`](#pile--tiang) · [`pier`](#pier--kolompilar) ·
[`material`](#material--beton) · [`mesh`](#mesh--kehalusan-diskretisasi) ·
[`analysis`](#analysis--pilihan-numerik) · [`design`](#design--umum) ·
[Pemilihan tulangan](#design--pemilihan-tulangan) · [Sengkang](#design--sengkang) ·
[Override CSV](#kapan-config-diabaikan--override-csv) ·
[Ringkasan wajib/opsional](#ringkasan--wajib-opsional-dan-bawaan)

Cara membaca kolom **Bawaan** — ketiganya **diperiksa langsung terhadap tool**, bukan
disimpulkan dari kode:

| Isi kolom | Artinya |
|---|---|
| `—` | **Wajib ada.** Tool berhenti dengan pesan jelas bila tidak ada — tidak pernah menebak. |
| suatu nilai | Boleh dihilangkan; nilai itu yang dipakai. Umumnya pilihan numerik, bukan angka rekayasa. |
| `null` | Fitur **mati** bila dikosongkan. Mengisinya adalah keputusan sadar Anda dan tercatat di manifest. |

> **Punya bawaan ≠ boleh diabaikan.** Beberapa field berbawaan tetap menentukan hasil —
> `design.strips_x` mengubah tabel angka desain, `pile.modeling` mengubah bentuk momen di
> kepala tiang. Bawaan hanya berarti tool tidak berhenti; ia tidak berarti pilihannya tidak
> penting.

> Kunci yang tidak dikenal **diabaikan diam-diam**, kecuali di dalam blok `units` yang
> menolaknya. Karena itu contoh bawaan memakai kunci `_catatan` sebagai komentar — JSON
> tidak punya sintaks komentar.

### Gambaran model — siapa menumpu siapa

Ini yang paling sering membingungkan di awal, dan menentukan arti hampir semua field
lainnya: **pile bukan tumpuan.**

![Skema tumpuan dan beban](docs/img/skema-tumpuan-beban.svg)

Reaksi pile `Pz` yang sudah Anda ketahui dari analisis struktur atas dimasukkan sebagai
**beban ke atas** pada lingkaran kepala tiang, dan **pier**-lah yang dijepit. Konsekuensinya
disengaja: karena bebannya sudah diketahui, keseimbangan dapat diperiksa **persis** setiap
run — itulah cek VC-0.

### Sistem koordinat — satu titik untuk tiga blok

![Sistem koordinat](docs/img/sistem-koordinat.svg)

`pilecap.origin`, `pile.grid_origin`, dan `pier.centerline` memakai **sistem koordinat yang
sama**. Cara paling aman: biarkan ketiganya `[0, 0]` dan biarkan semuanya berpusat di tengah
pilecap. Bila salah satu digeser tanpa yang lain, geometrinya tetap sah secara JSON tetapi
menjadi model yang berbeda dari yang Anda maksud — periksa `mesh_plan.png` atau tombol
**Perbarui pratinjau** di UI sebelum menganalisis.

### `project` — identitas run

Tidak memengaruhi satu pun angka, tetapi ikut tercetak di kop **setiap** gambar, di
`calc_sheet.md`, dan di `run_manifest.json`. Itulah yang membuat hasil dapat ditelusuri
kembali ke pekerjaan dan orangnya.

| Field | Bawaan | Arti |
|---|---|---|
| `project.name` | kosong | Judul di setiap plot dan kepala laporan. Mis. `"Jembatan A - Pilecap P3"`. |
| `project.engineer` | kosong | Penanggung jawab perhitungan. |
| `project.date` | kosong | Tanggal **desain**, bukan tanggal run (waktu run dicatat otomatis dan terpisah). `YYYY-MM-DD` memudahkan pengurutan. |

Tool **tidak menolak** blok ini bila kosong — ia bukan angka rekayasa. Tetapi laporan tanpa
nama dan tanpa penanggung jawab kehilangan justru jejak yang membuatnya dapat diaudit, jadi
perlakukan ketiganya sebagai wajib dalam praktik.

### `units` — satuan yang Anda ketik

Seluruh blok ini boleh dihilangkan; bawaannya **mm / kN / MPa**.

| Field | Pilihan | Bawaan | Berlaku untuk |
|---|---|---|---|
| `units.length` | `mm`, `cm`, `m` | `mm` | Tebal, panjang, diameter, spasi, selimut — **termasuk CSV geometri**. |
| `units.force` | `N`, `kN`, `MN` | `kN` | `Pz` di `pile_reactions.csv` dan berat jenis beton. |
| `units.stress` | `Pa`, `kPa`, `MPa`, `GPa` | `MPa` | `f'c`, `E`, `fy`. 1 MPa = 1 N/mm² — satuan SNI 2847:2019. |

> **Ini satu-satunya kesalahan yang tidak dapat dideteksi tool.** 1200 mm dan 1200 m
> sama-sama angka yang sah. Pastikan pilihan di sini cocok dengan angka yang benar-benar
> Anda ketik.

### `pilecap` — pelatnya

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `pilecap.thickness` | panjang | `—` | Tebal pelat. **Besaran paling berpengaruh di seluruh model:** kekakuan lentur sebanding tebal **pangkat tiga**, jadi tebal meleset 10% menggeser lendutan ~30%. Menentukan juga tinggi efektif `d` dan kapasitas geser. |
| `pilecap.length_x` | panjang | `—` | Ukuran arah X. **Diabaikan** bila ada CSV poligon pilecap. |
| `pilecap.length_y` | panjang | `—` | Ukuran arah Y. Sama, diabaikan bila ada CSV poligon. |
| `pilecap.origin` | panjang | `—` | Koordinat **titik pusat**, bukan sudut. |

### `pile` — tiang

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `pile.diameter` | panjang | `—` | Diameter kepala tiang — luas lingkaran tempat `Pz` disebar. Diameter lebih kecil memusatkan beban dan menaikkan momen lokal. Selalu dibutuhkan, juga sebagai bawaan bila CSV koordinat pile tidak punya kolom diameter. |
| `pile.n_col` | – | `—` | Jumlah pile arah X pada susunan grid. Total = kolom × baris. |
| `pile.n_row` | – | `—` | Jumlah pile arah Y. |
| `pile.spacing_x` | panjang | `—` | Jarak antar sumbu pile arah X. Praktik umum menuntut ≥ 3× diameter; tool menolak pile yang **tumpang tindih**, tetapi kecukupan jarak terhadap standar tetap keputusan Anda. |
| `pile.spacing_y` | panjang | `—` | Jarak arah Y. Boleh berbeda dari X. |
| `pile.grid_origin` | panjang | `—` | Titik pusat susunan pile; grid dibangun simetris terhadapnya. |
| `pile.modeling` | – | `pressure` | `pressure` (disarankan) menyebar `Pz` merata pada seluruh lingkaran — mendekati kenyataan, momen halus. `nodal` menaruhnya sebagai gaya titik di node yang sama; total identik, momen di kepala tiang lebih runcing. Keduanya lulus VC-0. |

Seluruh blok `n_col`/`n_row`/`spacing_*`/`grid_origin` **diabaikan** bila ada CSV koordinat
pile — untuk susunan tidak teratur, pakai CSV.

### `pier` — kolom/pilar

Pier menjadi **tumpuan**: seluruh node di dalam daerahnya dijepit penuh 6 DOF.

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `pier.shape` | – | `—` | `rectangular` (minta lebar X & Y) atau `circular` (minta satu diameter). Menentukan letak muka pier tempat momen desain dibaca. |
| `pier.width_x` | panjang | `—` ᵃ | Ukuran searah X. **Harus ukuran sebenarnya**, bukan pembulatan ke atas: makin lebar, makin luas daerah jepit dan makin kecil momen di mukanya. |
| `pier.width_y` | panjang | `—` ᵃ | Ukuran searah Y. |
| `pier.diameter` | panjang | `—` ᵇ | Diameter pier bulat. |
| `pier.centerline` | panjang | `—` | Koordinat sumbu pier. Untuk **lebih dari satu pier**, pakai CSV poligon pier. |
| `pier.support` | – | `fixed` | Hanya jepit penuh 6 DOF di v1.0. Tumpuan pegas belum ada dan sengaja tidak ditawarkan agar tidak ada pilihan yang tampak ada tetapi tidak berfungsi (PRD Bagian 17 item 11). |
| `pier.max_pile_overlap_fraction` | – | `null` | Lihat di bawah. |

<sub>ᵃ hanya bila `shape` = `rectangular` — ᵇ hanya bila `shape` = `circular`</sub>

#### `pier.max_pile_overlap_fraction` — mengizinkan pile menindih pier

![Tumpang tindih pile dengan pier](docs/img/tumpang-tindih-pile-pier.svg)

Kosong (bawaan) = pile **tidak boleh** menindih pier; run ditolak bila ternyata menindih.
Diisi (mis. `0.15`) = Anda mengizinkan sampai fraksi itu — paling banyak 15% luas pile
berada di dalam pier.

Bagian yang berada di dalam footprint pier **tidak melenturkan pelat**: pier dimodelkan
jepit sempurna, jadi gaya di sana tersalur langsung ke pier sebagai **aksi strut**, dan
**tool tidak menghitung kapasitasnya** — itu wajib Anda cek terpisah. Uraian lengkap
beserta batas bocoran mesh ada di
[bagiannya sendiri](#pile-yang-tumpang-tindih-dengan-pier-piermax_pile_overlap_fraction).

### `material` — beton

Pelat dimodelkan **elastis linier**: satu `E` dan satu Poisson untuk seluruh pelat. Retak,
rangkak, dan susut **tidak** dimodelkan.

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `material.fc` | tegangan | `—` | Kuat tekan silinder umur 28 hari. Dipakai kapasitas lentur & geser SNI, dan menamai material pada ekspor Midas. **TIDAK** dipakai menghitung `E`. |
| `material.E` | tegangan | `—` | Kekakuan beton. Menentukan **lendutan**, tetapi hampir tidak memengaruhi momen desain — tumpuannya statis tertentu terhadap beban yang sudah diketahui. Beton normal f'c 30: sekitar 25.000–27.000 MPa. |
| `material.E_source` | – | `—` | **Wajib, run ditolak bila kosong.** Dari mana `E` berasal — satu-satunya jejak yang membuat angka itu dapat diperiksa orang lain. Mis. `"SNI 2847:2019 Ps. 19.2.2.1 untuk wc=2400"`, `"uji lab 2026-01-15"`, atau `"0,5 Ec untuk memperhitungkan retak"`. |
| `material.poisson` | – | `—` | Lazimnya 0,15–0,20 untuk beton. Ikut menentukan seberapa besar momen satu arah membangkitkan momen arah tegak lurusnya; nyata, tetapi jauh lebih kecil daripada pengaruh tebal. |
| `material.density` | kN/m³ | `null` | Lazimnya 24. **Hanya** dipakai bila `analysis.include_self_weight` menyala. |

> Tool **tidak pernah** menghitung `E` dari `f'c`: rumusnya belum dikonfirmasi pasalnya, dan
> angka tanpa sumber dilarang (PRD Bagian 1.3 poin 2). Bila Anda ingin memperhitungkan
> penurunan kekakuan akibat retak, turunkan sendiri `E` dan tuliskan alasannya di
> `E_source`.

### `mesh` — kehalusan diskretisasi

Pelat dipotong menjadi ribuan elemen segi empat. Hubungannya **tidak linier**: memperkecil
ukuran jadi setengah membuat jumlah elemen **empat kali**.

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `mesh.size_mode` | – | `uniform` | `uniform` = satu ukuran di seluruh pelat, paling mudah diprediksi. `graded` = memperhalus hanya di sekitar pile dan/atau pier, sehingga teliti dengan elemen lebih sedikit. |
| `mesh.size_global` | panjang | `—` | Panjang sisi elemen. **Patokan: ≤ 1/6 diameter pile** — di bawah itu run ditolak (rule 7a). Terlalu besar membuat lingkaran pile tampak kotak; terlalu kecil hanya memperlama hitungan. |
| `mesh.size_local_pile` | panjang | `null` | Ukuran di daerah kepala tiang pada mode `graded`. Harus ≤ ukuran global. |
| `mesh.size_local_pier` | panjang | `null` | Ukuran di daerah pier pada mode `graded`. **Di sinilah momen desain dibaca**, jadi memperhalusnya langsung memperbaiki ketelitian angka yang Anda pakai. |
| `mesh.algorithm` | – | `11` | Algoritma gmsh. 11 = Quasi-structured Quad, bagian dari kontrak numerik tool ini. |
| `mesh.recombination_algorithm` | – | `3` | 3 = Blossom full-quad, yang memaksa hasil 100% segi empat. |
| `mesh.recombine` | – | `true` | Harus menyala: `ShellMITC4` hanya menerima segi empat 4 titik. |
| `mesh.require_all_quad` | – | `true` | **Biarkan menyala.** Mematikannya membuat run berlanjut dengan mesh yang tidak sepenuhnya dapat dianalisis — kesalahan yang tidak terlihat di gambar mana pun. |
| `mesh.element_order` | – | `1` | Hanya orde 1 yang didukung; `ShellMITC4` memang elemen 4 titik. |

Pada mode `graded`, **salah satu** dari `size_local_pile` / `size_local_pier` wajib diisi.

### `analysis` — pilihan numerik

| Field | Bawaan | Arti |
|---|---|---|
| `analysis.shell_element` | `ShellMITC4` | Elemen 4 titik MITC yang memperhitungkan **deformasi geser melintang** (pelat tebal Mindlin–Reissner). Bawaan karena pilecap umumnya tebal terhadap bentangnya. `ShellDKGQ` adalah elemen pelat **tipis** (Kirchhoff) yang mengabaikan geser melintang dan akan **meremehkan lendutan** pada pelat setebal ini; `ShellNLDKGQ` versinya dengan nonlinieritas geometri. Keduanya tidak diperlukan pada analisis elastis linier. |
| `analysis.section` | `PlateFiber` | Satu material elastis terintegrasi pada tebal penuh — yang sesuai di sini. `LayeredShell` membagi tebal jadi beberapa lapis dan baru bermanfaat bila tiap lapis bermaterial berbeda; pada satu material hasilnya sama tetapi lebih lambat. |
| `analysis.n_layers` | `10` | Jumlah lapis pada `LayeredShell` saja. Minimal 2. |
| `analysis.include_self_weight` | `false` | Menambah berat pilecap sendiri sebagai beban merata ke bawah. |

> **`include_self_weight` — hati-hati hitungan ganda.** Pada banyak alur kerja, `Pz` yang
> keluar dari analisis struktur atas **sudah** memuat berat pilecap. Centang hanya bila Anda
> yakin belum. Menyalakannya juga membuat Σ beban tidak lagi sama dengan Σ `Pz`
> (PRD Bagian 17 item 6 masih terbuka).

### `design` — umum

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `design.code` | – | kosong | **Label yang dicetak, bukan sakelar.** Mengubah teksnya tidak mengubah rumus mana pun — perhitungan selalu mengikuti SNI 2847:2019 sebagaimana diterapkan `shell-kit`. |
| `design.cover` | panjang | `—` | Tebal beton sampai sisi luar tulangan. Menentukan `d`, yang langsung menentukan kebutuhan tulangan: selimut lebih tebal → `d` lebih kecil → tulangan lebih banyak. SNI menuntut 75 mm untuk beton yang dicor langsung di atas tanah. |
| `design.fy` | tegangan | `—` | Tegangan leleh baja. Berbanding **terbalik** dengan luas tulangan — salah mengisinya langsung menggeser seluruh hasil. |
| `design.fy_source` | – | `—` | **Wajib, run ditolak bila kosong.** `shell-kit` punya `DEFAULT_FY = 420` tetapi tool ini tidak memakainya diam-diam. Mis. `"BjTS 420B, SNI 2052:2017"`. |
| `design.phi_flexure` | – | `null` | Faktor reduksi lentur. Kosong = 0,90 bawaan SNI dari `shell-kit`; asalnya tetap dicetak di calc sheet. |
| `design.phi_shear` | – | `null` | Faktor reduksi geser. Kosong = 0,75. Lebih kecil daripada `phi` lentur karena keruntuhan geser getas dan lebih sulit diprediksi. |
| `design.as_min_surface_zone` | panjang | `null` | Kosong = murni SNI 2847:2019. Diisi (mis. `300`) = mengikuti ACI 350-06 Ps. 7.12.2.1 untuk elemen tebal. **Pada pilecap tebal ini mengubah hampir seluruh hasil lentur** — lihat [bagiannya](#designas_min_surface_zone--opsional-tetapi-berdampak-besar). |

### `design` — pemilihan tulangan

Dari `As` yang dibutuhkan, tool memilih batang yang benar-benar dapat dipasang. Anda
menetapkan **satu** hal, tool menghitung sisanya.

![Dua mode pemilihan tulangan](docs/img/mode-tulangan.svg)

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `design.rebar_basis` | – | `element` | **Dari mana angka desain diambil** — lihat [Metode desain tulangan](#metode-desain-tulangan--per-elemen-atau-per-lajur). |
| `design.rebar_mode` | – | `—` | `spacing_fixed` = Anda tetapkan spasi, tool pilih diameter. `diameter_fixed` = Anda tetapkan batang, tool hitung spasi. |
| `design.rebar_spacing` | panjang | `—` ᶜ | Jarak antar batang. Tool memilih diameter terkecil dari daftar standar yang masih memenuhi `As`. 150–200 mm lazim untuk pilecap. |
| `design.rebar_config` | – | `—` ᵈ | Susunan batang, dibaca `<jumlah>D<diameter>`: `"2D25"` = dua batang D25 per titik pemasangan. Daftarnya datang langsung dari `shell-kit`. |
| `design.rebar_select_codes` | – | `null` | Batasi pilihan ke kode tertentu, mis. bila di lapangan hanya tersedia D22 dan D25. Bila diisi, plot tulangan menjadi **kategorikal** berlabel kode. |
| `design.strips_x` | – | `5` ᵉ | Lihat di bawah. |
| `design.strips_y` | – | `5` ᵉ | Lihat di bawah. |
| `design.moment_at` | – | `pier_face` ᵉ | Lihat di bawah. |

<sub>ᶜ hanya pada `spacing_fixed` — ᵈ hanya pada `diameter_fixed` —
ᵉ **hanya dibaca pada `rebar_basis: "strip"`**; pada mode `element` ketiganya diabaikan
dan tool memberi peringatan bila terisi</sub>

`rebar_mode` dan `rebar_basis` adalah **sumbu yang berbeda** dan mudah tertukar:
`rebar_basis` menentukan **dari mana `As` berasal**, `rebar_mode` menentukan **batang apa
yang dipasang** untuk memenuhi `As` itu. Keduanya berlaku bersamaan.

#### Metode desain tulangan — per elemen atau per lajur

`design.rebar_basis` menentukan **dari mana angka desain diambil**. Berlaku untuk
**seluruh kombinasi sekaligus, termasuk envelope** — satu setelan, bukan per kombinasi.

> **Hanya tulangan LENTUR.** Sengkang tidak terpengaruh setelan ini. Geser satu arah
> selalu disajikan dalam dua bentuk sekaligus: cek penampang kritis pada `d` dari muka
> pier (dasar penerimaan, karena bidang runtuh geser memotong seluruh lebar) dan peta
> `Av/s` per elemen yang dihitung dengan fungsi desain `shell-kit` yang sama seperti `As`
> (berguna menentukan zona pemasangan). Lihat calc sheet bagian 7 dan 7b.

![Dua mode desain tulangan](docs/img/mode-desain-tulangan.svg)

Sumbernya **sama**: momen `m_x`/`m_y` tiap elemen shell. Yang berbeda hanya operasinya.
Keduanya memakai penampang selebar **1 m** dan rumus SNI yang sama lewat `shell-kit` —
tidak satu pun rumus ditulis ulang di sini.

| | `element` (bawaan) | `strip` |
|---|---|---|
| `As` diambil dari | momen tiap elemen apa adanya | rata-rata berbobot momen sepanjang potongan di muka pier |
| Setara dengan | algoritma asli `shell-kit` | metode klasik pilecap (penampang kritis) |
| Deliverable utama | **kontur** `As` & diameter | **tabel** per lajur |
| Pembagian zona penulangan | **Anda**, saat mendetail dari kontur | **tool**, lewat `strips_x`/`strips_y` |
| Konvergen terhadap mesh? | **tidak** di tepi pier | ya |
| Dapat dicek tangan? | tidak | ya (`ΣPz × lengan`) |

**Angka nyata dari `ex01`**, muka pier arah X — model yang sama, dua metode:

| | `As` |
|---|---:|
| `element` — puncak | **1.541 mm²/m** di (−659, −547), yaitu **tepat di sudut pier** |
| `strip` — lajur tengah dari 5 lajur | **1.330 mm²/m** |
| `strip` — bila hanya 1 lajur | 1.080 mm²/m (`As_min` yang menahan) |

##### Yang perlu Anda ketahui tentang `element`

Nilai puncak di tepi zona jepit pier adalah **singularitas numerik**: ia membesar terus
setiap kali mesh diperhalus dan **tidak pernah konvergen**. Terukur pada model pilecap
15,9 m: puncak `m_x` naik ~16% ketika `size_global` 300 → 150 mm.

Arah galatnya **konservatif** — tulangan bertambah, bukan berkurang — sehingga tidak
berbahaya seperti galat yang meremehkan. Tetapi artinya:

- Angka desain Anda **bergantung pada `mesh.size_global` yang Anda pilih**. Karena itu
  ukuran mesh ikut tercetak di calc sheet bersama angkanya.
- **Periksa kolom lokasi** di tabel ringkasan. Puncak yang jatuh di sudut pier adalah
  artefak tumpuan; puncak di tempat lain adalah kebutuhan nyata. Keduanya terlihat sama
  bila hanya angkanya yang dibaca.

##### Yang perlu Anda ketahui tentang `strip`

Hasilnya bergantung `strips_x`/`strips_y` — angka yang **tidak diwajibkan pasal mana pun**,
sehingga dua engineer dengan model identik bisa mendapat `As` berbeda. Momen di muka pier
jauh dari merata: pada `ex01` lajur tengah memikul 3,8× lajur tepi, sehingga lajur yang
terlalu lebar **mengencerkan puncaknya** — un-konservatif tepat di lokasi paling kritis.

Patokan yang lebih masuk akal daripada "5 lajur": tetapkan dari **lebar lajur**, sekitar
1–1,5 m. Untuk cap 15,9 m itu berarti `strips_x` sekitar 11–16, bukan 5. Tetapi jangan
terlalu banyak juga — lajur yang lebih sempit daripada beberapa elemen akan memasukkan
kembali singularitas yang hendak dihindari.

##### Memilih

Mulailah dengan bawaan `element` bila Anda terbiasa dengan alur `shell-kit`: baca kontur,
tentukan sendiri bandnya. Beralihlah ke `strip` bila Anda butuh angka yang konvergen,
dapat dicek tangan, dan mengikuti metode penampang kritis yang lazim untuk pilecap.

Apa pun pilihannya, **basis yang dipakai selalu tercetak** di `calc_sheet.md` dan
`SUMMARY.md` — tidak ada berkas hasil yang beredar tanpa menyatakan metodenya.

##### Contoh nyata (`ex02`): peta yang sama, tafsir yang berbeda

Berikut `contour_diameter_x_bawah.png` yang benar-benar dihasilkan dari `ex02`
(spasi dikunci 100 mm), satu kombinasi (`1.2D+1.6L`), dijalankan dua kali — hanya
`design.rebar_basis` yang diubah:

![Perbandingan kontur diameter tulangan, rebar_basis element vs strip](docs/img/contoh-diameter-element-vs-strip.png)

Petanya **identik piksel demi piksel** — wajar, karena `designs` (dan karenanya
`contour_As_*`/`contour_diameter_*`) selalu dihitung dari medan momen per elemen apa
adanya, terlepas dari `rebar_basis`. Yang berbeda **hanya** baris CATATAN di kop gambar:
kiri menyatakan gambar inilah sumber angka desain, kanan menyatakan gambar ini cuma peta
orientasi dan angka resminya ada di `strip_moments_*.csv`/calc sheet bagian 6. Baca
`rebar_basis` di kop sebelum menafsirkan gambar mana pun dari alat ini — gambarnya sendiri
tidak cukup untuk membedakan.

#### Lajur momen: `strips_x`, `strips_y`, dan `moment_at`

> Ketiganya **hanya berlaku pada `rebar_basis: "strip"`**. Pada mode `element` ketiganya
> tidak dibaca sama sekali, dan tool memberi peringatan bila terisi.

![Lajur momen desain](docs/img/lajur-momen.svg)

Kedua field ini **bukan** soal orientasi lajur di ruang, melainkan **momen mana** yang
dihitung di sana:

* **`strips_x`** → jumlah lajur untuk `m_xx`, yang menentukan **tulangan arah X**.
  Potongannya di kedua **muka pier arah X**; tinggi pilecap (arah Y) dibagi jadi `strips_x`
  pita, tiap pita menghasilkan **satu** momen desain.
* **`strips_y`** → simetris: `m_yy` → **tulangan arah Y**, potongan di muka pier arah Y,
  lebar pilecap (arah X) yang dibagi.

Pada `ex01` dengan 5 lajur × 2 sisi × 2 arah hasilnya **20 baris** — persis isi tabel
`calc_sheet.md` bagian 7a dan `strip_moments_*.csv`.

**Ke mana efeknya sampai.** `As` muncul di dua tempat, dan **peran keduanya bertukar
mengikuti `rebar_basis`** — inilah yang paling mudah salah dibaca:

| Keluaran | `rebar_basis: "element"` (bawaan) | `rebar_basis: "strip"` |
|---|---|---|
| `rebar_design.csv`, `contour_As_*.png` | **Inilah `As` yang dipakai** — dan `strips_x/y` tidak berpengaruh apa pun | Peta **orientasi** sebaran; bukan angka desain |
| `strip_moments_*.csv`, calc sheet bagian 6 | **tidak dihasilkan** | dihasilkan; dipengaruhi `strips_x/y` |
| calc sheet bagian 7a "Angka desain" | maksimum per arah×muka **beserta lokasinya** | satu baris per lajur |

Jadi `strips_x`/`strips_y` hanya berpengaruh pada mode `strip`. Pada mode `element` keduanya
tidak dibaca sama sekali, dan tool memperingatkan bila terisi.

Dalam mode `strip`: lebih banyak lajur = penulangan lebih mengikuti sebaran momen, tetapi
gambar kerja lebih rumit. Lebih sedikit = lebih sederhana, tetapi tiap lajur merata-ratakan
muka yang lebih panjang sehingga puncak lokal bisa teredam. **5 lajur per arah lazim** untuk
cap berukuran `ex01`; untuk cap lebar, tetapkan dari lebar lajur (~1–1,5 m) alih-alih dari
jumlahnya.

`moment_at` menentukan **di titik mana** momen dibaca:

| Nilai | Arti |
|---|---|
| `pier_face` (bawaan) | Di muka pier, sesuai praktik SNI. **Satu-satunya yang sah dipakai desain.** |
| `peak` | Nilai terbesar di mana pun — pada model pelat selalu jatuh **tepat di tepi zona jepit**. **Singularitas numerik:** angkanya membesar terus setiap kali mesh diperhalus, jadi tidak pernah konvergen. Tool tetap menghitungnya dan menandainya `SINGULAR`, tetapi tanda itu bukan pengganti keputusan Anda. |
| `both` | Mencetak keduanya berdampingan untuk perbandingan; baris `pier_face` tetap yang dipakai. |

### `design` — sengkang

Sengkang adalah tulangan **vertikal** yang menembus tebal pilecap untuk menahan geser,
dipasang sebagai kisi dengan dua spasi. **Keduanya bersama** menentukan luas yang dipikul
satu kaki sengkang, sehingga keduanya wajib.

| Field | Satuan | Bawaan | Arti |
|---|---|---|---|
| `design.stirrup_spacing_long` | panjang | `—` | Jarak antar sengkang searah X. |
| `design.stirrup_spacing_trans` | panjang | `—` | Jarak antar sengkang searah Y. Luas tributari satu kaki = hasil kali kedua spasi. |
| `design.stirrup_select_diameters` | – | `null` | Batasi ke diameter yang tersedia di lapangan. Kosong = daftar bawaan `shell-kit` (D10–D25). Daerah yang butuh lebih besar daripada diameter terbesar yang diizinkan ditandai **TIDAK MEMADAI** di plot, bukan dibulatkan diam-diam. |

Pada banyak pilecap tebal, geser terpenuhi oleh beton saja dan tool melaporkan "tanpa
sengkang" di sebagian besar luasan — **itu hasil yang sah**, bukan kegagalan hitungan.

### Kapan config diabaikan — override CSV

Bila berkas CSV geometri terdeteksi di folder input, **blok JSON terkait diabaikan
seluruhnya**:

| CSV di folder input | Yang diabaikan dari JSON |
|---|---|
| `*pilecap*polygon*.csv` | `pilecap.length_x`, `length_y`, `origin` (tebal **tetap** dari JSON) |
| `*pile*coord*.csv` | `pile.n_col`, `n_row`, `spacing_x`, `spacing_y`, `grid_origin` |
| `*pier*polygon*.csv` | `pier.shape`, `width_x`, `width_y`, `diameter`, `centerline` |

Setiap override diteriakkan sebagai **WARNING 5 baris** di log, dicatat di
`run_manifest.json`, dan muncul sebagai baris PERINGATAN berwarna di kop setiap gambar —
tidak pernah diam-diam. Pakai `--no-custom` untuk memaksa memakai parameter JSON.

### Ringkasan — wajib, opsional, dan bawaan

**Sembilan field ini opsional** (`null` = fitur mati):

`pier.max_pile_overlap_fraction` · `material.density` · `mesh.size_local_pile` ·
`mesh.size_local_pier` · `design.phi_flexure` · `design.phi_shear` ·
`design.as_min_surface_zone` · `design.rebar_select_codes` ·
`design.stirrup_select_diameters`

**Punya bawaan** — boleh dihilangkan, tetapi tetap menentukan hasil: seluruh blok
`project`, `units`, dan `analysis`; seluruh blok `mesh` **kecuali** `size_global`;
`pile.modeling`, `pier.support`, `design.code`, `design.strips_x`, `design.strips_y`,
`design.moment_at`.

**Sisanya wajib** — run **ditolak** bila tidak ada:

| Blok | Field wajib |
|---|---|
| `pilecap` | `thickness`, `length_x`, `length_y`, `origin` |
| `pile` | `diameter`, `n_col`, `n_row`, `spacing_x`, `spacing_y`, `grid_origin` |
| `pier` | `shape`, `centerline`, dan `width_x`+`width_y` **atau** `diameter` |
| `material` | `fc`, `E`, `E_source`, `poisson` |
| `mesh` | `size_global` |
| `design` | `cover`, `fy`, `fy_source`, `rebar_mode`, `rebar_spacing`/`rebar_config`, `stirrup_spacing_long`, `stirrup_spacing_trans` |

Empat di antaranya paling sering terlewat karena tidak punya bawaan yang masuk akal:
`material.E`, `material.E_source`, `design.fy`, `design.fy_source` — lihat
[Nilai yang WAJIB Anda tetapkan sendiri](#nilai-yang-wajib-anda-tetapkan-sendiri).

> Penjelasan di bagian ini dan tooltip di `pilecap-ui`/`pilecap-gui` berasal dari daftar
> field yang sama
> (`src/pilecap_fem/ui/schema.py`). Test `test_readme_mendokumentasikan_setiap_field`
> menggagalkan suite bila ada field baru yang belum masuk ke sini — supaya keduanya tidak
> menyimpang diam-diam.

---

## Contoh

| Folder | Isi |
|--------|-----|
| `examples/ex01_standard_4pile/` | Pilecap persegi 4 pile, pier persegi — kasus paling umum |
| `examples/ex02_standard_12pile/` | Grid 4×3, pier lingkaran |
| `examples/ex03_custom_polygon/` | Pilecap poligon L, pile custom non-grid, **dua** pier poligon. Sekaligus acuan format ketiga CSV geometri. |
| `examples/ex04_pile_overlap_pier/` | Dua dari enam pile **menindih pier** (`f` = 7,2%). Contoh satu-satunya yang memakai `pier.max_pile_overlap_fraction`. |

Jalankan `ex03` untuk melihat mekanisme **override geometri**: setiap entitas yang datang
dari CSV diteriakkan sebagai WARNING 5 baris, dicatat di `run_manifest.json`, dan muncul
sebagai baris PERINGATAN berwarna di kop setiap gambar.

Jalankan `ex04` untuk melihat penanganan **pile yang tumpang tindih dengan pier** — lihat
bagian berikutnya.

## Pile yang tumpang tindih dengan pier (`pier.max_pile_overlap_fraction`)

Bawaannya tool **menolak** geometri yang pile-nya menyentuh atau menindih pier. Sejak
v0.9.0 tumpang tindih **berluas** dapat diizinkan dengan mengisi
`pier.max_pile_overlap_fraction` (nirdimensi, `null` = menolak seperti sebelumnya).

Yang terjadi bila diizinkan: seluruh cakram pile tetap dibebani `p = Pz / A_pile`, tetapi
pier dimodelkan **jepit sempurna**, sehingga bagian beban yang jatuh di dalam footprint
pier langsung masuk ke reaksi dan **tidak melenturkan pelat**. Laporan memisahkan dua
komponen yang sifatnya berbeda:

| Komponen | Asal | Bergantung mesh? |
|----------|------|------------------|
| `pz_strut` = `f × Pz` | **Geometri** — bagian cakram di dalam footprint pier (aksi strut) | tidak |
| `pz_bocor_mesh` | **Diskretisasi** — elemen di muka pier yang sebagian bebannya mendarat di node jepit | ya, orde `h` |

Keduanya tampil terpisah di `equilibrium_check.json` dan `calc_sheet.md` bagian 3a. Yang
digabung menjadi satu angka akan menyamar sebagai parameter geometri padahal separuhnya
parameter meshing.

**Bocoran mesh dibatasi, bukan sekadar dilaporkan — karena arahnya tidak aman.** Beban yang
mendarat di node jepit tidak melenturkan pelat, sehingga momen dan tulangan yang dihitung
ikut mengecil: mesh yang lebih kasar menghasilkan desain yang lebih ringan. Sejak v0.9.1
besarnya diukur dan dibatasi:

| Bocoran | Yang terjadi |
|---------|--------------|
| ≤ 2% | jalan tanpa komentar |
| 2–5% | jalan, tetapi **peringatan** menyebut angkanya dan ukuran elemen yang dibutuhkan |
| > 5% | **run ditolak** |

Pemeriksaannya terjadi sudah di `pilecap-mesh`, sebelum satu pun kombinasi dibaca — fraksi
bocoran tidak bergantung besar `Pz`, jadi tidak perlu menunggu analisis. Kedua batas
diturunkan dari pengukuran (tabel di komentar `config.OVERLAP_LEAK_WARN`), bukan tebakan.

Yang menentukan besarnya bukan luas irisan melainkan **bentuknya**: pile yang menindih
**sudut** pier punya chord lebih panjang, sehingga bocor sampai 2,3× lebih besar daripada
yang menindih satu **muka** pada kehalusan mesh yang sama. Karena itu rasio `D/h` tidak
dipakai sebagai penduga.

**Yang perlu Anda putuskan sendiri:** tool **tidak menghitung kapasitas strut**. Bagian
`pz_strut` wajib dicek terpisah sebagai tumpu/strut. Mengisi
`pier.max_pile_overlap_fraction` adalah pernyataan bahwa Anda menerima itu — nilainya
tercatat di `run_manifest.json` sebagai keputusan Anda, dan peringatannya muncul di log,
manifest, `SUMMARY.md`, calc sheet, serta **kop setiap gambar**.

**Pile yang seluruhnya berada di bawah pier** — misalnya pile tengah grup 3×3 tepat di
bawah kolom — diizinkan dengan `pier.max_pile_overlap_fraction = 1.0` (sejak v0.13.2;
sebelumnya konfigurasi ini tidak dapat dijalankan dengan nilai berapa pun). Ia adalah batas
yang sah dari model di atas, bukan kasus terpisah: seluruh cakram menjadi lensa, **100%
`Pz`-nya tercatat sebagai `pz_strut`** dan tersalur langsung ke pier, sementara pelat tidak
menerima lentur sedikit pun dari pile itu. Neraca VC-0 tetap utuh. Dua konsekuensi yang
wajib Anda baca:

- **Seluruh beban pile itu berada di luar pemeriksaan tool.** Kapasitas tumpu dan strutnya
  — sering pile dengan beban terbesar, karena berada tepat di bawah kolom — sepenuhnya
  tanggung jawab engineer.
- **`a/d` minimum tercetak 0,000** pada pile itu: ia memang tidak punya bentang geser. Rasio
  itu disajikan tanpa vonis, sama seperti rasio lainnya.

**Pile yang hanya bersinggungan** dengan muka pier (luas irisan tepat nol) **selalu
ditolak**, dengan atau tanpa opsi ini: di sana tidak ada lensa untuk diukur, sehingga
seluruh beban yang terserap adalah artefak diskretisasi murni tanpa satu pun komponen
geometri yang dapat dilaporkan. Geser pile-nya sedikit sehingga menjadi tumpang tindih
yang terukur, atau celah yang jelas.

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

Sejak v0.8.0 `VC-6` berjalan sebagai **release gate**: setiap contoh bawaan dimodelkan
ulang di Midas Civil — diimpor dari `model.mct` yang ditulis tool ini sendiri, sehingga
penomoran node & elemennya identik 1:1 — lalu hasilnya dibandingkan elemen demi elemen.
Sejak v0.9.0 cakupannya **keempat** contoh, termasuk `ex04` yang pile-nya menindih pier.

Kesesuaian yang terukur (RMS terhadap nilai puncak, 4 contoh × 2 kombinasi):

| Besaran | RMS terburuk | Korelasi minimum |
|---------|-------------:|-----------------:|
| Momen `m_xx`, `m_yy`, `m_xy` | 0,144% | 0,99991 |
| Geser `q_x`, `q_y` | 0,265% | 0,99993 |
| Lendutan per node `uz` | 0,258% | 0,999971 |
| Reaksi tumpuan `Rz` | 0,539% | 0,999596 |
| Momen **puncak** (penentu tulangan) | 0,515% | — |

### Selisihnya per elemen, bukan hanya angka ringkasnya

Satu angka RMS dapat menyembunyikan banyak hal, jadi selisih tiap elemen disajikan apa
adanya. Gambar dihasilkan `tools/plot_vc6_perbandingan.py`, yang memakai ulang pembaca
Midas dan rekonsiliasi tanda **yang sama persis** dengan gate VC-6 — bukan jalur kedua yang
bisa menyimpang diam-diam.

![Selisih per elemen terhadap Midas Civil](docs/img/vc6-sebaran-m_xx-1_2D_1_6L.png)

Panel kiri: selisih tiap elemen terhadap besar nilainya. Yang penting bukan sempitnya
sebaran, melainkan bahwa titiknya **terpusat di garis nol tanpa kemiringan** — kekeliruan
sistematis akan menarik titik ke satu sisi seiring membesarnya nilai. Panel kanan membaca
sebaran yang sama secara kumulatif: **separuh elemen menyimpang < 0,03%**, 99% < 1%.

Yang belum dijawab angka ringkas: **di mana** selisih terbesar berada. Peta berikut
menunjukkannya untuk keempat contoh sekaligus, satu panel masing-masing:

![Letak selisih per elemen](docs/img/vc6-peta-m_xx-1_2D_1_6L.png)

Simpangan terbesar berkumpul persis di **tepi cakram pile** — tempat beban tekanan berhenti
mendadak — dan di sekitar pier. Di situlah ShellMITC4 dan QUAD4 hibrida Midas memang paling
sah berbeda. Di seluruh bidang pelat lainnya, tempat angka desain sebenarnya diambil,
selisihnya nyaris tidak terlihat.

> Letak elemen terburuk **diukur, bukan diperkirakan**: labelnya diturunkan dari
> `geometry.json`, dan pada keempat contoh ia jatuh di tepi cakram **pile**, bukan pier.
> Sampai v0.12.0 docstring VC-6 keliru menyebutnya "singularitas tepi pier" — kekeliruan
> yang justru terungkap karena label itu berhenti diketik tangan.

`ex04` menguji apa yang tidak disentuh tiga lainnya — **jalur tumpang tindih pile–pier**.
Yang terbukti di sana, masing-masing terhadap implementasi independen: himpunan node jepit
Midas **sama persis** dengan milik tool ini (479 node, termasuk node lensa — nol selisih di
kedua arah), `Σ FZ` cocok dengan `Σ Pz` sampai ~9 angka berarti meski sebagian tekanan
bekerja pada elemen lensa, dan resultan per elemennya tetap cocok pada RMS ≤ 0,134%.

Tiga hal yang perlu dibaca jujur:

- **Konvensi tanda geser Midas berlawanan** dengan konvensi tool ini, dan itu
  direkonsiliasi secara eksplisit — bukan disembunyikan. Buktinya seragam: tidak ada satu
  pun dari ~5.500 elemen yang menyimpang.
- **Jalur lendutan adalah yang terlemah**, karena ekspor Midas hanya 6 desimal dalam meter
  (resolusi 1 µm). Pada pilecap kaku itu besar: ex01 0,44%, ex03 0,052%, **ex04 0,91%** dari
  skala — seluruhnya lebih besar daripada selisih terukur, sehingga yang terbukti hanyalah
  "tidak berbeda sejauh yang dapat diukur". Hanya ex02 yang bebas dari batasan ini. Yang
  membuktikan ketelitian adalah jalur resultan elemen dan reaksi.
  Di tempat pembulatan tidak mendominasi, terlihat pula **bias kecil yang sistematis**:
  Midas melendut 0,08% (ex02) dan 0,15% (ex03) lebih besar, sebanding dengan lendutannya.
  Pembulatan material saat ekspor sudah disingkirkan sebagai penyebab (keempat contoh
  memakai E dan ν yang sama, biasnya berbeda); **penyebab sebenarnya belum
  teridentifikasi**. Ia tidak muncul pada momen karena pada analisis linier perbedaan
  kekakuan tidak mengubah gaya yang ditentukan keseimbangan — lihat
  `tests/data/vc6/SUMBER.md` Bagian 5.3.
- **Kesesuaian ex04 tidak membuktikan bahwa idealisasi jepit-sempurna itu benar.** Kedua
  program memakai idealisasi yang sama, jadi perbandingannya tidak dapat menilai asumsinya.
  Kapasitas strut tetap wajib dicek terpisah.

Sebagai efek samping, `Σ FZ` reaksi Midas sama dengan `Σ Pz` masukan sampai ~9 angka
berarti — ini memvalidasi **ekspor `model.mct`** secara end-to-end, satu-satunya cek yang
menyentuh sisi Midas yang sesungguhnya. Rincian lengkap: `tests/data/vc6/SUMBER.md`.


#### Seluruh gaya dalam, kedua kombinasi beban

Kedua gambar di atas menyajikan `m_xx` pada kombinasi gravitasi. Set lengkapnya —
**5 gaya dan lendutan × 2 kombinasi × 4 contoh** — ada di bawah ini, dikelompokkan per besaran.
Seluruhnya dihasilkan `tools/plot_vc6_perbandingan.py` dari data yang sama dengan gate
VC-6, dan angkanya tersedia sebagai tabel di **Lampiran C panduan**.

<details>
<summary><b>Momen lentur arah X</b> — <code>m_xx</code></summary>

**Kombinasi 1.2D+1.6L**

![Sebaran selisih m_xx, 1.2D+1.6L](docs/img/vc6-sebaran-m_xx-1_2D_1_6L.png)

![Letak selisih m_xx, 1.2D+1.6L](docs/img/vc6-peta-m_xx-1_2D_1_6L.png)

**Kombinasi 1.2D+1.0W**

![Sebaran selisih m_xx, 1.2D+1.0W](docs/img/vc6-sebaran-m_xx-1_2D_1_0W.png)

![Letak selisih m_xx, 1.2D+1.0W](docs/img/vc6-peta-m_xx-1_2D_1_0W.png)

</details>

<details>
<summary><b>Momen lentur arah Y</b> — <code>m_yy</code></summary>

**Kombinasi 1.2D+1.6L**

![Sebaran selisih m_yy, 1.2D+1.6L](docs/img/vc6-sebaran-m_yy-1_2D_1_6L.png)

![Letak selisih m_yy, 1.2D+1.6L](docs/img/vc6-peta-m_yy-1_2D_1_6L.png)

**Kombinasi 1.2D+1.0W**

![Sebaran selisih m_yy, 1.2D+1.0W](docs/img/vc6-sebaran-m_yy-1_2D_1_0W.png)

![Letak selisih m_yy, 1.2D+1.0W](docs/img/vc6-peta-m_yy-1_2D_1_0W.png)

</details>

<details>
<summary><b>Momen puntir</b> — <code>m_xy</code></summary>

**Kombinasi 1.2D+1.6L**

![Sebaran selisih m_xy, 1.2D+1.6L](docs/img/vc6-sebaran-m_xy-1_2D_1_6L.png)

![Letak selisih m_xy, 1.2D+1.6L](docs/img/vc6-peta-m_xy-1_2D_1_6L.png)

**Kombinasi 1.2D+1.0W**

![Sebaran selisih m_xy, 1.2D+1.0W](docs/img/vc6-sebaran-m_xy-1_2D_1_0W.png)

![Letak selisih m_xy, 1.2D+1.0W](docs/img/vc6-peta-m_xy-1_2D_1_0W.png)

</details>

<details>
<summary><b>Geser melintang arah X</b> — <code>q_x</code></summary>

**Kombinasi 1.2D+1.6L**

![Sebaran selisih q_x, 1.2D+1.6L](docs/img/vc6-sebaran-q_x-1_2D_1_6L.png)

![Letak selisih q_x, 1.2D+1.6L](docs/img/vc6-peta-q_x-1_2D_1_6L.png)

**Kombinasi 1.2D+1.0W**

![Sebaran selisih q_x, 1.2D+1.0W](docs/img/vc6-sebaran-q_x-1_2D_1_0W.png)

![Letak selisih q_x, 1.2D+1.0W](docs/img/vc6-peta-q_x-1_2D_1_0W.png)

</details>

<details>
<summary><b>Geser melintang arah Y</b> — <code>q_y</code></summary>

**Kombinasi 1.2D+1.6L**

![Sebaran selisih q_y, 1.2D+1.6L](docs/img/vc6-sebaran-q_y-1_2D_1_6L.png)

![Letak selisih q_y, 1.2D+1.6L](docs/img/vc6-peta-q_y-1_2D_1_6L.png)

**Kombinasi 1.2D+1.0W**

![Sebaran selisih q_y, 1.2D+1.0W](docs/img/vc6-sebaran-q_y-1_2D_1_0W.png)

![Letak selisih q_y, 1.2D+1.0W](docs/img/vc6-peta-q_y-1_2D_1_0W.png)

</details>
<details>
<summary><b>Lendutan vertikal</b> — <code>uz</code> per node</summary>

Dibaca berbeda dari gaya dalam. Selisih dinyatakan dalam **µm**, karena batas
ketelitiannya absolut: ekspor Midas membulatkan ke 1 µm, sehingga selisih di bawah
0,5 µm (pita abu-abu) tidak dapat dibedakan dari nol. Peta memakai skala warna
**bersama** — skala per panel akan membesarkan derau pembulatan ex04 menjadi pola yang
tampak seperti ketidakcocokan. Kemiringan titik ex02/ex03 pada panel kiri adalah bias
sistematis yang diuraikan di atas, bukan derau.

**Kombinasi 1.2D+1.6L**

![Sebaran selisih uz, 1.2D+1.6L](docs/img/vc6-sebaran-uz-1_2D_1_6L.png)

![Letak selisih uz, 1.2D+1.6L](docs/img/vc6-peta-uz-1_2D_1_6L.png)

**Kombinasi 1.2D+1.0W**

![Sebaran selisih uz, 1.2D+1.0W](docs/img/vc6-sebaran-uz-1_2D_1_0W.png)

![Letak selisih uz, 1.2D+1.0W](docs/img/vc6-peta-uz-1_2D_1_0W.png)

</details>

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

Diukur ulang pada 8 run (v0.9.0): ex02 **0,0069%**, ex04 **0,0001%**. Contoh yang pile-nya
menindih pier ternyata **lebih stabil**, bukan kurang — pada ukuran elemen yang tetap,
jumlah node yang jatuh di muka pier praktis tidak berubah antar run. Yang memang menggeser
angka desainnya pada geometri seperti itu adalah **ukuran elemen yang Anda pilih**, bukan
pengulangan run; lihat bagian tumpang tindih pile–pier di atas.
