"""Golden file — regresi numerik lintas versi (PRD Bagian 8.2).

.. rubric:: Apa yang dibandingkan, dan mengapa BUKAN yang lain

**Mesh dibandingkan lewat statistik invariant, bukan koordinat node.** gmsh tidak
menjamin penomoran maupun posisi node bit-identik antar versi; menyimpan koordinat berarti
membuat test yang gagal setiap kali gmsh dinaikkan, tanpa satu pun angka desain berubah.
Yang disimpan adalah besaran yang memang HARUS tetap: luas per physical group (geometri
murni, `rtol` ketat), sifat 100% quad, dan jumlah node/elemen (toleransi longgar).

**Hasil FEM dibandingkan berbasis LOKASI, bukan nomor elemen.** Nomor elemen berubah antar
versi gmsh, sehingga perbandingan berbasis nomor akan menyilangkan lokasi yang berbeda
tanpa ketahuan. Golden menyimpan nilai medan pada grid probe tetap yang diturunkan dari
**polygon pilecap** (data input, bit-identik setiap run), dirata-rata dengan **kernel
Gauss berbobot luas** atas seluruh elemen.

Ketiganya perlu, dan masing-masing menutup kegagalan yang benar-benar terjadi saat berkas
ini dibangun (lihat CHANGELOG v0.4.0): mesh gmsh **tidak reproducible** — nilai satu
elemen terdekat berbeda hingga 21% antar run, rata-rata dengan radius tegas masih meloncat
saat elemen tepi berpindah keanggotaan, dan grid yang diturunkan dari bounding box mesh
ikut bergeser 3,3 mm sehingga seluruh probe berpindah tempat.

**Selalu `np.isclose`, tidak pernah `==`.** Hasil floating point dari solver tidak wajib
identik bit demi bit antar platform.

.. rubric:: Regenerasi

Hanya lewat ``pytest --regen-golden``, dan **wajib** disertai catatan alasan di
``CHANGELOG.md``. Golden yang diregenerasi tanpa alasan menghapus satu-satunya bukti
bahwa angka tool tidak berubah diam-diam — yang justru menjadi alasan berkas ini ada.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from pilecap_fem import (
    capacity_engine,
    cli_pilecap_analyze,
    cli_pilecap_report,
    config,
    mesh_model,
    postproc_engine,
    reporter,
)
from pilecap_fem.geometry_builder import GeometryModel

pytestmark = pytest.mark.slow

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"

#: Golden disimpan DI DALAM contoh (PRD Bagian 5.4 mensyaratkan `examples/*/expected/`),
#: bukan di `tests/golden/`. Satu salinan saja: dua berkas dengan isi yang tumpang tindih
#: akan menyimpang diam-diam. Konsekuensi yang diinginkan: berkas ini ikut dikemas,
#: sehingga pengguna `uvx` dapat memverifikasi instalasinya mereproduksi angka acuan.
GOLDEN_NAME = "golden.json"


def golden_path(example: str) -> Path:
    return EXAMPLES / example / "expected" / GOLDEN_NAME


#: Grid probe NxN di dalam bounding box polygon pilecap. 7x7 memberi 49 titik: cukup
#: menutupi daerah pier, pile, dan lapangan, tanpa membuat berkas golden menjadi salinan
#: element_resultants.csv yang berisik.
N_PROBE = 7

#: Jumlah node/elemen boleh bergeser sedikit antar versi gmsh tanpa mengubah hasil desain.
MESH_COUNT_RTOL = 0.02
#: Luas physical group adalah geometri murni -- tidak boleh bergeser sama sekali.
AREA_RTOL = 1e-6
#: `atol` per besaran, dinyatakan sebagai fraksi dari nilai terbesar di golden. Tanpa ini
#: elemen yang nilainya nyaris nol akan gagal pada `rtol` meskipun bedanya tidak berarti.
NEAR_ZERO_FRACTION = 1e-4

#: Toleransi besaran DESAIN (momen lajur, `d`, `As`). DIUKUR pada 3 run berturut-turut
#: dengan kode yang sama: sebaran maksimum 0,021% (ex02), 0,000% (ex01 & ex03). Nilai
#: `VALIDATION_RTOL` = 0,1% karena itu memberi margin ~5x terhadap variasi mesh yang
#: memang ada, tanpa melonggar sampai perubahan nyata bisa lolos.
DESIGN_RTOL = config.VALIDATION_RTOL
#: Toleransi nilai medan hasil rata-rata kernel Gauss. Lebih longgar dari besaran desain:
#: rata-rata itu memuluskan medan tetapi tetap dihitung dari elemen yang posisinya berbeda
#: antar run. Angkanya diverifikasi dengan menjalankan perbandingan terhadap mesh yang
#: dibangkitkan ulang, bukan ditebak.
FIELD_RTOL = 5e-3

FIELDS = ("m_xx", "m_yy", "m_xy", "q_x", "q_y")


# ---------------------------------------------------------------------------
# Menjalankan contoh (sekali per sesi)
# ---------------------------------------------------------------------------


def _run_example(name: str, output_root: Path) -> Path:
    directory = EXAMPLES / name
    analyze_args = cli_pilecap_analyze.build_parser().parse_args(
        [
            "--config",
            str(directory / "pilecap_config.json"),
            "--input-dir",
            str(directory),
            "--output-dir",
            str(output_root),
            "--dpi",
            "60",
        ]
    )
    run_dir = cli_pilecap_analyze.run(analyze_args, "pilecap-analyze (golden)")
    report_args = cli_pilecap_report.build_parser().parse_args(
        ["--result-dir", str(run_dir), "--dpi", "60"]
    )
    cli_pilecap_report.run(report_args, "pilecap-report (golden)")
    return run_dir


@pytest.fixture(scope="session")
def runs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    root = tmp_path_factory.mktemp("golden")
    return {name: _run_example(name, root / name) for name in config.EXAMPLE_NAMES}


# ---------------------------------------------------------------------------
# Ekstraksi besaran yang di-golden-kan
# ---------------------------------------------------------------------------


def _manifest(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))


def _mesh_stats(run_dir: Path) -> dict[str, Any]:
    stats = _manifest(run_dir)["model_stats"]
    return {
        "n_nodes": stats["n_nodes"],
        "n_elements": stats["n_elements"],
        "all_quad": stats["mesh"]["all_quad"],
        "n_surfaces_after_fragment": stats["mesh"]["n_surfaces_after_fragment"],
        "group_element_counts": stats["group_element_counts"],
        "group_area_occ_m2": stats["group_area_occ_m2"],
        "n_fixed_nodes": stats["n_fixed_nodes"],
    }


def _probe_grid(geom: GeometryModel) -> np.ndarray:
    """Grid probe tetap, diturunkan dari **bounding box polygon pilecap**.

    Sumbernya geometri input, BUKAN mesh. Bounding box centroid elemen ikut bergeser
    antar run (terukur 3,3 mm pada ex02), sehingga probe yang diturunkan darinya
    berpindah tempat -- dan seluruh nilai di bawahnya ikut berubah tanpa ada yang salah
    pada medannya. Polygon pilecap berasal langsung dari input dan bit-identik setiap run.

    Tepi bbox dihindari (5%..95%) agar probe tidak jatuh tepat di batas pelat.
    """
    xmin, ymin, xmax, ymax = geom.pilecap.bounds
    xs = np.linspace(xmin + 0.05 * (xmax - xmin), xmin + 0.95 * (xmax - xmin), N_PROBE)
    ys = np.linspace(ymin + 0.05 * (ymax - ymin), ymin + 0.95 * (ymax - ymin), N_PROBE)
    grid_x, grid_y = np.meshgrid(xs, ys, indexing="ij")
    return np.column_stack([grid_x.ravel(), grid_y.ravel()])


def _probe_values(
    combo_dir: Path, mesh: mesh_model.MeshModel, geom: GeometryModel
) -> dict[str, Any]:
    """Nilai medan di sekitar setiap probe lewat kernel Gauss berbobot luas.

    **Bukan** nilai satu elemen terdekat, dan **bukan** rata-rata dalam radius tegas.
    Keduanya sudah dicoba dan gagal berulang tanpa perubahan kode:

    * Nilai satu elemen terdekat berbeda hingga **21%** antar run -- bukan karena medannya
      berubah, melainkan karena elemen terdekatnya bukan elemen yang sama.
    * Rata-rata dengan radius tegas masih bergantung pada elemen mana yang kebetulan
      berada tepat di dalam/di luar batas; satu elemen yang berpindah keanggotaan
      menggeser rata-ratanya secara diskrit.

    Kernel Gauss tanpa cutoff membuat bobot berubah **mulus** terhadap posisi centroid,
    sehingga pergeseran mesh sekecil apa pun hanya menggeser hasilnya sekecil itu juga.
    Itulah yang membuat besaran ini benar-benar dapat dibandingkan antar run.
    """
    results = reporter.read_element_resultants_csv(
        combo_dir / "element_resultants.csv", combo_dir.name
    )
    probes = _probe_grid(geom)
    sigma = 1.5 * float(np.sqrt(np.median(mesh.elem_area)))

    delta = mesh.elem_centroid[None, :, :] - probes[:, None, :]
    d2 = np.einsum("pij,pij->pi", delta, delta)
    weight = np.exp(-d2 / (2.0 * sigma**2)) * mesh.elem_area[None, :]
    total = weight.sum(axis=1)

    # Pilecap poligon (mis. L) punya daerah kosong di dalam bounding box-nya. Probe di sana
    # tetap mendapat bobot tak nol dari elemen jauh, tetapi bobotnya sangat kecil sehingga
    # hasilnya tidak bermakna; probe itu dibuang lewat ambang bobot relatif.
    kept = total > 0.01 * float(total.max())
    if not kept.any():
        raise AssertionError("tidak ada satu pun probe yang memuat elemen")

    return {
        "probe_xy_m": probes[kept].tolist(),
        "sigma_m": sigma,
        "values_si": {
            field: ((weight[kept] @ getattr(results, field)) / total[kept]).tolist()
            for field in FIELDS
        },
    }


def _strip_design(
    run_dir: Path, combo_dir: Path, mesh: mesh_model.MeshModel, geom: GeometryModel
) -> list[dict]:
    """Baris desain lentur per lajur -- angka desain sesungguhnya, bukan puncak elemen."""
    manifest = _manifest(run_dir)
    cfg = (manifest.get("parameters") or {}).get("config_si") or {}
    results = reporter.read_element_resultants_csv(
        combo_dir / "element_resultants.csv", combo_dir.name
    )
    design_cfg = cfg.get("design") or {}
    strip_rows = postproc_engine.design_moment_sections(
        results,
        mesh,
        geom,
        n_strips_x=int(design_cfg.get("strips_x", 5)),
        n_strips_y=int(design_cfg.get("strips_y", 5)),
        mesh_size=float((cfg.get("mesh") or {}).get("size_global") or 0.1),
        moment_at=str(design_cfg.get("moment_at", "pier_face")),
    )
    inputs = capacity_engine.CapacityInputs.from_config(cfg)
    return [
        {
            "pier_id": row["pier_id"],
            "sisi": row["sisi"],
            "direction": row["direction"],
            "strip": row["strip"],
            "face": row["face"],
            "M_total_Nm": row["M_total_Nm"],
            "width_m": row["width_m"],
            "Mu_per_m_Nm": row["Mu_per_m_Nm"],
            "d_eff_m": row["d_eff_m"],
            "As_design_m2_per_m": row["As_design_m2_per_m"],
            "status": row["status"],
        }
        for row in capacity_engine.strip_flexure_design(strip_rows, inputs)
        if row["lokasi"] == "muka_pier"
    ]


def _snapshot(run_dir: Path) -> dict[str, Any]:
    model_dir = run_dir / config.MODEL_SUBDIR
    mesh = mesh_model.from_csv(model_dir / "nodes.csv", model_dir / "elements.csv")
    geom = GeometryModel.from_json_dict(
        json.loads((model_dir / config.FILE_GEOMETRY_JSON).read_text(encoding="utf-8"))
    )
    manifest = _manifest(run_dir)

    combos: dict[str, Any] = {}
    for combo, slug in manifest["combo_slug_map"].items():
        combo_dir = run_dir / f"Combo_{slug}"
        combos[combo] = {
            "probes": _probe_values(combo_dir, mesh, geom),
            "strip_design": _strip_design(run_dir, combo_dir, mesh, geom),
        }
    return {"mesh_stats": _mesh_stats(run_dir), "combos": combos}


# ---------------------------------------------------------------------------
# Perbandingan
# ---------------------------------------------------------------------------


def _load_or_regen(name: str, snapshot: dict[str, Any], regen: bool) -> dict[str, Any]:
    path = golden_path(name)
    if regen or not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        pytest.skip(
            f"Golden {path.name} ditulis ulang. Jalankan ulang tanpa --regen-golden untuk "
            "membandingkannya, dan catat alasan regenerasi di CHANGELOG.md."
        )
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def snapshots(runs: dict[str, Path]) -> dict[str, dict[str, Any]]:
    """Ekstraksi dilakukan sekali per contoh, dipakai ulang semua test perbandingan."""
    return {name: _snapshot(run_dir) for name, run_dir in runs.items()}


@pytest.fixture(params=config.EXAMPLE_NAMES)
def golden_case(
    request: pytest.FixtureRequest,
    snapshots: dict[str, dict[str, Any]],
    regen_golden: bool,
) -> tuple[str, dict[str, Any], dict[str, Any]]:
    name = str(request.param)
    snapshot = snapshots[name]
    expected = _load_or_regen(name, snapshot, regen_golden)
    return name, expected, snapshot


def test_mesh_invariant_geometri_tidak_bergeser(golden_case):
    """Luas per physical group adalah geometri murni -- tidak boleh berubah sama sekali."""
    _, expected, actual = golden_case
    exp = expected["mesh_stats"]
    act = actual["mesh_stats"]

    assert act["all_quad"] is True
    assert act["n_surfaces_after_fragment"] == exp["n_surfaces_after_fragment"]
    assert set(act["group_area_occ_m2"]) == set(exp["group_area_occ_m2"])
    for group, area in exp["group_area_occ_m2"].items():
        assert np.isclose(act["group_area_occ_m2"][group], area, rtol=AREA_RTOL, atol=0.0), (
            f"luas physical group {group} bergeser: {act['group_area_occ_m2'][group]} != {area}"
        )


def test_jumlah_node_elemen_dalam_toleransi(golden_case):
    """Penomoran gmsh boleh bergeser sedikit; perubahan besar berarti mesh lain."""
    _, expected, actual = golden_case
    for key in ("n_nodes", "n_elements"):
        assert np.isclose(
            actual["mesh_stats"][key],
            expected["mesh_stats"][key],
            rtol=MESH_COUNT_RTOL,
            atol=0.0,
        ), f"{key}: {actual['mesh_stats'][key]} vs golden {expected['mesh_stats'][key]}"


def test_probe_berada_di_lokasi_dan_kepadatan_yang_sama(golden_case):
    """Probe harus berada di titik yang sama, dengan kepadatan mesh yang sebanding.

    Grid probe berasal dari polygon pilecap sehingga wajib **persis** sama; `sigma`
    berasal dari luas elemen sehingga hanya boleh bergeser sedikit. Bila salah satunya
    berubah, nilai medan yang dibandingkan sesudahnya bukan besaran yang sama.
    """
    name, expected, actual = golden_case
    for combo, exp in expected["combos"].items():
        act = actual["combos"][combo]["probes"]
        assert np.allclose(act["probe_xy_m"], exp["probes"]["probe_xy_m"], atol=1e-12), (
            f"{name} [{combo}]: grid probe bergeser -- geometri pilecap berubah"
        )
        assert np.isclose(act["sigma_m"], exp["probes"]["sigma_m"], rtol=0.05), (
            f"{name} [{combo}]: sigma {act['sigma_m']:.5f} m vs golden "
            f"{exp['probes']['sigma_m']:.5f} m -- kepadatan mesh berubah"
        )


def test_resultant_pada_probe_cocok_dengan_golden(golden_case):
    name, expected, actual = golden_case
    for combo, exp in expected["combos"].items():
        for field in FIELDS:
            gold = np.asarray(exp["probes"]["values_si"][field], dtype=np.float64)
            got = np.asarray(
                actual["combos"][combo]["probes"]["values_si"][field], dtype=np.float64
            )
            atol = NEAR_ZERO_FRACTION * float(np.nanmax(np.abs(gold)) or 1.0)
            bad = ~np.isclose(got, gold, rtol=FIELD_RTOL, atol=atol)
            assert not bad.any(), (
                f"{name} [{combo}] {field}: {int(bad.sum())} dari {gold.size} probe berbeda; "
                f"contoh golden={gold[bad][0]:.6e} hasil={got[bad][0]:.6e}"
            )


def test_desain_tulangan_per_lajur_cocok_dengan_golden(golden_case):
    """`As` per lajur -- angka yang benar-benar dipakai desain."""
    name, expected, actual = golden_case
    for combo, exp in expected["combos"].items():
        gold_rows = exp["strip_design"]
        act_rows = actual["combos"][combo]["strip_design"]
        assert len(act_rows) == len(gold_rows), f"{name} [{combo}]: jumlah lajur berbeda"

        for gold, got in zip(gold_rows, act_rows, strict=True):
            key = (gold["pier_id"], gold["sisi"], gold["direction"], gold["strip"])
            assert (got["pier_id"], got["sisi"], got["direction"], got["strip"]) == key
            assert got["face"] == gold["face"], f"{name} [{combo}] {key}: muka berubah"
            assert got["status"] == gold["status"], f"{name} [{combo}] {key}: status berubah"
            for column in ("Mu_per_m_Nm", "d_eff_m", "As_design_m2_per_m"):
                assert _close(got[column], gold[column], DESIGN_RTOL), (
                    f"{name} [{combo}] {key} {column}: {got[column]} vs golden {gold[column]}"
                )


def _close(got: float, gold: float, rtol: float) -> bool:
    """Perbandingan yang menangani `NaN` sebagai NILAI, bukan sebagai kegagalan.

    `NaN` di golden berarti "besaran ini memang tidak terdefinisi di sini" (mis. lajur
    tanpa elemen). Yang harus dijaga adalah statusnya tidak berubah: NaN tetap NaN, dan
    angka tetap angka. `np.isclose` dengan `atol` yang dihitung dari nilai NaN justru
    menghasilkan `atol = nan` dan membandingkan apa pun menjadi False secara diam-diam.
    """
    if np.isnan(gold) or np.isnan(got):
        return bool(np.isnan(gold) and np.isnan(got))
    atol = NEAR_ZERO_FRACTION * abs(gold or 1.0)
    return bool(np.isclose(got, gold, rtol=rtol, atol=atol))
