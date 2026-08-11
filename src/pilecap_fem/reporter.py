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
from typing import TYPE_CHECKING, Any

import numpy as np

from pilecap_fem import __version__, capacity_engine, config, io_utils
from pilecap_fem.capacity_engine import CapacityInputs, FlexureDesign, OneWayShearCapacity
from pilecap_fem.geometry_builder import GeometryModel, GeometryResolution
from pilecap_fem.mesh_model import MeshModel
from pilecap_fem.postproc_engine import ElementResults, Envelope, ShearCheck

if TYPE_CHECKING:  # pragma: no cover
    # Hanya anotasi tipe. Mengimpornya saat runtime menarik gmsh (lewat mesh_engine)
    # dan openseespy (lewat fem_engine) -- padahal `pilecap-report` hanya membaca CSV.
    from pilecap_fem.fem_engine import ComboResult
    from pilecap_fem.mesh_engine import MeshOptions, RawMesh

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


def _overlap_block(equilibrium: dict[str, Any]) -> str:
    """Rincian beban pile yang TIDAK melenturkan pelat, bila ada tumpang tindih pile-pier.

    Kosong sepenuhnya bila tidak ada overlap, sehingga calc sheet run biasa tidak berubah
    satu baris pun.
    """
    rows = [r for r in equilibrium.get("pile_loads", []) if r.get("A_lens_m2", 0.0) > 0.0]
    if not rows:
        return ""

    unit_f = io_utils.display_unit("force")
    tabel = _markdown_table(
        [
            "pile",
            "f (lensa/cakram)",
            f"strut -- geometri [{unit_f}]",
            f"bocor mesh -- diskretisasi [{unit_f}]",
            f"ke pelat [{unit_f}]",
        ],
        [
            [
                r["pile_id"],
                f"{r['overlap_fraction']:.2%}",
                f"{io_utils.to_display(r['pz_strut_N'], 'force'):,.2f}",
                f"{io_utils.to_display(r['pz_bocor_mesh_N'], 'force'):,.2f}",
                f"{io_utils.to_display(r['pz_ke_pelat_N'], 'force'):,.2f}",
            ]
            for r in rows
        ],
    )
    return f"""
### 3a. Beban pile yang TIDAK melenturkan pelat (tumpang tindih dengan pier)

{tabel}

Kolom **strut** adalah komponen GEOMETRI: bagian cakram pile yang berada di dalam footprint
pier. Pier diidealkan jepit sempurna, sehingga tekanan di sana langsung masuk ke reaksi --
secara fisik gaya itu tersalur langsung dari kepala pile ke pier menembus tebal pilecap.
**Tool TIDAK menghitung kapasitas strut tersebut; bagian ini wajib Anda cek terpisah sebagai
tumpu/strut.**

Kolom **bocor mesh** adalah komponen DISKRETISASI: beban elemen di tepi footprint pier yang
ikut mendarat pada node jepit. Besarnya sebanding `L x h / (2 A_pile)` sehingga **mengecil
bila mesh diperhalus** -- angka ini milik kehalusan mesh, bukan milik geometri. Karena itu
keduanya disajikan terpisah; menjumlahkannya akan menyamarkan yang mana yang mana.

`Sigma reaksi` tetap sama dengan `Sigma Pz` -- tidak ada beban yang hilang dari neraca. Yang
berbeda adalah berapa banyak yang benar-benar dirasakan PELAT (lihat KNOWN_LIMITATIONS #10).
"""


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


def write_node_displacements_csv(path: Path, combo_result: ComboResult, mesh: MeshModel) -> Path:
    """`node_displacements.csv` -- perpindahan & rotasi tiap node.

    **Di luar daftar PRD Bagian 9.1, dan diperlukan.** PRD meminta
    `contour_deflection.png` tetapi tidak menyediakan sumber datanya; tanpa berkas ini
    kontur lendutan mustahil dibuat ulang oleh `pilecap-report` dari CSV, dan checker
    tidak punya angka lendutan untuk diperiksa sama sekali.
    """
    unit_len = io_utils.display_unit("length")
    unit_d = io_utils.display_unit("deflection")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "node_tag",
                f"x [{unit_len}]",
                f"y [{unit_len}]",
                f"ux [{unit_d}]",
                f"uy [{unit_d}]",
                f"uz [{unit_d}]",
                "rx [rad]",
                "ry [rad]",
                "rz [rad]",
            ]
        )
        for index in range(mesh.n_nodes):
            disp = combo_result.displacements[index]
            writer.writerow(
                [
                    int(mesh.node_tags[index]),
                    f"{io_utils.to_display(mesh.node_xy[index, 0], 'length'):.3f}",
                    f"{io_utils.to_display(mesh.node_xy[index, 1], 'length'):.3f}",
                    *(f"{io_utils.to_display(v, 'deflection'):.6f}" for v in disp[:3]),
                    *(f"{v:.9e}" for v in disp[3:]),
                ]
            )
    return path


def read_node_displacements_csv(path: Path) -> np.ndarray:
    """Baca balik `node_displacements.csv` -> array (N, 6) dalam SI.

    Kolom translasi disimpan dalam mm (satuan tampilan), jadi dikembalikan ke meter
    di sini -- konversi tampilan tetap hanya terjadi di modul ini (PRD Bagian 4.3).
    """
    factor = config.DISPLAY_UNITS["deflection"][1]
    rows: list[list[float]] = []
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            rows.append(
                [
                    float(row["ux [mm]"]) / factor,
                    float(row["uy [mm]"]) / factor,
                    float(row["uz [mm]"]) / factor,
                    float(row["rx [rad]"]),
                    float(row["ry [rad]"]),
                    float(row["rz [rad]"]),
                ]
            )
    return np.asarray(rows, dtype=np.float64)


