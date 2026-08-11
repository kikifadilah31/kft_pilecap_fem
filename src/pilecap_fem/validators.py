"""Validasi fail-fast (PRD Bagian 5.3, Core 3).

Setiap aturan PRD Bagian 5.3 diimplementasikan di sini dan HANYA di sini, sehingga
`tests/test_validators.py` dapat membuktikan secara parametrized bahwa setiap aturan
memang melempar exception (PRD Bagian 15.1).

Prinsip pembagian:

* **RAISE** untuk kondisi yang membuat hasil tidak bermakna (skema, rentang fisik,
  geometri tidak konsisten).
* **WARNING** hanya untuk kondisi yang hasilnya tetap sah tetapi perlu perhatian engineer.
* Nilai tak terdefinisi di level data (bukan level model) diwakili `np.nan`, bukan raise --
  itu ditangani `postproc_engine.py` pada Fase 2.

Modul ini juga menampung hierarki exception tool agar seluruh modul melempar tipe yang
sama; ini menghindari penambahan file di luar struktur paket PRD Bagian 3.1.
"""

from __future__ import annotations

import itertools
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
from shapely.geometry import Point
from shapely.validation import explain_validity

from pilecap_fem import config, geometry_builder
from pilecap_fem.geometry_builder import GeometryModel

if TYPE_CHECKING:  # pragma: no cover
    import pandas as pd

_log = config.get_logger("validators")


# ---------------------------------------------------------------------------
# Hierarki exception
# ---------------------------------------------------------------------------


class PilecapError(Exception):
    """Basis seluruh error pilecap-fem. CLI menangkap ini dan mencetak pesan ringkas."""


class InputError(PilecapError):
    """File input tidak ada/ambigu, skema salah, tipe salah, satuan tidak dikenal."""


class GeometryError(PilecapError):
    """Geometri tidak konsisten secara fisik (PRD Bagian 5.3 konsistensi geometri)."""


class MeshError(PilecapError):
    """Meshing gagal atau hasilnya tidak memenuhi syarat model FEM."""


class AnalysisError(PilecapError):
    """Analisis FEM gagal konvergen atau gagal cek keseimbangan (Fase 2)."""


# ---------------------------------------------------------------------------
# Helper CSV -- dipanggil dari io_utils saat parsing (rule 1, 13a, 13b)
# ---------------------------------------------------------------------------


def check_required_columns(frame: pd.DataFrame, required: tuple[str, ...], path: Path) -> None:
    """Rule 1 -- kolom wajib CSV hilang."""
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise InputError(
            f"Kolom wajib hilang di {path}: {missing}.\n"
            f"  Kolom yang ditemukan: {list(frame.columns)}\n"
            f"  Kolom yang dibutuhkan: {list(required)}"
        )
    if len(frame) == 0:
        raise InputError(f"File CSV kosong (tidak ada baris data): {path}")


def check_numeric_no_nan(frame: pd.DataFrame, columns: tuple[str, ...], path: Path) -> None:
    """Rule 1 & 4 -- kolom numerik tidak bisa di-cast, atau mengandung NaN."""
    for col in columns:
        try:
            values = frame[col].astype(float)
        except (ValueError, TypeError) as exc:
            raise InputError(
                f"Kolom {col!r} di {path} tidak dapat dikonversi ke angka: {exc}"
            ) from exc
        if values.isna().any():
            bad_rows = (values.index[values.isna()] + 2).tolist()  # +2: header + 1-based
            raise InputError(
                f"Kolom {col!r} di {path} mengandung nilai kosong/NaN pada baris {bad_rows}. "
                "Nilai numerik input tidak boleh kosong (PRD Bagian 5.3 rule 4)."
            )


def check_polygon_vertex_ids(vertex_ids: np.ndarray, path: Path, *, context: str = "") -> None:
    """Rule 13a -- `vertex_id` duplikat, tidak berurutan, atau bukan integer."""
    where = f" ({context})" if context else ""
    as_float = np.asarray(vertex_ids, dtype=np.float64)
    if not np.all(np.isfinite(as_float)) or not np.allclose(as_float, np.round(as_float)):
        raise InputError(
            f"`vertex_id` di {path}{where} harus berupa bilangan bulat. Diterima: {vertex_ids!r}"
        )
    ids = np.round(as_float).astype(np.int64)

    unique, counts = np.unique(ids, return_counts=True)
    duplicates = unique[counts > 1].tolist()
    if duplicates:
        raise InputError(
            f"`vertex_id` duplikat di {path}{where}: {duplicates}. "
            "Setiap titik polygon harus punya vertex_id unik (PRD Bagian 5.3 rule 13a)."
        )

    expected = np.arange(1, len(ids) + 1)
    if not np.array_equal(np.sort(ids), expected):
        raise InputError(
            f"`vertex_id` di {path}{where} harus berurutan 1..{len(ids)} tanpa lompat. "
            f"Diterima (terurut): {np.sort(ids).tolist()} "
            "(PRD Bagian 5.3 rule 13a)."
        )


def check_polygon_no_folded_duplicates(
    vertices: np.ndarray, path: Path, *, context: str = "", atol: float = 1e-9
) -> None:
    """Rule 13b -- dua titik identik yang TIDAK berdampingan (indikasi polygon terlipat)."""
    where = f" ({context})" if context else ""
    n = len(vertices)
    for i, j in itertools.combinations(range(n), 2):
        adjacent = (j - i == 1) or (i == 0 and j == n - 1)
        if adjacent:
            continue
        if np.allclose(vertices[i], vertices[j], atol=atol, rtol=0.0):
            raise InputError(
                f"Polygon di {path}{where} punya dua titik identik yang tidak berdampingan: "
                f"titik ke-{i + 1} dan ke-{j + 1} sama-sama {vertices[i].tolist()}. "
                "Ini indikasi polygon terlipat (PRD Bagian 5.3 rule 13b)."
            )


