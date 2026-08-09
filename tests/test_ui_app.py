"""Test halaman Streamlit itu sendiri, lewat `streamlit.testing.v1.AppTest`.

Dipisahkan dari `test_ui.py`, yang sengaja berjalan **tanpa streamlit terpasang**. Berkas
ini melengkapinya pada hal-hal yang hanya ada di halaman: widget opsi run yang ditulis
langsung di `app.py` (di luar skema), dan perilaku pemuat config yang bergantung pada
session state.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="antarmuka opsional: `uv sync --extra ui`")

from streamlit.testing.v1 import AppTest

from pilecap_fem.ui.launcher import CWD_ENV

APP = Path(__file__).resolve().parents[1] / "src" / "pilecap_fem" / "ui" / "app.py"
REPO = Path(__file__).resolve().parents[1]


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch) -> AppTest:
    monkeypatch.setitem(os.environ, CWD_ENV, str(REPO))
    return AppTest.from_file(str(APP), default_timeout=180).run()


def _widgets(at: AppTest) -> list:
    return [
        *at.number_input,
        *at.selectbox,
        *at.text_input,
        *at.checkbox,
        *at.multiselect,
    ]


def test_setiap_widget_formulir_punya_tooltip(app: AppTest):
    """Termasuk widget opsi run yang ditulis langsung di `app.py`, di luar `schema.py`.

    `test_ui.py` hanya dapat menjaga field yang berasal dari skema. Blok "Opsi penyajian"
    tidak melewatinya sama sekali, sehingga tanpa test ini ia dapat kehilangan penjelasan
    tanpa satu pun kegagalan.
    """
    assert not app.exception
    tanpa = [w.label for w in _widgets(app) if not getattr(w, "help", None)]
    assert tanpa == []


def test_memuat_config_mengisi_formulir_dan_mengubah_field_yang_tampil(app: AppTest):
    """Cabang `pier.shape` harus ikut berpindah, bukan sekadar angkanya yang berganti."""
    app.text_input[1].set_value("examples/ex02_standard_12pile/pilecap_config.json")
    app.button[0].click().run()

    assert not app.exception
    assert any("Dimuat dari" in s.value for s in app.success)
    assert app.session_state["fld:pier.shape"] == "circular"
    assert app.session_state["fld:pilecap.thickness"] == 1500

    labels = [w.label for w in app.number_input]
    assert not any("Lebar arah X" in label for label in labels)


def test_config_tidak_ada_ditolak_dengan_pesan_bukan_traceback(app: AppTest):
    app.text_input[1].set_value("tidak/ada/pilecap_config.json")
    app.button[0].click().run()

    assert not app.exception
    assert any("tidak ditemukan" in e.value for e in app.error)


def test_pratinjau_menggambar_denah_tanpa_menjalankan_analisis(app: AppTest):
    """Tombol pratinjau adalah submit KEDUA; ia tidak boleh memicu subprocess run."""
    app.text_input[0].set_value("examples/ex01_standard_4pile")
    tombol = [b for b in app.button if b.label == "Perbarui pratinjau"]
    assert tombol, "tombol pratinjau tidak ada"

    tombol[0].click().run()
    assert not app.exception
    assert [s.value for s in app.subheader] == ["Pratinjau geometri"]
    assert not app.error
    # Run yang sungguhan akan menulis session state ini; pratinjau tidak boleh.
    assert app.session_state["last_run_dir"] == ""
