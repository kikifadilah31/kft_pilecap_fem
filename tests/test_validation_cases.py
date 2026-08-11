"""Validation Cases VC-0 s/d VC-7 (PRD Bagian 8.1) -- **RELEASE GATE**.

PRD Bagian 1.3 poin 1: rilis DIBLOKIR bila ada validation case yang gagal. Ini bukan
target aspirasional.

Aturan mutlak PRD Bagian 8.1: koefisien VC-1 (Timoshenko) dan VC-7 (metode konvensional)
TIDAK BOLEH dipakai sebelum diverifikasi ke sumbernya. Karena PRD Bagian 17 item 7 masih
terbuka, kedua case itu di-`skip` dengan alasan eksplisit -- BUKAN diisi angka tebakan.

**VC-6 kini berjalan** (PRD Bagian 17 item 8 TERTUTUP sejak 2026-08-10): model pembanding
Midas Civil untuk keempat contoh bawaan tersedia di `tests/data/vc6/`. Ia membandingkan
resultan elemen, lendutan per node, dan reaksi tumpuan; provenance beserta rekonsiliasi
konvensinya ada di `tests/data/vc6/SUMBER.md`.

`ex04` (v0.9.0) menambahkan cakupan yang tidak dimiliki tiga lainnya: pile yang menindih
pier, sehingga node lensa dijepit SEKALIGUS dibebani. Ia menguji `*CONSTRAINT` dan
`*PRESSURE` pada ekspor MCT terhadap Midas -- lihat SUMBER.md Bagian 1.1.

Kalibrasi tanda (`config.MOMENT_SIGN_FACTOR`, `config.SHEAR_SIGN_FACTOR`) TIDAK
bergantung pada koefisien buku: VC-3 memakai pelat satu arah bertumpuan sederhana, yang
statis tertentu sehingga momen & gesernya mengikuti kesetimbangan saja.
"""

from __future__ import annotations

import dataclasses
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import validation_helpers
from validation_helpers import (
    EdgeSupport,
    UniformPressure,
    elastic_material,
    gmsh_plate,
    integrate_column,
    structured_plate,
)

from pilecap_fem import (
    config,
    fem_engine,
    geometry_builder,
    io_utils,
    mesh_engine,
    mesh_model,
    postproc_engine,
    validators,
)

pytestmark = pytest.mark.slow

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

# Geometri acuan pelat satu arah. Statika eksak: M_midspan = q Lx^2 Ly / 8.
LX, LY, THICKNESS = 4.0, 2.0, 0.1
PRESSURE = 1000.0  # [Pa] ke bawah


def run_plate(
    mesh: mesh_model.MeshModel,
    *,
    nu: float = 0.0,
    thickness: float = THICKNESS,
    pressure: float = PRESSURE,
    span_end: float = LX,
) -> tuple[fem_engine.ComboResult, postproc_engine.ElementResults]:
    """Analisis pelat satu arah: tumpuan sederhana di dua tepi, tekanan merata ke bawah."""
    material = elastic_material(nu=nu, t=thickness)
    result = fem_engine.analyze_combo(
        mesh,
        geom=None,  # type: ignore[arg-type]
        material=material,
        options=fem_engine.AnalysisOptions(equilibrium_rtol=1e-6),
        combo="VC",
        pz_by_pile={},
        load_strategy=UniformPressure(-pressure),
        support_strategy=EdgeSupport(span_axis=0, span_start=0.0, span_end=span_end),
    )
    return result, postproc_engine.compute_element_results(result, mesh)


# ===========================================================================
# VC-3 -- Pelat satu arah: KALIBRASI TANDA & BESARAN (statika eksak)
# ===========================================================================


@pytest.mark.parametrize("nu", [0.0, 0.2])
def test_vc3_momen_tengah_bentang_cocok_statika_eksak(nu: float):
    """`M = q L^2 B / 8`, EKSAK dari kesetimbangan -- tanpa koefisien dari buku."""
    nx, ny = 24, 12
    mesh = structured_plate(LX, LY, nx, ny)
    _, results = run_plate(mesh, nu=nu)

    total, actual_x, n_elem = integrate_column(
        mesh, results.m_xx, cut_axis=0, cut_position=LX / 2, h=LX / nx
    )
    # Momen eksak pada posisi kolom yang BENAR-BENAR dipakai, bukan di L/2 ideal.
    exact = PRESSURE * LY * (LX * actual_x - actual_x**2) / 2.0

    assert n_elem == ny, "harus tepat satu kolom elemen"
    assert total == pytest.approx(exact, rel=2e-2)


def test_vc3_tanda_momen_positif_saat_serat_bawah_tertarik():
    """Inti kalibrasi `config.MOMENT_SIGN_FACTOR`.

    Pelat bertumpuan sederhana dengan beban ke bawah membuat serat BAWAH tertarik.
    Menurut konvensi PRD Bagian 7.1, kondisi itu = momen POSITIF. Test ini GAGAL bila
    `MOMENT_SIGN_FACTOR` diubah keliru.
    """
    mesh = structured_plate(LX, LY, 24, 12)
    _, results = run_plate(mesh)

    total, _, _ = integrate_column(mesh, results.m_xx, cut_axis=0, cut_position=LX / 2, h=LX / 24)
    assert total > 0.0, (
        "Momen lapangan pelat bertumpuan sederhana harus POSITIF menurut konvensi "
        "PRD Bagian 7.1 (serat bawah tertarik). Periksa config.MOMENT_SIGN_FACTOR."
    )

    # Tanpa koreksi tanda, OpenSees memberi nilai berlawanan -- itulah alasan faktor ada.
    mentah = results.raw_gauss.mean(axis=1)[:, postproc_engine.IDX_M11]
    assert np.mean(mentah) < 0.0
    assert config.MOMENT_SIGN_FACTOR == -1.0


