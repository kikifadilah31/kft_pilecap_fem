"""Test `geometry_builder.py` (PRD Bagian 15.1)."""

from __future__ import annotations

import math

import numpy as np
import pytest
from shapely.geometry import Point

from pilecap_fem.geometry_builder import (
    EntityResolution,
    GeometryResolution,
    Pier,
    Pile,
    Polygon2D,
    ResolvedGeometrySources,
    build_geometry_model,
    build_pile_grid,
    drop_repeated_closing_vertex,
    normalize_ccw,
    polygon_centroid,
    polygon_from_rect,
    signed_area,
)

SQUARE_CCW = np.array([[0.0, 0.0], [4.0, 0.0], [4.0, 3.0], [0.0, 3.0]])
L_SHAPE = np.array([[0.0, 0.0], [8.0, 0.0], [8.0, 3.5], [4.0, 3.5], [4.0, 7.0], [0.0, 7.0]])


def _json_resolution() -> GeometryResolution:
    return GeometryResolution(
        pilecap=EntityResolution(source="json_standard"),
        pile=EntityResolution(source="json_grid"),
        pier=EntityResolution(source="json_standard"),
    )


# ---------------------------------------------------------------------------
# Polygon
# ---------------------------------------------------------------------------


def test_signed_area_positif_untuk_ccw():
    assert signed_area(SQUARE_CCW) == pytest.approx(12.0)
    assert signed_area(SQUARE_CCW[::-1]) == pytest.approx(-12.0)


def test_normalize_ccw_menghasilkan_luas_dan_geometri_identik():
    """Orientasi CW dan CCW harus menghasilkan polygon yang sama (PRD Bagian 15.1)."""
    from_ccw = Polygon2D(normalize_ccw(L_SHAPE))
    from_cw = Polygon2D(normalize_ccw(L_SHAPE[::-1].copy()))

    assert from_ccw.area == pytest.approx(from_cw.area)
    assert from_ccw.signed_area > 0 and from_cw.signed_area > 0
    # Titik-titiknya boleh berbeda urutan awal, tetapi himpunan titiknya identik.
    assert {tuple(v) for v in from_ccw.vertices} == {tuple(v) for v in from_cw.vertices}
    assert from_ccw.to_shapely().equals(from_cw.to_shapely())


def test_luas_l_shape_sesuai_hitungan_tangan():
    assert Polygon2D(normalize_ccw(L_SHAPE)).area == pytest.approx(8 * 3.5 + 4 * 3.5)


def test_drop_repeated_closing_vertex():
    closed = np.vstack([SQUARE_CCW, SQUARE_CCW[:1]])
    assert len(drop_repeated_closing_vertex(closed)) == 4
    assert len(drop_repeated_closing_vertex(SQUARE_CCW)) == 4


def test_centroid_persegi_di_tengah():
    assert polygon_centroid(SQUARE_CCW) == pytest.approx((2.0, 1.5))


def test_centroid_l_shape_bukan_rata_rata_titik_sudut():
    """Centroid geometris berbeda dari rata-rata titik sudut untuk polygon tak simetris."""
    centroid = polygon_centroid(L_SHAPE)
    mean_of_vertices = tuple(L_SHAPE.mean(axis=0))
    assert not np.allclose(centroid, mean_of_vertices)
    # Centroid harus berada di dalam polygon.
    assert Polygon2D(normalize_ccw(L_SHAPE)).to_shapely().contains(Point(*centroid))


def test_polygon_minimal_tiga_titik():
    with pytest.raises(ValueError, match="minimal 3 titik"):
        Polygon2D(np.array([[0.0, 0.0], [1.0, 0.0]]))


def test_polygon_bentuk_array_salah():
    with pytest.raises(ValueError, match=r"bentuk \(n, 2\)"):
        Polygon2D(np.array([0.0, 1.0, 2.0]))


