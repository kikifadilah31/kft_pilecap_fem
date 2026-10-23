"""Uji asap antarmuka desktop Qt (eksperimental). Dilewati bila PySide6 tidak terpasang.

Cermin `test_ui_wxgui.py`, dengan satu perbedaan nyata: Qt dijalankan pada platform
`offscreen`, jadi uji ini **tidak membutuhkan display** dan tidak perlu dilewati di CI.

Platform `offscreen` tidak punya font sama sekali (DIUKUR: 0 keluarga font, sedangkan platform
Windows 446). Karena itu tidak ada uji di sini yang bergantung pada ukuran teks dalam piksel.

Logika yang dapat salah secara diam-diam diuji di `test_ui_desktop.py`, tanpa toolkit apa pun;
di sini hanya perangkaiannya.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

# Harus disetel SEBELUM QApplication dibuat. `setdefault`: bila pengembang sengaja memilih
# platform lain (mis. untuk melihat jendelanya), pilihan itu dihormati.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

QtWidgets = pytest.importorskip(
    "PySide6.QtWidgets", reason="antarmuka Qt opsional: `uv sync --extra qt`"
)

from pilecap_fem.ui import formstate, runner, schema  # noqa: E402

CONTOH_EX01 = Path("examples/ex01_standard_4pile/pilecap_config.json")


@pytest.fixture(scope="module")
def app():
    """Satu `QApplication` untuk seluruh berkas; Qt tidak mengizinkan dua dalam satu proses."""
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def jendela(app, monkeypatch):
    """Jendela utama, dengan ilustrasi diganti label biasa.

    Ilustrasi memanggil Typst di thread latar; itu punya ujinya sendiri di bawah, dan
    membiarkannya di setiap uji hanya memperlambat tanpa menguji hal baru.
    """
    from pilecap_fem.ui.qtgui import illustration
    from pilecap_fem.ui.qtgui import main as qmain

    monkeypatch.setattr(illustration, "buat", lambda nama, **_kw: QtWidgets.QLabel(f"[{nama}]"))
    w = qmain.JendelaUtama()
    yield w
    w.close()
    w.deleteLater()
    app.processEvents()


def test_jendela_membangun_seluruh_field(jendela):
    assert set(jendela._kontrol) == {f.key for f in formstate.SEMUA_FIELD}


def test_jendela_punya_satu_halaman_per_seksi(jendela):
    """11 seksi skema ditambah satu untuk opsi run."""
    assert jendela._tumpuk.count() == len(schema.SECTIONS) + 1
    assert jendela._daftar.count() == jendela._tumpuk.count()


def test_mengubah_bentuk_pier_menukar_field_yang_tampil(jendela):
    k = jendela._kontrol
    k["pier.shape"].tulis("rectangular")
    jendela._segarkan()
    assert k["pier.width_x"].terlihat()
    assert not k["pier.diameter"].terlihat()

    k["pier.shape"].tulis("circular")
    jendela._segarkan()
    assert not k["pier.width_x"].terlihat()
    assert k["pier.diameter"].terlihat()


def test_mengubah_satuan_memperbarui_label(jendela):
    jendela._kontrol["units.length"].tulis("cm")
    jendela._segarkan()
    assert jendela._kontrol["pilecap.thickness"].label.text() == "Tebal [cm]"


def test_nilai_bawaan_pulang_pergi_lewat_kontrol(jendela):
    """Menulis lalu membaca kembali tidak boleh mengubah satu nilai pun.

    Inilah yang dipatahkan `wx.SpinCtrlDouble` di antarmuka wx (`digits=0`: `0.05` terbaca
    `0.0`). Qt memakai kotak teks dan koersi `formstate` yang sama, jadi sifatnya diuji sama.
    """
    nilai = schema.default_values()
    jendela._muat_nilai(nilai)
    for key, awal in nilai.items():
        balik = jendela._kontrol[key].baca()
        if jendela._kontrol[key].field.kind == "multiselect" and awal is None:
            # `None` dan `[]` sama-sama berarti "pakai seluruh pilihan"; `build_config`
            # memetakan keduanya ke hasil yang sama, sama seperti wx dan `st.multiselect`.
            assert balik == []
            continue
        assert balik == awal, f"{key}: {awal!r} -> {balik!r}"


def test_desimal_kecil_tidak_terpotong(jendela):
    """Rasio redaman 0,05 harus tetap 0,05 -- kegagalan yang pernah terjadi di wx."""
    kf = next(
        k for k in jendela._kontrol.values() if k.field.kind == "number" and not k.field.optional
    )
    kf.kontrol.setText("0.05")
    assert kf.baca() == 0.05
    assert kf.peringatan is None


def test_memuat_config_contoh_mengisi_formulir(jendela):
    jendela._config_dimuat.setText(str(CONTOH_EX01.resolve()))
    dicatat: list[tuple[str, str]] = []
    jendela._beritahu = lambda pesan, tingkat: dicatat.append((pesan, tingkat))  # type: ignore[method-assign]
    jendela._pada_muat_config()

    assert dicatat, "pemuatan harus memberi tahu hasilnya"
    asli = json.loads(CONTOH_EX01.read_text(encoding="utf-8"))
    assert jendela._kontrol["pilecap.thickness"].baca() == asli["pilecap"]["thickness"]


def test_config_dari_formulir_sama_dengan_config_contoh(jendela):
    """Membuka lalu menyimpan ulang config yang ada tidak boleh mengubah nilainya.

    Dibandingkan sebagai NILAI; normalisasi `75` -> `75.0` disengaja dan dimiliki ketiga
    antarmuka. Daftar pilihan bernilai `None` dilewati karena dropdown tidak punya keadaan
    kosong -- perilaku yang sama di wx dan Streamlit.
    """
    nilai_asli, _ = schema.values_from_config(json.loads(CONTOH_EX01.read_text(encoding="utf-8")))
    jendela._muat_nilai(nilai_asli)
    jendela._segarkan()

    dari_formulir = schema.build_config(jendela._nilai_skema(jendela._nilai()))
    pulang, tak_dikenal = schema.values_from_config(dari_formulir)
    assert not tak_dikenal

    jenis = {f.key: f for f in schema.ALL_FIELDS}
    diperiksa = 0
    for kunci, awal in nilai_asli.items():
        if awal is None and jenis[kunci].kind in {"select", "multiselect"}:
            continue
        assert pulang[kunci] == awal, f"{kunci}: {awal!r} -> {pulang[kunci]!r}"
        diperiksa += 1
    assert diperiksa > 40, f"terlalu sedikit field yang benar-benar diperiksa: {diperiksa}"


def test_tombol_jalankan_menyerahkan_argv_ke_runner(jendela, tmp_path, monkeypatch):
    """Runner di-monkeypatch: uji ini soal perangkaian, bukan soal menjalankan analisis."""
    from pilecap_fem.ui.qtgui import main as qmain

    direkam: dict[str, object] = {}

    def palsu(cli_argv, workdir, *, pada_baris, pada_selesai):
        direkam["argv"] = list(cli_argv)
        pada_baris("INFO mulai")
        pada_selesai(runner.Hasil(returncode=0, run_dir=str(tmp_path / "out")))

    dicatat: list[tuple[str, str]] = []
    monkeypatch.setattr(qmain.runner, "jalankan", palsu)
    monkeypatch.setattr(qmain, "WORKDIR", tmp_path)
    jendela._beritahu = lambda pesan, tingkat: dicatat.append((pesan, tingkat))  # type: ignore[method-assign]
    jendela._input_dir.setText(str(tmp_path / "input"))

    jendela._pada_jalankan()

    argv = direkam["argv"]
    assert isinstance(argv, list)
    assert "--config" in argv
    assert str(tmp_path / "input") in argv
    assert len(sorted((tmp_path / "ui_configs").glob("pilecap_config_*.json"))) == 1
    # Log dan pemberitahuan akhir melewati sinyal, lalu tombol kembali aktif.
    assert "INFO mulai" in jendela._log.toPlainText()
    assert dicatat and dicatat[-1][1] == "sukses"
    assert jendela._tombol_jalan.isEnabled()


def test_isian_tak_terbaca_ditanyakan_sebelum_run(jendela, tmp_path, monkeypatch):
    """Isian yang tidak terbaca diganti nilai bawaan; pengguna berhak tahu SEBELUM run."""
    from pilecap_fem.ui.qtgui import main as qmain

    dipanggil: list[str] = []
    ditanyakan: list[str] = []
    monkeypatch.setattr(qmain.runner, "jalankan", lambda *a, **k: dipanggil.append("jalan"))
    monkeypatch.setattr(qmain, "WORKDIR", tmp_path)
    jendela._tanya = lambda teks: (ditanyakan.append(teks), False)[1]  # type: ignore[method-assign]

    jendela._kontrol["pilecap.thickness"].kontrol.setText("seribu dua ratus")
    jendela._pada_jalankan()

    assert ditanyakan and "tidak terbaca" in ditanyakan[0]
    assert not dipanggil, "run harus dibatalkan bila pengguna menjawab Tidak"


def test_masukan_ditolak_mengangkat_baris_gagal(jendela, tmp_path):
    dicatat: list[tuple[str, str]] = []
    jendela._beritahu = lambda pesan, tingkat: dicatat.append((pesan, tingkat))  # type: ignore[method-assign]
    jendela._config_path = tmp_path / "c.json"

    jendela._selesai(runner.Hasil(returncode=2, lines=["WARNING x", "GAGAL: pile di luar pelat"]))

    pesan, tingkat = dicatat[-1]
    assert tingkat == "galat"
    assert pesan.startswith("Masukan ditolak:")
    assert "GAGAL: pile di luar pelat" in pesan
    assert jendela._hasil.text() == "Gagal (exit 2)"


def test_log_dibatasi_sama_dengan_antarmuka_lain(jendela):
    assert jendela._log.maximumBlockCount() == runner.MAX_LOG_LINES


def test_teks_bantuan_dirender_sebagai_markdown(jendela):
    """Pembeda dari wx: `**satu**` dirender tebal, bukan ditampilkan dengan bintangnya."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QTextDocument

    dengan_markdown = [
        kf for kf in jendela._kontrol.values() if kf.bantuan is not None and "**" in kf.field.help
    ]
    assert dengan_markdown, "skema seharusnya punya teks bantuan bermarkdown"
    for kf in dengan_markdown:
        assert kf.bantuan.textFormat() == Qt.TextFormat.MarkdownText
        assert kf.bantuan.wordWrap()
        dokumen = QTextDocument()
        dokumen.setMarkdown(kf.field.help)
        assert "**" not in dokumen.toPlainText(), f"{kf.field.key}: bintang tidak dirender"


