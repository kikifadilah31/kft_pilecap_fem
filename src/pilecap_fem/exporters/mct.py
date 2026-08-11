"""Ekspor model pilecap ke berkas Midas Civil `.mct`.

Format diturunkan dari berkas rujukan `ref/PILECAP_P32N.mct` yang disediakan user.
Empat hal DIUBAH dengan sengaja terhadap rujukan itu, masing-masing dengan alasan:

1. **`*UNIT` ditulis eksplisit.** Rujukan tidak memuatnya sama sekali, sehingga berkasnya
   mewarisi satuan model Midas penerima -- bila model itu memakai N/mm, seluruh angka
   terbaca salah tanpa satu pun peringatan. Nilainya tetap kN + m seperti rujukan.

2. **Arah tekanan `GZ`, bukan `LZ`.** `LZ` adalah normal LOKAL pelat, yang tandanya
   mengikuti urutan simpul menurut kaidah tangan kanan. Urutan itu TIDAK dijamin pada mesh
   gmsh kita: `mesh_model._quad_areas_and_centroids` sengaja mengambil `np.abs(signed)`
   dengan alasan yang tertulis di docstring-nya. Elemen yang kebetulan searah jarum jam
   akan menerima beban terbalik -- kesalahan yang tidak memunculkan error apa pun. Pilecap
   datar di bidang XY, sehingga `GZ` setara persis dan bebas dari ketergantungan itu.

3. **`*GROUP` selalu bentuk elemen-saja** (`NAMA, , <elemen>, 0`). Grup `Surface1008` pada
   rujukan RUSAK karena terpotong di sekitar 8.192 byte: daftar node-nya 1.670 token (tidak
   habis dibagi 4) dan barisnya kehilangan daftar elemen beserta field terakhir. Membiarkan
   Midas menurunkan node dari elemen menghindari seluruh kelas kegagalan itu.

4. **Header komentar `;`.** Rujukan tidak memuat satu pun `;`. Midas mengabaikan baris
   komentar, dan berkas hasil generator tanpa jejak asal bertentangan dengan PRD Core 4.

.. warning::
   Bagian `*CONSTRAINT` **tidak ada** di berkas rujukan, sehingga sintaksnya ditulis
   menurut konvensi MCT dan belum tervalidasi terhadap contoh nyata. Statusnya dinyatakan
   di header setiap berkas yang dihasilkan agar diperiksa pada impor pertama.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pilecap_fem import __version__, config
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel
from pilecap_fem.reporter import slugify

if TYPE_CHECKING:  # pragma: no cover
    # Hanya anotasi. Mengimpornya saat runtime menarik openseespy, padahal ekspor MCT
    # tidak menjalankan solver apa pun.
    from pilecap_fem.fem_engine import MaterialProperties

_log = config.get_logger("exporters.mct")

#: Satuan yang ditulis di `*UNIT`. Sama dengan yang dipakai berkas rujukan (terbaca dari
#: `E = 2.7805e+07` kN/m^2 dan tebal `2.5`), hanya kini dinyatakan.
MCT_FORCE_UNIT = "KN"
MCT_LENGTH_UNIT = "M"
MCT_HEAT_UNIT = "KJ"
MCT_TEMP_UNIT = "C"

#: SI -> satuan MCT.
_N_TO_KN = 1e-3
_PA_TO_KN_PER_M2 = 1e-3

#: `iSUB` pada `*ELEMENT`: 1 = thick plate (Mindlin), setara `ShellMITC4` yang juga
#: memperhitungkan deformasi geser melintang.
_PLATE_THICK = 1

#: `iTYPE` pada header `*LOADCOMB`. 1 = Envelope; 0 akan MENJUMLAHKAN seluruh kombinasi
#: terfaktor -- hasil yang sangat salah dan tetap dihitung Midas tanpa keluhan.
_LOADCOMB_ENVELOPE = 1


#: Digit berarti untuk angka MCT. Dipakai `%g`, BUKAN `repr`: koordinat hasil gmsh membawa
#: derau representasi biner (`-0.7999999999999999` untuk -0,8 m yang eksak di input), dan
#: menuliskannya apa adanya membuat berkas sulit dibaca tanpa menambah ketelitian apa pun.
#: 12 digit menyisakan ~1e-9 m pada koordinat pilecap dan jauh lebih halus daripada
#: ketelitian tekanan mana pun.
_SIGNIFICANT_DIGITS = 12


def _num(value: float) -> str:
    """Angka MCT: bilangan bulat tanpa `.0`, sisanya `%.12g`.

    Mengikuti gaya berkas rujukan, yang menulis `0` dan `15.9`, bukan `0.0` dan `15.900`.
    """
    if value == int(value):
        return str(int(value))
    return f"{value:.{_SIGNIFICANT_DIGITS}g}"


def _header(
    *,
    project_name: str,
    command: str,
    mesh: MeshModel,
    n_groups: int,
    combos: Sequence[str],
    now: datetime,
) -> list[str]:
    lines = [
        "; " + "=" * 74,
        f"; Berkas MCT dihasilkan pilecap-fem v{__version__}",
        f"; Proyek   : {project_name or '(tanpa nama)'}",
        f"; Waktu    : {now.isoformat(timespec='seconds')}",
        f"; Perintah : {command}",
        "; " + "-" * 74,
        f"; Satuan   : {MCT_FORCE_UNIT}, {MCT_LENGTH_UNIT} (dinyatakan di *UNIT di bawah;",
        ";            berkas rujukan TIDAK menyatakannya sehingga mewarisi satuan model)",
        f"; Model    : {mesh.n_nodes:,} node | {mesh.n_elements:,} elemen PLATE | {n_groups} grup",
        "; Elemen   : iSUB=1 (thick plate / Mindlin), setara ShellMITC4 di pilecap-fem",
        "; Tekanan  : arah GZ (global Z), positif = pile mendorong pilecap ke ATAS.",
        ";            GZ dipakai -- bukan LZ seperti rujukan -- karena urutan simpul quad",
        ";            gmsh tidak dijamin CCW, sehingga normal lokal dapat terbalik.",
        "; " + "-" * 74,
        "; PERIKSA SAAT IMPOR PERTAMA -- dua bagian di bawah ini TIDAK dapat divalidasi",
        "; terhadap berkas rujukan, sehingga sintaksnya ditulis menurut konvensi MCT:",
        ";   1. *CONSTRAINT  -- rujukan tidak memuat tumpuan sama sekali. Pastikan jepit",
        ";      6 DOF di area pier terbaca benar.",
        ";   2. *MATERIAL    -- dipakai varian USER-DEFINED (field ke-10 = 2: E, nu, ...),",
        ";      bukan varian lookup database seperti rujukan. Alasannya: pilecap-fem",
        ";      menuntut E diisi user beserta sumbernya dan TIDAK pernah menurunkannya",
        ";      dari f'c, sehingga nilai eksplisit itulah yang harus dibawa.",
    ]
    if combos:
        lines.append("; " + "-" * 74)
        lines.append("; Pemetaan nama kombinasi -> nama load case MCT (nama MCT tidak")
        lines.append("; boleh memuat koma atau spasi):")
        for combo in combos:
            lines.append(f";   {combo}  ->  {slugify(combo)}")
    lines.append("; " + "=" * 74)
    return lines


def _node_section(mesh: MeshModel) -> list[str]:
    lines = ["*NODE"]
    for tag, (x, y) in zip(mesh.node_tags, mesh.node_xy, strict=True):
        lines.append(f"{int(tag)}, {_num(float(x))}, {_num(float(y))}, 0")
    return lines


def _element_section(mesh: MeshModel) -> list[str]:
    """`iEL,PLATE,iMAT,iPRO,n1,n2,n3,n4,iSUB,iWID` -- 10 field, tanpa ANGLE/EXVAL."""
    lines = ["*ELEMENT"]
    for i, tag in enumerate(mesh.elem_tags):
        n1, n2, n3, n4 = (int(mesh.node_tags[j]) for j in mesh.elem_conn[i])
        lines.append(f"{int(tag)},PLATE,1,1, {n1}, {n2}, {n3}, {n4},{_PLATE_THICK},0")
    return lines


def _group_section(mesh: MeshModel) -> list[str]:
    """Satu `*GROUP` per physical group gmsh, bentuk elemen-saja."""
    lines = ["*GROUP"]
    for name in mesh.group_names:
        tags = mesh.elem_tags[mesh.group_mask(name)]
        elements = " ".join(str(int(t)) for t in tags)
        lines.append(f"{name}, , {elements}, 0")
    return lines


def _material_section(material: MaterialProperties, fc_pa: float | None) -> list[str]:
    """Varian USER-DEFINED (field ke-10 = 2), bukan lookup database seperti rujukan.

    `pilecap-fem` menuntut `material.E` diisi user beserta `E_source` dan menolak
    menurunkannya dari `f'c` (PRD Bagian 7.4). Membawa nilai eksplisit itu ke Midas berarti
    memakai varian user-defined; varian database akan membuat Midas memakai `E` miliknya
    sendiri, sehingga model yang diekspor tidak lagi setara dengan yang dianalisis.
    """
    e_kn_m2 = material.E * _PA_TO_KN_PER_M2
    name = f"fc{fc_pa * 1e-6:.0f}" if fc_pa else "BETON"
    return [
        "*MATERIAL",
        f"1, CONC , {name} , 0, 0, , C, NO, 0.05, 2, {_num(e_kn_m2)}, "
        f"{_num(material.nu)}, 0, {_num(material.density * _N_TO_KN)}",
    ]


def _thickness_section(material: MaterialProperties) -> list[str]:
    return ["*THICKNESS", f"1, VALUE, 1, YES, {_num(material.thickness)}, 0, NO, 0, 0"]


def _constraint_section(mesh: MeshModel, geom: GeometryModel) -> list[str]:
    """Jepit 6 DOF pada himpunan node yang SAMA dengan model OpenSees.

    Memakai `fem_engine.fixed_support_nodes`, bukan menghitung sendiri dari
    `mesh.pier_groups()`. Kalau dihitung sendiri, node group LENSA (bagian pile di dalam
    pier) akan tertinggal bebas di Midas padahal terjepit di OpenSees -- dan VC-6
    membandingkan kedua model itu.
    """
    from pilecap_fem.fem_engine import fixed_support_nodes

    indeks = fixed_support_nodes(mesh, geom)
    if indeks.size == 0:
        return []
    daftar = " ".join(str(int(mesh.node_tags[n])) for n in indeks)
    return ["*CONSTRAINT", f"{daftar}, 111111, "]


def _load_sections(
    mesh: MeshModel,
    geom: GeometryModel,
    loads: Mapping[str, Mapping[str, float]],
) -> list[str]:
    """`*STLDCASE` + `*LOADCOMB` envelope + satu blok `*PRESSURE` per kombinasi."""
    from pilecap_fem.fem_engine import pile_pressures

    combos = list(loads)
    names = {combo: slugify(combo) for combo in combos}

    lines = ["*STLDCASE"]
    lines += [f"{names[c]},USER" for c in combos]

    # Envelope, BUKAN penjumlahan: tiap kombinasi sudah terfaktor di `pile_reactions.csv`,
    # jadi menjumlahkannya akan melipatgandakan beban.
    lines.append("*LOADCOMB")
    lines.append(f"NAME=ENVELOPE, GEN, ACTIVE, 0, {_LOADCOMB_ENVELOPE}, , 0, 0, 0, 1")
    lines += [f"ST,{names[c]},1" for c in combos]

    for combo in combos:
        lines.append(f"*USE-STLD,{names[combo]}")
        lines.append("*PRESSURE")
        for load in pile_pressures(mesh, geom, dict(loads[combo])):
            p = _num(load.pressure * _PA_TO_KN_PER_M2)
            for index in load.element_index:
                tag = int(mesh.elem_tags[index])
                lines.append(f"{tag}, PRES , PLATE, FACE, GZ, 0, 0, 0, NO,{p}, 0, 0, 0, 0, ,0")
    return lines


def write_mct(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    material: MaterialProperties | None,
    *,
    project_name: str = "",
    command: str = "",
    fc_pa: float | None = None,
    loads: Mapping[str, Mapping[str, float]] | None = None,
    now: datetime | None = None,
) -> Path:
    """Tulis model ke berkas Midas Civil `.mct`.

    `loads` memetakan nama kombinasi -> `{pile_id: Pz [N]}`. Bila `None`, berkas berisi
    geometri, grup, dan tumpuan saja -- itulah yang dihasilkan `pilecap-mesh`, yang memang
    tidak pernah membaca `pile_reactions.csv`.

    `material` boleh `None` hanya bila `material.E` tidak diisi user, yang sah pada
    `pilecap-mesh`. Blok `*MATERIAL`/`*THICKNESS` lalu DIHILANGKAN dan ketiadaannya
    dinyatakan sebagai komentar, bukan diisi angka karangan: menurunkan `E` sendiri
    dilarang PRD Bagian 7.4, dan berkas yang diam-diam memakai `E` tebakan akan
    menghasilkan lendutan yang salah tanpa satu pun tanda.
    """
    combos = list(loads) if loads else []
    lines = _header(
        project_name=project_name,
        command=command,
        mesh=mesh,
        n_groups=len(mesh.group_names),
        combos=combos,
        now=now or datetime.now(),
    )
    lines.append("*UNIT")
    lines.append(f"{MCT_FORCE_UNIT}, {MCT_LENGTH_UNIT}, {MCT_HEAT_UNIT}, {MCT_TEMP_UNIT}")
    lines += _node_section(mesh)
    lines += _element_section(mesh)
    lines += _group_section(mesh)
    if material is not None:
        lines += _material_section(material, fc_pa)
        lines += _thickness_section(material)
    else:
        lines.append("; TANPA *MATERIAL dan *THICKNESS: `material.E` tidak diisi di konfigurasi.")
        lines.append("; pilecap-fem tidak menurunkan E dari f'c (PRD Bagian 7.4), sehingga")
        lines.append("; nilainya harus Anda isi sendiri di Midas sebelum model dijalankan.")
    lines += _constraint_section(mesh, geom)
    if loads:
        lines += _load_sections(mesh, geom, loads)
    else:
        lines.append("; Tanpa pembebanan: dihasilkan `pilecap-mesh`, yang tidak membaca")
        lines.append("; pile_reactions.csv. Jalankan `pilecap-analyze` untuk versi lengkap.")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log.info(
        "%s ditulis: %d node, %d elemen, %d grup, %d kombinasi",
        path.name,
        mesh.n_nodes,
        mesh.n_elements,
        len(mesh.group_names),
        len(combos),
    )
    return path


def pressure_rows(mesh: MeshModel, geom: GeometryModel, pz_by_pile: Mapping[str, float]) -> int:
    """Jumlah baris `*PRESSURE` untuk satu kombinasi -- dipakai test dan pesan log."""
    from pilecap_fem.fem_engine import pile_pressures

    return int(np.sum([load.n_elements for load in pile_pressures(mesh, geom, dict(pz_by_pile))]))


__all__ = ["MCT_FORCE_UNIT", "MCT_LENGTH_UNIT", "pressure_rows", "write_mct"]
