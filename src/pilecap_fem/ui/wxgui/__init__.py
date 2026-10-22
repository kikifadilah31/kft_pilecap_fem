"""Antarmuka desktop wxPython -- SATU-SATUNYA tempat `wx` diimpor.

.. rubric:: Aturan yang tidak boleh dilanggar

**Hanya sub-paket ini yang boleh mengimpor `wx`.** Aturan ini salinan dari aturan
"`schema.py` dan `argv.py` tidak mengimpor streamlit", dengan alasan yang sama persis: yang
dapat salah secara diam-diam -- pemetaan formulir ke config, visibilitas bersyarat, label
satuan, koersi "kosong" -- tinggal di `schema.py`, `runopts.py`, dan `formstate.py`, dan
ketiganya harus dapat diuji pada lingkungan **tanpa display sama sekali**.

Berkas di sini karena itu hanya menggambar dan meneruskan. Dijaga
`tests/test_ui.py::test_hanya_wxgui_yang_mengimpor_wx`.

**Engine tidak pernah dijalankan di dalam proses ini.** Lihat alasan lengkapnya di
`pilecap_fem/ui/__init__.py`; satu di antaranya berlaku lebih keras di sini daripada di
Streamlit: OpenSeesPy dan gmsh menyimpan state global proses, dan jendela desktop berumur
panjang persis seperti server. Analisis karena itu selalu lewat `subprocess`
(`runner.py`). Satu-satunya yang berjalan in-process adalah pratinjau geometri, yang tidak
menyentuh gmsh maupun solver.

.. rubric:: Pembagian berkas

* `fields.py` -- `Field` menjadi kontrol wx, beserta baca/tulis nilainya.
* `svgview.py` -- menampilkan ilustrasi; rasterisasinya sendiri ada di `ui.rasterize`,
  di luar sub-paket ini, karena ia tidak butuh wx dan cache yang salah adalah kegagalan
  diam-diam yang wajib dapat diuji tanpa display.
* `runner.py` -- subprocess CLI dan aliran lognya ke GUI.
* `main.py` -- jendela utama yang merangkai semuanya.
"""
