"""Test `reporting_pdf` -- primitif Typst dan konverter Markdown.

Seluruh test di sini berjalan atas STRING `.typ`, tanpa mengompilasi apa pun, kecuali
dua test kompilasi di bagian terakhir. Itu disengaja: dokumen dibangun sebagai teks,
sehingga isinya dapat diperiksa jauh lebih cepat dan lebih tajam daripada lewat PDF jadi.
"""

from __future__ import annotations

import re

import pytest

from pilecap_fem import config, reporter
from pilecap_fem.reporting_pdf import chapters
from pilecap_fem.reporting_pdf import typst_kit as tk

DEEP_RATIO = {
    "min_a_over_d": 0.754,
    "min_at": "P1 (muka pier PIER1)",
    "verdict": "TIDAK DINILAI",
}


# ---------------------------------------------------------------------------
# Escape -- teks liabilitas tidak boleh berubah makna karena markup Typst
# ---------------------------------------------------------------------------


def test_escape_menjaga_karakter_yang_bermakna_markup_typst():
    """`<`/`>` ikut di-escape karena `<nama>` adalah LABEL di Typst.

    Tanpa itu string `**<-- OVERRIDE**` pada tabel resolusi geometri akan tertelan
    seluruhnya -- baris yang justru menandai bahwa geometri tidak berasal dari config.
    """
    assert tk.esc("<-- OVERRIDE") == "\\<-- OVERRIDE"
    for ch in ("#", "$", "[", "]", "@", "*", "_", "`", "~", "\\"):
        assert tk.esc(ch) == f"\\{ch}", ch


def test_escape_menjaga_nama_kombinasi_apa_adanya():
    """Nama kombinasi datang dari CSV user; `1.2D+1.6L` tidak boleh jadi markup."""
    assert "1.2D+1.6L" in tk.esc("1.2D+1.6L")


def test_flag_baris_perintah_tidak_berubah_menjadi_en_dash():
    """`--opsvis` WAJIB tetap dua tanda hubung, bukan en dash.

    Regresi: Typst mengubah `--` menjadi en dash sebagai fitur tipografi, sehingga pesan
    log yang dikutip laporan mencetak `-opsvis`. Pembaca yang menyalin perintah itu
    mendapati perintah yang tidak berjalan. DIUKUR: backslash, string kode, maupun
    zero-width space tidak mencegahnya -- hanya raw span yang mempertahankannya.
    """
    for teks in ("Gunakan --opsvis untuk", "dipakai `--no-rebar-plots`"):
        assert "`--" in tk.esc(teks), f"flag tidak dibungkus raw span: {teks!r}"

    # Tanda hubung ganda yang BUKAN flag tetap dibiarkan menjadi en dash -- di situ
    # konversi tipografi Typst memang yang benar.
    assert "`--" not in tk.esc("nilai naik -- lalu turun")


def test_nomor_keterbatasan_tidak_hilang_sebagai_markup():
    """`#9` dan `#10` adalah rujukan antar butir, bukan pemanggilan fungsi Typst."""
    keluaran = tk.from_markdown("Lihat #9 dan #10.")
    assert "\\#9" in keluaran and "\\#10" in keluaran


# ---------------------------------------------------------------------------
# Markup inline
# ---------------------------------------------------------------------------


def test_tebal_menjadi_penekanan_berwarna_bukan_sekadar_tebal():
    """Markdown `**x**` -> `#tegas[x]` (tebal + warna), `*x*` -> `_x_` (miring).

    `#tegas` menggantikan HURUF KAPITAL di tengah kalimat sebagai penanda "penting".
    Kapital mendadak memutus alur baca pada dokumen yang ditandatangani; warna gelap
    + tebal tetap menonjol tanpa merusak tata bahasanya.
    """
    assert tk.from_markdown("**tebal**") == "#tegas[tebal]"
    assert tk.from_markdown("*miring*") == "_miring_"


