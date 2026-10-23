# Changelog

Format mengikuti template PRD Bagian 16C.

## [Unreleased]

### Fixed — `design.phi_shear` tidak dipakai untuk menghitung sengkang

`design.phi_shear` hanya mengubah `φV_c` yang dilaporkan dan vonis "perlu sengkang". Luas
sengkang (`A_v/s`), ambang `0,5 φV_c`, dan vonis BADAN HANCUR dihitung
`shell_kit.rebar.calc_shear_Av_per_s`, yang tidak menerima φ dan selalu memakai 0,75.

DIUKUR (`f'c` 30 MPa, `f_y` 420 MPa, `d` 1000 mm, `V_u = 1,5 V_c`): `phi_shear: 0.60` memberi
`A_v/s` **2,217** alih-alih **3,326 mm²/mm** — sengkang 33% lebih sedikit daripada yang
dimaksud pengguna, tanpa peringatan. Hanya berdampak bila `phi_shear` diisi selain 0,75;
config dengan `phi_shear` kosong (bawaan, termasuk seluruh contoh) tidak berubah.

Diperbaiki tanpa menulis ulang rumus shell-kit: φ hanya muncul di sana dalam bentuk `V_u/φ`,
jadi shell-kit diberi `V_u' = V_u · 0,75/φ`, yang menghasilkan rumus dengan φ pengguna secara
persis. Berlaku untuk cek penampang kritis maupun peta sengkang per elemen. Test baru memeriksa
24 kombinasi φ × `V_u` di keempat rezim (tanpa sengkang, `A_v,min`, sengkang nyata, badan
hancur) terhadap rumus SNI yang disusun dari blok bangunan shell-kit; 9 di antaranya terbukti
merah pada perilaku lama.

### Added — rumus tulangan di README

Bagian baru "Rumus perhitungan tulangan" memuat rumus lentur, geser, dan `V_n,maks` persis
seperti yang dihitung shell-kit, masing-masing dengan nama fungsinya. Setiap rumus diperiksa
menghasilkan angka identik dengan fungsi shell-kit-nya. `V_n,maks` tidak dihitung kode sebagai
angka tersendiri; yang diperiksa adalah `V_s ≤ V_s,maks`, yang setara dengan
`V_n ≤ V_n,maks = 0,83 √f'c b_w d_v` (λ = 1).

## [0.15.0] — 2026-10-23 — antarmuka desktop ketiga (PySide6), eksperimental

### Added — `pilecap-qt`, antarmuka desktop ketiga (PySide6), EKSPERIMENTAL

Disediakan untuk **dibandingkan** dengan `pilecap-gui` (wxPython) dan `pilecap-ui`
(Streamlit) sebelum salah satunya dipilih. Tidak ada antarmuka yang dihapus; ketiganya dapat
dijalankan berdampingan (`uv sync --extra qt`, lalu `uv run pilecap-qt`).

Extra `qt` memasang `pyside6-essentials`, bukan `pyside6`: paket utuh ikut menarik WebEngine,
PDF, dan Addons — unduhan ±244 MB berbanding ±79 MB (DIUKUR), tanpa satu pun dipakai.

Yang berbeda dari jendela wx, dan menjadi bahan perbandingannya:

* Teks bantuan dirender sebagai **markdown** (`**satu**` tampil tebal), bukan mentah.
* Warna teks diturunkan dari palet aktif, sehingga terbaca di **mode gelap** Windows yang
  diikuti Qt. Warna tetap untuk latar terang (`#606060`) nyaris hilang di latar gelap --
  terlihat pada tangkapan layar pertama antarmuka ini.
* Teks bantuan membungkus sendiri mengikuti lebar jendela; jarak label dan kotak diatur
  `QFormLayout`, bukan sizer yang disusun tangan seperti sumber bug v0.14.1.
* Uji asapnya berjalan **tanpa display** (`QT_QPA_PLATFORM=offscreen`).

### Changed — logika desktop bersama diekstrak dari `wxgui/main.py`

Supaya antarmuka kedua tidak menyalin pesan galat, aturan kode keluar, dan penyusunan
perintah, logika non-widget jendela wx pindah ke `ui/desktop.py` (tanpa toolkit), dipakai wx
maupun Qt: pemuatan config, status folder input, pratinjau geometri, penyiapan run, dan pesan
hasil per kode keluar. `pilihan_aman` dan `teks_angka` pindah ke `ui/formstate.py`. Perilaku
wx tidak berubah; dijaga uji asap wx yang sudah ada.

### Catatan teknis — diukur, bukan diasumsikan

* **QtSvg merender ilustrasi dengan benar** pada platform Windows — label `<text>` dan warna
  dari blok `<style>` utuh, berbeda dari `wx.svg`. Antarmuka Qt tetap memakai PNG dari
  `ui/rasterize.py` supaya ketiga antarmuka menampilkan gambar yang sama dengan PDF.
* **Platform `offscreen` Qt tidak punya font** (0 keluarga, berbanding 446 pada platform
  Windows), sehingga render teks yang diuji di sana tampil sebagai kotak kosong. Uji Qt karena
  itu tidak menguji ukuran teks dalam piksel.
* Jendela Qt terbangun dalam ±1,0 s, setara wx (±1,1 s). Run pertama sesudah memasang PySide6
  makan ±9 s — ongkos sekali, tidak berulang pada run berikutnya.

## [0.14.1] — 2026-10-22 — jarak antar field di jendela desktop

Dilaporkan pengguna lewat tangkapan layar: pada `pilecap-gui`, jarak antar field terlalu
berjauhan.

### Fixed — margin bawah ~270 px di bawah setiap field

Teks bantuan ditambahkan dengan `wx.LEFT | wx.BOTTOM` dan **satu** nilai border. Border itu
berlaku ke kedua sisi, sehingga margin bawahnya ikut sebesar pergeseran kiri (242 px).
Tinggi satu baris field terukur **330-430 px** untuk isi yang hanya ~85 px; kini 71-84 px.
Isi halaman "Desain - umum" turun dari 2392 px menjadi 566 px.

Pergeseran kiri kini lewat spacer, bukan border. Pesan galat daftar pilihan memakai pola
yang sama dan ikut diperbaiki.

### Fixed — teks bantuan terpotong di sisi kanan

Teks dibungkus pada lebar tetap 620 px, sehingga terpotong pada jendela yang lebih sempit
dari ukuran bawaan. Kini lebarnya mengikuti halaman, termasuk saat jendela diubah ukurannya.
Ruang untuk scrollbar selalu disisihkan: mengukurnya hanya saat tampil membuat lebar yang
dihitung bergantung pada scrollbar, yang kemunculannya bergantung pada tinggi isi, yang
bergantung pada lebar itu -- sebuah lingkaran yang berayun tanpa henti.

### Changed

* Kolom label dipersempit dari 260 ke 230 px. Label terpanjang terukur 207 px, jadi kolom
  lama meninggalkan celah lebar antara label pendek dan kotak isiannya.
* Penanda "di-override CSV" disembunyikan saat kosong, bukan menyisakan satu baris kosong di
  halaman Pilecap, Pile, dan Pier.

### Test

Dua test baru menjaga tata letak. `test_tinggi_baris_field_tidak_membengkak_oleh_margin`
terbukti **merah** pada margin yang dirusak lagi ("baris setinggi 283px untuk isi 37px"),
sehingga ia benar-benar menangkap bug ini.

### Belum diperbaiki

Teks bantuan di jendela desktop masih menampilkan tanda markdown mentah (mis. `**satu**`),
karena teks itu ditulis untuk Streamlit yang merendernya.

## [0.14.0] — 2026-10-21 — antarmuka desktop sebagai frontend kedua

Pemicunya panduan mandiri 0.12.0, yang dibuat untuk pembaca yang tidak dapat membaca README
di GitHub. Bagi mereka, satu-satunya antarmuka grafis yang ada masih menuntut hal yang
janggal: menyalakan server lalu membuka peramban ke `localhost`.

### Added — `pilecap-gui`, jendela aplikasi native

Antarmuka wxPython sebagai **frontend kedua yang berdiri sendiri**. Streamlit tetap ada dan
tetap berfungsi tanpa perubahan perilaku: mengganti sekaligus berarti mempertaruhkan
satu-satunya antarmuka grafis yang sudah teruji demi yang belum ada.

| | Jendela aplikasi | Formulir peramban |
|---|---|---|
| Extra | `gui` (wxPython) | `ui` (Streamlit) |
| Perintah | `pilecap-gui` | `pilecap-ui` |
| Port jaringan | tidak ada | `localhost:8501` |

Kedua extra terpisah satu sama lain: pemakai jendela tidak ikut menarik server Streamlit.

### Changed — logika bersama diekstrak supaya kedua antarmuka tidak dapat menyimpang

Yang semula ditulis inline di `ui/app.py` kini jadi modul tanpa toolkit, dipakai keduanya:

* `ui/runopts.py` — sepuluh opsi run sebagai `schema.Field`, sehingga **satu loop perender
  melayani bagian skema maupun opsi run**. Sebelumnya opsi run punya prosa bantuan dan kunci
  `dest` yang ditulis tangan; salinan kedua akan menyimpang dan flag yang tidak dikenal baru
  ketahuan saat run gagal di tangan pengguna.
* `ui/formstate.py` — visibilitas bersyarat, label satuan, koersi angka.
* `ui/detect.py` — deteksi berkas input berikut penanganan pola ambigu.
* `ui/runner.py` — subprocess CLI. Memuat lima hal rapuh yang sebelumnya hanya ada di
  `app.py`: penyaring derau tqdm, batas baris log, keharusan menguras stdout, pengangkatan
  baris `GAGAL:` ke atas log, dan perintah proses anak itu sendiri.

Kesetaraan keduanya diverifikasi dengan membandingkan `pilecap_config.json` yang
**benar-benar ditulis** masing-masing antarmuka untuk masukan yang sama: identik byte demi
byte.

### Fixed — satu duplikasi laten di halaman Streamlit

`ui/app.py` mengetik ulang `{"length": "mm", "force": "kN", "stress": "MPa"}`, menduplikasi
`config.DEFAULT_INPUT_UNITS`. Kini diturunkan, sehingga label satuan tidak dapat menyimpang
diam-diam begitu bawaannya berubah.

### Catatan teknis — dua hal yang diukur, bukan diasumsikan

**Ilustrasi tidak dapat dirender `wx.svg`.** Upaya pertama memakainya dan gagal secara
diam-diam. `wx.svg` memakai nanosvg, yang tidak merender `<text>` dan tidak membaca blok
`<style>` berkelas — dan seluruh ilustrasi di repo ini memakai keduanya. Hasil render
`sistem-koordinat.svg` diukur: tiga kepala panah di atas bidang hitam, tanpa satu pun dari
18 labelnya. Gambar tanpa label bukan versi sederhana dari gambarnya, ia gambar yang lain.
Rasterisasi karena itu lewat Typst, yang sudah terkunci sebagai dependency dan sudah merender
ilustrasi yang sama untuk laporan PDF; hasilnya di-cache (`ui/rasterize.py`).

**Field angka tidak dapat memakai `wx.SpinCtrlDouble`.** Kontrol itu menurunkan jumlah
desimalnya dari `inc`, dan dengan `inc` berapa pun yang masuk akal di sini ia melaporkan
`digits=0` — sehingga `0.05` dibacanya `0.0` dan `27.5` dibacanya `28.0`, tanpa peringatan.
Pada rasio redaman dan tebal pelat, nilai yang berubah diam-diam saat config dimuat adalah
kegagalan terburuk yang bisa dipunyai alat ini: hasilnya tetap keluar, tetap tampak wajar,
dan salah. Seluruh field angka karena itu kotak teks dengan koersi terpusat.

### Test

Dua aturan rumah yang sebelumnya **terdokumentasi tetapi tidak dijaga satu test pun** kini
ditegakkan lewat pemeriksaan AST: hanya `ui/wxgui/` yang boleh mengimpor `wx`, dan `ui/wxgui/`
tidak boleh mengimpor engine di tingkat modul.

## [0.13.2] — 2026-09-14 — pile yang seluruhnya berada di bawah pier dapat dianalisis

Dilaporkan pengguna: pilecap 4800 x 4800, tebal 1500, grup pile 3 x 3 berspasi 1800 --
pile tengahnya tepat di bawah pier -- **tidak dapat dianalisis dengan config apa pun**.

### Fixed — konfigurasi yang sangat lazim terkunci di jalan buntu

Pile tengah grup 3 x 3 yang tepat di bawah kolom punya fraksi tumpang tindih 100%. Tiga
kemungkinan config, ketiganya ditolak:

| `max_pile_overlap_fraction` | Ditolak karena |
|---|---|
| kosong | ada tumpang tindih |
| 0.99 | tumpang tindihnya 100%, melebihi batas |
| 1.0 | validator mensyaratkan batas **< 1** |

Pesan galat baris kedua bahkan menyarankan "naikkan batasnya bila memang disengaja" --
padahal satu-satunya nilai yang cukup ditolak baris ketiga. Field `pilecap-ui` pun sudah
mengizinkan `max_value = 1.0`, lalu validatornya menolak nilai yang diterima formulirnya
sendiri.

