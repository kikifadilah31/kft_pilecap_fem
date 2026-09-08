"""Bab-bab dokumen yang digerakkan data: sampul, ringkasan, input, per kombinasi,
envelope, keterbatasan, tanggung jawab, dan lampiran provenance.

Seluruh angka di sini berasal dari `ReportData` apa adanya. Tidak ada satu pun besaran
rekayasa yang dihitung ulang -- lihat aturan modul di `__init__.py`.

Satuan SELALU diambil dari `io_utils.display_unit`, tidak pernah diketik sebagai literal
(PRD Bagian 9.2). Dijaga `test_sumber_reporting_pdf_tidak_mengetik_satuan_sebagai_literal`.
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np

from pilecap_fem import __version__, capacity_engine, config, io_utils, postproc_engine, reporter
from pilecap_fem.reporting_pdf import typst_kit as tk
from pilecap_fem.reporting_pdf.figures import FigureStore
from pilecap_fem.reporting_pdf.model import ReportData

__all__ = [
    "appendix_provenance",
    "chapter_combos",
    "chapter_envelope",
    "chapter_input",
    "chapter_limitations",
    "chapter_responsibility",
    "chapter_summary",
    "cover",
    "outline",
]

_UNSET = "-"


# ---------------------------------------------------------------------------
# Bantuan format
# ---------------------------------------------------------------------------


def _disp(value: float, quantity: str, spec: str = ",.2f") -> str:
    """Nilai SI -> satuan tampilan, diformat. `NaN` menjadi tanda hubung."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return _UNSET
    return format(io_utils.to_display(float(value), quantity), spec)


def _unit(quantity: str) -> str:
    return io_utils.display_unit(quantity)


def _loc(mesh: Any, index: int) -> str:
    """Lokasi elemen sebagai `elem <tag> (x, y)` dalam satuan panjang tampilan."""
    x, y = mesh.elem_centroid[index]
    return (
        f"elem {int(mesh.elem_tags[index])} "
        f"({_disp(x, 'length', ',.0f')}, {_disp(y, 'length', ',.0f')})"
    )


def _md(text: str) -> str:
    return tk.from_markdown(text)


_HEADING_MD = re.compile(r"^\s{0,3}#{1,6}\s")


def _md_body(text: str) -> str:
    """Konversi satu BAGIAN calc sheet, tanpa heading bawaannya.

    `reporter.overlap_block`, `stirrup_section`, `capacity_provenance_table`, dan
    `traceability_block` dirancang untuk ditempel ke `calc_sheet.md`, sehingga masing-
    masing membawa heading bernomor sendiri (`### 3a.`, `## 7b.`, dan seterusnya).
    Penomoran bab PDF dibangun `document.py`, dan menyisipkan heading calc sheet ke
    dalamnya akan merusak urutannya.

    Heading itu dibuang **di sini, secara sengaja dan terbatas pada blok ini** -- bukan oleh
    konverter, yang tetap menolak heading tak terduga di prosa mana pun.
    """
    isi = [baris for baris in text.splitlines() if not _HEADING_MD.match(baris)]
    return tk.from_markdown("\n".join(isi))


# ---------------------------------------------------------------------------
# Sampul & daftar isi
# ---------------------------------------------------------------------------


def cover(data: ReportData) -> str:
    """Halaman sampul: identitas proyek, provenance run, dan disclaimer."""
    block = data.block
    nama = data.project_name or "(tanpa nama proyek)"
    baris = [
        ["Proyek", nama],
        ["Engineer", block.engineer or _UNSET],
        ["Tanggal", block.date or _UNSET],
        ["Folder keluaran", f"`{data.run_name}`"],
        ["Perintah", f"`{data.command}`"],
        ["Versi perangkat lunak", f"pilecap-fem v{__version__}"],
        ["Waktu analisis", str(data.manifest.get("timestamp", _UNSET))],
        ["Sistem satuan internal", config.SI_UNIT_SYSTEM],
        ["Status analisis", str(data.manifest.get("status", _UNSET))],
        ["Basis desain tulangan", f"`{data.rebar_basis}`"],
    ]
    bagian = [
        "#align(center)[",
        "  #v(3cm)",
        '  #text(size: 20pt, weight: "bold")[LAPORAN ANALISIS PILECAP]',
        "  #v(4mm)",
        f"  #text(size: 13pt)[{tk.esc(nama)}]",
        "  #v(2mm)",
        '  #text(size: 10pt, style: "italic")[Analisis pelat lentur dengan metode elemen'
        " hingga; desain penampang menurut SNI 2847:2019]",
        "]",
        "#v(1.4cm)",
        tk.table(["Keterangan", "Nilai"], baris),
        "#v(8mm)",
        tk.callout("CAUTION", _md(reporter.disclaimer_block()), title="TANGGUNG JAWAB"),
    ]
    if block.warnings:
        peringatan = "\n\n".join(_md(w) for w in block.warnings)
        bagian += ["#v(4mm)", tk.callout("WARNING", peringatan, title="PERINGATAN GEOMETRI")]
    bagian.append(tk.pagebreak())
    return "\n\n".join(bagian)


def outline() -> str:
    return "\n\n".join(
        [
            "#outline(title: [Daftar Isi], depth: 2)",
            tk.pagebreak(),
            "#outline(title: [Daftar Gambar], target: figure.where(kind: image))",
            "#outline(title: [Daftar Tabel], target: figure.where(kind: table))",
            tk.pagebreak(),
        ]
    )


