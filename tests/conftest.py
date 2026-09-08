"""Fixture bersama untuk seluruh test Fase 1."""

from __future__ import annotations

import json
import re
import shutil
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
_STEMPEL_WAKTU = re.compile(rb"/(?:Mod|Creation)Date\(D:[^)]*\)")


def pdf_tanpa_stempel_waktu(data: bytes) -> bytes:
    """PDF dengan stempel waktunya dibuang, supaya dua kompilasi dapat dibandingkan.

    Typst menanam `/ModDate` dan `/CreationDate` dari jam dinding. Dua kompilasi yang
    kebetulan berada di sisi berbeda dari pergantian detik karena itu SELALU berbeda byte,
    berapa pun samanya isi dokumen. Tanpa menormalkannya, test yang membandingkan dua
    kompilasi sesungguhnya menguji jam, bukan apa yang hendak diujinya -- dan ia lolos
    hanya selama dokumennya cukup kecil untuk dikompilasi dua kali dalam satu detik.
    """
    return _STEMPEL_WAKTU.sub(b"", data)


@pytest.fixture
def tanpa_stempel_waktu():
    """Fungsi penormal stempel waktu PDF, dipakai test yang membandingkan dua kompilasi."""
    return pdf_tanpa_stempel_waktu
