"""Test end-to-end CLI `pilecap-analyze` (PRD Bagian 6.2 & 15.2)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from pilecap_fem import cli_pilecap_analyze
from pilecap_fem.validators import AnalysisError, InputError

pytestmark = pytest.mark.slow


def run_cli(directory: Path, output_root: Path, *extra: str) -> Path:
    args = cli_pilecap_analyze.build_parser().parse_args(
        [
            "--config",
            str(directory / "pilecap_config.json"),
            "--input-dir",
            str(directory),
            "--output-dir",
            str(output_root),
            "--dpi",
            "80",
            *extra,
        ]
    )
    return cli_pilecap_analyze.run(args, "pilecap-analyze (test)")


@pytest.fixture(scope="module")
def ex01_run(tmp_path_factory, request):
    """Satu run ex01 dipakai bersama beberapa test agar tidak mengulang analisis."""
    import shutil

    source = Path(__file__).resolve().parents[1] / "examples" / "ex01_standard_4pile"
    workdir = tmp_path_factory.mktemp("analyze")
    target = workdir / "ex01"
    shutil.copytree(source, target)
    return run_cli(target, workdir / "output")


# ---------------------------------------------------------------------------
# Struktur output
# ---------------------------------------------------------------------------


def test_membuat_folder_per_kombinasi(ex01_run: Path):
    combos = sorted(p.name for p in ex01_run.iterdir() if p.name.startswith("Combo_"))
    assert combos == ["Combo_1_2D_1_0W", "Combo_1_2D_1_6L"]


def test_setiap_kombinasi_punya_artefak_lengkap(ex01_run: Path):
    for combo_dir in ex01_run.glob("Combo_*"):
        for name in ("element_resultants.csv", "reactions.csv", "equilibrium_check.json"):
            assert (combo_dir / name).is_file(), f"{combo_dir.name}/{name} tidak dibuat"


def test_artefak_model_tetap_ditulis(ex01_run: Path):
    model_dir = ex01_run / "00_Model"
    for name in ("mesh_summary.md", "mesh_plan.png", "nodes.csv", "elements.csv"):
        assert (model_dir / name).is_file()


# ---------------------------------------------------------------------------
# VC-0 pada setiap run produksi (PRD Bagian 1.3 poin 3)
# ---------------------------------------------------------------------------


def test_equilibrium_check_json_lulus_di_setiap_kombinasi(ex01_run: Path):
    for combo_dir in ex01_run.glob("Combo_*"):
        payload = json.loads((combo_dir / "equilibrium_check.json").read_text(encoding="utf-8"))
        assert payload["status"] == "PASS"
        assert payload["force_status"] == "PASS"
        assert payload["moment_status"] == "PASS"
        assert payload["force_residual_rel"] < 1e-9
        assert payload["reference_point_m"] == [0.0, 0.0]


def test_jejak_beban_per_pile_tercatat_dan_persis(ex01_run: Path):
    """Tabel Bagian 3 calc sheet: Sigma(p x A_e) harus PERSIS sama dengan P_z."""
    payload = json.loads(
        (ex01_run / "Combo_1_2D_1_6L" / "equilibrium_check.json").read_text(encoding="utf-8")
    )
    assert len(payload["pile_loads"]) == 4
    for row in payload["pile_loads"]:
        assert row["applied_total_N"] == pytest.approx(row["Pz_N"], rel=1e-12)
        assert abs(row["discrepancy_N"]) < 1e-6
        assert row["n_elements"] > 0
        assert row["pressure_Pa"] == pytest.approx(row["Pz_N"] / row["A_disk_mesh_m2"])


def test_manifest_mencatat_vc0_per_kombinasi(ex01_run: Path):
    manifest = json.loads((ex01_run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "OK"
    assert manifest["combos_analyzed"] == ["1.2D+1.6L", "1.2D+1.0W"]
    assert manifest["checks"]["equilibrium_VC0[1.2D+1.6L]"] == "PASS"
    assert manifest["checks"]["equilibrium_VC0[1.2D+1.0W]"] == "PASS"
    assert manifest["checks"]["capacity_checks"] == "NOT_EVALUATED"


def test_manifest_mencatat_pemetaan_slug_kombinasi(ex01_run: Path):
    """PRD Bagian 9.2: slug bersifat lossy, jadi pemetaannya wajib dicatat."""
    manifest = json.loads((ex01_run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["combo_slug_map"]["1.2D+1.6L"] == "1_2D_1_6L"
    assert manifest["combo_slug_map"]["1.2D+1.0W"] == "1_2D_1_0W"


def test_manifest_mencatat_asal_nilai_E(ex01_run: Path):
    """PRD Bagian 7.4: asal angka E wajib dapat ditelusuri."""
    manifest = json.loads((ex01_run / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["model_stats"]["E_source"]
    assert manifest["model_stats"]["element_type"] == "ShellMITC4"
    assert manifest["model_stats"]["pile_load_modeling"] == "pressure"
    assert manifest["model_stats"]["n_fixed_nodes"] > 0


# ---------------------------------------------------------------------------
# Isi CSV
# ---------------------------------------------------------------------------


def test_header_element_resultants_memuat_satuan(ex01_run: Path):
    path = ex01_run / "Combo_1_2D_1_6L" / "element_resultants.csv"
    with open(path, encoding="utf-8") as handle:
        header = next(csv.reader(handle))
    for column in ("m_x [kNm/m]", "m_y [kNm/m]", "m_xy [kNm/m]", "q_x [kN/m]", "theta [deg]"):
        assert column in header
    # Komponen LOKAL ikut disertakan agar transformasi dapat dihitung ulang.
    for column in ("m11 [kNm/m]", "m22 [kNm/m]", "m12 [kNm/m]"):
        assert column in header


def test_jumlah_baris_element_resultants_sama_dengan_jumlah_elemen(ex01_run: Path):
    manifest = json.loads((ex01_run / "run_manifest.json").read_text(encoding="utf-8"))
    path = ex01_run / "Combo_1_2D_1_6L" / "element_resultants.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == manifest["model_stats"]["n_elements"] + 1


def test_total_reaksi_di_reactions_csv_sama_dengan_sigma_pz(ex01_run: Path):
    path = ex01_run / "Combo_1_2D_1_6L" / "reactions.csv"
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    total = next(r for r in rows if r["node_tag"] == "TOTAL")
    # Sigma Pz = 4 x 1250.5 kN; reaksi berlawanan arah.
    assert float(total["Rz [kN]"]) == pytest.approx(-4 * 1250.5, rel=1e-9)


# ---------------------------------------------------------------------------
# Filter & override
# ---------------------------------------------------------------------------


def test_filter_combo(ex01: Path, tmp_path: Path):
    run_dir = run_cli(ex01, tmp_path / "output", "--combo", "1.2D+1.0W")
    combos = [p.name for p in run_dir.iterdir() if p.name.startswith("Combo_")]
    assert combos == ["Combo_1_2D_1_0W"]

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["combos_analyzed"] == ["1.2D+1.0W"]


def test_combo_tidak_dikenal_raise(ex01: Path, tmp_path: Path):
    with pytest.raises(InputError, match="tidak ada di"):
        run_cli(ex01, tmp_path / "output", "--combo", "kombinasi-hantu")


def test_override_elemen_shell(ex01: Path, tmp_path: Path):
    """PRD Bagian 11: mode perbandingan ShellDKGQ harus dapat dijalankan user."""
    run_dir = run_cli(ex01, tmp_path / "output", "--element", "ShellDKGQ", "--combo", "1.2D+1.6L")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["model_stats"]["element_type"] == "ShellDKGQ"


def test_self_weight_menambah_beban_dan_tetap_lulus_vc0(ex01: Path, tmp_path: Path):
    run_dir = run_cli(ex01, tmp_path / "output", "--self-weight", "--combo", "1.2D+1.6L")
    payload = json.loads(
        (run_dir / "Combo_1_2D_1_6L" / "equilibrium_check.json").read_text(encoding="utf-8")
    )
    assert payload["status"] == "PASS"
    assert payload["self_weight_total_N"] < 0.0  # berat sendiri bekerja ke BAWAH
    # Beban total = Sigma Pz + berat sendiri (negatif), jadi lebih kecil dari Sigma Pz.
    assert payload["total_applied_fz_N"] < 4 * 1250.5e3


def test_no_save_raw_melewati_element_resultants(ex01: Path, tmp_path: Path):
    run_dir = run_cli(ex01, tmp_path / "output", "--no-save-raw", "--combo", "1.2D+1.6L")
    combo_dir = run_dir / "Combo_1_2D_1_6L"
    assert not (combo_dir / "element_resultants.csv").exists()
    assert (combo_dir / "reactions.csv").is_file()


def test_equilibrium_rtol_mustahil_menggagalkan_run(ex01: Path, tmp_path: Path):
    """Run yang gagal VC-0 TIDAK boleh menghasilkan output desain."""
    with pytest.raises(AnalysisError, match="VC-0 GAGAL"):
        run_cli(ex01, tmp_path / "output", "--equilibrium-rtol", "1e-30")

    run_dir = next((tmp_path / "output").iterdir())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert "AnalysisError" in manifest["checks"]["error"]


# ---------------------------------------------------------------------------
# Material wajib (berbeda dari pilecap-mesh)
# ---------------------------------------------------------------------------


def test_E_null_menggagalkan_analyze(ex01: Path, tmp_path: Path, patch):
    """`pilecap-mesh` boleh jalan tanpa E; `pilecap-analyze` tidak."""
    patch(ex01 / "pilecap_config.json", material={"E": None})
    with pytest.raises(InputError, match="TIDAK menghitung modulus elastisitas"):
        run_cli(ex01, tmp_path / "output")


def test_pile_id_tidak_cocok_raise(ex01: Path, tmp_path: Path):
    """PRD Bagian 5.3 rule 3 -- selisih dua arah harus dilaporkan."""
    path = ex01 / "pile_reactions.csv"
    text = path.read_text(encoding="utf-8").replace("P4", "P9")
    path.write_text(text, encoding="utf-8")
    with pytest.raises(InputError, match="tidak cocok"):
        run_cli(ex01, tmp_path / "output")


def test_total_pz_tidak_positif_raise(ex01: Path, tmp_path: Path):
    """PRD Bagian 5.3 rule 15."""
    path = ex01 / "pile_reactions.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    fixed = [lines[0]] + [
        line.replace(",1250.5,", ",-1250.5,") if "1.2D+1.6L" in line else line for line in lines[1:]
    ]
    path.write_text("\n".join(fixed) + "\n", encoding="utf-8")
    with pytest.raises(InputError, match="rule 15"):
        run_cli(ex01, tmp_path / "output")


def test_gaya_lateral_tak_nol_menghasilkan_warning(ex01: Path, tmp_path: Path):
    """Hx/Hy diabaikan di v1.0, tetapi TIDAK boleh hilang diam-diam."""
    path = ex01 / "pile_reactions.csv"
    lines = path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace(",0,0", ",125.0,0")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    run_dir = run_cli(ex01, tmp_path / "output", "--combo", "1.2D+1.6L")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert any("DIABAIKAN di v1.0" in w for w in manifest["warnings"])
