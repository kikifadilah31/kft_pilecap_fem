"""Halaman Streamlit `pilecap-ui`.

Dijalankan oleh `launcher.py`, bukan diimpor. Seluruh logika yang dapat salah secara
diam-diam ada di `schema.py` dan `argv.py`, yang keduanya diuji tanpa streamlit.

Halaman ini hanya: menggambar formulir, menampilkan perintah, menjalankan subprocess,
dan menampilkan log beserta hasilnya.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path
from typing import Any

import streamlit as st

from pilecap_fem import __version__, config
from pilecap_fem.ui import argv as argv_builder
from pilecap_fem.ui import detect, formstate, runner, runopts, schema
from pilecap_fem.ui.launcher import CWD_ENV

#: Dipakai bersama antarmuka desktop; lihat `ui/runner.py` untuk alasan satu salinan.
PROGRESS_NOISE = runner.PROGRESS_NOISE
MAX_LOG_LINES = runner.MAX_LOG_LINES

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
    """Pembungkus cache atas `detect.deteksi`, yang dipakai bersama antarmuka desktop."""
    return detect.deteksi(folder)


# ---------------------------------------------------------------------------
# Widget dari deskripsi field
# ---------------------------------------------------------------------------


def apply_loaded_config(path_text: str) -> None:
    """Muat `pilecap_config.json` ke session state, lalu rerun agar widget membacanya.

    HARUS dipanggil di luar `st.form` dan sebelum widget dibangun: Streamlit menolak mutasi
    `session_state` milik widget yang sudah terlanjur ada pada rerun ini. Karena itu nilai
    ditulis lebih dulu, lalu `st.rerun()` membangun ulang seluruh formulir dari nilai baru.
    """
    import json

    path = Path(path_text).expanduser()
    if not path.is_absolute():
        path = WORKDIR / path
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        st.error(f"Berkas tidak ditemukan: `{path}`", icon=":material/error:")
        return
    except json.JSONDecodeError as exc:
        st.error(f"Bukan JSON yang sah: {exc}", icon=":material/error:")
        return
    if not isinstance(raw, dict):
        st.error("Isi config harus berupa objek JSON di level teratas.", icon=":material/error:")
        return

    loaded_values, unknown = schema.values_from_config(raw)
    for f in schema.ALL_FIELDS:
        value = loaded_values[f.key]
        if f.kind == "pair":
            pair = list(value or [0.0, 0.0])
            st.session_state[f"fld:{f.key}:x"] = float(pair[0])
            st.session_state[f"fld:{f.key}:y"] = float(pair[1])
            continue
        if f.kind == "multiselect":
            st.session_state[f"fld:{f.key}"] = list(value or ())
            continue
        if f.optional and f.kind == "number":
            # Field opsional digambar sebagai text_input agar "kosong" dapat dinyatakan.
            st.session_state[f"fld:{f.key}"] = "" if value is None else str(value)
            continue
        if value is not None:
            st.session_state[f"fld:{f.key}"] = value

    st.session_state["loaded_from"] = str(path)
    st.session_state["loaded_unknown"] = list(unknown)
    st.rerun()


def seed(key: str, name: str, value: Any) -> dict[str, Any]:
    """Argumen nilai awal, DIHILANGKAN bila widget sudah punya nilai di session state.

    Streamlit memperingatkan bila sebuah widget menerima nilai awal (`value`/`index`/
    `default`) sekaligus nilainya diatur lewat session state -- dan pemuat config memang
    mengatur lewat session state, karena itu satu-satunya cara mengubah isi widget yang
    sudah terlanjur dibuat. Menghilangkan argumennya membuat kedua jalur -- bawaan skema
    dan config yang dimuat -- hidup berdampingan tanpa peringatan.
    """
    return {} if key in st.session_state else {name: value}


def render_field(f: schema.Field, values: dict[str, Any], unit_labels: dict[str, str]) -> Any:
    """Gambar satu widget menurut deskripsinya di `schema.py`."""
    unit = unit_labels.get(f.unit, f.unit)
    label = f"{f.label} [{unit}]" if unit else f.label
    key = f"fld:{f.key}"
    current = st.session_state.get(key, values.get(f.key, f.default))

    if f.kind == "bool":
        return st.checkbox(label, key=key, help=f.help or None, **seed(key, "value", bool(current)))

    if f.kind == "select":
        options = list(f.options())
        index = options.index(current) if current in options else 0
        return st.selectbox(
            label, options, key=key, help=f.help or None, **seed(key, "index", index)
        )

    if f.kind == "multiselect":
        return st.multiselect(
            label,
            list(f.options()),
            key=key,
            help=f.help or None,
            **seed(key, "default", list(current or ())),
        )

    if f.kind == "text":
        return st.text_input(
            label, key=key, help=f.help or None, **seed(key, "value", str(current or ""))
        )

    if f.kind == "int":
        return st.number_input(
            label,
            step=int(f.step) if f.step else 1,
            min_value=int(f.min_value) if f.min_value is not None else None,
            max_value=int(f.max_value) if f.max_value is not None else None,
            key=key,
            help=f.help or None,
            **seed(key, "value", int(current) if current is not None else 0),
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
                key=f"{key}:x",
                label_visibility="collapsed",
                help=f.help or None,
                **seed(f"{key}:x", "value", float(pair[0])),
            )
            y = st.number_input(
                f"{f.label} y",
                key=f"{key}:y",
                label_visibility="collapsed",
                help=f.help or None,
                **seed(f"{key}:y", "value", float(pair[1])),
            )
        return [x, y]

    # number -- yang opsional memakai text_input agar "kosong" benar-benar dapat
    # dinyatakan; `st.number_input` tidak punya keadaan kosong yang jelas.
    if f.optional:
        raw = st.text_input(
            label,
            placeholder="kosongkan bila tidak dipakai",
            key=key,
            help=f.help or None,
            **seed(key, "value", "" if current is None else str(current)),
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
        min_value=f.min_value,
        max_value=f.max_value,
        key=key,
        help=f.help or None,
        **seed(key, "value", float(current if current is not None else 0.0)),
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
overridden = detect.override_terdeteksi(detected)

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

# --- Muat config yang sudah ada -------------------------------------------
# HARUS di luar `st.form`: tombol di dalam form hanya bereaksi saat form dikirim, dan
# nilai widget baru dapat ditulis ke session state sebelum widget-nya dibangun.
with st.container(border=True):
    st.markdown("**Muat `pilecap_config.json` yang sudah ada** _(opsional)_")
    st.caption(
        "Mengisi seluruh formulir di bawah dari berkas config yang pernah dibuat — "
        "hasil run sebelumnya, contoh bawaan, atau config tulisan tangan. "
        "Anda tetap dapat menyuntingnya setelah dimuat."
    )
    with st.container(horizontal=True):
        config_to_load = st.text_input(
            "Path config",
            value="",
            placeholder="mis. examples/ex01_standard_4pile/pilecap_config.json",
            label_visibility="collapsed",
            help="Path berkas config JSON, boleh relatif terhadap folder kerja. Config "
            "hasil run sebelumnya ada di `ui_configs/` atau di folder hasil run itu "
            "sendiri; contoh bawaan ada di `examples/`.",
        )
        muat = st.button("Muat", icon=":material/upload_file:")
    if muat:
        if config_to_load.strip():
            apply_loaded_config(config_to_load.strip())
        else:
            st.warning("Isi dulu path config-nya.", icon=":material/warning:")

    if st.session_state.get("loaded_from"):
        st.success(f"Dimuat dari `{st.session_state['loaded_from']}`", icon=":material/check:")
        unknown = st.session_state.get("loaded_unknown") or []
        if unknown:
            # Dilaporkan, tidak dibuang diam-diam: config tulisan tangan boleh memuat field
            # yang belum diwakili formulir, dan menyimpan ulang lewat formulir ini akan
            # menghilangkannya.
            st.warning(
                "Kunci berikut tidak dikenal formulir dan **tidak akan ikut** ditulis ke "
                f"config baru: `{'`, `'.join(unknown)}`",
                icon=":material/warning:",
            )

values = schema.default_values()

with st.form("masukan", border=False):
    # Diturunkan dari pilihan `units.*` berikut cadangan `config.DEFAULT_INPUT_UNITS`;
    # daftar yang diketik di sini akan menyimpang diam-diam begitu bawaannya berubah.
    unit_labels = formstate.unit_labels(values)

    for section in schema.SECTIONS:
        sumber_override = (
            overridden.get(section.override_entity) if section.override_entity else None
        )
        with st.container(border=True):
            st.markdown(f"### {section.title}")
            if section.help:
                st.caption(section.help)
            if section.illustration:
                # `st.image` menerima STRING SVG, jadi berkasnya cukup dibaca -- tidak
                # perlu rasterisasi dan tidak ada dependency tambahan. Kegagalan membaca
                # tidak boleh menjatuhkan formulir: ilustrasi itu alat bantu, sedangkan
                # yang sedang dikerjakan user adalah masukan analisisnya.
                try:
                    st.image(
                        (config.illustrations_dir() / section.illustration).read_text(
                            encoding="utf-8"
                        ),
                        width="stretch",
                    )
                except OSError as exc:  # pragma: no cover -- instalasi tidak lengkap
                    st.caption(f":material/broken_image: Ilustrasi tidak dapat dimuat ({exc}).")
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
        st.markdown(f"### {runopts.RUN_SECTION.title}")
        st.caption(runopts.RUN_SECTION.help)
        # Dirender dengan loop YANG SAMA seperti bagian skema di atas. Sepuluh opsi ini
        # semula ditulis inline di sini; begitu ada frontend kedua, salinan keduanya akan
        # menyimpang dari kunci `dest` yang diharapkan `build_argv` -- dan flag yang tidak
        # dikenal baru ketahuan saat run gagal di tangan pengguna.
        run_form: dict[str, Any] = runopts.default_values()
        for f in runopts.RUN_FIELDS:
            run_form[f.key] = render_field(f, run_form, unit_labels)

    run_values = runopts.to_argv_values(run_form)

    with st.container(horizontal=True):
        submitted = st.form_submit_button(
            "Jalankan analisis", icon=":material/play_arrow:", type="primary"
        )
        # Submit KEDUA pada form yang sama. Nilai widget di dalam `st.form` baru
        # diperbarui saat form dikirim, sehingga tombol biasa akan menggambar pratinjau
        # dari nilai yang sudah usang -- justru gambar yang paling menyesatkan di sini.
        preview = st.form_submit_button("Perbarui pratinjau", icon=":material/preview:")

if preview:
    # Hanya geometri: tidak menyentuh gmsh maupun OpenSees, jadi selesai dalam milidetik.
    from pilecap_fem import renderer
    from pilecap_fem.ui import preview as preview_mod
    from pilecap_fem.validators import PilecapError

    st.divider()
    st.subheader("Pratinjau geometri")
    try:
        geom = preview_mod.build_preview_geometry(
            schema.build_config(values), Path(input_dir) if input_dir.strip() else None
        )
    except PilecapError as exc:
        # Pesan validator sudah ditulis untuk dibaca engineer; ditampilkan apa adanya.
        st.error(str(exc), icon=":material/error:")
    else:
        st.pyplot(
            renderer.render_geometry_plan(
                geom,
                style=renderer.PlotStyle(theme=config.theme(run_values["theme"])),
                # Engineer & tanggal sudah lama dikumpulkan formulir tetapi dibuang di
                # pratinjau; kini ikut ke kop, sama seperti pada plot hasil run.
                block=renderer.TitleBlock(
                    project=str(values.get("project.name") or ""),
                    engineer=str(values.get("project.engineer") or ""),
                    date=str(values.get("project.date") or ""),
                ),
            )
        )
        st.caption(
            "Belum ada mesh maupun analisis — ini hanya susunan geometrinya. "
            "Tekan **Jalankan analisis** bila sudah sesuai."
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
        runner.perintah(cli_argv),
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
    ringkas = runner.ringkas_kegagalan(lines)
    if ringkas:
        st.error("Masukan ditolak:", icon=":material/error:")
        st.code("\n".join(ringkas))
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
