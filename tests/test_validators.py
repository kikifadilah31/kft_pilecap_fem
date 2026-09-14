"""Test `validators.py` -- setiap aturan PRD Bagian 5.3 MEMANG melempar exception.

Struktur test ini disengaja parametrized/eksplisit per aturan (PRD Bagian 15.1), agar
kegagalan langsung menunjuk nomor rule yang bocor.
"""

from __future__ import annotations

import numpy as np
import pytest

from pilecap_fem import config, geometry_builder, validators
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
from pilecap_fem.validators import GeometryError, InputError, MeshError

ALL_JSON = {"pilecap": False, "pile": False, "pier": False}


def base_cfg() -> dict:
    """Config SI yang valid; test memodifikasi satu hal untuk memicu satu rule."""
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
            "support": "fixed",
        },
        "material": {"fc": 30e6, "E": 25e9, "E_source": "uji lab", "poisson": 0.2, "density": 24e3},
        "mesh": {
            "size_mode": "uniform",
            "size_global": 0.13,
            "size_local_pile": None,
            "size_local_pier": None,
            "algorithm": 11,
            "recombination_algorithm": 3,
            "recombine": True,
            "require_all_quad": True,
            "element_order": 1,
        },
    }


def make_geom(
    *,
    cap: Polygon2D | None = None,
    piles: tuple[Pile, ...] | None = None,
    piers: tuple[Pier, ...] | None = None,
) -> GeometryModel:
    resolution = GeometryResolution(
        pilecap=EntityResolution(source="json_standard"),
        pile=EntityResolution(source="json_grid"),
        pier=EntityResolution(source="json_standard"),
    )
    default_piles = tuple(
        Pile(pile_id=f"P{i + 1}", x=x, y=y, diameter=0.8)
        for i, (x, y) in enumerate([(-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)])
    )
    default_pier = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=1.2, width_y=1.2),
    )
    piles_final = default_piles if piles is None else piles
    piers_final = default_pier if piers is None else piers
    return GeometryModel(
        pilecap=polygon_from_rect(4.8, 4.8, (0.0, 0.0)) if cap is None else cap,
        thickness=1.2,
        piles=piles_final,
        piers=piers_final,
        resolution=resolution,
        # Dihitung seperti `build_geometry_model`, supaya test bekerja pada model yang sama
        # bentuknya dengan yang dipakai produksi.
        overlaps=geometry_builder.compute_pile_pier_overlaps(piles_final, piers_final),
    )


def test_baseline_valid():
    """Sanity: konfigurasi & geometri dasar harus LOLOS semua validator."""
    cfg = base_cfg()
    geom = make_geom()
    validators.validate_config_geometry_params(cfg, ALL_JSON)
    validators.validate_config_mesh(cfg)
    validators.validate_material(cfg)
    validators.validate_geometry(geom)
    validators.validate_mesh_vs_geometry(cfg, geom)


# ---------------------------------------------------------------------------
# Rentang fisik (rule 5, 6) & material
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("block", "key", "value"),
    [
        ("pilecap", "thickness", 0.0),
        ("pilecap", "thickness", -1.0),
        ("pilecap", "length_x", 0.0),
        ("pilecap", "length_y", -4.0),
        ("pile", "diameter", 0.0),
        ("pile", "spacing_x", -2.0),
        ("pier", "width_x", 0.0),
    ],
)
def test_rule5_nilai_tidak_positif_raise(block: str, key: str, value: float):
    cfg = base_cfg()
    cfg[block][key] = value
    with pytest.raises(InputError, match="harus > 0"):
        validators.validate_config_geometry_params(cfg, ALL_JSON)


@pytest.mark.parametrize("poisson", [-0.01, 0.5, 0.7])
def test_rule6_poisson_di_luar_rentang_raise(poisson: float):
    cfg = base_cfg()
    cfg["material"]["poisson"] = poisson
    with pytest.raises(InputError, match="poisson"):
        validators.validate_material(cfg)


@pytest.mark.parametrize("poisson", [0.0, 0.15, 0.2, 0.49])
def test_poisson_dalam_rentang_lolos(poisson: float):
    cfg = base_cfg()
    cfg["material"]["poisson"] = poisson
    validators.validate_material(cfg)


