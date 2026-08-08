"""Antarmuka grafis opsional `pilecap-ui`, dijalankan offline di localhost.

Sub-paket ini berada di luar daftar modul PRD Bagian 3.1 -- preseden yang sama dengan
`capacity_engine.py`: PRD ditulis ketika antarmuka grafis belum menjadi lingkup.

.. rubric:: Aturan yang tidak boleh dilanggar

Bagian ini **TIDAK PERNAH** menjalankan engine di dalam prosesnya sendiri. Ia menyusun
daftar argumen lalu memanggil CLI sebagai **subprocess**.

Aturan itu bukan gaya. Tiga alasan, masing-masing sudah terbukti:

1. **Repo `shell-kit` pernah membayarnya.** Docstring `shell_kit/ui/__init__.py` mencatat
   bahwa UI Streamlit di sana pernah mengimpor potongan engine lalu menulis ulang
   orkestrasinya, sehingga ada dua implementasi yang harus dijaga sinkron -- dan UI itu
   akhirnya dihapus.

2. **OpenSeesPy dan gmsh menyimpan state global proses.** `fem_engine` memanggil
   `ops.wipe()` per kombinasi dan `mesh_engine` melakukan init/finalize gmsh. Server
   Streamlit berumur panjang dan dapat menjalankan beberapa rerun; di dalam satu proses,
   dua analisis akan saling merusak state C library yang sama.

3. **`run_manifest.json` merekam string perintah.** Dengan subprocess, yang tercatat
   adalah perintah CLI yang benar-benar dapat dijalankan ulang orang lain. Pada tool
   bertingkat liabilitas ini (PRD Bagian 1.3), jejak yang tidak dapat direproduksi sama
   nilainya dengan tidak ada jejak.

Konsekuensi yang diinginkan: UI **tidak bisa** menyimpang dari CLI. Setiap opsi, setiap
validasi fail-fast, dan setiap pesan error otomatis ikut tanpa disalin.

.. rubric:: Pembagian modul

`schema.py` dan `argv.py` **sengaja tidak mengimpor streamlit**. Keduanya berisi satu-
satunya bagian UI yang dapat salah secara diam-diam -- config yang tidak sah dan flag yang
tidak dikenal -- sehingga keduanya harus dapat diuji pada lingkungan yang hanya memasang
paket inti, tanpa extra `[ui]`.
"""
