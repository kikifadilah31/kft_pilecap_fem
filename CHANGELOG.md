# Changelog

Format mengikuti template PRD Bagian 16C.

## [0.7.0] — 2026-08-09 — Ekspor Midas MCT, plot sengkang kategorikal, tiga peningkatan UI

Lima temuan dari pemakaian v0.6.0. Dua menyangkut seluruh tool, tiga menyangkut antarmuka.

### Added

- **Ekspor Midas Civil `00_Model/model.mct`** — model teks siap impor, **lengkap dengan
  pembebanan**: node, elemen PLATE (`iSUB=1`, thick plate/Mindlin, setara `ShellMITC4`),
  grup yang sama dengan `elements.csv`, material, tebal, tumpuan jepit pier, satu
  `*STLDCASE` per kombinasi, dan `*LOADCOMB` envelope. `pilecap-mesh` menulis versi tanpa
  beban; `pilecap-analyze`/`pilecap-run` menulis ulang versi lengkapnya.
- Sub-paket `src/pilecap_fem/exporters/` sebagai jalan masuk format teks berikutnya
  (mis. SAP2000). Aturannya tertulis di `__init__.py`: exporter **hanya menerjemahkan**,
  tidak pernah menghitung ulang besaran rekayasa.
- `fem_engine.pile_pressures()` — sumber **tunggal** tekanan pile `p = Pz / A_disk`,
  dipakai bersama oleh strategi beban OpenSees dan penulis `*PRESSURE`.
- **UI: pratinjau geometri.** Tombol **Perbarui pratinjau** menggambar denah pilecap/pile/
  pier sebelum run, lewat `renderer.render_geometry_plan()` yang mengembalikan `Figure`.
  Tidak menyentuh gmsh maupun OpenSees, dan menghormati override CSV.
- **UI: memuat `pilecap_config.json` yang sudah ada** (`schema.values_from_config`). Kunci
  yang tidak dikenal formulir **dilaporkan**, tidak dibuang diam-diam.
- **UI: penjelasan pada setiap field.** 58 field skema, 11 bagian, dan 9 widget opsi run
  yang ditulis langsung di `app.py` — seluruhnya. Dijaga empat test agar cakupannya tidak
  surut saat field baru ditambahkan.
- `docs/CATATAN_SHELL_KIT.md` — vonis beserta buktinya bahwa cacat plot sengkang **bukan**
  dari `shell-kit`, plus satu wart: `config.REBAR_CMAP` di sana adalah kode mati.
- `tests/test_exporters.py` (16 test) dan `tests/test_ui_app.py` (4 test lewat
  `streamlit.testing.v1.AppTest`, di-skip bila extra `ui` tidak terpasang). `test_ui.py`
  tetap sepenuhnya bebas streamlit.

### Fixed

- **Kontur diameter sengkang digambar sebagai gradasi mulus**, tidak bertingkat seperti
  kontur diameter lentur. Nilainya memang diskret di sumbernya — `shell-kit` mengembalikan
  `0`, anggota persis `SHEAR_DIAMETERS`, atau `NaN` — tetapi `ShearRebarMap` adalah
  satu-satunya objek hasil tulangan tanpa `labels`/`is_categorical`, sehingga pemilih plot
  tidak punya apa pun untuk dicabangkan dan nilainya jatuh ke `render_contour` dengan
  colormap kontinu. Colorbarnya pun berlabel angka interpolasi alih-alih `D10`…`D25`.
  Sekarang `ShearRebarMap` membawa `available_diameters` dan plotnya kategorikal.
- Docstring `renderer._triangulation` mengklaim urutan simpul quad "sudah dijamin CCW oleh
  `mesh_model`". **Klaim itu tidak benar** — `_quad_areas_and_centroids` justru sengaja
  memakai `np.abs(signed)` agar tidak bergantung pada orientasi gmsh. Test yang lulus hanya
  membuktikan gmsh kebetulan menghasilkan CCW pada contoh yang diuji. Docstring diperbaiki,
  dan konsekuensinya dipakai: ekspor MCT memilih arah `GZ`, bukan `LZ`.
- `help` pada field `pair` hanya menempel di kotak `x`, tidak di `y`.

### Changed

- `PreparedModel` kini membawa `material` dan `fc`. Pada `pilecap-mesh` keduanya boleh
  `None` — perintah itu memang tidak mewajibkan `material.E` — dan MCT yang dihasilkan
  **menyatakan** ketiadaan blok `*MATERIAL` alih-alih mengarang nilai `E`.

