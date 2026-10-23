"""Logika bersama antarmuka desktop (wxPython dan PySide6). TIDAK mengimpor toolkit apa pun.

Semula seluruhnya ada di dalam `wxgui/main.py`, bercampur dengan widget. Begitu ada frontend
desktop kedua, setiap fungsi di sini akan tersalin -- dan salinan pesan galat, aturan exit
code, atau penyusunan perintah adalah tempat dua antarmuka mulai menyimpang tanpa ada yang
memperhatikan. Alasannya sama dengan `runner.py`, `detect.py`, dan `formstate.py`.

Fungsi di sini mengembalikan teks beserta `tingkat`-nya (`info`/`sukses`/`peringatan`/
`galat`); masing-masing toolkit hanya memetakan tingkat itu ke ikon dan warnanya sendiri.

`workdir` selalu diterima sebagai argumen, tidak dibaca dari variabel global modul ini:
frontend menyimpannya sebagai atribut modulnya sendiri, dan test menimpa atribut itu.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pilecap_fem.ui import argv as argv_builder
from pilecap_fem.ui import runner, runopts, schema
from pilecap_fem.ui.launcher import CWD_ENV

#: Jeda sebelum lintasan penyegaran dijalankan, dalam milidetik.
#:
#: Penyegaran dipicu tiap ketukan tombol. Tanpa jeda, mengetik "1200" menjalankan empat
#: lintasan penuh atas 70 field berikut tata letaknya -- terasa sebagai kibasan dan huruf yang
#: tertinggal. Cukup pendek untuk tidak terasa sebagai lag, cukup panjang untuk menyatukan
#: satu kata ketikan.
JEDA_SEGAR_MS = 180

Tingkat = Literal["info", "sukses", "peringatan", "galat"]


@dataclass(frozen=True)
class Pesan:
    """Teks untuk pengguna beserta tingkatnya; toolkit yang memilih ikon dan warnanya."""

    tingkat: Tingkat
    isi: str


def folder_kerja() -> Path:
    """Folder kerja: tempat perintah dipanggil, sama dengan Streamlit dan CLI."""
    return Path(os.environ.get(CWD_ENV, os.getcwd()))


# ---------------------------------------------------------------------------
# Nilai formulir
# ---------------------------------------------------------------------------


def nilai_skema(nilai: dict[str, Any]) -> dict[str, Any]:
    """Buang kunci opsi run; `schema.build_config` hanya mengenal kunci skema."""
    return {k: v for k, v in nilai.items() if not k.startswith(runopts.PREFIX)}


def susun_perintah_pratinjau(nilai: dict[str, Any], input_dir: str, workdir: Path) -> str:
    """Perintah yang AKAN dijalankan, memakai nama config yang belum ada.

    Config baru ditulis tiap run (`schema.write_config` tidak pernah menimpa), jadi nama
    pastinya belum diketahui sebelum tombol ditekan. Yang ditampilkan karena itu memakai
    nama contoh -- bentuk flag-nya yang penting di sini, dan itu sudah tepat.
    """
    try:
        cli_argv = argv_builder.build_argv(
            workdir / "ui_configs" / "pilecap_config_<timestamp>.json",
            Path(input_dir or "."),
            runopts.to_argv_values(nilai),
        )
    except Exception as exc:  # formulir setengah terisi bukan kesalahan pengguna
        return f"(perintah belum dapat disusun: {exc})"
    return argv_builder.format_command(cli_argv)


def peringatan_koersi(pasangan: Iterable[tuple[str, str | None]]) -> list[str]:
    """`"label: pesan"` untuk setiap isian yang tidak terbaca, dari pasangan (label, pesan)."""
    return [f"{label}: {pesan}" for label, pesan in pasangan if pesan]


def teks_konfirmasi_koersi(peringatan: list[str]) -> str:
    """Pertanyaan sebelum run bila ada isian yang diganti nilai bawaan.

    Ditanyakan, tidak dijalankan diam-diam: isian yang tidak terbaca diganti nilai bawaan, dan
    itu perubahan pada masukan analisis yang berhak diketahui pengguna SEBELUM run berjalan
    belasan menit.
    """
    return (
        "Beberapa isian tidak terbaca dan akan memakai nilai bawaan:\n\n  "
        + "\n  ".join(peringatan)
        + "\n\nLanjutkan?"
    )


# ---------------------------------------------------------------------------
# Folder input
# ---------------------------------------------------------------------------


def status_folder_input(folder: str, terdeteksi: dict[str, str]) -> Pesan:
    """Satu baris status di bawah kotak folder input."""
    if not Path(folder).is_dir():
        return Pesan("galat", "Folder tidak ditemukan.")
    if "reactions" not in terdeteksi:
        return Pesan(
            "peringatan",
            "pile_reactions.csv tidak terdeteksi -- analisis tidak dapat berjalan tanpa itu.",
        )
    return Pesan("sukses", f"Reaksi pile: {terdeteksi['reactions']}")


def teks_override(berkas: str) -> str:
    """Penanda pada seksi yang field-nya diabaikan karena geometrinya diambil dari CSV."""
    return (
        f"Diabaikan -- di-override {berkas}. Nilai tetap ditulis ke config supaya terlihat "
        "apa yang dilewati."
    )


# ---------------------------------------------------------------------------
# Memuat config
# ---------------------------------------------------------------------------


class ConfigTakTerbaca(Exception):
    """Config yang diminta tidak dapat dimuat; pesannya siap ditampilkan apa adanya."""


def muat_config(teks: str, workdir: Path) -> tuple[dict[str, Any], tuple[str, ...], Path]:
    """Baca `pilecap_config.json` menjadi nilai formulir.

    Mengembalikan `(nilai, kunci_tak_dikenal, path)`; memunculkan `ConfigTakTerbaca` dengan
    pesan untuk pengguna bila berkasnya tidak dapat dipakai. Path relatif diukur dari folder
    kerja, sama seperti halaman Streamlit.
    """
    teks = (teks or "").strip()
    if not teks:
        raise ConfigTakTerbaca("Isi dulu path config-nya.")
    path = Path(teks).expanduser()
    if not path.is_absolute():
        path = workdir / path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ConfigTakTerbaca(f"Berkas tidak ditemukan:\n{path}") from None
    except json.JSONDecodeError as exc:
        raise ConfigTakTerbaca(f"Bukan JSON yang sah: {exc}") from None
    if not isinstance(raw, dict):
        raise ConfigTakTerbaca("Isi config harus objek JSON di level teratas.")
    nilai, tak_dikenal = schema.values_from_config(raw)
    return nilai, tuple(tak_dikenal), path


def pesan_dimuat(path: Path, tak_dikenal: tuple[str, ...]) -> Pesan:
    """Pemberitahuan setelah config dimuat.

    Kunci yang tidak dikenal DILAPORKAN, tidak dibuang diam-diam: config tulisan tangan boleh
    memuat field yang belum diwakili formulir, dan menyimpan ulang lewat formulir akan
    menghilangkannya.
    """
    isi = f"Dimuat dari {path}"
    if not tak_dikenal:
        return Pesan("info", isi)
    isi += (
        "\n\nKunci berikut tidak dikenal formulir dan TIDAK akan ikut ditulis ke config baru:"
        "\n  " + "\n  ".join(tak_dikenal)
    )
    return Pesan("peringatan", isi)


# ---------------------------------------------------------------------------
# Pratinjau & menjalankan
# ---------------------------------------------------------------------------


def gambar_pratinjau(nilai: dict[str, Any], input_dir: str) -> Any:
    """Figure matplotlib denah geometri. Memunculkan `PilecapError` bila masukan ditolak.

    Hanya geometri: tidak menyentuh gmsh maupun OpenSees, jadi selesai dalam milidetik dan
    boleh berjalan di proses antarmuka. Pesan `PilecapError` sudah ditulis untuk dibaca
    engineer, jadi pemanggil menampilkannya apa adanya.
    """
    from pilecap_fem import config, renderer
    from pilecap_fem.ui import preview as preview_mod

    folder = (input_dir or "").strip()
    geom = preview_mod.build_preview_geometry(
        schema.build_config(nilai_skema(nilai)), Path(folder) if folder else None
    )
    return renderer.render_geometry_plan(
        geom,
        style=renderer.PlotStyle(theme=config.theme(nilai["run.theme"])),
        block=renderer.TitleBlock(
            project=str(nilai.get("project.name") or ""),
            engineer=str(nilai.get("project.engineer") or ""),
            date=str(nilai.get("project.date") or ""),
        ),
    )


def siapkan_run(nilai: dict[str, Any], input_dir: str, workdir: Path) -> tuple[Path, list[str]]:
    """Tulis config baru lalu susun argv CLI-nya. Mengembalikan `(config_path, argv)`."""
    config_path = schema.write_config(schema.build_config(nilai_skema(nilai)), workdir)
    cli_argv = argv_builder.build_argv(config_path, Path(input_dir), runopts.to_argv_values(nilai))
    return config_path, cli_argv


def label_hasil(hasil: runner.Hasil) -> Pesan:
    """Satu baris ringkas untuk bilah status dan label di samping tombol."""
    if hasil.returncode == 0:
        return Pesan("sukses", f"Selesai -- {hasil.run_dir}")
    return Pesan("galat", f"Gagal (exit {hasil.returncode})")


def pesan_hasil(hasil: runner.Hasil, config_path: Path) -> Pesan:
    """Pemberitahuan di akhir run, menurut kode keluar CLI.

    `0` sukses, `2` masukan ditolak, `4` fitur belum tersedia, selain itu berhenti tak
    terduga. Pada `2`, baris `GAGAL:` dan sesudahnya DIDAHULUKAN: pada masukan dengan override
    geometri, log diakhiri belasan baris WARNING dan penyebab sebenarnya terkubur di bawahnya.
    """
    if hasil.returncode == 0:
        return Pesan(
            "sukses",
            f"Analisis selesai.\n\nFolder hasil:\n{hasil.run_dir}\n\n"
            f"Config yang dipakai:\n{config_path}\n\n"
            "Buka SUMMARY.md di folder hasil untuk ringkasan, dan calc_sheet.md di tiap "
            "folder kombinasi untuk perhitungan yang dapat ditelusuri.",
        )
    if hasil.returncode == 2:
        ringkas = runner.ringkas_kegagalan(hasil.lines)
        if ringkas:
            return Pesan("galat", "Masukan ditolak:\n\n" + "\n".join(ringkas))
        return Pesan("galat", "Masukan ditolak. Lihat log di jendela.")
    if hasil.returncode == 4:
        return Pesan("peringatan", "Fitur yang diminta belum tersedia di versi ini.")
    return Pesan(
        "galat",
        f"Berhenti tak terduga (exit {hasil.returncode}). Log lengkap ada di jendela.",
    )


__all__ = [
    "JEDA_SEGAR_MS",
    "ConfigTakTerbaca",
    "Pesan",
    "Tingkat",
    "folder_kerja",
    "gambar_pratinjau",
    "label_hasil",
    "muat_config",
    "nilai_skema",
    "peringatan_koersi",
    "pesan_dimuat",
    "pesan_hasil",
    "siapkan_run",
    "status_folder_input",
    "susun_perintah_pratinjau",
    "teks_konfirmasi_koersi",
    "teks_override",
]
