"""Test `io_utils.py`: konversi satuan + resolusi geometri PRD Bagian 5.2.1."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from pilecap_fem import config, io_utils
from pilecap_fem.validators import InputError


def _load(directory: Path) -> io_utils.LoadedConfig:
    return io_utils.load_config(directory / "pilecap_config.json")


def _resolve(directory: Path, **kwargs) -> object:
    return io_utils.resolve_geometry_sources(_load(directory), input_dir=directory, **kwargs)


# ---------------------------------------------------------------------------
# Auto-detection (Core 10)
# ---------------------------------------------------------------------------


def test_autodetect_menemukan_config(ex01: Path):
    assert io_utils.autodetect(ex01, "config", required=True) == ex01 / "pilecap_config.json"


def test_autodetect_lebih_dari_satu_match_raise(ex01: Path):
    (ex01 / "backup_config.json").write_text("{}", encoding="utf-8")
    with pytest.raises(InputError, match="Lebih dari satu file cocok"):
        io_utils.autodetect(ex01, "config", required=True)


def test_autodetect_file_wajib_hilang_raise_dengan_isi_folder(tmp_path: Path):
    (tmp_path / "sesuatu.txt").write_text("x", encoding="utf-8")
    with pytest.raises(InputError, match=r"sesuatu\.txt"):
        io_utils.autodetect(tmp_path, "config", required=True)


def test_autodetect_file_opsional_hilang_mengembalikan_none(ex01: Path):
    assert io_utils.autodetect(ex01, "pier_polygon", required=False) is None


def test_autodetect_folder_tidak_ada_raise(tmp_path: Path):
    with pytest.raises(InputError, match="Folder input tidak ditemukan"):
        io_utils.autodetect(tmp_path / "tidak_ada", "config")


# ---------------------------------------------------------------------------
# Konversi satuan (PRD Bagian 4.2)
# ---------------------------------------------------------------------------


def test_konversi_mm_kn_mpa_ke_si(ex01: Path):
    loaded = _load(ex01)
    raw, si = loaded.raw, loaded.si

    assert raw["pilecap"]["length_x"] == 4800  # mm
    assert si["pilecap"]["length_x"] == pytest.approx(4.8)  # m
    assert si["pilecap"]["thickness"] == pytest.approx(1.2)
    assert si["pile"]["diameter"] == pytest.approx(0.8)
    assert si["pile"]["spacing_x"] == pytest.approx(2.4)
    assert si["pier"]["width_x"] == pytest.approx(1.2)
    assert si["mesh"]["size_global"] == pytest.approx(0.130)
    assert si["design"]["cover"] == pytest.approx(0.075)
    assert si["material"]["fc"] == pytest.approx(30e6)  # MPa -> Pa
    assert si["material"]["E"] == pytest.approx(25e9)
    assert si["material"]["density"] == pytest.approx(24e3)  # kN/m^3 -> N/m^3


def test_pasangan_koordinat_ikut_dikonversi(ex03: Path):
    si = _load(ex03).si
    assert si["pilecap"]["origin"] == pytest.approx([4.0, 3.5])
    assert si["pile"]["grid_origin"] == pytest.approx([4.0, 3.5])
    assert si["pier"]["centerline"] == pytest.approx([4.0, 3.5])


def test_round_trip_satuan_meter_tidak_mengubah_nilai(ex01: Path):
    """Config dalam meter harus menghasilkan nilai SI yang sama dengan versi mm."""
    path = ex01 / "pilecap_config.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    si_mm = io_utils.load_config(path).si

    data["units"]["length"] = "m"
    for block, keys in (
        ("pilecap", ("length_x", "length_y", "thickness")),
        ("pile", ("diameter", "spacing_x", "spacing_y")),
        ("pier", ("width_x", "width_y")),
        ("mesh", ("size_global",)),
        ("design", ("cover",)),
    ):
        for key in keys:
            data[block][key] = data[block][key] / 1000.0
    path.write_text(json.dumps(data), encoding="utf-8")
    si_m = io_utils.load_config(path).si

    assert si_m["pilecap"]["length_x"] == pytest.approx(si_mm["pilecap"]["length_x"])
    assert si_m["mesh"]["size_global"] == pytest.approx(si_mm["mesh"]["size_global"])
    assert si_m["pile"]["diameter"] == pytest.approx(si_mm["pile"]["diameter"])


def test_satuan_tidak_dikenal_raise(ex01: Path, patch):
    patch(ex01 / "pilecap_config.json", units={"length": "inch"})
    with pytest.raises(InputError, match="Satuan length"):
        _load(ex01)


def test_kunci_units_tak_dikenal_raise(ex01: Path, patch):
    patch(ex01 / "pilecap_config.json", units={"temperature": "C"})
    with pytest.raises(InputError, match="tidak dikenal"):
        _load(ex01)


def test_config_bukan_json_raise(tmp_path: Path):
    path = tmp_path / "pilecap_config.json"
    path.write_text("{ bukan json", encoding="utf-8")
    with pytest.raises(InputError, match="bukan JSON yang sah"):
        io_utils.load_config(path)


def test_to_display_dan_display_unit():
    assert io_utils.to_display(1.5, "length") == pytest.approx(1500.0)
    assert io_utils.to_display(1234.0, "force") == pytest.approx(1.234)
    assert io_utils.display_unit("moment_per_width") == "kNm/m"
    with pytest.raises(KeyError):
        io_utils.display_unit("besaran_ngawur")


def test_sha256_stabil(ex01: Path):
    path = ex01 / "pile_reactions.csv"
    assert io_utils.sha256_file(path) == io_utils.sha256_file(path)
    assert len(io_utils.sha256_file(path)) == 64


# ---------------------------------------------------------------------------
# Pembacaan CSV geometri
# ---------------------------------------------------------------------------


def test_polygon_diurutkan_berdasarkan_vertex_id_bukan_urutan_baris(tmp_path: Path):
    """PRD Bagian 5.1(d): urutan BARIS tidak menentukan; vertex_id yang menentukan."""
    path = tmp_path / "cap_polygon.csv"
    path.write_text("vertex_id,x,y\n3,8000,6000\n1,0,0\n4,0,6000\n2,8000,0\n", encoding="utf-8")
    polygon = io_utils.load_pilecap_polygon(path, 1e-3)
    assert polygon.area == pytest.approx(48.0)
    assert polygon.n_vertices == 4


def test_baris_penutup_duplikat_dibuang(tmp_path: Path, caplog):
    path = tmp_path / "cap_polygon.csv"
    path.write_text(
        "vertex_id,x,y\n1,0,0\n2,8000,0\n3,8000,6000\n4,0,6000\n5,0,0\n", encoding="utf-8"
    )
    with caplog.at_level(logging.INFO, logger="pilecap_fem.io_utils"):
        polygon = io_utils.load_pilecap_polygon(path, 1e-3)
    assert polygon.n_vertices == 4
    assert polygon.area == pytest.approx(48.0)
    assert any("penutup" in record.message for record in caplog.records)


def test_polygon_orientasi_cw_dinormalisasi(tmp_path: Path):
    path = tmp_path / "cap_polygon.csv"
    path.write_text("vertex_id,x,y\n1,0,0\n2,0,6000\n3,8000,6000\n4,8000,0\n", encoding="utf-8")
    polygon = io_utils.load_pilecap_polygon(path, 1e-3)
    assert polygon.signed_area > 0
    assert polygon.area == pytest.approx(48.0)


def test_pier_polygon_multi_dengan_pier_id(ex03: Path):
    piers = io_utils.load_pier_polygons(ex03 / "pier_polygon.csv", 1e-3)
    assert [pid for pid, _ in piers] == ["PIER_A", "PIER_B"]
    assert piers[0][1].area == pytest.approx(1.4 * 1.0)
    assert piers[1][1].area == pytest.approx(1.4 * 1.4)


def test_pier_polygon_tanpa_kolom_pier_id_menjadi_satu_pier(tmp_path: Path):
    path = tmp_path / "pier_polygon.csv"
    path.write_text("vertex_id,x,y\n1,0,0\n2,2000,0\n3,2000,1500\n4,0,1500\n", encoding="utf-8")
    piers = io_utils.load_pier_polygons(path, 1e-3)
    assert len(piers) == 1
    assert piers[0][0] == "PIER1"


def test_pile_coords_dengan_dan_tanpa_kolom_diameter(ex03: Path, tmp_path: Path):
    piles = io_utils.load_pile_coords(ex03 / "custom_pile_coords.csv", 1e-3, 0.7)
    assert len(piles) == 12
    assert piles[0].diameter == pytest.approx(0.7)
    assert piles[2].diameter == pytest.approx(0.9)  # kolom diameter meng-override

    path = tmp_path / "pile_coords.csv"
    path.write_text("pile_id,x,y\nA,1000,1000\nB,2000,1000\n", encoding="utf-8")
    fallback = io_utils.load_pile_coords(path, 1e-3, 0.65)
    assert [p.diameter for p in fallback] == pytest.approx([0.65, 0.65])


def test_pile_id_duplikat_raise(tmp_path: Path):
    path = tmp_path / "pile_coords.csv"
    path.write_text("pile_id,x,y\nP1,0,0\nP1,1000,0\n", encoding="utf-8")
    with pytest.raises(InputError, match="duplikat"):
        io_utils.load_pile_coords(path, 1e-3, 0.8)


def test_kolom_wajib_hilang_raise_dengan_daftar_kolom(tmp_path: Path):
    path = tmp_path / "cap_polygon.csv"
    path.write_text("vertex_id,x\n1,0\n2,1\n3,2\n", encoding="utf-8")
    with pytest.raises(InputError, match=r"Kolom yang ditemukan"):
        io_utils.load_pilecap_polygon(path, 1e-3)


# ---------------------------------------------------------------------------
# Resolusi geometri PRD Bagian 5.2.1 -- inti aturan override
# ---------------------------------------------------------------------------


def test_tanpa_csv_ketiga_entitas_json(ex01: Path):
    resolution = _resolve(ex01).resolution
    assert resolution.pilecap.source == "json_standard"
    assert resolution.pile.source == "json_grid"
    assert resolution.pier.source == "json_standard"
    assert not resolution.has_any_override()
    assert all(
        r.overridden_json_keys == () for r in (resolution.pilecap, resolution.pile, resolution.pier)
    )


def test_autodetect_menang_atas_json(ex03: Path):
    resolution = _resolve(ex03).resolution
    assert resolution.pilecap.source == "csv_autodetect"
    assert resolution.pile.source == "csv_autodetect"
    assert resolution.pier.source == "csv_autodetect"
    assert resolution.has_any_override()


def test_flag_cli_menang_atas_autodetect(ex03: Path, tmp_path: Path):
    lain = tmp_path / "polygon_lain.csv"
    lain.write_text("vertex_id,x,y\n1,0,0\n2,5000,0\n3,5000,5000\n4,0,5000\n", encoding="utf-8")
    sources = _resolve(ex03, cli_pilecap_polygon=lain)
    assert sources.resolution.pilecap.source == "cli_flag"
    assert sources.resolution.pilecap.file == lain
    assert sources.pilecap_polygon.area == pytest.approx(25.0)
    # entitas lain tetap dari auto-detect
    assert sources.resolution.pile.source == "csv_autodetect"


def test_no_custom_mengembalikan_ke_json(ex03: Path):
    resolution = _resolve(ex03, no_custom=True).resolution
    assert resolution.pilecap.source == "json_standard"
    assert resolution.pile.source == "json_grid"
    assert resolution.pier.source == "json_standard"
    assert not resolution.has_any_override()


def test_no_custom_plus_flag_eksplisit_raise(ex03: Path):
    """PRD Bagian 5.3 rule 13d -- instruksi saling bertentangan."""
    with pytest.raises(InputError, match="saling bertentangan"):
        _resolve(ex03, no_custom=True, cli_pilecap_polygon=ex03 / "pilecap_polygon.csv")


def test_flag_cli_menunjuk_file_tidak_ada_raise(ex01: Path, tmp_path: Path):
    with pytest.raises(InputError, match="tidak ditemukan / tidak terbaca"):
        _resolve(ex01, cli_pier_polygon=tmp_path / "hantu.csv")


def test_setiap_override_menghasilkan_warning_dan_overridden_keys(ex03: Path, caplog):
    with caplog.at_level(logging.WARNING, logger="pilecap_fem.io_utils"):
        resolution = _resolve(ex03).resolution

    messages = [record.getMessage() for record in caplog.records]
    joined = "\n".join(messages)
    for entity in ("pilecap", "pile", "pier"):
        assert f"OVERRIDE GEOMETRI - {entity}" in joined
    assert "Gunakan --no-custom bila ini TIDAK diinginkan." in joined
    # Nilai JSON yang diabaikan ditampilkan apa adanya (satuan input, bukan SI).
    assert "pilecap.length_x=8000" in joined
    assert "pile.n_col=4" in joined

    assert resolution.pilecap.overridden_json_keys == config.OVERRIDDEN_JSON_KEYS["pilecap"]
    assert resolution.pile.overridden_json_keys == config.OVERRIDDEN_JSON_KEYS["pile"]
    # centerline ikut diabaikan karena multi-pier mengambil centroid tiap polygon
    assert "pier.centerline" in resolution.pier.overridden_json_keys


def test_tanpa_override_tidak_ada_warning(ex01: Path, caplog):
    with caplog.at_level(logging.WARNING, logger="pilecap_fem.io_utils"):
        _resolve(ex01)
    assert not [r for r in caplog.records if "OVERRIDE" in r.getMessage()]


def test_entitas_independen_hanya_pier_dari_csv(ex01: Path):
    """pilecap & pile tetap JSON, hanya pier yang di-override lewat flag CLI."""
    pier_csv = ex01 / "pier_poly.csv"
    pier_csv.write_text(
        "vertex_id,x,y\n1,-600,-600\n2,600,-600\n3,600,600\n4,-600,600\n", encoding="utf-8"
    )
    sources = _resolve(ex01, cli_pier_polygon=pier_csv)
    assert sources.resolution.pilecap.source == "json_standard"
    assert sources.resolution.pile.source == "json_grid"
    assert sources.resolution.pier.source == "cli_flag"
    assert sources.pilecap_polygon is None
    assert sources.piles is None
    assert len(sources.pier_polygons) == 1


def test_manifest_mencatat_sha256_file_override(ex03: Path):
    resolution = _resolve(ex03).resolution
    manifest = resolution.to_manifest()
    assert manifest["pilecap"]["sha256"] == io_utils.sha256_file(ex03 / "pilecap_polygon.csv")
    assert manifest["pilecap"]["file"].endswith("pilecap_polygon.csv")
    assert manifest["pile"]["overridden_json_keys"] == list(config.OVERRIDDEN_JSON_KEYS["pile"])


def test_sources_present_map(ex03: Path, ex01: Path):
    assert io_utils.sources_present(_resolve(ex03).resolution) == {
        "pilecap": True,
        "pile": True,
        "pier": True,
    }
    assert io_utils.sources_present(_resolve(ex01).resolution) == {
        "pilecap": False,
        "pile": False,
        "pier": False,
    }
