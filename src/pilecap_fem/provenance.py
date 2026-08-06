"""Reproducibility & provenance -- `run_manifest.json` (PRD Bagian 10, Core 5).

Manifest ditulis **sebelum** proses panjang dimulai, lalu dilengkapi field hasil di akhir,
sehingga run yang gagal pun tetap meninggalkan jejak yang dapat ditelusuri.
"""

from __future__ import annotations

import json
import platform
import sys
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any

from pilecap_fem import __version__, config
from pilecap_fem.geometry_builder import GeometryResolution

_log = config.get_logger("provenance")

#: Dependency yang versinya wajib tercatat. gmsh & openseespy paling kritis: hasil mesh
#: dan solver dapat berbeda antar versi (PRD Bagian 10).
TRACKED_DEPENDENCIES = (
    "numpy",
    "gmsh",
    "openseespy",
    "opsvis",
    "matplotlib",
    "pandas",
    "shapely",
    # shell-kit menentukan SETIAP angka kapasitas yang dilaporkan. Pin transitifnya lebih
    # longgar dari pin kita, jadi mencatat versi yang benar-benar terpasang adalah satu-
    # satunya cara penyimpangan numerik tetap terdeteksi di kemudian hari.
    "shell-kit",
)

MANIFEST_FILENAME = "run_manifest.json"


def dependency_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in TRACKED_DEPENDENCIES:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "TIDAK TERPASANG"
    return versions


class Manifest:
    """Pembangun `run_manifest.json` yang dapat ditulis berulang kali selama run."""

    def __init__(self, output_dir: Path, command: str) -> None:
        self.path = output_dir / MANIFEST_FILENAME
        self._data: dict[str, Any] = {
            "tool_version": __version__,
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "command": command,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "dependencies": dependency_versions(),
            "inputs": {},
            "parameters": {},
            "unit_system": config.SI_UNIT_SYSTEM,
            "geometry_resolution": {},
            "standards": {},
            "model_stats": {},
            "checks": {},
            "combos_analyzed": [],
            "warnings": [],
            "open_blockers": config.OPEN_BLOCKERS,
            "status": "RUNNING",
        }

    # -- pengisian ---------------------------------------------------------

    def add_input(self, path: Path, sha256: str | None) -> None:
        self._data["inputs"][Path(path).as_posix()] = (
            f"sha256:{sha256}" if sha256 else "sha256:(tidak dihitung)"
        )

    def set_parameters(self, parameters: dict[str, Any]) -> None:
        """CLI args + config efektif.

        Parameter JSON yang di-override CSV TETAP disimpan apa adanya di sini, tidak
        dihapus, agar checker dapat melihat apa yang semula tertulis (PRD Bagian 5.2.1).
        """
        self._data["parameters"] = parameters

    def set_geometry_resolution(self, resolution: GeometryResolution) -> None:
        self._data["geometry_resolution"] = resolution.to_manifest()

    def set_standards(
        self,
        design_cfg: dict[str, Any] | None,
        capacity_provenance: dict[str, Any] | None = None,
    ) -> None:
        """Standar & pasal yang dipakai.

        `capacity_provenance` datang dari `capacity_engine.provenance_block()` dan baru
        ada di jalur `pilecap-report`; `pilecap-analyze` menghasilkan demand saja sehingga
        blok itu memang tidak berlaku di sana.
        """
        design_cfg = design_cfg or {}
        standards: dict[str, Any] = {
            "design_code": design_cfg.get("code"),
            "phi_flexure": design_cfg.get("phi_flexure"),
            "phi_shear": design_cfg.get("phi_shear"),
        }
        if capacity_provenance is None:
            standards["catatan"] = (
                "Tahap ini hanya menghasilkan DEMAND. Kapasitas lentur & geser satu arah "
                "dihitung `pilecap-report` lewat shell-kit."
            )
        else:
            standards["capacity"] = capacity_provenance
            standards["catatan"] = (
                "Kapasitas lentur & geser SATU ARAH dihitung shell-kit menurut "
                "SNI 2847:2019 (lihat blok `capacity`). Geser PONS tetap NOT_EVALUATED."
            )
        self._data["standards"] = standards

    def update_model_stats(self, stats: dict[str, Any]) -> None:
        self._data["model_stats"].update(stats)

    def update_checks(self, checks: dict[str, Any]) -> None:
        self._data["checks"].update(checks)

    def add_warnings(self, warnings: list[str] | tuple[str, ...]) -> None:
        self._data["warnings"].extend(warnings)

    def set_status(self, status: str) -> None:
        self._data["status"] = status

    # -- penulisan ---------------------------------------------------------

    @property
    def data(self) -> dict[str, Any]:
        return self._data

    def write(self) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False, default=str) + "\n",
            encoding="utf-8",
        )
        _log.debug("run_manifest.json ditulis (status=%s)", self._data["status"])
        return self.path


def make_run_dir(output_root: Path, now: datetime | None = None) -> Path:
    """Folder run baru `pilecap_YYYYMMDD_HHMMSS`. Tidak pernah menimpa (PRD Bagian 9.1)."""
    stamp = (now or datetime.now()).strftime(config.RUN_DIR_FORMAT)
    candidate = output_root / stamp
    suffix = 1
    while candidate.exists():
        suffix += 1
        candidate = output_root / f"{stamp}_{suffix}"
    candidate.mkdir(parents=True)
    return candidate
