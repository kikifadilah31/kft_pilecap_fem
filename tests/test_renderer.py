"""Test `renderer.py` (PRD Bagian 9.3).

Yang diuji bukan "gambarnya bagus" -- itu urusan pemeriksaan visual -- melainkan hal
yang bisa salah diam-diam: satuan colorbar, penanganan NaN, skala yang berpusat di nol,
dan ambang opsvis yang harus MENGUMUMKAN kalau melewati plot.
"""

from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import pytest
from validation_helpers import structured_plate

from pilecap_fem import config, renderer
from pilecap_fem.geometry_builder import (
    EntityResolution,
    GeometryModel,
    GeometryResolution,
    Pier,
    Pile,
    Polygon2D,
    normalize_ccw,
    polygon_from_rect,
)


@pytest.fixture(scope="module")
def sample():
    """Geometri + mesh sederhana yang cukup untuk seluruh plot."""
    mesh = structured_plate(4.8, 4.8, 12, 12)
    mesh_shifted = type(mesh)(
        node_tags=mesh.node_tags,
        node_xy=mesh.node_xy - 2.4,  # pusatkan di origin agar cocok dengan geometri
        elem_tags=mesh.elem_tags,
        elem_conn=mesh.elem_conn,
        elem_area=mesh.elem_area,
        elem_centroid=mesh.elem_centroid - 2.4,
        elem_theta=mesh.elem_theta,
        elem_group=mesh.elem_group,
        group_names=mesh.group_names,
    )
    geom = GeometryModel(
        pilecap=polygon_from_rect(4.8, 4.8, (0.0, 0.0)),
        thickness=1.2,
        piles=tuple(
            Pile(pile_id=f"P{i + 1}", x=x, y=y, diameter=0.8)
            for i, (x, y) in enumerate([(-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)])
        ),
        piers=(
            Pier(
                pier_id="PIER1",
                shape="rectangular",
                centerline=(0.0, 0.0),
                width_x=1.2,
                width_y=1.2,
            ),
        ),
        resolution=GeometryResolution(
            pilecap=EntityResolution(source="json_standard"),
            pile=EntityResolution(source="json_grid"),
            pier=EntityResolution(source="json_standard"),
        ),
    )
    return geom, mesh_shifted


def _values(mesh, kind: str = "diverging") -> np.ndarray:
    x = mesh.elem_centroid[:, 0]
    return x * 1e5 if kind == "diverging" else np.abs(x) * 1e5 + 1.0


# ---------------------------------------------------------------------------
# Kontur
# ---------------------------------------------------------------------------


def test_kontur_menghasilkan_png_tidak_kosong(sample, tmp_path: Path):
    geom, mesh = sample
    path = renderer.render_contour(
        tmp_path / "contour_mx.png",
        geom,
        mesh,
        _values(mesh),
        quantity="moment_per_width",
        title="Momen m_x",
        combo="1.2D+1.6L",
        style=renderer.PlotStyle(dpi=60),
    )
    assert path.is_file()
    assert path.stat().st_size > 5_000


def test_kontur_menerima_nilai_nan_tanpa_melempar(sample, tmp_path: Path):
    """NaN adalah DATA (PRD Core 3), bukan kegagalan -- harus digambar abu-abu."""
    geom, mesh = sample
    values = _values(mesh).copy()
    values[:10] = np.nan
    path = renderer.render_contour(
        tmp_path / "nan.png",
        geom,
        mesh,
        values,
        quantity="moment_per_width",
        title="Momen m_x",
        style=renderer.PlotStyle(dpi=60),
    )
    assert path.is_file()


def test_kontur_seluruhnya_nan_raise(sample, tmp_path: Path):
    geom, mesh = sample
    with pytest.raises(ValueError, match="tidak terdefinisi"):
        renderer.render_contour(
            tmp_path / "all_nan.png",
            geom,
            mesh,
            np.full(mesh.n_elements, np.nan),
            quantity="moment_per_width",
            title="Momen m_x",
            style=renderer.PlotStyle(dpi=60),
        )


