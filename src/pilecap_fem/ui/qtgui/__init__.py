"""Antarmuka desktop PySide6 -- SATU-SATUNYA tempat `PySide6` diimpor. EKSPERIMENTAL.

Disediakan untuk dibandingkan dengan `ui/wxgui/` sebelum salah satunya dipilih; keduanya
memakai lapisan logika yang sama persis.

.. rubric:: Aturan yang tidak boleh dilanggar

Salinan aturan `wxgui/`, dengan alasan yang sama:

* **Hanya sub-paket ini yang boleh mengimpor `PySide6`**, dan ia tidak mengimpor `wx` (begitu
  pula sebaliknya). Yang dapat salah secara diam-diam tinggal di `schema.py`, `runopts.py`,
  `formstate.py`, `desktop.py`, `detect.py`, dan `runner.py`, yang semuanya diuji tanpa
  display.
* **Engine tidak pernah dijalankan di dalam proses ini.** OpenSeesPy dan gmsh menyimpan state
  global proses, dan jendela desktop berumur panjang. Analisis selalu lewat `subprocess`
  (`runner.py`); yang berjalan in-process hanya pratinjau geometri.

Keduanya dijaga test AST di `tests/test_ui_desktop.py`.

.. rubric:: Yang berbeda dari `wxgui/` -- justru bahan perbandingannya

* Teks bantuan dirender sebagai **markdown** (`QLabel` + `Qt.MarkdownText`), bukan tampil
  mentah.
* Teks bantuan **membungkus sendiri** mengikuti lebar; tidak perlu mekanisme
  `wxgui.fields.TeksBantuan.atur_lebar`.
* Jarak label dan kotak isian diatur **`QFormLayout`**, bukan sizer yang disusun tangan --
  sizer itulah sumber bug jarak yang diperbaiki di v0.14.1.
* Uji asapnya berjalan **tanpa display** (`QT_QPA_PLATFORM=offscreen`), jadi tidak perlu
  dilewati di CI. Catatan: platform `offscreen` tidak punya font (DIUKUR: 0 keluarga), jadi
  ukuran teks dalam piksel tidak dapat diuji di sana.

.. rubric:: Pembagian berkas

* `fields.py` -- `Field` menjadi widget Qt, beserta baca/tulis nilainya.
* `illustration.py` -- ilustrasi dari `ui.rasterize` (PNG Typst, identik dengan PDF).
* `main.py` -- jendela utama yang merangkai semuanya.
"""
