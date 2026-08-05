"""Test pengemasan & distribusi (PRD Bagian 14, Cond D).

Menjaga tiga hal yang pernah salah atau mudah salah lagi:

1. **Versi tercecer di dua tempat.** `pyproject.toml` dan `__init__.py` pernah tertinggal
   di 0.1.0 sementara CHANGELOG sudah 0.3.0 -- akibatnya SETIAP `run_manifest.json`
   mengklaim versi tool yang keliru (PRD Core 5).
2. **Dependency tidak di-pin.** `uvx` mengabaikan `uv.lock` saat install dari git, jadi
   rentang longgar berarti pengguna bisa menjalankan numerik yang berbeda dari yang
   lolos validation case.
3. **Contoh tidak ikut terkemas.** `config.examples_dir()` punya fallback ke folder repo
   yang membuat kesalahan pengemasan tidak terlihat saat dijalankan dari repo.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import zipfile
from importlib import metadata
from pathlib import Path

import pytest

import pilecap_fem
from pilecap_fem import config
from pilecap_fem.validators import InputError

REPO = Path(__file__).resolve().parents[1]
PYPROJECT = REPO / "pyproject.toml"

#: Keempat command PRD Bagian 14.
EXPECTED_SCRIPTS = {
    "pilecap-mesh": "pilecap_fem.cli_pilecap_mesh:entry_point",
    "pilecap-analyze": "pilecap_fem.cli_pilecap_analyze:entry_point",
    "pilecap-report": "pilecap_fem.cli_pilecap_report:entry_point",
    "pilecap-run": "pilecap_fem.cli_pilecap_run:entry_point",
}


def _pyproject_text() -> str:
    return PYPROJECT.read_text(encoding="utf-8")


def _dependencies() -> list[str]:
    import tomllib

    with open(PYPROJECT, "rb") as handle:
        return list(tomllib.load(handle)["project"]["dependencies"])


# ---------------------------------------------------------------------------
# Versi: satu sumber, konsisten di mana-mana
# ---------------------------------------------------------------------------


def test_versi_paket_cocok_dengan_dunder_version():
    """Inilah yang menangkap penyimpangan versi yang pernah terjadi."""
    assert metadata.version("pilecap-fem") == pilecap_fem.__version__


def test_versi_tidak_ditulis_ulang_di_pyproject():
    """Versi harus DINAMIS dari `__init__.py`, bukan diketik lagi di pyproject."""
    text = _pyproject_text()
    assert 'dynamic = ["version"]' in text
    assert "[tool.hatch.version]" in text
    assert not re.search(r"^version\s*=", text, flags=re.MULTILINE), (
        "`version = ...` statis ditemukan di pyproject.toml; itu membuat versi hidup di "
        "dua tempat dan bisa menyimpang lagi."
    )


def test_versi_cocok_dengan_changelog():
    """Rilis tanpa catatan perubahan tidak dapat diaudit (PRD Bagian 16C)."""
    changelog = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    versions = re.findall(r"^## \[([0-9]+\.[0-9]+\.[0-9]+)\]", changelog, flags=re.MULTILINE)
    assert versions, "CHANGELOG.md tidak memuat satu pun entri versi"
    assert versions[0] == pilecap_fem.__version__, (
        f"versi tool {pilecap_fem.__version__} tidak cocok dengan entri teratas "
        f"CHANGELOG ({versions[0]})"
    )


def test_versi_muncul_di_manifest_provenance():
    from pilecap_fem import provenance

    manifest = provenance.Manifest(REPO / "output" / "_dummy", "uji")
    assert manifest.data["tool_version"] == pilecap_fem.__version__


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def test_keempat_entry_point_terdaftar_dan_dapat_dipanggil():
    """Dibaca dari metadata paket TERPASANG, bukan dari daftar yang diketik ulang."""
    scripts = {
        ep.name: ep.value
        for ep in metadata.distribution("pilecap-fem").entry_points
        if ep.group == "console_scripts"
    }
    assert scripts == EXPECTED_SCRIPTS

    for name in EXPECTED_SCRIPTS:
        ep = next(
            e
            for e in metadata.distribution("pilecap-fem").entry_points
            if e.name == name and e.group == "console_scripts"
        )
        assert callable(ep.load()), f"entry point {name} tidak dapat dipanggil"


@pytest.mark.parametrize("name", sorted(EXPECTED_SCRIPTS))
def test_setiap_command_menampilkan_versi_yang_benar(name: str):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.argv=['{name}','--version']; "
            f"from {EXPECTED_SCRIPTS[name].split(':')[0]} import entry_point; entry_point()",
        ],
        capture_output=True,
        text=True,
    )
    assert pilecap_fem.__version__ in (result.stdout + result.stderr)


@pytest.mark.parametrize("heavy", ["gmsh", "openseespy"])
def test_pilecap_report_tidak_menarik_solver(heavy: str):
    """`pilecap-report` hanya membaca CSV -- solver tidak perlu ikut dimuat.

    Bukan sekadar soal kecepatan: `openseespy` gagal diimpor pada interpreter yang
    tidak didukung, sehingga pelaporan dari CSV pun akan ikut mati tanpa alasan.
    """
    code = f"import sys; import pilecap_fem.cli_pilecap_report; print({heavy!r} in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False", (
        f"mengimpor cli_pilecap_report ikut memuat {heavy} -- periksa impor "
        "TYPE_CHECKING di mesh_model.py, postproc_engine.py, dan reporter.py"
    )


# ---------------------------------------------------------------------------
# Penjaga interpreter
# ---------------------------------------------------------------------------


def test_interpreter_saat_ini_lolos_penjaga():
    pilecap_fem._check_interpreter()


def test_penjaga_interpreter_konsisten_dengan_requires_python():
    import tomllib

    with open(PYPROJECT, "rb") as handle:
        requires = tomllib.load(handle)["project"]["requires-python"]
    low, high = pilecap_fem.REQUIRED_PYTHON
    assert f">={low[0]}.{low[1]}" in requires
    assert f"<{high[0]}.{high[1]}" in requires


@pytest.mark.parametrize("versi", [(3, 11), (3, 13), (3, 14)])
def test_penjaga_menolak_interpreter_tak_didukung(versi: tuple[int, int], monkeypatch):
    """DIUKUR: `uvx` dari sumber git memilih interpreter SEBELUM tahu requires-python.

    Terbukti memakai Python 3.14 dan tetap memasang paketnya; tanpa penjaga ini,
    kegagalannya muncul sebagai `DLL load failed while importing opensees` yang
    terbaca seperti instalasi rusak, bukan seperti salah interpreter.
    """
    monkeypatch.setattr(sys, "version_info", (*versi, 0, "final", 0))
    monkeypatch.setattr(sys, "version", f"{versi[0]}.{versi[1]}.0")
    with pytest.raises(RuntimeError, match=r"--python 3\.12"):
        pilecap_fem._check_interpreter()


# ---------------------------------------------------------------------------
# Pinning dependency
# ---------------------------------------------------------------------------


def test_seluruh_dependency_runtime_dipin_eksak():
    """`uvx` install dari git MENGABAIKAN uv.lock -- pin di sinilah yang berlaku."""
    longgar = [d for d in _dependencies() if "==" not in d]
    assert not longgar, (
        f"dependency berikut tidak di-pin eksak: {longgar}. "
        "Pengguna uvx bisa mendapat numerik yang berbeda dari yang lolos validation case."
    )


def test_versi_terpasang_cocok_dengan_yang_dipin():
    """Yang berjalan di sini harus benar-benar versi yang dijanjikan pyproject."""
    for spec in _dependencies():
        name, pinned = spec.split("==")
        assert metadata.version(name) == pinned, (
            f"{name} terpasang {metadata.version(name)} tetapi di-pin {pinned}"
        )


def test_batas_python_menutup_313():
    """DIUKUR: openseespy 3.8.0.0 terpasang di 3.13 tetapi GAGAL diimpor (DLL)."""
    import tomllib

    with open(PYPROJECT, "rb") as handle:
        requires = tomllib.load(handle)["project"]["requires-python"]
    assert "<3.13" in requires, (
        "batas atas <3.13 dihapus; tanpa itu uv akan memasang openseespy di Python 3.13 "
        "yang lolos instalasi tetapi gagal saat diimpor"
    )


# ---------------------------------------------------------------------------
# Contoh bawaan
# ---------------------------------------------------------------------------


def test_examples_dir_memuat_ketiga_contoh():
    source = config.examples_dir()
    for name in config.EXAMPLE_NAMES:
        assert (source / name / "pilecap_config.json").is_file(), f"{name} tidak lengkap"
        assert (source / name / "pile_reactions.csv").is_file()


def test_ex03_memuat_ketiga_csv_geometri():
    """ex03 sekaligus acuan format CSV geometri (PRD Bagian 5.4)."""
    ex03 = config.examples_dir() / "ex03_custom_polygon"
    for name in ("pilecap_polygon.csv", "pier_polygon.csv", "custom_pile_coords.csv"):
        assert (ex03 / name).is_file()


def test_init_example_menyalin_berkas_identik(tmp_path: Path):
    from pilecap_fem import cli_pilecap_mesh

    args = cli_pilecap_mesh.build_parser().parse_args(["--init-example", str(tmp_path)])
    assert cli_pilecap_mesh.handle_init_example(args) is True

    source = config.examples_dir()
    for name in config.EXAMPLE_NAMES:
        for original in (source / name).iterdir():
            salinan = tmp_path / name / original.name
            assert salinan.is_file(), f"{name}/{original.name} tidak tersalin"
            assert salinan.read_bytes() == original.read_bytes(), (
                f"{name}/{original.name} berbeda dari contoh yang dipakai test regresi"
            )


def test_init_example_menolak_menimpa(tmp_path: Path):
    """Contoh dimaksudkan untuk dimodifikasi user -- jangan ditimpa diam-diam."""
    from pilecap_fem import cli_pilecap_mesh

    (tmp_path / config.EXAMPLE_NAMES[0]).mkdir(parents=True)
    args = cli_pilecap_mesh.build_parser().parse_args(["--init-example", str(tmp_path)])
    with pytest.raises(InputError, match="sudah ada"):
        cli_pilecap_mesh.handle_init_example(args)


def test_tanpa_flag_init_example_tidak_berbuat_apa_apa(tmp_path: Path):
    from pilecap_fem import cli_pilecap_mesh

    args = cli_pilecap_mesh.build_parser().parse_args([])
    assert cli_pilecap_mesh.handle_init_example(args) is False


@pytest.mark.parametrize(
    "module_name", ["cli_pilecap_mesh", "cli_pilecap_analyze", "cli_pilecap_run"]
)
def test_init_example_tersedia_di_command_yang_relevan(module_name: str):
    """`pilecap-report` sengaja TIDAK punya flag ini -- ia bekerja pada run yang sudah ada."""
    import importlib

    module = importlib.import_module(f"pilecap_fem.{module_name}")
    args = module.build_parser().parse_args(["--init-example", "x"])
    assert args.init_example == Path("x")


# ---------------------------------------------------------------------------
# Isi wheel -- memeriksa artefak yang benar-benar didistribusikan
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_wheel_memuat_contoh_dan_seluruh_modul(tmp_path: Path):
    """Membangun wheel sungguhan lalu memeriksa isinya.

    Ini satu-satunya cara membuktikan `examples/` benar-benar terkemas: dijalankan dari
    repo, `config.examples_dir()` akan tetap berhasil lewat fallback meskipun konfigurasi
    pengemasan salah.

    `uv` dipanggil lewat path ABSOLUT hasil `shutil.which()`, bukan nama telanjang.
    Pada Windows, `CreateProcess` meresolusi nama telanjang lewat PATH saat spawn, dan
    itu terbukti gagal (`WinError 2`) ketika test ini berjalan di akhir suite penuh
    meskipun lulus saat dijalankan sendirian -- kegagalan yang tidak ada hubungannya
    dengan isi wheel.
    """
    uv = shutil.which("uv")
    assert uv is not None, "`uv` tidak ditemukan di PATH; test pengemasan membutuhkannya"

    result = subprocess.run(
        [uv, "build", "--wheel", "--out-dir", str(tmp_path)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"uv build gagal:\n{result.stdout}\n{result.stderr}"

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, f"diharapkan satu wheel, ditemukan {wheels}"
    assert pilecap_fem.__version__ in wheels[0].name

    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())

    for module in (
        "cli_pilecap_mesh",
        "cli_pilecap_analyze",
        "cli_pilecap_report",
        "cli_pilecap_run",
        "fem_engine",
        "math_engine",
        "postproc_engine",
        "renderer",
        "reporter",
    ):
        assert f"pilecap_fem/{module}.py" in names, f"modul {module} tidak ikut terkemas"

    for name in config.EXAMPLE_NAMES:
        path = f"pilecap_fem/examples/{name}/pilecap_config.json"
        assert path in names, f"contoh {name} tidak ikut terkemas ({path})"

    assert any(n.endswith("LICENSE") for n in names), "LICENSE tidak ikut terkemas"
