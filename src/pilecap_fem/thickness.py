"""Medan tebal pilecap: seragam, parametrik "perisai", atau CSV per bidang (pilecap tapper).

Seluruh nilai dalam SI (meter). Modul ini murni geometri: tidak membaca berkas (CSV dibaca
`io_utils`), tidak mengimpor OpenSees, dan tidak mengimpor `geometry_builder` -- yang
mengimpornya secara malas, karena `validators` sudah mengimpor `geometry_builder`.

.. rubric:: Satu representasi: himpunan bidang tebal

Setiap sumber tebal yang tidak seragam dinyatakan sebagai **bidang**: poligon 3 atau 4 titik
dengan tebal di tiap titik sudutnya.

* segitiga diinterpolasi barisentrik -- bidang datar eksak;
* segiempat lewat inversi bilinear -- eksak bidang datar bila dua sisinya sejajar (bidang
  miring atap perisai pada denah persegi), permukaan bergaris lurus bila tidak (denah
  trapesium).

Profil parametrik hanya MEMBANGKITKAN bidang-bidang itu; CSV memberikannya langsung. Jalur
evaluasinya satu, sehingga parametrik dan CSV yang menggambarkan bentuk yang sama memberi
tebal elemen yang identik.

.. rubric:: Mengapa CSV per bidang, bukan titik x, y, t

Dengan titik saja, segitiga harus dibentuk otomatis (Delaunay), dan bila titiknya sedikit
-- delapan titik sudah cukup untuk pilecap P2 -- triangulasi itu tidak dijamin mengikuti
garis jurai: sudut pilecap bisa terhubung ke sudut plateau milik bidang sebelah, sehingga
permukaannya lain dari gambar tanpa ada yang salah ketik. Bidang yang ditulis eksplisit
persis mengikuti garis di denah.

.. rubric:: Pita tebal

Elemen shell -- di OpenSees maupun Midas -- hanya punya SATU tebal. Pilecap tapper karena
itu dilihat sebagai tangga per elemen: tebal di titik berat elemen. Tebal itu lalu
dibulatkan ke kelipatan `pilecap.thickness_step`; elemen bertebal sama setelah pembulatan
disebut satu **pita** dan berbagi satu penampang OpenSees / satu ID `*THICKNESS` Midas.
Pita bukan garis offset dan bukan node baru: mesh tidak berubah sama sekali.

Pilecap SERAGAM tidak pernah melewati jalur ini, termasuk pembulatannya: tebal 1,234 m
harus tetap 1,234 m, bukan 1,23 m.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Any, Literal, cast

import numpy as np
import shapely
from shapely.geometry import Polygon
from shapely.geometry.polygon import orient

from pilecap_fem.validators import InputError

Source = Literal["parametrik", "csv"]

#: Langkah pembulatan tebal bawaan [m]. Lihat docstring modul.
THICKNESS_STEP_DEFAULT = 0.010

#: Toleransi panjang: dua titik dianggap berimpit, atau titik dianggap di tepi bidang [m].
TOL_PANJANG = 1e-6

#: Toleransi tebal untuk kontinuitas di tepi bidang yang dipakai bersama [m].
TOL_TEBAL = 1e-6

#: Toleransi relatif luas untuk gabungan bidang terhadap poligon pilecap.
TOL_LUAS_REL = 1e-6


# ---------------------------------------------------------------------------
# Bidang tebal
# ---------------------------------------------------------------------------


def _cross(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.asarray(a[..., 0] * b[..., 1] - a[..., 1] * b[..., 0], dtype=np.float64)


@dataclass(frozen=True)
class ThicknessFace:
    """Satu bidang: poligon 3/4 titik (CCW) dengan tebal [m] di tiap titik sudutnya."""

    face_id: str
    xy: np.ndarray
    t: np.ndarray

    def __post_init__(self) -> None:
        xy = np.asarray(self.xy, dtype=np.float64)
        t = np.asarray(self.t, dtype=np.float64)
        if xy.ndim != 2 or xy.shape[1] != 2 or xy.shape[0] not in (3, 4):
            raise InputError(
                f"Bidang tebal {self.face_id!r}: butuh 3 atau 4 titik sudut, diterima "
                f"{xy.shape[0] if xy.ndim == 2 else xy.shape}. Bidang dengan lebih banyak "
                "titik pecah menjadi segitiga/segiempat."
            )
        if t.shape != (xy.shape[0],):
            raise ValueError(f"Bidang {self.face_id!r}: jumlah tebal tidak sama dengan titik.")
        if not np.all(np.isfinite(xy)) or not np.all(np.isfinite(t)):
            raise InputError(f"Bidang tebal {self.face_id!r}: ada koordinat/tebal kosong.")
        if np.any(t <= 0.0):
            raise InputError(f"Bidang tebal {self.face_id!r}: tebal harus > 0, diterima {t}.")

        poly = Polygon(xy)
        if not poly.is_valid or poly.area <= TOL_PANJANG**2:
            raise InputError(
                f"Bidang tebal {self.face_id!r} tidak sah: berpotongan sendiri atau luasnya nol. "
                "Urutkan titik sudutnya mengelilingi bidang."
            )
        # Orientasi CCW dengan MEMBALIK urutan (bukan memutarnya), supaya tiap tebal tetap
        # menempel pada titik sudutnya; inversi bilinear tetap sah untuk urutan terbalik.
        luas_bertanda = 0.5 * float(np.sum(_cross(xy, np.roll(xy, -1, axis=0))))
        if luas_bertanda < 0.0:
            xy, t = xy[::-1].copy(), t[::-1].copy()
        if xy.shape[0] == 4 and abs(poly.convex_hull.area - poly.area) > TOL_LUAS_REL * poly.area:
            raise InputError(
                f"Bidang tebal {self.face_id!r} adalah segiempat cekung. Pecah menjadi dua "
                "segitiga."
            )
        object.__setattr__(self, "xy", xy)
        object.__setattr__(self, "t", t)

    @functools.cached_property
    def polygon(self) -> Polygon:
        return Polygon(self.xy)

    @functools.cached_property
    def _area_tol(self) -> Polygon:
        return self.polygon.buffer(TOL_PANJANG)

    def covers(self, pts: np.ndarray) -> np.ndarray:
        """Titik di dalam bidang atau di tepinya (dengan toleransi)."""
        return np.asarray(shapely.intersects_xy(self._area_tol, pts[:, 0], pts[:, 1]))

    def interpolate(self, pts: np.ndarray) -> np.ndarray:
        """Tebal di titik-titik `pts` (n, 2). Titik di luar bidang dijepit ke tepinya."""
        pts = np.atleast_2d(np.asarray(pts, dtype=np.float64))
        if self.xy.shape[0] == 3:
            return self._interp_tri(pts)
        return self._interp_quad(pts)

    def _interp_tri(self, pts: np.ndarray) -> np.ndarray:
        a, b, c = self.xy
        det = _cross(b - a, c - a)
        l1 = _cross(pts - a, c - a) / det
        l2 = _cross(b - a, pts - a) / det
        w = np.stack([1.0 - l1 - l2, l1, l2], axis=-1)
        w = np.clip(w, 0.0, None)
        w /= w.sum(axis=-1, keepdims=True)
        return np.asarray(w @ self.t, dtype=np.float64)

    def _interp_quad(self, pts: np.ndarray) -> np.ndarray:
        u, v = _inverse_bilinear(self.xy, pts)
        t0, t1, t2, t3 = self.t
        hasil = (1 - u) * (1 - v) * t0 + u * (1 - v) * t1 + u * v * t2 + (1 - u) * v * t3
        return np.asarray(hasil, dtype=np.float64)

    def to_json(self) -> dict[str, Any]:
        return {"face": self.face_id, "xy_m": self.xy.tolist(), "t_m": self.t.tolist()}

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> ThicknessFace:
        return cls(str(data["face"]), np.asarray(data["xy_m"]), np.asarray(data["t_m"]))


def _inverse_bilinear(quad: np.ndarray, pts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Koordinat (u, v) di [0, 1]^2 untuk titik `pts` pada segiempat `quad` (a, b, c, d).

    Pemetaan: P(u, v) = a + e u + f v + g u v, dengan e = b - a, f = d - a, g = a - b + c - d.
    Kedua akar persamaan kuadrat dicoba dan dipilih yang rekonstruksinya paling dekat;
    hasilnya dijepit ke [0, 1] supaya titik di tepi (toleransi) tidak diekstrapolasi.
    """
    a, b, c, d = quad
    e, f, g = b - a, d - a, a - b + c - d
    h = pts - a
    k2 = float(_cross(g, f))
    k1 = _cross(e, f) + _cross(h, g)
    k0 = _cross(h, e)

    def _u_dari_v(v: np.ndarray) -> np.ndarray:
        den_x = e[0] + g[0] * v
        den_y = e[1] + g[1] * v
        pakai_x = np.abs(den_x) >= np.abs(den_y)
        with np.errstate(divide="ignore", invalid="ignore"):
            ux = (h[:, 0] - f[0] * v) / den_x
            uy = (h[:, 1] - f[1] * v) / den_y
        return np.asarray(np.where(pakai_x, ux, uy), dtype=np.float64)

    skala = max(abs(float(_cross(e, f))), 1e-300)
    if abs(k2) <= 1e-12 * skala:
        v = -k0 / k1
        u = _u_dari_v(v)
    else:
        akar = np.sqrt(np.maximum(k1 * k1 - 4.0 * k0 * k2, 0.0))
        kandidat = []
        for tanda in (-1.0, 1.0):
            v_k = (-k1 + tanda * akar) / (2.0 * k2)
            u_k = _u_dari_v(v_k)
            # Akar yang tak sah memang menghasilkan inf/NaN; ia dibuang lewat skor di bawah,
            # jadi peringatan numpy-nya hanya derau di log pengguna.
            with np.errstate(invalid="ignore", over="ignore"):
                rekon = a + np.outer(u_k, e) + np.outer(v_k, f) + np.outer(u_k * v_k, g)
                galat = np.linalg.norm(rekon - pts, axis=1)
                luar = np.maximum(0.0, np.maximum(-u_k, u_k - 1)) + np.maximum(
                    0.0, np.maximum(-v_k, v_k - 1)
                )
            with np.errstate(invalid="ignore"):
                skor = galat + luar
            # Akar yang penyebutnya nol memberi NaN/inf. NaN WAJIB dianggap terburuk: tanpa
            # ini `0 < NaN` bernilai salah dan akar tak sah itulah yang terpilih -- terukur di
            # sudut pilecap, yang lalu mendapat tebal plateau alih-alih tebal tepi.
            kandidat.append((u_k, v_k, np.where(np.isfinite(skor), skor, np.inf)))
        pilih_kedua = kandidat[1][2] < kandidat[0][2]
        u = np.where(pilih_kedua, kandidat[1][0], kandidat[0][0])
        v = np.where(pilih_kedua, kandidat[1][1], kandidat[0][1])
    return np.clip(u, 0.0, 1.0), np.clip(v, 0.0, 1.0)


