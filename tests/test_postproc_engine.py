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


# ---------------------------------------------------------------------------
# Envelope (PRD Bagian 12, Cond C)
# ---------------------------------------------------------------------------


def _fake_results(combo: str, m_xx, m_yy=None) -> postproc_engine.ElementResults:
    """`ElementResults` sintetis dengan nilai yang dikendalikan penuh."""
    values = np.asarray(m_xx, dtype=np.float64)
    other = np.asarray(m_yy if m_yy is not None else m_xx, dtype=np.float64)
    zeros = np.zeros_like(values)
    return postproc_engine.ElementResults(
        combo=combo,
        m11=zeros,
        m22=zeros,
        m12=zeros,
        q1=zeros,
        q2=zeros,
        p11=zeros,
        p22=zeros,
        p12=zeros,
        m_xx=values,
        m_yy=other,
        m_xy=zeros,
        q_x=zeros,
        q_y=zeros,
        theta=zeros,
        raw_gauss=np.zeros((len(values), 4, 8)),
    )


def test_envelope_memilih_ekstrem_per_lokasi():
    """`fmax`/`fmin` per LOKASI, bukan per kombinasi secara keseluruhan."""
    env = postproc_engine.build_envelope(
        {
            "A": _fake_results("A", [10.0, -5.0, 3.0]),
            "B": _fake_results("B", [-2.0, 8.0, 3.0]),
        },
        fields=("m_xx",),
    )
    field = env.fields["m_xx"]
    assert field.max_values == pytest.approx([10.0, 8.0, 3.0])
    assert field.min_values == pytest.approx([-2.0, -5.0, 3.0])


def test_envelope_governing_combo_menunjuk_kombinasi_yang_tepat():
    """Tanpa kolom governing, envelope tidak auditable (PRD Bagian 12)."""
    env = postproc_engine.build_envelope(
        {
            "1.2D+1.6L": _fake_results("1.2D+1.6L", [10.0, -5.0]),
            "1.2D+1.0W": _fake_results("1.2D+1.0W", [-2.0, 8.0]),
        },
        fields=("m_xx",),
    )
    assert env.governing_names("m_xx", "max") == ["1.2D+1.6L", "1.2D+1.0W"]
    assert env.governing_names("m_xx", "min") == ["1.2D+1.0W", "1.2D+1.6L"]


def test_envelope_positif_dan_negatif_dipisah():
    """Maksimum menentukan tulangan bawah, minimum menentukan tulangan atas."""
    env = postproc_engine.build_envelope({"A": _fake_results("A", [5.0, -5.0])}, fields=("m_xx",))
    field = env.fields["m_xx"]
    assert field.max_values == pytest.approx([5.0, -5.0])
    assert field.min_values == pytest.approx([5.0, -5.0])


def test_envelope_mengabaikan_nan_pada_sebagian_kombinasi():
    env = postproc_engine.build_envelope(
        {
            "A": _fake_results("A", [np.nan, 4.0]),
            "B": _fake_results("B", [7.0, np.nan]),
        },
        fields=("m_xx",),
    )
    field = env.fields["m_xx"]
    assert field.max_values == pytest.approx([7.0, 4.0])
    assert env.governing_names("m_xx", "max") == ["B", "A"]


def test_envelope_seluruh_nan_menghasilkan_nan():
    env = postproc_engine.build_envelope(
        {"A": _fake_results("A", [np.nan]), "B": _fake_results("B", [np.nan])},
        fields=("m_xx",),
    )
    assert np.isnan(env.fields["m_xx"].max_values[0])


def test_envelope_kosong_raise():
    with pytest.raises(ValueError, match="Tidak ada kombinasi"):
        postproc_engine.build_envelope({})


def test_envelope_jumlah_elemen_berbeda_raise():
    with pytest.raises(ValueError, match="mesh yang sama"):
        postproc_engine.build_envelope(
            {"A": _fake_results("A", [1.0, 2.0]), "B": _fake_results("B", [1.0])},
            fields=("m_xx",),
        )


