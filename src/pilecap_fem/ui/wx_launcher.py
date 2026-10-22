"""Peluncur `pilecap-gui`: membuka jendela desktop wxPython.

Cermin `launcher.py`, dengan satu perbedaan penting: tidak ada server dan tidak ada
peramban. Jendela berjalan di proses ini sendiri, sehingga tidak ada port yang dibuka dan
tidak ada apa pun yang disajikan ke jaringan.

wxPython bersifat opsional (extra `[gui]`), jadi ketiadaannya harus berujung petunjuk
pemasangan yang bisa ditindaklanjuti -- bukan traceback `ModuleNotFoundError`.

.. rubric:: Mengapa dua antarmuka hidup berdampingan

Keduanya memakai `schema.py`, `runopts.py`, `argv.py`, dan `preview.py` yang sama, lalu
memanggil CLI sebagai subprocess. Karena config dibangun `schema.build_config` di kedua
jalur, keduanya **tidak dapat** menghasilkan masukan analisis yang berbeda.
"""

from __future__ import annotations

import os
import sys

from pilecap_fem import __version__

#: Folder kerja. Sama dengan `launcher.py` supaya kedua antarmuka menaruh hasil di tempat
#: yang sama persis, yaitu tempat pengguna memanggil perintahnya.
from pilecap_fem.ui.launcher import CWD_ENV

INSTALL_HINT = """\
Paket 'wxpython' tidak ditemukan. Antarmuka desktop bersifat OPSIONAL, sehingga pengguna
CLI tidak ikut memasangnya.

  Dari clone lokal:
    uv sync --extra gui

  Pasang permanen dari rilis:
    uv tool install --python 3.12 --force "pilecap-fem[gui] @ <URL wheel rilis>"

Antarmuka berbasis peramban tetap tersedia tanpa wxPython:
    pilecap-ui
"""


def wx_available() -> bool:
    """True bila `wx` dapat diimpor."""
    try:
        import wx  # noqa: F401
    except ImportError:
        return False
    return True


def launch(argv: list[str] | None = None) -> int:
    """Buka jendela desktop. Mengembalikan exit code.

    `argv` diterima agar tanda tangannya seragam dengan `entry_point` CLI lain, tetapi tidak
    dipakai: seluruh masukan diisi lewat formulir, bukan lewat baris perintah.
    """
    if not wx_available():
        print(INSTALL_HINT)
        return 1

    # Diimpor SETELAH pemeriksaan di atas: modul ini harus dapat diimpor -- dan diuji --
    # pada lingkungan tanpa wxPython, sama seperti `launcher.py` tanpa streamlit.
    from pilecap_fem.ui.wxgui.main import run_app

    # `setdefault`, bukan penimpaan: nilai yang sudah ada dihormati, sehingga test dapat
    # mengarahkan folder kerja tanpa harus mengubah cwd prosesnya sendiri. Nilai efektifnya
    # dipakai ulang untuk banner di bawah -- mencetak `os.getcwd()` di sana akan menyebut
    # folder yang BERBEDA dari yang dipakai `wxgui.main.WORKDIR` persis pada kasus itu.
    #
    # Berbeda dari `launcher.py`, yang memang menimpanya: di sana variabel ini adalah
    # saluran induk-ke-anak menuju proses Streamlit, sedangkan di sini tidak ada proses anak
    # untuk formulirnya.
    workdir = os.environ.setdefault(CWD_ENV, os.getcwd())

    print(f"PILECAP-FEM v{__version__} - antarmuka desktop")
    print(f"Folder kerja : {workdir}")
    print("Hasil disimpan di folder itu, sama seperti menjalankan CLI langsung.")
    print("Tutup jendelanya untuk keluar.")
    sys.stdout.flush()

    return run_app()


def entry_point(argv: list[str] | None = None) -> int:
    return launch(argv)


__all__ = ["CWD_ENV", "INSTALL_HINT", "entry_point", "launch", "wx_available"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
