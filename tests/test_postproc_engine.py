"""Test `postproc_engine.py` (PRD Bagian 15.1 & 15.4 -- target coverage >= 90%).

Memakai pelat satu arah yang sama dengan VC-3, sehingga jawabannya diketahui dari
statika eksak dan setiap angka dapat diperiksa dengan tangan.
"""

from __future__ import annotations

import numpy as np
import pytest
from validation_helpers import (
    EdgeSupport,
    UniformPressure,
    elastic_material,
    structured_plate,
)

from pilecap_fem import config, fem_engine, postproc_engine

pytestmark = pytest.mark.slow

LX, LY, NX, NY = 4.0, 2.0, 20, 10
PRESSURE = 1000.0


@pytest.fixture(scope="module")
def analysed():
    mesh = structured_plate(LX, LY, NX, NY)
    result = fem_engine.analyze_combo(
        mesh,
        geom=None,
        material=elastic_material(nu=0.0, t=0.1),
        options=fem_engine.AnalysisOptions(equilibrium_rtol=1e-6),
        combo="POST",
        pz_by_pile={},
        load_strategy=UniformPressure(-PRESSURE),
        support_strategy=EdgeSupport(span_axis=0, span_start=0.0, span_end=LX),
    )
    return mesh, result, postproc_engine.compute_element_results(result, mesh)


# ---------------------------------------------------------------------------
# compute_element_results
# ---------------------------------------------------------------------------


def test_bentuk_array_hasil(analysed):
    mesh, _, results = analysed
    assert results.n_elements == mesh.n_elements
    for field in ("m11", "m22", "m12", "q1", "q2", "m_xx", "m_yy", "m_xy", "q_x", "q_y"):
        assert getattr(results, field).shape == (mesh.n_elements,)
    assert results.raw_gauss.shape == (
        mesh.n_elements,
        config.SHELL_N_GAUSS,
        config.SHELL_N_RESULTANT_COMPONENTS,
    )


def test_bentuk_resultant_salah_raise(analysed):
    mesh, result, _ = analysed
    from dataclasses import replace

    rusak = replace(result, local_resultants=result.local_resultants[:, :, :6])
    with pytest.raises(ValueError, match="tidak sesuai harapan"):
        postproc_engine.compute_element_results(rusak, mesh)


def test_theta_eksplisit_menggantikan_theta_mesh(analysed):
    """VC-2 memakai jalur ini untuk menguji transformasi terhadap sudut yang diketahui."""
    mesh, result, bawaan = analysed
    diputar = postproc_engine.compute_element_results(
        result, mesh, theta=np.full(mesh.n_elements, np.pi / 2)
    )
    # theta = 90 deg menukar peran sumbu: m_xx global menjadi m22 lokal.
    assert np.allclose(diputar.m_xx, bawaan.m22)
    assert np.allclose(diputar.m_yy, bawaan.m11)


def test_q_magnitude_konsisten(analysed):
    _, _, results = analysed
    assert np.allclose(results.q_magnitude, np.hypot(results.q_x, results.q_y))


def test_extreme_mengembalikan_indeks_dan_nilai(analysed):
    _, _, results = analysed
    index, value = results.extreme("m_xx")
    assert 0 <= index < results.n_elements
    assert value == pytest.approx(results.m_xx[index])
    assert abs(value) == pytest.approx(np.max(np.abs(results.m_xx)))


def test_faktor_tanda_benar_benar_diterapkan(analysed):
    """Nilai lokal harus = faktor koreksi x rata-rata Gauss mentah."""
    _, _, results = analysed
    mentah = results.raw_gauss.mean(axis=1)
    assert np.allclose(results.m11, config.MOMENT_SIGN_FACTOR * mentah[:, postproc_engine.IDX_M11])
    assert np.allclose(results.q1, config.SHEAR_SIGN_FACTOR * mentah[:, postproc_engine.IDX_Q1])
    assert np.allclose(
        results.p11, config.MEMBRANE_SIGN_FACTOR * mentah[:, postproc_engine.IDX_P11]
    )


# ---------------------------------------------------------------------------
# traceability_sample (PRD Bagian 9.4 bagian 5)
# ---------------------------------------------------------------------------


