# Catatan untuk `shell-kit`

Ditulis 2026-08-09, terhadap `shell-kit` v3.3.0.

Berkas ini menjawab satu pertanyaan yang diajukan saat memakai `pilecap-fem` v0.6.0:

> Plot kontur diameter *shear* tidak seperti untuk lentur — kenapa gradasinya tidak
> bertingkat? Apakah ini kesalahan pada `shell-kit`?

---

## Jawaban singkat: **bukan**. Tidak ada yang perlu Anda ubah di `shell-kit`.

Cacatnya ada di `pilecap-fem`, dan sudah diperbaiki di v0.7.0. Rinciannya di bawah,
supaya vonis ini dapat Anda periksa sendiri dan bukan sekadar dipercaya.

### Buktinya: datanya memang sudah diskret di sumbernya

`shell_kit/rebar.py:851-857`:

```python
idx = np.searchsorted(diameters, D_req, side='left')
result = np.full(D_req.shape, np.nan)   # melebihi terbesar -> tidak memadai
result[found] = diameters[idx[found]]
```

Setiap nilai yang keluar dari fungsi itu pasti salah satu dari tiga hal: `0.0` (tidak
butuh sengkang), anggota **persis** `SHEAR_DIAMETERS`, atau `NaN` (tidak memadai). Tidak
ada satu pun nilai kontinu yang mungkin keluar. Jadi bukan `shell-kit` yang menghasilkan
gradasi.

### Dan `shell-kit` sendiri sudah menggambarnya dengan benar

`shell_kit/plotting_rebar.py:205-223` memakai `BoundaryNorm` di atas nilai mm untuk plot
diameter, sehingga colorbarnya bertingkat dan berlabel `D10`…`D25`. Perilaku itu sudah
benar; yang tidak memakainya adalah kami.

### Yang salah di `pilecap-fem`

`cli_pilecap_report.py` mengirim `stirrup_diameter` ke `render_contour(...)`, yang
membangun `Normalize(vmin, vmax)` di atas colormap **kontinu** `YlOrRd`. Enam nilai
diskret mendarat di enam titik sembarang pada gradasi mulus, dengan colorbar berlabel
angka interpolasi alih-alih kode diameter.

Akar penyebab yang membuatnya mudah terjadi: `ShearRebarMap` adalah satu-satunya objek
hasil tulangan **tanpa** `labels` dan tanpa `is_categorical`, sehingga kode pemilih plot
tidak punya apa pun untuk dicabangkan — berbeda dari `RebarSelection` untuk lentur.
Daftar diameter yang diizinkan sebenarnya sudah tersedia, hanya tidak ikut dibawa ke
hasil. Perbaikan v0.7.0 membawanya serta.

---

## Satu wart kecil yang ditemukan sambil menelusuri

Ini **tidak** memengaruhi hasil apa pun. Disampaikan hanya karena akan membingungkan
orang berikutnya yang membacanya.

**`config.REBAR_CMAP` di `shell-kit` adalah kode mati.** `plotting_rebar.py:23`
mendeklarasikan ulang `REBAR_CMAP` sebagai variabel lokal modul dan memakai yang lokal
itu; nilai di `config` tidak pernah terbaca. Siapa pun yang ingin mengganti colormap
tulangan akan wajar mengubah `config.REBAR_CMAP` lebih dulu, dan tidak akan terjadi
apa-apa.

Dua pilihan perbaikan, keduanya sepele:

1. Hapus `REBAR_CMAP` dari `config.py`, atau
2. Hapus deklarasi lokal di `plotting_rebar.py:23` dan pakai `config.REBAR_CMAP`.

Pilihan (2) lebih baik bila colormap memang dimaksudkan dapat diatur dari satu tempat.

---

## Yang TIDAK diminta berubah

Perlu ditegaskan supaya tidak salah baca: **API `shell_kit.rebar` yang dipakai
`pilecap-fem` tidak perlu berubah sama sekali.** Seluruh fungsi murni yang kami panggil
(`calculate_required_shear_reinforcement`, `select_shear_diameter`, tabel
`REBAR_CONFIG_TABLE`, konstanta `AVAILABLE_DIAMETERS` dan `SHEAR_DIAMETERS`) sudah
memberikan persis yang dibutuhkan, termasuk daftar diameter yang membuat plot kategorikal
mungkin dibuat.