# ---------------------------------------------------------------------------
# Medan tebal
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThicknessField:
    """Medan tebal TIDAK seragam. Pilecap seragam diwakili `None`, bukan objek ini."""

    source: Source
    faces: tuple[ThicknessFace, ...]
    step: float
    #: Nama berkas CSV (bila `source == "csv"`), untuk laporan dan manifest.
    file: str | None = None
    #: Parameter profil parametrik (bila `source == "parametrik"`), untuk laporan.
    params: dict[str, float] = field(default_factory=dict)

    @property
    def t_max(self) -> float:
        return float(max(f.t.max() for f in self.faces))

    @property
    def t_min(self) -> float:
        return float(min(f.t.min() for f in self.faces))

    def thickness_at(self, xy: np.ndarray) -> np.ndarray:
        """Tebal [m] di titik-titik (n, 2). Titik di luar seluruh bidang -> InputError."""
        pts = np.atleast_2d(np.asarray(xy, dtype=np.float64))
        out = np.full(len(pts), np.nan)
        for face in self.faces:
            sisa = np.flatnonzero(np.isnan(out))
            if sisa.size == 0:
                break
            kena = sisa[face.covers(pts[sisa])]
            if kena.size:
                out[kena] = face.interpolate(pts[kena])
        hilang = np.flatnonzero(np.isnan(out))
        if hilang.size:
            x, y = pts[hilang[0]]
            raise InputError(
                f"Titik ({x:.4f}, {y:.4f}) m tidak berada di bidang tebal mana pun "
                f"({hilang.size} titik). Bidang tebal harus menutup seluruh pilecap."
            )
        return out

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "step_m": self.step,
            "file": self.file,
            "params_m": dict(self.params),
            "faces": [f.to_json() for f in self.faces],
        }

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> ThicknessField:
        return cls(
            source=data["source"],
            faces=tuple(ThicknessFace.from_json(f) for f in data["faces"]),
            step=float(data["step_m"]),
            file=data.get("file"),
            params={k: float(v) for k, v in (data.get("params_m") or {}).items()},
        )


