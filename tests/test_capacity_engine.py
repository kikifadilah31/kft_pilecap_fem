"""Test adapter `capacity_engine` ke `shell-kit` (PRD Bagian 7.2(6)-(7), Bagian 1.3).

Fokus test ini BUKAN membuktikan rumus SNI benar -- itu tanggung jawab `shell-kit` dan
test-nya sendiri. Yang dibuktikan di sini adalah bahwa adapter **tidak mengubah angka**
di perbatasan satuan, dan bahwa hal-hal yang tidak boleh diam-diam (default `fy`, `NaN`
yang bermakna ganda, momen bertanda) memang tidak terjadi diam-diam.
"""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from shell_kit import rebar as sk_rebar

from pilecap_fem import capacity_engine as ce
from pilecap_fem import config
from pilecap_fem.validators import InputError

# f'c 30 MPa, fy 420 MPa, t 1200 mm, selimut 75 mm, spasi 150 mm -- dalam SI.
INPUTS = ce.CapacityInputs(
    fc=30e6,
    fy=420e6,
    thickness=1.2,
    cover=0.075,
    spacing=0.15,
    phi_flexure=0.9,
    phi_shear=0.75,
    phi_source="test",
    fy_source="test",
    stirrup_spacing_long=0.200,
    stirrup_spacing_trans=0.200,
)


def _config_si(**design_override: object) -> dict:
    design: dict[str, object] = {
        "fy": 420e6,
        "fy_source": "test",
        "rebar_mode": "spacing_fixed",
        "rebar_spacing": 0.15,
        "cover": 0.075,
        "phi_flexure": None,
        "phi_shear": None,
        "stirrup_spacing_long": 0.200,
        "stirrup_spacing_trans": 0.200,
    }
    design.update(design_override)
    return {
        "material": {"fc": 30e6},
        "pilecap": {"thickness": 1.2},
        "design": design,
    }


# ---------------------------------------------------------------------------
# Perbatasan satuan
# ---------------------------------------------------------------------------


def test_konversi_si_ke_satuan_shell_kit():
    assert INPUTS.fc_mpa == pytest.approx(30.0)
    assert INPUTS.fy_mpa == pytest.approx(420.0)
    assert INPUTS.thickness_mm == pytest.approx(1200.0)
    assert INPUTS.cover_mm == pytest.approx(75.0)
    assert INPUTS.spacing_mm == pytest.approx(150.0)


def test_adapter_tidak_mengubah_angka_shell_kit():
    """Hasil `flexure_design` identik dengan memanggil `shell_kit.rebar` langsung.

    Inilah pembuktian bahwa lapisan konversi SI <-> satuan teknik pulang-pergi tanpa
    kehilangan apa pun. Bila suatu saat faktor `config.DISPLAY_UNITS` diubah, test ini
    yang menangkapnya -- bukan laporan desain di lapangan.
    """
    moments = np.array([642_323.4, 1_200_000.0, 55_000.0, 2_988_600.0])  # N.m/m, positif

    design = ce.flexure_design(moments, INPUTS, direction="x", face="bawah")

    as_ref, d_ref, dia_ref, _ = sk_rebar.solve_rebar_iterative(
        moments / 1e3,  # N.m/m -> kN.m/m
        30.0,
        420.0,
        1200.0,
        75.0,
        "x",
        1,
        150.0,
        phi=0.9,
    )
    assert np.allclose(design.as_required * 1e6, as_ref, equal_nan=True)
    assert np.allclose(design.d_effective * 1e3, d_ref, equal_nan=True)
    assert np.allclose(design.bar_diameter * 1e3, dia_ref, equal_nan=True)


def test_as_min_dari_shell_kit_bukan_angka_sendiri():
    design = ce.flexure_design(np.array([0.0]), INPUTS, direction="x", face="bawah")
    expected = sk_rebar.calc_as_min_per_face(420.0, 1200.0)
    assert design.as_min * 1e6 == pytest.approx(expected)


def test_kedalaman_efektif_berbeda_antar_arah():
    """Arah X lapis luar, Y lapis dalam -- perbedaan itu harus sampai ke hasil."""
    moments = np.array([642_323.4])
    d_x = ce.flexure_design(moments, INPUTS, direction="x", face="bawah").d_effective[0]
    d_y = ce.flexure_design(moments, INPUTS, direction="y", face="bawah").d_effective[0]
    assert d_x > d_y


