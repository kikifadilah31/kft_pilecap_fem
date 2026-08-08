"""Peluncur `pilecap-ui`: menyalakan server Streamlit pada `app.py`.

Streamlit bersifat opsional (extra `[ui]`), jadi ketiadaannya harus berujung petunjuk
pemasangan yang bisa ditindaklanjuti -- bukan traceback `ModuleNotFoundError`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from pilecap_fem import __version__

#: Folder kerja diteruskan lewat environment, bukan diandalkan dari `os.getcwd()` di dalam
#: `app.py`: Streamlit menjalankan skrip halaman dengan direktori aktifnya sendiri, dan
#: hasil analisis harus mendarat di tempat user memanggil `pilecap-ui` -- sama seperti
#: menjalankan CLI langsung.
CWD_ENV = "PILECAP_UI_CWD"

INSTALL_HINT = """\
Paket 'streamlit' tidak ditemukan. Antarmuka grafis bersifat OPSIONAL, sehingga pengguna
CLI tidak ikut memasangnya.

  Dari clone lokal:
    uv sync --extra ui

  Pasang permanen dari GitHub:
    uv tool install --python 3.12 "pilecap-fem[ui] @ git+https://github.com/kikifadilah31/kft_pilecap_fem"

  Jalankan sekali tanpa memasang:
    uvx --python 3.12 --with streamlit \\
        --from git+https://github.com/kikifadilah31/kft_pilecap_fem pilecap-ui
"""


def streamlit_available() -> bool:
    """True bila `streamlit` dapat diimpor."""
    try:
        import streamlit  # noqa: F401
    except ImportError:
        return False
    return True


def launch(argv: list[str] | None = None) -> int:
    """Jalankan server Streamlit. Mengembalikan exit code.

    `argv` diterima agar tanda tangannya seragam dengan `entry_point` CLI lain, tetapi
    tidak dipakai: seluruh masukan diisi lewat formulir, bukan lewat baris perintah.
    """
    if not streamlit_available():
        print(INSTALL_HINT)
        return 1

    app_path = Path(__file__).parent / "app.py"
    env = dict(os.environ)
    env[CWD_ENV] = os.getcwd()

    print("=" * 64)
    print(f"PILECAP-FEM v{__version__} - ANTARMUKA GRAFIS")
    print("=" * 64)
    print(f"Folder kerja : {os.getcwd()}")
    print("Hasil disimpan di folder itu, sama seperti menjalankan CLI langsung.")
    print("Alamat       : http://localhost:8501 (hanya mesin ini)")
    print("Tutup jendela terminal ini untuk menghentikan server.")
    print()

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_path),
            # Mengikat HANYA ke localhost. Tanpa ini Streamlit menyajikan formulir --
            # beserta seluruh data proyek di dalamnya -- ke seluruh jaringan lokal.
            # User meminta alat yang berjalan offline; ini bagian dari memenuhinya.
            "--server.address=localhost",
            "--browser.gatherUsageStats=false",
        ],
        env=env,
        cwd=os.getcwd(),
        check=False,
    )
    return result.returncode


def entry_point(argv: list[str] | None = None) -> int:
    return launch(argv)


__all__ = ["CWD_ENV", "INSTALL_HINT", "entry_point", "launch", "streamlit_available"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
