"""CLI `pilecap-run` -- orkestrator end-to-end mesh -> analyze -> report (PRD Bagian 6.4).

BELUM DIIMPLEMENTASIKAN (Fase 3), karena bergantung pada `pilecap-analyze` (Fase 2)
dan `pilecap-report` (Fase 3).
"""

from __future__ import annotations

import sys

_MESSAGE = """\
`pilecap-run` belum diimplementasikan (dijadwalkan Fase 3).

Command ini menjalankan mesh -> analyze -> report dalam satu folder output, sehingga baru
dapat berfungsi setelah `pilecap-analyze` (Fase 2) dan `pilecap-report` (Fase 3) selesai.

Yang sudah bisa dipakai sekarang: `pilecap-mesh` (geometri + mesh all-quad).
"""


def entry_point(argv: list[str] | None = None) -> int:
    print(_MESSAGE, file=sys.stderr)
    return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