def check_polygon_area(area: float, path: Path, *, context: str = "") -> None:
    """Rule 13c -- luas polygon hasil pembacaan <= 0 (degenerate)."""
    where = f" ({context})" if context else ""
    if area <= 0.0 or not math.isfinite(area):
        raise InputError(
            f"Polygon di {path}{where} degenerate: luas = {area} m^2 (harus > 0). "
            "Periksa apakah titik-titiknya segaris atau berulang (PRD Bagian 5.3 rule 13c)."
        )


# ---------------------------------------------------------------------------
# Validasi config (skema & rentang fisik)
# ---------------------------------------------------------------------------


def _require(cfg: dict, block: str, key: str, *, why: str) -> Any:
    if block not in cfg:
        raise InputError(f"Blok {block!r} tidak ada di file config. {why}")
    if cfg[block].get(key) is None:
        raise InputError(f"`{block}.{key}` tidak diisi di file config. {why}")
    return cfg[block][key]


def _require_positive(value: float, name: str) -> None:
    if not math.isfinite(value) or value <= 0.0:
        raise InputError(f"`{name}` harus > 0, diterima {value} (PRD Bagian 5.3 rule 5).")


def validate_config_geometry_params(cfg: dict, sources_present: dict[str, bool]) -> None:
    """Rule 5, 13e, 13f -- parameter JSON yang dibutuhkan lengkap & masuk akal.

    `sources_present` memberi tahu entitas mana yang geometrinya datang dari CSV, sehingga
    parameter JSON yang di-override tidak perlu lengkap (PRD Bagian 5.3 rule 13f).
    Nilai `cfg` sudah dalam SI.
    """
    thickness = _require(cfg, "pilecap", "thickness", why="Tebal pilecap selalu dibutuhkan.")
    _require_positive(float(thickness), "pilecap.thickness")

    # Divalidasi DI LUAR cabang `sources_present["pier"]`: pier dari CSV pun boleh memakai
    # opsi ini. Nirdimensi -- sengaja TIDAK didaftarkan di `io_utils._LENGTH_SCALARS`;
    # fraksi yang diam-diam dikali 1e-3 akan katastrofik dan tak terlihat.
    batas = (cfg.get("pier") or {}).get("max_pile_overlap_fraction")
    if batas is not None:
        nilai = float(batas)
        if not 0.0 < nilai < 1.0:
            raise InputError(
                f"`pier.max_pile_overlap_fraction` = {nilai} harus di antara 0 dan 1 "
                "(fraksi luas pile yang boleh berada di dalam footprint pier).\n"
                "  Nilai 1,0 berarti pile boleh lenyap seluruhnya ke dalam pier, yang "
                "membuat model pelat lentur ini tidak bermakna untuk pile tersebut."
            )

    if not sources_present["pilecap"]:
        for key in ("length_x", "length_y"):
            value = _require(
                cfg,
                "pilecap",
                key,
                why=(
                    "Tidak ada pilecap_polygon.csv, sehingga bentuk pilecap harus diambil dari "
                    "parameter JSON (PRD Bagian 5.3 rule 13f)."
                ),
            )
            _require_positive(float(value), f"pilecap.{key}")
        if cfg["pilecap"].get("origin") is None:
            raise InputError(
                "`pilecap.origin` tidak diisi padahal tidak ada pilecap_polygon.csv "
                "(PRD Bagian 5.3 rule 13f)."
            )

    diameter = _require(
        cfg,
        "pile",
        "diameter",
        why="Diameter pile selalu dibutuhkan (default bila CSV tanpa kolom).",
    )
    _require_positive(float(diameter), "pile.diameter")

    if not sources_present["pile"]:
        for key in ("n_col", "n_row", "spacing_x", "spacing_y"):
            value = _require(
                cfg,
                "pile",
                key,
                why=(
                    "Tidak ada CSV koordinat pile, sehingga grid harus lengkap di JSON "
                    "(PRD Bagian 5.3 rule 13f)."
                ),
            )
            _require_positive(float(value), f"pile.{key}")
        if cfg["pile"].get("grid_origin") is None:
            raise InputError(
                "`pile.grid_origin` tidak diisi padahal tidak ada CSV koordinat pile "
                "(PRD Bagian 5.3 rule 13f)."
            )

    if not sources_present["pier"]:
        shape = cfg.get("pier", {}).get("shape")
        if shape not in ("rectangular", "circular"):
            raise InputError(
                f"`pier.shape` = {shape!r} tidak sah dan tidak ada pier_polygon.csv. "
                "Nilai yang diterima: 'rectangular' atau 'circular' "
                "(PRD Bagian 5.3 rule 13e)."
            )
        if shape == "rectangular":
            for key in ("width_x", "width_y"):
                _require_positive(
                    float(_require(cfg, "pier", key, why="Dibutuhkan untuk pier rectangular.")),
                    f"pier.{key}",
                )
        else:
            _require_positive(
                float(_require(cfg, "pier", "diameter", why="Dibutuhkan untuk pier circular.")),
                "pier.diameter",
            )
        if cfg["pier"].get("centerline") is None:
            raise InputError(
                "`pier.centerline` tidak diisi padahal pier berasal dari parameter JSON."
            )
        support = cfg["pier"].get("support", "fixed")
        if support != "fixed":
            raise InputError(
                f"`pier.support` = {support!r} belum didukung di v1.0. "
                "Hanya 'fixed' (jepit 6 DOF) yang tersedia (PRD Bagian 5.1(a))."
            )