def test_envelope_combo_name_di_luar_rentang_aman():
    env = postproc_engine.build_envelope({"A": _fake_results("A", [1.0])}, fields=("m_xx",))
    assert env.combo_name(0) == "A"
    assert env.combo_name(99) == "-"


# ---------------------------------------------------------------------------
# Geser (PRD Bagian 7.2(7)) -- DEMAND SAJA
# ---------------------------------------------------------------------------


def _pilecap_geom():
    from pilecap_fem.geometry_builder import (
        EntityResolution,
        GeometryModel,
        GeometryResolution,
        Pier,
        Pile,
        polygon_from_rect,
    )

    return GeometryModel(
        pilecap=polygon_from_rect(8.0, 8.0, (0.0, 0.0)),
        thickness=1.0,
        piles=tuple(
            Pile(pile_id=f"P{i + 1}", x=x, y=y, diameter=0.8)
            for i, (x, y) in enumerate([(-2.5, -2.5), (2.5, -2.5), (-2.5, 2.5), (2.5, 2.5)])
        ),
        piers=(
            Pier(
                pier_id="PIER1",
                shape="rectangular",
                centerline=(0.0, 0.0),
                width_x=1.0,
                width_y=1.0,
            ),
        ),
        resolution=GeometryResolution(
            pilecap=EntityResolution(source="json_standard"),
            pile=EntityResolution(source="json_grid"),
            pier=EntityResolution(source="json_standard"),
        ),
    )


def test_effective_depth():
    geom = _pilecap_geom()
    assert postproc_engine.effective_depth(geom, 0.075) == pytest.approx(0.925)


def test_effective_depth_negatif_raise():
    geom = _pilecap_geom()
    with pytest.raises(ValueError, match="Tinggi efektif"):
        postproc_engine.effective_depth(geom, 1.5)


def test_pier_face_cuts_dari_bounding_box():
    geom = _pilecap_geom()
    faces = postproc_engine.pier_face_cuts(geom.piers[0])
    assert faces["x"] == pytest.approx((-0.5, 0.5))
    assert faces["y"] == pytest.approx((-0.5, 0.5))


def test_punching_bo_sesuai_hitungan_tangan():
    """Pier 1.0 x 1.0, d = 0.4 -> penampang 1.4 x 1.4, b_o = 5.6 m."""
    geom = _pilecap_geom()
    pz = {p.pile_id: 1000.0e3 for p in geom.piles}
    check = postproc_engine.punching_shear(geom, geom.piers[0], pz, d=0.4)
    assert check.b_o_m == pytest.approx(5.6, rel=1e-6)
    assert check.V_u_N == pytest.approx(4_000_000.0)
    assert check.v_u_Pa == pytest.approx(4_000_000.0 / (5.6 * 0.4))
    assert check.capacity_status == "NOT_EVALUATED"


def test_punching_mengecualikan_pile_di_dalam_penampang_kritis():
    """Pile di dalam perimeter tidak menyeberang -- dan itu DINYATAKAN di catatan."""
    geom = _pilecap_geom()
    pz = {p.pile_id: 1000.0e3 for p in geom.piles}
    # d besar -> penampang kritis melebar melewati seluruh pile.
    check = postproc_engine.punching_shear(geom, geom.piers[0], pz, d=6.0)
    assert check.V_u_N == pytest.approx(0.0)
    assert "DI DALAM penampang kritis" in check.note


def test_shear_demand_menghasilkan_baris_untuk_setiap_pier(analysed):
    mesh, _, results = analysed
    geom = _pilecap_geom()
    pz = {p.pile_id: 1000.0e3 for p in geom.piles}
    checks = postproc_engine.shear_demand(results, mesh, geom, pz, cover_m=0.075)
    kinds = {c.kind for c in checks}
    assert "punching" in kinds
    assert {"one_way_x_min", "one_way_x_maks", "one_way_y_min", "one_way_y_maks"} <= kinds
    assert all(c.capacity_status == "NOT_EVALUATED" for c in checks)
    assert all("belum dikonfirmasi" in c.note for c in checks)


