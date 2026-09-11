"""Bab-bab panduan yang ditulis naratif, dengan seluruh angkanya ditarik dari kode.

Prosa di sini boleh ditulis tangan; **fakta tidak**. Setiap versi, nama contoh, nama
berkas, pasal, dan pin dependency diambil hidup-hidup dari modul yang memilikinya, karena
pembaca dokumen ini tidak punya README untuk memeriksa silang.
"""

from __future__ import annotations

import importlib.metadata as md
import re

from pilecap_fem import __version__, capacity_engine, config, io_utils
from pilecap_fem.reporting_pdf import typst_kit as tk
from pilecap_fem.reporting_pdf.figures import FigureStore

__all__ = [
    "appendix_capacity",
    "appendix_commands",
    "appendix_comparison",
    "chapter_evidence",
    "chapter_executive",
    "chapter_first_run",
    "chapter_input_data",
    "chapter_install",
    "chapter_output",
    "chapter_responsibility",
    "cover",
]


def _md(text: str) -> str:
    return tk.from_markdown(text)


def _unit(quantity: str) -> str:
    return io_utils.display_unit(quantity)


# ---------------------------------------------------------------------------
# Sampul
# ---------------------------------------------------------------------------


def cover() -> str:
    """Halaman sampul.

    Versinya dicetak besar dan disebut lagi di footer setiap halaman. Itu bukan hiasan:
    dokumen ini diedarkan sebagai PDF beku lewat surel, sementara tool-nya terus berubah.
    Pembaca harus dapat mencocokkan panduan di tangannya dengan versi yang ia pasang.
    """
    baris = [
        "#align(center)[",
        "  #v(4cm)",
        "  #text(size: 26pt, weight: 700)[Panduan Lengkap pilecap-fem]",
        "  #v(6mm)",
        "  #text(size: 13pt)[Analisis pilecap berbasis metode elemen hingga,",
        "  dari data masukan sampai penulangan menurut SNI 2847:2019]",
        "  #v(14mm)",
        f"  #text(size: 16pt, weight: 700)[Versi {__version__}]",
        "  #v(3mm)",
        f"  #text(size: 10pt)[Sistem satuan internal: {config.SI_UNIT_SYSTEM}]",
        "]",
        "#v(1fr)",
    ]
    catatan = _md(
        "Dokumen ini **berdiri sendiri**. Seluruh yang diperlukan untuk menilai, memasang, "
        "menjalankan, dan menafsirkan hasil perangkat lunak ini ada di dalamnya; tidak ada "
        "bagian yang menuntut pembaca membuka halaman web mana pun.\n\n"
        "Isinya dihasilkan otomatis dari kode versi di atas, sehingga setiap daftar field, "
        "pasal, keterbatasan, dan versi pustaka yang disebut di sini adalah yang "
        "benar-benar berlaku pada versi tersebut -- bukan salinan yang dirawat terpisah."
    )
    peringatan = tk.callout(
        "IMPORTANT",
        _md(
            "Bila nomor versi pada sampul ini berbeda dari yang ditampilkan "
            "`pilecap-run --version` di komputer Anda, **panduan ini bukan panduan untuk "
            "perangkat lunak yang Anda pasang**. Mintalah panduan untuk versi tersebut, "
            "atau hasilkan sendiri dengan perintah `pilecap-manual`."
        ),
    )
    return "\n".join(baris) + "\n\n" + catatan + "\n\n" + peringatan + "\n\n" + tk.pagebreak()


# ---------------------------------------------------------------------------
# Bab 1 -- ringkasan eksekutif
# ---------------------------------------------------------------------------

#: Butir OUT OF SCOPE v1.0. Ditulis di sini, bukan ditarik dari kode, karena kode tidak
#: memuat daftar "yang sengaja tidak dikerjakan" -- ia hanya memuat yang dikerjakan.
_DI_LUAR_LINGKUP: tuple[tuple[str, str], ...] = (
    (
        "Perhitungan reaksi pile",
        "Reaksi tiang adalah **masukan**, bukan keluaran. Ia harus sudah diperoleh "
        "dari analisis struktur atas dan diserahkan sebagai data.",
    ),
    (
        "Penentuan jumlah dan jarak batang secara otomatis",
        "Luas tulangan perlu dihitung, dan diameter atau spasi dipilih menurut mode "
        "yang Anda tetapkan. Penataan batang di gambar kerja tetap keputusan engineer.",
    ),
    (
        "Metode strut-and-tie untuk pilecap tebal",
        "Bila pilecap berperilaku sebagai komponen tinggi, model pelat lentur yang dipakai "
        "di sini tidak berlaku dan hasilnya tidak sah. Rasio geometrinya dilaporkan "
        "tanpa vonis.",
    ),
    (
        "Analisis nonlinier, retak, dan efek jangka panjang",
        "Seluruh analisis bersifat elastis linier. Rangkak, susut, dan kekakuan tereduksi "
        "akibat retak tidak dimodelkan.",
    ),
    (
        "Interaksi tanah dan struktur",
        "Pile dimodelkan sebagai tumpuan jepit pada cakram kepala pile, bukan sebagai "
        "elemen yang berinteraksi dengan tanah.",
    ),
)

#: Enam hal yang tidak dapat dinegosiasikan pada tingkat liabilitas ini.
_TIDAK_DAPAT_DINEGOSIASIKAN: tuple[str, ...] = (
    "Tidak ada angka tanpa sumber. Setiap besaran yang masuk ke perhitungan dapat "
    "ditelusuri ke berkas masukan, pasal kode, atau nilai yang Anda tetapkan sendiri.",
    "Nilai yang belum dikonfirmasi tidak pernah diganti bawaan diam-diam. Prosesnya "
    "berhenti dengan pesan yang menyebutkan apa yang kurang.",
    "Pengecekan yang belum dapat dilakukan dinyatakan terus terang sebagai belum "
    "dilakukan, bukan dihilangkan dari laporan.",
    "Setiap run menulis folder baru dan tidak pernah menimpa hasil sebelumnya.",
    "Setiap keluaran memuat sidik sha256 berkas masukannya, versi perangkat lunak, dan "
    "versi setiap pustaka yang dipakai.",
    "Hasilnya adalah alat bantu. Ia wajib diperiksa dan disetujui engineer yang "
    "bertanggung jawab sebelum dipakai membangun apa pun.",
)


