"""Ekspor SAP2000 `.s2k`, CSV assignment beban, dan berat sendiri di MCT.

Seperti `test_exporters.py`, yang diuji bukan "SAP2000 mau membukanya" -- itu hanya terbukti
dengan impor sungguhan -- melainkan hal yang dapat salah diam-diam: entitas yang tidak cocok
dengan mesh, beban yang berbeda dari model OpenSees, kombinasi yang dijumlahkan, sumbu lokal
yang terbalik, dan baris yang melampaui gaya berkas buatan SAP sendiri.
"""

from __future__ import annotations

import collections
import csv
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from test_exporters import LOADS, build_model

from pilecap_fem import config, fem_engine, mesh_model, reporter
from pilecap_fem import thickness as th
from pilecap_fem.exporters import mct, s2k


@pytest.fixture(scope="module")
def model():
    """Pelat 4x2 m yang sama dengan `test_exporters.py` -- dua pile, satu pier."""
    return build_model()


_FIELD = re.compile(r'(\w+)=("[^"]*"|\S+)')
_NOW = datetime(2026, 11, 10, 12, 0, 0)


def parse_s2k(text: str) -> dict[str, list[dict[str, str]]]:
    """Tabel -> daftar baris `{kolom: nilai}`. Menyambung baris lanjutan ` _` seperti SAP."""
    tables: dict[str, list[dict[str, str]]] = collections.defaultdict(list)
    current: str | None = None
    buffer = ""
    for raw in text.splitlines():
        if raw.startswith("TABLE:"):
            current = raw.split('"')[1]
            continue
        if raw.startswith("END TABLE DATA"):
            break
        if current is None or not raw.strip():
            continue
        line = (buffer + " " + raw.strip()) if buffer else raw.strip()
        if line.endswith(" _"):
            buffer = line[:-2]
            continue
        buffer = ""
        tables[current].append({k: v.strip('"') for k, v in _FIELD.findall(line)})
    return tables


def _tulis(model, tmp_path: Path, **kwargs) -> tuple[str, dict[str, list[dict[str, str]]]]:
    geom, mesh, material = model
    kwargs.setdefault("material", material)
    path = s2k.write_s2k(
        tmp_path / "model.s2k",
        geom,
        mesh,
        kwargs.pop("material"),
        project_name="uji",
        fc_pa=30e6,
        now=_NOW,
        **kwargs,
    )
    text = path.read_text(encoding="utf-8")
    return text, parse_s2k(text)


# ---------------------------------------------------------------------------
# Geometri, seksi, tumpuan
# ---------------------------------------------------------------------------


def test_joint_dan_area_sama_dengan_mesh(model, tmp_path: Path):
    _, mesh, _ = model
    _, t = _tulis(model, tmp_path, loads=LOADS)
    joints = {int(r["Joint"]): (float(r["XorR"]), float(r["Y"])) for r in t["JOINT COORDINATES"]}
    assert len(joints) == mesh.n_nodes
    for tag, (x, y) in zip(mesh.node_tags, mesh.node_xy, strict=True):
        assert joints[int(tag)] == pytest.approx((x, y), abs=1e-9)
    areas = {
        int(r["Area"]): {int(r[f"Joint{k}"]) for k in range(1, 5)} for r in t["CONNECTIVITY - AREA"]
    }
    assert len(areas) == mesh.n_elements
    for tag, conn in zip(mesh.elem_tags, mesh.elem_conn, strict=True):
        assert areas[int(tag)] == {int(mesh.node_tags[j]) for j in conn}


def test_simpul_area_diurut_berlawanan_jarum_jam(model, tmp_path: Path):
    """Elemen yang searah jarum jam di mesh dibalik, sehingga sumbu lokal 3 SAP = +Z."""
    geom, mesh, material = model
    conn = mesh.elem_conn.copy()
    conn[::3] = conn[::3, ::-1]  # sebagian elemen sengaja dibuat searah jarum jam
    campur = mesh_model.from_arrays(
        mesh.node_xy,
        conn,
        group_names=mesh.group_names,
        elem_group=mesh.elem_group,
    )
    path = s2k.write_s2k(tmp_path / "m.s2k", geom, campur, material, now=_NOW)
    t = parse_s2k(path.read_text(encoding="utf-8"))
    xy = {int(r["Joint"]): (float(r["XorR"]), float(r["Y"])) for r in t["JOINT COORDINATES"]}
    for r in t["CONNECTIVITY - AREA"]:
        p = np.array([xy[int(r[f"Joint{k}"])] for k in range(1, 5)])
        luas = 0.5 * np.sum(p[:, 0] * np.roll(p[:, 1], -1) - np.roll(p[:, 0], -1) * p[:, 1])
        assert luas > 0.0