def test_E_null_raise_dan_tidak_menghitung_dari_fc():
    """Keputusan user (PRD Bagian 17 item 4): tool TIDAK PERNAH menurunkan E dari f'c."""
    cfg = base_cfg()
    cfg["material"]["E"] = None
    with pytest.raises(InputError, match="TIDAK menghitung modulus elastisitas"):
        validators.validate_material(cfg)


def test_E_source_wajib_diisi():
    cfg = base_cfg()
    cfg["material"]["E_source"] = "  "
    with pytest.raises(InputError, match="E_source"):
        validators.validate_material(cfg)


def test_material_tidak_dicek_oleh_validator_geometri():
    """`pilecap-mesh` tidak boleh gagal hanya karena E belum diisi."""
    cfg = base_cfg()
    cfg["material"]["E"] = None
    validators.validate_config_geometry_params(cfg, ALL_JSON)  # tidak raise
    validators.validate_config_mesh(cfg)  # tidak raise


# ---------------------------------------------------------------------------
# Parameter mesh (rule 7, 7a, 7b, 7c, 7d)
# ---------------------------------------------------------------------------


def test_rule7_mesh_terlalu_kasar_raise():
    cfg = base_cfg()
    cfg["mesh"]["size_global"] = 4.8 * config.MESH_SIZE_MAX_FRACTION + 0.01
    with pytest.raises(InputError, match="terlalu kasar"):
        validators.validate_mesh_vs_geometry(cfg, make_geom())


def test_rule7a_pile_kurang_terdiskretisasi_raise():
    cfg = base_cfg()
    cfg["mesh"]["size_global"] = 0.5  # D/h = 0.8/0.5 = 1.6 < 6
    with pytest.raises(InputError, match=r"D_pile/h"):
        validators.validate_mesh_vs_geometry(cfg, make_geom())


def test_rule7a_pesan_menyebut_ukuran_mesh_maksimum():
    cfg = base_cfg()
    cfg["mesh"]["size_global"] = 0.5
    with pytest.raises(InputError) as excinfo:
        validators.validate_mesh_vs_geometry(cfg, make_geom())
    # 0.8 / 6 = 0.1333 m = 133 mm
    assert "133 mm" in str(excinfo.value)


def test_rule7a_tepat_di_ambang_lolos():
    cfg = base_cfg()
    cfg["mesh"]["size_global"] = 0.8 / config.MIN_ELEM_PER_PILE_DIAMETER
    validators.validate_mesh_vs_geometry(cfg, make_geom())


def test_rule7a_angka_bulat_tepat_di_ambang_lolos_meski_pembulatan_floating_point():
    """D600 dengan mesh 100 mm TEPAT memenuhi D/h = 6 -- dan dulu DITOLAK.

    Di floating point, 0,6 / 0,1 = 5,999999999999999. Test `tepat_di_ambang` di atas tidak
    menangkapnya karena 0,8 / (0,8/6) kebetulan dibulatkan ke arah yang aman; yang ini
    memakai pasangan angka bulat yang benar-benar diketik pengguna dan benar-benar gagal.
    Pesan galatnya waktu itu menyarankan "turunkan ke <= 100 mm" -- nilai yang sudah dipakai.
    """
    cfg = base_cfg()
    cfg["mesh"]["size_global"] = 0.1
    piles = tuple(
        Pile(pile_id=f"P{i + 1}", x=x, y=y, diameter=0.6)
        for i, (x, y) in enumerate([(-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)])
    )
    assert config.MIN_ELEM_PER_PILE_DIAMETER > 0.6 / 0.1, "prasyarat test: pembulatan harus terjadi"
    validators.validate_mesh_vs_geometry(cfg, make_geom(piles=piles))