Batas `< 1` ternyata tidak melindungi dari model yang tidak sah, melainkan dari **crash**.
Pada tumpang tindih penuh, bagian cakram di luar pier kosong, sehingga gmsh tidak membuat
group `PILE_*` sama sekali -- hanya group lensanya -- dan `fem_engine.pile_pressures`
berhenti dengan `KeyError`. Rumus bebannya sendiri tidak perlu diubah: pada tumpang
tindih sebagian seluruh cakram SUDAH dibebani `p = Pz / A_cakram`, termasuk lensa, dan
bagian lensa terserap ke reaksi pier. Tumpang tindih penuh adalah batas yang sah dari model
itu -- seluruh `Pz` menjadi strut, pelat tidak menerima lentur dari pile tersebut.

Diperbaiki: validator menerima `0 < f <= 1`, dan `pile_pressures` memulai himpunan
elemennya dari lensa bila group pile tidak ada. Beban tetap tidak dapat hilang diam-diam:
pile yang tidak punya group pile MAUPUN lensa tetap ditolak.

DIVERIFIKASI pada konfigurasi pengguna (pile D600 dan pier 1200 x 1200 diasumsikan karena
tidak disebutkan), bukan hanya "berjalan tanpa crash":

* **VC-0 lulus** pada kedua kombinasi: 9.500 kN terapan = 9.500 kN reaksi, residu 1,4e-15.
* **P5**: fraksi 1,000, `pz_strut` = 1.500 kN (100%), `pz_ke_pelat` = 0, bocoran mesh = 0.
* **Simetri**: momen di muka pier +650 / -650 mm = 1.324 / 1.309 kNm/m (selisih 1,1%).
* **Hitungan tangan**: tiga pile di kolom luar (3.000 kN) dengan lengan 1,2 m memberi
  3.600 kNm; tersebar selebar pier = 3.000 kNm/m, selebar pilecap = 750 kNm/m. FEM:
  1.320 kNm/m, di antara keduanya sebagaimana mestinya.
* **Pelaporan jujur**: calc sheet bagian 3a mencetak P5 dengan strut 100% dan kalimat bahwa
  kapasitasnya wajib dicek terpisah; `a/d` minimum 0,000 tercetak tanpa vonis; laporan
  `--pdf` terbit lengkap; tidak ada "nan" di keluaran mana pun.

### Fixed — dua saran di pesan galat yang tidak dapat diikuti

* **Saran batas tumpang tindih** kini menyebut nilai konkretnya dan **dibulatkan ke atas**.
  Pembulatan biasa akan menyarankan 0.07 untuk tumpang tindih 7,2% -- nilai yang tetap
  ditolak.
* **Rule 7a menolak D600 dengan mesh 100 mm**, dua angka yang sangat umum. Di floating point
  0,6 / 0,1 = 5,999999999999999 < 6, lalu pesannya menyarankan "turunkan ke <= 100 mm" --
  nilai yang sudah dipakai. Kini perbandingannya bertoleransi relatif 1e-9, yang hanya
  menyerap derau pembulatan, dan saran ukuran mesh dibulatkan **ke bawah** karena ia batas
  atas (pembulatan biasa menyarankan 109 mm untuk D651,6, yang tetap ditolak).

  Test `test_rule7a_tepat_di_ambang_lolos` yang sudah ada tidak menangkapnya: ia memakai
  0,8 / (0,8/6), yang kebetulan dibulatkan ke arah yang aman. Test baru memakai pasangan
  angka yang benar-benar diketik pengguna dan benar-benar gagal.

### Changed

`test_max_pile_overlap_fraction_di_luar_rentang_ditolak` sebelumnya MENGUNCI perilaku lama
(1,0 ditolak). Ia diubah, bukan dilewati: 1,0 kini sah, sedangkan 0, negatif, dan > 1 tetap
ditolak. README mendapat paragraf tentang pile yang seluruhnya di bawah pier, termasuk dua
konsekuensinya -- seluruh beban pile itu di luar pemeriksaan tool, dan `a/d` = 0.

## [0.13.1] — 2026-09-11 — perbandingan lendutan per node, dan bias yang ditemukannya

> **Tidak dirilis terpisah.** Versi ini tidak pernah diberi tag maupun wheel; seluruh
> isinya ikut diterbitkan dalam **0.13.2**.

Ditemukan pengguna: 0.13.0 menyebut perbandingan VC-6 "lengkap", padahal hanya Jalur 1
(resultan elemen) yang digambar. Jalur 2 -- lendutan per node -- belum ada sama sekali.

### Added — gambar perbandingan lendutan `uz`

`vc6-sebaran-uz-<slug>.png` dan `vc6-peta-uz-<slug>.png` untuk kedua kombinasi, plus subbab
"Lendutan vertikal" di Lampiran C panduan dan blok tersendiri di README.

Dua keputusan rancangan SENGAJA berbeda dari gambar gaya, dan keduanya diturunkan dari
batas ketelitian jalur ini (SUMBER.md 5.2): ekspor Midas membulatkan lendutan ke 1 µm.

* **Selisih dalam mikrometer, bukan persen terhadap puncak.** Batasnya absolut -- 0,5 µm
  pada setiap contoh -- sedangkan persen terhadap puncak membuat batas yang sama tampak
  0,02% di ex02 dan 0,45% di ex04. Dalam µm, satu pita abu-abu berlaku untuk keempat contoh.
* **Skala warna peta BERSAMA, bukan per panel.** Kebalikan dari peta gaya. DIUKUR, 90,9%
  node ex04 berselisih di bawah galat pembulatan; skala per panel akan membesarkan derau itu
  menjadi pola berwarna tajam yang terbaca seperti ketidakcocokan sungguhan.

Tabel lendutan di Lampiran C memuat kolom yang tidak ada pada tabel gaya: **pangsa node di
dalam pembulatan ekspor** -- 65,4% (ex01), 19,1% (ex02), 48,6% (ex03), 90,9% (ex04) pada
kombinasi gravitasi.

### Found — bias kecil yang sistematis pada lendutan

Gambar pertamanya memperlihatkan hal yang tidak tertangkap gate: di tempat pembulatan tidak
mendominasi, **Midas melendut sedikit lebih besar, sebanding dengan lendutannya**. DIUKUR
dengan regresi melalui titik asal: 0,077-0,084% (ex02, R² 0,32-0,61) dan 0,146-0,152%
(ex03, R² 0,63-0,68). Pada ex01 dan ex04 R²-nya 0,06-0,22, sehingga bias di sana **tidak
dapat dipastikan** -- bukan "tidak ada".

Gate VC-6 tidak menangkapnya karena memeriksa RMS dan korelasi, dan keduanya tidak peka
terhadap kemiringan yang seragam. Gambarlah yang menangkapnya -- panel kiri yang judulnya
sendiri bertanya "terpusat di nol, atau miring?".

Satu penyebab **disingkirkan**: keempat contoh memakai E = 25.000 MPa dan ν = 0,2 yang sama,
sehingga pembulatan material saat ekspor akan memberi kemiringan yang sama pada semua contoh
-- yang terukur berbeda. **Penyebab sebenarnya belum teridentifikasi**, dan dugaan tentang
perbedaan formulasi elemen sengaja tidak dikutip sebagai penjelasan.

Bias ini tidak bertentangan dengan kesesuaian momen 0,02-0,13%: pada analisis elastis
linier, perbedaan kekakuan mengubah lendutan tetapi tidak mengubah gaya yang ditentukan
keseimbangan. Ia sepuluh kali di bawah gate, dan tidak menyentuh angka desain -- tulangan
dihitung dari momen. Dicatat di SUMBER.md 5.3, docstring gate lendutan, Bab 8 dan Lampiran C
panduan, serta README.

### Fixed — docstring gate lendutan tertinggal dari SUMBER.md

Ia masih menyatakan batas resolusi "tidak lagi mengikat" pada ex03, padahal SUMBER.md 5.2
sudah mengoreksinya saat ex04 ditambahkan (ex03 terikat, meski tipis). Kelas kesalahan yang
sama dengan klaim "tepi pier" pada 0.12.1: dua tempat yang menyatakan hal yang sama, lalu
hanya satu yang diperbarui.

DIUKUR pada 0.13.1: 25 berkas perbandingan, 3,25 MB; panduan 61 halaman, 6,65 MB.

## [0.13.0] — 2026-09-11 — perbandingan VC-6 lengkap: 5 gaya x 2 kombinasi

Diminta pengguna: ketiga jenis diagram perbandingan, untuk SELURUH contoh bawaan dan
SELURUH gaya dalam, terhadap model pembanding Midas.

### Added — 20 gambar perbandingan + Lampiran C panduan

`tools/plot_vc6_perbandingan.py` kini menghasilkan, untuk tiap kombinasi beban x tiap gaya
(`m_xx`, `m_yy`, `m_xy`, `q_x`, `q_y`): gambar sebaran (struktur selisih + kurva kumulatif,
keempat contoh bertumpuk) dan peta kisi 2x2 letak selisih. Total 20 gambar plus
`vc6-ringkasan.json`.

DIUKUR pada v0.13.0: 21 berkas, **2,61 MB** seluruhnya; panduan **57 halaman, 5,54 MB**,
dibangun 0,7 detik. Jauh di bawah perkiraan 10-15 MB berkat tiga penghematan yang tidak
membuang satu elemen pun dari gambar: dihasilkan tepat pada `PDF_IMAGE_MAX_PX` sehingga
tidak ada byte yang dibayar dua kali, palet PNG dikuantisasi, dan `docs/manual/_figur_pdf/`
berhenti di-commit karena isinya turunan `docs/img/`.

Panduan mendapat **Lampiran C**; Bab 8 sengaja TIDAK berubah isinya -- tetap satu gaya pada
satu kombinasi, plus penunjuk. Menanam kedua puluh gambar di sana akan mengubur narasi
buktinya, dan jalur baca eksekutif (Bab 1, berhenti di halaman 5) harus tetap utuh.

Tabel angka di Lampiran C dibaca dari `vc6-ringkasan.json` yang ditulis skrip yang sama
dengan yang menghasilkan gambarnya. Data VC-6 tidak ikut ke dalam wheel sehingga panduan
tidak dapat menghitungnya sendiri; membacanya dari berkas yang sama membuat tabel dan
gambar tidak dapat menyimpang satu sama lain.

Peta memakai skala warna **per panel**, bukan bersama: puncak antarcontoh berbeda sampai
sepuluh kali lipat, dan skala bersama akan membuat tiga panel tampak kosong.

### Fixed — test font sesungguhnya masih menguji jam

v0.12.1 menormalkan `/ModDate` dan `/CreationDate`, dan itu tidak cukup. Typst juga menanam
stempel yang sama sebagai XMP (`xmp:ModifyDate`, `xmp:CreateDate`) DAN menurunkan tiga sidik
dokumen darinya (`/ID`, `xmpMM:InstanceID`, `xmpMM:DocumentID`). Panduan yang membesar
membuat dua kompilasinya kerap jatuh di detik berbeda, sehingga test gagal sekitar sekali
dari tiga kali dijalankan -- kegagalan sesekali yang jauh lebih menyesatkan daripada
kegagalan tetap. DIVERIFIKASI dengan memaksa jeda melewati pergantian detik: setelah
normalisasi lengkap, keluarannya identik byte demi byte.

### Fixed — dua klaim yang salah karena angkanya diketik, bukan dihitung

* Tabel Lampiran C sempat mencetak RMS `ex03` sebagai 0,056% sedangkan pengukuran langsung
  0,055%: nilainya dibulatkan dua kali, sekali saat ditulis ke JSON lalu sekali lagi saat
  dicetak. Ringkasan kini menyimpan enam desimal sehingga pembulatan hanya terjadi di
  tempat pencetakan.
* Kenaikan versi 0.12.0 -> 0.12.1 mengganti seluruh kemunculan "0.12.0" di README, termasuk
  di dalam catatan sejarah yang berbunyi "Sampai v0.12.0 docstring VC-6 keliru..." --
  sehingga catatan itu berubah menyatakan dirinya sendiri masih keliru. Dikembalikan.

Sebagai efek samping, peta keempat contoh memperlihatkan hal yang menguatkan koreksi
v0.12.1: pada SELURUH contoh, elemen dengan simpangan terbesar jatuh di tepi cakram **pile**
(P1, P6, P3, P4), bukan tepi pier.

### Changed — keterbacaan gambar

Pengguna perlu bertanya bagaimana membaca kurva kumulatifnya. Judul panel karena itu diganti
menjadi pertanyaan yang ia jawab ("Berapa persen elemen yang selisihnya di bawah sekian?"),
ditambah satu anak panah contoh baca yang angkanya dihitung, dan satu paragraf cara membaca
di pembuka Lampiran C.

## [0.12.1] — 2026-09-08 — selisih VC-6 per elemen dapat dilihat, bukan hanya diringkas

> **Tidak dirilis terpisah.** Versi ini tidak pernah diberi tag maupun wheel; seluruh
> isinya ikut diterbitkan dalam **0.13.0**. Entrinya dipertahankan karena mencatat
> perbaikan yang berdiri sendiri -- klaim keliru "tepi pier" pada docstring VC-6.

