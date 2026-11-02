"""Deteksi berkas input di folder yang ditunjuk. Dipakai KEDUA antarmuka, tanpa toolkit.

Memakai `io_utils.autodetect` yang sama dengan CLI, sehingga apa yang ditampilkan antarmuka
persis apa yang nanti dipakai -- termasuk penolakannya bila ada dua berkas yang cocok pada
satu pola.
"""

from __future__ import annotations

from pathlib import Path

from pilecap_fem import config

#: Pola berkas yang, bila ada, MENGGANTIKAN field geometri di formulir. Dipetakan ke
#: `Section.override_entity` supaya antarmuka dapat menandai seksi yang diabaikan.
OVERRIDE_ENTITY: dict[str, str] = {
    "pilecap_polygon": "pilecap",
    "pile_coords": "pile",
    "pier_polygon": "pier",
}

#: Awalan pesan untuk pola yang cocok ke lebih dari satu berkas. Ditampilkan sebagai masalah,
#: bukan dilempar sebagai galat: pengguna masih dapat mengisi formulir dan membetulkan
#: foldernya, sedangkan jendela yang menolak terbuka tidak menjelaskan apa-apa.
AMBIGU = "AMBIGU: "


def deteksi(folder: str | Path) -> dict[str, str]:
    """Peta `kunci pola -> nama berkas` untuk folder input.

    Folder yang tidak ada mengembalikan peta kosong, bukan galat: kotak isian folder diketik
    pengguna, jadi keadaan "belum ada" adalah keadaan normal yang terus-menerus terjadi saat
    mengetik, bukan kesalahan.
    """
    from pilecap_fem import io_utils

    path = Path(folder)
    found: dict[str, str] = {}
    if not path.is_dir():
        return found
    for key in config.FILE_PATTERNS:
        try:
            match = io_utils.autodetect(path, key, required=False)
        except Exception as exc:  # pola ambigu -> tampilkan sebagai masalah, bukan crash
            found[key] = f"{AMBIGU}{exc}"
            continue
        if match is not None:
            found[key] = match.name
    return found


def override_terdeteksi(terdeteksi: dict[str, str]) -> dict[str, str]:
    """Peta `entitas seksi -> nama berkas` untuk geometri yang diambil dari CSV."""
    return {OVERRIDE_ENTITY[k]: v for k, v in terdeteksi.items() if k in OVERRIDE_ENTITY}


#: Seksi tempat catatan CSV tebal ditampilkan.
TEBAL_ENTITY = "pilecap"


def catatan_tebal(terdeteksi: dict[str, str]) -> str | None:
    """Catatan untuk seksi Pilecap bila tebal diambil dari CSV per bidang.

    Bukan override SELURUH seksi seperti `pilecap_polygon`: yang digantikan hanya field
    tebal, sedangkan dimensi dan titik asal pilecap tetap dipakai. Karena itu ia catatan
    tersendiri, bukan entri `OVERRIDE_ENTITY` yang akan menandai seluruh seksi diabaikan.
    """
    berkas = terdeteksi.get("pilecap_thickness")
    if not berkas or berkas.startswith(AMBIGU):
        return None
    return (
        f"Tebal diambil dari {berkas} (CSV per bidang) -- pilecap tapper. "
        "Field pilecap.thickness, pilecap.edge_thickness, dan pilecap.taper_shoulder "
        "DIABAIKAN; tebal maksimum = tebal terbesar di CSV."
    )


__all__ = [
    "AMBIGU",
    "OVERRIDE_ENTITY",
    "TEBAL_ENTITY",
    "catatan_tebal",
    "deteksi",
    "override_terdeteksi",
]
