"""Benchmark local reproduzível, sem rede ou impressora.

python benchmarks/benchmark_rip.py --baseline /tmp/engine-anterior.py --repeat 3
O baseline precisa ser uma cópia de autorip/engine.py compatível com este pacote.
"""
import argparse
import importlib.util
import json
import platform
import statistics
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image, ImageDraw
from autorip import engine
from autorip.config import Settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--baseline-morph", type=Path,
                        help="Copia de autorip/morph.py da mesma versao de base")
    parser.add_argument("--baseline-prt", type=Path,
                        help="Copia de autorip/prt.py da mesma versao de base")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("repeat precisa ser positivo")
    spec = importlib.util.spec_from_file_location("autorip._benchmark_baseline", args.baseline)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if args.baseline_morph:
        morph_spec = importlib.util.spec_from_file_location("autorip._benchmark_morph", args.baseline_morph)
        old_morph = importlib.util.module_from_spec(morph_spec)
        morph_spec.loader.exec_module(old_morph)
        baseline.morph = old_morph
    if args.baseline_prt:
        writer_spec = importlib.util.spec_from_file_location("autorip._benchmark_prt", args.baseline_prt)
        old_prt = importlib.util.module_from_spec(writer_spec)
        writer_spec.loader.exec_module(old_prt)
        baseline.PrtWriter = old_prt.PrtWriter
    settings = Settings(label_enabled=False, margin_top_in=.1, margin_bottom_in=.1)
    old, new = baseline.Rip(settings), engine.Rip(settings)
    alpha = np.zeros((640, 1700), np.float32)
    alpha[30:610, 40:1660] = 1
    alpha[200:230, 300:320] = 0
    alpha[350:400, 800:900] = .5
    result = {"python":platform.python_version(), "platform":platform.platform(),
              "numpy":np.__version__, "repeat":args.repeat,
              "dpi":[settings.dpi_x,settings.dpi_y], "results":{}}
    def record(name, first, second):
        # Alterne a ordem para reduzir o viés de carga/frequência da CPU.
        first(); second()
        samples = [[], []]
        actions = [first, second]
        for iteration in range(args.repeat):
            for index in ((0, 1) if iteration % 2 == 0 else (1, 0)):
                start = time.perf_counter()
                actions[index]()
                samples[index].append(time.perf_counter() - start)
        a, b = map(statistics.median, samples)
        result["results"][name] = {"baseline_seconds":round(a,6),"new_seconds":round(b,6),
                                   "speedup":round(a/b,2),"reduction_percent":round(100*(1-b/a),1)}
        print(json.dumps({name:result["results"][name]}), flush=True)
    values = np.random.default_rng(42).random((512, 1700), dtype=np.float32)
    record("halftone_512x1700", lambda:old._halftone(values,251), lambda:new._halftone(values,251))
    def peak_mib(action):
        tracemalloc.start()
        try:
            action()
            return round(tracemalloc.get_traced_memory()[1] / 1024**2, 2)
        finally:
            tracemalloc.stop()
    result["halftone_peak_mib"] = {"baseline":peak_mib(lambda:old._halftone(values,251)),
                                    "new":peak_mib(lambda:new._halftone(values,251))}
    record("white_640x1700", lambda: old._white_levels(alpha), lambda: new._white_levels(alpha))
    full = np.ones_like(alpha)
    record("white_full_640x1700", lambda:old._white_levels(full), lambda:new._white_levels(full))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"source.png"
        image = Image.new("RGBA", (640,480), (0,0,0,0))
        ImageDraw.Draw(image).rounded_rectangle((20,20,620,460),radius=35,fill=(30,120,210,255))
        image.save(path)
        def process(rip):
            info = rip.process(str(path),str(Path(folder)/"output.PRT"),width_cm=5)
            Path(info["output_path"]).unlink()
        record("rip_5x3.75cm", lambda:process(old),lambda:process(new))
        render_args = (image, 0, 512, 0, 3543, 1417, [])
        result["render_peak_mib"] = {"baseline":peak_mib(lambda:old._render(*render_args)),
                                      "new":peak_mib(lambda:new._render(*render_args))}
        def same_bytes():
            first = baseline.Rip(settings).process(str(path),str(Path(folder)/"reference.PRT"),width_cm=2.54)
            second = engine.Rip(settings).process(str(path),str(Path(folder)/"candidate.PRT"),width_cm=2.54)
            equal = Path(first["output_path"]).read_bytes() == Path(second["output_path"]).read_bytes()
            Path(first["output_path"]).unlink(); Path(second["output_path"]).unlink()
            return equal
        result["unchanged_with_white"] = same_bytes()
        # Permite comparar também bases anteriores à troca da morfologia.
        settings.white_enabled = False
        first = baseline.Rip(settings).process(str(path),str(Path(folder)/"old.PRT"),width_cm=2.54)
        second = engine.Rip(settings).process(str(path),str(Path(folder)/"new.PRT"),width_cm=2.54)
        result["unchanged_without_white"] = Path(first["output_path"]).read_bytes() == Path(second["output_path"]).read_bytes()
    print(json.dumps(result,indent=2),flush=True)


if __name__ == "__main__":
    main()
