"""Bab referensi konfigurasi: seluruh bagian dan field formulir, dari `ui.schema`.

Inilah bab yang membuat panduan ini dapat berdiri sendiri. Pembacanya tidak punya README
maupun `--help` yang mudah dijangkau, sehingga daftar field yang tidak lengkap berarti ia
kehilangan satu-satunya keterangan yang ia miliki tentang setelan tersebut.

.. rubric:: Konsekuensi yang disengaja

Merender bab ini **memuat solver**, karena daftar pilihan sebagian field diambil dari
sumbernya (`fem_engine`, `shell-kit`) alih-alih disalin. Artinya panduan hanya dapat
dibangun dari pemasangan yang benar-benar berfungsi. Itu fitur, bukan keterbatasan: daftar
pilihan yang disalin akan menyimpang diam-diam begitu sumbernya berubah.
"""

from __future__ import annotations

import json
from typing import Any

from pilecap_fem import config, io_utils
from pilecap_fem.reporting_pdf import typst_kit as tk
from pilecap_fem.reporting_pdf.figures import FigureStore
from pilecap_fem.ui import schema

__all__ = ["SYARAT_TAMPIL", "chapter_config"]

#: Kalimat syarat untuk setiap field yang hanya berlaku pada cabang tertentu.
#:
#: Ditulis sebagai data, bukan diintrospeksi dari `Field.visible_when`: predikatnya adalah
#: fungsi, dan fungsi tidak dapat menjelaskan dirinya kepada pembaca. Yang menjaga daftar
#: ini tetap jujur adalah `test_setiap_field_bersyarat_punya_kalimat_penjelas`, yang
#: menuntut kuncinya SAMA PERSIS dengan himpunan field ber-`visible_when` -- sehingga
#: field bersyarat baru menghentikan pembuatan panduan alih-alih terbit tanpa syaratnya.
SYARAT_TAMPIL: dict[str, str] = {
    "pier.width_x": "bentuk pier `rectangular`",
    "pier.width_y": "bentuk pier `rectangular`",
    "pier.diameter": "bentuk pier `circular`",
    "mesh.size_local_pile": "mode ukuran mesh `graded`",
    "mesh.size_local_pier": "mode ukuran mesh `graded`",
    "analysis.n_layers": "penampang `LayeredShell`",
    "design.rebar_spacing": "mode tulangan `spacing_fixed`",
    "design.rebar_config": "mode tulangan `diameter_fixed`",
    "design.strips_x": "basis angka desain `strip`",
    "design.strips_y": "basis angka desain `strip`",
    "design.moment_at": "basis angka desain `strip`",
}

#: Nama jenis isian dalam bahasa yang dimengerti pembaca non-teknis.
_JENIS: dict[str, str] = {
    "number": "angka desimal",
    "int": "bilangan bulat",
    "text": "teks",
    "select": "satu pilihan",
    "multiselect": "beberapa pilihan",
    "bool": "ya atau tidak",
    "pair": "sepasang angka",
}

#: Gambar tambahan untuk field tertentu: (berkas, caption, catatan penafsirannya).
#:
#: Berbeda dari `Section.illustration` yang digerakkan data, gambar ini ditempatkan
#: sengaja pada satu field. `design.rebar_basis` adalah setelan yang paling mudah
#: disalahtafsirkan di seluruh alat ini -- kedua pilihannya menghasilkan gambar kontur yang
#: IDENTIK, dan yang berbeda hanya arti angkanya. Menunjukkan keduanya berdampingan adalah
#: satu-satunya cara menjelaskan itu tanpa pembaca harus menjalankan sendiri dua kali.
_GAMBAR_FIELD: dict[str, tuple[str, str, str]] = {
    "design.rebar_basis": (
        "contoh-diameter-element-vs-strip.png",
        "Kontur diameter tulangan dari run yang sama, hanya `design.rebar_basis` yang "
        "diubah: `element` (kiri) dan `strip` (kanan).",
        "Kedua peta itu **identik piksel demi piksel**, dan itu memang seharusnya: kontur "
        "selalu digambar dari medan momen per elemen apa adanya, terlepas dari basis yang "
        "dipilih. Yang berbeda hanya keterangan di kepala gambar -- kiri menyatakan "
        "gambar inilah sumber angka desain, kanan menyatakan gambar ini sekadar peta "
        "orientasi sedangkan angka resminya ada di berkas lajur. **Bacalah basis yang "
        "tercetak di kepala gambar sebelum menafsirkan gambar mana pun dari alat ini**; "
        "gambarnya sendiri tidak cukup untuk membedakan.",
    ),
}

