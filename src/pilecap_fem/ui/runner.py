"""Menjalankan CLI sebagai proses anak dan mengalirkan lognya. Dipakai KEDUA antarmuka.

Tidak mengimpor streamlit maupun wx. Antarmuka memberi dua callback -- satu per baris log,
satu saat selesai -- dan modul ini tidak tahu apa pun tentang widget. Selain membuatnya dapat
diuji tanpa display, pemisahan itu yang memastikan kelima hal rapuh di bawah hanya punya
SATU salinan:

1. derau tqdm yang harus disaring,
2. batas jumlah baris log yang ditahan,
3. keharusan menguras stdout,
4. aturan bahwa baris `GAGAL:` diangkat ke atas log,
5. perintah proses anak itu sendiri.

Kelimanya pernah hanya ada di `app.py`. Begitu ada antarmuka kedua, salinan keduanya akan
menyimpang -- dan penyimpangan pada butir 4 berarti pengguna melihat belasan baris WARNING
tanpa penyebabnya, yaitu tepat keadaan yang membuat orang menyimpulkan alatnya rusak.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

#: Baris kemajuan tqdm. Ia menulis ulang satu baris memakai `\r`, yang di log bergulir
#: berubah menjadi ratusan baris hampir identik.
PROGRESS_NOISE = re.compile(r"\r|\d+%\||it/s\]|s/it\]")

#: Jumlah baris log terakhir yang ditahan. Run penuh dapat menghasilkan puluhan ribu baris;
#: menahan semuanya membuat antarmuka tersendat tanpa menambah informasi yang dibaca orang.
MAX_LOG_LINES = 400


@dataclass
class Hasil:
    """Hasil satu run: kode keluar, folder hasil, dan log yang sudah disaring."""

    returncode: int = -1
    run_dir: str = ""
    lines: list[str] = field(default_factory=list)


def perintah(cli_argv: list[str]) -> list[str]:
    """Perintah proses anak untuk `pilecap-run`.

    .. rubric:: Satu-satunya tempat yang harus diubah bila paket ini dibekukan

    Bentuk `sys.executable -m <modul>` mengandaikan `sys.executable` adalah interpreter
    Python. Pada bundel beku (PyInstaller dan sejenisnya) ia justru menunjuk ke executable
    aplikasi itu sendiri, sehingga `-m` tidak berarti apa-apa dan proses anak akan membuka
    jendela baru alih-alih menjalankan analisis.

    Pembekuan **belum diverifikasi** untuk paket ini -- openseespy dan gmsh membawa DLL biner
    yang terkenal rewel di-bundle -- jadi tidak ada protokol tebakan yang ditulis di sini.
    Yang dilakukan: memusatkan perintahnya di satu fungsi, agar pekerjaan itu nanti punya
    satu tempat yang jelas dan bukan dua pemanggil `Popen` yang tersebar.
    """
    return [sys.executable, "-m", "pilecap_fem.cli_pilecap_run", *cli_argv]


def ringkas_kegagalan(lines: list[str]) -> list[str] | None:
    """Potongan log mulai dari baris `GAGAL:`, atau `None` bila tidak ada.

    Pesan `PilecapError` sudah ditulis untuk dibaca engineer, jadi ditampilkan apa adanya --
    tetapi HARUS didahulukan: pada masukan dengan override geometri, log diakhiri belasan
    baris WARNING dan penyebab sebenarnya terkubur di bawahnya.
    """
    for i, ln in enumerate(lines):
        if ln.startswith("GAGAL:"):
            return lines[i:]
    return None


def jalankan(
    cli_argv: list[str],
    workdir: Path,
    *,
    pada_baris: Callable[[str], None],
    pada_selesai: Callable[[Hasil], None],
) -> threading.Thread:
    """Jalankan analisis di thread latar; kembalikan thread-nya.

    `pada_baris` dan `pada_selesai` dipanggil DARI thread itu, bukan dari pemanggil. Antarmuka
    grafis wajib membungkusnya sendiri (mis. `wx.CallAfter`) -- modul ini tidak dapat
    melakukannya tanpa tahu toolkit-nya, dan menebaknya akan menyembunyikan syarat itu dari
    pemanggil berikutnya.
    """
    hasil = Hasil()

    def kerja() -> None:
        try:
            proc = subprocess.Popen(
                perintah(cli_argv),
                cwd=str(workdir),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            hasil.lines.append(f"GAGAL: proses anak tidak dapat dijalankan: {exc}")
            pada_baris(hasil.lines[-1])
            pada_selesai(hasil)
            return

        keluaran: list[str] = []

        def kuras_stdout(stream: object) -> None:
            """stdout HARUS ikut dibaca meski isinya sedikit.

            Pipe yang penuh dan tidak pernah dibaca akan menggantungkan proses anak. stdout
            di sini hanya memuat baris `OK -> <run_dir>`, tetapi mengabaikannya tetap
            berisiko.
            """
            for line in stream:  # type: ignore[attr-defined]
                keluaran.append(line.rstrip())

        assert proc.stdout is not None and proc.stderr is not None  # PIPE diminta di atas
        penguras = threading.Thread(target=kuras_stdout, args=(proc.stdout,), daemon=True)
        penguras.start()

        # Log pilecap-fem mengalir ke STDERR (`logging.StreamHandler(stream=sys.stderr)`),
        # sedangkan stdout hanya memuat hasil akhir. Inilah yang di-stream ke layar.
        for line in proc.stderr:
            if PROGRESS_NOISE.search(line):
                continue
            bersih = line.rstrip()
            hasil.lines.append(bersih)
            del hasil.lines[:-MAX_LOG_LINES]
            pada_baris(bersih)

        proc.wait()
        penguras.join(timeout=5)

        for line in keluaran:
            if line.startswith("OK ->"):
                hasil.run_dir = line.split("->", 1)[1].strip()
        hasil.returncode = proc.returncode
        pada_selesai(hasil)

    t = threading.Thread(target=kerja, name="pilecap-run", daemon=True)
    t.start()
    return t


__all__ = [
    "MAX_LOG_LINES",
    "PROGRESS_NOISE",
    "Hasil",
    "jalankan",
    "perintah",
    "ringkas_kegagalan",
]
