"""Modo automatico: observa a hot folder, processa cada PNG e grava o .PRT na pasta de saida."""
import os, shutil, time, traceback
from .config import Settings
from .engine import Rip

EXTS = (".png", ".tif", ".tiff", ".jpg", ".jpeg")


def _stable(path, wait=1.0):
    try:
        a = os.path.getsize(path); time.sleep(wait); return a == os.path.getsize(path) and a > 0
    except OSError:
        return False


def run_once(s: Settings, rip: Rip, log=print):
    for d in (s.hot_folder, s.output_folder, s.done_folder, s.error_folder):
        os.makedirs(d, exist_ok=True)
    n = 0
    for name in sorted(os.listdir(s.hot_folder)):
        if not name.lower().endswith(EXTS):
            continue
        src = os.path.join(s.hot_folder, name)
        if not _stable(src):
            continue
        out = os.path.join(s.output_folder, os.path.splitext(name)[0] + ".PRT")
        try:
            log(f"[RIP] {name} ...")
            info = rip.process(src, out)
            shutil.move(src, os.path.join(s.done_folder, name))
            log(f"[OK ] {out}  {info['width_cm']:.2f}x{info['height_cm']:.2f} cm")
            n += 1
        except Exception:
            log(f"[ERRO] {name}\n{traceback.format_exc()}")
            shutil.move(src, os.path.join(s.error_folder, name))
    return n


def watch(s: Settings, log=print, stop=lambda: False):
    rip = Rip(s)
    log(f"Observando: {os.path.abspath(s.hot_folder)}")
    while not stop():
        run_once(s, rip, log)
        time.sleep(s.poll_seconds)
