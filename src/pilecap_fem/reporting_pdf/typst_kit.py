"""Primitif Typst: escape, tabel, heading, gambar, callout, persamaan, dan konverter
Markdown terbatas.

.. rubric:: Mengapa ada konverter Markdown di sini

Beberapa blok prosa proyek ini WAJIB tampil apa adanya di setiap laporan
(`config.KNOWN_LIMITATIONS`, disclaimer, `OPEN_BLOCKERS`, peringatan deep pilecap).
Blok-blok itu sudah ditulis sebagai Markdown dan sudah dipakai `reporter.py`. Menyalinnya
ke bentuk Typst berarti dua salinan teks liabilitas yang dapat menyimpang diam-diam --
persis yang dilarang PRD Bagian 1.3 poin 5. Karena itu `from_markdown` menerjemahkannya
saat pembuatan dokumen, sehingga sumbernya tetap satu.

Konverter ini **sempit dan galak**: ia menerima persis konstruksi yang benar-benar dipakai
blok-blok tersebut, dan **RAISE** pada konstruksi yang tidak dikenal. Ia sengaja BUKAN
konverter Markdown umum -- menjatuhkan konstruksi asing diam-diam akan menghilangkan
kalimat peringatan dari dokumen tercetak tanpa satu pun tanda.
"""

from __future__ import annotations

import re
from typing import Any, Final

__all__ = [
    "PREAMBLE",
    "TypstMarkupError",
    "callout",
    "equation",
    "esc",
    "figure",
    "from_markdown",
    "heading",
    "pagebreak",
    "table",
]


class TypstMarkupError(ValueError):
    """Konstruksi Markdown yang tidak dikenal konverter, atau markup yang cacat."""


# ---------------------------------------------------------------------------
# Preamble
# ---------------------------------------------------------------------------
#
# Font: hanya TIGA keluarga yang benar-benar dibundel typst 0.15 -- New Computer Modern,
# Libertinus Serif, dan DejaVu Sans Mono. "Arial"/"Segoe UI" memang ter-resolve di Windows,
# tetapi itu font SISTEM: dokumen yang sama akan tampil berbeda di mesin lain. DIUKUR:
# kompilasi dengan `ignore_system_fonts=True` menghasilkan berkas yang IDENTIK byte demi
# byte, yang membuktikan dokumen ini tidak menyentuh font sistem sama sekali.

PREAMBLE: Final[str] = """\
// Dihasilkan oleh pilecap-fem. JANGAN diedit tangan -- berkas ini ditimpa setiap
// `pilecap-report --pdf` dijalankan. Sumber angkanya ada di calc_sheet.md dan CSV.

#set page(paper: "a4", margin: (x: 2cm, y: 2.4cm))
#set text(font: "New Computer Modern", size: 10pt, lang: "id")
#set par(justify: true)
#set heading(numbering: "1.1")
#show heading.where(level: 1): set text(size: 15pt)
#show heading.where(level: 2): set text(size: 12pt)
#show heading.where(level: 3): set text(size: 10.5pt)
#show link: set text(fill: rgb("#1a4b8c"))

#set table(inset: 5pt, stroke: 0.4pt + luma(170))
#show table.cell.where(y: 0): set text(weight: "bold")

#set figure(numbering: "1")
#show figure.caption: set text(size: 8.5pt)

// Kotak peringatan. `judul` dicetak tebal di baris pertama; warnanya membedakan
// tingkat: merah = peringatan yang membatalkan keabsahan angka, biru = catatan.
#let kotak(judul, warna, isi) = block(
  width: 100%,
  inset: 8pt,
  radius: 2pt,
  fill: warna.lighten(90%),
  stroke: (left: 2.5pt + warna),
  [#text(weight: "bold", fill: warna.darken(20%))[#judul] \\ #isi],
)
"""

#: Warna callout per jenis admonition GitHub.
_CALLOUT_STYLE: Final[dict[str, tuple[str, str]]] = {
    "WARNING": ("PERINGATAN", 'rgb("#b45309")'),
    "CAUTION": ("HATI-HATI", 'rgb("#b91c1c")'),
    "IMPORTANT": ("PENTING", 'rgb("#b91c1c")'),
    "NOTE": ("CATATAN", 'rgb("#1d4ed8")'),
    "TIP": ("SARAN", 'rgb("#15803d")'),
}


# ---------------------------------------------------------------------------
# Escape
# ---------------------------------------------------------------------------