def validate_config_mesh(cfg: dict) -> None:
    """Rule 7b, 7c, 7d -- parameter mesh yang saling bertentangan atau belum didukung."""
    mesh = cfg.get("mesh")
    if mesh is None:
        raise InputError("Blok `mesh` tidak ada di file config.")

    size_mode = mesh.get("size_mode", "uniform")
    if size_mode not in ("uniform", "graded"):
        raise InputError(
            f"`mesh.size_mode` = {size_mode!r} tidak sah. Pilih 'uniform' atau 'graded'."
        )

    size_global = mesh.get("size_global")
    if size_global is None:
        raise InputError("`mesh.size_global` wajib diisi (ukuran elemen target).")
    _require_positive(float(size_global), "mesh.size_global")

    # Rule 7b: MeshSizeMin = MeshSizeMax pada mode uniform MEMBATALKAN seluruh size field,
    # sehingga size_local_* akan diabaikan diam-diam. Itu pelanggaran Core 3.
    if size_mode == "uniform":
        local = {
            k: mesh.get(k)
            for k in ("size_local_pile", "size_local_pier")
            if mesh.get(k) is not None
        }
        if local:
            raise InputError(
                f"`mesh.size_mode` = 'uniform' tetapi {list(local)} diisi.\n"
                "  Pada mode uniform, MeshSizeMin = MeshSizeMax membatalkan seluruh mesh size "
                "field, sehingga refinement lokal TIDAK akan berpengaruh sama sekali.\n"
                "  Pilih `size_mode` = 'graded', atau kosongkan `size_local_*` "
                "(PRD Bagian 5.1(f))."
            )
    else:
        local_values = [
            mesh.get(k) for k in ("size_local_pile", "size_local_pier") if mesh.get(k) is not None
        ]
        if not local_values:
            raise InputError(
                "`mesh.size_mode` = 'graded' tetapi tidak ada `size_local_pile`/`size_local_pier` "
                "yang diisi. Mode graded tanpa refinement lokal tidak ada bedanya dengan uniform."
            )
        for name in ("size_local_pile", "size_local_pier"):
            value = mesh.get(name)
            if value is not None:
                _require_positive(float(value), f"mesh.{name}")
                if float(value) > float(size_global):
                    raise InputError(
                        f"`mesh.{name}` = {value} m lebih besar dari `mesh.size_global` = "
                        f"{size_global} m. Refinement lokal harus LEBIH HALUS dari ukuran global."
                    )

    # Rule 7c
    order = int(mesh.get("element_order", 1))
    if order not in config.SUPPORTED_ELEMENT_ORDERS:
        raise InputError(
            f"`mesh.element_order` = {order} belum didukung di v1.0 "
            f"(hanya {sorted(config.SUPPORTED_ELEMENT_ORDERS)}).\n"
            "  Quad 9-node memerlukan ShellMITC9 dan penanganan konektivitas berbeda "
            "(PRD Bagian 5.1(f))."
        )

    # Rule 7d
    algorithm = int(mesh.get("algorithm", config.GMSH_ALGORITHM_DEFAULT))
    if algorithm not in config.GMSH_VALID_ALGORITHMS:
        raise InputError(
            f"`mesh.algorithm` = {algorithm} bukan nilai Mesh.Algorithm gmsh yang sah. "
            f"Nilai sah: {sorted(config.GMSH_VALID_ALGORITHMS)} "
            f"(11 = Quasi-structured Quad, direkomendasikan)."
        )
    recomb = int(mesh.get("recombination_algorithm", config.GMSH_RECOMB_ALGORITHM_DEFAULT))
    if recomb not in config.GMSH_VALID_RECOMB_ALGORITHMS:
        raise InputError(
            f"`mesh.recombination_algorithm` = {recomb} bukan nilai "
            f"Mesh.RecombinationAlgorithm gmsh yang sah. "
            f"Nilai sah: {sorted(config.GMSH_VALID_RECOMB_ALGORITHMS)} "
            f"(3 = Blossom full-quad, direkomendasikan)."
        )


def validate_material(cfg: dict) -> None:
    """Rule 5 & 6 untuk material, plus kebijakan `E` (PRD Bagian 7.4).

    TIDAK dipanggil oleh `pilecap-mesh` -- meshing tidak membutuhkan properti material.
    WAJIB dipanggil oleh `pilecap-analyze` dan `pilecap-run` sebelum model FEM dibangun.
    """
    material = cfg.get("material")
    if material is None:
        raise InputError("Blok `material` tidak ada di file config.")

    fc = material.get("fc")
    if fc is None:
        raise InputError("`material.fc` wajib diisi.")
    _require_positive(float(fc), "material.fc")

    # Keputusan user (PRD Bagian 17 item 4): tool TIDAK PERNAH menghitung E dari f'c.
    # Rumus E beton dari f'c belum dikonfirmasi pasalnya, dan pada tingkat liabilitas
    # PRD Bagian 1.3 angka tanpa sumber dilarang.
    if material.get("E") is None:
        raise InputError(
            "`material.E` bernilai null.\n"
            "  Tool ini TIDAK menghitung modulus elastisitas beton dari f'c: rumus dan "
            "pasalnya belum dikonfirmasi, dan angka tanpa sumber dilarang "
            "(PRD Bagian 1.3 poin 2 & Bagian 7.4).\n"
            "  Isi `material.E` secara eksplisit beserta `material.E_source` "
            '(mis. "SNI 2847:2019 Ps. X.Y.Z" atau "hasil uji lab tanggal ...").'
        )
    _require_positive(float(material["E"]), "material.E")

    e_source = material.get("E_source")
    if not isinstance(e_source, str) or not e_source.strip():
        raise InputError(
            "`material.E_source` wajib diisi bila `material.E` diisi.\n"
            "  Nilainya dicetak apa adanya di calc_sheet.md dan run_manifest.json agar "
            "checker dapat menelusuri asal angka E (PRD Bagian 9.4 bagian 1)."
        )

    poisson = material.get("poisson")
    if poisson is None:
        raise InputError("`material.poisson` wajib diisi.")
    if not (config.POISSON_MIN <= float(poisson) < config.POISSON_MAX):
        raise InputError(
            f"`material.poisson` = {poisson} di luar rentang "
            f"{config.POISSON_MIN} <= v < {config.POISSON_MAX} (PRD Bagian 5.3 rule 6)."
        )

    density = material.get("density")
    if density is not None and float(density) < 0.0:
        raise InputError(f"`material.density` tidak boleh negatif, diterima {density}.")