### Yang belum dapat diverifikasi

Bagian `*CONSTRAINT` dan varian user-defined `*MATERIAL` **tidak ada** di berkas rujukan
`ref/PILECAP_P32N.mct`, sehingga sintaksnya ditulis menurut konvensi MCT. Statusnya
dinyatakan di header setiap berkas yang dihasilkan agar diperiksa pada impor pertama —
satu-satunya cara memastikannya adalah mengimpornya sungguhan ke Midas Civil.

## [0.6.0] — 2026-08-08 — `pilecap-ui`: formulir offline di localhost

Sampai v0.5.0 tool hanya dapat dijalankan lewat empat perintah CLI dengan puluhan flag,
ditambah `pilecap_config.json` yang harus ditulis tangan. Bagi engineer yang tidak terbiasa
CLI, hambatannya bukan pada rekayasanya melainkan pada cara menjalankannya.

### Added
- **`pilecap-ui`** — formulir Streamlit yang berjalan **offline di localhost**, mengisi
  seluruh masukan lalu menjalankan `pilecap-run`. Extra opsional: `uv sync --extra ui`.
- Sub-paket `src/pilecap_fem/ui/` berisi `launcher.py`, `schema.py`, `argv.py`, `app.py`.
- `tests/test_ui.py` (24 test) yang seluruhnya berjalan **tanpa streamlit terpasang**.

### Tidak ada engine baru — dan itu dijaga secara struktural

UI **tidak pernah** menjalankan engine di dalam prosesnya sendiri: ia menyusun daftar
argumen lalu memanggil CLI sebagai subprocess. Tiga alasan, masing-masing sudah terbukti:

1. **`shell-kit` sudah membayarnya.** Docstring `shell_kit/ui/__init__.py` mencatat bahwa
   UI Streamlit di sana pernah mengimpor potongan engine lalu menulis ulang orkestrasinya,
   sehingga ada dua implementasi yang harus dijaga sinkron — dan UI itu akhirnya dihapus.
2. **OpenSeesPy dan gmsh menyimpan state global proses.** Server Streamlit berumur panjang
   dan dapat menjalankan beberapa rerun; di dalam satu proses, dua analisis akan saling
   merusak state C library yang sama.
3. **`run_manifest.json` merekam string perintah.** Dengan subprocess, yang tercatat adalah
   perintah `pilecap-run` yang benar-benar dapat dijalankan ulang orang lain — bukan
   sekadar "dijalankan dari UI".

Dua test menutup kelas bug ini secara permanen: config hasil formulir dijalankan melalui
`io_utils.load_config` + seluruh validator, dan setiap argv yang dipancarkan diberikan ke
`cli_pilecap_run.build_parser()` yang asli. Formulir karena itu tidak dapat menghasilkan
masukan yang ditolak engine, dan tidak dapat memancarkan flag yang tidak dikenal CLI.

### Temuan: kunci bernilai `null` TIDAK setara dengan kunci yang tidak ada

Versi pertama `build_config` menulis `null` untuk setiap field yang tidak berlaku pada
cabang aktif, dengan alasan agar pembaca config melihat kuncinya. Verifikasi end-to-end
langsung menggagalkannya:

```
TypeError: int() argument must be ... not 'NoneType'
  fem_engine.py:94  n_layers=int(analysis.get("n_layers", 10))
```

`dict.get` mengembalikan `None` yang **ada** alih-alih bawaannya. Contoh bawaan pun ternyata
sudah memakai konvensi yang benar — `ex02` (pier lingkaran) tidak memuat `pier.width_x`
sama sekali, bukan menulisnya `null`. Aturan yang dipakai sekarang mengikuti contoh:
field yang **tidak berlaku dihilangkan**, field opsional yang **tampil tetapi dikosongkan
ditulis `null`** (seperti `mesh.size_local_pile` dan `design.phi_flexure`).

### Dua hal yang sengaja tidak dapat diakses dari UI

- **`--preview`** memanggil `plt.show()`; di server tanpa display ia menggantung. Justru
  ketika flag ini tidak diberikan, `renderer.PlotStyle.from_args` memaksa backend Agg.
