"""CLI `pilecap-mesh` -- geometri + meshing saja (PRD Bagian 6.1).

Dipakai untuk cek visual sebelum analisis panjang. Tidak membangun model FEM dan tidak
membutuhkan properti material, sehingga `validators.validate_material()` sengaja TIDAK
dipanggil di sini -- `material.E` baru wajib diisi saat `pilecap-analyze` dijalankan.

Modul ini juga menampung **rantai bersama input -> geometri -> mesh** (`prepare_model`)
beserta argumen CLI-nya, karena `pilecap-analyze` dan `pilecap-run` menjalankan rantai
yang sama persis sebelum melanjutkan ke FEM. Menyalinnya ke tiap CLI berisiko keduanya
menyimpang diam-diam -- justru kelas kesalahan yang paling berbahaya di sini.
"""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pilecap_fem import (
    __version__,
    config,
    geometry_builder,
    io_utils,
    mesh_engine,
    provenance,
    renderer,
    reporter,
    validators,
)
from pilecap_fem import mesh_model as mesh_model_mod
from pilecap_fem.geometry_builder import GeometryModel, ResolvedGeometrySources
from pilecap_fem.mesh_model import MeshModel
from pilecap_fem.validators import InputError, PilecapError

_log = config.get_logger("cli_pilecap_mesh")


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    """Argumen input/output & resolusi geometri, sama untuk semua CLI (PRD Bagian 6)."""
    parser.add_argument("--config", type=Path, default=None, help="File konfigurasi JSON")
    parser.add_argument(
        "--input-dir", type=Path, default=Path("input"), help="Folder auto-detect input"
    )
    parser.add_argument(
        "--output-dir", type=Path, default=Path("output"), help="Root folder output"
    )
    parser.add_argument(
        "--pilecap-polygon",
        type=Path,
        default=None,
        help="CSV polygon pilecap - OVERRIDE length_x/length_y/origin",
    )
    parser.add_argument(
        "--pile-coords",
        type=Path,
        default=None,
        help="CSV koordinat pile - OVERRIDE konfigurasi grid",
    )
    parser.add_argument(
        "--pier-polygon",
        type=Path,
        default=None,
        help="CSV polygon pier - OVERRIDE shape/width_*/diameter/centerline",
    )
    parser.add_argument(
        "--no-custom",
        action="store_true",
        help="Abaikan seluruh CSV geometri hasil auto-detect; paksa parameter JSON",
    )
    parser.add_argument("--dpi", type=int, default=config.OUTPUT_DPI)
    parser.add_argument(
        "--init-example",
        type=Path,
        default=None,
        metavar="DIR",
        help=(
            "Salin ketiga contoh bawaan ke DIR lalu keluar. Berguna bagi pengguna "
            "`uvx` yang tidak meng-clone repo."
        ),
    )
    parser.add_argument(
        "--log-level", choices=("DEBUG", "INFO", "WARNING", "ERROR"), default="INFO"
    )
    parser.add_argument("--version", action="version", version=f"pilecap-fem {__version__}")


def add_mesh_arguments(parser: argparse.ArgumentParser) -> None:
    """Argumen yang mengubah meshing (PRD Bagian 6.1)."""
    parser.add_argument(
        "--size", type=float, default=None, help="Override ukuran mesh global [satuan input]"
    )
    parser.add_argument("--size-mode", choices=("uniform", "graded"), default=None)
    parser.add_argument("--algorithm", type=int, default=None, help="Override Mesh.Algorithm")
    parser.add_argument(
        "--recomb-algorithm", type=int, default=None, help="Override Mesh.RecombinationAlgorithm"
    )
    parser.add_argument(
        "--allow-tri",
        action="store_true",
        help="Izinkan elemen segitiga lolos (DIAGNOSTIK SAJA - model FEM akan menolaknya)",
    )
    parser.add_argument("--export-msh", action="store_true", help="Simpan juga model.msh")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pilecap-mesh",
        description="Generate geometri + mesh all-quad pilecap (tanpa analisis FEM).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    add_common_arguments(parser)
    add_mesh_arguments(parser)
    parser.add_argument("--preview", action="store_true", help="Tampilkan plot mesh interaktif")
    return parser