Ditanyakan pengguna: apa arti kolom "RMS terburuk", dan dapatkah selisih per elemen
terhadap Midas Civil digambarkan supaya dapat dibandingkan sendiri.

### Added — `tools/plot_vc6_perbandingan.py` dan dua gambar perbandingan

Satu angka RMS dapat menyembunyikan dua hal yang justru menentukan kepercayaan: apakah
selisihnya terpusat di nol tanpa kemiringan sistematis, dan DI MANA simpangan terbesarnya
berada. Dua gambar baru menjawab keduanya, dan kini ditanam di README serta bab
"Bukti dan validasi" panduan.

`vc6-perbandingan-sebaran.png` -- panel kiri memplot selisih tiap elemen terhadap besar
nilainya; yang dibaca bukan sempitnya sebaran melainkan bahwa titiknya terpusat di garis
nol tanpa kemiringan. Panel kanan membaca sebaran yang sama secara kumulatif: DIUKUR,
separuh elemen menyimpang < 0,03% dan 99% < 1%.

Rancangan panel kiri sempat berupa scatter "Midas vs kami". Itu dibuang: pada ketelitian
setinggi ini seluruh titiknya runtuh ke garis `y = x`, sehingga gambarnya memakan separuh
ruang tanpa memberi tahu apa pun selain "cocok".

`vc6-perbandingan-peta.png` -- letak selisih pada denah, memakai kasus PALING BURUK
(`ex02`, `q_y`, simpangan maksimum 7,75%), bukan yang paling rapi. Simpangan terbesar
terkonsentrasi di tepi cakram pile dan sekitar pier, tempat beban dan tumpuan berhenti
mendadak; di seluruh bidang pelat lainnya -- tempat angka desain sebenarnya diambil --
selisihnya nyaris tidak terlihat.

Skripnya memakai ulang `validation_helpers` yang dipakai test, bukan pembaca Midas kedua.
Menulis pembaca kedua berarti dua jalur yang dapat menyimpang diam-diam, dan gambar yang
menyatakan kesesuaian LEBIH BAIK daripada yang sesungguhnya diuji jauh lebih buruk daripada
tidak ada gambar. Ia skrip, bukan bagian paket, karena `tests/data/vc6/` tidak ikut ke
dalam wheel; gambarnya dihasilkan sekali lalu di-commit ke `docs/img/`.

### Fixed — VC-6 keliru menyebut elemen terburuk berada di tepi pier

Docstring `test_vc6_resultan_elemen_cocok_dengan_midas` menyatakan simpangan 7,7% pada
`ex02 q_y` terjadi "di singularitas tepi pier". DIUKUR, elemen itu berada **44 mm di luar
tepi cakram pile P6**, sedangkan tepi pier 205 mm jauhnya.

Kekeliruan ini ditemukan justru karena label pada gambar peta DITURUNKAN dari
`geometry.json` alih-alih diketik: label yang diketik tangan lebih dulu ditulis "tepi pier"
mengikuti docstring, lalu angka yang dihitung membantahnya. Label itu kini selalu diturunkan,
sehingga tidak dapat lagi menyimpang bila kasus atau medan yang dipetakan diganti.

### Changed — test wheel menjaga SELURUH gambar yang ditanam panduan

Sebelumnya hanya berkas `Section.illustration` yang diperiksa, sehingga gambar di luar itu
(perbandingan VC-6, contoh basis desain) dapat luput dari pengemasan. Daftarnya kini
diturunkan dari sumber panduan yang benar-benar dihasilkan, bukan diketik ulang di test --
daftar kedua akan tertinggal begitu sebuah gambar ditambahkan, dan kegagalannya hanya
menimpa pengguna wheel berupa kotak "GAMBAR TIDAK TERSEDIA" pada bab yang seharusnya
membuktikan angkanya dapat dipercaya.

Panduan kini 41 halaman, 1,78 MB (dari 40 halaman / 1,16 MB pada 0.12.0).

## [0.12.0] — 2026-09-08 — panduan mandiri `pilecap-manual`

Diminta pengguna: satu dokumen lengkap tentang tool ini -- asumsi, keterbatasan, cara
pakai, sampai keluaran -- untuk dikirim ke calon pengguna yang **tidak dapat membaca
README di GitHub atau tidak paham GitHub sama sekali**, dan ke eksekutif perusahaan yang
menilai adopsi.

### Added — command keenam `pilecap-manual`

```bash
pilecap-manual --out docs/manual        # -> panduan_pilecap_fem.typ + .pdf
```

DIUKUR pada v0.12.0: **39 halaman, 0,74 MB, 0,5 detik**, nol warning Typst. Ukurannya
disengaja: hanya 7 ilustrasi (6 SVG vektor + 1 PNG), bukan ratusan kontur seperti laporan
run, karena kanal edarnya adalah surel.

Kerangkanya: ringkasan eksekutif yang tuntas dan berhenti di ±halaman 5 (apa yang
dikerjakan, apa yang **tidak**, tingkat pertanggungjawaban, bukti validasi, kebutuhan
penerapan, pernyataan tanggung jawab), pemasangan langkah demi langkah untuk orang yang
belum pernah membuka terminal, contoh bawaan, penyiapan data, referensi **seluruh 60 field
dalam 11 bagian**, dasar teori, keluaran, bukti dan validasi, keterbatasan, tanggung jawab,
dan dua lampiran.

Dokumen ini **dihasilkan dari kode**, bukan ditulis tangan. Alasannya bukan selera: proyek
ini sudah berulang kali digigit dokumentasi yang tertinggal (tabel perbandingan README,
caption plot, rujukan "Bagian 7", catatan sengkang). Versi, daftar field, pasal SNI,
keterbatasan, item terbuka, dan pin dependency ditarik hidup-hidup saat dokumen dibangun.
Prosa authored yang berpasangan dengan data hidup dikunci ke himpunan kunci hidupnya
(`EXAMPLE_NAMES`, `FILE_PATTERNS`, `OPEN_BLOCKERS`, entry point), sehingga penambahan baru
**meledak saat panduan dibangun** alih-alih hilang diam-diam. Terbukti bekerja saat
pengembangan: kunci `FILE_PATTERNS` yang salah ketik menghentikan build, bukan menghasilkan
tabel yang kurang dua baris.

`pilecap-manual` ikut di dalam wheel, bukan sekadar skrip repo. Itu akar perbaikan untuk
risiko PDF beku: penerima wheel dapat menghasilkan panduan yang cocok dengan versi yang
benar-benar ia pasang. Sampul, footer setiap halaman, dan bab pemasangan menyuruh pembaca
mencocokkan `pilecap-run --version` dengan nomor di sampul.

Paket `pilecap_fem/manual/` sengaja terpisah dari `reporting_pdf/`: paket itu memegang
invarian bahwa seluruh isinya adalah penyusunan ulang SATU run, dan generator tanpa run di
dalamnya akan melemahkan satu-satunya invarian yang melindungi dokumen bertanda tangan.
Arah impornya satu arah, dijaga `test_reporting_pdf_tidak_mengimpor_manual`.

### Fixed — nomor subbab yang di-hardcode di dalam prosa `theory.py`

`chapter_theory` menulis "konvensi yang ditetapkan pada Subbab 2.2" -- benar hanya selama
bab itu kebetulan menjadi Bab 2. Di panduan ia Bab 6, sehingga rujukannya salah. Ini kelas
kesalahan yang **sama persis** dengan rujukan "Bagian 7" yang diperbaiki di v0.11.3, dan
perbaikannya juga sama: label `<teori-konvensi-tanda>` plus rujukan yang dapat diklik.
Laporan run ikut terperbaiki.

Akar pencegahannya bukan perbaikan itu sendiri melainkan
`test_setiap_rujukan_silang_di_panduan_punya_label_tujuannya` beserta kembarannya untuk
laporan run: keduanya menuntut setiap `#link(<label>)` punya heading tujuannya. Dua dokumen
kini memakai ulang bab yang sama, sehingga sebuah bab dapat merujuk label yang hanya ada di
salah satunya -- kegagalan yang tidak terlihat sampai PDF-nya dibuka orang. Test itu juga
yang memaksa panduan benar-benar menyediakan `<lampiran-provenance>` dan
`<bab-keterbatasan>`, dua tujuan yang dirujuk `chapter_theory` keluar dari dirinya.

### Changed — penekanan HURUF KAPITAL di prosa `ui/schema.py` menjadi `**tebal**`

31 penekanan pada 21 field dan 8 bagian. Prosa `help=` ditulis ketika ia hanya tampil di
formulir Streamlit; kini ia juga tercetak di panduan PDF, tempat proyek ini sudah
memutuskan (v0.11.1) bahwa kapital mendadak diganti tebal berwarna. Akronim teknis (MITC,
DOF, DKGQ, ACI, BjTS, `DEFAULT_FY`) sengaja dibiarkan -- di sana kapital memang ejaannya.
Formulir ikut membaik: Streamlit merender `**tebal**` sebagaimana mestinya.

### Changed — `chapter_limitations` tidak lagi menerima `ReportData`

Seluruh isinya statis kecuali catatan opsi yang dilewati, sehingga kini bertanda tangan
`chapter_limitations(*, no_rebar_plots=False, no_envelope=False)` dan dapat dipakai apa
adanya oleh panduan. Logika kompilasi Typst diekstrak menjadi
`reporting_pdf.document.compile_document()`, sehingga panduan mewarisi perlakuan yang sama
terhadap kegagalan: sumber `.typ` selalu ditulis lebih dulu, PDF yang terkunci penampil
dikenali, setiap warning dicatat. Komentar kepala preamble dan footer halaman
diparameterkan -- komentar yang menyebut perintah keliru menuntun pembaca menimpa dokumen
lain. DIVERIFIKASI: `.typ` laporan run yang dihasilkan ulang identik byte demi byte
kecuali dua baris rujukan yang memang diperbaiki.

### Added — `typst_kit.code_block()` dan `typst_kit.url()`

Bab instalasi seluruhnya berisi perintah, sedangkan `from_markdown` sengaja **menolak**
blok kode berpagar. `code_block()` merendernya sebagai `raw`, dengan alasan yang sama
seperti raw span pada `esc()`: tipografi Typst mengubah `--` menjadi en dash, sehingga
`--python 3.12` yang disalin pembaca menjadi perintah yang tidak berjalan.

`config.wheel_url()` menjadi satu-satunya sumber alamat unduhan, dan
`test_url_wheel_di_panduan_sama_dengan_yang_di_readme` menagih README agar cocok --
menjadikan suntingan tiap rilis diperiksa, bukan diingat.

## [0.11.3] — 2026-08-26 — `--pdf` gagal pada pile yang tumpang tindih dengan pier

Dilaporkan pengguna: `TypstMarkupError: heading Markdown di dalam blok prosa` pada baris
`### 3a. Beban pile yang TIDAK melenturkan pelat (tumpang tindih dengan pier)`.

### Fixed — `reporter.overlap_block` dirutekan lewat konverter yang salah

Fragmen calc sheet yang membawa heading bernomor sendiri (`stirrup_section`,
`capacity_provenance_table`, `traceability_block`, dan `overlap_block`) WAJIB melewati
`chapters._md_body()`, yang membuang heading itu sebelum konversi -- bukan `_md()`, yang
justru dirancang RAISE pada heading tak terduga di prosa lain. `overlap_block` (bagian
"3a", hanya muncul bila ada pile yang menindih pier) terlewat saat `chapters.py` ditulis,
karena `ex01`/`ex02` -- contoh yang dipakai mengembangkan fitur PDF -- tidak punya
tumpang tindih pile-pier, sehingga fungsinya selalu mengembalikan string kosong di kedua
run itu dan baris ini tidak pernah benar-benar dieksekusi. Baru meledak pada model
dengan overlap nyata.

Diperbaiki: dirutekan ke `_md_body()`, plus heading Typst asli level-3 ditambahkan
sebelum kontennya -- bukan sekadar dibuang -- supaya sub-bagian "Beban pile yang tidak
melenturkan pelat" tetap punya entri sendiri di Daftar Isi, sama seperti "Tulangan geser
(sengkang)" pada bagian lain. Direproduksi dan diverifikasi pada `ex04_pile_overlap_pier`
(satu-satunya contoh bawaan dengan overlap nyata): PDF 41 halaman berhasil dibuat,
Tabel 4.1.1 tampil benar. Dijaga
`test_overlap_block_meledak_lewat_md_biasa_tetapi_aman_lewat_md_body`.

Ditemukan oleh pengguna: plot diameter sengkang mode spasi tetap tidak menyebut spasi
yang dipakai. Sengkang hanya punya SATU mode -- `stirrup_spacing_long`/
`stirrup_spacing_trans` ditetapkan pengguna, tool memilih diameter yang memenuhinya --
dan nilai itu sebelumnya hanya tercetak di `calc_sheet.md` bagian 7b (Markdown), tidak
pernah di plot itu sendiri. Plot `Av/s` dan diameter sengkang (per kombinasi maupun
envelope) kini menyertakan baris "Grid sengkang (spasi tetap, ditetapkan pengguna):
{long} x {trans} mm." di kop gambar. Dijaga
`test_plot_sengkang_menyebut_grid_spasi_yang_dipakai`.