def validate_faces(faces: tuple[ThicknessFace, ...], cap: Polygon) -> None:
    """Bidang harus menutup pilecap tanpa celah dan tumpang tindih, dan tebalnya kontinu.

    Lompatan tebal di tepi yang dipakai bersama hampir selalu salah ketik, jadi ditolak --
    termasuk titik sudut satu bidang yang jatuh di tengah sisi bidang lain.
    """
    if not faces:
        raise InputError("Medan tebal tidak punya bidang sama sekali.")
    ids = [f.face_id for f in faces]
    kembar = sorted({i for i in ids if ids.count(i) > 1})
    if kembar:
        raise InputError(f"ID bidang tebal dipakai lebih dari sekali: {kembar}.")

    gabungan = shapely.union_all([f.polygon for f in faces])
    tol_luas = TOL_LUAS_REL * cap.area
    jumlah_luas = sum(f.polygon.area for f in faces)
    if jumlah_luas - gabungan.area > tol_luas:
        pasangan = [
            (a.face_id, b.face_id)
            for i, a in enumerate(faces)
            for b in faces[i + 1 :]
            if a.polygon.intersection(b.polygon).area > tol_luas
        ]
        raise InputError(f"Bidang tebal saling tumpang tindih: {pasangan[:5]}.")
    selisih = cap.symmetric_difference(gabungan).area
    if selisih > tol_luas:
        celah = cap.difference(gabungan).area
        lebih = gabungan.difference(cap).area
        raise InputError(
            "Bidang tebal tidak menutup pilecap dengan tepat: "
            f"celah {celah:.6f} m2 tidak tertutup bidang mana pun, "
            f"{lebih:.6f} m2 bidang berada di luar pilecap."
        )

    for a in faces:
        for titik, t_a in zip(a.xy, a.t, strict=True):
            for b in faces:
                if b is a or b.polygon.exterior.distance(shapely.Point(titik)) > TOL_PANJANG:
                    continue
                t_b = float(b.interpolate(titik[None, :])[0])
                if abs(t_b - t_a) > TOL_TEBAL:
                    raise InputError(
                        f"Tebal tidak kontinu di ({titik[0]:.4f}, {titik[1]:.4f}) m: bidang "
                        f"{a.face_id!r} memberi {t_a * 1e3:.1f} mm, bidang {b.face_id!r} "
                        f"memberi {t_b * 1e3:.1f} mm. Tepi yang dipakai bersama harus bertebal "
                        "sama."
                    )