def test_vc3_geser_cocok_statika_dan_bertanda_benar():
    """Kalibrasi `config.SHEAR_SIGN_FACTOR`, DIUKUR terpisah dari momen."""
    nx = 24
    mesh = structured_plate(LX, LY, nx, 12)
    _, results = run_plate(mesh)

    kiri, x_kiri, _ = integrate_column(mesh, results.q_x, cut_axis=0, cut_position=0.5, h=LX / nx)
    kanan, x_kanan, _ = integrate_column(
        mesh, results.q_x, cut_axis=0, cut_position=LX - 0.5, h=LX / nx
    )

    v_kiri = PRESSURE * LY * (LX / 2 - x_kiri)
    v_kanan = PRESSURE * LY * (LX / 2 - x_kanan)

    assert kiri == pytest.approx(v_kiri, rel=3e-2)
    assert kanan == pytest.approx(v_kanan, rel=3e-2)
    assert kiri > 0.0 > kanan, "geser harus berubah tanda dari tumpuan kiri ke kanan"
    assert config.SHEAR_SIGN_FACTOR == -1.0


@pytest.mark.parametrize("method", ["exact", "bbox", "area_ratio"])
def test_vc3_ketiga_metode_pembobotan_lebar_setara_pada_mesh_terstruktur(method: str):
    """PRD Bagian 7.2(4) meminta metode pembobotan dibandingkan pada VC-3.

    Pada mesh terstruktur (quad sejajar sumbu) ketiganya HARUS memberi hasil sama.
    Perbedaannya baru muncul pada mesh tak beraturan -- lihat
    `test_vc2_metode_lebar_bbox_melebihkan_pada_mesh_tak_beraturan`.
    """
    from pilecap_fem import math_engine

    nx, ny = 24, 12
    mesh = structured_plate(LX, LY, nx, ny)
    _, results = run_plate(mesh)

    cut = LX / 2 - LX / nx / 2  # di tengah kolom elemen, bukan di batasnya
    coords = mesh.node_xy[mesh.elem_conn]
    mask = math_engine.select_elements_crossing_cut(coords, cut_axis=0, cut_position=cut)
    widths = math_engine.cut_element_widths(
        coords, mesh.elem_area, cut_axis=0, method=method, cut_position=cut
    )
    total = math_engine.integrate_strip(results.m_xx, widths, mask)

    assert int(mask.sum()) == ny
    assert float(np.sum(widths[mask])) == pytest.approx(LY, rel=1e-9)
    exact = PRESSURE * LY * (LX * cut - cut**2) / 2.0
    assert total == pytest.approx(exact, rel=2e-2)


def test_vc2_metode_lebar_bbox_melebihkan_pada_mesh_tak_beraturan():
    """Bukti terukur mengapa `"exact"` menjadi default (PRD Bagian 7.2(4) opsi a).

    Pada mesh quasi-structured quad, jumlah lebar `bbox` di sepanjang garis potong
    MELEBIHI lebar pelat, sedangkan `exact` menutupnya persis.
    """
    from pilecap_fem import math_engine

    mesh = gmsh_plate(LX, LY, 0.15, disk_radius=0.5)
    coords = mesh.node_xy[mesh.elem_conn]
    cut = LX / 2
    mask = math_engine.select_elements_crossing_cut(coords, cut_axis=0, cut_position=cut)

    exact = math_engine.cut_element_widths(
        coords, mesh.elem_area, cut_axis=0, method="exact", cut_position=cut
    )
    bbox = math_engine.cut_element_widths(coords, mesh.elem_area, cut_axis=0, method="bbox")

    assert float(np.sum(exact[mask])) == pytest.approx(LY, rel=1e-6)
    assert float(np.sum(bbox[mask])) > LY * 1.05


# ===========================================================================
# VC-2 -- Invariansi orientasi mesh (membuktikan transformasi Bagian 7.2(3))
# ===========================================================================


@pytest.mark.parametrize("shift", [0, 1, 2, 3])
def test_vc2_pergeseran_konektivitas_tidak_mengubah_hasil_global(shift: int):
    """Sumbu lokal diputar kelipatan 90 derajat -> `m_xx` global harus tetap sama."""
    nx, ny = 20, 10
    mesh = structured_plate(LX, LY, nx, ny, shift=shift)
    _, results = run_plate(mesh)

    total, x, _ = integrate_column(mesh, results.m_xx, cut_axis=0, cut_position=LX / 2, h=LX / nx)
    exact = PRESSURE * LY * (LX * x - x**2) / 2.0

    # theta memang berubah 90 derajat tiap pergeseran...
    assert np.allclose(np.abs(np.sin(2 * mesh.elem_theta)), 0.0, atol=1e-9)
    # ...tetapi hasil GLOBAL tidak boleh ikut berubah.
    assert total == pytest.approx(exact, rel=2e-2)


