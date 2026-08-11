"""Test `mesh_engine.py` + `mesh_model.py` (PRD Bagian 15.1).

Test di sini menjalankan meshing sungguhan (beberapa detik per kasus) sehingga ditandai
`@pytest.mark.slow`. Jalankan tanpa test lambat dengan: `pytest -m "not slow"`.

Butir yang WAJIB lulus agar rilis tidak diblokir:
  * `n_tri == 0` untuk ketiga contoh di `examples/`
  * opsi gmsh yang diminta benar-benar ter-set (read-back)
  * Sigma luas sub-face = luas pilecap (rtol 1e-9)
  * setiap physical group pile/pier punya >= 1 elemen
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from pilecap_fem import config, geometry_builder, io_utils, mesh_engine, mesh_model, validators
from pilecap_fem.validators import MeshError

pytestmark = pytest.mark.slow

#: Diimpor dari `config`, TIDAK disalin: daftar ini pernah ada di tiga tempat, dan
#: contoh baru harus otomatis ikut teruji, bukan menunggu tiga daftar disamakan.
EXAMPLE_NAMES = config.EXAMPLE_NAMES


def build(directory: Path, *, no_custom: bool = False):
    """Bangun geometri + mesh dari sebuah folder contoh."""
    loaded = io_utils.load_config(directory / "pilecap_config.json")
    sources = io_utils.resolve_geometry_sources(loaded, input_dir=directory, no_custom=no_custom)
    validators.validate_config_geometry_params(
        loaded.si, io_utils.sources_present(sources.resolution)
    )
    validators.validate_config_mesh(loaded.si)
    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    validators.validate_geometry(
        geom,
        max_overlap_fraction=(loaded.si.get("pier") or {}).get("max_pile_overlap_fraction"),
    )
    validators.validate_mesh_vs_geometry(loaded.si, geom)
    options = mesh_engine.MeshOptions.from_config(loaded.si)
    raw = mesh_engine.generate_mesh(geom, options)
    return geom, options, raw, mesh_model.build_mesh_model(raw)


@pytest.fixture(scope="module")
def meshed(request):
    """Cache hasil meshing per contoh agar tidak di-mesh ulang tiap test."""
    cache: dict[str, tuple] = {}

    def _get(name: str):
        if name not in cache:
            directory = Path(__file__).resolve().parents[1] / "examples" / name
            cache[name] = build(directory)
        return cache[name]

    return _get


# ---------------------------------------------------------------------------
# Release gate: 100% quad
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_mesh_100_persen_quad(name: str, meshed):
    """RILIS DIBLOKIR bila test ini gagal (PRD Bagian 15.1).

    ShellMITC4 tidak menerima elemen 3-node; segitiga yang lolos akan menyebabkan
    lubang pada model FEM.
    """
    _, _, raw, _ = meshed(name)
    assert raw.n_tri == 0, f"{name}: masih ada {raw.n_tri} segitiga"
    assert raw.n_quad > 0


# ---------------------------------------------------------------------------
# Fragment & physical group
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_total_luas_sub_face_sama_dengan_luas_pilecap(name: str, meshed):
    geom, _, raw, _ = meshed(name)
    assert raw.total_surface_area == pytest.approx(geom.pilecap_area, rel=config.AREA_RTOL)


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_setiap_group_pile_dan_pier_punya_elemen(name: str, meshed):
    geom, _, _, mesh = meshed(name)
    counts = mesh.group_element_counts()
    for pile in geom.piles:
        assert counts.get(pile.group_name, 0) > 0, f"{pile.group_name} kosong"
    for pier in geom.piers:
        assert counts.get(pier.group_name, 0) > 0, f"{pier.group_name} kosong"


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_tidak_ada_elemen_tanpa_group(name: str, meshed):
    _, _, _, mesh = meshed(name)
    assert int(sum(mesh.group_element_counts().values())) == mesh.n_elements


def test_multi_pier_menghasilkan_group_terpisah(meshed):
    geom, _, _, mesh = meshed("ex03_custom_polygon")
    assert geom.n_piers == 2
    assert set(mesh.pier_groups()) == {"PIER_PIER_A", "PIER_PIER_B"}
    for name in mesh.pier_groups():
        assert mesh.group_element_counts()[name] > 0
    # Dua pier tidak berbagi elemen.
    a, b = (mesh.group_mask(n) for n in sorted(mesh.pier_groups()))
    assert not np.any(a & b)


def test_jumlah_group_pile_sama_dengan_jumlah_pile(meshed):
    geom, _, _, mesh = meshed("ex03_custom_polygon")
    assert len(mesh.pile_groups()) == geom.n_piles == 12


# ---------------------------------------------------------------------------
# Opsi gmsh (read-back)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_opsi_gmsh_yang_diminta_benar_benar_terset(name: str, meshed):
    """Menangkap salah nama opsi atau perubahan penomoran antar versi gmsh."""
    _, options, raw, _ = meshed(name)
    assert raw.effective_options["Mesh.Algorithm"] == pytest.approx(options.algorithm)
    assert raw.effective_options["Mesh.RecombinationAlgorithm"] == pytest.approx(
        options.recombination_algorithm
    )
    # Mode uniform: MeshSizeMin == MeshSizeMax == size_global
    assert raw.effective_options["Mesh.MeshSizeMin"] == pytest.approx(options.size_global)
    assert raw.effective_options["Mesh.MeshSizeMax"] == pytest.approx(options.size_global)


def test_default_opsi_sesuai_prd(meshed):
    _, options, _, _ = meshed("ex01_standard_4pile")
    assert options.algorithm == config.GMSH_ALGORITHM_DEFAULT == 11
    assert options.recombination_algorithm == config.GMSH_RECOMB_ALGORITHM_DEFAULT == 3


def test_versi_gmsh_tercatat(meshed):
    _, _, raw, _ = meshed("ex01_standard_4pile")
    assert raw.gmsh_version.startswith("4.")


# ---------------------------------------------------------------------------
# Keseragaman mesh mode uniform
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_keseragaman_elemen_group_cap(name: str, meshed):
    """PRD Bagian 17 item 15 -- ambang 0.35 berlaku pada group CAP.

    `area_uniformity_cv` atas SELURUH elemen selalu tinggi (0.35-0.42) karena didominasi
    cincin transisi di sekeliling disk pile: metrik itu mengukur kelengkungan geometri,
    bukan keseragaman mesh.
    """
    _, _, _, mesh = meshed(name)
    assert mesh.area_uniformity_cv_cap <= config.MESH_UNIFORMITY_MAX_CV


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_ukuran_elemen_mendekati_target(name: str, meshed):
    """Luas elemen CAP rata-rata harus dalam orde h^2."""
    _, options, _, mesh = meshed(name)
    cap_area = mesh.elem_area[mesh.group_mask(config.GROUP_CAP)]
    assert np.median(cap_area) == pytest.approx(options.size_global**2, rel=0.35)


# ---------------------------------------------------------------------------
# MeshModel (Cond A)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_luas_elemen_positif_dan_konektivitas_valid(name: str, meshed):
    _, _, _, mesh = meshed(name)
    assert np.all(mesh.elem_area > 0.0)
    assert mesh.elem_conn.min() >= 0
    assert mesh.elem_conn.max() < mesh.n_nodes
    assert mesh.elem_conn.shape == (mesh.n_elements, 4)


@pytest.mark.parametrize("name", EXAMPLE_NAMES)
def test_centroid_setiap_elemen_di_dalam_pilecap(name: str, meshed):
    geom, _, _, mesh = meshed(name)
    cap = geom.pilecap.to_shapely()
    # Uji subset acak agar tetap cepat.
    rng = np.random.default_rng(0)
    sample = rng.choice(mesh.n_elements, size=min(200, mesh.n_elements), replace=False)
    from shapely.geometry import Point

    assert all(cap.covers(Point(*mesh.elem_centroid[i])) for i in sample)


def test_luas_mesh_group_pile_mendekati_luas_analitis(meshed):
    """`A_disk` dari luas mesh (PRD Bagian 7.3) harus mendekati pi*r^2."""
    geom, _, _, mesh = meshed("ex01_standard_4pile")
    for pile in geom.piles:
        assert mesh.group_area(pile.group_name) == pytest.approx(pile.nominal_area, rel=0.02)


def test_total_luas_mesh_mendekati_luas_pilecap(meshed):
    geom, _, _, mesh = meshed("ex01_standard_4pile")
    assert mesh.total_mesh_area == pytest.approx(geom.pilecap_area, rel=1e-3)


def test_nodes_in_group_mengembalikan_node_unik(meshed):
    geom, _, _, mesh = meshed("ex01_standard_4pile")
    nodes = mesh.nodes_in_group(geom.piers[0].group_name)
    assert len(nodes) == len(set(nodes.tolist()))
    assert len(nodes) > 0
    assert nodes.max() < mesh.n_nodes


def test_theta_dalam_rentang_pi(meshed):
    _, _, _, mesh = meshed("ex01_standard_4pile")
    assert np.all(mesh.elem_theta >= -np.pi)
    assert np.all(mesh.elem_theta <= np.pi)


def test_ekspor_csv(meshed, tmp_path: Path):
    _, _, _, mesh = meshed("ex01_standard_4pile")
    nodes_csv = tmp_path / "nodes.csv"
    elements_csv = tmp_path / "elements.csv"
    mesh.write_nodes_csv(nodes_csv)
    mesh.write_elements_csv(elements_csv)

    node_lines = nodes_csv.read_text(encoding="utf-8").splitlines()
    assert node_lines[0] == "node_tag,x [m],y [m],z [m]"  # satuan wajib di header
    assert len(node_lines) == mesh.n_nodes + 1

    elem_lines = elements_csv.read_text(encoding="utf-8").splitlines()
    assert "area [m^2]" in elem_lines[0]
    assert len(elem_lines) == mesh.n_elements + 1


def test_group_mask_untuk_nama_tidak_ada_raise(meshed):
    _, _, _, mesh = meshed("ex01_standard_4pile")
    with pytest.raises(KeyError, match="PILE_TIDAK_ADA"):
        mesh.group_mask("PILE_TIDAK_ADA")


# ---------------------------------------------------------------------------
# Mode graded (Distance + Threshold field)
# ---------------------------------------------------------------------------


def _graded_setup(**mesh_overrides):
    directory = Path(__file__).resolve().parents[1] / "examples" / "ex01_standard_4pile"
    loaded = io_utils.load_config(directory / "pilecap_config.json")
    loaded.si["mesh"].update(
        {"size_mode": "graded", "size_global": 0.30, "size_local_pile": 0.10, **mesh_overrides}
    )
    sources = io_utils.resolve_geometry_sources(loaded, input_dir=directory, no_custom=True)
    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    validators.validate_config_mesh(loaded.si)
    return geom, mesh_engine.MeshOptions.from_config(loaded.si)


def test_graded_menghasilkan_mesh_all_quad():
    geom, options = _graded_setup()
    raw = mesh_engine.generate_mesh(geom, options)
    assert raw.n_tri == 0
    assert raw.n_quad > 0


def test_graded_mesh_size_min_max_sesuai_size_local_dan_global():
    geom, options = _graded_setup()
    raw = mesh_engine.generate_mesh(geom, options)
    assert raw.effective_options["Mesh.MeshSizeMin"] == pytest.approx(0.10)
    assert raw.effective_options["Mesh.MeshSizeMax"] == pytest.approx(0.30)


def test_graded_elemen_dekat_pile_lebih_halus_dari_elemen_jauh():
    """Bukti bahwa field Distance+Threshold benar-benar bekerja, bukan sekadar ter-set."""
    geom, options = _graded_setup()
    raw = mesh_engine.generate_mesh(geom, options)
    mesh = mesh_model.build_mesh_model(raw)

    cap_mask = mesh.group_mask(config.GROUP_CAP)
    centroids = mesh.elem_centroid[cap_mask]
    areas = mesh.elem_area[cap_mask]

    # Jarak tiap centroid CAP ke pusat pile terdekat.
    pile_xy = np.array([[p.x, p.y] for p in geom.piles])
    distance = np.min(np.linalg.norm(centroids[:, None, :] - pile_xy[None, :, :], axis=2), axis=1)

    dekat = areas[distance < 0.6]
    jauh = areas[distance > 1.5]
    assert len(dekat) > 0 and len(jauh) > 0
    assert np.median(dekat) < np.median(jauh)


def test_graded_dengan_refinement_pier_saja():
    geom, options = _graded_setup(size_local_pile=None, size_local_pier=0.12)
    raw = mesh_engine.generate_mesh(geom, options)
    assert raw.n_tri == 0
    assert raw.effective_options["Mesh.MeshSizeMin"] == pytest.approx(0.12)


def test_graded_dengan_refinement_pile_dan_pier():
    geom, options = _graded_setup(size_local_pile=0.10, size_local_pier=0.15)
    raw = mesh_engine.generate_mesh(geom, options)
    assert raw.n_tri == 0
    # MeshSizeMin = min(size_local_*)
    assert raw.effective_options["Mesh.MeshSizeMin"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Jalur --no-custom
# ---------------------------------------------------------------------------


def test_no_custom_menghasilkan_geometri_standar_yang_sah():
    """ex03 dengan --no-custom harus jatuh ke persegi + grid 4x3 + satu pier."""
    directory = Path(__file__).resolve().parents[1] / "examples" / "ex03_custom_polygon"
    geom, _, raw, mesh = build(directory, no_custom=True)

    assert geom.pilecap.n_vertices == 4
    assert geom.pilecap_area == pytest.approx(8.0 * 7.0)
    assert geom.n_piles == 12
    assert geom.n_piers == 1
    assert geom.piers[0].pier_id == "PIER1"
    assert raw.n_tri == 0
    assert mesh.group_element_counts()["PIER_PIER1"] > 0


# ---------------------------------------------------------------------------
# Jalur kegagalan meshing
# ---------------------------------------------------------------------------


def _triangle_producing_setup():
    """Konfigurasi yang SENGAJA menghasilkan segitiga, untuk menguji jalur kegagalan.

    Catatan hasil pengukuran: `Mesh.Algorithm = 11` (Quasi-structured Quad) sudah
    menghasilkan mesh 100% quad SENDIRI, bahkan ketika `setRecombine` tidak dipanggil.
    Karena itu mematikan `recombine` saja tidak cukup untuk memunculkan segitiga --
    algoritma 2D-nya juga harus diganti ke algoritma berbasis segitiga
    (6 = Frontal-Delaunay).
    """
    directory = Path(__file__).resolve().parents[1] / "examples" / "ex01_standard_4pile"
    loaded = io_utils.load_config(directory / "pilecap_config.json")
    loaded.si["mesh"]["recombine"] = False
    loaded.si["mesh"]["algorithm"] = 6
    loaded.si["mesh"]["size_global"] = 0.30  # kasar agar cepat

    sources = io_utils.resolve_geometry_sources(loaded, input_dir=directory, no_custom=True)
    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    return geom, mesh_engine.MeshOptions.from_config(loaded.si)


def test_segitiga_tersisa_menghasilkan_raise():
    geom, options = _triangle_producing_setup()
    with pytest.raises(MeshError, match="all-quad"):
        mesh_engine.generate_mesh(geom, options)


def test_pesan_raise_menyebut_jumlah_dan_centroid_segitiga():
    geom, options = _triangle_producing_setup()
    with pytest.raises(MeshError) as excinfo:
        mesh_engine.generate_mesh(geom, options)
    message = str(excinfo.value)
    assert "Centroid segitiga" in message
    assert "ShellMITC4 tidak menerima elemen 3-node" in message


def test_allow_tri_melewati_cek_dengan_warning():
    geom, options = _triangle_producing_setup()
    raw = mesh_engine.generate_mesh(geom, options, allow_tri=True)
    assert raw.n_tri > 0
    assert any("TIDAK ALL-QUAD" in w for w in raw.warnings)
    # Mesh murni segitiga: cek lanjutan dilewati, tapi dinyatakan eksplisit.
    assert any("DILEWATI" in w for w in raw.warnings)


def test_algorithm_11_all_quad_tanpa_recombine():
    """Bukti bahwa Algorithm 11 sendiri sudah menghasilkan all-quad.

    Ini menjelaskan mengapa `recombine=false` saja tidak memunculkan segitiga, dan
    mengapa `RecombinationAlgorithm = 3` berfungsi sebagai lapis pengaman kedua, bukan
    satu-satunya mekanisme (PRD Bagian 5.1(f)).
    """
    directory = Path(__file__).resolve().parents[1] / "examples" / "ex01_standard_4pile"
    loaded = io_utils.load_config(directory / "pilecap_config.json")
    loaded.si["mesh"]["recombine"] = False
    loaded.si["mesh"]["size_global"] = 0.30

    sources = io_utils.resolve_geometry_sources(loaded, input_dir=directory, no_custom=True)
    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    raw = mesh_engine.generate_mesh(geom, mesh_engine.MeshOptions.from_config(loaded.si))
    assert raw.n_tri == 0


def test_export_msh(tmp_path: Path):
    directory = Path(__file__).resolve().parents[1] / "examples" / "ex01_standard_4pile"
    loaded = io_utils.load_config(directory / "pilecap_config.json")
    loaded.si["mesh"]["size_global"] = 0.20
    sources = io_utils.resolve_geometry_sources(loaded, input_dir=directory, no_custom=True)
    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    options = mesh_engine.MeshOptions.from_config(loaded.si)

    target = tmp_path / "model.msh"
    mesh_engine.generate_mesh(geom, options, export_msh=target)
    assert target.is_file()
    assert target.stat().st_size > 0
