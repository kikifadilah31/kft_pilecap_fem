"""Laporan auditable (PRD Core 4, Bagian 9.4).

Bersama `renderer.py`, ini satu-satunya tempat konversi ke satuan tampilan.
Setiap tabel WAJIB mencantumkan satuan di header (PRD Bagian 9.2).

Bahasa: Indonesia, istilah teknis dibiarkan Inggris (keputusan user, PRD Bagian 17 item 9).
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

import numpy as np

from pilecap_fem import __version__, config, io_utils
from pilecap_fem.fem_engine import ComboResult
from pilecap_fem.geometry_builder import GeometryModel, GeometryResolution
from pilecap_fem.mesh_engine import MeshOptions, RawMesh
from pilecap_fem.mesh_model import MeshModel
from pilecap_fem.postproc_engine import ElementResults

_log = config.get_logger("reporter")


def slugify(name: str) -> str:
    """Nama kombinasi -> nama folder yang aman (PRD Bagian 9.2).

    Karakter non-alfanumerik menjadi `_`. Pemetaan nama asli <-> slug dicatat di
    `run_manifest.json`, karena slug bersifat lossy: `1.2D+1.6L` dan `1,2D-1,6L`
    menghasilkan slug yang sama.
    """
    slug = re.sub(r"[^0-9A-Za-z]+", "_", name).strip("_")
    return slug or "combo"


def disclaimer_block() -> str:
    text = config.DISCLAIMER_TEXT.format(version=__version__)
    prefix = (
        "> **[DRAFT - redaksi final belum ditetapkan, PRD Bagian 17 item 18]**\n>\n"
        if (config.DISCLAIMER_IS_DRAFT)
        else ""
    )
    return f"{prefix}> {text}\n"


def open_blockers_block() -> str:
    rows = "\n".join(f"| {key} | {desc} |" for key, desc in config.OPEN_BLOCKERS.items())
    return (
        "Item berikut BELUM dikonfirmasi, sehingga pengecekan terkait **tidak dilakukan** "
        "oleh tool ini:\n\n"
        "| PRD Bagian 17 | Item |\n|---|---|\n" + rows + "\n"
    )


def geometry_resolution_table(resolution: GeometryResolution) -> str:
    """Tabel resolusi sumber geometri (PRD Bagian 9.4 bagian 1a) -- WAJIB."""
    lines = [
        "| Entitas | Sumber terpilih | File (sha256) | Field JSON yang DIABAIKAN |",
        "|---------|-----------------|---------------|---------------------------|",
    ]
    for entity, res in (
        ("pilecap", resolution.pilecap),
        ("pile", resolution.pile),
        ("pier", resolution.pier),
    ):
        file_text = "-"
        if res.file is not None:
            file_text = f"{Path(res.file).name} ({io_utils.short_hash(res.sha256)})"
        ignored = ", ".join(res.overridden_json_keys) if res.overridden_json_keys else "-"
        marker = " **<-- OVERRIDE**" if res.is_override else ""
        lines.append(f"| {entity}{marker} | `{res.source}` | {file_text} | {ignored} |")

    note = ""
    if resolution.has_any_override():
        note = (
            "\n> **PERHATIAN:** geometri TIDAK sepenuhnya berasal dari file config. "
            "Baris bertanda OVERRIDE di atas diambil dari CSV. "
            "Gunakan `--no-custom` bila ini tidak diinginkan.\n"
        )
    return "\n".join(lines) + "\n" + note


def write_element_resultants_csv(path: Path, results: ElementResults, mesh: MeshModel) -> Path:
    """`element_resultants.csv` -- resultant per elemen dalam satuan TAMPILAN.

    Kolom lokal (`m11`, `m22`, `m12`) ikut disertakan agar checker dapat menghitung
    ulang transformasi sendiri dari nilai yang sama (PRD Bagian 9.1).
    """
    to_mm = io_utils.to_display
    unit_len = io_utils.display_unit("length")
    unit_m = io_utils.display_unit("moment_per_width")
    unit_q = io_utils.display_unit("shear_per_width")

    header = [
        "elem_tag",
        f"centroid_x [{unit_len}]",
        f"centroid_y [{unit_len}]",
        "area [m^2]",
        "group",
        "theta [deg]",
        f"m11 [{unit_m}]",
        f"m22 [{unit_m}]",
        f"m12 [{unit_m}]",
        f"m_x [{unit_m}]",
        f"m_y [{unit_m}]",
        f"m_xy [{unit_m}]",
        f"q_x [{unit_q}]",
        f"q_y [{unit_q}]",
        f"q_mag [{unit_q}]",
    ]

    moment = np.column_stack(
        [results.m11, results.m22, results.m12, results.m_xx, results.m_yy, results.m_xy]
    )
    shear = np.column_stack([results.q_x, results.q_y, results.q_magnitude])

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for i in range(results.n_elements):
            writer.writerow(
                [
                    int(mesh.elem_tags[i]),
                    f"{to_mm(mesh.elem_centroid[i, 0], 'length'):.3f}",
                    f"{to_mm(mesh.elem_centroid[i, 1], 'length'):.3f}",
                    f"{mesh.elem_area[i]:.9e}",
                    mesh.group_names[int(mesh.elem_group[i])],
                    f"{np.degrees(results.theta[i]):.4f}",
                    *(f"{to_mm(v, 'moment_per_width'):.6f}" for v in moment[i]),
                    *(f"{to_mm(v, 'shear_per_width'):.6f}" for v in shear[i]),
                ]
            )
    _log.debug("element_resultants.csv ditulis: %s", path)
    return path


def write_reactions_csv(path: Path, combo_result: ComboResult, mesh: MeshModel) -> Path:
    """`reactions.csv` -- reaksi tiap node jepit + baris TOTAL."""
    unit_len = io_utils.display_unit("length")
    unit_f = io_utils.display_unit("force")
    unit_m = io_utils.display_unit("moment")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "node_tag",
                f"x [{unit_len}]",
                f"y [{unit_len}]",
                f"Rx [{unit_f}]",
                f"Ry [{unit_f}]",
                f"Rz [{unit_f}]",
                f"Mx [{unit_m}]",
                f"My [{unit_m}]",
                f"Mz [{unit_m}]",
            ]
        )
        for index, reaction in zip(
            combo_result.reaction_nodes, combo_result.reactions, strict=True
        ):
            writer.writerow(
                [
                    int(mesh.node_tags[index]),
                    f"{io_utils.to_display(mesh.node_xy[index, 0], 'length'):.3f}",
                    f"{io_utils.to_display(mesh.node_xy[index, 1], 'length'):.3f}",
                    *(f"{io_utils.to_display(v, 'force'):.6f}" for v in reaction[:3]),
                    *(f"{io_utils.to_display(v, 'moment'):.6f}" for v in reaction[3:]),
                ]
            )
        totals = combo_result.reactions.sum(axis=0)
        writer.writerow(
            [
                "TOTAL",
                "",
                "",
                *(f"{io_utils.to_display(v, 'force'):.6f}" for v in totals[:3]),
                *(f"{io_utils.to_display(v, 'moment'):.6f}" for v in totals[3:]),
            ]
        )
    return path


def write_equilibrium_json(path: Path, combo_result: ComboResult) -> Path:
    """`equilibrium_check.json` -- VC-0 apa adanya, dalam SI (PRD Bagian 9.1)."""
    payload = combo_result.equilibrium.to_dict()
    payload["combo"] = combo_result.combo
    payload["catatan"] = (
        "Nilai dalam SI (N, N.m). Momen dihitung terhadap titik acuan yang tercantum, "
        "sehingga checker dapat menghitung ulang dari nodes.csv dan reactions.csv."
    )
    payload["pile_loads"] = [
        {
            "pile_id": t.pile_id,
            "Pz_N": t.pz,
            "A_disk_mesh_m2": t.a_disk_mesh,
            "A_disk_nominal_m2": t.a_disk_nominal,
            "pressure_Pa": t.pressure,
            "n_elements": t.n_elements,
            "applied_total_N": t.applied_total,
            "discrepancy_N": t.discrepancy,
        }
        for t in combo_result.load_traces
    ]
    payload["self_weight_total_N"] = combo_result.self_weight_total
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_mesh_summary(
    path: Path,
    *,
    geom: GeometryModel,
    mesh: MeshModel,
    raw: RawMesh,
    options: MeshOptions,
    project_name: str,
    run_dir: Path,
    warnings: tuple[str, ...],
) -> Path:
    """`mesh_summary.md` (PRD Bagian 6.1)."""
    unit_len = io_utils.display_unit("length")
    to_mm = lambda v: io_utils.to_display(v, "length")  # noqa: E731

    all_quad = "**YA**" if raw.n_tri == 0 else f"**TIDAK** ({raw.n_tri} segitiga)"

    group_rows = []
    for name in sorted(raw.surface_area_by_group):
        occ_area = raw.surface_area_by_group[name]
        mesh_area = mesh.group_area(name) if name in mesh.group_names else float("nan")
        n_elem = mesh.group_element_counts().get(name, 0)
        group_rows.append(
            f"| `{name}` | {n_elem} | {occ_area:.6f} | {mesh_area:.6f} | "
            f"{(mesh_area - occ_area) / occ_area:+.3%} |"
        )

    group_table = "\n".join(group_rows)
    pier_table = "\n".join(
        f"| {p.pier_id} | {p.shape} | {to_mm(p.centerline[0]):.0f} | "
        f"{to_mm(p.centerline[1]):.0f} | {p.area:.6f} |"
        for p in geom.piers
    )
    option_rows = "\n".join(
        f"| `{key}` | {value:g} |" for key, value in sorted(raw.effective_options.items())
    )

    pile_counts = {n: mesh.group_element_counts()[n] for n in mesh.pile_groups()}
    pile_range = f"{min(pile_counts.values())}-{max(pile_counts.values())}" if pile_counts else "-"

    warning_block = "\n".join(f"- {w}" for w in warnings) if warnings else "_(tidak ada)_"

    content = f"""\
