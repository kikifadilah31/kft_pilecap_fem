"""Test pile yang tumpang tindih dengan pier (v0.9.0).

Geometri ujinya dibangun langsung di sini, bukan lewat contoh bawaan, karena yang
diuji adalah PERILAKU pada geometri terkendali: `a` = 300 mm, `r` = 400 mm, sehingga
luas lensanya dapat dihitung dari rumus tertutup dan dibandingkan dengan hasil mesh --
contoh bawaan diuji terhadap rumus itu di `test_ex04_f_cocok_dengan_rumus_analitis`,
bukan terhadap dirinya sendiri.
"""

from __future__ import annotations

import dataclasses
import math
from pathlib import Path

import pytest

from pilecap_fem import (
    config,
    fem_engine,
    geometry_builder,
    io_utils,
    mesh_engine,
    mesh_model,
    validators,
)
from pilecap_fem.geometry_builder import (
    EntityResolution,
    GeometryModel,
    GeometryResolution,
    Pier,
    Pile,
    polygon_from_rect,
)
from pilecap_fem.validators import AnalysisError

pytestmark = pytest.mark.slow

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

#: Geometri terverifikasi: pusat pile 300 mm di luar muka pier, jari-jari 400 mm.
A_OFFSET = 0.30
R_PILE = 0.40
#: `A = r^2 acos(a/r) - a sqrt(r^2 - a^2)` -- luas tembereng lingkaran di seberang chord.
A_LENSA_ANALITIS = R_PILE**2 * math.acos(A_OFFSET / R_PILE) - A_OFFSET * math.sqrt(
    R_PILE**2 - A_OFFSET**2
)
F_ANALITIS = A_LENSA_ANALITIS / (math.pi * R_PILE**2)

PZ = 1_000e3


def _geom(*, x_pile: float = 0.9) -> GeometryModel:
    """Pilecap 4,8 x 4,8 dengan satu pier 1,2 x 1,2 dan satu pile D800 di `x_pile`."""
    resolution = GeometryResolution(
        pilecap=EntityResolution(source="json_standard"),
        pile=EntityResolution(source="json_grid"),
        pier=EntityResolution(source="json_standard"),
    )
    piles = (Pile(pile_id="P1", x=x_pile, y=0.0, diameter=2 * R_PILE),)
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=1.2, width_y=1.2),
    )
    return GeometryModel(
        pilecap=polygon_from_rect(4.8, 4.8, (0.0, 0.0)),
        thickness=1.2,
        piles=piles,
        piers=piers,
        resolution=resolution,
        overlaps=geometry_builder.compute_pile_pier_overlaps(piles, piers),
    )


#: Irisan yang terpotong DUA sisi: pusat pile di luar muka-x pier DAN di bawah muka-y-nya.
#: Similaritas dari model nyata pemilik proyek (r=900 mm, 500/450 mm) diskalakan ke r=400,
#: sehingga `f`-nya identik 14,66%.
_SUDUT_SKALA = R_PILE / 0.9
_SUDUT_PUSAT = (1.2 + 0.500 * _SUDUT_SKALA, 0.6 - 0.450 * _SUDUT_SKALA)


def _geom_sudut() -> GeometryModel:
    """Pile yang menindih SUDUT pier -- bentuk irisan yang tidak dicakup ex04 maupun `_geom`.

    Perlu diuji tersendiri karena bocoran mesh bergantung panjang chord, bukan luas irisan:
    irisan yang terpotong dua sisi bocor jauh lebih besar pada kehalusan mesh yang sama
    (DIUKUR 2,3x pada D/h=24, lihat komentar `config.OVERLAP_LEAK_WARN`).
    """
    resolution = GeometryResolution(
        pilecap=EntityResolution(source="json_standard"),
        pile=EntityResolution(source="json_grid"),
        pier=EntityResolution(source="json_standard"),
    )
    piles = (Pile(pile_id="P1", x=_SUDUT_PUSAT[0], y=_SUDUT_PUSAT[1], diameter=2 * R_PILE),)
    piers = (
        Pier(pier_id="PIER1", shape="rectangular", centerline=(0.0, 0.0), width_x=2.4, width_y=1.2),
    )
    return GeometryModel(
        pilecap=polygon_from_rect(5.6, 5.6, (0.0, 0.0)),
        thickness=1.2,
        piles=piles,
        piers=piers,
        resolution=resolution,
        overlaps=geometry_builder.compute_pile_pier_overlaps(piles, piers),
    )


