"""Laporan PDF lengkap satu run, dikompilasi Typst dari dalam Python.

.. rubric:: Aturan modul ini

Generator PDF **hanya menyusun ulang**, tidak pernah menghitung ulang besaran rekayasa --
aturan yang sama dengan `exporters/`. Ia memakai `reporter.CalcSheetInputs`, yaitu objek
yang SAMA PERSIS yang masuk ke `calc_sheet.md`. Bila generator menghitung sendiri, calc
sheet dan PDF dapat menyimpang tanpa satu pun test menangkapnya -- dan yang beredar
sebagai dokumen tercetak dan ditandatangani justru yang kedua.

Alasan yang sama melarang membaca balik CSV hasil: CSV sudah dibulatkan ke satuan
tampilan dan tidak membawa `as_min`, `phi_v_c`, `labels`, maupun `status`.

Blok prosa tetap (`config.KNOWN_LIMITATIONS`, disclaimer, `OPEN_BLOCKERS`, peringatan
deep pilecap) tidak disalin ke bentuk Typst melainkan diterjemahkan saat pembuatan
dokumen lewat `typst_kit.from_markdown`, sehingga sumbernya tetap satu.
"""

from __future__ import annotations

from pilecap_fem.reporting_pdf.document import (
    PdfReportError,
    build_pdf_report,
    preflight,
    render_source,
)
from pilecap_fem.reporting_pdf.model import ReportData
from pilecap_fem.reporting_pdf.typst_kit import TypstMarkupError

__all__ = [
    "PdfReportError",
    "ReportData",
    "TypstMarkupError",
    "build_pdf_report",
    "preflight",
    "render_source",
]
