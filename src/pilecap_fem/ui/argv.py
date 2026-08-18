"""Susun daftar argumen `pilecap-run` dari nilai formulir.

**TIDAK mengimpor streamlit.** Bersama `schema.py`, modul ini adalah satu-satunya bagian
UI yang dapat salah secara diam-diam -- memancarkan flag yang tidak dikenal CLI -- sehingga
ia harus dapat diuji tanpa extra `[ui]` terpasang.

.. rubric:: Argv yang sama dipakai untuk dua hal

Daftar yang dikembalikan `build_argv` **ditampilkan** ke user lewat `format_command` dan
**dijalankan** apa adanya. Karena keduanya satu objek, perintah yang disalin user tidak
mungkin menyimpang dari yang benar-benar berjalan.

.. rubric:: Nilai bawaan dihilangkan

`DEFAULTS` diambil dari konstanta yang sama dengan parser CLI, bukan disalin. Argumen yang
nilainya sama dengan bawaan tidak dipancarkan, sehingga perintah yang ditampilkan tetap
pendek dan enak dibaca -- yang justru penting bagi user yang sedang belajar CLI-nya.
"""

from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

from pilecap_fem import config

PROG = "pilecap-run"

#: Bawaan parser CLI. Sumbernya `config`, bukan angka yang ditulis ulang di sini.
DEFAULTS: dict[str, Any] = {
    "dpi": config.OUTPUT_DPI,
    "theme": config.DEFAULT_THEME,
    "contour_method": config.DEFAULT_CONTOUR_METHOD,
    "log_level": "INFO",
    "output_dir": "output",
}

#: Flag yang TIDAK PERNAH dipancarkan UI, beserta alasannya.
#:
#: `--preview` memanggil `plt.show()`; di server tanpa display ia menggantung. Justru
#: ketika flag ini tidak diberikan, `renderer.PlotStyle.from_args` memaksa backend Agg.
#:
#: `--wood-armer` memanggil `math_engine.wood_armer` yang SELALU `raise NotImplementedError`
#: (exit code 4). Menampilkannya berarti menawarkan tombol yang dijamin gagal.
FORBIDDEN_FLAGS: tuple[str, ...] = ("--preview", "--wood-armer")


def build_argv(
    config_path: Path,
    input_dir: Path,
    values: dict[str, Any],
) -> list[str]:
    """Argumen untuk `pilecap-run`, tanpa nama program.

    `values` memakai kunci `dest` argparse (`output_dir`, `theme`, `contour_method`, ...),
    bukan kunci config bertitik -- seluruh isi config sudah masuk lewat `--config`.
    """
    argv: list[str] = ["--config", str(config_path), "--input-dir", str(input_dir)]

    def add(flag: str, key: str) -> None:
        value = values.get(key)
        if value is None or value == "":
            return
        if key in DEFAULTS and str(value) == str(DEFAULTS[key]):
            return
        argv.extend([flag, str(value)])

    def add_flag(flag: str, key: str) -> None:
        if values.get(key):
            argv.append(flag)

    add("--output-dir", "output_dir")
    add("--theme", "theme")
    add("--contour-method", "contour_method")
    add("--dpi", "dpi")
    add("--log-level", "log_level")

    # Reaksi pile: kosong berarti biarkan CLI melakukan auto-detect sendiri.
    add("--reactions", "reactions")

    # Kombinasi: `--combo` boleh diulang (action="append").
    for combo in values.get("combo") or ():
        argv.extend(["--combo", str(combo)])

    add("--equilibrium-rtol", "equilibrium_rtol")
    add_flag("--no-custom", "no_custom")
    add_flag("--export-msh", "export_msh")
    add_flag("--opsvis", "opsvis")
    add_flag("--no-save-raw", "no_save_raw")
    add_flag("--no-rebar-plots", "no_rebar_plots")
    add_flag("--no-envelope", "no_envelope")
    add_flag("--pdf", "pdf")

    return argv


def format_command(argv: list[str]) -> str:
    """Perintah lengkap yang dapat disalin ke terminal."""
    return " ".join([PROG, *(shlex.quote(a) for a in argv)])


__all__ = ["DEFAULTS", "FORBIDDEN_FLAGS", "PROG", "build_argv", "format_command"]
