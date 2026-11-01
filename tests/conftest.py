"""Fixture bersama untuk seluruh test Fase 1."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from pilecap_fem import config

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
#: Diimpor dari `config`, TIDAK disalin: daftar ini pernah ada di tiga tempat, dan
#: contoh baru harus otomatis ikut teruji, bukan menunggu tiga daftar disamakan.
EXAMPLE_NAMES = config.EXAMPLE_NAMES


@pytest.fixture
def examples_dir() -> Path:
    return EXAMPLES_DIR


@pytest.fixture
def ex01(tmp_path: Path) -> Path:
    """Salinan ex01 di folder sementara (aman untuk dimodifikasi test)."""
    return _copy_example("ex01_standard_4pile", tmp_path)


@pytest.fixture
def ex03(tmp_path: Path) -> Path:
    """Salinan ex03 (polygon L, pile custom, dua pier) di folder sementara."""
    return _copy_example("ex03_custom_polygon", tmp_path)


def _copy_example(name: str, tmp_path: Path) -> Path:
    target = tmp_path / name
    shutil.copytree(EXAMPLES_DIR / name, target)
    return target


def patch_config(path: Path, **blocks: dict) -> Path:
    """Ubah beberapa key di dalam blok config yang sudah ada, lalu tulis ulang.

    Dipakai lewat fixture `patch` agar test tidak perlu mengimpor modul conftest.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    for block, updates in blocks.items():
        data.setdefault(block, {}).update(updates)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


@pytest.fixture
def patch():
    """Fixture yang mengembalikan `patch_config`."""
    return patch_config


# ---------------------------------------------------------------------------
# Golden file (PRD Bagian 8.2)
# ---------------------------------------------------------------------------


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--regen-golden",
        action="store_true",
        default=False,
        help=(
            "Tulis ulang seluruh berkas di tests/golden/ dari hasil run saat ini. "
            "WAJIB disertai catatan alasan di CHANGELOG.md -- golden yang diregenerasi "
            "tanpa alasan menghapus satu-satunya bukti bahwa angka tool tidak berubah."
        ),
    )


@pytest.fixture(scope="session")
def regen_golden(request: pytest.FixtureRequest) -> bool:
    return bool(request.config.getoption("--regen-golden"))


#: Stempel waktu yang ditanam Typst di setiap PDF (`/ModDate`, `/CreationDate`).
#: Segalanya di dalam PDF yang diturunkan dari JAM DINDING, bukan dari isi dokumen.
#:
#: Ada TIGA, dan ketiganya harus dibuang bersama -- membuang sebagian saja menghasilkan test
#: yang lolos hampir selalu lalu gagal sesekali, yang lebih menyesatkan daripada test yang
#: selalu gagal:
#:
#: 1. `/ModDate` dan `/CreationDate` pada kamus Info.
#: 2. Blok XMP (`xmp:ModifyDate`, `xmp:CreateDate`) -- stempel yang sama dalam bentuk XML.
#: 3. Sidik dokumen -- `/ID`, `xmpMM:InstanceID`, `xmpMM:DocumentID` -- yang Typst turunkan
#:    dari isi BERIKUT stempel waktunya, sehingga ikut berubah meskipun dokumennya identik.
_STEMPEL_WAKTU: tuple[re.Pattern[bytes], ...] = (
    re.compile(rb"/(?:Mod|Creation)Date\(D:[^)]*\)"),
    re.compile(rb"<xmp:(?:Modify|Create)Date>[^<]*</xmp:(?:Modify|Create)Date>"),
    re.compile(rb"<xmpMM:(?:Instance|Document)ID>[^<]*</xmpMM:(?:Instance|Document)ID>"),
    re.compile(rb"/ID\s*\[(?:\s*\([^)]*\)\s*|\s*<[^>]*>\s*)+\]"),
)


def pdf_tanpa_stempel_waktu(data: bytes) -> bytes:
    """PDF dengan stempel waktunya dibuang, supaya dua kompilasi dapat dibandingkan.

    Dua kompilasi yang kebetulan berada di sisi berbeda dari pergantian detik SELALU
    berbeda byte, berapa pun samanya isi dokumen. Tanpa menormalkannya, test yang
    membandingkan dua kompilasi sesungguhnya menguji jam, bukan apa yang hendak diujinya --
    dan ia lolos hanya selama dokumennya cukup kecil untuk dikompilasi dua kali dalam satu
    detik. Panduan yang bertambah besar membuat batas itu terlampaui.
    """
    for pola in _STEMPEL_WAKTU:
        data = pola.sub(b"", data)
    return data


@pytest.fixture
def tanpa_stempel_waktu():
    """Fungsi penormal stempel waktu PDF, dipakai test yang membandingkan dua kompilasi."""
    return pdf_tanpa_stempel_waktu


# ---------------------------------------------------------------------------
# Isolasi toolkit GUI: wx dan Qt tidak boleh hidup dalam satu proses
# ---------------------------------------------------------------------------
#
# DIUKUR (Windows, wxPython 4.3.2, PySide6 6.x): begitu sebuah `wx.App` pernah dibuat lalu
# dilepas -- atau sebuah jendela wx pernah dibuat -- `QApplication.processEvents()` pertama
# berikutnya mati dengan "access violation" (atau 0xc0000374, heap rusak), BAIK pada platform
# `offscreen` maupun `windows`. Penyebabnya: dispatcher event Qt di Windows memompa SELURUH
# antrean pesan Win32 milik thread, termasuk pesan untuk jendela tersembunyi wx yang
# keadaannya sudah dibongkar. `offscreen` hanya mengganti tampilan, bukan dispatcher-nya.
#
# Urutan Qt -> wx kebetulan selamat, tetapi itu tidak terbukti aman, hanya belum terlihat
# rusak. Maka bila satu sesi memilih test dari LEBIH DARI SATU toolkit, test setiap toolkit
# dijalankan di proses pytest anak tersendiri, lalu laporannya diputar ulang di proses induk
# per test -- sehingga hasil, `-x`, `-ra`, dan junitxml tetap per test seperti biasa. Satu
# berkas yang dijalankan sendirian tetap berjalan di proses ini, tanpa subprocess.
#
# Berkas test GUI menandai dirinya dengan `pytestmark = pytest.mark.gui_toolkit("<nama>")`.

