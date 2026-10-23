"""Keadaan formulir: visibilitas bersyarat, label satuan, dan koersi nilai.

**TIDAK mengimpor streamlit maupun wx.** Modul ini memegang seluruh keputusan formulir yang
dapat salah secara diam-diam -- field yang seharusnya tersembunyi tetapi tampil, label satuan
yang tertinggal, "kosong" yang berubah menjadi nol -- sehingga ia harus dapat diuji pada
lingkungan tanpa display sama sekali.

.. rubric:: Mengapa satu lintasan penuh, bukan graf ketergantungan

Streamlit menjalankan ulang seluruh skrip pada tiap interaksi, dan di situlah visibilitas
serta label diputuskan. Frontend event-driven seperti wx tidak mendapatkannya gratis.

Alih-alih melacak "field mana memengaruhi field mana", `layout_state` menghitung ULANG
keadaan seluruh field dari `values`. Dengan 60 field itu praktis gratis, dan ia melenyapkan
satu kelas bug sepenuhnya: ketergantungan yang terlewat didaftarkan. Frontend cukup
memanggilnya setelah perubahan apa pun.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pilecap_fem import config
from pilecap_fem.ui import runopts
from pilecap_fem.ui.schema import ALL_FIELDS, Field

#: Field yang keadaannya dihitung modul ini: isi config DITAMBAH opsi run.
#:
#: Digabung di sini, bukan di tiap frontend, supaya keduanya tidak mungkin merender himpunan
#: yang berbeda.
SEMUA_FIELD: tuple[Field, ...] = (*ALL_FIELDS, *runopts.RUN_FIELDS)


@dataclass(frozen=True)
class FieldView:
    """Bagaimana satu field harus tampil pada keadaan formulir saat ini."""

    field: Field
    visible: bool
    label: str


def unit_labels(values: dict[str, Any]) -> dict[str, str]:
    """Satuan tampilan saat ini per besaran, dari pilihan `units.*` di formulir.

    Diturunkan dari nilai formulir dengan cadangan `config.DEFAULT_INPUT_UNITS` -- BUKAN dari
    daftar yang diketik ulang. Halaman Streamlit sempat menanam `{"length": "mm", "force":
    "kN", "stress": "MPa"}` langsung di kodenya; daftar seperti itu diam-diam menyimpang
    begitu bawaan di `config` berubah, dan label satuan yang keliru pada formulir masukan
    adalah kesalahan yang merambat sampai ke angka desain.
    """
    labels = dict(config.DEFAULT_INPUT_UNITS)
    for besaran in labels:
        dipilih = values.get(f"units.{besaran}")
        if dipilih:
            labels[besaran] = str(dipilih)
    return labels


def label_for(f: Field, labels: dict[str, str]) -> str:
    """Label field berikut satuannya, mis. ``Tebal [mm]``.

    `Field.unit` dapat berupa KUNCI BESARAN (`length`, `stress`) yang satuannya dipilih
    pengguna, atau label harfiah yang memang tetap (`kN/m^3`). Keduanya dibedakan lewat
    keberadaannya di `labels`, bukan lewat daftar terpisah.
    """
    if not f.unit:
        return f.label
    return f"{f.label} [{labels.get(f.unit, f.unit)}]"


def layout_state(values: dict[str, Any]) -> dict[str, FieldView]:
    """Keadaan tampil seluruh field pada `values` saat ini.

    Opsi run tidak punya `visible_when`, sehingga selalu tampil -- tetapi tetap dilewatkan ke
    sini supaya frontend hanya perlu satu jalur untuk keduanya.
    """
    labels = unit_labels(values)
    keluaran: dict[str, FieldView] = {}
    for f in SEMUA_FIELD:
        tampil = f.visible_when is None or bool(f.visible_when(values))
        keluaran[f.key] = FieldView(field=f, visible=tampil, label=label_for(f, labels))
    return keluaran


def coerce_optional_number(raw: str) -> tuple[float | None, str | None]:
    """Teks dari field angka OPSIONAL menjadi `(nilai, peringatan)`.

    Field angka opsional digambar sebagai kotak teks, bukan pemutar angka, karena "kosong"
    harus benar-benar dapat dinyatakan -- dan kontrol angka tidak punya keadaan kosong yang
    jelas. Mengosongkannya berarti "pakai bawaan engine", yang berbeda maknanya dari nol.

    Masukan yang tidak terbaca mengembalikan `None` BESERTA peringatan, tidak diam-diam
    menjadi nol: pengguna yang salah ketik berhak tahu bahwa isiannya diabaikan.
    """
    teks = (raw or "").strip()
    if not teks:
        return None, None
    try:
        return float(teks), None
    except ValueError:
        return None, f"{teks!r} bukan angka; diabaikan."


def coerce_number(raw: str, default: Any) -> tuple[Any, str | None]:
    """Teks dari field angka WAJIB menjadi `(nilai, peringatan)`.

    Field angka wajib pun digambar sebagai kotak teks di antarmuka desktop, bukan sebagai
    pemutar angka. Alasannya DIUKUR, bukan selera: `wx.SpinCtrlDouble` menurunkan jumlah
    angka di belakang koma dari `inc`-nya, dan dengan `inc` berapa pun yang masuk akal di
    sini ia melaporkan `digits=0` -- sehingga `0.05` dibacanya `0.0` dan `27.5` dibacanya
    `28.0`, tanpa sepatah pun peringatan. Rasio redaman dan tebal pelat yang berubah
    diam-diam saat config dimuat adalah kegagalan terburuk yang bisa dipunyai alat ini:
    hasilnya tetap keluar, tetap tampak wajar, dan salah.

    Berbeda dari `coerce_optional_number`, kosong di sini BUKAN "pakai bawaan engine" --
    field ini wajib punya nilai -- sehingga kosong maupun tak terbaca jatuh ke bawaan field
    beserta peringatannya.

    Selalu `float`, tidak pernah `int`, meski teksnya literal bilangan bulat. Itu bukan
    kelalaian: `st.number_input` pada halaman Streamlit terkunci bertipe float sejak render
    pertama, sehingga config yang ditulisnya memuat `75.0`. Mengembalikan `int` di sini
    membuat kedua antarmuka menulis config yang berbeda dari masukan yang sama -- DIUKUR
    dengan membandingkan berkas yang benar-benar ditulis keduanya, bukan disimpulkan dari
    kode.
    """
    teks = (raw or "").strip()
    if not teks:
        return default, "kosong; dipakai nilai bawaan."
    try:
        return float(teks), None
    except ValueError:
        return default, f"{teks!r} bukan angka; dipakai nilai bawaan."


def pilihan_aman(f: Field) -> tuple[tuple[Any, ...], str | None]:
    """Daftar pilihan field, beserta pesan bila sumbernya gagal dibaca.

    `choices_fn` untuk `analysis.shell_element` dan `analysis.section` menarik openseespy --
    lambat, dan dapat gagal pada instalasi yang tidak lengkap. Kegagalannya **tidak boleh
    menjatuhkan formulir**: pengguna masih dapat mengisi seluruh field lain, dan kontrol yang
    kosong beserta pesannya jauh lebih berguna daripada jendela yang menolak terbuka.
    """
    try:
        return tuple(f.options()), None
    # Sumber pilihan ada di luar paket ini, jadi galatnya tidak dapat didaftar.
    except Exception as exc:
        return (), f"Daftar pilihan tidak dapat dibaca: {exc}"


def teks_angka(nilai: Any) -> str:
    """Angka menjadi teks untuk ditaruh di kotak isian.

    Bilangan bulat ditulis tanpa ekor `.0` -- `1200`, bukan `1200.0` -- karena nyaris semua
    masukan geometri bulat dan ekor itu membuat formulir tampak berisik.

    Aman karena `formstate.coerce_number` SELALU mengembalikan `float`: apa pun yang
    ditampilkan di sini dibaca kembali sebagai float yang sama, sehingga peringkasan ini
    tidak dapat mengubah config yang ditulis.
    """
    if nilai is None:
        return ""
    if isinstance(nilai, float) and nilai.is_integer():
        return str(int(nilai))
    return str(nilai)


__all__ = [
    "SEMUA_FIELD",
    "FieldView",
    "coerce_number",
    "coerce_optional_number",
    "label_for",
    "layout_state",
    "pilihan_aman",
    "teks_angka",
    "unit_labels",
]