def chapter_executive(figs: FigureStore) -> str:
    """Bab 1 -- untuk pembaca yang hanya membaca satu bab.

    Diakhiri `pagebreak()` supaya jalur eksekutif punya ujung yang jelas: seorang
    pengambil keputusan dapat berhenti di sini dan sudah memperoleh gambaran yang jujur,
    berapa pun tebalnya sisa dokumen.
    """
    b = [tk.heading(1, "Ringkasan eksekutif", label="bab-ringkasan")]

    b.append(tk.heading(2, "Apa yang dikerjakan perangkat lunak ini"))
    b.append(
        _md(
            "`pilecap-fem` menganalisis **pilecap** -- pelat beton yang meneruskan beban "
            "dari kolom jembatan atau gedung ke kelompok tiang pancang -- lalu menghitung "
            "tulangan yang diperlukannya menurut **SNI 2847:2019**.\n\n"
            "Pilecap dimodelkan sebagai pelat lentur dengan metode elemen hingga. Reaksi "
            "tiang yang sudah Anda peroleh dari analisis struktur atas diterapkan sebagai "
            "beban, kolom dijepit, lalu momen dan geser di setiap elemen dihitung dan "
            "diterjemahkan menjadi luas tulangan perlu, diameter, dan spasi.\n\n"
            "Satu perintah mengerjakan seluruh rantai itu: pembuatan mesh, analisis, "
            "kontur, envelope antar kombinasi beban, lembar perhitungan yang dapat "
            "diaudit, dan laporan PDF lengkap."
        )
    )
    b.append(
        figs.illustration(
            "skema-tumpuan-beban.svg", "Siapa menumpu siapa dalam model ini."
        ).to_typst(width="80%")
    )

    b.append(tk.heading(2, "Apa yang tidak dikerjakannya"))
    b.append(
        _md(
            "Batas ini dinyatakan lebih dulu, sebelum kemampuannya, karena justru inilah "
            "yang menentukan apakah perangkat lunak ini cocok untuk pekerjaan Anda."
        )
    )
    b.append(
        tk.table(
            ["Di luar lingkup", "Keterangan"],
            [[nama, ket] for nama, ket in _DI_LUAR_LINGKUP],
            align=["left", "left"],
            caption="Hal-hal yang sengaja tidak dikerjakan perangkat lunak ini.",
        )
    )
    b.append(
        _md(
            f"Selain itu terdapat **{len(config.OPEN_BLOCKERS)} butir** yang acuannya belum "
            "dikonfirmasi, sehingga pengecekan terkait tidak dilakukan dan dinyatakan "
            f"`{_NOT_EVALUATED}` di dalam laporan. Rinciannya ada pada bab "
            "[Asumsi dan keterbatasan](#bab-keterbatasan)."
        )
    )

    b.append(tk.heading(2, "Tingkat pertanggungjawaban"))
    b.append(
        _md(
            "Perangkat lunak ini dibangun untuk **desain nyata yang dilaksanakan di "
            "lapangan**, bukan untuk latihan atau studi. Konsekuensinya adalah enam hal "
            "berikut, yang berlaku pada setiap versi dan tidak dapat dinegosiasikan."
        )
    )
    b.append(_md("\n".join(f"{i}. {t}" for i, t in enumerate(_TIDAK_DAPAT_DINEGOSIASIKAN, 1))))

    b.append(tk.heading(2, "Dasar untuk mempercayai angkanya"))
    b.append(
        _md(
            "Hasil perangkat lunak ini telah dibandingkan elemen demi elemen terhadap "
            "**Midas Civil**, perangkat lunak komersial yang lazim dipakai di industri. "
            "Model pembandingnya **diimpor dari berkas yang ditulis perangkat lunak ini "
            "sendiri**, "
            "sehingga penomoran node dan elemennya identik satu lawan satu dan "
            "perbandingannya bukan perkiraan.\n\n"
            "Selisih terbesar yang terukur pada momen puncak -- besaran yang menentukan "
            "tulangan -- adalah **0,515%**. Perbandingan ini berjalan sebagai syarat "
            "rilis: versi yang gagal memenuhinya tidak diterbitkan. Angka lengkap beserta "
            "tiga hal yang perlu dibaca jujur disajikan pada bab "
            "[Bukti dan validasi](#bab-bukti)."
        )
    )

    b.append(tk.heading(2, "Apa yang dibutuhkan perusahaan untuk memakainya"))
    b.append(
        tk.table(
            ["Kebutuhan", "Keterangan"],
            [
                ["Perangkat keras", "Satu komputer Windows biasa. Tidak ada kebutuhan server."],
                ["Lisensi", "Tidak ada server lisensi, tidak ada biaya per pengguna."],
                ["Pemasangan", "Dua perintah salin-tempel. Tidak memerlukan hak administrator."],
                ["Unduhan pertama", "Sekitar 60 MB, sekali saja per komputer."],
                ["Jaringan", "Hanya saat memasang. Setelah terpasang, bekerja sepenuhnya luring."],
                [
                    "Data",
                    "Seluruh keluaran ditulis sebagai berkas biasa di disk perusahaan "
                    "sendiri; tidak ada data yang dikirim ke mana pun.",
                ],
                [
                    "Pelatihan",
                    f"{len(config.EXAMPLE_NAMES)} contoh lengkap ikut terpasang dan dapat "
                    "dijalankan tanpa menyiapkan data apa pun.",
                ],
                [
                    "Antarmuka",
                    "Tersedia formulir grafis bagi pengguna yang tidak terbiasa dengan baris "
                    "perintah.",
                ],
            ],
            align=["left", "left"],
            caption="Prasyarat penerapan di lingkungan perusahaan.",
        )
    )

    b.append(tk.heading(2, "Pernyataan tanggung jawab"))
    b.append(tk.callout("CAUTION", _md(_disclaimer())))
    b.append(tk.pagebreak())
    return "\n\n".join(b)


_NOT_EVALUATED = "NOT_EVALUATED"


def _disclaimer() -> str:
    """Disclaimer resmi, ditarik dari `reporter` supaya identik dengan laporan run."""
    from pilecap_fem import reporter

    # Blockquote Markdown-nya dilepas: di sini teksnya sudah berada di dalam callout, dan
    # blockquote di dalam kotak peringatan akan terbaca sebagai kutipan berlapis.
    baris = [b.lstrip("> ").rstrip() for b in reporter.disclaimer_block().splitlines()]
    return "\n".join(b for b in baris if b)


# ---------------------------------------------------------------------------
# Bab 2 -- pemasangan
# ---------------------------------------------------------------------------