#: Karakter yang bermakna markup di Typst dan karena itu wajib di-escape pada teks
#: literal. `<` dan `>` ikut karena `<nama>` adalah label di Typst -- string seperti
#: `**<-- OVERRIDE**` di tabel resolusi geometri akan tertelan tanpa ini.
_ESCAPE: Final[dict[str, str]] = {
    "\\": "\\\\",
    "#": "\\#",
    "$": "\\$",
    "[": "\\[",
    "]": "\\]",
    "<": "\\<",
    ">": "\\>",
    "@": "\\@",
    "*": "\\*",
    "_": "\\_",
    "`": "\\`",
    "~": "\\~",
}

#: Karakter yang hanya bermakna markup di AWAL baris (heading, list, term list).
_LINE_START_ESCAPE: Final[str] = "-+=/"

_ORDERED_ITEM = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")
_UNORDERED_ITEM = re.compile(r"^(\s*)[-*+]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\s*\|(?:\s*:?-{3,}:?\s*\|)+\s*$")
_LEADING_NUMBER = re.compile(r"^\d+\.")


#: Flag baris perintah di dalam teks bebas, mis. `--opsvis`, `--no-rebar-plots`.
_CLI_FLAG = re.compile(r"(?<![-\w])--[A-Za-z][\w-]*")


def esc(text: str) -> str:
    """Escape teks literal agar tampil apa adanya di Typst.

    Flag baris perintah dibungkus sebagai raw span, BUKAN sekadar di-escape. Alasannya
    korektif, bukan kosmetik: Typst mengubah `--` menjadi en dash sebagai fitur tipografi,
    sehingga `--opsvis` tercetak sebagai `-opsvis` -- perintah yang TIDAK berjalan bila
    disalin pembaca. DIUKUR: `\\-\\-`, `-\\-`, string kode `#"--"`, maupun sisipan
    zero-width space semuanya tetap dikonversi; hanya raw span yang mempertahankannya.

    Tanda `--` lain dalam prosa sengaja dibiarkan menjadi en dash, karena di situ memang
    itu yang benar secara tipografi.
    """
    keluaran: list[str] = []
    posisi = 0
    for m in _CLI_FLAG.finditer(str(text)):
        keluaran.append("".join(_ESCAPE.get(c, c) for c in text[posisi : m.start()]))
        keluaran.append(f"`{m.group(0)}`")
        posisi = m.end()
    keluaran.append("".join(_ESCAPE.get(c, c) for c in str(text)[posisi:]))
    return "".join(keluaran)


def _escape_line_start(line: str) -> str:
    """Lindungi karakter yang hanya bermakna markup di awal baris."""
    stripped = line.lstrip()
    if not stripped:
        return line
    pad = line[: len(line) - len(stripped)]
    if stripped[0] in _LINE_START_ESCAPE or _LEADING_NUMBER.match(stripped):
        return f"{pad}\\{stripped}"
    return line


# ---------------------------------------------------------------------------
# Inline markup
# ---------------------------------------------------------------------------


def _underscore_emphasis(text: str, start: int) -> int | None:
    r"""Indeks `_` penutup bila `_..._` di posisi `start` memang penekanan Markdown.

    Aturan batas kata WAJIB, bukan kehalusan: prosa proyek ini penuh pengenal ber-underscore
    di luar backtick (`m_xx`, `A_pile`, `strips_x`, `mesh.size_*`). Memperlakukan setiap `_`
    sebagai penekanan akan memiringkan potongan acak dan menelan underscore-nya.

    Karena itu `_` hanya membuka penekanan bila karakter sebelumnya bukan alfanumerik, dan
    hanya menutup bila karakter sesudahnya bukan alfanumerik.
    """
    if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
        return None
    if start + 1 >= len(text) or text[start + 1].isspace():
        return None
    i = start + 1
    while (i := text.find("_", i)) != -1:
        sesudah = text[i + 1] if i + 1 < len(text) else " "
        if not sesudah.isalnum() and not text[i - 1].isspace():
            return i
        i += 1
    return None