def test_polygon_from_rect_berpusat_di_origin():
    poly = polygon_from_rect(8.0, 6.0, (1.0, 2.0))
    assert poly.area == pytest.approx(48.0)
    assert poly.centroid == pytest.approx((1.0, 2.0))
    assert poly.bounds == pytest.approx((-3.0, -1.0, 5.0, 5.0))


# ---------------------------------------------------------------------------
# Grid pile
# ---------------------------------------------------------------------------


def test_build_pile_grid_jumlah_dan_koordinat():
    piles = build_pile_grid(
        n_col=4, n_row=3, spacing_x=3.0, spacing_y=2.6, grid_origin=(0.0, 0.0), diameter=0.8
    )
    assert len(piles) == 12
    assert [p.pile_id for p in piles[:4]] == ["P1", "P2", "P3", "P4"]

    xs = sorted({p.x for p in piles})
    ys = sorted({p.y for p in piles})
    assert xs == pytest.approx([-4.5, -1.5, 1.5, 4.5])
    assert ys == pytest.approx([-2.6, 0.0, 2.6])

    # Penomoran row-major dari kiri-bawah: P1 di sudut kiri-bawah.
    assert (piles[0].x, piles[0].y) == pytest.approx((-4.5, -2.6))
    assert (piles[-1].x, piles[-1].y) == pytest.approx((4.5, 2.6))


def test_build_pile_grid_menghormati_origin():
    piles = build_pile_grid(
        n_col=2, n_row=2, spacing_x=2.0, spacing_y=2.0, grid_origin=(10.0, 5.0), diameter=0.6
    )
    assert {(p.x, p.y) for p in piles} == {(9.0, 4.0), (11.0, 4.0), (9.0, 6.0), (11.0, 6.0)}


def test_pile_grid_satu_baris_satu_kolom():
    piles = build_pile_grid(
        n_col=1, n_row=1, spacing_x=2.0, spacing_y=2.0, grid_origin=(3.0, 4.0), diameter=0.5
    )
    assert len(piles) == 1
    assert (piles[0].x, piles[0].y) == pytest.approx((3.0, 4.0))


# ---------------------------------------------------------------------------
# Pier
# ---------------------------------------------------------------------------


def test_pier_rectangular_luas_dan_posisi():
    pier = Pier(
        pier_id="PIER1",
        shape="rectangular",
        centerline=(1.0, 2.0),
        width_x=2.0,
        width_y=1.5,
    )
    assert pier.area == pytest.approx(3.0)
    assert pier.to_shapely().bounds == pytest.approx((0.0, 1.25, 2.0, 2.75))


def test_pier_circular_luas_mendekati_analitis():
    pier = Pier(pier_id="PIER1", shape="circular", centerline=(0.0, 0.0), diameter=1.8)
    # Polygon 64 segmen sedikit lebih kecil dari lingkaran eksak.
    assert pier.area == pytest.approx(math.pi * 0.9**2, rel=1e-3)


def test_pier_shape_tanpa_dimensi_raise():
    with pytest.raises(ValueError, match="width_x/width_y kosong"):
        Pier(pier_id="X", shape="rectangular", centerline=(0.0, 0.0)).to_shapely()


def test_pier_group_name_dan_pile_group_name():
    assert Pier(pier_id="A", shape="circular", centerline=(0, 0), diameter=1.0).group_name == (
        "PIER_A"
    )
    assert Pile(pile_id="P7", x=0.0, y=0.0, diameter=0.8).group_name == "PILE_P7"


# ---------------------------------------------------------------------------
# Perakitan model
# ---------------------------------------------------------------------------


def _minimal_cfg() -> dict:
    return {
        "pilecap": {"length_x": 4.8, "length_y": 4.8, "origin": [0, 0], "thickness": 1.2},
        "pile": {
            "diameter": 0.8,
            "n_col": 2,
            "n_row": 2,
            "spacing_x": 2.4,
            "spacing_y": 2.4,
            "grid_origin": [0, 0],
        },
        "pier": {
            "shape": "rectangular",
            "centerline": [0, 0],
            "width_x": 1.2,
            "width_y": 1.2,
        },
    }


