"""CLI `pilecap-report` -- post-processing, plot, dan laporan (PRD Bagian 6.3).

BELUM DIIMPLEMENTASIKAN (Fase 3).
"""

from __future__ import annotations

import sys

_MESSAGE = """\
`pilecap-report` belum diimplementasikan (dijadwalkan Fase 3).

Fase 3 mencakup: kontur momen & geser, envelope antar kombinasi, calc_sheet.md dan
SUMMARY.md auditable. Sebagian isinya menunggu jawaban blocker PRD Bagian 17 item 2, 3,
5, dan 18 (standar desain, pasal penampang kritis & kapasitas geser, kriteria deep pile
cap, redaksi disclaimer). Sampai itu terjawab, laporan hanya menampilkan DEMAND dan
kapasitas berstatus NOT_EVALUATED.

Yang sudah bisa dipakai sekarang: `pilecap-mesh` (geometri + mesh all-quad).
"""


def entry_point(argv: list[str] | None = None) -> int:
    print(_MESSAGE, file=sys.stderr)
    return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
