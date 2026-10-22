"""Test antarmuka desktop yang TIDAK membutuhkan display.

Seluruh test di berkas ini berjalan tanpa wxPython maupun streamlit terpasang. Itu bukan
kebetulan melainkan syarat rancangan: yang dapat salah secara diam-diam di antarmuka desktop
-- koersi angka, visibilitas bersyarat, label satuan, pemetaan opsi run ke flag CLI --
semuanya ditaruh di modul tanpa toolkit justru supaya dapat diuji di sini.

Dua di antaranya menjaga aturan rumah yang sebelumnya hanya terdokumentasi:

* hanya `ui/wxgui/` yang boleh mengimpor `wx`;
* `ui/wxgui/` tidak boleh mengimpor engine di tingkat modul.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

from pilecap_fem import cli_pilecap_run, config
from pilecap_fem.ui import argv as argv_builder
from pilecap_fem.ui import detect, formstate, runner, runopts, schema, wx_launcher

UI_DIR = Path(schema.__file__).parent


# ---------------------------------------------------------------------------
# Opsi run sebagai deskriptor bersama
# ---------------------------------------------------------------------------


def test_setiap_opsi_run_diterima_parser_cli():
    """Penjaga utama deskriptor bersama: tiap opsi run harus dikenal CLI yang asli.

    Tanpa test ini, opsi yang kunci `dest`-nya salah ketik baru ketahuan saat run gagal di
    tangan pengguna -- setelah config ditulis dan proses anak dijalankan.
    """
    nilai = runopts.default_values()
    nilai.update(
        {
            "run.output_dir": "hasil",
            "run.theme": "dark",
            "run.contour_method": "average-nodal",
            "run.dpi": 150,
            "run.log_level": "DEBUG",
            "run.combo": "1.2D+1.6L 1.2D+1.0W",
            "run.opsvis": True,
            "run.no_rebar_plots": True,
            "run.no_envelope": True,
            "run.pdf": True,
        }
    )
    argv = argv_builder.build_argv(Path("c.json"), Path("input"), runopts.to_argv_values(nilai))
    parsed = cli_pilecap_run.build_parser().parse_args(argv)

    assert parsed.theme == "dark"
    assert parsed.contour_method == "average-nodal"
    assert parsed.dpi == 150
    assert parsed.log_level == "DEBUG"
    assert parsed.combo == ["1.2D+1.6L", "1.2D+1.0W"]
    assert parsed.opsvis and parsed.no_rebar_plots and parsed.no_envelope and parsed.pdf


def test_opsi_run_kosong_tidak_memancarkan_flag():
    """Nilai bawaan tetap dihilangkan supaya perintah yang ditampilkan pendek."""
    argv = argv_builder.build_argv(
        Path("c.json"), Path("input"), runopts.to_argv_values(runopts.default_values())
    )
    assert "--theme" not in argv
    assert "--dpi" not in argv
    assert "--combo" not in argv


def test_combo_kosong_menjadi_none_bukan_daftar_kosong():
    """`--combo` tanpa argumen ditolak argparse; kosong harus berarti "tidak diberikan"."""
    nilai = runopts.default_values() | {"run.combo": "   "}
    assert runopts.to_argv_values(nilai)["combo"] is None


def test_opsi_run_tidak_memancarkan_flag_terlarang():
    nilai = runopts.default_values() | {"run.opsvis": True}
    argv = argv_builder.build_argv(Path("c.json"), Path("input"), runopts.to_argv_values(nilai))
    for flag in argv_builder.FORBIDDEN_FLAGS:
        assert flag not in argv
    assert "--opsvis" in argv, "flag lain tetap harus lewat"


def test_setiap_opsi_run_punya_bantuan():
    """Prosa bantuan pindah ke sini dari `app.py`; kehilangan satu pun berarti regresi."""
    tanpa = [f.key for f in runopts.RUN_FIELDS if not (f.help or "").strip()]
    assert not tanpa, f"opsi run tanpa teks bantuan: {tanpa}"


# ---------------------------------------------------------------------------
# Keadaan formulir
# ---------------------------------------------------------------------------


def test_layout_state_mencakup_seluruh_field():
    nilai = schema.default_values() | runopts.default_values()
    tampilan = formstate.layout_state(nilai)
    assert set(tampilan) == {f.key for f in formstate.SEMUA_FIELD}


def test_layout_state_menyembunyikan_field_bersyarat():
    """Kedua cabang `pier.shape` diuji, bukan hanya yang bawaan."""
    nilai = schema.default_values() | runopts.default_values()

    nilai["pier.shape"] = "rectangular"
    t = formstate.layout_state(nilai)
    assert t["pier.width_x"].visible
    assert not t["pier.diameter"].visible

    nilai["pier.shape"] = "circular"
    t = formstate.layout_state(nilai)
    assert not t["pier.width_x"].visible
    assert t["pier.diameter"].visible


def test_setiap_field_bersyarat_dapat_tampil_dan_dapat_tersembunyi():
    """Field bersyarat yang tidak pernah dapat tampil adalah field yang mati diam-diam.

    Dicoba dengan benar-benar menyapu setiap pilihan dari setiap field `select`/`bool`,
    bukan dengan mengandaikan ada pengendali di seksi yang sama. Sapuan satu field pada satu
    waktu sudah cukup: seluruh `visible_when` di skema ini bergantung pada satu kunci saja.
    """
    dasar = schema.default_values() | runopts.default_values()
    bersyarat = [f for f in formstate.SEMUA_FIELD if f.visible_when is not None]
    assert bersyarat, "skema seharusnya punya field bersyarat"

    # Setiap keadaan yang dapat dicapai dengan mengubah SATU field pengendali.
    keadaan = [dasar]
    for pengendali in formstate.SEMUA_FIELD:
        if pengendali.kind == "bool":
            pilihan: tuple[object, ...] = (True, False)
        elif pengendali.kind == "select":
            try:
                pilihan = tuple(pengendali.options())
            except Exception:  # sumber pilihan di luar paket ini
                continue
        else:
            continue
        for opsi in pilihan:
            keadaan.append(dasar | {pengendali.key: opsi})

    for f in bersyarat:
        terlihat = {bool(f.visible_when(n)) for n in keadaan}  # type: ignore[misc]
        assert True in terlihat, f"{f.key} tidak pernah dapat tampil"
        assert False in terlihat, f"{f.key} tidak pernah dapat tersembunyi"


def test_layout_state_memperbarui_label_satuan():
    nilai = schema.default_values() | runopts.default_values()

    nilai["units.length"] = "mm"
    assert formstate.layout_state(nilai)["pilecap.thickness"].label == "Tebal [mm]"

    nilai["units.length"] = "cm"
    assert formstate.layout_state(nilai)["pilecap.thickness"].label == "Tebal [cm]"


def test_label_satuan_jatuh_ke_bawaan_config():
    """Satuan yang belum dipilih tidak boleh membuat label kehilangan satuannya."""
    labels = formstate.unit_labels({})
    assert labels["length"] == config.DEFAULT_INPUT_UNITS["length"]


# ---------------------------------------------------------------------------
# Koersi angka -- bagian yang paling mudah salah secara diam-diam
# ---------------------------------------------------------------------------


def test_number_opsional_kosong_menjadi_none():
    assert formstate.coerce_optional_number("") == (None, None)
    assert formstate.coerce_optional_number("   ") == (None, None)


def test_number_opsional_tidak_terbaca_jadi_none_dengan_peringatan():
    nilai, pesan = formstate.coerce_optional_number("dua puluh")
    assert nilai is None
    assert pesan and "bukan angka" in pesan


def test_number_wajib_kosong_jatuh_ke_bawaan_dengan_peringatan():
    nilai, pesan = formstate.coerce_number("", 1200.0)
    assert nilai == 1200.0
    assert pesan and "kosong" in pesan


def test_number_wajib_selalu_float_bukan_int():
    """Penjaga kesetaraan dua frontend, dan ia MENANGKAP regresi yang pernah terjadi.

    `st.number_input` terkunci bertipe float sejak render pertama, sehingga config yang
    ditulis Streamlit memuat `75.0`. Antarmuka desktop yang mengembalikan `int` membuat
    kedua antarmuka menulis config berbeda dari masukan yang sama persis -- persis yang
    dilarang. Diuji di sini karena perbandingan berkas ujung-ke-ujung terlalu mahal untuk
    dijalankan di tiap commit, sedangkan sifat yang dijaganya sesempit satu baris.
    """
    for teks in ("75", "1200", "0"):
        nilai, pesan = formstate.coerce_number(teks, 0.0)
        assert pesan is None
        assert isinstance(nilai, float), f"{teks!r} -> {type(nilai).__name__}"


def test_number_wajib_membaca_desimal_apa_adanya():
    """Rasio redaman 0,05 harus tetap 0,05 -- bukan 0."""
    assert formstate.coerce_number("0.05", 0.0) == (0.05, None)
    assert formstate.coerce_number("27.5", 0.0) == (27.5, None)


# ---------------------------------------------------------------------------
# Deteksi input
# ---------------------------------------------------------------------------


def test_deteksi_folder_tidak_ada_mengembalikan_kosong(tmp_path):
    """Folder yang belum ada adalah keadaan normal saat mengetik, bukan galat."""
    assert detect.deteksi(tmp_path / "belum-ada") == {}


def test_deteksi_menemukan_reaksi_pile(tmp_path):
    (tmp_path / "pile_reactions.csv").write_text("pile,Fz\n1,100\n", encoding="utf-8")
    terdeteksi = detect.deteksi(tmp_path)
    assert terdeteksi.get("reactions") == "pile_reactions.csv"
    assert detect.override_terdeteksi(terdeteksi) == {}


def test_override_terdeteksi_memetakan_ke_entitas_seksi():
    peta = detect.override_terdeteksi({"pile_coords": "pile_coords.csv", "reactions": "r.csv"})
    assert peta == {"pile": "pile_coords.csv"}


def test_entitas_override_cocok_dengan_skema():
    """Peta override harus menunjuk `Section.override_entity` yang benar-benar ada."""
    entitas_skema = {s.override_entity for s in schema.SECTIONS if s.override_entity}
    assert set(detect.OVERRIDE_ENTITY.values()) <= entitas_skema


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def test_perintah_anak_memanggil_modul_cli():
    perintah = runner.perintah(["--config", "c.json"])
    assert perintah[1:3] == ["-m", "pilecap_fem.cli_pilecap_run"]
    assert perintah[-2:] == ["--config", "c.json"]


def test_ringkas_kegagalan_mengangkat_baris_gagal():
    """Penyebab sebenarnya tidak boleh terkubur di bawah belasan baris WARNING."""
    lines = [
        "WARNING geometri di-override",
        "GAGAL: pile di luar pelat",
        "WARNING sisa",
    ]
    assert runner.ringkas_kegagalan(lines) == ["GAGAL: pile di luar pelat", "WARNING sisa"]


def test_ringkas_kegagalan_tanpa_baris_gagal():
    assert runner.ringkas_kegagalan(["WARNING a", "INFO b"]) is None


def test_derau_tqdm_disaring():
    assert runner.PROGRESS_NOISE.search("  45%|####      | 9/20 [00:01<00:01, 8.3it/s]")
    assert not runner.PROGRESS_NOISE.search("INFO membangun mesh")


# ---------------------------------------------------------------------------
# Aturan impor -- sebelumnya hanya terdokumentasi, kini dijaga
# ---------------------------------------------------------------------------


def _impor_tingkat_modul(path: Path) -> set[str]:
    """Nama paket yang diimpor di TINGKAT MODUL saja.

    Impor di dalam fungsi sengaja diabaikan: itu justru pola yang dipakai paket ini untuk
    menunda dependency berat, dan melarangnya akan melarang hal yang benar.
    """
    pohon = ast.parse(path.read_text(encoding="utf-8"))
    nama: set[str] = set()
    for simpul in pohon.body:
        if isinstance(simpul, ast.Import):
            nama.update(a.name.split(".")[0] for a in simpul.names)
        elif isinstance(simpul, ast.ImportFrom) and simpul.module and simpul.level == 0:
            nama.add(simpul.module.split(".")[0])
    return nama


def _modul_ui() -> list[Path]:
    return sorted(p for p in UI_DIR.glob("*.py") if p.name != "__init__.py")


def test_hanya_wxgui_yang_mengimpor_wx():
    """Aturan rumah: modul logika harus dapat diuji tanpa display sama sekali."""
    pelanggar = [p.name for p in _modul_ui() if "wx" in _impor_tingkat_modul(p)]
    assert not pelanggar, f"mengimpor wx di luar ui/wxgui/: {pelanggar}"


def test_modul_logika_tidak_mengimpor_streamlit():
    """Aturan yang sama untuk streamlit, kini ditegakkan dan bukan hanya dicatat."""
    pelanggar = [
        p.name for p in _modul_ui() if p.name != "app.py" and "streamlit" in _impor_tingkat_modul(p)
    ]
    assert not pelanggar, f"mengimpor streamlit di luar app.py: {pelanggar}"


def test_wxgui_tidak_mengimpor_engine_di_tingkat_modul():
    """UI tidak pernah menjalankan engine di dalam prosesnya sendiri.

    OpenSeesPy dan gmsh menyimpan state global proses, dan jendela desktop berumur panjang
    persis seperti server. Mengimpornya di tingkat modul adalah langkah pertama menuju
    memanggilnya di sana.
    """
    terlarang = {"openseespy", "gmsh", "opsvis"}
    wxgui = UI_DIR / "wxgui"
    pelanggar = {
        p.name: sorted(_impor_tingkat_modul(p) & terlarang)
        for p in sorted(wxgui.glob("*.py"))
        if _impor_tingkat_modul(p) & terlarang
    }
    assert not pelanggar, f"engine diimpor di tingkat modul: {pelanggar}"


def test_rasterize_tidak_mengimpor_toolkit():
    """Rasterisasi harus dapat diuji tanpa display; cache yang salah adalah bug diam-diam."""
    nama = _impor_tingkat_modul(UI_DIR / "rasterize.py")
    assert "wx" not in nama
    assert "streamlit" not in nama


# ---------------------------------------------------------------------------
# Peluncur
# ---------------------------------------------------------------------------


def test_wx_absen_memberi_petunjuk_bukan_traceback(monkeypatch, capsys):
    monkeypatch.setattr(wx_launcher, "wx_available", lambda: False)
    kode = wx_launcher.launch([])
    keluaran = capsys.readouterr().out

    assert kode == 1
    assert "uv sync --extra gui" in keluaran
    assert "pilecap-ui" in keluaran, "antarmuka peramban tetap harus ditawarkan"


def test_banner_menyebut_folder_kerja_yang_benar_benar_dipakai(monkeypatch, capsys, tmp_path):
    """Banner yang menyebut folder lain dari yang dipakai lebih buruk daripada tanpa banner.

    Pernah terjadi: `launch()` menghormati `PILECAP_UI_CWD` yang sudah disetel, tetapi
    mencetak `os.getcwd()` -- sehingga ia melaporkan folder repo padahal hasil analisis
    mendarat di tempat lain.

    Jendelanya diganti modul tiruan di `sys.modules`, bukan di-monkeypatch pada modul
    aslinya: mengimpor `wxgui.main` akan menarik `wx`, dan berkas test ini harus tetap
    berjalan pada lingkungan tanpa wxPython terpasang.
    """
    import types

    palsu = types.ModuleType("pilecap_fem.ui.wxgui.main")
    palsu.run_app = lambda: 0  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pilecap_fem.ui.wxgui.main", palsu)
    monkeypatch.setenv(wx_launcher.CWD_ENV, str(tmp_path))
    monkeypatch.setattr(wx_launcher, "wx_available", lambda: True)

    assert wx_launcher.launch([]) == 0
    keluaran = capsys.readouterr().out

    assert str(tmp_path) in keluaran, "banner tidak menyebut folder kerja yang dipakai"


def test_peluncur_desktop_memakai_folder_kerja_yang_sama():
    """Kedua antarmuka harus menaruh hasil di tempat yang sama persis."""
    from pilecap_fem.ui import launcher

    assert wx_launcher.CWD_ENV == launcher.CWD_ENV


# ---------------------------------------------------------------------------
# Rasterisasi ilustrasi
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_ilustrasi_dirasterisasi_dan_di_cache():
    """Ilustrasi harus benar-benar menjadi PNG, dan tidak dirasterisasi dua kali.

    Ditandai `slow` karena memanggil Typst. `wx.svg` sempat dicoba lebih dulu dan DIUKUR
    gagal: nanosvg tidak merender `<text>` dan tidak membaca blok `<style>` berkelas,
    sehingga hasilnya tiga kepala panah tanpa satu pun dari 18 label. Gambar tanpa label
    bukan versi sederhana dari gambarnya -- ia gambar yang lain.
    """
    from pilecap_fem.ui import rasterize

    nama = "sistem-koordinat.svg"
    pertama = rasterize.png_untuk(nama, lebar=240)
    assert pertama.is_file()
    assert pertama.stat().st_size > 0

    kedua = rasterize.png_untuk(nama, lebar=240)
    assert kedua == pertama, "cache harus mengembalikan berkas yang sama"

    lain = rasterize.png_untuk(nama, lebar=300)
    assert lain != pertama, "lebar berbeda harus berkas berbeda"


def test_ilustrasi_tidak_ada_memunculkan_filenotfound():
    from pilecap_fem.ui import rasterize

    with pytest.raises(FileNotFoundError):
        rasterize.png_untuk("tidak-ada-sama-sekali.svg")


def test_setiap_ilustrasi_seksi_ada_di_paket():
    """Seksi yang menunjuk ilustrasi yang tidak terpasang akan gagal di tangan pengguna."""
    hilang = [
        s.illustration
        for s in schema.SECTIONS
        if s.illustration and not (config.illustrations_dir() / s.illustration).is_file()
    ]
    assert not hilang, f"ilustrasi tidak ada di paket: {hilang}"