def test_tebal_boleh_melintasi_pergantian_baris():
    """Regresi: Markdown membungkus paragraf secara LUNAK.

    `config.KNOWN_LIMITATIONS` butir #1 memuat `**tidak sah sebagai\\nsatu-satunya dasar
    desain**`. Versi pertama konverter ini memproses per baris, melihat `**` tanpa penutup,
    lalu menolak teks yang sebenarnya sah.
    """
    assert tk.from_markdown("awal **tebal\nlanjut** akhir") == "awal #tegas[tebal lanjut] akhir"


def test_isi_kode_tidak_ikut_di_escape():
    """Di dalam raw Typst tidak ada markup, jadi `A_pile` harus tetap utuh."""
    assert tk.from_markdown("`L*h/(2*A_pile)`") == "`L*h/(2*A_pile)`"


def test_miring_bergaris_bawah_dikenali():
    """Markdown mengizinkan `_x_` maupun `*x*`, dan proyek ini memakai KEDUANYA.

    `reporter.py` menulis `_(tidak ada lajur yang dihitung)_`, dan bab Dasar Teori
    menulis `_Sumber:_`. Versi pertama konverter ini hanya mengenal `*x*`, sehingga
    `_Sumber:_` tercetak sebagai garis bawah literal -- degradasi diam-diam, persis yang
    hendak dicegah modul ini.
    """
    assert tk.from_markdown("_Sumber:_ Timoshenko") == "_Sumber:_ Timoshenko"
    assert tk.from_markdown("_(tidak ada lajur)_") == "_(tidak ada lajur)_"


def test_pengenal_bergaris_bawah_tidak_berubah_jadi_miring():
    """Prosa proyek ini penuh `m_xx`, `A_pile`, `strips_x` DI LUAR backtick.

    Memperlakukan setiap `_` sebagai penekanan akan memiringkan potongan acak sekaligus
    menelan garis bawahnya -- nama besaran jadi salah tulis di dokumen desain.
    """
    keluaran = tk.from_markdown("medan m_xx dan A_pile serta strips_x tetap utuh")
    assert "m\\_xx" in keluaran
    assert "A\\_pile" in keluaran
    assert "strips\\_x" in keluaran


def test_markup_inline_yang_tidak_ditutup_ditolak():
    with pytest.raises(tk.TypstMarkupError, match="tidak ditutup"):
        tk.from_markdown("**tebal tanpa penutup")


# ---------------------------------------------------------------------------
# Konverter galak -- konstruksi asing RAISE, tidak dijatuhkan diam-diam
# ---------------------------------------------------------------------------


def test_konversi_markdown_menolak_heading():
    """Heading liar merusak penomoran bab; strukturnya milik `document.py`."""
    with pytest.raises(tk.TypstMarkupError, match="heading"):
        tk.from_markdown("## Bagian baru")


def test_konversi_markdown_menolak_blok_kode_berpagar():
    with pytest.raises(tk.TypstMarkupError, match="berpagar"):
        tk.from_markdown("```\nkode\n```")


def test_konversi_markdown_menolak_admonition_tak_dikenal():
    with pytest.raises(tk.TypstMarkupError, match="admonition"):
        tk.from_markdown("> [!MISTERI]\n> isi")


def test_baris_tabel_tanpa_pemisah_ditolak():
    """Tabel tanpa `|---|` adalah tabel cacat, bukan paragraf biasa."""
    with pytest.raises(tk.TypstMarkupError, match="pemisah"):
        tk.from_markdown("| a | b |\n| 1 | 2 |")


# ---------------------------------------------------------------------------
# Tabel
# ---------------------------------------------------------------------------


def test_perataan_kolom_mengikuti_penanda_titik_dua():
    md = "| a | b | c |\n|---|---:|:---:|\n| 1 | 2 | 3 |"
    assert "align: (left, right, center)" in tk.from_markdown(md)


