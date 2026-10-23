"""`Field` menjadi widget Qt, beserta pembacaan nilainya kembali.

Satu fungsi per arah (`tulis`/`baca`), dan koersi teks ke angka SELURUHNYA lewat
`ui.formstate` -- sama persis dengan `wxgui/fields.py`. Aturan konversi yang tersebar adalah
cara paling mudah membuat dua antarmuka menghasilkan config yang berbeda dari masukan yang
sama.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from pilecap_fem.ui import formstate
from pilecap_fem.ui.schema import Field

#: Lebar kotak isian angka. Seragam supaya kolomnya rata dari seksi ke seksi.
LEBAR_ANGKA = 140

#: Warna status per tingkat `desktop.Pesan`, untuk latar terang dan latar gelap.
#:
#: Dua set, bukan satu: Qt mengikuti mode gelap Windows, dan warna yang dipilih untuk latar
#: terang (`#b00000`, `#008000`) nyaris tak terbaca di latar gelap -- DIAMATI pada tangkapan
#: layar pertama antarmuka ini.
WARNA_TERANG = {"sukses": "#008000", "peringatan": "#b06000", "galat": "#b00000"}
WARNA_GELAP = {"sukses": "#6fcf6f", "peringatan": "#e8a84a", "galat": "#ff7070"}


def _palet() -> QPalette:
    app = QApplication.instance()
    return app.palette() if isinstance(app, QApplication) else QPalette()


def tema_gelap() -> bool:
    """True bila latar jendela gelap (mode gelap sistem diikuti Qt)."""
    return _palet().color(QPalette.ColorRole.Window).lightness() < 128


def gaya_sekunder() -> str:
    """Teks keterangan: warna teks jendela yang diredupkan.

    Diturunkan dari palet, bukan abu-abu tetap: abu-abu yang terbaca di latar putih hampir
    menghilang di latar gelap, dan sebaliknya.
    """
    c = _palet().color(QPalette.ColorRole.WindowText)
    return f"color: rgba({c.red()}, {c.green()}, {c.blue()}, 170);"


def gaya_tingkat(tingkat: str) -> str:
    """Gaya teks untuk satu tingkat `desktop.Pesan`; `info` memakai warna sekunder."""
    warna = (WARNA_GELAP if tema_gelap() else WARNA_TERANG).get(tingkat)
    return f"color: {warna};" if warna else gaya_sekunder()


def label_bantuan(teks: str, *, kecil: bool = True) -> QLabel:
    """Label keterangan berformat markdown yang membungkus sendiri.

    Teks bantuan di `schema.py` ditulis dalam markdown untuk Streamlit (`**satu**`,
    `` `kode` ``). `Qt.MarkdownText` merendernya seperti di Streamlit, alih-alih menampilkan
    tanda bintangnya mentah seperti di antarmuka wx.
    """
    label = QLabel(teks)
    label.setTextFormat(Qt.TextFormat.MarkdownText)
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    label.setStyleSheet(gaya_sekunder())
    if kecil:
        font = label.font()
        font.setPointSizeF(max(7.0, font.pointSizeF() - 1))
        label.setFont(font)
    return label


class KontrolField:
    """Satu baris formulir: label di kolom kiri, kontrol + teks bantuan di kolom kanan.

    Membungkus widget Qt-nya alih-alih mewarisinya, karena satu `Field` dapat memerlukan DUA
    kontrol (`pair`) dan barisnya juga memuat teks bantuan yang ikut disembunyikan.
    """

    def __init__(self, f: Field, *, pilihan: tuple[Any, ...]) -> None:
        self.field = f
        self._pilihan = pilihan
        self._peringatan: str | None = None
        self._form: QFormLayout | None = None

        self.label = QLabel(f.label)
        # Disejajarkan dengan teks di DALAM kotak isian, bukan dengan tepi atasnya.
        self.label.setContentsMargins(0, 4, 0, 0)

        self.wadah = QWidget()
        susun = QVBoxLayout(self.wadah)
        susun.setContentsMargins(0, 0, 0, 0)
        susun.setSpacing(2)

        baris = QHBoxLayout()
        baris.setContentsMargins(0, 0, 0, 0)
        self._kedua: Any = None
        # `Any`: jenis kontrolnya memang berbeda per `kind`.
        self.kontrol: Any = self._buat_kontrol(baris)
        susun.addLayout(baris)

        self.bantuan: QLabel | None = None
        if f.help:
            self.bantuan = label_bantuan(f.help)
            susun.addWidget(self.bantuan)
        self._susun = susun

    # -- pembuatan ---------------------------------------------------------

    def _buat_kontrol(self, baris: QHBoxLayout) -> Any:
        f = self.field
        if f.kind == "bool":
            k: Any = QCheckBox()
        elif f.kind == "select":
            k = QComboBox()
            k.addItems([str(o) for o in self._pilihan])
        elif f.kind == "multiselect":
            k = QListWidget()
            for o in self._pilihan:
                item = QListWidgetItem(str(o))
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Unchecked)
                k.addItem(item)
            k.setFixedHeight(112)
        elif f.kind == "int":
            k = QSpinBox()
            k.setRange(
                int(f.min_value) if f.min_value is not None else 0,
                int(f.max_value) if f.max_value is not None else 1_000_000,
            )
            if f.step:
                # `run.dpi` berentang 50..600; menaikkannya satu per satu membuat kontrolnya
                # praktis tidak terpakai.
                k.setSingleStep(int(f.step))
            k.setFixedWidth(LEBAR_ANGKA)
        elif f.kind == "pair":
            k = QLineEdit()
            k.setFixedWidth(LEBAR_ANGKA)
            self._kedua = QLineEdit()
            self._kedua.setFixedWidth(LEBAR_ANGKA)
        else:
            # `text`, dan SELURUH field angka -- wajib maupun opsional.
            #
            # Angka memakai kotak teks tanpa `QDoubleValidator`: validator itu mengikuti
            # locale, dan pada locale Indonesia desimalnya koma -- `0.05` akan ditolak. Koersi
            # dilakukan `formstate`, sama persis dengan antarmuka wx.
            k = QLineEdit()
            if f.kind == "number":
                k.setFixedWidth(LEBAR_ANGKA)

        baris.addWidget(k)
        if self._kedua is not None:
            baris.addWidget(self._kedua)
        if f.kind in {"int", "number", "pair", "bool"}:
            baris.addStretch(1)
        return k

    def pasang(self, form: QFormLayout) -> None:
        """Tambahkan baris ini ke `form`; visibilitasnya kemudian diatur lewat form itu."""
        form.addRow(self.label, self.wadah)
        self._form = form

    def tampilkan_galat(self, teks: str) -> None:
        """Pesan merah di bawah kontrol, mis. daftar pilihan yang gagal dibaca."""
        pesan = QLabel(teks)
        pesan.setWordWrap(True)
        pesan.setStyleSheet(gaya_tingkat("galat"))
        self._susun.addWidget(pesan)

    # -- nilai -------------------------------------------------------------

    def tulis(self, nilai: Any) -> None:
        """Isi kontrol dari sebuah nilai formulir."""
        f = self.field
        k = self.kontrol
        if f.kind == "bool":
            k.setChecked(bool(nilai))
        elif f.kind == "select":
            daftar = [str(o) for o in self._pilihan]
            k.setCurrentIndex(daftar.index(str(nilai)) if str(nilai) in daftar else 0)
        elif f.kind == "multiselect":
            terpilih = {str(x) for x in (nilai or ())}
            for i in range(k.count()):
                item = k.item(i)
                item.setCheckState(
                    Qt.CheckState.Checked if item.text() in terpilih else Qt.CheckState.Unchecked
                )
        elif f.kind == "int":
            k.setValue(int(nilai) if nilai is not None else 0)
        elif f.kind == "pair":
            pasangan = list(nilai or [0.0, 0.0])
            k.setText(formstate.teks_angka(pasangan[0]))
            self._kedua.setText(formstate.teks_angka(pasangan[1]))
        elif f.kind == "number":
            k.setText(formstate.teks_angka(nilai))
        else:
            k.setText("" if nilai is None else str(nilai))

    def baca(self) -> Any:
        """Nilai formulir dari kontrol. Menyetel `peringatan` bila masukannya tak terbaca."""
        f = self.field
        k = self.kontrol
        self._peringatan = None
        if f.kind == "bool":
            return bool(k.isChecked())
        if f.kind == "select":
            i = k.currentIndex()
            return self._pilihan[i] if 0 <= i < len(self._pilihan) else f.default
        if f.kind == "multiselect":
            return [
                self._pilihan[i]
                for i in range(k.count())
                if k.item(i).checkState() == Qt.CheckState.Checked
            ]
        if f.kind == "int":
            return int(k.value())
        if f.kind == "pair":
            bawaan = list(f.default or [0.0, 0.0])
            kiri, p1 = formstate.coerce_number(k.text(), bawaan[0])
            kanan, p2 = formstate.coerce_number(self._kedua.text(), bawaan[1])
            pesan = [p for p in (p1, p2) if p]
            self._peringatan = " ".join(pesan) if pesan else None
            return [float(kiri), float(kanan)]
        if f.kind == "number" and f.optional:
            nilai, self._peringatan = formstate.coerce_optional_number(k.text())
            return nilai
        if f.kind == "number":
            nilai, self._peringatan = formstate.coerce_number(k.text(), f.default)
            return nilai
        return str(k.text())

    @property
    def peringatan(self) -> str | None:
        """Pesan dari pembacaan terakhir, mis. angka yang tidak terbaca."""
        return self._peringatan

    # -- tampilan ----------------------------------------------------------

    def terapkan(self, tampilan: formstate.FieldView) -> None:
        """Perbarui label dan visibilitas menurut keadaan formulir saat ini."""
        self.label.setText(tampilan.label)
        if self._form is not None:
            self._form.setRowVisible(self.wadah, tampilan.visible)

    def terlihat(self) -> bool:
        """Apakah baris ini sedang ditampilkan menurut formulirnya (tanpa syarat jendela tampil)."""
        return not self.wadah.isHidden()

    def pada_perubahan(self, handler: Callable[..., None]) -> None:
        """Panggil `handler` setiap kali nilainya berubah."""
        f = self.field
        k = self.kontrol
        if f.kind == "bool":
            k.toggled.connect(handler)
        elif f.kind == "select":
            k.currentIndexChanged.connect(handler)
        elif f.kind == "multiselect":
            k.itemChanged.connect(handler)
        elif f.kind == "int":
            k.valueChanged.connect(handler)
        else:
            k.textChanged.connect(handler)
            if self._kedua is not None:
                self._kedua.textChanged.connect(handler)


__all__ = [
    "LEBAR_ANGKA",
    "WARNA_GELAP",
    "WARNA_TERANG",
    "KontrolField",
    "gaya_sekunder",
    "gaya_tingkat",
    "label_bantuan",
    "tema_gelap",
]