def validate_design(cfg: dict) -> None:
    """Masukan yang dibutuhkan cek kapasitas `shell-kit` (PRD Bagian 7.2(6)-(7)).

    TIDAK dipanggil oleh `pilecap-mesh` maupun `pilecap-analyze`: keduanya hanya
    menghasilkan demand. WAJIB dipanggil oleh `pilecap-report` dan `pilecap-run`, karena
    di sanalah `As perlu` dicetak.

    `fy` diperlakukan persis seperti `material.E`: kosong berarti RAISE. `shell-kit`
    menyediakan ``DEFAULT_FY = 420`` dan memakainya diam-diam akan membuat SELURUH luas
    tulangan yang dilaporkan bersandar pada angka yang tidak pernah ditetapkan siapa pun
    (PRD Bagian 1.3 poin 2).
    """
    design = cfg.get("design")
    if design is None:
        raise InputError("Blok `design` tidak ada di file config.")

    if design.get("fy") is None:
        raise InputError(
            "`design.fy` (mutu leleh baja tulangan) bernilai null, sehingga cek kapasitas "
            "tidak dapat dijalankan.\n"
            "  Tool ini TIDAK memakai nilai default: mutu baja menentukan seluruh luas "
            "tulangan yang dilaporkan (PRD Bagian 1.3 poin 2).\n"
            "  Isi `design.fy` [MPa] beserta `design.fy_source` "
            '(mis. "SNI 2847:2019 Tabel 20.2.2.4(a) BjTS 420B" atau "sertifikat pabrik ...").'
        )
    _require_positive(float(design["fy"]), "design.fy")

    fy_source = design.get("fy_source")
    if not isinstance(fy_source, str) or not fy_source.strip():
        raise InputError(
            "`design.fy_source` wajib diisi bila `design.fy` diisi.\n"
            "  Nilainya dicetak apa adanya di calc_sheet.md dan run_manifest.json agar "
            "checker dapat menelusuri asal angka fy (PRD Bagian 9.4 bagian 1)."
        )

    _validate_rebar_mode(design)
    _validate_stirrups(design)

    surface_zone = design.get("as_min_surface_zone")
    if surface_zone is not None:
        _require_positive(float(surface_zone), "design.as_min_surface_zone")

    if design.get("cover") is None:
        raise InputError("`design.cover` bernilai null; tinggi efektif d tidak dapat dihitung.")
    _require_positive(float(design["cover"]), "design.cover")

    thickness = (cfg.get("pilecap") or {}).get("thickness")
    if thickness is not None and float(design["cover"]) >= 0.5 * float(thickness):
        raise InputError(
            f"`design.cover` = {design['cover']} m tidak masuk akal terhadap "
            f"`pilecap.thickness` = {thickness} m: selimut satu muka mencapai setengah "
            "tebal pelat, sehingga tidak tersisa tinggi efektif."
        )

    # phi boleh null -- artinya "pakai konstanta shell-kit", dan asalnya dicetak di calc
    # sheet. Yang tidak boleh adalah angka di luar rentang yang bermakna.
    for key in ("phi_flexure", "phi_shear"):
        value = design.get(key)
        if value is None:
            continue
        if not (0.0 < float(value) <= 1.0):
            raise InputError(
                f"`design.{key}` = {value} di luar rentang 0 < phi <= 1. "
                "Kosongkan (null) bila ingin memakai nilai SNI bawaan shell-kit."
            )


#: Mode pemilihan batang tulangan lentur. Menentukan MANA yang jadi masukan dan mana yang
#: dihitung -- keduanya sah, tetapi tidak boleh ambigu.
REBAR_MODES: tuple[str, str] = ("spacing_fixed", "diameter_fixed")


def _known_config_codes() -> list[str]:
    """Kode konfigurasi yang dikenal `shell-kit`, diambil dari sumbernya."""
    from shell_kit import rebar as sk_rebar

    codes: list[str] = list(sk_rebar.get_available_config_codes())
    return codes