def _cfg(size: float) -> dict:
    """Config SI minimal. `include_self_weight` MATI supaya neraca hanya memuat `Pz`."""
    return {
        "material": {"fc": 30e6, "E": 25e9, "poisson": 0.2, "density": 0.0, "E_source": "uji"},
        "pilecap": {"thickness": 1.2},
        "mesh": {
            "size_mode": "uniform",
            "size_global": size,
            "size_local_pile": None,
            "size_local_pier": None,
            "algorithm": 11,
            "recombination_algorithm": 3,
            "recombine": True,
            "require_all_quad": True,
            "element_order": 1,
        },
        "analysis": {
            "shell_element": "ShellMITC4",
            "section": "PlateFiber",
            "n_layers": 10,
            "include_self_weight": False,
        },
    }


def _mesh(geom: GeometryModel, size: float) -> mesh_model.MeshModel:
    options = mesh_engine.MeshOptions.from_config(_cfg(size))
    return mesh_model.build_mesh_model(mesh_engine.generate_mesh(geom, options))


def _jalankan(size: float) -> tuple[mesh_model.MeshModel, GeometryModel, fem_engine.ComboResult]:
    geom = _geom()
    cfg = _cfg(size)
    mesh = _mesh(geom, size)
    hasil = fem_engine.analyze_combo(
        mesh,
        geom,
        fem_engine.MaterialProperties.from_config(cfg),
        fem_engine.AnalysisOptions.from_config(cfg),
        combo="UJI",
        pz_by_pile={"P1": PZ},
    )
    return mesh, geom, hasil


@pytest.fixture(scope="module")
def run_kasar():
    """Satu run pada h = D/8 dipakai beberapa test.

    BUKAN D/6 (mesh terkasar yang diizinkan rule 7a), meski itu pilihan yang tampak paling
    alami: pada D/6 bocorannya TERUKUR 4,87%, hanya 2,6% di bawah `OVERLAP_LEAK_ERROR` = 5%.
    Fixture yang duduk di tepi ambang akan meledak sewaktu-waktu karena pergeseran node
    antar run gmsh, dan kegagalan acak melatih orang mengabaikan test. D/8 memberi jarak
    ~20% (bocoran terukur 4,03%) tanpa mengubah satu pun yang diuji test-test ini.
    """
    return _jalankan(2 * R_PILE / 8)


# ---------------------------------------------------------------------------
# Grup lensa
# ---------------------------------------------------------------------------


def test_lens_disjoint_dari_pile_dan_pier(run_kasar):
    """Keanggotaan lensa di himpunan jepit harus EKSPLISIT, bukan kebetulan awalan nama.

    `pile_groups()`/`pier_groups()` memilih berdasarkan awalan; bila `LENS_` sampai
    tertangkap salah satunya, lensa akan diam-diam ikut jalur yang salah tanpa satu pun
    test lain gagal.
    """
    mesh, _, _ = run_kasar
    lensa = set(mesh.lens_groups())
    assert lensa, "geometri overlap wajib menghasilkan minimal satu grup lensa"
    assert lensa.isdisjoint(mesh.pile_groups())
    assert lensa.isdisjoint(mesh.pier_groups())


def test_fixed_support_menjepit_node_pier_dan_lens(run_kasar):
    mesh, geom, _ = run_kasar
    jepit = set(fem_engine.fixed_support_nodes(mesh, geom).tolist())
    for nama in (*mesh.lens_groups(), *mesh.pier_groups()):
        assert set(mesh.nodes_in_group(nama).tolist()) <= jepit, f"{nama} tidak dijepit"


def test_beban_mencakup_elemen_lens(run_kasar):
    """`a_disk` harus menjadi luas cakram PENUH, sehingga `p = Pz / A_pile` tetap berlaku."""
    mesh, geom, _ = run_kasar
    (tekanan,) = fem_engine.pile_pressures(mesh, geom, {"P1": PZ})
    assert tekanan.lens_group_names, "grup lensa harus ikut ke dalam himpunan beban"
    # Toleransi 2% adalah faceting cakram pada mesh kasar, bukan kelonggaran: yang dijaga
    # di sini adalah `a_disk` = cakram PENUH, bukan bulan sabitnya saja -- keduanya terpaut
    # 7,2%, jauh di luar toleransi ini.
    assert tekanan.a_disk == pytest.approx(math.pi * R_PILE**2, rel=2e-2)
    assert tekanan.a_disk > math.pi * R_PILE**2 * (1 - F_ANALITIS / 2)
    assert tekanan.pressure == pytest.approx(PZ / tekanan.a_disk, rel=1e-12)