def read_element_resultants_csv(path: Path, combo: str) -> ElementResults:
    """Baca balik `element_resultants.csv` -> `ElementResults` dalam SI.

    Inilah yang membuat plot `pilecap-report` lahir dari berkas yang SAMA dengan yang
    dibaca checker: bila gambar dan CSV berbeda, itu akan ketahuan.

    `raw_gauss` tidak tersimpan di CSV, sehingga rantai telusur bagian 5 calc sheet
    hanya dapat dibuat oleh `pilecap-analyze`. Report memakai nilai yang sudah
    ditransformasi -- dan menyatakan itu apa adanya.
    """
    # Pemetaan kolom -> besaran, EKSPLISIT. Membedakan momen dari geser lewat nilai
    # faktornya tidak sah: `moment_per_width` dan `shear_per_width` kebetulan sama-sama
    # 1e-3, sehingga perbandingan nilai memilih label satuan yang salah.
    column_quantity = {
        "m11": "moment_per_width",
        "m22": "moment_per_width",
        "m12": "moment_per_width",
        "m_x": "moment_per_width",
        "m_y": "moment_per_width",
        "m_xy": "moment_per_width",
        "q_x": "shear_per_width",
        "q_y": "shear_per_width",
    }
    columns: dict[str, list[float]] = {key: [] for key in (*column_quantity, "theta")}

    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for key, quantity in column_quantity.items():
                header = f"{key} [{io_utils.display_unit(quantity)}]"
                if header not in row:
                    raise KeyError(
                        f"Kolom {header!r} tidak ada di {path.name}. "
                        f"Kolom yang tersedia: {list(row)}"
                    )
                columns[key].append(float(row[header]) / config.DISPLAY_UNITS[quantity][1])
            columns["theta"].append(np.radians(float(row["theta [deg]"])))

    def arr(key: str) -> np.ndarray:
        return np.asarray(columns[key], dtype=np.float64)

    zeros = np.zeros(len(columns["m11"]), dtype=np.float64)
    return ElementResults(
        combo=combo,
        m11=arr("m11"),
        m22=arr("m22"),
        m12=arr("m12"),
        q1=zeros,
        q2=zeros,
        p11=zeros,
        p22=zeros,
        p12=zeros,
        m_xx=arr("m_x"),
        m_yy=arr("m_y"),
        m_xy=arr("m_xy"),
        q_x=arr("q_x"),
        q_y=arr("q_y"),
        theta=arr("theta"),
        raw_gauss=np.zeros((len(columns["m11"]), 0, 0), dtype=np.float64),
    )


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
            # Tiga angka di bawah hanya bermakna bila pile tumpang tindih dengan pier.
            # Sengaja DIPISAH: `pz_strut_N` murni geometri (mesh-independen), sedangkan
            # `pz_bocor_mesh_N` artefak diskretisasi (mengecil saat mesh diperhalus).
            # Satu angka gabungan akan menyamar sebagai parameter geometri.
            "A_lens_m2": t.a_lens,
            "overlap_fraction": t.overlap_fraction,
            "pz_strut_N": t.pz_strut,
            "pz_bocor_mesh_N": t.pz_bocor_mesh,
            "pz_ke_pelat_N": t.pz_ke_pelat,
        }
        for t in combo_result.load_traces
    ]
    if any(t.a_lens > 0.0 for t in combo_result.load_traces):
        payload["catatan_overlap"] = (
            "Sebagian beban pile mendarat pada node JEPIT (bagian cakram di dalam footprint "
            "pier) sehingga TIDAK melenturkan pelat. `pz_strut_N` adalah komponen "
            "geometrinya -- gaya yang tersalur langsung pile->pier menembus tebal pilecap, "
            "yang WAJIB dicek terpisah sebagai tumpu/strut karena tool tidak menghitung "
            "kapasitasnya. `pz_bocor_mesh_N` adalah komponen diskretisasi dan mengecil bila "
            "mesh diperhalus. Sigma reaksi tetap = Sigma Pz: tidak ada beban yang hilang "
            "dari neraca, yang berbeda adalah berapa banyak yang dirasakan PELAT."
        )
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
| Cek keseimbangan VC-0 | BELUM DIJALANKAN (butuh `pilecap-analyze`) |
| Desain lentur & geser satu arah | BELUM DIJALANKAN (butuh `pilecap-report`) |
| Kapasitas geser pons | NOT_EVALUATED (pasal belum dikonfirmasi) |

{open_blockers_block()}

## 8. PERNYATAAN TANGGUNG JAWAB

{disclaimer_block()}
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _log.info("mesh_summary.md ditulis: %s", path)
    return path


# ---------------------------------------------------------------------------
# CSV hasil post-processing (PRD Bagian 9.1)
# ---------------------------------------------------------------------------


def write_strip_moments_csv(path: Path, rows: list[dict[str, Any]], direction: str) -> Path:
    """`strip_moments_x.csv` / `_y.csv` -- momen total per lajur.

    Kolom `singular` menandai baris yang berasal dari lokasi puncak: nilai itu
    **bukan momen desain** melainkan singularitas numerik di tepi zona jepit
    (PRD Bagian 7.2(5)).
    """
    unit_len = io_utils.display_unit("length")
    unit_m = io_utils.display_unit("moment")
    selected = [r for r in rows if r["direction"] == direction]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "lokasi",
                "pier_id",
                "sisi",
                "strip",
                f"batas_lajur_min [{unit_len}]",
                f"batas_lajur_maks [{unit_len}]",
                f"potongan_diminta [{unit_len}]",
                f"potongan_aktual [{unit_len}]",
                "n_elemen",
                f"M_total [{unit_m}]",
                "metode_lebar",
                "singular",
            ]
        )
        for row in selected:
            writer.writerow(
                [
                    row["lokasi"],
                    row["pier_id"],
                    row["sisi"],
                    row["strip"],
                    f"{io_utils.to_display(row['bounds_m'][0], 'length'):.1f}",
                    f"{io_utils.to_display(row['bounds_m'][1], 'length'):.1f}",
                    f"{io_utils.to_display(row['cut_requested_m'], 'length'):.1f}",
                    f"{io_utils.to_display(row['cut_actual_m'], 'length'):.1f}",
                    row["n_elements"],
                    f"{io_utils.to_display(row['M_total_Nm'], 'moment'):.4f}",
                    row["width_method"],
                    "YA" if row["singular"] else "tidak",
                ]
            )
    return path


def write_shear_checks_csv(path: Path, checks: list[ShearCheck]) -> Path:
    """`shear_checks.csv` -- demand geser satu arah & pons. Kapasitas NOT_EVALUATED."""
    unit_len = io_utils.display_unit("length")
    unit_f = io_utils.display_unit("force")
    unit_s = io_utils.display_unit("stress")

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "pier_id",
                "jenis",
                f"d [{unit_len}]",
                f"lokasi [{unit_len}]",
                f"b_o [{unit_len}]",
                f"V_u [{unit_f}]",
                f"v_u [{unit_s}]",
                "kapasitas",
                "catatan",
            ]
        )
        for check in checks:
            writer.writerow(
                [
                    check.pier_id,
                    check.kind,
                    f"{io_utils.to_display(check.d_m, 'length'):.1f}",
                    (
                        "-"
                        if check.location_m is None
                        else f"{io_utils.to_display(check.location_m, 'length'):.1f}"
                    ),
                    "-"
                    if check.b_o_m is None
                    else f"{io_utils.to_display(check.b_o_m, 'length'):.1f}",
                    f"{io_utils.to_display(check.V_u_N, 'force'):.4f}",
                    "-"
                    if check.v_u_Pa is None
                    else f"{io_utils.to_display(check.v_u_Pa, 'stress'):.6f}",
                    check.capacity_status,
                    check.note,
                ]
            )
    return path


