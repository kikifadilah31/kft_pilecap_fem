"""Test `pilecap-ui` (PRD Bagian 1.3 -- antarmuka tidak boleh menyimpang dari CLI).

Seluruh test di berkas ini berjalan **tanpa streamlit terpasang**: hanya `schema`, `argv`,
dan `launcher` yang diimpor, dan ketiganya sengaja bebas streamlit. Dengan begitu bagian
UI yang dapat salah secara diam-diam tetap terjaga pada lingkungan yang hanya memasang
paket inti.

Dua test di sini menutup satu kelas bug secara permanen:

* config hasil formulir dijalankan melalui `io_utils.load_config` + seluruh validator;
* setiap argv yang dipancarkan diberikan ke `cli_pilecap_run.build_parser()` yang asli.

Keduanya berarti formulir tidak dapat menghasilkan masukan yang ditolak engine, dan tidak
dapat memancarkan flag yang tidak dikenal CLI.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from pilecap_fem import cli_pilecap_run, config, io_utils, validators
from pilecap_fem.ui import argv as argv_builder
from pilecap_fem.ui import launcher, schema


def _filled(**override: object) -> dict:
    """Nilai formulir dengan dua field wajib yang sengaja tidak berbawaan sah."""
    values = schema.default_values()
    values["material.E_source"] = "uji"
    values["design.fy_source"] = "uji"
    values.update(override)
    return values


# ---------------------------------------------------------------------------
# Config hasil formulir harus diterima engine
# ---------------------------------------------------------------------------


def _validate_all(path: Path, *, sources: dict[str, bool] | None = None) -> dict:
    loaded = io_utils.load_config(path)
    cfg = loaded.si
    present = sources or {"pilecap": False, "pile": False, "pier": False}
    validators.validate_config_geometry_params(cfg, present)
    validators.validate_config_mesh(cfg)
    validators.validate_material(cfg)
    validators.validate_design(cfg)
    return cfg


def test_config_bawaan_lolos_seluruh_validator(tmp_path: Path):
    path = schema.write_config(schema.build_config(_filled()), tmp_path)
    cfg = _validate_all(path)

    # Sekaligus membuktikan konversi satuan berjalan: formulir menulis mm/MPa.
    assert cfg["pilecap"]["thickness"] == pytest.approx(1.2)
    assert cfg["design"]["fy"] == pytest.approx(420e6)


@pytest.mark.parametrize("mode", validators.REBAR_MODES)
def test_kedua_mode_tulangan_menghasilkan_config_sah(tmp_path: Path, mode: str):
    path = schema.write_config(
        schema.build_config(_filled(**{"design.rebar_mode": mode})), tmp_path
    )
    cfg = _validate_all(path)
    design = cfg["design"]

    if mode == "spacing_fixed":
        assert design["rebar_spacing"] == pytest.approx(0.150)
        assert "rebar_config" not in design
    else:
        assert design["rebar_config"] == "2D25"
        assert "rebar_spacing" not in design


@pytest.mark.parametrize("shape", ["rectangular", "circular"])
def test_kedua_bentuk_pier_menghasilkan_config_sah(tmp_path: Path, shape: str):
    path = schema.write_config(schema.build_config(_filled(**{"pier.shape": shape})), tmp_path)
    cfg = _validate_all(path)

    if shape == "rectangular":
        assert "diameter" not in cfg["pier"]
    else:
        assert "width_x" not in cfg["pier"]


def test_mode_graded_menulis_ukuran_lokal(tmp_path: Path):
    values = _filled(**{"mesh.size_mode": "graded", "mesh.size_local_pile": 60.0})
    path = schema.write_config(schema.build_config(values), tmp_path)
    cfg = _validate_all(path)
    assert cfg["mesh"]["size_local_pile"] == pytest.approx(0.060)


def test_field_tersembunyi_DIHILANGKAN_bukan_ditulis_null():
    """Kunci bernilai `null` tidak setara dengan kunci yang tidak ada.

    `fem_engine.AnalysisOptions.from_config` memakai `int(analysis.get("n_layers", 10))`.
    `dict.get` mengembalikan `None` yang ADA alih-alih bawaannya, sehingga config
    ber-`"n_layers": null` meledak sebagai `int(None)`. Contoh bawaan pun menghilangkan
    kunci yang tidak berlaku (ex02 tanpa `pier.width_x`), bukan menulisnya null.
    """
    cfg = schema.build_config(_filled())  # section = PlateFiber -> n_layers tidak berlaku
    assert "n_layers" not in cfg["analysis"]

    berlaku = schema.build_config(_filled(**{"analysis.section": "LayeredShell"}))
    assert berlaku["analysis"]["n_layers"] == 10


def test_field_opsional_yang_kosong_tetap_ditulis_null():
    """`null` di sini bermakna "pakai bawaan, dan itu keputusan sadar" -- seperti contoh."""
    cfg = schema.build_config(_filled())
    assert cfg["design"]["phi_flexure"] is None
    assert cfg["design"]["as_min_surface_zone"] is None
    assert cfg["design"]["stirrup_select_diameters"] is None


def test_sumber_wajib_kosong_tetap_ditolak_validator(tmp_path: Path):
    """Formulir tidak boleh menyelundupkan bawaan untuk field yang menuntut sumber."""
    values = schema.default_values()  # E_source & fy_source sengaja kosong
    path = schema.write_config(schema.build_config(values), tmp_path)
    with pytest.raises(validators.InputError, match="E_source"):
        _validate_all(path)


# ---------------------------------------------------------------------------
# Argv harus dikenal CLI yang asli
# ---------------------------------------------------------------------------


def test_argv_bawaan_diterima_parser_cli():
    argv = argv_builder.build_argv(Path("c.json"), Path("input"), {})
    parsed = cli_pilecap_run.build_parser().parse_args(argv)

    assert parsed.config == Path("c.json")
    assert parsed.input_dir == Path("input")
    assert parsed.theme == config.DEFAULT_THEME


def test_argv_penuh_diterima_parser_cli():
    argv = argv_builder.build_argv(
        Path("c.json"),
        Path("input"),
        {
            "output_dir": "hasil",
            "theme": "dark",
            "contour_method": "average-nodal",
            "dpi": 150,
            "log_level": "DEBUG",
            "combo": ["1.2D+1.6L", "1.2D+1.0W"],
            "equilibrium_rtol": 1e-4,
            "reactions": "r.csv",
            "no_custom": True,
            "export_msh": True,
            "opsvis": True,
            "no_save_raw": True,
            "no_rebar_plots": True,
            "no_envelope": True,
        },
    )
    parsed = cli_pilecap_run.build_parser().parse_args(argv)

    assert parsed.theme == "dark"
    assert parsed.contour_method == "average-nodal"
    assert parsed.combo == ["1.2D+1.6L", "1.2D+1.0W"]
    assert parsed.opsvis and parsed.no_envelope and parsed.export_msh


def test_nilai_bawaan_dihilangkan_dari_perintah():
    """Perintah yang ditampilkan harus tetap pendek supaya dapat dibaca dan disalin."""
    argv = argv_builder.build_argv(
        Path("c.json"),
        Path("input"),
        {"theme": config.DEFAULT_THEME, "dpi": config.OUTPUT_DPI, "output_dir": "output"},
    )
    assert "--theme" not in argv
    assert "--dpi" not in argv
    assert "--output-dir" not in argv


def test_flag_terlarang_tidak_pernah_dipancarkan():
    """`--preview` membuka jendela matplotlib; `--wood-armer` dijamin gagal (exit 4)."""
    argv = argv_builder.build_argv(
        Path("c.json"),
        Path("input"),
        dict.fromkeys(["preview", "wood_armer", "opsvis"], True),
    )
    for flag in argv_builder.FORBIDDEN_FLAGS:
        assert flag not in argv
    assert "--opsvis" in argv, "flag lain tetap harus lewat"


def test_format_command_mengutip_path_berspasi():
    """Perintah yang ditampilkan harus dapat disalin apa adanya ke terminal.

    Separator path tidak dikunci di sini -- pada Windows `Path` menghasilkan `\\`, dan
    yang diuji adalah pengutipannya, bukan bentuk pathnya.
    """
    argv = argv_builder.build_argv(Path("a b/c.json"), Path("in put"), {})
    command = argv_builder.format_command(argv)

    assert command.startswith("pilecap-run ")
    assert "'in put'" in command
    assert str(Path("a b/c.json")) in command
    # Setiap argumen berspasi harus terkutip, bukan telanjang.
    assert " a b" not in command.replace("'", "@").replace('"', "@")


# ---------------------------------------------------------------------------
# Pilihan formulir tidak boleh basi terhadap engine
# ---------------------------------------------------------------------------


def _choices(key: str) -> tuple:
    return next(f for f in schema.ALL_FIELDS if f.key == key).options()


def test_pilihan_enum_diambil_dari_sumbernya():
    assert _choices("design.rebar_mode") == validators.REBAR_MODES
    assert _choices("units.length") == tuple(config.LENGTH_TO_SI)
    assert _choices("units.force") == tuple(config.FORCE_TO_SI)
    assert _choices("units.stress") == tuple(config.STRESS_TO_SI)
    assert _choices("mesh.algorithm") == tuple(sorted(config.GMSH_VALID_ALGORITHMS))
    assert _choices("design.moment_at") == ("pier_face", "peak", "both")


def test_pilihan_elemen_shell_cocok_dengan_fem_engine():
    from pilecap_fem import fem_engine

    assert _choices("analysis.shell_element") == tuple(fem_engine.SUPPORTED_SHELL_ELEMENTS)
    assert _choices("analysis.section") == tuple(fem_engine.SUPPORTED_SECTIONS)


def test_pilihan_kode_tulangan_cocok_dengan_shell_kit():
    from shell_kit import rebar as sk_rebar

    assert _choices("design.rebar_config") == tuple(sk_rebar.get_available_config_codes())


def test_setiap_field_memetakan_ke_blok_config_yang_dikenal():
    dikenal = {
        "project",
        "units",
        "pilecap",
        "pile",
        "pier",
        "material",
        "mesh",
        "analysis",
        "design",
    }
    assert {f.block for f in schema.ALL_FIELDS} <= dikenal


# ---------------------------------------------------------------------------
# Penulisan config tidak boleh mencemari folder input
# ---------------------------------------------------------------------------


def test_config_ditulis_ke_subfolder_agar_autodetect_tetap_bekerja(tmp_path: Path):
    """`io_utils.autodetect` RAISE bila ada lebih dari satu `*config*.json` di folder.

    Menumpuk config bertimestamp langsung di folder input akan merusak `pilecap-run`
    tanpa `--config` bagi siapa pun yang menjalankannya kemudian dari CLI.
    """
    (tmp_path / "pile_reactions.csv").write_text("combo,pile_id,Pz\nA,P1,1\n", encoding="utf-8")

    for _ in range(3):
        schema.write_config(schema.build_config(_filled()), tmp_path)

    assert len(list((tmp_path / schema.CONFIG_SUBDIR).glob("*.json"))) == 3
    # Folder input sendiri tetap bersih -> auto-detect config tidak menjadi ambigu.
    assert io_utils.autodetect(tmp_path, "config", required=False) is None


def test_write_config_tidak_pernah_menimpa(tmp_path: Path):
    now = datetime(2026, 8, 8, 21, 0, 0)
    a = schema.write_config(schema.build_config(_filled()), tmp_path, now=now)
    b = schema.write_config(schema.build_config(_filled()), tmp_path, now=now)

    assert a != b
    assert a.exists() and b.exists()


def test_config_yang_ditulis_adalah_json_yang_dapat_dibaca_manusia(tmp_path: Path):
    path = schema.write_config(schema.build_config(_filled()), tmp_path)
    text = path.read_text(encoding="utf-8")

    assert text.endswith("\n")
    assert json.loads(text)["units"]["length"] == "mm"


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------


def test_streamlit_absen_memberi_petunjuk_bukan_traceback(monkeypatch, capsys):
    monkeypatch.setattr(launcher, "streamlit_available", lambda: False)

    assert launcher.launch() == 1
    keluaran = capsys.readouterr().out
    assert "uv sync --extra ui" in keluaran
    assert "OPSIONAL" in keluaran


def test_launcher_mengikat_hanya_ke_localhost(monkeypatch):
    """Formulir memuat data proyek; ia tidak boleh tersaji ke jaringan lokal."""
    direkam: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        direkam["cmd"] = cmd

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(launcher, "streamlit_available", lambda: True)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)

    assert launcher.launch() == 0
    assert "--server.address=localhost" in direkam["cmd"]
    assert direkam["cmd"][1:4] == ["-m", "streamlit", "run"]


def test_launcher_meneruskan_folder_kerja_lewat_environment(monkeypatch):
    diteruskan: dict[str, dict] = {}

    def fake_run(cmd, **kwargs):
        diteruskan["env"] = kwargs["env"]

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(launcher, "streamlit_available", lambda: True)
    monkeypatch.setattr(launcher.subprocess, "run", fake_run)
    launcher.launch()

    assert launcher.CWD_ENV in diteruskan["env"]