def test_tabel_menolak_baris_yang_jumlah_selnya_berbeda():
    """Kolom yang tidak konsisten adalah cacat data, bukan hal yang boleh dirapikan."""
    with pytest.raises(tk.TypstMarkupError, match="sel"):
        tk.table(["a", "b"], [["1"]])


def test_konversi_markdown_mempertahankan_tabel_bersarang_di_butir_daftar():
    """Konstruksi tersulit di seluruh proyek: `KNOWN_LIMITATIONS` butir #10.

    Tabel `D/h` ter-indentasi DI DALAM butir daftar bernomor. Bila dedent-nya salah,
    tabel itu terbaca sebagai teks biasa dan angka pengukurannya kehilangan bentuknya.
    """
    keluaran = tk.from_markdown(config.KNOWN_LIMITATIONS)
    assert "#table(" in keluaran, "tabel D/h tidak terbentuk"
    assert "align: (left, right, right, right)" in keluaran
    # Kolom angka harus utuh, termasuk baris rumus analitis.
    assert "[7,2147%]" in keluaran and "[92,79%]" in keluaran


# ---------------------------------------------------------------------------
# Rujukan silang yang dapat diklik
# ---------------------------------------------------------------------------


def test_heading_berlabel_menjadi_sasaran_rujukan():
    assert tk.heading(1, "Dasar teori", label="bab-teori") == "= Dasar teori <bab-teori>"
    assert tk.ref("bab-teori", "Dasar teori") == "#link(<bab-teori>)[Dasar teori]"


def test_rujukan_markdown_menjadi_tautan_yang_dapat_diklik():
    """`[teks](#label)` -> `#link(<label>)[teks]`.

    Regresi: rujukan semula dibangun dengan memanggil `ref()` lalu menyambungnya ke teks
    yang masih akan melewati `from_markdown`. Konverter meng-escape `#`, `<`, dan `[`,
    sehingga tautannya tercetak sebagai teks mentah `\\#link(\\<bab-teori\\>)[...]` --
    tidak dapat diklik dan merusak kalimatnya.
    """
    keluaran = tk.from_markdown("Lihat bab [Dasar teori](#bab-teori) untuk rinciannya.")
    assert "#link(<bab-teori>)[Dasar teori]" in keluaran
    assert "\\#link" not in keluaran

    # Kurung siku biasa TIDAK boleh ikut tertangkap sebagai tautan.
    assert "\\[" in tk.from_markdown("nilai [lihat catatan] berikut")


def test_label_tidak_sah_ditolak():
    """Label cacat menghasilkan `.typ` yang gagal kompilasi jauh dari sumbernya."""
    for buruk in ("Bab Teori", "bab teori", "-awal", ""):
        with pytest.raises(tk.TypstMarkupError):
            tk.heading(1, "x", label=buruk)


# ---------------------------------------------------------------------------
# Blok prosa tetap -- WAJIB direproduksi lengkap (PRD Bagian 1.3 poin 5)
# ---------------------------------------------------------------------------


def test_known_limitations_muncul_lengkap_sepuluh_butir():
    keluaran = tk.from_markdown(config.KNOWN_LIMITATIONS)
    assert "#enum(" in keluaran and "start: 1" in keluaran
    # Sepuluh butir -> sepuluh argumen konten pada satu enum terluar.
    assert keluaran.count("\n  [\n") == 10, "jumlah butir keterbatasan berubah"


def test_disclaimer_bertanda_draft_selama_flag_draft_aktif():
    """Penanda DRAFT hilang dari PDF = klaim yang lebih kuat daripada yang disetujui."""
    keluaran = tk.from_markdown(reporter.disclaimer_block())
    if config.DISCLAIMER_IS_DRAFT:
        assert "DRAFT" in keluaran
    assert "ALAT BANTU" in keluaran