def test_norm_diverging_berpusat_nol_saat_nilai_dua_tanda():
    from matplotlib.colors import TwoSlopeNorm

    norm, note = renderer._build_norm(-100.0, 300.0, diverging=True)
    assert isinstance(norm, TwoSlopeNorm)
    assert norm.vcenter == 0.0
    assert note == ""


def test_norm_jatuh_ke_skala_simetris_saat_nilai_satu_tanda():
    """`TwoSlopeNorm` menuntut vmin < 0 < vmax; jangan sampai diam-diam jadi sekuensial."""
    from matplotlib.colors import Normalize

    norm, note = renderer._build_norm(50.0, 300.0, diverging=True)
    assert isinstance(norm, Normalize)
    assert norm.vmin == pytest.approx(-300.0)
    assert norm.vmax == pytest.approx(300.0)
    assert "satu tanda" in note


def test_norm_sekuensial_saat_tidak_diverging():
    from matplotlib.colors import Normalize

    norm, note = renderer._build_norm(0.0, 10.0, diverging=False)
    assert isinstance(norm, Normalize)
    assert norm.vmin == pytest.approx(0.0)
    assert note == ""


# ---------------------------------------------------------------------------
# Nilai nodal -> per elemen
# ---------------------------------------------------------------------------


def test_element_values_from_nodal_merata_ratakan(sample):
    _, mesh = sample
    nodal = np.ones(mesh.n_nodes) * 3.0
    assert renderer.element_values_from_nodal(mesh, nodal) == pytest.approx(
        np.full(mesh.n_elements, 3.0)
    )


def test_element_values_from_nodal_menolak_array_2d(sample):
    """Menyerahkan seluruh matriks (N, 6) harus DITOLAK, bukan menghasilkan (M, 6)."""
    _, mesh = sample
    with pytest.raises(ValueError, match="harus 1-D"):
        renderer.element_values_from_nodal(mesh, np.zeros((mesh.n_nodes, 6)))


def test_element_values_from_nodal_menolak_panjang_salah(sample):
    _, mesh = sample
    with pytest.raises(ValueError, match="node"):
        renderer.element_values_from_nodal(mesh, np.zeros(mesh.n_nodes + 5))


# ---------------------------------------------------------------------------
# Boundary & mesh plan
# ---------------------------------------------------------------------------


def test_boundary_load_check_terbentuk(sample, tmp_path: Path):
    geom, mesh = sample
    path = renderer.render_boundary_load_check(
        tmp_path / config.FILE_BOUNDARY_CHECK, geom, mesh, style=renderer.PlotStyle(dpi=60)
    )
    assert path.is_file()
    assert path.stat().st_size > 5_000


def test_mesh_plan_menampilkan_subjudul_override(sample, tmp_path: Path):
    """PRD Bagian 9.3: override geometri WAJIB terlihat di gambar."""
    geom, mesh = sample
    overridden = GeometryModel(
        pilecap=geom.pilecap,
        thickness=geom.thickness,
        piles=geom.piles,
        piers=geom.piers,
        resolution=GeometryResolution(
            pilecap=EntityResolution(
                source="csv_autodetect", file=Path("input/pilecap_polygon.csv")
            ),
            pile=EntityResolution(source="json_grid"),
            pier=EntityResolution(source="json_standard"),
        ),
    )
    assert renderer._override_subtitle(geom) is None
    subtitle = renderer._override_subtitle(overridden)
    assert subtitle is not None
    assert "GEOMETRI OVERRIDE" in subtitle
    assert "pilecap_polygon.csv" in subtitle

    path = renderer.render_mesh_plan(
        tmp_path / "plan.png", overridden, mesh, style=renderer.PlotStyle(dpi=60)
    )
    assert path.is_file()


# ---------------------------------------------------------------------------
# opsvis: ambang & pengumuman
# ---------------------------------------------------------------------------