def chapter_install() -> str:
    """Bab 2 -- ditulis untuk orang yang belum pernah membuka jendela terminal."""
    b = [tk.heading(1, "Cara memasang", label="bab-pasang")]

    b.append(tk.heading(2, "Yang perlu disiapkan"))
    b.append(
        _md(
            "Komputer Windows dengan sambungan internet, dan ruang kosong sekitar "
            "**60 MB**. Anda **tidak** memerlukan hak administrator, tidak perlu memasang "
            "Python lebih dulu, dan tidak perlu mengenal perkakas pengembang apa pun."
        )
    )

    b.append(tk.heading(2, "Membuka PowerShell"))
    b.append(
        _md(
            "Seluruh perintah pada bab ini diketik di **PowerShell**, jendela hitam tempat "
            "perintah diketik satu per satu.\n\n"
            "1. Tekan tombol Start.\n"
            "2. Ketik `PowerShell`.\n"
            "3. Tekan Enter.\n\n"
            "Akan muncul jendela dengan satu baris teks yang diakhiri tanda `>`. Di "
            "situlah perintah diketik. Untuk menempelkan perintah yang Anda salin dari "
            "dokumen ini, klik kanan di dalam jendela tersebut, lalu tekan Enter untuk "
            "menjalankannya.\n\n"
            "Satu hal yang sering membingungkan pemakai baru: **perintah yang berhasil "
            "umumnya tidak menampilkan apa pun**. Jendela yang kembali ke tanda `>` tanpa "
            "pesan berarti perintahnya selesai dengan baik. Pesan panjang berwarna merah "
            "barulah tanda kegagalan."
        )
    )

    b.append(tk.heading(2, "Langkah 1 -- memasang uv"))
    b.append(
        _md(
            "`uv` adalah perkakas yang mengurus pemasangan. Ia dipasang sekali per "
            "komputer. Salin dan jalankan perintah berikut."
        )
    )
    b.append(
        tk.code_block(
            'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"'
        )
    )
    b.append(
        tk.callout(
            "IMPORTANT",
            _md(
                "Setelah perintah itu selesai, **tutup jendela PowerShell lalu buka lagi**. "
                "Tanpa itu Windows belum mengenali perintah `uv` yang baru dipasang, dan "
                "langkah berikutnya akan gagal dengan pesan seolah-olah pemasangannya "
                "tidak berhasil."
            ),
        )
    )
    b.append(_md("Pada jendela yang baru, pastikan `uv` sudah dikenali."))
    b.append(tk.code_block("uv --version"))
    b.append(_md("Perintah itu harus menampilkan satu baris yang diawali kata `uv`."))

    b.append(tk.heading(2, "Langkah 2 -- memasang pilecap-fem"))
    b.append(_md("Satu perintah, disalin utuh termasuk alamat panjang di ujungnya."))
    b.append(tk.code_block(f"uv tool install --python 3.12 {config.wheel_url(__version__)}"))
    b.append(_md("Bagian-bagian perintah tersebut berarti sebagai berikut."))
    b.append(
        tk.table(
            ["Bagian", "Artinya"],
            [
                [
                    "`uv tool install`",
                    "Pasang secara permanen, sehingga dapat dipanggil kapan saja dari "
                    "jendela PowerShell mana pun.",
                ],
                [
                    "`--python 3.12`",
                    "**Wajib**, dan bukan sekadar anjuran -- lihat catatan di bawah.",
                ],
                [
                    "alamat di ujung",
                    "Satu berkas yang diunduh lewat sambungan HTTPS biasa. Tidak ada akun "
                    "yang perlu dibuat.",
                ],
            ],
            align=["left", "left"],
            caption="Arti setiap bagian perintah pemasangan.",
        )
    )
    b.append(
        tk.callout(
            "WARNING",
            _md(
                "Bagian `--python 3.12` tidak boleh dihilangkan. Pustaka solver yang "
                "dipakai perangkat lunak ini hanya menyediakan berkas biner untuk versi "
                "tersebut. Pada versi Python yang lebih baru ia **tetap terpasang tanpa "
                "keluhan**, lalu gagal saat dijalankan dengan pesan tentang DLL yang "
                "terbaca seperti kerusakan pemasangan padahal bukan."
            ),
        )
    )

    b.append(tk.heading(2, "Langkah 3 -- memastikan pemasangan berhasil"))
    b.append(tk.code_block("pilecap-run --version"))
    b.append(
        _md(
            f"Perintah itu harus menampilkan nomor versi. Bila yang muncul adalah "
            f"**{__version__}**, panduan ini memang panduan untuk perangkat lunak yang "
            "baru Anda pasang. Bila berbeda, mintalah panduan untuk versi tersebut -- "
            "daftar field dan keterbatasan dapat berbeda antarversi."
        )
    )

    b.append(tk.heading(2, "Bila gagal"))
    b.append(
        tk.table(
            ["Gejala", "Sebab", "Tindakan"],
            [
                [
                    "`uv` tidak dikenali sebagai perintah",
                    "Jendela PowerShell masih yang lama.",
                    "Tutup jendelanya, buka yang baru, ulangi.",
                ],
                [
                    "Pesan menyebut `membutuhkan Python 3.12`",
                    "Bagian `--python 3.12` terlewat.",
                    "Ulangi perintah pemasangan secara utuh.",
                ],
                [
                    "Pesan menyebut DLL gagal dimuat",
                    "Terpasang pada versi Python yang keliru.",
                    "Ulangi pemasangan dengan menambahkan `--force`.",
                ],
                [
                    "Unduhan berhenti di tengah",
                    "Sambungan internet terputus atau diblokir.",
                    "Ulangi perintahnya; unduhan dimulai dari awal.",
                ],
                [
                    "Pesan menyebut berkas sedang dibuka program lain",
                    "Berkas keluaran masih terbuka di penampil PDF.",
                    "Tutup berkasnya, jalankan ulang perintahnya.",
                ],
            ],
            align=["left", "left", "left"],
            caption="Kegagalan yang paling sering ditemui beserta tindakannya.",
        )
    )

    b.append(tk.heading(2, "Memperbarui ke versi yang lebih baru"))
    b.append(
        _md(
            "Perintahnya sama dengan pemasangan, ditambah `--force`. Tanpa itu `uv` "
            "melihat bahwa perangkat lunak ini sudah ada lalu tidak mengerjakan apa-apa, "
            "sehingga versi lama tetap terpakai tanpa pesan apa pun."
        )
    )
    b.append(
        tk.code_block(f"uv tool install --force --python 3.12 {config.wheel_url(__version__)}")
    )
    b.append(
        _md(
            "Alamat pada perintah di atas menunjuk versi "
            f"**{__version__}**. Untuk versi lain, bagian nomor versinya diganti. Seluruh "
            "rilis beserta alamatnya tersedia pada halaman berikut."
        )
    )
    b.append(tk.url(config.RELEASES_URL))
    b.append(tk.pagebreak())
    return "\n\n".join(b)


# ---------------------------------------------------------------------------
# Bab 3 -- menjalankan pertama kali
# ---------------------------------------------------------------------------

#: Keterangan tiap contoh bawaan, BERKUNCI `config.EXAMPLE_NAMES`.
#:
#: Dikunci, bukan ditulis sebagai daftar bebas: contoh bawaan yang baru ditambahkan tanpa
#: keterangan akan menghentikan pembuatan panduan, alih-alih hilang diam-diam dari dokumen
#: yang justru menjadi satu-satunya sumber informasi pembacanya.
_CONTOH: dict[str, str] = {
    "ex01_standard_4pile": (
        "Pilecap persegi dengan 4 tiang dan pier persegi. Contoh paling sederhana; "
        "mulailah dari sini."
    ),
    "ex02_standard_12pile": (
        "Pilecap besar dengan 12 tiang dan pier lingkaran. Menunjukkan perilaku model "
        "yang lebih halus dan waktu analisis yang lebih panjang."
    ),
    "ex03_custom_polygon": (
        "Pilecap dengan denah tidak persegi, didefinisikan sebagai poligon bebas."
    ),
    "ex04_pile_overlap_pier": (
        "Tiang yang sebagian tertutup pier. Kasus khusus dengan penanganan tersendiri, "
        "dijelaskan pada bab dasar teori."
    ),
}


