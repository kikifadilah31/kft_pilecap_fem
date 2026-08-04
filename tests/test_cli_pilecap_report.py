"""Test end-to-end CLI `pilecap-report` dan `pilecap-run` (PRD Bagian 6.3, 6.4, 9.1)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from pilecap_fem import (
    cli_pilecap_analyze,
    cli_pilecap_report,
    cli_pilecap_run,
    config,
    mesh_model,
)
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.validators import InputError

pytestmark = pytest.mark.slow

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _analyze(directory: Path, output_root: Path, *extra: str) -> Path:
    args = cli_pilecap_analyze.build_parser().parse_args(
        [
            "--config",
            str(directory / "pilecap_config.json"),
            "--input-dir",
            str(directory),
            "--output-dir",
            str(output_root),
            "--dpi",
            "60",
            *extra,
        ]
    )
    return cli_pilecap_analyze.run(args, "pilecap-analyze (test)")


def _report(run_dir: Path, *extra: str) -> Path:
    args = cli_pilecap_report.build_parser().parse_args(
        ["--result-dir", str(run_dir), "--dpi", "60", *extra]
    )
    return cli_pilecap_report.run(args, "pilecap-report (test)")


@pytest.fixture(scope="module")
def reported(tmp_path_factory):
    """Satu run analyze + report dipakai bersama beberapa test."""
    workdir = tmp_path_factory.mktemp("report")
    target = workdir / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, workdir / "output")
    _report(run_dir)
    return run_dir


# ---------------------------------------------------------------------------
# Struktur keluaran PRD Bagian 9.1
# ---------------------------------------------------------------------------


def test_seluruh_berkas_model_terbentuk(reported: Path):
    model_dir = reported / config.MODEL_SUBDIR
    for name in (
        "mesh_summary.md",
        config.FILE_MESH_PLAN,
        config.FILE_MODEL_OPSVIS,
        config.FILE_BOUNDARY_CHECK,
        config.FILE_GEOMETRY_JSON,
        "nodes.csv",
        "elements.csv",
    ):
        assert (model_dir / name).is_file(), f"00_Model/{name} tidak dibuat"


def test_seluruh_berkas_kombinasi_terbentuk(reported: Path):
    for combo_dir in reported.glob("Combo_*"):
        for name in (
            config.FILE_CALC_SHEET,
            "element_resultants.csv",
            "strip_moments_x.csv",
            "strip_moments_y.csv",
            "shear_checks.csv",
            "reactions.csv",
            "equilibrium_check.json",
            config.FILE_NODE_DISPLACEMENTS,
            config.FILE_TRACEABILITY,
            config.FILE_DEFORMED_OPSVIS,
            config.FILE_CONTOUR_DEFLECTION,
            *(name for name, _, _ in config.CONTOUR_FIELDS.values()),
        ):
            path = combo_dir / name
            assert path.is_file(), f"{combo_dir.name}/{name} tidak dibuat"
            assert path.stat().st_size > 0


def test_folder_envelope_lengkap(reported: Path):
    envelope_dir = reported / config.ENVELOPE_SUBDIR
    assert (envelope_dir / "envelope_values.csv").is_file()
    assert (envelope_dir / "envelope_summary.md").is_file()
    plots = list(envelope_dir.glob("envelope_*.png"))
    assert len(plots) == 2 * len(config.CONTOUR_FIELDS)


def test_summary_terbentuk(reported: Path):
    assert (reported / config.FILE_SUMMARY).is_file()


# ---------------------------------------------------------------------------
# Isi laporan -- yang WAJIB muncul (PRD Bagian 1.3 poin 5 & 6)
# ---------------------------------------------------------------------------


def test_summary_memuat_known_limitations_dan_disclaimer(reported: Path):
    text = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    assert "strut-and-tie" in text  # keterbatasan #1
    assert "jepit sempurna" in text  # keterbatasan #2
    assert "ALAT BANTU" in text
    assert "engineer yang" in text
    assert "NOT_EVALUATED" in text


def test_summary_melaporkan_rasio_deep_tanpa_vonis(reported: Path):
    text = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    assert "TIDAK DINILAI" in text
    assert "belum dikonfirmasi" in text


def test_summary_memuat_governing_combo(reported: Path):
    text = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    assert "governing_combo" in text
    assert "1.2D+1.6L" in text or "1.2D+1.0W" in text


def test_calc_sheet_memuat_sepuluh_bagian(reported: Path):
    text = (reported / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).read_text(encoding="utf-8")
    for heading in (
        "## 1. INPUT YANG DIPAKAI",
        "### 1a. RESOLUSI SUMBER GEOMETRI",
        "## 2. MODEL FEM",
        "## 3. PEMBEBANAN",
        "## 4. CEK KESEIMBANGAN (VC-0)",
        "## 5. HASIL PER ELEMEN",
        "## 6. MOMEN DESAIN PER LAJUR",
        "## 7. GESER",
        "## 8. ASUMSI & KETERBATASAN",
        "## 9. PERNYATAAN TANGGUNG JAWAB",
        "## 10. PROVENANCE",
    ):
        assert heading in text, f"calc sheet kehilangan bagian: {heading}"


def test_calc_sheet_rantai_telusur_dapat_dihitung_ulang(reported: Path):
    """Angka di calc sheet harus benar-benar menghasilkan m_xx yang dilaporkan."""
    trace = json.loads(
        (reported / "Combo_1_2D_1_6L" / config.FILE_TRACEABILITY).read_text(encoding="utf-8")
    )
    mean = np.array(trace["gauss_mean"])
    factor = trace["sign_factors"]["moment"]
    m11, m22, m12 = (factor * mean[i] for i in (3, 4, 5))
    theta = np.radians(trace["theta_deg"])
    c, s = np.cos(theta), np.sin(theta)
    assert m11 * c * c + m22 * s * s - 2 * m12 * s * c == pytest.approx(
        trace["global"]["m_xx"], rel=1e-9
    )

    text = (reported / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).read_text(encoding="utf-8")
    assert f"tag {trace['element_tag']}" in text
    assert "GP1" in text and "GP4" in text


def test_calc_sheet_menandai_kapasitas_tidak_dihitung(reported: Path):
    text = (reported / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).read_text(encoding="utf-8")
    assert "KAPASITAS TIDAK DIHITUNG" in text
    assert "demand" in text.lower()


def test_shear_checks_seluruhnya_not_evaluated(reported: Path):
    import csv

    with open(reported / "Combo_1_2D_1_6L" / "shear_checks.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(r["kapasitas"] == "NOT_EVALUATED" for r in rows)
    assert any(r["jenis"] == "punching" for r in rows)


def test_envelope_csv_memuat_governing_per_lokasi(reported: Path):
    import csv

    with open(
        reported / config.ENVELOPE_SUBDIR / "envelope_values.csv", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert "m_xx_max_governing_combo" in rows[0]
    assert all(r["m_xx_max_governing_combo"] for r in rows)


def test_envelope_cocok_dengan_maksimum_antar_kombinasi(reported: Path):
    """Envelope harus benar-benar = ekstrem dari CSV per kombinasi."""
    import csv

    per_combo = []
    for combo_dir in sorted(reported.glob("Combo_*")):
        with open(combo_dir / "element_resultants.csv", encoding="utf-8") as handle:
            per_combo.append([float(r["m_x [kNm/m]"]) for r in csv.DictReader(handle)])
    expected = np.max(np.vstack(per_combo), axis=0)

    with open(
        reported / config.ENVELOPE_SUBDIR / "envelope_values.csv", encoding="utf-8"
    ) as handle:
        actual = [float(r["m_xx_max [kNm/m]"]) for r in csv.DictReader(handle)]

    assert np.allclose(actual, expected, atol=1e-4)


def test_envelope_summary_memperingatkan_bukan_untuk_cek_statika(reported: Path):
    text = (reported / config.ENVELOPE_SUBDIR / "envelope_summary.md").read_text(encoding="utf-8")
    assert "BUKAN kondisi keseimbangan tunggal" in text
    assert "tidak boleh" in text


# ---------------------------------------------------------------------------
# Round-trip CSV
# ---------------------------------------------------------------------------


def test_mesh_round_trip_dari_csv_identik(reported: Path):
    """`pilecap-report` membaca mesh dari CSV -- hasilnya harus identik dengan aslinya."""
    model_dir = reported / config.MODEL_SUBDIR
    mesh = mesh_model.from_csv(model_dir / "nodes.csv", model_dir / "elements.csv")
    manifest = json.loads((reported / "run_manifest.json").read_text(encoding="utf-8"))

    stats = manifest["model_stats"]
    assert mesh.n_nodes == stats["n_nodes"]
    assert mesh.n_elements == stats["n_elements"]
    assert set(mesh.group_names) == set(stats["group_element_counts"])
    assert mesh.group_element_counts() == stats["group_element_counts"]
    assert float(mesh.elem_area.sum()) == pytest.approx(
        sum(stats["group_area_occ_m2"].values()), rel=1e-3
    )


def test_geometry_json_round_trip(reported: Path):
    path = reported / config.MODEL_SUBDIR / config.FILE_GEOMETRY_JSON
    geom = GeometryModel.from_json_dict(json.loads(path.read_text(encoding="utf-8")))
    kembali = GeometryModel.from_json_dict(geom.to_json_dict())

    assert kembali.pilecap_area == pytest.approx(geom.pilecap_area)
    assert kembali.thickness == pytest.approx(geom.thickness)
    assert [p.pile_id for p in kembali.piles] == [p.pile_id for p in geom.piles]
    assert [p.pier_id for p in kembali.piers] == [p.pier_id for p in geom.piers]
    assert kembali.resolution.pilecap.source == geom.resolution.pilecap.source


def test_report_dapat_dijalankan_ulang_tanpa_analisis_ulang(reported: Path):
    """Mengganti jumlah lajur tidak boleh menuntut analisis FEM diulang."""
    _report(reported, "--strips-x", "3", "--strips-y", "3")
    import csv

    with open(reported / "Combo_1_2D_1_6L" / "strip_moments_x.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    # 3 lajur x 2 sisi muka pier x 1 pier
    assert len(rows) == 6


# ---------------------------------------------------------------------------
# Jalur gagal
# ---------------------------------------------------------------------------


def test_wood_armer_gagal_dengan_pesan_sumber_primer(reported: Path):
    """PRD Bagian 7.2(6): aturan koreksi wajib dari Wood (1968), bukan dari ingatan."""
    with pytest.raises(NotImplementedError, match="sumber primer"):
        _report(reported, "--wood-armer")


def test_entry_point_wood_armer_mengembalikan_kode_4(reported: Path, capsys):
    code = cli_pilecap_report.entry_point(
        ["--result-dir", str(reported), "--wood-armer", "--dpi", "60"]
    )
    assert code == 4
    assert "BELUM TERSEDIA" in capsys.readouterr().err


def test_no_envelope_melewati_folder_envelope(tmp_path: Path):
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, tmp_path / "output", "--combo", "1.2D+1.6L")
    _report(run_dir, "--no-envelope")
    assert not (run_dir / config.ENVELOPE_SUBDIR).exists()
    assert (run_dir / config.FILE_SUMMARY).is_file()


def test_run_gagal_tidak_dapat_dilaporkan(tmp_path: Path):
    """Laporan tidak boleh dibuat dari run yang statusnya FAILED."""
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    with pytest.raises(Exception, match="VC-0 GAGAL"):
        _analyze(target, tmp_path / "output", "--equilibrium-rtol", "1e-30")

    run_dir = next((tmp_path / "output").iterdir())
    with pytest.raises(InputError, match="bukan 'OK'"):
        _report(run_dir)


def test_geometry_json_hilang_raise(reported: Path, tmp_path: Path):
    salinan = tmp_path / "salinan"
    shutil.copytree(reported, salinan)
    (salinan / config.MODEL_SUBDIR / config.FILE_GEOMETRY_JSON).unlink()
    with pytest.raises(InputError, match=r"geometry.json"):
        _report(salinan)


def test_traceability_hilang_raise(reported: Path, tmp_path: Path):
    """Calc sheet tidak boleh menyajikan rantai telusur yang terpotong diam-diam."""
    salinan = tmp_path / "salinan2"
    shutil.copytree(reported, salinan)
    (salinan / "Combo_1_2D_1_6L" / config.FILE_TRACEABILITY).unlink()
    with pytest.raises(InputError, match="terpotong"):
        _report(salinan)


def test_no_save_raw_membuat_laporan_menolak(tmp_path: Path):
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, tmp_path / "output", "--no-save-raw", "--combo", "1.2D+1.6L")
    with pytest.raises(InputError, match="no-save-raw"):
        _report(run_dir)


def test_latest_run_memilih_yang_terbaru(tmp_path: Path):
    root = tmp_path / "output"
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    first = _analyze(target, root, "--combo", "1.2D+1.6L")
    second = _analyze(target, root, "--combo", "1.2D+1.6L")
    assert cli_pilecap_report.latest_run(root) == second
    assert first != second


def test_latest_run_tanpa_run_raise(tmp_path: Path):
    (tmp_path / "kosong").mkdir()
    with pytest.raises(InputError, match="Tidak ada run"):
        cli_pilecap_report.latest_run(tmp_path / "kosong")


# ---------------------------------------------------------------------------
# pilecap-run (PRD Bagian 6.4)
# ---------------------------------------------------------------------------


def test_pilecap_run_end_to_end(tmp_path: Path):
    """Satu perintah menghasilkan struktur penuh, dalam SATU folder run."""
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    args = cli_pilecap_run.build_parser().parse_args(
        [
            "--config",
            str(target / "pilecap_config.json"),
            "--input-dir",
            str(target),
            "--output-dir",
            str(tmp_path / "output"),
            "--dpi",
            "60",
            "--combo",
            "1.2D+1.6L",
        ]
    )
    run_dir = cli_pilecap_run.run(args, "pilecap-run (test)")

    assert (run_dir / config.FILE_SUMMARY).is_file()
    assert (run_dir / config.MODEL_SUBDIR / config.FILE_BOUNDARY_CHECK).is_file()
    assert (run_dir / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).is_file()
    assert (run_dir / "Combo_1_2D_1_6L" / "contour_mx.png").is_file()
    # Hanya SATU folder run: analyze dan report berbagi folder yang sama.
    assert len(list((tmp_path / "output").iterdir())) == 1


def test_pilecap_run_meneruskan_argumen_laporan(tmp_path: Path):
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    args = cli_pilecap_run.build_parser().parse_args(
        [
            "--config",
            str(target / "pilecap_config.json"),
            "--input-dir",
            str(target),
            "--output-dir",
            str(tmp_path / "output"),
            "--dpi",
            "60",
            "--combo",
            "1.2D+1.6L",
            "--no-envelope",
            "--strips-x",
            "2",
        ]
    )
    run_dir = cli_pilecap_run.run(args, "pilecap-run (test)")
    assert not (run_dir / config.ENVELOPE_SUBDIR).exists()
