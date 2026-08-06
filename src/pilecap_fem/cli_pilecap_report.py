"""CLI `pilecap-report` -- post-processing, plot, dan laporan auditable (PRD Bagian 6.3).

Bekerja dari hasil `pilecap-analyze` yang sudah ada, **membaca ulang CSV**, bukan
menyimpan objek di memori. Konsekuensinya disengaja: plot dan tabel laporan lahir dari
berkas yang SAMA dengan yang dibaca engineer pemeriksa. Bila gambar tidak cocok dengan
CSV, itu akan ketahuan -- bukan tersembunyi di balik dua jalur kode yang berbeda.

Laporan dapat dibuat ulang berkali-kali (mengganti jumlah lajur, DPI, gaya plot) tanpa
mengulang analisis FEM.

.. rubric:: Yang TIDAK dapat dibuat modul ini

* **Plot opsvis** -- opsvis membaca domain OpenSees yang hidup, bukan file. Kedua PNG
  opsvis dibuat `pilecap-analyze` selagi model masih ada.
* **Rantai telusur titik Gauss** -- `element_resultants.csv` menyimpan nilai yang sudah
  dirata-rata dan ditransformasi. Bagian 5 calc sheet karena itu menampilkan rantai dari
  nilai lokal yang tersimpan, dan menyatakan keterbatasan itu apa adanya.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
from tqdm import tqdm

from pilecap_fem import (
    __version__,
    capacity_engine,
    config,
    io_utils,
    math_engine,
    mesh_model,
    postproc_engine,
    renderer,
    reporter,
)
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.validators import InputError, PilecapError

_log = config.get_logger("cli_pilecap_report")


def add_report_arguments(parser: argparse.ArgumentParser) -> None:
    """Argumen khusus pelaporan (PRD Bagian 6.3), dipakai ulang oleh `pilecap-run`."""
    parser.add_argument("--strips-x", type=int, default=None, help="Jumlah lajur arah X")
    parser.add_argument("--strips-y", type=int, default=None, help="Jumlah lajur arah Y")
    parser.add_argument(
        "--moment-at",
        choices=("pier_face", "peak", "both"),
        default=None,
        help="Lokasi momen desain (default: dari config)",
    )
    parser.add_argument(
        "--wood-armer",
        action="store_true",
        help="Hitung momen desain Wood-Armer (BELUM tersedia - lihat pesan errornya)",
    )
    parser.add_argument("--no-envelope", action="store_true", help="Lewati envelope")
    parser.add_argument(
        "--no-verify-hash",
        action="store_true",
        help="Lewati verifikasi hash file input terhadap manifest (TIDAK disarankan)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pilecap-report",
        description="Plot kontur, envelope, dan laporan auditable dari hasil pilecap-analyze.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=None,
        help="Folder hasil pilecap-analyze (default: run terakhir di --output-dir)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Root folder output, dipakai mencari run terakhir",
    )
    add_report_arguments(parser)
    parser.add_argument("--dpi", type=int, default=config.OUTPUT_DPI)
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    parser.add_argument("--version", action="version", version=f"pilecap-fem {__version__}")
    return parser


def latest_run(output_root: Path) -> Path:
    """Run terakhir di `output/`, dipilih dari nama folder yang bertimestamp."""
    if not output_root.is_dir():
        raise InputError(f"Folder output tidak ditemukan: {output_root}")
    runs = sorted(
        p for p in output_root.iterdir() if p.is_dir() and (p / "run_manifest.json").is_file()
    )
    if not runs:
        raise InputError(
            f"Tidak ada run yang bisa dilaporkan di {output_root} "
            "(folder yang memuat run_manifest.json). Jalankan `pilecap-analyze` dulu."
        )
    return runs[-1]


def _load_manifest(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "run_manifest.json"
    if not path.is_file():
        raise InputError(f"`run_manifest.json` tidak ada di {run_dir}.")
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("status") != "OK":
        raise InputError(
            f"Run di {run_dir} berstatus {manifest.get('status')!r}, bukan 'OK'. "
            "Laporan tidak dibuat dari run yang gagal -- perbaiki dulu penyebabnya "
            f"({manifest.get('checks', {}).get('error', 'lihat run.log')})."
        )
    return manifest


def _load_geometry(model_dir: Path) -> GeometryModel:
    path = model_dir / config.FILE_GEOMETRY_JSON
    if not path.is_file():
        raise InputError(
            f"`{config.FILE_GEOMETRY_JSON}` tidak ada di {model_dir}. "
            "Run ini kemungkinan dibuat versi tool sebelum Fase 3; jalankan ulang "
            "`pilecap-analyze`."
        )
    return GeometryModel.from_json_dict(json.loads(path.read_text(encoding="utf-8")))


def _verify_inputs(run_dir: Path, manifest: dict[str, Any]) -> list[str]:
    """Cocokkan sha256 file input dengan manifest.

    Laporan tidak boleh dibuat dari data yang tidak jelas asalnya. File input yang sudah
    berubah sejak analisis TIDAK membatalkan angka yang sudah tersimpan, tetapi wajib
    muncul sebagai WARNING agar checker tahu.
    """
    warnings: list[str] = []
    for name, recorded in (manifest.get("inputs") or {}).items():
        path = Path(name)
        if not path.is_absolute():
            path = run_dir.parent.parent / name if not path.exists() else path
        if not path.is_file():
            warnings.append(f"File input {name} tidak lagi ditemukan; hash tidak dapat dicek.")
            continue
        actual = f"sha256:{io_utils.sha256_file(path)}"
        if actual != recorded:
            warnings.append(
                f"File input {name} BERUBAH sejak analisis (hash tidak cocok). "
                "Angka pada laporan ini berasal dari analisis yang lama."
            )
    return warnings


def _combo_dirs(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Path]:
    slug_map = manifest.get("combo_slug_map") or {}
    if not slug_map:
        raise InputError(
            "`combo_slug_map` tidak ada di manifest; folder kombinasi tidak dapat "
            "dipetakan kembali ke nama aslinya."
        )
    mapping: dict[str, Path] = {}
    for combo, slug in slug_map.items():
        directory = run_dir / f"Combo_{slug}"
        if not directory.is_dir():
            raise InputError(f"Folder {directory.name} untuk kombinasi {combo!r} tidak ada.")
        mapping[combo] = directory
    return mapping


def run(args: argparse.Namespace, command: str) -> Path:
    run_dir = args.result_dir or latest_run(args.output_dir)
    config.setup_logging(run_dir, args.log_level)
    _log.info("pilecap-fem v%s | laporan untuk run: %s", __version__, run_dir)

    if args.wood_armer:
        # Dipanggil lebih dulu agar user tidak menunggu seluruh plot selesai hanya untuk
        # mendapati fiturnya memang belum ada.
        math_engine.wood_armer(np.zeros(1), np.zeros(1), np.zeros(1))

    manifest = _load_manifest(run_dir)
    model_dir = run_dir / config.MODEL_SUBDIR
    geom = _load_geometry(model_dir)
    mesh = mesh_model.from_csv(model_dir / "nodes.csv", model_dir / "elements.csv")
    _log.info("Mesh dibaca ulang dari CSV: %d node, %d elemen", mesh.n_nodes, mesh.n_elements)

    warnings: list[str] = []
    if not args.no_verify_hash:
        warnings.extend(_verify_inputs(run_dir, manifest))
        for message in warnings:
            _log.warning("%s", message)

    cfg = (manifest.get("parameters") or {}).get("config_si") or {}
    design = cfg.get("design") or {}
    strips_x = args.strips_x or int(design.get("strips_x", 5))
    strips_y = args.strips_y or int(design.get("strips_y", 5))
    moment_at = args.moment_at or str(design.get("moment_at", "pier_face"))
    cover_m = float(design.get("cover") or 0.0)
    mesh_size = float(((cfg.get("mesh") or {}).get("size_global")) or 0.1)

    if cover_m <= 0.0:
        raise InputError(
            "`design.cover` tidak diisi di config run ini, sehingga tinggi efektif "
            "d = t - cover tidak dapat dihitung dan cek geser tidak dapat dibuat."
        )

    # Dibangun SEBELUM plot apa pun: `CapacityInputs.from_config` memanggil
    # `validators.validate_design`, sehingga config yang kurang lengkap gagal dalam
    # hitungan milidetik, bukan setelah seluruh kontur selesai digambar (Core 3).
    capacity_inputs = capacity_engine.CapacityInputs.from_config(cfg)
    _log.info(
        "Cek kapasitas aktif: shell-kit v%s | fy = %.0f MPa | phi = %.2f/%.2f (%s)",
        capacity_engine.provenance_block(capacity_inputs)["engine_version"],
        capacity_inputs.fy_mpa,
        capacity_inputs.phi_flexure,
        capacity_inputs.phi_shear,
        capacity_inputs.phi_source,
    )

    deep_ratio = postproc_engine.shear_span_ratio(geom, cover_m)
    combo_dirs = _combo_dirs(run_dir, manifest)

    # Cek visual tumpuan & pembebanan: jawaban atas pertanyaan yang sulit dijawab dari
    # angka -- apakah jepit dan beban benar-benar menempel di tempat yang seharusnya.
    first_equilibrium = json.loads(
        (next(iter(combo_dirs.values())) / "equilibrium_check.json").read_text(encoding="utf-8")
    )
    renderer.render_boundary_load_check(
        model_dir / config.FILE_BOUNDARY_CHECK,
        geom,
        mesh,
        pz_by_pile={
            row["pile_id"]: float(row["Pz_N"]) for row in first_equilibrium.get("pile_loads", [])
        },
        dpi=args.dpi,
    )
    results_by_combo: dict[str, postproc_engine.ElementResults] = {}
    designs_by_combo: dict[str, dict[tuple[str, str], capacity_engine.FlexureDesign]] = {}
    strip_design_by_combo: dict[str, list[dict[str, Any]]] = {}
    combo_rows: list[dict[str, Any]] = []
    checks: dict[str, Any] = {
        k: v for k, v in (manifest.get("checks") or {}).items() if k != "error"
    }

    for combo, combo_dir in tqdm(combo_dirs.items(), desc="Laporan", unit="combo"):
        results_by_combo[combo] = _report_one_combo(
            combo=combo,
            combo_dir=combo_dir,
            run_dir=run_dir,
            geom=geom,
            mesh=mesh,
            manifest=manifest,
            cfg=cfg,
            strips_x=strips_x,
            strips_y=strips_y,
            moment_at=moment_at,
            cover_m=cover_m,
            mesh_size=mesh_size,
            deep_ratio=deep_ratio,
            command=command,
            dpi=args.dpi,
            combo_rows=combo_rows,
            capacity_inputs=capacity_inputs,
            designs_by_combo=designs_by_combo,
            strip_design_by_combo=strip_design_by_combo,
        )

    envelope = None
    if not args.no_envelope and len(results_by_combo) >= 1:
        envelope = _write_envelope(
            run_dir, geom, mesh, results_by_combo, designs_by_combo, dpi=args.dpi
        )

    reporter.write_summary(
        run_dir / config.FILE_SUMMARY,
        project_name=str(
            ((manifest.get("parameters") or {}).get("config_raw") or {})
            .get("project", {})
            .get("name", "")
        ),
        run_name=run_dir.name,
        command=command,
        geom=geom,
        mesh=mesh,
        combo_rows=combo_rows,
        checks=checks,
        deep_ratio=deep_ratio,
        warnings=warnings + list(manifest.get("warnings") or []),
        envelope=envelope,
        rebar_governing=capacity_engine.governing_strip_design(strip_design_by_combo),
        capacity_inputs=capacity_inputs,
    )

    _log.info("Laporan selesai: %d kombinasi -> %s", len(combo_dirs), run_dir)
    return run_dir


def _report_one_combo(
    *,
    combo: str,
    combo_dir: Path,
    run_dir: Path,
    geom: GeometryModel,
    mesh: mesh_model.MeshModel,
    manifest: dict[str, Any],
    cfg: dict[str, Any],
    strips_x: int,
    strips_y: int,
    moment_at: str,
    cover_m: float,
    mesh_size: float,
    deep_ratio: dict[str, Any],
    command: str,
    dpi: int,
    combo_rows: list[dict[str, Any]],
    capacity_inputs: capacity_engine.CapacityInputs,
    designs_by_combo: dict[str, dict[tuple[str, str], capacity_engine.FlexureDesign]],
    strip_design_by_combo: dict[str, list[dict[str, Any]]],
) -> postproc_engine.ElementResults:
    resultants_csv = combo_dir / "element_resultants.csv"
    if not resultants_csv.is_file():
        raise InputError(
            f"{resultants_csv.name} tidak ada di {combo_dir.name}. "
            "Jalankan `pilecap-analyze` TANPA --no-save-raw agar laporan dapat dibuat."
        )
    results = reporter.read_element_resultants_csv(resultants_csv, combo)
    equilibrium = json.loads((combo_dir / "equilibrium_check.json").read_text(encoding="utf-8"))
    pz_by_pile = {row["pile_id"]: float(row["Pz_N"]) for row in equilibrium.get("pile_loads", [])}

    # --- kontur -------------------------------------------------------------
    for field, (filename, quantity, title) in config.CONTOUR_FIELDS.items():
        renderer.render_contour(
            combo_dir / filename,
            geom,
            mesh,
            getattr(results, field),
            quantity=quantity,
            title=title,
            combo=combo,
            pz_by_pile=pz_by_pile,
            dpi=dpi,
        )

    displacements_csv = combo_dir / config.FILE_NODE_DISPLACEMENTS
    if displacements_csv.is_file():
        uz = reporter.read_node_displacements_csv(displacements_csv)[:, 2]
        renderer.render_contour(
            combo_dir / config.FILE_CONTOUR_DEFLECTION,
            geom,
            mesh,
            renderer.element_values_from_nodal(mesh, uz),
            quantity="deflection",
            title="Lendutan vertikal w",
            combo=combo,
            pz_by_pile=pz_by_pile,
            dpi=dpi,
        )

    # --- momen lajur & geser ------------------------------------------------
    strip_rows = postproc_engine.design_moment_sections(
        results,
        mesh,
        geom,
        n_strips_x=strips_x,
        n_strips_y=strips_y,
        mesh_size=mesh_size,
        moment_at=moment_at,
    )
    reporter.write_strip_moments_csv(combo_dir / "strip_moments_x.csv", strip_rows, "x")
    reporter.write_strip_moments_csv(combo_dir / "strip_moments_y.csv", strip_rows, "y")

    shear_checks = postproc_engine.shear_demand(results, mesh, geom, pz_by_pile, cover_m=cover_m)
    reporter.write_shear_checks_csv(combo_dir / "shear_checks.csv", shear_checks)

    # --- kapasitas (shell-kit) ----------------------------------------------
    designs = capacity_engine.design_all_faces(
        {d: getattr(results, field) for d, field in config.REBAR_MOMENT_FIELD.items()},
        capacity_inputs,
    )
    designs_by_combo[combo] = designs
    strip_design = capacity_engine.strip_flexure_design(strip_rows, capacity_inputs)
    strip_design_by_combo[combo] = strip_design
    shear_capacities = capacity_engine.one_way_shear_from_checks(shear_checks, capacity_inputs)

    reporter.write_rebar_design_csv(combo_dir / config.FILE_REBAR_DESIGN, designs, mesh)
    for (direction, face), (filename, title) in config.REBAR_FACES.items():
        renderer.render_contour(
            combo_dir / filename,
            geom,
            mesh,
            capacity_engine.as_design_array(designs[(direction, face)]),
            quantity="steel_area",
            title=title,
            # `As` tidak bertanda: skala diverging yang dipusatkan di nol akan membuang
            # separuh rentang warna untuk nilai yang tidak pernah muncul.
            diverging=False,
            combo=combo,
            pz_by_pile=pz_by_pile,
            dpi=dpi,
        )

    # --- calc sheet ---------------------------------------------------------
    material_cfg = cfg.get("material") or {}
    stats = manifest.get("model_stats") or {}

    trace_path = combo_dir / config.FILE_TRACEABILITY
    if not trace_path.is_file():
        raise InputError(
            f"`{config.FILE_TRACEABILITY}` tidak ada di {combo_dir.name}. Rantai telusur "
            "titik Gauss (PRD Bagian 9.4 bagian 5) hanya dapat dibuat oleh "
            "`pilecap-analyze`; laporan tidak boleh menyajikan versi yang terpotong "
            "tanpa sepengetahuan checker. Jalankan ulang `pilecap-analyze`."
        )
    trace = json.loads(trace_path.read_text(encoding="utf-8"))

    material = {
        "E": float(material_cfg.get("E", 0.0)),
        "E_source": material_cfg.get("E_source"),
        "nu": float(material_cfg.get("poisson", 0.0)),
        "D": stats.get("flexural_rigidity_Nm", float("nan")),
        "shell_element": stats.get("element_type", "ShellMITC4"),
        "section": stats.get("section", "PlateFiber"),
        "n_fixed_nodes": stats.get("n_fixed_nodes", "-"),
    }
    reporter.write_calc_sheet(
        combo_dir / config.FILE_CALC_SHEET,
        combo=combo,
        geom=geom,
        mesh=mesh,
        results=results,
        equilibrium=equilibrium,
        material=material,
        strip_rows=strip_rows,
        shear_checks=shear_checks,
        capacity_inputs=capacity_inputs,
        strip_design=strip_design,
        designs=designs,
        shear_capacities=shear_capacities,
        trace=trace,
        deep_ratio=deep_ratio,
        project_name=str(
            ((manifest.get("parameters") or {}).get("config_raw") or {})
            .get("project", {})
            .get("name", "")
        ),
        run_name=run_dir.name,
        command=command,
        dependencies=manifest.get("dependencies") or {},
    )

    summary_row = next(
        (r for r in (manifest.get("combo_summary") or []) if r.get("combo") == combo),
        None,
    )
    combo_rows.append(
        {
            "combo": combo,
            "sum_pz_kN": (summary_row or {}).get("sum_pz_kN", sum(pz_by_pile.values()) / 1e3),
            "max_abs_m_xx_kNm_per_m": float(np.nanmax(np.abs(results.m_xx))) / 1e3,
            "max_abs_m_yy_kNm_per_m": float(np.nanmax(np.abs(results.m_yy))) / 1e3,
            "max_deflection_mm": (summary_row or {}).get("max_deflection_mm", float("nan")),
            "vc0": equilibrium.get("status", "-"),
        }
    )
    return results


def _write_envelope(
    run_dir: Path,
    geom: GeometryModel,
    mesh: mesh_model.MeshModel,
    results_by_combo: dict[str, postproc_engine.ElementResults],
    designs_by_combo: dict[str, dict[tuple[str, str], capacity_engine.FlexureDesign]],
    *,
    dpi: int,
) -> postproc_engine.Envelope:
    envelope = postproc_engine.build_envelope(results_by_combo)
    envelope_dir = run_dir / config.ENVELOPE_SUBDIR
    envelope_dir.mkdir(parents=True, exist_ok=True)

    plots: list[str] = []
    for field, (base, quantity, title) in config.CONTOUR_FIELDS.items():
        stem = base.replace("contour_", "envelope_").replace(".png", "")
        for which, values in (
            ("max", envelope.fields[field].max_values),
            ("min", envelope.fields[field].min_values),
        ):
            name = f"{stem}_{which}.png"
            renderer.render_contour(
                envelope_dir / name,
                geom,
                mesh,
                values,
                quantity=quantity,
                title=f"ENVELOPE {which} - {title}",
                combo="seluruh kombinasi",
                dpi=dpi,
            )
            plots.append(name)

    reporter.write_rebar_envelope_csv(
        envelope_dir / config.FILE_REBAR_ENVELOPE, designs_by_combo, mesh
    )
    reporter.write_envelope_csv(envelope_dir / "envelope_values.csv", envelope, mesh)
    reporter.write_envelope_summary(
        envelope_dir / "envelope_summary.md", envelope, mesh, plots=plots
    )
    return envelope


def entry_point(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = "pilecap-report " + " ".join(argv if argv is not None else sys.argv[1:])
    try:
        run_dir = run(args, command.strip())
    except NotImplementedError as exc:
        print(f"\nBELUM TERSEDIA: {exc}", file=sys.stderr)
        return 4
    except PilecapError as exc:
        logging.getLogger("pilecap_fem").error("%s", exc)
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        if args.log_level == "DEBUG":
            raise
        return 2
    print(f"\nOK -> {run_dir}")
    return 0


__all__ = ["build_parser", "entry_point", "latest_run", "run"]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