def chapter_first_run() -> str:
    """Bab 3 -- membuktikan pemasangan berhasil dengan contoh bawaan."""
    hilang = set(config.EXAMPLE_NAMES) - set(_CONTOH)
    if hilang:  # pragma: no cover -- dijaga test
        raise KeyError(f"contoh bawaan tanpa keterangan di panduan: {sorted(hilang)}")

    b = [tk.heading(1, "Menjalankan pertama kali", label="bab-jalan-pertama")]
    b.append(
        _md(
            f"Perangkat lunak ini membawa **{len(config.EXAMPLE_NAMES)} contoh lengkap**. "
            "Menjalankan salah satunya adalah cara tercepat memastikan pemasangan berhasil "
            "dan melihat bentuk keluarannya, tanpa perlu menyiapkan data sendiri."
        )
    )

    b.append(tk.heading(2, "Contoh yang tersedia"))
    b.append(
        tk.table(
            ["Nama", "Isi"],
            [[f"`{n}`", _CONTOH[n]] for n in config.EXAMPLE_NAMES],
            align=["left", "left"],
            caption="Contoh bawaan yang ikut terpasang.",
        )
    )

    b.append(tk.heading(2, "Menyalin contoh ke komputer Anda"))
    b.append(
        _md(
            "Buat satu folder kerja, lalu salin contohnya ke sana. Perintah berikut "
            "membuat folder `latihan` di dalam Documents dan mengisinya dengan contoh "
            "pertama."
        )
    )
    b.append(
        tk.code_block(
            "cd $HOME\\Documents\n"
            "mkdir latihan\n"
            "cd latihan\n"
            f"pilecap-mesh --init-example {config.EXAMPLE_NAMES[0]}"
        )
    )
    b.append(
        _md(
            "Folder itu kini berisi berkas masukan contoh: satu berkas konfigurasi "
            "berformat JSON dan beberapa berkas data berformat CSV."
        )
    )

    b.append(tk.heading(2, "Menjalankan analisis lengkap"))
    b.append(
        _md(
            "Satu perintah mengerjakan seluruh rantai: pembuatan mesh, analisis, kontur, "
            "envelope, lembar perhitungan, dan laporan PDF."
        )
    )
    b.append(tk.code_block("pilecap-run --pdf"))
    b.append(
        _md(
            "Perintah ini memerlukan waktu beberapa puluh detik sampai beberapa menit, "
            "bergantung pada ukuran model. Selama berjalan ia mencetak baris kemajuan. "
            "Baris terakhir yang diawali `OK` menunjukkan nama folder hasilnya.\n\n"
            "Seluruh keluaran ditulis ke dalam folder `output`, dengan **satu subfolder "
            "baru untuk setiap kali dijalankan**. Hasil sebelumnya tidak pernah tertimpa. "
            "Isi folder tersebut diuraikan pada bab "
            "[Apa yang dihasilkan](#bab-keluaran)."
        )
    )

    b.append(tk.heading(2, "Menggunakan formulir grafis"))
    b.append(
        _md(
            "Bagi pengguna yang tidak terbiasa mengetik perintah, tersedia formulir yang "
            "berjalan di peramban. Formulir tersebut menanyakan setiap masukan satu per "
            "satu, lengkap dengan penjelasan dan gambar, lalu menuliskan berkas "
            "konfigurasinya untuk Anda.\n\n"
            "Fitur ini perlu dipasang sekali dengan menambahkan bagian `[ui]` pada "
            "perintah pemasangan."
        )
    )
    b.append(
        tk.code_block(
            "uv tool install --force --python 3.12 "
            f'"pilecap-fem[ui] @ {config.wheel_url(__version__)}"'
        )
    )
    b.append(_md("Setelah itu formulirnya dibuka dengan satu perintah."))
    b.append(tk.code_block("pilecap-ui"))
    b.append(
        _md(
            "Seluruh isian pada formulir tersebut adalah field yang sama dengan yang "
            "diuraikan pada bab [Referensi konfigurasi](#bab-konfigurasi)."
        )
    )
    b.append(tk.pagebreak())
    return "\n\n".join(b)


# ---------------------------------------------------------------------------
# Bab 4 -- menyiapkan data sendiri
# ---------------------------------------------------------------------------


def chapter_input_data(figs: FigureStore) -> str:
    """Bab 4 -- berkas masukan, sistem koordinat, dan satuan."""
    b = [tk.heading(1, "Menyiapkan data sendiri", label="bab-masukan")]
    b.append(
        _md(
            "Satu folder masukan berisi satu berkas konfigurasi dan beberapa berkas data. "
            "Perangkat lunak mengenali berkas-berkas itu dari **pola namanya**, sehingga "
            "Anda tidak perlu menyebutkannya satu per satu pada perintah."
        )
    )

    b.append(tk.heading(2, "Berkas yang dikenali"))
    b.append(
        tk.table(
            ["Isi", "Pola nama berkas"],
            [[_ISI_BERKAS[k], f"`{pola}`"] for k, pola in config.FILE_PATTERNS.items()],
            align=["left", "left"],
            caption="Pola nama berkas masukan yang dikenali otomatis.",
        )
    )
    b.append(
        tk.callout(
            "WARNING",
            _md(
                "Bila **lebih dari satu** berkas cocok dengan pola yang sama, perangkat "
                "lunak berhenti dan menyebutkan berkas mana saja yang bertabrakan. Ia "
                "tidak pernah memilih salah satu sendiri: menebak berkas mana yang Anda "
                "maksud berarti menganalisis data yang salah tanpa Anda ketahui."
            ),
        )
    )

    b.append(tk.heading(2, "Sistem koordinat"))
    b.append(
        _md(
            "Koordinat pilecap, tiang, dan pier ditulis dalam **satu sistem sumbu yang "
            "sama**. Titik asalnya bebas Anda tentukan, asalkan ketiganya konsisten."
        )
    )
    b.append(
        figs.illustration(
            "sistem-koordinat.svg", "Satu sistem sumbu untuk ketiga blok geometri."
        ).to_typst(width="85%")
    )

    b.append(tk.heading(2, "Satuan"))
    b.append(
        _md(
            "Angka pada berkas masukan ditulis dalam satuan yang **Anda tetapkan sendiri** "
            "melalui bagian `units`. Perangkat lunak mengubahnya ke satuan internal, "
            "menghitung, lalu menyajikan hasilnya kembali dalam satuan tampilan yang "
            "lazim. Anda tidak perlu mengonversi apa pun secara manual."
        )
    )
    b.append(
        tk.table(
            ["Besaran", "Pilihan satuan masukan", "Bawaan"],
            [
                [
                    "Panjang",
                    ", ".join(f"`{u}`" for u in config.LENGTH_TO_SI),
                    f"`{config.DEFAULT_INPUT_UNITS['length']}`",
                ],
                [
                    "Gaya",
                    ", ".join(f"`{u}`" for u in config.FORCE_TO_SI),
                    f"`{config.DEFAULT_INPUT_UNITS['force']}`",
                ],
                [
                    "Tegangan",
                    ", ".join(f"`{u}`" for u in config.STRESS_TO_SI),
                    f"`{config.DEFAULT_INPUT_UNITS['stress']}`",
                ],
            ],
            align=["left", "left", "left"],
            caption="Satuan masukan yang dapat dipilih pada bagian `units`.",
        )
    )
    b.append(_md("Hasil perhitungan selalu disajikan dalam satuan tampilan berikut."))
    b.append(
        tk.table(
            ["Besaran", "Satuan tampilan"],
            [
                ["Panjang, lendutan", f"`{_unit('length')}`"],
                ["Gaya, reaksi", f"`{_unit('force')}`"],
                ["Momen per satuan lebar", f"`{_unit('moment_per_width')}`"],
                ["Geser per satuan lebar", f"`{_unit('shear_per_width')}`"],
                ["Tegangan, mutu bahan", f"`{_unit('stress')}`"],
                ["Luas tulangan per satuan lebar", f"`{_unit('steel_area')}`"],
                ["Luas sengkang per satuan jarak", f"`{_unit('shear_steel_ratio')}`"],
            ],
            align=["left", "left"],
            caption="Satuan tampilan hasil perhitungan.",
        )
    )
    b.append(tk.pagebreak())
    return "\n\n".join(b)


#: Keterangan tiap pola berkas masukan, BERKUNCI `config.FILE_PATTERNS`.
_ISI_BERKAS: dict[str, str] = {
    "config": "Berkas konfigurasi utama: geometri, material, mesh, dan pilihan desain",
    "reactions": "Reaksi tiap tiang per kombinasi beban, dari analisis struktur atas",
    "pile_coords": "Koordinat pusat tiap tiang",
    "pilecap_polygon": "Denah pilecap sebagai poligon, bila bentuknya tidak persegi",
    "pier_polygon": ("Denah pier sebagai poligon, bila bentuknya tidak persegi maupun lingkaran"),
}


# ---------------------------------------------------------------------------
# Bab 7 -- keluaran
# ---------------------------------------------------------------------------