# ---------------------------------------------------------------------------
# Momen bertanda -> muka
# ---------------------------------------------------------------------------


def test_momen_bertanda_dipisah_per_muka():
    """`calc_as_required` tidak mengambil |.|; pemisahan muka WAJIB dilakukan adapter.

    Tanpa pemisahan ini, momen negatif menghasilkan luas tulangan NEGATIF -- angka yang
    akan lolos ke laporan tanpa satu pun tanda bahaya.
    """
    moments = np.array([500_000.0, -300_000.0, 0.0])

    bawah = ce.flexure_design(moments, INPUTS, direction="x", face="bawah")
    atas = ce.flexure_design(moments, INPUTS, direction="x", face="atas")

    assert bawah.mu.tolist() == [500_000.0, 0.0, 0.0]
    assert atas.mu.tolist() == [0.0, 300_000.0, 0.0]
    assert np.all(bawah.as_required >= 0.0)
    assert np.all(atas.as_required >= 0.0)


def test_face_tidak_dikenal_ditolak():
    with pytest.raises(ValueError, match="bawah"):
        ce.flexure_design(np.array([1.0]), INPUTS, direction="x", face="samping")


def test_direction_tidak_dikenal_ditolak():
    with pytest.raises(ValueError, match="'x' atau 'y'"):
        ce.flexure_design(np.array([1.0]), INPUTS, direction="z", face="bawah")


# ---------------------------------------------------------------------------
# NaN shell-kit -> status eksplisit
# ---------------------------------------------------------------------------


def test_penampang_tidak_memadai_bukan_nan_diam_diam():
    """`np.nan` shell-kit ("tidak memadai") tidak boleh tampil sebagai "tidak ada data".

    Momen 20.000 kN.m/m pada pelat 1,2 m jelas melampaui batas kendali tarik.
    """
    design = ce.flexure_design(np.array([20e9]), INPUTS, direction="x", face="bawah")
    assert design.status[0] == ce.STATUS_SECTION_INADEQUATE
    assert not np.isfinite(design.as_required[0])
    assert design.n_inadequate == 1


def test_momen_nol_ditandai_tanpa_momen():
    design = ce.flexure_design(np.array([0.0]), INPUTS, direction="x", face="bawah")
    assert design.status[0] == ce.STATUS_NO_MOMENT


def test_momen_nan_ditandai_tidak_terdefinisi():
    design = ce.flexure_design(np.array([np.nan]), INPUTS, direction="x", face="bawah")
    assert design.status[0] == ce.STATUS_UNDEFINED


def test_as_design_memakai_minimum_bila_perlu_lebih_kecil():
    design = ce.flexure_design(np.array([10_000.0]), INPUTS, direction="x", face="bawah")
    assert ce.as_design_array(design)[0] == pytest.approx(design.as_min)


def test_as_design_mempertahankan_nan():
    design = ce.flexure_design(np.array([20e9]), INPUTS, direction="x", face="bawah")
    assert not np.isfinite(ce.as_design_array(design)[0])


# ---------------------------------------------------------------------------
# Geser satu arah
# ---------------------------------------------------------------------------


def test_kapasitas_geser_satu_arah_sama_dengan_shell_kit():
    capacity = ce.one_way_shear_capacity(200e3, 1.117, INPUTS, label="uji")
    assert capacity.v_c == pytest.approx(sk_rebar.calc_Vc(30.0, 1000.0, 1117.0))
    assert capacity.v_s_max == pytest.approx(sk_rebar.calc_Vs_max(30.0, 1000.0, 1117.0))
    assert capacity.phi_v_c == pytest.approx(0.75 * capacity.v_c)
    assert capacity.demand_capacity_ratio == pytest.approx(200e3 / capacity.phi_v_c)


def test_geser_tanda_negatif_dipakai_besarannya():
    naik = ce.one_way_shear_capacity(200e3, 1.117, INPUTS, label="+")
    turun = ce.one_way_shear_capacity(-200e3, 1.117, INPUTS, label="-")
    assert turun.demand_capacity_ratio == pytest.approx(naik.demand_capacity_ratio)