def test_build_geometry_model_dari_json_saja():
    geom = build_geometry_model(
        _minimal_cfg(), ResolvedGeometrySources(resolution=_json_resolution())
    )
    assert geom.n_piles == 4
    assert geom.n_piers == 1
    assert geom.piers[0].pier_id == "PIER1"
    assert geom.pilecap_area == pytest.approx(4.8 * 4.8)
    assert geom.thickness == pytest.approx(1.2)
    assert geom.min_pile_diameter == pytest.approx(0.8)


def test_entitas_independen_pilecap_csv_pile_json():
    """PRD Bagian 5.2.1: pilecap boleh dari CSV sementara pile & pier tetap dari JSON."""
    sources = ResolvedGeometrySources(
        resolution=GeometryResolution(
            pilecap=EntityResolution(source="csv_autodetect"),
            pile=EntityResolution(source="json_grid"),
            pier=EntityResolution(source="json_standard"),
        ),
        pilecap_polygon=Polygon2D(normalize_ccw(L_SHAPE)),
    )
    geom = build_geometry_model(_minimal_cfg(), sources)
    assert geom.pilecap_area == pytest.approx(8 * 3.5 + 4 * 3.5)
    assert geom.n_piles == 4  # tetap dari grid JSON
    assert geom.piers[0].shape == "rectangular"  # tetap dari JSON


def test_pier_dari_csv_centerline_adalah_centroid_polygon():
    """Keputusan multi-pier: centerline pier dari CSV = centroid polygon-nya."""
    poly_a = Polygon2D(
        normalize_ccw(np.array([[5.3, 1.25], [6.7, 1.25], [6.7, 2.25], [5.3, 2.25]]))
    )
    poly_b = Polygon2D(
        normalize_ccw(np.array([[1.3, 4.55], [2.7, 4.55], [2.7, 5.95], [1.3, 5.95]]))
    )
    sources = ResolvedGeometrySources(
        resolution=GeometryResolution(
            pilecap=EntityResolution(source="json_standard"),
            pile=EntityResolution(source="json_grid"),
            pier=EntityResolution(source="csv_autodetect"),
        ),
        pier_polygons=(("PIER_A", poly_a), ("PIER_B", poly_b)),
    )
    geom = build_geometry_model(_minimal_cfg(), sources)

    assert geom.n_piers == 2
    assert [p.pier_id for p in geom.piers] == ["PIER_A", "PIER_B"]
    assert all(p.shape == "polygon" for p in geom.piers)
    assert geom.piers[0].centerline == pytest.approx((6.0, 1.75))
    assert geom.piers[1].centerline == pytest.approx((2.0, 5.25))
    # centerline JSON [0, 0] TIDAK dipakai
    assert geom.piers[0].centerline != pytest.approx((0.0, 0.0))


def test_pile_by_id_dan_error_bila_tidak_ada():
    geom = build_geometry_model(
        _minimal_cfg(), ResolvedGeometrySources(resolution=_json_resolution())
    )
    assert geom.pile_by_id("P3").pile_id == "P3"
    with pytest.raises(KeyError, match="P99"):
        geom.pile_by_id("P99")


def test_geometry_resolution_to_manifest_lengkap_meski_tanpa_override():
    """PRD Bagian 5.2.1: sumber ketiga entitas WAJIB tercatat meski tidak ada override."""
    manifest = _json_resolution().to_manifest()
    assert set(manifest) == {"pilecap", "pile", "pier"}
    assert manifest["pilecap"]["source"] == "json_standard"
    assert manifest["pile"]["source"] == "json_grid"
    assert all(m["overridden_json_keys"] == [] for m in manifest.values())
    assert all(m["file"] is None for m in manifest.values())
