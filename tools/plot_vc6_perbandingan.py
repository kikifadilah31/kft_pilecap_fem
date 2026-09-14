"""Hasilkan gambar perbandingan per elemen: pilecap-fem vs Midas Civil (VC-6).

Menghasilkan, untuk SETIAP kombinasi beban x SETIAP gaya (5 x 2 = 10 pasang):

* `vc6-sebaran-<gaya>-<slug>.png` -- struktur selisih + sebaran kumulatifnya, keempat
  contoh bertumpuk dalam satu gambar sehingga dapat langsung dibandingkan.
* `vc6-peta-<gaya>-<slug>.png` -- kisi 2x2 letak selisih pada denah, satu panel per contoh.

plus `vc6-ringkasan.json`: RMS/p50/p99/maksimum tiap (contoh, kombinasi, gaya). Panduan
membaca berkas itu untuk tabelnya, sehingga angka di dokumen berasal dari perhitungan yang
SAMA dengan gambarnya dan tidak dapat menyimpang darinya.

.. rubric:: Mengapa ini skrip, bukan bagian dari paket

Data pembandingnya ada di `tests/data/vc6/`, yang TIDAK ikut ke dalam wheel -- ia arsip
verifikasi, bukan bagian dari alat. Karena itu keluarannya dihasilkan sekali di sini lalu
di-commit ke `docs/img/`, sama seperti ilustrasi lain yang dipakai README dan panduan.

.. rubric:: Mengapa memakai ulang `validation_helpers`

Gambar ini harus menunjukkan hal yang SAMA dengan yang diukur gate VC-6. Menulis pembaca
Midas kedua di sini berarti dua jalur yang dapat menyimpang diam-diam -- dan gambar yang
menyatakan kesesuaian lebih baik daripada yang sesungguhnya diuji adalah kegagalan yang
jauh lebih buruk daripada tidak ada gambar. Seluruh pembacaan, rekonsiliasi tanda geser,
dan pemilihan baris centroid karena itu diambil dari modul yang dipakai test.

Jalankan dari akar repo::

    uv run python tools/plot_vc6_perbandingan.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tests"))

import validation_helpers as vh  # noqa: E402
from test_validation_cases import (  # noqa: E402
    VC6_DATA,
    VC6_KASUS,
    VC6_KOMBINASI,
    _vc6_jalankan,
)

from pilecap_fem import config, io_utils  # noqa: E402

KELUARAN = REPO / "docs" / "img"
TEMA = config.THEMES["light"]

#: Gaya dalam yang dibandingkan. Urutannya sama dengan urutan pemeriksaan di gate VC-6.
MEDAN: tuple[str, ...] = ("m_xx", "m_yy", "m_xy", "q_x", "q_y")

#: Nama tampilan tiap gaya, dalam notasi math Typst/matplotlib.
LABEL_MEDAN: dict[str, str] = {
    "m_xx": "$m_{xx}$",
    "m_yy": "$m_{yy}$",
    "m_xy": "$m_{xy}$",
    "q_x": "$q_x$",
    "q_y": "$q_y$",
}

#: Sisi terpanjang gambar [piksel]. Disamakan dengan `config.PDF_IMAGE_MAX_PX`, bukan
#: dipilih bebas: panduan menurunkan skala setiap gambar ke nilai itu, sehingga
#: menghasilkan sumber yang lebih besar berarti membayar byte dua kali -- sekali di repo,
#: sekali lagi saat diturunkan skalanya.
LEBAR_PX = config.PDF_IMAGE_MAX_PX

WARNA = {"ex01": "#1f5f9c", "ex02": "#b45309", "ex03": "#15803d", "ex04": "#8b1e1e"}
JUDUL_KASUS = {
    "ex01": "ex01 - 4 tiang",
    "ex02": "ex02 - 12 tiang",
    "ex03": "ex03 - poligon",
    "ex04": "ex04 - tiang menindih pier",
}


def nama_berkas(jenis: str, medan: str, slug: str) -> str:
    """Nama berkas gambar. Dipakai skrip ini DAN dijaga test panduan."""
    return f"vc6-{jenis}-{medan}-{slug}.png"


# ---------------------------------------------------------------------------
# Pemuatan & besaran
# ---------------------------------------------------------------------------


def _muat(kasus: str, combo: str, slug: str):
    """Hasil kami + hasil Midas untuk satu kasus & kombinasi, sudah sejajar.

    Mengembalikan resultan per ELEMEN dan lendutan per NODE. Keduanya diambil dengan cara
    yang sama persis seperti gate VC-6: resultan dari baris centroid ekspor global, lendutan
    dari `midas_nodal` yang menolak berkas yang isinya ternyata bukan lendutan.
    """
    mesh, mentah, kami, _ = _vc6_jalankan(kasus, combo)
    rows = vh.load_midas_centroid(VC6_DATA / kasus / "midas_force_global.csv", slug)
    if list(rows.index) != [int(t) for t in mesh.elem_tags]:
        raise SystemExit(f"{kasus}: penomoran elemen Midas tidak lagi 1:1 dengan mesh tersimpan")

    jenis, tabel = vh.midas_nodal(VC6_DATA / kasus / "midas_displacement.csv", slug)
    if jenis != "displacement":
        raise SystemExit(f"{kasus}: berkas lendutan ternyata berisi {jenis}")
    tag_ke_indeks = {int(t): i for i, t in enumerate(mesh.node_tags)}
    indeks = [tag_ke_indeks[int(t)] for t in tabel.index]
    lendutan = {
        "xy": mesh.node_xy[indeks],
        "kami": mentah.displacements[indeks, 2],
        "midas": tabel["DZ(m)"].to_numpy(dtype=np.float64),
    }
    return mesh, kami, vh.midas_resultants_si(rows), lendutan


def _selisih_relatif(midas: np.ndarray, kami: np.ndarray) -> np.ndarray:
    """Selisih per elemen dalam persen terhadap PUNCAK, sama seperti gate VC-6.

    Dibagi puncak, bukan nilai per titik: di dekat garis nol momen kedua program sama-sama
    benar tetapi rasio per titiknya tak terhingga.
    """
    return (midas - kami) / float(np.max(np.abs(kami))) * 100.0


def _angka(nilai: float, desimal: int = 0) -> str:
    """Format angka gaya Indonesia: titik ribuan, koma desimal."""
    teks = f"{nilai:,.{desimal}f}"
    return teks.translate(str.maketrans({",": ".", ".": ","}))


def _tanda(nilai: float) -> str:
    """Persentase bertanda, koma desimal gaya Indonesia."""
    return f"{'+' if nilai >= 0 else ''}{_angka(nilai, 2)}%"


def _fitur_terdekat(kasus: str, x: float, y: float) -> str:
    """Fitur geometri terdekat dari sebuah titik, beserta jaraknya ke TEPI-nya.

    Diturunkan dari `geometry.json`, tidak diketik tangan. Keterangan yang diketik akan
    tetap tercetak meskipun kasus atau gayanya diganti dan titik terburuknya pindah --
    persis kelas klaim basi yang berulang kali menggigit proyek ini. Fungsi ini sudah
    membuktikan nilainya: ia menangkap klaim keliru "tepi pier" yang bertahan sejak v0.8.0.
    """
    geom = json.loads((VC6_DATA / kasus / "geometry.json").read_text(encoding="utf-8"))
    kandidat: list[tuple[float, str]] = []
    for pier in geom.get("piers") or ():
        cx, cy = pier["centerline_m"]
        if pier.get("diameter_m"):
            jarak = float(np.hypot(x - cx, y - cy) - pier["diameter_m"] / 2.0)
            kandidat.append((abs(jarak), f"tepi pier {pier['pier_id']}"))
    for pile in geom.get("piles") or ():
        jarak = float(
            np.hypot(x - pile["x_m"], y - pile["y_m"]) - pile.get("diameter_m", 0.0) / 2.0
        )
        kandidat.append((abs(jarak), f"tepi tiang {pile['pile_id']}"))
    if not kandidat:  # pragma: no cover -- geometri tanpa pier maupun pile
        return "lokasi tidak dapat diidentifikasi"
    jarak, nama = min(kandidat)
    panjang = _angka(io_utils.to_display(jarak, "length"))
    return f"{panjang} {io_utils.display_unit('length')} dari {nama}"


def _gaya_sumbu(ax) -> None:
    ax.set_facecolor(TEMA.background)
    ax.tick_params(colors=TEMA.text, labelsize=7.5)
    for sisi in ax.spines.values():
        sisi.set_color(TEMA.grid)
    ax.grid(True, color=TEMA.grid, linewidth=0.6, alpha=0.8)
    ax.set_axisbelow(True)


def _simpan(fig, jalur: Path, lebar_inci: float) -> Path:
    """Simpan, lalu kuantisasi paletnya.

    Plot sebar dengan colormap divergen di atas latar putih memakai jauh di bawah 256 warna
    nyata, sehingga PNG berpalet menghemat 40-60% tanpa perubahan yang terlihat. Ini
    penghematan ENKODING: tidak satu pun elemen dihilangkan dari gambar.
    """
    fig.savefig(jalur, dpi=LEBAR_PX / lebar_inci, facecolor=TEMA.background)
    plt.close(fig)
    with Image.open(jalur) as img:
        img.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT).save(
            jalur, optimize=True
        )
    return jalur


# ---------------------------------------------------------------------------
# Gambar 1 -- struktur & sebaran selisih
# ---------------------------------------------------------------------------

_LEBAR_SEBARAN = 11.0


def gambar_sebaran(data: dict, medan: str, combo: str, slug: str) -> Path:
    """Dua panel: struktur selisih terhadap besar nilai, dan sebaran kumulatifnya."""
    fig, (kiri, kanan) = plt.subplots(
        1, 2, figsize=(_LEBAR_SEBARAN, 4.6), facecolor=TEMA.background
    )

    # Panel kiri sengaja BUKAN scatter "Midas vs kami": pada ketelitian setinggi ini seluruh
    # titiknya runtuh ke garis y=x dan gambarnya tidak memberi tahu apa pun selain "cocok".
    # Yang dapat dilihat justru STRUKTUR selisihnya -- derau terpusat di nol, atau kemiringan
    # sistematis yang berarti salah satu program keliru.
    for kasus in VC6_KASUS:
        kami, midas = data[kasus]["kami"][medan], data[kasus]["midas"][medan]
        kiri.scatter(
            midas / float(np.max(np.abs(kami))),
            _selisih_relatif(midas, kami),
            s=3,
            alpha=0.35,
            linewidths=0,
            color=WARNA[kasus],
        )

    kiri.axhline(0.0, color=TEMA.text, linewidth=0.9, linestyle="--", zorder=5)
    batas_y = max(
        float(np.percentile(np.abs(_selisih_relatif(d["midas"][medan], d["kami"][medan])), 99.8))
        for d in data.values()
    )
    kiri.set_ylim(-batas_y, batas_y)
    kiri.set_xlabel("nilai Midas Civil / puncak", color=TEMA.text, fontsize=8.5)
    kiri.set_ylabel("selisih terhadap puncak  [%]", color=TEMA.text, fontsize=8.5)
    kiri.set_title("Apakah selisihnya terpusat di nol, atau miring?", color=TEMA.text, fontsize=9.5)
    _gaya_sumbu(kiri)
    pegangan = [
        Line2D([], [], marker="o", linestyle="", markersize=5, color=WARNA[k], label=JUDUL_KASUS[k])
        for k in VC6_KASUS
    ]
    pegangan.append(Line2D([], [], linestyle="--", color=TEMA.text, label="selisih nol"))
    kiri.legend(handles=pegangan, fontsize=7, loc="upper left", framealpha=0.9, ncol=2)

    contoh_baca: tuple[str, float] | None = None
    for kasus in VC6_KASUS:
        selisih = np.abs(_selisih_relatif(data[kasus]["midas"][medan], data[kasus]["kami"][medan]))
        terurut = np.sort(selisih)
        pangsa = np.arange(1, terurut.size + 1) / terurut.size * 100.0
        kanan.plot(terurut, pangsa, color=WARNA[kasus], linewidth=1.6, label=JUDUL_KASUS[kasus])
        p50 = float(np.percentile(selisih, 50))
        if contoh_baca is None or p50 > contoh_baca[1]:
            contoh_baca = (kasus, p50)

    for garis, teks in ((50, "separuh elemen"), (95, "95% elemen"), (99, "99% elemen")):
        kanan.axhline(garis, color=TEMA.grid, linewidth=0.8, linestyle=":")
        kanan.text(1.4e-5, garis + 1.2, teks, fontsize=6.5, color=TEMA.text, va="bottom")

    # Satu contoh baca, angkanya DIHITUNG. Kurva kumulatif tidak lazim bagi pembaca non-
    # statistik -- tanpa contoh, gambar ini menuntut penjelasan lisan setiap kali dipakai.
    assert contoh_baca is not None
    kasus_baca, p50_baca = contoh_baca
    kanan.annotate(
        f"baca begini: separuh elemen {kasus_baca}\nmenyimpang kurang dari {_angka(p50_baca, 3)}%",
        xy=(p50_baca, 50.0),
        xytext=(0.04, 0.74),
        textcoords="axes fraction",
        fontsize=7,
        color=TEMA.text,
        bbox={"facecolor": TEMA.annotation_face, "edgecolor": TEMA.grid, "pad": 3},
        arrowprops={"arrowstyle": "->", "color": TEMA.text, "linewidth": 0.9},
    )

    kanan.set_xscale("log")
    kanan.set_xlim(1e-5, 10)
    kanan.set_ylim(0, 103)
    kanan.set_xlabel(
        "|selisih| per elemen terhadap puncak  [%]  (skala logaritmik)",
        color=TEMA.text,
        fontsize=8.5,
    )
    kanan.set_ylabel("persentase elemen di bawahnya  [%]", color=TEMA.text, fontsize=8.5)
    kanan.set_title(
        "Berapa persen elemen yang selisihnya di bawah sekian?", color=TEMA.text, fontsize=9.5
    )
    _gaya_sumbu(kanan)
    kanan.legend(fontsize=7, loc="lower right", framealpha=0.9)

    fig.suptitle(
        f"Selisih {LABEL_MEDAN[medan]} per elemen terhadap Midas Civil - kombinasi {combo}",
        color=TEMA.text,
        fontsize=11.5,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _simpan(fig, KELUARAN / nama_berkas("sebaran", medan, slug), _LEBAR_SEBARAN)


# ---------------------------------------------------------------------------
# Gambar 2 -- letak selisih
# ---------------------------------------------------------------------------

_LEBAR_PETA = 11.0


def gambar_peta(data: dict, medan: str, combo: str, slug: str) -> Path:
    """Kisi 2x2 letak selisih pada denah, satu panel per contoh.

    Inilah gambar yang membedakan "cocok" dari "kebetulan cocok rata-rata". Bila selisihnya
    derau, ia tersebar merata; bila ada kekeliruan sistematis, ia berkumpul di satu zona.

    Skala warna DITETAPKAN PER PANEL, bukan bersama seluruh contoh: puncak antarcontoh
    berbeda sampai sepuluh kali lipat, dan skala bersama akan membuat tiga panel tampak
    kosong sehingga polanya justru hilang.
    """
    fig, sumbu = plt.subplots(2, 2, figsize=(_LEBAR_PETA, 9.4), facecolor=TEMA.background)
    satuan = io_utils.display_unit("length")

    for ax, kasus in zip(sumbu.ravel(), VC6_KASUS, strict=True):
        mesh = data[kasus]["mesh"]
        selisih = _selisih_relatif(data[kasus]["midas"][medan], data[kasus]["kami"][medan])
        x, y = mesh.elem_centroid[:, 0], mesh.elem_centroid[:, 1]
        batas = float(np.percentile(np.abs(selisih), 99.5)) or 1e-9

        sc = ax.scatter(
            io_utils.to_display(x, "length"),
            io_utils.to_display(y, "length"),
            c=selisih,
            s=4,
            cmap=TEMA.cmap_force,
            vmin=-batas,
            vmax=batas,
            linewidths=0,
        )
        puncak_i = int(np.argmax(np.abs(selisih)))
        px = io_utils.to_display(float(x[puncak_i]), "length")
        py = io_utils.to_display(float(y[puncak_i]), "length")
        ax.scatter(
            px, py, s=110, facecolors="none", edgecolors=TEMA.color_max, linewidths=1.4, zorder=6
        )
        ket = _fitur_terdekat(kasus, float(x[puncak_i]), float(y[puncak_i]))
        # Keterangan diarahkan KE DALAM panel. Offset tetap ke kanan akan terpotong tepi
        # gambar setiap kali titik terburuknya kebetulan jatuh di separuh kanan -- dan letak
        # titik itu berubah tiap gaya, sehingga tidak dapat ditebak saat menulis kode.
        tengah = io_utils.to_display((float(x.min()) + float(x.max())) / 2.0, "length")
        di_kanan = px > tengah
        ax.annotate(
            f"{_tanda(selisih[puncak_i])} ({ket})",
            xy=(px, py),
            xytext=(-10 if di_kanan else 10, 16),
            textcoords="offset points",
            ha="right" if di_kanan else "left",
            fontsize=6.5,
            color=TEMA.text,
            bbox={"facecolor": TEMA.annotation_face, "edgecolor": TEMA.grid, "pad": 2},
            arrowprops={"arrowstyle": "->", "color": TEMA.text, "linewidth": 0.7},
        )

        bar = fig.colorbar(sc, ax=ax, shrink=0.82)
        bar.set_label("selisih thd puncak [%]", color=TEMA.text, fontsize=7)
        bar.ax.tick_params(colors=TEMA.text, labelsize=6.5)

        ax.set_xlabel(f"x  [{satuan}]", color=TEMA.text, fontsize=8)
        ax.set_ylabel(f"y  [{satuan}]", color=TEMA.text, fontsize=8)
        ax.set_title(
            f"{JUDUL_KASUS[kasus]} - {_angka(len(selisih))} elemen", color=TEMA.text, fontsize=9
        )
        ax.set_aspect("equal")
        _gaya_sumbu(ax)

    fig.suptitle(
        f"Letak selisih {LABEL_MEDAN[medan]} pada denah - kombinasi {combo}\n"
        "skala warna per panel, dipotong pada persentil 99,5",
        color=TEMA.text,
        fontsize=11.5,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _simpan(fig, KELUARAN / nama_berkas("peta", medan, slug), _LEBAR_PETA)


# ---------------------------------------------------------------------------
# Gambar 3 & 4 -- lendutan per node
# ---------------------------------------------------------------------------

#: Galat pembulatan ekspor lendutan Midas [mikrometer].
#:
#: `midas_displacement.csv` menulis 6 desimal dalam METER, sehingga langkahnya 1 µm dan
#: galat pembulatan tiap nilainya paling besar setengah langkah. Selisih yang lebih kecil
#: dari ini dapat dijelaskan SELURUHNYA oleh pembulatan -- tidak dapat dibedakan dari nol.
#: Lihat `tests/data/vc6/SUMBER.md` Bagian 5.2.
PEMBULATAN_UM = 0.5


def _selisih_um(midas: np.ndarray, kami: np.ndarray) -> np.ndarray:
    """Selisih lendutan per node dalam mikrometer.

    Sengaja BUKAN persen terhadap puncak seperti gambar gaya. Batas ketelitian jalur ini
    absolut -- 0,5 µm pada setiap contoh -- sedangkan persen terhadap puncak membuat batas
    itu berbeda-beda per contoh (0,02% pada ex02, 0,45% pada ex04). Dalam mikrometer, satu
    pita pembulatan berlaku untuk keempat contoh sekaligus dan dapat digambar sebagai satu
    pita.
    """
    return (midas - kami) * 1e6


def gambar_sebaran_lendutan(data: dict, combo: str, slug: str) -> Path:
    """Struktur & sebaran selisih lendutan, dengan pita pembulatan ekspor Midas.

    Pita itu yang membuat gambar ini jujur. Tanpa dia, selisih ex04 -- yang 91% nodenya
    berada di bawah galat pembulatan -- akan terbaca sebagai ketidakcocokan, padahal yang
    terukur hanyalah batas ketelitian berkas pembandingnya.
    """
    fig, (kiri, kanan) = plt.subplots(
        1, 2, figsize=(_LEBAR_SEBARAN, 4.6), facecolor=TEMA.background
    )

    kiri.axhspan(-PEMBULATAN_UM, PEMBULATAN_UM, color=TEMA.grid, alpha=0.7, zorder=0)
    for kasus in VC6_KASUS:
        ld = data[kasus]["lendutan"]
        kiri.scatter(
            ld["midas"] / float(np.max(np.abs(ld["kami"]))),
            _selisih_um(ld["midas"], ld["kami"]),
            s=3,
            alpha=0.35,
            linewidths=0,
            color=WARNA[kasus],
        )
    kiri.axhline(0.0, color=TEMA.text, linewidth=0.9, linestyle="--", zorder=5)
    kiri.set_xlabel("lendutan Midas Civil / puncak", color=TEMA.text, fontsize=8.5)
    kiri.set_ylabel("selisih  [µm]", color=TEMA.text, fontsize=8.5)
    kiri.set_title(
        "Selisih per node; pita abu-abu = pembulatan ekspor Midas",
        color=TEMA.text,
        fontsize=9.5,
    )
    _gaya_sumbu(kiri)
    pegangan = [
        Line2D([], [], marker="o", linestyle="", markersize=5, color=WARNA[k], label=JUDUL_KASUS[k])
        for k in VC6_KASUS
    ]
    pegangan.append(
        Line2D([], [], linewidth=7, color=TEMA.grid, label=f"±{_angka(PEMBULATAN_UM, 1)} µm")
    )
    # Kanan-bawah: pada lendutan selisih hampir selalu positif di nilai besar, sehingga
    # sudut itu kosong. Sudut kiri-atas justru tempat titik ex02/ex03 naik.
    kiri.legend(handles=pegangan, fontsize=7, loc="lower right", framealpha=0.9, ncol=2)

    for kasus in VC6_KASUS:
        ld = data[kasus]["lendutan"]
        selisih = np.sort(np.abs(_selisih_um(ld["midas"], ld["kami"])))
        pangsa = np.arange(1, selisih.size + 1) / selisih.size * 100.0
        kanan.plot(selisih, pangsa, color=WARNA[kasus], linewidth=1.6, label=JUDUL_KASUS[kasus])

    kanan.axvspan(1e-4, PEMBULATAN_UM, color=TEMA.grid, alpha=0.7, zorder=0)
    kanan.axvline(PEMBULATAN_UM, color=TEMA.text, linewidth=0.9, linestyle="--")
    for garis, teks in ((50, "separuh node"), (95, "95% node")):
        kanan.axhline(garis, color=TEMA.grid, linewidth=0.8, linestyle=":")
        kanan.text(1.2e-4, garis + 1.2, teks, fontsize=6.5, color=TEMA.text, va="bottom")

    kanan.set_xscale("log")
    kanan.set_xlim(1e-4, 10)
    kanan.set_ylim(0, 103)
    kanan.set_xlabel("|selisih| per node  [µm]  (skala logaritmik)", color=TEMA.text, fontsize=8.5)
    kanan.set_ylabel("persentase node di bawahnya  [%]", color=TEMA.text, fontsize=8.5)
    kanan.set_title(
        "Berapa persen node yang selisihnya di bawah sekian?", color=TEMA.text, fontsize=9.5
    )
    _gaya_sumbu(kanan)
    # Pita diterangkan lewat legenda, bukan teks mengambang: letak kurva berubah tiap
    # kombinasi, sehingga teks yang ditempatkan tetap akan menabrak salah satunya.
    pegangan_kanan, _ = kanan.get_legend_handles_labels()
    pegangan_kanan.append(
        Patch(color=TEMA.grid, label="pembulatan ekspor:\ntidak dapat dibedakan dari nol")
    )
    # Kiri-atas di dalam pita kosong: seluruh kurva masih di bawah 20% di rentang itu.
    kanan.legend(
        handles=pegangan_kanan,
        fontsize=6.8,
        loc="upper left",
        bbox_to_anchor=(0.01, 0.90),
        framealpha=0.92,
    )

    fig.suptitle(
        f"Selisih lendutan $u_z$ per node terhadap Midas Civil - kombinasi {combo}",
        color=TEMA.text,
        fontsize=11.5,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    return _simpan(fig, KELUARAN / nama_berkas("sebaran", "uz", slug), _LEBAR_SEBARAN)


def gambar_peta_lendutan(data: dict, combo: str, slug: str) -> Path:
    """Kisi 2x2 letak selisih lendutan pada denah, dengan skala warna BERSAMA.

    Kebalikan dari peta gaya, dan disengaja. Pada gaya, skala per panel perlu karena puncak
    antarcontoh berbeda sampai sepuluh kali lipat. Pada lendutan justru berbahaya: selisih
    ex04 hampir seluruhnya derau pembulatan (maks 0,7 µm), dan skala per panel akan
    membesarkannya menjadi pola berwarna tajam yang terbaca seperti ketidakcocokan
    sungguhan. Skala bersama dalam mikrometer menampilkan tiap panel apa adanya.
    """
    # Lebih tinggi daripada peta gaya: judul panelnya dua baris (jumlah node + pangsa di
    # dalam pembulatan), dan tanpa ruang tambahan label sumbu x panel atas menabrak judul
    # panel di bawahnya.
    fig, sumbu = plt.subplots(2, 2, figsize=(_LEBAR_PETA, 10.4), facecolor=TEMA.background)
    satuan = io_utils.display_unit("length")
    batas = max(
        float(
            np.percentile(np.abs(_selisih_um(d["lendutan"]["midas"], d["lendutan"]["kami"])), 99.5)
        )
        for d in data.values()
    )

    for ax, kasus in zip(sumbu.ravel(), VC6_KASUS, strict=True):
        ld = data[kasus]["lendutan"]
        selisih = _selisih_um(ld["midas"], ld["kami"])
        x, y = ld["xy"][:, 0], ld["xy"][:, 1]
        sc = ax.scatter(
            io_utils.to_display(x, "length"),
            io_utils.to_display(y, "length"),
            c=selisih,
            s=4,
            cmap=TEMA.cmap_force,
            vmin=-batas,
            vmax=batas,
            linewidths=0,
        )
        dalam = float(np.mean(np.abs(selisih) <= PEMBULATAN_UM)) * 100
        bar = fig.colorbar(sc, ax=ax, shrink=0.82)
        bar.set_label("selisih [µm]", color=TEMA.text, fontsize=7)
        bar.ax.tick_params(colors=TEMA.text, labelsize=6.5)
        for tepi in (-PEMBULATAN_UM, PEMBULATAN_UM):
            bar.ax.axhline(tepi, color=TEMA.text, linewidth=0.8, linestyle="--")

        ax.set_xlabel(f"x  [{satuan}]", color=TEMA.text, fontsize=8)
        ax.set_ylabel(f"y  [{satuan}]", color=TEMA.text, fontsize=8)
        ax.set_title(
            f"{JUDUL_KASUS[kasus]} - {_angka(len(selisih))} node\n"
            f"{_angka(dalam, 1)}% node di dalam pembulatan ekspor",
            color=TEMA.text,
            fontsize=8.5,
        )
        ax.set_aspect("equal")
        _gaya_sumbu(ax)

    fig.suptitle(
        f"Letak selisih lendutan $u_z$ pada denah - kombinasi {combo}\n"
        f"skala warna BERSAMA; garis putus pada skala = pembulatan ekspor Midas "
        f"(±{_angka(PEMBULATAN_UM, 1)} µm)",
        color=TEMA.text,
        fontsize=11,
        fontweight="bold",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    return _simpan(fig, KELUARAN / nama_berkas("peta", "uz", slug), _LEBAR_PETA)


# ---------------------------------------------------------------------------
# Ringkasan angka
# ---------------------------------------------------------------------------


def ringkasan(semua: dict) -> Path:
    """Tulis RMS/p50/p99/maksimum tiap (kombinasi, gaya, contoh) sebagai JSON.

    Panduan membaca berkas ini alih-alih mengetik ulang angkanya. Data VC-6 tidak ikut ke
    dalam wheel, sehingga panduan tidak dapat menghitungnya sendiri di komputer pengguna --
    dan tabel yang diketik ulang akan menyimpang dari gambarnya cepat atau lambat.
    """
    keluaran: dict[str, dict[str, dict[str, dict[str, float]]]] = {}
    for (combo, _slug), data in semua.items():
        for medan in MEDAN:
            for kasus in VC6_KASUS:
                kami, midas = data[kasus]["kami"][medan], data[kasus]["midas"][medan]
                s = _selisih_relatif(midas, kami)
                keluaran.setdefault(combo, {}).setdefault(medan, {})[kasus] = {
                    # Dibulatkan ke 6 desimal, bukan ke jumlah desimal yang dicetak.
                    # Membulatkan dua kali -- di sini lalu lagi saat dicetak -- membuat
                    # nilai tepat di batas (mis. 0,0555%) tercetak berbeda dari pengukuran
                    # langsung, dan selisih semu itu paling menyulitkan saat seseorang
                    # mencocokkan tabel panduan dengan keluaran gate.
                    "rms": round(float(np.sqrt(np.mean(s**2))), 6),
                    "p50": round(float(np.percentile(np.abs(s), 50)), 6),
                    "p99": round(float(np.percentile(np.abs(s), 99)), 6),
                    "maks": round(float(np.max(np.abs(s))), 6),
                    "n_elemen": int(s.size),
                }
        for kasus in VC6_KASUS:
            ld = data[kasus]["lendutan"]
            s = _selisih_relatif(ld["midas"], ld["kami"])
            d_um = _selisih_um(ld["midas"], ld["kami"])
            keluaran.setdefault(combo, {}).setdefault("uz", {})[kasus] = {
                # Besaran bersama dengan gaya, supaya dapat dibandingkan dengan gate.
                "rms": round(float(np.sqrt(np.mean(s**2))), 6),
                # Besaran KHUSUS lendutan: dalam mikrometer, karena batas ketelitiannya
                # absolut, bukan relatif terhadap puncak.
                "uz_maks_mm": round(float(np.max(np.abs(ld["kami"]))) * 1e3, 6),
                "maks_um": round(float(np.max(np.abs(d_um))), 6),
                "p50_um": round(float(np.percentile(np.abs(d_um), 50)), 6),
                "dalam_pembulatan": round(float(np.mean(np.abs(d_um) <= PEMBULATAN_UM)) * 100, 6),
                "n_node": int(d_um.size),
            }
    jalur = KELUARAN / "vc6-ringkasan.json"
    jalur.write_text(json.dumps(keluaran, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return jalur


def main() -> int:
    KELUARAN.mkdir(parents=True, exist_ok=True)

    # Analisis dijalankan sekali per (contoh, kombinasi) lalu dipakai ulang untuk kelima
    # gaya -- delapan analisis, bukan empat puluh.
    semua: dict[tuple[str, str], dict] = {}
    for combo, slug in VC6_KOMBINASI:
        data: dict = {}
        for kasus in VC6_KASUS:
            mesh, kami, midas, lendutan = _muat(kasus, combo, slug)
            data[kasus] = {
                "mesh": mesh,
                "kami": {m: getattr(kami, m) for m in MEDAN},
                "midas": midas,
                "lendutan": lendutan,
            }
        semua[(combo, slug)] = data

    dibuat: list[Path] = []
    for (combo, slug), data in semua.items():
        for medan in MEDAN:
            dibuat.append(gambar_sebaran(data, medan, combo, slug))
            dibuat.append(gambar_peta(data, medan, combo, slug))
        dibuat.append(gambar_sebaran_lendutan(data, combo, slug))
        dibuat.append(gambar_peta_lendutan(data, combo, slug))
    dibuat.append(ringkasan(semua))

    total = sum(p.stat().st_size for p in dibuat)
    for p in dibuat:
        print(f"  {p.relative_to(REPO)}  ({p.stat().st_size / 1024:,.0f} KB)")
    print(f"\n  {len(dibuat)} berkas, total {total / 1024 / 1024:.2f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