- **`--wood-armer`** memanggil `math_engine.wood_armer` yang selalu `NotImplementedError`
  (exit 4) — menampilkannya berarti menawarkan tombol yang dijamin gagal.

### Catatan lain

- Config bertimestamp ditulis ke `<folder kerja>/ui_configs/`, **bukan** ke folder input:
  `io_utils.autodetect` memakai glob `*config*.json` dan RAISE bila menemukan lebih dari
  satu, sehingga menumpuknya di folder input akan merusak `pilecap-run` tanpa `--config`
  bagi siapa pun yang menjalankannya kemudian dari CLI.
- Server mengikat **hanya ke `localhost`**. Tanpa itu Streamlit menyajikan formulir beserta
  seluruh data proyek di dalamnya ke jaringan lokal.
- Log dialirkan dari **stderr** dan folder hasil dibaca dari **stdout** (`OK -> <path>`) —
  kebalikan dari pola `shell-kit`, karena `config.setup_logging` menulis ke stderr.
- `streamlit>=1.57` adalah **satu-satunya dependency yang tidak di-pin eksak**. Alasan pin
  eksak di proyek ini bersifat numerik (versi yang lolos VC-0..VC-5); Streamlit tidak ikut
  satu pun validation case dan tidak menyentuh angka rekayasa mana pun.

---

## [0.5.0] — 2026-08-06 — Plot tulangan lengkap + tema terang/gelap gaya `shell-kit`

v0.4.0 sudah menghitung kapasitas, tetapi keluaran visualnya baru separuh: plot tulangan
hanya menampilkan `As` perlu, tulangan **geser tidak diplot sama sekali**, dan gambar tidak
memuat konteks material sehingga kehilangan asumsinya begitu dicetak. Rilis ini
menyetarakan keluaran dengan `shell-kit rebar` **penuh**.

### Added
- **Plot seleksi batang** — 4 plot baru per kombinasi menjawab "pakai D berapa di mana",
  bukan sekadar "berapa mm² baja". Tiga mode, dipilih lewat `design.rebar_mode`:
  spasi tetap → **diameter** (kategorikal), diameter tetap → **spasi** (kontinu), dan
  spasi tetap + `rebar_select_codes` → **konfigurasi** (`2D25` dst., kategorikal).
- **Tulangan geser** — `capacity_engine.shear_rebar_map` + 4 plot (`Av/s` dan diameter
  sengkang, dua arah) + `Combo_*/shear_rebar.csv`.
- **Tema terang/gelap** — `--theme {light,dark}` pada keempat CLI, warna mengikuti
  `shell-kit` (`#FFFFFF`/`#1E1E1E`, cmap gaya `RdBu_r`/`seismic`, tulangan `YlOrRd`).
  Seluruh warna kini berasal dari `config.Theme`, tidak lagi hardcoded di `renderer`.
- **Gaya shell-kit** pada semua plot: marker MAKS/MIN berlian dengan callout melengkung,
  badge `PENAMPANG TIDAK MEMADAI`, watermark, dan **baris konteks material**
  (`f'c`, `fy`, tebal, selimut, mode) di bawah judul.
- **`--contour-method {element-center,average-nodal}`** — `element-center` tetap bawaan.
- **`design.as_min_surface_zone`** (opsional) — lihat catatan di bawah.
- `--no-rebar-plots` untuk melewati 8 plot tulangan bila pelaporan terasa lambat.

### Changed
- **`design.rebar_mode`, `stirrup_spacing_long`, dan `stirrup_spacing_trans` kini WAJIB.**
  Config v0.4.0 akan RAISE. Disengaja: diameter sengkang dihitung dari luas per kaki
  `Av/s x s_long x s_trans`, sehingga menebak grid sengkang berarti melaporkan diameter
  yang tidak pernah ditetapkan siapa pun (perlakuan sama dengan `design.fy`).
- `renderer` menerima `PlotStyle` (tema, metode, dpi, preview) menggantikan parameter
  terpisah; `render_contour` sudah 11 argumen sebelum tema ada.

### Fixed
- **`pilecap-run` menjatuhkan flag baru diam-diam.** Argumen laporan disalin satu per satu
  dari daftar manual, sehingga `--theme dark` diterima di baris perintah lalu hilang
  sebelum sampai ke pelaporan — laporan tetap terang tanpa pesan apa pun. Kini seluruh
  argumen yang dikenal parser laporan disalin otomatis, jadi bentuk kegagalan ini tidak
  terulang untuk flag berikutnya.