def test_geser_dengan_d_tidak_valid_tidak_terdefinisi():
    capacity = ce.one_way_shear_capacity(200e3, 0.0, INPUTS, label="uji")
    assert capacity.status == ce.STATUS_UNDEFINED
    assert not np.isfinite(capacity.v_c)


def test_pons_dilewati_bukan_dihitung_dengan_rumus_satu_arah():
    """Rumus geser satu arah TIDAK boleh dipakai untuk pons.

    `calc_Vc` memakai `b_w x d_v`; memakainya untuk keruntuhan dua arah berarti menerapkan
    rumus di luar lingkupnya. Pons harus benar-benar tidak muncul di hasil.
    """
    from pilecap_fem.postproc_engine import ShearCheck

    checks = [
        ShearCheck(
            pier_id="PIER1",
            kind="one_way_x_min",
            d_m=1.117,
            location_m=-1.7,
            b_o_m=4.8,
            V_u_N=960e3,
            v_u_Pa=None,
            capacity_status="NOT_EVALUATED",
            note="",
        ),
        ShearCheck(
            pier_id="PIER1",
            kind="punching",
            d_m=1.117,
            location_m=None,
            b_o_m=9.2,
            V_u_N=5000e3,
            v_u_Pa=None,
            capacity_status="NOT_EVALUATED",
            note="",
        ),
    ]
    capacities = ce.one_way_shear_from_checks(checks, INPUTS)

    assert set(capacities) == {"PIER1|one_way_x_min"}
    assert capacities["PIER1|one_way_x_min"].v_u == pytest.approx(960e3 / 4.8)


# ---------------------------------------------------------------------------
# Desain per lajur
# ---------------------------------------------------------------------------


def _strip_row(**over: object) -> dict:
    row: dict[str, object] = {
        "strip": 1,
        "direction": "x",
        "pier_id": "PIER1",
        "sisi": "maks",
        "lokasi": "muka_pier",
        "M_total_Nm": 556_250.0 * 2.0,
        "width_m": 2.0,
        "singular": False,
    }
    row.update(over)
    return row


def test_desain_lajur_memakai_lebar_terintegrasi():
    """`Mu` per satuan lebar = `M_total / width_m`, bukan lebar nominal lajur."""
    rows = ce.strip_flexure_design([_strip_row()], INPUTS)
    assert rows[0]["Mu_per_m_Nm"] == pytest.approx(556_250.0)
    assert rows[0]["face"] == "bawah"
    assert rows[0]["status"] == ce.STATUS_OK


def test_desain_lajur_momen_negatif_ke_muka_atas():
    rows = ce.strip_flexure_design([_strip_row(M_total_Nm=-800_000.0)], INPUTS)
    assert rows[0]["face"] == "atas"
    assert rows[0]["Mu_per_m_Nm"] == pytest.approx(400_000.0)


def test_desain_lajur_lebar_nol_tidak_terdefinisi():
    rows = ce.strip_flexure_design([_strip_row(width_m=0.0)], INPUTS)
    assert rows[0]["status"] == ce.STATUS_UNDEFINED


def test_governing_mengabaikan_nilai_singular():
    """Nilai `peak` bertanda SINGULAR bukan momen desain, jadi tidak boleh governing."""
    by_combo = {
        "K1": ce.strip_flexure_design([_strip_row()], INPUTS),
        "K2": ce.strip_flexure_design(
            [_strip_row(M_total_Nm=9_000_000.0, lokasi="peak", singular=True)], INPUTS
        ),
    }
    governing = ce.governing_strip_design(by_combo)
    assert len(governing) == 1
    assert governing[0]["combo"] == "K1"


def test_governing_memilih_kombinasi_terbesar():
    by_combo = {
        "K1": ce.strip_flexure_design([_strip_row()], INPUTS),
        "K2": ce.strip_flexure_design([_strip_row(M_total_Nm=1_600_000.0)], INPUTS),
    }
    governing = ce.governing_strip_design(by_combo)
    assert governing[0]["combo"] == "K2"


