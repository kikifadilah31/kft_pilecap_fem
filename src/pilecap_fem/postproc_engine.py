"""Post-processing: resultant lokal OpenSees -> momen & geser sumbu global.

Rantai perhitungannya sengaja dibuat eksplisit dan dapat ditelusuri langkah demi langkah
(PRD Core 4), karena inilah bagian yang harus dapat dihitung ulang dengan tangan oleh
engineer pemeriksa:

    eleResponse('stresses')  -> (n_gauss, 8) per elemen  [APA ADANYA dari OpenSees]
      -> rata-rata antar titik Gauss
      -> koreksi tanda ke konvensi PRD Bagian 7.1  (MOMENT_SIGN_FACTOR, SHEAR_SIGN_FACTOR)
      -> transformasi tensor lokal(theta) -> global XY  (math_engine)
      -> m_xx, m_yy, m_xy [N.m/m] dan q_x, q_y [N/m]

Modul ini bekerja murni SI. Konversi ke satuan tampilan terjadi di `reporter.py` /
`renderer.py` (PRD Bagian 4.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np

from pilecap_fem import config, math_engine
from pilecap_fem.fem_engine import ComboResult
from pilecap_fem.geometry_builder import GeometryModel, Pier
from pilecap_fem.mesh_model import MeshModel

_log = config.get_logger("postproc_engine")

#: Indeks komponen dalam blok 8-nilai (config.RESULTANT_COMPONENT_ORDER).
IDX_P11, IDX_P22, IDX_P12 = 0, 1, 2
IDX_M11, IDX_M22, IDX_M12 = 3, 4, 5
IDX_Q1, IDX_Q2 = 6, 7


@dataclass(frozen=True)
class ElementResults:
    """Resultant per elemen dalam SI, lokal maupun global."""

    combo: str
    # Lokal, sudah dikoreksi tanda ke konvensi PRD Bagian 7.1
    m11: np.ndarray
    m22: np.ndarray
    m12: np.ndarray
    q1: np.ndarray
    q2: np.ndarray
    p11: np.ndarray
    p22: np.ndarray
    p12: np.ndarray
    # Global
    m_xx: np.ndarray
    m_yy: np.ndarray
    m_xy: np.ndarray
    q_x: np.ndarray
    q_y: np.ndarray
    # Sudut yang dipakai untuk transformasi [rad]
    theta: np.ndarray
    #: Nilai per titik Gauss SEBELUM dirata-rata & sebelum koreksi tanda, disimpan agar
    #: `calc_sheet.md` dapat menampilkan rantai telusur lengkap satu elemen.
    raw_gauss: np.ndarray

    @property
    def n_elements(self) -> int:
        return int(self.m_xx.shape[0])

    @property
    def q_magnitude(self) -> np.ndarray:
        return np.asarray(np.hypot(self.q_x, self.q_y), dtype=np.float64)

    def extreme(self, field: str) -> tuple[int, float]:
        """(indeks elemen, nilai) dengan magnitudo terbesar pada suatu field."""
        values = getattr(self, field)
        index = int(np.nanargmax(np.abs(values)))
        return index, float(values[index])


def compute_element_results(
    combo_result: ComboResult, mesh: MeshModel, *, theta: np.ndarray | None = None
) -> ElementResults:
    """Ubah resultant lokal mentah menjadi momen & geser sumbu global.

    `theta` dapat diberikan eksplisit (dipakai VC-2 untuk menguji transformasi terhadap
    sudut yang diketahui); default memakai `mesh.elem_theta`.
    """
    raw = combo_result.local_resultants
    expected = (mesh.n_elements, config.SHELL_N_GAUSS, config.SHELL_N_RESULTANT_COMPONENTS)
    if raw.shape != expected:
        raise ValueError(
            f"Bentuk resultant {raw.shape} tidak sesuai harapan {expected}. "
            "Jumlah elemen atau struktur response OpenSees berubah."
        )

    # Rata-rata aritmetik antar titik Gauss (PRD Bagian 7.2(2)).
    averaged = raw.mean(axis=1)

    ms = config.MOMENT_SIGN_FACTOR
    qs = config.SHEAR_SIGN_FACTOR
    ps = config.MEMBRANE_SIGN_FACTOR

    m11 = ms * averaged[:, IDX_M11]
    m22 = ms * averaged[:, IDX_M22]
    m12 = ms * averaged[:, IDX_M12]
    q1 = qs * averaged[:, IDX_Q1]
    q2 = qs * averaged[:, IDX_Q2]
    p11 = ps * averaged[:, IDX_P11]
    p22 = ps * averaged[:, IDX_P22]
    p12 = ps * averaged[:, IDX_P12]

    angles = mesh.elem_theta if theta is None else np.asarray(theta, dtype=np.float64)
    m_xx, m_yy, m_xy = math_engine.transform_moments(m11, m22, m12, angles)
    q_x, q_y = math_engine.transform_shear(q1, q2, angles)

    n_nan = int(np.count_nonzero(~np.isfinite(m_xx)))
    if n_nan:
        _log.warning(
            "%d elemen menghasilkan m_xx tak terdefinisi (NaN); ditandai di plot dan CSV.",
            n_nan,
        )

    _log.debug(
        "Resultant [%s]: |m_xx| maks = %.1f kNm/m, |q| maks = %.1f kN/m",
        combo_result.combo,
        np.nanmax(np.abs(m_xx)) / 1e3,
        np.nanmax(np.hypot(q_x, q_y)) / 1e3,
    )

    return ElementResults(
        combo=combo_result.combo,
        m11=m11,
        m22=m22,
        m12=m12,
        q1=q1,
        q2=q2,
        p11=p11,
        p22=p22,
        p12=p12,
        m_xx=m_xx,
        m_yy=m_yy,
        m_xy=m_xy,
        q_x=q_x,
        q_y=q_y,
        theta=angles,
        raw_gauss=raw,
    )


def traceability_sample(results: ElementResults, mesh: MeshModel, index: int) -> dict[str, Any]:
    """Rantai telusur LENGKAP satu elemen (PRD Bagian 9.4 bagian 5).

    Isinya cukup bagi checker untuk menghitung ulang elemen itu dengan tangan:
    koordinat node, resultant tiap titik Gauss apa adanya, hasil rata-rata, faktor
    koreksi tanda, sudut theta, dan hasil transformasi.

    Hanya dapat dibuat dari hasil `pilecap-analyze`, karena nilai per titik Gauss tidak
    tersimpan di `element_resultants.csv`. `pilecap-analyze` menuliskan hasil fungsi ini
    ke `Combo_*/traceability_sample.json` supaya `pilecap-report` tetap dapat menyajikan
    rantai yang LENGKAP, bukan versi yang dipotong diam-diam.
    """
    if results.raw_gauss.size == 0:
        raise ValueError(
            "Nilai per titik Gauss tidak tersedia pada objek hasil ini (kemungkinan "
            "dibaca ulang dari element_resultants.csv). Rantai telusur lengkap hanya "
            "dapat dibuat dari hasil pilecap-analyze; gunakan berkas "
            "`traceability_sample.json` yang ditulis di sana."
        )
    conn = mesh.elem_conn[index]
    return {
        "element_index": index,
        "element_tag": int(mesh.elem_tags[index]),
        "group": mesh.group_names[int(mesh.elem_group[index])],
        "centroid_m": mesh.elem_centroid[index].tolist(),
        "area_m2": float(mesh.elem_area[index]),
        "node_tags": [int(mesh.node_tags[n]) for n in conn],
        "node_coords_m": mesh.node_xy[conn].tolist(),
        "gauss_raw": {
            "component_order": list(config.RESULTANT_COMPONENT_ORDER),
            "response_name": config.SHELL_RESULTANT_RESPONSE,
            "values": results.raw_gauss[index].tolist(),
        },
        "gauss_mean": results.raw_gauss[index].mean(axis=0).tolist(),
        "sign_factors": {
            "moment": config.MOMENT_SIGN_FACTOR,
            "shear": config.SHEAR_SIGN_FACTOR,
            "membrane": config.MEMBRANE_SIGN_FACTOR,
        },
        "local_after_sign": {
            "m11": float(results.m11[index]),
            "m22": float(results.m22[index]),
            "m12": float(results.m12[index]),
            "q1": float(results.q1[index]),
            "q2": float(results.q2[index]),
        },
        "theta_rad": float(results.theta[index]),
        "theta_deg": float(np.degrees(results.theta[index])),
        "global": {
            "m_xx": float(results.m_xx[index]),
            "m_yy": float(results.m_yy[index]),
            "m_xy": float(results.m_xy[index]),
            "q_x": float(results.q_x[index]),
            "q_y": float(results.q_y[index]),
        },
        "formula": (
            "m_xx = m11 cos^2(theta) + m22 sin^2(theta) - 2 m12 sin(theta) cos(theta); "
            "m_yy = m11 sin^2(theta) + m22 cos^2(theta) + 2 m12 sin(theta) cos(theta); "
            "m_xy = (m11 - m22) sin(theta) cos(theta) + m12 (cos^2(theta) - sin^2(theta)); "
            "q_x = q1 cos(theta) - q2 sin(theta); q_y = q1 sin(theta) + q2 cos(theta)"
        ),
    }


def strip_moments(
    results: ElementResults,
    mesh: MeshModel,
    *,
    direction: str,
    n_strips: int,
    cut_position: float,
    mesh_size: float,
    width_method: str = "exact",
) -> list[dict[str, Any]]:
    """Momen total per lajur pada satu garis potong (PRD Bagian 7.2(4)).

    `direction` = ``"x"`` menghitung `M_x` pada potongan tegak lurus sumbu X (yaitu
    garis `x = cut_position`), dibagi menjadi `n_strips` lajur sepanjang sumbu Y.

    Pemilihan elemen memakai :func:`math_engine.select_elements_crossing_cut`: elemen
    yang benar-benar dipotong garis, bukan yang centroid-nya kebetulan dekat. Pada mesh
    quasi-structured quad, pemilihan berbasis centroid melewatkan sebagian lebar dan
    MEREMEHKAN momen lajur beberapa persen tanpa memunculkan error apa pun.
    """
    if direction not in ("x", "y"):
        raise ValueError(f"direction = {direction!r} harus 'x' atau 'y'.")
    cut_axis = 0 if direction == "x" else 1
    other_axis = 1 - cut_axis
    values = results.m_xx if direction == "x" else results.m_yy

    centroids = mesh.elem_centroid
    coords = mesh.node_xy[mesh.elem_conn]
    widths = math_engine.cut_element_widths(
        coords,
        mesh.elem_area,
        cut_axis=cut_axis,
        method=width_method,
        cut_position=cut_position,
    )

    low = float(centroids[:, other_axis].min())
    high = float(centroids[:, other_axis].max())
    edges = np.linspace(low, high, n_strips + 1)

    rows: list[dict[str, Any]] = []
    for i in range(n_strips):
        bounds = (float(edges[i]), float(edges[i + 1]))
        mask = math_engine.select_elements_crossing_cut(
            coords,
            cut_axis=cut_axis,
            cut_position=cut_position,
            centroids=centroids,
            strip_bounds=bounds,
        )
        total = math_engine.integrate_strip(values, widths, mask)
        actual = math_engine.cut_column_position(centroids, mask, cut_axis)
        rows.append(
            {
                "strip": i + 1,
                "direction": direction,
                "bounds_m": bounds,
                "cut_requested_m": cut_position,
                "cut_actual_m": actual,
                "n_elements": int(mask.sum()),
                "M_total_Nm": total,
                "width_method": width_method,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Penampang di muka pier (PRD Bagian 7.2(5))
# ---------------------------------------------------------------------------


def pier_face_cuts(pier: Pier) -> dict[str, tuple[float, float]]:
    """Posisi muka pier pada sumbu X dan Y [m]: ``{"x": (xmin, xmax), "y": (...)}``.

    Untuk pier persegi ini persis mukanya. Untuk pier POLIGON, bounding box adalah
    penyederhanaan ke arah LUAR (penampang diambil sedikit lebih jauh dari pusat);
    itu dinyatakan di `calc_sheet.md`, bukan disembunyikan.

    .. warning::
       Yang ditetapkan di sini hanyalah **lokasi geometris muka pier**. Apakah lokasi
       itu memang penampang kritis menurut standar adalah pertanyaan pasal yang BELUM
       dikonfirmasi (PRD Bagian 17 item 3). Laporan menyebutnya "muka pier (lokasi
       geometris)", bukan "penampang kritis menurut SNI".
    """
    xmin, ymin, xmax, ymax = pier.to_shapely().bounds
    return {"x": (float(xmin), float(xmax)), "y": (float(ymin), float(ymax))}


def design_moment_sections(
    results: ElementResults,
    mesh: MeshModel,
    geom: GeometryModel,
    *,
    n_strips_x: int,
    n_strips_y: int,
    mesh_size: float,
    moment_at: str = "pier_face",
) -> list[dict[str, Any]]:
    """Momen per lajur di muka tiap pier dan/atau di lokasi puncak.

    * ``"pier_face"`` (default) -- dipakai untuk desain.
    * ``"peak"`` -- **nilai singular numerik**: seluruh node area pier dijepit sehingga
      terjadi konsentrasi tegangan di tepi zona jepit (PRD Bagian 8.3 keterbatasan #2).
      Dilaporkan tetapi ditandai `singular=True`, BUKAN momen desain.
    * ``"both"`` -- keduanya.
    """
    if moment_at not in ("pier_face", "peak", "both"):
        raise ValueError(f"moment_at = {moment_at!r} harus 'pier_face', 'peak', atau 'both'.")

    rows: list[dict[str, Any]] = []

    if moment_at in ("pier_face", "both"):
        for pier in geom.piers:
            faces = pier_face_cuts(pier)
            for direction, n_strips in (("x", n_strips_x), ("y", n_strips_y)):
                for side, position in zip(("min", "maks"), faces[direction], strict=True):
                    rows.extend(
                        {
                            **row,
                            "lokasi": "muka_pier",
                            "pier_id": pier.pier_id,
                            "sisi": side,
                            "singular": False,
                        }
                        for row in strip_moments(
                            results,
                            mesh,
                            direction=direction,
                            n_strips=n_strips,
                            cut_position=position,
                            mesh_size=mesh_size,
                        )
                    )

    if moment_at in ("peak", "both"):
        for direction, field, n_strips in (
            ("x", "m_xx", n_strips_x),
            ("y", "m_yy", n_strips_y),
        ):
            index, _ = results.extreme(field)
            position = float(mesh.elem_centroid[index, 0 if direction == "x" else 1])
            rows.extend(
                {
                    **row,
                    "lokasi": "peak",
                    "pier_id": "-",
                    "sisi": "-",
                    "singular": True,
                }
                for row in strip_moments(
                    results,
                    mesh,
                    direction=direction,
                    n_strips=n_strips,
                    cut_position=position,
                    mesh_size=mesh_size,
                )
            )

    return rows


# ---------------------------------------------------------------------------
# Geser (PRD Bagian 7.2(7)) -- DEMAND SAJA
# ---------------------------------------------------------------------------

CAPACITY_NOT_EVALUATED = "NOT_EVALUATED"
_CAPACITY_NOTE = (
    "Kapasitas TIDAK dihitung: pasal V_c, b_o, d, dan phi belum dikonfirmasi "
    "(PRD Bagian 17 item 3). Nilai pada baris ini adalah DEMAND saja."
)


@dataclass(frozen=True)
class ShearCheck:
    """Satu baris `shear_checks.csv`. Kapasitas SELALU `NOT_EVALUATED` di v1.0."""

    pier_id: str
    kind: str
    d_m: float
    location_m: float | None
    b_o_m: float | None
    V_u_N: float
    v_u_Pa: float | None
    capacity_status: str
    note: str


def effective_depth(geom: GeometryModel, cover_m: float) -> float:
    """Tinggi efektif `d = t - cover` [m] (PRD Bagian 7.2(7))."""
    d = geom.thickness - cover_m
    if d <= 0.0:
        raise ValueError(
            f"Tinggi efektif d = t - cover = {geom.thickness} - {cover_m} = {d} m <= 0. "
            "Periksa `pilecap.thickness` dan `design.cover`."
        )
    return d


def one_way_shear(
    results: ElementResults,
    mesh: MeshModel,
    pier: Pier,
    *,
    d: float,
) -> list[ShearCheck]:
    """Geser satu arah pada jarak `d` dari muka pier, kedua sisi, kedua arah.

    `q` global diintegrasi memakai jalur yang SAMA dengan momen lajur
    (`select_elements_crossing_cut` + lebar potongan eksak), sehingga definisi "lebar"
    konsisten antara momen dan geser.
    """
    faces = pier_face_cuts(pier)
    coords = mesh.node_xy[mesh.elem_conn]
    checks: list[ShearCheck] = []

    for direction, values in (("x", results.q_x), ("y", results.q_y)):
        cut_axis = 0 if direction == "x" else 1
        lo, hi = faces[direction]
        low_bound = float(mesh.elem_centroid[:, cut_axis].min())
        high_bound = float(mesh.elem_centroid[:, cut_axis].max())

        for side, position in (("min", lo - d), ("maks", hi + d)):
            if not low_bound <= position <= high_bound:
                checks.append(
                    ShearCheck(
                        pier_id=pier.pier_id,
                        kind=f"one_way_{direction}_{side}",
                        d_m=d,
                        location_m=position,
                        b_o_m=None,
                        V_u_N=float("nan"),
                        v_u_Pa=None,
                        capacity_status=CAPACITY_NOT_EVALUATED,
                        note=(
                            f"Penampang pada {position:.4f} m berada DI LUAR pilecap; "
                            "geser satu arah tidak terdefinisi di sisi ini. " + _CAPACITY_NOTE
                        ),
                    )
                )
                continue

            mask = math_engine.select_elements_crossing_cut(
                coords, cut_axis=cut_axis, cut_position=position
            )
            widths = math_engine.cut_element_widths(
                coords, mesh.elem_area, cut_axis=cut_axis, cut_position=position
            )
            v_u = math_engine.integrate_strip(values, widths, mask)
            width_total = float(np.nansum(widths[mask]))

            checks.append(
                ShearCheck(
                    pier_id=pier.pier_id,
                    kind=f"one_way_{direction}_{side}",
                    d_m=d,
                    location_m=position,
                    b_o_m=width_total,
                    V_u_N=v_u,
                    v_u_Pa=(abs(v_u) / (width_total * d) if width_total > 0 else None),
                    capacity_status=CAPACITY_NOT_EVALUATED,
                    note=_CAPACITY_NOTE,
                )
            )
    return checks


def punching_shear(
    geom: GeometryModel,
    pier: Pier,
    pz_by_pile: dict[str, float],
    *,
    d: float,
) -> ShearCheck:
    """Geser pons dari KESEIMBANGAN GAYA, bukan dari resultant shell.

    PRD Bagian 7.2(7) & Bagian 8.3 keterbatasan #7: elemen shell 2D tidak memodelkan
    mekanisme keruntuhan pons tiga dimensi, sehingga `q` shell tidak boleh dipakai.
    Yang dipakai adalah gaya yang harus menyeberangi penampang kritis:

        V_u = jumlah P_z pile DI LUAR penampang kritis pada d/2 dari muka pier

    Penampang dibentuk dengan `buffer(d/2, join_style="mitre")` sehingga sudutnya siku,
    bukan membulat -- dan definisi itu berlaku juga untuk pier poligon.
    """
    critical = pier.to_shapely().buffer(d / 2.0, join_style="mitre")
    b_o = float(critical.exterior.length)

    outside = 0.0
    inside_ids: list[str] = []
    for pile in geom.piles:
        if critical.contains(pile.to_shapely().centroid):
            inside_ids.append(pile.pile_id)
        else:
            outside += float(pz_by_pile.get(pile.pile_id, 0.0))

    note = _CAPACITY_NOTE
    if inside_ids:
        note = (
            f"Pile {inside_ids} berada DI DALAM penampang kritis pons sehingga "
            "reaksinya tidak diperhitungkan menyeberang. " + note
        )

    return ShearCheck(
        pier_id=pier.pier_id,
        kind="punching",
        d_m=d,
        location_m=None,
        b_o_m=b_o,
        V_u_N=outside,
        v_u_Pa=(outside / (b_o * d) if b_o > 0 else None),
        capacity_status=CAPACITY_NOT_EVALUATED,
        note=note,
    )


def shear_span_ratio(geom: GeometryModel, cover_m: float) -> dict[str, Any]:
    """Rasio bentang geser terhadap tinggi efektif, `a / d` (PRD Bagian 8.3 poin 1).

    `a` = jarak terdekat dari muka pier ke pusat pile. Rasio kecil menandakan perilaku
    *deep member* (strut-and-tie), yang TIDAK dimodelkan tool ini.

    **Dilaporkan TANPA VONIS.** Ambang yang memisahkan deep dari non-deep beserta
    pasalnya belum dikonfirmasi (PRD Bagian 17 item 5). Mencetak angka batas tanpa
    pasal berarti tool memberi kesimpulan yang tidak dapat dipertanggungjawabkan --
    justru yang dilarang PRD Bagian 1.3 poin 2. Yang disajikan adalah angkanya saja,
    supaya engineer menilai sendiri.
    """
    d = effective_depth(geom, cover_m)
    rows: list[dict[str, Any]] = []
    for pier in geom.piers:
        face = pier.to_shapely().exterior
        for pile in geom.piles:
            a = float(face.distance(pile.to_shapely().centroid))
            rows.append(
                {
                    "pier_id": pier.pier_id,
                    "pile_id": pile.pile_id,
                    "a_m": a,
                    "d_m": d,
                    "a_over_d": a / d,
                }
            )
    minimum = min(rows, key=lambda r: r["a_over_d"]) if rows else None
    return {
        "d_m": d,
        "rows": rows,
        "min_a_over_d": (minimum["a_over_d"] if minimum else float("nan")),
        "min_at": (f"{minimum['pier_id']} - {minimum['pile_id']}" if minimum else "-"),
        "verdict": "TIDAK DINILAI",
        "note": (
            "Ambang deep pile cap beserta pasalnya belum dikonfirmasi "
            "(PRD Bagian 17 item 5). Rasio disajikan apa adanya; penilaian apakah "
            "pilecap ini berperilaku deep member menjadi tanggung jawab engineer."
        ),
    }


def shear_demand(
    results: ElementResults,
    mesh: MeshModel,
    geom: GeometryModel,
    pz_by_pile: dict[str, float],
    *,
    cover_m: float,
) -> list[ShearCheck]:
    """Seluruh cek geser untuk semua pier: satu arah + pons. DEMAND saja."""
    d = effective_depth(geom, cover_m)
    checks: list[ShearCheck] = []
    for pier in geom.piers:
        checks.extend(one_way_shear(results, mesh, pier, d=d))
        checks.append(punching_shear(geom, pier, pz_by_pile, d=d))
    return checks


# ---------------------------------------------------------------------------
# Envelope antar kombinasi (PRD Bagian 12, Cond C)
# ---------------------------------------------------------------------------

#: Field yang di-envelope. `q_magnitude` disertakan karena PRD Bagian 12 meminta
#: magnitudo DAN komponennya dilaporkan keduanya.
ENVELOPE_FIELDS: tuple[str, ...] = ("m_xx", "m_yy", "m_xy", "q_x", "q_y", "q_magnitude")


@dataclass(frozen=True)
class FieldEnvelope:
    """Nilai ekstrem satu field per lokasi elemen, beserta kombinasi penyebabnya."""

    field: str
    max_values: np.ndarray
    max_combo_index: np.ndarray
    min_values: np.ndarray
    min_combo_index: np.ndarray


@dataclass(frozen=True)
class Envelope:
    combos: tuple[str, ...]
    fields: dict[str, FieldEnvelope]

    def combo_name(self, index: int) -> str:
        i = int(index)
        return self.combos[i] if 0 <= i < len(self.combos) else "-"

    def governing_names(self, field: str, which: str) -> list[str]:
        envelope = self.fields[field]
        indices = envelope.max_combo_index if which == "max" else envelope.min_combo_index
        return [self.combo_name(i) for i in indices]


def build_envelope(
    results_by_combo: dict[str, ElementResults],
    *,
    fields: tuple[str, ...] = ENVELOPE_FIELDS,
) -> Envelope:
    """Envelope per LOKASI elemen lintas kombinasi (PRD Bagian 12).

    Positif dan negatif dipisah: untuk momen, maksimum menentukan tulangan bawah dan
    minimum menentukan tulangan atas -- keduanya menentukan desain.

    **`governing_combo` per lokasi wajib**: tanpa itu envelope tidak auditable, karena
    nilai ekstrem tidak dapat ditelusuri kembali ke kombinasi asalnya.

    Envelope BUKAN kondisi keseimbangan tunggal dan tidak boleh dipakai untuk cek
    statika -- peringatan itu dicetak di setiap plot dan tabel envelope.
    """
    if not results_by_combo:
        raise ValueError("Tidak ada kombinasi untuk di-envelope.")

    combos = tuple(results_by_combo)

    # Diperiksa SEBELUM np.vstack: pesan bawaan numpy ("array at index 0 has size 2...")
    # tidak memberi tahu bahwa masalahnya adalah mesh yang berbeda antar kombinasi.
    sizes = {c: results_by_combo[c].n_elements for c in combos}
    if len(set(sizes.values())) > 1:
        raise ValueError(
            "Jumlah elemen berbeda antar kombinasi; envelope hanya sah bila seluruh "
            f"kombinasi memakai mesh yang sama. Jumlah elemen per kombinasi: {sizes}"
        )

    envelopes: dict[str, FieldEnvelope] = {}
    n_positions = next(iter(sizes.values()))

    for field in fields:
        stack = np.vstack([np.asarray(getattr(results_by_combo[c], field)) for c in combos])
        valid = np.isfinite(stack)
        any_valid = valid.any(axis=0)
        columns = np.arange(stack.shape[1])

        max_index = np.where(valid, stack, -np.inf).argmax(axis=0)
        min_index = np.where(valid, stack, np.inf).argmin(axis=0)

        envelopes[field] = FieldEnvelope(
            field=field,
            max_values=np.where(any_valid, stack[max_index, columns], np.nan),
            max_combo_index=max_index,
            min_values=np.where(any_valid, stack[min_index, columns], np.nan),
            min_combo_index=min_index,
        )

    _log.info(
        "Envelope: %d kombinasi x %d elemen untuk %d field",
        len(combos),
        n_positions,
        len(fields),
    )
    return Envelope(combos=combos, fields=envelopes)