### Temuan: `As_min` mendominasi hasil, dan ada opsi resmi yang mengubahnya

DIUKUR pada ex01: **18 dari 20 lajur** mendapat `As = As_min`, hanya 2 yang dikendalikan
momen. `shell_kit.rebar.calc_as_min_per_face` menyediakan `surface_zone`:

| tebal | `As_min` tanpa batas | dengan batas 300 mm |
|-------|----------------------|---------------------|
| 1.200 mm | 1.080 mm²/m | 540 mm²/m |
| 1.400 mm | 1.260 mm²/m | 540 mm²/m |
| 1.500 mm | 1.350 mm²/m | 540 mm²/m |

**ACI 350-06 Ps. 7.12.2.1** membatasi 300 mm per muka untuk elemen >600 mm; **SNI 2847:2019
tidak menyatakan batas ini**. Karena satu opsi ini menggeser hampir seluruh hasil lentur
pilecap tebal, ia diekspos sebagai `design.as_min_surface_zone` — **opsional, `null` =
murni SNI**, dan bila dipakai nilainya beserta sitasinya dicetak di `run_manifest.json`.
Bukan dipakai diam-diam, bukan pula disembunyikan.

### Temuan: peta geser per elemen mudah disalahbaca

DIUKUR pada ex01 kombinasi `1.2D+1.6L`: **307** elemen ber-`Av/s > 0`, tetapi hanya **31**
yang `V_u > phi V_c`. Selisihnya adalah elemen yang beton-nya cukup dan hanya terkena
`Av,min`. Satu angka gabungan akan terbaca seolah sepertiga pelat butuh sengkang.

`Av/s` karena itu dihitung **dua kali**, dengan dan tanpa `Av,min`, dan keduanya muncul
sebagai kolom terpisah di `shear_rebar.csv`, sebagai dua kolom di calc sheet bagian 7b,
dan sebagai caption di plot. `ShearRebarMap.n_needs_stirrup` sengaja menghitung
`V_u > phi V_c`, bukan `Av/s > 0`.

Catatan kedua: diameter sengkang bisa **nyaris seragam** (pada ex01: hanya D10) karena grid
200×200 mm membuat luas per kaki mudah terpenuhi. **`Av/s` yang membawa informasi**, bukan
diameternya — dinyatakan di caption agar "sengkang seragam" tidak terbaca sebagai "aman".

### Mengapa gaya shell-kit direplikasi, bukan diimpor

`shell_kit.plotting.generate_plot_worker` menerima tuple posisional, menyimpan PNG, dan
mengembalikan path saja — **tidak ada Figure/Axes yang dikembalikan, tidak ada hook**.
Anotasi denah pilecap (lingkaran pile bertanda `Pz`, arsir pier `JEPIT`) yang diwajibkan
PRD Bagian 9.3 karena itu MUSTAHIL ditambahkan bila plotter itu dipanggil.

Pembedaannya tetap dipegang: **rumus** kapasitas menentukan kebenaran angka desain sehingga
wajib satu sumber dan tetap diimpor dari `shell_kit.rebar` — tidak satu baris pun disalin.
**Gaya visual** hanya penyajian; salinan yang menyimpang paling jauh menghasilkan warna
berbeda, bukan angka berbeda.

### Golden file: sengaja TIDAK diregenerasi

Ketiga contoh tetap `rebar_mode: "spacing_fixed"` dengan `rebar_spacing` yang sama dan
`as_min_surface_zone: null`, sehingga seluruh angka lentur harus identik dengan v0.4.0.
`tests/test_golden.py` yang tetap hijau adalah buktinya — penambahan besar ini murni aditif.

---

## [0.4.0] — 2026-08-05 — Integrasi `shell-kit`: cek kapasitas SNI 2847:2019 + golden file

Sampai v0.3.1 seluruh cek kapasitas berstatus `NOT_EVALUATED` karena PRD Bagian 17 item 2
(standar & tahun) dan item 3 (pasal `V_c`, `b_o`, `d`, `phi`) belum dikonfirmasi; laporan
hanya menyajikan **demand**. Keduanya kini tertutup dari sumber yang sah — `shell-kit`
v3.3.0 milik user sendiri, yang sudah mengimplementasikan SNI 2847:2019 lengkap dengan
sitasi pasal — **tanpa `pilecap-fem` pernah menebak satu pasal pun**.

