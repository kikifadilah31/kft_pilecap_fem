"""Ekspor model ke format program lain yang berbasis teks.

Saat ini hanya Midas Civil (`mct.py`). Kerangka di sini disiapkan supaya format berikutnya
-- SAP2000 `.s2k` misalnya -- masuk sebagai modul sejajar, bukan sebagai cabang `if` di
dalam CLI.

.. rubric:: Aturan modul ini

Exporter **hanya menerjemahkan**, tidak pernah menghitung ulang besaran rekayasa. Tekanan
pile diambil dari `fem_engine.pile_pressures`, yaitu fungsi yang sama yang dipakai model
OpenSees. Bila exporter menghitung sendiri `Pz / A_disk`, model yang diekspor dan model
yang dianalisis dapat menyimpang tanpa satu pun test menangkapnya -- dan pengguna akan
membandingkan dua model yang diam-diam berbeda bebannya.
"""

from __future__ import annotations

from pilecap_fem.exporters.mct import write_mct

__all__ = ["write_mct"]
