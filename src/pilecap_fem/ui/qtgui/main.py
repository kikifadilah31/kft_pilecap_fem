"""Jendela utama antarmuka desktop Qt. EKSPERIMENTAL.

Hanya merangkai: seluruh keputusan yang dapat salah secara diam-diam ada di `schema.py`,
`runopts.py`, `formstate.py`, `detect.py`, `runner.py`, dan `desktop.py` -- modul yang SAMA
dengan yang dipakai antarmuka wx, semuanya tanpa toolkit dan dapat diuji tanpa display.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from pilecap_fem import __version__
from pilecap_fem.ui import argv as argv_builder
from pilecap_fem.ui import desktop, detect, formstate, runner, runopts, schema
from pilecap_fem.ui.qtgui import fields, illustration

#: Folder kerja. Atribut modul, dibaca saat dipakai -- test menimpanya.
WORKDIR = desktop.folder_kerja()


def _monospace() -> QFont:
    return QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)


class _Jembatan(QObject):
    """Membawa callback `runner.jalankan` dari thread pekerja ke thread GUI.

    Sinyal yang dipancarkan dari thread lain ke objek milik thread GUI otomatis diantrekan --
    padanan `wx.CallAfter`, dan satu-satunya cara aman menyentuh widget dari sana.
    """

    baris = Signal(str)
    selesai = Signal(object)


class JendelaPratinjau(QWidget):
    """Pratinjau geometri di jendela sendiri yang dapat diubah ukuran."""

    def __init__(self, figure: Any) -> None:
        super().__init__()
        self.setWindowTitle("Pratinjau geometri")
        self.resize(900, 780)
        # Dipilih eksplisit: tanpa ini matplotlib mencoba PyQt6 lebih dulu bila kebetulan ada.
        os.environ.setdefault("QT_API", "pyside6")
        from matplotlib.backends.backend_qtagg import (
            FigureCanvasQTAgg,
            NavigationToolbar2QT,
        )

        kanvas = FigureCanvasQTAgg(figure)
        susun = QVBoxLayout(self)
        susun.addWidget(NavigationToolbar2QT(kanvas, self))
        susun.addWidget(kanvas, 1)
        keterangan = QLabel("Belum ada mesh maupun analisis -- ini hanya susunan geometrinya.")
        keterangan.setStyleSheet(fields.gaya_sekunder())
        susun.addWidget(keterangan)


class JendelaUtama(QMainWindow):
    """Formulir masukan, pratinjau, dan log run dalam satu jendela."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"pilecap-fem v{__version__} (Qt, eksperimental)")
        self.resize(1120, 860)

        self._kontrol: dict[str, fields.KontrolField] = {}
        self._tanda_override: dict[str, QLabel] = {}
        self._berjalan = False
        self._config_path: Path | None = None
        self._jendela_lain: list[QWidget] = []  # dijaga agar tidak dibuang pengumpul sampah

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(desktop.JEDA_SEGAR_MS)
        self._timer.timeout.connect(self._segarkan)

        self._jembatan = _Jembatan(self)
        self._jembatan.baris.connect(self._tambah_log)
        self._jembatan.selesai.connect(self._selesai)

        pusat = QWidget()
        susun = QVBoxLayout(pusat)
        susun.addLayout(self._bangun_atas())

        # Pembagi vertikal: pengguna dapat memberi formulir atau log ruang lebih.
        pembagi = QSplitter(Qt.Orientation.Vertical)
        pembagi.addWidget(self._bangun_formulir())
        pembagi.addWidget(self._bangun_bawah())
        pembagi.setStretchFactor(0, 3)
        pembagi.setStretchFactor(1, 1)
        susun.addWidget(pembagi, 1)
        self.setCentralWidget(pusat)

        self._muat_nilai(schema.default_values() | runopts.default_values())
        self._segarkan()
        self._perbarui_deteksi()
        self.statusBar().showMessage(f"Folder kerja: {WORKDIR}")

    # -- penyusunan --------------------------------------------------------

    def _bangun_atas(self) -> QVBoxLayout:
        susun = QVBoxLayout()

        judul = QLabel("pilecap-fem")
        font = judul.font()
        font.setPointSizeF(font.pointSizeF() + 5)
        font.setBold(True)
        judul.setFont(font)
        susun.addWidget(judul)

        sub = QLabel(
            "Antarmuka ini menjalankan `pilecap-run` yang sama persis, sehingga hasilnya "
            "identik dengan menjalankannya dari terminal."
        )
        sub.setStyleSheet(fields.gaya_sekunder())
        susun.addWidget(sub)

        grid = QFormLayout()
        baris = QHBoxLayout()
        self._input_dir = QLineEdit(str(WORKDIR / "input"))
        self._input_dir.textChanged.connect(self._perbarui_deteksi)
        baris.addWidget(self._input_dir, 1)
        telusuri = QPushButton("Telusuri...")
        telusuri.clicked.connect(self._pada_telusuri)
        baris.addWidget(telusuri)
        grid.addRow("Folder input", baris)

        self._status_input = QLabel("")
        grid.addRow("", self._status_input)

        baris2 = QHBoxLayout()
        self._config_dimuat = QLineEdit()
        self._config_dimuat.setPlaceholderText(
            "mis. examples/ex01_standard_4pile/pilecap_config.json"
        )
        baris2.addWidget(self._config_dimuat, 1)
        pilih = QPushButton("Pilih...")
        pilih.clicked.connect(self._pada_pilih_config)
        baris2.addWidget(pilih)
        muat = QPushButton("Muat")
        muat.clicked.connect(self._pada_muat_config)
        baris2.addWidget(muat)
        grid.addRow("Muat config", baris2)

        susun.addLayout(grid)
        return susun

    def _bangun_formulir(self) -> QWidget:
        """Seksi sebagai daftar di kiri, field seksi terpilih di kanan.

        Setara `wx.Treebook` di antarmuka wx. Daftarnya mencerminkan Bab 5 panduan, yang
        menyusun dokumentasinya persis per seksi.
        """
        wadah = QWidget()
        susun = QHBoxLayout(wadah)
        susun.setContentsMargins(0, 0, 0, 0)

        self._daftar = QListWidget()
        self._daftar.setFixedWidth(230)
        self._tumpuk = QStackedWidget()
        self._daftar.currentRowChanged.connect(self._tumpuk.setCurrentIndex)

        seksi: list[Any] = [*schema.SECTIONS, runopts.RUN_SECTION]
        for s in seksi:
            self._daftar.addItem(s.title)
            self._tumpuk.addWidget(self._bangun_halaman(s))
        self._daftar.setCurrentRow(0)

        susun.addWidget(self._daftar)
        susun.addWidget(self._tumpuk, 1)
        return wadah

    def _bangun_halaman(self, seksi: Any) -> QScrollArea:
        isi = QWidget()
        susun = QVBoxLayout(isi)

        if seksi.help:
            susun.addWidget(fields.label_bantuan(seksi.help, kecil=False))

        if getattr(seksi, "illustration", None):
            susun.addWidget(illustration.buat(seksi.illustration))

        if getattr(seksi, "override_entity", None):
            tanda = QLabel("")
            tanda.setWordWrap(True)
            tanda.setStyleSheet(fields.gaya_tingkat("peringatan"))
            tanda.hide()  # baru tampil bila ada CSV yang meng-override seksi ini
            susun.addWidget(tanda)
            self._tanda_override[seksi.override_entity] = tanda

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
        form.setVerticalSpacing(12)
        for f in seksi.fields:
            pilihan, galat = formstate.pilihan_aman(f)
            kf = fields.KontrolField(f, pilihan=pilihan)
            kf.pasang(form)
            kf.pada_perubahan(self._pada_ubah)
            if galat:
                kf.tampilkan_galat(galat)
            self._kontrol[f.key] = kf
        susun.addLayout(form)
        susun.addStretch(1)

        gulir = QScrollArea()
        gulir.setWidgetResizable(True)
        gulir.setWidget(isi)
        return gulir

    def _bangun_bawah(self) -> QWidget:
        wadah = QWidget()
        susun = QVBoxLayout(wadah)
        susun.setContentsMargins(0, 0, 0, 0)

        ket = QLabel("Perintah yang dijalankan -- dapat disalin ke terminal:")
        ket.setStyleSheet(fields.gaya_sekunder())
        susun.addWidget(ket)

        self._perintah = QLineEdit()
        self._perintah.setReadOnly(True)
        self._perintah.setFont(_monospace())
        susun.addWidget(self._perintah)

        baris = QHBoxLayout()
        self._tombol_jalan = QPushButton("Jalankan analisis")
        self._tombol_jalan.clicked.connect(self._pada_jalankan)
        baris.addWidget(self._tombol_jalan)
        pratinjau = QPushButton("Pratinjau geometri")
        pratinjau.clicked.connect(self._pada_pratinjau)
        baris.addWidget(pratinjau)
        baris.addStretch(1)
        self._hasil = QLabel("")
        baris.addWidget(self._hasil)
        susun.addLayout(baris)

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(_monospace())
        self._log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # Batas yang sama dengan antarmuka lain; Qt membuang baris tertua dengan sendirinya.
        self._log.setMaximumBlockCount(runner.MAX_LOG_LINES)
        susun.addWidget(self._log, 1)
        return wadah

    # -- nilai formulir ----------------------------------------------------

    def _nilai(self) -> dict[str, Any]:
        """Seluruh nilai formulir, termasuk opsi run."""
        return {key: kf.baca() for key, kf in self._kontrol.items()}

    def _muat_nilai(self, nilai: dict[str, Any]) -> None:
        for key, kf in self._kontrol.items():
            if key in nilai:
                kf.tulis(nilai[key])

    def _pada_ubah(self, *_args: Any) -> None:
        # Hanya menjadwalkan; lihat `desktop.JEDA_SEGAR_MS`.
        self._timer.start()

    def _segarkan(self) -> None:
        """Satu lintasan penyegaran: visibilitas, label satuan, dan pratinjau perintah.

        Tanpa graf ketergantungan, sama seperti antarmuka wx: 70 field membuat lintasan penuh
        sangat murah, dan ia menghilangkan seluruh kelas bug "dependensi terlewat".
        """
        nilai = self._nilai()
        tampilan = formstate.layout_state(nilai)
        for key, kf in self._kontrol.items():
            kf.terapkan(tampilan[key])
        self._perintah.setText(
            desktop.susun_perintah_pratinjau(nilai, self._input_dir.text(), WORKDIR)
        )

    @staticmethod
    def _nilai_skema(nilai: dict[str, Any]) -> dict[str, Any]:
        return desktop.nilai_skema(nilai)

    # -- folder input & config ---------------------------------------------

    def _pada_telusuri(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pilih folder input", str(WORKDIR))
        if folder:
            self._input_dir.setText(folder)

    def _perbarui_deteksi(self, *_args: Any) -> None:
        folder = self._input_dir.text()
        terdeteksi = detect.deteksi(folder)
        override = detect.override_terdeteksi(terdeteksi)

        status = desktop.status_folder_input(folder, terdeteksi)
        self._status_input.setText(status.isi)
        self._status_input.setStyleSheet(fields.gaya_tingkat(status.tingkat))

        for entitas, tanda in self._tanda_override.items():
            berkas = override.get(entitas)
            if berkas:
                tanda.setText(desktop.teks_override(berkas))
            tanda.setVisible(bool(berkas))

    def _pada_pilih_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Pilih pilecap_config.json", str(WORKDIR), "Config JSON (*.json)"
        )
        if path:
            self._config_dimuat.setText(path)

    def _pada_muat_config(self) -> None:
        try:
            nilai, tak_dikenal, path = desktop.muat_config(self._config_dimuat.text(), WORKDIR)
        except desktop.ConfigTakTerbaca as exc:
            self._beritahu(str(exc), "galat")
            return
        self._muat_nilai(nilai)
        self._segarkan()
        pesan = desktop.pesan_dimuat(path, tak_dikenal)
        self._beritahu(pesan.isi, pesan.tingkat)

    # -- kotak pesan (dipusatkan supaya test dapat menggantinya) --------------

    def _beritahu(self, pesan: str, tingkat: str) -> None:
        if tingkat == "galat":
            QMessageBox.critical(self, "pilecap-fem", pesan)
        elif tingkat == "peringatan":
            QMessageBox.warning(self, "pilecap-fem", pesan)
        else:
            QMessageBox.information(self, "pilecap-fem", pesan)

    def _tanya(self, pesan: str) -> bool:
        jawab = QMessageBox.question(
            self,
            "pilecap-fem",
            pesan,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return jawab == QMessageBox.StandardButton.Yes

    # -- pratinjau ---------------------------------------------------------

    def _pada_pratinjau(self) -> None:
        from pilecap_fem.validators import PilecapError

        try:
            figure = desktop.gambar_pratinjau(self._nilai(), self._input_dir.text())
        except PilecapError as exc:
            # Pesan validator sudah ditulis untuk dibaca engineer; ditampilkan apa adanya.
            self._beritahu(str(exc), "galat")
            return
        jendela = JendelaPratinjau(figure)
        self._jendela_lain.append(jendela)
        jendela.show()

    # -- menjalankan -------------------------------------------------------

    def _pada_jalankan(self) -> None:
        if self._berjalan:
            return
        nilai = self._nilai()

        peringatan = desktop.peringatan_koersi(
            (kf.field.label, kf.peringatan) for kf in self._kontrol.values()
        )
        if peringatan and not self._tanya(desktop.teks_konfirmasi_koersi(peringatan)):
            return

        try:
            config_path, cli_argv = desktop.siapkan_run(nilai, self._input_dir.text(), WORKDIR)
        except Exception as exc:
            self._beritahu(f"Config tidak dapat ditulis: {exc}", "galat")
            return
        self._perintah.setText(argv_builder.format_command(cli_argv))

        self._config_path = config_path
        self._log.clear()
        self._hasil.setText("")
        self._berjalan = True
        self._tombol_jalan.setEnabled(False)
        self.statusBar().showMessage("Menjalankan...")

        runner.jalankan(
            cli_argv,
            WORKDIR,
            pada_baris=self._jembatan.baris.emit,
            pada_selesai=self._jembatan.selesai.emit,
        )

    def _tambah_log(self, baris: str) -> None:
        self._log.appendPlainText(baris)

    def _selesai(self, hasil: runner.Hasil) -> None:
        self._berjalan = False
        self._tombol_jalan.setEnabled(True)

        label = desktop.label_hasil(hasil)
        self._hasil.setText(label.isi)
        self._hasil.setStyleSheet(fields.gaya_tingkat(label.tingkat))
        self.statusBar().showMessage(label.isi)

        pesan = desktop.pesan_hasil(hasil, self._config_path or Path("?"))
        self._beritahu(pesan.isi, pesan.tingkat)


def run_app() -> int:
    """Buka jendela dan jalankan loop peristiwa. Mengembalikan exit code."""
    app = QApplication.instance() or QApplication(sys.argv)
    jendela = JendelaUtama()
    jendela.show()
    return int(app.exec())


__all__ = ["JendelaPratinjau", "JendelaUtama", "run_app"]