# ---------------------------------------------------------------------------
# Bab 1 -- ringkasan eksekutif
# ---------------------------------------------------------------------------


def chapter_summary(data: ReportData) -> str:
    """Ringkasan eksekutif.

    Peringatan deep pilecap dan catatan pons SELALU mendahului tabel `As`
    (PRD Bagian 8.3 keterbatasan #1). Peringatan yang baru terbaca setelah angka
    tercetak sudah terlambat.
    """
    bagian = [tk.heading(1, "Ringkasan eksekutif", label="bab-ringkasan")]

    bagian.append(
        _md(
            f"Dokumen ini menyajikan hasil analisis pilecap "
            f"**{data.project_name or '(tanpa nama)'}** terhadap {len(data.combo_rows)} "
            f"kombinasi beban menggunakan model pelat lentur berbasis metode elemen hingga. "
            f"Angka desain tulangan ditentukan dengan basis `{data.rebar_basis}`, "
            f"sebagaimana diuraikan pada bab [Dasar teori](#bab-teori)."
        )
    )

    bagian.append(tk.heading(2, "Hasil per kombinasi"))
    baris = [
        [
            r["combo"],
            f"{r['sum_pz_kN']:,.2f}",
            f"{r['max_abs_m_xx_kNm_per_m']:,.2f}",
            f"{r['max_abs_m_yy_kNm_per_m']:,.2f}",
            f"{r['max_deflection_mm']:,.3f}",
            r["vc0"],
        ]
        for r in data.combo_rows
    ]
    bagian.append(
        tk.table(
            [
                "Kombinasi",
                f"Sigma Pz [{_unit('force')}]",
                f"maks abs m_x [{_unit('moment_per_width')}]",
                f"maks abs m_y [{_unit('moment_per_width')}]",
                f"lendutan maks [{_unit('deflection')}]",
                "VC-0",
            ],
            baris,
            align=["left", "right", "right", "right", "right", "left"],
            caption="Ringkasan hasil analisis pada setiap kombinasi beban.",
        )
    )

    bagian.append(tk.heading(2, "Desain tulangan governing lintas kombinasi"))
    bagian.append(_md(reporter.deep_pilecap_warning(data.deep_ratio)))
    bagian.append(
        tk.callout(
            "IMPORTANT",
            _md(
                "**Kapasitas geser pons tidak dihitung** dalam dokumen ini dan berstatus "
                f"`{postproc_engine.CAPACITY_NOT_EVALUATED}`, karena pasal acuannya belum "
                "dikonfirmasi. Yang disajikan hanya gaya geser yang bekerja."
            ),
        )
    )
    bagian.append(_governing_table(data))

    if data.warnings:
        bagian.append(tk.heading(2, "Peringatan selama proses analisis"))
        # Isi `data.warnings` adalah pesan log operasional, ditulis untuk operator yang
        # menjalankan analisis dan bukan sebagai prosa laporan. Pesan itu WAJIB tetap
        # tampil -- menyembunyikan peringatan bertentangan dengan PRD Bagian 1.3 -- tetapi
        # pembaca harus tahu bahwa yang dikutip adalah keluaran log, bukan temuan rekayasa
        # yang sudah dirumuskan. Karena itu diberi pengantar dan dicetak sebagai kutipan.
        bagian.append(
            _md(
                "Pesan berikut tercatat selama proses analisis dan pelaporan. Pesan "
                "dikutip apa adanya dari catatan proses, sehingga penulisannya mengikuti "
                "format teknis perangkat lunak."
            )
        )
        bagian.append(tk.callout("WARNING", "\n\n".join(_md(f"- {w}") for w in data.warnings)))

    bagian.append(tk.heading(2, "Peninjauan yang tidak tercakup"))
    bagian.append(
        _md(
            "Peninjauan berikut tidak dilakukan dalam dokumen ini dan wajib diselesaikan "
            "secara terpisah oleh engineer yang bertanggung jawab.\n\n"
            "- Kapasitas geser pons; hanya gaya geser yang bekerja yang dihitung.\n"
            "- Penetapan perilaku *deep pile cap*; rasio `a/d` disajikan tanpa kesimpulan.\n"
            "- Momen desain menurut metode Wood-Armer; belum tersedia.\n"
            "- Kapasitas strut pada pile yang tumpang tindih dengan pier.\n"
            "- Kekakuan pile, gaya lateral `Hx` dan `Hy`, serta momen pada kepala pile."
        )
    )
    bagian.append(tk.pagebreak())
    return "\n\n".join(bagian)


def _governing_table(data: ReportData) -> str:
    rows = data.rebar_governing
    if not rows:
        return _md("_(tidak terdapat baris governing yang dapat dilaporkan)_")

    basis_elemen = data.rebar_basis == "element"
    header = [
        "Arah",
        "Muka",
        "Kombinasi",
        f"Mu [{_unit('moment_per_width')}]",
        f"d [{_unit('length')}]",
        f"As perlu [{_unit('steel_area')}]",
        f"As pakai [{_unit('steel_area')}]",
        "Lokasi" if basis_elemen else "Lajur",
    ]
    baris = []
    for r in rows:
        baris.append(
            [
                r["direction"].upper(),
                r["face"],
                r.get("combo", _UNSET),
                _disp(r.get("Mu_per_m_Nm", float("nan")), "moment_per_width"),
                _disp(r.get("d_eff_m", float("nan")), "length", ",.0f"),
                _disp(r.get("As_required_m2_per_m", float("nan")), "steel_area", ",.0f"),
                _disp(r.get("As_design_m2_per_m", float("nan")), "steel_area", ",.0f"),
                reporter.lokasi_governing(r, basis_elemen=basis_elemen),
            ]
        )
    return tk.table(
        header,
        baris,
        align=["left", "left", "left", "right", "right", "right", "right", "left"],
        caption="Tulangan lentur governing dari seluruh kombinasi beban.",
    )


