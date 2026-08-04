# kft_pilecap_fem — `pilecap-fem`

FEM berbasis OpenSees untuk analisis pilecap, sekaligus pilecap mesh generator berbasis
gmsh Python API. Spesifikasi lengkap ada di [`PRD_pilecap_fem.md`](PRD_pilecap_fem.md).

> **Status: Fase 2 selesai.** Yang berfungsi: **input → geometri → mesh all-quad**
> (`pilecap-mesh`) dan **mesh → FEM → momen & geser per elemen** (`pilecap-analyze`),
> dengan cek keseimbangan VC-0 di setiap run. `pilecap-report` dan `pilecap-run` masih
> stub yang memberi tahu statusnya (Fase 3).

> **Tingkat liabilitas: desain nyata yang dibangun di lapangan** (PRD Bagian 1.3).
> Tool ini **alat bantu**, bukan pengganti engineer. Setiap hasil wajib diperiksa dan
> disetujui oleh *engineer of record*. Tidak ada angka tanpa sumber: nilai yang belum
> dikonfirmasi membuat tool **berhenti dengan pesan jelas**, bukan memakai default diam-diam.

---

## Instalasi

Butuh [`uv`](https://docs.astral.sh/uv/) dan Python 3.12.

```bash
uv sync --dev
```

## Pemakaian

```bash
uv run pilecap-mesh --config examples/ex01_standard_4pile/pilecap_config.json --input-dir examples/ex01_standard_4pile --export-msh
```

Dengan folder `input/` berisi file-file yang cocok pola auto-detect, cukup:

```bash
uv run pilecap-mesh
```

Untuk analisis FEM lengkap (butuh `pile_reactions.csv`):

```bash
uv run pilecap-analyze --config examples/ex01_standard_4pile/pilecap_config.json --input-dir examples/ex01_standard_4pile
```

Hasil ditulis ke `output/pilecap_YYYYMMDD_HHMMSS/` — **setiap run folder baru, tidak pernah
menimpa**:

```
output/pilecap_20260804_093148/
├── run_manifest.json      # provenance: sha256 input, versi dependency, resolusi geometri
├── run.log
├── 00_Model/
│   ├── mesh_summary.md    # statistik mesh, opsi gmsh efektif, tabel resolusi geometri
│   ├── mesh_plan.png      # denah mesh + label pile & pier
│   ├── nodes.csv          # tag, x, y, z  [SI]
│   ├── elements.csv       # tag, n1..n4, luas, centroid, theta, group
│   └── model.msh          # opsional (--export-msh), untuk dibuka di GUI gmsh
└── Combo_<nama>/          # satu folder per kombinasi (pilecap-analyze)
    ├── element_resultants.csv   # m11/m22/m12 lokal + m_x/m_y/m_xy/q_x/q_y global
    ├── reactions.csv            # reaksi tiap node jepit + baris TOTAL
    └── equilibrium_check.json   # VC-0 + jejak beban tiap pile
```

### Argumen penting

| Argumen | Berlaku di | Keterangan |
|---------|------------|------------|
| `--config`, `--input-dir`, `--output-dir` | keduanya | Lokasi input & output |
| `--pilecap-polygon` / `--pile-coords` / `--pier-polygon` | keduanya | Tunjuk CSV geometri secara eksplisit |
| `--no-custom` | keduanya | Abaikan seluruh CSV geometri hasil auto-detect; paksa parameter JSON |
| `--size` | keduanya | Override ukuran mesh global, dalam satuan input (default mm) |
| `--size-mode uniform\|graded` | keduanya | `graded` mengaktifkan refinement lokal di pile/pier |
| `--allow-tri` | keduanya | Izinkan segitiga lolos — **diagnostik saja**, model FEM akan menolaknya |
| `--preview` | `mesh` | Tampilkan plot mesh interaktif |
| `--reactions` | `analyze` | CSV reaksi pile (default auto-detect) |
| `--combo NAMA` | `analyze` | Analisis hanya kombinasi tertentu (boleh diulang) |
| `--element ShellMITC4\|ShellDKGQ\|ShellNLDKGQ` | `analyze` | Mode perbandingan elemen (PRD §11) |
| `--self-weight` | `analyze` | Aktifkan berat sendiri pilecap |
| `--equilibrium-rtol` | `analyze` | Toleransi cek keseimbangan VC-0 |
| `--export-msh`, `--dpi`, `--log-level` | keduanya | Output tambahan & verbositas |

### Cek keseimbangan VC-0

`pilecap-analyze` menjalankan cek kesetimbangan gaya & momen pada **setiap** kombinasi,
bukan hanya saat testing (PRD §1.3 poin 3). Kombinasi yang gagal menghentikan run;
`run_manifest.json` ditandai `FAILED` dan **tidak ada output desain yang dihasilkan**.
Pada ketiga contoh residunya berada di kisaran 1e-14 sampai 1e-16.

## Satuan

Internal **SI murni** (N, m, Pa). File input default **mm / kN / MPa**, dapat di-override
lewat blok `units` di config. Konversi terjadi **hanya** di `io_utils.py`; tabel faktornya
**hanya** di `config.py`.

## Contoh

| Folder | Isi |
|--------|-----|
| `examples/ex01_standard_4pile/` | Pilecap persegi 4 pile, pier persegi — kasus paling umum |
| `examples/ex02_standard_12pile/` | Grid 4×3, pier lingkaran |
| `examples/ex03_custom_polygon/` | Pilecap poligon L, pile custom non-grid, **dua** pier poligon. Sekaligus acuan format ketiga CSV geometri. |

Jalankan `ex03` untuk melihat mekanisme **override geometri**: setiap entitas yang datang
dari CSV diteriakkan sebagai WARNING 5 baris, dicatat di `run_manifest.json`, dan diberi
subjudul di `mesh_plan.png`.

## Pengembangan

```bash
uv run pytest -q
```
```bash
uv run ruff check . && uv run ruff format --check . && uv run mypy src/pilecap_fem
```

Test yang menjalankan meshing sungguhan ditandai `slow`; lewati dengan `pytest -m "not slow"`.

**Release gate:** `n_tri == 0` untuk ketiga contoh. Bila test itu gagal, rilis diblokir —
`ShellMITC4` tidak menerima elemen 3-node.

## Yang BELUM dilakukan tool ini

Perhitungan kapasitas (lentur & geser) berstatus `NOT_EVALUATED` sampai pasal standar
dikonfirmasi. Lihat `config.OPEN_BLOCKERS` dan PRD Bagian 17 — item **2, 3, 5, 6, 7, 8, 10, 18**
masih terbuka. `material.E` **wajib** diisi user beserta `material.E_source`; tool tidak
pernah menghitungnya dari `f'c`.
