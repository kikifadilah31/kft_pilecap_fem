"""Visualisasi (PRD Bagian 9.3). TIDAK ADA perhitungan rekayasa di modul ini.

Bersama `reporter.py`, ini satu-satunya tempat konversi ke satuan tampilan lewat
`io_utils.to_display()` (PRD Bagian 4.3).

Bahasa label: Indonesia, istilah teknis dibiarkan Inggris (keputusan user,
PRD Bagian 17 item 9).
"""

from __future__ import annotations

from pathlib import Path

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
    resolution = geom.resolution
    parts = []
    for entity, res in (
        ("pilecap", resolution.pilecap),
        ("pile", resolution.pile),
        ("pier", resolution.pier),
    ):
        if res.is_override and res.file is not None:
            parts.append(f"{entity} <- {Path(res.file).name}")
    if not parts:
        return None
    return "GEOMETRI OVERRIDE: " + " | ".join(parts)


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
    if not preview:
        matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection

    to_mm = lambda v: io_utils.to_display(v, "length")  # noqa: E731
    unit = io_utils.display_unit("length")

    polygons = [to_mm(mesh.node_xy[conn]) for conn in mesh.elem_conn]

    xmin, ymin, xmax, ymax = geom.pilecap.bounds
    width, height = to_mm(xmax - xmin), to_mm(ymax - ymin)
    aspect = height / width if width > 0 else 1.0
    fig, ax = plt.subplots(figsize=(12.0, max(5.0, 12.0 * aspect * 0.85)))

    ax.add_collection(
        PolyCollection(
            polygons,
            facecolors=_face_colors(mesh),
            edgecolors=_COLOR_EDGE,
            linewidths=0.25,
        )
    )

    cap = to_mm(geom.pilecap.closed_vertices())
    ax.plot(cap[:, 0], cap[:, 1], color="black", linewidth=1.8, zorder=5)

    for pile in geom.piles:
        circle = plt.Circle(
            (to_mm(pile.x), to_mm(pile.y)),
            to_mm(pile.radius),
            fill=False,
            linestyle="--",
            linewidth=1.2,
            edgecolor="#1f5f9c",
            zorder=6,
        )
        ax.add_patch(circle)
        ax.annotate(
            pile.pile_id,
            (to_mm(pile.x), to_mm(pile.y)),
            ha="center",
            va="center",
            fontsize=8,
            color="#0d3b66",
            zorder=7,
        )

    for pier in geom.piers:
        exterior = np.asarray(pier.to_shapely().exterior.coords)
        ax.fill(
            to_mm(exterior[:, 0]),
            to_mm(exterior[:, 1]),
            facecolor="none",
            edgecolor="#8b1e1e",
            hatch="///",
            linewidth=1.6,
            zorder=6,
        )
        cx, cy = pier.centerline
        ax.annotate(
            f"{pier.pier_id}\nJEPIT",
            (to_mm(cx), to_mm(cy)),
            ha="center",
            va="center",
            fontsize=9,
            fontweight="bold",
            color="#8b1e1e",
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

    title = "Denah Mesh Pilecap"
    if project_name:
        title += f" - {project_name}"
    subtitle_parts = [
        f"{mesh.n_nodes:,} node",
        f"{mesh.n_elements:,} quad",
        f"{n_tri:,} tri",
    ]
    if mesh_size_m is not None:
        subtitle_parts.append(f"h = {to_mm(mesh_size_m):.0f} {unit}")
    subtitle = " | ".join(subtitle_parts)

    override = _override_subtitle(geom)
    if override is not None:
        ax.set_title(f"{title}\n{subtitle}\n{override}", fontsize=11, color="#8b1e1e")
    else:
        ax.set_title(f"{title}\n{subtitle}", fontsize=11)

    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=dpi)
    _log.info("mesh_plan.png ditulis: %s", path)

    if preview:  # pragma: no cover - interaktif
        plt.show()
    plt.close(fig)
    return path