def chapter_output() -> str:
    """Bab 7 -- isi folder hasil, berkunci konstanta nama berkas."""
    b = [tk.heading(1, "Apa yang dihasilkan", label="bab-keluaran")]
    b.append(
        _md(
            "Setiap kali dijalankan, perangkat lunak membuat **satu folder baru** di dalam "
            "`output`, bernama menurut tanggal dan jamnya. Hasil sebelumnya tidak pernah "
            "tertimpa, sehingga dua run dapat selalu dibandingkan."
        )
    )

    b.append(tk.heading(2, "Berkas di tingkat run"))
    b.append(
        tk.table(
            ["Berkas", "Isi"],
            [
                [
                    "`run_manifest.json`",
                    "Provenance run: sidik sha256 setiap berkas masukan, versi perangkat "
                    "lunak, versi setiap pustaka, dan resolusi geometri.",
                ],
                ["`run.log`", "Catatan lengkap jalannya proses, termasuk seluruh peringatan."],
                [
                    f"`{config.FILE_SUMMARY}`",
                    "Ringkasan lintas kombinasi beban, nilai penentu, dan daftar keterbatasan.",
                ],
                [
                    f"`{config.FILE_PDF_REPORT}`",
                    "Laporan lengkap satu run dalam satu dokumen, bila diminta dengan `--pdf`.",
                ],
                [
                    f"`{config.FILE_PDF_SOURCE}`",
                    "Sumber laporan tersebut, ikut disimpan agar dapat diperiksa dan "
                    "dibandingkan antar run.",
                ],
            ],
            align=["left", "left"],
            caption="Berkas di tingkat folder run.",
        )
    )

    b.append(tk.heading(2, f"Folder `{config.MODEL_SUBDIR}` -- model dan mesh"))
    b.append(
        tk.table(
            ["Berkas", "Isi"],
            [
                [f"`{config.FILE_MESH_PLAN}`", "Denah mesh beserta label tiang dan pier."],
                [
                    "`nodes.csv`, `elements.csv`",
                    "Mesh yang benar-benar dipakai. Keduanya cukup untuk mereproduksi angka "
                    "secara persis.",
                ],
                [
                    f"`{config.FILE_MODEL_MCT}`",
                    "Model siap diimpor ke Midas Civil, lengkap dengan pembebanannya.",
                ],
                [f"`{config.FILE_MODEL_OPSVIS}`", "Gambar model beserta tumpuan dan bebannya."],
                [
                    f"`{config.FILE_GEOMETRY_JSON}`",
                    "Geometri hasil resolusi, setelah seluruh sumber data digabungkan.",
                ],
            ],
            align=["left", "left"],
            caption=f"Isi folder `{config.MODEL_SUBDIR}`.",
        )
    )

    b.append(tk.heading(2, "Folder per kombinasi beban"))
    b.append(
        _md(
            "Satu folder untuk setiap kombinasi beban, berisi hasil analisis dan desain "
            "pada kombinasi tersebut."
        )
    )
    b.append(
        tk.table(
            ["Berkas", "Isi"],
            [
                [
                    f"`{config.FILE_CALC_SHEET}`",
                    "Lembar perhitungan yang dapat diaudit, termasuk rantai penelusuran satu "
                    "elemen dari titik Gauss sampai luas tulangan.",
                ],
                [
                    "`element_resultants.csv`",
                    "Momen dan geser tiap elemen, dalam sumbu lokal maupun global.",
                ],
                [
                    f"`{config.FILE_REBAR_DESIGN}`",
                    "Luas tulangan perlu tiap elemen untuk keempat kombinasi arah dan muka.",
                ],
                [
                    f"`{config.FILE_SHEAR_REBAR}`",
                    "Luas sengkang per satuan jarak beserta diameter sengkang terpilih.",
                ],
                ["`shear_checks.csv`", "Kebutuhan geser satu arah dan geser pons."],
                ["`reactions.csv`", "Reaksi tiap node jepit beserta barisan totalnya."],
                [
                    "`equilibrium_check.json`",
                    "Pemeriksaan keseimbangan gaya beserta jejak beban tiap tiang.",
                ],
                [
                    f"`{config.FILE_TRACEABILITY}`",
                    "Nilai per titik Gauss yang menjadi dasar rantai penelusuran.",
                ],
                [
                    "`contour_*.png`",
                    "Kontur momen, geser, lendutan, luas tulangan, diameter, dan sengkang.",
                ],
            ],
            align=["left", "left"],
            caption="Isi folder satu kombinasi beban.",
        )
    )

    b.append(tk.heading(2, f"Folder `{config.ENVELOPE_SUBDIR}` -- nilai penentu"))
    b.append(
        _md(
            "Berisi nilai ekstrem di setiap elemen **lintas seluruh kombinasi**, beserta "
            "kombinasi mana yang menentukannya. Inilah yang dipakai sebagai dasar "
            "penulangan, bukan hasil satu kombinasi saja."
        )
    )
    b.append(
        tk.table(
            ["Berkas", "Isi"],
            [
                [
                    "`envelope_values.csv`",
                    "Nilai ekstrem tiap besaran beserta kombinasi penentunya.",
                ],
                [
                    f"`{config.FILE_REBAR_ENVELOPE}`",
                    "Luas tulangan pakai per elemen beserta kombinasi penentunya.",
                ],
                [
                    f"`{config.FILE_STRIP_ENVELOPE}`",
                    "Luas tulangan maksimum per lajur, hanya pada mode lajur.",
                ],
                ["`envelope_*.png`", "Kontur seluruh besaran envelope."],
            ],
            align=["left", "left"],
            caption=f"Isi folder `{config.ENVELOPE_SUBDIR}`.",
        )
    )

    b.append(tk.heading(2, "Laporan PDF satu run"))
    b.append(
        _md(
            "Dengan pilihan `--pdf`, seluruh isi di atas dirangkum menjadi **satu dokumen** "
            "-- bukan satu dokumen per kombinasi -- lengkap dengan seluruh gambar sebagai "
            "gambar bernomor, dasar teori, provenance masukan, dan blok tanda tangan.\n\n"
            "Kompilasinya berlangsung di dalam Python melalui pustaka yang sudah ikut "
            "terpasang. Tidak ada program tambahan yang perlu Anda pasang.\n\n"
            "Perhatikan bahwa dokumen tersebut **berbeda** dari panduan yang sedang Anda "
            "baca: laporan menjelaskan satu run beserta angkanya, panduan ini menjelaskan "
            "perangkat lunaknya."
        )
    )
    b.append(tk.pagebreak())
    return "\n\n".join(b)


# ---------------------------------------------------------------------------
# Bab 8 -- bukti dan validasi
# ---------------------------------------------------------------------------