# ---------------------------------------------------------------------------
# Pemisahan strut (fisika) dari bocoran mesh (artefak)
# ---------------------------------------------------------------------------


def test_terserap_terpisah_jadi_strut_dan_bocor_mesh(run_kasar):
    _, _, hasil = run_kasar
    (jejak,) = hasil.load_traces
    assert jejak.pz_strut == pytest.approx(jejak.overlap_fraction * jejak.pz, rel=1e-12)
    assert jejak.pz_strut + jejak.pz_bocor_mesh == pytest.approx(jejak.absorbed_total, rel=1e-12)
    assert jejak.pz_ke_pelat == pytest.approx(jejak.pz - jejak.absorbed_total, rel=1e-12)
    # Bocoran nyata dan positif: itulah yang membuat pemisahan ini perlu dilaporkan.
    assert jejak.pz_bocor_mesh > 0.0


def test_vc0_tetap_lulus_dan_sigma_reaksi_sama_dengan_sigma_pz(run_kasar):
    """Neraca global UTUH: tidak ada yang hilang, hanya berpindah ke reaksi."""
    _, _, hasil = run_kasar
    assert hasil.equilibrium.passed
    assert hasil.equilibrium.total_applied_fz == pytest.approx(
        PZ - hasil.self_weight_total, rel=1e-9
    )
    assert hasil.equilibrium.total_reaction_fz == pytest.approx(
        -hasil.equilibrium.total_applied_fz, rel=hasil.equilibrium.force_rtol
    )


@pytest.fixture(scope="module")
def studi_kehalusan():
    """Studi kehalusan D/h = 6, 12, 24, memakai `leak_traces` -- TANPA menjalankan solver.

    Dua alasan, keduanya penting:

    1. Studi ini hanya butuh jejak beban, bukan hasil analisis. Melewati solver membuatnya
       jauh lebih murah.
    2. Ia sengaja menyertakan mesh KASAR, yang bocorannya justru dekat ambang
       `OVERLAP_LEAK_ERROR`. Lewat `analyze_combo`, guard itu akan menghentikannya --
       padahal mengukur perilaku di ujung kasar itulah maksud test ini. Jalur ini mengukur
       besaran yang sama tanpa memicu guard-nya.

    Nilai TERUKUR (mode uniform), dicatat supaya pergeserannya kelak terlihat:

    | D/h | `f_mesh` | bocor mesh | ke pelat |
    |-----|---------:|-----------:|---------:|
    |   6 |  7,0768% |    4,8744% |  88,049% |
    |  12 |  7,1587% |    3,2175% |  89,624% |
    |  24 |  7,2021% |    1,3717% |  91,426% |

    `f_analitis` = 7,2147%.
    """
    geom = _geom()
    return [fem_engine.leak_traces(_mesh(geom, 2 * R_PILE / p), geom)[0] for p in (6, 12, 24)]


def test_komponen_strut_tidak_bergantung_kehalusan_mesh(studi_kehalusan):
    """`strut/Pz` = `f_mesh`, dan `f_mesh` KONVERGEN ke rumus analitis.

    Inilah yang membuktikan komponen fisikanya benar-benar terpisah dari artefak
    diskretisasi -- bukan sekadar dua nama untuk satu angka gabungan. Yang diuji bukan
    sekadar "dekat", melainkan bahwa galatnya MENGECIL saat mesh diperhalus; komponen
    yang mesh-dependen tidak akan berperilaku begitu.
    """
    galat = []
    for jejak in studi_kehalusan:
        assert jejak.pz_strut / jejak.pz == pytest.approx(jejak.overlap_fraction, rel=1e-12)
        galat.append(abs(jejak.overlap_fraction - F_ANALITIS) / F_ANALITIS)

    assert galat[0] > galat[1] > galat[2], f"galat f_mesh tidak konvergen: {galat}"
    assert galat[0] < 0.03, "bahkan pada mesh terkasar, f_mesh harus dalam 3% dari rumus"