def test_rule7a_saran_ukuran_mesh_selalu_meloloskan_aturannya():
    """Batas atas dibulatkan KE BAWAH. Pembulatan biasa akan menyarankan 109 mm untuk D651,6,
    padahal 0,6516 / 0,109 = 5,98 < 6 -- saran yang tetap ditolak.
    """
    cfg = base_cfg()
    cfg["mesh"]["size_global"] = 0.5
    piles = tuple(
        Pile(pile_id=f"P{i + 1}", x=x, y=y, diameter=0.6516)
        for i, (x, y) in enumerate([(-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)])
    )
    with pytest.raises(InputError) as excinfo:
        validators.validate_mesh_vs_geometry(cfg, make_geom(piles=piles))
    saran_mm = int(str(excinfo.value).split("<= ")[1].split(" mm")[0])
    cfg["mesh"]["size_global"] = saran_mm / 1000.0
    validators.validate_mesh_vs_geometry(cfg, make_geom(piles=piles))


def test_rule7a_mode_graded_memakai_size_local_pile():
    """PRD menulis rule 7a terhadap `size_global`, rumusan yang mengasumsikan mode uniform.

    Pada mode graded, area pile di-mesh dengan `size_local_pile`, sehingga itulah ukuran
    yang menentukan apakah lingkaran pile terdiskretisasi memadai.
    """
    cfg = base_cfg()
    cfg["mesh"].update({"size_mode": "graded", "size_global": 0.30, "size_local_pile": 0.10})
    validators.validate_mesh_vs_geometry(cfg, make_geom())  # D/h_pile = 8 >= 6, lolos


def test_rule7a_graded_dengan_size_local_pile_masih_terlalu_kasar_raise():
    cfg = base_cfg()
    cfg["mesh"].update({"size_mode": "graded", "size_global": 0.30, "size_local_pile": 0.25})
    with pytest.raises(InputError, match="size_local_pile"):
        validators.validate_mesh_vs_geometry(cfg, make_geom())


def test_rule7a_graded_tanpa_size_local_pile_tetap_memakai_size_global():
    """Refinement hanya di pier -> area pile tetap dinilai terhadap `size_global`."""
    cfg = base_cfg()
    cfg["mesh"].update({"size_mode": "graded", "size_global": 0.30, "size_local_pier": 0.10})
    with pytest.raises(InputError, match="size_global"):
        validators.validate_mesh_vs_geometry(cfg, make_geom())


@pytest.mark.parametrize("key", ["size_local_pile", "size_local_pier"])
def test_rule7b_uniform_dengan_size_local_raise(key: str):
    cfg = base_cfg()
    cfg["mesh"][key] = 0.05
    with pytest.raises(InputError, match="TIDAK akan berpengaruh"):
        validators.validate_config_mesh(cfg)


def test_graded_tanpa_size_local_raise():
    cfg = base_cfg()
    cfg["mesh"]["size_mode"] = "graded"
    with pytest.raises(InputError, match="tidak ada `size_local"):
        validators.validate_config_mesh(cfg)


def test_graded_dengan_size_local_lebih_besar_dari_global_raise():
    cfg = base_cfg()
    cfg["mesh"].update({"size_mode": "graded", "size_local_pile": 0.30})
    with pytest.raises(InputError, match="harus LEBIH HALUS"):
        validators.validate_config_mesh(cfg)


def test_graded_valid_lolos():
    cfg = base_cfg()
    cfg["mesh"].update({"size_mode": "graded", "size_local_pile": 0.06})
    validators.validate_config_mesh(cfg)


@pytest.mark.parametrize("order", [0, 2, 3])
def test_rule7c_element_order_selain_1_raise(order: int):
    cfg = base_cfg()
    cfg["mesh"]["element_order"] = order
    with pytest.raises(InputError, match="belum didukung"):
        validators.validate_config_mesh(cfg)


@pytest.mark.parametrize(("key", "value"), [("algorithm", 99), ("recombination_algorithm", 7)])
def test_rule7d_opsi_gmsh_tidak_sah_raise(key: str, value: int):
    cfg = base_cfg()
    cfg["mesh"][key] = value
    with pytest.raises(InputError, match="gmsh yang sah"):
        validators.validate_config_mesh(cfg)


def test_size_mode_tidak_dikenal_raise():
    cfg = base_cfg()
    cfg["mesh"]["size_mode"] = "adaptive"
    with pytest.raises(InputError, match="size_mode"):
        validators.validate_config_mesh(cfg)