def test_restraint_sama_dengan_node_jepit_opensees(model, tmp_path: Path):
    geom, mesh, _ = model
    _, t = _tulis(model, tmp_path)
    harapan = {int(mesh.node_tags[n]) for n in fem_engine.fixed_support_nodes(mesh, geom)}
    rows = t["JOINT RESTRAINT ASSIGNMENTS"]
    assert {int(r["Joint"]) for r in rows} == harapan
    assert all(r[d] == "Yes" for r in rows for d in ("U1", "U2", "U3", "R1", "R2", "R3"))


def test_grup_menutupi_seluruh_area_tepat_sekali(model, tmp_path: Path):
    _, mesh, _ = model
    _, t = _tulis(model, tmp_path)
    assert {r["GroupName"] for r in t["GROUPS 1 - DEFINITIONS"]} == set(mesh.group_names)
    label = [int(r["ObjectLabel"]) for r in t["GROUPS 2 - ASSIGNMENTS"]]
    assert sorted(label) == sorted(int(e) for e in mesh.elem_tags)
    assert all(r["ObjectType"] == "Area" for r in t["GROUPS 2 - ASSIGNMENTS"])


def test_seksi_seragam_shell_thick_dan_material_eksplisit(model, tmp_path: Path):
    _, _, material = model
    _, t = _tulis(model, tmp_path)
    (seksi,) = t["AREA SECTION PROPERTIES"]
    assert seksi["Section"] == s2k.SECTION_UNIFORM
    assert seksi["Type"] == "Shell-Thick"
    assert float(seksi["Thickness"]) == float(seksi["BendThick"]) == material.thickness
    assert seksi["WMod"] == "1"  # field terakhir terbaca -> baris lanjutan tersambung benar
    assert {r["Section"] for r in t["AREA SECTION ASSIGNMENTS"]} == {s2k.SECTION_UNIFORM}
    (mat,) = t["MATERIAL PROPERTIES 02 - BASIC MECHANICAL PROPERTIES"]
    assert float(mat["E1"]) == pytest.approx(material.E * 1e-3)
    assert float(mat["UnitWeight"]) == pytest.approx(material.density * 1e-3)
    assert float(t["MATERIAL PROPERTIES 03B - CONCRETE DATA"][0]["Fc"]) == pytest.approx(30e3)
    assert t["PROGRAM CONTROL"][0]["CurrUnits"] == "KN, m, C"


def test_tapper_satu_seksi_per_pita(model, tmp_path: Path):
    _, mesh, _ = model
    tebal = np.where(np.abs(mesh.elem_centroid[:, 0]) < 1.0, 1.2, 0.8)
    values, band = np.unique(tebal, return_inverse=True)
    bands = th.ThicknessBands(band.astype(np.int64), values, 0.01)
    _, t = _tulis(model, tmp_path, bands=bands)
    seksi = {r["Section"]: float(r["Thickness"]) for r in t["AREA SECTION PROPERTIES"]}
    assert seksi == {"T800": 0.8, "T1200": 1.2}
    per_area = {int(r["Area"]): seksi[r["Section"]] for r in t["AREA SECTION ASSIGNMENTS"]}
    for tag, h in zip(mesh.elem_tags, tebal, strict=True):
        assert per_area[int(tag)] == h


def test_tanpa_material_dan_tanpa_beban_dinyatakan(model, tmp_path: Path):
    _, t = _tulis(model, tmp_path, material=None)
    for nama in (
        "AREA SECTION PROPERTIES",
        "MATERIAL PROPERTIES 01 - GENERAL",
        "AREA LOADS - UNIFORM",
    ):
        assert nama not in t
    keterangan = {r["Item"]: r.get("Data", "") for r in t["PROJECT INFORMATION"]}
    assert "TANPA material" in keterangan["Model Description"]
    assert "tanpa beban" in keterangan["Model Description"]


def test_baris_tidak_melampaui_batas_berkas_sap(model, tmp_path: Path):
    text, _ = _tulis(model, tmp_path, loads=LOADS)
    assert max(len(line) for line in text.splitlines()) <= 240
    assert text.rstrip().endswith("END TABLE DATA")


# ---------------------------------------------------------------------------
# Beban
# ---------------------------------------------------------------------------


