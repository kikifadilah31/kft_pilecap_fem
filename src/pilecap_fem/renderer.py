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

from pathlib import Path
from typing import Any

import matplotlib
import numpy as np

from pilecap_fem import config, io_utils
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel

_log = config.get_logger("renderer")

_COLOR_CAP = "#eef2f6"
_COLOR_PILE = "#bcd9f0"
_COLOR_PIER = "#f2c4c4"
_COLOR_EDGE = "#9aa5b1"
_COLOR_PILE_LINE = "#1f5f9c"
_COLOR_PIER_LINE = "#8b1e1e"


def _use_agg(preview: bool) -> None:
    if not preview:
        matplotlib.use("Agg", force=True)


def _to_mm(value: Any) -> Any:
    return io_utils.to_display(value, "length")


def _face_colors(mesh: MeshModel) -> list[str]:
    palette = []
    for name in mesh.group_names:
        if name.startswith(config.GROUP_PILE_PREFIX):
            palette.append(_COLOR_PILE)
        elif name.startswith(config.GROUP_PIER_PREFIX):
            palette.append(_COLOR_PIER)
        else:
            palette.append(_COLOR_CAP)
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
    pile_label_color: str = "#0d3b66",
) -> None:
    """Anotasi wajib PRD Bagian 9.3, sama untuk SELURUH plot denah.

    Dipakai ulang oleh mesh plan, kontur, boundary check, dan envelope, sehingga
    outline pilecap, lingkaran pile, dan arsir pier tidak pernah berbeda antar gambar.

    `pz_by_pile` opsional: bila diberikan, nilai `Pz` ikut dicetak di label pile
    (PRD Bagian 9.3 meminta "label ID + nilai Pz").
    """
    import matplotlib.pyplot as plt

    unit = io_utils.display_unit("length")

    cap = _to_mm(geom.pilecap.closed_vertices())
    ax.plot(cap[:, 0], cap[:, 1], color="black", linewidth=1.8, zorder=5)

    for pile in geom.piles:
        ax.add_patch(
            plt.Circle(
                (_to_mm(pile.x), _to_mm(pile.y)),
                _to_mm(pile.radius),
                fill=False,
                linestyle="--",
                linewidth=1.2,
                edgecolor=_COLOR_PILE_LINE,
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
            color=pile_label_color,
            zorder=7,
            bbox={
                "boxstyle": "round,pad=0.15",
                "facecolor": "white",
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
            edgecolor=_COLOR_PIER_LINE,
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
            color=_COLOR_PIER_LINE,
            zorder=7,
            bbox={
                "boxstyle": "round,pad=0.25",
                "facecolor": "white",
                "alpha": 0.85,
                "edgecolor": "none",
            },
        )

    ax.set_xlabel(f"X - memanjang [{unit}]")
    ax.set_ylabel(f"Y - melintang [{unit}]")
    ax.set_aspect("equal", adjustable="box")
    ax.autoscale_view()
    ax.grid(True, linewidth=0.3, alpha=0.4)


def _figure_for(geom: GeometryModel, width: float = 12.0) -> tuple[Any, Any]:
    import matplotlib.pyplot as plt

    xmin, ymin, xmax, ymax = geom.pilecap.bounds
    span_x, span_y = xmax - xmin, ymax - ymin
    aspect = (span_y / span_x) if span_x > 0 else 1.0
    return plt.subplots(figsize=(width, max(5.0, width * aspect * 0.85)))


def _element_polygons(mesh: MeshModel) -> list[np.ndarray]:
    return [_to_mm(mesh.node_xy[conn]) for conn in mesh.elem_conn]


def _save(fig: Any, path: Path, dpi: int, preview: bool) -> Path:
    import matplotlib.pyplot as plt

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
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
    dpi: int = config.OUTPUT_DPI,
    preview: bool = False,
) -> Path:
    """Denah mesh + label pile & pier (PRD Bagian 9.1 `mesh_plan.png`)."""
    _use_agg(preview)
    from matplotlib.collections import PolyCollection

    unit = io_utils.display_unit("length")
    fig, ax = _figure_for(geom)
    ax.add_collection(
        PolyCollection(
            _element_polygons(mesh),
            facecolors=_face_colors(mesh),
            edgecolors=_COLOR_EDGE,
            linewidths=0.25,
        )
    )
    _annotate_plan(ax, geom)

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
        ax.set_title(f"{title}\n{subtitle}\n{override}", fontsize=11, color=_COLOR_PIER_LINE)
    else:
        ax.set_title(f"{title}\n{subtitle}", fontsize=11)

    _save(fig, path, dpi, preview)
    _log.info("%s ditulis: %s", path.name, path)
    return path


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
    dpi: int = config.OUTPUT_DPI,
    preview: bool = False,
) -> Path:
    """Kontur satu besaran per elemen (PRD Bagian 9.1 `contour_*.png`).

    `values_si` adalah nilai SI per elemen; konversi ke satuan tampilan terjadi di sini
    (PRD Bagian 4.3). `quantity` menentukan satuan colorbar lewat `config.DISPLAY_UNITS`.
    """
    _use_agg(preview)
    from matplotlib.collections import PolyCollection
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
    cmap = matplotlib.colormaps[config.CMAP_MOMENT if diverging else config.CMAP_MAGNITUDE].copy()
    cmap.set_bad(config.COLOR_NAN)

    fig, ax = _figure_for(geom)
    collection = PolyCollection(
        _element_polygons(mesh),
        array=np.ma.masked_invalid(values),
        cmap=cmap,
        norm=norm,
        edgecolors="none",
    )
    ax.add_collection(collection)
    _annotate_plan(ax, geom, pz_by_pile=pz_by_pile)

    colorbar = fig.colorbar(collection, ax=ax, shrink=0.85, pad=0.02)
    colorbar.set_label(f"{title} [{unit}]")

    # Tandai lokasi ekstrem -- PRD Bagian 9.3 meminta "nilai maks/min + lokasinya".
    idx_max = int(np.nanargmax(np.where(finite, values, -np.inf)))
    idx_min = int(np.nanargmin(np.where(finite, values, np.inf)))
    for index, label, color in (
        (idx_max, f"maks {values[idx_max]:,.1f}", "#111111"),
        (idx_min, f"min {values[idx_min]:,.1f}", "#111111"),
    ):
        cx, cy = _to_mm(mesh.elem_centroid[index])
        ax.plot(cx, cy, marker="o", markersize=5, markerfacecolor="none", color=color, zorder=8)
        ax.annotate(
            f"{label} {unit}\n({cx:,.0f}, {cy:,.0f})",
            (cx, cy),
            textcoords="offset points",
            xytext=(8, 8),
            fontsize=7,
            color=color,
            zorder=8,
            bbox={
                "boxstyle": "round,pad=0.2",
                "facecolor": "white",
                "alpha": 0.8,
                "edgecolor": "none",
            },
        )

    if n_nan:
        ax.legend(
            handles=[Patch(facecolor=config.COLOR_NAN, label=config.LABEL_NAN)],
            loc="lower left",
            fontsize=8,
            framealpha=0.9,
        )

    heading = title if not combo else f"{title} - Kombinasi {combo}"
    subtitle = f"maks {vmax:,.1f} | min {vmin:,.1f} {unit}{norm_note}"
    if n_nan:
        subtitle += f" | {n_nan} elemen NaN"
    ax.set_title(f"{heading}\n{subtitle}", fontsize=11)

    _save(fig, path, dpi, preview)
    _log.debug("%s ditulis (maks %.3f, min %.3f %s)", path.name, vmax, vmin, unit)
    return path


