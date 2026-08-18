"""Test end-to-end CLI `pilecap-report` dan `pilecap-run` (PRD Bagian 6.3, 6.4, 9.1)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from pilecap_fem import (
    cli_pilecap_analyze,
    cli_pilecap_report,
    cli_pilecap_run,
    config,
    mesh_model,
)
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.validators import InputError, PilecapError

pytestmark = pytest.mark.slow

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def _analyze(directory: Path, output_root: Path, *extra: str) -> Path:
    args = cli_pilecap_analyze.build_parser().parse_args(
        [
            "--config",
            str(directory / "pilecap_config.json"),
            "--input-dir",
            str(directory),
            "--output-dir",
            str(output_root),
            "--dpi",
            "60",
            *extra,
        ]
    )
    return cli_pilecap_analyze.run(args, "pilecap-analyze (test)")


def _report(run_dir: Path, *extra: str) -> Path:
    args = cli_pilecap_report.build_parser().parse_args(
        ["--result-dir", str(run_dir), "--dpi", "60", *extra]
    )
    return cli_pilecap_report.run(args, "pilecap-report (test)")


@pytest.fixture(scope="module")
def reported(tmp_path_factory):
    """Satu run analyze + report dipakai bersama beberapa test."""
    workdir = tmp_path_factory.mktemp("report")
    target = workdir / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, workdir / "output")
    _report(run_dir)
    return run_dir


# ---------------------------------------------------------------------------
# Struktur keluaran PRD Bagian 9.1
# ---------------------------------------------------------------------------


def test_seluruh_berkas_model_terbentuk(reported: Path):
    model_dir = reported / config.MODEL_SUBDIR
    for name in (
        "mesh_summary.md",
        config.FILE_MESH_PLAN,
        config.FILE_MODEL_OPSVIS,
        config.FILE_BOUNDARY_CHECK,
        config.FILE_GEOMETRY_JSON,
        "nodes.csv",
        "elements.csv",
    ):
        assert (model_dir / name).is_file(), f"00_Model/{name} tidak dibuat"


def test_seluruh_berkas_kombinasi_terbentuk(reported: Path):
    # `strip_moments_*.csv` SENGAJA tidak ada di sini: `ex01` memakai
    # `design.rebar_basis = "element"` (bawaan), dan pada mode itu jalur lajur tidak
    # dijalankan sama sekali. Keberadaannya diuji pada mode lajur -- lihat
    # `test_mode_lajur_menghasilkan_strip_moments`.
    for combo_dir in reported.glob("Combo_*"):
        for name in (
            config.FILE_CALC_SHEET,
            "element_resultants.csv",
            "shear_checks.csv",
            "reactions.csv",
            "equilibrium_check.json",
            config.FILE_NODE_DISPLACEMENTS,
            config.FILE_TRACEABILITY,
            config.FILE_DEFORMED_OPSVIS,
            config.FILE_CONTOUR_DEFLECTION,
            *(name for name, _, _ in config.CONTOUR_FIELDS.values()),
        ):
            path = combo_dir / name
            assert path.is_file(), f"{combo_dir.name}/{name} tidak dibuat"
            assert path.stat().st_size > 0


def test_folder_envelope_lengkap(reported: Path):
    envelope_dir = reported / config.ENVELOPE_SUBDIR
    assert (envelope_dir / "envelope_values.csv").is_file()
    assert (envelope_dir / "envelope_summary.md").is_file()
    assert (envelope_dir / config.FILE_REBAR_ENVELOPE).is_file()

    # 2 x field gaya (maks & min) + 12 plot tulangan: 4 As, 4 batang terpilih,
    # 2 Av/s, 2 diameter sengkang.
    plots = list(envelope_dir.glob("envelope_*.png"))
    assert len(plots) == 2 * len(config.CONTOUR_FIELDS) + 12


def test_envelope_memuat_plot_tulangan(reported: Path):
    """Tanpa plot envelope, desain lintas kombinasi hanya bisa dibaca dengan mata.

    Pengguna harus membandingkan satu set kontur per kombinasi -- persis pekerjaan yang
    envelope ada untuk menghilangkannya.
    """
    envelope_dir = reported / config.ENVELOPE_SUBDIR
    for berkas, _ in config.REBAR_FACES.values():
        assert (envelope_dir / berkas.replace("contour_", "envelope_")).is_file()
    for _, avs, dia, _ in config.SHEAR_REBAR_FIELDS.values():
        assert (envelope_dir / avs.replace("contour_", "envelope_")).is_file()
        assert (envelope_dir / dia.replace("contour_", "envelope_")).is_file()


def test_envelope_lajur_hanya_pada_mode_lajur(reported: Path, reported_lajur: Path):
    """`strip_design_envelope.csv` menjawab "apa yang saya pasang di lajur ini".

    Pada mode elemen lajur tidak dihitung sama sekali, sehingga berkasnya tidak boleh ada
    -- berkas kosong atau berisi angka lama sama menyesatkannya.
    """
    import csv

    assert not (reported / config.ENVELOPE_SUBDIR / config.FILE_STRIP_ENVELOPE).exists()

    path = reported_lajur / config.ENVELOPE_SUBDIR / config.FILE_STRIP_ENVELOPE
    assert path.is_file()
    with open(path, encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    # 5 lajur x 2 sisi muka pier x 2 arah, masing-masing dengan kombinasi penentunya.
    assert len(rows) == 20
    assert all(r["governing_combo"] for r in rows)


def test_summary_terbentuk(reported: Path):
    assert (reported / config.FILE_SUMMARY).is_file()


# ---------------------------------------------------------------------------
# Isi laporan -- yang WAJIB muncul (PRD Bagian 1.3 poin 5 & 6)
# ---------------------------------------------------------------------------


def test_summary_memuat_known_limitations_dan_disclaimer(reported: Path):
    text = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    assert "strut-and-tie" in text  # keterbatasan #1
    assert "jepit sempurna" in text  # keterbatasan #2
    assert "ALAT BANTU" in text
    assert "engineer yang" in text
    assert "NOT_EVALUATED" in text


def test_summary_melaporkan_rasio_deep_tanpa_vonis(reported: Path):
    text = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    assert "TIDAK DINILAI" in text
    assert "belum dikonfirmasi" in text


def test_summary_memuat_governing_combo(reported: Path):
    text = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    assert "governing_combo" in text
    assert "1.2D+1.6L" in text or "1.2D+1.0W" in text


def test_calc_sheet_memuat_sepuluh_bagian(reported: Path):
    text = (reported / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).read_text(encoding="utf-8")
    for heading in (
        "## 1. INPUT YANG DIPAKAI",
        "### 1a. RESOLUSI SUMBER GEOMETRI",
        "## 2. MODEL FEM",
        "## 3. PEMBEBANAN",
        "## 4. CEK KESEIMBANGAN (VC-0)",
        "## 5. HASIL PER ELEMEN",
        "## 6. MOMEN DESAIN PER LAJUR",
        "## 7. GESER",
        "## 8. ASUMSI & KETERBATASAN",
        "## 9. PERNYATAAN TANGGUNG JAWAB",
        "## 10. PROVENANCE",
    ):
        assert heading in text, f"calc sheet kehilangan bagian: {heading}"


def test_calc_sheet_rantai_telusur_dapat_dihitung_ulang(reported: Path):
    """Angka di calc sheet harus benar-benar menghasilkan m_xx yang dilaporkan."""
    trace = json.loads(
        (reported / "Combo_1_2D_1_6L" / config.FILE_TRACEABILITY).read_text(encoding="utf-8")
    )
    mean = np.array(trace["gauss_mean"])
    factor = trace["sign_factors"]["moment"]
    m11, m22, m12 = (factor * mean[i] for i in (3, 4, 5))
    theta = np.radians(trace["theta_deg"])
    c, s = np.cos(theta), np.sin(theta)
    assert m11 * c * c + m22 * s * s - 2 * m12 * s * c == pytest.approx(
        trace["global"]["m_xx"], rel=1e-9
    )

    text = (reported / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).read_text(encoding="utf-8")
    assert f"tag {trace['element_tag']}" in text
    assert "GP1" in text and "GP4" in text


def test_calc_sheet_memisahkan_kapasitas_yang_dihitung_dari_yang_tidak(reported: Path):
    """Lentur & geser SATU ARAH dihitung; pons tetap tidak -- dan keduanya dinyatakan.

    Sejak integrasi shell-kit, kalimat "KAPASITAS TIDAK DIHITUNG" yang berlaku menyeluruh
    tidak lagi benar. Yang harus dijaga adalah pembedaannya: pembaca tidak boleh mengira
    pons ikut tercakup hanya karena angka kapasitas lain sudah muncul.
    """
    text = (reported / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).read_text(encoding="utf-8")

    assert "GESER PONS TETAP TIDAK DICEK" in text
    assert "NOT_EVALUATED" in text
    assert "Kapasitas geser SATU ARAH" in text
    assert "SNI 2847:2019 Ps. 22.5.5.1" in text
    assert "7a. DESAIN LENTUR" in text
    assert "shell-kit" in text


def test_peringatan_deep_pilecap_mendahului_tabel_As(reported: Path):
    """Peringatan deep pilecap WAJIB di ATAS tabel `As`, bukan catatan kaki.

    Diuji lewat posisi karakter: angka `As` yang terbaca lebih dulu daripada
    peringatannya adalah persis kegagalan yang ingin dicegah (PRD Bagian 8.3 #1).
    """
    for name in (config.FILE_CALC_SHEET, "../" + config.FILE_SUMMARY):
        text = (reported / "Combo_1_2D_1_6L" / name).read_text(encoding="utf-8")
        warning_at = text.find("TIDAK SAH sebagai dasar desain")
        table_at = text.find("As pakai [mm^2/m]")
        assert warning_at != -1, f"peringatan deep pilecap tidak ada di {name}"
        assert table_at != -1, f"tabel As tidak ada di {name}"
        assert warning_at < table_at, f"peringatan muncul SETELAH tabel As di {name}"


def test_shear_checks_seluruhnya_not_evaluated(reported: Path):
    import csv

    with open(reported / "Combo_1_2D_1_6L" / "shear_checks.csv", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert all(r["kapasitas"] == "NOT_EVALUATED" for r in rows)
    assert any(r["jenis"] == "punching" for r in rows)


def test_envelope_csv_memuat_governing_per_lokasi(reported: Path):
    import csv

    with open(
        reported / config.ENVELOPE_SUBDIR / "envelope_values.csv", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    assert rows
    assert "m_xx_max_governing_combo" in rows[0]
    assert all(r["m_xx_max_governing_combo"] for r in rows)


def test_envelope_cocok_dengan_maksimum_antar_kombinasi(reported: Path):
    """Envelope harus benar-benar = ekstrem dari CSV per kombinasi."""
    import csv

    per_combo = []
    for combo_dir in sorted(reported.glob("Combo_*")):
        with open(combo_dir / "element_resultants.csv", encoding="utf-8") as handle:
            per_combo.append([float(r["m_x [kNm/m]"]) for r in csv.DictReader(handle)])
    expected = np.max(np.vstack(per_combo), axis=0)

    with open(
        reported / config.ENVELOPE_SUBDIR / "envelope_values.csv", encoding="utf-8"
    ) as handle:
        actual = [float(r["m_xx_max [kNm/m]"]) for r in csv.DictReader(handle)]

    assert np.allclose(actual, expected, atol=1e-4)


def test_envelope_summary_memperingatkan_bukan_untuk_cek_statika(reported: Path):
    text = (reported / config.ENVELOPE_SUBDIR / "envelope_summary.md").read_text(encoding="utf-8")
    assert "BUKAN kondisi keseimbangan tunggal" in text
    assert "tidak boleh" in text


# ---------------------------------------------------------------------------
# Round-trip CSV
# ---------------------------------------------------------------------------


def test_mesh_round_trip_dari_csv_identik(reported: Path):
    """`pilecap-report` membaca mesh dari CSV -- hasilnya harus identik dengan aslinya."""
    model_dir = reported / config.MODEL_SUBDIR
    mesh = mesh_model.from_csv(model_dir / "nodes.csv", model_dir / "elements.csv")
    manifest = json.loads((reported / "run_manifest.json").read_text(encoding="utf-8"))

    stats = manifest["model_stats"]
    assert mesh.n_nodes == stats["n_nodes"]
    assert mesh.n_elements == stats["n_elements"]
    assert set(mesh.group_names) == set(stats["group_element_counts"])
    assert mesh.group_element_counts() == stats["group_element_counts"]
    assert float(mesh.elem_area.sum()) == pytest.approx(
        sum(stats["group_area_occ_m2"].values()), rel=1e-3
    )


def test_geometry_json_round_trip(reported: Path):
    path = reported / config.MODEL_SUBDIR / config.FILE_GEOMETRY_JSON
    geom = GeometryModel.from_json_dict(json.loads(path.read_text(encoding="utf-8")))
    kembali = GeometryModel.from_json_dict(geom.to_json_dict())

    assert kembali.pilecap_area == pytest.approx(geom.pilecap_area)
    assert kembali.thickness == pytest.approx(geom.thickness)
    assert [p.pile_id for p in kembali.piles] == [p.pile_id for p in geom.piles]
    assert [p.pier_id for p in kembali.piers] == [p.pier_id for p in geom.piers]
    assert kembali.resolution.pilecap.source == geom.resolution.pilecap.source


def test_report_dapat_dijalankan_ulang_tanpa_analisis_ulang(reported_lajur: Path):
    """Mengganti jumlah lajur tidak boleh menuntut analisis FEM diulang.

    Memakai fixture mode LAJUR: pada mode elemen jumlah lajur tidak dibaca sama sekali,
    sehingga di sana test ini tidak menguji apa pun.
    """
    _report(reported_lajur, "--strips-x", "3", "--strips-y", "3")
    import csv

    with open(
        reported_lajur / "Combo_1_2D_1_6L" / "strip_moments_x.csv", encoding="utf-8"
    ) as handle:
        rows = list(csv.DictReader(handle))
    # 3 lajur x 2 sisi muka pier x 1 pier
    assert len(rows) == 6


# ---------------------------------------------------------------------------
# Jalur gagal
# ---------------------------------------------------------------------------


def test_wood_armer_gagal_dengan_pesan_sumber_primer(reported: Path):
    """PRD Bagian 7.2(6): aturan koreksi wajib dari Wood (1968), bukan dari ingatan."""
    with pytest.raises(NotImplementedError, match="sumber primer"):
        _report(reported, "--wood-armer")


def test_entry_point_wood_armer_mengembalikan_kode_4(reported: Path, capsys):
    code = cli_pilecap_report.entry_point(
        ["--result-dir", str(reported), "--wood-armer", "--dpi", "60"]
    )
    assert code == 4
    assert "BELUM TERSEDIA" in capsys.readouterr().err


def test_no_envelope_melewati_folder_envelope(tmp_path: Path):
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, tmp_path / "output", "--combo", "1.2D+1.6L")
    _report(run_dir, "--no-envelope")
    assert not (run_dir / config.ENVELOPE_SUBDIR).exists()
    assert (run_dir / config.FILE_SUMMARY).is_file()


def test_run_gagal_tidak_dapat_dilaporkan(tmp_path: Path):
    """Laporan tidak boleh dibuat dari run yang statusnya FAILED."""
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    with pytest.raises(Exception, match="VC-0 GAGAL"):
        _analyze(target, tmp_path / "output", "--equilibrium-rtol", "1e-30")

    run_dir = next((tmp_path / "output").iterdir())
    with pytest.raises(InputError, match="bukan 'OK'"):
        _report(run_dir)


def test_geometry_json_hilang_raise(reported: Path, tmp_path: Path):
    salinan = tmp_path / "salinan"
    shutil.copytree(reported, salinan)
    (salinan / config.MODEL_SUBDIR / config.FILE_GEOMETRY_JSON).unlink()
    with pytest.raises(InputError, match=r"geometry.json"):
        _report(salinan)


def test_traceability_hilang_raise(reported: Path, tmp_path: Path):
    """Calc sheet tidak boleh menyajikan rantai telusur yang terpotong diam-diam."""
    salinan = tmp_path / "salinan2"
    shutil.copytree(reported, salinan)
    (salinan / "Combo_1_2D_1_6L" / config.FILE_TRACEABILITY).unlink()
    with pytest.raises(InputError, match="terpotong"):
        _report(salinan)


def test_no_save_raw_membuat_laporan_menolak(tmp_path: Path):
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, tmp_path / "output", "--no-save-raw", "--combo", "1.2D+1.6L")
    with pytest.raises(InputError, match="no-save-raw"):
        _report(run_dir)


def test_latest_run_memilih_yang_terbaru(tmp_path: Path):
    root = tmp_path / "output"
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    first = _analyze(target, root, "--combo", "1.2D+1.6L")
    second = _analyze(target, root, "--combo", "1.2D+1.6L")
    assert cli_pilecap_report.latest_run(root) == second
    assert first != second


def test_latest_run_tanpa_run_raise(tmp_path: Path):
    (tmp_path / "kosong").mkdir()
    with pytest.raises(InputError, match="Tidak ada run"):
        cli_pilecap_report.latest_run(tmp_path / "kosong")


# ---------------------------------------------------------------------------
# pilecap-run (PRD Bagian 6.4)
# ---------------------------------------------------------------------------


def test_pilecap_run_end_to_end(tmp_path: Path):
    """Satu perintah menghasilkan struktur penuh, dalam SATU folder run."""
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    args = cli_pilecap_run.build_parser().parse_args(
        [
            "--config",
            str(target / "pilecap_config.json"),
            "--input-dir",
            str(target),
            "--output-dir",
            str(tmp_path / "output"),
            "--dpi",
            "60",
            "--combo",
            "1.2D+1.6L",
        ]
    )
    run_dir = cli_pilecap_run.run(args, "pilecap-run (test)")

    assert (run_dir / config.FILE_SUMMARY).is_file()
    assert (run_dir / config.MODEL_SUBDIR / config.FILE_BOUNDARY_CHECK).is_file()
    assert (run_dir / "Combo_1_2D_1_6L" / config.FILE_CALC_SHEET).is_file()
    assert (run_dir / "Combo_1_2D_1_6L" / "contour_mx.png").is_file()
    # Hanya SATU folder run: analyze dan report berbagi folder yang sama.
    assert len(list((tmp_path / "output").iterdir())) == 1


def test_pilecap_run_meneruskan_argumen_laporan(tmp_path: Path):
    target = tmp_path / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    args = cli_pilecap_run.build_parser().parse_args(
        [
            "--config",
            str(target / "pilecap_config.json"),
            "--input-dir",
            str(target),
            "--output-dir",
            str(tmp_path / "output"),
            "--dpi",
            "60",
            "--combo",
            "1.2D+1.6L",
            "--no-envelope",
            "--strips-x",
            "2",
        ]
    )
    run_dir = cli_pilecap_run.run(args, "pilecap-run (test)")
    assert not (run_dir / config.ENVELOPE_SUBDIR).exists()


# ---------------------------------------------------------------------------
# design.rebar_basis -- mode elemen (bawaan) vs mode lajur
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reported_lajur(tmp_path_factory):
    """Run `ex01` yang dipaksa ke mode LAJUR, untuk menguji cabang yang satunya."""
    import json

    workdir = tmp_path_factory.mktemp("report_lajur")
    target = workdir / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    cfg_path = target / "pilecap_config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["design"]["rebar_basis"] = "strip"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    run_dir = _analyze(target, workdir / "output")
    _report(run_dir)
    return run_dir


def test_mode_elemen_tidak_menghasilkan_keluaran_lajur(reported: Path):
    """Mode elemen memutus jalur lajur, bukan sekadar menyembunyikan tabelnya.

    Berkas yang tetap ditulis akan terbaca sebagai angka desain oleh siapa pun yang
    membuka folder hasil -- padahal pada mode ini ia bukan, dan tidak pernah dipakai.
    """
    for combo_dir in reported.glob("Combo_*"):
        assert not (combo_dir / "strip_moments_x.csv").exists()
        assert not (combo_dir / "strip_moments_y.csv").exists()

        teks = (combo_dir / config.FILE_CALC_SHEET).read_text(encoding="utf-8")
        assert "dari nilai per ELEMEN" in teks
        assert "dari momen LAJUR" not in teks
        # Angka desain mode ini bergantung kehalusan mesh; ukurannya WAJIB tercetak
        # bersama angkanya, kalau tidak hasilnya tidak dapat direproduksi.
        assert "`mesh.size_global`" in teks


def test_mode_lajur_menghasilkan_strip_moments(reported_lajur: Path):
    """Mode lajur mempertahankan seluruh perilaku lama, apa adanya."""
    for combo_dir in reported_lajur.glob("Combo_*"):
        for name in ("strip_moments_x.csv", "strip_moments_y.csv"):
            path = combo_dir / name
            assert path.is_file(), f"{combo_dir.name}/{name} tidak dibuat"
            assert path.stat().st_size > 0

        teks = (combo_dir / config.FILE_CALC_SHEET).read_text(encoding="utf-8")
        assert "dari momen LAJUR di muka pier" in teks
        assert "dari nilai per ELEMEN" not in teks


def test_summary_menyatakan_basis_yang_dipakai(reported: Path, reported_lajur: Path):
    """Tidak ada berkas hasil yang boleh beredar tanpa menyebut metodenya.

    Kedua mode menghasilkan angka yang berbeda dari model yang sama, jadi angka tanpa
    keterangan metode tidak dapat dibandingkan maupun diperiksa ulang.
    """
    elemen = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    lajur = (reported_lajur / config.FILE_SUMMARY).read_text(encoding="utf-8")

    assert "`element`" in elemen and "nilai per elemen" in elemen
    assert "`strip`" in lajur and "integrasi lajur" in lajur
    # Kolom telusur berbeda karena yang ditelusuri memang berbeda.
    assert "lokasi [" in elemen
    assert "| lajur |" in lajur or "lajur" in lajur


def test_mode_elemen_melaporkan_lokasi_puncak(reported: Path):
    """Tanpa koordinat, puncak di sudut pier (singularitas) tidak dapat dibedakan.

    Inilah satu-satunya cara membaca angka maksimum mode elemen secara bertanggung
    jawab -- dan justru itu yang hilang bila hanya angkanya yang dicetak.
    """
    teks = (reported / config.FILE_SUMMARY).read_text(encoding="utf-8")
    assert "elem " in teks, "baris governing tidak menyebut elemen asalnya"
    # Muka yang dikuasai As_min: SELURUH elemen seri, jadi koordinat mana pun tidak
    # istimewa dan menyajikannya seolah bermakna akan menyesatkan.
    assert "seluruh elemen seri" in teks


def test_caption_plot_per_kombinasi_mengikuti_rebar_basis(tmp_path_factory, monkeypatch):
    """Caption yang tercetak di plot As per-kombinasi HARUS mengikuti `rebar_basis`.

    Regresi: `_render_rebar_plots` dipanggil dari `_report_one_combo` tanpa meneruskan
    `rebar_basis`, sehingga jatuh ke default fungsi ("strip") apa pun mode yang
    sebenarnya dipakai -- caption bertema "peta orientasi" tercetak pada plot mode
    `element` padahal plot itu JUSTRU sumber angka desainnya. Jalur envelope tidak
    terpengaruh karena sudah meneruskan `rebar_basis` secara eksplisit.
    """
    workdir = tmp_path_factory.mktemp("caption")
    target = workdir / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, workdir / "output")

    captured: dict[str, tuple[str, ...]] = {}
    original = cli_pilecap_report.renderer.render_contour

    def spy(path, *args, **kwargs):
        name = Path(path).name
        if name.startswith("contour_As_"):
            captured[name] = kwargs["block"].notes
        return original(path, *args, **kwargs)

    monkeypatch.setattr(cli_pilecap_report.renderer, "render_contour", spy)
    _report(run_dir)

    assert captured, "tidak ada plot contour_As_* yang tertangkap"
    for name, notes in captured.items():
        gabungan = " ".join(notes).lower()
        assert "sumber angka desain" in gabungan, (
            f"{name}: caption tidak menyatakan mode element -- {notes}"
        )
        assert "peta orientasi" not in gabungan, (
            f"{name}: caption masih memakai teks mode strip -- {notes}"
        )


# ---------------------------------------------------------------------------
# Laporan PDF (`--pdf`)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def reported_pdf(tmp_path_factory):
    """Run tersendiri dengan `--pdf`.

    Sengaja TIDAK memakai ulang `reported`: begitu PDF dibuat di folder itu,
    `test_tanpa_flag_pdf_tidak_ada_berkas_pdf_yang_dibuat` kehilangan artinya karena
    urutan test tidak dijamin.
    """
    workdir = tmp_path_factory.mktemp("pdf")
    target = workdir / "ex01"
    shutil.copytree(EXAMPLES / "ex01_standard_4pile", target)
    run_dir = _analyze(target, workdir / "output")
    _report(run_dir, "--pdf")
    return run_dir


def test_flag_pdf_menghasilkan_berkas_pdf_dan_sumber_typ(reported_pdf: Path):
    """Sumber `.typ` ikut disimpan: ia satu-satunya bentuk laporan yang dapat di-diff."""
    pdf = reported_pdf / config.FILE_PDF_REPORT
    typ = reported_pdf / config.FILE_PDF_SOURCE
    assert pdf.is_file() and typ.is_file()
    assert pdf.read_bytes().startswith(b"%PDF-")


def test_tanpa_flag_pdf_tidak_ada_berkas_pdf_yang_dibuat(reported: Path):
    """`--pdf` bersifat opt-in; run yang sudah ada tidak boleh berubah perilakunya."""
    assert not (reported / config.FILE_PDF_REPORT).exists()
    assert not (reported / config.FILE_PDF_SOURCE).exists()


def test_pdf_memuat_seluruh_bab_wajib(reported_pdf: Path):
    teks = (reported_pdf / config.FILE_PDF_SOURCE).read_text(encoding="utf-8")
    for judul in (
        "= Ringkasan eksekutif",
        "= Dasar teori",
        "= Data masukan",
        "= Envelope lintas kombinasi",
        "= Asumsi dan keterbatasan",
        "= Pernyataan tanggung jawab",
        "= Lampiran A",
    ):
        assert judul in teks, f"bab {judul!r} hilang dari dokumen"


def test_pdf_menyebut_setiap_kombinasi_yang_dianalisis(reported_pdf: Path):
    teks = (reported_pdf / config.FILE_PDF_SOURCE).read_text(encoding="utf-8")
    for combo_dir in reported_pdf.glob("Combo_*"):
        slug = combo_dir.name.removeprefix("Combo_")
        assert slug.replace("_", "") in teks.replace("\\", "").replace(".", "").replace(
            "+", ""
        ).replace("_", ""), f"kombinasi {slug} tidak muncul di dokumen"


def test_peringatan_deep_pilecap_mendahului_tabel_As_di_pdf(reported_pdf: Path):
    """PRD Bagian 8.3 keterbatasan #1 -- saudara `test_peringatan_deep_pilecap_...`.

    Begitu angka `As` tercetak, pembaca cenderung langsung memakainya. Peringatan yang
    baru terbaca SETELAH tabel sudah terlambat, dan di PDF konsekuensinya lebih besar
    daripada di Markdown: dokumen inilah yang dicetak dan ditandatangani.
    """
    teks = (reported_pdf / config.FILE_PDF_SOURCE).read_text(encoding="utf-8")
    awal = teks.index("= Ringkasan eksekutif")
    peringatan = teks.index("MODEL LENTUR PELAT", awal)
    tabel = teks.index("As perlu", peringatan - 4000 if peringatan > 4000 else 0)
    assert peringatan < teks.index("As pakai", awal), (
        "peringatan deep pilecap muncul SETELAH tabel As pada ringkasan"
    )
    assert tabel >= 0


def test_ringkasan_pdf_cocok_dengan_summary_md(reported_pdf: Path):
    """Penjaga divergensi utama: PDF dan SUMMARY harus menyebut angka yang SAMA.

    Keduanya lahir dari objek yang sama (`reporter.CalcSheetInputs` dan `rebar_governing`),
    jadi perbedaan di sini berarti salah satu jalur penyajian menghitung sendiri -- persis
    yang dilarang aturan modul `reporting_pdf`.
    """
    summary = (reported_pdf / config.FILE_SUMMARY).read_text(encoding="utf-8")
    typ = (reported_pdf / config.FILE_PDF_SOURCE).read_text(encoding="utf-8")

    bagian = summary[summary.index("## 3a.") :]
    bagian = bagian[: bagian.index("\n## ")] if "\n## " in bagian else bagian
    baris = [b for b in bagian.splitlines() if b.startswith("| ") and " | " in b]
    nilai = [b.split("|")[3].strip() for b in baris[2:]]  # kolom "As pakai"
    assert nilai, "tabel governing SUMMARY tidak terbaca"

    for angka in nilai:
        assert angka in typ, (
            f"As governing {angka!r} ada di SUMMARY.md tetapi TIDAK di laporan PDF -- "
            "kedua dokumen menyimpang"
        )


def test_pdf_tidak_memuat_dump_seluruh_elemen(reported_pdf: Path):
    """Keputusan desain: tabel memuat nilai governing, data lengkap tetap di CSV.

    `ex01` punya ribuan elemen; mencetaknya akan menghasilkan dokumen ratusan halaman
    yang tidak terbaca. Yang wajib ada adalah PENUNJUK ke berkas datanya.
    """
    typ = (reported_pdf / config.FILE_PDF_SOURCE).read_text(encoding="utf-8")
    mesh = mesh_model.from_csv(
        reported_pdf / config.MODEL_SUBDIR / "nodes.csv",
        reported_pdf / config.MODEL_SUBDIR / "elements.csv",
    )
    assert typ.count("\n  [") < mesh.n_elements, "dokumen tampak memuat satu baris per elemen"
    assert "`element_resultants.csv`" in typ or "element\\_resultants.csv" in typ


def test_pdf_dapat_dibuat_ulang_tanpa_analisis_ulang(reported_pdf: Path):
    """`pilecap-report --pdf` harus dapat dijalankan berulang pada folder run yang sama."""
    sebelum = (reported_pdf / config.FILE_PDF_REPORT).stat().st_mtime
    _report(reported_pdf, "--pdf")
    assert (reported_pdf / config.FILE_PDF_REPORT).stat().st_mtime >= sebelum


def test_gagal_kompilasi_mempertahankan_berkas_typ(reported_pdf: Path, monkeypatch):
    """`.typ` adalah satu-satunya yang membuat kegagalan kompilasi dapat didiagnosis."""
    from shell_kit.pdf import PdfCompileError

    from pilecap_fem.reporting_pdf import document

    def gagal(typ_path, pdf_path=None, root=None):
        raise PdfCompileError(typ_path, "kesalahan buatan untuk test")

    monkeypatch.setattr(document, "compile_to_pdf", gagal, raising=False)
    monkeypatch.setattr("shell_kit.pdf.compile_to_pdf", gagal)

    with pytest.raises(PilecapError, match="DIPERTAHANKAN"):
        _report(reported_pdf, "--pdf")
    assert (reported_pdf / config.FILE_PDF_SOURCE).is_file()


def test_pilecap_run_meneruskan_flag_pdf():
    """`--pdf` didaftarkan di `add_report_arguments`, sehingga `pilecap-run` ikut menerima."""
    args = cli_pilecap_run.build_parser().parse_args([])
    assert hasattr(args, "pdf")
    assert cli_pilecap_run.build_parser().parse_args(["--pdf"]).pdf is True