def test_ilustrasi_termuat_dari_thread_latar(app):
    """Ilustrasi asli: dirasterisasi di thread latar, lalu tiba lewat sinyal di thread GUI."""
    from pilecap_fem.ui.qtgui import illustration

    label = illustration.LabelIlustrasi("sistem-koordinat.svg", lebar=240)
    batas = time.monotonic() + 60
    while label.pixmap().isNull() and time.monotonic() < batas:
        app.processEvents()
        time.sleep(0.02)
    assert not label.pixmap().isNull(), label.text()
    label.deleteLater()


def test_warna_keterangan_mengikuti_tema(app):
    """Teks keterangan harus terang di latar gelap dan gelap di latar terang.

    Tangkapan layar pertama antarmuka ini memperlihatkan keterangan abu-abu tetap (`#606060`)
    yang nyaris hilang karena Qt mengikuti mode gelap Windows.
    """
    from PySide6.QtGui import QColor, QPalette

    from pilecap_fem.ui.qtgui import fields

    asli = app.palette()
    try:
        gelap = QPalette()
        gelap.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
        gelap.setColor(QPalette.ColorRole.WindowText, QColor(235, 235, 235))
        app.setPalette(gelap)
        assert fields.tema_gelap()
        assert "235, 235, 235" in fields.gaya_sekunder()
        assert fields.WARNA_GELAP["galat"] in fields.gaya_tingkat("galat")

        terang = QPalette()
        terang.setColor(QPalette.ColorRole.Window, QColor(245, 245, 245))
        terang.setColor(QPalette.ColorRole.WindowText, QColor(20, 20, 20))
        app.setPalette(terang)
        assert not fields.tema_gelap()
        assert "20, 20, 20" in fields.gaya_sekunder()
        assert fields.WARNA_TERANG["galat"] in fields.gaya_tingkat("galat")
    finally:
        app.setPalette(asli)
