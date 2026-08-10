"""Visualisasi (PRD Bagian 9.3). TIDAK ADA perhitungan rekayasa di modul ini.

Bersama `reporter.py`, ini satu-satunya tempat konversi ke satuan tampilan lewat
`io_utils.to_display()` (PRD Bagian 4.3).

Bahasa label: Indonesia, istilah teknis dibiarkan Inggris (keputusan user,
PRD Bagian 17 item 9).

.. rubric:: Dua keputusan penyajian yang disengaja

**Kontur digambar datar per elemen**, bukan dihaluskan. Nilai resultant memang
dihitung per elemen (rata-rata antar titik Gauss); interpolasi nodal akan menyiratkan
kehalusan yang tidak pernah kita hitung. Pada daerah singularitas di tepi zona jepit
justru penghalusan itulah yang paling menyesatkan.

**Kegagalan plot tidak menghentikan run.** Plot adalah alat bantu baca, bukan sumber
angka desain; matinya satu gambar tidak mengubah satu pun nilai di CSV. Karena itu
kegagalan `opsvis` dicatat sebagai WARNING yang muncul di log DAN laporan -- bukan
dilewati diam-diam, tetapi juga tidak membatalkan hasil analisis yang sudah lulus VC-0.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Final

import matplotlib
import numpy as np

from pilecap_fem import config, io_utils
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel

_log = config.get_logger("renderer")

#: Label axes kop. Dipakai test untuk menemukannya tanpa aritmetika indeks -- figur kontur
#: punya tiga axes (gambar, colorbar, kop) dan `fig.axes[-1]` akan salah begitu ada
#: colorbar kedua.
PANEL_LABEL: Final[str] = "pilecap_title_block"


@dataclass(frozen=True)
class PlotStyle:
    """Pilihan penyajian yang dibawa bersama, bukan sebagai lima parameter terpisah.

    `render_contour` sudah menerima sebelas argumen sebelum tema dan metode kontur ada.
    Mengelompokkan yang bersifat penyajian membuat tanda tangannya berhenti tumbuh, dan
    membuat "gaya" dapat diteruskan utuh dari CLI ke setiap fungsi gambar.
    """

    theme: config.Theme = field(default_factory=config.theme)
    method: str = config.DEFAULT_CONTOUR_METHOD
    dpi: int = config.OUTPUT_DPI
    preview: bool = False

    def __post_init__(self) -> None:
        if self.method not in config.CONTOUR_METHODS:
            raise ValueError(
                f"contour method {self.method!r} tidak dikenal. Pilihan: {config.CONTOUR_METHODS}"
            )

    @classmethod
    def from_args(cls, args: Any) -> PlotStyle:
        """Bangun dari `argparse.Namespace`; flag yang tidak ada memakai bawaannya."""
        return cls(
            theme=config.theme(getattr(args, "theme", None)),
            method=getattr(args, "contour_method", None) or config.DEFAULT_CONTOUR_METHOD,
            dpi=getattr(args, "dpi", config.OUTPUT_DPI),
            preview=bool(getattr(args, "preview", False)),
        )


@dataclass(frozen=True)
class TitleBlock:
    """Kop gambar teknik: identitas proyek, asumsi, catatan. Wadah murni.

    TIDAK memuat statistik hasil (maks/min). Itu disengaja: `_mark_extremes` sudah
    menuliskan nilai ekstrem DI ATAS elemen yang bersangkutan beserta koordinatnya, dan
    colorbar sudah membawa rentangnya. Menyalinnya ke kop hanya menciptakan tempat kedua
    yang bisa berbeda dari gambarnya sendiri.

    `warnings` dipisah sebagai field, bukan konvensi awalan teks. PRD Bagian 9.3 menuntut
    baris `GEOMETRI OVERRIDE` menonjol; sebelumnya itu dicapai dengan mewarnai SELURUH
    judul merah -- termasuk nama besaran yang tidak ada hubungannya dengan override. Field
    bertipe membuat "baris ini peringatan" dapat diperiksa test, bukan ditebak dari string.
    """

    project: str = ""
    engineer: str = ""
    date: str = ""
    #: Besaran yang MELAHIRKAN angka pada gambar (f'c, fy, tebal, selimut, mode, phi).
    assumptions: tuple[str, ...] = ()
    #: Cara membaca gambar (peringatan orientasi, "baca bersama plot Av/s").
    notes: tuple[str, ...] = ()
    #: Dicetak dengan warna peringatan tema.
    warnings: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (
            self.project
            or self.engineer
            or self.date
            or self.assumptions
            or self.notes
            or self.warnings
        )

    def with_assumptions(self, *extra: str) -> TitleBlock:
        return replace(self, assumptions=self.assumptions + tuple(e for e in extra if e))

    def with_notes(self, *extra: str) -> TitleBlock:
        return replace(self, notes=self.notes + tuple(e for e in extra if e))

    def with_warnings(self, *extra: str) -> TitleBlock:
        return replace(self, warnings=self.warnings + tuple(e for e in extra if e))


# --- Tata letak kop -------------------------------------------------------
#
# Seluruh ukuran dalam INCI, bukan fraksi figur: tinggi figur berayun 5,0-10,2 inci
# mengikuti aspek pilecap, sehingga fraksi yang tetap akan menghasilkan kop yang
# ukurannya berubah-ubah. Kop pada gambar teknik berukuran tetap.

_PANEL_MARGIN_L_IN: Final[float] = 0.35
_PANEL_MARGIN_B_IN: Final[float] = 0.22
_PANEL_GAP_TOP_IN: Final[float] = 0.12
_PANEL_PAD_IN: Final[float] = 0.10
#: Ruang di kanan kop untuk watermark.
_PANEL_RIGHT_RESERVE_IN: Final[float] = 2.40
_PANEL_MIN_W_IN: Final[float] = 3.50
_PANEL_MIN_H_IN: Final[float] = 0.55
#: Pagar atas tinggi kop. Bila terlampaui, catatan dipangkas DENGAN PENGUMUMAN.
_PANEL_MAX_H_IN: Final[float] = 3.20

_FS_PROJECT: Final[float] = 9.0
_FS_META: Final[float] = 7.5
_FS_LABEL: Final[float] = 6.5
_FS_BODY: Final[float] = 7.5
_LINE_FACTOR: Final[float] = 1.45
_SEP_IN: Final[float] = 0.07

#: Lebar rata-rata satu karakter DejaVu Sans (font bawaan matplotlib) dalam em, untuk
#: teks prosa campuran. Sengaja konservatif: perkiraan yang meleset ke arah LEBIH banyak
#: baris menghasilkan kop yang sedikit lapang, bukan kop yang terpotong.
_CHAR_EM: Final[float] = 0.52

_TRUNCATION_NOTE: Final[str] = "(catatan selengkapnya di calc_sheet.md)"

#: Ruang di ATAS axes untuk judul dua baris, dalam inci.
#:
#: Dicadangkan eksplisit, tidak diserahkan ke `tight_layout`. DIUKUR: dengan `rect` yang
#: hanya membatasi sisi bawah, `tight_layout` menempatkan judul `loc="left"` berikut
#: `pad`-nya sampai `y1 = 1,013` -- yaitu KELUAR tepi atas figur, sehingga hurufnya
#: terpotong. Angkanya = pad 22 pt + tinggi huruf 13 pt + margin.
_HEADING_RESERVE_IN: Final[float] = 0.62


@dataclass(frozen=True)
class _PanelLine:
    """Satu baris kop yang sudah dibungkus dan siap digambar."""

    text: str
    fontsize: float
    kind: str  # project | meta | label | body | warning | sep


def _use_agg(preview: bool) -> None:
    if not preview:
        matplotlib.use("Agg", force=True)


def _line_height_in(fontsize: float) -> float:
    return fontsize * _LINE_FACTOR / 72.0


def _wrap(text: str, width_in: float, fontsize: float) -> list[str]:
    """Bungkus teks ke lebar kolom kop.

    Anggaran karakter DITURUNKAN dari lebar panel, bukan konstanta. Nilai lama
    `textwrap.fill(override, width=62)` hanya benar untuk satu lebar figur, dan diam-diam
    salah pada pratinjau UI yang lebarnya 7 inci.

    `break_long_words=False` melindungi nama berkas seperti `custom_pile_coords.csv` dari
    terpotong di tengah -- nama berkas yang terpenggal pada baris peringatan override
    justru menyesatkan.
    """
    budget = max(20, int(width_in * 72.0 / (_CHAR_EM * fontsize)))
    return textwrap.wrap(text, width=budget, break_long_words=False, break_on_hyphens=False) or [""]


def _panel_width_in(fig_width_in: float) -> float:
    """Lebar kop. Pada figur sempit, kop memakai lebar penuh dan watermark pindah."""
    wide = fig_width_in - _PANEL_MARGIN_L_IN - _PANEL_RIGHT_RESERVE_IN
    if wide >= _PANEL_MIN_W_IN:
        return wide
    return fig_width_in - 2.0 * _PANEL_MARGIN_L_IN


def _layout_lines(block: TitleBlock, panel_width_in: float) -> list[_PanelLine]:
    """Ubah `TitleBlock` menjadi daftar baris siap gambar.

    Dipakai BERSAMA oleh jalur pengukuran tinggi dan jalur penggambaran. Itu bukan
    kebetulan: pengukuran dan penggambaran yang tidak sinkron adalah bug paling mungkin
    pada tata letak ini, dan satu fungsi membuatnya mustahil.
    """
    text_w = max(1.0, panel_width_in - 2.0 * _PANEL_PAD_IN)
    lines: list[_PanelLine] = []

    if block.project:
        for part in _wrap(block.project, text_w, _FS_PROJECT):
            lines.append(_PanelLine(part, _FS_PROJECT, "project"))
    meta = " · ".join(p for p in (block.engineer, block.date) if p)
    if meta:
        for part in _wrap(meta, text_w, _FS_META):
            lines.append(_PanelLine(part, _FS_META, "meta"))

    def section(label: str, items: tuple[str, ...], kind: str) -> None:
        if not items:
            return
        if lines:
            lines.append(_PanelLine("", 0.0, "sep"))
        lines.append(_PanelLine(label, _FS_LABEL, "label"))
        for item in items:
            for part in _wrap(item, text_w, _FS_BODY):
                lines.append(_PanelLine(part, _FS_BODY, kind))

    section("ASUMSI DESAIN", block.assumptions, "body")
    section("CATATAN", block.notes, "body")
    section("PERINGATAN", block.warnings, "warning")
    return lines


def _panel_height_in(lines: Sequence[_PanelLine]) -> float:
    total = 2.0 * _PANEL_PAD_IN
    for line in lines:
        total += _SEP_IN if line.kind == "sep" else _line_height_in(line.fontsize)
    return total


def _fit_lines(block: TitleBlock, panel_width_in: float) -> list[_PanelLine]:
    """Baris kop yang sudah dipastikan muat pagar `_PANEL_MAX_H_IN`.

    Bila kelebihan, catatan dibuang dari BELAKANG dan digantikan satu baris penunjuk.
    Dipangkas dengan pengumuman, tidak pernah diam-diam -- sikap yang sama dengan seluruh
    penanganan data tak lengkap di tool ini.
    """
    lines = _layout_lines(block, panel_width_in)
    if _panel_height_in(lines) <= _PANEL_MAX_H_IN:
        return lines

    trimmed = block
    while trimmed.notes and _panel_height_in(lines) > _PANEL_MAX_H_IN:
        trimmed = replace(trimmed, notes=trimmed.notes[:-1])
        diumumkan = replace(trimmed, notes=(*trimmed.notes, _TRUNCATION_NOTE))
        lines = _layout_lines(diumumkan, panel_width_in)
    return lines


def _reserve_bottom_in(block: TitleBlock | None, fig_width_in: float) -> float:
    """Tinggi pita yang harus DITAMBAHKAN ke figur untuk menampung kop."""
    if block is None or block.is_empty():
        return 0.0
    lines = _fit_lines(block, _panel_width_in(fig_width_in))
    height = min(max(_panel_height_in(lines), _PANEL_MIN_H_IN), _PANEL_MAX_H_IN)
    return height + _PANEL_GAP_TOP_IN + _PANEL_MARGIN_B_IN


def _draw_title_block(fig: Any, block: TitleBlock | None, theme: config.Theme) -> Any:
    """Gambar kop sebagai axes tersendiri di kiri-bawah figur.

    HARUS dipanggil SESUDAH `tight_layout`: `add_axes` menghasilkan axes di luar gridspec,
    dan memanggilnya lebih dulu membuat `tight_layout` mengeluh "Axes that are not
    compatible with tight_layout" sekaligus memindahkan kop dari tempatnya.
    """
    if block is None or block.is_empty():
        return None

    fig_w, fig_h = fig.get_figwidth(), fig.get_figheight()
    panel_w = _panel_width_in(fig_w)
    lines = _fit_lines(block, panel_w)
    panel_h = min(max(_panel_height_in(lines), _PANEL_MIN_H_IN), _PANEL_MAX_H_IN)

    panel = fig.add_axes(
        (
            _PANEL_MARGIN_L_IN / fig_w,
            _PANEL_MARGIN_B_IN / fig_h,
            panel_w / fig_w,
            panel_h / fig_h,
        ),
        label=PANEL_LABEL,
        zorder=20,
    )
    panel.set_xticks([])
    panel.set_yticks([])
    # Latar diberikan eksplisit: tanpa itu kop tampil transparan-di-atas-putih pada tema
    # gelap -- kelas bug yang sama dengan yang dijaga `test_tema_*`.
    panel.set_facecolor(theme.background)
    for spine in panel.spines.values():
        spine.set_color(theme.text)
        spine.set_linewidth(1.0)

    cursor = panel_h - _PANEL_PAD_IN
    for line in lines:
        if line.kind == "sep":
            cursor -= _SEP_IN / 2.0
            panel.axhline(cursor / panel_h, color=theme.grid, linewidth=0.8, zorder=21)
            cursor -= _SEP_IN / 2.0
            continue
        height = _line_height_in(line.fontsize)
        cursor -= height
        panel.text(
            _PANEL_PAD_IN / panel_w,
            (cursor + height * 0.22) / panel_h,
            line.text,
            transform=panel.transAxes,
            fontsize=line.fontsize,
            color=theme.pier_line if line.kind == "warning" else theme.text,
            fontweight="bold" if line.kind in ("project", "label", "warning") else "normal",
            alpha=0.75 if line.kind == "label" else 1.0,
            va="bottom",
            ha="left",
            zorder=22,
        )
    return panel


def _set_heading(ax: Any, theme: config.Theme, *, heading: str, combo: str = "") -> None:
    """Judul dua baris: nama besaran (besar) lalu kombinasi (kecil, redup).

    Matplotlib hanya punya tiga slot judul (`left`/`center`/`right`) dan ketiganya tidak
    bertumpuk, sehingga dua ukuran menuntut dua artist. Baris kecil ditempatkan pada
    offset tetap 6 pt dan baris besar di slot judul dengan `pad`; kebalikannya rapuh
    karena baris besar dapat berganti panjang.
    """
    ax.set_title(heading, fontsize=13, fontweight="bold", color=theme.text, loc="left", pad=22)
    if combo:
        ax.annotate(
            f"Kombinasi {combo}",
            xy=(0.0, 1.0),
            xycoords="axes fraction",
            xytext=(0, 6),
            textcoords="offset points",
            ha="left",
            va="bottom",
            fontsize=9.5,
            color=theme.text,
            alpha=0.65,
            annotation_clip=False,
        )


def _finalize(fig: Any, block: TitleBlock | None, theme: config.Theme, *, three_d: bool) -> None:
    """Rapikan tata letak lalu gambar kop & watermark. URUTAN DI SINI MENGIKAT."""
    reserve = _reserve_bottom_in(block, fig.get_figwidth())
    frac = reserve / fig.get_figheight() if reserve else 0.0
    atas = 1.0 - _HEADING_RESERVE_IN / fig.get_figheight()
    if three_d:
        # `tight_layout` tidak andal pada Axes3D milik opsvis.
        fig.subplots_adjust(bottom=max(frac, 0.02), top=atas)
    else:
        fig.tight_layout(rect=(0.0, frac, 1.0, atas))
    _draw_title_block(fig, block, theme)
    _watermark(fig, theme)


def _to_mm(value: Any) -> Any:
    return io_utils.to_display(value, "length")


def _face_colors(mesh: MeshModel, theme: config.Theme) -> list[str]:
    palette = []
    for name in mesh.group_names:
        if name.startswith(config.GROUP_PILE_PREFIX):
            palette.append(theme.pile)
        elif name.startswith(config.GROUP_PIER_PREFIX):
            palette.append(theme.pier)
        else:
            palette.append(theme.cap)
    return [palette[int(g)] for g in mesh.elem_group]


def _override_subtitle(geom: GeometryModel) -> str | None:
    """Subjudul wajib bila ada entitas yang di-override CSV (PRD Bagian 9.3)."""
    parts = []
    for entity, res in (
        ("pilecap", geom.resolution.pilecap),
        ("pile", geom.resolution.pile),
        ("pier", geom.resolution.pier),
    ):
        if res.is_override and res.file is not None:
            parts.append(f"{entity} <- {Path(res.file).name}")
    if not parts:
        return None
    return "GEOMETRI OVERRIDE: " + " | ".join(parts)


def _annotate_plan(
    ax: Any,
    geom: GeometryModel,
    *,
    pz_by_pile: dict[str, float] | None = None,
    theme: config.Theme | None = None,
    pile_label_color: str | None = None,
) -> None:
    """Anotasi wajib PRD Bagian 9.3, sama untuk SELURUH plot denah.

    Dipakai ulang oleh mesh plan, kontur, boundary check, dan envelope, sehingga
    outline pilecap, lingkaran pile, dan arsir pier tidak pernah berbeda antar gambar.

    `pz_by_pile` opsional: bila diberikan, nilai `Pz` ikut dicetak di label pile
    (PRD Bagian 9.3 meminta "label ID + nilai Pz").
    """
    import matplotlib.pyplot as plt

    unit = io_utils.display_unit("length")
    th = theme or config.theme()
    label_color = pile_label_color or th.pile_label

    cap = _to_mm(geom.pilecap.closed_vertices())
    ax.plot(cap[:, 0], cap[:, 1], color=th.outline, linewidth=1.8, zorder=5)

    for pile in geom.piles:
        ax.add_patch(
            plt.Circle(
                (_to_mm(pile.x), _to_mm(pile.y)),
                _to_mm(pile.radius),
                fill=False,
                linestyle="--",
                linewidth=1.2,
                edgecolor=th.pile_line,
                zorder=6,
            )
        )
        label = pile.pile_id
        if pz_by_pile is not None and pile.pile_id in pz_by_pile:
            pz_kn = io_utils.to_display(pz_by_pile[pile.pile_id], "force")
            label = f"{pile.pile_id}\n{pz_kn:,.0f} kN"
        ax.annotate(
            label,
            (_to_mm(pile.x), _to_mm(pile.y)),
            ha="center",
            va="center",
            fontsize=7,
            color=label_color,
            zorder=7,
            bbox={
                "boxstyle": "round,pad=0.15",
                "facecolor": th.annotation_face,
                "alpha": 0.7,
                "edgecolor": "none",
            },
        )

    for pier in geom.piers:
        exterior = np.asarray(pier.to_shapely().exterior.coords)
        ax.fill(
            _to_mm(exterior[:, 0]),
            _to_mm(exterior[:, 1]),
            facecolor="none",
            edgecolor=th.pier_line,
            hatch="///",
            linewidth=1.6,
            zorder=6,
        )
        cx, cy = pier.centerline
        ax.annotate(
            f"{pier.pier_id}\nJEPIT",
            (_to_mm(cx), _to_mm(cy)),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color=th.pier_line,
            zorder=7,
            bbox={
                "boxstyle": "round,pad=0.25",
                "facecolor": th.annotation_face,
                "alpha": 0.85,
                "edgecolor": "none",
            },
        )

    ax.set_xlabel(f"X - memanjang [{unit}]", color=th.text)
    ax.set_ylabel(f"Y - melintang [{unit}]", color=th.text)
    ax.tick_params(colors=th.text)
    for spine in ax.spines.values():
        spine.set_color(th.grid)
    ax.set_aspect("equal", adjustable="box")
    ax.autoscale_view()
    ax.grid(True, linewidth=0.3, alpha=0.4, color=th.grid)


def _figure_for(
    geom: GeometryModel,
    width: float = 12.0,
    theme: config.Theme | None = None,
    *,
    reserve_bottom_in: float = 0.0,
) -> tuple[Any, Any]:
    """Figur berukuran mengikuti aspek pilecap, ditambah pita kosong untuk kop.

    Pita DITAMBAHKAN ke tinggi figur, tidak diambil dari area gambar. Itu pilihan sadar:
    pada pilecap panjang-ramping (`plot_h` mentok di 5,0 inci), mengambil ~1,3 inci berarti
    kehilangan seperempat tinggi gambar. Gambar teknik memperbesar kertasnya untuk kop,
    bukan mengecilkan pandangannya.
    """
    import matplotlib.pyplot as plt

    th = theme or config.theme()
    xmin, ymin, xmax, ymax = geom.pilecap.bounds
    span_x, span_y = xmax - xmin, ymax - ymin
    aspect = (span_y / span_x) if span_x > 0 else 1.0
    plot_h = max(5.0, width * aspect * 0.85)
    fig, ax = plt.subplots(figsize=(width, plot_h + reserve_bottom_in + _HEADING_RESERVE_IN))
    fig.patch.set_facecolor(th.background)
    ax.set_facecolor(th.background)
    return fig, ax


def _element_polygons(mesh: MeshModel) -> list[np.ndarray]:
    return [_to_mm(mesh.node_xy[conn]) for conn in mesh.elem_conn]


def _triangulation(mesh: MeshModel) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Node + segitiga untuk metode `average-nodal`.

    Setiap quad dipecah menjadi dua segitiga mengikuti urutan simpul mesh (0-1-2 dan
    0-2-3).

    Urutan itu **tidak dijamin CCW** -- `mesh_model._quad_areas_and_centroids` sengaja
    memakai `np.abs(signed)` agar tidak bergantung pada orientasi penomoran gmsh. Yang
    dibutuhkan di sini lebih longgar daripada CCW: cukup quad-nya cembung dan simpulnya
    berurutan keliling, dan itu memang berlaku untuk quad mesh. Pembagian ini tidak
    terpengaruh arah keliling, karena warna segitiga tidak melihat tanda luas. Test
    memeriksanya dengan membandingkan rentang nilai terhadap `element-center` pada kasus
    yang sama.
    """
    conn = mesh.elem_conn
    tris = np.vstack([conn[:, [0, 1, 2]], conn[:, [0, 2, 3]]])
    return _to_mm(mesh.node_xy[:, 0]), _to_mm(mesh.node_xy[:, 1]), tris


