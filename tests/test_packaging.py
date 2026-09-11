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

#: Seluruh command yang dipasang. Keempat yang pertama adalah command PRD Bagian 14;
#: `pilecap-ui` dan `pilecap-manual` menyusul kemudian.
EXPECTED_SCRIPTS = {
    "pilecap-mesh": "pilecap_fem.cli_pilecap_mesh:entry_point",
    "pilecap-analyze": "pilecap_fem.cli_pilecap_analyze:entry_point",
    "pilecap-report": "pilecap_fem.cli_pilecap_report:entry_point",
    "pilecap-run": "pilecap_fem.cli_pilecap_run:entry_point",
    "pilecap-ui": "pilecap_fem.ui.launcher:entry_point",
    "pilecap-manual": "pilecap_fem.cli_pilecap_manual:entry_point",
}

#: `pilecap-ui` sengaja TIDAK menerima argumen baris perintah -- seluruh masukan diisi
#: lewat formulir -- sehingga ia tidak punya `--version` untuk diuji.
VERSIONED_SCRIPTS = {k: v for k, v in EXPECTED_SCRIPTS.items() if k != "pilecap-ui"}


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


def test_setiap_entry_point_terdaftar_dan_dapat_dipanggil():
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


@pytest.mark.parametrize("name", sorted(VERSIONED_SCRIPTS))
def test_setiap_command_menampilkan_versi_yang_benar(name: str):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"import sys; sys.argv=['{name}','--version']; "
            f"from {VERSIONED_SCRIPTS[name].split(':')[0]} import entry_point; entry_point()",
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


@pytest.mark.parametrize("heavy", ["gmsh", "openseespy"])
def test_reporting_pdf_tidak_menarik_solver(heavy: str):
    """Laporan PDF juga hanya menyusun ulang hasil; solver tidak perlu ikut dimuat.

    Alasannya sama dengan `cli_pilecap_report`, dan penjaganya dibutuhkan tersendiri:
    `reporting_pdf` mengimpor `reporter` dan `capacity_engine`, jadi disiplin impor kedua
    modul itu bisa runtuh lewat jalur ini tanpa test di atas menyadarinya.
    """
    code = f"import sys; import pilecap_fem.reporting_pdf; print({heavy!r} in sys.modules)"
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "False", f"mengimpor reporting_pdf ikut memuat {heavy}"


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
    """`uvx` install dari git MENGABAIKAN uv.lock -- pin di sinilah yang berlaku.

    Dua bentuk pin diterima, dan hanya dua: `paket==versi` untuk paket PyPI, serta
    `paket @ https://.../vX.Y.Z/paket-X.Y.Z-*.whl` untuk direct reference berupa wheel
    yang path dan nama berkasnya sama-sama menyematkan versi tetap. Yang dilarang adalah
    rentang longgar (`>=`, `~=`, atau tanpa penanda) DAN `git+` tanpa versi di wheel-nya,
    karena dua pengguna yang menginstal di hari berbeda dapat menjalankan numerik berbeda.
    """
    longgar = [d for d in _dependencies() if not _pin_eksak(d)]
    assert not longgar, (
        f"dependency berikut tidak di-pin eksak: {longgar}. "
        "Pengguna uvx bisa mendapat numerik yang berbeda dari yang lolos validation case."
    )


def test_shell_kit_bukan_git_dan_terkunci_ke_versi_rilis():
    """`git+` memaksa git terpasang di mesin PEMASANG, bukan hanya mesin pengembang.

    Pengguna lapangan yang menjalankan `uv sync` tanpa git akan gagal instalasi dengan
    pesan yang seolah tidak berkaitan. Direct reference berupa wheel URL menghindarinya:
    `uv`/`pip` mengunduhnya lewat HTTPS biasa, tanpa satu pun perintah git. Tag versi tetap
    dijaga -- kini lewat path release (`.../vX.Y.Z/...`) dan nama wheel itu sendiri,
    bukan lewat `@tag` di belakang URL git.
    """
    spec = next(d for d in _dependencies() if d.startswith("shell-kit"))
    assert "git+" not in spec, (
        "shell-kit tidak boleh lagi memakai git+ (butuh git di mesin pemasang)"
    )
    assert spec.endswith(".whl"), "shell-kit harus direct reference ke berkas wheel"

    url = spec.split("@", 1)[1].strip()
    match = re.search(r"/(v\d+\.\d+\.\d+)/shell_kit-(\d+\.\d+\.\d+)-[^/]+\.whl$", url)
    assert match is not None, f"URL wheel shell-kit tidak menyematkan tag versi: {url!r}"
    assert match.group(1).lstrip("v") == match.group(2), (
        f"tag rilis ({match.group(1)}) dan versi di nama wheel ({match.group(2)}) berbeda"
    )


