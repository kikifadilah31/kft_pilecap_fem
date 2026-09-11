// Dihasilkan oleh pilecap-fem. JANGAN diedit tangan -- berkas ini ditimpa setiap
// `pilecap-manual` dijalankan. Isinya ditarik dari kode versi ini; jangan disunting terpisah.

#set page(paper: "a4", margin: (x: 2cm, y: 2.4cm))
#set text(font: "New Computer Modern", size: 10pt, lang: "id")
#set par(justify: true)
#set heading(numbering: "1.1")
#show heading.where(level: 1): set text(size: 15pt)
#show heading.where(level: 2): set text(size: 12pt)
#show heading.where(level: 3): set text(size: 10.5pt)
#show link: set text(fill: rgb("#1a4b8c"))

#set table(inset: 5pt, stroke: 0.4pt + luma(170))
#show table.cell.where(y: 0): set text(weight: "bold")
// Rata kanan-kiri dimatikan di dalam sel: kolom tabel sempit, dan perataan paksa
// merenggangkan "maks abs m_x" menjadi celah-celah lebar yang terbaca berantakan.
#show table.cell: set par(justify: false)

// Penekanan istilah penting. Dipakai menggantikan HURUF KAPITAL di tengah kalimat:
// kapital mendadak memutus alur baca dan terbaca seperti membentak, sedangkan warna
// gelap + tebal tetap menonjol tanpa merusak tata bahasa.
#let tegas(isi) = text(fill: rgb("#1f3864"), weight: "bold")[#isi]

#set figure(numbering: "1")
#show figure.caption: set text(size: 8.5pt)

// Kotak peringatan. `judul` dicetak tebal di baris pertama; warnanya membedakan
// tingkat: merah = peringatan yang membatalkan keabsahan angka, biru = catatan.
#let kotak(judul, warna, isi) = block(
  width: 100%,
  inset: 8pt,
  radius: 2pt,
  fill: warna.lighten(90%),
  stroke: (left: 2.5pt + warna),
  [#text(weight: "bold", fill: warna.darken(20%))[#judul] \ #isi],
)


#set page(footer: context [
  #set text(size: 7.5pt, fill: luma(90))
  pilecap-fem v0.13.0 -- alat bantu perhitungan; wajib diperiksa dan disetujui engineer yang bertanggung jawab
  #h(1fr)
  #counter(page).display("1 / 1", both: true)
])

#align(center)[
  #v(4cm)
  #text(size: 26pt, weight: 700)[Panduan Lengkap pilecap-fem]
  #v(6mm)
  #text(size: 13pt)[Analisis pilecap berbasis metode elemen hingga,
  dari data masukan sampai penulangan menurut SNI 2847:2019]
  #v(14mm)
  #text(size: 16pt, weight: 700)[Versi 0.13.0]
  #v(3mm)
  #text(size: 10pt)[Sistem satuan internal: SI (N, m, Pa)]
]
#v(1fr)

Dokumen ini #tegas[berdiri sendiri]. Seluruh yang diperlukan untuk menilai, memasang, menjalankan, dan menafsirkan hasil perangkat lunak ini ada di dalamnya; tidak ada bagian yang menuntut pembaca membuka halaman web mana pun.

Isinya dihasilkan otomatis dari kode versi di atas, sehingga setiap daftar field, pasal, keterbatasan, dan versi pustaka yang disebut di sini adalah yang benar-benar berlaku pada versi tersebut -- bukan salinan yang dirawat terpisah.

#kotak([PENTING], rgb("#b91c1c"))[
Bila nomor versi pada sampul ini berbeda dari yang ditampilkan `pilecap-run --version` di komputer Anda, #tegas[panduan ini bukan panduan untuk perangkat lunak yang Anda pasang]. Mintalah panduan untuk versi tersebut, atau hasilkan sendiri dengan perintah `pilecap-manual`.
]

#pagebreak()

#outline(title: [Daftar Isi], depth: 2)

#pagebreak()

#outline(title: [Daftar Gambar], target: figure.where(kind: image))

#outline(title: [Daftar Tabel], target: figure.where(kind: table))

#pagebreak()

= Ringkasan eksekutif <bab-ringkasan>

== Apa yang dikerjakan perangkat lunak ini

`pilecap-fem` menganalisis #tegas[pilecap] -- pelat beton yang meneruskan beban dari kolom jembatan atau gedung ke kelompok tiang pancang -- lalu menghitung tulangan yang diperlukannya menurut #tegas[SNI 2847:2019].

Pilecap dimodelkan sebagai pelat lentur dengan metode elemen hingga. Reaksi tiang yang sudah Anda peroleh dari analisis struktur atas diterapkan sebagai beban, kolom dijepit, lalu momen dan geser di setiap elemen dihitung dan diterjemahkan menjadi luas tulangan perlu, diameter, dan spasi.

Satu perintah mengerjakan seluruh rantai itu: pembuatan mesh, analisis, kontur, envelope antar kombinasi beban, lembar perhitungan yang dapat diaudit, dan laporan PDF lengkap.

#figure(
  image("_figur_pdf/skema-tumpuan-beban.svg", width: 80%),
  caption: [Siapa menumpu siapa dalam model ini.],
)

== Apa yang tidak dikerjakannya

Batas ini dinyatakan lebih dulu, sebelum kemampuannya, karena justru inilah yang menentukan apakah perangkat lunak ini cocok untuk pekerjaan Anda.

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Di luar lingkup], [Keterangan],
  [Perhitungan reaksi pile], [Reaksi tiang adalah #tegas[masukan], bukan keluaran. Ia harus sudah diperoleh dari analisis struktur atas dan diserahkan sebagai data.],
  [Penentuan jumlah dan jarak batang secara otomatis], [Luas tulangan perlu dihitung, dan diameter atau spasi dipilih menurut mode yang Anda tetapkan. Penataan batang di gambar kerja tetap keputusan engineer.],
  [Metode strut-and-tie untuk pilecap tebal], [Bila pilecap berperilaku sebagai komponen tinggi, model pelat lentur yang dipakai di sini tidak berlaku dan hasilnya tidak sah. Rasio geometrinya dilaporkan tanpa vonis.],
  [Analisis nonlinier, retak, dan efek jangka panjang], [Seluruh analisis bersifat elastis linier. Rangkak, susut, dan kekakuan tereduksi akibat retak tidak dimodelkan.],
  [Interaksi tanah dan struktur], [Pile dimodelkan sebagai tumpuan jepit pada cakram kepala pile, bukan sebagai elemen yang berinteraksi dengan tanah.],
),
  caption: [Hal-hal yang sengaja tidak dikerjakan perangkat lunak ini.],
)

Selain itu terdapat #tegas[6 butir] yang acuannya belum dikonfirmasi, sehingga pengecekan terkait tidak dilakukan dan dinyatakan `NOT_EVALUATED` di dalam laporan. Rinciannya ada pada bab #link(<bab-keterbatasan>)[Asumsi dan keterbatasan].

== Tingkat pertanggungjawaban

Perangkat lunak ini dibangun untuk #tegas[desain nyata yang dilaksanakan di lapangan], bukan untuk latihan atau studi. Konsekuensinya adalah enam hal berikut, yang berlaku pada setiap versi dan tidak dapat dinegosiasikan.

#enum(
  start: 1,
  [
Tidak ada angka tanpa sumber. Setiap besaran yang masuk ke perhitungan dapat ditelusuri ke berkas masukan, pasal kode, atau nilai yang Anda tetapkan sendiri.
  ],
  [
Nilai yang belum dikonfirmasi tidak pernah diganti bawaan diam-diam. Prosesnya berhenti dengan pesan yang menyebutkan apa yang kurang.
  ],
  [
Pengecekan yang belum dapat dilakukan dinyatakan terus terang sebagai belum dilakukan, bukan dihilangkan dari laporan.
  ],
  [
Setiap run menulis folder baru dan tidak pernah menimpa hasil sebelumnya.
  ],
  [
Setiap keluaran memuat sidik sha256 berkas masukannya, versi perangkat lunak, dan versi setiap pustaka yang dipakai.
  ],
  [
Hasilnya adalah alat bantu. Ia wajib diperiksa dan disetujui engineer yang bertanggung jawab sebelum dipakai membangun apa pun.
  ],
)

== Dasar untuk mempercayai angkanya

Hasil perangkat lunak ini telah dibandingkan elemen demi elemen terhadap #tegas[Midas Civil], perangkat lunak komersial yang lazim dipakai di industri. Model pembandingnya #tegas[diimpor dari berkas yang ditulis perangkat lunak ini sendiri], sehingga penomoran node dan elemennya identik satu lawan satu dan perbandingannya bukan perkiraan.

Selisih terbesar yang terukur pada momen puncak -- besaran yang menentukan tulangan -- adalah #tegas[0,515%]. Perbandingan ini berjalan sebagai syarat rilis: versi yang gagal memenuhinya tidak diterbitkan. Angka lengkap beserta tiga hal yang perlu dibaca jujur disajikan pada bab #link(<bab-bukti>)[Bukti dan validasi].

== Apa yang dibutuhkan perusahaan untuk memakainya

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Kebutuhan], [Keterangan],
  [Perangkat keras], [Satu komputer Windows biasa. Tidak ada kebutuhan server.],
  [Lisensi], [Tidak ada server lisensi, tidak ada biaya per pengguna.],
  [Pemasangan], [Dua perintah salin-tempel. Tidak memerlukan hak administrator.],
  [Unduhan pertama], [Sekitar 60 MB, sekali saja per komputer.],
  [Jaringan], [Hanya saat memasang. Setelah terpasang, bekerja sepenuhnya luring.],
  [Data], [Seluruh keluaran ditulis sebagai berkas biasa di disk perusahaan sendiri; tidak ada data yang dikirim ke mana pun.],
  [Pelatihan], [4 contoh lengkap ikut terpasang dan dapat dijalankan tanpa menyiapkan data apa pun.],
  [Antarmuka], [Tersedia formulir grafis bagi pengguna yang tidak terbiasa dengan baris perintah.],
),
  caption: [Prasyarat penerapan di lingkungan perusahaan.],
)

== Pernyataan tanggung jawab

#kotak([HATI-HATI], rgb("#b91c1c"))[
#tegas[\[DRAFT - redaksi final belum ditetapkan, PRD Bagian 17 item 18\]] Hasil perhitungan ini dihasilkan secara otomatis oleh pilecap-fem v0.13.0 dan merupakan ALAT BANTU. Hasil wajib diperiksa dan disetujui oleh engineer yang bertanggung jawab. Pengecekan di luar ruang lingkup PRD Bagian 1.4 TIDAK dilakukan oleh tool ini.
]

#pagebreak()

= Cara memasang <bab-pasang>

== Yang perlu disiapkan

Komputer Windows dengan sambungan internet, dan ruang kosong sekitar #tegas[60 MB]. Anda #tegas[tidak] memerlukan hak administrator, tidak perlu memasang Python lebih dulu, dan tidak perlu mengenal perkakas pengembang apa pun.

== Membuka PowerShell

Seluruh perintah pada bab ini diketik di #tegas[PowerShell], jendela hitam tempat perintah diketik satu per satu.

#enum(
  start: 1,
  [
Tekan tombol Start.
  ],
  [
Ketik `PowerShell`.
  ],
  [
Tekan Enter.
  ],
)

Akan muncul jendela dengan satu baris teks yang diakhiri tanda `>`. Di situlah perintah diketik. Untuk menempelkan perintah yang Anda salin dari dokumen ini, klik kanan di dalam jendela tersebut, lalu tekan Enter untuk menjalankannya.

Satu hal yang sering membingungkan pemakai baru: #tegas[perintah yang berhasil umumnya tidak menampilkan apa pun]. Jendela yang kembali ke tanda `>` tanpa pesan berarti perintahnya selesai dengan baik. Pesan panjang berwarna merah barulah tanda kegagalan.

== Langkah 1 -- memasang uv

`uv` adalah perkakas yang mengurus pemasangan. Ia dipasang sekali per komputer. Salin dan jalankan perintah berikut.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "powershell -ExecutionPolicy ByPass -c \"irm https://astral.sh/uv/install.ps1 | iex\""),
)

#kotak([PENTING], rgb("#b91c1c"))[
Setelah perintah itu selesai, #tegas[tutup jendela PowerShell lalu buka lagi]. Tanpa itu Windows belum mengenali perintah `uv` yang baru dipasang, dan langkah berikutnya akan gagal dengan pesan seolah-olah pemasangannya tidak berhasil.
]

Pada jendela yang baru, pastikan `uv` sudah dikenali.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "uv --version"),
)

Perintah itu harus menampilkan satu baris yang diawali kata `uv`.

== Langkah 2 -- memasang pilecap-fem

Satu perintah, disalin utuh termasuk alamat panjang di ujungnya.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "uv tool install --python 3.12 https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.13.0/pilecap_fem-0.13.0-py3-none-any.whl"),
)

Bagian-bagian perintah tersebut berarti sebagai berikut.

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Bagian], [Artinya],
  [`uv tool install`], [Pasang secara permanen, sehingga dapat dipanggil kapan saja dari jendela PowerShell mana pun.],
  [`--python 3.12`], [#tegas[Wajib], dan bukan sekadar anjuran -- lihat catatan di bawah.],
  [alamat di ujung], [Satu berkas yang diunduh lewat sambungan HTTPS biasa. Tidak ada akun yang perlu dibuat.],
),
  caption: [Arti setiap bagian perintah pemasangan.],
)

#kotak([PERINGATAN], rgb("#b45309"))[
Bagian `--python 3.12` tidak boleh dihilangkan. Pustaka solver yang dipakai perangkat lunak ini hanya menyediakan berkas biner untuk versi tersebut. Pada versi Python yang lebih baru ia #tegas[tetap terpasang tanpa keluhan], lalu gagal saat dijalankan dengan pesan tentang DLL yang terbaca seperti kerusakan pemasangan padahal bukan.
]