# ---------------------------------------------------------------------------
# Bab 3 -- data masukan
# ---------------------------------------------------------------------------


def chapter_input(data: ReportData, figs: FigureStore) -> str:
    geom, mesh, cfg = data.geom, data.mesh, data.cfg
    inputs = data.capacity_inputs
    stats = data.manifest.get("model_stats") or {}
    bagian = [tk.heading(1, "Data masukan", label="bab-masukan")]

    # -- provenance & hash --------------------------------------------------
    bagian.append(tk.heading(2, "Provenance run"))
    dep = data.manifest.get("dependencies") or {}
    bagian.append(
        tk.table(
            ["Keterangan", "Nilai"],
            [
                ["Versi tool", f"pilecap-fem v{data.manifest.get('tool_version', _UNSET)}"],
                ["Python", str(data.manifest.get("python", _UNSET))],
                ["Platform", str(data.manifest.get("platform", _UNSET))],
                ["Waktu", str(data.manifest.get("timestamp", _UNSET))],
                ["Perintah", f"`{data.command}`"],
            ],
            caption="Identitas run.",
        )
    )
    if dep:
        bagian.append(
            tk.table(
                ["Dependency", "Versi"],
                [[k, str(v)] for k, v in sorted(dep.items())],
                caption="Versi pustaka yang digunakan pada saat analisis dijalankan.",
            )
        )

    berkas = data.manifest.get("inputs") or {}
    if berkas:
        bagian.append(
            tk.table(
                ["Berkas input", "sha256"],
                [
                    [f"`{k}`", io_utils.short_hash(str(v).removeprefix("sha256:"))]
                    for k, v in sorted(berkas.items())
                ],
                caption="Nilai hash berkas masukan sebagai dasar keterulangan hasil.",
            )
        )

    # -- resolusi geometri --------------------------------------------------
    bagian.append(tk.heading(2, "Resolusi sumber geometri"))
    bagian.append(_md(reporter.geometry_resolution_table(geom.resolution)))

    # -- geometri -----------------------------------------------------------
    bagian.append(tk.heading(2, "Geometri"))
    bagian.append(
        tk.table(
            ["Besaran", "Nilai"],
            [
                ["Luas pilecap", f"{geom.pilecap.area:.6f} {_unit('area')}"],
                [
                    "Tebal pilecap `t`",
                    f"{_disp(geom.thickness, 'length', ',.0f')} {_unit('length')}",
                ],
                ["Jumlah pile", str(geom.n_piles)],
                ["Jumlah pier", str(geom.n_piers)],
            ],
            caption="Dimensi utama pilecap.",
        )
    )
    bagian.append(
        tk.table(
            ["Pile", f"x [{_unit('length')}]", f"y [{_unit('length')}]", f"D [{_unit('length')}]"],
            [
                [
                    p.pile_id,
                    _disp(p.x, "length", ",.0f"),
                    _disp(p.y, "length", ",.0f"),
                    _disp(p.diameter, "length", ",.0f"),
                ]
                for p in geom.piles
            ],
            align=["left", "right", "right", "right"],
            caption="Koordinat dan diameter setiap pile.",
        )
    )
    bagian.append(
        tk.table(
            [
                "Pier",
                "Bentuk",
                f"Centerline x [{_unit('length')}]",
                f"Centerline y [{_unit('length')}]",
            ],
            [
                [
                    pr.pier_id,
                    str(getattr(pr.shape, "value", pr.shape)),
                    _disp(pr.centerline[0], "length", ",.0f"),
                    _disp(pr.centerline[1], "length", ",.0f"),
                ]
                for pr in geom.piers
            ],
            align=["left", "left", "right", "right"],
            caption="Geometri pier dan titik acuannya.",
        )
    )
    bagian.append(
        figs.resolve(
            data.model_dir / config.FILE_MESH_PLAN,
            "Denah mesh: pilecap, pile, dan pier.",
            reason="dihasilkan `pilecap-mesh`.",
            from_earlier_phase=True,
        ).to_typst()
    )

    # -- material & asumsi desain ------------------------------------------
    bagian.append(tk.heading(2, "Material dan asumsi desain"))
    material = cfg.get("material") or {}
    prov = capacity_engine.provenance_block(inputs)
    bagian.append(
        tk.table(
            ["Besaran", "Nilai", "Sumber"],
            [
                ["f'c", f"{inputs.fc_mpa:,.0f} {_unit('stress')}", _UNSET],
                ["fy", f"{inputs.fy_mpa:,.0f} {_unit('stress')}", str(inputs.fy_source)],
                [
                    "E",
                    f"{io_utils.to_display(float(material.get('E', 0.0)), 'stress'):,.1f}"
                    f" {_unit('stress')}",
                    str(material.get("E_source", _UNSET)),
                ],
                ["Rasio Poisson `nu`", f"{float(material.get('poisson', 0.0)):.3f}", _UNSET],
                ["Selimut", f"{inputs.cover_mm:,.0f} {_unit('length')}", _UNSET],
                ["phi lentur", f"{inputs.phi_flexure:.2f}", str(inputs.phi_source)],
                ["phi geser", f"{inputs.phi_shear:.2f}", str(inputs.phi_source)],
                ["Mode tulangan", f"`{inputs.rebar_mode}`", _UNSET],
                ["Basis angka desain", f"`{data.rebar_basis}`", _UNSET],
            ],
            caption="Parameter material dan desain beserta sumber penetapannya.",
        )
    )
    catatan = [prov.get("catatan_dv"), prov.get("catatan_as_min"), prov.get("catatan_pons")]
    tersedia = [c for c in catatan if c]
    if tersedia:
        bagian.append(tk.callout("NOTE", "\n\n".join(_md(str(c)) for c in tersedia)))

    # -- pembebanan ---------------------------------------------------------
    bagian.append(tk.heading(2, "Pembebanan"))
    bagian.append(
        _md(
            "Reaksi pile `Pz` berkedudukan sebagai **data masukan**, bukan sebagai hasil "
            "analisis. Reaksi tersebut diterapkan sebagai beban berarah ke atas pada cakram "
            "kepala pile, sedangkan tumpuan model ditempatkan pada pier. Karena besar beban "
            "telah diketahui, keseimbangan gaya dapat diperiksa secara eksak pada setiap "
            "eksekusi analisis melalui pemeriksaan VC-0."
        )
    )
    bagian.append(
        figs.resolve(
            data.model_dir / config.FILE_BOUNDARY_CHECK,
            "Cek visual tumpuan dan pembebanan.",
            reason="dihasilkan `pilecap-report`.",
        ).to_typst()
    )

    # -- mesh & model FEM ---------------------------------------------------
    bagian.append(tk.heading(2, "Mesh dan model FEM"))
    mesh_cfg = cfg.get("mesh") or {}
    bagian.append(
        tk.table(
            ["Besaran", "Nilai"],
            [
                ["Jenis elemen", str(stats.get("element_type", "ShellMITC4"))],
                ["Section", str(stats.get("section", "PlateFiber"))],
                ["Jumlah node", f"{len(mesh.node_tags):,}"],
                ["Jumlah elemen", f"{len(mesh.elem_tags):,}"],
                ["Node jepit (pier)", str(stats.get("n_fixed_nodes", _UNSET))],
                [
                    "Ukuran mesh global",
                    f"{_disp(data.mesh_size_m, 'length', ',.0f')} {_unit('length')}",
                ],
                ["Algoritma gmsh", str(mesh_cfg.get("algorithm", _UNSET))],
                [
                    "Kekakuan lentur `D`",
                    f"{float(stats.get('flexural_rigidity_Nm', float('nan'))):.6e} N.m",
                ],
            ],
            caption="Statistik model yang dianalisis.",
        )
    )
    bagian.append(
        figs.resolve(
            data.model_dir / config.FILE_MODEL_OPSVIS,
            "Model OpenSees: elemen, tumpuan, dan pembebanan.",
            reason=(
                "opsvis dilewati bila elemen melebihi "
                f"{config.OPSVIS_MAX_ELEMENTS:,}; jalankan ulang dengan `--opsvis`."
            ),
            from_earlier_phase=True,
        ).to_typst()
    )
    bagian.append(tk.pagebreak())
    return "\n\n".join(bagian)