def handle_init_example(args: argparse.Namespace) -> bool:
    """Tangani `--init-example DIR`. Kembalikan True bila program harus berhenti.

    Dipanggil paling awal di keempat `entry_point`, sebelum satu pun file input dibaca.

    Menolak menimpa folder yang sudah berisi: contoh ditulis untuk dimodifikasi user,
    dan menimpanya diam-diam berarti membuang pekerjaan yang mungkin sudah dilakukan.
    """
    target: Path | None = getattr(args, "init_example", None)
    if target is None:
        return False

    source = config.examples_dir()
    target.mkdir(parents=True, exist_ok=True)

    existing = [name for name in config.EXAMPLE_NAMES if (target / name).exists()]
    if existing:
        raise InputError(
            f"Folder contoh berikut sudah ada di {target}: {existing}.\n"
            "  Contoh tidak ditimpa -- berkas itu dimaksudkan untuk Anda modifikasi.\n"
            "  Hapus atau pindahkan folder tersebut, atau tunjuk direktori lain."
        )

    for name in config.EXAMPLE_NAMES:
        shutil.copytree(source / name, target / name)

    print(f"Contoh disalin ke {target.resolve()}:")
    for name in config.EXAMPLE_NAMES:
        n_files = len(list((target / name).iterdir()))
        print(f"  {name}/  ({n_files} berkas)")
    print(
        "\nCoba jalankan:\n"
        f"  pilecap-run --config {config.EXAMPLE_NAMES[0]}/pilecap_config.json "
        f"--input-dir {config.EXAMPLE_NAMES[0]}"
    )
    return True


def apply_cli_mesh_overrides(
    cfg: dict[str, Any], args: argparse.Namespace, length_factor: float
) -> dict[str, Any]:
    """Terapkan override CLI ke blok `mesh`, sebelum validasi.

    `--size` diberikan dalam satuan input (default mm) dan dikonversi ke SI di sini
    memakai faktor yang sama dengan file config -- tetap satu tabel konversi
    (PRD Bagian 4.2).
    """
    applied: dict[str, Any] = {}
    mesh = cfg.setdefault("mesh", {})
    if getattr(args, "size", None) is not None:
        mesh["size_global"] = float(args.size) * length_factor
        applied["size"] = args.size
    if getattr(args, "size_mode", None) is not None:
        mesh["size_mode"] = args.size_mode
        applied["size_mode"] = args.size_mode
    if getattr(args, "algorithm", None) is not None:
        mesh["algorithm"] = args.algorithm
        applied["algorithm"] = args.algorithm
    if getattr(args, "recomb_algorithm", None) is not None:
        mesh["recombination_algorithm"] = args.recomb_algorithm
        applied["recomb_algorithm"] = args.recomb_algorithm
    if applied:
        _log.info("Override CLI pada blok mesh: %s", applied)
    return applied


@dataclass(frozen=True)
class PreparedModel:
    """Hasil rantai bersama input -> geometri -> mesh."""

    loaded: io_utils.LoadedConfig
    sources: ResolvedGeometrySources
    geom: GeometryModel
    options: mesh_engine.MeshOptions
    raw: mesh_engine.RawMesh
    mesh: MeshModel
    cli_overrides: dict[str, Any]

    @property
    def project_name(self) -> str:
        return str((self.loaded.raw.get("project") or {}).get("name", ""))


