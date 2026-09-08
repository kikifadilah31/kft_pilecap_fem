"""CLI `pilecap-manual` -- hasilkan panduan mandiri untuk versi yang sedang terpasang.

.. rubric:: Mengapa ini sebuah command, bukan skrip rilis

Panduan diedarkan sebagai PDF beku, sementara perangkat lunaknya terus berubah. Pembaca
yang memegang panduan versi lama sambil menjalankan versi baru adalah risiko yang nyata,
dan satu-satunya akar perbaikannya adalah membuat panduan dapat dihasilkan ulang **dari
paket yang benar-benar terpasang**. Skrip yang hanya ada di repo tidak dapat melakukannya
bagi pengguna yang menerima wheel saja -- justru pengguna yang paling membutuhkannya.

Impor berat sengaja ditahan di dalam `run()`: `--version` dan `--help` harus tetap ringan,
dan keduanya diuji oleh `tests/test_packaging.py`.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pilecap_fem import __version__, config
from pilecap_fem.validators import PilecapError

_log = config.get_logger("cli_pilecap_manual")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pilecap-manual",
        description="Hasilkan panduan lengkap pilecap-fem dalam bentuk Typst dan PDF.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("panduan"),
        help="Folder tempat panduan ditulis",
    )
    parser.add_argument(
        "--typ-only",
        action="store_true",
        help="Tulis sumber Typst saja, tanpa mengompilasi PDF",
    )
    parser.add_argument(
        "--no-strict",
        action="store_true",
        help="Tetap terbitkan meskipun ada bagian yang tidak lengkap",
    )
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    parser.add_argument("--version", action="version", version=f"pilecap-fem {__version__}")
    return parser


def run(args: argparse.Namespace) -> Path:
    """Bangun panduan; kembalikan jalur berkas terakhir yang ditulis."""
    from pilecap_fem.manual import build_manual

    config.setup_logging(level=args.log_level)
    _log.info("pilecap-fem v%s | menyusun panduan", __version__)

    typ_path, pdf_path = build_manual(args.out, strict=not args.no_strict, typ_only=args.typ_only)
    _log.info("Sumber panduan: %s", typ_path)
    return pdf_path or typ_path


def entry_point(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        hasil = run(args)
    except PilecapError as exc:
        logging.getLogger("pilecap_fem").error("%s", exc)
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        if args.log_level == "DEBUG":
            raise
        return 2
    print(f"\nOK -> {hasil}")
    return 0


__all__ = ["build_parser", "entry_point", "run"]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
