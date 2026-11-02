"""Pilecap tapper (tebal bervariasi): medan tebal, pita, FEM, ekspor Midas, desain tebal lokal.

Medan tebal diuji terhadap rumus ANALITIK atap perisai, bukan terhadap dirinya sendiri; uji
FEM memakai mesh dari array (bukan gmsh) supaya dua analisis benar-benar melihat mesh yang
sama -- mesh gmsh tidak reproducible bit demi bit antar proses, jadi membandingkan dua run
terpisah hanya mengukur derau mesh.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon, box

from pilecap_fem import capacity_engine as ce
from pilecap_fem import config, fem_engine, io_utils, mesh_model, postproc_engine, validators
from pilecap_fem import thickness as th
from pilecap_fem.exporters import mct
from pilecap_fem.geometry_builder import (
    EntityResolution,
    GeometryModel,
    GeometryResolution,
    Pier,
    Pile,
    polygon_from_rect,
)
from pilecap_fem.validators import InputError

# Pilecap persegi panjang + pier 1500x2500 + bahu 500: bentuk P2 tanpa trapesiumnya.
HX, HY = 4.5, 6.0
PX, PY = 0.75 + 0.5, 1.25 + 0.5
CAP = np.array([[-HX, -HY], [HX, -HY], [HX, HY], [-HX, HY]])
PIER = box(-0.75, -1.25, 0.75, 1.25)

# Denah trapesium P2 dari gambar [m], titik asal di kiri bawah.
CX, H = 4.669, 12.098
CAP_P2 = np.array([[CX - 4.431, 0.0], [CX + 4.431, 0.0], [CX + 4.669, H], [CX - 4.669, H]])
PIER_P2 = box(CX - 0.75, H / 2 - 1.25, CX + 0.75, H / 2 + 1.25)


def _perisai(cap=CAP, pier=PIER, t_max=2.0, t_edge=1.0, shoulder=0.5) -> th.ThicknessField:
    faces = th.faces_perisai(cap, pier, t_max=t_max, t_edge=t_edge, shoulder=shoulder)
    th.validate_faces(faces, Polygon(cap))
    return th.ThicknessField("parametrik", faces, 0.01)


def _analitik(x: np.ndarray, y: np.ndarray, t_max=2.0, t_edge=1.0) -> np.ndarray:
    """Atap perisai pada denah persegi: tebal = minimum dari empat bidang miring."""
    fx = np.clip((HX - np.abs(x)) / (HX - PX), 0.0, 1.0)
    fy = np.clip((HY - np.abs(y)) / (HY - PY), 0.0, 1.0)
    return t_edge + (t_max - t_edge) * np.minimum(fx, fy)


# ---------------------------------------------------------------------------
# Medan tebal
# ---------------------------------------------------------------------------


def test_perisai_sama_dengan_rumus_analitik():
    """Termasuk sudut, tepi, dan garis jurai -- titik tempat bug akar NaN pernah muncul."""
    rng = np.random.default_rng(0)
    pts = np.column_stack([rng.uniform(-HX, HX, 20_000), rng.uniform(-HY, HY, 20_000)])
    jurai = np.linspace([PX, PY], [HX, HY], 50)
    pts = np.vstack([pts, CAP, jurai, -jurai, [[0, 0], [HX, 0], [0, HY], [PX, 0], [0, PY]]])
    field = _perisai()
    assert np.allclose(field.thickness_at(pts), _analitik(pts[:, 0], pts[:, 1]), atol=1e-12)


def test_perisai_nilai_kunci():
    field = _perisai()
    t = field.thickness_at([[0.0, 0.0], [PX, PY], [HX, HY], [HX, 0.0], [(PX + HX) / 2, 0.0]])
    assert t.tolist() == pytest.approx([2.0, 2.0, 1.0, 1.0, 1.5])


def test_perisai_trapesium_p2_tepi_tipis_plateau_tebal():
    """Denah trapesium P2: tebal 1000 di seluruh tepi, 2000 di plateau, monoton di antaranya."""
    field = _perisai(cap=CAP_P2, pier=PIER_P2)
    tepi = np.vstack([np.linspace(CAP_P2[i], CAP_P2[(i + 1) % 4], 25) for i in range(4)])
    assert np.allclose(field.thickness_at(tepi), 1.0, atol=1e-12)
    plateau = np.array(box(CX - 1.25, H / 2 - 1.75, CX + 1.25, H / 2 + 1.75).exterior.coords)
    assert np.allclose(field.thickness_at(plateau), 2.0, atol=1e-12)

    # Sinar dari pusat pier ke tiap sudut dan titik tengah sisi: tebal tidak pernah naik.
    pusat = np.array([CX, H / 2])
    for ujung in [*CAP_P2, *((CAP_P2 + np.roll(CAP_P2, -1, axis=0)) / 2)]:
        sinar = np.linspace(pusat, ujung, 200)
        assert np.all(np.diff(field.thickness_at(sinar)) <= 1e-12)


def test_csv_per_bidang_identik_dengan_parametrik(tmp_path: Path):
    """Bidang P2 yang ditulis sebagai CSV memberi tebal yang sama dengan profil parametrik."""
    field = _perisai(cap=CAP_P2, pier=PIER_P2)
    baris = ["face,x,y,t"]
    for face in field.faces:
        for (x, y), t in zip(face.xy, face.t, strict=True):
            baris.append(f"{face.face_id},{x * 1e3:.6f},{y * 1e3:.6f},{t * 1e3:.6f}")
    csv = tmp_path / "pilecap_thickness.csv"
    csv.write_text("\n".join(baris) + "\n", encoding="utf-8")

    faces = io_utils.load_thickness_faces(csv, 1e-3)
    dari_csv = th.ThicknessField("csv", faces, 0.01, file=csv.name)
    th.validate_faces(faces, Polygon(CAP_P2))

    rng = np.random.default_rng(1)
    poly = Polygon(CAP_P2)
    pts = np.column_stack([rng.uniform(0, 9.338, 30_000), rng.uniform(0, H, 30_000)])
    import shapely

    pts = pts[shapely.contains_xy(poly, pts[:, 0], pts[:, 1])]
    assert np.allclose(dari_csv.thickness_at(pts), field.thickness_at(pts), atol=1e-9)


def _tulis_csv(tmp_path: Path, baris: list[str]) -> Path:
    csv = tmp_path / "cap_thick.csv"
    csv.write_text("face,x,y,t\n" + "\n".join(baris) + "\n", encoding="utf-8")
    return csv


#: Pilecap 2 x 2 m dipecah dua bidang: kiri bertebal 1,0 -> 1,5, kanan 1,5 -> 2,0.
_DUA_BIDANG = [
    "A,0,0,1000", "A,1000,0,1500", "A,1000,2000,1500", "A,0,2000,1000",
    "B,1000,0,1500", "B,2000,0,2000", "B,2000,2000,2000", "B,1000,2000,1500",
]  # fmt: skip
_KOTAK_2M = Polygon([(0, 0), (2, 0), (2, 2), (0, 2)])


def test_csv_sah_diterima(tmp_path: Path):
    faces = io_utils.load_thickness_faces(_tulis_csv(tmp_path, _DUA_BIDANG), 1e-3)
    th.validate_faces(faces, _KOTAK_2M)
    field = th.ThicknessField("csv", faces, 0.01)
    assert field.thickness_at([[0.5, 1.0], [1.5, 1.0]]).tolist() == pytest.approx([1.25, 1.75])


@pytest.mark.parametrize(
    ("ganti", "pesan"),
    [
        ({1: "A,900,0,1500", 2: "A,900,2000,1500"}, "tidak menutup"),  # celah
        ({4: "B,800,0,1500", 7: "B,800,2000,1500"}, "tumpang tindih"),
        ({5: "B,2000,0,1900"}, None),  # sudut LUAR tidak dipakai bersama: tetap sah
        ({4: "B,1000,0,1600"}, "tidak kontinu"),  # lompatan tebal di tepi bersama
    ],
)
def test_csv_cacat_ditolak(tmp_path: Path, ganti: dict[int, str], pesan: str | None):
    baris = list(_DUA_BIDANG)
    for i, isi in ganti.items():
        baris[i] = isi
    faces = io_utils.load_thickness_faces(_tulis_csv(tmp_path, baris), 1e-3)
    if pesan is None:
        th.validate_faces(faces, _KOTAK_2M)  # mengubah tebal sudut LUAR tetap sah
        return
    with pytest.raises(InputError, match=pesan):
        th.validate_faces(faces, _KOTAK_2M)


def test_csv_bidang_lebih_dari_empat_titik_ditolak(tmp_path: Path):
    baris = [*_DUA_BIDANG[:4], "A,500,2000,1250", *_DUA_BIDANG[4:]]
    with pytest.raises(InputError, match="3 atau 4 titik"):
        io_utils.load_thickness_faces(_tulis_csv(tmp_path, baris), 1e-3)


def test_csv_tebal_tidak_menyisakan_tinggi_efektif_ditolak(tmp_path: Path):
    faces = io_utils.load_thickness_faces(_tulis_csv(tmp_path, _DUA_BIDANG), 1e-3)
    cfg = {"pilecap": {"thickness": 2.0}, "design": {"cover": 0.6}}
    with pytest.raises(InputError, match=r"design\.cover"):
        th.build_field(
            cfg,
            cap_xy=np.array(_KOTAK_2M.exterior.coords)[:-1],
            piers=[box(0.8, 0.8, 1.2, 1.2)],
            pier_shapes=["rectangular"],
            csv_faces=faces,
        )


# ---------------------------------------------------------------------------
# build_field: sumber dan penolakan
# ---------------------------------------------------------------------------


def _cfg(**pilecap) -> dict:
    return {"pilecap": {"thickness": 2.0, **pilecap}}


def _build(cfg: dict, *, pier=PIER, shape="rectangular", cap=CAP):
    return th.build_field(cfg, cap_xy=cap, piers=[pier], pier_shapes=[shape])


def test_tanpa_field_tapper_tetap_seragam():
    """Config lama sama sekali tidak menyentuh jalur tapper."""
    assert _build(_cfg()) is None


@pytest.mark.parametrize(
    ("pilecap", "pesan"),
    [
        ({"edge_thickness": 1.0}, "taper_shoulder"),
        ({"edge_thickness": 2.5, "taper_shoulder": 0.5}, "edge_thickness"),
        ({"edge_thickness": 1.0, "taper_shoulder": -0.1}, "negatif"),
        # Pier 1,5 x 2,5 m + bahu 3,8 m -> plateau 9,1 m lebar, melebihi pilecap 9 m.
        ({"edge_thickness": 1.0, "taper_shoulder": 3.8}, "Plateau"),
        ({"edge_thickness": 1.0, "taper_shoulder": 0.5, "thickness_step": 0.0}, "thickness_step"),
    ],
)
def test_parametrik_tidak_sah_ditolak(pilecap: dict, pesan: str):
    with pytest.raises(InputError, match=pesan):
        _build(_cfg(**pilecap))


def test_parametrik_butuh_pier_persegi_dan_pilecap_segiempat():
    cfg = _cfg(edge_thickness=1.0, taper_shoulder=0.5)
    with pytest.raises(InputError, match="satu pier persegi"):
        _build(cfg, pier=PIER.buffer(0.1), shape="circular")
    segilima = np.array([[-HX, -HY], [HX, -HY], [HX, HY], [0, HY + 1], [-HX, HY]])
    with pytest.raises(InputError, match="segiempat cembung"):
        _build(cfg, cap=segilima)


# ---------------------------------------------------------------------------
# Pita tebal
# ---------------------------------------------------------------------------


def test_seragam_tidak_pernah_dibulatkan():
    """Tebal 1,234 m harus tetap 1,234 m -- jalur seragam tidak melewati thickness_step."""
    bands = th.element_bands(None, 1.234, np.zeros((5, 2)))
    assert bands.step is None
    assert bands.values.tolist() == [1.234]


def test_pita_membulatkan_ke_kelipatan_step():
    field = replace(_perisai(), step=0.05)
    titik = np.array([[(PX + HX) / 2, 0.0], [PX + 0.01, 0.0], [HX - 0.01, 0.0]])
    bands = th.element_bands(field, 2.0, titik)
    assert bands.elem_thickness.tolist() == pytest.approx([1.5, 2.0, 1.0])
    assert np.allclose(np.round(bands.values / 0.05), bands.values / 0.05)


def test_step_terlalu_kasar_ditolak():
    field = replace(_perisai(t_edge=0.3), step=1.0)
    with pytest.raises(InputError, match="terlalu kasar"):
        th.element_bands(field, 2.0, np.array([[HX - 0.01, 0.0]]))


# ---------------------------------------------------------------------------
# Serialisasi
# ---------------------------------------------------------------------------


def _geom(field: th.ThicknessField | None, thickness: float = 1.2) -> GeometryModel:
    return GeometryModel(
        pilecap=polygon_from_rect(4.0, 2.0, (0.0, 0.0)),
        thickness=thickness,
        piles=(
            Pile(pile_id="P1", x=-1.5, y=0.0, diameter=1.0),
            Pile(pile_id="P2", x=1.5, y=0.0, diameter=1.0),
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
        thickness_field=field,
    )


def test_geometry_json_seragam_tidak_berubah():
    """Run seragam menulis geometry.json yang sama persis dengan sebelum fitur tapper."""
    assert "thickness_field" not in _geom(None).to_json_dict()


def test_geometry_json_tapper_bolak_balik():
    field = _perisai()
    data = json.loads(json.dumps(_geom(field, 2.0).to_json_dict()))
    kembali = GeometryModel.from_json_dict(data).thickness_field
    assert kembali is not None
    pts = np.random.default_rng(2).uniform([-HX, -HY], [HX, HY], (2_000, 2))
    assert np.array_equal(kembali.thickness_at(pts), field.thickness_at(pts))
    assert (kembali.source, kembali.step, kembali.file) == (field.source, field.step, field.file)


# ---------------------------------------------------------------------------
# FEM dan ekspor Midas -- pada mesh deterministik dari array
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pelat():
    """Pelat 4 x 2 m, dua area pile dan satu area pier sebagai group (pola test_exporters)."""
    nx, ny = 16, 8
    gx, gy = np.meshgrid(np.linspace(-2.0, 2.0, nx + 1), np.linspace(-1.0, 1.0, ny + 1))
    nodes = np.column_stack([gx.ravel(), gy.ravel()])
    conn = np.array(
        [
            [
                j * (nx + 1) + i,
                j * (nx + 1) + i + 1,
                (j + 1) * (nx + 1) + i + 1,
                (j + 1) * (nx + 1) + i,
            ]
            for j in range(ny)
            for i in range(nx)
        ],
        dtype=np.int64,
    )
    groups = ("CAP", "PIER_PIER1", "PILE_P1", "PILE_P2")
    cx = nodes[conn][:, :, 0].mean(axis=1)
    cy = nodes[conn][:, :, 1].mean(axis=1)
    elem_group = np.zeros(len(conn), dtype=np.int32)
    elem_group[(np.abs(cx + 1.5) < 0.5) & (np.abs(cy) < 0.5)] = groups.index("PILE_P1")
    elem_group[(np.abs(cx - 1.5) < 0.5) & (np.abs(cy) < 0.5)] = groups.index("PILE_P2")
    elem_group[(np.abs(cx) < 0.5) & (np.abs(cy) < 0.5)] = groups.index("PIER_PIER1")
    mesh = mesh_model.from_arrays(nodes, conn, group_names=groups, elem_group=elem_group)
    material = fem_engine.MaterialProperties(E=25e9, nu=0.2, thickness=1.2, density=24e3)
    options = fem_engine.AnalysisOptions(include_self_weight=True)
    return mesh, material, options


_BEBAN = {"P1": 600e3, "P2": 400e3}


def test_kasus_batas_satu_pita_identik_bit_demi_bit_dengan_seragam(pelat):
    """Tebal tepi = tebal plateau: jalur pita harus memberi hasil IDENTIK, termasuk berat
    sendiri. Membuktikan pita tidak mengubah apa pun selain tebal itu sendiri."""
    mesh, material, options = pelat
    geom = _geom(None)
    bands = th.ThicknessBands(np.zeros(mesh.n_elements, dtype=np.int64), np.array([1.2]), 0.01)

    a = fem_engine.analyze_combo(mesh, geom, material, options, combo="c", pz_by_pile=_BEBAN)
    b = fem_engine.analyze_combo(
        mesh, geom, material, options, combo="c", pz_by_pile=_BEBAN, bands=bands
    )
    assert np.array_equal(a.displacements, b.displacements)
    assert np.array_equal(a.local_resultants, b.local_resultants)
    assert np.array_equal(a.reactions, b.reactions)


def test_berat_sendiri_mengikuti_tebal_tiap_elemen(pelat):
    mesh, material, options = pelat
    geom = _geom(None)
    tebal = np.where(np.abs(mesh.elem_centroid[:, 0]) < 1.0, 1.2, 0.8)
    values, band = np.unique(tebal, return_inverse=True)
    bands = th.ThicknessBands(band.astype(np.int64), values, 0.01)

    hasil = fem_engine.analyze_combo(
        mesh, geom, material, options, combo="c", pz_by_pile=_BEBAN, bands=bands
    )
    harapan = -material.density * float(np.sum(mesh.elem_area * tebal))
    assert hasil.self_weight_total == pytest.approx(harapan, rel=1e-12)
    assert hasil.equilibrium.passed


def test_pelat_lebih_tipis_melendut_lebih_besar(pelat):
    """Arah fisis yang benar: menipiskan sebagian pelat menambah lendutan maksimum."""
    mesh, material, options = pelat
    options = replace(options, include_self_weight=False)
    geom = _geom(None)
    tipis = np.where(np.abs(mesh.elem_centroid[:, 0]) < 1.0, 1.2, 0.6)
    values, band = np.unique(tipis, return_inverse=True)
    rata = fem_engine.analyze_combo(mesh, geom, material, options, combo="c", pz_by_pile=_BEBAN)
    tapper = fem_engine.analyze_combo(
        mesh,
        geom,
        material,
        options,
        combo="c",
        pz_by_pile=_BEBAN,
        bands=th.ThicknessBands(band.astype(np.int64), values, 0.01),
    )
    assert np.abs(tapper.displacements[:, 2]).max() > np.abs(rata.displacements[:, 2]).max()


def test_mct_satu_id_tebal_per_pita(pelat, tmp_path: Path):
    mesh, material, _ = pelat
    tebal = np.where(np.abs(mesh.elem_centroid[:, 0]) < 1.0, 1.2, 0.8)
    values, band = np.unique(tebal, return_inverse=True)
    bands = th.ThicknessBands(band.astype(np.int64), values, 0.01)
    path = mct.write_mct(tmp_path / "m.mct", _geom(None), mesh, material, bands=bands)
    teks = path.read_text(encoding="utf-8").splitlines()

    blok = teks[teks.index("*THICKNESS") + 1 : teks.index("*THICKNESS") + 1 + len(values)]
    assert [float(b.split(",")[4]) for b in blok] == pytest.approx(values.tolist())
    awal = teks.index("*ELEMENT") + 1
    ipro = [int(b.split(",")[3]) for b in teks[awal : awal + mesh.n_elements]]
    assert ipro == (band + 1).tolist()


def test_mct_seragam_tetap_satu_id(pelat, tmp_path: Path):
    mesh, material, _ = pelat
    teks = mct.write_mct(tmp_path / "m.mct", _geom(None), mesh, material).read_text(
        encoding="utf-8"
    )
    assert teks.count("VALUE, 1, YES") == 1
    assert "Pilecap tapper" not in teks


# ---------------------------------------------------------------------------
# Desain dengan tebal lokal (Fase 2)
# ---------------------------------------------------------------------------

_INPUTS = ce.CapacityInputs(
    fc=30e6,
    fy=420e6,
    thickness=1.6,
    cover=0.075,
    spacing=0.15,
    phi_flexure=0.9,
    phi_shear=0.75,
    phi_source="test",
    fy_source="test",
    stirrup_spacing_long=0.200,
    stirrup_spacing_trans=0.200,
)
_TEBAL = np.array([0.9, 1.2, 1.6])


def _momen_dan_tebal(n: int = 60, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    momen = rng.uniform(-2.5e6, 4.0e6, n)
    momen[3] = np.nan  # elemen tidak terdefinisi harus tetap TIDAK_TERDEFINISI
    momen[5] = 0.0
    return momen, rng.choice(_TEBAL, n)


@pytest.mark.parametrize(
    "mode",
    [
        {},
        {"rebar_mode": "diameter_fixed", "rebar_config": "2D25"},
        {"rebar_select_codes": ("16", "19", "25", "2D25")},
    ],
    ids=["spasi_tetap", "diameter_tetap", "kode_pilihan"],
)
@pytest.mark.parametrize(("direction", "face"), [("x", "bawah"), ("y", "atas")])
def test_desain_lentur_per_pita_sama_dengan_desain_seragam_tebal_itu(mode, direction, face):
    """Tiap elemen tapper harus mendapat PERSIS hasil pelat seragam setebal elemen itu.

    Itulah arti "desain dengan tebal lokal": tidak ada rumus baru, hanya `h` per elemen.
    Dibandingkan dengan jalur seragam yang sudah tervalidasi, bukan dengan dirinya sendiri.
    """
    momen, tebal = _momen_dan_tebal()
    dasar = replace(_INPUTS, **mode)
    tapper = dasar.with_element_thickness(tebal)
    d = ce.flexure_design(momen, tapper, direction=direction, face=face)
    sel = ce.select_flexure_bars(d, tapper)

    for h in _TEBAL:
        idx = np.flatnonzero(tebal == h)
        seragam = replace(dasar, thickness=float(h))
        acuan = ce.flexure_design(momen[idx], seragam, direction=direction, face=face)
        acuan_sel = ce.select_flexure_bars(acuan, seragam)
        np.testing.assert_array_equal(d.as_required[idx], acuan.as_required)
        np.testing.assert_array_equal(d.d_effective[idx], acuan.d_effective)
        np.testing.assert_array_equal(d.bar_diameter[idx], acuan.bar_diameter)
        np.testing.assert_array_equal(d.status[idx], acuan.status)
        assert np.all(np.asarray(d.as_min)[idx] == acuan.as_min)
        np.testing.assert_array_equal(sel.values[idx], acuan_sel.values)
        np.testing.assert_array_equal(sel.status[idx], acuan_sel.status)
        np.testing.assert_array_equal(ce.as_design_array(d)[idx], ce.as_design_array(acuan))


def test_tebal_lebih_tipis_butuh_tulangan_lebih_banyak():
    """Arah fisis: momen sama, `d` lebih kecil -> `As` lebih besar; `As_min` lebih kecil."""
    momen = np.full(3, 2.0e6)
    d = ce.flexure_design(
        momen, _INPUTS.with_element_thickness(_TEBAL), direction="x", face="bawah"
    )
    assert d.as_required[0] > d.as_required[1] > d.as_required[2]
    assert d.as_min[0] < d.as_min[1] < d.as_min[2]


def test_tebal_seragam_lewat_jalur_pita_sama_dengan_jalur_seragam():
    momen, _ = _momen_dan_tebal()
    a = ce.flexure_design(momen, _INPUTS, direction="x", face="bawah")
    b = ce.flexure_design(
        momen,
        _INPUTS.with_element_thickness(np.full(momen.size, _INPUTS.thickness)),
        direction="x",
        face="bawah",
    )
    np.testing.assert_array_equal(a.as_required, b.as_required)
    np.testing.assert_array_equal(a.status, b.status)
    assert np.all(b.as_min == a.as_min)


def test_peta_sengkang_per_pita_sama_dengan_peta_seragam_tebal_itu():
    rng = np.random.default_rng(3)
    geser = rng.uniform(-3.0e6, 3.0e6, 60)
    tebal = rng.choice(_TEBAL, 60)
    peta = ce.shear_rebar_map(geser, _INPUTS.with_element_thickness(tebal), direction="y")
    for h in _TEBAL:
        idx = np.flatnonzero(tebal == h)
        acuan = ce.shear_rebar_map(geser[idx], replace(_INPUTS, thickness=float(h)), direction="y")
        np.testing.assert_array_equal(peta.av_per_s[idx], acuan.av_per_s)
        np.testing.assert_array_equal(peta.stirrup_diameter[idx], acuan.stirrup_diameter)
        np.testing.assert_array_equal(peta.status[idx], acuan.status)
        assert np.all(np.asarray(peta.phi_v_c)[idx] == acuan.phi_v_c)
        assert np.all(np.asarray(peta.d_shear)[idx] == acuan.d_shear)
    assert peta.n_needs_stirrup == int(np.count_nonzero(np.abs(geser) > peta.phi_v_c))


def test_momen_lajur_tidak_dapat_didesain_dengan_tebal_per_elemen():
    """Satu angka per lajur tidak punya tebal per elemen -- harus ditolak, bukan ditebak."""
    with pytest.raises(ValueError, match="hanya per elemen"):
        ce.flexure_design(
            np.array([1.0e6]),
            _INPUTS.with_element_thickness(_TEBAL),
            direction="x",
            face="bawah",
        )


def test_tebal_elemen_tidak_menyisakan_tinggi_efektif_ditolak():
    with pytest.raises(ValueError, match="selimut"):
        _INPUTS.with_element_thickness(np.array([1.2, 0.15]))


@pytest.mark.parametrize("basis", ["strip", None])
def test_mode_lajur_ditolak_untuk_pilecap_tapper(basis):
    cfg = {"design": {"rebar_basis": basis}} if basis else {"design": {}}
    tapper = _geom(_linier_x(), 1.4)
    if basis == "strip":
        with pytest.raises(InputError, match="tapper"):
            validators.validate_rebar_basis_for_geometry(cfg, tapper)
    else:
        validators.validate_rebar_basis_for_geometry(cfg, tapper)  # bawaan = element
    validators.validate_rebar_basis_for_geometry({"design": {"rebar_basis": "strip"}}, _geom(None))


# --- geser satu arah, pons, a/d dengan d lokal --------------------------------


def _linier_x(t_kiri: float = 1.0, t_kanan: float = 1.4) -> th.ThicknessField:
    """Satu bidang 4 x 2 m, tebal linier dalam x: mudah dihitung tangan."""
    xy = np.array([[-2.0, -1.0], [2.0, -1.0], [2.0, 1.0], [-2.0, 1.0]])
    face = th.ThicknessFace("A", xy, np.array([t_kiri, t_kanan, t_kanan, t_kiri]))
    return th.ThicknessField("csv", (face,), 0.01)


def _hasil_geser(mesh) -> postproc_engine.ElementResults:
    satu = np.ones(mesh.n_elements)
    nol = np.zeros(mesh.n_elements)
    return postproc_engine.ElementResults(
        combo="c",
        m11=nol,
        m22=nol,
        m12=nol,
        q1=nol,
        q2=nol,
        p11=nol,
        p22=nol,
        p12=nol,
        m_xx=nol,
        m_yy=nol,
        m_xy=nol,
        q_x=1.0e5 * satu,
        q_y=1.0e5 * satu,
        theta=nol,
        raw_gauss=np.zeros((mesh.n_elements, 4, 8)),
    )


def test_geser_satu_arah_tapper_seragam_sama_dengan_jalur_lama(pelat):
    mesh, _, _ = pelat
    geom = _geom(None)
    hasil = _hasil_geser(mesh)
    lama = postproc_engine.one_way_shear(hasil, mesh, geom.piers[0], d=1.125)
    baru = postproc_engine.one_way_shear(
        hasil,
        mesh,
        geom.piers[0],
        d=1.125,
        elem_thickness=np.full(mesh.n_elements, 1.2),
        cover_m=0.075,
    )
    for a, b in zip(lama, baru, strict=True):
        assert (a.kind, a.d_m, a.location_m, a.b_o_m) == (b.kind, b.d_m, b.location_m, b.b_o_m)
        assert a.V_u_N == b.V_u_N or (np.isnan(a.V_u_N) and np.isnan(b.V_u_N))


def test_geser_satu_arah_tapper_letak_adalah_titik_tetap_d_setara(pelat):
    """Penampang pada jarak `d` dari muka pier, dengan `d` = `d` setara DI penampang itu."""
    mesh, _, _ = pelat
    field = _linier_x()
    geom = _geom(field, 1.4)
    tebal = np.round(field.thickness_at(mesh.elem_centroid) / 0.01) * 0.01
    hasil = _hasil_geser(mesh)
    cek = postproc_engine.one_way_shear(
        hasil, mesh, geom.piers[0], d=1.325, elem_thickness=tebal, cover_m=0.075
    )
    coords = mesh.node_xy[mesh.elem_conn]
    dievaluasi = 0
    for c in cek:
        if not c.kind.startswith("one_way_x") or not np.isfinite(c.V_u_N):
            continue
        muka = -0.5 if c.kind.endswith("min") else 0.5
        assert abs(c.location_m - muka) == pytest.approx(c.d_m, abs=1e-6)
        d_setara, d_min = postproc_engine._cut_depth(
            coords, mesh, cut_axis=0, position=c.location_m, elem_thickness=tebal, cover_m=0.075
        )
        assert c.d_m == pytest.approx(d_setara, abs=1e-6)
        assert d_min <= d_setara + 1e-12
        assert f"d terkecil {d_min:.4f} m" in c.note
        dievaluasi += 1
    assert dievaluasi == 2
    # Sisi kanan lebih tebal -> d-nya lebih besar dan penampangnya lebih jauh dari pier.
    kiri, kanan = (next(c for c in cek if c.kind == f"one_way_x_{s}") for s in ("min", "maks"))
    assert kanan.d_m > kiri.d_m


def test_a_per_d_memakai_d_lokal_di_tiap_pile():
    field = _linier_x()
    geom = _geom(field, 1.4)
    baris = {r["pile_id"]: r for r in postproc_engine.shear_span_ratio(geom, 0.075)["rows"]}
    for pile in geom.piles:
        harapan = float(field.thickness_at(np.array([[pile.x, pile.y]]))[0]) - 0.075
        assert baris[pile.pile_id]["d_m"] == pytest.approx(harapan)
    assert baris["P1"]["d_m"] < baris["P2"]["d_m"]
    # Seragam: d tetap satu angka t - cover.
    seragam = postproc_engine.shear_span_ratio(_geom(None), 0.075)
    assert all(r["d_m"] == pytest.approx(1.125) for r in seragam["rows"])


def test_shear_demand_tapper_tanpa_tebal_elemen_ditolak(pelat):
    mesh, _, _ = pelat
    with pytest.raises(ValueError, match="elem_thickness"):
        postproc_engine.shear_demand(
            _hasil_geser(mesh), mesh, _geom(_linier_x(), 1.4), {}, cover_m=0.075
        )


# ---------------------------------------------------------------------------
# Ujung ke ujung: ex05 dianalisis lalu didesain dengan tebal lokal
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_ex05_dianalisis_lalu_didesain_dengan_tebal_lokal(examples_dir: Path, tmp_path: Path):
    from pilecap_fem import cli_pilecap_analyze, cli_pilecap_report

    contoh = tmp_path / "ex05"
    shutil.copytree(examples_dir / "ex05_tapered_p2", contoh)
    keluaran = tmp_path / "out"
    assert (
        cli_pilecap_analyze.entry_point(["--input-dir", str(contoh), "--output-dir", str(keluaran)])
        == 0
    )
    run = next(keluaran.glob("pilecap_*"))
    model = run / "00_Model"
    geom = json.loads((model / "geometry.json").read_text(encoding="utf-8"))
    assert geom["thickness_field"]["source"] == "parametrik"
    assert "Pilecap tapper:" in (model / "model.mct").read_text(encoding="utf-8")

    assert cli_pilecap_report.entry_point(["--result-dir", str(run), "--no-envelope"]) == 0
    assert (model / config.FILE_CONTOUR_THICKNESS).is_file()

    # Tebal yang dipakai desain = tebal pita yang diekspor ke Midas, per elemen.
    tebal = pd.read_csv(model / "element_thickness.csv").set_index("element_tag")
    combo = next(run.glob("Combo_*"))
    desain = pd.read_csv(combo / "rebar_design.csv")
    t_elem = tebal.loc[desain["elem_tag"], "t_band_m"].to_numpy() * 1e3
    as_min = desain.filter(like="As_min").iloc[:, 0].to_numpy()
    # As_min = 0,0018 h b / 2 per muka (SNI, tanpa batas zona permukaan): mengikuti h lokal.
    np.testing.assert_allclose(as_min, 0.0018 * t_elem * 1000.0 / 2.0, rtol=1e-3)
    d_x = desain.filter(like="d_x_bawah").iloc[:, 0].to_numpy()
    assert np.all(d_x < t_elem - 75.0 + 1e-6)
    assert np.corrcoef(d_x, t_elem)[0, 1] > 0.999

    teks = (combo / "calc_sheet.md").read_text(encoding="utf-8")
    assert "Pilecap tapper" in teks and "d` SETARA" in teks
    assert "tapper" in (run / "SUMMARY.md").read_text(encoding="utf-8")


@pytest.mark.slow
def test_mode_lajur_tapper_ditolak_sebelum_analisis(examples_dir: Path, tmp_path: Path):
    from pilecap_fem import cli_pilecap_analyze

    contoh = tmp_path / "ex05"
    shutil.copytree(examples_dir / "ex05_tapered_p2", contoh)
    cfg_path = contoh / "pilecap_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["design"]["rebar_basis"] = "strip"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    kode = cli_pilecap_analyze.entry_point(
        ["--input-dir", str(contoh), "--output-dir", str(tmp_path / "out")]
    )
    assert kode != 0
    assert not list((tmp_path / "out").glob("pilecap_*/Combo_*"))