def faces_perisai(
    cap_xy: np.ndarray,
    pier: Polygon,
    *,
    t_max: float,
    t_edge: float,
    shoulder: float,
) -> tuple[ThicknessFace, ...]:
    """Bidang profil "perisai": plateau datar di sekitar pier + 4 bidang miring ke tepi.

    Plateau = pier diperbesar `shoulder` (sudut tajam). Tiap sisi pilecap berpasangan dengan
    sisi plateau yang menghadapnya; keduanya dihubungkan garis jurai sudut-ke-sudut.
    """
    cap = orient(Polygon(cap_xy), 1.0)
    cap_v = np.asarray(cap.exterior.coords)[:-1]
    if len(cap_v) != 4 or abs(cap.convex_hull.area - cap.area) > TOL_LUAS_REL * cap.area:
        raise InputError(
            f"Profil tebal parametrik butuh pilecap segiempat cembung; pilecap ini punya "
            f"{len(cap_v)} titik sudut. Untuk bentuk lain, berikan tebal sebagai CSV per bidang."
        )

    diperbesar = pier.buffer(shoulder, join_style="mitre") if shoulder > 0 else pier
    # `simplify` membuang titik segaris yang kadang ditinggalkan buffer bersudut tajam.
    sederhana = cast(Polygon, diperbesar.simplify(TOL_PANJANG))
    plateau = orient(Polygon(sederhana.exterior.coords), 1.0)
    pl_v = np.asarray(plateau.exterior.coords)[:-1]
    if len(pl_v) != 4:
        raise InputError(
            "Profil tebal parametrik butuh pier segiempat (persegi panjang); pier ini "
            f"menghasilkan plateau {len(pl_v)} titik. Berikan tebal sebagai CSV per bidang."
        )
    if not cap.buffer(-TOL_PANJANG).contains(plateau):
        raise InputError(
            f"Plateau (pier + bahu {shoulder * 1e3:.0f} mm) keluar dari atau menyentuh tepi "
            "pilecap; tidak ada ruang untuk bidang miring."
        )

    biaya = [sum(np.linalg.norm(cap_v[i] - pl_v[(i + k) % 4]) for i in range(4)) for k in range(4)]
    k = int(np.argmin(biaya))
    pl_v = np.roll(pl_v, -k, axis=0)

    faces = [ThicknessFace("PLATEAU", pl_v.copy(), np.full(4, t_max))]
    for i in range(4):
        j = (i + 1) % 4
        quad = np.array([cap_v[i], cap_v[j], pl_v[j], pl_v[i]])
        try:
            faces.append(
                ThicknessFace(f"MIRING_{i + 1}", quad, np.array([t_edge, t_edge, t_max, t_max]))
            )
        except InputError as exc:
            raise InputError(
                f"Bidang miring ke-{i + 1} tidak sah ({exc}). Garis jurai saling berpotongan; "
                "berikan tebal sebagai CSV per bidang."
            ) from exc
    return tuple(faces)


