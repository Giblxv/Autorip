import argparse, os, sys
from .config import Settings
from .engine import Rip
from .watcher import watch, run_once


def main():
    ap = argparse.ArgumentParser(prog="autorip")
    ap.add_argument("--config", default="autorip.json")
    ap.add_argument("--watch", action="store_true", help="modo automatico (hot folder)")
    ap.add_argument("--once", action="store_true", help="processa a hot folder uma vez")
    ap.add_argument("--icc"); ap.add_argument("--width-cm", type=float)
    ap.add_argument("--no-white", action="store_true")
    ap.add_argument("--gui", action="store_true", help="abre o painel")
    ap.add_argument("files", nargs="*", help="arquivos para processar manualmente")
    a = ap.parse_args()
    if a.gui or (not a.files and not a.watch and not a.once):
        from .server import main as gui; return gui()
    s = Settings.load(a.config)
    if a.icc: s.icc_path = a.icc
    if a.no_white: s.white_enabled = False
    if not os.path.exists(a.config): s.save(a.config)
    if a.watch:
        watch(s)
    elif a.once:
        run_once(s, Rip(s))
    else:
        rip = Rip(s)
        for f in a.files:
            out = os.path.join(s.output_folder, os.path.splitext(os.path.basename(f))[0] + ".PRT")
            os.makedirs(s.output_folder, exist_ok=True)
            print(rip.process(f, out, a.width_cm, progress=lambda p: print(f"\r{p*100:5.1f}%", end="")))

if __name__ == "__main__":
    main()
