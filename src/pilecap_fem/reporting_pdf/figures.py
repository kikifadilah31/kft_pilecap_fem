"""Penyediaan gambar untuk dokumen PDF: penemuan, downscale, dan penandaan.

.. rubric:: Tiga hal yang ditangani di sini

1. **Ukuran.** Plot 300 dpi pada figur 14 inci berukuran ~4.150 px. Menanamnya apa adanya
   membuat PDF membengkak tanpa menambah ketajaman yang terlihat, jadi setiap gambar
   dilewatkan `shell_kit.pdf.downscale_figure`. PNG aslinya tidak pernah diubah.

2. **Gambar yang tidak ada.** `--no-rebar-plots`, opsvis yang dilewati karena elemennya
   terlalu banyak, atau `--no-save-raw` membuat sebagian gambar memang tidak pernah dibuat.
   Yang absen **tidak pernah dihilangkan diam-diam**: ia muncul sebagai kotak yang
   menyebutkan berkasnya, alasannya, dan cara memunculkannya. Ruang kosong tanpa keterangan
   akan terbaca sebagai "tidak ada apa-apa di sini", padahal artinya "tidak diperiksa".

3. **Gambar basi.** `pilecap-report` memang dirancang untuk dijalankan ulang. PNG dari
   pelaporan sebelumnya masih ada di disk dan akan ikut tertanam, mungkin dengan tema atau
   DPI yang berbeda. Yang lebih tua daripada run ini ditandai di caption-nya.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from pilecap_fem import config
from pilecap_fem.reporting_pdf import typst_kit as tk

__all__ = ["FigureRef", "FigureStore", "MissingFigure"]

_log = config.get_logger("reporting_pdf")


@dataclass(frozen=True)
class FigureRef:
    """Gambar yang benar-benar ada dan siap dirujuk dokumen."""

    rel_path: str
    caption: str
    stale: bool = False

    def to_typst(self, *, width: str = "100%") -> str:
        caption = self.caption
        if self.stale:
            caption += " _(gambar berasal dari pelaporan sebelumnya, bukan dari run ini)_"
        return tk.figure(self.rel_path, caption, width=width)


@dataclass(frozen=True)
class MissingFigure:
    """Gambar yang tidak ada, beserta alasan yang dapat ditindaklanjuti."""

    name: str
    caption: str
    reason: str

    def to_typst(self, *, width: str = "100%") -> str:
        return tk.callout(
            "NOTE",
            tk.from_markdown(f"**{self.caption}** -- {self.reason}"),
            title="GAMBAR TIDAK TERSEDIA",
        )


Figure = FigureRef | MissingFigure


class FigureStore:
    """Menyiapkan gambar milik satu run dan mencatat yang tidak tersedia.

    `root` kompilasi Typst adalah folder run, sehingga seluruh jalur ditulis relatif
    terhadapnya dalam bentuk POSIX. Typst menolak membaca berkas di luar `root`, dan
    string jalur bergaya Windows tidak sah di dalamnya.
    """

    def __init__(self, run_dir: Path, *, started_at: float) -> None:
        from shell_kit.pdf import PRINT_FIGURE_DIR

        self.run_dir = run_dir
        self.print_dir = run_dir / PRINT_FIGURE_DIR
        self.started_at = started_at
        self.missing: list[MissingFigure] = []
        self.stale: list[str] = []

    # -- API ---------------------------------------------------------------

    def resolve(
        self, path: Path, caption: str, *, reason: str, from_earlier_phase: bool = False
    ) -> Figure:
        """Gambar dari dalam folder run (kontur, envelope, model).

        `from_earlier_phase` menandai gambar yang memang dibuat tahap SEBELUM pelaporan --
        `mesh_plan.png` oleh `pilecap-mesh`, `model_opsvis.png` oleh `pilecap-analyze`.
        Gambar itu selalu lebih tua daripada `pilecap-report` menurut rancangan, sehingga
        memeriksanya terhadap waktu mulai pelaporan akan menandai SETIAP run sebagai basi --
        peringatan yang selalu menyala sama saja dengan tidak ada peringatan.
        """
        if not path.is_file():
            return self._miss(path.name, caption, reason)
        stale = not from_earlier_phase and path.stat().st_mtime < self.started_at
        if stale:
            self.stale.append(path.name)
            _log.warning(
                "%s lebih tua daripada pelaporan ini; ia berasal dari pelaporan sebelumnya "
                "dan tetap ditanam ke PDF dengan penandaan di caption-nya.",
                path.name,
            )
        return FigureRef(self._prepare(path), caption, stale=stale)

    def illustration(self, name: str, caption: str) -> Figure:
        """Ilustrasi tangan dari `docs/img`.

        Disalin lebih dulu ke folder run karena `config.illustrations_dir()` menunjuk ke
        dalam paket terpasang -- di LUAR `root` kompilasi, yang tidak boleh dibaca Typst.
        """
        try:
            src = config.illustrations_dir() / name
        except FileNotFoundError as exc:  # pragma: no cover -- pengemasan rusak
            return self._miss(name, caption, f"folder ilustrasi tidak ditemukan ({exc}).")
        if not src.is_file():
            return self._miss(name, caption, "berkas ilustrasi tidak ada di paket terpasang.")

        self.print_dir.mkdir(parents=True, exist_ok=True)
        salinan = self.print_dir / name
        if not salinan.exists() or salinan.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, salinan)
        return FigureRef(self._prepare_stabil(salinan), caption)

    # -- internal ----------------------------------------------------------

    def _miss(self, name: str, caption: str, reason: str) -> MissingFigure:
        item = MissingFigure(name=name, caption=caption, reason=reason)
        self.missing.append(item)
        _log.warning("gambar %s tidak ada: %s", name, reason)
        return item

    def _prepare_stabil(self, path: Path) -> str:
        """Sama seperti `_prepare`, tetapi nama berkas hasilnya STABIL.

        `downscale_figure` memberi awalan hash yang diturunkan dari jalur absolut
        sumbernya, sehingga gambar yang sama memperoleh nama berbeda di setiap folder
        keluaran. Pada laporan run itu tidak terasa -- foldernya memang baru setiap kali.

        Pada ilustrasi tidak: ilustrasi dipakai panduan, yang sumber `.typ`-nya di-commit
        dan di-diff antarversi. Nama yang berubah-ubah membuat setiap diff memuat satu
        perubahan palsu, dan perubahan palsu yang rutin adalah cara tercepat membuat orang
        berhenti membaca diff.
        """
        rel = self._prepare(path)
        hasil = (self.run_dir / rel).resolve()
        if hasil.name == path.name:
            return rel
        hasil.replace(path)
        return path.resolve().relative_to(self.run_dir.resolve()).as_posix()

    def _prepare(self, path: Path) -> str:
        """Downscale bila perlu, lalu kembalikan jalur relatif gaya POSIX."""
        from shell_kit.pdf import downscale_figure

        if path.suffix.lower() == ".svg":
            dipakai = path  # vektor: memperkecilnya tidak menghemat apa pun
        else:
            self.print_dir.mkdir(parents=True, exist_ok=True)
            dipakai = Path(
                downscale_figure(str(path), str(self.print_dir), max_px=config.PDF_IMAGE_MAX_PX)
            )
        return dipakai.resolve().relative_to(self.run_dir.resolve()).as_posix()
