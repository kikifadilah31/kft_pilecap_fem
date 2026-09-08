"""Panduan mandiri `pilecap-fem`: satu dokumen yang menggantikan seluruh dokumentasi daring.

.. rubric:: Mengapa paket ini terpisah dari `reporting_pdf`

`reporting_pdf` memegang satu invarian: segala isinya adalah penyusunan ulang **satu run**,
diambil dari objek yang sama yang menghasilkan `calc_sheet.md`. Seluruh babnya bertipe
terhadap `ReportData`, dan `ReportData` tidak punya satu pun field statis.

Panduan ini tidak punya run sama sekali. Menaruh generator tanpa run di dalam paket itu
akan melemahkan satu-satunya invarian yang melindungi dokumen bertanda tangan. Karena itu
arah impornya satu arah dan tegas: `manual` boleh memakai `reporting_pdf`, tidak pernah
sebaliknya. Dijaga `tests/test_manual.py::test_reporting_pdf_tidak_mengimpor_manual`.

.. rubric:: Mengapa dokumen ini DIHASILKAN, bukan ditulis tangan

Pembacanya adalah orang yang tidak dapat membuka README di GitHub, atau tidak paham
GitHub sama sekali. Bagi mereka dokumen ini bukan pelengkap dokumentasi -- ia satu-satunya
dokumentasi. Dokumen semacam itu tidak boleh basi.

Proyek ini sudah berulang kali digigit dokumentasi yang ditulis tangan lalu tertinggal:
tabel perbandingan README yang basi, caption plot yang basi, rujukan "Bagian 7" yang basi.
Karena itu setiap fakta yang dimiliki kode -- versi, daftar field, keterbatasan, pasal SNI,
pin dependency, nama contoh bawaan -- ditarik hidup-hidup saat dokumen dibangun. Yang
ditulis tangan hanyalah prosa naratifnya, persis seperti `reporting_pdf/theory.py`.

Prosa authored yang berpasangan dengan data hidup SELALU dikunci ke himpunan kunci
hidupnya (`config.EXAMPLE_NAMES`, `config.OPEN_BLOCKERS`, konstanta `FILE_*`), sehingga
contoh atau blocker baru **meledak saat dokumen dibangun** alih-alih hilang diam-diam.

.. rubric:: Satuan

Sama seperti `reporting_pdf`: satuan tidak pernah diketik sebagai literal, selalu diambil
dari `io_utils.display_unit` (PRD Bagian 9.2). Dijaga
`tests/test_manual.py::test_sumber_manual_tidak_mengetik_satuan_sebagai_literal`.
"""

from __future__ import annotations

from pilecap_fem.manual.document import build_manual, render_source

__all__ = ["build_manual", "render_source"]