def test_bocor_mesh_mengecil_orde_h(studi_kehalusan):
    """Bocoran ~ `L h / (2 A)`: mengecil sebanding `h`.

    Mendokumentasikan perilaku yang DITERIMA, bukan menyembunyikannya. Diuji atas rentang
    penuh 6 -> 24 (empat kali lebih halus), bukan per langkah: penyusutan per langkah
    TERUKUR tidak rata (1,51x lalu 2,35x) karena bergantung pada bagaimana barisan node
    kebetulan jatuh di muka pier -- justru sifat mesh-dependen yang sedang diukur.
    """
    rasio = [j.pz_bocor_mesh / j.pz for j in studi_kehalusan]
    assert rasio[0] > rasio[1] > rasio[2] > 0.0
    susut = rasio[0] / rasio[2]  # ideal 4x untuk orde h; TERUKUR 3,55x
    assert 2.5 < susut < 6.0, f"penyusutan {susut:.2f}x atas 4x kehalusan, bukan orde h"


# ---------------------------------------------------------------------------
# Overlap SUDUT + guard bocoran mesh
# ---------------------------------------------------------------------------


def test_overlap_sudut_bocor_lebih_besar_daripada_muka():
    """Bentuk irisan menentukan bocoran, bukan luasnya -- alasan `D/h` bukan prediktor.

    Irisan yang terpotong DUA sisi punya chord lebih panjang, sehingga lebih banyak elemen
    bulan sabit bersentuhan dengan node jepit. Kalau suatu saat guard-nya diganti proksi
    geometri, test ini yang menunjukkan mengapa itu salah.
    """
    h = 2 * R_PILE / 12
    muka = _geom()
    sudut = _geom_sudut()

    bocor_muka = fem_engine.leak_traces(_mesh(muka, h), muka)[0]
    bocor_sudut = fem_engine.leak_traces(_mesh(sudut, h), sudut)[0]

    # Luas irisannya jauh berbeda, tetapi yang diuji di sini bocorannya.
    assert bocor_sudut.overlap_fraction > bocor_muka.overlap_fraction
    assert bocor_sudut.pz_bocor_mesh / bocor_sudut.pz > bocor_muka.pz_bocor_mesh / bocor_muka.pz


def test_leak_traces_tidak_bergantung_besar_pz():
    """Fraksi bocoran murni geometri+mesh -- itu yang membuatnya dapat diukur SAAT MESH.

    Bila ia bergantung `Pz`, guard di `pilecap-mesh` (yang tidak pernah membaca
    `pile_reactions.csv`) tidak akan mungkin ada.
    """
    geom = _geom()
    mesh = _mesh(geom, 2 * R_PILE / 8)
    satuan = fem_engine.leak_traces(mesh, geom)[0]

    (besar,) = fem_engine.PilePressureLoad().apply(
        mesh, geom, {"P1": PZ}, fixed_nodes=fem_engine.fixed_support_nodes(mesh, geom)
    )[1]
    assert satuan.pz_bocor_mesh / satuan.pz == pytest.approx(
        besar.pz_bocor_mesh / besar.pz, rel=1e-12
    )


def test_guard_menolak_bocoran_di_atas_ambang_error():
    """Mesh terkasar pada overlap SUDUT melewati `OVERLAP_LEAK_ERROR` -- harus ditolak.

    Inilah kasus yang memicu guard ini: model nyata dengan pile menindih sudut pier pada
    mesh terkasar yang diizinkan rule 7a menghasilkan pelat yang menerima ~6% lebih kecil
    daripada seharusnya, tanpa satu pun tanda sebelum v0.9.1.
    """
    geom = _geom_sudut()
    mesh = _mesh(geom, 2 * R_PILE / 6)
    traces = fem_engine.leak_traces(mesh, geom)
    assert traces[0].pz_bocor_mesh / traces[0].pz > config.OVERLAP_LEAK_ERROR

    with pytest.raises(AnalysisError, match="BOCORAN MESH MELEBIHI BATAS") as exc:
        fem_engine.check_mesh_leak(mesh, geom, traces)

    pesan = str(exc.value)
    # Pesan wajib memuat KETIGA hal, bukan sekadar "terlalu kasar".
    assert "%" in pesan, "harus menyebut angka bocorannya"
    assert "TIDAK aman" in pesan, "harus menyebut ARAH galatnya"
    assert "mm" in pesan, "harus menyebut ukuran elemen yang dibutuhkan"
    assert all(ord(c) < 128 for c in pesan), "pesan ikut ke log cp1252"


