"""Test end-to-end CLI `pilecap-mesh` (PRD Bagian 6.1 & 15.2)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pilecap_fem import cli_pilecap_mesh, io_utils, provenance
from pilecap_fem.validators import InputError

pytestmark = pytest.mark.slow


def run_cli(directory: Path, output_root: Path, *extra: str) -> Path:
    args = cli_pilecap_mesh.build_parser().parse_args(
        [
            "--config",
            str(directory / "pilecap_config.json"),
            "--input-dir",
            str(directory),
            "--output-dir",
            str(output_root),
            *extra,
        ]
    )
    return cli_pilecap_mesh.run(args, "pilecap-mesh (test)")


def test_run_menghasilkan_seluruh_artefak(ex01: Path, tmp_path: Path):
    run_dir = run_cli(ex01, tmp_path / "output", "--export-msh", "--dpi", "80")
    model_dir = run_dir / "00_Model"

    for name in ("mesh_summary.md", "mesh_plan.png", "nodes.csv", "elements.csv", "model.msh"):
        assert (model_dir / name).is_file(), f"{name} tidak dibuat"
    assert (run_dir / "run_manifest.json").is_file()
    assert (run_dir / "run.log").is_file()


def test_manifest_lengkap_dan_hash_cocok(ex01: Path, tmp_path: Path):
    run_dir = run_cli(ex01, tmp_path / "output", "--dpi", "80")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert manifest["status"] == "OK"
    assert manifest["unit_system"] == "SI (N, m, Pa)"
    assert manifest["dependencies"]["gmsh"].startswith("4.")
    assert manifest["checks"]["all_quad"] == "PASS"
    assert manifest["checks"]["equilibrium_VC0"].startswith("NOT_RUN")
    assert manifest["checks"]["capacity_checks"] == "NOT_EVALUATED"
    assert manifest["model_stats"]["mesh"]["n_tri"] == 0
    assert manifest["model_stats"]["mesh"]["all_quad"] is True

    # Sumber ketiga entitas tercatat meski tidak ada override (PRD Bagian 5.2.1).
    resolution = manifest["geometry_resolution"]
    assert set(resolution) == {"pilecap", "pile", "pier"}
    assert resolution["pilecap"]["source"] == "json_standard"

    # sha256 config cocok dengan file aslinya.
    config_key = next(k for k in manifest["inputs"] if k.endswith("pilecap_config.json"))
    expected = io_utils.sha256_file(ex01 / "pilecap_config.json")
    assert manifest["inputs"][config_key] == f"sha256:{expected}"

    # Parameter mentah tetap disimpan apa adanya untuk audit.
    assert manifest["parameters"]["config_raw"]["pilecap"]["length_x"] == 4800
    assert manifest["parameters"]["config_si"]["pilecap"]["length_x"] == pytest.approx(4.8)


def test_mesh_summary_memuat_tabel_resolusi_dan_disclaimer(ex01: Path, tmp_path: Path):
    run_dir = run_cli(ex01, tmp_path / "output", "--dpi", "80")
    text = (run_dir / "00_Model" / "mesh_summary.md").read_text(encoding="utf-8")

    assert "RESOLUSI SUMBER GEOMETRI" in text
    assert "json_standard" in text and "json_grid" in text
    assert "ALL-QUAD?" in text and "**YA**" in text
    assert "PERNYATAAN TANGGUNG JAWAB" in text
    assert "ALAT BANTU" in text
    assert "NOT_EVALUATED" in text
    # Setiap tabel wajib menyertakan satuan.
    assert "[m^2]" in text and "[mm]" in text


def test_ex03_override_dilaporkan_di_manifest_dan_summary(ex03: Path, tmp_path: Path):
    run_dir = run_cli(ex03, tmp_path / "output", "--dpi", "80")

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    resolution = manifest["geometry_resolution"]
    assert resolution["pilecap"]["source"] == "csv_autodetect"
    assert resolution["pile"]["source"] == "csv_autodetect"
    assert resolution["pier"]["source"] == "csv_autodetect"
    assert "pilecap.length_x" in resolution["pilecap"]["overridden_json_keys"]
    assert resolution["pilecap"]["sha256"] is not None

    text = (run_dir / "00_Model" / "mesh_summary.md").read_text(encoding="utf-8")
    assert "OVERRIDE" in text
    assert "PERHATIAN" in text
    assert "PIER_A" in text and "PIER_B" in text


def test_ex03_no_custom_tidak_ada_override(ex03: Path, tmp_path: Path):
    run_dir = run_cli(ex03, tmp_path / "output", "--no-custom", "--dpi", "80")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    resolution = manifest["geometry_resolution"]

    assert resolution["pilecap"]["source"] == "json_standard"
    assert resolution["pile"]["source"] == "json_grid"
    assert resolution["pier"]["source"] == "json_standard"
    assert all(r["overridden_json_keys"] == [] for r in resolution.values())

    text = (run_dir / "00_Model" / "mesh_summary.md").read_text(encoding="utf-8")
    assert "PERHATIAN" not in text


def test_peringatan_overlap_sampai_ke_mesh_summary(tmp_path: Path):
    """Peringatan GEOMETRI, bukan hanya peringatan mesher, harus masuk `mesh_summary.md`.

    Di sinilah pembaca pertama kali melihat group `LENS_*` pada tabel luas -- tempat
    penjelasannya paling dibutuhkan. Sempat terlewat: pemanggilnya hanya meneruskan
    `raw.warnings`, sehingga tabelnya memuat lensa tanpa satu baris pun yang menerangkan
    mengapa ia ada.
    """
    import shutil

    source = Path(__file__).resolve().parents[1] / "examples" / "ex04_pile_overlap_pier"
    target = tmp_path / "ex04"
    shutil.copytree(source, target)
    run_dir = run_cli(target, tmp_path / "output", "--dpi", "80")

    text = (run_dir / "00_Model" / "mesh_summary.md").read_text(encoding="utf-8")
    assert "TUMPANG TINDIH" in text
    assert "LENS_P2__PIER1" in text, "group lensa harus muncul di tabel luas"


def test_override_cli_tercatat_di_manifest(ex01: Path, tmp_path: Path):
    """`--size` diberikan dalam satuan input (mm) dan dikonversi memakai faktor yang sama."""
    run_dir = run_cli(ex01, tmp_path / "output", "--size", "120", "--algorithm", "8", "--dpi", "80")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert manifest["parameters"]["cli_mesh_overrides"]["size"] == 120.0
    assert manifest["parameters"]["cli_mesh_overrides"]["algorithm"] == 8
    assert manifest["parameters"]["config_si"]["mesh"]["size_global"] == pytest.approx(0.120)
    assert manifest["model_stats"]["mesh"]["algorithm"] == 8
    assert manifest["model_stats"]["mesh"]["mesh_size_max_m"] == pytest.approx(0.120)


def test_override_size_mode_graded_lewat_cli(ex01: Path, tmp_path: Path, patch):
    patch(ex01 / "pilecap_config.json", mesh={"size_global": 300, "size_local_pile": 100})
    run_dir = run_cli(ex01, tmp_path / "output", "--size-mode", "graded", "--dpi", "80")
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))

    assert manifest["model_stats"]["mesh"]["size_mode"] == "graded"
    assert manifest["model_stats"]["mesh"]["mesh_size_min_m"] == pytest.approx(0.10)
    assert manifest["model_stats"]["mesh"]["mesh_size_max_m"] == pytest.approx(0.30)
    assert manifest["model_stats"]["mesh"]["n_tri"] == 0


def test_config_uniform_dengan_size_local_raise(ex01: Path, tmp_path: Path, patch):
    """PRD Bagian 5.3 rule 7b -- parameter akan diabaikan diam-diam."""
    patch(ex01 / "pilecap_config.json", mesh={"size_local_pile": 60})
    with pytest.raises(InputError, match="TIDAK akan berpengaruh"):
        run_cli(ex01, tmp_path / "output")


def test_size_terlalu_besar_raise(ex01: Path, tmp_path: Path):
    """PRD Bagian 5.3 rule 7a: D_pile/h = 800/500 = 1.6 < 6."""
    with pytest.raises(InputError, match=r"D_pile/h"):
        run_cli(ex01, tmp_path / "output", "--size", "500")


def test_run_gagal_tetap_meninggalkan_manifest_berstatus_failed(ex01: Path, tmp_path: Path):
    """PRD Bagian 10: run yang gagal pun harus terlacak."""
    root = tmp_path / "output"
    with pytest.raises(InputError):
        run_cli(ex01, root, "--size", "500")

    run_dir = next(root.iterdir())
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert "InputError" in manifest["checks"]["error"]
    assert "D_pile/h" in manifest["checks"]["error"]
    assert manifest["tool_version"]
    assert (run_dir / "run.log").is_file()


def test_no_custom_plus_flag_eksplisit_raise(ex03: Path, tmp_path: Path):
    with pytest.raises(InputError, match="saling bertentangan"):
        run_cli(
            ex03,
            tmp_path / "output",
            "--no-custom",
            "--pier-polygon",
            str(ex03 / "pier_polygon.csv"),
        )


def test_entry_point_mengembalikan_kode_2_pada_kegagalan(ex01: Path, tmp_path: Path, capsys):
    code = cli_pilecap_mesh.entry_point(
        [
            "--config",
            str(ex01 / "pilecap_config.json"),
            "--input-dir",
            str(ex01),
            "--output-dir",
            str(tmp_path / "output"),
            "--size",
            "500",
        ]
    )
    assert code == 2
    assert "GAGAL" in capsys.readouterr().err


def test_setiap_run_membuat_folder_baru(ex01: Path, tmp_path: Path):
    root = tmp_path / "output"
    first = run_cli(ex01, root, "--dpi", "80")
    second = run_cli(ex01, root, "--dpi", "80")
    assert first != second
    assert first.exists() and second.exists()


def test_make_run_dir_tidak_menimpa(tmp_path: Path):
    a = provenance.make_run_dir(tmp_path)
    b = provenance.make_run_dir(tmp_path)
    assert a != b
    assert a.is_dir() and b.is_dir()


@pytest.mark.parametrize(
    "module_name",
    ["cli_pilecap_mesh", "cli_pilecap_analyze", "cli_pilecap_report", "cli_pilecap_run"],
)
def test_keempat_cli_punya_entry_point_dan_parser(module_name: str):
    """Keempat entry point PRD Bagian 14 kini nyata -- tidak ada lagi stub."""
    import importlib

    module = importlib.import_module(f"pilecap_fem.{module_name}")
    assert callable(module.entry_point)
    parser = module.build_parser()
    assert parser.prog.startswith("pilecap-")
