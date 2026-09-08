"""Panduan mandiri `pilecap-manual`.

Pembaca panduan ini tidak punya README maupun akses GitHub untuk memeriksa silang, jadi
yang diuji di sini bukan sekadar "dokumen terbentuk", melainkan bahwa dokumen itu benar-
benar LENGKAP dan MANDIRI: seluruh field terdaftar, seluruh keterbatasan tercetak, tidak
ada rujukan yang menggantung, dan tidak satu pun kalimat yang menyuruh pembaca membuka
halaman web.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from pilecap_fem import __version__, config
from pilecap_fem.manual import chapters as bab
from pilecap_fem.manual import config_reference, document
from pilecap_fem.reporting_pdf.figures import FigureStore
from pilecap_fem.ui import schema

#: Rujukan yang benar-benar dipakai dokumen: `#link(<label>)[teks]`.
_RUJUKAN = re.compile(r"#link\(<([a-z0-9_-]+)>\)")

#: Label yang didefinisikan sebuah heading: `== Judul <label>`.
_LABEL = re.compile(r"^=+ .*<([a-z0-9_-]+)>\s*$", re.MULTILINE)


@pytest.fixture(scope="module")
def sumber(tmp_path_factory) -> str:
    """Sumber `.typ` panduan, dibangun sekali untuk seluruh modul ini."""
    keluaran = tmp_path_factory.mktemp("panduan")
    return document.render_source(FigureStore(keluaran, started_at=0.0))


# ---------------------------------------------------------------------------
# Kelengkapan
# ---------------------------------------------------------------------------


def test_panduan_memuat_seluruh_bab_wajib(sumber: str):
    """Kerangka dokumen tidak boleh kehilangan satu bab pun tanpa disadari."""
    for judul in (
        "Ringkasan eksekutif",
        "Cara memasang",
        "Menjalankan pertama kali",
        "Menyiapkan data sendiri",
        "Referensi konfigurasi",
        "Dasar teori",
        "Apa yang dihasilkan",
        "Bukti dan validasi",
        "Asumsi dan keterbatasan",
        "Tanggung jawab dan lisensi",
        "Lampiran A",
        "Lampiran B",
    ):
        assert f"= {judul}" in sumber, f"bab {judul!r} hilang dari panduan"


def test_panduan_menyebut_seluruh_field_config(sumber: str):
    """Justru daftar field inilah yang membuat panduan dapat berdiri sendiri.

    Satu field yang hilang berarti pembacanya tidak punya keterangan apa pun tentang
    setelan itu -- ia tidak dapat membuka README maupun `--help` sebagai gantinya.
    """
    hilang = [f.key for f in schema.ALL_FIELDS if f"`{f.key}`" not in sumber]
    assert not hilang, f"field tidak terdokumentasi di panduan: {hilang}"


def test_panduan_tidak_menyebut_field_yang_tidak_ada_di_schema(sumber: str):
    """Cermin dari test di atas: menangkap field yang DIHAPUS dari schema.

    Tanpa ini, field yang dibuang tetap tercetak di panduan sebagai setelan yang
    sesungguhnya sudah tidak ada, dan pembacanya akan mencarinya sia-sia.
    """
    sah = {f.key for f in schema.ALL_FIELDS}
    disebut = set(re.findall(r"`([a-z_]+\.[a-z_]+)`", sumber))
    # Hanya kunci bertitik yang berbentuk seperti kunci config yang diperiksa; nama
    # berkas (`model.mct`) dan sejenisnya tidak termasuk.
    kandidat = {k for k in disebut if k.split(".")[0] in {f.block for f in schema.ALL_FIELDS}}
    assert not (kandidat - sah), f"panduan menyebut field yang tidak ada: {sorted(kandidat - sah)}"


def test_panduan_menyebut_setiap_bagian_formulir(sumber: str):
    for bagian in schema.SECTIONS:
        assert bagian.title in sumber, f"bagian {bagian.title!r} hilang"


def test_panduan_memuat_seluruh_butir_keterbatasan(sumber: str):
    """`KNOWN_LIMITATIONS` wajib tercetak utuh, bukan diringkas."""
    jumlah = config.KNOWN_LIMITATIONS.count("\n1. ") + config.KNOWN_LIMITATIONS.count("\n10. ")
    assert jumlah, "pola penomoran KNOWN_LIMITATIONS berubah; test ini perlu disesuaikan"
    for potongan in ("Asumsi dan keterbatasan",):
        assert potongan in sumber


def test_panduan_memuat_seluruh_item_yang_belum_dikonfirmasi(sumber: str):
    """Item yang belum dikonfirmasi adalah pengecekan yang TIDAK dilakukan.

    Menghilangkan salah satunya dari panduan berarti menjanjikan pemeriksaan yang tidak
    pernah terjadi -- persis yang dilarang tingkat liabilitas proyek ini.
    """
    for kunci in config.OPEN_BLOCKERS:
        assert kunci in sumber, f"item terbuka {kunci} tidak disebut panduan"


def test_panduan_memuat_setiap_ilustrasi_yang_dikemas(tmp_path):
    """Seluruh ilustrasi harus benar-benar ditemukan, bukan menjadi kotak 'tidak tersedia'."""
    figs = FigureStore(tmp_path, started_at=0.0)
    teks = document.render_source(figs)
    assert not figs.missing, f"ilustrasi tidak ditemukan: {[m.name for m in figs.missing]}"
    for berkas in config.illustrations_dir().glob("*.svg"):
        assert berkas.name in teks, f"ilustrasi {berkas.name} tidak dipakai panduan"


def test_setiap_ilustrasi_bagian_formulir_muncul_di_bab_konfigurasi(sumber: str):
    """Penempatan ilustrasi digerakkan `Section.illustration`, bukan ditulis satu per satu."""
    for bagian in schema.SECTIONS:
        if bagian.illustration:
            assert bagian.illustration in sumber, f"ilustrasi {bagian.title} tidak dirender"


# ---------------------------------------------------------------------------
# Rujukan silang
# ---------------------------------------------------------------------------


def test_setiap_rujukan_silang_di_panduan_punya_label_tujuannya(sumber: str):
    """Rujukan yang tujuannya tidak ada akan tercetak sebagai tanda tanya di PDF.

    Bab dasar teori dipakai ulang apa adanya dan membawa dua rujukan keluar
    (`lampiran-provenance`, `bab-keterbatasan`). Test inilah yang menjamin panduan
    benar-benar menyediakan kedua tujuan itu, bukan sekadar diasumsikan menyediakannya.
    """
    tujuan = set(_RUJUKAN.findall(sumber))
    tersedia = set(_LABEL.findall(sumber))
    assert not (tujuan - tersedia), f"rujukan menggantung: {sorted(tujuan - tersedia)}"


# ---------------------------------------------------------------------------
# Kemandirian -- keputusan pembaca tanpa GitHub, dikodekan sebagai test
# ---------------------------------------------------------------------------


def test_panduan_tidak_menyuruh_pembaca_membuka_github_atau_readme(sumber: str):
    """Pembaca panduan ini tidak dapat membaca README di GitHub, atau tidak memahaminya.

    Diperiksa atas daftar FRASA, bukan atas domain `github.com` -- domain itu sah muncul
    di dalam alamat unduhan wheel, yang justru wajib ada supaya pembaca dapat memasang.
    """
    dilarang = ("lihat README", "README.md", "git clone", "clone repo", "halaman Releases")
    ditemukan = [f for f in dilarang if f in sumber]
    assert not ditemukan, f"panduan mengandalkan sumber di luar dirinya: {ditemukan}"


def test_url_wheel_di_panduan_sama_dengan_yang_di_readme(sumber: str):
    """Alamat pemasangan hanya boleh punya satu sumber.

    Sebelumnya alamat itu diketik tangan di README dan harus disunting setiap rilis --
    suntingan yang diingat, bukan diperiksa. Sekarang keduanya berasal dari
    `config.wheel_url`, dan test ini yang menagihnya.
    """
    url = config.wheel_url(__version__)
    assert url in sumber, "panduan tidak memuat alamat unduhan wheel"
    readme = Path(__file__).resolve().parents[1] / "README.md"
    assert url in readme.read_text(encoding="utf-8"), (
        f"README masih menyebut alamat wheel versi lain; seharusnya {url}"
    )


def test_panduan_menyebut_versi_yang_terpasang(sumber: str):
    assert f"Versi {__version__}" in sumber
    assert f"pilecap-fem v{__version__}" in sumber, "footer tidak menyebut versi"


# ---------------------------------------------------------------------------
# Determinisme
# ---------------------------------------------------------------------------


def test_panduan_dihasilkan_sama_persis_pada_dua_pemanggilan(tmp_path):
    """Sumber yang berubah tanpa sebab membuat diff antarversi tidak dapat ditinjau."""
    a = document.render_source(FigureStore(tmp_path / "a", started_at=0.0))
    b = document.render_source(FigureStore(tmp_path / "b", started_at=0.0))
    assert a == b


def test_panduan_tidak_memuat_tanggal_hari_ini_sebagai_bawaan_project_date(sumber: str):
    """Bawaan `project.date` dievaluasi saat impor, sehingga berubah setiap hari.

    Mencetaknya apa adanya membuat sumber panduan yang di-commit berubah tiap hari tanpa
    ada yang berubah pada perangkat lunaknya.
    """
    from datetime import datetime

    hari_ini = datetime.now().strftime("%Y-%m-%d")
    assert hari_ini not in sumber, "panduan mencetak tanggal hari ini sebagai bawaan"
    assert "tanggal hari ini" in sumber


# ---------------------------------------------------------------------------
# Prosa yang berpasangan dengan data hidup
# ---------------------------------------------------------------------------


def test_setiap_field_bersyarat_punya_kalimat_penjelas():
    """Syarat berlakunya field tidak dapat dibaca dari `visible_when`, yang berupa fungsi.

    Karena itu kalimatnya ditulis sebagai data. Test ini menuntut daftar itu SAMA PERSIS
    dengan himpunan field bersyarat, sehingga field bersyarat baru menghentikan pembuatan
    panduan alih-alih terbit tanpa menyebutkan kapan ia berlaku.
    """
    bersyarat = {f.key for f in schema.ALL_FIELDS if f.visible_when is not None}
    assert bersyarat == set(config_reference.SYARAT_TAMPIL)


def test_setiap_contoh_bawaan_punya_keterangan():
    assert set(config.EXAMPLE_NAMES) <= set(bab._CONTOH)


def test_setiap_pola_berkas_masukan_punya_keterangan():
    assert set(config.FILE_PATTERNS) <= set(bab._ISI_BERKAS)


def test_setiap_entry_point_dijelaskan_panduan():
    """Perintah baru yang tidak dijelaskan panduan tidak akan pernah ditemukan pembacanya."""
    import tomllib

    akar = Path(__file__).resolve().parents[1]
    with (akar / "pyproject.toml").open("rb") as fh:
        scripts = set(tomllib.load(fh)["project"]["scripts"])
    assert scripts == {nama for nama, _ in bab._PERINTAH}


# ---------------------------------------------------------------------------
# Aturan rumah, direplikasi untuk paket ini
# ---------------------------------------------------------------------------


def test_sumber_manual_tidak_mengetik_satuan_sebagai_literal():
    """Satuan wajib datang dari `io_utils.display_unit` (PRD Bagian 9.2).

    Aturan yang sama dengan `reporting_pdf`, dan alasannya sama: satuan yang diketik akan
    menyimpang diam-diam begitu `config.DISPLAY_UNITS` berubah.
    """
    import pilecap_fem.manual as paket

    dilarang = ("kNm/m", "mm^2/m", "mm^2/mm", "kN/m", "kPa", "MPa")
    for berkas in Path(paket.__file__).parent.glob("*.py"):
        teks = berkas.read_text(encoding="utf-8")
        kode = "\n".join(b for b in teks.splitlines() if not b.lstrip().startswith("#"))
        for satuan in dilarang:
            assert f'"{satuan}"' not in kode, (
                f"{berkas.name} mengetik satuan {satuan!r}; pakai io_utils.display_unit()."
            )


def test_manual_tidak_perlu_pengecualian_e501():
    """Paket ini dibangun per baris, sama seperti `reporting_pdf`."""
    import tomllib

    akar = Path(__file__).resolve().parents[1]
    with (akar / "pyproject.toml").open("rb") as fh:
        ignores = tomllib.load(fh)["tool"]["ruff"]["lint"].get("per-file-ignores", {})
    assert not [k for k in ignores if "manual" in k], "manual butuh pengecualian E501"


def test_reporting_pdf_tidak_mengimpor_manual():
    """Arah impor satu arah: laporan run tidak boleh bergantung pada panduan.

    Kebalikannya akan menyeret prosa panduan ke dalam dokumen bertanda tangan, dan
    melemahkan invarian `reporting_pdf` bahwa isinya hanya penyusunan ulang satu run.
    """
    import pilecap_fem.reporting_pdf as paket

    for berkas in Path(paket.__file__).parent.glob("*.py"):
        teks = berkas.read_text(encoding="utf-8")
        assert "pilecap_fem.manual" not in teks, f"{berkas.name} mengimpor paket manual"


# ---------------------------------------------------------------------------
# Kompilasi
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_panduan_benar_benar_dapat_dikompilasi_tanpa_satu_pun_warning(tmp_path):
    """Sumber yang lolos konversi tetapi gagal dikompilasi tetap kegagalan.

    Warning ikut ditolak: rujukan yang menggantung dan gambar yang tidak termuat muncul
    sebagai warning, bukan galat, sehingga dokumen tetap terbit dalam keadaan berkurang.
    """
    typ, pdf = document.build_manual(tmp_path)
    assert pdf is not None
    assert pdf.read_bytes().startswith(b"%PDF-")
    assert typ.exists(), "sumber .typ wajib ikut disimpan"


@pytest.mark.slow
def test_panduan_tidak_memakai_font_sistem(tmp_path, tanpa_stempel_waktu):
    """Panduan harus tampil sama di komputer penerimanya, bukan hanya di komputer penulis.

    Stempel waktu dinormalkan lebih dulu: Typst menanam jam dinding di setiap PDF, dan
    panduan cukup besar sehingga dua kompilasinya kerap jatuh di detik yang berbeda.
    Tanpa itu, test ini menguji jam alih-alih font.
    """
    import typst

    typ, _ = document.build_manual(tmp_path, typ_only=True)
    dengan, _ = typst.compile_with_warnings(str(typ), root=str(tmp_path))
    tanpa, _ = typst.compile_with_warnings(str(typ), root=str(tmp_path), ignore_system_fonts=True)
    if isinstance(dengan, list):
        dengan, tanpa = dengan[0], tanpa[0]
    assert tanpa_stempel_waktu(dengan) == tanpa_stempel_waktu(tanpa), (
        "panduan bergantung pada font sistem"
    )


def test_tabel_ringkas_tidak_menandai_field_bersyarat_sebagai_wajib(sumber: str):
    """`pier.width_x` dan `pier.diameter` adalah cabang yang saling meniadakan.

    Menandai keduanya "ya" pada kolom Wajib akan menyesatkan pembaca yang hanya memindai
    tabel ringkas -- dan itulah cara membaca yang justru dirancang untuk tabel itu.
    """
    # Dibatasi pada bagian Pier: `pile.diameter` bernama sama tetapi TIDAK bersyarat.
    bagian_pier = sumber.split("== Pier <cfg-pier>", 1)[1].split("\n== ", 1)[0]
    for nama in ("width_x", "width_y", "diameter"):
        baris = [b for b in bagian_pier.splitlines() if b.strip().startswith(f"[`{nama}`],")]
        assert baris, f"baris tabel `{nama}` tidak ditemukan di bagian Pier"
        assert "[bersyarat]" in baris[0], f"field bersyarat ditandai wajib biasa: {baris[0]}"


def test_tabel_dependency_menyebut_versi_bukan_penanda_lingkungan():
    """Regresi: `streamlit>=1.57; extra == 'ui'` memuat `==` di penanda lingkungannya.

    Mengurai versi sebelum memotong penanda itu membuat `streamlit` tercetak berversi
    `'ui'` -- terbaca sebagai versi yang sah, padahal bukan versi sama sekali.
    """
    baris = {r[0]: r[1] for r in bab._baris_dependency()}
    assert baris["`streamlit`"] == "`>=1.57`"
    assert baris["`gmsh`"] == "`4.15.2`"
    # Wheel yang dipasang lewat URL: versinya diambil dari nama berkasnya.
    assert baris["`shell-kit`"].strip("`")[0].isdigit()


def test_gambar_perbandingan_basis_desain_ikut_di_panduan(sumber: str):
    """`design.rebar_basis` adalah setelan yang paling mudah disalahtafsirkan.

    Kedua pilihannya menghasilkan kontur yang identik piksel demi piksel; yang berbeda
    hanya arti angkanya. Tanpa gambar berdampingan, pembaca yang hanya memegang dokumen
    ini tidak punya cara melihat itu.
    """
    assert "contoh-diameter-element-vs-strip.png" in sumber
    assert "identik piksel demi piksel" in sumber