def test_peringatan_deep_pilecap_menjadi_kotak_peringatan():
    """Admonition `> [!WARNING]` harus jadi kotak, bukan kutipan biasa yang terlewat."""
    keluaran = tk.from_markdown(reporter.deep_pilecap_warning(DEEP_RATIO))
    assert "#kotak(" in keluaran
    # Kalimat pembatal keabsahan WAJIB tetap ada, dan tetap ditandai sebagai penting --
    # sekarang lewat `#tegas` (tebal + warna), bukan huruf kapital.
    assert "#tegas[tidak sah sebagai dasar desain]" in keluaran
    assert "0.754" in keluaran


def test_open_blockers_direproduksi_beserta_seluruh_itemnya():
    keluaran = tk.from_markdown(reporter.open_blockers_block())
    for key in config.OPEN_BLOCKERS:
        assert f"\\{key}" in keluaran, f"blocker {key} hilang dari dokumen"


_EQUILIBRIUM_DENGAN_OVERLAP = {
    "pile_loads": [
        {
            "pile_id": "P1",
            "A_lens_m2": 0.05,
            "overlap_fraction": 0.15,
            "pz_strut_N": 15_000.0,
            "pz_bocor_mesh_N": 500.0,
            "pz_ke_pelat_N": 84_500.0,
            "Pz_N": 100_000.0,
        }
    ]
}


def test_overlap_block_meledak_lewat_md_biasa_tetapi_aman_lewat_md_body():
    """Regresi: `overlap_block` MEMBAWA heading `### 3a.` sendiri, sama seperti
    `stirrup_section`. Rute `_md()` (dipakai chapters.py sebelum perbaikan) menolaknya --
    tepat kegagalan yang dilaporkan user pada run dengan tumpang tindih pile-pier (`ex04`).
    `_md_body()` (rute yang benar) membuang heading itu tanpa RAISE.
    """
    blok = reporter.overlap_block(_EQUILIBRIUM_DENGAN_OVERLAP)
    assert blok.strip(), "fixture ini seharusnya menghasilkan blok non-kosong"

    with pytest.raises(tk.TypstMarkupError, match="heading Markdown"):
        tk.from_markdown(blok)

    keluaran = chapters._md_body(blok)
    assert "### 3a" not in keluaran
    assert "strut" in keluaran


# ---------------------------------------------------------------------------
# Gambar
# ---------------------------------------------------------------------------


def test_jalur_gambar_ditulis_dengan_pemisah_posix():
    """Typst hanya menerima `/`. Backslash Windows hanya gagal di mesin pengguna."""
    with pytest.raises(tk.TypstMarkupError, match="Windows"):
        tk.figure("Combo_1\\contour_mx.png", "Momen m_x")


def test_gambar_membawa_caption():
    keluaran = tk.figure("Combo_1/contour_mx.png", "Momen m_x -- kombinasi 1.2D+1.6L")
    assert 'image("Combo_1/contour_mx.png"' in keluaran
    assert "caption:" in keluaran


# ---------------------------------------------------------------------------
# Kompilasi sungguhan -- penjaga terakhir bahwa yang dihasilkan memang sah
# ---------------------------------------------------------------------------


def _compile(source: str, tmp_path):
    import typst

    typ = tmp_path / "uji.typ"
    typ.write_text(source, encoding="utf-8")
    pdf, warnings = typst.compile_with_warnings(str(typ), root=str(tmp_path))
    if isinstance(pdf, list):
        pdf = pdf[0]
    return pdf, [str(w) for w in (warnings or [])]