def test_penampang_di_luar_pilecap_ditandai_bukan_diam(analysed):
    """Penampang yang jatuh di luar pelat harus BERBICARA, bukan menghasilkan angka palsu."""
    mesh, _, results = analysed
    geom = _pilecap_geom()
    checks = postproc_engine.one_way_shear(results, mesh, geom.piers[0], d=50.0)
    assert all(np.isnan(c.V_u_N) for c in checks)
    assert all("DI LUAR pilecap" in c.note for c in checks)


# ---------------------------------------------------------------------------
# Rasio deep pile cap -- DILAPORKAN TANPA VONIS
# ---------------------------------------------------------------------------


def test_rasio_deep_pilecap_dilaporkan_tanpa_vonis():
    """PRD Bagian 17 item 5 terbuka: tool tidak boleh menyimpulkan deep/tidak."""
    geom = _pilecap_geom()
    ratio = postproc_engine.shear_span_ratio(geom, cover_m=0.075)
    assert ratio["verdict"] == "TIDAK DINILAI"
    assert "belum dikonfirmasi" in ratio["note"]
    assert ratio["d_m"] == pytest.approx(0.925)
    # a = jarak muka pier (0.5) ke pusat pile terdekat; pile di (2.5, 2.5).
    assert ratio["min_a_over_d"] > 0.0
    assert len(ratio["rows"]) == geom.n_piles * geom.n_piers


# ---------------------------------------------------------------------------
# Momen desain di muka pier
# ---------------------------------------------------------------------------


def test_design_moment_sections_menandai_nilai_puncak_sebagai_singular(analysed):
    """PRD Bagian 7.2(5): nilai peak dilaporkan TAPI ditandai singularitas numerik."""
    mesh, _, results = analysed
    geom = _pilecap_geom()
    rows = postproc_engine.design_moment_sections(
        results, mesh, geom, n_strips_x=2, n_strips_y=2, mesh_size=LX / NX, moment_at="both"
    )
    assert any(r["singular"] for r in rows)
    assert any(not r["singular"] for r in rows)
    assert {r["lokasi"] for r in rows} == {"muka_pier", "peak"}


def test_design_moment_sections_default_hanya_muka_pier(analysed):
    mesh, _, results = analysed
    geom = _pilecap_geom()
    rows = postproc_engine.design_moment_sections(
        results, mesh, geom, n_strips_x=2, n_strips_y=2, mesh_size=LX / NX
    )
    assert {r["lokasi"] for r in rows} == {"muka_pier"}
    assert not any(r["singular"] for r in rows)


def test_design_moment_sections_moment_at_tidak_dikenal_raise(analysed):
    mesh, _, results = analysed
    with pytest.raises(ValueError, match="pier_face"):
        postproc_engine.design_moment_sections(
            results,
            mesh,
            _pilecap_geom(),
            n_strips_x=2,
            n_strips_y=2,
            mesh_size=0.2,
            moment_at="ngawur",
        )


def test_traceability_sample_menolak_hasil_tanpa_titik_gauss(analysed):
    """Hasil yang dibaca ulang dari CSV tidak punya nilai Gauss -- harus BERBICARA."""
    mesh, _, _ = analysed
    tanpa_gauss = _fake_results("X", np.ones(mesh.n_elements))
    tanpa_gauss = postproc_engine.ElementResults(
        **{**vars(tanpa_gauss), "raw_gauss": np.zeros((mesh.n_elements, 0, 0))}
    )
    with pytest.raises(ValueError, match=r"traceability_sample.json"):
        postproc_engine.traceability_sample(tanpa_gauss, mesh, 0)
