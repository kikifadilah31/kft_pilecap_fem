# Changelog

Format mengikuti template PRD Bagian 16C.

## [0.1.0] — 2026-08-04 — Fase 1: geometri + mesh generator

### Added
- `config.py` — Single Source of Truth: tabel konversi satuan, pola auto-detect, ambang
  validasi, opsi gmsh, blok teks disclaimer & Known Limitations, `setup_logging()`.
- `io_utils.py` — satu-satunya titik konversi satuan; auto-detect input; pembacaan CSV
  polygon/pile/pier; **resolusi sumber geometri PRD Bagian 5.2.1** lengkap dengan WARNING
  override 5 baris.
- `validators.py` — implementasi aturan fail-fast PRD Bagian 5.3 + hierarki exception tool.
- `geometry_builder.py` — data model (`Polygon2D`, `Pile`, `Pier`, `GeometryModel`,
  `GeometryResolution`) dan generator grid pile / polygon.
- `mesh_engine.py` — gmsh OCC + `fragment` + physical group (prioritas PIER > PILE > CAP) +
  mesh all-quad + verifikasi hasil.
- `mesh_model.py` — cache Cond A: luas, centroid, theta, dan lookup group O(1).
- `provenance.py` — `run_manifest.json`.
- `renderer.py` / `reporter.py` — subset Fase 1: `mesh_plan.png` & `mesh_summary.md`.
- `cli_pilecap_mesh.py` — CLI `pilecap-mesh`; tiga CLI lain berupa stub berpesan jelas.
- `examples/` — tiga kasus sesuai PRD Bagian 5.4 (folder `expected/` menyusul di Fase 2–3).
- 186 test; coverage 96%.

### Standards
Item PRD Bagian 17 yang **dikonfirmasi user** pada rilis ini:

| # | Item | Keputusan |
|---|------|-----------|
| 4 | `E` beton | Wajib diisi user; `E: null` → RAISE. Tool tidak pernah menghitung E dari `f'c`. Ditambah field wajib `material.E_source`. |
| 9 | Bahasa laporan | Indonesia, istilah teknis dibiarkan Inggris. |
| 11 | Pile sebagai pegas | Belum diperlukan; `fem_engine` akan dirancang dengan abstraksi strategy (Fase 2). |
| 12, 14 | Satuan input | mm / kN / MPa. `Mesh.MeshSize` dalam meter. |
| 13 | `MIN_ELEM_PER_PILE_DIAMETER` | **6** |
| 15 | Ambang keseragaman mesh | **0.35**, diterapkan pada group CAP (lihat Deviations) |
| 16 | Versi gmsh | **4.15.2**, di-pin eksak |
| 17 | Multi-pier | Didukung. JSON tetap satu pier; lebih dari satu pier hanya lewat `pier_polygon.csv` berkolom `pier_id`. |

Masih **terbuka** (memblokir Fase 3): item 2, 3, 5, 6, 7, 8, 10, 18. Selama itu, cek
kapasitas berstatus `NOT_EVALUATED`.

### Deviations from PRD — beserta alasannya
1. **Ambang keseragaman mesh (item 15) berlaku pada group CAP, bukan seluruh elemen.**
   Pengukuran pada ketiga contoh: `std/mean` seluruh elemen 0.346 / 0.403 / 0.417, sedangkan
   pada group CAP 0.131 / 0.200 / 0.171. Nilai "seluruh elemen" didominasi cincin transisi di
   sekeliling disk pile — metrik itu mengukur kelengkungan geometri, bukan keseragaman mesh.
   Angka 0.35 dipertahankan; hanya definisinya dipertajam.
2. **Rule 7a (`D_pile / h ≥ 6`) memakai `size_local_pile` bila `size_mode = "graded"`.**
   PRD menuliskannya terhadap `size_global`, rumusan yang ditulis dengan asumsi mode
   `uniform`. Pada mode graded, area pile justru di-mesh dengan `size_local_pile`, sehingga
   membandingkan terhadap `size_global` akan menolak konfigurasi yang justru memenuhi maksud
   aturannya.
3. **`pier.centerline` masuk daftar field yang di-override bila ada `pier_polygon.csv`.**
   PRD Bagian 5.2.1 menyatakan centerline tidak pernah di-override — aturan itu ditulis saat
   asumsinya masih satu pier. Dengan multi-pier, satu nilai JSON tidak dapat melayani N pier;
   centerline tiap pier diambil dari centroid polygon-nya dan override-nya diteriakkan
   seperti override lain.
4. **`mesh_model.elem_theta` dihitung dari geometri elemen** (`v1 = ½(r₂+r₃−r₁−r₄)`), bukan
   dari penyederhanaan "local-x ≈ arah node1→node2" di PRD Bagian 7.2(3). Nilai ini
   **ditandai belum terverifikasi** dan tidak boleh dipakai menghasilkan momen desain sampai
   VC-2 dijalankan (Fase 2).

### Findings — hasil pengukuran, bukan asumsi
- **`Mesh.Algorithm = 11` menghasilkan mesh 100% quad sendiri**, bahkan tanpa
  `setRecombine`. `RecombinationAlgorithm = 3` + `setRecombine` berfungsi sebagai lapis
  pengaman kedua. Verifikasi `n_tri == 0` setelah `generate(2)` tetap wajib — itulah yang
  membuktikan hasilnya.
- **OpenSees tidak menyediakan `eleLoad` tekanan permukaan sembarang untuk elemen shell.**
  Berdampak pada Fase 2: mode `pressure` (PRD Bagian 7.3a) akan diterapkan sebagai beban
  nodal konsisten per elemen. Matematikanya identik (`p_i = P_z,i / A_disk,i` dengan
  `A_disk` = jumlah luas elemen mesh), Σ beban tetap persis `P_z,i` sehingga VC-0 tetap eksak.

### Validation
- VC-0 s/d VC-7: **belum dijalankan** — seluruhnya membutuhkan model FEM (Fase 2+).
  `pilecap-mesh` mencatat `equilibrium_VC0: NOT_RUN` di `run_manifest.json`.
- Golden file: **belum dibuat** — dibuat setelah hasil FEM tersedia (Fase 2–3).
- `config.MOMENT_SIGN_FACTOR` sengaja bernilai `None`; ditetapkan hanya setelah VC-1.
