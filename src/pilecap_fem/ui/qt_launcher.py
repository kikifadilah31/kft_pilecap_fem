"""Peluncur `pilecap-qt`: membuka jendela desktop PySide6. EKSPERIMENTAL.

Antarmuka ketiga, disediakan untuk dibandingkan dengan `pilecap-gui` (wxPython) dan
`pilecap-ui` (Streamlit) sebelum salah satunya dipilih. Cermin `wx_launcher.py`: tidak ada
server, tidak ada peramban, dan ketiadaan PySide6 berujung petunjuk pemasangan -- bukan
traceback `ModuleNotFoundError`.

Ketiga antarmuka memakai `schema.py`, `runopts.py`, `argv.py`, `formstate.py`, `desktop.py`,
dan `runner.py` yang sama, sehingga ketiganya **tidak dapat** menghasilkan masukan analisis
yang berbeda.
"""

from __future__ import annotations

import os
import sys

from pilecap_fem import __version__

#: Folder kerja. Sama dengan kedua peluncur lain supaya ketiganya menaruh hasil di tempat yang
#: sama persis, yaitu tempat pengguna memanggil perintahnya.
from pilecap_fem.ui.launcher import CWD_ENV

INSTALL_HINT = """\
Paket 'PySide6' tidak ditemukan. Antarmuka Qt bersifat OPSIONAL (dan masih eksperimental),
sehingga pengguna CLI tidak ikut memasangnya.

  Dari clone lokal:
    uv sync --extra qt

  Pasang permanen dari rilis:
    uv tool install --python 3.12 --force "pilecap-fem[qt] @ <URL wheel rilis>"

Antarmuka lain tetap tersedia:
    pilecap-gui   (jendela wxPython, extra `gui`)
    pilecap-ui    (formulir peramban, extra `ui`)
"""


def qt_available() -> bool:
    """True bila `PySide6.QtWidgets` dapat diimpor."""
    try:
        import PySide6.QtWidgets  # noqa: F401
    except ImportError:
        return False
    return True


def launch(argv: list[str] | None = None) -> int:
    """Buka jendela desktop. Mengembalikan exit code.

    `argv` diterima agar tanda tangannya seragam dengan `entry_point` CLI lain, tetapi tidak
    dipakai: seluruh masukan diisi lewat formulir, bukan lewat baris perintah.
    """
    if not qt_available():
        print(INSTALL_HINT)
        return 1

    # Diimpor SETELAH pemeriksaan di atas: modul ini harus dapat diimpor -- dan diuji -- pada
    # lingkungan tanpa PySide6, sama seperti `wx_launcher.py` tanpa wxPython.
    from pilecap_fem.ui.qtgui.main import run_app

    # Nilai efektifnya yang dicetak, bukan `os.getcwd()`: keduanya berbeda persis ketika
    # `PILECAP_UI_CWD` sudah disetel (lihat `wx_launcher.launch`).
    workdir = os.environ.setdefault(CWD_ENV, os.getcwd())

    print(f"PILECAP-FEM v{__version__} - antarmuka desktop Qt (eksperimental)")
    print(f"Folder kerja : {workdir}")
    print("Hasil disimpan di folder itu, sama seperti menjalankan CLI langsung.")
    print("Tutup jendelanya untuk keluar.")
    sys.stdout.flush()

    return run_app()


def entry_point(argv: list[str] | None = None) -> int:
    return launch(argv)


__all__ = ["CWD_ENV", "INSTALL_HINT", "entry_point", "launch", "qt_available"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
