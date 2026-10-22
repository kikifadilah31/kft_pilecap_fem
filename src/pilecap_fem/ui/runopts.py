"""Opsi penyajian & jalannya analisis, sebagai deskriptor yang dipakai SEMUA frontend.

**TIDAK mengimpor streamlit maupun wx**, dengan alasan yang sama seperti `schema.py` dan
`argv.py`: yang dapat salah diam-diam di sini adalah memancarkan flag yang tidak dikenal CLI.

.. rubric:: Mengapa dipisahkan dari `app.py`

Sepuluh opsi ini semula ditulis inline di halaman Streamlit, lengkap dengan prosa bantuannya.
Begitu ada frontend kedua, menuliskannya ulang berarti dua salinan prosa dan **dua peluang
menyimpang dari kunci `dest` yang diharapkan `argv.build_argv`** -- padahal flag yang tidak
dikenal baru ketahuan saat run gagal di tangan pengguna.

Karena ia memakai ulang `schema.Field`, satu loop perender widget melayani bagian skema
maupun bagian ini. Frontend tidak perlu tahu bedanya.

.. rubric:: Kunci berawalan `run.`

Kunci config sesungguhnya berbentuk `blok.field` (`pilecap.thickness`) dan ikut ke dalam
`pilecap_config.json`. Opsi di sini BUKAN isi config -- ia argumen baris perintah -- sehingga
diberi awalan `run.` agar tidak mungkin tertukar. `to_argv_values()` melepas awalan itu tepat
sebelum menyerahkannya ke `build_argv`, yang memakai kunci `dest` argparse apa adanya.
"""

from __future__ import annotations

from typing import Any

from pilecap_fem import config
from pilecap_fem.ui.schema import Field, Section

#: Awalan kunci. Dilepas oleh `to_argv_values`.
PREFIX = "run."