# ---------------------------------------------------------------------------
# Bab per kombinasi
# ---------------------------------------------------------------------------


def chapter_combos(data: ReportData, figs: FigureStore) -> str:
    return "\n\n".join(_one_combo(data, figs, combo) for combo in data.calc_inputs_by_combo)


def _one_combo(data: ReportData, figs: FigureStore, combo: str) -> str:
    ci = data.calc_inputs_by_combo[combo]
    mesh = data.mesh
    bagian = [tk.heading(1, f"Kombinasi {combo}")]

    # -- ringkasan ----------------------------------------------------------
    idx_mx, val_mx = ci.results.extreme("m_xx")
    idx_my, val_my = ci.results.extreme("m_yy")
    row = next((r for r in data.combo_rows if r["combo"] == combo), {})
    bagian.append(
        tk.table(
            ["Besaran", "Nilai", "Lokasi"],
            [
                [
                    f"Sigma Pz [{_unit('force')}]",
                    f"{row.get('sum_pz_kN', float('nan')):,.2f}",
                    _UNSET,
                ],
                [
                    f"m_x magnitudo terbesar [{_unit('moment_per_width')}]",
                    _disp(val_mx, "moment_per_width"),
                    _loc(mesh, idx_mx),
                ],
                [
                    f"m_y magnitudo terbesar [{_unit('moment_per_width')}]",
                    _disp(val_my, "moment_per_width"),
                    _loc(mesh, idx_my),
                ],
                [
                    f"Lendutan maks [{_unit('deflection')}]",
                    f"{row.get('max_deflection_mm', float('nan')):,.3f}",
                    _UNSET,
                ],
                ["Status VC-0", str(ci.equilibrium.get("status", _UNSET)), _UNSET],
            ],
            align=["left", "right", "left"],
            caption=f"Ringkasan hasil kombinasi {combo}.",
        )
    )

    # -- keseimbangan -------------------------------------------------------
    bagian.append(tk.heading(2, "Pembebanan dan cek keseimbangan (VC-0)"))
    pile_rows = ci.equilibrium.get("pile_loads", [])
    if pile_rows:
        bagian.append(
            tk.table(
                [
                    "Pile",
                    f"Pz [{_unit('force')}]",
                    f"A_disk mesh [{_unit('area')}]",
                    f"p [{_unit('pressure')}]",
                    "n_elem",
                    f"Sigma(p.A_e) [{_unit('force')}]",
                ],
                [
                    [
                        r["pile_id"],
                        _disp(r["Pz_N"], "force"),
                        f"{r['A_disk_mesh_m2']:.6f}",
                        _disp(r["pressure_Pa"], "pressure"),
                        str(r["n_elements"]),
                        _disp(r["applied_total_N"], "force"),
                    ]
                    for r in pile_rows
                ],
                align=["left", "right", "right", "right", "right", "right"],
                caption=f"Penyaluran beban tiap pile pada kombinasi {combo}.",
            )
        )
    blok_overlap = reporter.overlap_block(ci.equilibrium)
    if blok_overlap.strip():
        # Heading Typst asli menggantikan `### 3a.` bawaan calc sheet yang dibuang
        # `_md_body` -- bukan sekadar dijatuhkan, supaya sub-bagian ini tetap punya entri
        # sendiri di Daftar Isi, sama seperti "Tulangan geser (sengkang)" di bawah.
        bagian.append(
            tk.heading(3, "Beban pile yang tidak melenturkan pelat (tumpang tindih dengan pier)")
        )
        bagian.append(_md_body(blok_overlap))

    # -- gaya dalam ---------------------------------------------------------
    bagian.append(tk.heading(2, "Gaya dalam"))
    ekstrem = []
    for field_, (_, quantity, judul) in config.CONTOUR_FIELDS.items():
        idx, val = ci.results.extreme(field_)
        ekstrem.append([judul, f"{_disp(val, quantity)} {_unit(quantity)}", _loc(mesh, idx)])
    bagian.append(
        tk.table(
            ["Besaran", "Magnitudo terbesar", "Lokasi"],
            ekstrem,
            align=["left", "right", "left"],
            caption=(
                "Nilai ekstrem tiap medan. Data lengkap per elemen ada di `element_resultants.csv`."
            ),
        )
    )
    kontur = [
        figs.resolve(
            ci.combo_dir / nama,
            f"{judul} -- kombinasi {combo}. Sumber angka: `element_resultants.csv`.",
            reason="kontur gaya selalu dibuat; ketiadaannya menandakan run terpotong.",
        )
        for nama, _, judul in config.CONTOUR_FIELDS.values()
    ]
    kontur.append(
        figs.resolve(
            ci.combo_dir / config.FILE_CONTOUR_DEFLECTION,
            f"Lendutan vertikal -- kombinasi {combo}.",
            reason="butuh `node_displacements.csv`; tidak ada bila dipakai `--no-save-raw`.",
        )
    )
    bagian.append(_grid(kontur))

    # -- rantai telusur -----------------------------------------------------
    bagian.append(tk.heading(2, "Rantai telusur satu elemen"))
    bagian.append(
        _md(
            "Satu elemen ditelusuri dari nilai pada titik Gauss hingga momen dalam sumbu "
            "global. Rantai perhitungan berikut memungkinkan pemeriksa melakukan "
            "perhitungan ulang secara mandiri tanpa menjalankan kembali analisis."
        )
    )
    bagian.append(_md_body(reporter.traceability_block(ci.trace)))

    # -- momen lajur --------------------------------------------------------
    bagian.append(tk.heading(2, "Momen desain per lajur"))
    if data.rebar_basis != "strip":
        bagian.append(
            tk.callout(
                "NOTE",
                _md(
                    "Analisis ini menggunakan `design.rebar_basis` = `element`, sehingga "
                    "prosedur integrasi lajur tidak dijalankan dan berkas "
                    "`strip_moments_*.csv` tidak dihasilkan. Angka desain diambil langsung "
                    "dari nilai momen tiap elemen."
                ),
            )
        )
    elif ci.strip_rows:
        bagian.append(
            tk.table(
                [
                    "Lokasi",
                    "Pier",
                    "Sisi",
                    "Arah",
                    "Lajur",
                    "n_elem",
                    f"M total [{_unit('moment')}]",
                    "Singular",
                ],
                [
                    [
                        r["lokasi"],
                        r["pier_id"],
                        r["sisi"],
                        r["direction"],
                        str(r["strip"]),
                        str(r["n_elements"]),
                        _disp(r["M_total_Nm"], "moment"),
                        "**SINGULAR**" if r["singular"] else _UNSET,
                    ]
                    for r in ci.strip_rows
                ],
                align=["left", "left", "left", "left", "right", "right", "right", "left"],
                caption=f"Momen lajur pada kombinasi {combo}. Rincian tersedia pada berkas "
                f"`strip_moments_*.csv`.",
            )
        )
    else:
        bagian.append(_md("_(tidak terdapat lajur yang dihitung)_"))

    # -- geser --------------------------------------------------------------
    bagian.append(tk.heading(2, "Geser"))
    if ci.shear_checks:
        bagian.append(
            tk.table(
                [
                    "Pier",
                    "Jenis",
                    f"d [{_unit('length')}]",
                    f"V_u [{_unit('force')}]",
                    "Status kapasitas",
                ],
                [
                    [
                        c.pier_id,
                        c.kind,
                        _disp(c.d_m, "length", ",.0f"),
                        _disp(c.V_u_N, "force"),
                        c.capacity_status,
                    ]
                    for c in ci.shear_checks
                ],
                align=["left", "left", "right", "right", "left"],
                caption=f"Gaya geser yang bekerja pada kombinasi {combo}. Rincian tersedia pada "
                f"berkas `shear_checks.csv`.",
            )
        )
    bagian.append(_md(reporter.one_way_section_outboard_note(data.deep_ratio)))
    bagian.append(
        tk.table(
            ["Besaran", "Nilai"],
            [
                ["`a/d` minimum", f"{data.deep_ratio['min_a_over_d']:.3f}"],
                ["Pada", str(data.deep_ratio["min_at"])],
                ["Vonis deep pile cap", str(data.deep_ratio["verdict"])],
            ],
            caption="Rasio bentang geser terhadap tinggi efektif, disajikan tanpa kesimpulan.",
        )
    )

    # -- lentur -------------------------------------------------------------
    bagian.append(tk.heading(2, "Desain tulangan lentur"))
    bagian.append(_md(reporter.deep_pilecap_warning(data.deep_ratio)))
    bagian.append(
        _md_body(
            reporter.capacity_provenance_table(
                capacity_engine.provenance_block(data.capacity_inputs)
            )
        )
    )
    bagian.append(_flexure_summary(data, ci))
    lentur = [
        figs.resolve(
            ci.combo_dir / nama,
            f"{judul} -- kombinasi {combo}.",
            reason="dilewati bila dipakai `--no-rebar-plots`.",
        )
        for nama, judul in config.REBAR_FACES.values()
    ]
    for (arah, muka), (nama, _) in config.REBAR_FACES.items():
        sel = ci.selections.get((arah, muka))
        if sel is None:
            continue
        berkas = nama.replace("contour_As_", f"contour_{sel.kind}_")
        lentur.append(
            figs.resolve(
                ci.combo_dir / berkas,
                f"{sel.kind.capitalize()} tulangan arah {arah.upper()} muka {muka}"
                f" -- kombinasi {combo}.",
                reason="dilewati bila dipakai `--no-rebar-plots`.",
            )
        )
    bagian.append(_grid(lentur))

    # -- sengkang -----------------------------------------------------------
    bagian.append(tk.heading(2, "Tulangan geser (sengkang)"))
    bagian.append(_md_body(reporter.stirrup_section(ci.shear_maps, data.capacity_inputs)))
    sengkang = []
    for _, avs, dia, label in config.SHEAR_REBAR_FIELDS.values():
        sengkang.append(
            figs.resolve(
                ci.combo_dir / avs,
                f"Av/s sengkang {label} -- kombinasi {combo}.",
                reason="dilewati bila dipakai `--no-rebar-plots`.",
            )
        )
        sengkang.append(
            figs.resolve(
                ci.combo_dir / dia,
                f"Diameter sengkang {label} -- kombinasi {combo}.",
                reason="dilewati bila dipakai `--no-rebar-plots`.",
            )
        )
    bagian.append(_grid(sengkang))

    # -- berkas rinci -------------------------------------------------------
    bagian.append(tk.heading(2, "Berkas data rinci"))
    bagian.append(
        _md(
            "Dokumen ini menyajikan nilai governing dan nilai ekstrem beserta lokasinya. "
            f"Data per elemen, yang mencakup {len(mesh.elem_tags):,} elemen, tidak dicetak "
            f"dan tersedia pada berkas berikut di dalam folder `{ci.combo_dir.name}`."
        )
    )
    berkas_rinci = [
        ["`element_resultants.csv`", "momen & geser tiap elemen, lokal dan global"],
        ["`rebar_design.csv`", "`As` perlu dan batang terpilih tiap elemen"],
        ["`shear_rebar.csv`", "`Av/s` dan diameter sengkang tiap elemen"],
        ["`shear_checks.csv`", "demand geser satu arah dan pons"],
        ["`equilibrium_check.json`", "rincian VC-0"],
        ["`traceability_sample.json`", "rantai telusur titik Gauss"],
        ["`calc_sheet.md`", "calc sheet lengkap kombinasi ini"],
    ]
    if data.rebar_basis == "strip":
        berkas_rinci.insert(3, ["`strip_moments_x.csv` / `_y.csv`", "momen tiap lajur"])
    bagian.append(tk.table(["Berkas", "Isi"], berkas_rinci))
    bagian.append(tk.pagebreak())
    return "\n\n".join(bagian)


