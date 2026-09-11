"""Perakitan panduan dan pemanggilan kompiler Typst.

Kompilasinya sendiri dipinjam dari `reporting_pdf.document.compile_document`, sehingga
perlakuan terhadap kegagalan -- sumber `.typ` yang selalu dipertahankan, PDF yang terkunci
penampil, warning yang dicatat -- persis sama dengan laporan run.
"""

from __future__ import annotations

import time
from pathlib import Path

from pilecap_fem import __version__, config
from pilecap_fem.manual import chapters, config_reference
from pilecap_fem.reporting_pdf import chapters as bab_laporan
from pilecap_fem.reporting_pdf import theory
from pilecap_fem.reporting_pdf import typst_kit as tk
from pilecap_fem.reporting_pdf.document import PdfReportError, compile_document, preflight
from pilecap_fem.reporting_pdf.figures import FigureStore

__all__ = ["build_manual", "render_source"]

_log = config.get_logger("manual")

#: Perintah yang menghasilkan dokumen ini, dipakai di komentar kepala `.typ` dan di pesan
#: galat. Ditulis sekali supaya keduanya tidak dapat menyimpang.
RERUN_HINT = "pilecap-manual"


def render_source(figs: FigureStore, degradasi: list[str] | None = None) -> str:
    """Rakit seluruh panduan menjadi satu string `.typ`.

    `degradasi` menampung hal-hal yang membuat dokumen kurang lengkap tetapi tidak
    menggagalkan pembuatannya (mis. daftar pilihan yang tidak dapat dibaca). Pemanggil
    yang berjalan ketat memakainya untuk menolak menerbitkan panduan yang bolong.
    """
    catat = [] if degradasi is None else degradasi
    bagian = [
        tk.preamble(
            regenerated_by=RERUN_HINT,
            source_note="Isinya ditarik dari kode versi ini; jangan disunting terpisah.",
        ),
        tk.page_footer(version=__version__, note=config.FOOTER_NOTE),
        chapters.cover(),
        bab_laporan.outline(),
        chapters.chapter_executive(figs),
        chapters.chapter_install(),
        chapters.chapter_first_run(),
        chapters.chapter_input_data(figs),
        config_reference.chapter_config(figs, catat),
        theory.chapter_theory(figs),
        chapters.chapter_output(),
        chapters.chapter_evidence(figs),
        bab_laporan.chapter_limitations(),
        chapters.chapter_responsibility(),
        chapters.appendix_capacity(),
        chapters.appendix_commands(),
        chapters.appendix_comparison(figs),
    ]
    return "\n\n".join(b for b in bagian if b)


def build_manual(
    out_dir: Path, *, strict: bool = True, typ_only: bool = False
) -> tuple[Path, Path | None]:
    """Bangun `.typ` panduan dan -- kecuali `typ_only` -- kompilasi PDF-nya.

    `strict` MENOLAK menerbitkan panduan yang terdegradasi. Itu disengaja: panduan yang
    diam-diam kehilangan daftar nilai sah sebuah field, atau kehilangan gambarnya, lebih
    berbahaya daripada tidak ada panduan sama sekali -- pembacanya tidak punya README
    untuk memeriksa silang.
    """
    mulai = time.perf_counter()
    if not typ_only:
        preflight()

    out_dir.mkdir(parents=True, exist_ok=True)
    # `started_at=0.0`: panduan bukan milik satu run, sehingga tidak ada gambar yang dapat
    # "lebih tua daripada run ini". Ilustrasinya memang berumur sama dengan paketnya.
    figs = FigureStore(out_dir, started_at=0.0)

    degradasi: list[str] = []
    sumber = render_source(figs, degradasi)
    degradasi += [f"gambar {m.name} tidak tersedia: {m.reason}" for m in figs.missing]
    if degradasi and strict:
        rincian = "\n".join(f"  - {d}" for d in degradasi)
        raise PdfReportError(
            f"Panduan tidak lengkap, sehingga tidak diterbitkan:\n{rincian}\n"
            "  Perbaiki penyebabnya, atau jalankan dengan --no-strict bila Anda memang "
            "menerima panduan yang berkurang isinya."
        )
    for d in degradasi:
        _log.warning("panduan terdegradasi: %s", d)

    typ_path = out_dir / config.FILE_MANUAL_SOURCE
    pdf_path = out_dir / config.FILE_MANUAL_REPORT

    if typ_only:
        typ_path.write_text(sumber, encoding="utf-8")
        _log.info("Sumber panduan: %s", typ_path)
        return typ_path, None

    compile_document(
        sumber, typ_path, pdf_path, root=out_dir, rerun_hint=RERUN_HINT, label="panduan"
    )
    _log.info(
        "Panduan: %s (%.1f MB, %.1f detik)",
        pdf_path.name,
        pdf_path.stat().st_size / 1024 / 1024,
        time.perf_counter() - mulai,
    )
    return typ_path, pdf_path
