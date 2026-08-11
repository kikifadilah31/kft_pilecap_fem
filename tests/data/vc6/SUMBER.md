# Sumber data VC-6 — model pembanding Midas Civil

Berkas di folder ini adalah **bukti** untuk `VC-6` (`tests/test_validation_cases.py`), yaitu
validasi silang `pilecap-fem` terhadap program elemen hingga mapan. VC-6 adalah *release
gate*: rilis diblokir bila ia gagal (PRD Bagian 1.3 poin 1).

Data disediakan pemilik proyek pada 2026-08-10 (ex01–ex03) dan 2026-08-11 (ex04), dan
menutup `PRD Bagian 17 item 8`, yang sebelumnya TERBUKA karena model pembanding belum
tersedia.

---

## 1. Asal

Keempat contoh bawaan (`examples/ex01…ex04`) dianalisis ulang di **Midas Civil**
(solver `MEC V2.0.0`). Model Midas-nya **diimpor dari `00_Model/model.mct`** yang ditulis
`pilecap_fem.exporters.mct` — bukan dimodelkan ulang dengan tangan. Konsekuensinya penting
dan disengaja: penomoran node dan elemen **identik 1:1** dengan milik kita, sehingga
perbandingan per-elemen dan per-node bermakna tanpa pemetaan apa pun.

### 1.1 ex04 menguji jalur tumpang tindih pile–pier (v0.9.0)

`ex04` ditambahkan setelah v0.9.0 dan **bukan sekadar contoh keempat**: ia satu-satunya
kasus yang pile-nya menindih pier, sehingga ia menguji tiga hal yang tidak disentuh
ex01–ex03 — masing-masing terhadap implementasi yang sepenuhnya independen:

1. **Himpunan tumpuan termasuk node lensa.** `*CONSTRAINT` pada MCT ditulis dari
   `fem_engine.fixed_support_nodes`, yang menjepit node `PIER_*` **ditambah** node
   `LENS_*`. Terukur: himpunan node reaksi Midas **sama persis** dengan milik kami —
   479 node, tanpa satu pun selisih di kedua arah. Bila lensa tertinggal bebas di Midas,
   angkanya akan berbeda dan seluruh perbandingan menjadi tidak sahih.
2. **Seluruh cakram pile dibebani, termasuk bagian di dalam pier.** `Σ FZ` Midas sama
   dengan `Σ Pz` masukan sampai ~9 angka berarti (§ Jalur 3), padahal sebagian tekanan itu
   bekerja pada elemen lensa. Ini membuktikan `*PRESSURE` pada MCT memang memuat elemen
   lensa.