# ---------------------------------------------------------------------------
# Masukan wajib -- tidak ada default diam-diam
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("override", "pesan"),
    [
        ({"fy": None}, "design.fy"),
        ({"fy_source": None}, "design.fy_source"),
        ({"fy_source": "  "}, "design.fy_source"),
        ({"rebar_spacing": None}, "design.rebar_spacing"),
        ({"cover": None}, "design.cover"),
        ({"phi_flexure": 1.5}, "phi_flexure"),
        ({"phi_shear": 0.0}, "phi_shear"),
    ],
)
def test_masukan_kurang_atau_di_luar_rentang_raise(override: dict, pesan: str):
    with pytest.raises(InputError, match=pesan):
        ce.CapacityInputs.from_config(_config_si(**override))


def test_fy_default_shell_kit_tidak_dipakai_diam_diam():
    """`shell_kit.rebar.DEFAULT_FY` ada, tetapi tool ini tidak boleh memakainya sendiri."""
    assert hasattr(sk_rebar, "DEFAULT_FY")
    with pytest.raises(InputError):
        ce.CapacityInputs.from_config(_config_si(fy=None))


def test_selimut_setengah_tebal_ditolak():
    with pytest.raises(InputError, match="tidak masuk akal"):
        ce.CapacityInputs.from_config(_config_si(cover=0.6))


def test_phi_kosong_memakai_konstanta_shell_kit_dan_mencatat_asalnya():
    inputs = ce.CapacityInputs.from_config(_config_si())
    assert inputs.phi_flexure == pytest.approx(sk_rebar.PHI_FLEXURE)
    assert inputs.phi_shear == pytest.approx(sk_rebar.PHI_SHEAR)
    assert "shell-kit" in inputs.phi_source


def test_phi_dari_user_menang_dan_asalnya_dicatat():
    inputs = ce.CapacityInputs.from_config(_config_si(phi_flexure=0.85))
    assert inputs.phi_flexure == pytest.approx(0.85)
    assert inputs.phi_source == "config user"


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


def test_provenance_memuat_versi_pasal_dan_kedua_peringatan():
    block = ce.provenance_block(INPUTS)
    assert block["engine"] == "shell-kit"
    assert block["engine_version"] != "?"
    assert block["standard"] == "SNI 2847:2019"
    assert "22.5.5.1" in block["clauses"]["Vc"]
    assert "pons" in block["catatan_pons"].lower()
    assert "deep member" in block["peringatan_deep_pilecap"]
    assert block["fy_source"] == "test"


def test_design_all_faces_menghasilkan_keempat_kombinasi():
    moments = {"x": np.array([500_000.0, -200_000.0]), "y": np.array([300_000.0, 100_000.0])}
    designs = ce.design_all_faces(moments, INPUTS)
    assert set(designs) == set(config.REBAR_FACES)
    assert designs[("x", "atas")].mu.tolist() == [0.0, 200_000.0]


# ---------------------------------------------------------------------------
# Seleksi batang -- tiga mode
# ---------------------------------------------------------------------------


def _design_x(inputs: ce.CapacityInputs) -> ce.FlexureDesign:
    """Momen yang menutup rentang: kecil (As_min), sedang, besar."""
    moments = np.array([50_000.0, 642_323.4, 1_800_000.0, 0.0])
    return ce.flexure_design(moments, inputs, direction="x", face="bawah")


def test_mode_spasi_tetap_memilih_diameter():
    design = _design_x(INPUTS)
    selection = ce.select_flexure_bars(design, INPUTS)

    assert selection.kind == ce.SELECTION_DIAMETER
    assert selection.is_categorical
    # Nilainya HARUS diameter yang sudah dipakai solver menghitung As -- memanggil
    # pemilih ulang bisa memberi jawaban lain dari `d` yang melahirkan As itu.
    assert np.allclose(selection.values, design.bar_diameter, equal_nan=True)
    dipakai = {round(v * 1e3) for v in selection.values if np.isfinite(v) and v > 0}
    assert dipakai <= set(sk_rebar.AVAILABLE_DIAMETERS.astype(int))