### Added
- **`capacity_engine.py`** — satu-satunya batas satuan menuju `shell-kit`, analog
  `io_utils.py` untuk masukan. `shell_kit.rebar` bekerja dalam kN·m/m, kN/m, MPa, mm;
  seluruh `pilecap-fem` murni SI. Konversi terkumpul di satu modul, memakai faktor yang
  sama dari `config.DISPLAY_UNITS`, dan hasilnya dikembalikan ke SI.
- **`Combo_*/rebar_design.csv`** — `As perlu` per elemen untuk keempat kombinasi arah ×
  muka, terpisah dari `element_resultants.csv` agar demand mentah tetap dapat dibaca
  tanpa tercampur hasil desain.
- **`Envelope/rebar_design_envelope.csv`** — `As pakai` governing lintas kombinasi beserta
  `governing_combo` per elemen. Status `PENAMPANG_TIDAK_MEMADAI` **menular**: satu
  kombinasi yang gagal sudah cukup.
- **`calc_sheet.md` bagian 7a** (desain lentur) + kapasitas geser satu arah terisi di
  bagian 7, keduanya dengan blok provenance `shell-kit` dan daftar pasal.
- **`SUMMARY.md` bagian 3a** — `As` governing lintas kombinasi, dilacak sampai lajur asalnya.
- **Kontur `As`** arah X & Y × muka atas & bawah, skala sekuensial.
- **Golden file** `examples/*/expected/golden.json` + `pytest --regen-golden`
  (PRD Bagian 8.2 & 5.4). Diletakkan di dalam contoh, bukan di `tests/`, sehingga ikut
  dikemas: pengguna `uvx` dapat memverifikasi instalasinya mereproduksi angka acuan, bukan
  sekadar berjalan tanpa error. Regenerasi pertama — berkas dibuat baru pada rilis ini.

### Ditemukan saat membangun golden file: mesh gmsh TIDAK reproducible

Golden file berbasis koordinat node gagal berulang tanpa satu pun perubahan kode. Setelah
diukur: gmsh 4.15.2 menghasilkan mesh yang **berbeda antar run** dengan input dan versi
yang sama — jumlah node & elemen selalu identik (6994/6844 pada ex02), tetapi posisi node
berbeda hingga **33 mm**. Menyetel `General.NumThreads = 1` dan `Mesh.MaxNumThreads2D = 1`
tidak menghilangkannya, jadi penyebabnya bukan threading melainkan algoritma
Quasi-structured Quad itu sendiri.

Dampaknya pada angka desain **diukur, bukan diasumsikan** — 3 run berturut-turut:

| Contoh | momen lajur | `As` desain | `\|m_xx\|` puncak | lendutan maks |
|--------|-------------|-------------|-----------------|---------------|
| ex01 | 0,000% | 0,000% | 0,000% | 0,000% |
| ex02 | 0,020% | 0,021% | 0,001% | 0,000% |
| ex03 | 0,000% | 0,000% | 0,000% | 0,000% |

Konsekuensinya diambil, bukan diabaikan. Rancangan golden ditentukan oleh **tiga kegagalan
berturut-turut yang benar-benar terjadi**, masing-masing menyingkap satu asumsi keliru:

1. Membandingkan **nilai satu elemen terdekat** ke titik probe → berbeda **21%** antar
   run. Bukan medannya yang berubah, melainkan elemen terdekatnya bukan elemen yang sama.
2. Diganti **rata-rata berbobot luas dalam radius tegas** → masih gagal. Satu elemen yang
   berpindah keanggotaan di batas radius menggeser rata-ratanya secara diskrit.
3. Ditemukan penyebab yang lebih mendasar: **grid probe itu sendiri bergeser**, karena
   diturunkan dari bounding box centroid elemen (terukur 3,3 mm).

Bentuk akhir: grid probe diturunkan dari **polygon pilecap** (data input, bit-identik
setiap run), dan nilainya dirata-rata dengan **kernel Gauss berbobot luas** tanpa cutoff,
sehingga bobot berubah mulus terhadap posisi centroid. Diverifikasi dengan menjalankan
perbandingan **dua kali terhadap mesh yang dibangkitkan ulang**: 15/15 lulus keduanya.

