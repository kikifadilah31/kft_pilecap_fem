"""Matematika murni: transformasi tensor, integrasi strip, kekakuan pelat.

**Modul ini TIDAK BOLEH mengimpor gmsh, openseespy, atau matplotlib** (PRD Core 7).
Isinya fungsi bebas efek samping yang bekerja pada array NumPy, sehingga dapat diuji
tanpa menjalankan solver apa pun dan dapat dipakai ulang oleh modul mana saja.

Seluruh nilai dalam SI (N, m, Pa); sudut dalam radian.
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "cut_column_position",
    "cut_element_widths",
    "cut_intersection_lengths",
    "element_extent",
    "integrate_strip",
    "plate_flexural_rigidity",
    "select_cut_elements",
    "select_elements_crossing_cut",
    "select_nearest_cut_column",
    "transform_moments",
    "transform_shear",
    "wood_armer",
]


# ---------------------------------------------------------------------------
# Kekakuan pelat (PRD Bagian 7.2(1))
# ---------------------------------------------------------------------------


def plate_flexural_rigidity(E: float, t: float, nu: float) -> float:
    r"""Kekakuan lentur pelat :math:`D = E t^3 / (12 (1 - \nu^2))` [N.m].

    Sumber: Timoshenko & Woinowsky-Krieger, *Theory of Plates and Shells*, 2nd ed.
    Nilai ini hanya dilaporkan di `calc_sheet.md` agar checker dapat menghitung ulang;
    OpenSees menghitung kekakuannya sendiri dari `E`, `nu`, dan `t`.
    """
    if not 0.0 <= nu < 0.5:
        raise ValueError(f"nu = {nu} di luar rentang 0 <= nu < 0.5")
    if E <= 0.0 or t <= 0.0:
        raise ValueError(f"E = {E} dan t = {t} harus > 0")
    return E * t**3 / (12.0 * (1.0 - nu**2))


# ---------------------------------------------------------------------------
# Transformasi lokal -> global (PRD Bagian 7.2(3))
# ---------------------------------------------------------------------------


def transform_moments(
    m11: np.ndarray, m22: np.ndarray, m12: np.ndarray, theta: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    r"""Putar tensor momen dari sumbu lokal elemen ke sumbu global.

    `theta` = sudut sumbu lokal-1 elemen terhadap sumbu global X [rad].

    .. math::
        m_{xx} &= m_{11}\cos^2\theta + m_{22}\sin^2\theta - 2 m_{12}\sin\theta\cos\theta \\
        m_{yy} &= m_{11}\sin^2\theta + m_{22}\cos^2\theta + 2 m_{12}\sin\theta\cos\theta \\
        m_{xy} &= (m_{11}-m_{22})\sin\theta\cos\theta + m_{12}(\cos^2\theta - \sin^2\theta)

    Ini adalah rotasi tensor orde-2 baku :math:`M_{global} = R M_{lokal} R^T` dengan
    :math:`R = [[\cos\theta, -\sin\theta], [\sin\theta, \cos\theta]]`. Kebenarannya --
    termasuk TANDA suku :math:`2 m_{12}\sin\theta\cos\theta` yang bergantung pada
    konvensi `m12` OpenSees -- dibuktikan oleh **VC-2** (invariansi orientasi mesh).

    Seluruhnya vektor: bekerja pada ribuan elemen sekaligus (PRD Core 9).
    """
    c = np.cos(theta)
    s = np.sin(theta)
    cc, ss, cs = c * c, s * s, c * s

    m_xx = m11 * cc + m22 * ss - 2.0 * m12 * cs
    m_yy = m11 * ss + m22 * cc + 2.0 * m12 * cs
    m_xy = (m11 - m22) * cs + m12 * (cc - ss)
    return m_xx, m_yy, m_xy


def transform_shear(
    q1: np.ndarray, q2: np.ndarray, theta: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    r"""Putar vektor geser transversal dari sumbu lokal ke global.

    .. math:: q_x = q_1\cos\theta - q_2\sin\theta \qquad q_y = q_1\sin\theta + q_2\cos\theta
    """
    c = np.cos(theta)
    s = np.sin(theta)
    return q1 * c - q2 * s, q1 * s + q2 * c


# ---------------------------------------------------------------------------
# Integrasi strip (PRD Bagian 7.2(4))
# ---------------------------------------------------------------------------


def element_extent(coords: np.ndarray, axis: int) -> np.ndarray:
    """Rentang (max - min) koordinat tiap elemen pada sumbu `axis`.

    `coords` berbentuk (M, n_node, 2). `axis` 0 = X, 1 = Y.
    """
    values = coords[:, :, axis]
    return np.asarray(values.max(axis=1) - values.min(axis=1), dtype=np.float64)


def _strip_bounds_mask(
    centroids: np.ndarray, cut_axis: int, strip_bounds: tuple[float, float] | None
) -> np.ndarray:
    if strip_bounds is None:
        return np.ones(len(centroids), dtype=bool)
    other = 1 - cut_axis
    low, high = strip_bounds
    return (centroids[:, other] >= low) & (centroids[:, other] <= high)


def select_cut_elements(
    centroids: np.ndarray,
    *,
    cut_axis: int,
    cut_position: float,
    half_band: float,
    strip_bounds: tuple[float, float] | None = None,
) -> np.ndarray:
    """Mask elemen dalam pita `|centroid - cut_position| <= half_band`.

    Pemilihan berbasis pita bersifat RAPUH terhadap posisi garis potong: bila garis
    jatuh persis di batas antar elemen, pita sempit memilih NOL kolom dan pita lebar
    memilih DUA kolom (hasil integrasi menjadi dua kali lipat). Keduanya tidak
    menghasilkan error apa pun.

    Untuk momen desain gunakan :func:`select_nearest_cut_column`, yang menempel ke
    kolom elemen terdekat sehingga selalu memilih tepat satu kolom. Fungsi ini tetap
    disediakan untuk keperluan yang memang membutuhkan pita eksplisit.
    """
    along = centroids[:, cut_axis]
    mask = np.abs(along - cut_position) <= half_band
    return np.asarray(mask & _strip_bounds_mask(centroids, cut_axis, strip_bounds), dtype=bool)


def select_nearest_cut_column(
    centroids: np.ndarray,
    *,
    cut_axis: int,
    cut_position: float,
    snap_tol: float,
    strip_bounds: tuple[float, float] | None = None,
) -> np.ndarray:
    """Mask SATU kolom elemen yang centroid-nya paling dekat ke `cut_position`.

    Cara kerja: cari elemen terdekat ke garis potong, lalu ambil semua elemen yang
    centroid-nya berada dalam `snap_tol` dari elemen itu (yaitu satu kolom yang sama).
    `snap_tol` harus lebih kecil dari ukuran elemen -- nilai lazim ``0.25 * h``.

    Hasilnya tidak pernah kosong (selama ada elemen dalam `strip_bounds`) dan tidak
    pernah menggandakan kolom, berapa pun posisi garis potong relatif terhadap mesh.
    Posisi kolom yang benar-benar dipakai dikembalikan lewat
    :func:`cut_column_position` agar dapat dilaporkan di calc sheet.
    """
    within = _strip_bounds_mask(centroids, cut_axis, strip_bounds)
    if not within.any():
        return within

    along = centroids[:, cut_axis]
    candidates = np.where(within)[0]
    nearest = candidates[np.argmin(np.abs(along[candidates] - cut_position))]
    return np.asarray(within & (np.abs(along - along[nearest]) <= snap_tol), dtype=bool)


def select_elements_crossing_cut(
    coords: np.ndarray,
    *,
    cut_axis: int,
    cut_position: float,
    centroids: np.ndarray | None = None,
    strip_bounds: tuple[float, float] | None = None,
) -> np.ndarray:
    """Mask elemen yang BENAR-BENAR dipotong garis `cut_axis = cut_position`.

    Kriterianya geometris, bukan kedekatan centroid:
    ``min_e <= cut_position < max_e`` (setengah terbuka). Konsekuensinya:

    * elemen terpilih **menutup garis potong tanpa celah dan tanpa tumpang tindih**,
      sehingga jumlah lebarnya sama dengan lebar pelat -- juga pada mesh TAK BERATURAN;
    * garis yang jatuh persis di batas antar elemen memilih tepat satu sisi, bukan dua.

    Ini menggantikan pemilihan berbasis centroid untuk integrasi strip. Pada mesh
    terstruktur keduanya setara, tetapi pada mesh quasi-structured quad (yang centroid-nya
    berselang-seling) pemilihan centroid melewatkan sebagian lebar dan MEREMEHKAN momen
    lajur beberapa persen tanpa error apa pun.
    """
    along = coords[:, :, cut_axis]
    low = along.min(axis=1)
    high = along.max(axis=1)

    mask = (low <= cut_position) & (cut_position < high)
    if not mask.any():
        # Garis potong tepat di tepi terluar model: pakai batas tertutup.
        mask = (low <= cut_position) & (cut_position <= high)

    if strip_bounds is not None:
        if centroids is None:
            raise ValueError("`strip_bounds` membutuhkan `centroids`.")
        mask &= _strip_bounds_mask(centroids, cut_axis, strip_bounds)
    return mask


def cut_column_position(centroids: np.ndarray, mask: np.ndarray, cut_axis: int) -> float:
    """Posisi aktual kolom elemen terpilih [m] -- untuk dilaporkan di calc sheet.

    Nilainya umumnya berbeda dari `cut_position` yang diminta (mesh tidak selalu punya
    elemen tepat di sana). Selisih itu WAJIB terlihat oleh checker, bukan disembunyikan.
    """
    if not mask.any():
        return float("nan")
    return float(np.mean(centroids[mask, cut_axis]))


def cut_intersection_lengths(
    coords: np.ndarray, *, cut_axis: int, cut_position: float
) -> np.ndarray:
    """Panjang potongan garis `cut_axis = cut_position` di dalam tiap elemen [m].

    Inilah "proyeksi geometrik eksak" yang dimaksud PRD Bagian 7.2(4) opsi (a): garis
    potong diiris terhadap keempat sisi quad, lalu diambil rentang titik-titik potongnya.

    Untuk quad sejajar sumbu hasilnya sama dengan rentang bounding box. Untuk quad
    MIRING keduanya berbeda, dan bounding box selalu MELEBIHKAN -- pada mesh
    quasi-structured quad selisihnya sampai puluhan persen pada momen lajur.

    Elemen yang tidak terpotong menghasilkan 0.0.
    """
    other = 1 - cut_axis
    a = coords[:, :, cut_axis]
    b = coords[:, :, other]

    a_next = np.roll(a, -1, axis=1)
    b_next = np.roll(b, -1, axis=1)

    da = a - cut_position
    da_next = a_next - cut_position

    # Sisi yang MELINTASI garis (tanda berbeda, termasuk salah satu ujung tepat di garis).
    crosses = (da <= 0) & (da_next >= 0) | (da >= 0) & (da_next <= 0)
    denominator = a_next - a
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(np.abs(denominator) > 0.0, -da / denominator, 0.0)
    hit = b + t * (b_next - b)

    # Sisi yang sejajar DAN berimpit dengan garis: kedua ujungnya ikut dipertimbangkan.
    collinear = (np.abs(denominator) == 0.0) & (np.abs(da) == 0.0)
    lo_candidates = np.where(crosses, hit, np.inf)
    hi_candidates = np.where(crosses, hit, -np.inf)
    lo_candidates = np.where(collinear, np.minimum(b, b_next), lo_candidates)
    hi_candidates = np.where(collinear, np.maximum(b, b_next), hi_candidates)

    lo = lo_candidates.min(axis=1)
    hi = hi_candidates.max(axis=1)
    lengths = np.where(np.isfinite(lo) & np.isfinite(hi), hi - lo, 0.0)
    return np.asarray(np.maximum(lengths, 0.0), dtype=np.float64)


def cut_element_widths(
    coords: np.ndarray,
    areas: np.ndarray,
    *,
    cut_axis: int,
    method: str = "exact",
    cut_position: float | None = None,
) -> np.ndarray:
    """Lebar kontribusi tiap elemen pada garis potong [m].

    Tiga metode; PRD Bagian 7.2(4) menandai pilihannya `[PERLU DIKONFIRMASI]` dan
    merekomendasikan opsi (a) dengan (b) sebagai fallback:

    * ``"exact"`` (**default**) -- opsi (a): panjang potongan sebenarnya di dalam elemen
      (:func:`cut_intersection_lengths`). Membutuhkan `cut_position`.
    * ``"bbox"`` -- rentang bounding box elemen pada sumbu tegak lurus. Sama dengan
      ``"exact"`` untuk quad sejajar sumbu, tetapi MELEBIHKAN untuk quad miring.
    * ``"area_ratio"`` -- opsi (b): ``A_e`` dibagi rentang elemen searah garis potong.

    Ketiganya dibandingkan pada VC-3 (mesh terstruktur -- hasilnya harus sama) dan
    VC-2 (mesh tak beraturan -- hanya ``"exact"`` yang tetap benar).
    """
    if method == "exact":
        if cut_position is None:
            raise ValueError("method='exact' membutuhkan `cut_position`.")
        return cut_intersection_lengths(coords, cut_axis=cut_axis, cut_position=cut_position)
    if method == "bbox":
        return element_extent(coords, 1 - cut_axis)
    if method == "area_ratio":
        along = element_extent(coords, cut_axis)
        with np.errstate(divide="ignore", invalid="ignore"):
            widths = np.where(along > 0.0, areas / along, np.nan)
        return np.asarray(widths, dtype=np.float64)
    raise ValueError(
        f"method = {method!r} tidak dikenal. Pilih 'exact', 'bbox', atau 'area_ratio'."
    )


def integrate_strip(values: np.ndarray, widths: np.ndarray, mask: np.ndarray) -> float:
    r"""Integrasi diskret :math:`M = \sum_{e \in strip} v_e w_e` [N.m].

    Elemen ber-nilai `NaN` DIABAIKAN, bukan meracuni hasil menjadi NaN -- konsisten
    dengan PRD Core 3 (nilai tak terdefinisi = data, bukan kegagalan model). Bila
    SELURUH elemen dalam lajur bernilai NaN, hasilnya NaN.
    """
    selected = values[mask]
    weights = widths[mask]
    if selected.size == 0:
        return float("nan")
    finite = np.isfinite(selected) & np.isfinite(weights)
    if not finite.any():
        return float("nan")
    return float(np.sum(selected[finite] * weights[finite]))


# ---------------------------------------------------------------------------
# Wood-Armer (PRD Bagian 7.2(6)) -- BELUM DIIMPLEMENTASIKAN
# ---------------------------------------------------------------------------


def wood_armer(
    m_xx: np.ndarray, m_yy: np.ndarray, m_xy: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Momen desain Wood-Armer untuk tulangan ortogonal.

    **BELUM DIIMPLEMENTASIKAN -- sengaja.**

    Rumus dasarnya (``m_x* = m_xx + |m_xy|``) mudah dituliskan, tetapi metode Wood-Armer
    yang lengkap memuat **aturan koreksi** bila salah satu hasilnya negatif (momen
    dialihkan ke arah lainnya). PRD Bagian 7.2(6) menyatakan aturan koreksi itu WAJIB
    disalin dari sumber primer -- Wood, R.H. (1968), *The reinforcement of slabs in
    accordance with a pre-determined field of moments*, Concrete Vol. 2 -- dan
    **bukan direkonstruksi dari ingatan**.

    Menuliskan hanya rumus dasarnya akan menghasilkan momen desain yang
    **tidak konservatif** pada daerah dengan momen berlawanan tanda, tanpa peringatan
    apa pun. Pada tingkat liabilitas PRD Bagian 1.3, itu tidak dapat diterima.

    Blocker: PRD Bagian 7.5 referensi R4.
    """
    raise NotImplementedError(
        "Wood-Armer belum diimplementasikan: aturan koreksi (kasus salah satu momen "
        "desain negatif) wajib disalin dari sumber primer Wood (1968), bukan "
        "direkonstruksi dari ingatan (PRD Bagian 7.2(6), referensi R4).\n"
        "  Sediakan rumus lengkap beserta sitasinya, atau jalankan tanpa --wood-armer "
        "dan pakai m_xx / m_yy / m_xy apa adanya."
    )