def test_guard_memperingatkan_di_antara_kedua_ambang():
    """Di antara WARN dan ERROR: jalan terus, tetapi peringatannya WAJIB muncul."""
    geom = _geom()
    mesh = _mesh(geom, 2 * R_PILE / 8)
    traces = fem_engine.leak_traces(mesh, geom)
    bocor = traces[0].pz_bocor_mesh / traces[0].pz
    assert config.OVERLAP_LEAK_WARN < bocor < config.OVERLAP_LEAK_ERROR, (
        f"prasyarat test tidak lagi berlaku: bocoran D/h=8 = {bocor:.4%}"
    )

    (peringatan,) = fem_engine.check_mesh_leak(mesh, geom, traces)
    assert "BOCORAN MESH" in peringatan
    assert "TIDAK aman" in peringatan


def test_guard_diam_bila_bocoran_kecil():
    """Mesh halus -> tidak ada peringatan sama sekali. Guard tidak boleh berisik sia-sia."""
    geom = _geom()
    mesh = _mesh(geom, 2 * R_PILE / 32)
    assert fem_engine.check_mesh_leak(mesh, geom, fem_engine.leak_traces(mesh, geom)) == ()


def test_guard_tidak_aktif_tanpa_overlap(run_kasar):
    """Geometri tanpa overlap tidak boleh menyentuh jalur ini sama sekali.

    Gerbang yang sama dengan golden ex01-ex03: tanpa tumpang tindih, tidak ada `a_lens`,
    sehingga tidak ada yang diperiksa dan tidak ada yang dapat berubah.
    """
    mesh, geom, _ = run_kasar
    tanpa = dataclasses.replace(geom, piers=(), overlaps=())
    traces = fem_engine.leak_traces(mesh, tanpa)
    assert all(t.a_lens == 0.0 for t in traces)
    assert fem_engine.check_mesh_leak(mesh, tanpa, traces) == ()


# ---------------------------------------------------------------------------
# Jaring pengaman: beban di node jepit tanpa overlap terdaftar
# ---------------------------------------------------------------------------


def test_beban_pada_node_jepit_tanpa_overlap_terdaftar_raise(run_kasar):
    """Mesh menyatukan node padahal `geom.overlaps` kosong -> HARUS meledak.

    Ini kegagalan senyap yang paling berbahaya: VC-0 tidak dapat menangkapnya karena
    `Sigma beban` dan `Sigma reaksi` sama-sama memuat gaya yang terserap, sehingga
    residunya nol dan run dilaporkan LULUS.
    """
    mesh, geom, _ = run_kasar
    cfg = _cfg(2 * R_PILE / 8)
    # Mesh-nya TETAP punya grup lensa (node terbagi), hanya catatan geometrinya dikosongkan
    # -- persis keadaan yang dihasilkan celah lebih kecil daripada satu elemen.
    with pytest.raises(AnalysisError, match="mendarat pada node"):
        fem_engine.analyze_combo(
            mesh,
            dataclasses.replace(geom, overlaps=()),
            fem_engine.MaterialProperties.from_config(cfg),
            fem_engine.AnalysisOptions.from_config(cfg),
            combo="UJI",
            pz_by_pile={"P1": PZ},
        )


# ---------------------------------------------------------------------------
# Contoh bawaan ex04
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ex04():
    directory = EXAMPLES / "ex04_pile_overlap_pier"
    loaded = io_utils.load_config(directory / "pilecap_config.json")
    sources = io_utils.resolve_geometry_sources(loaded, input_dir=directory)
    geom = geometry_builder.build_geometry_model(loaded.si, sources)
    batas = (loaded.si.get("pier") or {}).get("max_pile_overlap_fraction")
    peringatan = validators.validate_geometry(geom, max_overlap_fraction=batas)
    mesh = mesh_model.build_mesh_model(
        mesh_engine.generate_mesh(geom, mesh_engine.MeshOptions.from_config(loaded.si))
    )
    return geom, mesh, peringatan


def test_ex04_f_cocok_dengan_rumus_analitis(ex04):
    """Contoh bawaan diuji terhadap RUMUS, bukan terhadap dirinya sendiri."""
    geom, mesh, _ = ex04
    assert len(geom.overlaps) == 2, "P2 dan P5 yang menindih pier"
    for ov in geom.overlaps:
        assert ov.area_geom_m2 == pytest.approx(A_LENSA_ANALITIS, rel=1e-3)
        assert ov.fraction_geom == pytest.approx(F_ANALITIS, rel=1e-3)

    # `f_mesh` (luas elemen) dipakai untuk SELURUH pelaporan; `f_geom` hanya untuk ambang.
    tekanan = {
        t.pile_id: t
        for t in fem_engine.pile_pressures(mesh, geom, {p.pile_id: PZ for p in geom.piles})
    }
    menindih = {ov.pile_id for ov in geom.overlaps}
    for pid, t in tekanan.items():
        if pid in menindih:
            assert t.overlap_fraction == pytest.approx(F_ANALITIS, rel=0.02)
        else:
            assert t.overlap_fraction == 0.0


