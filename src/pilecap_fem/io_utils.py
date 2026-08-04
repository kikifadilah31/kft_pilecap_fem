"""I/O, konversi satuan, dan resolusi sumber geometri (PRD Core 2 & 10).

**Modul ini adalah SATU-SATUNYA titik konversi satuan di seluruh tool** (PRD Bagian 4.1).
Setiap nilai yang keluar dari sini sudah dalam SI: panjang m, gaya N, tegangan Pa.
Tabel faktor konversinya sendiri hidup di `config.py`, bukan di sini.

Modul ini juga memegang aturan resolusi sumber geometri PRD Bagian 5.2.1 -- termasuk
kewajiban meneriakkan setiap override secara eksplisit. Override yang senyap adalah
bahaya nyata pada tingkat liabilitas PRD Bagian 1.3.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pilecap_fem import config, validators
from pilecap_fem.geometry_builder import (
    EntityResolution,
    GeometryResolution,
    GeometrySource,
    Pile,
    Polygon2D,
    ResolvedGeometrySources,
    drop_repeated_closing_vertex,
    normalize_ccw,
)
from pilecap_fem.validators import InputError

_log = config.get_logger("io_utils")

# Field config yang dikonversi. Tabel ini menjabarkan PRD Bagian 4.2 secara eksplisit
# agar tidak ada field yang "kelupaan dikonversi" secara diam-diam.
_LENGTH_SCALARS: tuple[tuple[str, str], ...] = (
    ("pilecap", "length_x"),
    ("pilecap", "length_y"),
    ("pilecap", "thickness"),
    ("pile", "diameter"),
    ("pile", "spacing_x"),
    ("pile", "spacing_y"),
    ("pier", "width_x"),
    ("pier", "width_y"),
    ("pier", "diameter"),
    ("mesh", "size_global"),
    ("mesh", "size_local_pile"),
    ("mesh", "size_local_pier"),
    ("design", "cover"),
)
_LENGTH_PAIRS: tuple[tuple[str, str], ...] = (
    ("pilecap", "origin"),
    ("pile", "grid_origin"),
    ("pier", "centerline"),
)
_STRESS_SCALARS: tuple[tuple[str, str], ...] = (
    ("material", "fc"),
    ("material", "E"),
)
# Berat jenis: PRD Bagian 4.2 menetapkan satuannya kN/m^3 -- gaya per meter kubik,
# BUKAN per satuan panjang input pangkat tiga. Jadi hanya faktor gaya yang berlaku.
_FORCE_PER_CUBIC_METRE_SCALARS: tuple[tuple[str, str], ...] = (("material", "density"),)


# ---------------------------------------------------------------------------
# Utilitas dasar
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    """Hash isi file untuk run_manifest.json (PRD Core 5)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def short_hash(sha: str | None, length: int = 8) -> str:
    return "-" if sha is None else f"{sha[:length]}..."


def display_unit(quantity: str) -> str:
    """Label satuan tampilan untuk suatu besaran (PRD Bagian 4.3)."""
    try:
        return config.DISPLAY_UNITS[quantity][0]
    except KeyError as exc:
        raise KeyError(
            f"Besaran {quantity!r} tidak ada di config.DISPLAY_UNITS. "
            f"Tersedia: {sorted(config.DISPLAY_UNITS)}"
        ) from exc


def to_display(value: float | np.ndarray, quantity: str) -> Any:
    """Konversi nilai SI ke satuan tampilan (PRD Bagian 4.3).

    HANYA boleh dipanggil dari `renderer.py` dan `reporter.py`. Modul perhitungan
    (`math_engine`, `fem_engine`, `postproc_engine`, `mesh_engine`) bekerja murni SI.
    """
    _, factor = config.DISPLAY_UNITS[quantity]
    return value * factor


# ---------------------------------------------------------------------------
# Auto-detection (PRD Bagian 5.2, Core 10)
# ---------------------------------------------------------------------------