== Langkah 3 -- memastikan pemasangan berhasil

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "pilecap-run --version"),
)

Perintah itu harus menampilkan nomor versi. Bila yang muncul adalah #tegas[0.13.0], panduan ini memang panduan untuk perangkat lunak yang baru Anda pasang. Bila berbeda, mintalah panduan untuk versi tersebut -- daftar field dan keterbatasan dapat berbeda antarversi.

== Bila gagal

#figure(
  table(
  columns: 3,
  align: (left, left, left),
  [Gejala], [Sebab], [Tindakan],
  [`uv` tidak dikenali sebagai perintah], [Jendela PowerShell masih yang lama.], [Tutup jendelanya, buka yang baru, ulangi.],
  [Pesan menyebut `membutuhkan Python 3.12`], [Bagian `--python 3.12` terlewat.], [Ulangi perintah pemasangan secara utuh.],
  [Pesan menyebut DLL gagal dimuat], [Terpasang pada versi Python yang keliru.], [Ulangi pemasangan dengan menambahkan `--force`.],
  [Unduhan berhenti di tengah], [Sambungan internet terputus atau diblokir.], [Ulangi perintahnya; unduhan dimulai dari awal.],
  [Pesan menyebut berkas sedang dibuka program lain], [Berkas keluaran masih terbuka di penampil PDF.], [Tutup berkasnya, jalankan ulang perintahnya.],
),
  caption: [Kegagalan yang paling sering ditemui beserta tindakannya.],
)

== Memperbarui ke versi yang lebih baru

Perintahnya sama dengan pemasangan, ditambah `--force`. Tanpa itu `uv` melihat bahwa perangkat lunak ini sudah ada lalu tidak mengerjakan apa-apa, sehingga versi lama tetap terpakai tanpa pesan apa pun.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "uv tool install --force --python 3.12 https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.13.0/pilecap_fem-0.13.0-py3-none-any.whl"),
)

Alamat pada perintah di atas menunjuk versi #tegas[0.13.0]. Untuk versi lain, bagian nomor versinya diganti. Seluruh rilis beserta alamatnya tersedia pada halaman berikut.

#link("https://github.com/kikifadilah31/kft_pilecap_fem/releases")[#raw("https://github.com/kikifadilah31/kft_pilecap_fem/releases")]

#pagebreak()

= Menjalankan pertama kali <bab-jalan-pertama>

Perangkat lunak ini membawa #tegas[4 contoh lengkap]. Menjalankan salah satunya adalah cara tercepat memastikan pemasangan berhasil dan melihat bentuk keluarannya, tanpa perlu menyiapkan data sendiri.

== Contoh yang tersedia

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Nama], [Isi],
  [`ex01_standard_4pile`], [Pilecap persegi dengan 4 tiang dan pier persegi. Contoh paling sederhana; mulailah dari sini.],
  [`ex02_standard_12pile`], [Pilecap besar dengan 12 tiang dan pier lingkaran. Menunjukkan perilaku model yang lebih halus dan waktu analisis yang lebih panjang.],
  [`ex03_custom_polygon`], [Pilecap dengan denah tidak persegi, didefinisikan sebagai poligon bebas.],
  [`ex04_pile_overlap_pier`], [Tiang yang sebagian tertutup pier. Kasus khusus dengan penanganan tersendiri, dijelaskan pada bab dasar teori.],
),
  caption: [Contoh bawaan yang ikut terpasang.],
)

== Menyalin contoh ke komputer Anda

Buat satu folder kerja, lalu salin contohnya ke sana. Perintah berikut membuat folder `latihan` di dalam Documents dan mengisinya dengan contoh pertama.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "cd $HOME\\Documents\nmkdir latihan\ncd latihan\npilecap-mesh --init-example ex01_standard_4pile"),
)

Folder itu kini berisi berkas masukan contoh: satu berkas konfigurasi berformat JSON dan beberapa berkas data berformat CSV.

== Menjalankan analisis lengkap

Satu perintah mengerjakan seluruh rantai: pembuatan mesh, analisis, kontur, envelope, lembar perhitungan, dan laporan PDF.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "pilecap-run --pdf"),
)

Perintah ini memerlukan waktu beberapa puluh detik sampai beberapa menit, bergantung pada ukuran model. Selama berjalan ia mencetak baris kemajuan. Baris terakhir yang diawali `OK` menunjukkan nama folder hasilnya.

Seluruh keluaran ditulis ke dalam folder `output`, dengan #tegas[satu subfolder baru untuk setiap kali dijalankan]. Hasil sebelumnya tidak pernah tertimpa. Isi folder tersebut diuraikan pada bab #link(<bab-keluaran>)[Apa yang dihasilkan].

== Menggunakan formulir grafis

Bagi pengguna yang tidak terbiasa mengetik perintah, tersedia formulir yang berjalan di peramban. Formulir tersebut menanyakan setiap masukan satu per satu, lengkap dengan penjelasan dan gambar, lalu menuliskan berkas konfigurasinya untuk Anda.

Fitur ini perlu dipasang sekali dengan menambahkan bagian `[ui]` pada perintah pemasangan.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "uv tool install --force --python 3.12 \"pilecap-fem[ui] @ https://github.com/kikifadilah31/kft_pilecap_fem/releases/download/v0.13.0/pilecap_fem-0.13.0-py3-none-any.whl\""),
)

Setelah itu formulirnya dibuka dengan satu perintah.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "pilecap-ui"),
)

Seluruh isian pada formulir tersebut adalah field yang sama dengan yang diuraikan pada bab #link(<bab-konfigurasi>)[Referensi konfigurasi].

#pagebreak()

= Menyiapkan data sendiri <bab-masukan>

Satu folder masukan berisi satu berkas konfigurasi dan beberapa berkas data. Perangkat lunak mengenali berkas-berkas itu dari #tegas[pola namanya], sehingga Anda tidak perlu menyebutkannya satu per satu pada perintah.

== Berkas yang dikenali

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Isi], [Pola nama berkas],
  [Berkas konfigurasi utama: geometri, material, mesh, dan pilihan desain], [`*config*.json`],
  [Reaksi tiap tiang per kombinasi beban, dari analisis struktur atas], [`*react*.csv`],
  [Koordinat pusat tiap tiang], [`*pile*coord*.csv`],
  [Denah pilecap sebagai poligon, bila bentuknya tidak persegi], [`*cap*polygon*.csv`],
  [Denah pier sebagai poligon, bila bentuknya tidak persegi maupun lingkaran], [`*pier*polygon*.csv`],
),
  caption: [Pola nama berkas masukan yang dikenali otomatis.],
)

#kotak([PERINGATAN], rgb("#b45309"))[
Bila #tegas[lebih dari satu] berkas cocok dengan pola yang sama, perangkat lunak berhenti dan menyebutkan berkas mana saja yang bertabrakan. Ia tidak pernah memilih salah satu sendiri: menebak berkas mana yang Anda maksud berarti menganalisis data yang salah tanpa Anda ketahui.
]

== Sistem koordinat

Koordinat pilecap, tiang, dan pier ditulis dalam #tegas[satu sistem sumbu yang sama]. Titik asalnya bebas Anda tentukan, asalkan ketiganya konsisten.

#figure(
  image("_figur_pdf/sistem-koordinat.svg", width: 85%),
  caption: [Satu sistem sumbu untuk ketiga blok geometri.],
)

== Satuan

Angka pada berkas masukan ditulis dalam satuan yang #tegas[Anda tetapkan sendiri] melalui bagian `units`. Perangkat lunak mengubahnya ke satuan internal, menghitung, lalu menyajikan hasilnya kembali dalam satuan tampilan yang lazim. Anda tidak perlu mengonversi apa pun secara manual.

#figure(
  table(
  columns: 3,
  align: (left, left, left),
  [Besaran], [Pilihan satuan masukan], [Bawaan],
  [Panjang], [`mm`, `cm`, `m`], [`mm`],
  [Gaya], [`N`, `kN`, `MN`], [`kN`],
  [Tegangan], [`Pa`, `kPa`, `MPa`, `GPa`], [`MPa`],
),
  caption: [Satuan masukan yang dapat dipilih pada bagian `units`.],
)

Hasil perhitungan selalu disajikan dalam satuan tampilan berikut.

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Besaran], [Satuan tampilan],
  [Panjang, lendutan], [`mm`],
  [Gaya, reaksi], [`kN`],
  [Momen per satuan lebar], [`kNm/m`],
  [Geser per satuan lebar], [`kN/m`],
  [Tegangan, mutu bahan], [`MPa`],
  [Luas tulangan per satuan lebar], [`mm^2/m`],
  [Luas sengkang per satuan jarak], [`mm^2/mm`],
),
  caption: [Satuan tampilan hasil perhitungan.],
)

#pagebreak()

= Referensi konfigurasi <bab-konfigurasi>

Seluruh masukan perangkat lunak ini terdiri atas #tegas[60 field] yang dikelompokkan ke dalam #tegas[11 bagian]. Bab ini menguraikan seluruhnya, sehingga berkas konfigurasi dapat disusun tanpa rujukan lain.

Field ditulis di dalam berkas konfigurasi berformat JSON dengan nama bagian sebagai kunci luar dan nama field sebagai kunci dalam. Formulir grafis `pilecap-ui` menanyakan field yang sama dan menuliskan berkas itu untuk Anda.

#kotak([CATATAN], rgb("#1d4ed8"))[
Sebagian field hanya berlaku pada cabang tertentu -- misalnya lebar pier hanya berlaku bila pier berbentuk persegi. Field semacam itu #tegas[dihilangkan sama sekali] dari berkas konfigurasi pada cabang yang lain, bukan ditulis bernilai kosong. Setiap field yang bersyarat menyebutkan syaratnya sendiri di bawah ini.
]

== Proyek <cfg-proyek>

Identitas run. Tidak memengaruhi satu pun angka hasil, tetapi ikut tercetak di judul setiap gambar, di `calc_sheet.md`, dan di `run_manifest.json` -- itulah yang membuat berkas hasil dapat ditelusuri kembali ke pekerjaan dan orangnya.

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`name`], [teks], [ya], [`""`], [--],
  [`engineer`], [teks], [ya], [`""`], [--],
  [`date`], [teks], [ya], [tanggal hari ini], [--],
),
  caption: [Ringkasan field bagian Proyek.],
)

=== `project.name` -- Nama proyek

Muncul sebagai judul di setiap plot dan di kepala laporan. Contoh: "Jembatan A - Pilecap P3".

=== `project.engineer` -- Engineer

Nama Anda atau tim perencana. Dicetak di laporan sebagai penanggung jawab perhitungan.

=== `project.date` -- Tanggal

Tanggal desain, bukan tanggal run (waktu run dicatat terpisah dan otomatis). Format bebas; YYYY-MM-DD memudahkan pengurutan folder.

== Satuan masukan <cfg-satuan-masukan>

Seluruh angka di formulir ini ditulis dalam satuan yang dipilih di sini, dan label tiap field langsung ikut berubah. Di dalam mesin hitung semuanya diubah ke SI (N, m, Pa); Anda tidak perlu mengonversi apa pun sendiri. Yang #tegas[wajib] Anda pastikan: pilihan di sini harus cocok dengan angka yang benar-benar Anda ketik -- salah pilih adalah satu-satunya kesalahan di formulir ini yang tidak dapat dideteksi tool, karena 1200 mm dan 1200 m sama-sama angka yang sah.

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`length`], [satu pilihan], [ya], [`"mm"`], [--],
  [`force`], [satu pilihan], [ya], [`"kN"`], [--],
  [`stress`], [satu pilihan], [ya], [`"MPa"`], [--],
),
  caption: [Ringkasan field bagian Satuan masukan.],
)

=== `units.length` -- Panjang

Satuan untuk semua ukuran: tebal, panjang, diameter, spasi, selimut. Berlaku juga untuk CSV geometri di folder input.

Nilai yang sah: `mm`, `cm`, `m`.

=== `units.force` -- Gaya

Satuan untuk reaksi pile `Pz` di `pile_reactions.csv` dan untuk berat jenis beton (kN/m3).

Nilai yang sah: `N`, `kN`, `MN`.

=== `units.stress` -- Tegangan

Satuan untuk f'c, E, dan fy. 1 MPa = 1 N/mm2 -- itulah satuan yang dipakai SNI 2847:2019.

Nilai yang sah: `Pa`, `kPa`, `MPa`, `GPa`.

== Pilecap <cfg-pilecap>

Pelat beton yang menyatukan kepala tiang. Dimodelkan sebagai pelat datar di bidang XY dengan tebal seragam. Bila Anda menaruh CSV poligon di folder input, bentuknya diambil dari sana dan panjang X/Y di bawah diabaikan.

#figure(
  image("_figur_pdf/sistem-koordinat.svg", width: 80%),
  caption: [Ilustrasi untuk bagian Pilecap.],
)

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`thickness`], [angka desimal], [ya], [`1200.0`], [`mm`],
  [`length_x`], [angka desimal], [ya], [`4800.0`], [`mm`],
  [`length_y`], [angka desimal], [ya], [`4800.0`], [`mm`],
  [`origin`], [sepasang angka], [ya], [`[0.0, 0.0]`], [`mm`],
),
  caption: [Ringkasan field bagian Pilecap.],
)

=== `pilecap.thickness` -- Tebal

Tebal pelat, dipakai untuk kekakuan lentur, tinggi efektif tulangan, dan kapasitas geser. Ini besaran paling berpengaruh di seluruh model: kekakuan lentur pelat sebanding dengan tebal #tegas[pangkat tiga], sehingga tebal yang meleset 10% menggeser lendutan sekitar 30%.

Nilainya tidak boleh kurang dari `0.0`.

=== `pilecap.length_x` -- Panjang arah X