# MESH SUMMARY - {project_name or "Pilecap"}

Tool: pilecap-fem v{__version__} | Run: `{run_dir.name}` | Manifest: `run_manifest.json`
Sistem satuan internal: {config.SI_UNIT_SYSTEM}

## 1. RESOLUSI SUMBER GEOMETRI (PRD Bagian 5.2.1)

{geometry_resolution_table(geom.resolution)}

## 2. GEOMETRI

| Besaran | Nilai |
|---------|-------|
| Luas pilecap | {geom.pilecap_area:.6f} m^2 |
| Titik sudut polygon pilecap | {geom.pilecap.n_vertices} |
| Tebal pilecap | {to_mm(geom.thickness):.0f} {unit_len} |
| Jumlah pile | {geom.n_piles} |
| Diameter pile (min) | {to_mm(geom.min_pile_diameter):.0f} {unit_len} |
| Jumlah pier | {geom.n_piers} |

### Pier

| pier_id | shape | centerline X [{unit_len}] | centerline Y [{unit_len}] | luas [m^2] |
|---------|-------|---------------------------|---------------------------|------------|
{pier_table}

## 3. OPSI gmsh EFEKTIF (hasil read-back, bukan nilai yang diminta)

| Opsi | Nilai terbaca |
|------|---------------|
{option_rows}

