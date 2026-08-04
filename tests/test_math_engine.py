"""Test `math_engine.py` (PRD Bagian 15.1).

Seluruh test di sini murni matematika -- tidak menjalankan solver, tidak menyentuh gmsh.
Cepat, deterministik, dan menjadi jaring pengaman pertama sebelum VC-2/VC-3 yang mahal.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from pilecap_fem import math_engine


def arr(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float64)


# ---------------------------------------------------------------------------
# Kekakuan pelat
# ---------------------------------------------------------------------------


def test_kekakuan_pelat_sesuai_rumus():
    D = math_engine.plate_flexural_rigidity(E=25e9, t=0.3, nu=0.2)
    assert pytest.approx(25e9 * 0.3**3 / (12 * (1 - 0.04))) == D


def test_kekakuan_pelat_nu_nol_menyederhanakan():
    assert math_engine.plate_flexural_rigidity(E=1.0, t=2.0, nu=0.0) == pytest.approx(8.0 / 12.0)


@pytest.mark.parametrize(("E", "t", "nu"), [(-1.0, 0.3, 0.2), (25e9, 0.0, 0.2), (25e9, 0.3, 0.6)])
def test_kekakuan_pelat_input_tidak_sah_raise(E: float, t: float, nu: float):
    with pytest.raises(ValueError):
        math_engine.plate_flexural_rigidity(E=E, t=t, nu=nu)


# ---------------------------------------------------------------------------
# Transformasi momen
# ---------------------------------------------------------------------------


def test_theta_nol_adalah_identitas():
    m11, m22, m12 = arr(100.0), arr(40.0), arr(-15.0)
    m_xx, m_yy, m_xy = math_engine.transform_moments(m11, m22, m12, arr(0.0))
    assert m_xx == pytest.approx(m11)
    assert m_yy == pytest.approx(m22)
    assert m_xy == pytest.approx(m12)


def test_theta_90_menukar_mxx_dan_myy():
    m11, m22, m12 = arr(100.0), arr(40.0), arr(0.0)
    m_xx, m_yy, m_xy = math_engine.transform_moments(m11, m22, m12, arr(math.pi / 2))
    assert m_xx == pytest.approx(m22)
    assert m_yy == pytest.approx(m11)
    assert m_xy == pytest.approx(0.0, abs=1e-12)


def test_theta_180_kembali_ke_semula():
    m11, m22, m12 = arr(100.0), arr(40.0), arr(-15.0)
    m_xx, m_yy, m_xy = math_engine.transform_moments(m11, m22, m12, arr(math.pi))
    assert m_xx == pytest.approx(m11)
    assert m_yy == pytest.approx(m22)
    assert m_xy == pytest.approx(m12)


@pytest.mark.parametrize("theta_deg", [0, 17, 30, 45, 90, 123, 180, -37, -90])
def test_jejak_tensor_invariant_terhadap_theta(theta_deg: float):
    """`m_xx + m_yy` adalah invariant tensor -- harus konstan untuk theta apa pun."""
    m11, m22, m12 = arr(100.0), arr(40.0), arr(-15.0)
    m_xx, m_yy, _ = math_engine.transform_moments(m11, m22, m12, arr(math.radians(theta_deg)))
    assert (m_xx + m_yy).item() == pytest.approx(140.0)


@pytest.mark.parametrize("theta_deg", [13, 45, 77, -22])
def test_determinan_tensor_invariant_terhadap_theta(theta_deg: float):
    """`m_xx*m_yy - m_xy^2` juga invariant."""
    m11, m22, m12 = arr(100.0), arr(40.0), arr(-15.0)
    m_xx, m_yy, m_xy = math_engine.transform_moments(m11, m22, m12, arr(math.radians(theta_deg)))
    expected = 100.0 * 40.0 - 15.0**2
    assert (m_xx * m_yy - m_xy**2).item() == pytest.approx(expected)


@pytest.mark.parametrize("theta_deg", [11, 45, 96, -63])
def test_round_trip_transformasi_maju_mundur(theta_deg: float):
    """Transformasi dengan +theta lalu -theta harus mengembalikan nilai semula."""
    m11, m22, m12 = arr(100.0), arr(40.0), arr(-15.0)
    theta = arr(math.radians(theta_deg))
    gx, gy, gxy = math_engine.transform_moments(m11, m22, m12, theta)
    b11, b22, b12 = math_engine.transform_moments(gx, gy, gxy, -theta)
    assert b11 == pytest.approx(m11)
    assert b22 == pytest.approx(m22)
    assert b12 == pytest.approx(m12)


def test_lentur_satu_arah_pada_45_derajat():
    """Momen uniaksial m11 pada 45 deg -> terbagi rata dan menghasilkan puntir."""
    m_xx, m_yy, m_xy = math_engine.transform_moments(
        arr(100.0), arr(0.0), arr(0.0), arr(math.pi / 4)
    )
    assert m_xx == pytest.approx(50.0)
    assert m_yy == pytest.approx(50.0)
    assert m_xy == pytest.approx(50.0)


def test_tensor_isotropik_tidak_berubah_terhadap_rotasi():
    m_xx, m_yy, m_xy = math_engine.transform_moments(
        arr(60.0), arr(60.0), arr(0.0), arr(math.radians(33.0))
    )
    assert m_xx == pytest.approx(60.0)
    assert m_yy == pytest.approx(60.0)
    assert m_xy == pytest.approx(0.0, abs=1e-12)


def test_transformasi_momen_vektor_untuk_banyak_elemen():
    n = 500
    rng = np.random.default_rng(42)
    m11 = rng.normal(size=n) * 100
    m22 = rng.normal(size=n) * 100
    m12 = rng.normal(size=n) * 30
    theta = rng.uniform(-math.pi, math.pi, size=n)

    m_xx, m_yy, m_xy = math_engine.transform_moments(m11, m22, m12, theta)
    assert m_xx.shape == (n,)
    assert np.allclose(m_xx + m_yy, m11 + m22)
    assert np.allclose(m_xx * m_yy - m_xy**2, m11 * m22 - m12**2)


# ---------------------------------------------------------------------------
# Transformasi geser
# ---------------------------------------------------------------------------


def test_geser_theta_nol_identitas():
    q_x, q_y = math_engine.transform_shear(arr(10.0), arr(-4.0), arr(0.0))
    assert q_x == pytest.approx(10.0)
    assert q_y == pytest.approx(-4.0)


def test_geser_theta_90_memutar_vektor():
    q_x, q_y = math_engine.transform_shear(arr(10.0), arr(0.0), arr(math.pi / 2))
    assert q_x == pytest.approx(0.0, abs=1e-12)
    assert q_y == pytest.approx(10.0)


@pytest.mark.parametrize("theta_deg", [0, 23, 67, 145, -88])
def test_magnitudo_geser_invariant(theta_deg: float):
    q1, q2 = arr(12.0), arr(-5.0)
    q_x, q_y = math_engine.transform_shear(q1, q2, arr(math.radians(theta_deg)))
    assert np.hypot(q_x, q_y).item() == pytest.approx(13.0)


def test_geser_round_trip():
    theta = arr(math.radians(41.0))
    q_x, q_y = math_engine.transform_shear(arr(12.0), arr(-5.0), theta)
    b1, b2 = math_engine.transform_shear(q_x, q_y, -theta)
    assert b1 == pytest.approx(12.0)
    assert b2 == pytest.approx(-5.0)


# ---------------------------------------------------------------------------
# Integrasi strip
# ---------------------------------------------------------------------------


def _grid_elements(nx: int, ny: int, dx: float, dy: float):
    """Grid quad seragam; kembalikan (coords (M,4,2), centroids (M,2), areas (M,))."""
    coords, centroids = [], []
    for j in range(ny):
        for i in range(nx):
            x0, y0 = i * dx, j * dy
            coords.append([[x0, y0], [x0 + dx, y0], [x0 + dx, y0 + dy], [x0, y0 + dy]])
            centroids.append([x0 + dx / 2, y0 + dy / 2])
    coords = np.array(coords, dtype=np.float64)
    centroids = np.array(centroids, dtype=np.float64)
    areas = np.full(len(coords), dx * dy, dtype=np.float64)
    return coords, centroids, areas


def test_element_extent():
    coords, _, _ = _grid_elements(2, 2, 0.5, 0.25)
    assert math_engine.element_extent(coords, 0) == pytest.approx(np.full(4, 0.5))
    assert math_engine.element_extent(coords, 1) == pytest.approx(np.full(4, 0.25))


@pytest.mark.parametrize("method", ["exact", "bbox", "area_ratio"])
def test_ketiga_metode_lebar_sama_untuk_quad_persegi(method: str):
    coords, _, areas = _grid_elements(4, 3, 0.5, 0.25)
    widths = math_engine.cut_element_widths(
        coords, areas, cut_axis=0, method=method, cut_position=0.25
    )
    if method == "exact":
        # Hanya elemen yang benar-benar dipotong garis x = 0.25 yang punya lebar.
        mask = math_engine.select_elements_crossing_cut(coords, cut_axis=0, cut_position=0.25)
        assert widths[mask] == pytest.approx(np.full(3, 0.25))
        assert widths[~mask] == pytest.approx(np.zeros(9))
    else:
        assert widths == pytest.approx(np.full(12, 0.25))


def test_metode_lebar_tidak_dikenal_raise():
    coords, _, areas = _grid_elements(2, 2, 0.5, 0.5)
    with pytest.raises(ValueError, match="tidak dikenal"):
        math_engine.cut_element_widths(coords, areas, cut_axis=0, method="ngawur")


def test_metode_exact_tanpa_cut_position_raise():
    coords, _, areas = _grid_elements(2, 2, 0.5, 0.5)
    with pytest.raises(ValueError, match="membutuhkan `cut_position`"):
        math_engine.cut_element_widths(coords, areas, cut_axis=0, method="exact")


# ---------------------------------------------------------------------------
# Panjang potongan eksak & pemilihan elemen yang dipotong
# ---------------------------------------------------------------------------


def test_panjang_potongan_quad_persegi_sama_dengan_tinggi():
    coords, _, _ = _grid_elements(3, 2, 1.0, 0.4)
    lengths = math_engine.cut_intersection_lengths(coords, cut_axis=0, cut_position=0.5)
    # Kolom pertama (x 0..1) terpotong; kolom lain tidak.
    assert lengths[0] == pytest.approx(0.4)
    assert lengths[1] == pytest.approx(0.0)


def test_panjang_potongan_jajar_genjang_sama_dengan_tinggi():
    """Untuk quad yang tergeser murni, garis vertikal tetap memotong tinggi penuh."""
    quad = np.array([[[0.0, 0.0], [1.0, 0.0], [2.0, 1.0], [1.0, 1.0]]])
    exact = math_engine.cut_intersection_lengths(quad, cut_axis=0, cut_position=1.0)
    assert exact[0] == pytest.approx(1.0)
    assert math_engine.element_extent(quad, 1)[0] == pytest.approx(1.0)


def test_panjang_potongan_trapesium_lebih_kecil_dari_bounding_box():
    """Inti perbedaan metode `exact` vs `bbox` (PRD Bagian 7.2(4)).

    Trapesium (0,0)-(2,0)-(1,1)-(0,1) dipotong garis x = 1.5: potongan sebenarnya
    hanya setinggi 0.5, sedangkan rentang bounding box pada sumbu Y tetap 1.0.
    Memakai bounding box akan MELEBIHKAN kontribusi elemen ini 2x lipat.
    """
    trapezium = np.array([[[0.0, 0.0], [2.0, 0.0], [1.0, 1.0], [0.0, 1.0]]])
    exact = math_engine.cut_intersection_lengths(trapezium, cut_axis=0, cut_position=1.5)
    bbox = math_engine.element_extent(trapezium, 1)
    assert exact[0] == pytest.approx(0.5)
    assert bbox[0] == pytest.approx(1.0)
    assert exact[0] < bbox[0]


def test_elemen_terpotong_menutup_lebar_penuh_tanpa_tumpang_tindih():
    nx, ny, dx, dy = 6, 5, 0.5, 0.4
    coords, _, areas = _grid_elements(nx, ny, dx, dy)
    for cut in (0.1, 0.25, 1.0, 1.6, 2.9):
        mask = math_engine.select_elements_crossing_cut(coords, cut_axis=0, cut_position=cut)
        widths = math_engine.cut_element_widths(
            coords, areas, cut_axis=0, method="exact", cut_position=cut
        )
        assert int(mask.sum()) == ny, f"cut={cut} memilih {int(mask.sum())} elemen"
        assert float(np.sum(widths[mask])) == pytest.approx(ny * dy, rel=1e-9)


def test_garis_di_batas_elemen_memilih_satu_sisi_saja():
    """Aturan setengah terbuka mencegah dua kolom terpilih (hasil dua kali lipat)."""
    nx, ny, dx, dy = 6, 5, 0.5, 0.4
    coords, _, _ = _grid_elements(nx, ny, dx, dy)
    mask = math_engine.select_elements_crossing_cut(coords, cut_axis=0, cut_position=1.0)
    assert int(mask.sum()) == ny


def test_garis_di_tepi_terluar_tetap_memilih_elemen():
    nx, ny, dx, dy = 4, 3, 0.5, 0.5
    coords, _, _ = _grid_elements(nx, ny, dx, dy)
    mask = math_engine.select_elements_crossing_cut(coords, cut_axis=0, cut_position=nx * dx)
    assert int(mask.sum()) == ny


def test_crossing_dengan_strip_bounds_butuh_centroids():
    coords, _, _ = _grid_elements(4, 3, 0.5, 0.5)
    with pytest.raises(ValueError, match="membutuhkan `centroids`"):
        math_engine.select_elements_crossing_cut(
            coords, cut_axis=0, cut_position=1.0, strip_bounds=(0.0, 1.0)
        )


def test_integrasi_field_konstan_menghasilkan_nilai_kali_lebar():
    """PRD Bagian 15.1: field momen konstan -> hasil = m x lebar, EKSAK."""
    nx, ny, dx, dy = 8, 6, 0.5, 0.25
    coords, centroids, areas = _grid_elements(nx, ny, dx, dy)
    m = np.full(len(areas), 250.0)

    mask = math_engine.select_nearest_cut_column(
        centroids, cut_axis=0, cut_position=nx * dx / 2, snap_tol=dx * 0.25
    )
    widths = math_engine.cut_element_widths(coords, areas, cut_axis=0, method="bbox")
    total = math_engine.integrate_strip(m, widths, mask)

    assert int(mask.sum()) == ny  # tepat SATU kolom elemen
    assert total == pytest.approx(250.0 * ny * dy)


def test_pita_eksplisit_rapuh_terhadap_posisi_potongan():
    """Justru alasan `select_nearest_cut_column` ada: pita bisa memilih 0 atau 2 kolom."""
    nx, ny, dx, dy = 8, 6, 0.5, 0.25
    _, centroids, _ = _grid_elements(nx, ny, dx, dy)
    batas = 2.0  # tepat di BATAS antar elemen (centroid terdekat: 1.75 dan 2.25)

    kosong = math_engine.select_cut_elements(
        centroids, cut_axis=0, cut_position=batas, half_band=dx / 2 * 0.99
    )
    ganda = math_engine.select_cut_elements(
        centroids, cut_axis=0, cut_position=batas, half_band=dx / 2 * 1.01
    )
    assert int(kosong.sum()) == 0
    assert int(ganda.sum()) == 2 * ny


@pytest.mark.parametrize("cut", [0.0, 1.9, 2.0, 2.1, 2.25, 3.99, 4.0])
def test_nearest_column_selalu_satu_kolom_berapa_pun_posisi_potongan(cut: float):
    nx, ny, dx, dy = 8, 6, 0.5, 0.25
    _, centroids, _ = _grid_elements(nx, ny, dx, dy)
    mask = math_engine.select_nearest_cut_column(
        centroids, cut_axis=0, cut_position=cut, snap_tol=dx * 0.25
    )
    assert int(mask.sum()) == ny


def test_cut_column_position_melaporkan_posisi_aktual():
    nx, ny, dx, dy = 8, 6, 0.5, 0.25
    _, centroids, _ = _grid_elements(nx, ny, dx, dy)
    mask = math_engine.select_nearest_cut_column(
        centroids, cut_axis=0, cut_position=2.0, snap_tol=dx * 0.25
    )
    actual = math_engine.cut_column_position(centroids, mask, cut_axis=0)
    # Diminta 2.0, tetapi mesh hanya punya kolom di 1.75 dan 2.25.
    assert actual in (pytest.approx(1.75), pytest.approx(2.25))
    assert actual != pytest.approx(2.0)


def test_strip_bounds_membatasi_lajur():
    nx, ny, dx, dy = 8, 6, 0.5, 0.25
    _, centroids, _ = _grid_elements(nx, ny, dx, dy)
    mask = math_engine.select_nearest_cut_column(
        centroids,
        cut_axis=0,
        cut_position=2.25,
        snap_tol=dx * 0.25,
        strip_bounds=(0.0, 0.5),
    )
    assert int(mask.sum()) == 2  # hanya dua baris pertama (centroid y = 0.125, 0.375)


def test_strip_bounds_kosong_menghasilkan_mask_kosong():
    _, centroids, _ = _grid_elements(4, 4, 0.5, 0.5)
    mask = math_engine.select_nearest_cut_column(
        centroids, cut_axis=0, cut_position=1.0, snap_tol=0.1, strip_bounds=(100.0, 200.0)
    )
    assert int(mask.sum()) == 0


def test_integrasi_pada_potongan_arah_y():
    nx, ny, dx, dy = 8, 6, 0.5, 0.25
    coords, centroids, areas = _grid_elements(nx, ny, dx, dy)
    m = np.full(len(areas), 100.0)

    mask = math_engine.select_nearest_cut_column(
        centroids, cut_axis=1, cut_position=ny * dy / 2, snap_tol=dy * 0.25
    )
    widths = math_engine.cut_element_widths(coords, areas, cut_axis=1, method="bbox")
    assert int(mask.sum()) == nx
    assert math_engine.integrate_strip(m, widths, mask) == pytest.approx(100.0 * nx * dx)


def test_nan_diabaikan_bukan_meracuni_hasil():
    coords, _, areas = _grid_elements(4, 4, 0.5, 0.5)
    m = np.full(len(areas), 10.0)
    m[0] = np.nan

    mask = np.ones(len(areas), dtype=bool)
    widths = math_engine.cut_element_widths(coords, areas, cut_axis=0, method="bbox")
    total = math_engine.integrate_strip(m, widths, mask)
    assert math.isfinite(total)
    assert total == pytest.approx(10.0 * 0.5 * 15)


def test_seluruh_nan_menghasilkan_nan():
    coords, _, areas = _grid_elements(2, 2, 0.5, 0.5)
    m = np.full(len(areas), np.nan)
    widths = math_engine.cut_element_widths(coords, areas, cut_axis=0, method="bbox")
    assert math.isnan(math_engine.integrate_strip(m, widths, np.ones(len(areas), dtype=bool)))


def test_lajur_kosong_menghasilkan_nan():
    coords, _, areas = _grid_elements(2, 2, 0.5, 0.5)
    widths = math_engine.cut_element_widths(coords, areas, cut_axis=0, method="bbox")
    empty = np.zeros(len(areas), dtype=bool)
    assert math.isnan(math_engine.integrate_strip(np.zeros(len(areas)), widths, empty))


# ---------------------------------------------------------------------------
# Wood-Armer
# ---------------------------------------------------------------------------


def test_wood_armer_raise_dengan_alasan_eksplisit():
    """PRD Bagian 7.2(6): aturan koreksi wajib dari sumber primer, bukan dari ingatan."""
    with pytest.raises(NotImplementedError, match="sumber primer"):
        math_engine.wood_armer(arr(100.0), arr(50.0), arr(20.0))


def test_math_engine_tidak_mengimpor_solver_atau_plotting():
    """PRD Core 7: pemisahan tanggung jawab dijaga otomatis, bukan hanya lewat niat."""
    import inspect

    source = inspect.getsource(math_engine)
    for forbidden in ("import gmsh", "import openseespy", "import matplotlib", "from gmsh"):
        assert forbidden not in source, f"math_engine tidak boleh memuat {forbidden!r}"