## [0.11.1] — 2026-08-19 — Rujukan dapat diklik, penekanan tanpa kapital, envelope tulangan lengkap

Ditemukan lewat peninjauan visual PDF hasil `ex01` sebelum rilis, bukan lewat kode.

### Fixed — bab 6 Envelope hanya menampilkan 4 dari 12 gambar tulangan

`Envelope/` sudah berisi 12 PNG tulangan (4 `As` + 4 batang terpilih + 4 sengkang) sejak
v0.10.0, tetapi `chapter_envelope` hanya merujuk keempat `As`-nya. Delapan gambar
lain -- peta diameter/spasi batang dan `Av/s` sengkang -- sudah ada di disk dan tinggal
dirujuk, tetapi tidak pernah dirujuk. Pembaca melihat `As` envelope tanpa melihat batang
apa yang memenuhinya. Diperbaiki: bab ini sekarang menyusun daftar gambar dengan pola
yang sama dengan bab per kombinasi (`_selection_kinds` membaca `RebarSelection.kind` yang
sudah ada, bukan menebak ulang dari `rebar_mode`). Dijaga
`test_bab_envelope_memuat_seluruh_gambar_tulangan`, yang mengunci angka 12.

### Added — rujukan silang antar-bab dapat diklik

`typst_kit.heading()` menerima `label=`, dan prosa merujuknya lewat sintaks tautan
Markdown `[teks](#label)` yang diterjemahkan `#link(<label>)[teks]`. Ditulis sebagai
tautan Markdown, bukan `tk.ref()` yang disambung langsung ke string: percobaan pertama
menyambungnya sebagai literal Typst gagal diam-diam -- string itu tetap melewati
`from_markdown`, yang meng-escape `#`/`<`/`[`, sehingga tautannya tercetak sebagai teks
mati `\#link(\<bab-teori\>)[...]`. Dijaga
`test_rujukan_markdown_menjadi_tautan_yang_dapat_diklik`.

### Changed — penekanan penting tidak lagi lewat HURUF KAPITAL mendadak

`**tebal**` sekarang diterjemahkan `#tegas[...]` (tebal + warna biru gelap), bukan
`*tebal*` Typst biasa. Menggantikan pola lama yang menandai kalimat penting dengan
kapital di tengah prosa (`TIDAK SAH`, `ZONA`, `UKURAN ELEMEN`, `ARAH GALATNYA TIDAK
AMAN`) -- kapital mendadak memutus alur baca dokumen yang ditandatangani dan terbaca
seperti membentak. `config.KNOWN_LIMITATIONS` (PRD Bagian 8.3, direproduksi apa adanya
di setiap laporan) ikut ditulis ulang ejaannya: **tidak ada kata yang ditambah, dihapus,
atau diubah maknanya** -- hanya kapital yang dipindah ke `**tebal**`. Perubahan ejaan itu
otomatis ikut memperbaiki `calc_sheet.md` dan `SUMMARY.md`, bukan cuma PDF.

Sekalian: `#show table.cell: set par(justify: false)` -- rata kanan-kiri di dalam sel
tabel sempit merenggangkan header ("maks␣␣abs␣␣m_x") menjadi celah lebar yang tidak
terbaca sebagai satu frasa.

### Added — `--pdf`: satu dokumen lengkap, dengan dasar teori dan seluruh diagram

Sebelumnya keluaran hanya Markdown (`calc_sheet.md` per kombinasi, `SUMMARY.md`) plus
ratusan PNG tersebar di folder run. Untuk dokumen yang **ditandatangani dan diserahkan** itu
belum cukup: pembaca harus membuka belasan berkas dan merakit sendiri konteksnya, dan tidak
ada satu artefak pun yang memuat dasar teori beserta sumber tiap rumusnya.

`--pdf` (opt-in, pada `pilecap-report` maupun `pilecap-run`) menghasilkan **satu PDF untuk
seluruh run**: sampul, daftar isi, ringkasan eksekutif, dasar teori, data masukan, satu bab
per kombinasi, envelope, keterbatasan, pernyataan tanggung jawab, dan lampiran provenance.
Seluruh diagram yang sudah dibuat menjadi gambar bernomor dengan caption yang menyebut
kombinasi dan **CSV sumber angkanya**.

**Kompilasi terjadi di dalam Python.** Dipakai ulang `shell_kit.pdf` — `compile_to_pdf`
(binding native Typst, **tanpa biner luar**), `downscale_figure`, dan `PRINT_FIGURE_DIR` —
bukan membangun pipeline kedua. Yang ditulis sendiri hanya isinya, karena
`shell_kit.reporting_typst` berbentuk model data shell-kit, bukan pilecap.

**Angka PDF dan calc sheet dijamin sama OLEH KONSTRUKSI.** `_report_one_combo` dulu
menghitung `designs`, `selections`, `shear_maps`, `trace`, dan seterusnya, menyerahkannya ke
`write_calc_sheet`, lalu **membuang semuanya kecuali `results`**. PDF karena itu hanya punya
dua pilihan buruk: menghitung ulang (dilarang aturan `exporters/__init__.py` — penyaji tidak
pernah menghitung ulang besaran rekayasa) atau membaca balik CSV yang sudah dibulatkan ke
satuan tampilan dan tidak membawa `as_min`, `phi_v_c`, `labels`, maupun `status`. Keduanya
melahirkan jalur angka ketiga yang dapat menyimpang diam-diam.

Diselesaikan dengan `reporter.CalcSheetInputs`: satu objek berisi seluruh masukan calc
sheet, dikembalikan `_report_one_combo` dan dipakai ULANG oleh PDF. Nol perhitungan ulang,
dan tanpa `--pdf` biayanya nol byte. `test_ringkasan_pdf_cocok_dengan_summary_md`
membandingkan `As` governing yang terparsing dari kedua dokumen sebagai penjaga divergensi.

**Blok prosa liabilitas tidak disalin.** `config.KNOWN_LIMITATIONS`, disclaimer,
`OPEN_BLOCKERS`, dan peringatan deep pilecap diterjemahkan saat pembuatan dokumen lewat
`typst_kit.from_markdown`, sehingga sumbernya tetap satu. Konverter itu **sempit dan galak**:
ia menerima persis konstruksi yang dipakai blok-blok tersebut dan **RAISE** pada yang lain --
konstruksi asing yang dijatuhkan diam-diam berarti kalimat peringatan hilang dari dokumen
tercetak tanpa satu pun tanda.

**Urutan yang dijaga:** peringatan deep pilecap dan catatan pons SELALU mendahului tabel
`As`, sama seperti di Markdown, dan diuji lewat offset karakter pada `.typ`.

**Yang TIDAK dicetak:** data per elemen. Tabel memuat nilai governing dan ekstrem beserta
lokasinya; data lengkap tetap di CSV yang namanya disebut di dokumen. `ex01` punya ribuan
elemen — mencetaknya menghasilkan dokumen yang tidak terbaca.

**Gambar yang tidak ada tidak pernah dihilangkan diam-diam** — ia muncul sebagai kotak yang
menyebutkan berkasnya, alasannya, dan cara memunculkannya (`--no-rebar-plots`,
`--no-envelope`, `--no-save-raw`, atau opsvis yang dilewati di atas ambang elemen).

**`PDF_IMAGE_MAX_PX` DIUKUR, bukan diwarisi.** `shell_kit.pdf` memakai 1.600 px, tetapi
kontur di sini ditempatkan pada grid **dua kolom** selebar ~8 cm -- bukan selebar teks penuh
-- sehingga 1.600 px setara ~508 dpi di tempatnya, jauh di atas standar cetak 300 dpi.
Terukur pada `ex02` (12 pile, 2 kombinasi, tanpa bab envelope):

| `max_px` | ukuran | dpi pada lebar tempatnya |
|---|---:|---:|
| 1600 | 26,35 MB | ~508 |
| **1200 (dipilih)** | **16,95 MB** | **~381** |
| 1000 | 13,66 MB | ~317 |
| 800 | 10,05 MB | ~254 |

Dipilih **1.200 px**: masih ~381 dpi di tempatnya, dengan berkas **36% lebih kecil**.
Menaikkannya kembali tidak menambah ketajaman yang terlihat pada kertas, hanya ukuran berkas.
PNG aslinya tidak pernah diubah.

**DIUKUR** pada `ex02` lengkap (12 pile, 2 kombinasi, DPI bawaan): **39 halaman, 22,6 MB,
54 detik** untuk tahap PDF-nya saja. Angka ini dicatat supaya ambangnya dapat ditinjau dari
data, bukan dari dugaan.

**Render ilustrasi dibuktikan lebih dulu, bukan diandaikan.** Ketujuh SVG `docs/img` hanya
mendeklarasikan font generik (`sans-serif`, `monospace`) tanpa satu pun `font-family`
konkret, sehingga resvg di dalam Typst berpotensi menghilangkan seluruh label tanpa error.
DIUKUR: label terender, nol warning, dan keluaran dengan `ignore_system_fonts=True`
**identik byte demi byte** — dokumen ini tidak menyentuh font sistem, sehingga tampil sama
di mesin lain. Fakta itu dijaga `test_kompilasi_tidak_memakai_font_sistem`.

### Changed — `typst` dan `pillow` di-pin eksak, dengan alasan yang BERBEDA

Keduanya sudah ikut secara transitif (`typst` lewat shell-kit, `pillow` lewat matplotlib),
jadi menuliskannya menambah **nol byte**. Tetap dituliskan karena dependency transitif bukan
kontrak: `uvx`/`uv tool install` dari git mengabaikan `uv.lock` dan me-resolve ulang dari
`pyproject.toml`, dan bila shell-kit atau matplotlib berhenti membutuhkannya, `--pdf` mati
pada instalasi baru dengan `ImportError` yang membingungkan.

Alasan pin-nya sengaja dinyatakan berbeda dari pin lain: keduanya **tidak menyentuh satu pun
angka rekayasa** dan tidak ikut satu pun validation case. Yang dijaga adalah dokumen yang
reproducible — pergeseran tata letak antar versi Typst menggeser penomoran halaman pada
dokumen yang sudah ditandatangani. Konsekuensinya, menaikkan keduanya **tidak** menuntut
VC-0..VC-7 diulang, berbeda dari gmsh/openseespy/numpy. Keduanya juga masuk
`provenance.TRACKED_DEPENDENCIES`.

### Changed — lima helper prosa `reporter.py` menjadi publik

`overlap_block`, `one_way_section_outboard_note`, `stirrup_section`,
`capacity_provenance_table`, `traceability_block`, `lokasi_governing`, dan `selection_range`
kehilangan awalan garis bawahnya: ketujuhnya kini dipakai dua penyaji, bukan satu. Nol
perubahan keluaran; suite penuh tetap **683 lulus, 2 skip** sesudah refactor.

### Fixed — `to_display` menyebut lapisan penyajian, bukan dua modul

Docstring-nya menyatakan "HANYA boleh dipanggil dari `renderer.py` dan `reporter.py`".
`reporting_pdf` adalah lapisan penyajian ketiga dengan alasan yang sama persis, jadi aturannya
diperluas secara eksplisit alih-alih dilanggar diam-diam.

### Fixed — catatan sengkang (calc sheet 7b) menyatakan hal yang tidak lagi benar

Catatan bagian 7b berbunyi *"Ini PETA ORIENTASI, bukan angka desain"* untuk `Av/s` per
elemen. Pernyataan itu **peninggalan dari sebelum v0.10.0**, ketika lentur pun masih
berbasis lajur. Saat bawaan lentur dibalik ke `element` dan caption plot lentur ikut
diperbaiki, catatan geser tidak ditinjau ulang.

Yang membuatnya keliru: `Av/s` per elemen dihitung `shell_kit.rebar.calc_shear_Av_per_s`
— **fungsi desain yang sama** yang dipakai `shell-kit` sendiri untuk keluaran sengkangnya
(`cli_rebar.py:251`), dan `shell-kit` memasukkan kegagalannya ke hitungan titik tidak
memenuhi syarat (`reporting_rebar.py:274`). Menyebutnya "bukan angka desain" lebih keras
daripada yang dapat dipertanggungjawabkan.

Catatan diganti: kedua besaran dinyatakan sah dengan pertanyaan yang berbeda — cek
penampang kritis pada `d` dari muka pier sebagai dasar penerimaan (geser satu arah adalah
fenomena penampang, bidang runtuhnya memotong seluruh lebar), dan `Av/s` per elemen untuk
menentukan zona pemasangan. Singularitas `q` di tepi zona jepit ikut dinyatakan.

**Tidak ada satu pun angka yang berubah.** Ini murni perbaikan pernyataan; pilihan untuk
memperluas `design.rebar_basis` ke geser sengaja TIDAK diambil, karena mengubah dasar
penerimaan desain menuntut keputusan rekayasa tersendiri, bukan konsistensi kosmetik.

### Fixed — lingkup `design.rebar_basis` dinyatakan, bukan disiratkan

Parameter itu bernama dan berdokumentasi "dari mana angka desain tulangan diambil",
padahal penelusuran menunjukkan ia **hanya** menggerbangi jalur lajur lentur, caption
lentur, dan tabel governing lentur; `shear_rebar_map` dan `one_way_shear_from_checks`
berjalan tanpa syarat. Pembaca wajar menyangka sengkang ikut diatur. README, tooltip UI,
docstring `ShearRebarMap`, dan `_render_rebar_plots` kini menyebutkan batas itu.