@pytest.mark.parametrize("angle_deg", [30.0, 45.0])
def test_vc2_model_diputar_menghasilkan_komponen_global_sesuai_tensor(angle_deg: float):
    """Seluruh model diputar `alpha`; lentur uniaksial harus terurai persis menurut tensor.

    Untuk momen uniaksial `M` searah bentang yang membentuk sudut `alpha` dengan sumbu X:
    `m_xx = M cos^2(alpha)`, `m_yy = M sin^2(alpha)`, `m_xy = M sin(alpha) cos(alpha)`.
    """
    alpha = math.radians(angle_deg)
    nx, ny = 20, 10
    lurus = structured_plate(LX, LY, nx, ny)
    miring = structured_plate(LX, LY, nx, ny, angle=alpha)

    _, hasil_lurus = run_plate(lurus)

    material = elastic_material(nu=0.0, t=THICKNESS)
    result = fem_engine.analyze_combo(
        miring,
        geom=None,  # type: ignore[arg-type]
        material=material,
        options=fem_engine.AnalysisOptions(equilibrium_rtol=1e-6),
        combo="VC2",
        pz_by_pile={},
        load_strategy=UniformPressure(-PRESSURE),
        # Tepi tumpuan ikut berputar: proyeksikan ke arah bentang yang baru.
        support_strategy=_RotatedEdgeSupport(alpha, LX),
    )
    hasil_miring = postproc_engine.compute_element_results(result, miring)

    # Elemen di tengah bentang pada model lurus vs miring (indeks elemen sama persis,
    # karena konektivitas grid identik -- hanya koordinatnya yang berputar).
    tengah = _midspan_element_indices(lurus, nx, ny)
    m_span = float(np.mean(hasil_lurus.m_xx[tengah]))

    c, s = math.cos(alpha), math.sin(alpha)
    assert float(np.mean(hasil_miring.m_xx[tengah])) == pytest.approx(m_span * c * c, rel=3e-2)
    assert float(np.mean(hasil_miring.m_yy[tengah])) == pytest.approx(m_span * s * s, rel=3e-2)
    assert float(np.mean(hasil_miring.m_xy[tengah])) == pytest.approx(m_span * s * c, rel=3e-2)


def test_vc2_mesh_gmsh_orientasi_tersebar_tetap_menghasilkan_lentur_satu_arah():
    """Uji paling menentukan: orientasi elemen TERSEBAR, hasil global harus tetap benar.

    Mesh quasi-structured quad gmsh menghasilkan `theta` yang tersebar, sehingga banyak
    elemen punya `m12` lokal tak-nol. Bila TANDA suku `m12` pada transformasi salah,
    `m_yy` dan `m_xy` global tidak akan mendekati nol.
    """
    h = 0.15
    # Partisi lingkaran internal memaksa orientasi elemen tersebar tanpa mengubah
    # geometri fisik pelat -- persis kondisi area pile pada model sungguhan.
    mesh = gmsh_plate(LX, LY, h, disk_radius=0.5)
    _, results = run_plate(mesh)

    # Test ini hanya bermakna bila m12 lokal memang tak-nol pada sebagian elemen.
    skala = float(np.max(np.abs(results.m11)))
    fraksi_m12 = float(np.mean(np.abs(results.m12) > 0.01 * skala))
    assert fraksi_m12 > 0.05, (
        f"Hanya {fraksi_m12:.1%} elemen punya m12 lokal berarti -- mesh terlalu "
        "terstruktur sehingga test tidak menguji suku m12."
    )

    total, x, _ = integrate_column(mesh, results.m_xx, cut_axis=0, cut_position=LX / 2, h=h)
    exact = PRESSURE * LY * (LX * x - x**2) / 2.0
    assert total == pytest.approx(exact, rel=5e-2)

    # Lentur satu arah dengan nu = 0: komponen melintang & puntir global harus kecil.
    interior = np.abs(mesh.elem_centroid[:, 0] - LX / 2) < LX / 4
    assert float(np.mean(np.abs(results.m_yy[interior]))) < 0.05 * skala
    assert float(np.mean(np.abs(results.m_xy[interior]))) < 0.05 * skala


# ===========================================================================
# VC-4 -- Konvergensi mesh
# ===========================================================================