#: Bawaan yang TIDAK boleh dicetak apa adanya.
#:
#: `project.date` bawaannya dievaluasi saat modul dimuat, sehingga mencetaknya akan membuat
#: sumber panduan berubah setiap hari dan setiap diff antarversi menjadi tidak terbaca.
_BAWAAN_DINAMIS: dict[str, str] = {"project.date": "tanggal hari ini"}


def _bawaan(f: schema.Field) -> str:
    """Nilai bawaan sebagaimana Anda mengetiknya di berkas konfigurasi.

    Ditulis sebagai JSON, bukan sebagai `repr` Python. Berkas sasarannya memang JSON, dan
    ini sekaligus menghindari kerancuan koma desimal: sepasang angka yang ditulis `[0,0]`
    dalam kebiasaan Indonesia tidak dapat dibedakan dari satu angka nol koma nol.
    """
    if f.key in _BAWAAN_DINAMIS:
        return _BAWAAN_DINAMIS[f.key]
    if f.default is None:
        return "`null`"
    return f"`{json.dumps(f.default)}`"


def _satuan(f: schema.Field) -> str:
    """Satuan tampilan field, tidak pernah diketik sebagai literal.

    `Field.unit` adalah KUNCI BESARAN untuk sebagian field (`length`, `stress`) dan sudah
    berupa label untuk sisanya. Keduanya dibedakan lewat `config.DISPLAY_UNITS`, bukan
    lewat daftar yang ditulis di sini.
    """
    if not f.unit:
        return "--"
    if f.unit in config.DISPLAY_UNITS:
        return f"`{io_utils.display_unit(f.unit)}`"
    return f"`{f.unit}`"


def _pilihan(f: schema.Field, catat: list[str]) -> tuple[str, ...] | None:
    """Daftar nilai yang sah, diambil dari sumbernya.

    Kegagalan TIDAK ditelan: ia dicatat sebagai degradasi, sehingga panduan yang kehilangan
    daftar nilai sah sebuah field tidak dapat terbit tanpa disadari.
    """
    try:
        return f.options()
    except Exception as exc:
        catat.append(f"daftar pilihan `{f.key}` tidak dapat dibaca: {exc}")
        return None


def _wajib(f: schema.Field) -> str:
    """Kolom "Wajib" pada tabel ringkas.

    Field bersyarat ditandai tersendiri, bukan "ya". `Field.optional` menjawab pertanyaan
    yang berbeda -- boleh bernilai kosong atau tidak -- sehingga menandai `pier.width_x`
    dan `pier.diameter` sama-sama "ya" akan membuat pembaca yang hanya memindai tabel
    menyimpulkan keduanya harus diisi, padahal keduanya cabang yang saling meniadakan.
    """
    if f.key in SYARAT_TAMPIL:
        return "bersyarat"
    return "tidak" if f.optional else "ya"


def _batas(f: schema.Field) -> str:
    if f.min_value is not None and f.max_value is not None:
        return f"Nilainya harus antara `{f.min_value}` dan `{f.max_value}`."
    if f.min_value is not None:
        return f"Nilainya tidak boleh kurang dari `{f.min_value}`."
    if f.max_value is not None:
        return f"Nilainya tidak boleh lebih dari `{f.max_value}`."
    return ""


def _keterangan_field(f: schema.Field, figs: FigureStore, catat: list[str]) -> list[str]:
    """Prosa satu field: penjelasan, syarat berlaku, pilihan, batas, dan gambar."""
    keluaran = [tk.heading(3, f"`{f.key}` -- {f.label}")]
    if f.help:
        keluaran.append(tk.from_markdown(f.help))
    if f.key in _GAMBAR_FIELD:
        berkas, caption, catatan = _GAMBAR_FIELD[f.key]
        keluaran.append(figs.illustration(berkas, caption).to_typst())
        keluaran.append(tk.from_markdown(catatan))

    tambahan: list[str] = []
    if f.key in SYARAT_TAMPIL:
        tambahan.append(
            f"**Hanya berlaku bila {SYARAT_TAMPIL[f.key]}.** Pada cabang yang lain field "
            "ini tidak ditulis ke berkas konfigurasi sama sekali, dan tidak dibaca."
        )
    pilihan = _pilihan(f, catat)
    if pilihan:
        nilai = ", ".join(f"`{_json_ringkas(p)}`" for p in pilihan)
        tambahan.append(f"Nilai yang sah: {nilai}.")
    elif pilihan is None:
        tambahan.append(
            "Daftar nilai yang sah tidak dapat dibaca saat panduan ini dibuat; "
            "jalankan `pilecap-ui` untuk melihatnya."
        )
    batas = _batas(f)
    if batas:
        tambahan.append(batas)
    if f.optional:
        tambahan.append("Boleh dikosongkan; tulis `null` untuk memakai bawaannya.")
    if tambahan:
        keluaran.append(tk.from_markdown("\n\n".join(tambahan)))
    return keluaran