def prepare_model(
    args: argparse.Namespace,
    model_dir: Path,
    manifest: provenance.Manifest,
    *,
    require_material: bool,
) -> PreparedModel:
    """Baca input, resolusikan geometri, validasi, dan bangun mesh.

    `require_material` dipisahkan karena `pilecap-mesh` tidak membutuhkan `material.E`
    sama sekali; memaksanya di sana hanya akan menghalangi cek visual mesh tanpa alasan.
    """
    config_path = args.config or io_utils.autodetect(args.input_dir, "config", required=True)
    assert config_path is not None
    loaded = io_utils.load_config(config_path)

    sources = io_utils.resolve_geometry_sources(
        loaded,
        input_dir=args.input_dir if args.input_dir.is_dir() else None,
        cli_pilecap_polygon=args.pilecap_polygon,
        cli_pile_coords=args.pile_coords,
        cli_pier_polygon=args.pier_polygon,
        no_custom=args.no_custom,
    )

    length_factor = config.LENGTH_TO_SI[loaded.input_units["length"]]
    cli_overrides = apply_cli_mesh_overrides(loaded.si, args, length_factor)

    present = io_utils.sources_present(sources.resolution)
    validators.validate_config_geometry_params(loaded.si, present)
    validators.validate_config_mesh(loaded.si)
    if require_material:
        validators.validate_material(loaded.si)

    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    _log.info(
        "Pilecap luas %.3f m2 | t = %.3f m | %d pile | %d pier",
        geom.pilecap_area,
        geom.thickness,
        geom.n_piles,
        geom.n_piers,
    )
    validators.validate_geometry(geom)
    validators.validate_mesh_vs_geometry(loaded.si, geom)

    options = mesh_engine.MeshOptions.from_config(loaded.si)

    # Manifest dilengkapi SEBELUM meshing dimulai (PRD Bagian 10).
    manifest.add_input(config_path, loaded.sha256)
    for res in (sources.resolution.pilecap, sources.resolution.pile, sources.resolution.pier):
        if res.file is not None:
            manifest.add_input(res.file, res.sha256)
    manifest.set_geometry_resolution(sources.resolution)
    manifest.set_standards(loaded.si.get("design"))
    manifest.set_parameters(
        {
            "cli": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
            "cli_mesh_overrides": cli_overrides,
            # Parameter JSON yang di-override CSV TETAP disimpan apa adanya (PRD Bagian 5.2.1).
            "config_raw": loaded.raw,
            "config_si": loaded.si,
            "input_units": loaded.input_units,
        }
    )
    manifest.write()

    raw = mesh_engine.generate_mesh(
        geom,
        options,
        allow_tri=getattr(args, "allow_tri", False),
        export_msh=(model_dir / "model.msh") if getattr(args, "export_msh", False) else None,
        gmsh_terminal=(args.log_level == "DEBUG"),
    )
    mesh = mesh_model_mod.build_mesh_model(raw)

    return PreparedModel(
        loaded=loaded,
        sources=sources,
        geom=geom,
        options=options,
        raw=raw,
        mesh=mesh,
        cli_overrides=cli_overrides,
    )


def write_model_artifacts(
    prepared: PreparedModel,
    run_dir: Path,
    model_dir: Path,
    *,
    dpi: int,
    preview: bool = False,
) -> None:
    """Tulis isi `00_Model/`: nodes, elements, mesh_summary, mesh_plan."""
    prepared.mesh.write_nodes_csv(model_dir / "nodes.csv")
    prepared.mesh.write_elements_csv(model_dir / "elements.csv")
    reporter.write_mesh_summary(
        model_dir / "mesh_summary.md",
        geom=prepared.geom,
        mesh=prepared.mesh,
        raw=prepared.raw,
        options=prepared.options,
        project_name=prepared.project_name,
        run_dir=run_dir,
        warnings=prepared.raw.warnings,
    )
    renderer.render_mesh_plan(
        model_dir / "mesh_plan.png",
        prepared.geom,
        prepared.mesh,
        project_name=prepared.project_name,
        mesh_size_m=prepared.options.size_global,
        n_tri=prepared.raw.n_tri,
        dpi=dpi,
        preview=preview,
    )