def test_vc4_konvergensi_mesh_monoton_dan_stabil():
    """Ukuran mesh h, h/2, h/4 -> lendutan konvergen, perubahan < 2% di dua mesh terhalus."""
    deflections = []
    for nx in (10, 20, 40):
        mesh = structured_plate(LX, LY, nx, max(2, nx // 2))
        result, _ = run_plate(mesh)
        deflections.append(result.max_deflection)

    assert all(math.isfinite(d) and d > 0 for d in deflections)
    perubahan_kasar = abs(deflections[1] - deflections[0]) / deflections[1]
    perubahan_halus = abs(deflections[2] - deflections[1]) / deflections[2]
    assert perubahan_halus < perubahan_kasar, "perubahan harus mengecil (konvergen)"
    assert perubahan_halus < 0.02, f"perubahan dua mesh terhalus {perubahan_halus:.3%} >= 2%"


# ===========================================================================
# VC-5 -- Efek tebal (Mindlin vs Kirchhoff)
# ===========================================================================


def _kirchhoff_deflection(q: float, span: float, E: float, t: float, nu: float) -> float:
    """Lendutan tengah bentang pelat satu arah menurut teori pelat TIPIS (tanpa geser)."""
    D = E * t**3 / (12.0 * (1.0 - nu**2))
    return 5.0 * q * span**4 / (384.0 * D)


def test_vc5_pelat_tebal_melendut_lebih_besar_dari_prediksi_kirchhoff():
    """Kontribusi deformasi geser transversal harus TERLIHAT pada pelat tebal.

    Inilah pembenaran memakai Mindlin-Reissner (ShellMITC4) untuk pilecap
    (PRD Bagian 7.2(1)): teori Kirchhoff MEREMEHKAN lendutan pelat tebal.

    PRD Bagian 8.1 menetapkan kriteria VC-5 bersifat **kualitatif + arah perbedaan**,
    bukan nilai absolut. Karena itu yang diuji di sini:

      1. pelat tipis (t/L = 0.02) mendekati Kirchhoff;
      2. kelebihan lendutan MEMBESAR seiring tebal;
      3. kelebihan itu berskala kira-kira `(t/L)^2` -- tanda tangan khas kontribusi
         geser transversal, dan jauh lebih menentukan daripada satu ambang angka.
    """
    E, nu = 25e9, 0.0
    kelebihan = {}
    for t in (0.08, 0.40, 0.80):  # t/L = 0.02, 0.10, 0.20
        mesh = structured_plate(LX, LY, 32, 16)
        result, _ = run_plate(mesh, nu=nu, thickness=t)
        kirchhoff = _kirchhoff_deflection(PRESSURE, LX, E, t, nu)
        kelebihan[t] = result.max_deflection / kirchhoff - 1.0

    assert kelebihan[0.08] == pytest.approx(0.0, abs=0.02), (
        f"pelat tipis harus mendekati Kirchhoff, kelebihan = {kelebihan[0.08]:.4f}"
    )
    # Pelat tipis boleh sedikit NEGATIF: pada t/L = 0.02 kontribusi geser lebih kecil
    # daripada galat diskretisasi mesh. Yang menentukan adalah ARAH perubahannya.
    assert kelebihan[0.80] > kelebihan[0.40] > kelebihan[0.08], (
        f"kelebihan lendutan harus membesar seiring tebal: {kelebihan}"
    )
    assert kelebihan[0.80] > 0.03, (
        f"pelat tebal harus melendut LEBIH BESAR dari Kirchhoff, kelebihan = {kelebihan[0.80]:.4f}"
    )

    # Kontribusi geser berskala (t/L)^2: menggandakan t/L harus melipatempatkan kelebihan.
    rasio_skala = kelebihan[0.80] / kelebihan[0.40]
    assert rasio_skala == pytest.approx(4.0, rel=0.15), (
        f"kelebihan lendutan tidak berskala (t/L)^2: rasio = {rasio_skala:.2f}, "
        "seharusnya ~4 saat t/L digandakan"
    )


# ===========================================================================
# VC-0 -- Kesetimbangan statika pada model pilecap sungguhan
# ===========================================================================


def _build_example(name: str) -> tuple:
    directory = EXAMPLES / name
    loaded = io_utils.load_config(directory / "pilecap_config.json")
    sources = io_utils.resolve_geometry_sources(loaded, input_dir=directory)
    validators.validate_config_geometry_params(
        loaded.si, io_utils.sources_present(sources.resolution)
    )
    validators.validate_config_mesh(loaded.si)
    validators.validate_material(loaded.si)
    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    validators.validate_geometry(geom)
    validators.validate_mesh_vs_geometry(loaded.si, geom)
    raw = mesh_engine.generate_mesh(geom, mesh_engine.MeshOptions.from_config(loaded.si))
    mesh = mesh_model.build_mesh_model(raw)
    reactions = io_utils.load_reactions(
        directory / "pile_reactions.csv", config.FORCE_TO_SI[loaded.input_units["force"]]
    )
    validators.validate_reactions(reactions, geom)
    return loaded, geom, mesh, reactions


@pytest.fixture(scope="module")
def ex01_model():
    return _build_example("ex01_standard_4pile")


def test_vc0_kesetimbangan_gaya_dan_momen(ex01_model):
    """Dijalankan otomatis pada SETIAP run produksi, bukan hanya saat testing."""
    loaded, geom, mesh, reactions = ex01_model
    combo = reactions.combos[0]

    result = fem_engine.analyze_combo(
        mesh,
        geom,
        fem_engine.MaterialProperties.from_config(loaded.si),
        fem_engine.AnalysisOptions(equilibrium_rtol=1e-6),
        combo=combo,
        pz_by_pile=reactions.values[combo],
    )
    check = result.equilibrium

    assert check.passed
    assert check.force_residual_rel < 1e-6
    assert check.moment_residual_rel < 1e-4
    assert check.total_applied_fz == pytest.approx(reactions.total_pz(combo), rel=1e-12)
    assert check.total_reaction_fz == pytest.approx(-reactions.total_pz(combo), rel=1e-6)


def test_vc0_beban_terpasang_persis_sama_dengan_pz_tiap_pile(ex01_model):
    """PRD Bagian 7.3: `A_disk` dari luas mesh menjamin Sigma(p x A_e) = P_z PERSIS."""
    loaded, geom, mesh, reactions = ex01_model
    combo = reactions.combos[0]

    result = fem_engine.analyze_combo(
        mesh,
        geom,
        fem_engine.MaterialProperties.from_config(loaded.si),
        fem_engine.AnalysisOptions(equilibrium_rtol=1e-6),
        combo=combo,
        pz_by_pile=reactions.values[combo],
    )
    for trace in result.load_traces:
        assert trace.applied_total == pytest.approx(trace.pz, rel=1e-12)
        assert abs(trace.discrepancy) < 1e-6
        assert trace.n_elements > 0
        # Luas mesh mendekati pi r^2 tetapi TIDAK sama -- justru sebabnya A_disk diambil
        # dari mesh, bukan dari nilai analitis.
        assert trace.a_disk_mesh == pytest.approx(trace.a_disk_nominal, rel=0.03)


def test_vc0_mendeteksi_ketidakseimbangan_sungguhan(ex01_model):
    """`_check_equilibrium` menyatakan GAGAL saat reaksi memang tidak mengimbangi beban.

    Diuji langsung pada fungsinya dengan masukan yang sengaja tidak seimbang, BUKAN dengan
    menyetel toleransi ke angka mustahil. Alasannya konkret: residu gaya pada model yang
    benar kadang tepat `0.0`, dan `0.0 <= rtol` lulus untuk **setiap** rtol -- test yang
    mengandalkan trik toleransi karena itu bergantung pada keberuntungan floating point,
    dan pernah lulus/gagal berganti-ganti tanpa ada yang berubah di kode.
    """
    _, _, mesh, _ = ex01_model

    applied = np.zeros(mesh.n_nodes)
    applied[: mesh.n_nodes // 2] = 1000.0
    total = float(applied.sum())

    reaction_nodes = np.array([0, 1], dtype=np.int64)
    # Reaksi hanya mengimbangi 90% beban -> residu gaya relatif 0,1.
    reactions = np.zeros((2, 6))
    reactions[:, 2] = -0.45 * total

    check = fem_engine._check_equilibrium(mesh, applied, reaction_nodes, reactions, force_rtol=1e-3)
    assert check.force_residual_rel == pytest.approx(0.1, rel=1e-9)
    assert not check.force_passed
    assert not check.passed


def test_vc0_gagal_memblokir_analisis_bukan_sekadar_mencatat(ex01_model, monkeypatch):
    """Hasil VC-0 yang GAGAL harus melempar `AnalysisError`, bukan sekadar tercatat.

    Kegagalan VC-0 dipaksa lewat monkeypatch supaya yang diuji adalah **penyambungannya**:
    apakah hasil cek benar-benar menghentikan analisis. Deteksi ketidakseimbangannya
    sendiri diuji terpisah di atas.
    """
    loaded, geom, mesh, reactions = ex01_model
    combo = reactions.combos[0]
    asli = fem_engine._check_equilibrium

    def gagal(*args, **kwargs):
        check = asli(*args, **kwargs)
        return dataclasses.replace(check, force_residual_rel=0.5)

    monkeypatch.setattr(fem_engine, "_check_equilibrium", gagal)

    with pytest.raises(validators.AnalysisError, match="VC-0 GAGAL"):
        fem_engine.analyze_combo(
            mesh,
            geom,
            fem_engine.MaterialProperties.from_config(loaded.si),
            fem_engine.AnalysisOptions(equilibrium_rtol=1e-3),
            combo=combo,
            pz_by_pile=reactions.values[combo],
        )


def test_opensees_state_dibersihkan_antar_kombinasi(ex01_model):
    """PRD Bagian 13.4: `ops.wipe()` wajib -- state sisa adalah sumber bug halus klasik."""
    loaded, geom, mesh, reactions = ex01_model
    material = fem_engine.MaterialProperties.from_config(loaded.si)
    options = fem_engine.AnalysisOptions(equilibrium_rtol=1e-6)

    hasil = []
    for combo in reactions.combos:
        result = fem_engine.analyze_combo(
            mesh, geom, material, options, combo=combo, pz_by_pile=reactions.values[combo]
        )
        hasil.append(result)

    # Kombinasi berbeda -> hasil berbeda (bukan sisa model sebelumnya).
    assert hasil[0].max_deflection != pytest.approx(hasil[1].max_deflection, rel=1e-9)
    # Menjalankan ulang kombinasi pertama harus mengembalikan hasil yang IDENTIK.
    ulang = fem_engine.analyze_combo(
        mesh,
        geom,
        material,
        options,
        combo=reactions.combos[0],
        pz_by_pile=reactions.values[reactions.combos[0]],
    )
    assert ulang.max_deflection == pytest.approx(hasil[0].max_deflection, rel=1e-12)


# ===========================================================================
# VC-6 -- cross-check terhadap Midas Civil
# ===========================================================================
#
# Menutup PRD Bagian 17 item 8. Seluruh provenance, rekonsiliasi konvensi, dan batas
# ketelitian ekspor terdokumentasi di `tests/data/vc6/SUMBER.md` -- dibaca dulu sebelum
# mengubah angka gate mana pun di bawah.

VC6_DATA = Path(__file__).resolve().parent / "data" / "vc6"
VC6_KASUS = ("ex01", "ex02", "ex03", "ex04")
#: (nama tampilan, slug Midas). Urutannya sama dengan urutan subcase di `.log`/`.out`.
VC6_KOMBINASI = (("1.2D+1.6L", "1_2D_1_6L"), ("1.2D+1.0W", "1_2D_1_0W"))

#: Gate. Memberi margin 3-7x terhadap nilai terburuk yang benar-benar diamati; jangan
#: dilonggarkan tanpa mengukur ulang KEEMPAT kasus. Tabel lengkapnya di SUMBER.md Bagian 7.
VC6_KORELASI_MIN = 0.999
VC6_RMS_MOMEN = 0.010  # terburuk terukur 0,144% (ex04: 0,134%)
VC6_RMS_GESER = 0.015  # terburuk terukur 0,265% (ex04: 0,114%)
VC6_PUNCAK_MOMEN = 0.020  # terburuk terukur 0,515% (ex04: 0,378%)
#: Terburuk terukur 0,258% -- itu ex04, dan angkanya DIBATASI RESOLUSI EKSPOR, bukan tanda
#: ketidaksesuaian: lendutan ex04 hanya 0,110 mm sehingga 1 um setara 0,908%. Batas itu
#: mengikat pada ex01, ex03, dan ex04; hanya ex02 yang bebas darinya (SUMBER.md 5.2).
VC6_RMS_LENDUTAN = 0.010
VC6_RMS_REAKSI = 0.015  # terburuk terukur 0,539% (ex04: 0,088%)
VC6_TOTAL_REAKSI = 1e-4  # terburuk terukur ~6e-9 (ex04: ~4e-12)
VC6_ROTASI = 1e-4  # terburuk terukur 2e-6 (ex04: 1,3e-6)


def _vc6_jalankan(kasus: str, combo: str):
    """Jalankan solver di atas mesh TERSIMPAN milik kasus VC-6.

    Mesh sengaja dimuat dari CSV, tidak dibangun ulang: model Midas dibuat dari mesh itu,
    sedangkan gmsh tidak reproducible bit-demi-bit (README, "mesh tidak reproducible").
    Me-mesh ulang berarti membandingkan dua diskretisasi berbeda -- dan seluruh
    perbandingan per-elemen kehilangan maknanya tanpa satu pun tanda kegagalan.
    """
    folder = VC6_DATA / kasus
    geom = geometry_builder.GeometryModel.from_json_dict(
        json.loads((folder / "geometry.json").read_text(encoding="utf-8"))
    )
    mesh = mesh_model.from_csv(folder / "nodes.csv", folder / "elements.csv")
    loaded = io_utils.load_config(folder / "pilecap_config.json")
    reactions = io_utils.load_reactions(
        folder / "pile_reactions.csv", config.FORCE_TO_SI[loaded.input_units["force"]]
    )
    hasil = fem_engine.analyze_combo(
        mesh,
        geom,
        fem_engine.MaterialProperties.from_config(loaded.si),
        fem_engine.AnalysisOptions.from_config(loaded.si),
        combo=combo,
        pz_by_pile=reactions.values[combo],
        load_strategy=fem_engine.make_load_strategy(
            (loaded.si.get("pile") or {}).get("modeling", "pressure")
        ),
    )
    return mesh, hasil, postproc_engine.compute_element_results(hasil, mesh), reactions


@pytest.fixture(scope="module")
def vc6_hasil() -> dict[tuple[str, str], tuple]:
    """Delapan analisis (4 kasus x 2 kombinasi) dijalankan sekali; terukur ~8 detik total.

    Secepat itu justru KARENA mesh dimuat dari CSV -- gmsh tidak pernah dijalankan.
    """
    return {
        (kasus, combo): _vc6_jalankan(kasus, combo)
        for kasus in VC6_KASUS
        for combo, _ in VC6_KOMBINASI
    }


def _rms_relatif(midas: np.ndarray, kami: np.ndarray) -> float:
    """RMS selisih dibagi PUNCAK nilai kami -- bukan dibagi nilai per titik.

    Pembagian per titik akan meledak di dekat garis nol momen, tempat kedua kode sama-sama
    benar tetapi rasionya tak terhingga. Skala puncak adalah besaran yang benar-benar
    dipakai mendesain.
    """
    skala = float(np.max(np.abs(kami)))
    if skala == 0.0:
        return 0.0
    return float(np.sqrt(np.mean((midas - kami) ** 2)) / skala)


def _laporan(nama: str, midas: np.ndarray, kami: np.ndarray) -> str:
    """Pesan kegagalan yang memuat ANGKANYA, bukan sekadar 'tidak cocok'."""
    skala = float(np.max(np.abs(kami))) or 1.0
    return (
        f"{nama}: RMS={_rms_relatif(midas, kami) * 100:.3f}% "
        f"maks={np.max(np.abs(midas - kami)) / skala * 100:.3f}% "
        f"korelasi={np.corrcoef(midas, kami)[0, 1]:.6f} "
        f"(puncak kami={skala:,.4g}, Midas={np.max(np.abs(midas)):,.4g})"
    )


@pytest.mark.parametrize("kasus", VC6_KASUS)
@pytest.mark.parametrize(("combo", "slug"), VC6_KOMBINASI)
def test_vc6_resultan_elemen_cocok_dengan_midas(vc6_hasil, kasus: str, combo: str, slug: str):
    """Momen & geser per elemen vs Midas Civil, memakai ekspor sumbu GLOBAL.

    Tanda geser Midas dibalik lebih dulu (`MIDAS_SHEAR_SIGN`); itu perbedaan KONVENSI yang
    terbukti seragam pada seluruh elemen, bukan faktor penyetel -- lihat SUMBER.md 4.1.

    Simpangan titik-per-titik maksimum sengaja TIDAK di-gate: ex02 `q_y` mencapai 7,7% pada
    SATU elemen di singularitas tepi pier, tempat kedua formulasi elemen (ShellMITC4 vs
    QUAD4 hibrida Midas) memang paling sah berbeda. Angkanya tetap dicetak.
    """
    mesh, _, hasil, _ = vc6_hasil[(kasus, combo)]
    rows = validation_helpers.load_midas_centroid(VC6_DATA / kasus / "midas_force_global.csv", slug)
    assert list(rows.index) == [int(t) for t in mesh.elem_tags], (
        "penomoran elemen Midas tidak lagi 1:1 dengan mesh tersimpan"
    )
    midas = validation_helpers.midas_resultants_si(rows)

    for medan, batas in (
        ("m_xx", VC6_RMS_MOMEN),
        ("m_yy", VC6_RMS_MOMEN),
        ("m_xy", VC6_RMS_MOMEN),
        ("q_x", VC6_RMS_GESER),
        ("q_y", VC6_RMS_GESER),
    ):
        kami = getattr(hasil, medan)
        pesan = _laporan(f"{kasus}/{combo} {medan}", midas[medan], kami)
        assert _rms_relatif(midas[medan], kami) <= batas, pesan
        assert np.corrcoef(midas[medan], kami)[0, 1] >= VC6_KORELASI_MIN, pesan


@pytest.mark.parametrize("kasus", VC6_KASUS)
@pytest.mark.parametrize(("combo", "slug"), VC6_KOMBINASI)
def test_vc6_momen_puncak_cocok_dengan_midas(vc6_hasil, kasus: str, combo: str, slug: str):
    """Momen PUNCAK -- inilah yang menentukan tulangan, jadi diuji terpisah dari RMS.

    RMS yang baik masih mungkin menyembunyikan puncak yang meleset, dan puncaklah yang
    dipakai mendesain.
    """
    _, _, hasil, _ = vc6_hasil[(kasus, combo)]
    rows = validation_helpers.load_midas_centroid(VC6_DATA / kasus / "midas_force_global.csv", slug)
    midas = validation_helpers.midas_resultants_si(rows)
    for medan in ("m_xx", "m_yy"):
        puncak_kami = float(np.max(np.abs(getattr(hasil, medan))))
        puncak_midas = float(np.max(np.abs(midas[medan])))
        beda = abs(puncak_midas - puncak_kami) / puncak_kami
        assert beda <= VC6_PUNCAK_MOMEN, (
            f"{kasus}/{combo} |{medan}| puncak: kami={puncak_kami / 1e3:,.2f} "
            f"Midas={puncak_midas / 1e3:,.2f} kNm/m -> beda {beda * 100:.3f}%"
        )


@pytest.mark.parametrize("kasus", VC6_KASUS)
@pytest.mark.parametrize(("combo", "slug"), VC6_KOMBINASI)
def test_vc6_rotasi_lokal_ke_global_cocok_dengan_midas(kasus: str, combo: str, slug: str):
    """Cek-silang transformasi tensor terhadap implementasi INDEPENDEN.

    Ekspor tersedia dalam sumbu lokal maupun global. Merotasi yang lokal dengan `theta`
    dari `elements.csv` harus menghasilkan yang global. Lulusnya membuktikan dua hal
    sekaligus: `theta` kami adalah sudut sumbu material yang sama dengan yang dipakai
    Midas, DAN rumus rotasi `postproc_engine` sama dengan rumus Midas.

    VC-2 menguji hal yang sama secara sintetis dengan sudut yang diketahui; ini mengujinya
    terhadap kode nyata.
    """
    folder = VC6_DATA / kasus
    mesh = mesh_model.from_csv(folder / "nodes.csv", folder / "elements.csv")
    lokal = validation_helpers.load_midas_centroid(folder / "midas_force_local.csv", slug)
    global_ = validation_helpers.load_midas_centroid(folder / "midas_force_global.csv", slug)

    diputar = validation_helpers.rotate_moment_tensor(lokal, mesh.elem_theta)
    for medan, kolom, nilai in zip(
        ("m_xx", "m_yy", "m_xy"), validation_helpers.MIDAS_MOMENT_COLUMNS, diputar, strict=True
    ):
        acuan = global_[kolom].to_numpy(dtype=np.float64)
        assert _rms_relatif(nilai, acuan) <= VC6_ROTASI, _laporan(
            f"{kasus}/{combo} rotasi(lokal)->global {medan}", nilai, acuan
        )


@pytest.mark.parametrize("kasus", VC6_KASUS)
@pytest.mark.parametrize(("combo", "slug"), VC6_KOMBINASI)
def test_vc6_lendutan_per_node_cocok_dengan_midas(vc6_hasil, kasus: str, combo: str, slug: str):
    """Lendutan vertikal per node vs Midas, KEEMPAT contoh.

    Ekspor ex03 semula salah -- isinya reaksi, bukan lendutan -- sehingga jalur ini sempat
    hanya mencakup ex01 & ex02. Pemilik proyek memperbaikinya; riwayat itu tetap tercatat di
    SUMBER.md 5.1 supaya jejak auditnya tidak hilang.

    PERINGATAN TAFSIR: ekspor Midas menulis 6 desimal dalam METER, jadi resolusinya 1 um.
    Pada ex01 (lendutan maks 0,226 mm) itu setara 0,44% dari skala -- LEBIH BESAR daripada
    selisih terukur 0,216%. Lulusnya test ini di ex01 karena itu hanya membuktikan "tidak
    berbeda sejauh yang dapat diukur", bukan ketelitian 0,2%. Pada ex02 & ex03 (lendutan
    2,6 dan 1,9 mm) batasan itu tidak lagi mengikat.
    """
    mesh, mentah, _, _ = vc6_hasil[(kasus, combo)]
    jenis, tabel = validation_helpers.midas_nodal(VC6_DATA / kasus / "midas_displacement.csv", slug)
    assert jenis == "displacement", f"{kasus}: berkas lendutan ternyata berisi {jenis}"

    tag_ke_indeks = {int(t): i for i, t in enumerate(mesh.node_tags)}
    indeks = [tag_ke_indeks[int(t)] for t in tabel.index]
    kami = mentah.displacements[indeks, 2]
    midas = tabel["DZ(m)"].to_numpy(dtype=np.float64)

    pesan = _laporan(f"{kasus}/{combo} uz", midas, kami)
    assert _rms_relatif(midas, kami) <= VC6_RMS_LENDUTAN, pesan
    assert np.corrcoef(midas, kami)[0, 1] >= VC6_KORELASI_MIN, pesan


@pytest.mark.parametrize("kasus", VC6_KASUS)
def test_vc6_lendutan_maksimum_cocok_dengan_log_midas(vc6_hasil, kasus: str):
    """`MAXIMUM TRANSLATION` di `.log` solver Midas vs lendutan maksimum kami.

    Tersedia untuk KEEMPAT kasus, tidak bergantung pada ekspor per-node.
    """
    acuan = validation_helpers.midas_max_translation(VC6_DATA / kasus / "midas_solver.log")
    assert len(acuan) == len(VC6_KOMBINASI), (
        f"{kasus}: .log memuat {len(acuan)} subcase, diharapkan {len(VC6_KOMBINASI)}"
    )
    for (combo, _), midas in zip(VC6_KOMBINASI, acuan, strict=True):
        _, mentah, _, _ = vc6_hasil[(kasus, combo)]
        beda = abs(midas - mentah.max_deflection) / midas
        assert beda <= VC6_RMS_LENDUTAN, (
            f"{kasus}/{combo} lendutan maks: kami={mentah.max_deflection * 1e3:.5f} mm "
            f"Midas={midas * 1e3:.5f} mm -> beda {beda * 100:.3f}%"
        )


@pytest.mark.parametrize("kasus", VC6_KASUS)
@pytest.mark.parametrize(("combo", "slug"), VC6_KOMBINASI)
def test_vc6_reaksi_tumpuan_cocok_dengan_midas(vc6_hasil, kasus: str, combo: str, slug: str):
    """Reaksi vertikal per node jepit vs Midas, pada keempat kasus.

    Untuk ex04 test ini sekaligus menguji `fem_engine.fixed_support_nodes`: asersi
    kesamaan indeks di bawah menuntut himpunan node jepit Midas SAMA PERSIS dengan milik
    kami, dan himpunan itu memuat node `LENS_*`. Bila lensa tertinggal bebas di salah satu
    sisi, test gagal di asersi indeks -- bukan diam-diam lolos dengan angka yang berbeda.
    """
    mesh, mentah, _, _ = vc6_hasil[(kasus, combo)]
    jenis, tabel = validation_helpers.midas_nodal(VC6_DATA / kasus / "midas_reaction.csv", slug)
    assert jenis == "reaction"

    kami = pd.Series(
        mentah.reactions[:, 2] / 1e3,
        index=[int(t) for t in mesh.node_tags[mentah.reaction_nodes]],
    ).sort_index()
    midas = tabel["FZ(kN)"].astype(float).sort_index()
    assert list(kami.index) == list(midas.index), (
        f"{kasus}: himpunan node jepit berbeda -- kami {len(kami)}, Midas {len(midas)}"
    )

    pesan = _laporan(f"{kasus}/{combo} Rz", midas.to_numpy(), kami.to_numpy())
    assert _rms_relatif(midas.to_numpy(), kami.to_numpy()) <= VC6_RMS_REAKSI, pesan
    assert np.corrcoef(midas.to_numpy(), kami.to_numpy())[0, 1] >= VC6_KORELASI_MIN, pesan


@pytest.mark.parametrize("kasus", VC6_KASUS)
@pytest.mark.parametrize(("combo", "slug"), VC6_KOMBINASI)
def test_vc6_total_reaksi_midas_membuktikan_ekspor_mct(kasus: str, combo: str, slug: str):
    """Sigma FZ Midas == Sigma Pz masukan. Ini MENGUJI EKSPOR MCT, bukan solver kami.

    Model Midas diimpor dari `model.mct` yang ditulis `exporters.mct`. Bila totalnya cocok,
    terbukti Midas benar-benar menerima beban yang kita maksudkan -- satu-satunya cek yang
    pernah menyentuh sisi Midas yang sesungguhnya. Seluruh test MCT lainnya hanya memeriksa
    berkas kita terhadap harapan kita sendiri.
    """
    folder = VC6_DATA / kasus
    _, tabel = validation_helpers.midas_nodal(folder / "midas_reaction.csv", slug)
    loaded = io_utils.load_config(folder / "pilecap_config.json")
    reactions = io_utils.load_reactions(
        folder / "pile_reactions.csv", config.FORCE_TO_SI[loaded.input_units["force"]]
    )

    total_pz = sum(reactions.values[combo].values()) / 1e3  # kN, ke ATAS
    total_fz = float(tabel["FZ(kN)"].astype(float).sum())  # ke BAWAH
    beda = abs(total_pz + total_fz) / total_pz
    assert beda <= VC6_TOTAL_REAKSI, (
        f"{kasus}/{combo}: Sigma Pz masukan={total_pz:,.5f} kN, Sigma FZ Midas={total_fz:,.5f} kN "
        f"-> beda relatif {beda:.3e}. Ekspor MCT tidak membebani Midas seperti yang dimaksud."
    )


# ===========================================================================
# VC-1, VC-7 -- DILEWATI dengan alasan eksplisit
# ===========================================================================


@pytest.mark.skip(
    reason=(
        "VC-1 butuh koefisien Timoshenko & Woinowsky-Krieger (w_max = 0.00406 q a^4/D, "
        "M_max = 0.0479 q a^2) beserta nomor tabel pada edisi yang dipakai. "
        "PRD Bagian 17 item 7 masih TERBUKA. PRD Bagian 8.1 melarang memakai angka itu "
        "sebelum diverifikasi ke sumbernya. Kalibrasi tanda tidak terhambat: VC-3 "
        "memakai kasus statis tertentu yang tidak butuh koefisien buku."
    )
)
def test_vc1_pelat_bujursangkar_tumpuan_sederhana():  # pragma: no cover
    raise AssertionError("tidak boleh dijalankan sebelum sumbernya dikonfirmasi")


@pytest.mark.skip(
    reason=(
        "VC-7 butuh referensi contoh soal metode balok konvensional beserta angka "
        "acuannya. PRD Bagian 17 item 7 masih TERBUKA."
    )
)
def test_vc7_metode_konvensional():  # pragma: no cover
    raise AssertionError("tidak boleh dijalankan sebelum referensinya dikonfirmasi")


# ---------------------------------------------------------------------------
# Perkakas lokal
# ---------------------------------------------------------------------------


class _RotatedEdgeSupport:
    """EdgeSupport untuk model yang diputar: proyeksikan node ke arah bentang."""

    def __init__(self, alpha: float, span: float, tol: float = 1e-6) -> None:
        self.direction = np.array([math.cos(alpha), math.sin(alpha)])
        self.span = span
        self.tol = tol

    def apply(self, mesh: mesh_model.MeshModel, geom=None) -> np.ndarray:
        import openseespy.opensees as ops

        along = mesh.node_xy @ self.direction
        on_edge = (np.abs(along) < self.tol) | (np.abs(along - self.span) < self.tol)
        indices = np.where(on_edge)[0]
        assert indices.size > 0, "tidak ada node tepi pada model yang diputar"

        masks = {int(i): [0, 0, 1, 0, 0, 0] for i in indices}
        ordered = sorted(masks, key=lambda i: tuple(mesh.node_xy[i]))
        masks[ordered[0]][0] = 1
        masks[ordered[0]][1] = 1
        masks[ordered[-1]][1] = 1
        for index, dofs in masks.items():
            ops.fix(index + 1, *dofs)
        return np.array(sorted(masks), dtype=np.int64)


def _midspan_element_indices(mesh: mesh_model.MeshModel, nx: int, ny: int) -> np.ndarray:
    """Indeks elemen pada kolom tengah bentang untuk grid terstruktur nx x ny."""
    column = nx // 2
    return np.array([j * nx + column for j in range(ny)], dtype=np.int64)