def _validate_rebar_mode(design: dict) -> None:
    """Cabang `rebar_mode`: yang tetap adalah masukan, yang lain dihitung.

    Kode konfigurasi divalidasi DI SINI terhadap tabel shell-kit. Tanpa itu kode yang
    salah ketik baru meledak jauh di hilir sebagai `KeyError` mentah dari dalam
    `shell_kit.rebar` -- pesan yang tidak memberi tahu user apa pun tentang config-nya.
    """
    mode = design.get("rebar_mode")
    if mode is None:
        raise InputError(
            "`design.rebar_mode` belum diisi.\n"
            "  Tentukan mana yang Anda tetapkan dan mana yang dihitung tool:\n"
            '    "spacing_fixed"  -> Anda isi `rebar_spacing`, tool memilih DIAMETER\n'
            '    "diameter_fixed" -> Anda isi `rebar_config`, tool menghitung SPASI'
        )
    if mode not in REBAR_MODES:
        raise InputError(f"`design.rebar_mode` = {mode!r} tidak dikenal. Pilihan: {REBAR_MODES}.")

    if mode == "spacing_fixed":
        if design.get("rebar_spacing") is None:
            raise InputError(
                '`design.rebar_spacing` wajib diisi pada mode "spacing_fixed".\n'
                "  Nilai ini menentukan diameter batang yang dipilih dan karenanya tinggi "
                "efektif d, jadi ia mengubah `As perlu` -- tidak boleh ditebak.\n"
                "  Isi `design.rebar_spacing` [mm], mis. 150."
            )
        _require_positive(float(design["rebar_spacing"]), "design.rebar_spacing")
    else:
        code = design.get("rebar_config")
        if code is None:
            raise InputError(
                '`design.rebar_config` wajib diisi pada mode "diameter_fixed".\n'
                '  Isi kode konfigurasi batang, mis. "25" (D25 tunggal) atau "2D25".\n'
                f"  Kode tersedia: {', '.join(_known_config_codes())}"
            )
        known = _known_config_codes()
        if str(code).upper().strip() not in known:
            raise InputError(
                f"`design.rebar_config` = {code!r} bukan kode yang dikenal.\n"
                f"  Kode tersedia: {', '.join(known)}"
            )

    # Opsional pada kedua mode: mempersempit pilihan ke daftar konfigurasi tertentu,
    # yang sekaligus mengubah plot menjadi kategorikal berlabel kode.
    codes = design.get("rebar_select_codes")
    if codes is not None:
        if not isinstance(codes, list) or not codes:
            raise InputError(
                "`design.rebar_select_codes` harus berupa daftar kode yang tidak kosong, "
                'mis. ["16", "22", "2D25"]. Kosongkan (null) bila tidak dipakai.'
            )
        known = _known_config_codes()
        unknown = [c for c in codes if str(c).upper().strip() not in known]
        if unknown:
            raise InputError(
                f"`design.rebar_select_codes` memuat kode yang tidak dikenal: {unknown}.\n"
                f"  Kode tersedia: {', '.join(known)}"
            )


def _validate_stirrups(design: dict) -> None:
    """Spasi sengkang WAJIB -- keduanya menentukan diameter sengkang terpilih.

    Diperlakukan seperti `design.fy`: tanpa keduanya, `calc_shear_diameter` tidak punya
    luas per kaki untuk dihitung, dan menebak grid sengkang berarti melaporkan diameter
    yang tidak pernah ditetapkan siapa pun.
    """
    for key, contoh in (("stirrup_spacing_long", 200), ("stirrup_spacing_trans", 200)):
        if design.get(key) is None:
            raise InputError(
                f"`design.{key}` belum diisi.\n"
                "  Diameter sengkang dihitung dari luas per kaki "
                "`Av/s x s_long x s_trans`, sehingga KEDUA spasi menentukan hasilnya.\n"
                f"  Isi `design.{key}` [mm], mis. {contoh}."
            )
        _require_positive(float(design[key]), f"design.{key}")

    diameters = design.get("stirrup_select_diameters")
    if diameters is not None:
        if not isinstance(diameters, list) or not diameters:
            raise InputError(
                "`design.stirrup_select_diameters` harus berupa daftar diameter [mm] yang "
                "tidak kosong, mis. [10, 13, 16]. Kosongkan (null) untuk memakai daftar "
                "bawaan shell-kit."
            )
        for value in diameters:
            _require_positive(float(value), "design.stirrup_select_diameters")


# ---------------------------------------------------------------------------
# Validasi konsistensi geometri (rule 8-14)
# ---------------------------------------------------------------------------