def _flexure_summary(data: ReportData, ci: reporter.CalcSheetInputs) -> str:
    """Ringkasan `As` per arah x muka untuk satu kombinasi."""
    baris = []
    for (arah, muka), design in ci.designs.items():
        sel = ci.selections.get((arah, muka))
        baris.append(
            [
                arah.upper(),
                muka,
                _disp(design.as_governing, "steel_area", ",.0f"),
                _disp(float(design.as_min), "steel_area", ",.0f"),
                reporter.selection_range(sel) if sel is not None else _UNSET,
                str(design.n_inadequate),
            ]
        )
    return tk.table(
        [
            "Arah",
            "Muka",
            f"As maks [{_unit('steel_area')}]",
            f"As_min [{_unit('steel_area')}]",
            "Batang terpakai",
            "Elemen tidak memadai",
        ],
        baris,
        align=["left", "left", "right", "right", "left", "right"],
        caption=(
            "Ringkasan tulangan lentur pada kombinasi ini. Rincian per elemen tersedia pada "
            "berkas `rebar_design.csv`."
        ),
    )


def _grid(figures: list[Any]) -> str:
    """Dua gambar per baris -- memotong halaman sekaligus kebutuhan resolusi."""
    if not figures:
        return ""
    sel = ",\n".join(f"  [{f.to_typst(width='100%')}]" for f in figures)
    return f"#grid(\n  columns: 2,\n  gutter: 6pt,\n{sel},\n)"


