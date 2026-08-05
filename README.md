# kft_pilecap_fem — `pilecap-fem`

FEM berbasis OpenSees untuk analisis pilecap, sekaligus pilecap mesh generator berbasis
gmsh Python API. Spesifikasi lengkap ada di [`PRD_pilecap_fem.md`](PRD_pilecap_fem.md).

> **Status: Fase 3 selesai — keempat command berfungsi.** Rantai penuh
> **input → geometri → mesh all-quad → FEM → momen & geser → kontur, envelope, dan
> laporan auditable**, dengan cek keseimbangan VC-0 di setiap run.

> **Tingkat liabilitas: desain nyata yang dibangun di lapangan** (PRD Bagian 1.3).
> Tool ini **alat bantu**, bukan pengganti engineer. Setiap hasil wajib diperiksa dan
> disetujui oleh *engineer of record*. Tidak ada angka tanpa sumber: nilai yang belum
> dikonfirmasi membuat tool **berhenti dengan pesan jelas**, bukan memakai default diam-diam.

---

## Instalasi

Satu-satunya prasyarat adalah [`uv`](https://docs.astral.sh/uv/). Tidak perlu meng-clone
repo, dan tidak perlu menyiapkan Python sendiri.

**Jalankan langsung tanpa memasang apa pun:**

```bash
uvx --from git+https://github.com/kikifadilah31/kft_pilecap_fem pilecap-run --help
```

**Pasang sebagai tool permanen, disematkan ke versi tertentu:**

```bash
uv tool install git+https://github.com/kikifadilah31/kft_pilecap_fem@v0.3.0
```

Setelah itu keempat command (`pilecap-mesh`, `pilecap-analyze`, `pilecap-report`,
`pilecap-run`) tersedia langsung di terminal.

Empat hal yang perlu diketahui:

- **`--from` wajib** pada `uvx` karena nama paket (`pilecap-fem`) berbeda dari nama
  command yang dijalankan.
- **Sematkan tag versi** (`@v0.3.0`) untuk pekerjaan yang hasilnya akan diperiksa
  kemudian. `run_manifest.json` merekam `tool_version`; dengan tag, versi itu dapat
  ditarik kembali persis. Tanpa tag, instalasi selalu mengambil `main` terbaru.
- **Python 3.12 disediakan `uv` sendiri.** Batas `<3.13` bukan kehati-hatian berlebihan:
  `openseespy` 3.8.0.0 *terpasang* di Python 3.13 tetapi *gagal diimpor* karena `.pyd`
  di dalamnya dibangun untuk 3.12.
- **Unduhan pertama ~60 MB** (gmsh saja 40 MB), lalu di-cache `uv`.

### Mencoba tanpa menyiapkan data sendiri

```bash
uvx --from git+https://github.com/kikifadilah31/kft_pilecap_fem pilecap-mesh --init-example .
```

Menyalin ketiga contoh bawaan ke folder saat ini. Berkas yang disalin adalah berkas yang
**sama persis** dengan yang dipakai test regresi, jadi tidak bisa basi diam-diam.

### Untuk pengembangan

```bash
git clone https://github.com/kikifadilah31/kft_pilecap_fem && cd kft_pilecap_fem && uv sync --dev
```

Lalu jalankan lewat `uv run <command>`.

## Pemakaian

Contoh di bawah memakai `uv run` (jalur pengembangan). Bila memasang lewat
`uv tool install`, hilangkan awalan `uv run`.

```bash
uv run pilecap-mesh --config examples/ex01_standard_4pile/pilecap_config.json --input-dir examples/ex01_standard_4pile --export-msh
```

Dengan folder `input/` berisi file-file yang cocok pola auto-detect, cukup:

```bash
uv run pilecap-mesh
```

Untuk rantai penuh — mesh, analisis FEM, kontur, envelope, dan laporan — dalam satu
perintah dan satu folder (butuh `pile_reactions.csv`):

```bash
uv run pilecap-run --config examples/ex03_custom_polygon/pilecap_config.json --input-dir examples/ex03_custom_polygon
```

Membuat ulang laporan dari run yang sudah ada, tanpa mengulang analisis FEM:

```bash
uv run pilecap-report --result-dir output/pilecap_20260804_144133 --strips-x 7
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
├── SUMMARY.md             # ringkasan lintas kombinasi + governing + Known Limitations
├── Combo_<nama>/          # satu folder per kombinasi
│   ├── calc_sheet.md            # 10 bagian auditable, termasuk rantai telusur 1 elemen
│   ├── element_resultants.csv   # m11/m22/m12 lokal + m_x/m_y/m_xy/q_x/q_y global
│   ├── strip_moments_x.csv      # momen per lajur di muka pier
│   ├── shear_checks.csv         # demand geser satu arah & pons (kapasitas NOT_EVALUATED)
│   ├── reactions.csv            # reaksi tiap node jepit + baris TOTAL
│   ├── node_displacements.csv   # sumber contour_deflection.png
│   ├── equilibrium_check.json   # VC-0 + jejak beban tiap pile
│   ├── traceability_sample.json # nilai per titik Gauss untuk calc sheet bagian 5
│   ├── contour_mx.png … contour_deflection.png
│   └── deformed_opsvis.png
└── Envelope/              # nilai ekstrem lintas kombinasi + governing_combo
    ├── envelope_values.csv
    ├── envelope_summary.md
    └── envelope_*_max.png / _min.png
```

### Visualisasi

| Berkas | Isi |
|--------|-----|
| `mesh_plan.png` | Denah mesh, label pile & pier, subjudul override geometri |
| `boundary_load_check.png` | Peta node jepit & elemen terbeban — cek visual bahwa tumpuan dan beban menempel di tempat yang benar |
| `contour_m*.png` | Momen per elemen, colormap diverging berpusat nol (`TwoSlopeNorm`) |
| `contour_q*.png`, `contour_deflection.png` | Geser transversal dan lendutan |
| `model_opsvis.png`, `deformed_opsvis.png` | `opsv.plot_model()` / `plot_defo()`, faktor skala tercantum di judul |

Kontur digambar **datar per elemen**, tidak dihaluskan: nilai resultant memang per
elemen, dan interpolasi nodal akan menyiratkan kehalusan yang tidak pernah dihitung —
paling menyesatkan justru di daerah singularitas tepi zona jepit.

Plot opsvis **dilewati otomatis** di atas 3.000 elemen (dengan WARNING yang menyebut
alasannya), karena `opsv.plot_defo` tumbuh lebih cepat dari linier — terukur 5,1 detik
untuk 1.200 elemen. Paksa dengan `--opsvis`.

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
| `--opsvis` | `analyze` | Paksa plot opsvis meski di atas ambang elemen |
| `--result-dir` | `report` | Folder hasil analisis (default: run terakhir) |
| `--strips-x` / `--strips-y` | `report`, `run` | Jumlah lajur integrasi momen |
| `--moment-at pier_face\|peak\|both` | `report`, `run` | Lokasi momen desain |
| `--no-envelope` | `report`, `run` | Lewati envelope |
| `--wood-armer` | `report`, `run` | **Belum tersedia** — menolak dengan pesan sumber primer |
| `--init-example DIR` | `mesh`, `analyze`, `run` | Salin contoh bawaan ke DIR lalu keluar |
| `--export-msh`, `--dpi`, `--log-level` | semua | Output tambahan & verbositas |

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