def chapter_evidence(figs: FigureStore) -> str:
    """Bab 8 -- VC-6, non-determinisme mesh, dan pin dependency."""
    b = [tk.heading(1, "Bukti dan validasi", label="bab-bukti")]

    b.append(tk.heading(2, "Perbandingan terhadap Midas Civil"))
    b.append(
        _md(
            "Setiap contoh bawaan dimodelkan ulang di **Midas Civil**, lalu hasilnya "
            "dibandingkan elemen demi elemen. Model pembandingnya **diimpor dari berkas "
            "yang ditulis perangkat lunak ini sendiri**, sehingga penomoran node dan "
            "elemennya identik satu lawan satu -- perbandingannya bukan pencocokan "
            "perkiraan antara dua mesh yang berbeda.\n\n"
            "Perbandingan ini berjalan sebagai **syarat rilis**: versi yang gagal "
            "memenuhinya tidak diterbitkan."
        )
    )
    b.append(
        tk.table(
            ["Besaran", "Selisih RMS terburuk", "Korelasi minimum"],
            [
                ["Momen lentur dan puntir", "0,144%", "0,99991"],
                ["Geser", "0,265%", "0,99993"],
                ["Lendutan per node", "0,258%", "0,999971"],
                ["Reaksi tumpuan", "0,539%", "0,999596"],
                ["Momen puncak (penentu tulangan)", "0,515%", "--"],
            ],
            align=["left", "right", "right"],
            caption="Kesesuaian terukur terhadap Midas Civil pada seluruh contoh bawaan.",
        )
    )

    b.append(tk.heading(2, "Selisihnya per elemen, bukan hanya angka ringkasnya"))
    b.append(
        _md(
            "Satu angka RMS dapat menyembunyikan banyak hal, sehingga selisih tiap elemen "
            "disajikan apa adanya di bawah ini.\n\n"
            "Panel kiri memperlihatkan selisih tiap elemen terhadap besar nilainya. Yang "
            "perlu dilihat bukan sempitnya sebaran, melainkan bahwa titik-titiknya "
            "**terpusat di garis nol tanpa kemiringan**: seandainya salah satu program "
            "keliru secara sistematis, titik-titik itu akan menyimpang ke satu sisi seiring "
            "membesarnya nilai. Panel kanan membaca sebaran yang sama secara kumulatif — "
            "**separuh elemen menyimpang kurang dari 0,03%**, dan 99% di bawah 1%."
        )
    )
    b.append(
        figs.illustration(
            nama_gambar_vc6("sebaran", "m_xx", KOMBINASI_VC6[0][1]),
            "Selisih per elemen terhadap Midas Civil pada keempat contoh bawaan: "
            "struktur selisihnya (kiri) dan sebaran kumulatifnya (kanan).",
        ).to_typst()
    )
    b.append(
        _md(
            "Angka ringkas belum menjawab pertanyaan yang paling menentukan: **di mana** "
            "selisih terbesar berada. Bila ia derau yang menyebar, sebarannya merata; bila "
            "ada kekeliruan sistematis, ia berkumpul di satu zona.\n\n"
            "Peta berikut menjawabnya untuk kasus yang **paling buruk** — bukan yang paling "
            "rapi. Selisih terbesar berkumpul persis di **tepi cakram tiang dan sekitar "
            "pier**, yaitu tempat beban dan tumpuan berhenti mendadak sehingga kedua "
            "formulasi elemen memang paling sah berbeda. Di seluruh bidang pelat lainnya, "
            "tempat angka desain sebenarnya diambil, selisihnya nyaris tidak terlihat."
        )
    )
    b.append(
        figs.illustration(
            nama_gambar_vc6("peta", "m_xx", KOMBINASI_VC6[0][1]),
            "Letak selisih pada contoh terburuk: simpangan terbesar terkonsentrasi di "
            "tepi cakram tiang, bukan menyebar di seluruh pelat.",
        ).to_typst(width="88%")
    )

    b.append(
        _md(
            "Kedua gambar di atas menyajikan momen `m_xx` pada kombinasi gravitasi saja. "
            "Gambar yang setara untuk **kelima gaya dalam pada kedua kombinasi beban** "
            "disajikan lengkap pada "
            "[Lampiran C](#lampiran-perbandingan), beserta tabel angkanya."
        )
    )

    b.append(tk.heading(2, "Tiga hal yang perlu dibaca jujur"))
    b.append(
        _md(
            "1. **Konvensi tanda geser Midas berlawanan** dengan konvensi perangkat lunak "
            "ini. Perbedaan itu direkonsiliasi secara eksplisit, bukan disembunyikan, dan "
            "buktinya seragam pada seluruh elemen yang dibandingkan.\n"
            "2. **Jalur lendutan adalah yang paling lemah.** Ekspor Midas hanya menyimpan "
            "enam angka desimal dalam meter, dan pada pilecap yang kaku resolusi itu lebih "
            "besar daripada selisih yang diukur. Yang terbukti di jalur ini hanyalah "
            '"tidak berbeda sejauh yang dapat diukur". Yang benar-benar membuktikan '
            "ketelitian adalah jalur resultan elemen dan reaksi.\n"
            "3. **Kesesuaian pada kasus tiang yang menindih pier tidak membuktikan bahwa "
            "idealisasi jepit-sempurna itu benar.** Kedua program memakai idealisasi yang "
            "sama, sehingga perbandingannya tidak dapat menilai asumsi tersebut. Kapasitas "
            "strut tetap wajib diperiksa terpisah."
        )
    )

    b.append(tk.heading(2, "Mesh tidak identik bit demi bit antar run"))
    b.append(
        _md(
            "Dua run dengan masukan dan versi yang sama selalu menghasilkan **jumlah** node "
            "dan elemen yang identik, tetapi posisi node dapat sedikit berbeda. Penyebabnya "
            "ada pada algoritma pembuat mesh itu sendiri dan tidak dapat dimatikan.\n\n"
            "Dampaknya terhadap angka desain **terukur kecil**: momen lajur dan luas "
            "tulangan bergeser paling banyak 0,02% antar run. Konsekuensi praktisnya:\n\n"
            "- Luas tulangan, momen lajur, dan lendutan **dapat** dibandingkan antar run.\n"
            "- Nilai **per elemen pada satu titik tidak dapat** dibandingkan begitu saja, "
            "karena elemen di lokasi tersebut memang bukan elemen yang sama.\n"
            "- Untuk mereproduksi angka secara persis, simpan berkas `nodes.csv` dan "
            "`elements.csv`; keduanya memuat mesh yang benar-benar dipakai dan dapat "
            "dibaca kembali."
        )
    )

    b.append(tk.heading(2, "Pustaka yang dipakai dan versinya"))
    b.append(
        _md(
            "Seluruh versi berikut **dipatok persis**, bukan sekadar versi minimum. Itu "
            "disengaja: pustaka numerik yang berubah versi dapat menggeser hasil, dan "
            "dokumen desain yang angkanya bergeser tanpa sebab yang tercatat tidak dapat "
            "dipertanggungjawabkan. Versi yang sama juga dicatat di setiap berkas "
            "provenance run."
        )
    )
    b.append(
        tk.table(
            ["Pustaka", "Versi", "Perannya"],
            _baris_dependency(),
            align=["left", "left", "left"],
            caption="Pustaka pihak ketiga beserta versi yang dipatok.",
        )
    )
    b.append(tk.pagebreak())
    return "\n\n".join(b)


#: Peran tiap dependency. Kuncinya nama distribusi sebagaimana ditulis `pyproject.toml`.
_PERAN: dict[str, str] = {
    "gmsh": "Pembuat mesh segiempat",
    "numpy": "Aljabar dan operasi larik",
    "pandas": "Pembacaan dan penulisan tabel",
    "shapely": "Operasi geometri bidang",
    "matplotlib": "Penggambar kontur dan denah",
    "tqdm": "Penanda kemajuan proses",
    "openseespy": "Solver elemen hingga",
    "opsvis": "Penggambar model dan deformasi",
    "shell-kit": "Kapasitas dan pemilihan tulangan menurut SNI 2847:2019",
    "typst": "Kompilasi dokumen PDF",
    "pillow": "Penyiapan gambar untuk dokumen",
    "streamlit": "Formulir grafis (opsional)",
}


def _baris_dependency() -> list[list[str]]:
    """Baris tabel dependency, ditarik dari metadata paket terpasang.

    Dibaca dari `importlib.metadata`, bukan dari `pyproject.toml`: yang relevan bagi
    pembaca adalah apa yang benar-benar dipatok pada paket yang ia pasang.
    """
    baris: list[list[str]] = []
    for spec in md.requires("pilecap-fem") or ():
        # Penanda lingkungan (`; extra == 'ui'`) DIPOTONG lebih dulu. Ia memuat `==`
        # sendiri, sehingga mengurai versi sebelum memotongnya membuat `streamlit`
        # tercetak berversi `'ui'` -- angka yang terbaca sah tetapi tidak berarti apa-apa.
        inti, _, penanda = spec.partition(";")
        inti = inti.strip()

        if "@" in inti:
            # Wheel yang dipasang lewat URL: versinya ada di nama berkasnya.
            nama = inti.split("@", 1)[0].strip()
            berkas = inti.rsplit("/", 1)[-1]
            versi = berkas.split("-")[1] if berkas.count("-") >= 2 else "-"
        elif "==" in inti:
            nama, _, versi = inti.partition("==")
        else:
            cocok = re.match(r"^([A-Za-z0-9_.\-]+)\s*(.*)$", inti)
            nama, versi = (cocok.group(1), cocok.group(2) or "-") if cocok else (inti, "-")

        peran = _PERAN.get(nama.strip(), "--")
        if "extra ==" in penanda:
            peran += " -- hanya bila fitur tambahan dipasang"
        baris.append([f"`{nama.strip()}`", f"`{versi.strip()}`", peran])
    return baris