def validate_geometry(
    geom: GeometryModel, *, max_overlap_fraction: float | None = None
) -> list[str]:
    """Rule 8, 9, 10, 11, 12, 14 -- konsistensi geometri antar entitas.

    Multi-pier: rule 11 & 14 di-loop untuk setiap pier, ditambah cek pier-vs-pier yang
    tidak ada di PRD (PRD menulis Bagian 5.3 saat asumsinya masih satu pier) tetapi
    diperlukan agar dua pier tidak berbagi node jepit yang sama secara ambigu.

    `max_overlap_fraction` = `pier.max_pile_overlap_fraction` dari config. Bila `None`
    (bawaan), rule 14 berperilaku PERSIS seperti sebelum v0.9.0: tumpang tindih pile-pier
    ditolak. Mengembalikan daftar peringatan, seperti `validate_reactions`.
    """
    cap_poly = geom.pilecap.to_shapely()

    # Rule 12 -- polygon pilecap self-intersecting / titik unik < 3
    if not cap_poly.is_valid:
        raise GeometryError(
            f"Polygon pilecap tidak valid: {explain_validity(cap_poly)}"
            f"\n  Titik: {geom.pilecap.vertices.tolist()}"
            "\n  (PRD Bagian 5.3 rule 12)"
        )
    if geom.pilecap.area <= 0.0:
        raise GeometryError(f"Luas pilecap = {geom.pilecap.area} m^2, harus > 0.")

    if geom.n_piles == 0:
        raise GeometryError("Tidak ada pile yang terdefinisi.")
    if geom.n_piers == 0:
        raise GeometryError("Tidak ada pier yang terdefinisi.")

    # Rule 8 & 9 -- pusat pile di dalam pilecap, dan lingkaran pile tidak memotong tepi
    for pile in geom.piles:
        center = Point(pile.x, pile.y)
        if not cap_poly.contains(center):
            raise GeometryError(
                f"Pusat pile {pile.pile_id} di ({pile.x:.4f}, {pile.y:.4f}) m berada DI LUAR "
                f"polygon pilecap (PRD Bagian 5.3 rule 8)."
            )
        edge_distance = cap_poly.exterior.distance(center)
        if edge_distance < pile.radius:
            raise GeometryError(
                f"Pile {pile.pile_id} memotong tepi pilecap: jarak pusat ke tepi = "
                f"{edge_distance:.4f} m < radius {pile.radius:.4f} m.\n"
                "  Geometri menjadi ambigu setelah occ.fragment (potongan disk di luar cap "
                "akan hilang, sehingga luas area beban tidak sesuai). "
                "(PRD Bagian 5.3 rule 9)"
            )

    # Rule 10 -- dua lingkaran pile saling tumpang tindih
    for a, b in itertools.combinations(geom.piles, 2):
        distance = math.hypot(a.x - b.x, a.y - b.y)
        if distance < a.radius + b.radius:
            raise GeometryError(
                f"Pile {a.pile_id} dan {b.pile_id} saling tumpang tindih: jarak pusat "
                f"{distance:.4f} m < r1 + r2 = {a.radius + b.radius:.4f} m "
                "(PRD Bagian 5.3 rule 10)."
            )

    pier_polys = {}
    for pier in geom.piers:
        poly = pier.to_shapely()
        if not poly.is_valid:
            raise GeometryError(
                f"Polygon pier {pier.pier_id} tidak valid: {explain_validity(poly)} "
                "(PRD Bagian 5.3 rule 12)."
            )
        if poly.area <= 0.0:
            raise GeometryError(f"Luas pier {pier.pier_id} = {poly.area} m^2, harus > 0.")
        pier_polys[pier.pier_id] = poly

        # Rule 11 -- area pier seluruhnya di dalam pilecap
        if not cap_poly.covers(poly):
            outside = poly.difference(cap_poly).area
            raise GeometryError(
                f"Area pier {pier.pier_id} tidak seluruhnya berada di dalam polygon pilecap: "
                f"{outside:.6f} m^2 ({outside / poly.area:.1%}) berada di luar "
                "(PRD Bagian 5.3 rule 11)."
            )

        # Rule 14 -- pier tumpang tindih dengan pile
        for pile in geom.piles:
            pile_poly = pile.to_shapely()
            irisan = poly.intersection(pile_poly)
            overlap = irisan.area

            if overlap <= 0.0 and poly.intersects(pile_poly):
                # BERSINGGUNGAN: ditolak SELALU, dengan atau tanpa opt-in.
                #
                # Bukan kehati-hatian berlebih. Pada persinggungan tidak ada lensa sama
                # sekali, sehingga tidak ada komponen geometri yang dapat dihitung dan
                # dilaporkan -- 100% dari beban yang terserap ke node jepit adalah artefak
                # diskretisasi murni, dan besarnya bergantung pada node mana yang kebetulan
                # dipakai mesher. Kondisi ini sebelum v0.9.0 LOLOS rule 14 (`area > 0.0`
                # saja) dan menghasilkan penyerapan senyap yang VC-0 pun tidak menangkapnya.
                raise GeometryError(
                    f"Pile {pile.pile_id} BERSINGGUNGAN dengan pier {pier.pier_id} "
                    "(luas irisan nol, tetapi keduanya bersentuhan).\n"
                    "  Node di titik sentuh menjadi milik grup pile SEKALIGUS pier: ia "
                    "dijepit, tetapi tetap menerima beban pile. Gaya pada DOF terjepit "
                    "menghasilkan perpindahan NOL, jadi beban itu tidak melenturkan pelat "
                    "sama sekali -- dan VC-0 tetap LULUS karena kedua sisi neracanya "
                    "memuat gaya yang sama.\n"
                    "  Berbeda dari tumpang tindih yang berluas, di sini tidak ada bagian "
                    "geometri yang dapat dihitung: seluruhnya artefak kehalusan mesh.\n"
                    "  Geser pile sedikit -- keluar sehingga ada celah yang jelas, atau "
                    "masuk sehingga tumpang tindihnya terukur (lihat "
                    "`pier.max_pile_overlap_fraction`)."
                )

            if overlap <= 0.0:
                continue

            fraction = overlap / pile.nominal_area
            if max_overlap_fraction is None:
                raise GeometryError(
                    f"Area pier {pier.pier_id} tumpang tindih dengan pile {pile.pile_id} "
                    f"seluas {overlap:.6f} m^2 ({fraction:.1%} dari luas pile).\n"
                    "  Node tidak bisa sekaligus dijepit (pier) dan dibebani (pile) "
                    "(PRD Bagian 5.3 rule 14).\n"
                    "  Bila ini memang dimaksudkan, isi `pier.max_pile_overlap_fraction` "
                    "di config -- itu keputusan pemodelan Anda, dan konsekuensinya "
                    "dijelaskan di KNOWN_LIMITATIONS #10."
                )
            if fraction > max_overlap_fraction:
                raise GeometryError(
                    f"Tumpang tindih pile {pile.pile_id} dengan pier {pier.pier_id} = "
                    f"{fraction:.1%} dari luas pile, MELEBIHI batas "
                    f"`pier.max_pile_overlap_fraction` = {max_overlap_fraction:.1%} "
                    "yang Anda tetapkan.\n"
                    "  Naikkan batasnya bila memang disengaja, atau geser pile."
                )

    # Tambahan multi-pier: dua pier tidak boleh tumpang tindih.
    for (id_a, poly_a), (id_b, poly_b) in itertools.combinations(pier_polys.items(), 2):
        overlap = poly_a.intersection(poly_b).area
        if overlap > 0.0:
            raise GeometryError(
                f"Pier {id_a} dan {id_b} saling tumpang tindih seluas {overlap:.6f} m^2.\n"
                "  Setiap pier harus menempati area terpisah agar physical group-nya "
                "tidak ambigu."
            )

    # Nama group lensa DIBENTUK, tidak pernah diurai; id yang memuat pemisahnya membuat
    # `LENS_<pile>__<pier>` ambigu dan dua pasangan berbeda bisa bertabrak nama.
    if geom.overlaps:
        for entitas, ident in [("pile", p.pile_id) for p in geom.piles] + [
            ("pier", p.pier_id) for p in geom.piers
        ]:
            if config.GROUP_LENS_SEP in ident:
                raise GeometryError(
                    f"{entitas}_id {ident!r} memuat {config.GROUP_LENS_SEP!r}, yang dipakai "
                    "sebagai pemisah nama physical group lensa "
                    f"(`{config.GROUP_LENS_PREFIX}<pile>{config.GROUP_LENS_SEP}<pier>`).\n"
                    "  Ganti id-nya agar nama group tetap tak ambigu."
                )

    return list(geometry_builder.overlap_warning_lines(geom, max_overlap_fraction or 0.0))