# ---------------------------------------------------------------------------
# Kelengkapan parameter JSON (rule 13e, 13f)
# ---------------------------------------------------------------------------


def test_rule13f_parameter_json_tidak_lengkap_raise():
    cfg = base_cfg()
    cfg["pilecap"]["length_x"] = None
    with pytest.raises(InputError, match="rule 13f"):
        validators.validate_config_geometry_params(cfg, ALL_JSON)


def test_rule13f_parameter_boleh_kosong_bila_ada_csv_override():
    cfg = base_cfg()
    cfg["pilecap"]["length_x"] = None
    cfg["pilecap"]["origin"] = None
    validators.validate_config_geometry_params(cfg, {**ALL_JSON, "pilecap": True})


def test_rule13e_pier_shape_tidak_sah_raise():
    cfg = base_cfg()
    cfg["pier"]["shape"] = "hexagonal"
    with pytest.raises(InputError, match="rule 13e"):
        validators.validate_config_geometry_params(cfg, ALL_JSON)


def test_pier_shape_tidak_sah_boleh_bila_ada_pier_polygon_csv():
    cfg = base_cfg()
    cfg["pier"]["shape"] = "hexagonal"
    validators.validate_config_geometry_params(cfg, {**ALL_JSON, "pier": True})


def test_pier_support_selain_fixed_raise():
    cfg = base_cfg()
    cfg["pier"]["support"] = "spring"
    with pytest.raises(InputError, match="belum didukung"):
        validators.validate_config_geometry_params(cfg, ALL_JSON)


# ---------------------------------------------------------------------------
# Konsistensi geometri (rule 8, 9, 10, 11, 12, 14)
# ---------------------------------------------------------------------------


def test_rule8_pile_di_luar_pilecap_raise():
    piles = (Pile(pile_id="P1", x=10.0, y=0.0, diameter=0.8),)
    with pytest.raises(GeometryError, match="DI LUAR"):
        validators.validate_geometry(make_geom(piles=piles))


def test_rule9_pile_memotong_tepi_pilecap_raise():
    # Pusat 0.2 m dari tepi (x = 2.4), radius 0.4 -> memotong.
    piles = (Pile(pile_id="P1", x=2.2, y=0.0, diameter=0.8),)
    with pytest.raises(GeometryError, match="memotong tepi"):
        validators.validate_geometry(make_geom(piles=piles))


def test_rule10_dua_pile_tumpang_tindih_raise():
    piles = (
        Pile(pile_id="P1", x=-1.2, y=-1.2, diameter=0.8),
        Pile(pile_id="P2", x=-1.0, y=-1.2, diameter=0.8),
    )
    with pytest.raises(GeometryError, match="tumpang tindih"):
        validators.validate_geometry(make_geom(piles=piles))


def test_rule11_pier_tidak_seluruhnya_di_dalam_pilecap_raise():
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(2.4, 0.0), width_x=1.2, width_y=1.2),
    )
    with pytest.raises(GeometryError, match="tidak seluruhnya berada di dalam"):
        validators.validate_geometry(make_geom(piers=piers))


def test_rule12_polygon_self_intersecting_raise():
    bowtie = Polygon2D(np.array([[0.0, 0.0], [4.0, 4.0], [4.0, 0.0], [0.0, 4.0]]))
    with pytest.raises(GeometryError, match="tidak valid"):
        validators.validate_geometry(make_geom(cap=bowtie))


def test_rule14_pier_tumpang_tindih_pile_raise():
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=3.0, width_y=3.0),
    )
    with pytest.raises(GeometryError, match="rule 14"):
        validators.validate_geometry(make_geom(piers=piers))


# ---------------------------------------------------------------------------
# Tumpang tindih pile-pier (v0.9.0)
# ---------------------------------------------------------------------------


def _geom_bersinggungan() -> GeometryModel:
    """Pile yang menyinggung muka pier TEPAT: luas irisan nol, tetapi bersentuhan.

    Pier setengah-lebar 0,6 m; pile berjari-jari 0,4 m berpusat di x = 1,0 m, sehingga
    tepinya tepat menyentuh x = 0,6 m.
    """
    piles = (Pile(pile_id="P1", x=1.0, y=0.0, diameter=0.8),)
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=1.2, width_y=1.2),
    )
    return make_geom(piles=piles, piers=piers)


