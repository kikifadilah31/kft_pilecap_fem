"""Jendela utama antarmuka desktop.

Hanya merangkai: seluruh keputusan yang dapat salah secara diam-diam ada di `schema.py`,
`runopts.py`, `formstate.py`, `detect.py`, `runner.py`, dan `desktop.py` -- semuanya tanpa
wx, semuanya dapat diuji tanpa display, dan semuanya dipakai juga oleh antarmuka Qt.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import wx
from wx.lib.scrolledpanel import ScrolledPanel

from pilecap_fem import __version__
from pilecap_fem.ui import argv as argv_builder
from pilecap_fem.ui import desktop, detect, formstate, runner, runopts, schema
from pilecap_fem.ui.wxgui import fields, svgview

#: Folder kerja. Atribut modul, dibaca saat dipakai -- test menimpanya.
WORKDIR = desktop.folder_kerja()

#: Lihat `desktop.JEDA_SEGAR_MS`.
JEDA_SEGAR_MS = desktop.JEDA_SEGAR_MS

#: Ikon kotak pesan per tingkat `desktop.Pesan`.
IKON = {
    "info": wx.ICON_INFORMATION,
    "sukses": wx.ICON_INFORMATION,
    "peringatan": wx.ICON_WARNING,
    "galat": wx.ICON_ERROR,
}

#: Warna teks status per tingkat.
WARNA = {
    "info": wx.Colour(96, 96, 96),
    "sukses": wx.Colour(0, 128, 0),
    "peringatan": wx.Colour(176, 96, 0),
    "galat": wx.Colour(176, 0, 0),
}

#: Abu-abu untuk teks keterangan sekunder.
ABU = wx.Colour(96, 96, 96)


class FramePratinjau(wx.Frame):
    """Pratinjau geometri di jendela sendiri yang dapat diubah ukuran.

    Bukan panel sempit di dalam formulir: denah geometri padat dan layak diberi ruang, dan
    jendela terpisah dapat dibiarkan terbuka di sebelah formulir sambil nilainya disunting.
    """

    def __init__(self, induk: wx.Window, figure: Any) -> None:
        super().__init__(induk, title="Pratinjau geometri", size=(900, 780))
        # Impor berat; hanya dibayar saat pratinjau pertama dibuka.
        from matplotlib.backends.backend_wxagg import (
            FigureCanvasWxAgg,
            NavigationToolbar2WxAgg,
        )

        panel = wx.Panel(self)
        kanvas = FigureCanvasWxAgg(panel, -1, figure)
        bilah = NavigationToolbar2WxAgg(kanvas)
        bilah.Realize()

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(bilah, 0, wx.EXPAND)
        sizer.Add(kanvas, 1, wx.EXPAND)
        keterangan = wx.StaticText(
            panel,
            label="Belum ada mesh maupun analisis -- ini hanya susunan geometrinya.",
        )
        keterangan.SetForegroundColour(ABU)
        sizer.Add(keterangan, 0, wx.ALL, 6)
        panel.SetSizer(sizer)


class MainFrame(wx.Frame):
    """Formulir masukan, pratinjau, dan log run dalam satu jendela."""

    def __init__(self) -> None:
        super().__init__(None, title=f"pilecap-fem v{__version__}", size=(1120, 860))

        self._kontrol: dict[str, fields.KontrolField] = {}
        #: Penanda "seksi ini di-override CSV", per entitas seksi. Diisi saat halaman
        #: dibangun, labelnya diperbarui tiap folder input berubah.
        self._tanda_override: dict[str, fields.TeksBantuan] = {}
        self._halaman: list[wx.Window] = []
        self._baris_log: list[str] = []
        self._berjalan = False

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._bangun_atas(panel), 0, wx.EXPAND | wx.ALL, 8)
        sizer.Add(self._bangun_formulir(panel), 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)
        sizer.Add(self._bangun_bawah(panel), 0, wx.EXPAND | wx.ALL, 8)
        panel.SetSizer(sizer)

        self._timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, lambda _e: self._segarkan(), self._timer)

        self._muat_nilai(schema.default_values() | runopts.default_values())
        self._segarkan()
        self._perbarui_deteksi()
        self.CreateStatusBar()
        self.SetStatusText(f"Folder kerja: {WORKDIR}")
        self.Centre()

    # -- penyusunan --------------------------------------------------------

    def _bangun_atas(self, induk: wx.Window) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.VERTICAL)

        judul = wx.StaticText(induk, label="pilecap-fem")
        tebal = judul.GetFont()
        tebal.SetPointSize(tebal.GetPointSize() + 5)
        tebal.SetWeight(wx.FONTWEIGHT_BOLD)
        judul.SetFont(tebal)
        sizer.Add(judul, 0)

        sub = wx.StaticText(
            induk,
            label=(
                "Antarmuka ini menjalankan `pilecap-run` yang sama persis, sehingga hasilnya "
                "identik dengan menjalankannya dari terminal."
            ),
        )
        sub.SetForegroundColour(ABU)
        sizer.Add(sub, 0, wx.BOTTOM, 6)

        # --- folder input ---
        baris = wx.BoxSizer(wx.HORIZONTAL)
        baris.Add(
            wx.StaticText(induk, label="Folder input", size=(100, -1)),
            0,
            wx.ALIGN_CENTER_VERTICAL,
        )
        self._input_dir = wx.TextCtrl(induk, value=str(WORKDIR / "input"))
        self._input_dir.Bind(wx.EVT_TEXT, lambda _e: self._perbarui_deteksi())
        baris.Add(self._input_dir, 1, wx.ALIGN_CENTER_VERTICAL)
        telusuri = wx.Button(induk, label="Telusuri...")
        telusuri.Bind(wx.EVT_BUTTON, self._pada_telusuri)
        baris.Add(telusuri, 0, wx.LEFT, 6)
        sizer.Add(baris, 0, wx.EXPAND | wx.BOTTOM, 4)

        self._status_input = wx.StaticText(induk, label="")
        sizer.Add(self._status_input, 0, wx.BOTTOM, 6)

        # --- pemuat config ---
        baris2 = wx.BoxSizer(wx.HORIZONTAL)
        baris2.Add(
            wx.StaticText(induk, label="Muat config", size=(100, -1)),
            0,
            wx.ALIGN_CENTER_VERTICAL,
        )
        self._config_dimuat = wx.TextCtrl(induk)
        self._config_dimuat.SetHint("mis. examples/ex01_standard_4pile/pilecap_config.json")
        baris2.Add(self._config_dimuat, 1, wx.ALIGN_CENTER_VERTICAL)
        pilih = wx.Button(induk, label="Pilih...")
        pilih.Bind(wx.EVT_BUTTON, self._pada_pilih_config)
        baris2.Add(pilih, 0, wx.LEFT, 6)
        muat = wx.Button(induk, label="Muat")
        muat.Bind(wx.EVT_BUTTON, self._pada_muat_config)
        baris2.Add(muat, 0, wx.LEFT, 6)
        sizer.Add(baris2, 0, wx.EXPAND)

        return sizer

    def _bangun_formulir(self, induk: wx.Window) -> wx.Window:
        """Seksi sebagai daftar di kiri, field seksi terpilih di kanan.

        60 field dalam satu kolom bergulir setinggi ribuan piksel membuat pengguna berburu.
        Pohon seksi mencerminkan Bab 5 panduan, yang menyusun dokumentasinya persis per
        seksi -- jadi pembaca panduan menemukan tempat yang sama.
        """
        self._buku = wx.Treebook(induk, style=wx.BK_LEFT)

        seksi: list[Any] = [*schema.SECTIONS, runopts.RUN_SECTION]
        for s in seksi:
            self._buku.AddPage(self._bangun_halaman(self._buku, s), s.title)
        return self._buku

    def _bangun_halaman(self, induk: wx.Window, seksi: Any) -> wx.Window:
        halaman = ScrolledPanel(induk)
        sizer = wx.BoxSizer(wx.VERTICAL)
        teks_halaman: list[fields.TeksBantuan] = []
        kontrol_halaman: list[fields.KontrolField] = []

        if seksi.help:
            bantuan = fields.TeksBantuan(halaman, seksi.help)
            teks_halaman.append(bantuan)
            sizer.Add(bantuan, 0, wx.ALL, 6)

        if getattr(seksi, "illustration", None):
            sizer.Add(svgview.buat(halaman, seksi.illustration), 0, wx.ALL, 2)

        if getattr(seksi, "override_entity", None):
            # Diisi ulang oleh `_perbarui_deteksi`; disimpan agar labelnya dapat diubah
            # tanpa membangun ulang halaman.
            tanda = fields.TeksBantuan(halaman, "")
            tanda.SetForegroundColour(wx.Colour(176, 96, 0))
            tanda.Hide()  # baru tampil bila ada CSV yang meng-override seksi ini
            teks_halaman.append(tanda)
            sizer.Add(tanda, 0, wx.ALL, 6)
            self._tanda_override[seksi.override_entity] = tanda

        for f in seksi.fields:
            pilihan, galat = formstate.pilihan_aman(f)
            kf = fields.KontrolField(halaman, f, pilihan=pilihan)
            kf.pada_perubahan(self._pada_ubah)
            self._kontrol[f.key] = kf
            kontrol_halaman.append(kf)
            sizer.Add(kf.panel, 0, wx.EXPAND)
            if galat:
                pesan = wx.StaticText(halaman, label=galat)
                pesan.SetForegroundColour(wx.Colour(176, 0, 0))
                # Spacer, bukan border: lihat `KontrolField` soal margin bawah.
                geser = wx.BoxSizer(wx.HORIZONTAL)
                geser.AddSpacer(fields.INDENT_BANTUAN)
                geser.Add(pesan, 1)
                sizer.Add(geser, 0, wx.EXPAND | wx.BOTTOM, 4)

        halaman.SetSizer(sizer)
        halaman.SetupScrolling(scroll_x=False)

        def sesuaikan(event: wx.SizeEvent) -> None:
            """Bungkus ulang teks bantuan agar tidak terpotong di sisi kanan.

            Ruang untuk scrollbar vertikal SELALU disisihkan, ada atau tidak. Mengukurnya
            hanya saat tampil membuat lebar yang dihitung bergantung pada scrollbar, yang
            kemunculannya bergantung pada tinggi isi, yang bergantung pada lebar ini --
            sebuah lingkaran yang berayun tanpa henti.
            """
            event.Skip()
            lebar = halaman.GetClientSize().width - wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
            berubah = [t.atur_lebar(lebar - 16) for t in teks_halaman]
            berubah += [kf.atur_lebar(lebar) for kf in kontrol_halaman]
            if any(berubah):
                halaman.Layout()
                halaman.FitInside()

        halaman.Bind(wx.EVT_SIZE, sesuaikan)
        self._halaman.append(halaman)
        return halaman

    def _bangun_bawah(self, induk: wx.Window) -> wx.Sizer:
        sizer = wx.BoxSizer(wx.VERTICAL)

        ket = wx.StaticText(induk, label="Perintah yang dijalankan -- dapat disalin ke terminal:")
        ket.SetForegroundColour(ABU)
        sizer.Add(ket, 0)

        self._perintah = wx.TextCtrl(induk, style=wx.TE_READONLY, size=(-1, 48))
        self._perintah.SetFont(wx.Font(wx.FontInfo(9).Family(wx.FONTFAMILY_TELETYPE)))
        sizer.Add(self._perintah, 0, wx.EXPAND | wx.BOTTOM, 6)

        baris = wx.BoxSizer(wx.HORIZONTAL)
        self._tombol_jalan = wx.Button(induk, label="Jalankan analisis")
        self._tombol_jalan.Bind(wx.EVT_BUTTON, self._pada_jalankan)
        baris.Add(self._tombol_jalan, 0)
        self._tombol_pratinjau = wx.Button(induk, label="Pratinjau geometri")
        self._tombol_pratinjau.Bind(wx.EVT_BUTTON, self._pada_pratinjau)
        baris.Add(self._tombol_pratinjau, 0, wx.LEFT, 6)
        baris.AddStretchSpacer()
        self._hasil = wx.StaticText(induk, label="")
        baris.Add(self._hasil, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(baris, 0, wx.EXPAND | wx.BOTTOM, 6)

        self._log = wx.TextCtrl(
            induk, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP, size=(-1, 170)
        )
        self._log.SetFont(wx.Font(wx.FontInfo(9).Family(wx.FONTFAMILY_TELETYPE)))
        sizer.Add(self._log, 0, wx.EXPAND)

        return sizer

    # -- nilai formulir ----------------------------------------------------

    def _nilai(self) -> dict[str, Any]:
        """Seluruh nilai formulir, termasuk opsi run."""
        return {key: kf.baca() for key, kf in self._kontrol.items()}

    def _muat_nilai(self, nilai: dict[str, Any]) -> None:
        for key, kf in self._kontrol.items():
            if key in nilai:
                kf.tulis(nilai[key])

    def _pada_ubah(self, event: wx.CommandEvent) -> None:
        # Hanya menjadwalkan; lihat `JEDA_SEGAR_MS`.
        self._timer.Start(JEDA_SEGAR_MS, oneShot=True)
        event.Skip()

    def _segarkan(self) -> None:
        """Satu lintasan penyegaran: visibilitas, label satuan, dan pratinjau perintah.

        Tanpa graf ketergantungan. 70 field membuat lintasan penuh sangat murah, dan ia
        menghilangkan seluruh kelas bug "dependensi terlewat" -- termasuk perilaku yang
        mudah terlewat bahwa memilih satuan langsung mengubah label field di bawahnya.
        """
        nilai = self._nilai()
        tampilan = formstate.layout_state(nilai)

        self.Freeze()
        try:
            for key, kf in self._kontrol.items():
                kf.terapkan(tampilan[key])
            for halaman in self._halaman:
                halaman.Layout()
                halaman.FitInside()
        finally:
            self.Thaw()

        self._perintah.SetValue(self._susun_perintah(nilai))

    def _susun_perintah(self, nilai: dict[str, Any]) -> str:
        return desktop.susun_perintah_pratinjau(nilai, self._input_dir.GetValue(), WORKDIR)

    # -- folder input & config ---------------------------------------------

    def _pada_telusuri(self, event: wx.CommandEvent) -> None:
        with wx.DirDialog(self, "Pilih folder input", str(WORKDIR)) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._input_dir.SetValue(dlg.GetPath())

    def _perbarui_deteksi(self) -> None:
        folder = self._input_dir.GetValue()
        terdeteksi = detect.deteksi(folder)
        override = detect.override_terdeteksi(terdeteksi)

        status = desktop.status_folder_input(folder, terdeteksi)
        self._status_input.SetLabel(status.isi)
        self._status_input.SetForegroundColour(WARNA[status.tingkat])

        for entitas, tanda in self._tanda_override.items():
            berkas = override.get(entitas)
            if berkas:
                tanda.ganti(desktop.teks_override(berkas))
            tanda.Show(bool(berkas))
        for halaman in self._halaman:
            halaman.Layout()
            halaman.FitInside()
        self.Layout()

    def _pada_pilih_config(self, event: wx.CommandEvent) -> None:
        with wx.FileDialog(
            self,
            "Pilih pilecap_config.json",
            str(WORKDIR),
            wildcard="Config JSON (*.json)|*.json",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        ) as dlg:
            if dlg.ShowModal() == wx.ID_OK:
                self._config_dimuat.SetValue(dlg.GetPath())

    def _pada_muat_config(self, event: wx.CommandEvent) -> None:
        try:
            nilai, tak_dikenal, path = desktop.muat_config(self._config_dimuat.GetValue(), WORKDIR)
        except desktop.ConfigTakTerbaca as exc:
            self._beritahu(str(exc), wx.ICON_ERROR)
            return
        self._muat_nilai(nilai)
        self._segarkan()
        pesan = desktop.pesan_dimuat(path, tak_dikenal)
        self._beritahu(pesan.isi, IKON[pesan.tingkat])

    def _beritahu(self, pesan: str, ikon: int) -> None:
        wx.MessageBox(pesan, "pilecap-fem", wx.OK | ikon, self)

    # -- pratinjau ---------------------------------------------------------

    def _pada_pratinjau(self, event: wx.CommandEvent) -> None:
        from pilecap_fem.validators import PilecapError

        try:
            figure = desktop.gambar_pratinjau(self._nilai(), self._input_dir.GetValue())
        except PilecapError as exc:
            # Pesan validator sudah ditulis untuk dibaca engineer; ditampilkan apa adanya.
            self._beritahu(str(exc), wx.ICON_ERROR)
            return
        FramePratinjau(self, figure).Show()

    @staticmethod
    def _nilai_skema(nilai: dict[str, Any]) -> dict[str, Any]:
        return desktop.nilai_skema(nilai)

    # -- menjalankan -------------------------------------------------------

    def _pada_jalankan(self, event: wx.CommandEvent) -> None:
        if self._berjalan:
            return
        nilai = self._nilai()

        peringatan = desktop.peringatan_koersi(
            (kf.field.label, kf.peringatan) for kf in self._kontrol.values()
        )
        if peringatan:
            jawab = wx.MessageBox(
                desktop.teks_konfirmasi_koersi(peringatan),
                "pilecap-fem",
                wx.YES_NO | wx.ICON_WARNING,
                self,
            )
            if jawab != wx.YES:
                return

        try:
            config_path, cli_argv = desktop.siapkan_run(nilai, self._input_dir.GetValue(), WORKDIR)
        except Exception as exc:
            self._beritahu(f"Config tidak dapat ditulis: {exc}", wx.ICON_ERROR)
            return
        self._perintah.SetValue(argv_builder.format_command(cli_argv))

        self._baris_log = []
        self._log.SetValue("")
        self._hasil.SetLabel("")
        self._berjalan = True
        self._tombol_jalan.Disable()
        self.SetStatusText("Menjalankan...")

        runner.jalankan(
            cli_argv,
            WORKDIR,
            # Callback datang dari thread lain; `wx.CallAfter` satu-satunya cara aman
            # menyentuh widget dari sana.
            pada_baris=lambda baris: wx.CallAfter(self._tambah_log, baris),
            pada_selesai=lambda hasil: wx.CallAfter(self._selesai, hasil, config_path),
        )

    def _tambah_log(self, baris: str) -> None:
        self._baris_log.append(baris)
        del self._baris_log[: -runner.MAX_LOG_LINES]
        self._log.AppendText(baris + "\n")

    def _selesai(self, hasil: runner.Hasil, config_path: Path) -> None:
        self._berjalan = False
        self._tombol_jalan.Enable()

        label = desktop.label_hasil(hasil)
        self._hasil.SetForegroundColour(WARNA[label.tingkat])
        self._hasil.SetLabel(label.isi)
        self.SetStatusText(label.isi)

        pesan = desktop.pesan_hasil(hasil, config_path)
        self._beritahu(pesan.isi, IKON[pesan.tingkat])


def run_app() -> int:
    """Buka jendela dan jalankan loop peristiwa. Mengembalikan exit code."""
    app = wx.App()
    MainFrame().Show()
    app.MainLoop()
    return 0


__all__ = ["JEDA_SEGAR_MS", "FramePratinjau", "MainFrame", "run_app"]