def _json_ringkas(nilai: Any) -> str:
    """Nilai pilihan sebagaimana ditulis di berkas konfigurasi."""
    return nilai if isinstance(nilai, str) else json.dumps(nilai)


def chapter_config(figs: FigureStore, catat: list[str]) -> str:
    """Bab referensi konfigurasi, dua lapis per bagian.

    Lapis pertama adalah tabel ringkas yang dapat dipindai pengguna berpengalaman; lapis
    kedua adalah uraian tiap field bagi yang baru pertama kali menyiapkan masukan. Uraian
    itu memakai heading tingkat tiga, yang berada di luar kedalaman daftar isi -- daftar
    isi dengan 60 entri field justru menyulitkan pencarian.
    """
    hilang = {f.key for f in schema.ALL_FIELDS if f.visible_when} - set(SYARAT_TAMPIL)
    if hilang:  # pragma: no cover -- dijaga test
        raise KeyError(f"field bersyarat tanpa kalimat penjelas di panduan: {sorted(hilang)}")

    b = [tk.heading(1, "Referensi konfigurasi", label="bab-konfigurasi")]
    b.append(
        tk.from_markdown(
            f"Seluruh masukan perangkat lunak ini terdiri atas **{len(schema.ALL_FIELDS)} "
            f"field** yang dikelompokkan ke dalam **{len(schema.SECTIONS)} bagian**. Bab "
            "ini menguraikan seluruhnya, sehingga berkas konfigurasi dapat disusun tanpa "
            "rujukan lain.\n\n"
            "Field ditulis di dalam berkas konfigurasi berformat JSON dengan nama bagian "
            "sebagai kunci luar dan nama field sebagai kunci dalam. Formulir grafis "
            "`pilecap-ui` menanyakan field yang sama dan menuliskan berkas itu untuk Anda."
        )
    )
    b.append(
        tk.callout(
            "NOTE",
            tk.from_markdown(
                "Sebagian field hanya berlaku pada cabang tertentu -- misalnya lebar pier "
                "hanya berlaku bila pier berbentuk persegi. Field semacam itu "
                "**dihilangkan sama sekali** dari berkas konfigurasi pada cabang yang "
                "lain, bukan ditulis bernilai kosong. Setiap field yang bersyarat "
                "menyebutkan syaratnya sendiri di bawah ini."
            ),
        )
    )

    for bagian in schema.SECTIONS:
        b.extend(_bagian(bagian, figs, catat))

    b.append(tk.pagebreak())
    return "\n\n".join(b)


def _bagian(bagian: schema.Section, figs: FigureStore, catat: list[str]) -> list[str]:
    keluaran = [tk.heading(2, bagian.title, label=f"cfg-{tk.slug(bagian.title)}")]
    if bagian.help:
        keluaran.append(tk.from_markdown(bagian.help))
    if bagian.illustration:
        keluaran.append(
            figs.illustration(
                bagian.illustration, f"Ilustrasi untuk bagian {bagian.title}."
            ).to_typst(width="80%")
        )

    keluaran.append(
        tk.table(
            ["Field", "Jenis", "Wajib", "Bawaan", "Satuan"],
            [
                [
                    f"`{f.name}`",
                    _JENIS.get(f.kind, f.kind),
                    _wajib(f),
                    _bawaan(f),
                    _satuan(f),
                ]
                for f in bagian.fields
            ],
            align=["left", "left", "center", "left", "left"],
            caption=f"Ringkasan field bagian {bagian.title}.",
        )
    )
    for f in bagian.fields:
        keluaran.extend(_keterangan_field(f, figs, catat))
    return keluaran