#: Bila disetel, proses ini adalah anak: tulis setiap laporan ke berkas JSON-lines ini.
_ENV_LAPORAN_ANAK = "PILECAP_GUI_LAPORAN_ANAK"

_KUNCI_HASIL_ANAK = pytest.StashKey[dict[str, "_SesiAnak"]]()


class _SesiAnak:
    """Satu proses pytest anak untuk seluruh test terpilih dari satu toolkit."""

    def __init__(self, config: pytest.Config, toolkit: str, nodeids: list[str]) -> None:
        self.config = config
        self.toolkit = toolkit
        self.nodeids = nodeids
        self.laporan: dict[str, list[dict]] | None = None
        self.keluaran = ""
        self.returncode: int | None = None

    def jalankan(self) -> dict[str, list[dict]]:
        if self.laporan is not None:
            return self.laporan
        with tempfile.TemporaryDirectory(prefix=f"pilecap_gui_{self.toolkit}_") as tmp:
            berkas = Path(tmp) / "laporan.jsonl"
            env = {**os.environ, _ENV_LAPORAN_ANAK: str(berkas)}
            argv = [
                sys.executable, "-m", "pytest", *self.nodeids,
                "-p", "no:cacheprovider", "-q", "-o", "addopts=",
            ]  # fmt: skip
            proses = subprocess.run(
                argv,
                cwd=self.config.rootpath,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            self.returncode = proses.returncode
            self.keluaran = proses.stdout + proses.stderr
            self.laporan = {}
            if berkas.exists():
                for baris in berkas.read_text(encoding="utf-8").splitlines():
                    data = json.loads(baris)
                    self.laporan.setdefault(data["nodeid"], []).append(data)
        return self.laporan


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get(_ENV_LAPORAN_ANAK):
        return  # anak hanya pernah menerima test dari satu toolkit
    per_toolkit: dict[str, list[str]] = {}
    for item in items:
        tanda = item.get_closest_marker("gui_toolkit")
        if tanda is not None:
            per_toolkit.setdefault(tanda.args[0], []).append(item.nodeid)
    if len(per_toolkit) < 2:
        return
    sesi = {nama: _SesiAnak(config, nama, ids) for nama, ids in per_toolkit.items()}
    config.stash[_KUNCI_HASIL_ANAK] = {i: s for s in sesi.values() for i in s.nodeids}


def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None) -> bool | None:
    """Untuk test yang diisolasi: putar ulang laporan anak, JANGAN siapkan fixture-nya di sini."""
    sesi = item.config.stash.get(_KUNCI_HASIL_ANAK, {}).get(item.nodeid)
    if sesi is None:
        return None
    laporan = sesi.jalankan()
    hook = item.ihook
    hook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
    tahap: set[str] = set()
    for data in laporan.get(item.nodeid, []):
        rep = item.config.hook.pytest_report_from_serializable(config=item.config, data=data)
        if isinstance(rep.longrepr, list):
            # Laporan skip berupa tuple (berkas, baris, alasan); JSON menjadikannya list,
            # dan junitxml menolak selain tuple.
            rep.longrepr = tuple(rep.longrepr)
        tahap.add(rep.when)
        hook.pytest_runtest_logreport(report=rep)
    if "teardown" not in tahap:
        # pytest SELALU melaporkan teardown; tanpanya anak mati di tengah test ini atau sebelum
        # sampai kepadanya (mis. crash native). Itu kegagalan, bukan lolos diam-diam.
        ekor = "\n".join(sesi.keluaran.splitlines()[-40:])
        pesan = (
            f"proses pytest anak untuk toolkit {sesi.toolkit!r} berhenti sebelum test ini "
            f"selesai (exit {sesi.returncode}). Akhir keluarannya:\n{ekor}"
        )
        rep = pytest.TestReport(
            item.nodeid,
            item.location,
            {k: 1 for k in item.keywords},
            "failed",
            pesan,
            "teardown" if "call" in tahap else "call",
        )
        hook.pytest_runtest_logreport(report=rep)
    hook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True


class _PerekamLaporanAnak:
    """Di proses anak: tulis setiap laporan (setup/call/teardown) ke berkas untuk induk."""

    def __init__(self, config: pytest.Config, berkas: Path) -> None:
        self.config = config
        self.berkas = berkas

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        data = self.config.hook.pytest_report_to_serializable(config=self.config, report=report)
        # Ditulis per laporan, bukan di akhir: bila anak crash di tengah, test yang sudah
        # selesai tetap terlaporkan dan hanya sisanya yang dinyatakan gagal.
        with self.berkas.open("a", encoding="utf-8") as f:
            f.write(json.dumps(data) + "\n")


def pytest_configure(config: pytest.Config) -> None:
    berkas = os.environ.get(_ENV_LAPORAN_ANAK)
    if berkas:
        config.pluginmanager.register(_PerekamLaporanAnak(config, Path(berkas)))