Toleransi ditetapkan dari sebaran terukur di atas (`VALIDATION_RTOL` = 0,1% memberi margin
~5x untuk besaran desain), bukan dari tebakan.
- Ditambahkan sebagai **Known Limitation #9** sehingga muncul di setiap `SUMMARY.md` dan
  `calc_sheet.md`. Laporan tidak boleh menyiratkan reproducibility yang tidak dimilikinya
  (PRD Core 5), dan pembaca perlu tahu bahwa `00_Model/nodes.csv` + `elements.csv` adalah
  satu-satunya cara mereproduksi angka secara persis.

### Changed
- **`design.fy`, `design.fy_source`, dan `design.rebar_spacing` kini WAJIB**, diperlakukan
  persis seperti `material.E`: kosong berarti RAISE. `shell_kit.rebar.DEFAULT_FY = 420`
  **tidak** dipakai diam-diam — mutu baja menentukan seluruh luas tulangan yang dilaporkan
  (PRD Bagian 1.3 poin 2). Ketiga contoh diisi nilai bertanda `[CONTOH]`.
- `config.OPEN_BLOCKERS`: **#2 dan #3 ditutup**. Yang tersisa dari #3 hanya bagian pons,
  dicatat ulang sebagai **#3b** — `shell-kit` hanya menyediakan geser satu arah.
- `provenance.set_standards()` menerima blok provenance kapasitas; `run_manifest.json`
  kini merekam versi `shell-kit` beserta pasal yang dirujuk.
- `postproc_engine.design_moment_sections` menambahkan `width_m` (lebar yang benar-benar
  terintegrasi). Momen per satuan lebar memakai nilai ini, bukan lebar nominal lajur —
  memakai lebar nominal akan menggeser `As perlu` secara diam-diam.

### Fixed
- **Test VC-0 bergantung pada keberuntungan floating point.**
  `test_vc0_gagal_bila_toleransi_dibuat_mustahil` memaksa gagal dengan `rtol = 1e-30`,
  padahal residu gaya pada model yang benar kadang tepat `0.0` — dan `0.0 <= rtol` lulus
  untuk **setiap** rtol. Test itu karena itu lulus/gagal berganti-ganti tanpa ada yang
  berubah di kode. Diganti dua test deterministik: deteksi ketidakseimbangan diuji
  langsung pada `_check_equilibrium` dengan masukan yang memang tidak seimbang, dan
  penyambungan "gagal berarti memblokir" diuji lewat monkeypatch.

### Yang TETAP tidak dikerjakan
- **Kapasitas geser pons** tetap `NOT_EVALUATED`. `shell_kit.rebar.calc_Vc` adalah geser
  SATU ARAH (`b_w × d_v`); memakainya untuk keruntuhan dua arah berarti menerapkan rumus
  di luar lingkupnya. `V_u` dan `b_o` pons **sudah** dihitung — yang kurang hanya
  kapasitasnya.
