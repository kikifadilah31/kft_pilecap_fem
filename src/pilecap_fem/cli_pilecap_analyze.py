"""CLI `pilecap-analyze` -- model OpenSeesPy + analisis semua kombinasi (PRD Bagian 6.2).

Menjalankan rantai yang sama dengan `pilecap-mesh` sampai mesh terbentuk (lewat
`cli_pilecap_mesh.prepare_model`), lalu untuk SETIAP kombinasi pembebanan:

    ops.wipe() -> bangun model -> analyze(1) -> **cek keseimbangan VC-0** ->
    resultant lokal -> transformasi ke sumbu global -> hasil mentah

Cek keseimbangan berjalan di setiap kombinasi, bukan hanya saat testing
(PRD Bagian 1.3 poin 3). Kombinasi yang gagal VC-0 menghentikan run dan **tidak
menghasilkan output desain**.

Plot kontur, calc sheet, dan envelope adalah tugas `pilecap-report` (Fase 3).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path

from tqdm import tqdm

from pilecap_fem import (
    __version__,
    cli_pilecap_mesh,
    config,
    fem_engine,
    io_utils,
    postproc_engine,
    provenance,
    renderer,
    reporter,
    validators,
)
from pilecap_fem.validators import AnalysisError, InputError, PilecapError

_log = config.get_logger("cli_pilecap_analyze")


def add_analysis_arguments(parser: argparse.ArgumentParser) -> None:
    """Argumen khusus analisis (PRD Bagian 6.2).

    Dipisahkan agar `pilecap-run` menyusun parser-nya dari helper yang SAMA, bukan
    menyalin daftar argumen yang kemudian menyimpang diam-diam.
    """
    parser.add_argument(
        "--reactions", type=Path, default=None, help="CSV reaksi pile (default: auto-detect)"
    )
    parser.add_argument(
        "--combo",
        action="append",
        default=None,
        metavar="NAMA",
        help="Analisis hanya kombinasi ini (boleh diulang). Default: semua.",
    )
    parser.add_argument(
        "--element",
        choices=fem_engine.SUPPORTED_SHELL_ELEMENTS,
        default=None,
        help="Override jenis elemen shell",
    )
    parser.add_argument(
        "--self-weight",
        action="store_true",
        default=None,
        help="Aktifkan berat sendiri pilecap (default: dari config)",
    )
    parser.add_argument(
        "--equilibrium-rtol",
        type=float,
        default=config.EQUILIBRIUM_RTOL_DEFAULT,
        help="Toleransi relatif cek keseimbangan gaya VC-0",
    )
    parser.add_argument(
        "--no-save-raw",
        action="store_true",
        help="Lewati penulisan element_resultants.csv (hemat ruang; audit jadi terbatas)",
    )
    parser.add_argument(
        "--opsvis",
        action="store_true",
        help=(
            "Paksa plot opsvis dibuat meskipun jumlah elemen melebihi "
            f"{config.OPSVIS_MAX_ELEMENTS:,} (default: dilewati dengan WARNING)"
        ),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pilecap-analyze",
        description="Bangun model OpenSeesPy dan analisis seluruh kombinasi pembebanan.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    cli_pilecap_mesh.add_common_arguments(parser)
    cli_pilecap_mesh.add_mesh_arguments(parser)
    add_analysis_arguments(parser)
    return parser


def _select_combos(
    reactions: io_utils.ReactionTable, requested: list[str] | None
) -> tuple[str, ...]:
    if not requested:
        return reactions.combos
    unknown = [c for c in requested if c not in reactions.values]
    if unknown:
        raise InputError(
            f"Kombinasi {unknown} tidak ada di {reactions.path.name}.\n"
            f"  Tersedia: {list(reactions.combos)}"
        )
    # Pertahankan urutan file, bukan urutan flag, agar hasil tetap reproducible.
    return tuple(c for c in reactions.combos if c in set(requested))


def run(args: argparse.Namespace, command: str) -> Path:
    run_dir = provenance.make_run_dir(args.output_dir)
    config.setup_logging(run_dir, args.log_level)
    model_dir = run_dir / config.MODEL_SUBDIR
    model_dir.mkdir(parents=True, exist_ok=True)

    _log.info("pilecap-fem v%s | run: %s", __version__, run_dir)

    manifest = provenance.Manifest(run_dir, command)
    manifest.set_parameters(
        {"cli": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
    )
    manifest.write()

    try:
        return _run_inner(args, run_dir, model_dir, manifest)
    except Exception as exc:
        manifest.set_status("FAILED")
        manifest.update_checks({"error": f"{type(exc).__name__}: {exc}"})
        manifest.write()
        raise


def _run_inner(
    args: argparse.Namespace,
    run_dir: Path,
    model_dir: Path,
    manifest: provenance.Manifest,
) -> Path:
    prepared = cli_pilecap_mesh.prepare_model(args, model_dir, manifest, require_material=True)
    cli_pilecap_mesh.write_model_artifacts(prepared, run_dir, model_dir, dpi=args.dpi)
    cli_pilecap_mesh.record_model_stats(prepared, manifest)

    # Geometri hasil resolusi ditulis apa adanya agar folder run SWASEMBADA:
    # `pilecap-report` tidak perlu membuka file input asli yang bisa saja sudah berubah.
    (model_dir / config.FILE_GEOMETRY_JSON).write_text(
        json.dumps(prepared.geom.to_json_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    reactions_path = args.reactions or io_utils.autodetect(
        args.input_dir, "reactions", required=True
    )
    assert reactions_path is not None
    force_factor = config.FORCE_TO_SI[prepared.loaded.input_units["force"]]
    reactions = io_utils.load_reactions(reactions_path, force_factor)
    manifest.add_input(reactions_path, reactions.sha256)

    reaction_warnings = validators.validate_reactions(reactions, prepared.geom)
    manifest.add_warnings(reaction_warnings)

    material = fem_engine.MaterialProperties.from_config(prepared.loaded.si)
    options = fem_engine.AnalysisOptions.from_config(prepared.loaded.si)
    if args.element is not None:
        options = replace(options, shell_element=args.element)
    if args.self_weight is not None:
        options = replace(options, include_self_weight=bool(args.self_weight))
    options = replace(options, equilibrium_rtol=float(args.equilibrium_rtol))
    options.validate()

    load_strategy = fem_engine.make_load_strategy(
        (prepared.loaded.si.get("pile") or {}).get("modeling", "pressure")
    )

    _log.info(
        "Model FEM: %s + %s | t = %.3f m | E = %.0f MPa (%s) | nu = %.3f",
        options.shell_element,
        options.section,
        material.thickness,
        material.E / 1e6,
        material.E_source or "sumber tidak dicatat",
        material.nu,
    )
    _log.info(
        "D = E t^3 / 12(1-nu^2) = %.4e N.m",
        material.flexural_rigidity,
    )

    combos = _select_combos(reactions, args.combo)
    _log.info("Kombinasi yang dianalisis (%d): %s", len(combos), list(combos))

    slug_map: dict[str, str] = {}
    checks: dict[str, str] = {}
    summary: list[dict[str, object]] = []
    plot_warnings: list[str] = []
    opsvis_plotted = False

    for combo in tqdm(combos, desc="Kombinasi", unit="combo"):
        result = fem_engine.analyze_combo(
            prepared.mesh,
            prepared.geom,
            material,
            options,
            combo=combo,
            pz_by_pile=reactions.values[combo],
            load_strategy=load_strategy,
        )
        results = postproc_engine.compute_element_results(result, prepared.mesh)

        slug = reporter.slugify(combo)
        slug_map[combo] = slug
        combo_dir = run_dir / f"Combo_{slug}"
        combo_dir.mkdir(parents=True, exist_ok=True)

        if not args.no_save_raw:
            reporter.write_element_resultants_csv(
                combo_dir / "element_resultants.csv", results, prepared.mesh
            )
        reporter.write_reactions_csv(combo_dir / "reactions.csv", result, prepared.mesh)
        reporter.write_equilibrium_json(combo_dir / "equilibrium_check.json", result)
        reporter.write_node_displacements_csv(
            combo_dir / config.FILE_NODE_DISPLACEMENTS, result, prepared.mesh
        )

        # Rantai telusur elemen dengan |m_x| terbesar (PRD Bagian 9.4 bagian 5).
        # Ditulis DI SINI karena nilai per titik Gauss tidak tersimpan di
        # element_resultants.csv; tanpa berkas ini `pilecap-report` hanya bisa
        # menyajikan rantai yang terpotong.
        index_trace, _ = results.extreme("m_xx")
        (combo_dir / config.FILE_TRACEABILITY).write_text(
            json.dumps(
                postproc_engine.traceability_sample(results, prepared.mesh, index_trace),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        # Plot opsvis HARUS dibuat di sini: opsvis membaca domain OpenSees yang hidup,
        # bukan file. `pilecap-report` yang bekerja dari CSV tidak dapat membuatnya
        # tanpa menyelesaikan ulang model.
        if not opsvis_plotted:
            renderer.render_opsvis_model(
                model_dir / config.FILE_MODEL_OPSVIS,
                n_elements=prepared.mesh.n_elements,
                n_fixed_nodes=len(result.reaction_nodes),
                force=args.opsvis,
                dpi=args.dpi,
                warnings=plot_warnings,
            )
            opsvis_plotted = True
        renderer.render_opsvis_defo(
            combo_dir / config.FILE_DEFORMED_OPSVIS,
            combo=combo,
            sfac=renderer.deformation_scale(prepared.mesh, result.displacements),
            max_deflection_m=result.max_deflection,
            n_elements=prepared.mesh.n_elements,
            force=args.opsvis,
            dpi=args.dpi,
            warnings=plot_warnings,
        )

        checks[f"equilibrium_VC0[{combo}]"] = "PASS" if result.equilibrium.passed else "FAIL"
        index_mx, value_mx = results.extreme("m_xx")
        index_my, value_my = results.extreme("m_yy")
        summary.append(
            {
                "combo": combo,
                "slug": slug,
                "sum_pz_kN": reactions.total_pz(combo) / 1e3,
                "max_abs_m_xx_kNm_per_m": value_mx / 1e3,
                "max_abs_m_xx_at_m": prepared.mesh.elem_centroid[index_mx].tolist(),
                "max_abs_m_yy_kNm_per_m": value_my / 1e3,
                "max_abs_m_yy_at_m": prepared.mesh.elem_centroid[index_my].tolist(),
                "max_deflection_mm": result.max_deflection * 1e3,
                "equilibrium_force_residual_rel": result.equilibrium.force_residual_rel,
                "equilibrium_moment_residual_rel": result.equilibrium.moment_residual_rel,
            }
        )
        _log.info(
            "[%s] |m_x| maks = %.1f kNm/m @ (%.3f, %.3f) m | lendutan maks = %.2f mm",
            combo,
            abs(value_mx) / 1e3,
            prepared.mesh.elem_centroid[index_mx, 0],
            prepared.mesh.elem_centroid[index_mx, 1],
            result.max_deflection * 1e3,
        )

    manifest.update_model_stats(
        {
            "element_type": options.shell_element,
            "section": options.section,
            "n_fixed_nodes": sum(
                len(prepared.mesh.nodes_in_group(p.group_name)) for p in prepared.geom.piers
            ),
            "include_self_weight": options.include_self_weight,
            "pile_load_modeling": getattr(type(load_strategy), "name", "unknown"),
            "flexural_rigidity_Nm": material.flexural_rigidity,
            "E_source": material.E_source,
        }
    )
    manifest.update_checks(
        {
            "fragment_area_match": "PASS",
            "all_quad": "PASS" if prepared.raw.n_tri == 0 else "FAIL",
            "capacity_checks": "NOT_EVALUATED",
            **checks,
        }
    )
    manifest.add_warnings(plot_warnings)
    manifest.data["combos_analyzed"] = list(combos)
    manifest.data["combo_slug_map"] = slug_map
    manifest.data["combo_summary"] = summary
    manifest.set_status("OK")
    manifest.write()

    _log.info("Selesai: %d kombinasi -> %s", len(combos), run_dir)
    return run_dir


def entry_point(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = "pilecap-analyze " + " ".join(argv if argv is not None else sys.argv[1:])
    try:
        if cli_pilecap_mesh.handle_init_example(args):
            return 0
        run_dir = run(args, command.strip())
    except PilecapError as exc:
        logging.getLogger("pilecap_fem").error("%s", exc)
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        if args.log_level == "DEBUG":
            raise
        return 2
    print(f"\nOK -> {run_dir}")
    return 0


__all__ = ["AnalysisError", "build_parser", "entry_point", "run"]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