Ukuran pilecap arah memanjang (sumbu X). Dipakai hanya bila bentuknya persegi -- yaitu bila tidak ada CSV poligon pilecap di folder input.

=== `pilecap.length_y` -- Panjang arah Y

Ukuran pilecap arah melintang (sumbu Y). Sama seperti panjang X: diabaikan bila bentuknya diambil dari CSV poligon.

=== `pilecap.origin` -- Titik asal \[x, y\]

Koordinat #tegas[titik pusat] pilecap persegi, bukan sudutnya. Titik ini menentukan letak pilecap terhadap grid pile dan pier, jadi ketiganya harus memakai sistem koordinat yang sama. Biarkan \[0, 0\] bila Anda menempatkan semuanya relatif terhadap pusat pilecap.

== Pile <cfg-pile>

Tiang pancang/bor yang memikul pilecap. Di model ini pile #tegas[bukan] tumpuan: reaksinya (`Pz` dari `pile_reactions.csv`) diterapkan sebagai #tegas[beban ke atas] pada daerah lingkaran kepala tiang, sementara pier-lah yang dijepit. Karena reaksi pile sudah Anda ketahui dari analisis struktur atas, cara ini membuat keseimbangan gaya dapat diperiksa persis -- itulah cek VC-0 yang dijalankan setiap run.

#figure(
  image("_figur_pdf/skema-tumpuan-beban.svg", width: 80%),
  caption: [Ilustrasi untuk bagian Pile.],
)

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`diameter`], [angka desimal], [ya], [`800.0`], [`mm`],
  [`n_col`], [bilangan bulat], [ya], [`2`], [--],
  [`n_row`], [bilangan bulat], [ya], [`2`], [--],
  [`spacing_x`], [angka desimal], [ya], [`2400.0`], [`mm`],
  [`spacing_y`], [angka desimal], [ya], [`2400.0`], [`mm`],
  [`grid_origin`], [sepasang angka], [ya], [`[0.0, 0.0]`], [`mm`],
  [`modeling`], [satu pilihan], [ya], [`"pressure"`], [--],
),
  caption: [Ringkasan field bagian Pile.],
)

=== `pile.diameter` -- Diameter

Diameter kepala tiang. Menentukan luas lingkaran tempat reaksi pile disebar; diameter yang lebih kecil memusatkan beban dan menaikkan momen lokal. Selalu dibutuhkan -- juga sebagai bawaan bila CSV koordinat pile tidak punya kolom diameter.

=== `pile.n_col` -- Jumlah kolom

Banyaknya pile pada arah X untuk susunan grid teratur. Total pile = kolom x baris. Untuk susunan tidak teratur, pakai CSV koordinat pile di folder input dan abaikan field grid ini.

Nilainya tidak boleh kurang dari `1`.

=== `pile.n_row` -- Jumlah baris

Banyaknya pile pada arah Y untuk susunan grid teratur.

Nilainya tidak boleh kurang dari `1`.

=== `pile.spacing_x` -- Spasi arah X

Jarak antar sumbu pile pada arah X. Praktik umum menuntut jarak \>= 3x diameter pile; tool memperingatkan bila pile saling tumpang tindih, tetapi kecukupan jarak terhadap standar tetap keputusan Anda.

=== `pile.spacing_y` -- Spasi arah Y

Jarak antar sumbu pile pada arah Y. Boleh berbeda dari spasi X; susunan yang tidak seragam sama sekali dibuat lewat CSV koordinat pile.

=== `pile.grid_origin` -- Pusat grid \[x, y\]

Titik pusat susunan pile. Grid dibangun simetris terhadap titik ini, sehingga \[0, 0\] menempatkannya tepat di tengah bila pilecap juga berpusat di \[0, 0\].

=== `pile.modeling` -- Pemodelan beban

Cara reaksi pile masuk ke model. `pressure` (disarankan) menyebarkan Pz merata pada seluruh lingkaran kepala tiang -- mendekati kenyataan dan menghasilkan momen yang halus. `nodal` menempatkannya sebagai gaya titik di node-node yang sama; totalnya identik, tetapi momen tepat di kepala tiang menjadi lebih runcing. Keduanya lulus cek keseimbangan.

Nilai yang sah: `pressure`, `nodal`.

== Pier <cfg-pier>

Kolom/pilar yang berdiri di atas pilecap. Di model ini pier menjadi #tegas[tumpuan]: seluruh node di dalam daerah pier dijepit penuh (6 derajat kebebasan), menahan beban yang didorong pile dari bawah. Momen desain dibaca di #tegas[muka] pier, sesuai praktik SNI, karena momen tepat di sumbu tumpuan bersifat singular pada model pelat.

#figure(
  image("_figur_pdf/tumpang-tindih-pile-pier.svg", width: 80%),
  caption: [Ilustrasi untuk bagian Pier.],
)

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`shape`], [satu pilihan], [ya], [`"rectangular"`], [--],
  [`width_x`], [angka desimal], [bersyarat], [`1200.0`], [`mm`],
  [`width_y`], [angka desimal], [bersyarat], [`1200.0`], [`mm`],
  [`diameter`], [angka desimal], [bersyarat], [`1800.0`], [`mm`],
  [`centerline`], [sepasang angka], [ya], [`[0.0, 0.0]`], [`mm`],
  [`support`], [satu pilihan], [ya], [`"fixed"`], [--],
  [`max_pile_overlap_fraction`], [angka desimal], [tidak], [`null`], [--],
),
  caption: [Ringkasan field bagian Pier.],
)

=== `pier.shape` -- Bentuk

Penampang pier di bidang pilecap. `rectangular` meminta lebar X dan Y; `circular` meminta satu diameter. Pilihan ini mengubah field yang tampil di bawah dan menentukan letak muka pier tempat momen desain dibaca.

Nilai yang sah: `rectangular`, `circular`.

=== `pier.width_x` -- Lebar arah X

Ukuran pier searah sumbu X. Semakin lebar, semakin luas daerah jepit dan semakin kecil momen di mukanya -- jadi angka ini harus ukuran pier yang sebenarnya, bukan perkiraan yang dibulatkan ke atas.

#tegas[Hanya berlaku bila bentuk pier `rectangular`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

=== `pier.width_y` -- Lebar arah Y

Ukuran pier searah sumbu Y. Bersama lebar X menentukan daerah yang dijepit dan letak muka pier tempat momen desain arah Y dibaca.

#tegas[Hanya berlaku bila bentuk pier `rectangular`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

=== `pier.diameter` -- Diameter

Diameter pier bulat. Daerah jepitnya berupa lingkaran dengan diameter ini.

#tegas[Hanya berlaku bila bentuk pier `circular`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

=== `pier.centerline` -- Titik pusat \[x, y\]

Koordinat sumbu pier, dalam sistem koordinat yang sama dengan pilecap dan pile. Untuk lebih dari satu pier, pakai CSV poligon pier di folder input -- formulir ini hanya menampung satu pier.

=== `pier.support` -- Tumpuan

Jenis tumpuan di daerah pier. Hanya jepit penuh 6 DOF yang tersedia di v1.0; tumpuan pegas (pile sebagai pegas, pier sebagai beban) belum diimplementasikan dan sengaja tidak ditawarkan agar tidak ada pilihan yang tampak ada tetapi tidak berfungsi.

Nilai yang sah: `fixed`.

=== `pier.max_pile_overlap_fraction` -- Batas tumpang tindih pile-pier

Kosongkan (bawaan) bila pile #tegas[tidak] boleh menindih pier — run akan ditolak bila ternyata menindih. Diisi = Anda mengizinkannya sampai fraksi ini (mis. 0,15 = paling banyak 15% luas pile berada di dalam pier). #tegas[Konsekuensi:] bagian yang berada di dalam pier #tegas[tidak] melenturkan pelat — pier dimodelkan jepit sempurna, jadi gaya di sana tersalur langsung ke pier (aksi strut) dan kapasitasnya #tegas[harus] Anda cek terpisah; tool tidak menghitungnya. Untuk geometri seperti ini angka desain juga menjadi sensitif terhadap kehalusan mesh. Besarnya dilaporkan terpisah di calc sheet (komponen strut vs komponen diskretisasi).

Nilainya harus antara `0.0` dan `1.0`.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

== Material <cfg-material>

Properti beton pilecap. Pelat dimodelkan elastis linier: satu nilai E dan satu Poisson untuk seluruh pelat. Retak, rangkak, dan susut #tegas[tidak] dimodelkan -- bila Anda ingin memperhitungkan penurunan kekakuan akibat retak, turunkan sendiri nilai E yang Anda isi dan tuliskan alasannya di kolom asal nilai E.

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`fc`], [angka desimal], [ya], [`30.0`], [`MPa`],
  [`E`], [angka desimal], [ya], [`25000.0`], [`MPa`],
  [`E_source`], [teks], [ya], [`""`], [--],
  [`poisson`], [angka desimal], [ya], [`0.2`], [--],
  [`density`], [angka desimal], [tidak], [`24.0`], [`kN/m^3`],
),
  caption: [Ringkasan field bagian Material.],
)

=== `material.fc` -- f'c

Kuat tekan beton yang disyaratkan pada umur 28 hari (silinder). Dipakai untuk kapasitas lentur dan geser menurut SNI 2847:2019, dan untuk menamai material pada berkas ekspor Midas. #tegas[Tidak] dipakai menghitung E -- E Anda isi sendiri di bawah.

Nilainya tidak boleh kurang dari `0.0`.

=== `material.E` -- Modulus elastisitas E

Modulus elastisitas beton -- ukuran kekakuannya. Menentukan besar lendutan, tetapi hampir tidak memengaruhi momen desain pada model ini karena tumpuannya statis tertentu terhadap beban yang sudah diketahui. Tool #tegas[tidak] menghitung E dari f'c: rumusnya belum dikonfirmasi pasalnya, dan angka tanpa sumber dilarang. Nilai lazim beton normal fc30: sekitar 25.000-27.000 MPa.

Nilainya tidak boleh kurang dari `0.0`.

=== `material.E_source` -- Asal nilai E

#tegas[Wajib diisi] -- run akan ditolak bila kosong. Tuliskan dari mana angka E di atas berasal, karena inilah satu-satunya jejak yang membuat nilai itu dapat diperiksa orang lain. Dicetak apa adanya di calc\_sheet.md dan run\_manifest.json. Mis. "SNI 2847:2019 Ps. 19.2.2.1 untuk wc=2400" atau "hasil uji lab 2026-01-15" atau "0,5 Ec untuk memperhitungkan retak".

=== `material.poisson` -- Rasio Poisson

Perbandingan regangan melintang terhadap regangan searah beban. Untuk beton lazimnya 0,15-0,20. Pada pelat, angka ini ikut menentukan seberapa besar momen di satu arah membangkitkan momen di arah tegak lurusnya; pengaruhnya nyata tetapi jauh lebih kecil daripada tebal pelat.

Nilainya harus antara `0.0` dan `0.499999999`.

=== `material.density` -- Berat jenis

Berat beton per satuan volume, lazimnya 24 kN/m3. #tegas[Hanya] dipakai bila Anda mencentang "Sertakan berat sendiri pilecap" di bagian Analisis; bila tidak, angka ini tidak memengaruhi hasil sama sekali. Boleh dikosongkan.

Nilainya tidak boleh kurang dari `0.0`.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

== Mesh <cfg-mesh>

Pelat dipotong menjadi ribuan elemen kecil segi empat; di setiap elemen momen dan geser dihitung. Semakin kecil elemennya semakin teliti hasilnya, tetapi semakin lama analisisnya -- dan hubungannya tidak linier: memperkecil ukuran jadi setengah membuat jumlah elemen menjadi empat kali. Bawaan di sini sudah menghasilkan mesh yang halus untuk pilecap berukuran lazim. Kontrak numerik tool ini menuntut seluruh elemen berupa #tegas[segi empat]; bila gmsh terpaksa menyisipkan segitiga, run dihentikan alih-alih diam-diam memakai elemen bermutu lebih rendah.

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`size_mode`], [satu pilihan], [ya], [`"uniform"`], [--],
  [`size_global`], [angka desimal], [ya], [`130.0`], [`mm`],
  [`size_local_pile`], [angka desimal], [bersyarat], [`null`], [`mm`],
  [`size_local_pier`], [angka desimal], [bersyarat], [`null`], [`mm`],
  [`algorithm`], [satu pilihan], [ya], [`11`], [--],
  [`recombination_algorithm`], [satu pilihan], [ya], [`3`], [--],
  [`recombine`], [ya atau tidak], [ya], [`true`], [--],
  [`require_all_quad`], [ya atau tidak], [ya], [`true`], [--],
  [`element_order`], [satu pilihan], [ya], [`1`], [--],
),
  caption: [Ringkasan field bagian Mesh.],
)

=== `mesh.size_mode` -- Mode ukuran

`uniform` memakai satu ukuran elemen di seluruh pelat -- paling mudah diprediksi dan paling sering tepat. `graded` memperhalus mesh hanya di sekitar pile dan/atau pier, tempat tegangan berubah paling cepat, sehingga hasil sama telitinya dengan jumlah elemen lebih sedikit.

Nilai yang sah: `uniform`, `graded`.

=== `mesh.size_global` -- Ukuran global

Panjang sisi elemen di seluruh pelat. Patokan praktis: ambil sekitar 1/6 diameter pile atau lebih kecil, supaya lingkaran kepala tiang terwakili oleh cukup banyak elemen. Terlalu besar membuat beban pile tampak kotak dan momen puncaknya meleset; terlalu kecil hanya memperpanjang waktu hitung.

=== `mesh.size_local_pile` -- Ukuran lokal di pile

Ukuran elemen di daerah kepala tiang pada mode graded. Wajib diisi salah satu (pile atau pier), dan harus \<= ukuran global -- mengisinya lebih besar berarti memperkasar mesh justru di tempat yang paling butuh halus.