| Parameter | Nilai |
|-----------|-------|
| `size_mode` | `{options.size_mode}` |
| `size_global` | {to_mm(options.size_global):.1f} {unit_len} ({options.size_global:.4f} m) |
| `recombine` | {options.recombine} |
| `require_all_quad` | {options.require_all_quad} |
| `element_order` | {options.element_order} |
| gmsh terpasang | {raw.gmsh_version} (dipin: {config.GMSH_VERSION_PINNED}) |

## 4. STATISTIK MESH

| Besaran | Nilai |
|---------|-------|
| Jumlah node | {mesh.n_nodes:,} |
| Elemen quad (tipe gmsh 3) | {raw.n_quad:,} |
| Elemen triangle (tipe gmsh 2) | {raw.n_tri:,} |
| **ALL-QUAD?** | {all_quad} |
| Sub-face hasil `occ.fragment` | {raw.n_surfaces} |
| Keseragaman luas `std/mean` (seluruh elemen) | {mesh.area_uniformity_cv:.3f} |
| Keseragaman luas `std/mean` (**group CAP**) | {mesh.area_uniformity_cv_cap:.3f} (ambang test {config.MESH_UNIFORMITY_MAX_CV:.2f}) |
| Elemen per pile group | {pile_range} |
| D_pile / h | {geom.min_pile_diameter / options.size_global:.2f} (minimum {config.MIN_ELEM_PER_PILE_DIAMETER:g}) |

## 5. LUAS PER PHYSICAL GROUP

Kolom "luas OCC" adalah luas geometri eksak; "luas mesh" adalah jumlah luas elemen quad.
Selisih pada group pile berasal dari diskretisasi lingkaran menjadi quad -- ini normal dan
justru alasan `A_disk` untuk tekanan pile diambil dari **luas mesh**, bukan pi*r^2
(PRD Bagian 7.3).

| Physical group | Jumlah elemen | Luas OCC [m^2] | Luas mesh [m^2] | Selisih |
|----------------|---------------|----------------|-----------------|---------|
{group_table}
| **TOTAL** | **{mesh.n_elements}** | **{raw.total_surface_area:.6f}** | **{mesh.total_mesh_area:.6f}** | |

## 6. WARNING

{warning_block}

## 7. STATUS PENGECEKAN

| Cek | Status |
|-----|--------|
| Sigma luas sub-face = luas pilecap (rtol {config.AREA_RTOL:g}) | LULUS |
| Mesh 100% quad | {"LULUS" if raw.n_tri == 0 else "GAGAL"} |
| Setiap physical group pile/pier punya elemen | LULUS |
| D_pile / h >= {config.MIN_ELEM_PER_PILE_DIAMETER:g} | LULUS |
| Cek keseimbangan VC-0 | BELUM DIJALANKAN (butuh `pilecap-analyze`, Fase 2) |
| Kapasitas lentur & geser | NOT_EVALUATED |

{open_blockers_block()}

## 8. PERNYATAAN TANGGUNG JAWAB

{disclaimer_block()}
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _log.info("mesh_summary.md ditulis: %s", path)
    return path