def test_bersinggungan_ditolak_tanpa_opsi():
    """Lubang yang ditutup v0.9.0: kondisi ini LOLOS rule 14 versi lama (`area > 0.0`).

    Node di titik sentuh menjadi milik grup pile sekaligus pier: ia dijepit tetapi tetap
    dibebani, sehingga bebannya terserap ke reaksi tanpa melenturkan pelat -- dan VC-0
    tetap lulus karena kedua sisi neracanya memuat gaya yang sama.
    """
    geom = _geom_bersinggungan()
    assert geom.overlaps == (), "persinggungan berluas nol tidak boleh jadi PileOverlap"
    with pytest.raises(GeometryError, match="BERSINGGUNGAN"):
        validators.validate_geometry(geom)


def test_bersinggungan_ditolak_meski_opsi_diisi():
    """Ditolak SELALU, berbeda dari tumpang tindih berluas.

    Pada persinggungan tidak ada lensa untuk dibagi, sehingga 100% dari yang terserap
    adalah artefak diskretisasi murni -- tidak ada komponen geometri yang dapat dihitung
    dan dilaporkan.
    """
    with pytest.raises(GeometryError, match="BERSINGGUNGAN"):
        validators.validate_geometry(_geom_bersinggungan(), max_overlap_fraction=0.9)


def _geom_overlap() -> GeometryModel:
    """Pile berpusat 0,3 m di luar muka pier -> f = 7,21% (kasus terverifikasi gmsh)."""
    piles = (Pile(pile_id="P1", x=0.9, y=0.0, diameter=0.8),)
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=1.2, width_y=1.2),
    )
    return make_geom(piles=piles, piers=piers)


def test_overlap_ditolak_bila_opsi_tidak_diisi():
    """Perilaku bawaan HARUS sama persis dengan sebelum v0.9.0."""
    with pytest.raises(GeometryError, match="rule 14"):
        validators.validate_geometry(_geom_overlap())


def test_overlap_di_bawah_ambang_diterima_dengan_peringatan():
    peringatan = validators.validate_geometry(_geom_overlap(), max_overlap_fraction=0.15)
    assert peringatan, "overlap yang diizinkan tetap wajib memunculkan peringatan"
    assert "TUMPANG TINDIH" in peringatan[0]
    assert "7.2%" in peringatan[0]
    # Peringatan ini juga dikirim ke log konsol (cp1252 di Windows); satu karakter
    # non-ASCII akan melempar UnicodeEncodeError dan MENGHENTIKAN run.
    assert all(ord(c) < 128 for c in peringatan[0])


def test_overlap_di_atas_ambang_ditolak_menyebut_fraksi_dan_ambang():
    with pytest.raises(GeometryError, match="MELEBIHI batas"):
        validators.validate_geometry(_geom_overlap(), max_overlap_fraction=0.05)


def test_id_mengandung_pemisah_group_lens_ditolak():
    """Nama group lensa DIBENTUK, tidak pernah diurai -- id ambigu harus ditolak."""
    piles = (Pile(pile_id=f"P{config.GROUP_LENS_SEP}1", x=0.9, y=0.0, diameter=0.8),)
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=1.2, width_y=1.2),
    )
    with pytest.raises(GeometryError, match="pemisah nama physical group"):
        validators.validate_geometry(make_geom(piles=piles, piers=piers), max_overlap_fraction=0.9)


@pytest.mark.parametrize("nilai", [0.0, -0.1, 1.5, 1.0001])
def test_max_pile_overlap_fraction_di_luar_rentang_ditolak(nilai: float):
    cfg = base_cfg()
    cfg["pier"]["max_pile_overlap_fraction"] = nilai
    with pytest.raises(InputError, match="lebih dari 0 dan paling besar 1"):
        validators.validate_config_geometry_params(cfg, ALL_JSON)