#tegas[Hanya berlaku bila mode ukuran mesh `graded`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

=== `mesh.size_local_pier` -- Ukuran lokal di pier

Ukuran elemen di daerah pier pada mode graded. Di sinilah momen desain dibaca, sehingga memperhalusnya langsung memperbaiki ketelitian angka yang Anda pakai.

#tegas[Hanya berlaku bila mode ukuran mesh `graded`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

=== `mesh.algorithm` -- Mesh.Algorithm

Algoritma pembentuk mesh di gmsh. 11 = Quasi-structured Quad, yang menghasilkan segi empat rapi dan menjadi bagian kontrak numerik tool ini. Ubah hanya bila mesh gagal terbentuk dan Anda paham konsekuensinya; nilai yang dipakai selalu tercatat di run\_manifest.json.

Nilai yang sah: `1`, `2`, `3`, `5`, `6`, `7`, `8`, `9`, `11`.

=== `mesh.recombination_algorithm` -- Mesh.RecombinationAlgorithm

Cara gmsh menggabungkan segitiga menjadi segi empat. 3 = Blossom full-quad, yang memaksa hasil 100% segi empat. Bersama Mesh.Algorithm di atas, inilah yang membuat syarat all-quad dapat dipenuhi.

Nilai yang sah: `0`, `1`, `2`, `3`.

=== `mesh.recombine` -- Recombine jadi quad

Menyalakan penggabungan segitiga menjadi segi empat. Harus tetap menyala: elemen shell yang dipakai tool ini (ShellMITC4) hanya menerima segi empat 4 titik.

=== `mesh.require_all_quad` -- Tolak bila ada elemen segitiga

Menghentikan run bila gmsh tetap menyisakan segitiga. Biarkan menyala. Mematikannya membuat run berlanjut dengan mesh yang tidak sepenuhnya dapat dianalisis -- kesalahan yang tidak terlihat di gambar mana pun.

=== `mesh.element_order` -- Orde elemen

Orde 1 = elemen bersimpul di keempat sudut saja (linier). Hanya orde 1 yang didukung, karena ShellMITC4 memang elemen 4 titik.

Nilai yang sah: `1`.

== Analisis <cfg-analisis>

Pilihan pemodelan numerik. Bawaannya sudah tepat untuk pilecap pada umumnya; ubah hanya bila Anda punya alasan spesifik. Apa pun pilihannya, setiap run menjalankan cek keseimbangan VC-0: jumlah beban yang terpasang dibandingkan dengan jumlah reaksi tumpuan, dan run digagalkan bila keduanya tidak cocok.

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`shell_element`], [satu pilihan], [ya], [`"ShellMITC4"`], [--],
  [`section`], [satu pilihan], [ya], [`"PlateFiber"`], [--],
  [`n_layers`], [bilangan bulat], [bersyarat], [`10`], [--],
  [`include_self_weight`], [ya atau tidak], [ya], [`false`], [--],
),
  caption: [Ringkasan field bagian Analisis.],
)

=== `analysis.shell_element` -- Elemen shell

Rumusan matematis tiap elemen pelat. `ShellMITC4` adalah elemen 4 titik berformulasi MITC yang memperhitungkan #tegas[deformasi geser melintang] (teori pelat tebal Mindlin-Reissner). Dipilih sebagai bawaan karena pilecap umumnya tebal terhadap bentangnya; teori pelat tipis (Kirchhoff) mengabaikan geser melintang dan akan #tegas[meremehkan] lendutan pada pelat setebal ini. `ShellDKGQ` adalah elemen pelat tipis tersebut, dan `ShellNLDKGQ` versinya dengan nonlinieritas geometri -- keduanya tidak diperlukan pada analisis elastis linier di sini.

Nilai yang sah: `ShellMITC4`, `ShellDKGQ`, `ShellNLDKGQ`.

=== `analysis.section` -- Section

Cara penampang setebal pelat diwakili. `PlateFiber` memakai satu material elastis yang terintegrasi pada tebal penuh -- itu yang sesuai untuk analisis elastis linier di sini. `LayeredShell` membagi tebal menjadi beberapa lapis dan baru bermanfaat bila tiap lapis diberi material berbeda; pada model elastis satu material, hasilnya sama tetapi lebih lambat.

Nilai yang sah: `PlateFiber`, `LayeredShell`.

=== `analysis.n_layers` -- Jumlah lapis

Banyaknya lapis penampang pada `LayeredShell`. Lebih banyak lapis berarti integrasi tegangan pada tebal lebih halus, dengan biaya waktu hitung. Minimal 2.

#tegas[Hanya berlaku bila penampang `LayeredShell`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

Nilainya tidak boleh kurang dari `2`.

=== `analysis.include_self_weight` -- Sertakan berat sendiri pilecap

Menambahkan berat pilecap sendiri (tebal x berat jenis) sebagai beban merata ke bawah. #tegas[Hati-hati] dengan hitungan ganda: pada banyak alur kerja, reaksi pile yang keluar dari analisis struktur atas #tegas[sudah] memuat berat pilecap. Centang hanya bila Anda yakin Pz pada CSV reaksi belum memuatnya, dan ingat bahwa mencentangnya membuat jumlah beban tidak lagi sama dengan jumlah Pz (PRD Bagian 17 item 6 masih terbuka).

== Desain - umum <cfg-desain-umum>

Dari momen dan geser hasil analisis, tool menghitung kebutuhan tulangan menurut SNI 2847:2019 lewat pustaka shell-kit. Bagian ini menetapkan mutu bahan dan faktor reduksi yang dipakai perhitungan tersebut.

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`code`], [teks], [ya], [`"SNI 2847:2019 (lewat shell-kit)"`], [--],
  [`cover`], [angka desimal], [ya], [`75.0`], [`mm`],
  [`fy`], [angka desimal], [ya], [`420.0`], [`MPa`],
  [`fy_source`], [teks], [ya], [`""`], [--],
  [`phi_flexure`], [angka desimal], [tidak], [`null`], [--],
  [`phi_shear`], [angka desimal], [tidak], [`null`], [--],
  [`as_min_surface_zone`], [angka desimal], [tidak], [`null`], [`mm`],
),
  caption: [Ringkasan field bagian Desain - umum.],
)

=== `design.code` -- Standar

Label standar yang dicetak di laporan. Ini #tegas[catatan], bukan sakelar: mengubah teksnya tidak mengubah rumus mana pun -- perhitungannya selalu mengikuti SNI 2847:2019 sebagaimana diterapkan shell-kit.

=== `design.cover` -- Selimut beton

Tebal beton dari permukaan sampai sisi luar tulangan. Menentukan tinggi efektif d, yang langsung menentukan kebutuhan tulangan: selimut yang lebih tebal berarti d lebih kecil dan tulangan lebih banyak. SNI menuntut 75 mm untuk beton yang dicor langsung di atas tanah -- kondisi lazim pilecap.

=== `design.fy` -- fy baja tulangan

Tegangan leleh baja tulangan. BjTS 420 (setara ulir mutu 420 MPa) adalah yang paling umum. Berbanding terbalik dengan luas tulangan yang dibutuhkan, jadi salah mengisinya langsung menggeser seluruh hasil.

=== `design.fy_source` -- Asal nilai fy

#tegas[Wajib diisi] -- run ditolak bila kosong. shell-kit menyediakan DEFAULT\_FY = 420 tetapi tool ini tidak memakainya diam-diam: mutu baja menentukan seluruh luas tulangan. Mis. "BjTS 420B, SNI 2052:2017" atau "sertifikat mill pabrik X".

=== `design.phi_flexure` -- phi lentur

Faktor reduksi kekuatan untuk lentur: kapasitas rencana = phi x kapasitas nominal, cara standar memberi margin keamanan. Kosongkan untuk memakai nilai SNI bawaan shell-kit (0,90 untuk penampang terkendali tarik); asalnya tetap dicetak di calc sheet. Isi hanya bila standar Anda menuntut angka lain.

Nilainya harus antara `0.0` dan `1.0`.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

=== `design.phi_shear` -- phi geser

Faktor reduksi kekuatan untuk geser. Kosongkan untuk memakai 0,75 dari shell-kit sesuai SNI. Lebih kecil daripada phi lentur karena keruntuhan geser bersifat getas dan lebih sulit diprediksi.

Nilainya harus antara `0.0` dan `1.0`.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

=== `design.as_min_surface_zone` -- Batas zona permukaan As\_min

Kosong = murni SNI 2847:2019. Diisi (mis. 300) = judgement mengikuti ACI 350-06 Ps. 7.12.2.1 untuk elemen tebal; nilainya dicatat di manifest sebagai keputusan Anda. Pada pilecap tebal ini mengubah hampir seluruh hasil lentur.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

== Desain - pemilihan tulangan <cfg-desain-pemilihan-tulangan>

Dari luas tulangan yang dibutuhkan (As), tool memilih batang yang benar-benar dapat dipasang. Anda menetapkan #tegas[satu] dari dua hal -- spasi atau batangnya -- dan tool menghitung sisanya. Hasilnya digambar sebagai peta diameter dan peta spasi per elemen, bukan hanya angka As.

#figure(
  image("_figur_pdf/mode-desain-tulangan.svg", width: 80%),
  caption: [Ilustrasi untuk bagian Desain - pemilihan tulangan.],
)

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`rebar_basis`], [satu pilihan], [ya], [`"element"`], [--],
  [`rebar_mode`], [satu pilihan], [ya], [`"spacing_fixed"`], [--],
  [`rebar_spacing`], [angka desimal], [bersyarat], [`150.0`], [`mm`],
  [`rebar_config`], [satu pilihan], [bersyarat], [`"2D25"`], [--],
  [`rebar_select_codes`], [beberapa pilihan], [tidak], [`null`], [--],
  [`strips_x`], [bilangan bulat], [bersyarat], [`5`], [--],
  [`strips_y`], [bilangan bulat], [bersyarat], [`5`], [--],
  [`moment_at`], [satu pilihan], [bersyarat], [`"pier_face"`], [--],
),
  caption: [Ringkasan field bagian Desain - pemilihan tulangan.],
)

=== `design.rebar_basis` -- Metode hitung angka desain

Dari mana angka desain #tegas[tulangan lentur] diambil -- sengkang tidak terpengaruh sama sekali (lihat calc sheet bagian 7b). Berlaku untuk #tegas[seluruh] kombinasi sekaligus, termasuk envelope. `element` (bawaan) memakai nilai tiap elemen apa adanya -- algoritma asli shell-kit. Kontur menjadi deliverable utamanya, dan Anda yang menentukan pembagian zona penulangan saat mendetail. Nilai puncaknya di tepi pier bersifat #tegas[singular]: membesar terus setiap mesh diperhalus (terukur \~16% saat mesh 300 -\> 150 mm), jadi hasilnya bergantung ukuran mesh yang Anda pilih. Arahnya konservatif -- tulangan bertambah, bukan berkurang. `strip` mengintegrasi momen sepanjang potongan di muka pier: konvergen dan dapat dicek tangan, tetapi hasilnya bergantung jumlah lajur yang Anda tetapkan. Terukur pada ex01: memakai 1 lajur alih-alih 5 mengencerkan puncak 556 -\> 283 kNm/m.

#figure(
  image("_figur_pdf/contoh-diameter-element-vs-strip.png", width: 100%),
  caption: [Kontur diameter tulangan dari run yang sama, hanya `design.rebar_basis` yang diubah: `element` (kiri) dan `strip` (kanan).],
)

Kedua peta itu #tegas[identik piksel demi piksel], dan itu memang seharusnya: kontur selalu digambar dari medan momen per elemen apa adanya, terlepas dari basis yang dipilih. Yang berbeda hanya keterangan di kepala gambar -- kiri menyatakan gambar inilah sumber angka desain, kanan menyatakan gambar ini sekadar peta orientasi sedangkan angka resminya ada di berkas lajur. #tegas[Bacalah basis yang tercetak di kepala gambar sebelum menafsirkan gambar mana pun dari alat ini]; gambarnya sendiri tidak cukup untuk membedakan.

Nilai yang sah: `element`, `strip`.

=== `design.rebar_mode` -- Mode

spacing\_fixed: Anda tetapkan spasi, tool memilih diameter. diameter\_fixed: Anda tetapkan batang, tool menghitung spasi. Sumbu yang #tegas[berbeda] dari metode hitung di atas: yang ini menentukan batang yang dipasang, bukan dari mana angka As berasal.

Nilai yang sah: `spacing_fixed`, `diameter_fixed`.

=== `design.rebar_spacing` -- Spasi tulangan

Jarak antar batang yang Anda tetapkan; tool memilih diameter terkecil dari daftar standar yang masih memenuhi As pada spasi ini. Spasi lebih rapat berarti diameter lebih kecil dan retak lebih terkendali, tetapi pemasangan lebih padat. 150-200 mm lazim untuk pilecap.

#tegas[Hanya berlaku bila mode tulangan `spacing_fixed`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

=== `design.rebar_config` -- Konfigurasi batang

Susunan batang yang Anda tetapkan; tool menghitung spasi yang dibutuhkan untuk memenuhi As. Kode dibaca sebagai \<jumlah\>D\<diameter\>: "2D25" berarti dua batang D25 per titik pemasangan (mis. dipasang berpasangan), "1D22" berarti satu batang D22. Daftarnya datang langsung dari shell-kit.

#tegas[Hanya berlaku bila mode tulangan `diameter_fixed`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

Nilai yang sah: `13`, `16`, `2D13`, `19`, `22`, `3D13`, `2D16`, `25`, `4D13`, `2D19`, `3D16`, `2D22`, `32`, `4D16`, `3D19`, `2D25`, `4D19`, `3D22`, `3D25`, `4D22`, `2D32`, `4D25`, `3D32`, `4D32`.

=== `design.rebar_select_codes` -- Batasi pilihan ke kode ini

