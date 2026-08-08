"""pilecap-fem — Automated pile cap plate-bending analyzer (gmsh + OpenSeesPy)."""

import sys

#: Rentang interpreter yang didukung, sama dengan `requires-python` di pyproject.toml.
REQUIRED_PYTHON: tuple[tuple[int, int], tuple[int, int]] = ((3, 12), (3, 13))


def _check_interpreter() -> None:
    """Hentikan lebih awal bila interpreter di luar rentang yang didukung.

    Tanpa ini, Python yang keliru gagal jauh di hilir dengan pesan yang menyesatkan::

        RuntimeError: Failed to import openseespy on Windows:
        DLL load failed while importing opensees

    Pesan itu terbaca seperti instalasi yang rusak, padahal penyebabnya interpreter:
    `openseespy` hanya menyediakan binary untuk CPython 3.12.

    Pemeriksaan ini DIPERLUKAN meskipun `requires-python` sudah disetel, karena
    `uvx`/`uv tool install` dari sumber **git** memilih interpreter SEBELUM metadata
    paket diketahui -- terbukti memakai Python 3.14 dan tetap memasang paketnya.
    """
    low, high = REQUIRED_PYTHON
    current = sys.version_info[:2]
    if low <= current < high:
        return
    raise RuntimeError(
        f"pilecap-fem membutuhkan Python {low[0]}.{low[1]}.x, "
        f"terdeteksi {sys.version.split()[0]}.\n"
        "  openseespy hanya menyediakan binary untuk CPython 3.12; versi lain akan "
        "terpasang tetapi GAGAL saat diimpor.\n"
        "  Sebutkan interpreternya secara eksplisit:\n"
        "    uvx --python 3.12 --from git+https://github.com/kikifadilah31/kft_pilecap_fem "
        "pilecap-run\n"
        "    uv tool install --python 3.12 "
        "git+https://github.com/kikifadilah31/kft_pilecap_fem"
    )


_check_interpreter()

#: SATU-SATUNYA tempat versi ditulis. `pyproject.toml` membacanya lewat
#: `[tool.hatch.version]`, dan `provenance.Manifest` merekamnya sebagai `tool_version`
#: di setiap `run_manifest.json`. Menyimpan versi di dua tempat pernah membuat seluruh
#: laporan mengklaim v0.1.0 padahal tool sudah v0.3.0 -- dijaga oleh
#: `tests/test_packaging.py`.
__version__ = "0.6.0"