def test_versi_terpasang_cocok_dengan_yang_dipin():
    """Yang berjalan di sini harus benar-benar versi yang dijanjikan pyproject."""
    for spec in _dependencies():
        if "==" in spec:
            name, pinned = spec.split("==")
        elif spec.endswith(".whl"):
            # Direct reference wheel: nama berkas `paket-X.Y.Z-*.whl` membawa versinya.
            name = spec.split("@", 1)[0].strip()
            wheel_name = spec.rsplit("/", 1)[1]
            pinned = wheel_name.removeprefix(f"{name.replace('-', '_')}-").split("-")[0]
        else:
            # Direct reference git: tag `vX.Y.Z` menjadi versi X.Y.Z pada paket terpasang.
            name = spec.split("@", 1)[0].strip()
            pinned = spec.rsplit("@", 1)[1].lstrip("v")
        assert metadata.version(name) == pinned, (
            f"{name} terpasang {metadata.version(name)} tetapi di-pin {pinned}"
        )


def _pin_eksak(spec: str) -> bool:
    if "==" in spec:
        return True
    if spec.endswith(".whl"):
        return re.search(r"/v\d+\.\d+\.\d+/[^/]+\.whl$", spec) is not None
    return "git+" in spec and re.search(r"@v\d+\.\d+\.\d+$", spec) is not None


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
        # PRD Bagian 5.4: setiap contoh wajib memuat `expected/` (golden file). Ikut
        # dikemas supaya pengguna `uvx` dapat memverifikasi instalasinya mereproduksi
        # angka acuan, bukan hanya berjalan tanpa error.
        assert (source / name / "expected" / "golden.json").is_file(), (
            f"{name}/expected/golden.json tidak ada; jalankan "
            "`pytest tests/test_golden.py --regen-golden`"
        )


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
        # Rekursif: sejak v0.4.0 contoh memuat sub-folder `expected/` berisi golden file.
        for original in (source / name).rglob("*"):
            if not original.is_file():
                continue
            salinan = tmp_path / name / original.relative_to(source / name)
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

    # Halaman Streamlit adalah data yang dijalankan `streamlit run`, bukan modul yang
    # diimpor -- bila ia tidak ikut terkemas, `pilecap-ui` gagal hanya pada instalasi
    # sungguhan dan tidak pernah pada jalur pengembangan.
    assert "pilecap_fem/ui/app.py" in names, "halaman Streamlit tidak ikut terkemas"

    for module in (
        "capacity_engine",
        "cli_pilecap_mesh",
        "cli_pilecap_analyze",
        "cli_pilecap_report",
        "cli_pilecap_run",
        "cli_pilecap_manual",
        "fem_engine",
        "math_engine",
        "postproc_engine",
        "renderer",
        "reporter",
    ):
        assert f"pilecap_fem/{module}.py" in names, f"modul {module} tidak ikut terkemas"

    # Sub-paket memang ikut lewat `packages = ["src/pilecap_fem"]`, tetapi tata letak yang
    # rusak (mis. `__init__.py` tertinggal) hanya terlihat di sini, bukan saat dijalankan
    # dari repo.
    for module in ("__init__", "chapters", "document", "figures", "model", "theory", "typst_kit"):
        path = f"pilecap_fem/reporting_pdf/{module}.py"
        assert path in names, f"modul laporan PDF tidak ikut terkemas ({path})"

    # Panduan HARUS ikut di dalam wheel, bukan hanya ada di repo: pengguna yang menerima
    # wheel saja justru yang paling membutuhkan panduan sesuai versi terpasangnya.
    for module in ("__init__", "chapters", "config_reference", "document"):
        path = f"pilecap_fem/manual/{module}.py"
        assert path in names, f"modul panduan tidak ikut terkemas ({path})"

    for name in config.EXAMPLE_NAMES:
        for relative in ("pilecap_config.json", "expected/golden.json"):
            path = f"pilecap_fem/examples/{name}/{relative}"
            assert path in names, f"contoh {name} tidak lengkap terkemas ({path})"

    # Ilustrasi ditampilkan DI DALAM formulir `pilecap-ui`. Alasannya sama dengan contoh
    # di atas: dijalankan dari repo, `config.illustrations_dir()` tetap berhasil lewat
    # fallback meskipun pengemasannya salah -- sehingga kegagalannya hanya menimpa
    # pengguna `uvx`/wheel, yang justru paling terbantu gambar.
    from pilecap_fem.ui import schema as ui_schema

    dipakai = {s.illustration for s in ui_schema.SECTIONS if s.illustration}
    assert dipakai, "tidak ada satu pun bagian formulir yang memakai ilustrasi"
    for berkas in sorted(dipakai):
        path = f"pilecap_fem/docs_img/{berkas}"
        assert path in names, f"ilustrasi {berkas} tidak ikut terkemas ({path})"

    # Panduan menanam gambar DI LUAR `Section.illustration` juga -- perbandingan VC-6 dan
    # contoh basis desain. Diperiksa dari sumber panduan yang benar-benar dihasilkan, bukan
    # dari daftar yang diketik ulang di sini: daftar kedua akan tertinggal begitu sebuah
    # gambar ditambahkan, dan kegagalannya hanya menimpa pengguna wheel berupa kotak
    # "GAMBAR TIDAK TERSEDIA" pada bab yang seharusnya membuktikan angkanya dapat dipercaya.
    import re
    import tempfile

    from pilecap_fem.manual import document as manual_document
    from pilecap_fem.reporting_pdf.figures import FigureStore

    with tempfile.TemporaryDirectory() as tmp:
        sumber = manual_document.render_source(FigureStore(Path(tmp), started_at=0.0))
    for berkas in sorted(set(re.findall(r'image\("_figur_pdf/([^"]+)"', sumber))):
        path = f"pilecap_fem/docs_img/{berkas}"
        assert path in names, f"gambar panduan {berkas} tidak ikut terkemas ({path})"

    # Tabel Lampiran C panduan DIBACA dari berkas ini, bukan dirujuk lewat `image(...)`,
    # sehingga pemeriksaan gambar di atas tidak menangkapnya. Tanpa berkas ini
    # `pilecap-manual` gagal total -- dan hanya pada pengguna wheel, karena di repo
    # `config.illustrations_dir()` jatuh kembali ke `docs/img/` yang memuatnya.
    path = "pilecap_fem/docs_img/vc6-ringkasan.json"
    assert path in names, f"ringkasan VC-6 untuk Lampiran C tidak ikut terkemas ({path})"

    assert any(n.endswith("LICENSE") for n in names), "LICENSE tidak ikut terkemas"