def write_shear_rebar_csv(
    path: Path,
    shear_maps: dict[str, capacity_engine.ShearRebarMap],
    mesh: MeshModel,
) -> Path:
    """`shear_rebar.csv` -- kebutuhan sengkang per elemen, kedua arah.

    Kolom `Av_s` dan `Av_s_tanpa_min` sengaja DIPISAH. Dengan `Av,min` aktif, jumlah elemen
    ber-`Av/s > 0` jauh lebih besar daripada yang beton-nya benar-benar tidak cukup
    (DIUKUR pada ex01: 307 versus 31). Tanpa kolom kedua, pembaca tidak punya cara
    membedakan "perlu sengkang" dari "kena minimum".
    """
    unit_len = io_utils.display_unit("length")
    unit_q = io_utils.display_unit("shear_per_width")
    unit_av = io_utils.display_unit("shear_steel_ratio")
    to_disp = io_utils.to_display

    directions = list(shear_maps)
    header = [
        "elem_tag",
        f"centroid_x [{unit_len}]",
        f"centroid_y [{unit_len}]",
        "group",
    ]
    for direction in directions:
        header += [
            f"V_u_{direction} [{unit_q}]",
            f"phi_Vc_{direction} [{unit_q}]",
            f"Av_s_{direction} [{unit_av}]",
            f"Av_s_tanpa_min_{direction} [{unit_av}]",
            f"D_sengkang_{direction} [{unit_len}]",
            f"status_{direction}",
        ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for i in range(mesh.n_elements):
            row: list[Any] = [
                int(mesh.elem_tags[i]),
                f"{to_disp(mesh.elem_centroid[i, 0], 'length'):.3f}",
                f"{to_disp(mesh.elem_centroid[i, 1], 'length'):.3f}",
                mesh.group_names[int(mesh.elem_group[i])],
            ]
            for direction in directions:
                smap = shear_maps[direction]
                row += [
                    f"{to_disp(smap.v_u[i], 'shear_per_width'):.4f}",
                    f"{to_disp(smap.phi_v_c, 'shear_per_width'):.4f}",
                    f"{to_disp(smap.av_per_s[i], 'shear_steel_ratio'):.6f}",
                    f"{to_disp(smap.av_per_s_no_min[i], 'shear_steel_ratio'):.6f}",
                    f"{to_disp(smap.stirrup_diameter[i], 'length'):.1f}",
                    str(smap.status[i]),
                ]
            writer.writerow(row)
    _log.debug("shear_rebar.csv ditulis: %s", path)
    return path


def _selection_cell(selection: capacity_engine.RebarSelection, index: int) -> str:
    """Nilai seleksi satu elemen sebagai teks siap-baca.

    Kategorikal dicetak sebagai LABEL (`2D25`, `D16`), bukan indeks -- indeks hanya
    bermakna bersama daftar kodenya, dan CSV harus dapat dibaca tanpa berkas lain.
    """
    value = float(selection.values[index])
    if not np.isfinite(value):
        return "nan"
    if selection.kind == capacity_engine.SELECTION_CONFIG:
        position = int(value)
        return "-" if position == 0 else selection.labels[position - 1]
    if selection.kind == capacity_engine.SELECTION_DIAMETER:
        mm = io_utils.to_display(value, "length")
        return "-" if mm <= 0.0 else f"D{mm:.0f}"
    return f"{io_utils.to_display(value, 'length'):.1f}"


def write_rebar_design_csv(
    path: Path,
    designs: dict[tuple[str, str], FlexureDesign],
    mesh: MeshModel,
    *,
    selections: dict[tuple[str, str], capacity_engine.RebarSelection] | None = None,
) -> Path:
    """`rebar_design.csv` -- `As perlu` per elemen untuk keempat kombinasi arah x muka.

    Terpisah dari `element_resultants.csv` dengan sengaja: demand mentah harus tetap dapat
    dibaca tanpa tercampur hasil desain, sehingga checker dapat memverifikasi keduanya
    secara terpisah (PRD Bagian 9.1).

    Bentuknya LEBAR (satu baris per elemen) mengikuti `element_resultants.csv`, bukan
    panjang, supaya elemen yang sama pada keempat kombinasi dapat dibandingkan sebaris.
    """
    unit_len = io_utils.display_unit("length")
    unit_m = io_utils.display_unit("moment_per_width")
    unit_as = io_utils.display_unit("steel_area")

    keys = list(config.REBAR_FACES)
    header = [
        "elem_tag",
        f"centroid_x [{unit_len}]",
        f"centroid_y [{unit_len}]",
        "group",
    ]
    kind = next(iter(selections.values())).kind if selections else ""
    for direction, face in keys:
        tag = f"{direction}_{face}"
        header += [
            f"Mu_{tag} [{unit_m}]",
            f"d_{tag} [{unit_len}]",
            f"D_bar_{tag} [{unit_len}]",
            f"As_perlu_{tag} [{unit_as}]",
            f"As_pakai_{tag} [{unit_as}]",
        ]
        if selections:
            # Satuan menyusul jenis seleksinya: spasi dalam mm, diameter/konfigurasi
            # sebagai label. Header karena itu tidak dapat ditulis satu bentuk untuk semua.
            suffix = f" [{unit_len}]" if kind == capacity_engine.SELECTION_SPACING else ""
            header.append(f"{kind}_{tag}{suffix}")
        header.append(f"status_{tag}")
    # As minimum sama untuk semua elemen (fungsi fy & tebal saja), jadi satu kolom cukup.
    header.append(f"As_min [{unit_as}]")

    to_disp = io_utils.to_display
    as_design = {key: capacity_engine.as_design_array(designs[key]) for key in keys}

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for i in range(mesh.n_elements):
            row: list[Any] = [
                int(mesh.elem_tags[i]),
                f"{to_disp(mesh.elem_centroid[i, 0], 'length'):.3f}",
                f"{to_disp(mesh.elem_centroid[i, 1], 'length'):.3f}",
                mesh.group_names[int(mesh.elem_group[i])],
            ]
            for key in keys:
                design = designs[key]
                row += [
                    f"{to_disp(design.mu[i], 'moment_per_width'):.6f}",
                    f"{to_disp(design.d_effective[i], 'length'):.2f}",
                    f"{to_disp(design.bar_diameter[i], 'length'):.1f}",
                    f"{to_disp(design.as_required[i], 'steel_area'):.2f}",
                    f"{to_disp(as_design[key][i], 'steel_area'):.2f}",
                ]
                if selections:
                    row.append(_selection_cell(selections[key], i))
                row.append(str(design.status[i]))
            row.append(f"{to_disp(designs[keys[0]].as_min, 'steel_area'):.2f}")
            writer.writerow(row)
    _log.debug("rebar_design.csv ditulis: %s", path)
    return path


def write_rebar_envelope_csv(
    path: Path,
    designs_by_combo: dict[str, dict[tuple[str, str], FlexureDesign]],
    mesh: MeshModel,
) -> Path:
    """`rebar_design_envelope.csv` -- `As pakai` governing lintas seluruh kombinasi.

    Envelope diambil sebagai **maksimum**, bukan min/maks seperti envelope momen: luas
    tulangan tidak punya tanda, dan yang menentukan desain adalah kebutuhan terbesar pada
    muka itu (PRD Bagian 12). `governing_combo` dicatat agar setiap angka tetap dapat
    ditelusuri kembali ke kombinasi asalnya.

    Elemen ber-status `PENAMPANG_TIDAK_MEMADAI` pada kombinasi mana pun **menular** ke
    hasil envelope: satu kombinasi yang gagal sudah cukup membuat penampang itu tidak
    memadai, sekalipun kombinasi lain aman.
    """
    if not designs_by_combo:
        raise ValueError("designs_by_combo kosong; envelope tulangan tidak dapat dibuat.")

    unit_len = io_utils.display_unit("length")
    unit_as = io_utils.display_unit("steel_area")
    keys = list(config.REBAR_FACES)
    combos = list(designs_by_combo)

    header = [
        "elem_tag",
        f"centroid_x [{unit_len}]",
        f"centroid_y [{unit_len}]",
        "group",
    ]
    for direction, face in keys:
        tag = f"{direction}_{face}"
        header += [
            f"As_pakai_maks_{tag} [{unit_as}]",
            f"governing_combo_{tag}",
            f"status_{tag}",
        ]

    stacked: dict[tuple[str, str], np.ndarray] = {}
    inadequate: dict[tuple[str, str], np.ndarray] = {}
    for key in keys:
        stacked[key] = np.vstack(
            [capacity_engine.as_design_array(designs_by_combo[c][key]) for c in combos]
        )
        inadequate[key] = np.vstack(
            [
                designs_by_combo[c][key].status == capacity_engine.STATUS_SECTION_INADEQUATE
                for c in combos
            ]
        )

    to_disp = io_utils.to_display
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for i in range(mesh.n_elements):
            row: list[Any] = [
                int(mesh.elem_tags[i]),
                f"{to_disp(mesh.elem_centroid[i, 0], 'length'):.3f}",
                f"{to_disp(mesh.elem_centroid[i, 1], 'length'):.3f}",
                mesh.group_names[int(mesh.elem_group[i])],
            ]
            for key in keys:
                column = stacked[key][:, i]
                if np.all(~np.isfinite(column)):
                    row += ["nan", "-", capacity_engine.STATUS_UNDEFINED]
                    continue
                which = int(np.nanargmax(column))
                status = (
                    capacity_engine.STATUS_SECTION_INADEQUATE
                    if inadequate[key][:, i].any()
                    else capacity_engine.STATUS_OK
                )
                row += [
                    f"{to_disp(column[which], 'steel_area'):.2f}",
                    combos[which],
                    status,
                ]
            writer.writerow(row)
    _log.debug("rebar_design_envelope.csv ditulis: %s", path)
    return path


def write_envelope_csv(path: Path, envelope: Envelope, mesh: MeshModel) -> Path:
    """`envelope_values.csv` -- nilai ekstrem + `governing_combo` per lokasi.

    Tanpa kolom governing, envelope tidak auditable: nilai ekstrem tidak dapat
    ditelusuri kembali ke kombinasi asalnya (PRD Bagian 12).
    """
    unit_len = io_utils.display_unit("length")
    fields = list(envelope.fields)

    header = ["elem_tag", f"centroid_x [{unit_len}]", f"centroid_y [{unit_len}]", "group"]
    for field in fields:
        quantity = "moment_per_width" if field.startswith("m_") else "shear_per_width"
        unit = io_utils.display_unit(quantity)
        header += [
            f"{field}_max [{unit}]",
            f"{field}_max_governing_combo",
            f"{field}_min [{unit}]",
            f"{field}_min_governing_combo",
        ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        for i in range(mesh.n_elements):
            row: list[Any] = [
                int(mesh.elem_tags[i]),
                f"{io_utils.to_display(mesh.elem_centroid[i, 0], 'length'):.3f}",
                f"{io_utils.to_display(mesh.elem_centroid[i, 1], 'length'):.3f}",
                mesh.group_names[int(mesh.elem_group[i])],
            ]
            for field in fields:
                quantity = "moment_per_width" if field.startswith("m_") else "shear_per_width"
                env = envelope.fields[field]
                row += [
                    f"{io_utils.to_display(env.max_values[i], quantity):.6f}",
                    envelope.combo_name(env.max_combo_index[i]),
                    f"{io_utils.to_display(env.min_values[i], quantity):.6f}",
                    envelope.combo_name(env.min_combo_index[i]),
                ]
            writer.writerow(row)
    _log.info("envelope_values.csv ditulis: %s", path)
    return path


# ---------------------------------------------------------------------------
# calc_sheet.md (PRD Bagian 9.4) -- Core 4
# ---------------------------------------------------------------------------


def _markdown_table(header: list[str], rows: list[list[Any]]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * len(header)) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def _traceability_block(trace: dict[str, Any]) -> str:
    """Bagian 5 calc sheet: RANTAI LENGKAP satu elemen agar dapat dihitung ulang."""
    gauss = trace["gauss_raw"]
    order = gauss["component_order"]
    gauss_rows = [
        [f"GP{i + 1}"] + [f"{v:,.4f}" for v in values] for i, values in enumerate(gauss["values"])
    ]
    gauss_rows.append(["**rata-rata**"] + [f"**{v:,.4f}**" for v in trace["gauss_mean"]])

    local = trace["local_after_sign"]
    glob = trace["global"]
    return f"""\
Elemen contoh: **tag {trace["element_tag"]}** (group `{trace["group"]}`), centroid
({trace["centroid_m"][0]:.4f}, {trace["centroid_m"][1]:.4f}) m, luas {trace["area_m2"]:.6e} m^2.

Node (tag): {trace["node_tags"]}
Koordinat node [m]: {[[round(c, 4) for c in p] for p in trace["node_coords_m"]]}

**a. Resultant tiap titik Gauss, APA ADANYA dari OpenSees**
`eleResponse(tag, {gauss["response_name"]!r})`, satuan SI (N/m dan N.m/m):

{_markdown_table(["titik", *order], gauss_rows)}

**b. Koreksi tanda ke konvensi PRD Bagian 7.1**
faktor momen = {trace["sign_factors"]["moment"]}, faktor geser = {trace["sign_factors"]["shear"]}

m11 = {local["m11"]:,.4f} | m22 = {local["m22"]:,.4f} | m12 = {local["m12"]:,.4f} N.m/m
q1 = {local["q1"]:,.4f} | q2 = {local["q2"]:,.4f} N/m

**c. Sudut sumbu lokal elemen**
theta = {trace["theta_rad"]:.6f} rad = **{trace["theta_deg"]:.4f} deg**

**d. Transformasi ke sumbu global**
```
{trace["formula"]}
```

**e. Hasil**
m_xx = {glob["m_xx"]:,.4f} | m_yy = {glob["m_yy"]:,.4f} | m_xy = {glob["m_xy"]:,.4f} N.m/m
q_x = {glob["q_x"]:,.4f} | q_y = {glob["q_y"]:,.4f} N/m

> Seluruh angka di atas cukup bagi checker untuk menghitung ulang elemen ini dengan
> tangan, tanpa menjalankan tool.
"""


def deep_pilecap_warning(deep_ratio: dict[str, Any]) -> str:
    """Peringatan yang WAJIB mendahului setiap tabel `As` (PRD Bagian 8.3 keterbatasan #1).

    Diletakkan di ATAS tabel, bukan sebagai catatan kaki. Alasannya konkret: begitu angka
    `As perlu` tercetak, pembaca cenderung langsung memakainya. Bila pilecap ternyata
    berperilaku *deep member*, seluruh angka itu tidak sah -- dan peringatan yang baru
    terbaca setelah tabel sudah terlambat.
    """
    return f"""\
> [!WARNING]
> **`As` DI BAWAH INI BERASAL DARI MODEL LENTUR PELAT.** `shell-kit` adalah alat desain
> pelat per lajur 1 m. Bila pilecap berperilaku *deep member* (mekanisme strut-and-tie),
> angka-angka ini **TIDAK SAH sebagai dasar desain** (PRD Bagian 8.3 keterbatasan #1).
>
> `a/d` minimum terhitung = **{deep_ratio["min_a_over_d"]:.3f}** (pada {deep_ratio["min_at"]}).
> **Ambang batas deep pile cap belum dikonfirmasi** (PRD Bagian 17 item 5), sehingga tool
> ini TIDAK memberi vonis. Penilaian apakah pilecap ini deep atau tidak **ada pada
> engineer**, dan harus dilakukan SEBELUM angka `As` dipakai."""


def _capacity_provenance_table(provenance: dict[str, Any]) -> str:
    rows = [
        ["Engine kapasitas", f"{provenance['engine']} v{provenance['engine_version']}"],
        ["Standar", provenance["standard"]],
        ["`phi` lentur", f"{provenance['phi_flexure']:.3f}"],
        ["`phi` geser", f"{provenance['phi_shear']:.3f}"],
        ["**Asal `phi`**", provenance["phi_source"]],
        ["`fy`", f"{provenance['fy_MPa']:,.1f} MPa"],
        ["**Asal `fy`**", provenance["fy_source"]],
        ["Lebar lajur desain", f"{provenance['strip_width_mm']:,.0f} mm"],
    ]
    table = _markdown_table(["Item", "Nilai"], rows)
    functions = "\n".join(f"* `{name}`" for name in provenance["functions"])
    clauses = "\n".join(f"* **{key}** -- {text}" for key, text in provenance["clauses"].items())
    return f"{table}\n\nFungsi yang dipanggil:\n\n{functions}\n\nPasal yang dirujuk:\n\n{clauses}"


def _stirrup_section(
    shear_maps: dict[str, capacity_engine.ShearRebarMap],
    inputs: CapacityInputs,
) -> str:
    """Bagian 7b -- peta sengkang per elemen.

    Kolom "hanya Av,min" dipisahkan dari "perlu sengkang" dengan sengaja: dengan `Av,min`
    aktif, jumlah elemen ber-`Av/s > 0` sepuluh kali lipat jumlah elemen yang beton-nya
    benar-benar tidak cukup, dan satu angka gabungan akan terbaca seolah sebagian besar
    pelat butuh sengkang.
    """
    if not shear_maps:
        return ""

    unit_av = io_utils.display_unit("shear_steel_ratio")
    unit_len = io_utils.display_unit("length")
    unit_q = io_utils.display_unit("shear_per_width")
    to_disp = io_utils.to_display
    any_map = next(iter(shear_maps.values()))

    rows = []
    for direction, smap in shear_maps.items():
        finite = smap.stirrup_diameter[np.isfinite(smap.stirrup_diameter)]
        dipakai = sorted({round(float(to_disp(d, "length"))) for d in finite if d > 0})
        rows.append(
            [
                direction.upper(),
                f"{to_disp(float(np.nanmax(np.abs(smap.v_u))), 'shear_per_width'):,.1f}",
                f"{to_disp(smap.phi_v_c, 'shear_per_width'):,.1f}",
                f"**{smap.n_needs_stirrup}**",
                str(smap.n_av_min_only),
                f"{to_disp(float(np.nanmax(smap.av_per_s)), 'shear_steel_ratio'):.4f}",
                ", ".join(f"D{d}" for d in dipakai) if dipakai else "-",
                str(smap.n_web_crushed),
            ]
        )

    return f"""\
## 7b. TULANGAN GESER (SENGKANG) - peta per elemen

> [!NOTE]
> **Ini PETA ORIENTASI, bukan angka desain.** Geser satu arah pilecap didesain pada
> penampang `d` dari muka pier (bagian 7 di atas), bukan per elemen. Peta ini berguna
> untuk melihat DI MANA sengkang terkonsentrasi.

`Av/s` dihitung `shell_kit.rebar.calc_shear_Av_per_s`, diameter sengkang oleh
`calc_shear_diameter` dengan luas per kaki `Av/s x s_long x s_trans`.
Grid sengkang: **{inputs.stirrup_long_mm:,.0f} x {inputs.stirrup_trans_mm:,.0f} {unit_len}**
(ditetapkan user). `dv` = {to_disp(any_map.d_shear, "length"):,.0f} {unit_len}, dihitung
untuk **asumsi batang D16 di muka bawah** dan TIDAK diiterasi terhadap diameter sengkang
terpilih -- asumsi ini memengaruhi `V_c` dan tidak dapat dibaca dari hasil.

{
        _markdown_table(
            [
                "arah",
                f"\\|V_u\\| maks [{unit_q}]",
                f"phi V_c [{unit_q}]",
                "elemen perlu sengkang",
                "elemen hanya Av,min",
                f"Av/s maks [{unit_av}]",
                "diameter dipakai",
                "badan hancur",
            ],
            rows,
        )
    }

Kolom **"elemen perlu sengkang"** menghitung `V_u > phi V_c` -- beton benar-benar tidak
cukup. Kolom **"elemen hanya Av,min"** adalah elemen yang beton-nya cukup tetapi tetap
mendapat tulangan minimum. Keduanya dipisah karena menuntut kesimpulan yang berbeda.
"""


def _flexure_section(
    *,
    strip_design: list[dict[str, Any]],
    designs: dict[tuple[str, str], FlexureDesign],
    selections: dict[tuple[str, str], capacity_engine.RebarSelection],
    inputs: CapacityInputs,
    deep_ratio: dict[str, Any],
) -> str:
    """Bagian 7a calc sheet -- desain lentur."""
    unit_len = io_utils.display_unit("length")
    unit_as = io_utils.display_unit("steel_area")
    unit_m = io_utils.display_unit("moment_per_width")
    to_disp = io_utils.to_display

    strip_md = [
        [
            r["lokasi"],
            r["pier_id"],
            r["sisi"],
            r["direction"],
            r["strip"],
            r["face"],
            f"{to_disp(r['Mu_per_m_Nm'], 'moment_per_width'):,.2f}",
            f"{to_disp(r['d_eff_m'], 'length'):,.0f}",
            f"{to_disp(r['As_required_m2_per_m'], 'steel_area'):,.0f}",
            f"{to_disp(r['As_design_m2_per_m'], 'steel_area'):,.0f}",
            r["status"],
            "**SINGULAR**" if r.get("singular") else "-",
        ]
        for r in strip_design
    ]

    per_element = []
    for direction, face in config.REBAR_FACES:
        design = designs[(direction, face)]
        selection = selections[(direction, face)]
        per_element.append(
            [
                f"{direction} / {face}",
                f"{to_disp(design.as_governing, 'steel_area'):,.0f}",
                _selection_range(selection),
                design.n_inadequate,
            ]
        )

    as_min_disp = to_disp(next(iter(designs.values())).as_min, "steel_area")

    return f"""\
## 7a. DESAIN LENTUR - `As` perlu

{deep_pilecap_warning(deep_ratio)}

Rumus dan pasal TIDAK ditulis ulang di `pilecap-fem`. Seluruh kapasitas dihitung
`shell-kit`, sehingga rumus SNI hidup di satu repo saja dan tidak ada dua salinan yang
dapat menyimpang diam-diam.

{_capacity_provenance_table(capacity_engine.provenance_block(inputs))}

### Angka desain -- dari momen LAJUR di muka pier

Inilah `As` yang dipakai. Momen lajur sudah terintegrasi sepanjang potongan, sehingga
singularitas di tepi zona jepit pier terata-rata; puncak per elemen **tidak** dipakai
sebagai angka desain (PRD Bagian 7.2(5)).

`As pakai` = maks(`As perlu`, `As min`), dengan `As min` = {as_min_disp:,.0f} {unit_as}
(minimum susut & suhu, dihitung `shell_kit.rebar.calc_as_min_per_face`).

{
        _markdown_table(
            [
                "lokasi",
                "pier",
                "sisi",
                "arah",
                "lajur",
                "muka",
                f"Mu [{unit_m}]",
                f"d [{unit_len}]",
                f"As perlu [{unit_as}]",
                f"As pakai [{unit_as}]",
                "status",
                "catatan",
            ],
            strip_md,
        )
        if strip_md
        else "_(tidak ada lajur yang dihitung)_"
    }

### Peta per elemen -- ORIENTASI, bukan angka desain

Nilai berikut berasal dari `rebar_design.csv` dan kontur `contour_As_*.png`. Gunakan untuk
melihat SEBARAN kebutuhan tulangan. Nilai maksimumnya jatuh di tepi zona jepit pier dan
merupakan **singularitas numerik**, bukan kebutuhan nyata.

{
        _markdown_table(
            [
                "arah / muka",
                f"As perlu maks [{unit_as}]",
                f"{next(iter(selections.values())).kind} yang muncul",
                "elemen PENAMPANG_TIDAK_MEMADAI",
            ],
            per_element,
        )
    }
"""


def _selection_range(selection: capacity_engine.RebarSelection) -> str:
    """Ringkas seleksi satu muka menjadi daftar yang muncul, bukan satu angka.

    Satu nilai maksimum tidak cukup untuk seleksi: yang ingin dibaca engineer adalah
    batang APA SAJA yang muncul di pelat, karena itulah yang harus disediakan.
    """
    values = np.asarray(selection.values, dtype=np.float64)
    finite = values[np.isfinite(values) & (values > 0)]
    if finite.size == 0:
        return "-"
    if selection.kind == capacity_engine.SELECTION_CONFIG:
        return ", ".join(selection.labels[i - 1] for i in sorted({int(v) for v in finite}))
    if selection.kind == capacity_engine.SELECTION_DIAMETER:
        return ", ".join(
            f"D{d:.0f}" for d in sorted({io_utils.to_display(v, "length") for v in finite})
        )
    lo = io_utils.to_display(float(finite.min()), "length")
    hi = io_utils.to_display(float(finite.max()), "length")
    return f"{lo:,.0f} - {hi:,.0f} mm"


def _one_way_section_outboard_note(deep_ratio: dict[str, Any]) -> str:
    """Peringatan bila penampang geser satu arah jatuh DI LUAR pile.

    Ini fakta geometri, bukan pasal: `a` adalah jarak muka pier ke pusat pile dan
    penampang kritis diambil pada jarak `d` dari muka pier, sehingga `a/d < 1` berarti
    penampang itu berada di luar pusat pile. Di sana hampir tidak ada gaya yang menyeberang
    potongan, sehingga `v_u` menjadi sangat kecil dan rasio `v_u / phi V_c` **tidak
    bermakna** -- bukan bukti bahwa gesernya aman.

    Tanpa catatan ini, rasio seperti 0,004 terbaca sebagai "sangat aman" padahal yang
    terjadi adalah penampangnya salah tempat untuk geometri tersebut.
    """
    ratio = float(deep_ratio.get("min_a_over_d", float("nan")))
    if not np.isfinite(ratio) or ratio >= 1.0:
        return ""
    return f"""\
> [!CAUTION]
> **RASIO GESER SATU ARAH DI ATAS TIDAK BERMAKNA UNTUK GEOMETRI INI.** `a/d` =
> **{ratio:.3f}** < 1, artinya penampang pada jarak `d` dari muka pier jatuh **di luar
> pusat pile**. Nyaris tidak ada gaya yang menyeberang potongan itu, sehingga `v_u`
> kecil bukan karena gesernya aman melainkan karena penampangnya tidak relevan.
> Geometri dengan `a/d` sekecil ini justru mengarah ke perilaku *deep member*, yang
> penanganannya berada di luar lingkup model lentur pelat ini
> (PRD Bagian 8.3 keterbatasan #1, ambang PRD Bagian 17 item 5).

"""


def _shear_capacity_rows(
    checks: list[ShearCheck],
    capacities: dict[str, OneWayShearCapacity],
) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for check in checks:
        key = f"{check.pier_id}|{check.kind}"
        capacity = capacities.get(key)
        if capacity is None:
            rows.append(
                [
                    check.pier_id,
                    check.kind,
                    "-",
                    "-",
                    "-",
                    f"**{check.capacity_status}**",
                    "geser dua arah (pons) -- di luar lingkup shell-kit",
                ]
            )
            continue
        ratio = capacity.demand_capacity_ratio
        rows.append(
            [
                check.pier_id,
                check.kind,
                f"{io_utils.to_display(capacity.v_u, 'shear_per_width'):,.2f}",
                f"{io_utils.to_display(capacity.v_c, 'shear_per_width'):,.2f}",
                f"{io_utils.to_display(capacity.phi_v_c, 'shear_per_width'):,.2f}",
                (f"**{ratio:.3f}**" if np.isfinite(ratio) else f"**{capacity.status}**"),
                (
                    "perlu tulangan geser: Av/s = "
                    f"{io_utils.to_display(capacity.av_per_s, 'shear_steel_ratio'):.4f} mm^2/mm"
                    if capacity.needs_shear_steel
                    else "beton memadai tanpa tulangan geser"
                ),
            ]
        )
    return rows


def write_calc_sheet(
    path: Path,
    *,
    combo: str,
    geom: GeometryModel,
    mesh: MeshModel,
    results: ElementResults,
    equilibrium: dict[str, Any],
    material: dict[str, Any],
    strip_rows: list[dict[str, Any]],
    shear_checks: list[ShearCheck],
    capacity_inputs: CapacityInputs,
    strip_design: list[dict[str, Any]],
    designs: dict[tuple[str, str], FlexureDesign],
    selections: dict[tuple[str, str], capacity_engine.RebarSelection],
    shear_maps: dict[str, capacity_engine.ShearRebarMap],
    shear_capacities: dict[str, OneWayShearCapacity],
    trace: dict[str, Any],
    deep_ratio: dict[str, Any],
    project_name: str,
    run_name: str,
    command: str,
    dependencies: dict[str, str],
) -> Path:
    """`calc_sheet.md` -- 10 bagian PRD Bagian 9.4, bukan sekadar hasil akhir."""
    unit_len = io_utils.display_unit("length")
    unit_f = io_utils.display_unit("force")
    unit_m = io_utils.display_unit("moment_per_width")

    pile_rows = [
        [
            row["pile_id"],
            f"{io_utils.to_display(row['Pz_N'], 'force'):,.2f}",
            f"{row['A_disk_mesh_m2']:.6f}",
            f"{io_utils.to_display(row['pressure_Pa'], 'pressure'):,.2f}",
            row["n_elements"],
            f"{io_utils.to_display(row['applied_total_N'], 'force'):,.2f}",
            f"{io_utils.to_display(row['discrepancy_N'], 'force'):.3e}",
        ]
        for row in equilibrium.get("pile_loads", [])
    ]
    total_pz = sum(r["Pz_N"] for r in equilibrium.get("pile_loads", []))
    total_applied = sum(r["applied_total_N"] for r in equilibrium.get("pile_loads", []))
    pile_rows.append(
        [
            "**TOTAL**",
            f"**{io_utils.to_display(total_pz, 'force'):,.2f}**",
            "",
            "",
            "",
            f"**{io_utils.to_display(total_applied, 'force'):,.2f}**",
            f"**{io_utils.to_display(total_applied - total_pz, 'force'):.3e}**",
        ]
    )

    strip_rows_md = [
        [
            r["lokasi"],
            r["pier_id"],
            r["sisi"],
            r["direction"],
            r["strip"],
            f"{io_utils.to_display(r['cut_actual_m'], 'length'):,.0f}",
            r["n_elements"],
            f"{io_utils.to_display(r['M_total_Nm'], 'moment'):,.2f}",
            "**SINGULAR**" if r["singular"] else "-",
        ]
        for r in strip_rows
    ]

    shear_rows_md = [
        [
            c.pier_id,
            c.kind,
            f"{io_utils.to_display(c.d_m, 'length'):,.0f}",
            "-" if c.b_o_m is None else f"{io_utils.to_display(c.b_o_m, 'length'):,.0f}",
            f"{io_utils.to_display(c.V_u_N, 'force'):,.2f}",
            "-" if c.v_u_Pa is None else f"{io_utils.to_display(c.v_u_Pa, 'stress'):.4f}",
            c.capacity_status,
        ]
        for c in shear_checks
    ]
    capacity_rows_md = _shear_capacity_rows(shear_checks, shear_capacities)

    idx_mx, val_mx = results.extreme("m_xx")
    idx_my, val_my = results.extreme("m_yy")

    content = f"""\
# CALC SHEET - Pilecap {project_name or "(tanpa nama)"} - Kombinasi {combo}

Tool: pilecap-fem v{__version__} | Run: `{run_name}` | Manifest: `run_manifest.json`
Perintah: `{command}`
Sistem satuan internal: {config.SI_UNIT_SYSTEM}

## 1. INPUT YANG DIPAKAI

| Besaran | Nilai |
|---------|-------|
| Luas pilecap | {geom.pilecap_area:.6f} m^2 |
| Tebal pilecap `t` | {io_utils.to_display(geom.thickness, "length"):,.0f} {unit_len} |
| Modulus elastisitas `E` | {material["E"] / 1e6:,.1f} MPa |
| **Asal nilai `E`** | {material.get("E_source") or "TIDAK DICATAT"} |
| Rasio Poisson `nu` | {material["nu"]:.3f} |
| Jumlah pile | {geom.n_piles} |
| Jumlah pier | {geom.n_piers} |

### 1a. RESOLUSI SUMBER GEOMETRI (PRD Bagian 5.2.1)

{geometry_resolution_table(geom.resolution)}

## 2. MODEL FEM

Elemen: **{material.get("shell_element", "ShellMITC4")}** (Mindlin-Reissner, formulasi MITC).
Dipilih karena pilecap umumnya tebal sehingga deformasi geser transversal tidak dapat
diabaikan; teori Kirchhoff akan meremehkan lendutan (PRD Bagian 7.2(1)).

Section: **{material.get("section", "PlateFiber")}**, t = {
        io_utils.to_display(geom.thickness, "length"):,.0f} {unit_len}

Kekakuan lentur pelat:

```
D = E t^3 / (12 (1 - nu^2))
  = {material["E"]:.6e} x {geom.thickness:.4f}^3 / (12 x (1 - {material["nu"]:.3f}^2))
  = {material["D"]:.6e} N.m
```

| Besaran | Jumlah |
|---------|--------|
| Node | {mesh.n_nodes:,} |
| Elemen | {mesh.n_elements:,} |
| Node jepit (pier) | {material.get("n_fixed_nodes", "-")} |

## 3. PEMBEBANAN - jejak per pile

Tekanan `p = Pz / A_disk`, dengan `A_disk` diambil dari **jumlah luas elemen mesh**
dalam physical group pile -- bukan `pi r^2` analitis. Itulah yang menjamin
`Sigma(p x A_e)` persis sama dengan `Pz` (PRD Bagian 7.3).

{
        _markdown_table(
            [
                "pile",
                f"Pz [{unit_f}]",
                "A_disk mesh [m^2]",
                "p [kPa]",
                "n_elem",
                f"Sigma(p.A_e) [{unit_f}]",
                f"selisih [{unit_f}]",
            ],
            pile_rows,
        )
    }
{_overlap_block(equilibrium)}
## 4. CEK KESEIMBANGAN (VC-0)

| Besaran | Nilai |
|---------|-------|
| Sigma Fz beban | {io_utils.to_display(equilibrium["total_applied_fz_N"], "force"):,.4f} {unit_f} |
| Sigma Rz reaksi | {io_utils.to_display(equilibrium["total_reaction_fz_N"], "force"):,.4f} {
        unit_f
    } |
| Residu gaya (relatif) | {equilibrium["force_residual_rel"]:.3e} (toleransi {
        equilibrium["force_rtol"]:.1e}) |
| Residu momen (relatif) | {equilibrium["moment_residual_rel"]:.3e} (toleransi {
        equilibrium["moment_rtol"]:.1e}) |
| Titik acuan momen | {equilibrium["reference_point_m"]} m |
| **STATUS** | **{equilibrium["status"]}** |

## 5. HASIL PER ELEMEN - contoh telusur

{_traceability_block(trace)}

## 6. MOMEN DESAIN PER LAJUR

Momen desain diambil pada **muka pier (lokasi geometris)**. Nilai `peak` -- bila diminta
lewat `--moment-at peak/both` -- ditandai **SINGULAR**: seluruh node area pier dijepit
sehingga terjadi konsentrasi tegangan di tepi zona jepit. Nilai itu **bukan momen desain**
(PRD Bagian 7.2(5) & Bagian 8.3 keterbatasan #2).

> Apakah muka pier memang penampang kritis menurut standar adalah pertanyaan **pasal
> yang belum dikonfirmasi** (PRD Bagian 17 item 3). Yang dijamin tool ini hanyalah
> lokasinya geometris dan integrasinya benar.

{
        _markdown_table(
            [
                "lokasi",
                "pier",
                "sisi",
                "arah",
                "lajur",
                f"potongan [{unit_len}]",
                "n_elem",
                "M total [kNm]",
                "catatan",
            ],
            strip_rows_md,
        )
        if strip_rows_md
        else "_(tidak ada lajur yang dihitung)_"
    }

Nilai ekstrem per elemen (untuk orientasi, BUKAN momen desain):
`m_x` maks |.| = {io_utils.to_display(val_mx, "moment_per_width"):,.2f} {unit_m} @
({mesh.elem_centroid[idx_mx, 0]:.3f}, {mesh.elem_centroid[idx_mx, 1]:.3f}) m;
`m_y` maks |.| = {io_utils.to_display(val_my, "moment_per_width"):,.2f} {unit_m} @
({mesh.elem_centroid[idx_my, 0]:.3f}, {mesh.elem_centroid[idx_my, 1]:.3f}) m.

## 7. GESER

Geser satu arah diintegrasi pada jarak `d = t - cover` dari muka pier. Geser pons
dihitung dari **keseimbangan gaya** pada penampang `d/2` dari muka pier, bukan dari
resultant shell -- elemen shell 2D tidak memodelkan mekanisme keruntuhan pons tiga
dimensi (PRD Bagian 8.3 keterbatasan #7).

{
        _markdown_table(
            [
                "pier",
                "jenis",
                f"d [{unit_len}]",
                f"b_o [{unit_len}]",
                f"V_u [{unit_f}]",
                "v_u [MPa]",
                "kapasitas",
            ],
            shear_rows_md,
        )
        if shear_rows_md
        else "_(tidak ada cek geser)_"
    }

### Kapasitas geser SATU ARAH (SNI 2847:2019 Ps. 22.5.5.1, lewat shell-kit)

`V_c = 0,17 lambda sqrt(f'c) b_w d` per lajur 1 m, dengan
`phi = {capacity_inputs.phi_shear:.2f}`. Rasio = `v_u / (phi V_c)`; **> 1 berarti beton
saja tidak cukup** dan diperlukan tulangan geser sebesar `Av/s`.

{
        _markdown_table(
            [
                "pier",
                "jenis",
                f"v_u [{io_utils.display_unit('shear_per_width')}]",
                f"V_c [{io_utils.display_unit('shear_per_width')}]",
                f"phi V_c [{io_utils.display_unit('shear_per_width')}]",
                "v_u / phi V_c",
                "catatan",
            ],
            capacity_rows_md,
        )
        if capacity_rows_md
        else "_(tidak ada cek geser)_"
    }

{_one_way_section_outboard_note(deep_ratio)}
> [!IMPORTANT]
> **GESER PONS TETAP TIDAK DICEK.** `shell-kit` hanya menyediakan geser **satu arah**
> (`calc_Vc` memakai `b_w x d_v`). Memakainya untuk pons berarti menerapkan rumus di luar
> lingkupnya. `V_u` dan `b_o` pons **sudah** dihitung di tabel demand di atas; yang belum
> ada hanyalah kapasitasnya, dan pasalnya belum dikonfirmasi
> (PRD Bagian 17 item 3, bagian pons).

### Rasio bentang geser terhadap tinggi efektif

`a/d` minimum = **{deep_ratio["min_a_over_d"]:.3f}** (pada {deep_ratio["min_at"]}),
dengan `d` = {io_utils.to_display(deep_ratio["d_m"], "length"):,.0f} {unit_len}.

> **{deep_ratio["verdict"]}.** {deep_ratio["note"]}

{
        _flexure_section(
            strip_design=strip_design,
            designs=designs,
            selections=selections,
            inputs=capacity_inputs,
            deep_ratio=deep_ratio,
        )
    }

{_stirrup_section(shear_maps, capacity_inputs)}

## 8. ASUMSI & KETERBATASAN

{config.KNOWN_LIMITATIONS}

## 9. PERNYATAAN TANGGUNG JAWAB

{disclaimer_block()}

## 10. PROVENANCE

| Item | Nilai |
|------|-------|
| Versi tool | pilecap-fem v{__version__} |
| Run | `{run_name}` |
| Perintah | `{command}` |
{chr(10).join(f"| {name} | {version} |" for name, version in sorted(dependencies.items()))}

{open_blockers_block()}
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _log.debug("calc_sheet.md ditulis: %s", path)
    return path


# ---------------------------------------------------------------------------
# SUMMARY.md & envelope_summary.md
# ---------------------------------------------------------------------------


def write_envelope_summary(
    path: Path, envelope: Envelope, mesh: MeshModel, *, plots: list[str]
) -> Path:
    """`envelope_summary.md` -- ekstrem lintas kombinasi + kombinasi penyebabnya."""
    rows = []
    for field, env in envelope.fields.items():
        quantity = "moment_per_width" if field.startswith("m_") else "shear_per_width"
        unit = io_utils.display_unit(quantity)
        i_max = int(np.nanargmax(env.max_values))
        i_min = int(np.nanargmin(env.min_values))
        rows.append(
            [
                f"`{field}`",
                f"{io_utils.to_display(env.max_values[i_max], quantity):,.2f} {unit}",
                envelope.combo_name(env.max_combo_index[i_max]),
                f"({mesh.elem_centroid[i_max, 0]:.3f}, {mesh.elem_centroid[i_max, 1]:.3f})",
                f"{io_utils.to_display(env.min_values[i_min], quantity):,.2f} {unit}",
                envelope.combo_name(env.min_combo_index[i_min]),
                f"({mesh.elem_centroid[i_min, 0]:.3f}, {mesh.elem_centroid[i_min, 1]:.3f})",
            ]
        )

    plot_list = "\n".join(f"- `{name}`" for name in plots) or "_(tidak ada)_"
    content = f"""\
# ENVELOPE - nilai ekstrem seluruh kombinasi

Kombinasi yang di-envelope ({len(envelope.combos)}): {", ".join(envelope.combos)}

> **Envelope BUKAN kondisi keseimbangan tunggal.** Nilai di setiap lokasi dapat berasal
> dari kombinasi yang berbeda-beda, sehingga envelope **tidak boleh** dipakai untuk cek
> statika (PRD Bagian 12). Untuk cek keseimbangan gunakan hasil per kombinasi.

Positif dan negatif dipisah: maksimum menentukan tulangan bawah, minimum menentukan
tulangan atas -- keduanya menentukan desain.

{
        _markdown_table(
            [
                "field",
                "maks",
                "governing_combo",
                "lokasi [m]",
                "min",
                "governing_combo",
                "lokasi [m]",
            ],
            rows,
        )
    }

Nilai per lokasi beserta `governing_combo`-nya ada di `envelope_values.csv`.

## Plot

{plot_list}

{disclaimer_block()}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _log.info("envelope_summary.md ditulis: %s", path)
    return path


def write_summary(
    path: Path,
    *,
    project_name: str,
    run_name: str,
    command: str,
    geom: GeometryModel,
    mesh: MeshModel,
    combo_rows: list[dict[str, Any]],
    checks: dict[str, Any],
    deep_ratio: dict[str, Any],
    warnings: list[str],
    envelope: Envelope | None,
    rebar_governing: list[dict[str, Any]],
    capacity_inputs: CapacityInputs,
) -> Path:
    """`SUMMARY.md` -- ringkasan lintas kombinasi (PRD Bagian 9.4).

    Known Limitations PRD Bagian 8.3 direproduksi **apa adanya**; tool tidak boleh
    memberi kesan hasilnya berlaku universal (PRD Bagian 1.3 poin 5).
    """
    unit_m = io_utils.display_unit("moment_per_width")

    combo_table = _markdown_table(
        [
            "kombinasi",
            "Sigma Pz [kN]",
            f"|m_x| maks [{unit_m}]",
            f"|m_y| maks [{unit_m}]",
            "lendutan maks [mm]",
            "VC-0",
        ],
        [
            [
                r["combo"],
                f"{r['sum_pz_kN']:,.1f}",
                f"{abs(r['max_abs_m_xx_kNm_per_m']):,.1f}",
                f"{abs(r['max_abs_m_yy_kNm_per_m']):,.1f}",
                f"{r['max_deflection_mm']:,.2f}",
                r.get("vc0", "-"),
            ]
            for r in combo_rows
        ],
    )

    governing = "_(envelope dilewati)_"
    if envelope is not None:
        gov_rows = []
        for field, env in envelope.fields.items():
            quantity = "moment_per_width" if field.startswith("m_") else "shear_per_width"
            unit = io_utils.display_unit(quantity)
            i_max = int(np.nanargmax(env.max_values))
            i_min = int(np.nanargmin(env.min_values))
            gov_rows.append(
                [
                    f"`{field}`",
                    f"{io_utils.to_display(env.max_values[i_max], quantity):,.2f} {unit}",
                    envelope.combo_name(env.max_combo_index[i_max]),
                    f"{io_utils.to_display(env.min_values[i_min], quantity):,.2f} {unit}",
                    envelope.combo_name(env.min_combo_index[i_min]),
                ]
            )
        governing = _markdown_table(
            ["field", "maks", "governing_combo", "min", "governing_combo"], gov_rows
        )

    check_table = _markdown_table(
        ["cek", "status"], [[k, str(v)] for k, v in sorted(checks.items())]
    )
    warning_block = "\n".join(f"- {w}" for w in warnings) if warnings else "_(tidak ada)_"

    unit_as = io_utils.display_unit("steel_area")
    unit_len = io_utils.display_unit("length")
    rebar_table = (
        _markdown_table(
            [
                "arah",
                "muka",
                f"As pakai [{unit_as}]",
                f"Mu [{io_utils.display_unit('moment_per_width')}]",
                f"d [{unit_len}]",
                "status",
                "kombinasi",
                "lajur",
            ],
            [
                [
                    r["direction"],
                    r["face"],
                    f"{io_utils.to_display(r['As_design_m2_per_m'], 'steel_area'):,.0f}",
                    f"{io_utils.to_display(r['Mu_per_m_Nm'], 'moment_per_width'):,.1f}",
                    f"{io_utils.to_display(r['d_eff_m'], 'length'):,.0f}",
                    r["status"],
                    r["combo"],
                    f"{r['pier_id']} {r['sisi']} lajur {r['strip']}",
                ]
                for r in rebar_governing
            ],
        )
        if rebar_governing
        else "_(tidak ada lajur yang menghasilkan `As`)_"
    )

    content = f"""\
# SUMMARY - Pilecap {project_name or "(tanpa nama)"}

Tool: pilecap-fem v{__version__} | Run: `{run_name}`
Perintah: `{command}`
Sistem satuan internal: {config.SI_UNIT_SYSTEM}

## 1. MODEL

| Besaran | Nilai |
|---------|-------|
| Luas pilecap | {geom.pilecap_area:.6f} m^2 |
| Tebal | {io_utils.to_display(geom.thickness, "length"):,.0f} mm |
| Pile | {geom.n_piles} |
| Pier | {geom.n_piers} |
| Node / elemen | {mesh.n_nodes:,} / {mesh.n_elements:,} |

### Resolusi sumber geometri (PRD Bagian 5.2.1)

{geometry_resolution_table(geom.resolution)}

## 2. HASIL PER KOMBINASI

{combo_table}

## 3. GOVERNING (envelope lintas kombinasi)

{governing}

> Envelope bukan kondisi keseimbangan tunggal; jangan dipakai untuk cek statika.

## 3a. DESAIN TULANGAN LENTUR (governing lintas kombinasi)

{deep_pilecap_warning(deep_ratio)}

Angka di bawah berasal dari momen **lajur di muka pier**, bukan puncak per elemen.
Kapasitas dihitung `shell-kit` v{capacity_engine.provenance_block(capacity_inputs)["engine_version"]}
menurut SNI 2847:2019, dengan `fy` = {capacity_inputs.fy_mpa:,.0f} MPa
(asal: {capacity_inputs.fy_source}) dan `phi` lentur = {capacity_inputs.phi_flexure:.2f}
(asal: {capacity_inputs.phi_source}). Rinciannya di `calc_sheet.md` bagian 7a tiap kombinasi.

{rebar_table}

> [!IMPORTANT]
> **GESER PONS TIDAK DICEK.** `shell-kit` hanya menyediakan geser satu arah. `V_u` dan
> `b_o` pons sudah dihitung, kapasitasnya belum -- pasalnya belum dikonfirmasi
> (PRD Bagian 17 item 3, bagian pons).

## 4. STATUS PENGECEKAN

{check_table}

### Rasio bentang geser / tinggi efektif

`a/d` minimum = **{deep_ratio["min_a_over_d"]:.3f}** pada {deep_ratio["min_at"]}.

> **{deep_ratio["verdict"]}.** {deep_ratio["note"]}

## 5. WARNING

{warning_block}

## 6. ASUMSI & KETERBATASAN (PRD Bagian 8.3)

{config.KNOWN_LIMITATIONS}

## 7. PERNYATAAN TANGGUNG JAWAB

{disclaimer_block()}

{open_blockers_block()}
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _log.info("SUMMARY.md ditulis: %s", path)
    return path
