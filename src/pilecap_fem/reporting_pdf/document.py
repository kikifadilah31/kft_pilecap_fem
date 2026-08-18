"""Perakitan dokumen dan pemanggilan kompiler Typst.

Sumber `.typ` SELALU ditulis ke disk, berhasil maupun gagal: ia satu-satunya yang membuat
kegagalan kompilasi dapat didiagnosis, dan satu-satunya bentuk laporan yang dapat di-diff
antar run.
"""

from __future__ import annotations

import time
from pathlib import Path

from pilecap_fem import config
from pilecap_fem.reporting_pdf import chapters, theory
from pilecap_fem.reporting_pdf.figures import FigureStore
from pilecap_fem.reporting_pdf.model import ReportData
from pilecap_fem.reporting_pdf.typst_kit import PREAMBLE
from pilecap_fem.validators import PilecapError

__all__ = ["PdfReportError", "build_pdf_report", "preflight", "render_source"]

_log = config.get_logger("reporting_pdf")

_INSTALL_HINT = """\
Paket '{paket}' tidak ditemukan, sehingga `--pdf` tidak dapat dijalankan.

  Dari clone lokal:
    uv sync

  Instalasi permanen:
    uv tool upgrade pilecap-fem
"""


class PdfReportError(PilecapError):
    """Laporan PDF gagal dibuat. Ditangkap `entry_point` menjadi exit code 2."""


def preflight() -> None:
    """Pastikan kompiler dan pengolah gambar ada SEBELUM plot apa pun digambar.

    Mengikuti pola `--wood-armer`: fitur yang belum dapat dijalankan harus gagal di awal,
    bukan setelah pengguna menunggu seluruh kontur selesai.
    """
    for paket in ("typst", "PIL"):
        try:
            __import__(paket)
        except ImportError as exc:  # pragma: no cover -- lingkungan tanpa dependency
            nama = "pillow" if paket == "PIL" else paket
            raise PdfReportError(_INSTALL_HINT.format(paket=nama)) from exc


def render_source(data: ReportData, figs: FigureStore) -> str:
    """Rakit seluruh dokumen menjadi satu string `.typ`."""
    bagian = [
        PREAMBLE,
        _page_footer(data),
        chapters.cover(data),
        chapters.outline(),
        chapters.chapter_summary(data),
        theory.chapter_theory(figs),
        chapters.chapter_input(data, figs),
        chapters.chapter_combos(data, figs),
        chapters.chapter_envelope(data, figs),
        chapters.chapter_limitations(data),
        chapters.chapter_responsibility(data),
        chapters.appendix_provenance(data),
    ]
    return "\n\n".join(b for b in bagian if b)


def _page_footer(data: ReportData) -> str:
    """Footer tiap halaman: identitas tool + peringatan singkat + nomor halaman.

    Dipasang SETELAH sampul supaya halaman sampul tetap bersih.
    """
    versi = str(data.manifest.get("tool_version", "?"))
    return (
        "#set page(footer: context [\n"
        f"  #set text(size: 7.5pt, fill: luma(90))\n"
        f"  pilecap-fem v{versi} -- alat bantu perhitungan; wajib diperiksa dan disetujui "
        f"engineer yang bertanggung jawab\n"
        "  #h(1fr)\n"
        '  #counter(page).display("1 / 1", both: true)\n'
        "])"
    )


def build_pdf_report(run_dir: Path, data: ReportData) -> Path:
    """Bangun `.typ`, kompilasi ke PDF, dan kembalikan jalur PDF-nya."""
    from shell_kit.pdf import PdfCompileError, compile_to_pdf

    mulai = time.perf_counter()
    figs = FigureStore(run_dir, started_at=data.started_at)
    sumber = render_source(data, figs)

    typ_path = run_dir / config.FILE_PDF_SOURCE
    pdf_path = run_dir / config.FILE_PDF_REPORT
    typ_path.write_text(sumber, encoding="utf-8")

    try:
        _, warnings = compile_to_pdf(str(typ_path), str(pdf_path), root=str(run_dir))
    except PdfCompileError as exc:
        raise PdfReportError(
            f"Typst gagal mengompilasi laporan.\n{exc}\n"
            f"  Sumbernya DIPERTAHANKAN di: {typ_path}\n"
            "  Perbaiki penyebabnya lalu jalankan ulang `pilecap-report --pdf`."
        ) from exc
    except PermissionError as exc:
        raise PdfReportError(
            f"Tidak dapat menulis {pdf_path.name}: berkasnya sedang dibuka program lain "
            "(penampil PDF mengunci berkas di Windows).\n"
            "  Tutup berkasnya lalu jalankan ulang `pilecap-report --pdf`."
        ) from exc

    for w in warnings:
        _log.warning("typst: %s", str(w).replace("\n", " "))
    _peringatkan_gambar(warnings)

    if figs.missing:
        _log.warning(
            "%d gambar tidak tersedia dan muncul sebagai kotak penjelasan di PDF.",
            len(figs.missing),
        )
    ukuran_mb = pdf_path.stat().st_size / 1024 / 1024
    _log.info(
        "Laporan PDF: %s (%.1f MB, %.1f detik, %d gambar hilang)",
        pdf_path.name,
        ukuran_mb,
        time.perf_counter() - mulai,
        len(figs.missing),
    )
    return pdf_path


def _peringatkan_gambar(warnings: list[str]) -> None:
    """Warning gambar/font mendapat pemberitahuan tersendiri.

    Dokumen yang terdegradasi diam-diam -- gambar tak termuat, font tak ter-resolve --
    persis yang dilarang PRD: hasilnya tetap terbit, hanya isinya berkurang.
    """
    tersangka = [w for w in warnings if any(k in w.lower() for k in ("font", "image", "file"))]
    if tersangka:
        _log.warning(
            "PDF mungkin terdegradasi: %d warning menyangkut gambar atau font. "
            "Periksa hasilnya sebelum diedarkan.",
            len(tersangka),
        )