def test_setiap_illustration_section_ada_berkasnya():
    """`Section.illustration` yang menunjuk berkas tidak ada akan meledak di formulir.

    Murah diperiksa di sini, mahal ditemukan di sana: kegagalannya muncul di tengah
    halaman yang sedang diisi engineer, bukan saat suite dijalankan.
    """
    from pilecap_fem.ui import schema as ui_schema

    folder = config.illustrations_dir()
    for section in ui_schema.SECTIONS:
        if not section.illustration:
            continue
        path = folder / section.illustration
        assert path.is_file(), f"bagian {section.title!r} menunjuk {path} yang tidak ada"
        # `st.image` menerima STRING SVG; berkas yang bukan SVG akan tampil sebagai teks.
        assert path.read_text(encoding="utf-8").lstrip().startswith("<svg"), (
            f"{path.name} bukan berkas SVG"
        )


def test_streamlit_adalah_extra_opsional_bukan_dependency_inti():
    """Pengguna CLI tidak boleh ikut memasang Streamlit beserta dependensinya.

    Sekaligus menjaga alasan mengapa ini SATU-SATUNYA pin longgar: Streamlit tidak ikut
    satu pun validation case dan tidak menyentuh angka rekayasa mana pun.
    """
    import tomllib

    with open(PYPROJECT, "rb") as handle:
        project = tomllib.load(handle)["project"]

    assert not any("streamlit" in d for d in project["dependencies"]), (
        "streamlit tidak boleh menjadi dependency inti"
    )
    ui_extra = project["optional-dependencies"]["ui"]
    assert any(d.startswith("streamlit>=") for d in ui_extra), ui_extra


