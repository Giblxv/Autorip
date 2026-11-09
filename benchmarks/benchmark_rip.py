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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image, ImageDraw
from autorip import engine
from autorip.config import Settings


def median_seconds(action, repeats):
    action()  # aquecimento
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        action()
        samples.append(time.perf_counter() - start)
    return statistics.median(samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--repeat", type=int, default=3)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("repeat precisa ser positivo")
    spec = importlib.util.spec_from_file_location("autorip._benchmark_baseline", args.baseline)
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
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
        a = median_seconds(first, args.repeat)
        b = median_seconds(second, args.repeat)
        result["results"][name] = {"baseline_seconds":round(a,6),"new_seconds":round(b,6),
                                   "speedup":round(a/b,2),"reduction_percent":round(100*(1-b/a),1)}
        print(json.dumps({name:result["results"][name]}), flush=True)
    record("white_640x1700", lambda: old._white_levels(alpha), lambda: new._white_levels(alpha))
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder)/"source.png"
        image = Image.new("RGBA", (640,480), (0,0,0,0))
        ImageDraw.Draw(image).rounded_rectangle((20,20,620,460),radius=35,fill=(30,120,210,255))
        image.save(path)
        def process(rip):
            info = rip.process(str(path),str(Path(folder)/"output.PRT"),width_cm=5)
            Path(info["output_path"]).unlink()
        record("rip_5x3.75cm", lambda:process(old),lambda:process(new))
        # O novo disco muda o branco por intenção; sem branco, a saída deve ser idêntica.
        settings.white_enabled = False
        first = baseline.Rip(settings).process(str(path),str(Path(folder)/"old.PRT"),width_cm=2.54)
        second = engine.Rip(settings).process(str(path),str(Path(folder)/"new.PRT"),width_cm=2.54)
        result["unchanged_without_white"] = Path(first["output_path"]).read_bytes() == Path(second["output_path"]).read_bytes()
    print(json.dumps(result,indent=2),flush=True)


if __name__ == "__main__":
    main()