def test_mode_diameter_tetap_menghitung_spasi():
    inputs = dataclasses.replace(INPUTS, rebar_mode="diameter_fixed", rebar_config="2D25")
    design = _design_x(inputs)
    selection = ce.select_flexure_bars(design, inputs)

    assert selection.kind == ce.SELECTION_SPACING
    assert not selection.is_categorical

    spacing_mm = selection.values * 1e3
    as_mm2 = ce.as_design_array(design) * 1e6
    expected = sk_rebar.check_spacing_limits(
        sk_rebar.calc_spacing_from_diameter(as_mm2, 25.0), 1200.0, 25.0
    )
    assert np.allclose(spacing_mm, expected, equal_nan=True)


def test_mode_diameter_tetap_membatasi_spasi_maksimum():
    """`check_spacing_limits` memotong ke min(2h, 450) -- bukan angka bebas."""
    inputs = dataclasses.replace(INPUTS, rebar_mode="diameter_fixed", rebar_config="4D32")
    design = ce.flexure_design(np.array([20_000.0]), inputs, direction="x", face="bawah")
    selection = ce.select_flexure_bars(design, inputs)

    finite = selection.values[np.isfinite(selection.values)]
    assert np.all(finite * 1e3 <= min(2 * 1200.0, 450.0) + 1e-9)


def test_mode_kode_konfigurasi_menghasilkan_indeks_dan_label():
    codes = ("16", "22", "2D25")
    inputs = dataclasses.replace(INPUTS, rebar_select_codes=codes)
    design = _design_x(inputs)
    selection = ce.select_flexure_bars(design, inputs)

    assert selection.kind == ce.SELECTION_CONFIG
    assert selection.labels == tuple(sorted(codes, key=lambda c: sk_rebar.REBAR_CONFIG_TABLE[c][2]))
    dipakai = {int(v) for v in selection.values if np.isfinite(v) and v > 0}
    assert dipakai, "harus ada elemen yang memilih konfigurasi"
    assert max(dipakai) <= len(selection.labels)


def test_seleksi_membedakan_tanpa_tulangan_dari_tidak_memadai():
    """Dua sebab NaN yang berbeda tidak boleh dilaporkan sama.

    `As` NaN = penampang tidak memadai (tebalkan pelat). Seleksi NaN sementara `As`
    terdefinisi = tidak ada batang yang cukup besar (perbesar daftar batang).
    """
    inputs = dataclasses.replace(INPUTS, rebar_select_codes=("13",))
    design = ce.flexure_design(np.array([0.0, 2_500_000.0]), inputs, direction="x", face="bawah")
    selection = ce.select_flexure_bars(design, inputs)

    assert selection.status[0] == ce.STATUS_NO_MOMENT
    assert selection.status[1] == ce.STATUS_SECTION_INADEQUATE
    assert not np.isfinite(selection.values[1])


# ---------------------------------------------------------------------------
# As_min surface zone (ACI 350 -- opt-in)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("thickness_m", "tanpa_cap", "dengan_cap"),
    [(1.2, 1080.0, 540.0), (1.4, 1260.0, 540.0), (1.5, 1350.0, 540.0)],
)
def test_surface_zone_menurunkan_as_min(thickness_m, tanpa_cap, dengan_cap):
    """Satu opsi ini mengubah hampir seluruh hasil lentur pilecap tebal.

    DIUKUR pada ex01: 18 dari 20 lajur dikendalikan `As_min`, bukan momen. Karena itu
    nilainya diekspos dan dicatat, bukan dipakai diam-diam maupun disembunyikan.
    """
    polos = dataclasses.replace(INPUTS, thickness=thickness_m)
    dibatasi = dataclasses.replace(polos, as_min_surface_zone=0.300)

    a = ce.flexure_design(np.array([0.0]), polos, direction="x", face="bawah")
    b = ce.flexure_design(np.array([0.0]), dibatasi, direction="x", face="bawah")

    assert a.as_min * 1e6 == pytest.approx(tanpa_cap, rel=1e-9)
    assert b.as_min * 1e6 == pytest.approx(dengan_cap, rel=1e-9)


def test_surface_zone_dicatat_di_provenance_dengan_sitasinya():
    tanpa = ce.provenance_block(INPUTS)
    assert tanpa["as_min_surface_zone_mm"] is None
    assert "murni SNI" in tanpa["catatan_as_min"]

    dengan = ce.provenance_block(dataclasses.replace(INPUTS, as_min_surface_zone=0.300))
    assert dengan["as_min_surface_zone_mm"] == pytest.approx(300.0)
    assert "ACI 350-06" in dengan["catatan_as_min"]
    assert "TIDAK menyatakan" in dengan["catatan_as_min"]