3. **Respons pelatnya sendiri.** Elemen lensa dijepit **sekaligus** dibebani — keadaan yang
   tidak lazim dan sengaja dipilih (KNOWN_LIMITATIONS #10). Resultan per elemen tetap cocok
   dengan Midas pada RMS ≤ 0,134%.

Yang **tidak** dibuktikan ex04: bahwa idealisasi jepit-sempurna itu benar secara fisik.
Kedua program memakai idealisasi yang sama, jadi kesesuaiannya tidak dapat menilai
asumsinya. Kapasitas strut tetap wajib dicek terpisah oleh engineer.

## 2. LARANGAN: mesh tidak boleh diregenerasi

`nodes.csv`, `elements.csv`, dan `geometry.json` di sini adalah mesh **persis** yang dipakai
membangun model Midas. gmsh tidak reproducible bit-demi-bit — posisi node dapat bergeser
sampai 33 mm antar run (lihat README, "mesh tidak reproducible bit demi bit").

Karena itu VC-6 **memuat mesh dari CSV ini**, tidak pernah menjalankan gmsh. Me-mesh ulang
berarti membandingkan dua diskretisasi yang berbeda, dan seluruh perbandingan per-elemen
kehilangan maknanya tanpa satu pun tanda kegagalan.

## 3. Satuan & konvensi berkas Midas

| Hal | Nilai |
|-----|-------|
| Satuan internal solver | `PARAM, UNITS, M-N-J-SEC` → meter–newton |
| Satuan ekspor CSV | kN, kN·m/m, m, rad |
| Formulasi elemen | `PARAM, QUAD4STRUC, HYB` → QUAD4 hibrida |
| Sumbu pelaporan resultan | `PARAM, ELEMRSLTCORD, MATERIAL` → **sumbu material (lokal) elemen** |

Tiga baris `PARAM` di atas dikutip dari `…_model_Static Load.mec` dan **identik pada keempat
contoh** (ex04 diperiksa ulang saat penambahannya). Berkas `.mec` sendiri (0,8–2,9 MB) tidak disalin ke sini karena isinya sebagian
besar menduplikasi `nodes.csv`/`elements.csv`; sha256-nya tercatat di tabel §6 agar tetap
dapat diverifikasi terhadap arsip pemilik proyek.

## 4. Rekonsiliasi yang WAJIB diterapkan sebelum membandingkan

### 4.1 Tanda geser melintang berlawanan

Konvensi geser melintang Midas **berlawanan** dengan konvensi PRD Bagian 7.1. Pembacanya
karena itu mengalikan `Vxx`/`Vyy` dengan `−1`.

Bukti keseragamannya — diukur pada **seluruh** elemen, ex01–ex03 × dua kombinasi:
rasio `−q_midas / q_kita` **tidak menyimpang tandanya pada satu pun** dari ~5.500 elemen;
median 1,0008–1,0019, sebaran p1–p99 dalam ±3,5%. ex04 mengikuti konvensi yang sama dan
lulus gate geser dengan RMS ≤ 0,114%.

Yang membuat kesimpulan ini kuat: pembalikan tanda tetap muncul pada `midas_force_global.csv`,
yang **tidak melewati rotasi apa pun**. Jadi ini bukan artefak sumbu lokal maupun artefak
aritmetika kita, melainkan konvensi Midas yang sesungguhnya. Momen **tidak** butuh
pembalikan; hanya vektor geser.

### 4.2 Sumbu lokal vs global

`midas_force_local.csv` dilaporkan pada sumbu material elemen (§3), sehingga **tidak boleh**
dibandingkan langsung dengan `m_xx/m_yy/m_xy` kita. Contoh nyata (ex01, elemen 1,
`1.2D+1.6L`): `Mxx` lokal `25,392` vs global `18,234` kNm/m — dua angka yang tidak
berhubungan bila tertukar.

Perbandingan utama VC-6 karena itu memakai `midas_force_global.csv`, yang sudah dalam sumbu
global dan cocok langsung.

`midas_force_local.csv` **tetap disimpan** untuk satu keperluan: cek-silang transformasi
tensor. Merotasi ekspor lokal dengan `theta` dari `elements.csv` mereproduksi ekspor global
Midas sampai RMS 0,0001% (simpangan maks 0,0002%). Itu membuktikan dua hal sekaligus —
`theta` kita adalah sudut sumbu material yang sama dengan yang dipakai Midas, dan rumus
rotasi `postproc_engine` cocok dengan rumus Midas.

## 5. Isi tiap berkas & jebakan parsing

| Berkas | Isi | Dipakai |
|--------|-----|---------|
| `midas_force_global.csv` | resultan elemen, sumbu **global** | Jalur 1 (pembanding utama) |
| `midas_force_local.csv` | resultan elemen, sumbu **lokal** | cek-silang rotasi saja |
| `midas_reaction.csv` | reaksi tumpuan per node + blok TOTAL | Jalur 3 |
| `midas_displacement.csv` | lendutan per node (`DX…RZ`) | Jalur 2 — keempat contoh |
| `midas_solver.log` | `MAXIMUM TRANSLATION` per subcase | Jalur 2 |
| `midas_solver.out` | urutan subcase, konfirmasi run sukses | acuan urutan |

Jebakan yang semuanya sudah terverifikasi dan ditangani `tests/validation_helpers.py`:

* Berkas ber-**BOM UTF-8** → baca dengan `encoding="utf-8-sig"`, jika tidak kolom pertama
  bernama `﻿Elem`, bukan `Elem`.
* `·` pada `kN·m/m` adalah **U+00B7 MIDDLE DOT**, bukan titik ASCII.
* Kolom `Angle([deg])` **muncul dua kali** (sudut utama membran dan sudut utama momen);
  pandas menamai yang kedua `Angle([deg]).1`.
* Berkas resultan memuat **5 baris per elemen per kombinasi**: satu `Node=Cent` (centroid)
  diikuti 4 baris per simpul sudut. VC-6 memakai baris `Cent` saja.
* Kolom `Load` berisi **slug** (`1_2D_1_6L`), bukan nama tampilan (`1.2D+1.6L`).
* Berkas reaksi memuat baris teks `SUMMATION OF REACTION FORCES PRINTOUT` dan blok TOTAL
  berkolom `Node` kosong → saring dengan `pd.to_numeric(..., errors="coerce")`;
  `astype(int)` akan meledak.

### 5.1 Riwayat: ekspor lendutan ex03 sempat salah, lalu diperbaiki

**Keadaan sekarang: sudah benar.** `ex03/midas_displacement.csv` berisi lendutan per node
(`DX…RZ` dalam m/rad), cakupan 100% (4.949 node × 2 kombinasi), dan Jalur 2 mencakup ketiga
contoh.

Riwayatnya tetap dicatat di sini karena menghapusnya berarti menghapus jejak audit. Pada
penyalinan pertama (v0.8.0), berkas ex03 yang tersedia **byte-identik** dengan berkas
reaksinya (sha256 `f81148229…dcb51ce` pada keduanya) dan isinya memang reaksi (`FX…MZ` dalam
kN), bukan lendutan — jelas salah ekspor. Berkas itu **tidak** disalin, dan keterbatasannya
dinyatakan apa adanya alih-alih ditambal.

Pemilik proyek kemudian mengulang ekspornya. Berkas yang tersimpan sekarang adalah hasil
perbaikan itu; sha256-nya ada di tabel §6 dan **berbeda** dari berkas reaksi ex03.

Yang membuat kekeliruan itu tertangkap, dan akan tertangkap lagi: pembaca di
`validation_helpers.midas_nodal` **menentukan isi dari header, bukan dari nama berkas**, dan
melempar `ValueError` bila header tidak dikenali. Test Jalur 2 juga mengasersi
`jenis == "displacement"` secara eksplisit, sehingga berkas reaksi yang menyamar sebagai
lendutan menggagalkan test, bukan diam-diam dibandingkan sebagai besaran yang salah.

### 5.2 Batas ketelitian ekspor lendutan

`midas_displacement.csv` menulis 6 desimal dalam **meter**, jadi resolusinya 1 µm. Pada
pilecap kaku, angka itu besar dibandingkan lendutannya sendiri. Diukur **per kombinasi** —
bukan lintas kombinasi, karena batasnya berlaku pada tiap ekspor sendiri-sendiri:

| Contoh | Kombinasi | `uz` maks | 1 µm setara | RMS terukur | Mengikat? |
|--------|-----------|----------:|------------:|------------:|-----------|
| `ex01` | 1.2D+1.6L | 0,2253 mm | 0,444% | 0,216% | **ya** |
| `ex01` | 1.2D+1.0W | 0,3147 mm | 0,318% | 0,158% | **ya** |
| `ex02` | 1.2D+1.6L | 2,6401 mm | 0,038% | 0,043% | tidak |
| `ex02` | 1.2D+1.0W | 3,8285 mm | 0,026% | 0,038% | tidak |
| `ex03` | 1.2D+1.6L | 1,9286 mm | 0,052% | 0,045% | **ya (tipis)** |
| `ex03` | 1.2D+1.0W | 2,2331 mm | 0,045% | 0,042% | **ya (tipis)** |
| `ex04` | 1.2D+1.6L | **0,1101 mm** | **0,908%** | 0,258% | **ya, paling kuat** |
| `ex04` | 1.2D+1.0W | 0,1705 mm | 0,586% | 0,181% | **ya** |

"Mengikat" berarti resolusi ekspornya **lebih besar** daripada selisih yang terukur —
sehingga lulusnya test tidak dapat dibaca sebagai bukti ketelitian sebesar selisih itu; yang
terbukti hanyalah **"tidak berbeda sejauh yang dapat diukur"**.

> **Koreksi terhadap versi sebelumnya dokumen ini.** Sampai v0.9.0 bagian ini hanya menyebut
> ex01 sebagai yang terbatas resolusi, dan menyiratkan ex02 & ex03 bebas dari batasan itu.
> Pengukuran ulang saat ex04 ditambahkan menunjukkan **ex03 juga mengikat**, meski tipis
> (0,052% vs 0,045%). Hanya **ex02** yang benar-benar bebas. Angka lendutan maksimum ex01 di
> versi lama (0,226 mm) juga hanya mencakup satu kombinasi.

ex04 adalah yang paling terbatas: pilecap 1.500 mm dengan pier dinding 2.400 × 1.200 sangat
kaku, sehingga lendutannya hanya 0,110 mm. **Jalur lendutan karena itu bukan jalur yang
memvalidasi ex04**; yang mengikat untuk ex04 adalah Jalur 1 (resultan elemen) dan Jalur 3
(reaksi), yang keduanya tidak dibatasi resolusi ekspor.

Konsekuensi praktis untuk keempat contoh: **Jalur 2 adalah jalur terlemah dalam paket ini**.
Ia tetap berharga karena menangkap kesalahan besar (tanda terbalik, skala salah, model
berbeda), tetapi bukan ia yang membuktikan ketelitian — itu tugas Jalur 1 dan 3.

## 6. Daftar berkas & sha256

Dihitung terhadap berkas sumber di arsip pemilik proyek pada saat penyalinan
(`ref/model_pembanding_midas/`, tidak ikut version control).

### `ex01/`

| Berkas | Byte | sha256 |
|--------|-----:|--------|
| `elements.csv` | 146,845 | `d370df0180057996131972466c4e1960670cc6357cd4fd6d836cb3679a705003` |
| `geometry.json` | 1,374 | `c64ad503f20621ae6fbb8958ab7992da31cd7d9a6dce200840aefd29e08179c6` |
| `midas_displacement.csv` | 182,613 | `fb887fc10546bc1a6289d86b2a841afe9e89cd4e835250390304f4fc3f34ffaf` |
| `midas_force_global.csv` | 1,660,082 | `563a232fa75d024f8676f7752c80218d91d2934ecd930c1444374d78ffcdb35d` |
| `midas_force_local.csv` | 1,655,171 | `7c8f23e0643d6d4f72deab89edfc24b8169384f718390d40ab3704b1bf94a39f` |
| `midas_reaction.csv` | 8,796 | `ff8edf0dfd710ac9feded1d5764753a8e804f36df9f905669e536e36c48066d7` |
| `midas_solver.log` | 1,495 | `b46bce12f954c47618ad3e97b9c5fad0d946489f736b16c5341cecc897f7adef` |
| `midas_solver.out` | 3,964 | `b9bf193b9402ee88b129e1e6a6e18ddfee4dbcb6af7982234487a61bc43a398e` |
| `nodes.csv` | 81,171 | `e94d3c9a8f791aca6d95e30c7e7ab3d48a034da76ae7a0cb664a452a68ec3521` |
| `pile_reactions.csv` | 223 | `e9d250afd79ac7c4781c08bef200ef54748bd5525ffd77140906bba6a633d297` |
| `pilecap_config.json` | 1,874 | `fef9d9c9ce9927a9d4e4f8ff641888d01390b6660d1157e8f2af7b8a7021a665` |
| *(tidak disalin)* `…Static Load.mec` | 808,176 | `fc1c4f203e23322c07265f9ea0da39cb1e94960bf93b327387330066514d68c6` |

### `ex02/`

| Berkas | Byte | sha256 |
|--------|-----:|--------|
| `elements.csv` | 562,627 | `3f7b7a7c7de985447361f1f988b1cabcd6be44b494a2a5acd36ba9cb1adbf928` |
| `geometry.json` | 2,197 | `edcfccfae1acd3f74976ee2ceb02c1972a45752e71d87ca354f6b52d5cf61fa0` |
| `midas_displacement.csv` | 670,930 | `9614f7409b169e59b3999462c4a6f8d131866688070c1ca775fb18eced57a1df` |
| `midas_force_global.csv` | 6,405,625 | `2c26dc98e60fe73792d5159e434051c1c83f340797947b0c6081244dff3278d8` |
| `midas_force_local.csv` | 6,438,631 | `39bdb20828543846e51e71058d9b9ca3fab4c005194ef2815adb99c71754c630` |
| `midas_reaction.csv` | 29,454 | `3802936357a38d2d5d198c53979e3085388a0a5480942d40b588df1a336f1123` |
| `midas_solver.log` | 1,519 | `c032471830b799991f944ea07b848f2bb778cbf94d730ea09307a397adebcf0b` |
| `midas_solver.out` | 3,963 | `31a78c5ffcbba16c71caee91bc9032e53e8c237138741664ed9de1b78b08c814` |
| `nodes.csv` | 299,675 | `3d4017866b1217c96ada749c5597dd44fea734ec5f5cd055d8128f9e16e5f840` |
| `pile_reactions.csv` | 630 | `c6287c08fc6c1dd474d33e2bb5661c50fc4f315db4f490b5d03964e6f19b2a9d` |
| `pilecap_config.json` | 1,855 | `1e2ef50ded44606f21bcfb219fa7a9335de22ec5d7dac8a27ded73ce2f4a3d4a` |
| *(tidak disalin)* `…Static Load.mec` | 2,913,229 | `63fcbb809cd21a7e5119cc8329213d88050da669466516a179327680c2f26a34` |

### `ex03/`

| Berkas | Byte | sha256 |
|--------|-----:|--------|
| `elements.csv` | 391,641 | `db6a3ef3c6499fcf8bbf9e246885f96f1d5bec456130f7eaad6d1dfde72780e6` |
| `geometry.json` | 3,793 | `8ac28618104311a8036260e89542b548078790038092aba4f9556615707fc1be` |
| `midas_displacement.csv` | 472,557 | `27198a734dc3c899f2c77e39a3f3574fb59b5040c147a3a687e44250682f5f3b` |
| `midas_force_global.csv` | 4,468,666 | `dc985c4339d7186c4c089bc6368507baecb613e25fc4c7eba4943b1f293b1ca1` |
| `midas_force_local.csv` | 4,502,028 | `9528059f336f67fe5e444c546c9c89b0e1bbe6e6562b7c525a36078326d49513` |
| `midas_reaction.csv` | 27,239 | `f811482294fbd10af6da923b7cebecf6842c99e660b9a02dd40a52eefdcb51ce` |
| `midas_solver.log` | 1,491 | `cae01915399573e1ddb9abc8835330a17adaebdb8aa3dae0d557ef8448821e65` |
| `midas_solver.out` | 3,964 | `475dfdd04db7287245cf4cbab376cf435050f8d01909bfe2fdf8d329bea94e47` |
| `nodes.csv` | 206,779 | `7810db71c87e33686c6af05d713826c8f551ccb39bb494290940dd555d258f33` |
| `pile_reactions.csv` | 619 | `a4bc5ffef53bccacd182ef0053a374f9e91275756159320ee0ab0ff0aa8e57b6` |
| `pilecap_config.json` | 2,270 | `12d4d272d033ff393ee7a98ca1d9733f9cfece0035971555722fa2d14ac2bb88` |
| *(tidak disalin)* `…Static Load.mec` | 2,253,070 | `7a1694cf78edf1ceb3adb7ab87f925f83e6897a39bb124cfd183d6ba85afa91a` |

### `ex04/`

`pilecap_config.json` dan `pile_reactions.csv` di sini **byte-identik** dengan
`examples/ex04_pile_overlap_pier/` — diperiksa, bukan diasumsikan. Model Midas-nya karena
itu memang berasal dari contoh yang dikirim ke pengguna, bukan dari varian yang disetel
khusus agar cocok.

| Berkas | Byte | sha256 |
|--------|-----:|--------|
| `elements.csv` | 259,470 | `c222b0684bbe2c7b720a70e55d3164b6f4d03fe3889905c8dbc4724eed383b2e` |
| `geometry.json` | 1,919 | `cb0f478f185764959056d53d9e27a023b10e57f9c638c5b5a8862057477bbcac` |
| `midas_displacement.csv` | 299,346 | `1f32dcfb025772b134fe07fc37291ebde776521c70a1ace477acbc1bfa6bde47` |
| `midas_force_global.csv` | 2,735,671 | `299da1ad8b21daf98bdb000aa8a95e705707d683500cbd67d62b6ca14a165f76` |
| `midas_force_local.csv` | 2,746,474 | `71d8c131a98f6e2834940c4761e51fcb4e7f072a998fdd13b85eea37fddc3222` |
| `midas_reaction.csv` | 31,559 | `70bcec50aed148ec338397bdcb05a33d3256222c2cc9bd84929a81505bb226c5` |
| `midas_solver.log` | 1,485 | `2636ad3f3862cda747be46c77df82a5a5d658c92a600f0ab7c0b4932a311f190` |
| `midas_solver.out` | 3,964 | `7755eefa6e624e2f6a3736eaafadffd858cc4837b272dee4edb24150e81846c2` |
| `nodes.csv` | 139,352 | `7c7f1fc4d82c152c07d027624f69356a6b924ef7ce03cff2c4676b80ed9f6711` |
| `pile_reactions.csv` | 306 | `af352779c53dcd956fc8cc1716133e82b60ce4133fc4a273fa8938a09cfc6597` |
| `pilecap_config.json` | 2,137 | `896e9e38af1a341c234cad85ebd1de2e126885955ee8cbc4725bf7d8651ca224` |
| *(tidak disalin)* `…Static Load.mec` | 1,454,252 | `7654d4c385527feed9c0c53aafba5752ce364855c3547f2ebadd219b0b7ded81` |

## 7. Angka terukur VC-6

Diukur ulang saat ex04 ditambahkan (4 contoh × 2 kombinasi). Kolom "gate" adalah batas di
`tests/test_validation_cases.py`; marginnya sengaja 3–7×, dan **tidak boleh dilonggarkan
tanpa mengukur ulang keempatnya**.

| Jalur | Besaran | Terburuk ex01–03 | Terburuk ex04 | Gate |
|-------|---------|-----------------:|--------------:|-----:|
| 1 | Momen `m_xx`/`m_yy`/`m_xy` | 0,144% | 0,134% | 1,0% |
| 1 | Geser `q_x`/`q_y` | 0,265% | 0,114% | 1,5% |
| 1 | Momen **puncak** | 0,515% | 0,378% | 2,0% |
| 2 | Lendutan `uz` per node | 0,216% | **0,258%** | 1,0% |
| 3 | Reaksi `Rz` per node | 0,539% | 0,088% | 1,5% |
| 3 | `Σ FZ` vs `Σ Pz` | ~6e-9 | ~4e-12 | 1e-4 |
| — | Rotasi lokal→global | 2e-6 | 1,3e-6 | 1e-4 |

Korelasi minimum pada seluruh jalur ex04: 0,999942 (`m_xy`), gate 0,999.

Lendutan ex04 yang menjadi terburuk **bukan** tanda ketidaksesuaian: ia dibatasi resolusi
ekspor 1 µm yang setara 0,91% pada contoh sekaku itu (§5.2).