def test_ambang_opsvis_dari_config():
    assert renderer.opsvis_would_skip(config.OPSVIS_MAX_ELEMENTS + 1, force=False)
    assert not renderer.opsvis_would_skip(config.OPSVIS_MAX_ELEMENTS, force=False)
    assert not renderer.opsvis_would_skip(config.OPSVIS_MAX_ELEMENTS + 1, force=True)


def test_opsvis_dilewati_mencatat_warning_bukan_diam(tmp_path: Path, caplog):
    """Melewati plot TIDAK boleh senyap -- alasannya harus sampai ke log & laporan."""
    warnings: list[str] = []
    with caplog.at_level(logging.WARNING, logger="pilecap_fem.renderer"):
        result = renderer.render_opsvis_model(
            tmp_path / "model.png",
            n_elements=config.OPSVIS_MAX_ELEMENTS + 1,
            n_fixed_nodes=10,
            force=False,
            warnings=warnings,
        )
    assert result is None
    assert not (tmp_path / "model.png").exists()
    assert len(warnings) == 1
    assert "DILEWATI" in warnings[0]
    assert "--opsvis" in warnings[0]
    assert any("DILEWATI" in r.getMessage() for r in caplog.records)


def test_opsvis_defo_dilewati_juga_mencatat_warning(tmp_path: Path):
    warnings: list[str] = []
    result = renderer.render_opsvis_defo(
        tmp_path / "defo.png",
        combo="X",
        sfac=100.0,
        max_deflection_m=0.001,
        n_elements=config.OPSVIS_MAX_ELEMENTS + 1,
        force=False,
        warnings=warnings,
    )
    assert result is None
    assert len(warnings) == 1


def test_deformation_scale_membuat_lendutan_terlihat(sample):
    """Faktor skala dihitung sendiri agar angkanya DIKETAHUI untuk dicantumkan di judul."""
    _, mesh = sample
    displacements = np.zeros((mesh.n_nodes, 6))
    displacements[:, 2] = -0.001  # 1 mm ke bawah
    sfac = renderer.deformation_scale(mesh, displacements, ratio=0.1)
    span = float(
        max(
            mesh.node_xy[:, 0].max() - mesh.node_xy[:, 0].min(),
            mesh.node_xy[:, 1].max() - mesh.node_xy[:, 1].min(),
        )
    )
    assert sfac == pytest.approx(0.1 * span / 0.001)


def test_deformation_scale_tanpa_lendutan_tidak_membagi_nol(sample):
    _, mesh = sample
    assert renderer.deformation_scale(mesh, np.zeros((mesh.n_nodes, 6))) == 1.0


def test_kegagalan_opsvis_tidak_membatalkan_run(tmp_path: Path):
    """Plot bukan sumber angka desain: kegagalannya dicatat, bukan menghentikan run."""
    warnings: list[str] = []

    def gagal(ax):
        raise RuntimeError("simulasi opsvis rusak")

    result = renderer._render_opsvis(
        tmp_path / "x.png",
        gagal,
        title="uji",
        n_elements=10,
        force=False,
        style=renderer.PlotStyle(dpi=60),
        warnings=warnings,
    )
    assert result is None
    assert len(warnings) == 1
    assert "GAGAL dibuat" in warnings[0]
    assert "TIDAK terpengaruh" in warnings[0]


# ---------------------------------------------------------------------------
# Anotasi wajib
# ---------------------------------------------------------------------------


