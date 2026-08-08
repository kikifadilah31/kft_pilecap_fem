"""Halaman Streamlit `pilecap-ui`.

Dijalankan oleh `launcher.py`, bukan diimpor. Seluruh logika yang dapat salah secara
diam-diam ada di `schema.py` dan `argv.py`, yang keduanya diuji tanpa streamlit.

Halaman ini hanya: menggambar formulir, menampilkan perintah, menjalankan subprocess,
dan menampilkan log beserta hasilnya.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

import streamlit as st

from pilecap_fem import __version__, config
from pilecap_fem.ui import argv as argv_builder
from pilecap_fem.ui import schema
from pilecap_fem.ui.launcher import CWD_ENV

#: Derau tqdm di stderr: carriage return dan potongan progress bar.
PROGRESS_NOISE = re.compile(r"\r|\d+%\||it/s\]|s/it\]")
MAX_LOG_LINES = 400

WORKDIR = Path(os.environ.get(CWD_ENV, os.getcwd()))

st.set_page_config(
    page_title="pilecap-fem",
    page_icon=":material/foundation:",
    layout="centered",
)

st.session_state.setdefault("last_run_dir", "")
st.session_state.setdefault("last_config_path", "")
st.session_state.setdefault("last_command", "")


# ---------------------------------------------------------------------------
# Deteksi berkas input
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False, ttl="10s")
def detect_inputs(folder: str) -> dict[str, str]:
    """Jalankan auto-detect bawaan tool terhadap folder yang ditunjuk.

    Memakai `io_utils.autodetect` yang sama dengan CLI, sehingga apa yang ditampilkan di
    sini persis apa yang nanti dipakai -- termasuk penolakannya bila ada dua berkas yang
    cocok pada satu pola.
    """
    from pilecap_fem import io_utils

    path = Path(folder)
    found: dict[str, str] = {}
    if not path.is_dir():
        return found
    for key in config.FILE_PATTERNS:
        try:
            match = io_utils.autodetect(path, key, required=False)
        except Exception as exc:  # pola ambigu -> tampilkan sebagai masalah, bukan crash
            found[key] = f"AMBIGU: {exc}"
            continue
        if match is not None:
            found[key] = match.name
    return found


# ---------------------------------------------------------------------------
# Widget dari deskripsi field
# ---------------------------------------------------------------------------


def render_field(f: schema.Field, values: dict[str, Any], unit_labels: dict[str, str]) -> Any:
    """Gambar satu widget menurut deskripsinya di `schema.py`."""
    unit = unit_labels.get(f.unit, f.unit)
    label = f"{f.label} [{unit}]" if unit else f.label
    key = f"fld:{f.key}"
    current = values.get(f.key, f.default)

    if f.kind == "bool":
        return st.checkbox(label, value=bool(current), key=key, help=f.help or None)

    if f.kind == "select":
        options = list(f.options())
        index = options.index(current) if current in options else 0
        return st.selectbox(label, options, index=index, key=key, help=f.help or None)

    if f.kind == "multiselect":
        return st.multiselect(
            label, list(f.options()), default=list(current or ()), key=key, help=f.help or None
        )

    if f.kind == "text":
        return st.text_input(label, value=str(current or ""), key=key, help=f.help or None)

    if f.kind == "int":
        return st.number_input(
            label,
            value=int(current) if current is not None else 0,
            step=1,
            min_value=int(f.min_value) if f.min_value is not None else None,
            key=key,
            help=f.help or None,
        )

    if f.kind == "pair":
        # Label kelompok muncul sekali sebagai caption; label tiap kotak tetap ada untuk
        # pembaca layar tetapi disembunyikan -- tanpa itu setiap koordinat mengulang
        # seluruh nama field dan formulir jadi sulit dipindai.
        pair = list(current or [0.0, 0.0])
        st.caption(label)
        with st.container(horizontal=True):
            x = st.number_input(
                f"{f.label} x",
                value=float(pair[0]),
                key=f"{key}:x",
                label_visibility="collapsed",
                help=f.help or None,
            )
            y = st.number_input(
                f"{f.label} y",
                value=float(pair[1]),
                key=f"{key}:y",
                label_visibility="collapsed",
            )
        return [x, y]

    # number -- yang opsional memakai text_input agar "kosong" benar-benar dapat
    # dinyatakan; `st.number_input` tidak punya keadaan kosong yang jelas.
    if f.optional:
        raw = st.text_input(
            label,
            value="" if current is None else str(current),
            placeholder="kosongkan bila tidak dipakai",
            key=key,
            help=f.help or None,
        )
        if not raw.strip():
            return None
        try:
            return float(raw)
        except ValueError:
            st.warning(f"{f.label}: '{raw}' bukan angka; diabaikan.", icon=":material/warning:")
            return None

    return st.number_input(
        label,
        value=float(current if current is not None else 0.0),
        min_value=f.min_value,
        max_value=f.max_value,
        key=key,
        help=f.help or None,
    )


# ---------------------------------------------------------------------------
# Halaman
# ---------------------------------------------------------------------------

st.title("pilecap-fem")
st.caption(
    f"v{__version__} — antarmuka ini menjalankan `pilecap-run` yang sama persis, "
    "sehingga hasilnya identik dengan menjalankannya dari terminal."
)

with st.container(border=True):
    st.markdown(f"**Folder kerja** — `{WORKDIR}`")
    st.caption("Hasil analisis mendarat di sini, sama seperti menjalankan CLI dari folder ini.")

input_dir = st.text_input(
    "Folder input",
    value=str(WORKDIR / "input"),
    help="Folder berisi pile_reactions.csv dan (opsional) CSV geometri. "
    "Config TIDAK perlu ada di sini — formulir ini yang membuatnya.",
)

detected = detect_inputs(input_dir)
override_entity = {
    "pilecap_polygon": "pilecap",
    "pile_coords": "pile",
    "pier_polygon": "pier",
}
overridden: dict[str, str] = {
    override_entity[k]: v for k, v in detected.items() if k in override_entity
}

with st.container(border=True):
    if not Path(input_dir).is_dir():
        st.error("Folder tidak ditemukan.", icon=":material/error:")
    elif "reactions" not in detected:
        st.warning(
            "`pile_reactions.csv` tidak terdeteksi — analisis tidak dapat berjalan tanpa itu.",
            icon=":material/warning:",
        )
    else:
        st.success(f"Reaksi pile: `{detected['reactions']}`", icon=":material/check_circle:")

    if overridden:
        daftar = ", ".join(f"`{v}`" for v in overridden.values())
        st.info(
            f"CSV geometri terdeteksi ({daftar}). Field yang bersangkutan di bawah akan "
            "**diabaikan** — geometri diambil dari CSV.",
            icon=":material/rule:",
        )

values = schema.default_values()

with st.form("masukan", border=False):
    unit_labels = {"length": "mm", "force": "kN", "stress": "MPa"}

    for section in schema.SECTIONS:
        sumber_override = (
            overridden.get(section.override_entity) if section.override_entity else None
        )
        with st.container(border=True):
            st.markdown(f"### {section.title}")
            if section.help:
                st.caption(section.help)
            if sumber_override:
                st.caption(
                    f":material/rule: Diabaikan — di-override `{sumber_override}`. "
                    "Nilai tetap ditulis ke config supaya terlihat apa yang dilewati."
                )
            for f in section.fields:
                if f.visible_when is not None and not f.visible_when(values):
                    continue
                values[f.key] = render_field(f, values, unit_labels)
                # Satuan dipilih di formulir yang sama; label field berikutnya harus
                # mengikutinya dalam rerun ini juga.
                if f.key.startswith("units."):
                    unit_labels[f.name] = values[f.key]

    with st.container(border=True):
        st.markdown("### Opsi penyajian & jalannya analisis")
        run_values: dict[str, Any] = {}
        run_values["output_dir"] = st.text_input("Folder output", value="output")
        with st.container(horizontal=True):
            run_values["theme"] = st.selectbox("Tema plot", list(config.THEMES))
            run_values["contour_method"] = st.selectbox(
                "Metode kontur", list(config.CONTOUR_METHODS)
            )
        with st.container(horizontal=True):
            run_values["dpi"] = st.number_input(
                "DPI", value=config.OUTPUT_DPI, min_value=50, max_value=600, step=50
            )
            run_values["log_level"] = st.selectbox(
                "Level log", ["INFO", "DEBUG", "WARNING", "ERROR"]
            )
        combo_text = st.text_input(
            "Batasi kombinasi (pisahkan spasi)",
            placeholder="kosongkan untuk menganalisis semua",
        )
        run_values["combo"] = combo_text.split() if combo_text.strip() else None
        run_values["opsvis"] = st.checkbox(
            "Paksa plot opsvis walau elemen banyak",
            help=f"Bawaannya dilewati di atas {config.OPSVIS_MAX_ELEMENTS:,} elemen.",
        )
        run_values["no_rebar_plots"] = st.checkbox("Lewati plot tulangan (lebih cepat)")
        run_values["no_envelope"] = st.checkbox("Lewati envelope")

    submitted = st.form_submit_button(
        "Jalankan analisis", icon=":material/play_arrow:", type="primary"
    )

if not submitted:
    if st.session_state["last_run_dir"]:
        st.divider()
        st.success(
            f"Run terakhir: `{st.session_state['last_run_dir']}`",
            icon=":material/check_circle:",
        )
        st.code(st.session_state["last_command"], language="bash")
    st.stop()

# ---------------------------------------------------------------------------
# Jalankan
# ---------------------------------------------------------------------------

config_path = schema.write_config(schema.build_config(values), WORKDIR)
cli_argv = argv_builder.build_argv(config_path, Path(input_dir), run_values)
command = argv_builder.format_command(cli_argv)

st.session_state["last_config_path"] = str(config_path)
st.session_state["last_command"] = command

st.caption("Perintah yang dijalankan — dapat disalin dan dijalankan ulang di terminal:")
st.code(command, language="bash")

run_dir = ""
stdout_lines: list[str] = []

with st.status("Menjalankan…", expanded=True) as status:
    log_slot = st.empty()
    lines: list[str] = []

    proc = subprocess.Popen(
        [sys.executable, "-m", "pilecap_fem.cli_pilecap_run", *cli_argv],
        cwd=str(WORKDIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        encoding="utf-8",
        errors="replace",
    )

    def _drain_stdout(stream: Any) -> None:
        """stdout HARUS ikut dibaca meski isinya sedikit.

        Pipe yang penuh dan tidak pernah dibaca akan menggantungkan proses anak. stdout
        di sini hanya memuat baris `OK -> <run_dir>`, tetapi mengabaikannya tetap berisiko.
        """
        for line in stream:
            stdout_lines.append(line.rstrip())

    assert proc.stdout is not None and proc.stderr is not None  # PIPE diminta di atas
    drainer = threading.Thread(target=_drain_stdout, args=(proc.stdout,), daemon=True)
    drainer.start()

    # Log pilecap-fem mengalir ke STDERR (`logging.StreamHandler(stream=sys.stderr)`),
    # sedangkan stdout hanya memuat hasil akhir. Inilah yang di-stream ke layar.
    for line in proc.stderr:
        if PROGRESS_NOISE.search(line):
            continue
        lines.append(line.rstrip())
        log_slot.code("\n".join(lines[-MAX_LOG_LINES:]))

    proc.wait()
    drainer.join(timeout=5)

    for line in stdout_lines:
        if line.startswith("OK ->"):
            run_dir = line.split("->", 1)[1].strip()

    if proc.returncode == 0:
        status.update(label="Selesai", state="complete", expanded=False)
    else:
        status.update(label=f"Gagal (exit {proc.returncode})", state="error", expanded=True)

if proc.returncode == 0:
    st.session_state["last_run_dir"] = run_dir
    st.success("Analisis selesai.", icon=":material/check_circle:")
    with st.container(border=True):
        st.markdown(f"**Folder hasil** — `{run_dir}`")
        st.markdown(f"**Config yang dipakai** — `{config_path}`")
        st.caption(
            "Buka `SUMMARY.md` di folder hasil untuk ringkasan, dan `calc_sheet.md` di "
            "tiap folder kombinasi untuk perhitungan yang dapat ditelusuri."
        )
elif proc.returncode == 2:
    # PilecapError. Pesannya sudah ditulis untuk dibaca engineer, jadi ditampilkan apa
    # adanya -- tetapi HARUS didahulukan: pada input dengan override geometri, log
    # diakhiri belasan baris WARNING dan penyebab sebenarnya terkubur di bawahnya.
    ringkas = [ln for ln in lines if ln.startswith("GAGAL:")]
    if ringkas:
        mulai = lines.index(ringkas[0])
        st.error("Masukan ditolak:", icon=":material/error:")
        st.code("\n".join(lines[mulai:]))
    else:
        st.error("Masukan ditolak. Lihat log di atas.", icon=":material/error:")
    with st.expander("Log lengkap"):
        st.code("\n".join(lines[-MAX_LOG_LINES:]))
elif proc.returncode == 4:
    st.warning("Fitur yang diminta belum tersedia di versi ini.", icon=":material/build:")
else:
    st.error(
        f"Berhenti tak terduga (exit {proc.returncode}). Log lengkap ada di atas.",
        icon=":material/error:",
    )