Membatasi pilihan tool pada kode-kode tertentu saja, mis. bila di lapangan hanya tersedia D22 dan D25. Kosongkan untuk memakai seluruh diameter standar. Bila diisi, plot tulangan menjadi kategorikal berlabel kode -- setiap warna satu kode, bukan gradasi.

Nilai yang sah: `13`, `16`, `2D13`, `19`, `22`, `3D13`, `2D16`, `25`, `4D13`, `2D19`, `3D16`, `2D22`, `32`, `4D16`, `3D19`, `2D25`, `4D19`, `3D22`, `3D25`, `4D22`, `2D32`, `4D25`, `3D32`, `4D32`.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

=== `design.strips_x` -- Jumlah lajur arah X

Pilecap dibagi menjadi beberapa lajur (strip) sejajar sumbu X; di tiap lajur momen dirata-ratakan menjadi satu momen desain, sesuai cara penulangan pelat dikerjakan di lapangan. Lebih banyak lajur berarti penulangan lebih mengikuti sebaran momen tetapi gambar kerjanya lebih rumit. 5 lajur lazim.

#tegas[Hanya berlaku bila basis angka desain `strip`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

Nilainya tidak boleh kurang dari `1`.

=== `design.strips_y` -- Jumlah lajur arah Y

Banyaknya lajur sejajar sumbu Y, dengan cara kerja yang sama seperti lajur arah X. Tulangan kedua arah dihitung terpisah, jadi jumlah lajurnya boleh berbeda.

#tegas[Hanya berlaku bila basis angka desain `strip`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

Nilainya tidak boleh kurang dari `1`.

=== `design.moment_at` -- Lokasi momen desain

Di titik mana momen desain dibaca. `pier_face` = di muka pier, sesuai praktik SNI dan pilihan yang benar untuk desain. `peak` = nilai terbesar di mana pun, yang pada model pelat muncul tepat di tumpuan dan bersifat #tegas[Singular]: angkanya membesar terus setiap kali mesh diperhalus, sehingga bukan momen desain -- tool menandainya demikian di laporan. `both` mencetak keduanya untuk perbandingan.

#tegas[Hanya berlaku bila basis angka desain `strip`.] Pada cabang yang lain field ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca.

Nilai yang sah: `pier_face`, `peak`, `both`.

== Desain - sengkang <cfg-desain-sengkang>

Sengkang adalah tulangan #tegas[vertikal] yang menembus tebal pilecap untuk menahan geser, dipasang sebagai kisi dengan dua spasi: memanjang dan melintang. Tool menghitung kebutuhan Av/s dari geser hasil analisis, lalu menerjemahkannya menjadi diameter sengkang pada kisi yang Anda tetapkan. Kedua spasi bersama-sama menentukan luas yang harus dipikul satu kaki sengkang, sehingga keduanya wajib diisi. Pada banyak pilecap tebal, geser terpenuhi oleh beton saja dan tool akan melaporkan "tanpa sengkang" di sebagian besar luasan -- itu hasil yang sah.

#figure(
  table(
  columns: 5,
  align: (left, left, center, left, left),
  [Field], [Jenis], [Wajib], [Bawaan], [Satuan],
  [`stirrup_spacing_long`], [angka desimal], [ya], [`200.0`], [`mm`],
  [`stirrup_spacing_trans`], [angka desimal], [ya], [`200.0`], [`mm`],
  [`stirrup_select_diameters`], [beberapa pilihan], [tidak], [`null`], [--],
),
  caption: [Ringkasan field bagian Desain - sengkang.],
)

=== `design.stirrup_spacing_long` -- Spasi memanjang

Jarak antar sengkang searah sumbu X. Bersama spasi melintang menentukan luas tributari satu kaki sengkang; kisi lebih rapat berarti diameter sengkang lebih kecil untuk geser yang sama.

=== `design.stirrup_spacing_trans` -- Spasi melintang

Jarak antar sengkang searah sumbu Y. Luas tributari satu kaki sengkang adalah hasil kali kedua spasi, sehingga keduanya sama-sama menentukan diameter yang dibutuhkan.

=== `design.stirrup_select_diameters` -- Batasi diameter sengkang

Membatasi pilihan pada diameter tertentu saja, mis. bila di lapangan hanya tersedia D13 dan D16. Kosongkan untuk memakai daftar bawaan shell-kit (D10 sampai D25). Daerah yang butuh lebih besar daripada diameter terbesar yang diizinkan ditandai #tegas[tidak memadai] di plot, bukan dibulatkan diam-diam.

Nilai yang sah: `10.0`, `13.0`, `16.0`, `19.0`, `22.0`, `25.0`.

Boleh dikosongkan; tulis `null` untuk memakai bawaannya.

#pagebreak()

= Dasar teori <bab-teori>

== Lingkup dan idealisasi

Pilecap dimodelkan sebagai #tegas[pelat lentur] menggunakan elemen shell empat simpul. Tiga idealisasi berikut menentukan seluruh hasil yang disajikan dalam dokumen ini.

#enum(
  start: 1,
  [
Pile tidak dimodelkan sebagai tumpuan. Reaksi pile `Pz`, yang telah diperoleh dari analisis struktur atas, diterapkan sebagai beban terbagi rata berarah ke atas pada cakram kepala pile.
  ],
  [
Pier dimodelkan sebagai jepit sempurna pada enam derajat kebebasan. Idealisasi ini mengabaikan fleksibilitas pier dan menimbulkan konsentrasi tegangan pada tepi zona jepit.
  ],
  [
Material bersifat elastis linier isotropik, tanpa peninjauan retak maupun redistribusi momen akibat retak.
  ],
)

Idealisasi pertama membawa konsekuensi yang dimanfaatkan dalam pengendalian mutu analisis. Karena besar beban telah diketahui sejak awal, keseimbangan gaya dan momen dapat diperiksa secara eksak pada setiap eksekusi analisis. Pemeriksaan tersebut dilaporkan sebagai VC-0.

#figure(
  image("_figur_pdf/skema-tumpuan-beban.svg", width: 85%),
  caption: [Skema tumpuan dan pembebanan model: pile sebagai beban, pier sebagai tumpuan.],
)

== Sumbu dan konvensi tanda <teori-konvensi-tanda>

Sumbu global ditetapkan sebagai berikut: X arah memanjang, Y arah melintang, dan Z vertikal ke atas. Bidang model berimpit dengan bidang tengah pelat pada `z = 0`.

Besaran `m_xx` menyatakan momen per satuan lebar pada penampang yang tegak lurus sumbu X, dan ditahan oleh tulangan arah X. Momen bertanda positif menyatakan #tegas[serat bawah mengalami tarik], sehingga tulangan sisi bawah yang bekerja.

Faktor koreksi tanda momen dan gaya geser masing-masing bernilai #tegas[-1] dan #tegas[-1]. Kedua faktor tersebut ditetapkan pada satu lokasi dan diterapkan satu kali dalam rantai pengolahan hasil, serta dikalibrasi terhadap kasus statis tertentu pada VC-3.

#figure(
  image("_figur_pdf/sistem-koordinat.svg", width: 85%),
  caption: [Sistem koordinat bersama bagi definisi pilecap, pile, dan pier.],
)

== Elemen dan kekakuan pelat

Analisis menggunakan elemen #tegas[ShellMITC4] dengan formulasi Mindlin-Reissner dan penampang #tegas[PlateFiber]. Elemen ini dipilih karena pilecap pada umumnya tergolong pelat tebal, sehingga deformasi geser transversal tidak dapat diabaikan. Penggunaan teori pelat tipis (Kirchhoff) pada kasus tersebut menghasilkan lendutan yang lebih kecil daripada lendutan sebenarnya, sebagaimana diverifikasi melalui VC-5.

#figure(
  $ D = (E t^3) / (12 (1 - nu^2)) $,
  kind: "persamaan",
  supplement: [Persamaan],
  caption: [Kekakuan lentur pelat.],
)

Acuan: Timoshenko & Woinowsky-Krieger, Theory of Plates and Shells, ed. 2. Dievaluasi oleh fungsi `plate_flexural_rigidity`.

Nilai kekakuan lentur `D` dicantumkan agar pemeriksa dapat melakukan perhitungan ulang secara mandiri. Dalam analisis, kekakuan tersebut dibentuk sendiri oleh solver dari parameter `E`, `nu`, dan tebal pelat.

== Pengolahan hasil analisis

Resultan gaya dalam diperoleh dari keluaran solver melalui lima langkah pengolahan berikut.

#enum(
  start: 1,
  [
Pengambilan resultan pada setiap titik Gauss tanpa modifikasi.
  ],
  [
Perataan nilai antartitik Gauss dalam satu elemen.
  ],
  [
Koreksi tanda menuju konvensi yang ditetapkan pada subbab #link(<teori-konvensi-tanda>)[Sumbu dan konvensi tanda].
  ],
  [
Transformasi tensor dari sumbu lokal elemen ke sumbu global.
  ],
  [
Penyajian hasil sebagai `m_xx`, `m_yy`, `m_xy`, `q_x`, dan `q_y`.
  ],
)

#figure(
  $ m_(x x) = m_11 cos^2 theta + m_22 sin^2 theta - 2 m_12 sin theta cos theta $,
  kind: "persamaan",
  supplement: [Persamaan],
  caption: [Rotasi tensor momen dari sumbu lokal elemen ke sumbu global.],
)

Acuan: Rotasi tensor orde dua; tanda suku puntir diverifikasi melalui VC-2. Dievaluasi oleh fungsi `transform_moments`.

#figure(
  $ q_x = q_1 cos theta - q_2 sin theta $,
  kind: "persamaan",
  supplement: [Persamaan],
  caption: [Rotasi gaya geser transversal ke sumbu global.],
)

Acuan: Rotasi vektor; diverifikasi melalui VC-2. Dievaluasi oleh fungsi `transform_shear`.

Ketepatan transformasi tersebut, termasuk tanda suku puntir `2 m_12 sin theta cos theta` yang bergantung pada konvensi keluaran solver, diverifikasi melalui VC-2. Pada verifikasi tersebut, model dengan orientasi elemen yang berbeda harus menghasilkan resultan global yang sama.

== Momen desain per lajur

#figure(
  $ M = sum_(e) v_e w_e $,
  kind: "persamaan",
  supplement: [Persamaan],
  caption: [Integrasi momen sepanjang satu lajur potongan, dengan `e` menyatakan elemen yang memotong lajur tersebut.],
)

Acuan: Integrasi diskret; kesetaraan dengan statika eksak diverifikasi melalui VC-3. Dievaluasi oleh fungsi `integrate_strip`.

Elemen yang nilainya tidak terdefinisi tidak diikutsertakan dalam penjumlahan, sehingga satu elemen tidak menggugurkan hasil seluruh lajur. Lebar tributari `w_e` dihitung melalui proyeksi geometris eksak, dan potongan lajur diambil pada muka pier.

#kotak([PERINGATAN], rgb("#b45309"))[
Lokasi potongan yang ditetapkan adalah #tegas[muka pier secara geometris]. Kesesuaian lokasi tersebut terhadap definisi penampang kritis menurut standar belum dikonfirmasi. Seluruh tabel dalam dokumen ini karena itu menyebutnya sebagai muka pier, dan bukan sebagai penampang kritis menurut SNI 2847:2019.
]

#figure(
  image("_figur_pdf/lajur-momen.svg", width: 85%),
  caption: [Pembagian lajur dan lokasi potongan momen desain.],
)

== Geser

#figure(
  $ V_c = 0.17 lambda sqrt(f'_c) b_w d $,
  kind: "persamaan",
  supplement: [Persamaan],
  caption: [Kapasitas geser beton satu arah.],
)

Acuan: SNI 2847:2019 Ps. 22.5.5.1 (Vc = 0,17 lambda sqrt(f'c) bw d). Dievaluasi oleh fungsi `calc_Vc`.

#figure(
  $ A_v / s $,
  kind: "persamaan",
  supplement: [Persamaan],
  caption: [Luas sengkang per satuan jarak, dengan batas minimum kode.],
)

Acuan: SNI 2847:2019 Ps. 9.6.3.4 (tulangan geser minimum). Dievaluasi oleh fungsi `calc_shear_Av_per_s`.

Gaya geser satu arah ditinjau pada penampang berjarak `d` dari muka pier. Integrasi dilakukan melalui prosedur yang sama dengan integrasi momen lajur, sehingga definisi lebar tributari konsisten pada kedua peninjauan.

#kotak([PENTING], rgb("#b91c1c"))[
Gaya geser pons ditentukan dari #tegas[keseimbangan gaya], bukan dari resultan elemen shell. Elemen shell dua dimensi tidak memodelkan mekanisme keruntuhan pons yang bersifat tiga dimensi. Gaya geser pons terfaktor dihitung sebagai jumlah reaksi `Pz` pile yang berada di luar penampang kritis pada jarak `d/2` dari muka pier.

#tegas[Kapasitas geser pons tidak dihitung] dalam dokumen ini dan berstatus `NOT_EVALUATED`, karena pasal acuannya belum dikonfirmasi. Yang disajikan hanya gaya geser yang bekerja.
]

== Desain lentur menurut SNI 2847:2019