def test_area_load_identik_dengan_tekanan_fem_dan_total_pz(model, tmp_path: Path):
    geom, mesh, _ = model
    _, t = _tulis(model, tmp_path, loads=LOADS)
    luas = dict(zip((int(e) for e in mesh.elem_tags), mesh.elem_area, strict=True))
    per_combo: dict[str, dict[int, float]] = collections.defaultdict(dict)
    for r in t["AREA LOADS - UNIFORM"]:
        assert (r["CoordSys"], r["Dir"]) == ("GLOBAL", "Z")
        per_combo[r["LoadPat"]][int(r["Area"])] = float(r["UnifLoad"])
    assert set(per_combo) == set(LOADS)
    for combo, pz in LOADS.items():
        total = sum(p * luas[a] for a, p in per_combo[combo].items())
        assert total == pytest.approx(sum(pz.values()) * 1e-3, rel=1e-10)
        for load in fem_engine.pile_pressures(mesh, geom, pz):
            for i in load.element_index:
                assert per_combo[combo][int(mesh.elem_tags[i])] == pytest.approx(
                    load.pressure * 1e-3, rel=1e-11
                )


@pytest.mark.parametrize("modeling", ["pressure", "nodal"])
def test_joint_load_sama_dengan_gaya_nodal_opensees(model, tmp_path: Path, modeling: str):
    geom, mesh, material = model
    _, t = _tulis(model, tmp_path, loads=LOADS, load_mode="joint", pile_modeling=modeling)
    assert "AREA LOADS - UNIFORM" not in t
    tag_ke_indeks = {int(tag): i for i, tag in enumerate(mesh.node_tags)}
    for combo, pz in LOADS.items():
        gaya = np.zeros(mesh.n_nodes)
        for r in t["JOINT LOADS - FORCE"]:
            if r["LoadPat"] == combo:
                assert float(r["F1"]) == float(r["F2"]) == 0.0
                gaya[tag_ke_indeks[int(r["Joint"])]] = float(r["F3"])
        harapan = fem_engine.applied_nodal_loads(
            mesh,
            geom,
            material,
            fem_engine.AnalysisOptions(),
            pz,
            load_strategy=fem_engine.make_load_strategy(modeling),
        ).pile_fz
        np.testing.assert_allclose(gaya, harapan * 1e-3, rtol=1e-11, atol=1e-12)
        assert gaya.sum() == pytest.approx(sum(pz.values()) * 1e-3, rel=1e-10)


@pytest.mark.parametrize("self_weight", [False, True])
def test_berat_sendiri_lewat_selfwtmult_bukan_gaya(model, tmp_path: Path, self_weight: bool):
    _, t = _tulis(model, tmp_path, loads=LOADS, self_weight=self_weight)
    assert {r["SelfWtMult"] for r in t["LOAD PATTERN DEFINITIONS"]} == {"1" if self_weight else "0"}


def test_kombinasi_satu_case_per_combo_dan_envelope(model, tmp_path: Path):
    _, t = _tulis(model, tmp_path, loads=LOADS)
    assert [r["LoadPat"] for r in t["LOAD PATTERN DEFINITIONS"]] == list(LOADS)
    assert [r["Case"] for r in t["LOAD CASE DEFINITIONS"]] == list(LOADS)
    assert all(r["Type"] == "LinStatic" for r in t["LOAD CASE DEFINITIONS"])
    assert [(r["Case"], r["LoadName"]) for r in t["CASE - STATIC 1 - LOAD ASSIGNMENTS"]] == [
        (c, c) for c in LOADS
    ]
    kombinasi = t["COMBINATION DEFINITIONS"]
    assert kombinasi[0]["ComboType"] == "Envelope"
    assert {r["ComboName"] for r in kombinasi} == {s2k.ENVELOPE_NAME}
    assert [r["CaseName"] for r in kombinasi] == list(LOADS)


def test_mode_beban_tidak_dikenal_ditolak(model, tmp_path: Path):
    with pytest.raises(ValueError, match="load_mode"):
        _tulis(model, tmp_path, loads=LOADS, load_mode="garis")


# ---------------------------------------------------------------------------
# MCT: berat sendiri
# ---------------------------------------------------------------------------


def test_mct_tanpa_berat_sendiri_byte_identik(model, tmp_path: Path):
    geom, mesh, material = model
    a = mct.write_mct(tmp_path / "a.mct", geom, mesh, material, loads=LOADS, now=_NOW)
    b = mct.write_mct(
        tmp_path / "b.mct", geom, mesh, material, loads=LOADS, now=_NOW, self_weight=False
    )
    assert a.read_bytes() == b.read_bytes()
    assert "SELFWEIGHT" not in a.read_text(encoding="utf-8")


def test_mct_berat_sendiri_di_setiap_kombinasi(model, tmp_path: Path):
    geom, mesh, material = model
    teks = mct.write_mct(
        tmp_path / "m.mct", geom, mesh, material, loads=LOADS, now=_NOW, self_weight=True
    ).read_text(encoding="utf-8")
    baris = teks.splitlines()
    pakai = [i for i, b in enumerate(baris) if b.startswith("*USE-STLD")]
    assert len(pakai) == len(LOADS)
    for i in pakai:
        assert baris[i + 1 : i + 4] == ["*SELFWEIGHT", "0, 0, -1, ", "*PRESSURE"]
    assert "*SELFWEIGHT  -- berat sendiri" in teks  # dinyatakan belum tervalidasi di header


