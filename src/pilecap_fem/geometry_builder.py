"""Data model geometri + generator koordinat pilecap / pile / pier (PRD Bagian 3.2).

Seluruh nilai di modul ini SUDAH dalam SI (meter). Konversi satuan terjadi eksklusif di
`io_utils.py` (PRD Bagian 4.1). Modul ini tidak melakukan I/O file dan tidak mengimpor
`io_utils` -- arah dependensi hanya satu: io_utils -> geometry_builder.

Validasi semantik (pile di luar pilecap, polygon self-intersecting, dsb.) TIDAK dilakukan
di sini melainkan di `validators.py`, agar pesan error terkumpul di satu tempat dan mudah
diuji secara parametrized (PRD Bagian 15.1).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
from shapely.geometry import Point, Polygon, box

from pilecap_fem import config

PierShape = Literal["rectangular", "circular", "polygon"]
GeometrySource = Literal["cli_flag", "csv_autodetect", "json_standard", "json_grid"]

#: Jumlah segmen yang dipakai saat lingkaran didekati sebagai polygon shapely.
#: Hanya untuk pengecekan geometri (validators) dan penggambaran; pembangunan mesh
#: memakai `occ.addDisk` yang eksak, bukan pendekatan ini.
_CIRCLE_QUAD_SEGMENTS = 64


# ---------------------------------------------------------------------------
# Primitif
# ---------------------------------------------------------------------------


@dataclass(frozen=True, eq=False)
class Polygon2D:
    """Polygon tertutup, disimpan TERBUKA (titik terakhir tidak mengulang titik pertama).

    Orientasi selalu dinormalisasi ke CCW oleh `normalize_ccw()` sebelum objek dibuat
    (PRD Bagian 5.1(d)). Satuan: meter.
    """

    vertices: np.ndarray

    def __post_init__(self) -> None:
        arr = np.asarray(self.vertices, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 2:
            raise ValueError(
                f"Polygon2D butuh array bentuk (n, 2), diterima {arr.shape}. "
                "Setiap baris adalah koordinat (x, y) dalam meter."
            )
        if arr.shape[0] < 3:
            raise ValueError(
                f"Polygon2D butuh minimal 3 titik, diterima {arr.shape[0]}. "
                "(PRD Bagian 5.3 rule 12)"
            )
        object.__setattr__(self, "vertices", arr)

    @property
    def n_vertices(self) -> int:
        return int(self.vertices.shape[0])

    @property
    def signed_area(self) -> float:
        """Luas bertanda (shoelace). Positif = CCW."""
        return signed_area(self.vertices)

    @property
    def area(self) -> float:
        """Luas absolut [m^2]."""
        return abs(self.signed_area)

    @property
    def centroid(self) -> tuple[float, float]:
        """Centroid geometris polygon [m] (bukan rata-rata titik sudut)."""
        return polygon_centroid(self.vertices)

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) [m]."""
        return (
            float(self.vertices[:, 0].min()),
            float(self.vertices[:, 1].min()),
            float(self.vertices[:, 0].max()),
            float(self.vertices[:, 1].max()),
        )

    def to_shapely(self) -> Polygon:
        return Polygon(self.vertices)

    def closed_vertices(self) -> np.ndarray:
        """Salinan dengan titik pertama diulang di akhir (untuk plotting)."""
        return np.vstack([self.vertices, self.vertices[:1]])


@dataclass(frozen=True)
class Pile:
    """Satu pile, dimodelkan sebagai disk pada bidang tengah pelat. Satuan: meter."""

    pile_id: str
    x: float
    y: float
    diameter: float

    @property
    def radius(self) -> float:
        return self.diameter / 2.0

    @property
    def nominal_area(self) -> float:
        """Luas analitis pi*r^2 [m^2].

        CATATAN: nilai ini HANYA untuk pelaporan & pengecekan geometri. Tekanan pile
        dihitung dari jumlah luas elemen mesh dalam physical group, bukan dari nilai ini
        (PRD Bagian 7.3).
        """
        return math.pi * self.radius**2

    def to_shapely(self) -> Polygon:
        return Point(self.x, self.y).buffer(self.radius, quad_segs=_CIRCLE_QUAD_SEGMENTS)

    @property
    def group_name(self) -> str:
        return f"{config.GROUP_PILE_PREFIX}{self.pile_id}"