def record_model_stats(prepared: PreparedModel, manifest: provenance.Manifest) -> None:
    """Isi blok `model_stats` manifest dari hasil meshing (PRD Bagian 10)."""
    raw, mesh, options = prepared.raw, prepared.mesh, prepared.options
    manifest.update_model_stats(
        {
            "n_nodes": mesh.n_nodes,
            "n_elements": mesh.n_elements,
            "mesh": {
                "size_mode": options.size_mode,
                "mesh_size_min_m": raw.effective_options["Mesh.MeshSizeMin"],
                "mesh_size_max_m": raw.effective_options["Mesh.MeshSizeMax"],
                "algorithm": options.algorithm,
                "recombination_algorithm": options.recombination_algorithm,
                "n_quad": raw.n_quad,
                "n_tri": raw.n_tri,
                "all_quad": raw.n_tri == 0,
                "n_surfaces_after_fragment": raw.n_surfaces,
                "area_uniformity_cv_all": mesh.area_uniformity_cv,
                "area_uniformity_cv_cap": mesh.area_uniformity_cv_cap,
                "gmsh_version": raw.gmsh_version,
            },
            "group_element_counts": mesh.group_element_counts(),
            "group_area_occ_m2": raw.surface_area_by_group,
        }
    )
    manifest.add_warnings(list(raw.warnings))


def run(args: argparse.Namespace, command: str) -> Path:
    """Jalankan seluruh rantai Fase 1. Mengembalikan folder run.

    Seluruh badan dibungkus try/except agar run yang GAGAL pun meninggalkan
    `run_manifest.json` berstatus `FAILED` beserta pesan errornya (PRD Bagian 10:
    "run yang gagal pun terlacak").
    """
    run_dir = provenance.make_run_dir(args.output_dir)
    config.setup_logging(run_dir, args.log_level)
    model_dir = run_dir / config.MODEL_SUBDIR
    model_dir.mkdir(parents=True, exist_ok=True)

    _log.info("pilecap-fem v%s | run: %s", __version__, run_dir)

    # Manifest dibuat & ditulis PALING AWAL, sebelum satu pun file input dibaca.
    manifest = provenance.Manifest(run_dir, command)
    manifest.set_parameters(
        {"cli": {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}}
    )
    manifest.write()

    try:
        return _run_inner(args, command, run_dir, model_dir, manifest)
    except Exception as exc:
        manifest.set_status("FAILED")
        manifest.update_checks({"error": f"{type(exc).__name__}: {exc}"})
        manifest.write()
        raise


def _run_inner(
    args: argparse.Namespace,
    command: str,
    run_dir: Path,
    model_dir: Path,
    manifest: provenance.Manifest,
) -> Path:
    prepared = prepare_model(args, model_dir, manifest, require_material=False)
    write_model_artifacts(prepared, run_dir, model_dir, dpi=args.dpi, preview=args.preview)

    record_model_stats(prepared, manifest)
    manifest.update_model_stats({"element_type": "quad4 (calon ShellMITC4)"})
    manifest.update_checks(
        {
            "fragment_area_match": "PASS",
            "all_quad": "PASS" if prepared.raw.n_tri == 0 else "FAIL",
            "equilibrium_VC0": "NOT_RUN (butuh pilecap-analyze)",
            "capacity_checks": "NOT_EVALUATED",
        }
    )
    manifest.set_status("OK")
    manifest.write()

    _log.info("Selesai -> %s", model_dir)
    return run_dir


def entry_point(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = "pilecap-mesh " + " ".join(argv if argv is not None else sys.argv[1:])
    try:
        if handle_init_example(args):
            return 0
        run_dir = run(args, command.strip())
    except PilecapError as exc:
        logging.getLogger("pilecap_fem").error("%s", exc)
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        if args.log_level == "DEBUG":
            raise
        return 2
    except FileNotFoundError as exc:
        print(f"\nGAGAL: {exc}", file=sys.stderr)
        return 2
    print(f"\nOK -> {run_dir}")
    return 0


__all__ = ["InputError", "build_parser", "entry_point", "run"]

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(entry_point())