# ---------------------------------------------------------------------------
# Bab envelope
# ---------------------------------------------------------------------------


def chapter_envelope(data: ReportData, figs: FigureStore) -> str:
    bagian = [tk.heading(1, "Envelope lintas kombinasi", label="bab-envelope")]
    if data.envelope is None:
        bagian.append(
            tk.callout(
                "NOTE",
                _md(
                    "Envelope tidak dibentuk pada analisis ini karena opsi `--no-envelope` "
                    "digunakan. Jalankan ulang pelaporan tanpa opsi tersebut apabila "
                    "envelope diperlukan."
                ),
            )
        )
        bagian.append(tk.pagebreak())
        return "\n\n".join(bagian)

    env = data.envelope
    bagian.append(
        tk.callout(
            "WARNING",
            _md(
                "**Envelope bukan merupakan satu kondisi keseimbangan.** Nilai pada setiap "
                "lokasi dapat berasal dari kombinasi beban yang berbeda, sehingga envelope "
                "**tidak boleh digunakan** untuk pemeriksaan keseimbangan statika. "
                "Kombinasi penentu pada setiap lokasi dicantumkan dalam berkas "
                "`envelope_values.csv`."
            ),
        )
    )

    baris = []
    for field_ in config.CONTOUR_FIELDS:
        fe = env.fields[field_]
        quantity = config.CONTOUR_FIELDS[field_][1]
        i_max = int(np.nanargmax(fe.max_values))
        i_min = int(np.nanargmin(fe.min_values))
        baris.append(
            [
                field_,
                f"{_disp(float(fe.max_values[i_max]), quantity)} {_unit(quantity)}",
                env.combo_name(int(fe.max_combo_index[i_max])),
                f"{_disp(float(fe.min_values[i_min]), quantity)} {_unit(quantity)}",
                env.combo_name(int(fe.min_combo_index[i_min])),
            ]
        )
    bagian.append(
        tk.table(
            ["Medan", "Maks", "Kombinasi penentu", "Min", "Kombinasi penentu"],
            baris,
            align=["left", "right", "left", "right", "left"],
            caption="Nilai ekstrem envelope beserta kombinasi beban penentunya.",
        )
    )

    gaya = []
    for base, _quantity, judul in config.CONTOUR_FIELDS.values():
        stem = base.replace("contour_", "envelope_").replace(".png", "")
        for which in ("max", "min"):
            gaya.append(
                figs.resolve(
                    data.envelope_dir / f"{stem}_{which}.png",
                    f"Envelope {which} -- {judul}.",
                    reason="dilewati bila dipakai `--no-envelope`.",
                )
            )
    bagian.append(tk.heading(2, "Envelope gaya dalam"))
    bagian.append(_grid(gaya))

    bagian.append(tk.heading(2, "Envelope tulangan lentur"))
    bagian.append(_md(reporter.deep_pilecap_warning(data.deep_ratio)))
    alasan = "dilewati bila dipakai `--no-rebar-plots` atau `--no-envelope`."
    tulangan = [
        figs.resolve(
            data.envelope_dir / nama.replace("contour_", "envelope_"),
            f"Envelope -- {judul}.",
            reason=alasan,
        )
        for nama, judul in config.REBAR_FACES.values()
    ]
    # Peta batang terpilih ikut ditampilkan, sama seperti pada bab per kombinasi. Tanpa
    # ini pembaca melihat `As` envelope tetapi tidak melihat batang apa yang memenuhinya,
    # padahal berkasnya sudah dihasilkan dan tinggal dirujuk.
    for kind in _selection_kinds(data):
        for nama, _judul in config.REBAR_FACES.values():
            berkas = nama.replace("contour_As_", f"envelope_{kind}_")
            arah, muka = _arah_muka(nama)
            tulangan.append(
                figs.resolve(
                    data.envelope_dir / berkas,
                    f"Envelope -- {kind.capitalize()} tulangan arah {arah} muka {muka}.",
                    reason=alasan,
                )
            )
    bagian.append(_grid(tulangan))

    bagian.append(tk.heading(2, "Envelope tulangan geser"))
    sengkang = []
    for _, avs, dia, label in config.SHEAR_REBAR_FIELDS.values():
        sengkang.append(
            figs.resolve(
                data.envelope_dir / avs.replace("contour_", "envelope_"),
                f"Envelope -- Av/s sengkang {label}.",
                reason=alasan,
            )
        )
        sengkang.append(
            figs.resolve(
                data.envelope_dir / dia.replace("contour_", "envelope_"),
                f"Envelope -- diameter sengkang {label}.",
                reason=alasan,
            )
        )
    bagian.append(_grid(sengkang))
    bagian.append(tk.pagebreak())
    return "\n\n".join(bagian)