def build_field(
    cfg: dict[str, Any],
    *,
    cap_xy: np.ndarray,
    piers: list[Polygon],
    pier_shapes: list[str],
    csv_faces: tuple[ThicknessFace, ...] | None = None,
    csv_file: str | None = None,
) -> ThicknessField | None:
    """Medan tebal dari config SI + CSV opsional. `None` = pilecap seragam.

    Prioritas: CSV per bidang > profil parametrik > seragam.
    """
    pilecap = cfg.get("pilecap") or {}
    step = pilecap.get("thickness_step")
    step = THICKNESS_STEP_DEFAULT if step is None else float(step)
    if not step > 0.0:
        raise InputError(f"`pilecap.thickness_step` = {step} harus > 0.")
    cap = Polygon(cap_xy)

    if csv_faces is not None:
        validate_faces(csv_faces, cap)
        field_ = ThicknessField("csv", csv_faces, step, file=csv_file)
    elif pilecap.get("edge_thickness") is not None:
        t_max = float(pilecap["thickness"])
        t_edge = float(pilecap["edge_thickness"])
        shoulder = pilecap.get("taper_shoulder")
        if shoulder is None:
            raise InputError(
                "`pilecap.taper_shoulder` wajib diisi bila `pilecap.edge_thickness` diisi "
                "(lebar bahu datar di sekeliling pier; isi 0 bila bidang miring langsung "
                "dimulai dari muka pier)."
            )
        shoulder = float(shoulder)
        if not 0.0 < t_edge <= t_max:
            raise InputError(
                f"`pilecap.edge_thickness` = {t_edge} m harus > 0 dan <= `pilecap.thickness` "
                f"= {t_max} m (tebal maksimum di plateau)."
            )
        if shoulder < 0.0:
            raise InputError(f"`pilecap.taper_shoulder` = {shoulder} m tidak boleh negatif.")
        if len(piers) != 1 or pier_shapes[0] not in ("rectangular", "polygon"):
            raise InputError(
                "Profil tebal parametrik butuh tepat satu pier persegi; config ini punya "
                f"{len(piers)} pier ({', '.join(pier_shapes)}). Berikan tebal sebagai CSV per "
                "bidang."
            )
        faces = faces_perisai(cap_xy, piers[0], t_max=t_max, t_edge=t_edge, shoulder=shoulder)
        validate_faces(faces, cap)
        field_ = ThicknessField(
            "parametrik",
            faces,
            step,
            params={"thickness": t_max, "edge_thickness": t_edge, "taper_shoulder": shoulder},
        )
    else:
        return None

    cover = (cfg.get("design") or {}).get("cover")
    if cover is not None and float(cover) >= 0.5 * field_.t_min:
        raise InputError(
            f"`design.cover` = {cover} m tidak masuk akal terhadap tebal tertipis pilecap "
            f"{field_.t_min} m: selimut satu muka mencapai setengah tebal, sehingga tidak "
            "tersisa tinggi efektif."
        )
    return field_


