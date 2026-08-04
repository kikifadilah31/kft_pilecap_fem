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
    """
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