def test_anotasi_pile_menampilkan_pz_bila_diberikan(sample, tmp_path: Path):
    """PRD Bagian 9.3 meminta label pile memuat ID DAN nilai Pz."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    geom, _ = sample
    fig, ax = plt.subplots()
    renderer._annotate_plan(ax, geom, pz_by_pile={p.pile_id: 1_250_500.0 for p in geom.piles})
    texts = [t.get_text() for t in ax.texts]
    plt.close(fig)

    assert any("P1" in t and "1,250" in t for t in texts)
    assert any("JEPIT" in t for t in texts)


def test_anotasi_tanpa_pz_hanya_menampilkan_id(sample):
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    geom, _ = sample
    fig, ax = plt.subplots()
    renderer._annotate_plan(ax, geom)
    texts = [t.get_text() for t in ax.texts]
    plt.close(fig)

    assert "P1" in texts
    assert not any("kN" in t for t in texts)


def test_anotasi_pier_poligon(tmp_path: Path):
    """Pier poligon (multi-pier) harus ikut teranotasi seperti pier persegi."""
    import matplotlib

    matplotlib.use("Agg", force=True)
    import matplotlib.pyplot as plt

    poly = Polygon2D(normalize_ccw(np.array([[1.0, 1.0], [2.0, 1.0], [2.0, 2.0], [1.0, 2.0]])))
    geom = GeometryModel(
        pilecap=polygon_from_rect(6.0, 6.0, (3.0, 3.0)),
        thickness=1.0,
        piles=(Pile(pile_id="P1", x=4.5, y=4.5, diameter=0.6),),
        piers=(Pier(pier_id="PIER_A", shape="polygon", centerline=(1.5, 1.5), polygon=poly),),
        resolution=GeometryResolution(
            pilecap=EntityResolution(source="json_standard"),
            pile=EntityResolution(source="json_grid"),
            pier=EntityResolution(source="csv_autodetect", file=Path("pier_polygon.csv")),
        ),
    )
    fig, ax = plt.subplots()
    renderer._annotate_plan(ax, geom)
    texts = [t.get_text() for t in ax.texts]
    plt.close(fig)
    assert any("PIER_A" in t for t in texts)


# ---------------------------------------------------------------------------
# Tema (gaya shell-kit)
# ---------------------------------------------------------------------------


def _corner_pixel(path: Path) -> tuple[int, int, int]:
    """Warna piksel sudut kiri-atas -- latar figur, bukan area gambar."""
    import matplotlib.image as mpimg

    data = mpimg.imread(path)
    pixel = data[2, 2]
    return tuple(round(float(c) * 255) for c in pixel[:3])


@pytest.mark.parametrize("name", ["light", "dark"])
def test_tema_menghasilkan_latar_yang_benar_benar_dipakai(sample, tmp_path: Path, name: str):
    """Diperiksa dari PIKSEL, bukan ukuran berkas.

    Tanpa `facecolor` pada `savefig`, PNG tema gelap keluar berlatar PUTIH dengan teks
    terang -- nyaris tak terbaca, dan lolos sempurna bila test hanya memastikan berkas
    lebih besar dari sekian kilobyte.
    """
    geom, mesh = sample
    theme = config.theme(name)
    path = renderer.render_contour(
        tmp_path / f"contour_{name}.png",
        geom,
        mesh,
        _values(mesh),
        quantity="moment_per_width",
        title="Momen m_x",
        style=renderer.PlotStyle(theme=theme, dpi=60),
    )

    expected = tuple(int(theme.background[i : i + 2], 16) for i in (1, 3, 5))
    assert _corner_pixel(path) == expected


def test_kedua_tema_menghasilkan_gambar_yang_berbeda(sample, tmp_path: Path):
    geom, mesh = sample
    paths = []
    for name in ("light", "dark"):
        paths.append(
            renderer.render_contour(
                tmp_path / f"beda_{name}.png",
                geom,
                mesh,
                _values(mesh),
                quantity="moment_per_width",
                title="Momen m_x",
                style=renderer.PlotStyle(theme=config.theme(name), dpi=60),
            )
        )
    assert paths[0].read_bytes() != paths[1].read_bytes()


def test_tema_tidak_dikenal_raise():
    with pytest.raises(KeyError, match="tidak dikenal"):
        config.theme("biru")


# ---------------------------------------------------------------------------
# Metode kontur
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", config.CONTOUR_METHODS)
def test_kedua_metode_kontur_menghasilkan_png(sample, tmp_path: Path, method: str):
    geom, mesh = sample
    path = renderer.render_contour(
        tmp_path / f"metode_{method}.png",
        geom,
        mesh,
        _values(mesh),
        quantity="moment_per_width",
        title="Momen m_x",
        style=renderer.PlotStyle(method=method, dpi=60),
    )
    assert path.is_file()
    assert path.stat().st_size > 5_000


def test_metode_kontur_tidak_dikenal_raise():
    with pytest.raises(ValueError, match="tidak dikenal"):
        renderer.PlotStyle(method="entah")


def test_triangulasi_quad_tidak_terlipat(sample):
    """Dua segitiga per quad harus menutup luas quad-nya, tanpa tumpang tindih.

    Segitiga yang terlipat akan memberi luas total lebih kecil dari luas mesh -- gejala
    yang tidak terlihat pada gambar tetapi merusak seluruh interpolasi `average-nodal`.
    """
    _, mesh = sample
    x, y, tris = renderer._triangulation(mesh)

    a, b, c = x[tris[:, 0]], x[tris[:, 1]], x[tris[:, 2]]
    ay, by, cy = y[tris[:, 0]], y[tris[:, 1]], y[tris[:, 2]]
    signed = 0.5 * ((b - a) * (cy - ay) - (c - a) * (by - ay))

    assert np.all(signed > 0.0), "ada segitiga terlipat (luas bertanda negatif)"
    # Luas dalam mm^2 harus cocok dengan luas mesh dalam m^2.
    assert float(signed.sum()) == pytest.approx(float(mesh.elem_area.sum()) * 1e6, rel=1e-9)


def test_nodal_dari_elemen_mempertahankan_nan(sample):
    """Node yang SELURUH elemennya NaN tetap NaN -- tidak diisi diam-diam tetangganya."""
    _, mesh = sample
    values = np.full(mesh.n_elements, np.nan)
    assert np.all(np.isnan(renderer._nodal_from_elements(mesh, values)))

    values[:] = 5.0
    assert np.allclose(renderer._nodal_from_elements(mesh, values), 5.0)


# ---------------------------------------------------------------------------
# Plot kategorikal
# ---------------------------------------------------------------------------


def test_kategorikal_memakai_label_yang_diberikan(sample, tmp_path: Path):
    geom, mesh = sample
    codes = np.zeros(mesh.n_elements)
    codes[: mesh.n_elements // 3] = 1
    codes[mesh.n_elements // 3 : 2 * mesh.n_elements // 3] = 2

    path = renderer.render_categorical(
        tmp_path / "kategori.png",
        geom,
        mesh,
        codes,
        labels=("D16", "D19", "D22"),
        title="Diameter tulangan",
        style=renderer.PlotStyle(dpi=60),
    )
    assert path.is_file()
    assert path.stat().st_size > 5_000


def test_kategorikal_menandai_yang_tidak_memadai(sample, tmp_path: Path):
    """NaN pada seleksi = tidak ada batang yang cukup besar; harus terlihat, bukan hilang."""
    geom, mesh = sample
    codes = np.ones(mesh.n_elements)
    codes[:5] = np.nan

    path = renderer.render_categorical(
        tmp_path / "kategori_nan.png",
        geom,
        mesh,
        codes,
        labels=("D16",),
        title="Diameter tulangan",
        style=renderer.PlotStyle(dpi=60),
    )
    assert path.is_file()


def test_kategorikal_melebihi_palet_bawaan_tetap_berjalan(sample, tmp_path: Path):
    """Daftar kode bisa lebih panjang dari 25 warna bawaan -- warna tambahan dibangkitkan."""
    geom, mesh = sample
    labels = tuple(f"K{i}" for i in range(30))
    codes = np.linspace(0, 30, mesh.n_elements).round()

    path = renderer.render_categorical(
        tmp_path / "kategori_banyak.png",
        geom,
        mesh,
        codes,
        labels=labels,
        title="Banyak kategori",
        style=renderer.PlotStyle(dpi=60),
    )
    assert path.is_file()