Seluruh perhitungan kapasitas penampang mengacu pada SNI 2847:2019 dan dievaluasi oleh pustaka `shell-kit`, yang versinya dicatat pada #link(<lampiran-provenance>)[Lampiran A]. Perhitungan dilakukan pada penampang selebar #tegas[1,000 mm].

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Besaran], [Pasal acuan],
  [`Av_min`], [SNI 2847:2019 Ps. 9.6.3.4 (tulangan geser minimum)],
  [`Es`], [SNI 2847:2019 Ps. 20.2.2.2 (modulus elastisitas baja 200.000 MPa)],
  [`Vc`], [SNI 2847:2019 Ps. 22.5.5.1 (Vc = 0,17 lambda sqrt(f'c) bw d)],
  [`beta1`], [SNI 2847:2019 Ps. 22.2.2.4.3 (faktor tinggi blok tegangan)],
  [`epsilon_cu`], [SNI 2847:2019 Ps. 22.2.2.1 (regangan tekan ultimit 0,003)],
  [`lambda`], [SNI 2847:2019 Ps. 19.2.4 (faktor beton berat normal)],
  [`spacing`], [SNI 2847:2019 Ps. 25.2.1 (spasi bersih minimum)],
),
  caption: [Pasal SNI 2847:2019 yang diterapkan dalam perhitungan kapasitas.],
)

#figure(
  image("_figur_pdf/mode-tulangan.svg", width: 85%),
  caption: [Dua mode pemilihan batang tulangan: spasi tetap dan diameter tetap.],
)

== Rasio bentang geser terhadap tinggi efektif

Rasio `a/d` dihitung dengan `a` sebagai jarak terdekat dari muka pier ke pusat pile. Rasio yang kecil menunjukkan kecenderungan perilaku _deep member_ dengan mekanisme strut-and-tie, yang tidak tercakup dalam model pelat lentur.

Nilai rasio disajikan tanpa disertai kesimpulan. Batas yang memisahkan perilaku _deep_ dari _non-deep_ beserta pasal acuannya belum dikonfirmasi, sehingga penilaian atas perilaku tersebut menjadi kewenangan engineer yang bertanggung jawab.

== Basis angka desain: per elemen atau per lajur

Parameter `design.rebar_basis` menentukan sumber angka desain tulangan dan berlaku seragam untuk seluruh kombinasi beban, termasuk envelope.

#list(
  [
Basis `element` menggunakan nilai momen tiap elemen tanpa perataan. Peta kontur menjadi keluaran utamanya. Nilai puncak pada tepi zona jepit pier bersifat #tegas[singular] dan tidak konvergen terhadap kehalusan mesh: pengukuran menunjukkan kenaikan sekitar 16% ketika ukuran elemen diperkecil dari 300 mm menjadi 150 mm. Arah penyimpangannya bersifat konservatif.
  ],
  [
Basis `strip` menggunakan integrasi momen sepanjang potongan pada muka pier. Hasilnya konvergen dan dapat diperiksa secara manual, tetapi bergantung pada jumlah lajur yang ditetapkan melalui `strips_x` dan `strips_y`, yang tidak diatur oleh pasal tertentu. Sebagai gambaran, penggunaan satu lajur menggantikan lima lajur menurunkan momen puncak dari 556,2 kN.m/m menjadi 283,4 kN.m/m.
  ],
)

#figure(
  image("_figur_pdf/mode-desain-tulangan.svg", width: 90%),
  caption: [Perbandingan dua basis penentuan angka desain tulangan.],
)

== Pile yang tumpang tindih dengan pier

Bagian cakram pile yang berada di dalam denah pier tidak menimbulkan lentur pada pelat. Karena pier dimodelkan sebagai jepit sempurna, tekanan pada daerah tersebut tersalur langsung menjadi reaksi tumpuan. Secara fisik hal ini merupakan aksi #tegas[strut], yaitu penyaluran gaya langsung dari kepala pile ke pier menembus tebal pilecap. #tegas[Kapasitas strut tersebut tidak diperiksa] dalam dokumen ini dan wajib ditinjau secara terpisah.

Besaran gaya yang tidak melenturkan pelat dilaporkan dalam dua komponen terpisah: komponen geometris, yang tidak bergantung pada ukuran elemen, dan komponen diskretisasi, yang besarnya sebanding dengan ukuran elemen. Uraian lengkap beserta tabel pengukurannya disajikan pada bab #link(<bab-keterbatasan>)[Asumsi dan keterbatasan] butir 10.

#figure(
  image("_figur_pdf/tumpang-tindih-pile-pier.svg", width: 85%),
  caption: [Komponen tumpang tindih antara cakram pile dan denah pier.],
)

== Verifikasi dan validasi

Keluaran perangkat lunak diverifikasi melalui tujuh kasus uji (_validation case_). Kasus uji yang acuannya belum dikonfirmasi tidak dijalankan, dan statusnya dinyatakan secara terbuka pada tabel berikut.

#figure(
  table(
  columns: 3,
  align: (left, left, left),
  [Kasus uji], [Aspek yang diverifikasi], [Status],
  [VC-0], [Keseimbangan statik Sigma R\_z = Sigma P\_z], [Terpenuhi, tiap analisis],
  [VC-1], [Pelat bujursangkar dengan tumpuan sederhana], [Belum dijalankan; sumber koefisien belum dikonfirmasi],
  [VC-2], [Invariansi hasil terhadap orientasi elemen], [Terpenuhi],
  [VC-3], [Pelat satu arah; kalibrasi tanda dan magnitudo], [Terpenuhi],
  [VC-4], [Konvergensi terhadap kehalusan mesh], [Terpenuhi],
  [VC-5], [Pengaruh tebal pelat; Mindlin terhadap Kirchhoff], [Terpenuhi],
  [VC-6], [Validasi silang terhadap Midas Civil], [Terpenuhi; syarat rilis],
  [VC-7], [Metode balok konvensional], [Belum dijalankan; referensi belum dikonfirmasi],
),
  caption: [Status verifikasi dan validasi pada versi perangkat lunak yang menghasilkan dokumen ini.],
)

#pagebreak()

= Apa yang dihasilkan <bab-keluaran>

Setiap kali dijalankan, perangkat lunak membuat #tegas[satu folder baru] di dalam `output`, bernama menurut tanggal dan jamnya. Hasil sebelumnya tidak pernah tertimpa, sehingga dua run dapat selalu dibandingkan.

== Berkas di tingkat run

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Berkas], [Isi],
  [`run_manifest.json`], [Provenance run: sidik sha256 setiap berkas masukan, versi perangkat lunak, versi setiap pustaka, dan resolusi geometri.],
  [`run.log`], [Catatan lengkap jalannya proses, termasuk seluruh peringatan.],
  [`SUMMARY.md`], [Ringkasan lintas kombinasi beban, nilai penentu, dan daftar keterbatasan.],
  [`laporan_pilecap.pdf`], [Laporan lengkap satu run dalam satu dokumen, bila diminta dengan `--pdf`.],
  [`laporan_pilecap.typ`], [Sumber laporan tersebut, ikut disimpan agar dapat diperiksa dan dibandingkan antar run.],
),
  caption: [Berkas di tingkat folder run.],
)

== Folder `00_Model` -- model dan mesh

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Berkas], [Isi],
  [`mesh_plan.png`], [Denah mesh beserta label tiang dan pier.],
  [`nodes.csv`, `elements.csv`], [Mesh yang benar-benar dipakai. Keduanya cukup untuk mereproduksi angka secara persis.],
  [`model.mct`], [Model siap diimpor ke Midas Civil, lengkap dengan pembebanannya.],
  [`model_opsvis.png`], [Gambar model beserta tumpuan dan bebannya.],
  [`geometry.json`], [Geometri hasil resolusi, setelah seluruh sumber data digabungkan.],
),
  caption: [Isi folder `00_Model`.],
)

== Folder per kombinasi beban

Satu folder untuk setiap kombinasi beban, berisi hasil analisis dan desain pada kombinasi tersebut.

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Berkas], [Isi],
  [`calc_sheet.md`], [Lembar perhitungan yang dapat diaudit, termasuk rantai penelusuran satu elemen dari titik Gauss sampai luas tulangan.],
  [`element_resultants.csv`], [Momen dan geser tiap elemen, dalam sumbu lokal maupun global.],
  [`rebar_design.csv`], [Luas tulangan perlu tiap elemen untuk keempat kombinasi arah dan muka.],
  [`shear_rebar.csv`], [Luas sengkang per satuan jarak beserta diameter sengkang terpilih.],
  [`shear_checks.csv`], [Kebutuhan geser satu arah dan geser pons.],
  [`reactions.csv`], [Reaksi tiap node jepit beserta barisan totalnya.],
  [`equilibrium_check.json`], [Pemeriksaan keseimbangan gaya beserta jejak beban tiap tiang.],
  [`traceability_sample.json`], [Nilai per titik Gauss yang menjadi dasar rantai penelusuran.],
  [`contour_*.png`], [Kontur momen, geser, lendutan, luas tulangan, diameter, dan sengkang.],
),
  caption: [Isi folder satu kombinasi beban.],
)

== Folder `Envelope` -- nilai penentu

Berisi nilai ekstrem di setiap elemen #tegas[lintas seluruh kombinasi], beserta kombinasi mana yang menentukannya. Inilah yang dipakai sebagai dasar penulangan, bukan hasil satu kombinasi saja.

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Berkas], [Isi],
  [`envelope_values.csv`], [Nilai ekstrem tiap besaran beserta kombinasi penentunya.],
  [`rebar_design_envelope.csv`], [Luas tulangan pakai per elemen beserta kombinasi penentunya.],
  [`strip_design_envelope.csv`], [Luas tulangan maksimum per lajur, hanya pada mode lajur.],
  [`envelope_*.png`], [Kontur seluruh besaran envelope.],
),
  caption: [Isi folder `Envelope`.],
)

== Laporan PDF satu run

Dengan pilihan `--pdf`, seluruh isi di atas dirangkum menjadi #tegas[satu dokumen] -- bukan satu dokumen per kombinasi -- lengkap dengan seluruh gambar sebagai gambar bernomor, dasar teori, provenance masukan, dan blok tanda tangan.

Kompilasinya berlangsung di dalam Python melalui pustaka yang sudah ikut terpasang. Tidak ada program tambahan yang perlu Anda pasang.

Perhatikan bahwa dokumen tersebut #tegas[berbeda] dari panduan yang sedang Anda baca: laporan menjelaskan satu run beserta angkanya, panduan ini menjelaskan perangkat lunaknya.

#pagebreak()

= Bukti dan validasi <bab-bukti>

== Perbandingan terhadap Midas Civil

Setiap contoh bawaan dimodelkan ulang di #tegas[Midas Civil], lalu hasilnya dibandingkan elemen demi elemen. Model pembandingnya #tegas[diimpor dari berkas yang ditulis perangkat lunak ini sendiri], sehingga penomoran node dan elemennya identik satu lawan satu -- perbandingannya bukan pencocokan perkiraan antara dua mesh yang berbeda.

Perbandingan ini berjalan sebagai #tegas[syarat rilis]: versi yang gagal memenuhinya tidak diterbitkan.

#figure(
  table(
  columns: 3,
  align: (left, right, right),
  [Besaran], [Selisih RMS terburuk], [Korelasi minimum],
  [Momen lentur dan puntir], [0,144%], [0,99991],
  [Geser], [0,265%], [0,99993],
  [Lendutan per node], [0,258%], [0,999971],
  [Reaksi tumpuan], [0,539%], [0,999596],
  [Momen puncak (penentu tulangan)], [0,515%], [--],
),
  caption: [Kesesuaian terukur terhadap Midas Civil pada seluruh contoh bawaan.],
)

== Selisihnya per elemen, bukan hanya angka ringkasnya

Satu angka RMS dapat menyembunyikan banyak hal, sehingga selisih tiap elemen disajikan apa adanya di bawah ini.

Panel kiri memperlihatkan selisih tiap elemen terhadap besar nilainya. Yang perlu dilihat bukan sempitnya sebaran, melainkan bahwa titik-titiknya #tegas[terpusat di garis nol tanpa kemiringan]: seandainya salah satu program keliru secara sistematis, titik-titik itu akan menyimpang ke satu sisi seiring membesarnya nilai. Panel kanan membaca sebaran yang sama secara kumulatif — #tegas[separuh elemen menyimpang kurang dari 0,03%], dan 99% di bawah 1%.

#figure(
  image("_figur_pdf/vc6-sebaran-m_xx-1_2D_1_6L.png", width: 100%),
  caption: [Selisih per elemen terhadap Midas Civil pada keempat contoh bawaan: struktur selisihnya (kiri) dan sebaran kumulatifnya (kanan).],
)

Angka ringkas belum menjawab pertanyaan yang paling menentukan: #tegas[di mana] selisih terbesar berada. Bila ia derau yang menyebar, sebarannya merata; bila ada kekeliruan sistematis, ia berkumpul di satu zona.

Peta berikut menjawabnya untuk kasus yang #tegas[paling buruk] — bukan yang paling rapi. Selisih terbesar berkumpul persis di #tegas[tepi cakram tiang dan sekitar pier], yaitu tempat beban dan tumpuan berhenti mendadak sehingga kedua formulasi elemen memang paling sah berbeda. Di seluruh bidang pelat lainnya, tempat angka desain sebenarnya diambil, selisihnya nyaris tidak terlihat.

#figure(
  image("_figur_pdf/vc6-peta-m_xx-1_2D_1_6L.png", width: 88%),
  caption: [Letak selisih pada contoh terburuk: simpangan terbesar terkonsentrasi di tepi cakram tiang, bukan menyebar di seluruh pelat.],
)

Kedua gambar di atas menyajikan momen `m_xx` pada kombinasi gravitasi saja. Gambar yang setara untuk #tegas[kelima gaya dalam pada kedua kombinasi beban] disajikan lengkap pada #link(<lampiran-perbandingan>)[Lampiran C], beserta tabel angkanya.

== Tiga hal yang perlu dibaca jujur

#enum(
  start: 1,
  [
#tegas[Konvensi tanda geser Midas berlawanan] dengan konvensi perangkat lunak ini. Perbedaan itu direkonsiliasi secara eksplisit, bukan disembunyikan, dan buktinya seragam pada seluruh elemen yang dibandingkan.
  ],
  [
#tegas[Jalur lendutan adalah yang paling lemah.] Ekspor Midas hanya menyimpan enam angka desimal dalam meter, dan pada pilecap yang kaku resolusi itu lebih besar daripada selisih yang diukur. Yang terbukti di jalur ini hanyalah "tidak berbeda sejauh yang dapat diukur". Yang benar-benar membuktikan ketelitian adalah jalur resultan elemen dan reaksi.
  ],
  [
#tegas[Kesesuaian pada kasus tiang yang menindih pier tidak membuktikan bahwa idealisasi jepit-sempurna itu benar.] Kedua program memakai idealisasi yang sama, sehingga perbandingannya tidak dapat menilai asumsi tersebut. Kapasitas strut tetap wajib diperiksa terpisah.
  ],
)