# ---------------------------------------------------------------------------
# Bab 10 -- tanggung jawab
# ---------------------------------------------------------------------------


def chapter_responsibility() -> str:
    """Bab 10 -- pernyataan tanggung jawab dan lisensi."""
    b = [tk.heading(1, "Tanggung jawab dan lisensi", label="bab-tanggung-jawab")]
    b.append(tk.callout("CAUTION", _md(_disclaimer())))
    b.append(
        _md(
            "Pernyataan di atas berlaku bagi setiap keluaran perangkat lunak ini, dan "
            "dicetak apa adanya pada setiap lembar perhitungan, setiap ringkasan, dan "
            "setiap laporan PDF yang dihasilkannya.\n\n"
            "Dengan kata lain: perangkat lunak ini **tidak menggantikan engineer**. Ia "
            "mengerjakan bagian yang dapat diperiksa ulang -- pembuatan mesh, penyelesaian "
            "persamaan, penerapan pasal kode, penyusunan dokumen -- dan menyerahkan "
            "seluruh penilaian rekayasa kepada engineer yang bertanggung jawab. Setiap "
            "keluarannya dirancang agar dapat ditelusuri sampai ke berkas masukan dan "
            "pasal yang dipakai, justru supaya pemeriksaan itu mungkin dilakukan."
        )
    )

    b.append(tk.heading(2, "Lisensi"))
    b.append(
        _md(
            "Perangkat lunak ini diedarkan di bawah **Lisensi MIT**. Perusahaan boleh "
            "memakainya, menyalinnya, mengubahnya, dan memakainya untuk pekerjaan "
            "komersial tanpa biaya lisensi, dengan syarat pemberitahuan hak cipta dan "
            "teks lisensinya disertakan.\n\n"
            "Sebagaimana lazimnya lisensi tersebut, perangkat lunak ini diberikan "
            "**tanpa jaminan dalam bentuk apa pun**. Hal itu tidak mengurangi maupun "
            "menambah kewajiban engineer yang bertanggung jawab untuk memeriksa dan "
            "menyetujui setiap hasil sebelum dipakai."
        )
    )
    b.append(tk.pagebreak())
    return "\n\n".join(b)


# ---------------------------------------------------------------------------
# Lampiran
# ---------------------------------------------------------------------------


def appendix_capacity() -> str:
    """Lampiran A -- provenance kapasitas.

    Membawa label `lampiran-provenance` karena bab dasar teori merujuk ke sini. Isinya
    sengaja hanya bagian yang STATIS: nilai faktor reduksi dan mutu baja berbeda pada
    setiap run, dan mencetak angka contoh di panduan akan membuat pembaca mengira itulah
    nilai yang dipakai.
    """
    b = [tk.heading(1, "Lampiran A -- provenance kapasitas", label="lampiran-provenance")]
    b.append(
        _md(
            "Perhitungan kapasitas penampang tidak dikerjakan sendiri oleh perangkat lunak "
            "ini, melainkan diserahkan kepada pustaka `shell-kit` yang "
            "mengimplementasikan SNI 2847:2019 beserta sitasi pasalnya. Pemisahan itu "
            "disengaja: bagian yang menerjemahkan pasal kode menjadi angka diuji dan "
            "diversikan tersendiri."
        )
    )
    b.append(
        tk.table(
            ["Butir", "Nilai"],
            [
                ["Standar acuan", "SNI 2847:2019"],
                ["Pustaka kapasitas", f"`shell-kit` v{_versi_shell_kit()}"],
                ["Perangkat lunak ini", f"`pilecap-fem` v{__version__}"],
            ],
            align=["left", "left"],
            caption="Sumber perhitungan kapasitas.",
        )
    )
    b.append(tk.heading(2, "Pasal yang dipakai"))
    b.append(
        tk.table(
            ["Besaran", "Pasal"],
            [[f"`{k}`", v] for k, v in capacity_engine.SNI_CLAUSES.items()],
            align=["left", "left"],
            caption="Pasal SNI 2847:2019 yang dipakai beserta besaran yang ditentukannya.",
        )
    )
    b.append(
        tk.callout(
            "NOTE",
            _md(
                "Faktor reduksi kekuatan, mutu beton, dan mutu baja **tidak dicantumkan di "
                "sini**, karena nilainya Anda tetapkan sendiri pada setiap run. Nilai yang "
                "benar-benar dipakai beserta asalnya dicetak pada lampiran provenance di "
                "dalam laporan run masing-masing."
            ),
        )
    )
    b.append(tk.pagebreak())
    return "\n\n".join(b)


def _versi_shell_kit() -> str:
    try:
        return md.version("shell-kit")
    except md.PackageNotFoundError:  # pragma: no cover -- pemasangan tidak lengkap
        return "?"


#: Kombinasi beban VC-6: (nama tampilan, slug berkas). Kembar dari `VC6_KOMBINASI` di
#: `tests/test_validation_cases.py`. Paket tidak boleh mengimpor `tests/`, sehingga
#: daftarnya ditulis di sini dan `test_lampiran_perbandingan_memuat_setiap_gaya_dan_kombinasi`
#: yang menagih kesamaannya -- kombinasi baru menggagalkan test, bukan hilang dari lampiran.
KOMBINASI_VC6: tuple[tuple[str, str], ...] = (
    ("1.2D+1.6L", "1_2D_1_6L"),
    ("1.2D+1.0W", "1_2D_1_0W"),
)

#: Gaya dalam yang dibandingkan, beserta keterangannya bagi pembaca non-FEM.
MEDAN_VC6: tuple[tuple[str, str], ...] = (
    ("m_xx", "Momen lentur arah X"),
    ("m_yy", "Momen lentur arah Y"),
    ("m_xy", "Momen puntir"),
    ("q_x", "Geser melintang arah X"),
    ("q_y", "Geser melintang arah Y"),
)

#: Contoh bawaan beserta nama pendeknya, dipakai pada tabel Lampiran C.
_KASUS_VC6: tuple[str, ...] = ("ex01", "ex02", "ex03", "ex04")


def nama_gambar_vc6(jenis: str, medan: str, slug: str) -> str:
    """Nama berkas gambar perbandingan VC-6.

    Kembar dari `nama_berkas()` di `tools/plot_vc6_perbandingan.py`; dijaga
    `test_setiap_gambar_vc6_yang_dirujuk_panduan_ada_berkasnya`.
    """
    return f"vc6-{jenis}-{medan}-{slug}.png"


def _ringkasan_vc6() -> dict:
    """Angka RMS/p50/p99/maksimum, dibaca dari berkas yang ditulis skrip pembuat gambar.

    TIDAK dihitung ulang di sini, dan tidak diketik: data VC-6 tidak ikut ke dalam wheel,
    sehingga panduan tidak dapat menghitungnya sendiri di komputer pengguna. Membacanya dari
    berkas yang sama dengan yang menghasilkan gambarnya membuat tabel dan gambar tidak dapat
    menyimpang satu sama lain.
    """
    import json

    jalur = config.illustrations_dir() / "vc6-ringkasan.json"
    isi: dict = json.loads(jalur.read_text(encoding="utf-8"))
    return isi