### Changed — ragam bahasa laporan PDF dinaikkan ke kaidah penulisan teknik

Narasi bab Dasar Teori dan bab-bab data disusun ulang. Draf pertama berbentuk prosa yang
membela keputusan desain ("bukan ditebak", "alih-alih disembunyikan"), memakai penekanan
tebal hampir di tiap kalimat, dan menyebut nama modul Python (`config.py`,
`postproc_engine`, `eleResponse`) di dalam dokumen yang ditandatangani engineer. Aturan
penyuntingan yang kini dipakai:

- Huruf tebal hanya untuk istilah yang didefinisikan dan peringatan yang membatalkan
  keabsahan angka, bukan sebagai penekanan retoris.
- Kalimat deklaratif; pembelaan atas keputusan desain tetap tinggal di komentar kode.
- Istilah baku: *perangkat lunak* bukan *tool*, *proses analisis* bukan *run*, *pemeriksa*
  bukan *checker*, *diverifikasi melalui* bukan *digating*.
- Narasi tidak menyebut nama modul; jejak implementasi tetap ada, tetapi pada Lampiran
  Provenance yang memang diperuntukkan bagi itu.

Tiga cacat penyajian ikut ditutup, ketiganya ditemukan dengan membaca PDF hasil, bukan
dengan membaca kode:

1. **Flag baris perintah tercetak sebagai en dash.** Typst mengubah `--` menjadi en dash
   sebagai fitur tipografi, sehingga pesan `Gunakan --opsvis` tercetak `Gunakan -opsvis` --
   perintah yang TIDAK berjalan bila disalin pembaca. DIUKUR: `\-\-`, string kode `#"--"`,
   maupun sisipan zero-width space semuanya tetap dikonversi; hanya raw span yang
   mempertahankannya. `esc()` kini membungkus pola flag sebagai raw span, yang sekaligus
   benar secara semantik. Dijaga `test_flag_baris_perintah_tidak_berubah_menjadi_en_dash`.
2. **Persamaan bernomor sebagai "Gambar".** `#figure` tanpa `kind` tersendiri membuat
   persamaan ikut penomoran gambar sekaligus masuk Daftar Gambar, dan menggeser nomor
   gambar yang sebenarnya. Kini bernomor "Persamaan N" pada penghitung terpisah.
3. **Pesan log operator tersaji sebagai prosa laporan.** Bagian peringatan menerbitkan
   ulang `data.warnings` apa adanya, lengkap dengan nama konstanta internal dan angka
   benchmark. Pesan itu WAJIB tetap tampil, tetapi kini didahului kalimat yang menyatakan
   bahwa yang dikutip adalah catatan proses, bukan temuan rekayasa yang sudah dirumuskan.

## [0.10.0] — 2026-08-12 — Metode desain tulangan per elemen jadi bawaan, envelope tulangan lengkap

Perubahan bawaan terbesar sejak proyek ini mengintegrasikan `shell-kit`: angka desain
tulangan kini diambil langsung dari nilai per elemen, bukan dari integrasi lajur yang
diam-diam bergantung pada `strips_x`/`strips_y` yang tidak diwajibkan pasal mana pun.
Envelope tulangan menyusul lengkap (12 plot + CSV per lajur), dan seluruh kop gambar
dirapikan ke bahasa Indonesia baku.

### Changed — kop gambar (ASUMSI DESAIN, CATATAN, judul, label) dirapikan ke bahasa baku

Beberapa baris di kop cetak setiap plot membawa sisa kode mentah atau penekanan huruf
kapital di tengah kalimat -- terbaca sebagai catatan tempel, bukan dokumen teknik:

- `mode {inputs.rebar_mode}` mencetak nilai config apa adanya (`mode spacing_fixed`).
  Kini diterjemahkan lewat `_REBAR_MODE_LABELS`: `spacing_fixed` -> "spasi tetap",
  `diameter_fixed` -> "diameter tetap".
- `φ lentur 0.90 · φ geser 0.75 (shell-kit v3.3.0 (SNI 2847:2019))` bersarang dua tanda
  kurung ketika `phi_source` (yang sudah membawa kurungnya sendiri) ditempel lagi dalam
  kurung baris asumsi. Sumber φ sekarang baris tersendiri berlabel "Sumber φ: ...",
  sejalan dengan "Sumber fy: ..." yang sudah ada.
- `phi_source` untuk nilai φ yang ditetapkan pengguna berbunyi `"config user"` --
  campuran Inggris-Indonesia. Diganti `"ditetapkan pengguna
  (design.phi_flexure/design.phi_shear)"`.
- Catatan plot As/diameter berbunyi *"Inilah sumber angka desain... bersifat SINGULAR..."*
  dan catatan plot envelope tulangan berbunyi *"ENVELOPE seluruh kombinasi. BUKAN kondisi
  keseimbangan tunggal..."* -- pembuka kalimat informal ("Inilah") dan huruf kapital penuh
  di tengah kalimat sebagai pengganti penekanan. Ditulis ulang jadi kalimat baku lengkap,
  penekanan lewat pilihan kata bukan huruf kapital.
- Label sumbu memakai tanda hubung biasa (`X - memanjang [mm]`), tidak konsisten dengan
  en dash (`—`) yang dipakai di seluruh judul plot lain. Diseragamkan.

**Tidak diubah:** badge "PENAMPANG TIDAK MEMADAI"/"TIDAK ADA BATANG YANG MEMADAI" dan
placeholder `[CONTOH - ganti dengan mutu & sumber yang Anda tetapkan]` pada `fy_source`.
Keduanya penanda keras yang disengaja (kegagalan penampang; data belum ditetapkan
pengguna) -- huruf kapitalnya adalah alarm PRD Bagian 8.3, bukan gaya bahasa yang lupa
dirapikan.

Contoh perbandingan `element` vs `strip` di README (`docs/img/contoh-diameter-element-vs-strip.png`)
dibuat ulang dengan kop yang sudah dirapikan.

### Changed — PERUBAHAN BAWAAN: angka desain tulangan kini dari nilai per ELEMEN

Field baru **`design.rebar_basis`**, bawaan **`"element"`**. Metode hitung angka desain
menjadi pilihan, dan bawaannya berubah dari perilaku sebelumnya:

| Nilai | Angka desain dari | Setara |
|---|---|---|
| `"element"` **(bawaan baru)** | momen tiap elemen apa adanya | algoritma asli `shell-kit` |
| `"strip"` | integrasi lajur di muka pier | perilaku v0.9.x, metode penampang kritis |

**Berlaku untuk seluruh kombinasi sekaligus, termasuk envelope** — satu setelan, bukan per
kombinasi. Mencampurnya membuat envelope membandingkan besaran yang dihitung dengan cara
berbeda, sehingga angka governing-nya kehilangan arti.

**Untuk kembali ke perilaku lama:** setel `"design": {"rebar_basis": "strip"}`. Config lama
tanpa field ini akan **berpindah mode** — karena itu basis yang dipakai kini **selalu
tercetak** di `calc_sheet.md` dan `SUMMARY.md`; tidak ada berkas hasil yang beredar tanpa
menyatakan metodenya.

Pada mode `element`, jalur lajur **tidak dijalankan sama sekali** — `strip_moments_*.csv`
tidak ditulis, dan `strips_x`/`strips_y`/`moment_at` tidak dibaca (tool memperingatkan bila
terisi). Itulah arti "murni nilai elemen"; berkas yang tetap ditulis akan terbaca sebagai
angka desain oleh siapa pun yang membuka folder hasil.

**Yang mendorong perubahan ini.** Menelusuri pertanyaan pemilik proyek menemukan bahwa
metode lajur punya kelemahan yang tidak pernah dinyatakan: hasilnya bergantung
`strips_x`/`strips_y`, angka yang **tidak diwajibkan pasal mana pun**. DIUKUR pada `ex01`,
muka pier arah X — momen lajur tengah 536,9 kNm versus lajur tepi 141,4 kNm (**3,8×**),
sehingga memakai 1 lajur alih-alih 5 mengencerkan puncak dari 556,2 menjadi 283,4 kN·m/m
(**1,96×**) — un-konservatif tepat di lokasi paling kritis. Dan `grep strips_x
validators.py` **kosong**: tidak ada satu pun penjaga bahwa lajur cukup sempit terhadap
lebar cap.

Pada mode `element` keputusan pembagian zona berpindah ke engineer: tool memberi peta,
engineer menentukan band saat mendetail.

**Konsekuensi yang dinyatakan, bukan disembunyikan.** Nilai puncak per elemen di tepi zona
jepit pier adalah **singularitas** dan tidak konvergen — DIUKUR naik ~16% ketika mesh
300 → 150 mm. Arahnya **konservatif** (tulangan bertambah), berbeda sifat dari bocoran mesh
yang un-konservatif. Tetapi angka desain karena itu bergantung `mesh.size_global`, sehingga
ukuran mesh **ikut tercetak bersama angkanya** di calc sheet.

Ringkasan mode `element` mengikuti pola `shell-kit`: kontur adalah deliverable, tabel
maksimum per arah×muka adalah ringkasannya — **lengkap dengan lokasi puncaknya**. Tanpa
koordinat, puncak di sudut pier (artefak tumpuan) tidak dapat dibedakan dari puncak di
tempat lain (kebutuhan nyata). Muka yang maksimumnya jatuh tepat di `As_min` ditandai
`_seluruh elemen seri_`, bukan diberi koordinat elemen pertama yang kebetulan ditemui —
menyajikannya seolah bermakna akan menyesatkan justru pada muka yang paling sering terjadi
di pilecap tebal.

Contoh bawaan menyatakan modenya masing-masing: `ex01`, `ex02`, `ex04` memakai `element`;
**`ex03` memakai `strip`** supaya kedua jalur benar-benar terjalankan contoh bawaan dan test.

**Golden TIDAK diregenerasi**, menyimpang dari rencana. Rencananya menambahkan
`element_design` ke snapshot golden dengan alasan "jalur desain default wajib masuk gerbang
regresi". Diperiksa lagi: golden sudah menggating `probes` (nilai medan per elemen — masukan
jalur ini) **dan** `strip_design`, yang menjalankan `flexure_design` → `shell-kit` yang sama
persis. `design_all_faces` hanyalah loop tipis di atas fungsi itu, sehingga tambahannya
marginal — sementara regenerasi golden selalu berisiko menghapus bukti bahwa angka tool
tidak berubah. Jalur baru digating unit test yang tersasar
(`test_governing_elemen_*`, `test_mode_elemen_*`) alih-alih dengan menyentuh golden.

### Added — envelope tulangan: 12 plot + `strip_design_envelope.csv`

`Envelope/` sebelumnya hanya memuat envelope **gaya** (10 plot momen & geser). Tulangan
hanya punya `rebar_design_envelope.csv` — CSV tanpa satu pun gambar, dan envelope geser
tidak ada sama sekali. Sekarang lengkap: **4 `As` + 4 batang terpilih + 2 `Av/s` + 2
diameter sengkang**, setara isi folder `Envelope_Rebar` `shell-kit`.

**Dibangun dari envelope GAYA, bukan dari maksimum `As` antar kombinasi.** Momen envelope
per muka (`max_values` untuk bawah, `min_values` untuk atas) dan `|q|` envelope per arah
dimasukkan ke `flexure_design`/`shear_rebar_map`/`select_flexure_bars` yang sama persis
dengan kombinasi biasa. Dua alasan:

1. Hasilnya **satu desain yang konsisten** — `As`, `d_eff`, dan diameter lahir bersama
   dari satu momen. Mengambil maksimum `As` antar kombinasi memasangkan `As` dari satu
   kombinasi dengan `d` dari kombinasi lain.
2. **Pemilihan batang hanya sah dilakukan sekali di akhir.** Pada `rebar_select_codes`,
   `RebarSelection.values` adalah **indeks kategori**; maksimum indeks antar kombinasi
   tidak punya arti apa pun.

Angkanya tetap sama karena `As` monoton tak-turun terhadap `|Mu|` — asumsi itu **diuji**
(`test_envelope_as_sama_dengan_maksimum_antar_kombinasi`), bukan diandaikan, pada rentang
momen yang melintasi beberapa peralihan diameter karena hanya di situ ia bisa patah.

Plotnya memakai ulang `_render_rebar_plots` apa adanya lewat parameter `rename`
(`contour_*` → `envelope_*`); menyalin blok plotnya akan melahirkan dua jalur gambar yang
dapat menyimpang diam-diam.

**`strip_design_envelope.csv`** (mode `strip` saja) menjawab pertanyaan yang tidak dijawab
berkas mana pun sebelumnya: `As` maksimum **per lajur** lintas kombinasi beserta kombinasi
penentunya. `governing_strip_design` yang lama menciutkan seluruhnya jadi 4 baris — cukup
untuk "berapa maksimum keseluruhan", tidak cukup untuk "apa yang saya pasang di lajur ini".
Kuncinya menyertakan `face`, karena tanda momen satu lajur dapat berbalik antar kombinasi
sehingga satu lajur bisa menuntut tulangan bawah dari satu kombinasi **dan** tulangan atas
dari kombinasi lain.

