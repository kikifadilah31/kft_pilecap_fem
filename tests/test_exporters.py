"""Test ekspor model ke format program lain (`pilecap_fem.exporters`).

Yang diuji bukan "Midas mau membukanya" -- itu hanya dapat dibuktikan dengan mengimpornya
sungguhan, dan disebutkan sebagai risiko di README. Yang diuji adalah hal-hal yang dapat
salah diam-diam dan tidak akan terlihat sebagai error di Midas: jumlah entitas yang tidak
cocok dengan mesh, grup yang bocor atau bertumpang tindih, kombinasi yang DIJUMLAHKAN
alih-alih di-envelope, dan -- yang paling berbahaya -- tekanan yang berbeda dari yang
dipakai model OpenSees.
"""

from __future__ import annotations

import collections
from pathlib import Path

import numpy as np
import pytest

from pilecap_fem import config, fem_engine, mesh_model
from pilecap_fem.exporters import mct
from pilecap_fem.geometry_builder import (
    EntityResolution,
    GeometryModel,
    GeometryResolution,
    Pier,
    Pile,
    polygon_from_rect,
)
from pilecap_fem.reporter import slugify

PILE_IDS = ("P1", "P2")
LOADS = {"1.2D+1.6L": {"P1": 600e3, "P2": 400e3}, "1.2D+1.0W": {"P1": 750e3, "P2": 250e3}}


@pytest.fixture(scope="module")
def model():
    """Pelat 4x2 m dengan dua area pile dan satu area pier sebagai physical group.

    Dibangun dari array, bukan gmsh: yang diperiksa di sini adalah PENERJEMAHAN, dan mesh
    yang deterministik membuat setiap jumlah dalam test menjadi angka pasti.
    """
    nx, ny = 8, 4
    xs = np.linspace(-2.0, 2.0, nx + 1)
    ys = np.linspace(-1.0, 1.0, ny + 1)
    gx, gy = np.meshgrid(xs, ys)
    nodes = np.column_stack([gx.ravel(), gy.ravel()])

    conn = []
    for j in range(ny):
        for i in range(nx):
            k = j * (nx + 1) + i
            conn.append([k, k + 1, k + nx + 2, k + nx + 1])
    conn_arr = np.array(conn, dtype=np.int64)

    groups = ("CAP", "PIER_PIER1", "PILE_P1", "PILE_P2")
    centroid_x = nodes[conn_arr][:, :, 0].mean(axis=1)
    elem_group = np.zeros(len(conn_arr), dtype=np.int32)
    elem_group[centroid_x < -1.0] = groups.index("PILE_P1")
    elem_group[centroid_x > 1.0] = groups.index("PILE_P2")
    elem_group[np.abs(centroid_x) < 0.5] = groups.index("PIER_PIER1")

    mesh = mesh_model.from_arrays(nodes, conn_arr, group_names=groups, elem_group=elem_group)
    geom = GeometryModel(
        pilecap=polygon_from_rect(4.0, 2.0, (0.0, 0.0)),
        thickness=1.2,
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
    )
    material = fem_engine.MaterialProperties(
        E=25e9, nu=0.2, thickness=1.2, density=24e3, E_source="test"
    )
    return geom, mesh, material


def sections(text: str) -> dict[str, list[str]]:
    """Baris data per bagian `*NAMA`, tanpa komentar dan tanpa baris kosong."""
    out: dict[str, list[str]] = collections.defaultdict(list)
    current = ""
    for line in text.splitlines():
        if line.startswith("*"):
            current = line.split(",")[0].strip()
            continue
        if line.startswith(";") or not line.strip():
            continue
        out[current].append(line)
    return out


@pytest.fixture(scope="module")
def with_loads(model, tmp_path_factory) -> str:
    geom, mesh, material = model
    path = mct.write_mct(
        tmp_path_factory.mktemp("mct") / "model.mct",
        geom,
        mesh,
        material,
        project_name="uji",
        loads=LOADS,
    )
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Struktur berkas
# ---------------------------------------------------------------------------


def test_unit_ditulis_eksplisit(with_loads: str):
    """Berkas rujukan TIDAK memuat `*UNIT`, sehingga mewarisi satuan model penerima.

    Itu berarti angka yang sama terbaca sebagai kN atau N tergantung model tujuan -- salah
    besar 1000x tanpa satu pun peringatan. Karena itu satuan dinyatakan.
    """
    body = sections(with_loads)
    assert body["*UNIT"] == [f"{mct.MCT_FORCE_UNIT}, {mct.MCT_LENGTH_UNIT}, KJ, C"]


def test_jumlah_node_dan_elemen_sama_dengan_mesh(model, with_loads: str):
    _, mesh, _ = model
    body = sections(with_loads)
    assert len(body["*NODE"]) == mesh.n_nodes
    assert len(body["*ELEMENT"]) == mesh.n_elements


