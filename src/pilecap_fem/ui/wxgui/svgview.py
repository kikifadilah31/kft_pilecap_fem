"""Ilustrasi di formulir desktop: panel yang mengisi dirinya sendiri.

Rasterisasinya ada di `ui.rasterize` (tanpa wx, dapat diuji tanpa display); di sini hanya
urusan menampilkan dan tidak membekukan jendela.

Kegagalan membaca ilustrasi **tidak boleh menjatuhkan formulir**: ia alat bantu, sedangkan
yang sedang dikerjakan pengguna adalah masukan analisisnya. Perilaku ini sengaja sama dengan
halaman Streamlit, yang menurunkannya menjadi satu baris keterangan.
"""

from __future__ import annotations

import threading

import wx

from pilecap_fem.ui import rasterize


class PanelIlustrasi(wx.Panel):
    """Menampilkan satu ilustrasi, dirasterisasi di thread latar.

    Rasterisasi pertama di mesin yang belum pernah menjalankan Typst harus menghangatkan
    cache font sistem lebih dulu -- sekali, tetapi bisa beberapa detik. Membayarnya di thread
    GUI berarti jendela tampak menggantung tepat saat pertama kali dibuka, yaitu saat
    pengguna paling mungkin menyimpulkan alatnya rusak.
    """

    def __init__(self, induk: wx.Window, nama: str, *, lebar: int = 560) -> None:
        super().__init__(induk)
        self._nama = nama
        self._lebar = lebar
        self._hidup = True

        self._sizer = wx.BoxSizer(wx.VERTICAL)
        self._isi: wx.Window = self._keterangan("(memuat ilustrasi...)")
        self._sizer.Add(self._isi, 0, wx.ALL, 4)
        self.SetSizer(self._sizer)

        # Panel dapat dibuang sebelum thread selesai -- mis. pengguna menutup jendela saat
        # ilustrasi masih dirender. Menyentuh widget yang sudah mati menjatuhkan prosesnya.
        self.Bind(wx.EVT_WINDOW_DESTROY, self._pada_hancur)

        threading.Thread(target=self._kerjakan, name=f"ilustrasi-{nama}", daemon=True).start()

    # -- internal ----------------------------------------------------------

    def _pada_hancur(self, event: wx.WindowDestroyEvent) -> None:
        if event.GetEventObject() is self:
            self._hidup = False
        event.Skip()

    def _keterangan(self, teks: str) -> wx.StaticText:
        label = wx.StaticText(self, label=teks)
        label.SetForegroundColour(wx.Colour(128, 128, 128))
        return label

    def _kerjakan(self) -> None:
        """Thread latar: rasterisasi, lalu serahkan hasilnya ke thread GUI."""
        try:
            jalur = rasterize.png_untuk(self._nama, lebar=self._lebar)
        # Berkas hilang, Typst gagal, cache tidak dapat ditulis -- semuanya setara di sini.
        except Exception as exc:
            wx.CallAfter(self._selesai, None, str(exc))
            return
        wx.CallAfter(self._selesai, str(jalur), None)

    def _selesai(self, jalur: str | None, galat: str | None) -> None:
        """Thread GUI: ganti keterangan "memuat" dengan gambarnya, atau dengan sebabnya."""
        if not self._hidup:
            return
        if jalur is None:
            baru: wx.Window = self._keterangan(
                f"(ilustrasi {self._nama} tidak dapat dimuat: {galat})"
            )
        else:
            gambar = wx.Image(jalur, wx.BITMAP_TYPE_PNG)
            if not gambar.IsOk():
                baru = self._keterangan(f"(ilustrasi {self._nama} tidak terbaca)")
            else:
                baru = wx.StaticBitmap(self, bitmap=wx.Bitmap(gambar))

        self.Freeze()
        try:
            self._sizer.Detach(self._isi)
            self._isi.Destroy()
            self._isi = baru
            self._sizer.Add(baru, 0, wx.ALL, 4)
            self._sizer.Layout()
        finally:
            self.Thaw()
        # Ilustrasi jauh lebih tinggi daripada keterangan satu baris yang digantikannya,
        # jadi panel induk yang bergulir perlu menghitung ulang tingginya.
        induk = self.GetParent()
        if induk is not None:
            induk.Layout()
            if hasattr(induk, "FitInside"):
                induk.FitInside()


def buat(induk: wx.Window, nama: str, *, lebar: int = 560) -> wx.Window:
    """Panel ilustrasi `nama`. Selalu mengembalikan sebuah window, apa pun hasilnya.

    Pemanggilnya karena itu tidak perlu bercabang -- yang berarti tidak ada jalur kode
    "tanpa ilustrasi" yang dapat lupa diuji.
    """
    return PanelIlustrasi(induk, nama, lebar=lebar)


__all__ = ["PanelIlustrasi", "buat"]