### Fixed — caption plot tulangan menyatakan hal yang keliru pada mode elemen

Setiap plot lentur mencetak *"Peta orientasi — nilai desain diambil dari lajur muka pier"*.
Pada `rebar_basis = "element"` kalimat itu **terbalik**: peta itulah sumber angka desainnya,
dan lajur tidak dihitung sama sekali. Gambar inilah yang dicetak dan ditempel ke laporan,
sehingga caption yang salah beredar sebagai pernyataan keliru di setiap lembar. Caption kini
mengikuti mode. Caption plot geser tidak diubah — geser satu arah selalu didesain pada
penampang `d` dari muka pier, terlepas dari mode.

**Perbaikan pertama tidak lengkap.** `_render_rebar_plots` menerima parameter `rebar_basis`,
tetapi pemanggilnya di jalur **per-kombinasi** (`_report_one_combo`) tidak meneruskannya —
jatuh diam-diam ke bawaan fungsi (`"strip"`) apa pun mode yang sebenarnya dipakai. Jalur
**envelope** meneruskannya dengan benar, sehingga bug ini tersembunyi di balik plot envelope
yang sudah benar. Ketahuan saat membuat perbandingan `contour_diameter_x_bawah.png` `ex02`
antara `element` dan `strip` untuk README: kedua gambar mencetak caption `strip` yang sama,
padahal salah satunya seharusnya berbeda. Ditutup dengan meneruskan `rebar_basis=rebar_basis`
di pemanggilan yang hilang, plus regresi
`test_caption_plot_per_kombinasi_mengikuti_rebar_basis` yang memata-matai `block.notes` yang
sebenarnya dikirim ke `renderer.render_contour` — sesuatu yang tidak dapat diperiksa dari
berkas PNG setelah jadi.

Tabel "Ke mana efeknya sampai" di README juga basi karena alasan yang sama: ia menyatakan
`contour_As_*.png` "murni orientasi", padahal sejak bawaan berubah ia justru angka desain.
Diganti tabel yang menyatakan peran tiap keluaran **per mode**.

### Added — contoh nyata perbandingan `element` vs `strip` di README

`docs/img/contoh-diameter-element-vs-strip.png`: `contour_diameter_x_bawah.png` `ex02`
(spasi 100 mm) yang sungguh dihasilkan dua kali, hanya `design.rebar_basis` yang diubah.
Berbeda dari ilustrasi lain di `docs/img/` yang digambar tangan (SVG), ini tangkapan layar
langsung dari `pilecap-report` (PNG) — sengaja, karena poinnya justru **petanya identik
piksel demi piksel** antara kedua mode (lihat catatan di atas: `designs` selalu dihitung
dari medan per elemen apa adanya, terlepas `rebar_basis`), dan hanya baris CATATAN di kop
yang berbeda. `test_ilustrasi_readme_ada_berkasnya` diperluas untuk memvalidasi PNG lewat
header magic byte-nya, bukan cuma XML seperti SVG.

### Added — ilustrasi di dalam formulir `pilecap-ui`

Ilustrasi tidak lagi hanya ada di README: `Section.illustration` menampilkannya **di dalam
formulir**, pada bagian Pilecap (sistem koordinat), Pile (skema tumpuan–beban), Pier
(tumpang tindih), dan Desain–pemilihan tulangan (ilustrasi mode baru). Data-driven — satu
field di `ui/schema.py`, bukan cabang `if` yang tersebar di `app.py`.

`st.image` menerima **string SVG** (diverifikasi pada streamlit 1.61), jadi berkasnya cukup
dibaca: tidak perlu rasterisasi dan tidak ada dependency baru.

**Satu kendala pengemasan ditutup sekaligus.** `docs/` sebelumnya **tidak ikut ke wheel**,
sehingga UI pada instalasi `uvx`/wheel — justru pengguna yang paling terbantu gambar — akan
gagal menemukan berkasnya, dan kegagalannya tidak terlihat di repo karena
`config.illustrations_dir()` punya fallback. Ditutup dengan `force-include` (24 KB),
`illustrations_dir()` yang meniru pola `examples_dir()`, dan pemeriksaan isi wheel di
`test_wheel_memuat_contoh_dan_seluruh_modul` — persis alasan `examples` sudah diperiksa
terpisah di sana.

### Added — panduan lengkap `pilecap_config.json` di README, dengan ilustrasi

Seluruh **59 field** dari 11 blok kini dijelaskan di README: arti, satuan, bawaan, ke mana
efeknya sampai, dan apa akibatnya bila salah. Lima ilustrasi SVG di `docs/img/` untuk konsep
yang sulit dijelaskan dengan teks saja — skema tumpuan/beban (pile membebani, pier menumpu),
sistem koordinat bersama, lajur momen `strips_x`/`strips_y`, dua mode pemilihan tulangan, dan
anatomi tumpang tindih pile–pier.

**Kolom "Bawaan" DIUKUR terhadap tool, bukan disimpulkan dari kode:** setiap kunci dihapus
satu per satu dari `examples/ex01`, lalu dilihat apakah validator benar-benar menolaknya.
Pengukuran itu membetulkan tujuh baris yang sudah sempat ditulis salah — `project.*` (3),
`units.*` (3), dan `design.code` ternyata **punya bawaan**, bukan wajib seperti dugaan awal.
Yang benar-benar ditolak bila tidak ada berjumlah **26 field** (pier persegi; 25 bila pier
bulat), dan daftarnya kini ada di README apa adanya.

**Dijaga test, bukan diharapkan.** Penjelasan di README dan tooltip di `pilecap-ui` ditulis
untuk pembaca berbeda sehingga teksnya memang tidak sama — tetapi **cakupannya** tidak boleh
berbeda. Tiga test baru di `tests/test_packaging.py`:

* `test_readme_mendokumentasikan_setiap_field` — field baru di `ui/schema.py` yang lupa
  didokumentasikan menggagalkan suite. Sekaligus mengunci jumlah field & bagian yang disebut
  README, karena angka basi merusak kepercayaan pada dokumen selebihnya.
* `test_readme_tidak_menyebut_field_yang_tidak_ada` — arah sebaliknya: field yang dihapus
  dari schema tidak boleh tertinggal di dokumentasi.
* `test_ilustrasi_readme_ada_berkasnya` — tautan gambar yang putus baru terlihat setelah
  README dibuka di GitHub, yaitu setelah dirilis. Terlambat.

Ketemu sambil menghitung: README menyebut "58 field" padahal sudah 59 sejak
`pier.max_pile_overlap_fraction` ditambahkan di v0.9.0.

### Fixed — bocoran mesh pada tumpang tindih pile–pier tidak dibatasi, dan arahnya TIDAK AMAN

v0.9.0 memisahkan komponen **strut** (geometri) dari **bocor mesh** (diskretisasi) dan
melaporkan keduanya. Yang tidak dinyatakan — dan tidak dibatasi — adalah **arah galatnya**:
beban yang mendarat di node jepit tidak melenturkan pelat, sehingga momen dan tulangan yang
dihitung menjadi **lebih kecil daripada seharusnya**. Mesh yang lebih kasar menghasilkan
desain yang lebih ringan.

Ditemukan dari model nyata pemilik proyek: pile D1800 menindih **sudut** pier sebesar 14,66%.
Pada `size_global` 300 mm (D/h = 6, mesh terkasar yang diizinkan rule 7a), pelat menerima
**5,7–7,0 poin persen lebih kecil** daripada seharusnya — tanpa satu pun tanda. Peringatan
yang ada hanya berbunyi "SENSITIF terhadap kehalusan mesh": kualitatif, tanpa angka, tanpa
ukuran mesh yang dibutuhkan.

Sekarang bocoran **diukur dan dibatasi**, dua tingkat per pile:

| Bocoran | Yang terjadi |
|---------|--------------|
| ≤ `OVERLAP_LEAK_WARN` (2%) | jalan tanpa komentar |
| 2–5% | jalan, **peringatan** memuat angka, arah galat, dan ukuran elemen yang dibutuhkan |
| > `OVERLAP_LEAK_ERROR` (5%) | **`AnalysisError`** |

Diperiksa sudah di `pilecap-mesh`, sebelum satu pun kombinasi dibaca: fraksi bocoran tidak
bergantung besar `Pz` sama sekali (`fem_engine.leak_traces` memakai `Pz = 1 N`), jadi tidak
perlu menunggu analisis — dan `pilecap-mesh` memang tidak pernah membaca `pile_reactions.csv`.

**Ambangnya DIUKUR.** Dua geometri × lima kehalusan, `pz_bocor_mesh / Pz`:

| D/h | MUKA (`f`=7,21%) | SUDUT (`f`=14,65%) |
|-----|-----------------:|-------------------:|
| 6 | 4,603% | 5,855% |
| 8 | 4,033% | 5,301% |
| 12 | 3,320% | 4,175% |
| 24 | 1,363% | 3,199% |
| 48 | 0,767% | 1,225% |

Geometri ujinya divalidasi terhadap kasus nyata: MUKA pada D/h=8 memberi 4,033% vs ex04
terkirim yang terukur 4,04%; SUDUT pada D/h=6 memberi 5,855% vs model nyata 5,81%.

### Changed — rencana "rule 7a lebih ketat untuk pile overlap" DIBATALKAN oleh pengukuran

Rancangan awalnya memakai rasio `D/h` sebagai saringan awal. Tabel di atas membantahnya pada
dua titik sekaligus:

1. **`D/h` bukan prediktor bocoran.** Yang menentukan adalah panjang chord, bukan luas
   irisan: overlap **sudut** (terpotong dua sisi) bocor **2,3× lebih besar** daripada overlap
   **muka** pada `D/h` yang sama. Satu ambang `D/h` tidak dapat membatasi keduanya.
2. **Ambang yang masuk akal justru menolak contoh yang sah.** `D/h ≥ 12` akan menolak ex04,
   yang dikirim pada `D/h = 8` dengan bocoran 4,03% — di bawah batas ERROR.

Dan saringan awalnya tidak menghemat apa pun: guard yang sebenarnya sudah berjalan sebelum
solver, bahkan sebelum kombinasi dibaca. Proksi yang tidak akurat DAN tidak menghemat adalah
proksi yang tidak perlu ada, jadi ia tidak dibuat. `MIN_ELEM_PER_PILE_DIAMETER` tetap 6 untuk
semua pile.

### Fixed — pesan rule 14 bertentangan dengan kalimat berikutnya

Penolakan tumpang tindih berbunyi *"Node tidak bisa sekaligus dijepit (pier) dan dibebani
(pile)"*, lalu kalimat setelahnya menjelaskan cara melakukan persis itu lewat
`pier.max_pile_overlap_fraction`. Kalimat pertama tertinggal dari sebelum v0.9.0. Diganti
dengan alasan yang sebenarnya: bagian di dalam footprint pier tidak melenturkan pelat, dan
tool tidak menghitung kapasitas strut-nya.

### Fixed — teks kop keluar dari garis tepi panelnya sendiri

Ketahuan saat memeriksa gambar hasil guard baru. Baris PERINGATAN digambar **bold**, tetapi
dibungkus memakai anggaran lebar huruf biasa. DIUKUR dengan `TextPath`: bold DejaVu Sans
0,5970 em/karakter vs normal 0,5283, sedangkan konstantanya 0,52 — **di bawah keduanya**.
Akibatnya baris peringatan melewati tepi panel sampai ~13%: justru baris yang paling perlu
terbaca. Bug ini sudah ada sejak kop diperkenalkan di v0.8.0.

Diperbaiki di dua lapis, karena satu lapis saja masih meleset:

1. Anggaran terpisah untuk teks tebal (0,60) dan biasa (0,53), masing-masing sedikit di atas
   hasil ukur.
2. Anggaran itu tetap hanya **perkiraan**, dan perkiraan lebar rata-rata gagal pada teks yang
   komposisinya tidak biasa — peringatan penuh huruf kapital terukur 0,637 em/karakter. Karena
   itu hasil pembungkusan sekarang **diukur** dan anggarannya dikecilkan sampai benar-benar
   muat. Perkiraan hanya menentukan titik awal, bukan hasil akhir.

`test_baris_kop_muat_di_dalam_garis_tepi_panel` mengukur setiap baris dengan `TextPath`,
bukan menghitung karakter — sehingga ketidakcocokan antara `bold=` di pembungkus dan
`fontweight` di penggambar tertangkap, bukan diandalkan pada kewaspadaan.

### Changed — peringatan bocoran diringkas jadi satu baris

Versi pertamanya menulis empat baris prosa **per pile**. Pada ex04 itu berarti 11 baris
peringatan di kop setiap gambar — kop mendominasi gambarnya sendiri, dan pada pilecap dengan
banyak pile overlap ia menjadi tidak terbaca sama sekali. Sekarang satu baris untuk seluruh
pile (rentang bocoran, daftar pile, arah galat, ukuran elemen yang dibutuhkan); rinciannya
tetap lengkap per pile di `calc_sheet.md` bagian 3a dan di log. Pesan penolakan tetap panjang
— ia menghentikan run, jadi detailnya memang perlu.

