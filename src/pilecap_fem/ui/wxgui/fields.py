"""`Field` menjadi kontrol wx, beserta pembacaan nilainya kembali.

Satu fungsi per arah (`tulis`/`baca`), supaya tidak ada widget yang punya aturan konversinya
sendiri. Aturan konversi yang tersebar adalah cara paling mudah membuat dua antarmuka
menghasilkan config yang berbeda dari masukan yang sama.

Koersi teks ke angka sengaja TIDAK ada di sini melainkan di `ui.formstate`, supaya ia dapat
diuji tanpa display -- lihat alasannya di `formstate.coerce_number`.
"""

from __future__ import annotations

from typing import Any

import wx

from pilecap_fem.ui import formstate
from pilecap_fem.ui.schema import Field

#: Lebar kolom label. Cukup untuk label terpanjang berikut satuannya tanpa membuat kolom
#: kontrol menjadi sempit.
LEBAR_LABEL = 260

#: Lebar kotak isian angka. Seragam supaya kolomnya rata dari seksi ke seksi.
LEBAR_ANGKA = 140


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


class KontrolField:
    """Satu baris formulir: label, kontrol, dan keterangan bantuan.

    Membungkus kontrol wx-nya alih-alih mewarisinya, karena satu `Field` dapat memerlukan
    DUA kontrol (`pair`) dan satu baris juga memuat teks bantuan yang ikut disembunyikan.
    """

    def __init__(self, induk: wx.Window, f: Field, *, pilihan: tuple[Any, ...]) -> None:
        self.field = f
        self.panel = wx.Panel(induk)
        self._pilihan = pilihan
        self._peringatan: str | None = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        baris = wx.BoxSizer(wx.HORIZONTAL)

        self.label = wx.StaticText(self.panel, label=f.label, size=(LEBAR_LABEL, -1))
        baris.Add(self.label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        # `Any`, bukan `wx.Window`: jenis kontrolnya memang berbeda per `kind`, dan
        # tipe yang lebih sempit hanya akan dipatahkan `cast` di tiap pemakaian.
        self._kedua: Any = None
        self.kontrol: Any = self._buat_kontrol(baris)

        sizer.Add(baris, 0, wx.EXPAND | wx.ALL, 4)
        if f.help:
            self.bantuan = wx.StaticText(self.panel, label=f.help)
            self.bantuan.Wrap(620)
            self.bantuan.SetForegroundColour(wx.Colour(96, 96, 96))
            kecil = self.bantuan.GetFont()
            kecil.SetPointSize(max(7, kecil.GetPointSize() - 1))
            self.bantuan.SetFont(kecil)
            sizer.Add(self.bantuan, 0, wx.LEFT | wx.BOTTOM, LEBAR_LABEL + 12)
        self.panel.SetSizer(sizer)

    # -- pembuatan ---------------------------------------------------------

    def _buat_kontrol(self, baris: wx.BoxSizer) -> Any:
        f = self.field
        p = self.panel

        if f.kind == "bool":
            k: Any = wx.CheckBox(p)
        elif f.kind == "select":
            k = wx.Choice(p, choices=[str(o) for o in self._pilihan])
        elif f.kind == "multiselect":
            k = wx.CheckListBox(p, choices=[str(o) for o in self._pilihan])
            k.SetMinSize((-1, 108))
        elif f.kind == "int":
            k = wx.SpinCtrl(
                p,
                min=int(f.min_value) if f.min_value is not None else 0,
                max=int(f.max_value) if f.max_value is not None else 1_000_000,
            )
            if f.step:
                # `run.dpi` berentang 50..600; menaikkannya satu per satu membuat kontrolnya
                # praktis tidak terpakai.
                k.SetIncrement(int(f.step))
            k.SetMinSize((LEBAR_ANGKA, -1))
        elif f.kind == "pair":
            k = wx.TextCtrl(p, size=(LEBAR_ANGKA, -1))
            self._kedua = wx.TextCtrl(p, size=(LEBAR_ANGKA, -1))
        else:
            # `text`, dan SELURUH field angka -- wajib maupun opsional.
            #
            # Angka memakai kotak teks, bukan `wx.SpinCtrlDouble`, karena yang terakhir
            # menurunkan jumlah desimalnya dari `inc` dan melaporkan `digits=0`: ia membaca
            # `0.05` sebagai `0.0`. Lihat `formstate.coerce_number`.
            #
            # Untuk yang opsional ada alasan kedua yang berdiri sendiri: "kosong" harus
            # benar-benar dapat dinyatakan, dan itu berbeda maknanya dari nol -- ia berarti
            # "pakai bawaan engine".
            k = wx.TextCtrl(p)
            if f.kind == "number":
                k.SetMinSize((LEBAR_ANGKA, -1))

        lentur = 0 if (self._kedua is not None or f.kind in {"int", "number"}) else 1
        baris.Add(k, lentur, wx.EXPAND)
        if self._kedua is not None:
            baris.Add(self._kedua, 0, wx.LEFT, 6)
        return k

    # -- nilai -------------------------------------------------------------

    def tulis(self, nilai: Any) -> None:
        """Isi kontrol dari sebuah nilai formulir."""
        f = self.field
        if f.kind == "bool":
            self.kontrol.SetValue(bool(nilai))
        elif f.kind == "select":
            daftar = [str(o) for o in self._pilihan]
            self.kontrol.SetSelection(daftar.index(str(nilai)) if str(nilai) in daftar else 0)
        elif f.kind == "multiselect":
            terpilih = {str(x) for x in (nilai or ())}
            for i, o in enumerate(self._pilihan):
                self.kontrol.Check(i, str(o) in terpilih)
        elif f.kind == "int":
            self.kontrol.SetValue(int(nilai) if nilai is not None else 0)
        elif f.kind == "pair":
            pasangan = list(nilai or [0.0, 0.0])
            self.kontrol.SetValue(teks_angka(pasangan[0]))
            assert self._kedua is not None
            self._kedua.SetValue(teks_angka(pasangan[1]))
        elif f.kind == "number":
            self.kontrol.SetValue(teks_angka(nilai))
        else:
            self.kontrol.SetValue("" if nilai is None else str(nilai))

    def baca(self) -> Any:
        """Nilai formulir dari kontrol. Menyetel `peringatan` bila masukannya tak terbaca."""
        f = self.field
        self._peringatan = None
        if f.kind == "bool":
            return bool(self.kontrol.GetValue())
        if f.kind == "select":
            i = self.kontrol.GetSelection()
            return self._pilihan[i] if 0 <= i < len(self._pilihan) else f.default
        if f.kind == "multiselect":
            return [self._pilihan[i] for i in self.kontrol.GetCheckedItems()]
        if f.kind == "int":
            return int(self.kontrol.GetValue())
        if f.kind == "pair":
            assert self._kedua is not None
            bawaan = list(f.default or [0.0, 0.0])
            kiri, p1 = formstate.coerce_number(self.kontrol.GetValue(), bawaan[0])
            kanan, p2 = formstate.coerce_number(self._kedua.GetValue(), bawaan[1])
            pesan = [p for p in (p1, p2) if p]
            self._peringatan = " ".join(pesan) if pesan else None
            return [float(kiri), float(kanan)]
        if f.kind == "number" and f.optional:
            nilai, self._peringatan = formstate.coerce_optional_number(self.kontrol.GetValue())
            return nilai
        if f.kind == "number":
            nilai, self._peringatan = formstate.coerce_number(self.kontrol.GetValue(), f.default)
            return nilai
        return str(self.kontrol.GetValue())

    @property
    def peringatan(self) -> str | None:
        """Pesan dari pembacaan terakhir, mis. angka yang tidak terbaca."""
        return self._peringatan

    # -- tampilan ----------------------------------------------------------

    def terapkan(self, tampilan: formstate.FieldView) -> None:
        """Perbarui label dan visibilitas menurut keadaan formulir saat ini."""
        self.label.SetLabel(tampilan.label)
        self.panel.Show(tampilan.visible)

    def pada_perubahan(self, handler: Any) -> None:
        """Panggil `handler` setiap kali nilainya berubah."""
        peta: dict[str, list[Any]] = {
            "bool": [wx.EVT_CHECKBOX],
            "select": [wx.EVT_CHOICE],
            "multiselect": [wx.EVT_CHECKLISTBOX],
            "int": [wx.EVT_SPINCTRL, wx.EVT_TEXT],
        }
        # Sisanya -- `text`, `number`, `pair` -- semuanya kotak teks.
        peristiwa = peta.get(self.field.kind, [wx.EVT_TEXT])
        for ev in peristiwa:
            self.kontrol.Bind(ev, handler)
            if self._kedua is not None:
                self._kedua.Bind(ev, handler)


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


__all__ = ["LEBAR_ANGKA", "LEBAR_LABEL", "KontrolField", "pilihan_aman", "teks_angka"]