def _inline(text: str) -> str:
    """Terjemahkan markup inline Markdown -> Typst.

    Pemetaan yang mudah tertukar: Markdown `**tebal**` menjadi Typst `*tebal*`, sedangkan
    Markdown `*miring*` menjadi Typst `_miring_`. Isi `` `kode` `` diserahkan apa adanya --
    di dalam raw Typst tidak ada markup yang perlu di-escape.
    """
    out: list[str] = []
    buf: list[str] = []
    i, n = 0, len(text)

    def flush() -> None:
        if buf:
            out.append(esc("".join(buf)))
            buf.clear()

    while i < n:
        if text.startswith("**", i):
            end = text.find("**", i + 2)
            if end == -1:
                raise TypstMarkupError(f"`**` tebal tidak ditutup: {text[i : i + 40]!r}")
            flush()
            out.append(f"*{_inline(text[i + 2 : end])}*")
            i = end + 2
        elif text[i] == "`":
            end = text.find("`", i + 1)
            if end == -1:
                raise TypstMarkupError(f"backtick tidak ditutup: {text[i : i + 40]!r}")
            flush()
            out.append(f"`{text[i + 1 : end]}`")
            i = end + 1
        elif text[i] == "*":
            end = text.find("*", i + 1)
            if end == -1:
                raise TypstMarkupError(f"`*` miring tidak ditutup: {text[i : i + 40]!r}")
            flush()
            out.append(f"_{_inline(text[i + 1 : end])}_")
            i = end + 1
        elif text[i] == "_" and (tutup := _underscore_emphasis(text, i)) is not None:
            flush()
            out.append(f"_{_inline(text[i + 1 : tutup])}_")
            i = tutup + 1
        else:
            buf.append(text[i])
            i += 1

    flush()
    return "".join(out)


# ---------------------------------------------------------------------------
# Primitif blok
# ---------------------------------------------------------------------------


def heading(level: int, text: str) -> str:
    """Heading Typst. `level` 1 = bab."""
    if level < 1:
        raise TypstMarkupError(f"level heading tidak sah: {level}")
    return f"{'=' * level} {_inline(text)}"


def pagebreak() -> str:
    return "#pagebreak()"


def table(
    header: list[str],
    rows: list[list[Any]],
    *,
    align: list[str] | None = None,
    caption: str | None = None,
) -> str:
    """Tabel Typst.

    `header` dan tiap baris `rows` harus sama panjang -- tabel yang kolomnya tidak konsisten
    adalah cacat data, bukan sesuatu yang boleh dirapikan diam-diam.
    """
    n = len(header)
    for r, row in enumerate(rows):
        if len(row) != n:
            raise TypstMarkupError(f"baris {r} punya {len(row)} sel, header punya {n}: {row!r}")
    aligns = align or ["left"] * n
    if len(aligns) != n:
        raise TypstMarkupError(f"align punya {len(aligns)} entri, header punya {n}")

    # Badan ditulis TANPA awalan `#`. Awalan itu hanya dipakai untuk masuk ke mode kode
    # dari markup; di dalam `#figure(...)` kita SUDAH berada di mode kode, dan `#` di sana
    # adalah galat sintaks ("the character `#` is not valid in code").
    lines = [
        "table(",
        f"  columns: {n},",
        f"  align: ({', '.join(aligns)}{',' if n == 1 else ''}),",
        "  " + ", ".join(f"[{_inline(str(h))}]" for h in header) + ",",
    ]
    for row in rows:
        lines.append("  " + ", ".join(f"[{_inline(str(c))}]" for c in row) + ",")
    lines.append(")")
    body = "\n".join(lines)
    if caption is None:
        return f"#{body}"
    return f"#figure(\n  {body},\n  caption: [{_inline(caption)}],\n)"


def figure(rel_path: str, caption: str, *, width: str = "100%") -> str:
    """Gambar bernomor. `rel_path` WAJIB relatif terhadap root kompilasi, gaya POSIX."""
    if "\\" in rel_path:
        raise TypstMarkupError(
            f"jalur gambar memakai pemisah Windows: {rel_path!r}. "
            "Typst hanya menerima '/' -- pakai Path.as_posix()."
        )
    return f'#figure(\n  image("{rel_path}", width: {width}),\n  caption: [{_inline(caption)}],\n)'


def callout(kind: str, body: str, *, title: str | None = None) -> str:
    """Kotak peringatan. `kind` mengikuti admonition GitHub (WARNING/NOTE/...)."""
    key = kind.upper()
    if key not in _CALLOUT_STYLE:
        raise TypstMarkupError(
            f"jenis callout tidak dikenal: {kind!r}. Pilihan: {sorted(_CALLOUT_STYLE)}"
        )
    label, colour = _CALLOUT_STYLE[key]
    return f"#kotak([{_inline(title or label)}], {colour})[\n{body}\n]"