RUN_SECTION: Section = Section(
    title="Opsi penyajian & jalannya analisis",
    icon=":material/tune:",
    help="Tidak satu pun opsi di bagian ini mengubah angka hasil -- semuanya soal penyajian "
    "dan cakupan run. Bawaannya aman; lewati saja bila ragu.",
    fields=(
        Field(
            "run.output_dir",
            "Folder output",
            "text",
            "output",
            help="Folder tempat hasil ditulis, relatif terhadap folder kerja di atas. Setiap "
            "run membuat subfolder baru bertimestamp dan TIDAK PERNAH menimpa run sebelumnya, "
            "jadi aman dipakai berulang kali.",
        ),
        Field(
            "run.theme",
            "Tema plot",
            "select",
            config.DEFAULT_THEME,
            choices=tuple(config.THEMES),
            help="Warna latar seluruh gambar. `light` untuk dicetak atau ditempel di laporan; "
            "`dark` lebih nyaman dibaca di layar. Angka dan skalanya identik.",
        ),
        Field(
            "run.contour_method",
            "Metode kontur",
            "select",
            config.DEFAULT_CONTOUR_METHOD,
            choices=tuple(config.CONTOUR_METHODS),
            help="Cara nilai digambar. `element-center` mewarnai tiap elemen datar -- itulah "
            "yang sebenarnya dihitung, dan jadi bawaan. `average-nodal` merata-ratakan ke "
            "titik simpul sehingga tampak halus, tetapi kehalusan itu tidak pernah dihitung "
            "dan paling menyesatkan di sekitar tepi pier.",
        ),
        Field(
            "run.dpi",
            "DPI",
            "int",
            config.OUTPUT_DPI,
            min_value=50,
            max_value=600,
            step=50,
            help="Kerapatan titik gambar PNG. Naikkan bila gambar akan dicetak besar atau "
            "diperbesar untuk memeriksa detail; berkasnya ikut membesar.",
        ),
        Field(
            "run.log_level",
            "Level log",
            "select",
            "INFO",
            choices=("INFO", "DEBUG", "WARNING", "ERROR"),
            help="Seberapa rinci log yang tampil selama run dan ditulis ke `run.log`. `INFO` "
            "sudah memuat seluruh langkah penting. Pakai `DEBUG` hanya saat menelusuri "
            "masalah -- keluaran gmsh ikut ditampilkan dan sangat panjang.",
        ),
        Field(
            "run.combo",
            "Batasi kombinasi (pisahkan spasi)",
            "text",
            "",
            optional=True,
            help="Nama kombinasi dari `pile_reactions.csv` yang ingin dijalankan saja, mis. "
            "`1.2D+1.6L`. Berguna untuk mencoba cepat pada satu kombinasi sebelum menjalankan "
            "semuanya. Kosongkan untuk menganalisis seluruhnya.",
        ),
        Field(
            "run.opsvis",
            "Paksa plot opsvis walau elemen banyak",
            "bool",
            False,
            help="Gambar model dan bentuk terdeformasi dari OpenSeesPy. Bawaannya DILEWATI di "
            f"atas {config.OPSVIS_MAX_ELEMENTS:,} elemen karena waktu gambarnya tumbuh lebih "
            "cepat daripada linier dan dapat memakan menit-menit. Centang bila Anda memang "
            "membutuhkan gambar itu dan bersedia menunggu.",
        ),
        Field(
            "run.no_rebar_plots",
            "Lewati plot tulangan (lebih cepat)",
            "bool",
            False,
            help="Melewati peta diameter, spasi, dan sengkang. Angka tulangan TETAP dihitung "
            "dan tetap ada di `rebar_design.csv` serta calc sheet -- hanya gambarnya yang "
            "tidak dibuat. Berguna saat masih mencoba-coba geometri.",
        ),
        Field(
            "run.no_envelope",
            "Lewati envelope",
            "bool",
            False,
            help="Melewati pembuatan folder `Envelope/`, yang berisi nilai terselubung "
            "(maksimum/minimum) di seluruh kombinasi beserta keterangan kombinasi mana yang "
            "menentukan. Kosongkan centang ini bila Anda menganalisis lebih dari satu "
            "kombinasi -- envelope-lah yang biasanya dipakai mendesain.",
        ),
        Field(
            "run.pdf",
            "Buat laporan PDF",
            "bool",
            False,
            help="Satu dokumen PDF lengkap untuk seluruh run: sampul, dasar teori beserta "
            "rumus dan sumbernya, data masukan, satu bab per kombinasi, envelope, "
            "keterbatasan, dan provenance -- dengan seluruh diagram sebagai gambar bernomor. "
            "Sumber Typst-nya ikut disimpan agar hasilnya dapat diperiksa. Menambah waktu di "
            "akhir pelaporan dan menghasilkan berkas belasan MB.",
        ),
    ),
)

RUN_FIELDS: tuple[Field, ...] = RUN_SECTION.fields


def default_values() -> dict[str, Any]:
    """Nilai awal opsi run, berkunci `run.<dest>`."""
    return {f.key: f.default for f in RUN_FIELDS}


def to_argv_values(values: dict[str, Any]) -> dict[str, Any]:
    """Ubah nilai formulir menjadi dict berkunci `dest` yang diterima `argv.build_argv`.

    Hanya satu field yang perlu diterjemahkan: `combo` diketik sebagai satu baris teks
    dipisah spasi, sedangkan CLI menerima `--combo` berulang. Transformasinya ditulis
    eksplisit di sini, bukan disamarkan sebagai jenis field tersendiri -- pembaca kode
    berhak melihat bahwa ada satu yang memang istimewa.
    """
    keluaran: dict[str, Any] = {}
    for f in RUN_FIELDS:
        dest = f.key.removeprefix(PREFIX)
        nilai = values.get(f.key, f.default)
        if dest == "combo":
            teks = str(nilai or "").strip()
            keluaran[dest] = teks.split() if teks else None
            continue
        keluaran[dest] = nilai
    return keluaran


__all__ = ["PREFIX", "RUN_FIELDS", "RUN_SECTION", "default_values", "to_argv_values"]
