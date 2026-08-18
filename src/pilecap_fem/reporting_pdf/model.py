"""Bundel data satu laporan PDF.

Dipisah dari `document.py` supaya `chapters.py` dan `theory.py` dapat menerimanya sebagai
tipe tanpa mengimpor balik modul yang memanggil mereka.

Seluruh isinya adalah objek yang SUDAH dihitung `cli_pilecap_report`. Tidak ada satu pun
field yang diturunkan ulang di sini -- lihat aturan modul di `__init__.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pilecap_fem import capacity_engine, postproc_engine, renderer, reporter
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel

__all__ = ["ReportData"]


@dataclass(frozen=True)
class ReportData:
    """Segala yang dibutuhkan dokumen, apa adanya dari pelaporan."""

    run_dir: Path
    run_name: str
    command: str
    manifest: dict[str, Any]
    cfg: dict[str, Any]

    geom: GeometryModel
    mesh: MeshModel
    block: renderer.TitleBlock

    capacity_inputs: capacity_engine.CapacityInputs
    deep_ratio: dict[str, Any]
    rebar_basis: str
    mesh_size_m: float

    #: Masukan calc sheet per kombinasi -- objek yang SAMA yang menghasilkan `calc_sheet.md`.
    calc_inputs_by_combo: dict[str, reporter.CalcSheetInputs]
    designs_by_combo: dict[str, dict[tuple[str, str], capacity_engine.FlexureDesign]]
    strip_design_by_combo: dict[str, list[dict[str, Any]]]

    combo_rows: list[dict[str, Any]]
    checks: dict[str, Any]
    warnings: list[str]
    envelope: postproc_engine.Envelope | None

    no_rebar_plots: bool
    no_envelope: bool
    #: Waktu mulai pelaporan [epoch]; dipakai menandai gambar dari run sebelumnya.
    started_at: float
    rebar_governing: list[dict[str, Any]] = field(default_factory=list)

    @property
    def project_name(self) -> str:
        return str(
            ((self.manifest.get("parameters") or {}).get("config_raw") or {})
            .get("project", {})
            .get("name", "")
        )

    @property
    def model_dir(self) -> Path:
        from pilecap_fem import config

        return self.run_dir / config.MODEL_SUBDIR

    @property
    def envelope_dir(self) -> Path:
        from pilecap_fem import config

        return self.run_dir / config.ENVELOPE_SUBDIR