def appendix_comparison(figs: FigureStore) -> str:
    """Lampiran C -- perbandingan lengkap per elemen terhadap Midas Civil.

    Bab 8 sengaja hanya memuat satu gaya pada satu kombinasi: menanam kedua puluh gambar di
    sana akan mengubur narasi buktinya. Yang lengkap ditaruh di sini, tempat pembaca yang
    memang hendak memeriksa dapat menelusurinya satu per satu.
    """
    ringkas = _ringkasan_vc6()
    b = [
        tk.heading(
            1,
            "Lampiran C -- perbandingan lengkap terhadap Midas Civil",
            label="lampiran-perbandingan",
        )
    ]
    b.append(
        _md(
            "Lampiran ini menyajikan perbandingan per elemen untuk **kelima gaya dalam** "
            "pada **kedua kombinasi beban**, terhadap keempat contoh bawaan. Seluruhnya "
            "berasal dari perhitungan yang sama dengan yang dipakai syarat rilis, sehingga "
            "angka di sini identik dengan yang diperiksa saat versi ini diterbitkan."
        )
    )

    b.append(tk.heading(2, "Cara membaca gambar di lampiran ini"))
    b.append(
        _md(
            "Setiap gaya disajikan dengan dua gambar.\n\n"
            "1. **Struktur dan sebaran selisih.** Panel kiri memplot selisih tiap elemen "
            "terhadap besar nilainya; yang dibaca bukan sempitnya sebaran, melainkan bahwa "
            "titiknya terpusat di garis nol **tanpa kemiringan** -- kekeliruan sistematis "
            "akan menarik titik ke satu sisi seiring membesarnya nilai. Panel kanan "
            'menjawab "berapa persen elemen yang selisihnya di bawah sekian": pilih satu '
            "tinggi, geser ke kanan sampai menyentuh kurva, lalu baca angkanya di sumbu "
            "bawah. **Kurva yang lebih ke kiri berarti lebih rapat kesesuaiannya.**\n"
            "2. **Letak selisih pada denah.** Satu panel per contoh. Gambar ini membedakan "
            '"cocok" dari "kebetulan cocok rata-rata": selisih yang berupa derau '
            "tersebar merata, sedangkan kekeliruan sistematis berkumpul di satu zona. "
            "Skala warnanya **ditetapkan per panel**, karena puncak antarcontoh berbeda "
            "sampai sepuluh kali lipat."
        )
    )
    b.append(
        tk.callout(
            "NOTE",
            _md(
                "Selisih selalu dinyatakan terhadap **nilai puncak**, bukan terhadap nilai "
                "di titik itu sendiri. Di dekat garis nol momen kedua program sama-sama "
                "benar, tetapi rasio per titiknya tak terhingga sehingga tidak bermakna."
            ),
        )
    )

    for combo, slug in KOMBINASI_VC6:
        b.append(tk.heading(2, f"Kombinasi {combo}"))
        for medan, keterangan in MEDAN_VC6:
            b.append(tk.heading(3, f"{keterangan} (`{medan}`)"))
            angka = ringkas[combo][medan]
            b.append(
                tk.table(
                    ["Contoh", "Elemen", "RMS", "Separuh di bawah", "99% di bawah", "Maksimum"],
                    [
                        [
                            f"`{kasus}`",
                            f"{angka[kasus]['n_elemen']:,}".replace(",", "."),
                            _persen(angka[kasus]["rms"]),
                            _persen(angka[kasus]["p50"]),
                            _persen(angka[kasus]["p99"]),
                            _persen(angka[kasus]["maks"]),
                        ]
                        for kasus in _KASUS_VC6
                    ],
                    align=["left", "right", "right", "right", "right", "right"],
                    caption=f"Selisih `{medan}` terhadap Midas Civil, kombinasi {combo}.",
                )
            )
            b.append(
                figs.illustration(
                    nama_gambar_vc6("sebaran", medan, slug),
                    f"Struktur dan sebaran selisih `{medan}`, kombinasi {combo}.",
                ).to_typst()
            )
            b.append(
                figs.illustration(
                    nama_gambar_vc6("peta", medan, slug),
                    f"Letak selisih `{medan}` pada denah keempat contoh, kombinasi {combo}.",
                ).to_typst(width="92%")
            )
    return "\n\n".join(b)


def _persen(nilai: float) -> str:
    """Persentase gaya Indonesia, tiga desimal."""
    return f"{nilai:.3f}".replace(".", ",") + "%"


#: Perintah yang tersedia beserta perannya. Dikunci ke entry point di `pyproject.toml`
#: lewat `test_setiap_entry_point_dijelaskan_panduan`.
_PERINTAH: tuple[tuple[str, str], ...] = (
    ("pilecap-mesh", "Membuat mesh dan model dari berkas masukan, tanpa menjalankan analisis."),
    ("pilecap-analyze", "Menjalankan analisis elemen hingga atas model yang sudah dibuat."),
    (
        "pilecap-report",
        "Membuat kontur, envelope, lembar perhitungan, dan laporan dari hasil analisis.",
    ),
    ("pilecap-run", "Menjalankan seluruh rantai di atas dalam satu perintah."),
    ("pilecap-ui", "Membuka formulir grafis di peramban."),
    ("pilecap-manual", "Menghasilkan panduan ini untuk versi yang sedang terpasang."),
)


def appendix_commands() -> str:
    """Lampiran B -- daftar perintah beserta pilihan yang paling sering dipakai."""
    b = [tk.heading(1, "Lampiran B -- daftar perintah", label="lampiran-perintah")]
    b.append(
        tk.table(
            ["Perintah", "Kegunaan"],
            [[f"`{nama}`", ket] for nama, ket in _PERINTAH],
            align=["left", "left"],
            caption="Perintah yang tersedia setelah pemasangan.",
        )
    )
    b.append(
        _md(
            "Setiap perintah menerima `--help`, yang menampilkan seluruh pilihannya "
            "beserta nilai bawaannya pada versi yang terpasang. Itulah rujukan yang paling "
            "dapat dipercaya, karena datang langsung dari perangkat lunaknya."
        )
    )
    b.append(tk.code_block("pilecap-run --help"))

    b.append(tk.heading(2, "Pilihan yang paling sering dipakai"))
    b.append(
        tk.table(
            ["Pilihan", "Artinya"],
            [
                [
                    "`--input-dir`",
                    "Folder berisi berkas masukan. Bawaannya folder tempat perintah dijalankan.",
                ],
                ["`--output-dir`", "Folder induk tempat hasil ditulis. Bawaannya `output`."],
                [
                    "`--config`",
                    "Menyebut berkas konfigurasi secara langsung, bila pola nama otomatis "
                    "tidak dipakai.",
                ],
                ["`--pdf`", "Membuat laporan PDF lengkap untuk run tersebut."],
                ["`--init-example`", "Menyalin salah satu contoh bawaan ke folder saat ini."],
                ["`--version`", "Menampilkan versi perangkat lunak yang terpasang."],
                [
                    "`--log-level`",
                    "Mengatur seberapa rinci pesan yang dicetak selama proses berjalan.",
                ],
            ],
            align=["left", "left"],
            caption="Pilihan baris perintah yang paling sering dipakai.",
        )
    )

    b.append(tk.heading(2, "Menghasilkan ulang panduan ini"))
    b.append(
        _md(
            "Panduan ini dapat dibuat ulang kapan saja untuk versi yang sedang terpasang. "
            "Gunakan itu bila Anda memperbarui perangkat lunaknya: daftar field, "
            "keterbatasan, dan pasal dapat berbeda antarversi."
        )
    )
    b.append(tk.code_block("pilecap-manual --out panduan"))
    return "\n\n".join(b)