== Mesh tidak identik bit demi bit antar run

Dua run dengan masukan dan versi yang sama selalu menghasilkan #tegas[jumlah] node dan elemen yang identik, tetapi posisi node dapat sedikit berbeda. Penyebabnya ada pada algoritma pembuat mesh itu sendiri dan tidak dapat dimatikan.

Dampaknya terhadap angka desain #tegas[terukur kecil]: momen lajur dan luas tulangan bergeser paling banyak 0,02% antar run. Konsekuensi praktisnya:

#list(
  [
Luas tulangan, momen lajur, dan lendutan #tegas[dapat] dibandingkan antar run.
  ],
  [
Nilai #tegas[per elemen pada satu titik tidak dapat] dibandingkan begitu saja, karena elemen di lokasi tersebut memang bukan elemen yang sama.
  ],
  [
Untuk mereproduksi angka secara persis, simpan berkas `nodes.csv` dan `elements.csv`; keduanya memuat mesh yang benar-benar dipakai dan dapat dibaca kembali.
  ],
)

== Pustaka yang dipakai dan versinya

Seluruh versi berikut #tegas[dipatok persis], bukan sekadar versi minimum. Itu disengaja: pustaka numerik yang berubah versi dapat menggeser hasil, dan dokumen desain yang angkanya bergeser tanpa sebab yang tercatat tidak dapat dipertanggungjawabkan. Versi yang sama juga dicatat di setiap berkas provenance run.

#figure(
  table(
  columns: 3,
  align: (left, left, left),
  [Pustaka], [Versi], [Perannya],
  [`gmsh`], [`4.15.2`], [Pembuat mesh segiempat],
  [`matplotlib`], [`3.11.1`], [Penggambar kontur dan denah],
  [`numpy`], [`2.5.1`], [Aljabar dan operasi larik],
  [`openseespy`], [`3.8.0.0`], [Solver elemen hingga],
  [`opsvis`], [`1.3.7`], [Penggambar model dan deformasi],
  [`pandas`], [`2.3.3`], [Pembacaan dan penulisan tabel],
  [`pillow`], [`12.3.0`], [Penyiapan gambar untuk dokumen],
  [`shapely`], [`2.1.2`], [Operasi geometri bidang],
  [`shell-kit`], [`3.3.0`], [Kapasitas dan pemilihan tulangan menurut SNI 2847:2019],
  [`tqdm`], [`4.70.0`], [Penanda kemajuan proses],
  [`typst`], [`0.15.0`], [Kompilasi dokumen PDF],
  [`streamlit`], [`>=1.57`], [Formulir grafis (opsional) -- hanya bila fitur tambahan dipasang],
),
  caption: [Pustaka pihak ketiga beserta versi yang dipatok.],
)

#pagebreak()

= Asumsi dan keterbatasan <bab-keterbatasan>

Bagian ini dikutip tanpa perubahan dari dokumen acuan perangkat lunak dan berlaku bagi seluruh angka yang disajikan dalam dokumen ini.

#enum(
  start: 1,
  [
#tegas[Model pelat lentur, bukan strut-and-tie.] Pilecap dengan rasio bentang geser terhadap tinggi efektif yang kecil (_deep pile cap_) berperilaku sebagai _deep member_ dengan mekanisme strut-and-tie, bukan lentur pelat. Hasil tool ini #tegas[tidak sah sebagai satu-satunya dasar desain] untuk kasus tersebut.
  ],
  [
#tegas[Pier dimodelkan sebagai jepit sempurna.] Ini mengabaikan fleksibilitas pier dan menimbulkan singularitas tegangan di tepi zona jepit. Momen puncak di titik tersebut #tegas[bukan] momen desain. Tumpuan jepit juga cenderung #tegas[lebih kaku dari kondisi nyata], sehingga momen di daerah pier bisa #tegas[over-estimate] dan momen lapangan #tegas[under-estimate].
  ],
  [
#tegas[Reaksi pile adalah input, bukan hasil.] Tool tidak memverifikasi apakah distribusi reaksi pile yang diinput konsisten dengan kekakuan pilecap. Jika `Pz` berasal dari asumsi pilecap kaku sempurna, sedangkan model FEM ini pilecap lentur, terdapat inkonsistensi konseptual yang #tegas[tanggung jawab user] untuk menilai.
  ],
  [
#tegas[Pile hanya memberi gaya vertikal.] `Hx`, `Hy`, dan momen kepala pile diabaikan di v1.0.
  ],
  [
#tegas[Kekakuan pile diabaikan] - pile dimodelkan sebagai beban, bukan sebagai pegas/tumpuan elastis. Model alternatif (pile sebagai pegas, pier sebagai beban) memberi hasil berbeda dan #tegas[tidak] didukung di v1.0.
  ],
  [
#tegas[Material elastis linier isotropik.] Tidak ada retak, tidak ada redistribusi momen akibat retak. Momen elastis di daerah tumpuan cenderung lebih tinggi daripada momen setelah redistribusi.
  ],
  [
#tegas[Geser pons (punching) dari keseimbangan, bukan dari model shell.] Elemen shell 2D tidak memodelkan mekanisme keruntuhan pons tiga dimensi.
  ],
  [
#tegas[Berat sendiri opsional dan default OFF] - user harus sadar apakah `Pz` yang diinput sudah memperhitungkan berat pilecap atau belum. Tool tidak bisa mendeteksi ini.
  ],
  [
#tegas[Mesh gmsh tidak reproducible bit demi bit.] Terukur pada gmsh 4.15.2, dua run dengan input dan versi yang sama: jumlah node & elemen selalu identik, tetapi posisi node dapat berbeda hingga #tegas[33 mm] pada model 12 pile. Menyetel `General.NumThreads = 1` #tegas[tidak] menghilangkannya - penyebabnya ada di algoritma Quasi-structured Quad itu sendiri. Dampaknya pada angka desain terukur kecil: momen lajur dan `As` bergeser paling banyak #tegas[0,02%] antar run. Konsekuensi praktisnya: `As` dan momen lajur dapat dibandingkan antar run, tetapi #tegas[nilai per elemen di satu titik tidak] - dua run dapat memberi angka berbeda di lokasi yang sama karena elemennya memang bukan elemen yang sama. Untuk mereproduksi angka secara persis, simpan `00_Model/nodes.csv` dan `elements.csv`; keduanya memuat mesh yang benar-benar dipakai.
  ],
  [
#tegas[Pile yang tumpang tindih dengan pier: bagian di dalam footprint pier tidak melenturkan pelat.] Pier dimodelkan jepit sempurna (lihat \#2), sehingga tekanan yang bekerja di dalam footprint-nya langsung masuk ke reaksi. Secara fisik itu aksi #tegas[strut] -- gaya tersalur langsung dari kepala pile ke pier menembus tebal pilecap. Tool #tegas[tidak menghitung kapasitas strut itu]; bagian tersebut wajib dicek terpisah sebagai tumpu/strut, dan besarnya dilaporkan tersendiri di calc sheet.

#tegas[Angka desainnya bergantung pada ukuran elemen yang Anda pilih.] Selain komponen strut yang murni geometris, ada komponen diskretisasi: beban elemen di tepi footprint pier ikut mendarat pada node jepit. Besarnya sebanding `L·h/(2·A_pile)` (`L` = panjang potongan pile di muka pier, `h` = ukuran elemen), yaitu #tegas[orde `h`]. DIUKUR pada `a` = 300 mm, `r` = 400 mm:

#table(
  columns: 4,
  align: (left, right, right, right),
  [`D/h`], [strut (geometri)], [bocor mesh (diskretisasi)], [ke pelat],
  [6 (terkasar yang diizinkan)], [7,0768%], [4,8744%], [88,05%],
  [12], [7,1587%], [3,2175%], [89,62%],
  [24], [7,2021%], [1,3717%], [91,43%],
  [rumus analitis], [7,2147%], [0], [92,79%],
)

Artinya bagian `Pz` yang melenturkan pelat bergeser #tegas[\~3,4%] hanya karena mesh diperhalus 4x. Keduanya dilaporkan #tegas[terpisah] supaya terlihat mana yang geometri dan mana yang kehalusan mesh. Memperhalus mesh mengecilkan komponen diskretisasinya.

#tegas[Arah galatnya tidak aman.] Komponen diskretisasi membuat pelat menerima beban lebih #tegas[kecil] daripada seharusnya -- momen mengecil, sehingga tulangan yang dihitung lebih sedikit. Mesh yang lebih kasar menghasilkan desain yang lebih ringan, bukan lebih berat. Karena itu sejak v0.9.1 besarnya #tegas[dibatasi], bukan sekadar dilaporkan: di atas `OVERLAP_LEAK_WARN` muncul peringatan, di atas `OVERLAP_LEAK_ERROR` run ditolak. Batas itu diturunkan dari tabel pengukuran di dekat kedua konstanta tersebut.

Bocoran juga bergantung #tegas[bentuk] irisannya, bukan hanya luasnya: irisan yang terpotong dua sisi (pile menindih #tegas[sudut] pier) punya chord lebih panjang, sehingga bocor lebih besar daripada irisan satu muka pada kehalusan mesh yang sama -- terukur 2,3x pada D/h=24. Itulah sebabnya rasio `D/h` tidak dipakai sebagai penduga, dan yang diukur adalah bocoran yang sebenarnya.

Ini sensitivitas terhadap #tegas[ukuran elemen], bukan terhadap jitter mesh antar run. Batas 0,02% pada \#9 tetap berlaku: DIUKUR pada 8 run ex04 dengan ukuran elemen yang sama, sebaran besaran desainnya hanya #tegas[0,0001%] -- lebih kecil daripada contoh tanpa overlap. Kedua hal itu sering tertukar; yang perlu Anda putuskan adalah `mesh.size_*`, bukan berapa kali run diulang.
  ],
)

== Item yang belum dikonfirmasi

Item berikut BELUM dikonfirmasi, sehingga pengecekan terkait #tegas[tidak dilakukan] oleh tool ini:

#table(
  columns: 2,
  align: (left, left),
  [PRD Bagian 17], [Item],
  [\#3b], [Pasal kapasitas geser PONS: V\_c dua arah, definisi b\_o & d, phi],
  [\#5], [Kriteria batas deep pile cap + pasal],
  [\#6], [Apakah Pz input sudah termasuk berat sendiri pilecap],
  [\#7], [Sumber & angka koefisien VC-1 (Timoshenko, tabel mana)],
  [\#10], [Skala data realistis (jumlah elemen & kombinasi)],
  [\#18], [Redaksi disclaimer/pernyataan tanggung jawab],
)

#pagebreak()

= Tanggung jawab dan lisensi <bab-tanggung-jawab>

#kotak([HATI-HATI], rgb("#b91c1c"))[
#tegas[\[DRAFT - redaksi final belum ditetapkan, PRD Bagian 17 item 18\]] Hasil perhitungan ini dihasilkan secara otomatis oleh pilecap-fem v0.13.0 dan merupakan ALAT BANTU. Hasil wajib diperiksa dan disetujui oleh engineer yang bertanggung jawab. Pengecekan di luar ruang lingkup PRD Bagian 1.4 TIDAK dilakukan oleh tool ini.
]

Pernyataan di atas berlaku bagi setiap keluaran perangkat lunak ini, dan dicetak apa adanya pada setiap lembar perhitungan, setiap ringkasan, dan setiap laporan PDF yang dihasilkannya.

Dengan kata lain: perangkat lunak ini #tegas[tidak menggantikan engineer]. Ia mengerjakan bagian yang dapat diperiksa ulang -- pembuatan mesh, penyelesaian persamaan, penerapan pasal kode, penyusunan dokumen -- dan menyerahkan seluruh penilaian rekayasa kepada engineer yang bertanggung jawab. Setiap keluarannya dirancang agar dapat ditelusuri sampai ke berkas masukan dan pasal yang dipakai, justru supaya pemeriksaan itu mungkin dilakukan.

== Lisensi

Perangkat lunak ini diedarkan di bawah #tegas[Lisensi MIT]. Perusahaan boleh memakainya, menyalinnya, mengubahnya, dan memakainya untuk pekerjaan komersial tanpa biaya lisensi, dengan syarat pemberitahuan hak cipta dan teks lisensinya disertakan.

Sebagaimana lazimnya lisensi tersebut, perangkat lunak ini diberikan #tegas[tanpa jaminan dalam bentuk apa pun]. Hal itu tidak mengurangi maupun menambah kewajiban engineer yang bertanggung jawab untuk memeriksa dan menyetujui setiap hasil sebelum dipakai.

#pagebreak()

= Lampiran A -- provenance kapasitas <lampiran-provenance>

Perhitungan kapasitas penampang tidak dikerjakan sendiri oleh perangkat lunak ini, melainkan diserahkan kepada pustaka `shell-kit` yang mengimplementasikan SNI 2847:2019 beserta sitasi pasalnya. Pemisahan itu disengaja: bagian yang menerjemahkan pasal kode menjadi angka diuji dan diversikan tersendiri.

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Butir], [Nilai],
  [Standar acuan], [SNI 2847:2019],
  [Pustaka kapasitas], [`shell-kit` v3.3.0],
  [Perangkat lunak ini], [`pilecap-fem` v0.13.0],
),
  caption: [Sumber perhitungan kapasitas.],
)

== Pasal yang dipakai

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Besaran], [Pasal],
  [`beta1`], [SNI 2847:2019 Ps. 22.2.2.4.3 (faktor tinggi blok tegangan)],
  [`epsilon_cu`], [SNI 2847:2019 Ps. 22.2.2.1 (regangan tekan ultimit 0,003)],
  [`Es`], [SNI 2847:2019 Ps. 20.2.2.2 (modulus elastisitas baja 200.000 MPa)],
  [`lambda`], [SNI 2847:2019 Ps. 19.2.4 (faktor beton berat normal)],
  [`Vc`], [SNI 2847:2019 Ps. 22.5.5.1 (Vc = 0,17 lambda sqrt(f'c) bw d)],
  [`Av_min`], [SNI 2847:2019 Ps. 9.6.3.4 (tulangan geser minimum)],
  [`spacing`], [SNI 2847:2019 Ps. 25.2.1 (spasi bersih minimum)],
),
  caption: [Pasal SNI 2847:2019 yang dipakai beserta besaran yang ditentukannya.],
)

#kotak([CATATAN], rgb("#1d4ed8"))[
Faktor reduksi kekuatan, mutu beton, dan mutu baja #tegas[tidak dicantumkan di sini], karena nilainya Anda tetapkan sendiri pada setiap run. Nilai yang benar-benar dipakai beserta asalnya dicetak pada lampiran provenance di dalam laporan run masing-masing.
]