# ---------------------------------------------------------------------------
# Peta sengkang per elemen
# ---------------------------------------------------------------------------


def _shear_map(v_kn_per_m: np.ndarray) -> ce.ShearRebarMap:
    return ce.shear_rebar_map(v_kn_per_m * 1e3, INPUTS, direction="x")


def test_av_min_dan_tanpa_av_min_dihitung_terpisah():
    """Tanpa pemisahan ini, "perlu sengkang" dan "kena minimum" tidak dapat dibedakan.

    DIUKUR pada ex01: 307 elemen ber-`Av/s > 0` versus 31 elemen yang beton-nya benar-
    benar tidak cukup. Satu angka gabungan terbaca seolah sepertiga pelat butuh sengkang.
    """
    smap = _shear_map(np.array([100.0, 600.0, 1_400.0]))

    # V_u kecil: tidak perlu apa pun. Sedang: hanya Av,min. Besar: sengkang nyata.
    assert smap.av_per_s_no_min[0] == 0.0
    assert smap.av_per_s[1] > 0.0 and smap.av_per_s_no_min[1] == 0.0
    assert smap.av_per_s_no_min[2] > 0.0


def test_n_needs_stirrup_menghitung_vu_melebihi_phi_vc():
    smap = _shear_map(np.array([100.0, 600.0, 1_400.0]))
    manual = int(np.count_nonzero(np.abs(smap.v_u) > smap.phi_v_c))

    assert smap.n_needs_stirrup == manual
    # Justru INI yang harus berbeda dari hitungan naif berbasis Av/s > 0.
    assert smap.n_needs_stirrup < int(np.count_nonzero(smap.av_per_s > 0.0))


def test_diameter_sengkang_cocok_dengan_shell_kit():
    smap = _shear_map(np.array([1_400.0, 900.0]))
    expected = sk_rebar.calc_shear_diameter(smap.av_per_s * 1e3, 200.0, 200.0)
    assert np.allclose(smap.stirrup_diameter * 1e3, expected, equal_nan=True)


def test_dv_geser_memakai_asumsi_d16_muka_bawah():
    """Asumsi ini memengaruhi `V_c` dan tidak dapat dibaca dari hasil -- harus tercatat."""
    smap = _shear_map(np.array([500.0]))
    expected = sk_rebar.calc_effective_depth(1200.0, 75.0, 16.0, "x", "bottom")

    assert smap.d_shear * 1e3 == pytest.approx(expected)
    assert ce.provenance_block(INPUTS)["dv_assumed_bar_mm"] == pytest.approx(16.0)
    assert "D16" in ce.provenance_block(INPUTS)["catatan_dv"]


def test_daftar_diameter_sengkang_kustom_dihormati():
    inputs = dataclasses.replace(INPUTS, stirrup_diameters=(0.016, 0.019))
    smap = ce.shear_rebar_map(np.array([1_400e3]), inputs, direction="x")
    dipakai = {round(d * 1e3) for d in smap.stirrup_diameter if np.isfinite(d) and d > 0}
    assert dipakai <= {16, 19}


def test_arah_geser_tidak_dikenal_ditolak():
    with pytest.raises(ValueError, match="'x' atau 'y'"):
        ce.shear_rebar_map(np.array([1.0]), INPUTS, direction="z")


def test_provenance_mencatat_mode_dan_grid_sengkang():
    """Asumsi yang MENGUBAH angka desain harus dapat ditelusuri dari manifest."""
    block = ce.provenance_block(INPUTS)
    assert block["rebar_mode"] == "spacing_fixed"
    assert block["rebar_spacing_mm"] == pytest.approx(150.0)
    assert block["stirrup_grid_mm"] == [pytest.approx(200.0), pytest.approx(200.0)]

    codes = dataclasses.replace(INPUTS, rebar_select_codes=("16", "2D25"))
    assert ce.provenance_block(codes)["rebar_select_codes"] == ["16", "2D25"]