def _selection_kinds(data: ReportData) -> list[str]:
    """Jenis peta batang terpilih yang benar-benar dihasilkan run ini.

    Diambil dari `RebarSelection` yang sudah dipakai bab per kombinasi, bukan diturunkan
    ulang dari `rebar_mode`: nama berkasnya dibentuk dari `selection.kind` yang sama,
    sehingga menebaknya di sini berisiko merujuk berkas yang tidak pernah ditulis.
    """
    for ci in data.calc_inputs_by_combo.values():
        jenis = {sel.kind for sel in ci.selections.values()}
        if jenis:
            return sorted(jenis)
    return []


def _arah_muka(nama_berkas: str) -> tuple[str, str]:
    """`contour_As_x_bawah.png` -> ("X", "bawah")."""
    bagian = nama_berkas.removesuffix(".png").split("_")
    return bagian[-2].upper(), bagian[-1]


# ---------------------------------------------------------------------------
# Keterbatasan, tanggung jawab, lampiran
# ---------------------------------------------------------------------------


def chapter_limitations(*, no_rebar_plots: bool = False, no_envelope: bool = False) -> str:
    """Asumsi dan keterbatasan.

    Tidak menerima `ReportData`: seluruh isinya statis (`config.KNOWN_LIMITATIONS`,
    `reporter.open_blockers_block()`) kecuali catatan opsi yang dilewati. Karena itu bab
    ini dapat dipakai apa adanya oleh panduan mandiri, yang tidak punya run sama sekali --
    dan `chapter_theory` memang merujuk ke sini lewat label `bab-keterbatasan`.
    """
    bagian = [
        tk.heading(1, "Asumsi dan keterbatasan", label="bab-keterbatasan"),
        _md(
            "Bagian ini dikutip tanpa perubahan dari dokumen acuan perangkat lunak dan "
            "berlaku bagi seluruh angka yang disajikan dalam dokumen ini."
        ),
        _md(config.KNOWN_LIMITATIONS),
        tk.heading(2, "Item yang belum dikonfirmasi"),
        _md(reporter.open_blockers_block()),
    ]
    if no_rebar_plots or no_envelope:
        dilewati = []
        if no_rebar_plots:
            dilewati.append("`--no-rebar-plots`: seluruh gambar tulangan tidak dihasilkan")
        if no_envelope:
            dilewati.append("`--no-envelope`: bab envelope tidak berisi hasil")
        bagian.append(
            tk.callout(
                "NOTE",
                _md(
                    "Pelaporan ini dijalankan dengan opsi yang mengurangi kelengkapan "
                    "dokumen sebagai berikut.\n\n" + "\n".join(f"- {d}" for d in dilewati)
                ),
            )
        )
    bagian.append(tk.pagebreak())
    return "\n\n".join(bagian)


