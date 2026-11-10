"""Ekspor model pilecap ke berkas teks SAP2000 `.s2k`.

Format diturunkan dari berkas contoh pengguna `Pilecap P32N.$2k` (SAP2000 v24.2.0,
`CurrUnits="KN, m, C"`). Setiap tabel yang ditulis di sini ADA di berkas itu -- dengan nama,
urutan kolom, dan gaya penulisan yang sama -- KECUALI `COMBINATION DEFINITIONS`, yang ditulis
menurut konvensi SAP2000 dan belum tervalidasi terhadap contoh nyata. Statusnya dinyatakan
di tabel `PROJECT INFORMATION` setiap berkas agar diperiksa pada impor pertama.

Isinya setara dengan `exporters.mct`, dan diambil dari fungsi yang SAMA dengan model
OpenSees: tekanan pile dari `fem_engine.pile_pressures`, tumpuan dari
`fem_engine.fixed_support_nodes`, tebal per pita dari `ThicknessBands`. Tiga keputusan:

1. **Beban pile dapat ditulis dua cara** (`load_mode`): `area` -- `AREA LOADS - UNIFORM`
   arah Z global, identik dengan `*PRESSURE` GZ di MCT -- atau `joint` -- `JOINT LOADS -
   FORCE`, gaya nodal pile yang persis dirakit strategi beban OpenSees.
2. **Simpul tiap area diurut berlawanan jarum jam.** Mesh gmsh tidak menjamin urutannya
   (lihat `mesh_model._quad_areas_and_centroids`); tanpa ini sumbu lokal 3 SAP sebagian
   menghadap ke bawah dan M11/M22 terbaca bertanda terbalik di elemen tersebut. Beban tidak
   terpengaruh karena ditulis pada sumbu GLOBAL.
3. **Provenance di `PROJECT INFORMATION`, bukan baris komentar.** Contoh tidak memuat sintaks
   komentar, dan baris yang tidak dikenali dapat membuat impor gagal.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from pilecap_fem import __version__, config
from pilecap_fem.exporters.mct import _num
from pilecap_fem.geometry_builder import GeometryModel
from pilecap_fem.mesh_model import MeshModel

if TYPE_CHECKING:  # pragma: no cover
    # Hanya anotasi: mengimpornya saat runtime menarik openseespy.
    from pilecap_fem.fem_engine import MaterialProperties
    from pilecap_fem.thickness import ThicknessBands

_log = config.get_logger("exporters.s2k")

#: Satuan berkas, sama dengan contoh. Seluruh angka di bawah dikonversi ke sini.
S2K_UNITS = "KN, m, C"
_N_TO_KN = 1e-3
_PA_TO_KN_PER_M2 = 1e-3
_G = 9.80665

#: Nama seksi pilecap seragam; pilecap tapper memakai satu seksi per pita (`T1010`, ...).
SECTION_UNIFORM = "PILECAP"
ENVELOPE_NAME = "ENVELOPE"

#: Modifikasi kekakuan seksi, semuanya 1 -- ditulis eksplisit seperti contoh.
_MODIFIERS = tuple(
    f"{m}Mod=1" for m in ("F11", "F22", "F12", "M11", "M22", "M12", "V13", "V23", "M", "W")
)
_GROUP_FLAGS = (
    *(f"{k}=Yes" for k in ("Selection", "SectionCut", "Steel", "Concrete", "Aluminum")),
    *(f"{k}=Yes" for k in ("ColdFormed", "Stage", "Bridge")),
    *(f"{k}=No" for k in ("AutoSeismic", "AutoWind", "SelDesSteel", "SelDesAlum", "SelDesCold")),
    "MassWeight=Yes",
)

#: Panjang baris maksimum. Contoh memecah baris di ~240 karakter (`TextFileLen=240` di
#: preferensinya) dengan ` _` di ujung dan 8 spasi di awal baris lanjutan; ditiru persis,
#: karena baris yang jauh lebih panjang tidak pernah muncul di berkas buatan SAP sendiri.
_MAX_BARIS = 240


def _q(text: str) -> str:
    """Nilai teks: dikutip bila memuat spasi atau karakter non-alfanumerik, seperti contoh.

    Tanda kutip ganda di dalam nama diganti tanda kutip tunggal -- SAP tidak punya cara
    meloloskannya, dan nama kombinasi berasal dari CSV pengguna.
    """
    bersih = text.replace('"', "'")
    if bersih and all(c.isalnum() or c in "_-." for c in bersih):
        return bersih
    return f'"{bersih}"'


def _row(*fields: str) -> str:
    """Satu baris tabel; dipecah di batas field bila melewati `_MAX_BARIS`, seperti SAP."""
    baris: list[str] = []
    kini = "   " + fields[0]
    for f in fields[1:]:
        if len(kini) + 3 + len(f) + 2 > _MAX_BARIS:
            baris.append(kini + " _")
            kini = "        " + f
        else:
            kini += "   " + f
    baris.append(kini)
    return "\n".join(baris)


def _table(name: str, rows: list[str]) -> list[str]:
    return [f'TABLE:  "{name}"', *rows, " "]


def _section_name(t: float) -> str:
    return f"T{round(t * 1e3):d}"


def _ccw_connectivity(mesh: MeshModel) -> np.ndarray:
    """Tag node tiap area, diurut berlawanan jarum jam (luas bertanda positif)."""
    xy = mesh.node_xy[mesh.elem_conn]
    x, y = xy[:, :, 0], xy[:, :, 1]
    signed = 0.5 * np.sum(x * np.roll(y, -1, axis=1) - np.roll(x, -1, axis=1) * y, axis=1)
    conn = mesh.elem_conn.copy()
    cw = signed < 0.0
    conn[cw] = conn[cw][:, ::-1]
    return np.asarray(mesh.node_tags[conn])


def _material_tables(material: MaterialProperties, fc_pa: float | None, name: str) -> list[str]:
    unit_weight = material.density * _N_TO_KN
    e_kn = material.E * _PA_TO_KN_PER_M2
    g_kn = e_kn / (2.0 * (1.0 + material.nu))
    lines = _table(
        "MATERIAL PROPERTIES 01 - GENERAL",
        [_row(f"Material={_q(name)}", "Type=Concrete", "SymType=Isotropic", "TempDepend=No")],
    )
    lines += _table(
        "MATERIAL PROPERTIES 02 - BASIC MECHANICAL PROPERTIES",
        [
            _row(
                f"Material={_q(name)}",
                f"UnitWeight={_num(unit_weight)}",
                f"UnitMass={_num(unit_weight / _G)}",
                f"E1={_num(e_kn)}",
                f"G12={_num(g_kn)}",
                f"U12={_num(material.nu)}",
                "A1=9.9E-06",
            )
        ],
    )
    if fc_pa:
        fc_kn = fc_pa * _PA_TO_KN_PER_M2
        lines += _table(
            "MATERIAL PROPERTIES 03B - CONCRETE DATA",
            [
                _row(
                    f"Material={_q(name)}",
                    f"Fc={_num(fc_kn)}",
                    f"eFc={_num(fc_kn)}",
                    "LtWtConc=No",
                )
            ],
        )
    return lines


def _section_tables(
    mesh: MeshModel, material: MaterialProperties, bands: ThicknessBands | None, mat_name: str
) -> list[str]:
    if bands is None or bands.step is None:
        seksi = [(SECTION_UNIFORM, material.thickness)]
        per_elemen = [SECTION_UNIFORM] * mesh.n_elements
    else:
        seksi = [(_section_name(float(t)), float(t)) for t in bands.values]
        per_elemen = [seksi[int(b)][0] for b in bands.elem_band]
    props = [
        _row(
            f"Section={s}",
            f"Material={_q(mat_name)}",
            "MatAngle=0",
            "AreaType=Shell",
            "Type=Shell-Thick",
            "DrillDOF=Yes",
            f"Thickness={_num(t)}",
            f"BendThick={_num(t)}",
            *_MODIFIERS,
        )
        for s, t in seksi
    ]
    assign = [
        _row(f"Area={int(tag)}", f"Section={s}", "MatProp=Default")
        for tag, s in zip(mesh.elem_tags, per_elemen, strict=True)
    ]
    return _table("AREA SECTION ASSIGNMENTS", assign) + _table("AREA SECTION PROPERTIES", props)


def _project_information(
    *,
    project_name: str,
    now: datetime,
    material: MaterialProperties | None,
    loads: Mapping[str, Mapping[str, float]] | None,
    load_mode: str,
    self_weight: bool,
    bands: ThicknessBands | None,
) -> list[str]:
    # Satu field tidak dapat dipecah lintas baris, jadi setiap catatan dibuat ringkas dan
    # menempati item sendiri. Perintah lengkap tercatat di `run_manifest.json`.
    model = ["z=0 tanpa offset", "Shell-Thick (Mindlin)", "beban +Z = ke atas"]
    if bands is not None and bands.step is not None:
        model.append(f"tapper {bands.n_bands} seksi tebal")
    if material is None:
        model.append("TANPA material dan seksi (material.E kosong)")
    if loads:
        model.append("pile: area load" if load_mode == "area" else "pile: joint load")
        model.append("berat sendiri SelfWtMult=1" if self_weight else "tanpa berat sendiri")
    else:
        model.append("tanpa beban (jalankan pilecap-analyze)")
    periksa = (
        "PERIKSA saat impor pertama: tabel COMBINATION DEFINITIONS (ENVELOPE) belum tervalidasi"
        if loads
        else "-"
    )
    rows = [
        _row('Item="Project Name"', f"Data={_q((project_name or '(tanpa nama)')[:150])}"),
        _row('Item="Model Name"', f"Data={_q(f'pilecap-fem v{__version__}')}"),
        _row('Item="Model Description"', f"Data={_q('; '.join(model))}"),
        _row('Item="Revision Number"', f"Data={_q(now.isoformat(timespec='seconds'))}"),
        _row('Item="Issue Code"', f"Data={_q(periksa)}"),
    ]
    return _table("PROJECT INFORMATION", rows)


def write_s2k(
    path: Path,
    geom: GeometryModel,
    mesh: MeshModel,
    material: MaterialProperties | None,
    *,
    project_name: str = "",
    fc_pa: float | None = None,
    loads: Mapping[str, Mapping[str, float]] | None = None,
    load_mode: str = "area",
    pile_modeling: str = "pressure",
    self_weight: bool = False,
    bands: ThicknessBands | None = None,
    now: datetime | None = None,
) -> Path:
    """Tulis model ke berkas teks SAP2000 `.s2k`.

    `loads` memetakan nama kombinasi -> `{pile_id: Pz [N]}`; `None` = geometri, seksi, grup,
    dan tumpuan saja (itulah yang ditulis `pilecap-mesh`). `load_mode` memilih `area` atau
    `joint` (`config.S2K_LOAD_MODES`); `pile_modeling` adalah `pile.modeling` config, dipakai
    hanya oleh mode `joint` agar gaya nodalnya sama persis dengan model OpenSees.
    """
    from pilecap_fem.fem_engine import fixed_support_nodes, make_load_strategy, pile_pressures

    if load_mode not in config.S2K_LOAD_MODES:
        raise ValueError(f"load_mode = {load_mode!r}; pilihan: {config.S2K_LOAD_MODES}")
    combos = list(loads) if loads else []
    mat_name = f"FC{fc_pa * 1e-6:.0f}" if fc_pa else "BETON"
    tables: dict[str, list[str]] = {}

    tables["ACTIVE DEGREES OF FREEDOM"] = _table(
        "ACTIVE DEGREES OF FREEDOM",
        [_row("UX=Yes", "UY=Yes", "UZ=Yes", "RX=Yes", "RY=Yes", "RZ=Yes")],
    )
    if material is not None:
        for line_block in (
            _material_tables(material, fc_pa, mat_name),
            _section_tables(mesh, material, bands, mat_name),
        ):
            _merge(tables, line_block)

    conn = _ccw_connectivity(mesh)
    tables["CONNECTIVITY - AREA"] = _table(
        "CONNECTIVITY - AREA",
        [
            _row(f"Area={int(tag)}", *(f"Joint{k + 1}={int(n)}" for k, n in enumerate(nodes)))
            for tag, nodes in zip(mesh.elem_tags, conn, strict=True)
        ],
    )
    tables["GROUPS 1 - DEFINITIONS"] = _table(
        "GROUPS 1 - DEFINITIONS",
        [_row(f"GroupName={_q(name)}", *_GROUP_FLAGS) for name in mesh.group_names],
    )
    tables["GROUPS 2 - ASSIGNMENTS"] = _table(
        "GROUPS 2 - ASSIGNMENTS",
        [
            _row(f"GroupName={_q(name)}", "ObjectType=Area", f"ObjectLabel={int(tag)}")
            for name in mesh.group_names
            for tag in mesh.elem_tags[mesh.group_mask(name)]
        ],
    )
    tables["JOINT COORDINATES"] = _table(
        "JOINT COORDINATES",
        [
            _row(
                f"Joint={int(tag)}",
                "CoordSys=GLOBAL",
                "CoordType=Cartesian",
                f"XorR={_num(float(x))}",
                f"Y={_num(float(y))}",
                "Z=0",
                "SpecialJt=No",
            )
            for tag, (x, y) in zip(mesh.node_tags, mesh.node_xy, strict=True)
        ],
    )
    jepit = fixed_support_nodes(mesh, geom)
    tables["JOINT RESTRAINT ASSIGNMENTS"] = _table(
        "JOINT RESTRAINT ASSIGNMENTS",
        [_row(f"Joint={int(mesh.node_tags[n])}", *(f"{d}=Yes" for d in _DOFS)) for n in jepit],
    )

    if loads:
        names = {c: _q(c) for c in combos}
        tables["LOAD PATTERN DEFINITIONS"] = _table(
            "LOAD PATTERN DEFINITIONS",
            [
                _row(
                    f"LoadPat={names[c]}",
                    "DesignType=Other",
                    f"SelfWtMult={1 if self_weight else 0}",
                )
                for c in combos
            ],
        )
        tables["LOAD CASE DEFINITIONS"] = _table(
            "LOAD CASE DEFINITIONS",
            [
                _row(
                    f"Case={names[c]}",
                    "Type=LinStatic",
                    "InitialCond=Zero",
                    'DesTypeOpt="Prog Det"',
                    "DesignType=Other",
                    'DesActOpt="Prog Det"',
                    "DesignAct=Other",
                    "AutoType=None",
                    "RunCase=Yes",
                )
                for c in combos
            ],
        )
        tables["CASE - STATIC 1 - LOAD ASSIGNMENTS"] = _table(
            "CASE - STATIC 1 - LOAD ASSIGNMENTS",
            [
                _row(
                    f"Case={names[c]}",
                    'LoadType="Load pattern"',
                    f"LoadName={names[c]}",
                    "LoadSF=1",
                )
                for c in combos
            ],
        )
        # Envelope, BUKAN penjumlahan: kombinasi di `pile_reactions.csv` sudah terfaktor.
        envelope = []
        for k, c in enumerate(combos):
            kepala = (
                [f"ComboName={ENVELOPE_NAME}", "ComboType=Envelope", "AutoDesign=No"]
                if k == 0
                else [f"ComboName={ENVELOPE_NAME}"]
            )
            envelope.append(
                _row(*kepala, 'CaseType="Linear Static"', f"CaseName={names[c]}", "ScaleFactor=1")
            )
        tables["COMBINATION DEFINITIONS"] = _table("COMBINATION DEFINITIONS", envelope)

        if load_mode == "area":
            rows = []
            for c in combos:
                for load in pile_pressures(mesh, geom, dict(loads[c])):
                    p = _num(load.pressure * _PA_TO_KN_PER_M2)
                    rows += [
                        _row(
                            f"Area={int(mesh.elem_tags[i])}",
                            f"LoadPat={names[c]}",
                            "CoordSys=GLOBAL",
                            "Dir=Z",
                            f"UnifLoad={p}",
                        )
                        for i in load.element_index
                    ]
            tables["AREA LOADS - UNIFORM"] = _table("AREA LOADS - UNIFORM", rows)
        else:
            strategi = make_load_strategy(pile_modeling)
            rows = []
            for c in combos:
                gaya, _ = strategi.apply(mesh, geom, dict(loads[c]))
                for i in np.flatnonzero(gaya):
                    rows.append(
                        _row(
                            f"Joint={int(mesh.node_tags[i])}",
                            f"LoadPat={names[c]}",
                            "CoordSys=GLOBAL",
                            "F1=0",
                            "F2=0",
                            f"F3={_num(float(gaya[i]) * _N_TO_KN)}",
                            "M1=0",
                            "M2=0",
                            "M3=0",
                        )
                    )
            tables["JOINT LOADS - FORCE"] = _table("JOINT LOADS - FORCE", rows)

    tables["PROGRAM CONTROL"] = _table(
        "PROGRAM CONTROL",
        [_row("ProgramName=SAP2000", "Version=24.2.0", f'CurrUnits="{S2K_UNITS}"')],
    )
    tables["PROJECT INFORMATION"] = _project_information(
        project_name=project_name,
        now=now or datetime.now(),
        material=material,
        loads=loads,
        load_mode=load_mode,
        self_weight=self_weight,
        bands=bands,
    )

    # Urutan alfabetis nama tabel, seperti berkas yang diekspor SAP2000 sendiri.
    lines = [f"File {path.name} was saved by pilecap-fem v{__version__}", " "]
    for name in sorted(tables):
        lines += tables[name]
    lines.append("END TABLE DATA")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _log.info(
        "%s ditulis: %d joint, %d area, %d grup, %d kombinasi (beban %s)",
        path.name,
        mesh.n_nodes,
        mesh.n_elements,
        len(mesh.group_names),
        len(combos),
        load_mode if combos else "-",
    )
    return path


_DOFS = ("U1", "U2", "U3", "R1", "R2", "R3")


def _merge(tables: dict[str, list[str]], block: list[str]) -> None:
    """Pecah blok baris `_table(...)` berurutan menjadi entri per nama tabel."""
    nama: str | None = None
    for line in block:
        if line.startswith("TABLE:"):
            nama = line.split('"')[1]
            tables[nama] = [line]
        elif nama is not None:
            tables[nama].append(line)


__all__ = ["ENVELOPE_NAME", "S2K_UNITS", "SECTION_UNIFORM", "write_s2k"]