### Added — cakupan test overlap SUDUT

`ex04` hanya mencakup overlap **muka**. Model nyata menunjukkan overlap **sudut** berperilaku
berbeda, dan itu tidak teruji sama sekali. `tests/test_overlap.py` bertambah geometri sudut
(similaritas model nyata, `f` identik 14,66%) beserta test yang menuntut bocorannya memang
lebih besar daripada overlap muka — supaya alasan menolak proksi `D/h` tetap terjaga.

Fixture `run_kasar` dipindah dari D/h=6 ke D/h=8: pada D/h=6 bocorannya 4,87%, hanya 2,6% di
bawah ambang ERROR, dan fixture yang duduk di tepi ambang akan gagal sewaktu-waktu karena
pergeseran node antar run gmsh. Studi kehalusan kini memakai `leak_traces` tanpa solver —
lebih murah, dan tidak terhalang guard yang justru sedang ia ukur perilakunya.

### Added — VC-6 mencakup ex04: jalur tumpang tindih tervalidasi silang

Model pembanding Midas Civil untuk `ex04` disediakan pemilik proyek (2026-08-11), sehingga
release gate VC-6 naik dari 3 menjadi **4 contoh × 2 kombinasi**. Tidak ada perubahan kode
produksi — yang bertambah adalah bukti.

Ini bukan sekadar contoh keempat. `ex04` satu-satunya kasus yang pile-nya menindih pier,
sehingga ia menguji tiga hal yang tidak disentuh ex01–ex03, masing-masing terhadap
implementasi yang sepenuhnya independen:

1. **Himpunan tumpuan termasuk node lensa.** Node reaksi Midas **sama persis** dengan
   `fem_engine.fixed_support_nodes` — 479 node, nol selisih di kedua arah. Bila node
   `LENS_*` tertinggal bebas di Midas, `test_vc6_reaksi_tumpuan_cocok_dengan_midas` gagal
   pada asersi indeks, bukan diam-diam lolos dengan angka berbeda.
2. **Seluruh cakram pile dibebani, termasuk bagian di dalam pier.** `Σ FZ` Midas cocok
   dengan `Σ Pz` sampai ~4e-12 relatif, padahal sebagian tekanannya bekerja pada elemen
   lensa — membuktikan `*PRESSURE` pada MCT memang memuatnya.
3. **Respons pelatnya.** Elemen lensa dijepit **sekaligus** dibebani; resultan per elemen
   tetap cocok pada RMS ≤ 0,134%, korelasi ≥ 0,99994.

Terukur (gate lama tidak diubah — marginnya masih 3–7×):

| Jalur | Besaran | Terburuk ex01–03 | ex04 | Gate |
|-------|---------|-----------------:|-----:|-----:|
| 1 | Momen | 0,144% | 0,134% | 1,0% |
| 1 | Geser | 0,265% | 0,114% | 1,5% |
| 1 | Momen puncak | 0,515% | 0,378% | 2,0% |
| 2 | Lendutan `uz` | 0,216% | **0,258%** | 1,0% |
| 3 | Reaksi `Rz` | 0,539% | 0,088% | 1,5% |

**Yang dinyatakan apa adanya, bukan ditambal:**

- **Lendutan ex04 kini yang terburuk (0,258%), dan itu batas alat ukur, bukan
  ketidaksesuaian.** Pilecap 1.500 mm dengan pier dinding 2.400 × 1.200 sangat kaku —
  lendutan maksimumnya hanya 0,110 mm, sehingga resolusi ekspor Midas 1 µm setara **0,908%
  dari skala**, jauh lebih besar daripada selisih terukur. Jalur lendutan karena itu **bukan
  jalur yang memvalidasi ex04**; yang mengikat adalah Jalur 1 dan 3.