# ---------------------------------------------------------------------------
# Validasi reaksi pile (rule 3, 15)
# ---------------------------------------------------------------------------


def validate_reactions(reactions: Any, geom: GeometryModel) -> list[str]:
    """Rule 3 & 15 -- kecocokan `pile_id` dan tanda total reaksi.

    Rule 2 (duplikat dalam satu combo) sudah ditegakkan saat parsing di
    `io_utils.load_reactions`, karena di sanalah baris CSV masih terlihat satu per satu.

    Mengembalikan daftar WARNING (gaya lateral yang diabaikan).
    """
    if not reactions.combos:
        raise InputError(f"Tidak ada satu pun kombinasi di {reactions.path}.")

    geometry_ids = {p.pile_id for p in geom.piles}

    for combo in reactions.combos:
        combo_ids = set(reactions.values[combo])

        # Rule 3 -- selisih DUA ARAH harus dilaporkan, bukan hanya salah satunya.
        missing_in_csv = sorted(geometry_ids - combo_ids)
        missing_in_geometry = sorted(combo_ids - geometry_ids)
        if missing_in_csv or missing_in_geometry:
            raise InputError(
                f"Daftar `pile_id` tidak cocok untuk combo {combo!r}:\n"
                f"  Ada di geometri tetapi TIDAK di {reactions.path.name}: "
                f"{missing_in_csv or '-'}\n"
                f"  Ada di {reactions.path.name} tetapi TIDAK di geometri: "
                f"{missing_in_geometry or '-'}\n"
                f"  Pile dari geometri: {sorted(geometry_ids)}\n"
                "  (PRD Bagian 5.3 rule 3)"
            )

        # Rule 15 -- total reaksi harus positif (pile menekan pilecap ke atas).
        total = reactions.total_pz(combo)
        if total <= 0.0:
            raise InputError(
                f"Total Sigma Pz untuk combo {combo!r} = {total / 1e3:,.3f} kN <= 0.\n"
                "  Pz positif berarti pile menekan pilecap ke ATAS; total tidak positif "
                "berarti pilecap tidak dipikul sama sekali (PRD Bagian 5.3 rule 15)."
            )

    warnings: list[str] = []
    if reactions.lateral_nonzero:
        warnings.append(
            f"Kolom {list(reactions.lateral_nonzero)} berisi nilai tak-nol tetapi "
            "DIABAIKAN di v1.0: pile hanya memberi gaya vertikal "
            "(PRD Bagian 8.3 keterbatasan #4)."
        )
    for message in warnings:
        _log.warning("%s", message)
    return warnings


# ---------------------------------------------------------------------------
# Validasi parameter mesh terhadap geometri (rule 7, 7a)
# ---------------------------------------------------------------------------


def validate_mesh_vs_geometry(cfg: dict, geom: GeometryModel) -> None:
    """Rule 7 & 7a -- ukuran mesh terhadap dimensi pilecap dan diameter pile.

    `cfg` sudah dalam SI, sehingga `mesh.size_global` dalam meter.

    Catatan rule 7a: PRD Bagian 5.3 menuliskan `D_pile / size_global`, rumusan yang ditulis
    dengan asumsi mode `uniform`. Pada mode `graded`, area pile justru di-mesh dengan
    `size_local_pile`, sehingga membandingkan terhadap `size_global` akan menolak
    konfigurasi yang justru sudah memenuhi maksud aturannya (area pile terdiskretisasi
    memadai). Karena itu pembanding yang dipakai adalah **ukuran elemen yang benar-benar
    berlaku di area pile**.
    """
    mesh_cfg = cfg["mesh"]
    h = float(mesh_cfg["size_global"])

    h_at_pile = h
    size_source = "mesh.size_global"
    if mesh_cfg.get("size_mode") == "graded" and mesh_cfg.get("size_local_pile") is not None:
        h_at_pile = float(mesh_cfg["size_local_pile"])
        size_source = "mesh.size_local_pile"

    # Rule 7 -- mesh terlalu kasar untuk hasil bermakna
    xmin, ymin, xmax, ymax = geom.pilecap.bounds
    min_dimension = min(xmax - xmin, ymax - ymin)
    max_allowed = min_dimension * config.MESH_SIZE_MAX_FRACTION
    if h > max_allowed:
        raise InputError(
            f"`mesh.size_global` = {h:.4f} m terlalu kasar: melebihi "
            f"{config.MESH_SIZE_MAX_FRACTION:g} x dimensi terkecil pilecap "
            f"({min_dimension:.4f} m) = {max_allowed:.4f} m.\n"
            "  Mesh sekasar itu tidak menghasilkan distribusi momen yang bermakna "
            "(PRD Bagian 5.3 rule 7)."
        )

    # Rule 7a -- area pile harus terdiskretisasi memadai
    d_min = geom.min_pile_diameter
    ratio = d_min / h_at_pile
    if ratio < config.MIN_ELEM_PER_PILE_DIAMETER:
        recommended = d_min / config.MIN_ELEM_PER_PILE_DIAMETER
        raise InputError(
            f"Area pile tidak terdiskretisasi memadai: "
            f"D_pile/h = {d_min:.4f}/{h_at_pile:.4f} = {ratio:.2f} < "
            f"{config.MIN_ELEM_PER_PILE_DIAMETER:g}.\n"
            f"  Lingkaran pile berisiko hanya terwakili ~{max(1, round(ratio)):d} elemen, "
            "sehingga distribusi tekanan menjadi tidak berarti.\n"
            f"  Turunkan `{size_source}` ke <= {recommended * 1e3:.0f} mm "
            f"({recommended:.4f} m). (PRD Bagian 5.3 rule 7a)"
        )
    _log.debug(
        "Rule 7a lolos: D_pile/h = %.2f >= %g (h diambil dari %s)",
        ratio,
        config.MIN_ELEM_PER_PILE_DIAMETER,
        size_source,
    )