def test_max_pile_overlap_fraction_satu_diterima():
    """1,0 SAH: pile yang seluruhnya berada di bawah pier.

    Sampai v0.13.1 nilai ini ditolak, sehingga konfigurasi yang sangat lazim -- grup 3x3
    dengan pile tengah tepat di bawah kolom -- tidak dapat dianalisis dengan config apa pun:
    kosong ditolak karena ada tumpang tindih, 0,99 ditolak karena tumpang tindihnya 100%,
    dan 1,0 ditolak oleh pemeriksaan rentang ini.
    """
    cfg = base_cfg()
    cfg["pier"]["max_pile_overlap_fraction"] = 1.0
    validators.validate_config_geometry_params(cfg, ALL_JSON)


def _geom_pile_di_bawah_pier() -> GeometryModel:
    """Pile D800 berpusat tepat di tengah pier 1,2 x 1,2 -> seluruh cakram di dalam pier."""
    piles = (Pile(pile_id="P1", x=0.0, y=0.0, diameter=0.8),)
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=1.2, width_y=1.2),
    )
    return make_geom(piles=piles, piers=piers)


def test_pile_seluruhnya_di_bawah_pier_diterima_dengan_batas_satu():
    peringatan = validators.validate_geometry(_geom_pile_di_bawah_pier(), max_overlap_fraction=1.0)
    assert peringatan and "TUMPANG TINDIH" in peringatan[0]


def test_saran_menaikkan_batas_selalu_dapat_diikuti():
    """Pesan galat tidak boleh menyarankan nilai yang tetap ditolak.

    Dua jalan buntu yang pernah ada: menyarankan "naikkan batasnya" untuk tumpang tindih
    100% padahal 1,0 ditolak; dan -- bila dibulatkan biasa -- menyarankan 0.07 untuk
    tumpang tindih 7,2%, nilai yang juga tetap ditolak.
    """
    with pytest.raises(GeometryError) as penuh:
        validators.validate_geometry(_geom_pile_di_bawah_pier(), max_overlap_fraction=0.99)
    assert "1.00" in str(penuh.value)

    with pytest.raises(GeometryError) as sebagian:
        validators.validate_geometry(_geom_overlap(), max_overlap_fraction=0.05)
    saran = float(str(sebagian.value).split("paling sedikit ")[1].split()[0])
    assert saran >= 0.0721, f"saran {saran} tidak meloloskan tumpang tindih 7,21%"
    validators.validate_geometry(_geom_overlap(), max_overlap_fraction=saran)


def test_max_pile_overlap_fraction_tidak_dikonversi_satuan(tmp_path):
    """Nirdimensi -- TIDAK boleh ikut `io_utils._LENGTH_SCALARS`.

    Fraksi yang diam-diam dikali 1e-3 akan katastrofik dan tak terlihat: 0,25 menjadi
    0,00025 sehingga setiap overlap ditolak dengan pesan yang membingungkan.
    """
    import json

    from pilecap_fem import io_utils

    path = tmp_path / "pilecap_config.json"
    path.write_text(
        json.dumps({"units": {"length": "mm"}, "pier": {"max_pile_overlap_fraction": 0.25}}),
        encoding="utf-8",
    )
    assert io_utils.load_config(path).si["pier"]["max_pile_overlap_fraction"] == 0.25


def test_multi_pier_tumpang_tindih_raise():
    piers = (
        Pier(pier_id="A", shape="rectangular", centerline=(0.0, 0.0), width_x=1.2, width_y=1.2),
        Pier(pier_id="B", shape="rectangular", centerline=(0.5, 0.0), width_x=1.2, width_y=1.2),
    )
    with pytest.raises(GeometryError, match="saling tumpang tindih"):
        validators.validate_geometry(make_geom(piers=piers))


def test_multi_pier_terpisah_lolos():
    piles = (
        Pile(pile_id="P1", x=-2.0, y=-2.0, diameter=0.6),
        Pile(pile_id="P2", x=2.0, y=2.0, diameter=0.6),
    )
    piers = (
        Pier(pier_id="A", shape="rectangular", centerline=(-1.0, 1.0), width_x=1.0, width_y=1.0),
        Pier(pier_id="B", shape="rectangular", centerline=(1.0, -1.0), width_x=1.0, width_y=1.0),
    )
    validators.validate_geometry(make_geom(piles=piles, piers=piers))


