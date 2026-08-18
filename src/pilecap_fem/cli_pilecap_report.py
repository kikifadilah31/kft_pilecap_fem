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
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import numpy as np
from tqdm import tqdm

from pilecap_fem import (
    __version__,
    capacity_engine,
    config,
    geometry_builder,
    io_utils,
    math_engine,
    mesh_model,
    postproc_engine,
    provenance,
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
    parser.add_argument(
        "--contour-method",
        choices=config.CONTOUR_METHODS,
        default=config.DEFAULT_CONTOUR_METHOD,
        help=(
            "element-center: satu warna datar per elemen (jujur, bawaan). "
            "average-nodal: dihaluskan -- lebih rapi tetapi menyiratkan kehalusan yang "
            "tidak pernah dihitung, paling menyesatkan di singularitas tepi pier"
        ),
    )
    parser.add_argument(
        "--no-rebar-plots",
        action="store_true",
        help="Lewati 12 plot tulangan per kombinasi (mempercepat pelaporan)",
    )
    parser.add_argument("--no-envelope", action="store_true", help="Lewati envelope")
    parser.add_argument(
        "--pdf",
        action="store_true",
        help=(
            "Buat laporan PDF lengkap (dasar teori, input, tiap kombinasi, envelope) "
            "dengan seluruh diagram sebagai figures. Sumber Typst-nya ikut disimpan"
        ),
    )
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
    # Sengaja di sini, bukan di `add_report_arguments`: `pilecap-run` sudah mendapat
    # `--theme` dari `add_common_arguments`, dan mendaftarkannya di kedua tempat akan
    # membuat argparse menolak parser gabungannya.
    parser.add_argument(
        "--theme",
        choices=tuple(config.THEMES),
        default=config.DEFAULT_THEME,
        help="Tema warna seluruh plot (gaya shell-kit)",
    )
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

    # Dipakai menandai gambar yang berasal dari pelaporan SEBELUMNYA: `pilecap-report`
    # memang dirancang untuk dijalankan ulang, dan PNG lama tetap ada di disk.
    started_at = time.time()

    if args.wood_armer:
        # Dipanggil lebih dulu agar user tidak menunggu seluruh plot selesai hanya untuk
        # mendapati fiturnya memang belum ada.
        math_engine.wood_armer(np.zeros(1), np.zeros(1), np.zeros(1))

    if getattr(args, "pdf", False):
        # Alasan yang sama dengan `--wood-armer`: gagal SEBELUM satu plot pun digambar.
        from pilecap_fem import reporting_pdf

        reporting_pdf.preflight()
        if args.no_rebar_plots:
            _log.warning(
                "--pdf dipakai bersama --no-rebar-plots: seluruh gambar tulangan tidak "
                "dibuat, sehingga di PDF ia muncul sebagai kotak penjelasan, bukan gambar."
            )

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
    # Berlaku untuk SELURUH kombinasi sekaligus, termasuk envelope -- satu setelan, bukan
    # per kombinasi. Mencampurnya membuat envelope membandingkan besaran yang dihitung
    # dengan cara berbeda, sehingga angka governing-nya kehilangan arti.
    rebar_basis = str(design.get("rebar_basis") or config.REBAR_BASIS_DEFAULT)
    strips_x = args.strips_x or int(design.get("strips_x", 5))
    strips_y = args.strips_y or int(design.get("strips_y", 5))
    moment_at = args.moment_at or str(design.get("moment_at", "pier_face"))

    # Flag lajur yang diberikan eksplisit di CLI tetapi tidak dibaca adalah no-op senyap:
    # user menunggu hasil yang berubah, dan tidak ada apa pun yang memberitahunya bahwa
    # perintahnya tidak berpengaruh.
    if rebar_basis == "element":
        diabaikan = [
            nama
            for nama, nilai in (
                ("--strips-x", args.strips_x),
                ("--strips-y", args.strips_y),
                ("--moment-at", args.moment_at),
            )
            if nilai is not None
        ]
        if diabaikan:
            _log.warning(
                "%s DIABAIKAN: run ini memakai `design.rebar_basis` = 'element', yang "
                "mengambil angka desain langsung dari nilai tiap elemen tanpa hitungan "
                "lajur. Setel `rebar_basis` ke 'strip' di config bila yang Anda maksud "
                "sebaliknya.",
                ", ".join(diabaikan),
            )
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
    style = renderer.PlotStyle.from_args(args)
    # Dibangun sekali lalu diteruskan: identitas proyek harus sama persis di seluruh plot.
    base_block = _project_block(manifest, geom).with_assumptions(
        *_assumption_lines(capacity_inputs)
    )
    # Asumsi kapasitas MENGUBAH angka desain (mode tulangan, grid sengkang, batas
    # `As_min`, asumsi `dv`). Tanpa langkah ini semuanya hanya hidup di calc sheet dan
    # tidak pernah masuk catatan provenance run.
    provenance.record_capacity(run_dir, capacity_engine.provenance_block(capacity_inputs))
    _log.info(
        "Cek kapasitas aktif: shell-kit v%s | fy = %.0f MPa | phi = %.2f/%.2f (%s) | "
        "mode tulangan %s | tema %s",
        capacity_engine.provenance_block(capacity_inputs)["engine_version"],
        capacity_inputs.fy_mpa,
        capacity_inputs.phi_flexure,
        capacity_inputs.phi_shear,
        capacity_inputs.phi_source,
        capacity_inputs.rebar_mode,
        style.theme.name,
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
        style=style,
        block=base_block,
    )
    results_by_combo: dict[str, postproc_engine.ElementResults] = {}
    designs_by_combo: dict[str, dict[tuple[str, str], capacity_engine.FlexureDesign]] = {}
    strip_design_by_combo: dict[str, list[dict[str, Any]]] = {}
    # Masukan calc sheet per kombinasi, disimpan agar laporan PDF memakai angka yang SAMA
    # PERSIS -- bukan menghitung ulang, bukan membaca balik CSV yang sudah dibulatkan.
    calc_inputs_by_combo: dict[str, reporter.CalcSheetInputs] = {}
    combo_rows: list[dict[str, Any]] = []
    checks: dict[str, Any] = {
        k: v for k, v in (manifest.get("checks") or {}).items() if k != "error"
    }

    for combo, combo_dir in tqdm(combo_dirs.items(), desc="Laporan", unit="combo"):
        results_by_combo[combo], calc_inputs_by_combo[combo] = _report_one_combo(
            combo=combo,
            combo_dir=combo_dir,
            run_dir=run_dir,
            geom=geom,
            mesh=mesh,
            manifest=manifest,
            cfg=cfg,
            rebar_basis=rebar_basis,
            strips_x=strips_x,
            strips_y=strips_y,
            moment_at=moment_at,
            cover_m=cover_m,
            mesh_size=mesh_size,
            deep_ratio=deep_ratio,
            command=command,
            style=style,
            no_rebar_plots=args.no_rebar_plots,
            combo_rows=combo_rows,
            capacity_inputs=capacity_inputs,
            designs_by_combo=designs_by_combo,
            strip_design_by_combo=strip_design_by_combo,
            base_block=base_block,
        )

    envelope = None
    if not args.no_envelope and len(results_by_combo) >= 1:
        envelope = _write_envelope(
            run_dir,
            geom,
            mesh,
            results_by_combo,
            designs_by_combo,
            strip_design_by_combo,
            capacity_inputs=capacity_inputs,
            rebar_basis=rebar_basis,
            no_rebar_plots=args.no_rebar_plots,
            style=style,
            block=base_block,
        )

    semua_warning = warnings + list(manifest.get("warnings") or [])
    rebar_governing = (
        capacity_engine.governing_strip_design(strip_design_by_combo)
        if rebar_basis == "strip"
        else capacity_engine.governing_element_design(designs_by_combo, mesh)
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
        warnings=semua_warning,
        envelope=envelope,
        rebar_basis=rebar_basis,
        rebar_governing=rebar_governing,
        capacity_inputs=capacity_inputs,
    )

    if getattr(args, "pdf", False):
        # Impor tertunda: `reporting_pdf` menarik PIL, dan disiplin impor modul ini
        # dijaga `test_pilecap_report_tidak_menarik_solver`.
        from pilecap_fem import reporting_pdf

        pdf_path = reporting_pdf.build_pdf_report(
            run_dir,
            reporting_pdf.ReportData(
                run_dir=run_dir,
                run_name=run_dir.name,
                command=command,
                manifest=manifest,
                cfg=cfg,
                geom=geom,
                mesh=mesh,
                block=base_block,
                capacity_inputs=capacity_inputs,
                deep_ratio=deep_ratio,
                rebar_basis=rebar_basis,
                mesh_size_m=mesh_size,
                calc_inputs_by_combo=calc_inputs_by_combo,
                designs_by_combo=designs_by_combo,
                strip_design_by_combo=strip_design_by_combo,
                combo_rows=combo_rows,
                checks=checks,
                warnings=semua_warning,
                envelope=envelope,
                no_rebar_plots=args.no_rebar_plots,
                no_envelope=args.no_envelope,
                started_at=started_at,
                rebar_governing=rebar_governing,
            ),
        )
        _log.info("Laporan PDF: %s", pdf_path)

    _log.info("Laporan selesai: %d kombinasi -> %s", len(combo_dirs), run_dir)
    return run_dir


def _project_block(manifest: dict[str, Any], geom: GeometryModel) -> renderer.TitleBlock:
    """Identitas proyek untuk kop gambar, dibaca dari config yang terekam manifest.

    `engineer` dan `date` sudah lama diminta formulir dan tersimpan di config, tetapi
    sebelum v0.8.0 tidak pernah sampai ke satu plot pun -- hanya ke calc sheet.

    Peringatan tumpang tindih DIBANGUN ULANG dari `geom.overlaps`, bukan diendus dari
    daftar warning manifest: yang dicari adalah data, dan mencocokkan string warning akan
    diam-diam berhenti bekerja begitu kalimatnya diubah sedikit.
    """
    parameters = (manifest.get("parameters") or {}).get("config_raw") or {}
    project = parameters.get("project") or {}
    limit = (parameters.get("pier") or {}).get("max_pile_overlap_fraction") or 0.0
    return renderer.TitleBlock(
        project=str(project.get("name", "") or ""),
        engineer=str(project.get("engineer", "") or ""),
        date=str(project.get("date", "") or ""),
    ).with_warnings(*geometry_builder.overlap_warning_lines(geom, float(limit)))


#: Label baku untuk `design.rebar_mode` pada kop gambar -- nilai config aslinya adalah
#: kode `snake_case` (`validators.REBAR_MODES`), bukan kalimat yang layak dicetak apa
#: adanya pada dokumen teknik.
_REBAR_MODE_LABELS: Final[dict[str, str]] = {
    "spacing_fixed": "spasi tetap",
    "diameter_fixed": "diameter tetap",
}


def _assumption_lines(inputs: capacity_engine.CapacityInputs) -> tuple[str, ...]:
    """Asumsi desain untuk kop gambar, dipecah jadi baris pendek.

    Menggantikan satu baris 130 karakter yang dulu menempel di bawah judul. `phi` ikut
    dibawa sekarang: ia mengubah SETIAP angka tulangan pada gambar, tetapi sebelumnya
    tidak pernah tampil di plot mana pun.

    Sumber phi dan fy masing-masing baris tersendiri berlabel "Sumber ..." -- bukan
    ditempel sebagai tanda kurung di belakang angkanya. Digabung sebagai tanda kurung,
    `phi_source` yang sudah memuat tanda kurungnya sendiri (mis. "shell-kit v3.3.0
    (SNI 2847:2019)") berakhir bersarang dua kali, yang terbaca berantakan di kop cetak.
    """
    mode_label = _REBAR_MODE_LABELS.get(inputs.rebar_mode, inputs.rebar_mode)
    lines = [
        f"f'c {inputs.fc_mpa:,.0f} MPa · fy {inputs.fy_mpa:,.0f} MPa",
        f"Tebal {inputs.thickness_mm:,.0f} mm · selimut {inputs.cover_mm:,.0f} mm · "
        f"mode tulangan {mode_label}",
        f"φ lentur {inputs.phi_flexure:,.2f} · φ geser {inputs.phi_shear:,.2f}",
    ]
    if inputs.phi_source:
        lines.append(f"Sumber φ: {inputs.phi_source}")
    if inputs.fy_source:
        lines.append(f"Sumber fy: {inputs.fy_source}")
    return tuple(lines)


def _render_rebar_plots(
    combo_dir: Path,
    geom: GeometryModel,
    mesh: mesh_model.MeshModel,
    *,
    designs: dict[tuple[str, str], capacity_engine.FlexureDesign],
    selections: dict[tuple[str, str], capacity_engine.RebarSelection],
    shear_maps: dict[str, capacity_engine.ShearRebarMap],
    combo: str,
    pz_by_pile: dict[str, float],
    style: renderer.PlotStyle,
    block: renderer.TitleBlock,
    rebar_basis: str = "strip",
    rename: Callable[[str], str] | None = None,
    title_prefix: str = "",
) -> None:
    """Dua belas plot tulangan per kombinasi: 4 As + 4 seleksi + 4 geser.

    Caption plot LENTUR mengikuti `rebar_basis`, dan itu bukan kehalusan: gambar inilah
    yang dicetak dan ditempel ke laporan. Pada mode `strip` peta ini alat baca, sedangkan
    pada mode `element` ia justru sumber angka desainnya -- caption yang salah satu arah
    akan beredar sebagai pernyataan yang keliru pada setiap lembar.

    Caption plot GESER tidak bergantung mode, karena `rebar_basis` memang tidak menyentuh
    jalur geser: `Av/s` per elemen selalu dihitung dengan fungsi desain `shell-kit` yang
    sama, dan cek penampang kritis pada `d` dari muka pier selalu ikut dilaporkan. Uraian
    hubungan keduanya ada di calc sheet bagian 7b.
    """
    peringatan = (
        (
            "Peta ini merupakan sumber angka desain (parameter design.rebar_basis = "
            "element). Nilai puncak di tepi zona jepit pier bersifat singular secara "
            "numerik dan bergantung pada kehalusan mesh."
        )
        if rebar_basis == "element"
        else (
            "Peta ini bersifat peta orientasi. Angka desain resmi diambil dari lajur "
            "pada muka pier, bukan dari nilai puncak tiap elemen."
        )
    )

    # Nama berkas diganti lewat `rename` agar fungsi ini dapat dipakai ulang apa adanya
    # untuk envelope (`contour_*` -> `envelope_*`), memakai pola penggantian yang sama
    # dengan plot envelope gaya. Tanpa itu, envelope butuh salinan seluruh blok ini.
    nama = rename or (lambda n: n)
    # Judul WAJIB menyebut "Envelope" pada plot envelope. Kop memang sudah menyatakannya,
    # tetapi judullah yang dibaca pertama pada gambar yang dicetak dan ditempel ke
    # laporan -- plot gaya sudah melakukannya, dan plot tulangan tidak boleh berbeda.
    judul_plot = (lambda t: f"{title_prefix}{t}") if title_prefix else (lambda t: t)

    for (direction, face), (filename, title) in config.REBAR_FACES.items():
        design = designs[(direction, face)]
        renderer.render_contour(
            combo_dir / nama(filename),
            geom,
            mesh,
            capacity_engine.as_design_array(design),
            quantity="steel_area",
            title=judul_plot(title),
            # `As` tidak bertanda: skala diverging yang dipusatkan di nol akan membuang
            # separuh rentang warna untuk nilai yang tidak pernah muncul.
            diverging=False,
            combo=combo,
            pz_by_pile=pz_by_pile,
            style=style,
            block=block.with_notes(peringatan),
            n_inadequate=design.n_inadequate,
        )

        selection = selections[(direction, face)]
        stem = filename.replace("contour_As_", f"contour_{selection.kind}_")
        judul = f"{selection.kind.capitalize()} tulangan arah {direction.upper()} — muka {face}"
        if selection.is_categorical:
            renderer.render_categorical(
                combo_dir / nama(stem),
                geom,
                mesh,
                _category_index(selection),
                labels=selection.labels,
                title=judul_plot(judul),
                combo=combo,
                pz_by_pile=pz_by_pile,
                style=style,
                block=block.with_notes(peringatan),
            )
        else:
            renderer.render_contour(
                combo_dir / nama(stem),
                geom,
                mesh,
                selection.values,
                quantity=selection.quantity,
                title=judul_plot(judul),
                diverging=False,
                combo=combo,
                pz_by_pile=pz_by_pile,
                style=style,
                block=block.with_notes(peringatan),
                n_inadequate=selection.n_inadequate,
            )

    for direction, (_, avs_file, dia_file, label) in config.SHEAR_REBAR_FIELDS.items():
        smap = shear_maps[direction]
        catatan = (
            f"{smap.n_needs_stirrup:,} elemen dengan V_u > φV_c (memerlukan sengkang); "
            f"{smap.n_av_min_only:,} elemen hanya terkena Av,min."
        )
        renderer.render_contour(
            combo_dir / nama(avs_file),
            geom,
            mesh,
            smap.av_per_s,
            quantity="shear_steel_ratio",
            title=judul_plot(f"Av/s sengkang {label}"),
            diverging=False,
            combo=combo,
            pz_by_pile=pz_by_pile,
            style=style,
            block=block.with_notes(catatan),
            n_inadequate=smap.n_web_crushed,
        )
        # Diameter sengkang adalah pilihan DISKRET dari daftar yang diizinkan -- sama
        # sifatnya dengan diameter tulangan lentur, jadi digambar kategorikal. Sebelumnya
        # ia lewat `render_contour` sehingga enam nilai diskret mendarat di enam titik
        # sembarang pada gradasi `YlOrRd` yang kontinu, dengan colorbar berlabel angka
        # interpolasi alih-alih D10..D25.
        renderer.render_categorical(
            combo_dir / nama(dia_file),
            geom,
            mesh,
            _diameter_index(smap.stirrup_diameter, smap.labels),
            labels=smap.labels,
            title=judul_plot(f"Diameter sengkang {label}"),
            combo=combo,
            pz_by_pile=pz_by_pile,
            style=style,
            # Diameter sengkang sering nyaris seragam karena luas per kaki mudah
            # terpenuhi pada grid yang lebar; Av/s yang membawa informasinya.
            block=block.with_notes(catatan, "Baca bersama dengan plot Av/s."),
            n_inadequate=smap.n_web_crushed,
            zero_label="tanpa sengkang",
        )


def _diameter_index(values_si: np.ndarray, labels: tuple[str, ...]) -> np.ndarray:
    """Petakan diameter [m] ke indeks kategori 1..len(labels); 0 = tidak perlu, NaN tetap.

    Dibandingkan dalam mm yang dibulatkan, bukan dalam meter: nilai yang datang dari
    `shell-kit` adalah anggota persis daftar diameter, dan pembandingan float setelah
    pulang-pergi konversi satuan hanya aman pada skala mm.
    """
    diameters_mm = np.round(np.asarray(values_si, dtype=np.float64) * 1e3, 3)
    index = np.zeros(diameters_mm.shape, dtype=np.float64)
    for position, label in enumerate(labels, start=1):
        index[diameters_mm == float(label.lstrip("D"))] = position
    index[~np.isfinite(diameters_mm)] = np.nan
    return index


def _category_index(selection: capacity_engine.RebarSelection) -> np.ndarray:
    """Indeks kategori untuk hasil seleksi tulangan lentur.

    Mode konfigurasi sudah memberi indeks 1-basis; mode diameter memberi diameter dalam
    meter sehingga dipetakan lewat `_diameter_index`.
    """
    if selection.kind == capacity_engine.SELECTION_CONFIG:
        return np.asarray(selection.values, dtype=np.float64)
    return _diameter_index(selection.values, selection.labels)


def _report_one_combo(
    *,
    combo: str,
    combo_dir: Path,
    run_dir: Path,
    geom: GeometryModel,
    mesh: mesh_model.MeshModel,
    manifest: dict[str, Any],
    cfg: dict[str, Any],
    rebar_basis: str,
    strips_x: int,
    strips_y: int,
    moment_at: str,
    cover_m: float,
    mesh_size: float,
    deep_ratio: dict[str, Any],
    command: str,
    style: renderer.PlotStyle,
    no_rebar_plots: bool,
    combo_rows: list[dict[str, Any]],
    capacity_inputs: capacity_engine.CapacityInputs,
    designs_by_combo: dict[str, dict[tuple[str, str], capacity_engine.FlexureDesign]],
    strip_design_by_combo: dict[str, list[dict[str, Any]]],
    base_block: renderer.TitleBlock,
) -> tuple[postproc_engine.ElementResults, reporter.CalcSheetInputs]:
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
            style=style,
            block=base_block,
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
            style=style,
            block=base_block,
        )

    # --- momen lajur & geser ------------------------------------------------
    #
    # Pada `rebar_basis = "element"` seluruh jalur lajur DILEWATI, bukan sekadar tabelnya
    # disembunyikan: itulah arti "murni nilai elemen". `strip_moments_*.csv` pun tidak
    # ditulis, supaya tidak ada berkas yang tampak seperti angka desain padahal bukan.
    strip_rows: list[dict[str, Any]] = []
    if rebar_basis == "strip":
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
    strip_design = (
        capacity_engine.strip_flexure_design(strip_rows, capacity_inputs) if strip_rows else []
    )
    strip_design_by_combo[combo] = strip_design
    shear_capacities = capacity_engine.one_way_shear_from_checks(shear_checks, capacity_inputs)

    selections = {
        key: capacity_engine.select_flexure_bars(design, capacity_inputs)
        for key, design in designs.items()
    }
    shear_maps = {
        direction: capacity_engine.shear_rebar_map(
            getattr(results, field), capacity_inputs, direction=direction
        )
        for direction, (field, _, _, _) in config.SHEAR_REBAR_FIELDS.items()
    }

    reporter.write_rebar_design_csv(
        combo_dir / config.FILE_REBAR_DESIGN, designs, mesh, selections=selections
    )
    reporter.write_shear_rebar_csv(combo_dir / config.FILE_SHEAR_REBAR, shear_maps, mesh)

    if not no_rebar_plots:
        _render_rebar_plots(
            combo_dir,
            geom,
            mesh,
            designs=designs,
            selections=selections,
            shear_maps=shear_maps,
            combo=combo,
            pz_by_pile=pz_by_pile,
            style=style,
            block=base_block,
            rebar_basis=rebar_basis,
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
    calc_inputs = reporter.CalcSheetInputs(
        combo=combo,
        combo_dir=combo_dir,
        results=results,
        equilibrium=equilibrium,
        pz_by_pile=pz_by_pile,
        material=material,
        strip_rows=strip_rows,
        strip_design=strip_design,
        shear_checks=shear_checks,
        designs=designs,
        selections=selections,
        shear_maps=shear_maps,
        shear_capacities=shear_capacities,
        trace=trace,
    )
    reporter.write_calc_sheet(
        combo_dir / config.FILE_CALC_SHEET,
        inputs=calc_inputs,
        geom=geom,
        mesh=mesh,
        capacity_inputs=capacity_inputs,
        deep_ratio=deep_ratio,
        project_name=str(
            ((manifest.get("parameters") or {}).get("config_raw") or {})
            .get("project", {})
            .get("name", "")
        ),
        run_name=run_dir.name,
        command=command,
        dependencies=manifest.get("dependencies") or {},
        rebar_basis=rebar_basis,
        mesh_size_m=mesh_size,
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
    return results, calc_inputs


def _write_envelope(
    run_dir: Path,
    geom: GeometryModel,
    mesh: mesh_model.MeshModel,
    results_by_combo: dict[str, postproc_engine.ElementResults],
    designs_by_combo: dict[str, dict[tuple[str, str], capacity_engine.FlexureDesign]],
    strip_design_by_combo: dict[str, list[dict[str, Any]]],
    *,
    capacity_inputs: capacity_engine.CapacityInputs,
    rebar_basis: str,
    no_rebar_plots: bool,
    style: renderer.PlotStyle,
    block: renderer.TitleBlock,
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
                title=f"Envelope {which} — {title}",
                # `combo` sengaja kosong: mengisinya "seluruh kombinasi" membuat baris
                # kedua berbunyi "Kombinasi seluruh kombinasi". Keterangannya sudah ada
                # sebagai catatan di kop.
                style=style,
                # Sebelum v0.8.0 plot envelope sama sekali tidak membawa konteks, padahal
                # justru inilah yang paling sering dicetak dan ditempel ke laporan.
                block=block.with_notes(
                    "Nilai merupakan envelope (nilai ekstrem) dari seluruh kombinasi. "
                    "Kombinasi penentu tiap elemen tercantum pada envelope_values.csv."
                ),
            )
            plots.append(name)

    if not no_rebar_plots:
        plots += _render_envelope_rebar_plots(
            envelope_dir,
            geom,
            mesh,
            envelope=envelope,
            capacity_inputs=capacity_inputs,
            style=style,
            block=block,
            rebar_basis=rebar_basis,
        )

    reporter.write_rebar_envelope_csv(
        envelope_dir / config.FILE_REBAR_ENVELOPE, designs_by_combo, mesh
    )
    if rebar_basis == "strip" and strip_design_by_combo:
        reporter.write_strip_envelope_csv(
            envelope_dir / config.FILE_STRIP_ENVELOPE,
            capacity_engine.envelope_strip_design(strip_design_by_combo),
        )
    reporter.write_envelope_csv(envelope_dir / "envelope_values.csv", envelope, mesh)
    reporter.write_envelope_summary(
        envelope_dir / "envelope_summary.md", envelope, mesh, plots=plots
    )
    return envelope


def _render_envelope_rebar_plots(
    envelope_dir: Path,
    geom: GeometryModel,
    mesh: mesh_model.MeshModel,
    *,
    envelope: postproc_engine.Envelope,
    capacity_inputs: capacity_engine.CapacityInputs,
    style: renderer.PlotStyle,
    block: renderer.TitleBlock,
    rebar_basis: str,
) -> list[str]:
    """Dua belas plot tulangan envelope: 4 `As` + 4 batang + 2 `Av/s` + 2 sengkang.

    Dibangun dari envelope GAYA, lalu didesain sekali -- bukan dari maksimum `As` antar
    kombinasi. Alasannya ada di `Envelope.face_moment`.

    Memakai ulang `_render_rebar_plots` apa adanya lewat `rename`; menyalin blok plotnya
    akan melahirkan dua jalur gambar yang dapat menyimpang diam-diam.
    """
    designs = {
        (direction, face): capacity_engine.flexure_design(
            envelope.face_moment(direction, face),
            capacity_inputs,
            direction=direction,
            face=face,
        )
        for direction, face in config.REBAR_FACES
    }
    selections = {
        key: capacity_engine.select_flexure_bars(design, capacity_inputs)
        for key, design in designs.items()
    }
    shear_maps = {
        direction: capacity_engine.shear_rebar_map(
            envelope.abs_shear(direction), capacity_inputs, direction=direction
        )
        for direction in config.SHEAR_REBAR_FIELDS
    }

    _render_rebar_plots(
        envelope_dir,
        geom,
        mesh,
        designs=designs,
        selections=selections,
        shear_maps=shear_maps,
        # Kosong: baris kedua judul akan berbunyi "Kombinasi ENVELOPE", padahal envelope
        # justru BUKAN satu kombinasi. Keterangannya masuk sebagai catatan di kop.
        combo="",
        pz_by_pile={},
        style=style,
        block=block.with_notes(
            "Envelope atas seluruh kombinasi, bukan kondisi keseimbangan tunggal — tiap "
            "elemen dapat berasal dari kombinasi yang berbeda."
        ),
        rebar_basis=rebar_basis,
        rename=lambda name: name.replace("contour_", "envelope_"),
        title_prefix="Envelope — ",
    )

    nama_plot = [
        n.replace("contour_", "envelope_")
        for n in (
            [f for f, _ in config.REBAR_FACES.values()]
            + [
                f.replace("contour_As_", f"contour_{s.kind}_")
                for f, s in zip(
                    (f for f, _ in config.REBAR_FACES.values()), selections.values(), strict=True
                )
            ]
            + [avs for _, avs, _, _ in config.SHEAR_REBAR_FIELDS.values()]
            + [dia for _, _, dia, _ in config.SHEAR_REBAR_FIELDS.values()]
        )
    ]
    return nama_plot


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