# ---------------------------------------------------------------------------
# Validasi hasil mesh
# ---------------------------------------------------------------------------


def validate_mesh_result(
    *,
    n_quad: int,
    n_tri: int,
    tri_centroids: np.ndarray | None,
    require_all_quad: bool,
    group_element_counts: dict[str, int],
    total_group_area: float,
    pilecap_area: float,
    n_ungrouped: int,
) -> list[str]:
    """Verifikasi hasil mesh sebelum diserahkan ke model FEM.

    Mengembalikan daftar WARNING (bukan raise) yang perlu ditampilkan di laporan.
    """
    warnings: list[str] = []

    if n_quad + n_tri == 0:
        raise MeshError(
            "Mesh tidak menghasilkan satu pun elemen. Periksa geometri dan `mesh.size_global`."
        )

    # Cek all-quad didahulukan: bila seluruh elemen segitiga, pesan "tidak ada quad" jauh
    # kurang informatif daripada pesan rekombinasi gagal yang menyebut jumlah & centroid.
    if n_tri > 0:
        if require_all_quad:
            centroid_text = ""
            if tri_centroids is not None and len(tri_centroids) > 0:
                shown = tri_centroids[:20]
                lines = "\n".join(
                    f"    ({c[0]:.4f}, {c[1]:.4f}) m" for c in np.asarray(shown, dtype=float)
                )
                more = (
                    ""
                    if len(tri_centroids) <= 20
                    else f"\n    ... dan {len(tri_centroids) - 20} lagi"
                )
                centroid_text = f"\n  Centroid segitiga:\n{lines}{more}"
            raise MeshError(
                f"Rekombinasi tidak menghasilkan mesh all-quad: {n_tri} elemen segitiga "
                f"tersisa dari total {n_quad + n_tri} elemen.{centroid_text}\n"
                "  ShellMITC4 tidak menerima elemen 3-node; segitiga yang lolos akan "
                "menyebabkan lubang pada model FEM.\n"
                "  Saran: ubah `mesh.size_global`, atau periksa sliver hasil occ.fragment "
                "(pile terlalu dekat tepi/pier). (PRD Bagian 5.1(f))"
            )
        warnings.append(
            f"MESH TIDAK ALL-QUAD: {n_tri} elemen segitiga dibiarkan lolos karena --allow-tri. "
            "Model FEM AKAN MENOLAK mesh ini. Gunakan hanya untuk diagnosa."
        )

    if n_quad == 0:
        # Hanya mungkin sampai di sini lewat --allow-tri. Cek berikutnya semuanya
        # mengasumsikan mesh quad, jadi dihentikan di sini dengan peringatan eksplisit.
        warnings.append(
            "Tidak ada satu pun elemen quad -- seluruh cek physical group dan cek luas "
            "DILEWATI. Hasil ini hanya berguna untuk diagnosa, bukan untuk model FEM."
        )
        return warnings

    # Physical group pile/pier/lensa tanpa elemen = beban/tumpuan hilang secara diam-diam.
    #
    # LENSA ikut diperiksa: lensa yang lebih kecil daripada satu elemen akan lenyap dari
    # `elements.csv`, lalu meledak jauh di hilir sebagai `KeyError` saat laporan dibuat --
    # bukan sebagai pesan yang menjelaskan bahwa mesh-nya terlalu kasar.
    empty = sorted(
        name
        for name, count in group_element_counts.items()
        if count == 0
        and name.startswith(
            (config.GROUP_PILE_PREFIX, config.GROUP_PIER_PREFIX, config.GROUP_LENS_PREFIX)
        )
    )
    if empty:
        raise MeshError(
            f"Physical group berikut tidak punya satu pun elemen: {empty}.\n"
            "  Ini bug diam-diam paling berbahaya: beban pile atau tumpuan pier akan HILANG "
            "dari model tanpa pesan error.\n"
            "  Saran: perkecil `mesh.size_global` atau aktifkan refinement lokal "
            "(`size_mode` = 'graded')."
        )

    if n_ungrouped > 0:
        raise MeshError(
            f"{n_ungrouped} elemen tidak masuk physical group mana pun. "
            "Setiap elemen harus terklasifikasi sebagai CAP, PILE_*, PIER_*, atau LENS_*."
        )

    if not math.isclose(total_group_area, pilecap_area, rel_tol=config.AREA_RTOL):
        raise MeshError(
            f"Jumlah luas seluruh physical group = {total_group_area:.9f} m^2 tidak sama dengan "
            f"luas polygon pilecap = {pilecap_area:.9f} m^2 "
            f"(selisih {abs(total_group_area - pilecap_area):.3e} m^2, "
            f"rtol = {config.AREA_RTOL:g}).\n"
            "  Indikasi geometri tidak menyatu setelah occ.fragment."
        )

    n_total = n_quad + n_tri
    if n_total > config.MESH_ELEMENT_WARN_LIMIT:
        warnings.append(
            f"Jumlah elemen {n_total:,} melebihi {config.MESH_ELEMENT_WARN_LIMIT:,}. "
            "Waktu analisis per kombinasi akan lama."
        )

    return warnings