@dataclass(frozen=True)
class Pier:
    """Satu pier. Bentuk parametrik dipertahankan agar mesh_engine dapat memakai OCC.

    `centerline` adalah titik acuan penampang kritis (PRD Bagian 7.2(5)). Untuk pier dari
    JSON nilainya diambil dari `pier.centerline`; untuk pier dari `pier_polygon.csv`
    nilainya diturunkan dari centroid polygon (keputusan multi-pier, lihat plan).
    """

    pier_id: str
    shape: PierShape
    centerline: tuple[float, float]
    polygon: Polygon2D | None = None
    width_x: float | None = None
    width_y: float | None = None
    diameter: float | None = None

    def to_shapely(self) -> Polygon:
        if self.shape == "polygon":
            if self.polygon is None:
                raise ValueError(f"Pier {self.pier_id!r} bershape 'polygon' tetapi polygon=None.")
            return self.polygon.to_shapely()
        if self.shape == "rectangular":
            if self.width_x is None or self.width_y is None:
                raise ValueError(
                    f"Pier {self.pier_id!r} bershape 'rectangular' tetapi width_x/width_y kosong."
                )
            cx, cy = self.centerline
            return box(
                cx - self.width_x / 2.0,
                cy - self.width_y / 2.0,
                cx + self.width_x / 2.0,
                cy + self.width_y / 2.0,
            )
        if self.shape == "circular":
            if self.diameter is None:
                raise ValueError(
                    f"Pier {self.pier_id!r} bershape 'circular' tetapi diameter kosong."
                )
            return Point(*self.centerline).buffer(
                self.diameter / 2.0, quad_segs=_CIRCLE_QUAD_SEGMENTS
            )
        raise ValueError(f"Shape pier tidak dikenal: {self.shape!r}")

    @property
    def area(self) -> float:
        return float(self.to_shapely().area)

    @property
    def group_name(self) -> str:
        return f"{config.GROUP_PIER_PREFIX}{self.pier_id}"


# ---------------------------------------------------------------------------
# Resolusi sumber geometri (PRD Bagian 5.2.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntityResolution:
    """Dari mana geometri satu entitas berasal. Langsung serializable ke run_manifest.json."""

    source: GeometrySource
    file: Path | None = None
    sha256: str | None = None
    overridden_json_keys: tuple[str, ...] = ()

    @property
    def is_override(self) -> bool:
        return self.source in ("cli_flag", "csv_autodetect")

    def to_manifest(self) -> dict[str, object]:
        return {
            "source": self.source,
            "file": self.file.as_posix() if self.file is not None else None,
            "sha256": self.sha256,
            "overridden_json_keys": list(self.overridden_json_keys),
        }


@dataclass(frozen=True)
class GeometryResolution:
    """Resolusi ketiga entitas. Wajib terisi lengkap meskipun tidak ada override."""

    pilecap: EntityResolution
    pile: EntityResolution
    pier: EntityResolution

    def to_manifest(self) -> dict[str, dict[str, object]]:
        return {
            "pilecap": self.pilecap.to_manifest(),
            "pile": self.pile.to_manifest(),
            "pier": self.pier.to_manifest(),
        }

    def has_any_override(self) -> bool:
        return any(r.is_override for r in (self.pilecap, self.pile, self.pier))

    def as_summary_line(self) -> str:
        return f"pilecap={self.pilecap.source} | pile={self.pile.source} | pier={self.pier.source}"


@dataclass(frozen=True)
class ResolvedGeometrySources:
    """Muatan CSV yang berhasil diresolusi + catatan sumbernya.

    Field bernilai `None` berarti entitas tersebut memakai parameter JSON.
    Diisi oleh `io_utils.resolve_geometry_sources()`, dikonsumsi oleh
    `build_geometry_model()`.
    """

    resolution: GeometryResolution
    pilecap_polygon: Polygon2D | None = None
    piles: tuple[Pile, ...] | None = None
    pier_polygons: tuple[tuple[str, Polygon2D], ...] | None = None


