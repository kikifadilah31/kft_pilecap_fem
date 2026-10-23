"""Ilustrasi di formulir Qt: label yang mengisi dirinya sendiri.

Rasterisasinya `ui.rasterize` (PNG via Typst) -- sama dengan antarmuka wx dan identik dengan
gambar di laporan PDF. QtSvg sebenarnya merender ilustrasi ini dengan benar (DIUKUR pada
platform Windows: label `<text>` dan warna dari blok `<style>` utuh), tetapi memakai jalur
yang sama dengan wx menjaga ketiga antarmuka menampilkan gambar yang sama persis.

Kegagalan membaca ilustrasi **tidak boleh menjatuhkan formulir**: ia alat bantu, sedangkan
yang sedang dikerjakan pengguna adalah masukan analisisnya.
"""

from __future__ import annotations

import contextlib
import threading

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QLabel

from pilecap_fem.ui import rasterize
from pilecap_fem.ui.qtgui.fields import gaya_sekunder


class _Sinyal(QObject):
    """Pembawa hasil dari thread latar ke thread GUI.

    Sinyal yang dipancarkan dari thread lain ke objek milik thread GUI otomatis diantrekan
    (queued connection) -- padanan `wx.CallAfter`, dan satu-satunya cara aman menyentuh widget
    dari luar thread GUI.
    """

    selesai = Signal(str, str)


class LabelIlustrasi(QLabel):
    """Menampilkan satu ilustrasi, dirasterisasi di thread latar.

    Rasterisasi pertama di mesin yang belum pernah menjalankan Typst menghangatkan cache font
    sistem lebih dulu -- sekali, tetapi bisa beberapa detik. Membayarnya di thread GUI berarti
    jendela tampak menggantung tepat saat pertama kali dibuka.
    """

    def __init__(self, nama: str, *, lebar: int = 560) -> None:
        super().__init__("(memuat ilustrasi...)")
        self.setStyleSheet(gaya_sekunder())
        self._nama = nama
        # Dirasterisasi pada resolusi layar sesungguhnya supaya tidak kabur pada tampilan
        # yang diskalakan (mis. 150%); Qt lalu menampilkannya pada ukuran logis `lebar`.
        self._rasio = max(1.0, self.devicePixelRatioF())
        self._lebar_px = round(lebar * self._rasio)

        self._sinyal = _Sinyal(self)
        self._sinyal.selesai.connect(self._selesai)
        threading.Thread(target=self._kerjakan, name=f"ilustrasi-{nama}", daemon=True).start()

    def _kerjakan(self) -> None:
        """Thread latar: rasterisasi, lalu serahkan hasilnya ke thread GUI."""
        try:
            jalur, galat = str(rasterize.png_untuk(self._nama, lebar=self._lebar_px)), ""
        # Berkas hilang, Typst gagal, cache tidak dapat ditulis -- semuanya setara di sini.
        except Exception as exc:
            jalur, galat = "", str(exc)
        # RuntimeError: label sudah dibuang sebelum thread selesai (jendela ditutup); tidak
        # ada lagi yang perlu diberi tahu.
        with contextlib.suppress(RuntimeError):
            self._sinyal.selesai.emit(jalur, galat)

    def _selesai(self, jalur: str, galat: str) -> None:
        """Thread GUI: ganti keterangan "memuat" dengan gambarnya, atau dengan sebabnya."""
        if not jalur:
            self.setText(f"(ilustrasi {self._nama} tidak dapat dimuat: {galat})")
            return
        gambar = QPixmap(jalur)
        if gambar.isNull():
            self.setText(f"(ilustrasi {self._nama} tidak terbaca)")
            return
        gambar.setDevicePixelRatio(self._rasio)
        self.setStyleSheet("")
        self.setPixmap(gambar)


def buat(nama: str, *, lebar: int = 560) -> QLabel:
    """Label ilustrasi `nama`. Selalu mengembalikan widget, apa pun hasilnya."""
    return LabelIlustrasi(nama, lebar=lebar)


__all__ = ["LabelIlustrasi", "buat"]
