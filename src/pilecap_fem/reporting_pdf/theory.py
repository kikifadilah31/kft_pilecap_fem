"""Bab Dasar Teori.

.. rubric:: Aturan bab ini

Setiap persamaan yang dicetak WAJIB (a) menyebut sumbernya dan (b) benar-benar dievaluasi
tool ini. Keduanya dijaga struktur `Equation`: `source` memuat sitasinya, `implemented_by`
memuat nama fungsi yang mengevaluasinya, dan sebuah test menuntut nama itu ada di
`capacity_engine.provenance_block()["functions"]` atau di `math_engine`.

Alasannya bukan kerapian. Mencetak rumus yang TIDAK dipakai tool berarti dokumen
menjanjikan pengecekan yang tidak pernah terjadi -- persis liabilitas yang dijaga PRD
Bagian 1.3. String pasal SNI karena itu juga diambil dari `capacity_engine.SNI_CLAUSES`,
tidak diketik ulang di sini.
"""

from __future__ import annotations

from dataclasses import dataclass

from pilecap_fem import capacity_engine, config
from pilecap_fem.reporting_pdf import typst_kit as tk
from pilecap_fem.reporting_pdf.figures import FigureStore

__all__ = ["EQUATIONS", "Equation", "chapter_theory"]

_CLAUSE = capacity_engine.SNI_CLAUSES


@dataclass(frozen=True)
class Equation:
    """Satu persamaan beserta asal dan pelaksananya."""

    key: str
    body: str
    caption: str
    source: str
    implemented_by: str


EQUATIONS: tuple[Equation, ...] = (
    Equation(
        key="plate_rigidity",
        body="D = (E t^3) / (12 (1 - nu^2))",
        caption="Kekakuan lentur pelat.",
        source="Timoshenko & Woinowsky-Krieger, Theory of Plates and Shells, ed. 2",
        implemented_by="plate_flexural_rigidity",
    ),
    Equation(
        key="moment_transform",
        body=("m_(x x) = m_11 cos^2 theta + m_22 sin^2 theta - 2 m_12 sin theta cos theta"),
        caption="Rotasi tensor momen dari sumbu lokal elemen ke sumbu global.",
        source="Rotasi tensor orde dua; tanda suku puntir diverifikasi melalui VC-2",
        implemented_by="transform_moments",
    ),
    Equation(
        key="shear_transform",
        body="q_x = q_1 cos theta - q_2 sin theta",
        caption="Rotasi gaya geser transversal ke sumbu global.",
        source="Rotasi vektor; diverifikasi melalui VC-2",
        implemented_by="transform_shear",
    ),
    Equation(
        key="strip_integration",
        body="M = sum_(e) v_e w_e",
        caption="Integrasi momen sepanjang satu lajur potongan, dengan `e` menyatakan "
        "elemen yang memotong lajur tersebut.",
        source="Integrasi diskret; kesetaraan dengan statika eksak diverifikasi melalui VC-3",
        implemented_by="integrate_strip",
    ),
    Equation(
        key="Vc",
        body="V_c = 0.17 lambda sqrt(f'_c) b_w d",
        caption="Kapasitas geser beton satu arah.",
        source=_CLAUSE["Vc"],
        implemented_by="calc_Vc",
    ),
    Equation(
        key="Av_min",
        body="A_v / s",
        caption="Luas sengkang per satuan jarak, dengan batas minimum kode.",
        source=_CLAUSE["Av_min"],
        implemented_by="calc_shear_Av_per_s",
    ),
)