# ---------------------------------------------------------------------------
# Pita tebal per elemen
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThicknessBands:
    """Tebal per elemen yang sudah dikelompokkan. Satu pita = satu penampang / satu ID Midas."""

    #: Indeks pita per elemen (0-based) ke `values`.
    elem_band: np.ndarray
    #: Tebal tiap pita [m], urut naik.
    values: np.ndarray
    #: Langkah pembulatan [m]; `None` = seragam, tanpa pembulatan.
    step: float | None

    @property
    def n_bands(self) -> int:
        return len(self.values)

    @property
    def elem_thickness(self) -> np.ndarray:
        return np.asarray(self.values[self.elem_band], dtype=np.float64)


def uniform_bands(n_elements: int, thickness: float) -> ThicknessBands:
    """Satu pita bertebal persis `thickness` -- jalur seragam, tanpa pembulatan."""
    return ThicknessBands(np.zeros(n_elements, dtype=np.int64), np.array([float(thickness)]), None)


def element_bands(
    field_: ThicknessField | None, thickness: float, centroids: np.ndarray
) -> ThicknessBands:
    """Tebal di titik berat tiap elemen, dibulatkan ke kelipatan `field_.step`."""
    if field_ is None:
        return uniform_bands(len(centroids), thickness)
    t = field_.thickness_at(centroids)
    dibulatkan = np.round(np.round(t / field_.step) * field_.step, 9)
    if np.any(dibulatkan <= 0.0):
        raise InputError(
            f"`pilecap.thickness_step` = {field_.step} m terlalu kasar: ada elemen yang "
            "tebalnya dibulatkan menjadi nol."
        )
    values, inv = np.unique(dibulatkan, return_inverse=True)
    return ThicknessBands(inv.astype(np.int64), values, field_.step)


__all__ = [
    "THICKNESS_STEP_DEFAULT",
    "ThicknessBands",
    "ThicknessFace",
    "ThicknessField",
    "build_field",
    "element_bands",
    "faces_perisai",
    "uniform_bands",
    "validate_faces",
]