- **Kesesuaian ini tidak membuktikan idealisasi jepit-sempurna itu benar secara fisik.**
  Kedua program memakai idealisasi yang sama, jadi perbandingannya tidak dapat menilai
  asumsinya. Kapasitas strut tetap wajib dicek terpisah (`KNOWN_LIMITATIONS` #10).

### Fixed — SUMBER.md §5.2 menyebut batas resolusi lendutan terlalu sempit

Pengukuran ulang per kombinasi (pemicunya penambahan ex04) menemukan bahwa **ex03 juga
dibatasi resolusi ekspor** — tipis, 0,052% resolusi vs 0,045% selisih terukur — padahal
dokumen sebelumnya hanya menyebut ex01 dan menyiratkan ex02 & ex03 bebas. Hanya **ex02**
yang benar-benar bebas. Angka lendutan maksimum ex01 yang tercatat (0,226 mm) juga hanya
mencakup satu kombinasi dari dua.

Tidak ada gate yang berubah — yang salah adalah **klaim tentang seberapa kuat bukti Jalur 2**,
dan itu jenis kesalahan yang paling perlu dikoreksi. §5.2 kini memuat tabel per kombinasi
untuk keempat contoh beserta catatan koreksinya.

`pilecap_config.json` dan `pile_reactions.csv` pada paket VC-6 ex04 **diperiksa byte-identik**
dengan `examples/ex04_pile_overlap_pier/` — model Midas-nya berasal dari contoh yang dikirim
ke pengguna, bukan varian yang disetel agar cocok. `SUMBER.md` bertambah §1.1 (apa yang
ex04 uji dan apa yang tidak) dan §7 (tabel angka terukur keempat contoh).

`tests/data/vc6/` bertambah ~6 MB.

## [0.9.0] — 2026-08-11 — Pile yang tumpang tindih dengan pier, dan satu cacat senyap yang ditutup

Berawal dari satu pertanyaan: *apakah gaya aksial pile tetap diteruskan ke shell bila
pile-nya menindih pier?* Menelusurinya menemukan cacat yang **sudah aktif** di v0.8.0.

### Fixed — beban pile yang hilang tanpa satu pun tanda

Node yang dimiliki bersama oleh grup pile dan grup pier **dijepit 6 DOF**. Gaya pada DOF
terjepit menghasilkan perpindahan nol, jadi ia **tidak melenturkan pelat** dan langsung
masuk ke reaksi.

**VC-0 tidak dapat menangkapnya.** `Σ beban` dan `Σ reaksi` sama-sama memuat gaya itu,
sehingga residunya nol dan run dilaporkan LULUS — momen desainnya lebih kecil daripada
yang seharusnya, tanpa satu pun peringatan.

Pintu masuknya: rule 14 menolak `intersection().area > 0.0` secara ketat, sehingga pile
yang **bersinggungan tepat** dengan muka pier (luas irisan nol, tetapi node-nya tetap
terbagi) **lolos**. Jaring kedua di `_assign_groups` hanya menangkap *sub-face* yang
diklaim ganda, bukan *node* yang terbagi.

Dua penutup, dari dua arah:

- **Persinggungan eksak kini SELALU ditolak**, dengan atau tanpa opt-in. Di sana tidak ada
  lensa untuk diukur: 100% dari yang terserap adalah artefak diskretisasi murni, tanpa satu
  pun komponen geometri yang dapat dihitung dan dilaporkan. **Ini perubahan perilaku, dan
  memang itu maksudnya** — run lama pada geometri seperti itu salah, dan pesannya
  mengatakannya.
- **Jaring pengaman di `analyze_combo`**: bila `geom.overlaps` kosong tetapi ada beban yang
  mendarat di node jepit, run **berhenti** dengan `AnalysisError`. Menguji kondisi yang
  sebenarnya, bukan proksi geometrinya, sehingga menangkap juga celah pile–pier yang jauh
  lebih kecil daripada satu elemen dan diam-diam disatukan mesher — termasuk pada mesh yang
  dimuat ulang dari CSV.

### Added — `pier.max_pile_overlap_fraction`

Tumpang tindih **berluas** dapat diizinkan lewat field baru ini (nirdimensi, `null` =
menolak, yaitu perilaku v0.8.0 persis). Angka, bukan boolean, mengikuti pola
`design.as_min_surface_zone`: sekaligus rem eksplisit dan keputusan user yang tercatat di
`run_manifest.json`.

Skemanya: **seluruh cakram pile dibebani tanpa terkecuali**, `p = Pz / A_pile` tidak
berubah. Bagian yang jatuh di dalam footprint pier terserap ke reaksi, dan yang terserap
**diukur lalu dilaporkan** — dipecah menjadi dua komponen yang sifatnya berbeda:

| Komponen | Asal | Bergantung mesh? |
|----------|------|------------------|
| `pz_strut` = `p × A_lensa` | **Geometri** — aksi strut pile→pier menembus tebal pilecap | tidak |
| `pz_bocor_mesh` = terserap − `pz_strut` | **Diskretisasi** — beban konsisten elemen di muka pier | ya, orde `h` |

Memisahkannya bukan kosmetik. TERUKUR pada `a` = 300 mm, `r` = 400 mm:

| D/h | `f_mesh` (= strut/`Pz`) | bocor mesh | ke pelat |
|-----|------------------------:|-----------:|---------:|
| 6 (terkasar yang diizinkan) | 7,0768% | 4,8744% | 88,05% |
| 12 | 7,1587% | 3,2175% | 89,62% |
| 24 | 7,2021% | 1,3717% | 91,43% |
| rumus analitis | **7,2147%** | 0 | 92,79% |

Komponen strut **konvergen** ke `r²·acos(a/r) − a·√(r²−a²)`; komponen bocoran **mengecil
sebanding `h`**. Digabung menjadi satu angka, keduanya akan menyamar sebagai parameter
geometri padahal separuhnya parameter meshing.

Implementasinya: grup mesh kelas satu `LENS_<pile>__<pier>` yang **dibebani bersama pile
dan dijepit bersama pier** — dua keanggotaan yang disebut eksplisit lewat
`fem_engine.fixed_support_nodes`, bukan disimpulkan dari awalan nama. Awalannya sengaja
bukan turunan `PILE_`/`PIER_` sehingga `pile_groups()`/`pier_groups()` tidak mungkin
menyerapnya diam-diam; dijaga test disjoint.

`exporters/mct.py` memakai `fixed_support_nodes` yang sama. Tanpa itu model Midas akan
punya himpunan tumpuan berbeda dari model OpenSees yang dibandingkan VC-6.

**Peringatannya wajib dan menyeluruh**: log WARNING, `run_manifest.json`, `SUMMARY.md`,
`mesh_summary.md`, `calc_sheet.md` bagian 3a, dan **kop setiap gambar** — dibangun ulang
dari `geom.overlaps`, bukan diendus dari string. Elemen lensa juga diberi warna dan entri
legenda tersendiri di `boundary_load_check.png`.

**Tool tidak menghitung kapasitas strut.** `KNOWN_LIMITATIONS` item #10 baru menyatakan itu
dan, sama pentingnya, bahwa **batas reproducibility 0,02% pada item #9 tidak berlaku** untuk
geometri overlap.

### Fixed — `a/d` tampak aman persis ketika kondisinya paling deep

`shear_span_ratio` memakai `pier.exterior.distance(centroid)`. Untuk pusat pile yang berada
**di dalam** pier, `exterior` mengembalikan jarak ke ring — angka positif besar — sehingga
`a/d` besar dan pilecap tampak tidak-deep tepat pada kasus yang paling deep. Kebalikan dari
yang benar. Kini `a = 0` bila pier menutupi centroid pile. Perilaku untuk pile tanpa overlap
tidak berubah.

Pesan kegagalan VC-0 tidak lagi menyebut *"ada beban pile yang jatuh pada node jepit"*
sebagai dugaan penyebab: kondisi itu **tidak pernah** membuat VC-0 gagal, dan kini justru
keadaan yang sengaja diizinkan serta dilaporkan tersendiri.

### Added — contoh bawaan `ex04_pile_overlap_pier`

Pilecap 6.000 × 4.000 × 1.500 mm, pier persegi 2.400 × 1.200, enam pile D800. Dua di
antaranya (`P2`, `P5`) berpusat 300 mm di luar muka pier sehingga `f` = 7,21% — **geometri
yang sama dengan yang diverifikasi terhadap rumus analitis**, jadi contoh ini diuji terhadap
rumus, bukan terhadap dirinya sendiri.

`EXAMPLE_NAMES` sebelumnya terduplikasi di tiga tempat (`config.py`, `tests/conftest.py`,
`tests/test_mesh_engine.py`); kedua daftar di test kini mengimpor dari `config` sehingga
contoh baru otomatis ikut teruji.

### Fixed — peringatan overlap tidak sampai ke `mesh_summary.md`

Ketahuan pada verifikasi manual: `cli_pilecap_mesh` hanya meneruskan `raw.warnings` (milik
mesher) ke `write_mesh_summary`, sehingga peringatan geometri tidak ikut. Akibatnya
`mesh_summary.md` memuat baris `LENS_P2__PIER1` di tabel luas group **tanpa satu pun kalimat
yang menerangkan mengapa group itu ada** — padahal di situlah pembaca pertama kali
melihatnya. Dikunci `test_peringatan_overlap_sampai_ke_mesh_summary`.

### Fixed — golden `test_resultant_pada_probe` gagal intermiten dengan kode yang tidak berubah

`NEAR_ZERO_FRACTION = 1e-4` **lebih kecil daripada jitter yang memang ada**. DIUKUR pada
8 run ex02 berturut-turut dengan kode identik: sebaran nilai medan pada probe mencapai
**2,75e-4 dari puncak** (`m_xy`). Toleransi yang lebih ketat daripada kebisingan alat ukur
menghasilkan kegagalan acak — dan kegagalan acak melatih orang mengabaikan test.

Dinaikkan ke `1e-3` (margin ~3,6× terhadap sebaran terukur). **Pemeriksaan besaran desain
tidak dilonggarkan**: `DESIGN_RTOL` tetap 0,1%, dan sebaran `As` per lajur pada 8 run yang
sama hanya 6,8e-5 — dua orde di bawahnya. Yang berisik adalah nilai medan di titik yang
nyaris nol, bukan angka desainnya.

### Changed — dugaan tentang sensitivitas mesh pada geometri overlap TERBANTAH

Rencana v0.9.0 memperkirakan ex04 butuh toleransi golden lebih longgar, karena pergeseran
node antar run akan mengubah berapa banyak beban mendarat di node jepit. Konstanta terpisah
`MESH_NONDETERMINISM_DESIGN_SPREAD_OVERLAP` disediakan untuk itu, dengan catatan bahwa
angkanya **harus diukur, bukan ditebak**.

Diukur: 8 run ex04, sebaran besaran desain **0,0001%** — **70× lebih kecil** daripada ex02
yang tanpa overlap. Kedelapan mesh-nya memang berbeda (sha256 `nodes.csv` kedelapannya
berlainan), tetapi pada ukuran elemen yang **tetap**, jumlah node yang jatuh di muka pier
praktis tidak berubah.

Konstanta terpisahnya **dihapus**; dugaan yang terbantah dicatat di komentar konstanta yang
tersisa supaya tidak diulang. Yang memang sensitif pada geometri overlap adalah **ukuran
elemen** — hal yang berbeda, dan itulah yang dinyatakan `KNOWN_LIMITATIONS` #10.

### Changed — VC-6 Jalur 2 kini mencakup ketiga contoh

Ekspor lendutan ex03 yang di v0.8.0 ternyata byte-identik dengan berkas reaksinya sudah
diperbaiki pemilik proyek. Jalur 2 naik dari 4 menjadi 6 pasangan contoh×kombinasi:
RMS 0,045% / 0,042%, korelasi 1,000000 — di dalam gate yang sudah ada.

`tests/data/vc6/SUMBER.md` §5.1 **ditulis ulang, bukan dihapus**: arsip semula memuat berkas
salah ekspor, dan menghapus riwayatnya berarti menghapus jejak audit.

## [0.8.0] — 2026-08-10 — VC-6 tertutup & kop gambar teknik pada setiap plot

Dua pekerjaan yang tidak berkaitan, dari dua kebutuhan berbeda: menutup blocker rilis
terakhir yang tersisa, dan merapikan penyajian plot.

### Added — VC-6 berjalan sebagai release gate

`PRD Bagian 17 item 8` **DITUTUP**. Model pembanding Midas Civil untuk ketiga contoh
bawaan kini ada di `tests/data/vc6/` (~28 MB), dan `VC-6` berjalan sebagai release gate —
bukan lagi `@pytest.mark.skip` dengan janji.

Model Midas-nya **diimpor dari `model.mct` yang ditulis tool ini sendiri**, sehingga
penomoran node & elemen identik 1:1 dan perbandingan per-elemen bermakna tanpa pemetaan.

Tiga jalur validasi yang saling bebas, seluruhnya terukur (3 contoh × 2 kombinasi):

| Jalur | Besaran | RMS terburuk | Korelasi min |
|-------|---------|-------------:|-------------:|
| 1 | Momen `m_xx`/`m_yy`/`m_xy` | 0,144% | 0,99991 |
| 1 | Geser `q_x`/`q_y` | 0,265% | 0,99993 |
| 1 | Momen **puncak** (penentu tulangan) | 0,515% | — |
| 2 | Lendutan `uz` per node (ex01 & ex02) | 0,216% | 0,999986 |
| 3 | Reaksi tumpuan `Rz` (ketiga contoh) | 0,539% | 0,999596 |

Ditambah **cek-silang transformasi tensor**: merotasi ekspor sumbu lokal Midas dengan
`theta` kami mereproduksi ekspor sumbu global Midas sampai RMS 0,0001%. Itu menguji
`postproc_engine` terhadap implementasi independen — VC-2 menguji hal yang sama, tetapi
secara sintetis.

**Efek samping yang tidak diduga:** `Σ FZ` reaksi Midas sama dengan `Σ Pz` masukan sampai
~9 angka berarti. Karena model Midas diimpor dari MCT kita, ini **memvalidasi
`exporters/mct.py` secara end-to-end** — satu-satunya cek yang pernah menyentuh sisi Midas
yang sesungguhnya. Sebelumnya seluruh test MCT hanya memeriksa berkas kita terhadap harapan
kita sendiri.

Dua hal dinyatakan apa adanya, bukan ditambal:
- **Konvensi tanda geser Midas berlawanan** dengan konvensi PRD Bagian 7.1. Direkonsiliasi
  eksplisit di `validation_helpers.MIDAS_SHEAR_SIGN`, dengan bukti keseragaman: tidak satu
  pun dari ~5.500 elemen menyimpang, dan pembalikan itu tetap muncul pada ekspor sumbu
  global yang tidak melewati rotasi apa pun.
- **Lendutan ex01 dibatasi resolusi ekspor Midas** (1 µm = 0,44% dari skala, lebih besar
  daripada selisih terukur 0,216%). Lulusnya gate itu hanya berarti "tidak berbeda sejauh
  yang dapat diukur", dan docstring test menyatakannya.
- **Lendutan per node ex03 tidak tersedia**: berkas yang disediakan untuk ex03 ternyata
  byte-identik dengan berkas reaksinya. Tidak disalin, dan kekurangannya dicatat.

Simpangan titik-per-titik maksimum sengaja **tidak** di-gate (dicetak di pesan kegagalan):
ex02 `q_y` mencapai 7,7% pada satu elemen di singularitas tepi pier, tempat kedua formulasi
elemen memang paling sah berbeda.

### Changed — kop gambar teknik menggantikan judul empat baris

Judul plot sebelumnya menumpuk empat baris (nama besaran, statistik, asumsi material,
catatan metodologi), sehingga yang paling penting tenggelam. Sekarang:

- **Judul dua baris**: nama besaran (13 pt tebal) dan kombinasi (9,5 pt redup).
- **Kop bertepi di kiri-bawah, DI LUAR area gambar**, berisi identitas proyek → asumsi
  desain → catatan → peringatan, berformat kop gambar teknik. Berlaku untuk **semua** plot:
  kontur, kategorikal, envelope, denah mesh, denah geometri, cek tumpuan, dan opsvis.
- `renderer.TitleBlock` menggantikan parameter `info: str`. `warnings` jadi field
  tersendiri, bukan konvensi awalan teks: `GEOMETRI OVERRIDE` (wajib menonjol menurut PRD
  Bagian 9.3) sebelumnya dicapai dengan mewarnai **seluruh judul** merah, termasuk nama
  besaran yang tidak ada hubungannya.
- **`φ lentur`/`φ geser` beserta sumbernya kini tampil di plot.** Keduanya mengubah setiap
  angka tulangan pada gambar tetapi sebelumnya tidak pernah sampai ke satu plot pun.
- **Plot envelope kini berkop.** Sebelumnya envelope sama sekali tidak membawa konteks,
  padahal justru itu yang paling sering dicetak.
- `engineer` dan `date` dari config akhirnya sampai ke gambar — selama ini dikumpulkan
  formulir lalu hanya dipakai calc sheet.
- Bahasa dibakukan: `"PETA ORIENTASI - ..."` → `"Peta orientasi — nilai desain diambil dari
  lajur muka pier, bukan dari nilai puncak elemen."`; `"V_u > phi.V_c"` → `"V_u > φV_c"`;
  tanda pisah `—`.

Statistik maks/min **dihapus dari judul tanpa pindah ke kop**: `_mark_extremes` sudah
menuliskannya di atas elemennya sendiri beserta koordinat, dan colorbar membawa rentangnya.
Menyalinnya ke kop hanya menciptakan tempat kedua yang bisa berbeda dari gambarnya.

**Seluruh PNG bertambah tinggi** (~12%) karena kop DITAMBAHKAN di bawah, bukan diambil dari
area gambar — pada pilecap panjang-ramping, mengambilnya berarti kehilangan seperempat
tinggi gambar. Diperiksa: `reporter.py` tidak menyematkan gambar dengan lebar tetap, jadi
tidak ada konsumen hilir yang rusak. `tests/test_golden.py` juga tidak terdampak (ia
membandingkan statistik mesh dan nilai probe, tidak pernah menyentuh PNG).

### Fixed

- **Judul terpotong di tepi atas figur.** DIUKUR: dengan `rect` yang hanya membatasi sisi
  bawah, `tight_layout` menempatkan judul `loc="left"` berikut `pad`-nya sampai `y1 = 1,013`
  — di luar figur. Ruang atas kini dicadangkan eksplisit dalam inci
  (`_HEADING_RESERVE_IN`), sama seperti perlakuan kop.
- `textwrap.fill(override, width=62)` diganti anggaran karakter yang **diturunkan dari
  lebar panel**; angka 62 hanya benar untuk satu lebar figur dan diam-diam salah pada
  pratinjau UI yang lebarnya 7 inci.
- Watermark, legenda NaN, dan legenda "tidak ada batang yang memadai" sebelumnya
  berebut sudut kiri-bawah axes yang sama. Watermark pindah ke kanan-bawah figur, kedua
  legenda ke kiri-atas, dan jumlah elemen masuk ke label legendanya sendiri.
- Judul envelope tidak lagi berbunyi "Kombinasi seluruh kombinasi".

### Catatan pemeliharaan

`tests/data/vc6/` menambah ~28 MB ke repo. Ekspor Midas disimpan **apa adanya, tanpa
penyaringan** demi jejak audit langsung; `midas_force_local.csv` (12,6 MB) hanya melayani
cek-silang rotasi dan merupakan kandidat pemangkasan paling jelas bila ukurannya
dipermasalahkan. Provenance lengkap beserta sha256 setiap berkas ada di
`tests/data/vc6/SUMBER.md`.

## [0.7.1] — 2026-08-10 — Instalasi tanpa git

Ditemukan saat menjawab pertanyaan: dapatkah tool ini dipasang permanen di PC yang tidak
punya git terpasang? Jawabannya sebelumnya tidak — ada **dua** titik `git+` di rantai
instalasi, bukan satu. Tag v0.7.0 **tidak dipindahkan**, mengikuti preseden v0.3.1: berkas
di bawah ini adalah versi baru, bukan revisi diam-diam atas rilis yang sudah dipublikasikan.

### Fixed
- **`shell-kit @ git+...` diganti wheel-hosted.** `git+` memaksa `git` terpasang di mesin
  *pemasang*, bukan cuma mesin pengembang — pengguna yang menjalankan `uv sync`/`uv tool
  install` tanpa git akan gagal instalasi dengan pesan yang seolah tidak berkaitan. Wheel
  `shell-kit` v3.3.0 kini dibangun dari sumber tag yang sama lalu diunggah sebagai
  [release asset](https://github.com/kikifadilah31/plot_kontur_plate_fea_midas_civil/releases/tag/v3.3.0)
  repo yang sama; isinya identik, hanya jalur pengambilannya lewat HTTPS biasa.
- **`kft_pilecap_fem` sendiri juga dipasang lewat `git+` di README** — titik kedua yang
  luput pada perbaikan di atas. Repo dijadikan **publik** (sebelumnya privat; diperiksa
  dulu seluruh histori git untuk memastikan tidak ada berkas sensitif yang pernah
  ter-commit) dan setiap rilis kini turut mengunggah `pilecap_fem-<versi>-py3-none-any.whl`
  sebagai release asset, sehingga `uv tool install <URL wheel>` berjalan tanpa git sama
  sekali. Jalur `uvx --from git+...` tetap didukung bagi yang sudah punya git.
- Diverifikasi langsung: `uv sync` dan `uv tool install` dari wheel keduanya lulus
  (`exit 0`, seluruh entry point berfungsi) dengan `git` dihapus dari `PATH`.

### Changed
- `tests/test_packaging.py`: `test_shell_kit_dipin_ke_tag_bukan_branch` menjadi
  `test_shell_kit_bukan_git_dan_terkunci_ke_versi_rilis` — kini menolak `git+` dan
  menuntut tag versi di URL rilis **sama** dengan versi di nama berkas wheel.
- README: instalasi permanen memimpin dengan jalur wheel (tanpa git); jalur `uvx
  --from git+...` didokumentasikan sebagai alternatif untuk PC yang sudah punya git.

### Catatan pemeliharaan
Jalur wheel tersemat ke satu versi lewat URL-nya sendiri (tidak ada "selalu ambil
terbaru"). Setiap rilis baru **harus** menyertakan wheel `pilecap-fem` yang dibangun ulang
sebagai release asset agar jalur tanpa-git tetap berfungsi untuk versi itu.

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