def test_seluruh_blok_prosa_tetap_benar_benar_dapat_dikompilasi(tmp_path):
    """Konversi yang lolos tetapi tidak dapat dikompilasi tetap kegagalan.

    Menyertakan `KNOWN_LIMITATIONS` -- blok terpanjang dan satu-satunya yang memuat tabel
    bersarang di dalam daftar.
    """
    bagian = [
        tk.PREAMBLE,
        tk.from_markdown(config.KNOWN_LIMITATIONS),
        tk.from_markdown(reporter.disclaimer_block()),
        tk.from_markdown(reporter.open_blockers_block()),
        tk.from_markdown(reporter.deep_pilecap_warning(DEEP_RATIO)),
    ]
    pdf, warnings = _compile("\n\n".join(bagian), tmp_path)
    assert pdf.startswith(b"%PDF-")
    assert not warnings, f"kompilasi memunculkan warning: {warnings}"


def test_kompilasi_tidak_memakai_font_sistem(tmp_path):
    """Dokumen harus tampil sama di mesin lain.

    typst hanya membundel New Computer Modern, Libertinus Serif, dan DejaVu Sans Mono.
    Font sistem (Arial/Segoe UI di Windows) ikut ter-resolve secara diam-diam, sehingga
    dokumen yang memakainya akan berbeda di mesin tanpa font itu. DIUKUR: keluaran dengan
    dan tanpa font sistem harus IDENTIK byte demi byte.
    """
    import typst

    typ = tmp_path / "font.typ"
    typ.write_text(tk.PREAMBLE + "\nHalo pilecap 123\n", encoding="utf-8")
    dengan, _ = typst.compile_with_warnings(str(typ), root=str(tmp_path))
    tanpa, _ = typst.compile_with_warnings(str(typ), root=str(tmp_path), ignore_system_fonts=True)
    if isinstance(dengan, list):
        dengan, tanpa = dengan[0], tanpa[0]
    assert dengan == tanpa, "dokumen bergantung pada font sistem"


def test_sumber_reporting_pdf_tidak_mengetik_satuan_sebagai_literal():
    """Satuan WAJIB datang dari `io_utils.display_unit` (PRD Bagian 9.2).

    Satuan yang diketik langsung akan menyimpang diam-diam begitu `config.DISPLAY_UNITS`
    berubah -- dan tabel PDF akan menyatakan satuan yang berbeda dari calc sheet.
    """
    from pathlib import Path

    import pilecap_fem.reporting_pdf as paket

    dilarang = ("kNm/m", "mm^2/m", "mm^2/mm", "kN/m", "kPa", "MPa")
    for berkas in Path(paket.__file__).parent.glob("*.py"):
        teks = berkas.read_text(encoding="utf-8")
        # Docstring dan komentar boleh menyebut satuan; yang dilarang adalah literal
        # string yang benar-benar masuk ke dokumen.
        kode = "\n".join(baris for baris in teks.splitlines() if not baris.lstrip().startswith("#"))
        for satuan in dilarang:
            assert f'"{satuan}"' not in kode, (
                f"{berkas.name} mengetik satuan {satuan!r} sebagai literal; "
                "pakai io_utils.display_unit()."
            )


def test_reporting_pdf_tidak_perlu_pengecualian_e501():
    """Paket ini dibangun per baris, bukan satu f-string raksasa seperti `reporter.py`.

    Begitu ia butuh pengecualian E501, itu tanda blok teksnya sudah kembali menjadi
    f-string panjang yang tidak dapat dipotong -- kelemahan yang sengaja tidak diulang.
    """
    from pathlib import Path

    teks = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    blok = re.search(r"\[tool\.ruff\.lint\.per-file-ignores\](.*?)(\n\[|\Z)", teks, re.S)
    if blok:
        assert "reporting_pdf" not in blok.group(1)


# ---------------------------------------------------------------------------
# Gambar -- penemuan, downscale, dan penandaan
# ---------------------------------------------------------------------------


def _png(path, size):
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (200, 40, 40)).save(path)
    return path


def _store(run_dir, *, started_at=0.0):
    from pilecap_fem.reporting_pdf.figures import FigureStore

    return FigureStore(run_dir, started_at=started_at)