def test_modul_ui_yang_dapat_salah_diam_diam_tidak_mengimpor_streamlit():
    """`schema` dan `argv` harus dapat diuji tanpa extra `[ui]` terpasang.

    Keduanya berisi satu-satunya bagian UI yang dapat menghasilkan config tidak sah atau
    flag tidak dikenal; menautkannya ke streamlit berarti bagian itu tidak teruji pada
    lingkungan yang hanya memasang paket inti.
    """
    for name in ("schema.py", "argv.py"):
        source = (REPO / "src" / "pilecap_fem" / "ui" / name).read_text(encoding="utf-8")
        assert "import streamlit" not in source, f"{name} mengimpor streamlit"


# ---------------------------------------------------------------------------
# Dokumentasi config: README vs ui/schema.py
# ---------------------------------------------------------------------------


def _schema_field_keys() -> list[str]:
    from pilecap_fem.ui import schema

    return [f.key for s in schema.SECTIONS for f in s.fields]


def test_readme_mendokumentasikan_setiap_field():
    """README dan tooltip UI menjelaskan daftar field yang SAMA -- dijaga, bukan diharapkan.

    Keduanya ditulis untuk pembaca berbeda (README lengkap dengan ilustrasi, tooltip ringkas
    di formulir), jadi teksnya memang tidak sama. Yang tidak boleh berbeda adalah
    CAKUPANNYA: field baru di `ui/schema.py` yang lupa didokumentasikan di README akan
    menyimpang diam-diam, dan pembaca README tidak punya cara mengetahuinya.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    keys = _schema_field_keys()
    hilang = [key for key in keys if key not in readme]
    assert not hilang, (
        f"{len(hilang)} field ada di ui/schema.py tetapi tidak disebut di README.md: "
        f"{hilang}\n"
        "  Tambahkan ke bagian 'Panduan lengkap pilecap_config.json'."
    )

    # README menyebut jumlahnya secara eksplisit; angka yang basi adalah kesalahan kecil
    # yang justru merusak kepercayaan pada dokumen selebihnya.
    from pilecap_fem.ui import schema

    assert f"{len(keys)} field" in readme, (
        f"README tidak lagi menyebut jumlah field yang benar ({len(keys)})"
    )
    assert f"{len(schema.SECTIONS)} bagian" in readme, (
        f"README tidak lagi menyebut jumlah bagian yang benar ({len(schema.SECTIONS)})"
    )


def test_readme_tidak_menyebut_field_yang_tidak_ada():
    """Arah sebaliknya: field yang DIHAPUS dari schema tidak boleh tertinggal di README.

    Tanpa ini, dokumentasi tetap menjanjikan field yang sudah tidak diterima tool -- jenis
    kesalahan yang baru ketahuan saat pembaca mencobanya dan run-nya gagal.
    """
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    dikenal = set(_schema_field_keys())
    blok = {k.split(".", 1)[0] for k in dikenal}

    disebut = {m for m in re.findall(r"`([a-z_]+\.[a-z_]+)`", readme) if m.split(".", 1)[0] in blok}
    asing = sorted(disebut - dikenal)
    assert not asing, (
        f"README menyebut field yang tidak ada di ui/schema.py: {asing}\n"
        "  Perbaiki namanya, atau hapus bila field-nya memang sudah tidak ada."
    )


def test_ilustrasi_readme_ada_berkasnya():
    """Gambar yang ditautkan README harus benar-benar ada dan berupa berkas gambar yang sah.

    Tautan gambar yang putus baru terlihat setelah README dibuka di GitHub, yaitu setelah
    dirilis -- terlambat. Ilustrasi tangan (SVG) divalidasi sebagai XML; tangkapan layar
    hasil run nyata (PNG, mis. perbandingan `rebar_basis`) divalidasi lewat header PNG-nya
    sendiri -- keduanya hidup di `docs/img/` yang sama tetapi bukan format yang sama.
    """
    import xml.etree.ElementTree as ET

    readme = (REPO / "README.md").read_text(encoding="utf-8")
    tautan = re.findall(r"!\[[^\]]*\]\((docs/img/[^)]+)\)", readme)
    assert tautan, "bagian panduan config kehilangan seluruh ilustrasinya"

    for rel in tautan:
        path = REPO / rel
        assert path.is_file(), f"README menautkan {rel} yang tidak ada"
        if path.suffix == ".svg":
            ET.parse(path)
        elif path.suffix == ".png":
            assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", f"{rel} bukan PNG yang sah"
        else:
            raise AssertionError(f"{rel}: ekstensi {path.suffix!r} belum didukung test ini")