def test_traceability_sample_memuat_rantai_lengkap(analysed):
    mesh, _, results = analysed
    index, _ = results.extreme("m_xx")
    sample = postproc_engine.traceability_sample(results, mesh, index)

    for key in (
        "element_tag",
        "group",
        "centroid_m",
        "node_coords_m",
        "gauss_raw",
        "gauss_mean",
        "sign_factors",
        "local_after_sign",
        "theta_deg",
        "global",
        "formula",
    ):
        assert key in sample, f"rantai telusur kehilangan {key!r}"

    assert len(sample["node_coords_m"]) == 4
    assert sample["gauss_raw"]["response_name"] == config.SHELL_RESULTANT_RESPONSE
    assert sample["gauss_raw"]["component_order"] == list(config.RESULTANT_COMPONENT_ORDER)
    assert len(sample["gauss_raw"]["values"]) == config.SHELL_N_GAUSS


def test_traceability_sample_dapat_dihitung_ulang_dengan_tangan(analysed):
    """Angka di rantai telusur harus benar-benar menghasilkan nilai global yang sama."""
    mesh, _, results = analysed
    index, _ = results.extreme("m_xx")
    sample = postproc_engine.traceability_sample(results, mesh, index)

    mean = np.array(sample["gauss_mean"])
    factor = sample["sign_factors"]["moment"]
    m11 = factor * mean[postproc_engine.IDX_M11]
    m22 = factor * mean[postproc_engine.IDX_M22]
    m12 = factor * mean[postproc_engine.IDX_M12]
    assert m11 == pytest.approx(sample["local_after_sign"]["m11"])

    theta = np.radians(sample["theta_deg"])
    c, s = np.cos(theta), np.sin(theta)
    m_xx = m11 * c * c + m22 * s * s - 2 * m12 * s * c
    assert m_xx == pytest.approx(sample["global"]["m_xx"], rel=1e-9)


# ---------------------------------------------------------------------------
# strip_moments (PRD Bagian 7.2(4))
# ---------------------------------------------------------------------------


def test_strip_moments_menjumlah_ke_momen_total_statika(analysed):
    """Jumlah seluruh lajur pada satu potongan = momen total statika eksak."""
    mesh, _, results = analysed
    cut = LX / 2 - LX / NX / 2  # di tengah kolom elemen
    rows = postproc_engine.strip_moments(
        results,
        mesh,
        direction="x",
        n_strips=5,
        cut_position=cut,
        mesh_size=LX / NX,
    )

    assert len(rows) == 5
    assert all(r["n_elements"] > 0 for r in rows)
    total = sum(r["M_total_Nm"] for r in rows)
    exact = PRESSURE * LY * (LX * cut - cut**2) / 2.0
    assert total == pytest.approx(exact, rel=3e-2)


def test_strip_moments_mencatat_posisi_potongan_aktual(analysed):
    """Selisih posisi yang diminta vs yang dipakai WAJIB terlihat checker."""
    mesh, _, results = analysed
    rows = postproc_engine.strip_moments(
        results, mesh, direction="x", n_strips=3, cut_position=LX / 2, mesh_size=LX / NX
    )
    for row in rows:
        assert row["cut_requested_m"] == pytest.approx(LX / 2)
        assert np.isfinite(row["cut_actual_m"])
        assert row["width_method"] == "exact"


def test_strip_moments_arah_y(analysed):
    mesh, _, results = analysed
    rows = postproc_engine.strip_moments(
        results, mesh, direction="y", n_strips=4, cut_position=LY / 2, mesh_size=LY / NY
    )
    assert len(rows) == 4
    assert all(r["direction"] == "y" for r in rows)
    # Lentur satu arah sepanjang X dengan nu = 0 -> M_y praktis nol.
    assert abs(sum(r["M_total_Nm"] for r in rows)) < 0.02 * PRESSURE * LY * LX**2 / 8


def test_strip_moments_arah_tidak_dikenal_raise(analysed):
    mesh, _, results = analysed
    with pytest.raises(ValueError, match="harus 'x' atau 'y'"):
        postproc_engine.strip_moments(
            results, mesh, direction="z", n_strips=3, cut_position=1.0, mesh_size=0.2
        )


def test_strip_moments_batas_lajur_menutup_seluruh_lebar(analysed):
    mesh, _, results = analysed
    rows = postproc_engine.strip_moments(
        results, mesh, direction="x", n_strips=5, cut_position=LX / 2, mesh_size=LX / NX
    )
    total_elemen = sum(r["n_elements"] for r in rows)
    # Setiap elemen pada kolom potongan masuk tepat satu lajur.
    assert total_elemen == NY