def test_gambar_yang_tidak_ada_muncul_sebagai_kotak_penjelasan_bukan_dihilangkan(tmp_path):
    """Ruang kosong terbaca sebagai "tidak ada apa-apa", padahal artinya "tidak diperiksa"."""
    toko = _store(tmp_path)
    fig = toko.resolve(
        tmp_path / "Combo_1" / "contour_As_x_bawah.png",
        "As perlu arah X",
        reason="dibuat hanya bila `--no-rebar-plots` tidak dipakai.",
    )
    keluaran = fig.to_typst()
    assert "GAMBAR TIDAK TERSEDIA" in keluaran
    assert "no-rebar-plots" in keluaran
    assert len(toko.missing) == 1


def test_jalur_gambar_relatif_terhadap_folder_run_dan_bergaya_posix(tmp_path):
    """Typst membaca relatif terhadap `root`, dan menolak pemisah bergaya Windows."""
    _png(tmp_path / "Combo_1" / "contour_mx.png", (80, 60))
    fig = _store(tmp_path).resolve(tmp_path / "Combo_1" / "contour_mx.png", "Momen m_x", reason="-")
    assert fig.rel_path == "Combo_1/contour_mx.png"
    assert "\\" not in fig.rel_path


def test_gambar_besar_diperkecil_ke_folder_cetak(tmp_path):
    """Plot 300 dpi ~4.150 px membengkakkan PDF tanpa menambah ketajaman yang terlihat."""
    from PIL import Image

    _png(tmp_path / "Combo_1" / "besar.png", (3000, 2000))
    fig = _store(tmp_path).resolve(tmp_path / "Combo_1" / "besar.png", "Besar", reason="-")
    assert fig.rel_path.startswith("_figur_pdf/")
    with Image.open(tmp_path / fig.rel_path) as im:
        assert max(im.size) <= config.PDF_IMAGE_MAX_PX
    # Aslinya TIDAK boleh ikut berubah.
    with Image.open(tmp_path / "Combo_1" / "besar.png") as asli:
        assert asli.size == (3000, 2000)


def test_gambar_yang_sudah_kecil_dipakai_apa_adanya(tmp_path):
    """Menyalin gambar yang sudah kecil hanya menggandakan berkas tanpa manfaat."""
    _png(tmp_path / "Combo_1" / "kecil.png", (400, 300))
    fig = _store(tmp_path).resolve(tmp_path / "Combo_1" / "kecil.png", "Kecil", reason="-")
    assert fig.rel_path == "Combo_1/kecil.png"


def test_gambar_lebih_tua_dari_run_ini_ditandai_di_caption(tmp_path):
    """`pilecap-report` dirancang untuk dijalankan ulang.

    PNG dari pelaporan sebelumnya masih ada di disk dan akan ikut tertanam -- mungkin
    dengan tema atau DPI yang berbeda. Membiarkannya tanpa tanda berarti dokumen memuat
    gambar dari run lain tanpa satu pun petunjuk.
    """
    p = _png(tmp_path / "Combo_1" / "lama.png", (100, 80))
    import os

    os.utime(p, (1_000_000, 1_000_000))
    toko = _store(tmp_path, started_at=2_000_000.0)
    fig = toko.resolve(p, "Momen m_x", reason="-")
    assert fig.stale is True
    assert "pelaporan sebelumnya" in fig.to_typst()
    assert toko.stale == ["lama.png"]


def test_ilustrasi_svg_disalin_ke_folder_run_tanpa_diperkecil(tmp_path):
    """`illustrations_dir()` ada di LUAR root kompilasi, jadi harus disalin masuk.

    SVG juga tidak diperkecil: memperkecil vektor tidak menghemat apa pun.
    """
    toko = _store(tmp_path)
    fig = toko.illustration("sistem-koordinat.svg", "Sistem koordinat")
    assert fig.rel_path == "_figur_pdf/sistem-koordinat.svg"
    assert (tmp_path / fig.rel_path).is_file()
    assert not toko.missing
