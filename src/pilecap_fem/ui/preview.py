"""Pratinjau geometri untuk `pilecap-ui`, tanpa meshing dan tanpa solver.

**TIDAK mengimpor streamlit**, dengan alasan yang sama seperti `schema.py`: yang dapat salah
di sini adalah pemetaan formulir -> geometri, dan itu harus dapat diuji tanpa menyalakan
server.

.. rubric:: Mengapa lewat berkas sementara, bukan konversi satuan sendiri

`io_utils.load_config` adalah **satu-satunya** titik konversi satuan (PRD Bagian 4.2), dan
ia menerima path, bukan dict. Menyalin logika konversinya ke sini demi menghindari satu
berkas sementara berarti membuat pratinjau yang dapat menampilkan geometri berbeda dari
yang nanti dianalisis -- persis kesalahan yang paling tidak boleh terjadi pada gambar yang
dipakai orang untuk memutuskan "sudah benar, jalankan". Berkasnya ditulis di folder
sementara sistem dan dihapus setelah dibaca, sehingga `ui_configs/` tidak terisi satu
berkas per klik pratinjau.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from pilecap_fem import geometry_builder, io_utils, validators
from pilecap_fem.geometry_builder import GeometryModel


def build_preview_geometry(cfg: dict[str, Any], input_dir: Path | None) -> GeometryModel:
    """Bangun `GeometryModel` dari config formulir, lewat jalur yang sama dengan CLI.

    `input_dir` ikut diperhitungkan supaya override CSV -- pilecap poligon, koordinat pile,
    poligon pier -- tampil di pratinjau persis seperti nanti pada run. Pratinjau yang
    mengabaikannya akan menggambar grid pile JSON padahal CSV-lah yang akan dipakai.

    Melempar `InputError`/`GeometryError` dengan pesan yang sudah ditulis untuk engineer;
    pemanggil menampilkannya apa adanya, bukan sebagai traceback.
    """
    with tempfile.TemporaryDirectory(prefix="pilecap_ui_preview_") as tmp:
        path = Path(tmp) / "pilecap_config.json"
        path.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        loaded = io_utils.load_config(path)

    sources = io_utils.resolve_geometry_sources(
        loaded,
        input_dir=input_dir if input_dir is not None and input_dir.is_dir() else None,
    )
    present = io_utils.sources_present(sources.resolution)
    validators.validate_config_geometry_params(loaded.si, present)

    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    validators.validate_geometry(geom)
    return geom


__all__ = ["build_preview_geometry"]