def test_elemen_ditulis_sebagai_thick_plate(with_loads: str):
    """`iSUB=1` = thick plate (Mindlin), setara ShellMITC4 yang dipakai analisis.

    `iSUB=0` akan membuat Midas memakai pelat tipis dan MEREMEHKAN lendutan pilecap tebal.
    """
    for row in sections(with_loads)["*ELEMENT"]:
        fields = [f.strip() for f in row.split(",")]
        assert fields[1] == "PLATE"
        assert len(fields) == 10, "PLATE di rujukan hanya 10 field, tanpa ANGLE/EXVAL"
        assert fields[8] == "1"


def test_grup_menutupi_seluruh_elemen_tanpa_tumpang_tindih(model, with_loads: str):
    _, mesh, _ = model
    rows = sections(with_loads)["*GROUP"]
    assert len(rows) == len(mesh.group_names)

    seen: set[int] = set()
    for row in rows:
        name, nodes, elements, tail = [p.strip() for p in row.split(",")]
        assert name in mesh.group_names
        assert nodes == "", "dipakai bentuk elemen-saja; node diturunkan Midas"
        assert tail == "0"
        ids = {int(t) for t in elements.split()}
        assert not (seen & ids), f"elemen muncul di dua grup: {sorted(seen & ids)}"
        seen |= ids
    assert seen == {int(t) for t in mesh.elem_tags}


def test_constraint_memuat_tepat_node_pier(model, with_loads: str):
    """Jepit 6 DOF di area pier -- setara `fem_engine.FixedPierSupport`."""
    _, mesh, _ = model
    expected = {int(mesh.node_tags[n]) for n in mesh.nodes_in_group("PIER_PIER1")}
    row = sections(with_loads)["*CONSTRAINT"][0]
    daftar, dof, _ = [p.strip() for p in row.split(",")]
    assert {int(t) for t in daftar.split()} == expected
    assert dof == "111111"


# ---------------------------------------------------------------------------
# Pembebanan
# ---------------------------------------------------------------------------


def test_satu_stldcase_per_kombinasi_dengan_nama_tanpa_koma(with_loads: str):
    """Nama MCT tidak boleh memuat koma: ia sendiri pemisah field.

    Nama kombinasi asli (`1.2D+1.6L`) juga tidak boleh dipakai apa adanya karena titiknya
    lolos tetapi kombinasi seperti `D, L` akan memecah barisnya menjadi dua field.
    """
    rows = sections(with_loads)["*STLDCASE"]
    assert len(rows) == len(LOADS)
    for row in rows:
        name, kind = row.split(",")
        assert kind == "USER"
        assert "," not in name and " " not in name
        assert "+" not in name and "." not in name


def test_loadcomb_adalah_envelope_bukan_penjumlahan(with_loads: str):
    """Field ke-5 = 1 berarti Envelope. `0` akan MENJUMLAHKAN seluruh kombinasi terfaktor.

    Kombinasi di `pile_reactions.csv` masing-masing sudah terfaktor dan saling alternatif;
    menjumlahkannya menghasilkan beban berkali lipat -- dan Midas menghitungnya tanpa
    keluhan apa pun.
    """
    rows = sections(with_loads)["*LOADCOMB"]
    header = [f.strip() for f in rows[0].split(",")]
    assert header[0] == "NAME=ENVELOPE"
    assert header[4] == "1"
    assert [r.split(",")[0] for r in rows[1:]] == ["ST"] * len(LOADS)


def test_jumlah_baris_pressure_sama_dengan_elemen_pile(model, with_loads: str):
    _, mesh, _ = model
    per_combo = sum(int(np.count_nonzero(mesh.group_mask(f"PILE_{pid}"))) for pid in PILE_IDS)
    assert len(sections(with_loads)["*PRESSURE"]) == per_combo * len(LOADS)


def test_tekanan_identik_dengan_yang_dipakai_fem_engine(model, with_loads: str):
    """Bukti bahwa exporter MENERJEMAHKAN, bukan menghitung ulang.

    Bila suatu saat `mct.py` menghitung `Pz / A_disk` sendiri, kedua nilai dapat menyimpang
    -- mis. karena satu memakai `pi r^2` analitis dan satu lagi jumlah luas elemen -- dan
    pengguna akan membandingkan dua model yang diam-diam berbeda bebannya tanpa satu pun
    error.
    """
    geom, mesh, _ = model
    expected = {
        load.pile_id: load.pressure * 1e-3
        for load in fem_engine.pile_pressures(mesh, geom, dict(LOADS["1.2D+1.6L"]))
    }
    tag_to_pile = {
        int(mesh.elem_tags[i]): load.pile_id
        for load in fem_engine.pile_pressures(mesh, geom, dict(LOADS["1.2D+1.6L"]))
        for i in load.element_index
    }

    combo = slugify("1.2D+1.6L")
    active, seen = "", 0
    for line in with_loads.splitlines():
        if line.startswith("*USE-STLD,"):
            active = line.split(",", 1)[1]
        elif active == combo and ", PRES ," in line:
            fields = line.split(",")
            tag = int(fields[0])
            assert float(fields[9]) == pytest.approx(expected[tag_to_pile[tag]], rel=1e-12)
            seen += 1
    assert seen > 0