def test_ex04_memunculkan_peringatan_overlap(ex04):
    _, _, peringatan = ex04
    (baris,) = peringatan
    assert "TUMPANG TINDIH" in baris
    # KEDUA pasangan harus disebut: peringatan yang hanya menyebut satu pile membuat
    # engineer mengira hanya satu yang perlu dicek strut.
    assert "P2 dengan PIER1" in baris
    assert "P5 dengan PIER1" in baris
    # Peringatan ini ikut ke log konsol cp1252; satu karakter non-ASCII melempar
    # UnicodeEncodeError dan MENGHENTIKAN run.
    assert all(ord(c) < 128 for c in baris)


def test_ex04_grup_lensa_terbentuk(ex04):
    _, mesh, _ = ex04
    lensa = sorted(mesh.lens_groups())
    assert lensa == sorted(
        config.GROUP_LENS_PREFIX + f"{ov.pile_id}{config.GROUP_LENS_SEP}{ov.pier_id}"
        for ov in ex04[0].overlaps
    )
    for nama in lensa:
        assert int(mesh.group_mask(nama).sum()) > 0, f"{nama} kosong"


def test_mct_constraint_memuat_node_lens(ex04, tmp_path):
    """Tanpa ini model Midas punya himpunan tumpuan BERBEDA dari model OpenSees.

    VC-6 membandingkan keduanya; perbedaan tumpuan membuat perbandingannya tidak sahih.
    """
    from pilecap_fem.exporters import mct

    geom, mesh, _ = ex04
    path = mct.write_mct(
        tmp_path / "ex04.mct",
        geom,
        mesh,
        fem_engine.MaterialProperties.from_config(_cfg(0.1)),
        loads={"UJI": {p.pile_id: PZ for p in geom.piles}},
    )
    baris = path.read_text(encoding="utf-8").splitlines()
    mulai = baris.index("*CONSTRAINT")
    node_mct: set[int] = set()
    for b in baris[mulai + 1 :]:
        b = b.strip()
        if b.startswith("*"):
            break
        if not b or b.startswith(";"):
            continue
        node_mct.update(int(t) for t in b.split(",", 1)[0].split())

    diharapkan = {
        int(mesh.node_tags[i]) for i in fem_engine.fixed_support_nodes(mesh, geom).tolist()
    }
    assert node_mct == diharapkan


def test_shear_span_ratio_nol_bila_pusat_pile_di_dalam_pier():
    """`face.distance(centroid)` untuk centroid DI DALAM pier mengembalikan jarak ke muka.

    Akibatnya `a/d` tampak AMAN persis ketika kondisinya paling deep -- kebalikan dari
    yang seharusnya.
    """
    from pilecap_fem import postproc_engine

    resolution = GeometryResolution(
        pilecap=EntityResolution(source="json_standard"),
        pile=EntityResolution(source="json_grid"),
        pier=EntityResolution(source="json_standard"),
    )
    geom = GeometryModel(
        pilecap=polygon_from_rect(6.0, 6.0, (0.0, 0.0)),
        thickness=1.2,
        # P1 berpusat DI DALAM pier, P2 jauh di luarnya.
        piles=(
            Pile(pile_id="P1", x=0.4, y=0.0, diameter=0.8),
            Pile(pile_id="P2", x=2.0, y=0.0, diameter=0.8),
        ),
        piers=(
            Pier(
                pier_id="PIER1",
                shape="rectangular",
                centerline=(0.0, 0.0),
                width_x=2.0,
                width_y=2.0,
            ),
        ),
        resolution=resolution,
    )
    baris = {r["pile_id"]: r for r in postproc_engine.shear_span_ratio(geom, 0.075)["rows"]}
    assert baris["P1"]["a_m"] == 0.0
    assert baris["P1"]["a_over_d"] == 0.0
    assert baris["P2"]["a_m"] == pytest.approx(1.0, rel=1e-9)
