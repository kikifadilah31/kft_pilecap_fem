"""Ilustrasi SVG menjadi PNG, dengan cache. TIDAK mengimpor toolkit apa pun.

.. rubric:: Mengapa Typst, bukan perender SVG milik toolkit

Upaya pertama memakai ``wx.svg`` dan **gagal secara diam-diam** -- yang jauh lebih buruk
daripada gagal terang-terangan. ``wx.svg`` memakai nanosvg, yang tidak merender ``<text>``
dan tidak membaca blok ``<style>`` berkelas. Seluruh ilustrasi di repo ini memakai keduanya:
``sistem-koordinat.svg`` sendiri punya 18 label dan mengambil setiap warna garisnya dari satu
blok ``<style>``. Hasil render-nya DIUKUR: tiga kepala panah di atas bidang hitam, tanpa satu
pun label dan tanpa satu pun garis.

Ilustrasi tanpa label dan tanpa warna bukan versi sederhana dari gambarnya -- ia gambar yang
lain. Pada alat yang dipakai untuk desain nyata di lapangan, gambar yang menyesatkan lebih
berbahaya daripada tidak ada gambar.

Typst sudah terkunci sebagai dependency (``typst==0.15.0``) dan sudah merasterisasi
ilustrasi yang sama persis untuk laporan PDF, jadi ia tidak menambah apa pun pada pemasangan
dan hasilnya dijamin sama dengan yang dilihat pengguna di PDF.

.. rubric:: Mengapa ada cache

Kompilasi satu ilustrasi makan ~3,3 detik (DIUKUR). Itu tidak boleh dibayar setiap kali
formulir dibuka, dan sama sekali tidak boleh dibayar di thread GUI.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from pathlib import Path

from pilecap_fem import __version__, config

_log = logging.getLogger(__name__)

#: Folder cache. Diberi cap versi supaya ilustrasi yang berubah antar rilis tidak terbaca
#: dari cache rilis sebelumnya. Boleh hilang kapan saja -- ia akan dibangun ulang.
CACHE_DIR = Path(tempfile.gettempdir()) / f"pilecap-fem-ilustrasi-{__version__}"


def _kunci(sumber: Path, lebar: int) -> str:
    """Nama berkas cache: ikut berubah bila SVG-nya diubah atau lebarnya berbeda.

    Memakai mtime, bukan isi berkas, karena membaca seluruh SVG hanya untuk memutuskan
    apakah perlu membacanya meniadakan gunanya cache.
    """
    sidik = f"{sumber.name}|{lebar}|{sumber.stat().st_mtime_ns}"
    return hashlib.sha256(sidik.encode()).hexdigest()[:16]


def png_untuk(nama: str, *, lebar: int = 560) -> Path:
    """Jalur PNG ilustrasi `nama` selebar `lebar` piksel, dirasterisasi bila perlu.

    Memunculkan `FileNotFoundError` bila ilustrasinya tidak ada di paket terpasang, dan
    meneruskan kegagalan Typst apa adanya. Pemanggil di GUI yang memutuskan cara
    menurunkannya; modul ini tidak menelan galat, karena ia juga dipakai di luar GUI.
    """
    sumber = config.illustrations_dir() / nama
    if not sumber.is_file():
        raise FileNotFoundError(f"ilustrasi {nama} tidak ada di paket terpasang")

    tujuan = CACHE_DIR / f"{_kunci(sumber, lebar)}.png"
    if tujuan.is_file():
        return tujuan

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Typst hanya boleh membaca di dalam `root` kompilasi, sedangkan ilustrasinya ada di
    # dalam paket terpasang. Jadi disalin dulu -- alasan yang sama persis dengan
    # `reporting_pdf.figures.FigureSet.illustration`.
    salinan = CACHE_DIR / nama
    shutil.copy2(sumber, salinan)

    # `width` dalam pt dengan ppi 72 memberi lebar piksel 1:1, sehingga `lebar` benar-benar
    # berarti piksel dan bukan satuan yang harus dikonversi pemanggil.
    typ = CACHE_DIR / f"{tujuan.stem}.typ"
    typ.write_text(
        "#set page(width: auto, height: auto, margin: 0pt, fill: white)\n"
        f'#image("{nama}", width: {lebar}pt)\n',
        encoding="utf-8",
    )

    # Impor berat; hanya dibayar saat cache meleset.
    import typst

    sementara = tujuan.with_suffix(".tmp.png")
    typst.compile(typ, output=sementara, format="png", ppi=72, root=CACHE_DIR)
    # Diganti nama setelah selesai: PNG setengah jadi yang sudah bernama final akan
    # dianggap sah oleh pemanggil berikutnya selamanya.
    sementara.replace(tujuan)
    _log.debug("ilustrasi %s dirasterisasi ke %s", nama, tujuan)
    return tujuan


__all__ = ["CACHE_DIR", "png_untuk"]