def render_boundary_load_check(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    *,
    pz_by_pile: dict[str, float] | None = None,
    dpi: int = config.OUTPUT_DPI,
    preview: bool = False,
) -> Path:
    """Peta node jepit & area terbeban (PRD Bagian 9.1 `boundary_load_check.png`).

    Gambar ini menjawab satu pertanyaan yang sulit dijawab dari angka: apakah tumpuan
    dan beban benar-benar menempel di tempat yang seharusnya. Physical group yang salah
    atau kosong terlihat langsung di sini.
    """
    _use_agg(preview)
    from matplotlib.collections import PolyCollection
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch

    fig, ax = _figure_for(geom)

    is_pier = np.zeros(mesh.n_elements, dtype=bool)
    is_pile = np.zeros(mesh.n_elements, dtype=bool)
    for name in mesh.pier_groups():
        is_pier |= mesh.group_mask(name)
    for name in mesh.pile_groups():
        is_pile |= mesh.group_mask(name)

    colors = np.where(is_pier, _COLOR_PIER, np.where(is_pile, _COLOR_PILE, _COLOR_CAP))
    ax.add_collection(
        PolyCollection(
            _element_polygons(mesh),
            facecolors=list(colors),
            edgecolors=_COLOR_EDGE,
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
            color=_COLOR_PIER_LINE,
            zorder=8,
        )

    _annotate_plan(ax, geom, pz_by_pile=pz_by_pile)

    ax.legend(
        handles=[
            Line2D(
                [],
                [],
                linestyle="None",
                marker="s",
                markersize=5,
                color=_COLOR_PIER_LINE,
                label=f"Node JEPIT 6 DOF ({len(fixed_nodes)})",
            ),
            Patch(facecolor=_COLOR_PILE, label=f"Elemen terbeban ({int(is_pile.sum())})"),
            Patch(facecolor=_COLOR_CAP, label=f"Pelat bebas ({int((~is_pier & ~is_pile).sum())})"),
        ],
        loc="upper right",
        fontsize=8,
        framealpha=0.9,
    )
    ax.set_title(
        "Cek Visual Tumpuan & Pembebanan\n"
        f"{len(fixed_nodes)} node jepit di {len(mesh.pier_groups())} pier | "
        f"{int(is_pile.sum())} elemen terbeban di {len(mesh.pile_groups())} pile",
        fontsize=11,
    )

    _save(fig, path, dpi, preview)
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
    dpi: int,
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
    ax = fig.add_subplot(projection="3d")
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

    ax.set_title(title, fontsize=11)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    _log.info("%s ditulis: %s", path.name, path)
    return path


def render_opsvis_model(
    path: Path,
    *,
    n_elements: int,
    n_fixed_nodes: int,
    force: bool = False,
    dpi: int = config.OUTPUT_DPI,
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
        dpi=dpi,
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
    dpi: int = config.OUTPUT_DPI,
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
        dpi=dpi,
        warnings=warnings if warnings is not None else [],
    )
