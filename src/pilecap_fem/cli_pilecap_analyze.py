"""CLI `pilecap-analyze` -- model OpenSeesPy + analisis semua kombinasi (PRD Bagian 6.2).

BELUM DIIMPLEMENTASIKAN (Fase 2). Entry point sengaja tetap terdaftar agar
`pilecap-analyze --help` memberi tahu status, bukan "command not found".
"""

from __future__ import annotations

import sys

_MESSAGE = """\
`pilecap-analyze` belum diimplementasikan (dijadwalkan Fase 2).

Fase 2 mencakup: math_engine, fem_engine (ShellMITC4 + PlateFiber), postproc_engine,
cek keseimbangan VC-0 di setiap run, serta dua spike wajib yang belum boleh dilewati:

  * verifikasi urutan & jumlah komponen `eleResponse(tag, 'forces')`
    (assert len == n_gauss * 8) terhadap OpenSees versi terpasang;
  * penetapan `config.MOMENT_SIGN_FACTOR` lewat VC-1 dan pembuktian sudut theta
    lewat VC-2 -- keduanya DILARANG ditebak (PRD Bagian 7.1).

Yang sudah bisa dipakai sekarang: `pilecap-mesh` (geometri + mesh all-quad).
"""


def entry_point(argv: list[str] | None = None) -> int:
    print(_MESSAGE, file=sys.stderr)
    return 3


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