def _nodal_from_elements(mesh: MeshModel, values: np.ndarray) -> np.ndarray:
    """Rata-rata nilai elemen ke node (metode `average-nodal`).

    Elemen NaN tidak ikut merata-rata; node yang seluruh elemennya NaN tetap NaN, sehingga
    daerah tak terdefinisi tidak terisi diam-diam oleh tetangganya.
    """
    total = np.zeros(mesh.n_nodes, dtype=np.float64)
    count = np.zeros(mesh.n_nodes, dtype=np.float64)
    finite = np.isfinite(values)
    for column in range(mesh.elem_conn.shape[1]):
        nodes = mesh.elem_conn[:, column]
        np.add.at(total, nodes[finite], values[finite])
        np.add.at(count, nodes[finite], 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(count > 0, total / count, np.nan)


def _save(
    fig: Any,
    path: Path,
    dpi: int,
    preview: bool,
    theme: config.Theme | None = None,
    *,
    block: TitleBlock | None = None,
    three_d: bool = False,
) -> Path:
    import matplotlib.pyplot as plt

    th = theme or config.theme()
    # `_finalize`, BUKAN `fig.tight_layout()` polos: yang polos memotong kop karena
    # `savefig` di bawah sengaja tidak memakai `bbox_inches` (agar seluruh PNG dalam satu
    # laporan berdimensi seragam). Dijaga `test_kop_tidak_terpotong_savefig`.
    _finalize(fig, block, th, three_d=three_d)
    path.parent.mkdir(parents=True, exist_ok=True)
    # `facecolor` WAJIB diteruskan: tanpa itu PNG tema gelap keluar berlatar putih dengan
    # teks terang -- nyaris tak terbaca, dan lolos bila test hanya memeriksa ukuran berkas.
    fig.savefig(path, dpi=dpi, facecolor=th.background)
    if preview:  # pragma: no cover - interaktif
        plt.show()
    plt.close(fig)
    return path


# ---------------------------------------------------------------------------
# Denah mesh (Fase 1)
# ---------------------------------------------------------------------------


def render_mesh_plan(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    *,
    mesh_size_m: float | None = None,
    n_tri: int = 0,
    style: PlotStyle | None = None,
    block: TitleBlock | None = None,
) -> Path:
    """Denah mesh + label pile & pier (PRD Bagian 9.1 `mesh_plan.png`).

    `project_name` sudah tidak ada: nama proyek kini datang lewat `block`. Dua sumber
    untuk satu nama adalah cara keduanya mulai berbeda.
    """
    st = style or PlotStyle()
    _use_agg(st.preview)
    from matplotlib.collections import PolyCollection

    unit = io_utils.display_unit("length")
    stats = [f"{mesh.n_nodes:,} node", f"{mesh.n_elements:,} quad", f"{n_tri:,} tri"]
    if mesh_size_m is not None:
        stats.append(f"h = {_to_mm(mesh_size_m):.0f} {unit}")
    block = _with_geometry_context(block, geom).with_assumptions(" · ".join(stats))

    fig, ax = _figure_for(geom, theme=st.theme, reserve_bottom_in=_reserve_bottom_in(block, 12.0))
    ax.add_collection(
        PolyCollection(
            _element_polygons(mesh),
            facecolors=_face_colors(mesh, st.theme),
            edgecolors=st.theme.edge,
            linewidths=0.25,
        )
    )
    _annotate_plan(ax, geom, theme=st.theme)
    _set_heading(ax, st.theme, heading="Denah Mesh Pilecap")

    _save(fig, path, st.dpi, st.preview, st.theme, block=block)
    _log.info("%s ditulis: %s", path.name, path)
    return path


def _with_geometry_context(block: TitleBlock | None, geom: GeometryModel) -> TitleBlock:
    """Sisipkan baris `GEOMETRI OVERRIDE` sebagai PERINGATAN bila ada override CSV.

    PRD Bagian 9.3 menuntut override terlihat di gambar. Sebelumnya itu dicapai dengan
    mewarnai seluruh judul; kini ia baris tersendiri berwarna peringatan, sehingga judul
    dapat tetap netral.
    """
    base = block or TitleBlock()
    override = _override_subtitle(geom)
    return base.with_warnings(override) if override else base


def render_geometry_plan(
    geom: GeometryModel,
    *,
    style: PlotStyle | None = None,
    block: TitleBlock | None = None,
) -> Any:
    """Denah geometri TANPA mesh, dikembalikan sebagai `Figure` (bukan ditulis ke berkas).

    Dipakai pratinjau `pilecap-ui`: pengguna ingin melihat susunan pile/pilecap/pier
    sebelum menjalankan rantai penuh, dan pada titik itu mesh belum -- dan tidak perlu --
    dibangun. Menghindari gmsh membuat pratinjau berjalan dalam hitungan milidetik.

    Anotasinya `_annotate_plan` yang sama dengan seluruh plot denah lain, sehingga apa yang
    dilihat pengguna di formulir persis apa yang muncul di laporan.

    Jalur ini TIDAK lewat `_save`, tetapi tetap memanggil `_finalize` -- itulah yang membuat
    kop tampil sama di `st.pyplot` seperti di PNG, tanpa bergantung `bbox_inches`.
    """
    st = style or PlotStyle()
    _use_agg(st.preview)

    unit = io_utils.display_unit("length")
    block = _with_geometry_context(block, geom).with_assumptions(
        f"Luas {geom.pilecap_area:,.2f} m² · t {_to_mm(geom.thickness):,.0f} {unit} · "
        f"{geom.n_piles} pile · {geom.n_piers} pier"
    )

    fig, ax = _figure_for(
        geom, width=7.0, theme=st.theme, reserve_bottom_in=_reserve_bottom_in(block, 7.0)
    )
    _annotate_plan(ax, geom, theme=st.theme)
    _set_heading(ax, st.theme, heading="Denah Geometri Pilecap")
    _finalize(fig, block, st.theme, three_d=False)
    return fig


# ---------------------------------------------------------------------------
# Kontur momen & geser
# ---------------------------------------------------------------------------


def element_values_from_nodal(mesh: MeshModel, nodal: np.ndarray) -> np.ndarray:
    """Rata-rata nilai nodal ke tiap elemen, agar dapat digambar per elemen.

    Dipakai kontur lendutan: lendutan adalah besaran NODAL, sedangkan seluruh kontur
    lain per elemen. Merata-ratakan 4 node menjaga satu gaya penyajian dan tidak
    menambah kehalusan yang tidak dihitung.

    `nodal` WAJIB 1-D. Menyerahkan seluruh matriks perpindahan `(N, 6)` akan
    menghasilkan array `(M, 6)` yang tetap "berhasil" digambar sebagian dan baru
    meledak jauh di hilir -- karena itu ditolak di sini.
    """
    values = np.asarray(nodal, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError(
            f"`nodal` harus 1-D per node, diterima bentuk {values.shape}. "
            "Untuk lendutan vertikal berikan kolom uz saja, mis. `displacements[:, 2]`."
        )
    if values.shape[0] != mesh.n_nodes:
        raise ValueError(
            f"`nodal` berisi {values.shape[0]} nilai, sedangkan mesh punya {mesh.n_nodes} node."
        )
    return np.asarray(values[mesh.elem_conn].mean(axis=1), dtype=np.float64)


def _build_norm(vmin: float, vmax: float, diverging: bool) -> tuple[Any, str]:
    """Norm warna + catatan bila skala tidak dapat dipusatkan di nol."""
    from matplotlib.colors import Normalize, TwoSlopeNorm

    if not diverging:
        return Normalize(vmin=vmin, vmax=vmax), ""
    if vmin < 0.0 < vmax:
        return TwoSlopeNorm(vmin=vmin, vcenter=0.0, vmax=vmax), ""
    # TwoSlopeNorm menuntut vmin < vcenter < vmax. Bila seluruh nilai satu tanda,
    # dipakai skala SIMETRIS agar posisi nol tetap terbaca di colorbar -- bukan
    # diam-diam berganti menjadi skala sekuensial yang menyamarkan tandanya.
    vabs = max(abs(vmin), abs(vmax)) or 1.0
    return Normalize(vmin=-vabs, vmax=vabs), " (seluruh nilai satu tanda; skala simetris)"


def _mark_extremes(
    ax: Any,
    mesh: MeshModel,
    values: np.ndarray,
    finite: np.ndarray,
    unit: str,
    theme: config.Theme,
    *,
    include_min: bool = True,
) -> None:
    """Penanda maks/min bergaya shell-kit: berlian + callout melengkung.

    PRD Bagian 9.3 mewajibkan "nilai maks/min + lokasinya"; bentuknya mengikuti shell-kit
    (berlian `ms=12` bertepi putih, kotak membulat, panah `arc3`) agar plot pilecap dan
    plot shell-kit dapat dibaca berdampingan tanpa berganti kebiasaan mata.
    """
    idx_max = int(np.nanargmax(np.where(finite, values, -np.inf)))
    entries = [(idx_max, "MAKS", theme.color_max)]
    if include_min:
        idx_min = int(np.nanargmin(np.where(finite, values, np.inf)))
        entries.append((idx_min, "MIN", theme.color_min))

    for index, label, color in entries:
        cx, cy = _to_mm(mesh.elem_centroid[index])
        ax.plot(
            cx,
            cy,
            marker="D",
            markersize=9,
            color=color,
            markeredgecolor=theme.background,
            markeredgewidth=1.5,
            zorder=10,
        )
        ax.annotate(
            f"{label}: {values[index]:,.1f} {unit}\n({cx:,.0f}, {cy:,.0f})",
            xy=(cx, cy),
            textcoords="offset points",
            xytext=(26, 22),
            fontsize=8,
            fontweight="bold",
            color=theme.text,
            zorder=11,
            bbox={
                "boxstyle": "round,pad=0.4",
                "facecolor": theme.background,
                "edgecolor": theme.text,
                "linewidth": 1.0,
                "alpha": 0.9,
            },
            arrowprops={
                "arrowstyle": "-|>,head_width=0.4,head_length=0.6",
                "color": theme.text,
                "linewidth": 1.5,
                "connectionstyle": "arc3,rad=0.3",
            },
        )


def _watermark(fig: Any, theme: config.Theme) -> None:
    """Watermark di kanan-bawah FIGUR, bukan di dalam axes.

    Dulu ia menempati sudut kiri-bawah axes -- tempat yang kini ditempati kop, dan yang
    sejak dulu sudah berebut dengan legenda NaN dan legenda "tidak ada batang yang
    memadai" (keduanya `loc="lower left"`).
    """
    fig.text(
        0.995,
        0.006,
        f"pilecap-fem | TEMA {theme.name.upper()}",
        color=theme.text,
        alpha=0.3,
        fontsize=7,
        fontweight="bold",
        va="bottom",
        ha="right",
        zorder=12,
    )


def _inadequate_badge(ax: Any, n: int, theme: config.Theme, label: str) -> None:
    """Badge merah-abu di kanan bawah, mengikuti shell-kit.

    Dibuat mencolok dengan sengaja: elemen yang penampangnya tidak memadai adalah satu-
    satunya hal pada plot tulangan yang membatalkan seluruh pembacaan lainnya.
    """
    if not n:
        return
    ax.text(
        0.98,
        0.02,
        f"{label}: {n:,} elemen",
        transform=ax.transAxes,
        color="#FFFFFF",
        fontsize=9,
        fontweight="bold",
        va="bottom",
        ha="right",
        zorder=12,
        bbox={
            "boxstyle": "round,pad=0.4",
            "facecolor": theme.color_inadequate,
            "edgecolor": "#FFFFFF",
            "linewidth": 1.0,
        },
    )


def _draw_field(
    ax: Any,
    mesh: MeshModel,
    values: np.ndarray,
    *,
    cmap: Any,
    norm: Any,
    method: str,
    theme: config.Theme,
) -> Any:
    """Gambar medan per elemen dengan metode terpilih; kembalikan mappable untuk colorbar."""
    from matplotlib.collections import PolyCollection

    if method == "element-center":
        collection = PolyCollection(
            _element_polygons(mesh),
            array=np.ma.masked_invalid(values),
            cmap=cmap,
            norm=norm,
            edgecolors="none",
        )
        ax.add_collection(collection)
        return collection

    # average-nodal: nilai elemen dirata-ratakan ke node lalu dihaluskan.
    x, y, tris = _triangulation(mesh)
    nodal = _nodal_from_elements(mesh, values)
    filled = ax.tricontourf(
        x,
        y,
        tris,
        np.nan_to_num(nodal, nan=float(np.nanmin(nodal))),
        levels=config.CONTOUR_LEVELS,
        cmap=cmap,
        norm=norm,
        extend="both",
    )
    ax.tricontour(
        x,
        y,
        tris,
        np.nan_to_num(nodal, nan=float(np.nanmin(nodal))),
        levels=config.CONTOUR_LEVELS,
        colors=theme.text,
        linewidths=0.2,
        alpha=0.5,
    )
    return filled


def render_contour(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    values_si: np.ndarray,
    *,
    quantity: str,
    title: str,
    combo: str = "",
    diverging: bool = True,
    pz_by_pile: dict[str, float] | None = None,
    style: PlotStyle | None = None,
    block: TitleBlock | None = None,
    n_inadequate: int = 0,
) -> Path:
    """Kontur satu besaran per elemen (PRD Bagian 9.1 `contour_*.png`).

    `values_si` adalah nilai SI per elemen; konversi ke satuan tampilan terjadi di sini
    (PRD Bagian 4.3). `quantity` menentukan satuan colorbar lewat `config.DISPLAY_UNITS`.

    `block` membawa asumsi yang melahirkan angka pada gambar. Tanpa itu gambar yang dicetak
    dan ditempel ke laporan kehilangan seluruh konteksnya. Nilai maks/min TIDAK ikut ke
    kop: `_mark_extremes` sudah menuliskannya di atas elemennya sendiri beserta koordinat,
    dan colorbar membawa rentangnya.
    """
    st = style or PlotStyle()
    _use_agg(st.preview)
    from matplotlib.patches import Patch

    unit = io_utils.display_unit(quantity)
    values = np.asarray(io_utils.to_display(np.asarray(values_si, dtype=np.float64), quantity))
    finite = np.isfinite(values)
    n_nan = int((~finite).size - finite.sum())

    if not finite.any():
        raise ValueError(
            f"Seluruh nilai untuk kontur {path.name} tidak terdefinisi (NaN); "
            "tidak ada yang dapat digambar."
        )

    vmin, vmax = float(values[finite].min()), float(values[finite].max())
    norm, norm_note = _build_norm(vmin, vmax, diverging)
    cmap_name = st.theme.cmap_force if diverging else st.theme.cmap_rebar
    cmap = matplotlib.colormaps[cmap_name].copy()
    cmap.set_bad(st.theme.color_nan)

    block = _with_geometry_context(block, geom)
    if norm_note:
        # Tanpa catatan ini skala simetris terbaca seperti skala sekuensial biasa.
        block = block.with_notes(norm_note.strip(" ()").capitalize() + ".")
    if st.method != config.DEFAULT_CONTOUR_METHOD:
        # WAJIB tampil: `average-nodal` menampilkan kehalusan yang tidak pernah dihitung.
        block = block.with_assumptions(f"Metode kontur: {st.method}")

    fig, ax = _figure_for(geom, theme=st.theme, reserve_bottom_in=_reserve_bottom_in(block, 12.0))
    mappable = _draw_field(ax, mesh, values, cmap=cmap, norm=norm, method=st.method, theme=st.theme)
    _annotate_plan(ax, geom, pz_by_pile=pz_by_pile, theme=st.theme)

    colorbar = fig.colorbar(mappable, ax=ax, shrink=0.85, pad=0.02)
    colorbar.set_label(f"{title} [{unit}]", color=st.theme.text)
    colorbar.ax.tick_params(colors=st.theme.text)

    _mark_extremes(ax, mesh, values, finite, unit, st.theme)
    _inadequate_badge(ax, n_inadequate, st.theme, "PENAMPANG TIDAK MEMADAI")

    if n_nan:
        # Jumlah elemen masuk ke LABEL legenda -- ia menerangkan warna, jadi tempatnya di
        # sebelah warna itu, bukan di kop satu inci di bawah gambar.
        ax.legend(
            handles=[
                Patch(facecolor=st.theme.color_nan, label=f"{config.LABEL_NAN} ({n_nan:,} elemen)")
            ],
            loc="upper left",
            fontsize=8,
            framealpha=0.9,
            labelcolor=st.theme.text,
            facecolor=st.theme.background,
            edgecolor=st.theme.grid,
        )
    _set_heading(ax, st.theme, heading=title, combo=combo)

    _save(fig, path, st.dpi, st.preview, st.theme, block=block)
    _log.debug("%s ditulis (maks %.3f, min %.3f %s)", path.name, vmax, vmin, unit)
    return path


def render_categorical(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    codes: np.ndarray,
    *,
    labels: tuple[str, ...] | list[str],
    title: str,
    combo: str = "",
    pz_by_pile: dict[str, float] | None = None,
    style: PlotStyle | None = None,
    block: TitleBlock | None = None,
    n_inadequate: int = 0,
    zero_label: str = "tanpa tulangan",
) -> Path:
    """Plot KATEGORIKAL: tiap elemen diwarnai menurut batang yang terpilih.

    Terpisah dari `render_contour` dengan sengaja. Keduanya melayani model warna yang
    tidak berhubungan: kontur memetakan besaran kontinu ke gradien, sedangkan ini
    memetakan pilihan diskret ke warna yang harus mudah dibedakan satu sama lain.
    Menggabungkannya akan menghasilkan satu fungsi dengan dua cabang yang nyaris tidak
    berbagi apa pun selain judul.

    `codes` berisi indeks kategori: `0` berarti tidak perlu tulangan (selalu putih),
    `1..len(labels)` menunjuk `labels`, dan `NaN` berarti tidak ada batang yang memadai.
    Selalu digambar datar per elemen -- menghaluskan pilihan diskret tidak bermakna.
    """
    st = style or PlotStyle()
    _use_agg(st.preview)
    from matplotlib.collections import PolyCollection
    from matplotlib.colors import BoundaryNorm, ListedColormap
    from matplotlib.patches import Patch

    values = np.asarray(codes, dtype=np.float64)
    n_bins = len(labels) + 1  # +1 untuk kategori "tanpa tulangan"
    palette = list(config.CATEGORICAL_COLORS[:n_bins])
    if len(palette) < n_bins:  # daftar kode lebih panjang dari palet bawaan
        extra = matplotlib.colormaps["turbo"](np.linspace(0.05, 0.95, n_bins - len(palette)))
        palette += [matplotlib.colors.to_hex(c) for c in extra]

    cmap = ListedColormap(palette)
    cmap.set_bad(st.theme.color_inadequate)
    norm = BoundaryNorm(np.arange(n_bins + 1) - 0.5, cmap.N)

    used = sorted({int(v) for v in values[np.isfinite(values)] if v > 0})
    dipakai = ", ".join(labels[i - 1] for i in used) if used else "(tidak ada)"
    block = _with_geometry_context(block, geom).with_notes(f"Kategori terpakai: {dipakai}.")

    fig, ax = _figure_for(geom, theme=st.theme, reserve_bottom_in=_reserve_bottom_in(block, 12.0))
    collection = PolyCollection(
        _element_polygons(mesh),
        array=np.ma.masked_invalid(values),
        cmap=cmap,
        norm=norm,
        edgecolors="none",
    )
    ax.add_collection(collection)
    _annotate_plan(ax, geom, pz_by_pile=pz_by_pile, theme=st.theme)

    colorbar = fig.colorbar(collection, ax=ax, shrink=0.85, pad=0.02, ticks=np.arange(n_bins))
    colorbar.ax.set_yticklabels([zero_label, *labels])
    colorbar.set_label(title, color=st.theme.text)
    colorbar.ax.tick_params(colors=st.theme.text)

    n_bad = int(np.count_nonzero(~np.isfinite(values)))
    _inadequate_badge(ax, n_inadequate or n_bad, st.theme, "TIDAK ADA BATANG YANG MEMADAI")

    if n_bad:
        ax.legend(
            handles=[
                Patch(
                    facecolor=st.theme.color_inadequate,
                    label=f"Tidak ada batang yang memadai ({n_bad:,} elemen)",
                )
            ],
            loc="upper left",
            fontsize=8,
            framealpha=0.9,
            labelcolor=st.theme.text,
            facecolor=st.theme.background,
            edgecolor=st.theme.grid,
        )

    _set_heading(ax, st.theme, heading=title, combo=combo)

    _save(fig, path, st.dpi, st.preview, st.theme, block=block)
    _log.debug("%s ditulis (%d kategori dipakai)", path.name, len(used))
    return path


def render_boundary_load_check(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    *,
    pz_by_pile: dict[str, float] | None = None,
    style: PlotStyle | None = None,
    block: TitleBlock | None = None,
) -> Path:
    """Peta node jepit & area terbeban (PRD Bagian 9.1 `boundary_load_check.png`).

    Gambar ini menjawab satu pertanyaan yang sulit dijawab dari angka: apakah tumpuan
    dan beban benar-benar menempel di tempat yang seharusnya. Physical group yang salah
    atau kosong terlihat langsung di sini.

    Cacahan node jepit & elemen terbeban tidak masuk kop: label legendanya sudah memuat
    angka yang sama persis, dan mengulangnya di dua tempat hanya membuka peluang keduanya
    berbeda.
    """
    st = style or PlotStyle()
    _use_agg(st.preview)
    from matplotlib.collections import PolyCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    block = _with_geometry_context(block, geom)
    fig, ax = _figure_for(geom, theme=st.theme, reserve_bottom_in=_reserve_bottom_in(block, 12.0))

    is_pier = np.zeros(mesh.n_elements, dtype=bool)
    is_pile = np.zeros(mesh.n_elements, dtype=bool)
    for name in mesh.pier_groups():
        is_pier |= mesh.group_mask(name)
    for name in mesh.pile_groups():
        is_pile |= mesh.group_mask(name)

    colors = np.where(is_pier, st.theme.pier, np.where(is_pile, st.theme.pile, st.theme.cap))
    ax.add_collection(
        PolyCollection(
            _element_polygons(mesh),
            facecolors=list(colors),
            edgecolors=st.theme.edge,
            linewidths=0.2,
        )
    )

    fixed_nodes: set[int] = set()
    for name in mesh.pier_groups():
        fixed_nodes.update(int(n) for n in mesh.nodes_in_group(name))
    if fixed_nodes:
        pts = _to_mm(mesh.node_xy[sorted(fixed_nodes)])
        ax.plot(
            pts[:, 0],
            pts[:, 1],
            linestyle="None",
            marker="s",
            markersize=2.5,
            color=st.theme.pier_line,
            zorder=8,
        )

    _annotate_plan(ax, geom, pz_by_pile=pz_by_pile, theme=st.theme)

    ax.legend(
        handles=[
            Line2D(
                [],
                [],
                linestyle="None",
                marker="s",
                markersize=5,
                color=st.theme.pier_line,
                label=f"Node JEPIT 6 DOF ({len(fixed_nodes)})",
            ),
            Patch(facecolor=st.theme.pile, label=f"Elemen terbeban ({int(is_pile.sum())})"),
            Patch(
                facecolor=st.theme.cap,
                label=f"Pelat bebas ({int((~is_pier & ~is_pile).sum())})",
            ),
        ],
        loc="upper right",
        fontsize=8,
        framealpha=0.9,
        labelcolor=st.theme.text,
        facecolor=st.theme.background,
        edgecolor=st.theme.grid,
    )
    _set_heading(ax, st.theme, heading="Cek Visual Tumpuan & Pembebanan")

    _save(fig, path, st.dpi, st.preview, st.theme, block=block)
    _log.info("%s ditulis: %s", path.name, path)
    return path


# ---------------------------------------------------------------------------
# opsvis -- MEMBACA DOMAIN OpenSees YANG HIDUP
# ---------------------------------------------------------------------------


def opsvis_would_skip(n_elements: int, force: bool) -> bool:
    return (not force) and n_elements > config.OPSVIS_MAX_ELEMENTS


def _skip_message(n_elements: int) -> str:
    return (
        f"Plot opsvis DILEWATI: {n_elements:,} elemen melebihi ambang "
        f"{config.OPSVIS_MAX_ELEMENTS:,} (config.OPSVIS_MAX_ELEMENTS). "
        "Pengukuran menunjukkan opsv.plot_defo tumbuh lebih cepat dari linier "
        "(5,1 detik untuk 1.200 elemen). Gunakan --opsvis untuk tetap membuatnya."
    )


def deformation_scale(mesh: MeshModel, displacements: np.ndarray, ratio: float = 0.1) -> float:
    """Faktor skala deformasi agar lendutan maksimum tampak `ratio` x ukuran model.

    Dihitung sendiri (bukan diserahkan ke opsvis) supaya angkanya DIKETAHUI dan dapat
    dicantumkan di judul gambar, sesuai PRD Bagian 9.3.
    """
    max_disp = float(np.max(np.abs(np.asarray(displacements)[:, 2])))
    if max_disp <= 0.0:
        return 1.0
    xmin, ymin = mesh.node_xy.min(axis=0)
    xmax, ymax = mesh.node_xy.max(axis=0)
    span = max(xmax - xmin, ymax - ymin)
    return float(ratio * span / max_disp)


def _render_opsvis(
    path: Path,
    plot_call: Any,
    *,
    title: str,
    combo: str = "",
    n_elements: int,
    force: bool,
    style: PlotStyle,
    warnings: list[str],
    block: TitleBlock | None = None,
) -> Path | None:
    """Kerangka bersama kedua plot opsvis: ambang, figure 3D, penanganan kegagalan."""
    if opsvis_would_skip(n_elements, force):
        message = _skip_message(n_elements)
        _log.warning("%s", message)
        warnings.append(message)
        return None

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    reserve = _reserve_bottom_in(block, 11.0)
    fig = plt.figure(figsize=(11.0, 8.0 + reserve + _HEADING_RESERVE_IN))
    fig.patch.set_facecolor(style.theme.background)
    ax = fig.add_subplot(projection="3d")
    ax.set_facecolor(style.theme.background)
    try:
        plot_call(ax)
    except Exception as exc:
        # Sengaja menangkap seluruh exception: plot BUKAN sumber angka desain, dan
        # matinya satu gambar tidak boleh membatalkan analisis yang sudah lulus VC-0.
        # Kegagalannya tetap dicatat sebagai WARNING di log DAN laporan.
        plt.close(fig)
        message = (
            f"Plot opsvis {path.name} GAGAL dibuat: {type(exc).__name__}: {exc}. "
            "Hasil analisis TIDAK terpengaruh -- seluruh angka ada di CSV dan sudah "
            "lulus VC-0. Kegagalan ini dicatat agar tidak lolos diam-diam."
        )
        _log.warning("%s", message)
        warnings.append(message)
        return None

    _set_heading(ax, style.theme, heading=title, combo=combo)
    # Lewat `_save` agar jaminan `facecolor=` dan penanganan kop terpusat di satu tempat.
    _save(fig, path, style.dpi, False, style.theme, block=block, three_d=True)
    _log.info("%s ditulis: %s", path.name, path)
    return path


def render_opsvis_model(
    path: Path,
    *,
    n_elements: int,
    n_fixed_nodes: int,
    force: bool = False,
    style: PlotStyle | None = None,
    warnings: list[str] | None = None,
    block: TitleBlock | None = None,
) -> Path | None:
    """`opsv.plot_model()` -- cek geometri & tumpuan (PRD Bagian 9.3).

    HARUS dipanggil selagi domain OpenSees masih hidup: opsvis membaca dari domain,
    bukan dari file.
    """
    import opsvis as opsv

    return _render_opsvis(
        path,
        lambda ax: opsv.plot_model(
            node_labels=0,
            element_labels=0,
            gauss_points=False,
            local_axes=False,
            ax=ax,
        ),
        title="Model OpenSees",
        n_elements=n_elements,
        force=force,
        style=style or PlotStyle(),
        warnings=warnings if warnings is not None else [],
        block=(block or TitleBlock()).with_assumptions(
            f"{n_elements:,} elemen shell · {n_fixed_nodes:,} node jepit",
            "opsv.plot_model() — label node & elemen dimatikan agar terbaca",
        ),
    )


def render_opsvis_defo(
    path: Path,
    *,
    combo: str,
    sfac: float,
    max_deflection_m: float,
    n_elements: int,
    force: bool = False,
    style: PlotStyle | None = None,
    warnings: list[str] | None = None,
    block: TitleBlock | None = None,
) -> Path | None:
    """`opsv.plot_defo()` -- deformasi; faktor skala WAJIB dinyatakan (PRD Bagian 9.3)."""
    import opsvis as opsv

    max_mm = io_utils.to_display(max_deflection_m, "deflection")
    return _render_opsvis(
        path,
        lambda ax: opsv.plot_defo(sfac=sfac, node_supports=False, ax=ax),
        title="Bentuk Terdeformasi",
        combo=combo,
        n_elements=n_elements,
        force=force,
        style=style or PlotStyle(),
        warnings=warnings if warnings is not None else [],
        block=(block or TitleBlock()).with_assumptions(
            f"Faktor skala deformasi {sfac:,.1f}× · lendutan maksimum {max_mm:,.2f} mm"
        ),
    )