- **Vonis deep pile cap** (#5), Wood-Armer, VC-1/VC-6/VC-7, self-weight (#6), dan redaksi
  disclaimer (#18). Ketujuhnya dicatat sebagai GitHub Issue, bukan ditebak.

---

## [0.3.1] — 2026-08-04 — Perbaikan instalasi `uvx`

Ditemukan saat menguji instalasi sungguhan dari GitHub pada v0.3.0. Tag v0.3.0
**tidak dipindahkan**: memindahkan tag yang sudah dipublikasikan justru meniadakan
alasan tag itu ada, yaitu agar laporan lama dapat direproduksi dengan versi tool yang
persis sama.

### Fixed
- **`requires-python` tidak cukup untuk instalasi dari sumber git.** Terukur:
  `uvx --from git+...` memilih interpreter **sebelum** metadata paket diketahui,
  memakai Python 3.14.1 (terbaca di `pyvenv.cfg` lingkungan tool-nya) dan tetap
  memasang paketnya — lalu gagal dengan `DLL load failed while importing opensees`,
  pesan yang terbaca seperti instalasi rusak alih-alih salah interpreter.
  - `pilecap_fem._check_interpreter()` kini berjalan saat impor dan berhenti dengan
    pesan yang menyebut penyebab sebenarnya beserta perintah yang benar.
  - README: `--python 3.12` didokumentasikan sebagai **wajib**, menggantikan klaim
    keliru pada v0.3.0 bahwa `uv` menyediakan Python 3.12 sendiri.
- **`pilecap-report` menarik `openseespy`** lewat rantai
  `reporter → postproc_engine → fem_engine`, sehingga pelaporan dari CSV ikut mati di
  interpreter yang salah padahal tidak membutuhkan solver sama sekali. Impor
  `ComboResult` kini `TYPE_CHECKING`; terbukti bebas gmsh **dan** openseespy, dijaga
  test terparametrisasi untuk keduanya.
- Test pengemasan memanggil `uv` lewat path absolut hasil `shutil.which()`. Nama
  telanjang diresolusi `CreateProcess` lewat PATH saat spawn dan gagal (`WinError 2`)
  hanya ketika test berjalan di akhir suite penuh — kegagalan yang tidak ada
  hubungannya dengan isi wheel.

---

## [0.3.0] — 2026-08-04 — Fase 3: visualisasi + laporan auditable, siap `uvx`

### Distribution (PRD Bagian 14, Cond D)
- Dapat dipasang langsung dari GitHub:
  `uvx --from git+https://github.com/kikifadilah31/kft_pilecap_fem pilecap-run`.
- **Versi kini satu sumber**, dibaca `pyproject.toml` dari `__init__.py` lewat
  `[tool.hatch.version]`. Sebelumnya versi hidup di dua tempat dan keduanya tertinggal
  di `0.1.0`, sehingga **setiap `run_manifest.json` dan `calc_sheet.md` yang dihasilkan
  mengklaim v0.1.0** — cacat provenance (PRD Core 5). Dijaga `tests/test_packaging.py`,
  termasuk kecocokan dengan entri teratas CHANGELOG.
- **Seluruh dependency di-pin eksak (`==`)** ke versi yang lolos VC-0..VC-5, karena
  `uvx`/`uv tool install` dari git **mengabaikan `uv.lock`** dan me-resolve ulang dari
  `pyproject.toml`. Dengan rentang longgar, dua pengguna yang memasang di hari berbeda
  dapat menjalankan numerik yang berbeda (PRD Bagian 10).
- `examples/` ikut dikemas (18 KB) + flag `--init-example DIR` pada `pilecap-mesh`,
  `pilecap-analyze`, dan `pilecap-run`. `pilecap-report` sengaja tidak menerimanya:
  ia bekerja pada run yang sudah ada, dan menambahkannya akan menarik gmsh ke modul yang
  sengaja dibuat bebas gmsh (dijaga oleh test).
- `LICENSE` (draft, redaksi final oleh pemilik) + classifier `Private :: Do Not Upload`.

### Findings — distribusi
- **`openseespy` 3.8.0.0 TERPASANG di Python 3.13 tetapi GAGAL diimpor.** Wheel-nya
  bertag `py3-none-win_amd64` sehingga lolos pemeriksaan pip/uv, namun `.pyd` di dalamnya
  dibangun untuk CPython 3.12 → `DLL load failed while importing opensees`. Batas
  `requires-python = ">=3.12,<3.13"` karena itu **wajib**, bukan konservatif.
- **`requires-python` TIDAK cukup untuk instalasi dari sumber git.** Terukur: `uvx --from
  git+...` memilih interpreter **sebelum** metadata paket diketahui, memakai Python
  3.14.1 (terbaca di `pyvenv.cfg` lingkungan tool-nya) dan tetap memasang paketnya —
  lalu gagal dengan error DLL yang terbaca seperti instalasi rusak. Karena itu:
  - `--python 3.12` didokumentasikan sebagai **wajib** untuk `uvx`/`uv tool install`;
  - `pilecap_fem._check_interpreter()` berjalan saat impor dan menghentikan program
    dengan pesan yang menyebut penyebab sebenarnya beserta perintah yang benar.
- **`pilecap-report` sempat menarik `openseespy`** lewat rantai
  `reporter → postproc_engine → fem_engine`. Impor `ComboResult` kini `TYPE_CHECKING`,
  sehingga pelaporan dari CSV tidak lagi bergantung pada solver maupun gmsh — dijaga
  test terparametrisasi untuk keduanya.

### Added
- `renderer.py` penuh — kontur `m_x`/`m_y`/`m_xy`/`q_x`/`q_y`/lendutan,
  `boundary_load_check.png`, pembungkus `opsv.plot_model()` / `opsv.plot_defo()`,
  kontur envelope. Anotasi wajib (outline pilecap, lingkaran pile + `Pz`, arsir pier
  + `JEPIT`, arah sumbu) dipusatkan di `_annotate_plan()` sehingga tidak pernah
  menyimpang antar gambar.
- `postproc_engine` — `shear_demand()` (satu arah di `d` dari muka pier, pons dari
  keseimbangan gaya di `d/2`), `build_envelope()` dengan `governing_combo` per lokasi,
  `design_moment_sections()`, `shear_span_ratio()`.
- `reporter.py` — `calc_sheet.md` (10 bagian PRD Bagian 9.4), `SUMMARY.md`,
  `strip_moments_x/y.csv`, `shear_checks.csv`, `envelope_values.csv`,
  `envelope_summary.md`, plus pembaca balik CSV.
- `cli_pilecap_report.py` dan `cli_pilecap_run.py` — **keempat entry point PRD
  Bagian 14 kini nyata**, tidak ada lagi stub.
- 377 test; coverage 96% (`renderer` 100%, `math_engine` 100%, `postproc_engine` 99%,
  `reporter` 99%).

### Standards
`OPSVIS_MAX_ELEMENTS = 3.000` — ditetapkan dari pengukuran: `opsv.plot_model` 0,67 s dan
`opsv.plot_defo` 5,1 s untuk 1.200 elemen, dengan `plot_defo` tumbuh lebih cepat dari
linier. Di atas ambang, plot opsvis **dilewati dengan WARNING eksplisit** di log dan
laporan; `--opsvis` memaksa tetap dibuat.

### Deviations from PRD — beserta alasannya
9. **Plot opsvis dibuat `pilecap-analyze`, bukan `pilecap-report`.** opsvis membaca
   domain OpenSees yang HIDUP (`plot_defo` memanggil `ops.nodeDisp()`), sehingga tidak
   dapat dibuat dari CSV tanpa menyelesaikan ulang model. Seluruh kontur dan laporan
   tetap dibuat `pilecap-report` dari CSV.
10. **Dua berkas di luar daftar PRD Bagian 9.1**, keduanya diperlukan:
    `00_Model/geometry.json` (membuat run swasembada — report tidak bergantung pada file
    input yang bisa berubah) dan `Combo_*/node_displacements.csv` (PRD meminta
    `contour_deflection.png` tanpa menyediakan sumber datanya).
11. **`Combo_*/traceability_sample.json`** — nilai per titik Gauss tidak tersimpan di
    `element_resultants.csv`, sehingga rantai telusur PRD Bagian 9.4 bagian 5 ditulis
    `pilecap-analyze` sebagai berkas terpisah. `pilecap-report` **menolak berjalan**
    bila berkas itu hilang, alih-alih menyajikan rantai yang terpotong diam-diam.
12. **Kontur digambar datar per elemen**, tidak dihaluskan. Nilai resultant memang per
    elemen; interpolasi nodal akan menyiratkan kehalusan yang tidak dihitung, dan justru
    paling menyesatkan di daerah singularitas tepi zona jepit.

### Findings — visualisasi & laporan
- **Faktor `moment_per_width` dan `shear_per_width` kebetulan sama-sama `1e-3`.**
  Membedakan momen dari geser lewat nilai faktornya menghasilkan label satuan yang salah
  saat membaca balik CSV. Pemetaan kolom → besaran kini eksplisit.
- `np.vstack` pada envelope gagal dengan pesan numpy yang tidak menyebut penyebabnya;
  validasi jumlah elemen kini mendahului penumpukan.

### Validation
VC-0 tetap lulus pada ketiga contoh (residu 1e-14…1e-16), termasuk ex03 dua pier.
Rantai telusur `calc_sheet.md` diverifikasi dengan hitungan tangan: `m11 cos²θ +
m22 sin²θ − 2 m12 sinθ cosθ` dari angka yang tercetak menghasilkan `m_xx` yang
dilaporkan, cocok sampai `rel=1e-9`. Envelope diuji cocok dengan maksimum antar
`element_resultants.csv` per kombinasi.

### Masih terbuka
PRD Bagian 17 item 2, 3, 5, 6, 7, 8, 10, 18. Seluruh kapasitas tetap `NOT_EVALUATED`
dan laporan hanya menampilkan demand. Rasio `a/d` dilaporkan **tanpa vonis**.
`--wood-armer` menolak berjalan dengan pesan yang menyebut sumber primer Wood (1968).

---

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
