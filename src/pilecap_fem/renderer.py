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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

from pilecap_fem import config, io_utils
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel

_log = config.get_logger("renderer")


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


def _use_agg(preview: bool) -> None:
    if not preview:
        matplotlib.use("Agg", force=True)


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
    geom: GeometryModel, width: float = 12.0, theme: config.Theme | None = None
) -> tuple[Any, Any]:
    import matplotlib.pyplot as plt

    th = theme or config.theme()
    xmin, ymin, xmax, ymax = geom.pilecap.bounds
    span_x, span_y = xmax - xmin, ymax - ymin
    aspect = (span_y / span_x) if span_x > 0 else 1.0
    fig, ax = plt.subplots(figsize=(width, max(5.0, width * aspect * 0.85)))
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


def _save(fig: Any, path: Path, dpi: int, preview: bool, theme: config.Theme | None = None) -> Path:
    import matplotlib.pyplot as plt

    th = theme or config.theme()
    fig.tight_layout()
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
    project_name: str = "",
    mesh_size_m: float | None = None,
    n_tri: int = 0,
    style: PlotStyle | None = None,
) -> Path:
    """Denah mesh + label pile & pier (PRD Bagian 9.1 `mesh_plan.png`)."""
    st = style or PlotStyle()
    _use_agg(st.preview)
    from matplotlib.collections import PolyCollection

    unit = io_utils.display_unit("length")
    fig, ax = _figure_for(geom, theme=st.theme)
    ax.add_collection(
        PolyCollection(
            _element_polygons(mesh),
            facecolors=_face_colors(mesh, st.theme),
            edgecolors=st.theme.edge,
            linewidths=0.25,
        )
    )
    _annotate_plan(ax, geom, theme=st.theme)

    title = "Denah Mesh Pilecap"
    if project_name:
        title += f" - {project_name}"
    subtitle_parts = [
        f"{mesh.n_nodes:,} node",
        f"{mesh.n_elements:,} quad",
        f"{n_tri:,} tri",
    ]
    if mesh_size_m is not None:
        subtitle_parts.append(f"h = {_to_mm(mesh_size_m):.0f} {unit}")
    subtitle = " | ".join(subtitle_parts)

    override = _override_subtitle(geom)
    if override is not None:
        ax.set_title(f"{title}\n{subtitle}\n{override}", fontsize=11, color=st.theme.pier_line)
    else:
        ax.set_title(f"{title}\n{subtitle}", fontsize=11, color=st.theme.text)
    _watermark(ax, st.theme)

    _save(fig, path, st.dpi, st.preview, st.theme)
    _log.info("%s ditulis: %s", path.name, path)
    return path


def render_geometry_plan(
    geom: GeometryModel,
    *,
    project_name: str = "",
    style: PlotStyle | None = None,
) -> Any:
    """Denah geometri TANPA mesh, dikembalikan sebagai `Figure` (bukan ditulis ke berkas).

    Dipakai pratinjau `pilecap-ui`: pengguna ingin melihat susunan pile/pilecap/pier
    sebelum menjalankan rantai penuh, dan pada titik itu mesh belum -- dan tidak perlu --
    dibangun. Menghindari gmsh membuat pratinjau berjalan dalam hitungan milidetik.

    Anotasinya `_annotate_plan` yang sama dengan seluruh plot denah lain, sehingga apa yang
    dilihat pengguna di formulir persis apa yang muncul di laporan.
    """
    st = style or PlotStyle()
    _use_agg(st.preview)

    unit = io_utils.display_unit("length")
    fig, ax = _figure_for(geom, width=7.0, theme=st.theme)
    _annotate_plan(ax, geom, theme=st.theme)

    title = "Denah Geometri Pilecap"
    if project_name:
        title += f" - {project_name}"
    subtitle = " | ".join(
        [
            f"luas {geom.pilecap_area:,.2f} m2",
            f"t = {_to_mm(geom.thickness):.0f} {unit}",
            f"{geom.n_piles} pile",
            f"{geom.n_piers} pier",
        ]
    )
    # Dibungkus: figur pratinjau sengaja sempit (7 inci, agar muat di panel formulir), dan
    # baris override memuat tiga nama berkas sekaligus sehingga pasti terpotong di kedua
    # sisi bila dibiarkan satu baris -- justru baris yang paling perlu terbaca utuh.
    override = _override_subtitle(geom)
    color = st.theme.pier_line if override is not None else st.theme.text
    wrapped = textwrap.fill(override, width=62) if override else ""
    ax.set_title(
        f"{title}\n{subtitle}" + (f"\n{wrapped}" if wrapped else ""), fontsize=10, color=color
    )
    _watermark(ax, st.theme)
    fig.tight_layout()
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


