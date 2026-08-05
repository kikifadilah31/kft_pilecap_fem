"""CLI `pilecap-run` -- orkestrator end-to-end mesh -> analyze -> report (PRD Bagian 6.4).

Ini adalah command utama untuk pemakaian normal.

Implementasinya sengaja **tipis**: memanggil `pilecap-analyze` lalu `pilecap-report`
pada folder run yang sama, tanpa jalur kode ketiga. `pilecap-analyze` sudah mencakup
meshing, sehingga menyalin ulang tahapannya di sini hanya akan menciptakan dua rantai
yang bisa menyimpang diam-diam -- justru kelas kesalahan yang paling sulit terlihat.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from pilecap_fem import (
    cli_pilecap_analyze,
    cli_pilecap_mesh,
    cli_pilecap_report,
    config,
)
from pilecap_fem.validators import PilecapError

_log = config.get_logger("cli_pilecap_run")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pilecap-run",
        description="Jalankan mesh -> analyze -> report dalam satu folder output.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Disusun dari helper yang SAMA dengan kedua CLI aslinya, sehingga tidak ada
    # daftar argumen kedua yang harus dijaga tetap sinkron.
    cli_pilecap_mesh.add_common_arguments(parser)
    cli_pilecap_mesh.add_mesh_arguments(parser)
    parser.add_argument("--preview", action="store_true", help="Tampilkan plot mesh interaktif")
    cli_pilecap_analyze.add_analysis_arguments(parser)
    cli_pilecap_report.add_report_arguments(parser)
    return parser


def run(args: argparse.Namespace, command: str) -> Path:
    run_dir = cli_pilecap_analyze.run(args, command)

    report_args = cli_pilecap_report.build_parser().parse_args([])
    report_args.result_dir = run_dir
    report_args.output_dir = args.output_dir
    report_args.strips_x = args.strips_x
    report_args.strips_y = args.strips_y
    report_args.moment_at = args.moment_at
    report_args.wood_armer = args.wood_armer
    report_args.no_envelope = args.no_envelope
    report_args.dpi = args.dpi
    report_args.log_level = args.log_level
    # Input baru saja dibaca oleh tahap analisis pada proses yang sama; memeriksa
    # hash-nya lagi hanya membuang waktu tanpa menambah jaminan apa pun.
    report_args.no_verify_hash = True

    cli_pilecap_report.run(report_args, command)
    _log.info("pilecap-run selesai -> %s", run_dir)
    return run_dir


def entry_point(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = "pilecap-run " + " ".join(argv if argv is not None else sys.argv[1:])
    try:
        if cli_pilecap_mesh.handle_init_example(args):
            return 0
        run_dir = run(args, command.strip())
    except NotImplementedError as exc:
        print(f"\nBELUM TERSEDIA: {exc}", file=sys.stderr)
        return 4
    except PilecapError as exc:
        logging.getLogger("pilecap_fem").error("%s", exc)
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        if args.log_level == "DEBUG":
            raise
        return 2
    print(f"\nOK -> {run_dir}")
    return 0


__all__ = ["build_parser", "entry_point", "run"]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