def autodetect(input_dir: Path, key: str, *, required: bool = False) -> Path | None:
    """Cari satu file yang cocok `config.FILE_PATTERNS[key]` di `input_dir`.

    * >1 file cocok -> RAISE dengan daftar file (jangan pernah ambil yang pertama).
    * File wajib tidak ditemukan -> RAISE + tampilkan isi folder.
    * File opsional tidak ditemukan -> INFO log, kembalikan `None`.
    """
    pattern = config.FILE_PATTERNS[key]
    if not input_dir.is_dir():
        raise InputError(f"Folder input tidak ditemukan: {input_dir}")

    matches = sorted(p for p in input_dir.glob(pattern) if p.is_file())
    if len(matches) > 1:
        listing = "\n".join(f"    {p.name}" for p in matches)
        raise InputError(
            f"Lebih dari satu file cocok pola {pattern!r} untuk {key!r} di {input_dir}:\n"
            f"{listing}\n"
            "  Tool berhenti agar tidak memilih file yang salah secara diam-diam. "
            "Sisakan satu file, atau tunjuk file secara eksplisit lewat flag CLI "
            "(PRD Bagian 5.2)."
        )
    if not matches:
        if required:
            contents = sorted(p.name for p in input_dir.iterdir())
            listing = "\n".join(f"    {name}" for name in contents) or "    (folder kosong)"
            raise InputError(
                f"File wajib {key!r} (pola {pattern!r}) tidak ditemukan di {input_dir}.\n"
                f"  Isi folder:\n{listing}"
            )
        _log.info("Tidak ada file opsional %r (pola %s) di %s", key, pattern, input_dir)
        return None

    _log.debug("Auto-detect %s: %s", key, matches[0])
    return matches[0]


# ---------------------------------------------------------------------------
# Config JSON
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LoadedConfig:
    """Config setelah konversi ke SI, beserta bentuk mentahnya untuk audit.

    `raw` disimpan apa adanya agar `run_manifest.json` dan pesan override dapat
    menampilkan nilai persis seperti yang ditulis user di file (PRD Bagian 5.2.1:
    "Parameter JSON yang di-override TETAP DISIMPAN apa adanya di manifest").
    """

    si: dict[str, Any]
    raw: dict[str, Any]
    path: Path
    sha256: str
    input_units: dict[str, str]


def _unit_factor(units: dict[str, str], kind: str) -> float:
    table = {
        "length": config.LENGTH_TO_SI,
        "force": config.FORCE_TO_SI,
        "stress": config.STRESS_TO_SI,
    }[kind]
    unit = units[kind]
    if unit not in table:
        raise InputError(
            f"Satuan {kind} = {unit!r} tidak dikenal. Pilihan: {sorted(table)} "
            "(blok `units` di file config)."
        )
    return table[unit]


def _scale(block: dict[str, Any] | None, key: str, factor: float) -> None:
    if block is None or block.get(key) is None:
        return
    value = block[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"Nilai {key!r} = {value!r} harus berupa angka.")
    block[key] = float(value) * factor


def _scale_pair(block: dict[str, Any] | None, key: str, factor: float) -> None:
    if block is None or block.get(key) is None:
        return
    value = block[key]
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise InputError(f"Nilai {key!r} = {value!r} harus berupa [x, y].")
    block[key] = [float(value[0]) * factor, float(value[1]) * factor]