def _watermark(ax: Any, theme: config.Theme) -> None:
    ax.text(
        0.01,
        0.01,
        f"pilecap-fem | TEMA {theme.name.upper()}",
        transform=ax.transAxes,
        color=theme.text,
        alpha=0.3,
        fontsize=8,
        fontweight="bold",
        va="bottom",
        ha="left",
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
    info: str = "",
    n_inadequate: int = 0,
) -> Path:
    """Kontur satu besaran per elemen (PRD Bagian 9.1 `contour_*.png`).

    `values_si` adalah nilai SI per elemen; konversi ke satuan tampilan terjadi di sini
    (PRD Bagian 4.3). `quantity` menentukan satuan colorbar lewat `config.DISPLAY_UNITS`.

    `info` adalah baris konteks material (`f'c`, `fy`, tebal, selimut, `d_eff`). Tanpa itu
    gambar yang dicetak dan ditempel ke laporan kehilangan seluruh asumsi yang melahirkan
    angkanya.
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

    fig, ax = _figure_for(geom, theme=st.theme)
    mappable = _draw_field(ax, mesh, values, cmap=cmap, norm=norm, method=st.method, theme=st.theme)
    _annotate_plan(ax, geom, pz_by_pile=pz_by_pile, theme=st.theme)

    colorbar = fig.colorbar(mappable, ax=ax, shrink=0.85, pad=0.02)
    colorbar.set_label(f"{title} [{unit}]", color=st.theme.text)
    colorbar.ax.tick_params(colors=st.theme.text)

    _mark_extremes(ax, mesh, values, finite, unit, st.theme)
    _inadequate_badge(ax, n_inadequate, st.theme, "PENAMPANG TIDAK MEMADAI")
    _watermark(ax, st.theme)

    if n_nan:
        ax.legend(
            handles=[Patch(facecolor=st.theme.color_nan, label=config.LABEL_NAN)],
            loc="lower left",
            fontsize=8,
            framealpha=0.9,
            labelcolor=st.theme.text,
            facecolor=st.theme.background,
            edgecolor=st.theme.grid,
        )

    heading = title if not combo else f"{title} - Kombinasi {combo}"
    subtitle = f"maks {vmax:,.1f} | min {vmin:,.1f} {unit}{norm_note}"
    if n_nan:
        subtitle += f" | {n_nan} elemen NaN"
    if st.method != config.DEFAULT_CONTOUR_METHOD:
        subtitle += f" | metode {st.method}"
    if info:
        subtitle += f"\n{info}"
    ax.set_title(f"{heading}\n{subtitle}", fontsize=11, color=st.theme.text)

    _save(fig, path, st.dpi, st.preview, st.theme)
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
    info: str = "",
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

    fig, ax = _figure_for(geom, theme=st.theme)
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

    used = sorted({int(v) for v in values[np.isfinite(values)] if v > 0})
    n_bad = int(np.count_nonzero(~np.isfinite(values)))
    _inadequate_badge(ax, n_inadequate or n_bad, st.theme, "TIDAK ADA BATANG YANG MEMADAI")
    _watermark(ax, st.theme)

    if n_bad:
        ax.legend(
            handles=[
                Patch(facecolor=st.theme.color_inadequate, label="tidak ada batang yang memadai")
            ],
            loc="lower left",
            fontsize=8,
            framealpha=0.9,
            labelcolor=st.theme.text,
            facecolor=st.theme.background,
            edgecolor=st.theme.grid,
        )

    heading = title if not combo else f"{title} - Kombinasi {combo}"
    dipakai = ", ".join(labels[i - 1] for i in used) if used else "(tidak ada)"
    subtitle = f"dipakai: {dipakai}"
    if info:
        subtitle += f"\n{info}"
    ax.set_title(f"{heading}\n{subtitle}", fontsize=11, color=st.theme.text)

    _save(fig, path, st.dpi, st.preview, st.theme)
    _log.debug("%s ditulis (%d kategori dipakai)", path.name, len(used))
    return path


def render_boundary_load_check(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    *,
    pz_by_pile: dict[str, float] | None = None,
    style: PlotStyle | None = None,
) -> Path:
    """Peta node jepit & area terbeban (PRD Bagian 9.1 `boundary_load_check.png`).

    Gambar ini menjawab satu pertanyaan yang sulit dijawab dari angka: apakah tumpuan
    dan beban benar-benar menempel di tempat yang seharusnya. Physical group yang salah
    atau kosong terlihat langsung di sini.
    """
    st = style or PlotStyle()
    _use_agg(st.preview)
    from matplotlib.collections import PolyCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig, ax = _figure_for(geom, theme=st.theme)

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
    ax.set_title(
        "Cek Visual Tumpuan & Pembebanan\n"
        f"{len(fixed_nodes)} node jepit di {len(mesh.pier_groups())} pier | "
        f"{int(is_pile.sum())} elemen terbeban di {len(mesh.pile_groups())} pile",
        fontsize=11,
        color=st.theme.text,
    )
    _watermark(ax, st.theme)

    _save(fig, path, st.dpi, st.preview, st.theme)
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
    n_elements: int,
    force: bool,
    style: PlotStyle,
    warnings: list[str],
) -> Path | None:
    """Kerangka bersama kedua plot opsvis: ambang, figure 3D, penanganan kegagalan."""
    if opsvis_would_skip(n_elements, force):
        message = _skip_message(n_elements)
        _log.warning("%s", message)
        warnings.append(message)
        return None

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    fig = plt.figure(figsize=(11.0, 8.0))
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

    ax.set_title(title, fontsize=11, color=style.theme.text)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=style.dpi, facecolor=style.theme.background)
    plt.close(fig)
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
        title=(
            f"Model OpenSees - {n_elements:,} elemen shell, {n_fixed_nodes:,} node jepit\n"
            "opsv.plot_model() | label node & elemen dimatikan agar terbaca"
        ),
        n_elements=n_elements,
        force=force,
        style=style or PlotStyle(),
        warnings=warnings if warnings is not None else [],
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
) -> Path | None:
    """`opsv.plot_defo()` -- deformasi, faktor skala dicantumkan di judul."""
    import opsvis as opsv

    max_mm = io_utils.to_display(max_deflection_m, "deflection")
    return _render_opsvis(
        path,
        lambda ax: opsv.plot_defo(sfac=sfac, node_supports=False, ax=ax),
        title=(
            f"Deformasi - Kombinasi {combo}\n"
            f"faktor skala = {sfac:,.1f}x | lendutan maksimum = {max_mm:,.2f} mm"
        ),
        n_elements=n_elements,
        force=force,
        style=style or PlotStyle(),
        warnings=warnings if warnings is not None else [],
    )
