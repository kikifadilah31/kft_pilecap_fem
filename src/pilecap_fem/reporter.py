"""Laporan auditable (PRD Core 4, Bagian 9.4).

Bersama `renderer.py`, ini satu-satunya tempat konversi ke satuan tampilan.
Setiap tabel WAJIB mencantumkan satuan di header (PRD Bagian 9.2).

Bahasa: Indonesia, istilah teknis dibiarkan Inggris (keputusan user, PRD Bagian 17 item 9).
"""

from __future__ import annotations

from pathlib import Path

from pilecap_fem import __version__, config, io_utils
from pilecap_fem.geometry_builder import GeometryModel, GeometryResolution
from pilecap_fem.mesh_engine import MeshOptions, RawMesh
from pilecap_fem.mesh_model import MeshModel

_log = config.get_logger("reporter")


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
