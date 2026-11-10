"""Ekspor model ke format program lain yang berbasis teks.

Midas Civil (`mct.py`) dan SAP2000 (`s2k.py`), sebagai modul sejajar -- bukan sebagai
cabang `if` di dalam CLI.

.. rubric:: Aturan modul ini

Exporter **hanya menerjemahkan**, tidak pernah menghitung ulang besaran rekayasa. Tekanan
pile diambil dari `fem_engine.pile_pressures`, yaitu fungsi yang sama yang dipakai model
OpenSees. Bila exporter menghitung sendiri `Pz / A_disk`, model yang diekspor dan model
yang dianalisis dapat menyimpang tanpa satu pun test menangkapnya -- dan pengguna akan
membandingkan dua model yang diam-diam berbeda bebannya.
"""

from __future__ import annotations

from pilecap_fem.exporters.mct import write_mct
from pilecap_fem.exporters.s2k import write_s2k

__all__ = ["write_mct", "write_s2k"]