# ---------------------------------------------------------------------------
# Satu sumber beban + CSV assignment
# ---------------------------------------------------------------------------


def test_analyze_combo_memakai_beban_yang_sama_dengan_helper(model):
    """`load_node.csv` sah hanya bila helper = beban yang benar-benar dianalisis."""
    geom, mesh, material = model
    options = fem_engine.AnalysisOptions(include_self_weight=True)
    pz = LOADS["1.2D+1.6L"]
    hasil = fem_engine.analyze_combo(mesh, geom, material, options, combo="c", pz_by_pile=pz)
    helper = fem_engine.applied_nodal_loads(mesh, geom, material, options, pz)
    assert np.array_equal(hasil.applied_nodal_fz, helper.total_fz)
    assert hasil.self_weight_total == helper.self_weight_total


@pytest.mark.parametrize("self_weight", [False, True])
def test_beban_area_dan_nodal_seimbang(model, self_weight: bool):
    geom, mesh, material = model
    options = fem_engine.AnalysisOptions(include_self_weight=self_weight)
    berat = material.density * material.thickness * float(mesh.elem_area.sum())
    for pz in LOADS.values():
        harapan = sum(pz.values()) - (berat if self_weight else 0.0)
        area = fem_engine.element_area_loads(mesh, geom, material, options, pz)
        nodal = fem_engine.applied_nodal_loads(mesh, geom, material, options, pz).total_fz
        assert float(np.sum(area * mesh.elem_area)) == pytest.approx(harapan, rel=1e-12)
        assert float(nodal.sum()) == pytest.approx(harapan, rel=1e-12)


def test_csv_assignment_format_panjang_dan_isinya(model, tmp_path: Path):
    geom, mesh, material = model
    options = fem_engine.AnalysisOptions()
    area = {
        c: fem_engine.element_area_loads(mesh, geom, material, options, pz)
        for c, pz in LOADS.items()
    }
    node = {
        c: fem_engine.applied_nodal_loads(mesh, geom, material, options, pz).total_fz
        for c, pz in LOADS.items()
    }
    pa, pn = reporter.write_load_assignment_csvs(tmp_path, mesh, area_loads=area, node_loads=node)
    assert (pa.name, pn.name) == (config.FILE_LOAD_AREA, config.FILE_LOAD_NODE)

    with open(pa, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["elemen", "load_comb", "load [kPa]"]
    tag_area = dict(zip((int(e) for e in mesh.elem_tags), mesh.elem_area, strict=True))
    for combo, pz in LOADS.items():
        baris = [r for r in rows[1:] if r[1] == combo]
        assert len(baris) == int(np.count_nonzero(area[combo]))
        total = sum(float(r[2]) * 1e3 * tag_area[int(r[0])] for r in baris)
        assert total == pytest.approx(sum(pz.values()), rel=1e-6)

    with open(pn, encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["node", "load_comb", "load [kN]"]
    for combo, pz in LOADS.items():
        baris = [r for r in rows[1:] if r[1] == combo]
        assert len(baris) == int(np.count_nonzero(node[combo]))
        assert sum(float(r[2]) for r in baris) * 1e3 == pytest.approx(sum(pz.values()), rel=1e-6)
    assert [r[1] for r in rows[1:]] == sorted((r[1] for r in rows[1:]), key=list(LOADS).index)


# ---------------------------------------------------------------------------
# Ujung ke ujung
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_analyze_menulis_s2k_dan_csv_untuk_seluruh_kombinasi(examples_dir: Path, tmp_path: Path):
    """`--combo` membatasi ANALISIS, bukan ekspor -- sama dengan MCT."""
    from pilecap_fem import cli_pilecap_analyze

    out = tmp_path / "out"
    kode = cli_pilecap_analyze.entry_point(
        [
            "--input-dir",
            str(examples_dir / "ex01_standard_4pile"),
            "--output-dir",
            str(out),
            "--combo",
            "1.2D+1.6L",
            "--s2k-load",
            "joint",
        ]
    )
    assert kode == 0
    model_dir = next(out.glob("pilecap_*")) / config.MODEL_SUBDIR
    t = parse_s2k((model_dir / config.FILE_MODEL_S2K).read_text(encoding="utf-8"))
    semua = {r["LoadPat"] for r in t["LOAD PATTERN DEFINITIONS"]}
    assert len(semua) == 2 and "JOINT LOADS - FORCE" in t
    for berkas in (config.FILE_LOAD_AREA, config.FILE_LOAD_NODE):
        with open(model_dir / berkas, encoding="utf-8") as f:
            assert {r[1] for r in list(csv.reader(f))[1:]} == semua
