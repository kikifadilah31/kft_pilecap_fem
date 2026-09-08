"""CLI `pilecap-manual`."""

from __future__ import annotations

from pathlib import Path

import pytest

from pilecap_fem import __version__, cli_pilecap_manual, config


def test_entry_point_menulis_typ_dan_pdf(tmp_path, capsys):
    kode = cli_pilecap_manual.entry_point(["--out", str(tmp_path / "panduan")])
    assert kode == 0
    keluaran = tmp_path / "panduan"
    assert (keluaran / config.FILE_MANUAL_SOURCE).is_file()
    assert (keluaran / config.FILE_MANUAL_REPORT).read_bytes().startswith(b"%PDF-")
    assert "OK ->" in capsys.readouterr().out


def test_typ_only_tidak_mengompilasi_pdf(tmp_path):
    """Jalur cepat untuk memeriksa sumbernya tanpa menunggu kompilasi."""
    kode = cli_pilecap_manual.entry_point(["--out", str(tmp_path), "--typ-only"])
    assert kode == 0
    assert (tmp_path / config.FILE_MANUAL_SOURCE).is_file()
    assert not (tmp_path / config.FILE_MANUAL_REPORT).exists()


def test_version_tidak_memuat_solver_maupun_schema():
    """`--version` wajib ringan.

    Impor berat ditahan di dalam `run()`; bila ia naik ke tingkat modul, `--version`
    ikut menyeret openseespy dan `pilecap-manual --version` berubah dari seketika
    menjadi beberapa detik.
    """
    import ast

    berkas = Path(cli_pilecap_manual.__file__)
    pohon = ast.parse(berkas.read_text(encoding="utf-8"))
    tingkat_modul = [
        n.module or "" for n in pohon.body if isinstance(n, ast.ImportFrom) and n.col_offset == 0
    ]
    terlarang = [m for m in tingkat_modul if "manual" in m or "ui" in m or "fem_engine" in m]
    assert not terlarang, f"impor berat di tingkat modul: {terlarang}"

    with pytest.raises(SystemExit) as exc:
        cli_pilecap_manual.build_parser().parse_args(["--version"])
    assert exc.value.code == 0


def test_bawaan_out_tidak_menimpa_folder_output_run(tmp_path, monkeypatch):
    """Panduan bukan milik satu run, jadi bawaannya tidak boleh mengarah ke `output`."""
    args = cli_pilecap_manual.build_parser().parse_args([])
    assert args.out != Path("output")


def test_panduan_menyebut_versi_yang_terpasang_di_berkas(tmp_path):
    cli_pilecap_manual.entry_point(["--out", str(tmp_path), "--typ-only"])
    teks = (tmp_path / config.FILE_MANUAL_SOURCE).read_text(encoding="utf-8")
    assert __version__ in teks