def test_tanpa_pile_atau_pier_raise():
    with pytest.raises(GeometryError, match="Tidak ada pile"):
        validators.validate_geometry(make_geom(piles=()))


# ---------------------------------------------------------------------------
# Aturan CSV polygon (rule 13a, 13b, 13c)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ids",
    [
        [1, 2, 2, 4],  # duplikat
        [1, 2, 4, 5],  # ada lompatan
        [0, 1, 2, 3],  # tidak mulai dari 1
    ],
)
def test_rule13a_vertex_id_tidak_sah_raise(ids: list[int], tmp_path):
    with pytest.raises(InputError, match="vertex_id"):
        validators.check_polygon_vertex_ids(np.array(ids), tmp_path / "poly.csv")


def test_rule13a_vertex_id_bukan_integer_raise(tmp_path):
    with pytest.raises(InputError, match="bilangan bulat"):
        validators.check_polygon_vertex_ids(np.array([1.0, 2.5, 3.0]), tmp_path / "poly.csv")


def test_rule13a_vertex_id_urut_lolos(tmp_path):
    validators.check_polygon_vertex_ids(np.array([3, 1, 2, 4]), tmp_path / "poly.csv")


def test_rule13b_titik_identik_tidak_berdampingan_raise(tmp_path):
    vertices = np.array([[0.0, 0.0], [4.0, 0.0], [0.0, 0.0], [0.0, 4.0]])
    with pytest.raises(InputError, match="terlipat"):
        validators.check_polygon_no_folded_duplicates(vertices, tmp_path / "poly.csv")


def test_rule13c_polygon_degenerate_raise(tmp_path):
    with pytest.raises(InputError, match="degenerate"):
        validators.check_polygon_area(0.0, tmp_path / "poly.csv")


def test_polygon_titik_segaris_degenerate(tmp_path):
    collinear = Polygon2D(normalize_ccw(np.array([[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]])))
    with pytest.raises(InputError, match="degenerate"):
        validators.check_polygon_area(collinear.area, tmp_path / "poly.csv")


# ---------------------------------------------------------------------------
# Hasil mesh
# ---------------------------------------------------------------------------


def _mesh_result_kwargs(**overrides):
    kwargs = {
        "n_quad": 100,
        "n_tri": 0,
        "tri_centroids": np.empty((0, 2)),
        "require_all_quad": True,
        "group_element_counts": {"CAP": 60, "PILE_P1": 20, "PIER_PIER1": 20},
        "total_group_area": 23.04,
        "pilecap_area": 23.04,
        "n_ungrouped": 0,
    }
    kwargs.update(overrides)
    return kwargs


def test_mesh_result_baseline_lolos():
    assert validators.validate_mesh_result(**_mesh_result_kwargs()) == []


def test_segitiga_tersisa_raise_dengan_centroid():
    with pytest.raises(MeshError, match=r"all-quad") as excinfo:
        validators.validate_mesh_result(
            **_mesh_result_kwargs(n_tri=2, tri_centroids=np.array([[1.0, 2.0], [3.0, 4.0]]))
        )
    assert "(1.0000, 2.0000)" in str(excinfo.value)


def test_allow_tri_menghasilkan_warning_bukan_raise():
    warnings = validators.validate_mesh_result(
        **_mesh_result_kwargs(
            n_tri=2, tri_centroids=np.array([[1.0, 2.0], [3.0, 4.0]]), require_all_quad=False
        )
    )
    assert any("TIDAK ALL-QUAD" in w for w in warnings)


def test_mesh_murni_segitiga_melewati_cek_lanjutan_dengan_warning():
    warnings = validators.validate_mesh_result(
        **_mesh_result_kwargs(
            n_quad=0,
            n_tri=50,
            tri_centroids=np.zeros((50, 2)),
            require_all_quad=False,
            group_element_counts={"CAP": 0, "PILE_P1": 0, "PIER_PIER1": 0},
        )
    )
    assert any("DILEWATI" in w for w in warnings)


def test_mesh_kosong_raise():
    with pytest.raises(MeshError, match="satu pun elemen"):
        validators.validate_mesh_result(**_mesh_result_kwargs(n_quad=0, n_tri=0))