def equation(body: str, *, caption: str | None = None) -> str:
    """Persamaan tampilan. `body` ditulis dalam sintaks math Typst, BUKAN LaTeX.

    Diberi `kind` tersendiri, bukan memakai kind gambar bawaan `#figure`. Tanpa itu
    persamaan ikut bernomor sebagai "Gambar" dan ikut terdaftar di Daftar Gambar --
    keduanya keliru pada dokumen teknik, dan menggeser penomoran gambar yang sebenarnya.
    """
    block = f"$ {body} $"
    if caption is None:
        return block
    return (
        f"#figure(\n  {block},\n"
        f'  kind: "persamaan",\n'
        f"  supplement: [Persamaan],\n"
        f"  caption: [{_inline(caption)}],\n)"
    )


# ---------------------------------------------------------------------------
# Konverter Markdown -> Typst
# ---------------------------------------------------------------------------


def from_markdown(text: str) -> str:
    """Terjemahkan subset Markdown proyek ini ke Typst.

    Yang didukung: paragraf, `**tebal**`/`*miring*`/`` `kode` ``, daftar bernomor &
    tak bernomor (termasuk isi berbilang paragraf dan tabel bersarang), tabel pipa
    beserta perataannya, blockquote, dan admonition GitHub (`> [!WARNING]` dst.).

    Selain itu -- heading `#`, blok kode berpagar, gambar, tautan -- **RAISE**. Itu
    disengaja: blok prosa yang diterjemahkan di sini adalah teks liabilitas, dan
    konstruksi yang dijatuhkan diam-diam berarti kalimat peringatan hilang dari dokumen
    tercetak tanpa satu pun tanda.
    """
    return "\n\n".join(_blocks(text.splitlines()))


def _blocks(lines: list[str]) -> list[str]:
    out: list[str] = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        stripped = line.lstrip()

        if stripped.startswith("#") and re.match(r"^#{1,6}\s", stripped):
            raise TypstMarkupError(
                f"heading Markdown di dalam blok prosa: {line.strip()!r}. "
                "Struktur dokumen dibangun `document.py` lewat heading(), bukan "
                "disisipkan dari teks -- heading liar akan merusak penomoran bab."
            )
        if stripped.startswith("```") or stripped.startswith("~~~"):
            raise TypstMarkupError(f"blok kode berpagar belum didukung: {line.strip()!r}")

        if stripped.startswith(">"):
            j = i
            while j < n and lines[j].lstrip().startswith(">"):
                j += 1
            out.append(_blockquote(lines[i:j]))
            i = j
            continue

        if stripped.startswith("|"):
            if i + 1 >= n or not _TABLE_SEP.match(lines[i + 1]):
                raise TypstMarkupError(f"baris tabel tanpa baris pemisah `|---|`: {line.strip()!r}")
            j = i
            while j < n and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(_table_block(lines[i:j]))
            i = j
            continue

        if _ORDERED_ITEM.match(line) or _UNORDERED_ITEM.match(line):
            block, i = _list_block(lines, i)
            out.append(block)
            continue

        j = i
        while j < n and lines[j].strip() and not _is_block_start(lines[j]):
            j += 1
        if j == i:  # baris ini sendiri pembuka blok lain -- jangan berputar selamanya
            j = i + 1
        out.append(_paragraph(lines[i:j]))
        i = j

    return out


def _is_block_start(line: str) -> bool:
    stripped = line.lstrip()
    return bool(
        stripped.startswith(("|", ">")) or _ORDERED_ITEM.match(line) or _UNORDERED_ITEM.match(line)
    )


def _paragraph(lines: list[str]) -> str:
    """Satu paragraf.

    Baris digabung LEBIH DULU, baru markup inline diproses. Markdown membungkus paragraf
    secara lunak, sehingga `**...**` boleh melintasi pergantian baris -- dan memang begitu
    di `config.KNOWN_LIMITATIONS`. Memproses per baris akan melihat pembuka tanpa penutup
    dan menolak teks yang sebenarnya sah.
    """
    joined = " ".join(ln.strip() for ln in lines if ln.strip())
    return _escape_line_start(_inline(joined))


def _blockquote(lines: list[str]) -> str:
    inner = [re.sub(r"^\s*>\s?", "", ln) for ln in lines]
    kind = None
    if inner and (m := re.match(r"^\[!([A-Z]+)\]\s*$", inner[0].strip())):
        kind = m.group(1)
        inner = inner[1:]
    body = "\n\n".join(_blocks(inner))
    if kind is None:
        return f"#quote(block: true)[\n{body}\n]"
    if kind not in _CALLOUT_STYLE:
        raise TypstMarkupError(
            f"admonition tidak dikenal: [!{kind}]. Pilihan: {sorted(_CALLOUT_STYLE)}"
        )
    return callout(kind, body)