def chapter_responsibility(data: ReportData) -> str:
    block = data.block
    return "\n\n".join(
        [
            tk.heading(1, "Pernyataan tanggung jawab", label="bab-tanggung-jawab"),
            _md(reporter.disclaimer_block()),
            tk.heading(2, "Pengesahan"),
            tk.table(
                ["Peran", "Nama", "Tanggal", "Tanda tangan"],
                [
                    ["Dibuat oleh", block.engineer or "", block.date or "", ""],
                    ["Diperiksa oleh", "", "", ""],
                    ["Disetujui oleh", "", "", ""],
                ],
                caption="Dokumen ini belum berlaku sebelum ditandatangani oleh engineer "
                "yang berwenang.",
            ),
            tk.pagebreak(),
        ]
    )


def appendix_provenance(data: ReportData) -> str:
    prov = capacity_engine.provenance_block(data.capacity_inputs)
    bagian = [
        tk.heading(1, "Lampiran A -- Provenance kapasitas", label="lampiran-provenance"),
        tk.table(
            ["Keterangan", "Nilai"],
            [
                ["Engine", str(prov.get("engine", _UNSET))],
                ["Versi engine", str(prov.get("engine_version", _UNSET))],
                ["Standar", str(prov.get("standard", _UNSET))],
                ["phi lentur", f"{prov.get('phi_flexure', float('nan')):.2f}"],
                ["phi geser", f"{prov.get('phi_shear', float('nan')):.2f}"],
                ["Sumber phi", str(prov.get("phi_source", _UNSET))],
                ["fy", f"{prov.get('fy_MPa', float('nan')):,.0f} {_unit('stress')}"],
                ["Sumber fy", str(prov.get("fy_source", _UNSET))],
            ],
            caption="Sumber perhitungan kapasitas menurut SNI 2847:2019.",
        ),
    ]
    fungsi = prov.get("functions") or []
    if fungsi:
        bagian.append(
            tk.table(
                ["Fungsi shell-kit yang benar-benar dipanggil"],
                [[f"`{f}`"] for f in fungsi],
            )
        )
    pasal = prov.get("clauses") or {}
    if pasal:
        bagian.append(
            tk.table(
                ["Besaran", "Pasal"],
                [[f"`{k}`", str(v)] for k, v in sorted(pasal.items())],
                caption="Pasal SNI 2847:2019 yang diterapkan dalam perhitungan kapasitas.",
            )
        )
    bagian.append(
        _md(
            f"Berkas sumber dokumen ini disimpan sebagai `{config.FILE_PDF_SOURCE}` pada "
            "folder keluaran yang sama, sehingga isinya dapat diperiksa dan "
            "dibandingkan antaranalisis."
        )
    )
    return "\n\n".join(bagian)