def test_group_pile_kosong_raise():
    with pytest.raises(MeshError, match="bug diam-diam paling berbahaya"):
        validators.validate_mesh_result(
            **_mesh_result_kwargs(group_element_counts={"CAP": 80, "PILE_P1": 0, "PIER_PIER1": 20})
        )


def test_group_cap_kosong_tidak_raise():
    """Hanya group PILE/PIER yang kosong berbahaya -- CAP kosong secara teori mungkin."""
    validators.validate_mesh_result(
        **_mesh_result_kwargs(group_element_counts={"CAP": 0, "PILE_P1": 80, "PIER_PIER1": 20})
    )


def test_elemen_tanpa_group_raise():
    with pytest.raises(MeshError, match="tidak masuk physical group"):
        validators.validate_mesh_result(**_mesh_result_kwargs(n_ungrouped=3))


def test_luas_group_tidak_cocok_raise():
    with pytest.raises(MeshError, match="tidak sama dengan"):
        validators.validate_mesh_result(**_mesh_result_kwargs(total_group_area=23.05))


def test_jumlah_elemen_besar_menghasilkan_warning():
    warnings = validators.validate_mesh_result(
        **_mesh_result_kwargs(n_quad=config.MESH_ELEMENT_WARN_LIMIT + 1)
    )
    assert any("melebihi" in w for w in warnings)


# ---------------------------------------------------------------------------
# Skema desain: mode tulangan & sengkang
# ---------------------------------------------------------------------------


def _design_cfg(**override: object) -> dict:
    design: dict[str, object] = {
        "fy": 420e6,
        "fy_source": "uji",
        "rebar_mode": "spacing_fixed",
        "rebar_spacing": 0.15,
        "cover": 0.075,
        "stirrup_spacing_long": 0.200,
        "stirrup_spacing_trans": 0.200,
    }
    design.update(override)
    return {"pilecap": {"thickness": 1.2}, "material": {"fc": 30e6}, "design": design}


def test_design_lengkap_lolos():
    validators.validate_design(_design_cfg())


@pytest.mark.parametrize(
    ("override", "pesan"),
    [
        ({"rebar_mode": None}, "rebar_mode"),
        ({"rebar_mode": "entah"}, "tidak dikenal"),
        ({"rebar_spacing": None}, "spacing_fixed"),
        ({"rebar_mode": "diameter_fixed", "rebar_config": None}, "diameter_fixed"),
        ({"rebar_mode": "diameter_fixed", "rebar_config": "D99"}, "bukan kode yang dikenal"),
        ({"rebar_select_codes": ["16", "ZZ"]}, "tidak dikenal"),
        ({"rebar_select_codes": []}, "tidak kosong"),
        ({"stirrup_spacing_long": None}, "stirrup_spacing_long"),
        ({"stirrup_spacing_trans": None}, "stirrup_spacing_trans"),
        ({"stirrup_spacing_long": -1.0}, "harus > 0"),
        ({"stirrup_select_diameters": []}, "tidak kosong"),
        ({"as_min_surface_zone": 0.0}, "harus > 0"),
    ],
)
def test_skema_desain_menolak_masukan_tidak_sah(override: dict, pesan: str):
    with pytest.raises(validators.InputError, match=pesan):
        validators.validate_design(_design_cfg(**override))


def test_pesan_kode_salah_menyebutkan_kode_yang_tersedia():
    """Tanpa daftar ini user hanya tahu kodenya salah, bukan apa yang boleh dipakai."""
    with pytest.raises(validators.InputError) as excinfo:
        validators.validate_design(_design_cfg(rebar_mode="diameter_fixed", rebar_config="D99"))
    pesan = str(excinfo.value)
    assert "2D25" in pesan and "32" in pesan


def test_mode_diameter_fixed_tidak_menuntut_rebar_spacing():
    """Pada mode ini spasi adalah HASIL, bukan masukan -- menuntutnya akan keliru."""
    validators.validate_design(
        _design_cfg(rebar_mode="diameter_fixed", rebar_config="2D25", rebar_spacing=None)
    )