def test_jumlah_tekanan_kali_luas_sama_dengan_total_pz(model, with_loads: str):
    """Cek keseimbangan pada berkas yang DIEKSPOR, bukan pada model internal."""
    _, mesh, _ = model
    area = {int(t): float(a) for t, a in zip(mesh.elem_tags, mesh.elem_area, strict=True)}

    total: dict[str, float] = collections.defaultdict(float)
    active = ""
    for line in with_loads.splitlines():
        if line.startswith("*USE-STLD,"):
            active = line.split(",", 1)[1]
        elif active and ", PRES ," in line:
            fields = line.split(",")
            total[active] += float(fields[9]) * area[int(fields[0])]

    for combo, pz in LOADS.items():
        expected_kn = sum(pz.values()) * 1e-3
        assert total[slugify(combo)] == pytest.approx(expected_kn, rel=1e-9)


def test_arah_tekanan_gz_bukan_lz(with_loads: str):
    """`LZ` bergantung pada urutan simpul, yang TIDAK dijamin CCW pada mesh gmsh.

    Elemen yang kebetulan searah jarum jam akan menerima beban terbalik -- kesalahan yang
    tidak memunculkan error apa pun. Pilecap datar di bidang XY, sehingga `GZ` setara.
    """
    for row in sections(with_loads)["*PRESSURE"]:
        assert [f.strip() for f in row.split(",")][4] == "GZ"


# ---------------------------------------------------------------------------
# Varian tanpa beban & tanpa material
# ---------------------------------------------------------------------------


def test_tanpa_beban_tidak_memuat_bagian_pembebanan(model, tmp_path: Path):
    """`pilecap-mesh` berjalan sebelum reaksi pile dibaca; berkasnya harus tetap sah."""
    geom, mesh, material = model
    text = mct.write_mct(tmp_path / "m.mct", geom, mesh, material).read_text(encoding="utf-8")
    body = sections(text)
    assert "*STLDCASE" not in body
    assert "*PRESSURE" not in body
    assert "*LOADCOMB" not in body
    assert len(body["*NODE"]) == mesh.n_nodes


def test_tanpa_material_menyatakan_ketiadaannya(model, tmp_path: Path):
    """E tidak boleh dikarang. Berkas harus MENGATAKAN bahwa blok itu hilang.

    `pilecap-mesh` tidak mewajibkan `material.E`; menuliskan angka tebakan agar berkasnya
    "lengkap" berarti mengirim lendutan yang salah tanpa tanda apa pun.
    """
    geom, mesh, _ = model
    text = mct.write_mct(tmp_path / "m.mct", geom, mesh, None).read_text(encoding="utf-8")
    assert "*MATERIAL" not in sections(text)
    assert "material.E" in text and "tidak diisi" in text


def test_header_menandai_bagian_yang_belum_tervalidasi(with_loads: str):
    """`*CONSTRAINT` dan varian `*MATERIAL` tidak ada di berkas rujukan.

    Keduanya ditulis menurut konvensi MCT. Menyatakannya di berkas mengubah asumsi yang
    tak terlihat menjadi satu hal konkret untuk diperiksa saat impor pertama.
    """
    header = [ln for ln in with_loads.splitlines() if ln.startswith(";")]
    blob = "\n".join(header)
    assert "*CONSTRAINT" in blob
    assert "*MATERIAL" in blob
    assert "PERIKSA SAAT IMPOR PERTAMA" in blob
    assert config.FILE_MODEL_MCT == "model.mct"


def test_header_mencatat_pemetaan_nama_kombinasi(with_loads: str):
    """Nama MCT hasil slugify tidak dapat ditebak balik; pemetaannya harus tertulis."""
    header = "\n".join(ln for ln in with_loads.splitlines() if ln.startswith(";"))
    for combo in LOADS:
        assert combo in header


def test_angka_tidak_membawa_derau_representasi_biner(model, tmp_path: Path):
    """Koordinat -0,8 m harus tertulis `-0.8`, bukan `-0.7999999999999999`.

    Bukan soal estetika semata: berkas yang harus dibaca manusia saat mencocokkan model
    kehilangan kegunaannya bila setiap koordinat 17 digit.
    """
    geom, mesh, material = model
    text = mct.write_mct(tmp_path / "m.mct", geom, mesh, material).read_text(encoding="utf-8")
    for row in sections(text)["*NODE"]:
        for field in row.split(",")[1:]:
            assert len(field.strip().lstrip("-").replace(".", "")) <= 13