#pagebreak()

= Lampiran B -- daftar perintah <lampiran-perintah>

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Perintah], [Kegunaan],
  [`pilecap-mesh`], [Membuat mesh dan model dari berkas masukan, tanpa menjalankan analisis.],
  [`pilecap-analyze`], [Menjalankan analisis elemen hingga atas model yang sudah dibuat.],
  [`pilecap-report`], [Membuat kontur, envelope, lembar perhitungan, dan laporan dari hasil analisis.],
  [`pilecap-run`], [Menjalankan seluruh rantai di atas dalam satu perintah.],
  [`pilecap-ui`], [Membuka formulir grafis di peramban.],
  [`pilecap-manual`], [Menghasilkan panduan ini untuk versi yang sedang terpasang.],
),
  caption: [Perintah yang tersedia setelah pemasangan.],
)

Setiap perintah menerima `--help`, yang menampilkan seluruh pilihannya beserta nilai bawaannya pada versi yang terpasang. Itulah rujukan yang paling dapat dipercaya, karena datang langsung dari perangkat lunaknya.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "pilecap-run --help"),
)

== Pilihan yang paling sering dipakai

#figure(
  table(
  columns: 2,
  align: (left, left),
  [Pilihan], [Artinya],
  [`--input-dir`], [Folder berisi berkas masukan. Bawaannya folder tempat perintah dijalankan.],
  [`--output-dir`], [Folder induk tempat hasil ditulis. Bawaannya `output`.],
  [`--config`], [Menyebut berkas konfigurasi secara langsung, bila pola nama otomatis tidak dipakai.],
  [`--pdf`], [Membuat laporan PDF lengkap untuk run tersebut.],
  [`--init-example`], [Menyalin salah satu contoh bawaan ke folder saat ini.],
  [`--version`], [Menampilkan versi perangkat lunak yang terpasang.],
  [`--log-level`], [Mengatur seberapa rinci pesan yang dicetak selama proses berjalan.],
),
  caption: [Pilihan baris perintah yang paling sering dipakai.],
)

== Menghasilkan ulang panduan ini

Panduan ini dapat dibuat ulang kapan saja untuk versi yang sedang terpasang. Gunakan itu bila Anda memperbarui perangkat lunaknya: daftar field, keterbatasan, dan pasal dapat berbeda antarversi.

#block(
  width: 100%,
  fill: luma(245),
  inset: 8pt,
  radius: 2pt,
  breakable: true,
  raw(block: true, "pilecap-manual --out panduan"),
)

= Lampiran C -- perbandingan lengkap terhadap Midas Civil <lampiran-perbandingan>

Lampiran ini menyajikan perbandingan per elemen untuk #tegas[kelima gaya dalam] pada #tegas[kedua kombinasi beban], terhadap keempat contoh bawaan. Seluruhnya berasal dari perhitungan yang sama dengan yang dipakai syarat rilis, sehingga angka di sini identik dengan yang diperiksa saat versi ini diterbitkan.

== Cara membaca gambar di lampiran ini

Setiap gaya disajikan dengan dua gambar.

#enum(
  start: 1,
  [
#tegas[Struktur dan sebaran selisih.] Panel kiri memplot selisih tiap elemen terhadap besar nilainya; yang dibaca bukan sempitnya sebaran, melainkan bahwa titiknya terpusat di garis nol #tegas[tanpa kemiringan] -- kekeliruan sistematis akan menarik titik ke satu sisi seiring membesarnya nilai. Panel kanan menjawab "berapa persen elemen yang selisihnya di bawah sekian": pilih satu tinggi, geser ke kanan sampai menyentuh kurva, lalu baca angkanya di sumbu bawah. #tegas[Kurva yang lebih ke kiri berarti lebih rapat kesesuaiannya.]
  ],
  [
#tegas[Letak selisih pada denah.] Satu panel per contoh. Gambar ini membedakan "cocok" dari "kebetulan cocok rata-rata": selisih yang berupa derau tersebar merata, sedangkan kekeliruan sistematis berkumpul di satu zona. Skala warnanya #tegas[ditetapkan per panel], karena puncak antarcontoh berbeda sampai sepuluh kali lipat.
  ],
)

#kotak([CATATAN], rgb("#1d4ed8"))[
Selisih selalu dinyatakan terhadap #tegas[nilai puncak], bukan terhadap nilai di titik itu sendiri. Di dekat garis nol momen kedua program sama-sama benar, tetapi rasio per titiknya tak terhingga sehingga tidak bermakna.
]

== Kombinasi 1.2D+1.6L

=== Momen lentur arah X (`m_xx`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,132%], [0,024%], [0,581%], [1,593%],
  [`ex02`], [6.844], [0,024%], [0,004%], [0,090%], [0,428%],
  [`ex03`], [4.808], [0,055%], [0,009%], [0,191%], [1,437%],
  [`ex04`], [3.162], [0,063%], [0,013%], [0,254%], [0,801%],
),
  caption: [Selisih `m_xx` terhadap Midas Civil, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-m_xx-1_2D_1_6L.png", width: 100%),
  caption: [Struktur dan sebaran selisih `m_xx`, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-peta-m_xx-1_2D_1_6L.png", width: 92%),
  caption: [Letak selisih `m_xx` pada denah keempat contoh, kombinasi 1.2D+1.6L.],
)

=== Momen lentur arah Y (`m_yy`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,114%], [0,022%], [0,480%], [1,500%],
  [`ex02`], [6.844], [0,043%], [0,007%], [0,197%], [0,613%],
  [`ex03`], [4.808], [0,048%], [0,008%], [0,174%], [1,368%],
  [`ex04`], [3.162], [0,134%], [0,023%], [0,598%], [2,323%],
),
  caption: [Selisih `m_yy` terhadap Midas Civil, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-m_yy-1_2D_1_6L.png", width: 100%),
  caption: [Struktur dan sebaran selisih `m_yy`, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-peta-m_yy-1_2D_1_6L.png", width: 92%),
  caption: [Letak selisih `m_yy` pada denah keempat contoh, kombinasi 1.2D+1.6L.],
)

=== Momen puntir (`m_xy`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,144%], [0,019%], [0,561%], [1,971%],
  [`ex02`], [6.844], [0,057%], [0,010%], [0,228%], [0,958%],
  [`ex03`], [4.808], [0,080%], [0,013%], [0,307%], [2,007%],
  [`ex04`], [3.162], [0,102%], [0,016%], [0,382%], [2,067%],
),
  caption: [Selisih `m_xy` terhadap Midas Civil, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-m_xy-1_2D_1_6L.png", width: 100%),
  caption: [Struktur dan sebaran selisih `m_xy`, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-peta-m_xy-1_2D_1_6L.png", width: 92%),
  caption: [Letak selisih `m_xy` pada denah keempat contoh, kombinasi 1.2D+1.6L.],
)

=== Geser melintang arah X (`q_x`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,164%], [0,024%], [0,604%], [2,386%],
  [`ex02`], [6.844], [0,120%], [0,010%], [0,479%], [2,338%],
  [`ex03`], [4.808], [0,109%], [0,019%], [0,461%], [1,511%],
  [`ex04`], [3.162], [0,091%], [0,016%], [0,395%], [1,040%],
),
  caption: [Selisih `q_x` terhadap Midas Civil, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-q_x-1_2D_1_6L.png", width: 100%),
  caption: [Struktur dan sebaran selisih `q_x`, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-peta-q_x-1_2D_1_6L.png", width: 92%),
  caption: [Letak selisih `q_x` pada denah keempat contoh, kombinasi 1.2D+1.6L.],
)

=== Geser melintang arah Y (`q_y`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,162%], [0,022%], [0,650%], [2,093%],
  [`ex02`], [6.844], [0,265%], [0,019%], [1,046%], [7,747%],
  [`ex03`], [4.808], [0,094%], [0,016%], [0,408%], [1,657%],
  [`ex04`], [3.162], [0,114%], [0,017%], [0,521%], [1,377%],
),
  caption: [Selisih `q_y` terhadap Midas Civil, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-q_y-1_2D_1_6L.png", width: 100%),
  caption: [Struktur dan sebaran selisih `q_y`, kombinasi 1.2D+1.6L.],
)

#figure(
  image("_figur_pdf/vc6-peta-q_y-1_2D_1_6L.png", width: 92%),
  caption: [Letak selisih `q_y` pada denah keempat contoh, kombinasi 1.2D+1.6L.],
)

== Kombinasi 1.2D+1.0W

=== Momen lentur arah X (`m_xx`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,104%], [0,020%], [0,471%], [1,229%],
  [`ex02`], [6.844], [0,019%], [0,003%], [0,073%], [0,372%],
  [`ex03`], [4.808], [0,053%], [0,009%], [0,180%], [1,484%],
  [`ex04`], [3.162], [0,050%], [0,009%], [0,181%], [0,700%],
),
  caption: [Selisih `m_xx` terhadap Midas Civil, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-m_xx-1_2D_1_0W.png", width: 100%),
  caption: [Struktur dan sebaran selisih `m_xx`, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-peta-m_xx-1_2D_1_0W.png", width: 92%),
  caption: [Letak selisih `m_xx` pada denah keempat contoh, kombinasi 1.2D+1.0W.],
)

=== Momen lentur arah Y (`m_yy`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,083%], [0,017%], [0,371%], [0,994%],
  [`ex02`], [6.844], [0,045%], [0,007%], [0,212%], [0,780%],
  [`ex03`], [4.808], [0,048%], [0,007%], [0,176%], [1,427%],
  [`ex04`], [3.162], [0,108%], [0,017%], [0,415%], [1,936%],
),
  caption: [Selisih `m_yy` terhadap Midas Civil, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-m_yy-1_2D_1_0W.png", width: 100%),
  caption: [Struktur dan sebaran selisih `m_yy`, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-peta-m_yy-1_2D_1_0W.png", width: 92%),
  caption: [Letak selisih `m_yy` pada denah keempat contoh, kombinasi 1.2D+1.0W.],
)

=== Momen puntir (`m_xy`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,110%], [0,015%], [0,418%], [1,596%],
  [`ex02`], [6.844], [0,045%], [0,009%], [0,179%], [0,917%],
  [`ex03`], [4.808], [0,078%], [0,013%], [0,294%], [2,002%],
  [`ex04`], [3.162], [0,086%], [0,012%], [0,326%], [1,858%],
),
  caption: [Selisih `m_xy` terhadap Midas Civil, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-m_xy-1_2D_1_0W.png", width: 100%),
  caption: [Struktur dan sebaran selisih `m_xy`, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-peta-m_xy-1_2D_1_0W.png", width: 92%),
  caption: [Letak selisih `m_xy` pada denah keempat contoh, kombinasi 1.2D+1.0W.],
)

=== Geser melintang arah X (`q_x`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,141%], [0,019%], [0,548%], [2,380%],
  [`ex02`], [6.844], [0,104%], [0,008%], [0,397%], [2,385%],
  [`ex03`], [4.808], [0,102%], [0,017%], [0,428%], [1,516%],
  [`ex04`], [3.162], [0,072%], [0,013%], [0,303%], [0,766%],
),
  caption: [Selisih `q_x` terhadap Midas Civil, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-q_x-1_2D_1_0W.png", width: 100%),
  caption: [Struktur dan sebaran selisih `q_x`, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-peta-q_x-1_2D_1_0W.png", width: 92%),
  caption: [Letak selisih `q_x` pada denah keempat contoh, kombinasi 1.2D+1.0W.],
)

=== Geser melintang arah Y (`q_y`)

#figure(
  table(
  columns: 6,
  align: (left, right, right, right, right, right),
  [Contoh], [Elemen], [RMS], [Separuh di bawah], [99% di bawah], [Maksimum],
  [`ex01`], [1.835], [0,149%], [0,017%], [0,628%], [2,197%],
  [`ex02`], [6.844], [0,225%], [0,014%], [0,801%], [7,552%],
  [`ex03`], [4.808], [0,099%], [0,016%], [0,404%], [1,833%],
  [`ex04`], [3.162], [0,093%], [0,014%], [0,406%], [1,048%],
),
  caption: [Selisih `q_y` terhadap Midas Civil, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-sebaran-q_y-1_2D_1_0W.png", width: 100%),
  caption: [Struktur dan sebaran selisih `q_y`, kombinasi 1.2D+1.0W.],
)

#figure(
  image("_figur_pdf/vc6-peta-q_y-1_2D_1_0W.png", width: 92%),
  caption: [Letak selisih `q_y` pada denah keempat contoh, kombinasi 1.2D+1.0W.],
)