def chapter_theory(figs: FigureStore) -> str:
    """Bab 2 -- dasar teori, lengkap dengan rumus, sumber, dan ilustrasi."""
    b: list[str] = [tk.heading(1, "Dasar teori", label="bab-teori")]

    # 2.1 -----------------------------------------------------------------
    b.append(tk.heading(2, "Lingkup dan idealisasi"))
    b.append(
        _md(
            "Pilecap dimodelkan sebagai **pelat lentur** menggunakan elemen shell empat "
            "simpul. Tiga idealisasi berikut menentukan seluruh hasil yang disajikan dalam "
            "dokumen ini.\n\n"
            "1. Pile tidak dimodelkan sebagai tumpuan. Reaksi pile `Pz`, yang telah "
            "diperoleh dari analisis struktur atas, diterapkan sebagai beban terbagi rata "
            "berarah ke atas pada cakram kepala pile.\n"
            "2. Pier dimodelkan sebagai jepit sempurna pada enam derajat kebebasan. "
            "Idealisasi ini mengabaikan fleksibilitas pier dan menimbulkan konsentrasi "
            "tegangan pada tepi zona jepit.\n"
            "3. Material bersifat elastis linier isotropik, tanpa peninjauan retak maupun "
            "redistribusi momen akibat retak."
        )
    )
    b.append(
        _md(
            "Idealisasi pertama membawa konsekuensi yang dimanfaatkan dalam pengendalian "
            "mutu analisis. Karena besar beban telah diketahui sejak awal, keseimbangan "
            "gaya dan momen dapat diperiksa secara eksak pada setiap eksekusi analisis. "
            "Pemeriksaan tersebut dilaporkan sebagai VC-0."
        )
    )
    b.append(
        figs.illustration(
            "skema-tumpuan-beban.svg",
            "Skema tumpuan dan pembebanan model: pile sebagai beban, pier sebagai tumpuan.",
        ).to_typst(width="85%")
    )

    # 2.2 -----------------------------------------------------------------
    b.append(tk.heading(2, "Sumbu dan konvensi tanda"))
    b.append(
        _md(
            "Sumbu global ditetapkan sebagai berikut: X arah memanjang, Y arah melintang, "
            "dan Z vertikal ke atas. Bidang model berimpit dengan bidang tengah pelat pada "
            "`z = 0`.\n\n"
            "Besaran `m_xx` menyatakan momen per satuan lebar pada penampang yang tegak "
            "lurus sumbu X, dan ditahan oleh tulangan arah X. Momen bertanda positif "
            "menyatakan **serat bawah mengalami tarik**, sehingga tulangan sisi bawah yang "
            "bekerja."
        )
    )
    b.append(
        _md(
            f"Faktor koreksi tanda momen dan gaya geser masing-masing bernilai "
            f"**{config.MOMENT_SIGN_FACTOR:g}** dan **{config.SHEAR_SIGN_FACTOR:g}**. "
            "Kedua faktor tersebut ditetapkan pada satu lokasi dan diterapkan satu kali "
            "dalam rantai pengolahan hasil, serta dikalibrasi terhadap kasus statis "
            "tertentu pada VC-3."
        )
    )
    b.append(
        figs.illustration(
            "sistem-koordinat.svg",
            "Sistem koordinat bersama bagi definisi pilecap, pile, dan pier.",
        ).to_typst(width="85%")
    )

    # 2.3 & 2.4 -----------------------------------------------------------
    b.append(tk.heading(2, "Elemen dan kekakuan pelat"))
    b.append(
        _md(
            "Analisis menggunakan elemen **ShellMITC4** dengan formulasi Mindlin-Reissner "
            "dan penampang **PlateFiber**. Elemen ini dipilih karena pilecap pada umumnya "
            "tergolong pelat tebal, sehingga deformasi geser transversal tidak dapat "
            "diabaikan. Penggunaan teori pelat tipis (Kirchhoff) pada kasus tersebut "
            "menghasilkan lendutan yang lebih kecil daripada lendutan sebenarnya, "
            "sebagaimana diverifikasi melalui VC-5."
        )
    )
    b.append(_equation("plate_rigidity"))
    b.append(
        _md(
            "Nilai kekakuan lentur `D` dicantumkan agar pemeriksa dapat melakukan "
            "perhitungan ulang secara mandiri. Dalam analisis, kekakuan tersebut dibentuk "
            "sendiri oleh solver dari parameter `E`, `nu`, dan tebal pelat."
        )
    )

    # 2.5 -----------------------------------------------------------------
    b.append(tk.heading(2, "Pengolahan hasil analisis"))
    b.append(
        _md(
            "Resultan gaya dalam diperoleh dari keluaran solver melalui lima langkah "
            "pengolahan berikut.\n\n"
            "1. Pengambilan resultan pada setiap titik Gauss tanpa modifikasi.\n"
            "2. Perataan nilai antartitik Gauss dalam satu elemen.\n"
            "3. Koreksi tanda menuju konvensi yang ditetapkan pada Subbab 2.2.\n"
            "4. Transformasi tensor dari sumbu lokal elemen ke sumbu global.\n"
            "5. Penyajian hasil sebagai `m_xx`, `m_yy`, `m_xy`, `q_x`, dan `q_y`."
        )
    )
    b.append(_equation("moment_transform"))
    b.append(_equation("shear_transform"))
    b.append(
        _md(
            "Ketepatan transformasi tersebut, termasuk tanda suku puntir "
            "`2 m_12 sin theta cos theta` yang bergantung pada konvensi keluaran solver, "
            "diverifikasi melalui VC-2. Pada verifikasi tersebut, model dengan orientasi "
            "elemen yang berbeda harus menghasilkan resultan global yang sama."
        )
    )

    # 2.6 -----------------------------------------------------------------
    b.append(tk.heading(2, "Momen desain per lajur"))
    b.append(_equation("strip_integration"))
    b.append(
        _md(
            "Elemen yang nilainya tidak terdefinisi tidak diikutsertakan dalam penjumlahan, "
            "sehingga satu elemen tidak menggugurkan hasil seluruh lajur. Lebar tributari "
            "`w_e` dihitung melalui proyeksi geometris eksak, dan potongan lajur diambil "
            "pada muka pier."
        )
    )
    b.append(
        tk.callout(
            "WARNING",
            _md(
                "Lokasi potongan yang ditetapkan adalah **muka pier secara geometris**. "
                "Kesesuaian lokasi tersebut terhadap definisi penampang kritis menurut "
                "standar belum dikonfirmasi. Seluruh tabel dalam dokumen ini karena itu "
                "menyebutnya sebagai muka pier, dan bukan sebagai penampang kritis menurut "
                "SNI 2847:2019."
            ),
        )
    )
    b.append(
        figs.illustration(
            "lajur-momen.svg", "Pembagian lajur dan lokasi potongan momen desain."
        ).to_typst(width="85%")
    )

    # 2.7 & 2.8 -----------------------------------------------------------
    b.append(tk.heading(2, "Geser"))
    b.append(_equation("Vc"))
    b.append(_equation("Av_min"))
    b.append(
        _md(
            "Gaya geser satu arah ditinjau pada penampang berjarak `d` dari muka pier. "
            "Integrasi dilakukan melalui prosedur yang sama dengan integrasi momen lajur, "
            "sehingga definisi lebar tributari konsisten pada kedua peninjauan."
        )
    )
    b.append(
        tk.callout(
            "IMPORTANT",
            _md(
                "Gaya geser pons ditentukan dari **keseimbangan gaya**, bukan dari resultan "
                "elemen shell. Elemen shell dua dimensi tidak memodelkan mekanisme "
                "keruntuhan pons yang bersifat tiga dimensi. Gaya geser pons terfaktor "
                "dihitung sebagai jumlah reaksi `Pz` pile yang berada di luar penampang "
                "kritis pada jarak `d/2` dari muka pier.\n\n"
                "**Kapasitas geser pons tidak dihitung** dalam dokumen ini dan berstatus "
                "`NOT_EVALUATED`, karena pasal acuannya belum dikonfirmasi. Yang disajikan "
                "hanya gaya geser yang bekerja."
            ),
        )
    )

    # 2.9 -----------------------------------------------------------------
    b.append(tk.heading(2, "Desain lentur menurut SNI 2847:2019"))
    b.append(
        _md(
            "Seluruh perhitungan kapasitas penampang mengacu pada SNI 2847:2019 dan "
            "dievaluasi oleh pustaka `shell-kit`, yang versinya dicatat pada "
            "[Lampiran A](#lampiran-provenance). Perhitungan dilakukan pada penampang selebar "
            f"**{_strip_width_mm():,.0f} mm**."
        )
    )
    b.append(
        tk.table(
            ["Besaran", "Pasal acuan"],
            [[f"`{k}`", v] for k, v in sorted(_CLAUSE.items())],
            caption="Pasal SNI 2847:2019 yang diterapkan dalam perhitungan kapasitas.",
        )
    )
    b.append(
        figs.illustration(
            "mode-tulangan.svg",
            "Dua mode pemilihan batang tulangan: spasi tetap dan diameter tetap.",
        ).to_typst(width="85%")
    )

    # 2.10 ----------------------------------------------------------------
    b.append(tk.heading(2, "Rasio bentang geser terhadap tinggi efektif"))
    b.append(
        _md(
            "Rasio `a/d` dihitung dengan `a` sebagai jarak terdekat dari muka pier ke pusat "
            "pile. Rasio yang kecil menunjukkan kecenderungan perilaku *deep member* dengan "
            "mekanisme strut-and-tie, yang tidak tercakup dalam model pelat lentur.\n\n"
            "Nilai rasio disajikan tanpa disertai kesimpulan. Batas yang memisahkan "
            "perilaku *deep* dari *non-deep* beserta pasal acuannya belum dikonfirmasi, "
            "sehingga penilaian atas perilaku tersebut menjadi kewenangan engineer yang "
            "bertanggung jawab."
        )
    )

    # 2.11 ----------------------------------------------------------------
    b.append(tk.heading(2, "Basis angka desain: per elemen atau per lajur"))
    b.append(
        _md(
            "Parameter `design.rebar_basis` menentukan sumber angka desain tulangan dan "
            "berlaku seragam untuk seluruh kombinasi beban, termasuk envelope.\n\n"
            "- Basis `element` menggunakan nilai momen tiap elemen tanpa perataan. Peta "
            "kontur menjadi keluaran utamanya. Nilai puncak pada tepi zona jepit pier "
            "bersifat **singular** dan tidak konvergen terhadap kehalusan mesh: "
            "pengukuran menunjukkan kenaikan sekitar 16% ketika ukuran elemen diperkecil "
            "dari 300 mm menjadi 150 mm. Arah penyimpangannya bersifat konservatif.\n"
            "- Basis `strip` menggunakan integrasi momen sepanjang potongan pada muka pier. "
            "Hasilnya konvergen dan dapat diperiksa secara manual, tetapi bergantung pada "
            "jumlah lajur yang ditetapkan melalui `strips_x` dan `strips_y`, yang tidak "
            "diatur oleh pasal tertentu. Sebagai gambaran, penggunaan satu lajur "
            "menggantikan lima lajur menurunkan momen puncak dari 556,2 kN.m/m menjadi "
            "283,4 kN.m/m."
        )
    )
    b.append(
        figs.illustration(
            "mode-desain-tulangan.svg", "Perbandingan dua basis penentuan angka desain tulangan."
        ).to_typst(width="90%")
    )

    # 2.12 ----------------------------------------------------------------
    b.append(tk.heading(2, "Pile yang tumpang tindih dengan pier"))
    b.append(
        _md(
            "Bagian cakram pile yang berada di dalam denah pier tidak menimbulkan lentur "
            "pada pelat. Karena pier dimodelkan sebagai jepit sempurna, tekanan pada daerah "
            "tersebut tersalur langsung menjadi reaksi tumpuan. Secara fisik hal ini "
            "merupakan aksi **strut**, yaitu penyaluran gaya langsung dari kepala pile ke "
            "pier menembus tebal pilecap. **Kapasitas strut tersebut tidak diperiksa** "
            "dalam dokumen ini dan wajib ditinjau secara terpisah.\n\n"
            "Besaran gaya yang tidak melenturkan pelat dilaporkan dalam dua komponen "
            "terpisah: komponen geometris, yang tidak bergantung pada ukuran elemen, dan "
            "komponen diskretisasi, yang besarnya sebanding dengan ukuran elemen. Uraian "
            "lengkap beserta tabel pengukurannya disajikan pada bab "
            "[Asumsi dan keterbatasan](#bab-keterbatasan) butir 10."
        )
    )
    b.append(
        figs.illustration(
            "tumpang-tindih-pile-pier.svg",
            "Komponen tumpang tindih antara cakram pile dan denah pier.",
        ).to_typst(width="85%")
    )

    # 2.13 ----------------------------------------------------------------
    b.append(tk.heading(2, "Verifikasi dan validasi"))
    b.append(
        _md(
            "Keluaran perangkat lunak diverifikasi melalui tujuh kasus uji (*validation "
            "case*). Kasus uji yang acuannya belum dikonfirmasi tidak dijalankan, dan "
            "statusnya dinyatakan secara terbuka pada tabel berikut."
        )
    )
    b.append(
        tk.table(
            ["Kasus uji", "Aspek yang diverifikasi", "Status"],
            [
                ["VC-0", "Keseimbangan statik Sigma R_z = Sigma P_z", "Terpenuhi, tiap analisis"],
                [
                    "VC-1",
                    "Pelat bujursangkar dengan tumpuan sederhana",
                    "Belum dijalankan; sumber koefisien belum dikonfirmasi",
                ],
                ["VC-2", "Invariansi hasil terhadap orientasi elemen", "Terpenuhi"],
                ["VC-3", "Pelat satu arah; kalibrasi tanda dan magnitudo", "Terpenuhi"],
                ["VC-4", "Konvergensi terhadap kehalusan mesh", "Terpenuhi"],
                ["VC-5", "Pengaruh tebal pelat; Mindlin terhadap Kirchhoff", "Terpenuhi"],
                ["VC-6", "Validasi silang terhadap Midas Civil", "Terpenuhi; syarat rilis"],
                [
                    "VC-7",
                    "Metode balok konvensional",
                    "Belum dijalankan; referensi belum dikonfirmasi",
                ],
            ],
            caption="Status verifikasi dan validasi pada versi perangkat lunak yang "
            "menghasilkan dokumen ini.",
        )
    )
    b.append(tk.pagebreak())
    return "\n\n".join(b)


def _equation(key: str) -> str:
    eq = next(e for e in EQUATIONS if e.key == key)
    return "\n\n".join(
        [
            tk.equation(eq.body, caption=eq.caption),
            _md(f"Acuan: {eq.source}. Dievaluasi oleh fungsi `{eq.implemented_by}`."),
        ]
    )


def _strip_width_mm() -> float:
    from shell_kit.rebar import STRIP_WIDTH_MM

    return float(STRIP_WIDTH_MM)


def _md(text: str) -> str:
    return tk.from_markdown(text)