def load_config(path: Path) -> LoadedConfig:
    """Baca config JSON dan konversikan seluruh besaran berdimensi ke SI.

    Satu-satunya titik konversi satuan (PRD Bagian 4.2). Tidak memvalidasi rentang
    fisik -- itu tugas `validators.py`.
    """
    if not path.is_file():
        raise InputError(f"File config tidak ditemukan: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
        raw = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise InputError(f"File config {path} bukan JSON yang sah: {exc}") from exc
    if not isinstance(raw, dict):
        raise InputError(f"File config {path} harus berisi objek JSON di level teratas.")

    units = dict(config.DEFAULT_INPUT_UNITS)
    units.update(raw.get("units") or {})
    unknown = set(units) - set(config.DEFAULT_INPUT_UNITS)
    if unknown:
        raise InputError(
            f"Blok `units` di {path} memuat kunci yang tidak dikenal: {sorted(unknown)}. "
            f"Kunci yang sah: {sorted(config.DEFAULT_INPUT_UNITS)}"
        )

    f_length = _unit_factor(units, "length")
    f_force = _unit_factor(units, "force")
    f_stress = _unit_factor(units, "stress")

    si = json.loads(raw_text)  # salinan dalam, tidak berbagi objek dengan `raw`
    for block, key in _LENGTH_SCALARS:
        _scale(si.get(block), key, f_length)
    for block, key in _LENGTH_PAIRS:
        _scale_pair(si.get(block), key, f_length)
    for block, key in _STRESS_SCALARS:
        _scale(si.get(block), key, f_stress)
    for block, key in _FORCE_PER_CUBIC_METRE_SCALARS:
        _scale(si.get(block), key, f_force)

    sha = sha256_file(path)
    _log.info("Config: %s (sha256 %s)", path, short_hash(sha))
    _log.debug(
        "Satuan input: length=%s force=%s stress=%s -> SI",
        units["length"],
        units["force"],
        units["stress"],
    )
    return LoadedConfig(si=si, raw=raw, path=path, sha256=sha, input_units=units)


# ---------------------------------------------------------------------------
# CSV geometri
# ---------------------------------------------------------------------------


def _read_csv(path: Path, required: tuple[str, ...]) -> pd.DataFrame:
    if not path.is_file():
        raise InputError(f"File CSV tidak ditemukan atau tidak terbaca: {path}")
    try:
        frame = pd.read_csv(path)
    except pd.errors.EmptyDataError as exc:
        raise InputError(f"File CSV kosong: {path}") from exc
    except Exception as exc:  # pragma: no cover - pandas melempar banyak tipe
        raise InputError(f"Gagal membaca CSV {path}: {exc}") from exc
    frame.columns = [str(c).strip() for c in frame.columns]
    validators.check_required_columns(frame, required, path)
    return frame


def _polygon_from_frame(
    frame: pd.DataFrame, path: Path, length_factor: float, *, context: str = ""
) -> Polygon2D:
    """Bangun Polygon2D dari kolom `vertex_id`, `x`, `y` sesuai PRD Bagian 5.1(d)."""
    validators.check_numeric_no_nan(frame, ("vertex_id", "x", "y"), path)

    # Urutan baris file TIDAK menentukan; yang menentukan adalah vertex_id.
    ordered = frame.sort_values("vertex_id", kind="stable")
    vertices = ordered[["x", "y"]].to_numpy(dtype=np.float64) * length_factor

    trimmed = drop_repeated_closing_vertex(vertices)
    if len(trimmed) != len(vertices):
        _log.info(
            "%s%s: baris penutup yang mengulang titik pertama dibuang otomatis.",
            path.name,
            f" [{context}]" if context else "",
        )
        vertex_ids = ordered["vertex_id"].to_numpy()[: len(trimmed)]
    else:
        vertex_ids = ordered["vertex_id"].to_numpy()

    validators.check_polygon_vertex_ids(vertex_ids, path, context=context)
    validators.check_polygon_no_folded_duplicates(trimmed, path, context=context)

    polygon = Polygon2D(normalize_ccw(trimmed))
    validators.check_polygon_area(polygon.area, path, context=context)
    return polygon


def load_pilecap_polygon(path: Path, length_factor: float) -> Polygon2D:
    frame = _read_csv(path, ("vertex_id", "x", "y"))
    return _polygon_from_frame(frame, path, length_factor)


def load_pier_polygons(path: Path, length_factor: float) -> tuple[tuple[str, Polygon2D], ...]:
    """Satu atau beberapa polygon pier, dipisah kolom opsional `pier_id`.

    Tanpa kolom `pier_id`, seluruh baris dianggap satu pier ber-id ``PIER1``
    (PRD Bagian 5.1(e)).
    """
    frame = _read_csv(path, ("vertex_id", "x", "y"))
    if "pier_id" not in frame.columns:
        return (("PIER1", _polygon_from_frame(frame, path, length_factor)),)

    if frame["pier_id"].isna().any():
        raise InputError(f"Kolom `pier_id` di {path} mengandung nilai kosong.")

    result: list[tuple[str, Polygon2D]] = []
    for pier_id in frame["pier_id"].astype(str).unique():
        subset = frame[frame["pier_id"].astype(str) == pier_id]
        result.append(
            (
                pier_id,
                _polygon_from_frame(subset, path, length_factor, context=f"pier_id={pier_id}"),
            )
        )
    _log.info("%s: %d pier terbaca (%s)", path.name, len(result), ", ".join(p for p, _ in result))
    return tuple(result)


def load_pile_coords(path: Path, length_factor: float, default_diameter: float) -> tuple[Pile, ...]:
    """Koordinat pile custom. Kolom `diameter` opsional meng-override diameter global."""
    frame = _read_csv(path, ("pile_id", "x", "y"))
    validators.check_numeric_no_nan(frame, ("x", "y"), path)

    ids = frame["pile_id"].astype(str).tolist()
    duplicates = sorted({pid for pid in ids if ids.count(pid) > 1})
    if duplicates:
        raise InputError(f"`pile_id` duplikat di {path}: {duplicates}. Setiap pile harus unik.")

    has_diameter = "diameter" in frame.columns
    if has_diameter:
        validators.check_numeric_no_nan(frame, ("diameter",), path)

    piles: list[Pile] = []
    for _, row in frame.iterrows():
        diameter = (
            float(row["diameter"]) * length_factor if has_diameter else float(default_diameter)
        )
        piles.append(
            Pile(
                pile_id=str(row["pile_id"]),
                x=float(row["x"]) * length_factor,
                y=float(row["y"]) * length_factor,
                diameter=diameter,
            )
        )
    return tuple(piles)


# ---------------------------------------------------------------------------
# Reaksi pile (PRD Bagian 5.1(b))
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReactionTable:
    """Reaksi pile per kombinasi, sudah dalam SI (N).

    `combos` mempertahankan urutan kemunculan di file agar laporan dapat direproduksi
    persis. `values[combo][pile_id]` adalah `Pz` dalam newton, positif = tekan pada pile
    = gaya ke ATAS pada pilecap (PRD Bagian 7.1).
    """

    combos: tuple[str, ...]
    values: dict[str, dict[str, float]]
    path: Path
    sha256: str
    lateral_nonzero: tuple[str, ...] = ()

    def pile_ids(self) -> tuple[str, ...]:
        """Gabungan seluruh pile_id yang muncul, terurut."""
        ids: set[str] = set()
        for row in self.values.values():
            ids.update(row)
        return tuple(sorted(ids))

    def total_pz(self, combo: str) -> float:
        return float(sum(self.values[combo].values()))


def load_reactions(path: Path, force_factor: float) -> ReactionTable:
    """Baca `pile_reactions.csv` dan konversikan `Pz` ke newton.

    `Hx` / `Hy` dibaca hanya untuk dilaporkan: v1.0 MENGABAIKAN gaya lateral pile
    (PRD Bagian 5.1(b) & keterbatasan Bagian 8.3 poin 4). Nilai tak-nol dicatat agar
    muncul sebagai WARNING, bukan hilang diam-diam.
    """
    frame = _read_csv(path, ("combo", "pile_id", "Pz"))
    validators.check_numeric_no_nan(frame, ("Pz",), path)

    lateral_nonzero: list[str] = []
    for column in ("Hx", "Hy"):
        if column in frame.columns:
            lateral = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
            if bool((lateral.abs() > 0.0).any()):
                lateral_nonzero.append(column)

    combos: list[str] = []
    values: dict[str, dict[str, float]] = {}
    for combo, pile_id, pz in zip(
        frame["combo"].astype(str),
        frame["pile_id"].astype(str),
        frame["Pz"].astype(float),
        strict=True,
    ):
        if combo not in values:
            values[combo] = {}
            combos.append(combo)
        # Rule 2 -- pile_id duplikat dalam satu combo.
        if pile_id in values[combo]:
            raise InputError(
                f"`pile_id` {pile_id!r} muncul lebih dari sekali untuk combo {combo!r} "
                f"di {path} (PRD Bagian 5.3 rule 2)."
            )
        values[combo][pile_id] = float(pz) * force_factor

    sha = sha256_file(path)
    _log.info(
        "Reaksi: %s (sha256 %s) | %d kombinasi | %d pile",
        path.name,
        short_hash(sha),
        len(combos),
        len(values[combos[0]]) if combos else 0,
    )
    return ReactionTable(
        combos=tuple(combos),
        values=values,
        path=path,
        sha256=sha,
        lateral_nonzero=tuple(lateral_nonzero),
    )


# ---------------------------------------------------------------------------
# Resolusi sumber geometri (PRD Bagian 5.2.1)
# ---------------------------------------------------------------------------


def _describe_ignored(raw_cfg: dict[str, Any], keys: tuple[str, ...]) -> str:
    """Rangkai daftar field JSON yang diabaikan beserta nilai MENTAH-nya."""
    parts: list[str] = []
    for dotted in keys:
        block, key = dotted.split(".", 1)
        value = (raw_cfg.get(block) or {}).get(key)
        if value is not None:
            parts.append(f"{dotted}={json.dumps(value)}")
    return ", ".join(parts) if parts else "(tidak ada field JSON yang terisi)"


def warn_override(
    entity: str,
    resolution: EntityResolution,
    raw_cfg: dict[str, Any],
    result_summary: str,
) -> None:
    """Teriakkan override geometri dengan format persis PRD Bagian 5.2.1.

    Ini adalah satu-satunya tempat format ini dibuat, sehingga keempat kanal wajib
    (konsol, run.log, run_manifest.json, calc_sheet.md) melihat teks yang konsisten.
    """
    origin = "auto-detect" if resolution.source == "csv_autodetect" else "flag CLI"
    _log.warning("OVERRIDE GEOMETRI - %s", entity)
    _log.warning(
        "   Sumber   : %s  (%s, sha256 %s)",
        resolution.file,
        origin,
        short_hash(resolution.sha256),
    )
    _log.warning("   Diabaikan: %s", _describe_ignored(raw_cfg, resolution.overridden_json_keys))
    _log.warning("   Hasil    : %s", result_summary)
    _log.warning("   Gunakan --no-custom bila ini TIDAK diinginkan.")


def _resolve_one(
    entity: str,
    *,
    cli_path: Path | None,
    input_dir: Path | None,
    autodetect_key: str,
    no_custom: bool,
    json_source: GeometrySource,
) -> EntityResolution:
    """Tentukan sumber satu entitas: flag CLI > CSV auto-detect > parameter JSON."""
    if cli_path is not None:
        if no_custom:
            # Rule 13d -- instruksi saling bertentangan.
            raise InputError(
                f"--no-custom dipakai bersamaan dengan flag CSV geometri eksplisit untuk "
                f"{entity} ({cli_path}).\n"
                "  Instruksinya saling bertentangan: --no-custom meminta parameter JSON, "
                "sedangkan flag eksplisit meminta CSV.\n"
                "  Pilih salah satu (PRD Bagian 5.2.1 & 5.3 rule 13d)."
            )
        if not cli_path.is_file():
            raise InputError(
                f"File CSV geometri untuk {entity} diberikan lewat flag CLI tetapi tidak "
                f"ditemukan / tidak terbaca: {cli_path} (PRD Bagian 5.3 rule 13)."
            )
        return EntityResolution(
            source="cli_flag",
            file=cli_path,
            sha256=sha256_file(cli_path),
            overridden_json_keys=config.OVERRIDDEN_JSON_KEYS[entity],
        )

    if not no_custom and input_dir is not None:
        found = autodetect(input_dir, autodetect_key, required=False)
        if found is not None:
            return EntityResolution(
                source="csv_autodetect",
                file=found,
                sha256=sha256_file(found),
                overridden_json_keys=config.OVERRIDDEN_JSON_KEYS[entity],
            )

    return EntityResolution(source=json_source)


def resolve_geometry_sources(
    loaded: LoadedConfig,
    *,
    input_dir: Path | None,
    cli_pilecap_polygon: Path | None = None,
    cli_pile_coords: Path | None = None,
    cli_pier_polygon: Path | None = None,
    no_custom: bool = False,
) -> ResolvedGeometrySources:
    """Resolusi sumber geometri PER ENTITAS + pemuatan CSV terkait (PRD Bagian 5.2.1).

    Ketiga entitas bersifat independen: pilecap boleh dari CSV sementara pile tetap grid
    JSON dan pier tetap rectangular. Tidak ada "mode global".

    Sumber ketiga entitas SELALU dicatat, meskipun tidak ada override sama sekali, agar
    run tetap dapat direproduksi persis.
    """
    length_factor = _unit_factor(loaded.input_units, "length")
    raw_cfg = loaded.raw

    res_cap = _resolve_one(
        "pilecap",
        cli_path=cli_pilecap_polygon,
        input_dir=input_dir,
        autodetect_key="pilecap_polygon",
        no_custom=no_custom,
        json_source="json_standard",
    )
    res_pile = _resolve_one(
        "pile",
        cli_path=cli_pile_coords,
        input_dir=input_dir,
        autodetect_key="pile_coords",
        no_custom=no_custom,
        json_source="json_grid",
    )
    res_pier = _resolve_one(
        "pier",
        cli_path=cli_pier_polygon,
        input_dir=input_dir,
        autodetect_key="pier_polygon",
        no_custom=no_custom,
        json_source="json_standard",
    )

    pilecap_polygon: Polygon2D | None = None
    if res_cap.is_override:
        assert res_cap.file is not None
        pilecap_polygon = load_pilecap_polygon(res_cap.file, length_factor)
        warn_override(
            "pilecap",
            res_cap,
            raw_cfg,
            f"polygon {pilecap_polygon.n_vertices} titik, luas {pilecap_polygon.area:.6f} m2",
        )

    piles: tuple[Pile, ...] | None = None
    if res_pile.is_override:
        assert res_pile.file is not None
        default_diameter = (loaded.si.get("pile") or {}).get("diameter")
        if default_diameter is None:
            raise InputError(
                "`pile.diameter` wajib diisi di config sebagai default, meskipun koordinat "
                "pile datang dari CSV (dipakai bila CSV tidak punya kolom `diameter`)."
            )
        piles = load_pile_coords(res_pile.file, length_factor, float(default_diameter))
        diameters = sorted({p.diameter for p in piles})
        diameter_text = (
            f"D = {diameters[0] * 1e3:.0f} mm"
            if len(diameters) == 1
            else f"D = {diameters[0] * 1e3:.0f}-{diameters[-1] * 1e3:.0f} mm"
        )
        warn_override("pile", res_pile, raw_cfg, f"{len(piles)} pile dari CSV, {diameter_text}")

    pier_polygons: tuple[tuple[str, Polygon2D], ...] | None = None
    if res_pier.is_override:
        assert res_pier.file is not None
        pier_polygons = load_pier_polygons(res_pier.file, length_factor)
        total_area = sum(poly.area for _, poly in pier_polygons)
        warn_override(
            "pier",
            res_pier,
            raw_cfg,
            f"{len(pier_polygons)} pier polygon ({', '.join(p for p, _ in pier_polygons)}), "
            f"total luas {total_area:.6f} m2. "
            "Centerline tiap pier diambil dari centroid polygon-nya.",
        )

    resolution = GeometryResolution(pilecap=res_cap, pile=res_pile, pier=res_pier)
    _log.info("Resolusi geometri: %s", resolution.as_summary_line())

    return ResolvedGeometrySources(
        resolution=resolution,
        pilecap_polygon=pilecap_polygon,
        piles=piles,
        pier_polygons=pier_polygons,
    )


def sources_present(resolution: GeometryResolution) -> dict[str, bool]:
    """Peta entitas -> apakah geometrinya datang dari CSV (dipakai validators rule 13f)."""
    return {
        "pilecap": resolution.pilecap.is_override,
        "pile": resolution.pile.is_override,
        "pier": resolution.pier.is_override,
    }