def _split_row(line: str) -> list[str]:
    r"""Pecah satu baris tabel, menghormati pipa yang di-escape.

    `\|` di dalam sel adalah pipa LITERAL, bukan pemisah kolom -- dan itu benar-benar
    dipakai: header `stirrup_section` memuat `\|V_u\| maks` untuk menuliskan tanda nilai
    mutlak. Memecah pada setiap `|` mengubah satu kolom menjadi tiga, sehingga jumlah sel
    header tidak lagi cocok dengan barisnya.
    """
    teks = line.strip()
    sel: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(teks):
        if teks[i] == "\\" and i + 1 < len(teks) and teks[i + 1] == "|":
            buf.append("|")  # pipa literal, sudah tidak perlu escape Markdown-nya
            i += 2
        elif teks[i] == "|":
            sel.append("".join(buf).strip())
            buf.clear()
            i += 1
        else:
            buf.append(teks[i])
            i += 1
    sel.append("".join(buf).strip())
    # Pipa pembuka dan penutup menghasilkan sel kosong di kedua ujung.
    if sel and not sel[0]:
        sel.pop(0)
    if sel and not sel[-1]:
        sel.pop()
    return sel


def _table_block(lines: list[str]) -> str:
    header = _split_row(lines[0])
    aligns = []
    for spec in _split_row(lines[1]):
        left, right = spec.startswith(":"), spec.endswith(":")
        aligns.append("center" if left and right else "right" if right else "left")
    rows = [_split_row(ln) for ln in lines[2:]]
    return table(header, [list(r) for r in rows], align=aligns)


def _list_block(lines: list[str], start: int) -> tuple[str, int]:
    """Kumpulkan satu daftar beserta isi lanjutannya; kembalikan (Typst, indeks berikut)."""
    first = lines[start]
    ordered = bool(_ORDERED_ITEM.match(first))
    m = _ORDERED_ITEM.match(first) if ordered else _UNORDERED_ITEM.match(first)
    assert m is not None
    base_indent = len(m.group(1))
    first_number = int(m.group(2)) if ordered else 1

    items: list[list[str]] = []
    current: list[str] | None = None
    i, n = start, len(lines)

    while i < n:
        line = lines[i]
        if not line.strip():
            # Baris kosong masih milik daftar selama yang menyusul berupa lanjutan
            # ter-indentasi ATAU item berikutnya; selain itu daftarnya memang berakhir.
            nxt = next((k for k in range(i + 1, n) if lines[k].strip()), None)
            lanjut = nxt is not None and (
                len(lines[nxt]) - len(lines[nxt].lstrip()) > base_indent
                or _item_at(lines[nxt], ordered, base_indent)
            )
            if not lanjut:
                break
            if current is not None:
                current.append("")
            i += 1
            continue

        indent = len(line) - len(line.lstrip())
        if _item_at(line, ordered, base_indent):
            mm = (_ORDERED_ITEM if ordered else _UNORDERED_ITEM).match(line)
            assert mm is not None
            current = [mm.group(3) if ordered else mm.group(2)]
            items.append(current)
            i += 1
            continue
        if indent > base_indent and current is not None:
            current.append(line[base_indent:].lstrip() if indent <= base_indent else line)
            i += 1
            continue
        break

    if not items:
        raise TypstMarkupError(f"daftar tanpa satu pun item: {first.strip()!r}")

    # Lanjutan di-dedent seragam supaya tabel bersarang (KNOWN_LIMITATIONS #10) terbaca
    # sebagai tabel, bukan sebagai teks ter-indentasi.
    bodies = []
    for item in items:
        dedented = _dedent(item)
        bodies.append("\n\n".join(_blocks(dedented)))

    args = ",\n".join(f"  [\n{b}\n  ]" for b in bodies)
    if ordered:
        return f"#enum(\n  start: {first_number},\n{args},\n)", i
    return f"#list(\n{args},\n)", i


def _item_at(line: str, ordered: bool, base_indent: int) -> bool:
    m = (_ORDERED_ITEM if ordered else _UNORDERED_ITEM).match(line)
    return bool(m and len(m.group(1)) == base_indent)


def _dedent(item: list[str]) -> list[str]:
    """Buang indentasi bersama dari baris lanjutan satu item."""
    tail = [ln for ln in item[1:] if ln.strip()]
    pad = min((len(ln) - len(ln.lstrip()) for ln in tail), default=0)
    return [item[0]] + [ln[pad:] if ln.strip() else "" for ln in item[1:]]
