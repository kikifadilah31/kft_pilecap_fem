"""Uji asap antarmuka desktop. Dilewati bila wxPython atau display tidak ada.

Sengaja HANYA uji asap. Seluruh logika yang dapat salah secara diam-diam diuji di
`test_ui_desktop.py`, yang tidak membutuhkan display -- sehingga berkas ini boleh dilewati di
CI tanpa menghilangkan jaminan apa pun. Yang dijaga di sini hanya bahwa perangkaiannya benar:
jendelanya terbentuk, seluruh field terbangun, dan tombol Jalankan menyerahkan argv yang
benar ke runner.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

wx = pytest.importorskip("wx", reason="antarmuka desktop opsional: `uv sync --extra gui`")

from pilecap_fem.ui import formstate, runner, schema  # noqa: E402


@pytest.fixture(scope="module")
def app():
    """Satu `wx.App` untuk seluruh berkas; dua App dalam satu proses tidak didukung wx."""
    try:
        aplikasi = wx.App()
    except Exception as exc:  # pragma: no cover -- lingkungan tanpa display
        pytest.skip(f"wx.App tidak dapat dibuat: {exc}")
    yield aplikasi


@pytest.fixture
def frame(app, monkeypatch):
    """Jendela utama, dengan ilustrasi diganti teks biasa.

    Ilustrasi memanggil Typst di thread latar; itu punya testnya sendiri di
    `test_ui_desktop.py`, dan membiarkannya berjalan di sini hanya memperlambat uji asap
    tanpa menguji apa pun yang baru.
    """
    from pilecap_fem.ui.wxgui import main as wxmain
    from pilecap_fem.ui.wxgui import svgview

    monkeypatch.setattr(
        svgview, "buat", lambda induk, nama, **_kw: wx.StaticText(induk, label=f"[{nama}]")
    )
    jendela = wxmain.MainFrame()
    yield jendela
    jendela.Destroy()
    wx.SafeYield()


def test_jendela_membangun_seluruh_field(frame):
    assert set(frame._kontrol) == {f.key for f in formstate.SEMUA_FIELD}


def test_jendela_punya_satu_halaman_per_seksi(frame):
    """11 seksi skema ditambah satu untuk opsi run."""
    assert frame._buku.GetPageCount() == len(schema.SECTIONS) + 1


def test_mengubah_bentuk_pier_menukar_field_yang_tampil(frame):
    frame._kontrol["pier.shape"].tulis("rectangular")
    frame._segarkan()
    assert frame._kontrol["pier.width_x"].panel.IsShown()
    assert not frame._kontrol["pier.diameter"].panel.IsShown()

    frame._kontrol["pier.shape"].tulis("circular")
    frame._segarkan()
    assert not frame._kontrol["pier.width_x"].panel.IsShown()
    assert frame._kontrol["pier.diameter"].panel.IsShown()


def test_mengubah_satuan_memperbarui_label(frame):
    frame._kontrol["units.length"].tulis("cm")
    frame._segarkan()
    assert frame._kontrol["pilecap.thickness"].label.GetLabel() == "Tebal [cm]"


def test_nilai_bawaan_pulang_pergi_lewat_kontrol(frame):
    """Menulis lalu membaca kembali tidak boleh mengubah satu nilai pun.

    Inilah yang dipatahkan `wx.SpinCtrlDouble`: ia melaporkan `digits=0`, sehingga `0.05`
    terbaca `0.0` -- rasio redaman yang berubah diam-diam saat config dimuat.
    """
    nilai = schema.default_values()
    for key, kontrol in frame._kontrol.items():
        if key in nilai:
            kontrol.tulis(nilai[key])

    for key, awal in nilai.items():
        balik = frame._kontrol[key].baca()
        if frame._kontrol[key].field.kind == "multiselect" and awal is None:
            # `None` dan `[]` sama-sama berarti "pakai seluruh pilihan"; `build_config`
            # memetakan keduanya ke hasil yang sama, sama seperti `st.multiselect`.
            assert balik == []
            continue
        assert balik == awal, f"{key}: {awal!r} -> {balik!r}"


def test_memuat_config_contoh_mengisi_formulir(frame, tmp_path):
    contoh = Path("examples/ex01_standard_4pile/pilecap_config.json")
    frame._config_dimuat.SetValue(str(contoh.resolve()))

    dicatat: list[tuple[str, int]] = []
    frame._beritahu = lambda pesan, ikon: dicatat.append((pesan, ikon))  # type: ignore[method-assign]
    frame._pada_muat_config(None)

    assert dicatat, "pemuatan harus memberi tahu hasilnya"
    asli = json.loads(contoh.read_text(encoding="utf-8"))
    assert frame._kontrol["pilecap.thickness"].baca() == asli["pilecap"]["thickness"]


def test_config_dari_formulir_sama_dengan_config_contoh(frame):
    """Formulir yang dimuat dari sebuah config harus menghasilkan config yang sama.

    Ini jaminan bahwa antarmuka desktop tidak dapat mengubah masukan analisis diam-diam saat
    sekadar membuka lalu menyimpan ulang berkas yang sudah ada.

    Dibandingkan sebagai NILAI, bukan sebagai teks JSON: berkas contoh menulis `"cover": 75`
    sedangkan formulir mengeluarkan `75.0`. Normalisasi itu disengaja dan dimiliki kedua
    antarmuka -- `st.number_input` pun terkunci bertipe float -- sehingga keduanya tetap
    menulis berkas yang identik satu sama lain. Yang dilarang adalah nilainya BERUBAH, dan
    itulah yang diuji di sini.
    """
    contoh = Path("examples/ex01_standard_4pile/pilecap_config.json")
    nilai_asli, _ = schema.values_from_config(json.loads(contoh.read_text(encoding="utf-8")))
    frame._muat_nilai(nilai_asli)
    frame._segarkan()

    dari_formulir = schema.build_config(frame._nilai_skema(frame._nilai()))
    pulang, tak_dikenal = schema.values_from_config(dari_formulir)
    assert not tak_dikenal

    jenis = {f.key: f for f in schema.ALL_FIELDS}
    diperiksa = 0
    for kunci, awal in nilai_asli.items():
        if awal is None and jenis[kunci].kind in {"select", "multiselect"}:
            # Daftar pilihan tidak punya keadaan "kosong". `ex01` menulis
            # `"rebar_config": null` secara eksplisit, sedangkan `build_config`
            # menghilangkan kunci itu pada cabang `rebar_mode` yang sedang aktif -- jadi
            # pulang-perginya mengembalikan nilai bawaan field. Streamlit berperilaku sama
            # persis (`st.selectbox` juga jatuh ke indeks 0), dan perbandingan berkas
            # ujung-ke-ujung menunjukkan kedua antarmuka tetap menulis config identik.
            continue
        assert pulang[kunci] == awal, f"{kunci}: {awal!r} -> {pulang[kunci]!r}"
        diperiksa += 1

    assert diperiksa > 40, f"terlalu sedikit field yang benar-benar diperiksa: {diperiksa}"


def test_tombol_jalankan_menyerahkan_argv_ke_runner(frame, tmp_path, monkeypatch):
    """Runner di-monkeypatch: uji ini soal perangkaian, bukan soal menjalankan analisis."""
    from pilecap_fem.ui.wxgui import main as wxmain

    direkam: dict[str, object] = {}

    def palsu(cli_argv, workdir, *, pada_baris, pada_selesai):
        direkam["argv"] = list(cli_argv)
        direkam["workdir"] = workdir
        pada_baris("INFO mulai")
        pada_selesai(runner.Hasil(returncode=0, run_dir=str(tmp_path / "out")))
        return None

    monkeypatch.setattr(wxmain.runner, "jalankan", palsu)
    monkeypatch.setattr(wxmain, "WORKDIR", tmp_path)
    frame._beritahu = lambda pesan, ikon: None  # type: ignore[method-assign]
    frame._input_dir.SetValue(str(tmp_path / "input"))

    frame._pada_jalankan(None)

    argv = direkam["argv"]
    assert isinstance(argv, list)
    assert "--config" in argv
    assert str(tmp_path / "input") in argv
    # Config benar-benar ditulis sebelum runner dipanggil, dan selalu berkas baru.
    ditulis = sorted((tmp_path / "ui_configs").glob("pilecap_config_*.json"))
    assert len(ditulis) == 1


def test_isian_tak_terbaca_ditanyakan_sebelum_run(frame, tmp_path, monkeypatch):
    """Isian yang tidak terbaca diganti nilai bawaan -- itu perubahan pada masukan analisis.

    Pengguna berhak tahu SEBELUM run berjalan belasan menit, bukan sesudah membaca hasil.
    """
    from pilecap_fem.ui.wxgui import main as wxmain

    dipanggil: list[str] = []
    monkeypatch.setattr(
        wxmain.runner,
        "jalankan",
        lambda *a, **k: dipanggil.append("jalan"),
    )
    monkeypatch.setattr(wxmain, "WORKDIR", tmp_path)
    monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: wx.NO)

    frame._kontrol["pilecap.thickness"].kontrol.SetValue("seribu dua ratus")
    frame._pada_jalankan(None)

    assert not dipanggil, "run harus dibatalkan bila pengguna menjawab Tidak"


def test_tinggi_baris_field_tidak_membengkak_oleh_margin(frame):
    """Satu baris field tidak boleh jauh lebih tinggi daripada isinya.

    Pernah terjadi: teks bantuan ditambahkan dengan `wx.LEFT | wx.BOTTOM` dan SATU nilai
    border, sehingga margin bawahnya ikut sebesar pergeseran kiri (~270 px). Tinggi satu
    baris terukur 330-430 px untuk isi yang hanya ~85 px, dan formulirnya tampak berongga.
    """
    for key, kf in frame._kontrol.items():
        isi = kf.kontrol.GetBestSize().height
        if kf.bantuan is not None:
            isi += kf.bantuan.GetBestSize().height
        tinggi = kf.panel.GetBestSize().height
        assert tinggi <= isi + 32, f"{key}: baris setinggi {tinggi}px untuk isi {isi}px"


def test_teks_bantuan_dibungkus_ulang_dari_teks_asli(app):
    """`Wrap` menyisipkan baris baru permanen; bungkus ulang harus mulai dari teks aslinya."""
    from pilecap_fem.ui.wxgui import fields

    teks = "Jarak antar batang yang Anda tetapkan; tool memilih diameter terkecil. " * 4
    jendela = wx.Frame(None)
    try:
        t = fields.TeksBantuan(jendela, teks)
        t.atur_lebar(600)
        tinggi_lebar = t.GetBestSize().height

        assert t.atur_lebar(300), "lebar berbeda harus dilaporkan berubah"
        assert t.GetBestSize().height > tinggi_lebar, "kolom sempit harus lebih tinggi"

        assert t.atur_lebar(600)
        assert t.GetBestSize().height == tinggi_lebar, "kembali ke lebar awal, tinggi harus sama"
        assert " ".join(t.GetLabel().split()) == " ".join(teks.split()), "teks tidak boleh berubah"
        assert not t.atur_lebar(600), "lebar yang sama tidak perlu menata ulang"
    finally:
        jendela.Destroy()