@dataclass(frozen=True)
class GeometryModel:
    """Model geometri lengkap dalam SI (meter). Kontrak antar-modul untuk semua fase."""

    pilecap: Polygon2D
    thickness: float
    piles: tuple[Pile, ...]
    piers: tuple[Pier, ...]
    resolution: GeometryResolution
    warnings: tuple[str, ...] = field(default=())

    @property
    def n_piles(self) -> int:
        return len(self.piles)

    @property
    def n_piers(self) -> int:
        return len(self.piers)

    @property
    def min_pile_diameter(self) -> float:
        return min(p.diameter for p in self.piles)

    @property
    def pilecap_area(self) -> float:
        return self.pilecap.area

    def pile_by_id(self, pile_id: str) -> Pile:
        for p in self.piles:
            if p.pile_id == pile_id:
                return p
        raise KeyError(
            f"pile_id {pile_id!r} tidak ada. Tersedia: {[p.pile_id for p in self.piles]}"
        )


# ---------------------------------------------------------------------------
# Fungsi geometri murni
# ---------------------------------------------------------------------------


def signed_area(vertices: np.ndarray) -> float:
    """Luas bertanda polygon terbuka dengan rumus shoelace. Positif = CCW."""
    x = np.asarray(vertices, dtype=np.float64)[:, 0]
    y = np.asarray(vertices, dtype=np.float64)[:, 1]
    return float(0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def polygon_centroid(vertices: np.ndarray) -> tuple[float, float]:
    """Centroid geometris polygon terbuka.

    Fallback ke rata-rata titik sudut bila luasnya nol (polygon degenerate); kasus itu
    sendiri di-RAISE oleh `validators.validate_geometry()` (rule 13c), fallback ini hanya
    mencegah pembagian nol sebelum validator sempat berjalan.
    """
    v = np.asarray(vertices, dtype=np.float64)
    a = signed_area(v)
    if abs(a) < 1e-15:
        return (float(v[:, 0].mean()), float(v[:, 1].mean()))
    x, y = v[:, 0], v[:, 1]
    x_next, y_next = np.roll(x, -1), np.roll(y, -1)
    cross = x * y_next - x_next * y
    cx = float(np.sum((x + x_next) * cross) / (6.0 * a))
    cy = float(np.sum((y + y_next) * cross) / (6.0 * a))
    return (cx, cy)


def normalize_ccw(vertices: np.ndarray) -> np.ndarray:
    """Kembalikan titik-titik polygon dengan orientasi CCW.

    Orientasi input tidak perlu diperhatikan user (PRD Bagian 5.1(d)); normalisasi
    dilakukan di sini agar seluruh hilir (fragment gmsh, shapely, plotting) melihat
    satu konvensi saja.
    """
    v = np.asarray(vertices, dtype=np.float64)
    return v if signed_area(v) >= 0.0 else v[::-1].copy()


def drop_repeated_closing_vertex(vertices: np.ndarray, *, atol: float = 1e-12) -> np.ndarray:
    """Buang baris penutup yang mengulang titik pertama (PRD Bagian 5.1(d))."""
    v = np.asarray(vertices, dtype=np.float64)
    if v.shape[0] >= 2 and np.allclose(v[0], v[-1], atol=atol, rtol=0.0):
        return v[:-1].copy()
    return v


def polygon_from_rect(length_x: float, length_y: float, origin: tuple[float, float]) -> Polygon2D:
    """Persegi panjang berpusat di `origin` -> Polygon2D 4 titik, CCW.

    Pilecap SELALU direpresentasikan sebagai polygon agar seluruh modul hilir hanya punya
    satu jalur kode; hanya pembangunan entitas OCC yang membedakan bentuk.
    """
    cx, cy = origin
    hx, hy = length_x / 2.0, length_y / 2.0
    verts = np.array(
        [[cx - hx, cy - hy], [cx + hx, cy - hy], [cx + hx, cy + hy], [cx - hx, cy + hy]],
        dtype=np.float64,
    )
    return Polygon2D(normalize_ccw(verts))


# ---------------------------------------------------------------------------
# Builder per entitas
# ---------------------------------------------------------------------------


def build_pilecap(cfg: dict, sources: ResolvedGeometrySources) -> Polygon2D:
    """Polygon pilecap dari CSV (bila ada) atau dari `length_x`/`length_y`/`origin`."""
    if sources.pilecap_polygon is not None:
        return sources.pilecap_polygon
    cap = cfg["pilecap"]
    return polygon_from_rect(
        length_x=cap["length_x"],
        length_y=cap["length_y"],
        origin=tuple(cap["origin"]),
    )


def build_pile_grid(
    *,
    n_col: int,
    n_row: int,
    spacing_x: float,
    spacing_y: float,
    grid_origin: tuple[float, float],
    diameter: float,
) -> tuple[Pile, ...]:
    """Grid pile `n_col x n_row` berpusat di `grid_origin`.

    Penomoran: `P1` .. `Pn`, **row-major dari kiri-bawah** -- baris y terkecil lebih dulu,
    di dalam satu baris x membesar ke kanan. Urutan ini bagian dari kontrak: `pile_id` di
    `pile_reactions.csv` harus cocok dengannya (PRD Bagian 5.3 rule 3).
    """
    ox, oy = grid_origin
    piles: list[Pile] = []
    index = 1
    for j in range(n_row):
        y = oy + (j - (n_row - 1) / 2.0) * spacing_y
        for i in range(n_col):
            x = ox + (i - (n_col - 1) / 2.0) * spacing_x
            piles.append(Pile(pile_id=f"P{index}", x=x, y=y, diameter=diameter))
            index += 1
    return tuple(piles)


def build_piles(cfg: dict, sources: ResolvedGeometrySources) -> tuple[Pile, ...]:
    """Daftar pile dari CSV koordinat (bila ada) atau dari konfigurasi grid JSON."""
    if sources.piles is not None:
        return sources.piles
    pile_cfg = cfg["pile"]
    return build_pile_grid(
        n_col=int(pile_cfg["n_col"]),
        n_row=int(pile_cfg["n_row"]),
        spacing_x=pile_cfg["spacing_x"],
        spacing_y=pile_cfg["spacing_y"],
        grid_origin=tuple(pile_cfg["grid_origin"]),
        diameter=pile_cfg["diameter"],
    )


def build_piers(cfg: dict, sources: ResolvedGeometrySources) -> tuple[Pier, ...]:
    """Daftar pier.

    Dua jalur, sesuai keputusan user (PRD Bagian 17 item 17):

    * **JSON** -- tepat SATU pier (`rectangular` / `circular`), ber-id tetap ``PIER1``,
      centerline diambil dari `pier.centerline`.
    * **`pier_polygon.csv`** -- SATU ATAU LEBIH pier, dipisah kolom `pier_id`. Centerline
      tiap pier diturunkan dari centroid polygon-nya, karena satu nilai `pier.centerline`
      di JSON tidak dapat melayani beberapa pier sekaligus.
    """
    if sources.pier_polygons is not None:
        return tuple(
            Pier(
                pier_id=pier_id,
                shape="polygon",
                centerline=poly.centroid,
                polygon=poly,
            )
            for pier_id, poly in sources.pier_polygons
        )

    pier_cfg = cfg["pier"]
    shape = pier_cfg["shape"]
    centerline = tuple(pier_cfg["centerline"])
    return (
        Pier(
            pier_id="PIER1",
            shape=shape,
            centerline=(float(centerline[0]), float(centerline[1])),
            width_x=pier_cfg.get("width_x"),
            width_y=pier_cfg.get("width_y"),
            diameter=pier_cfg.get("diameter"),
        ),
    )


def build_geometry_model(cfg: dict, sources: ResolvedGeometrySources) -> GeometryModel:
    """Rakit `GeometryModel` lengkap dari config SI + sumber geometri yang sudah diresolusi.

    Tidak memvalidasi -- pemanggil WAJIB menjalankan `validators.validate_geometry()`
    setelah ini (PRD Bagian 3.2).
    """
    return GeometryModel(
        pilecap=build_pilecap(cfg, sources),
        thickness=cfg["pilecap"]["thickness"],
        piles=build_piles(cfg, sources),
        piers=build_piers(cfg, sources),
        resolution=sources.resolution,
    )
