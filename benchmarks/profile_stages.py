"""Perfil aproximado das etapas do RIP, sem rede e sem alterar o produto."""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import PrtWriter


def fixture(path):
    image = Image.new("RGBA", (4096, 3072), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((100, 100, 3996, 2972), radius=450, fill=(25, 140, 230, 190))
    draw.ellipse((1200, 400, 3000, 2200), fill=(240, 55, 110, 90))
    image.save(path)
    image.close()


def run_once(source, output, settings):
    timings = defaultdict(float)
    original = {
        "load": Rip._load_source,
        "prepare": Rip._prepare_resampling,
        "cmyk": Rip._to_cmyk,
        "thresholds": Rip._thresholds,
        "white": Rip._white_levels,
        "render": Rip._render,
        "write": PrtWriter.write_block,
    }

    def timed(name, function):
        def wrapper(*args, **kwargs):
            started = time.perf_counter()
            try:
                return function(*args, **kwargs)
            finally:
                timings[name] += time.perf_counter() - started
        return wrapper

    Rip._load_source = timed("load_source", original["load"])
    Rip._prepare_resampling = staticmethod(timed("prepare_resampling", original["prepare"]))
    Rip._to_cmyk = timed("to_cmyk", original["cmyk"])
    Rip._thresholds = timed("thresholds", original["thresholds"])
    Rip._white_levels = timed("white_morphology", original["white"])
    Rip._render = timed("render_total", original["render"])
    PrtWriter.write_block = timed("prt_write_pack", original["write"])
    try:
        started = time.perf_counter()
        info = Rip(settings).process(str(source), str(output), width_cm=2.54)
        timings["total"] = time.perf_counter() - started
        timings["unattributed"] = max(0.0, timings["total"] - sum(v for k, v in timings.items() if k != "total"))
        return info, dict(timings)
    finally:
        Rip._load_source = original["load"]
        Rip._prepare_resampling = staticmethod(original["prepare"])
        Rip._to_cmyk = original["cmyk"]
        Rip._thresholds = original["thresholds"]
        Rip._white_levels = original["white"]
        Rip._render = original["render"]
        PrtWriter.write_block = original["write"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("repeat precisa ser positivo")
    with tempfile.TemporaryDirectory(prefix="autorip-profile-") as folder:
        root = Path(folder)
        source = root / "profile.png"
        fixture(source)
        settings = Settings(label_enabled=False, offline_mode=True)
        samples = []
        for index in range(args.repeat):
            info, timings = run_once(source, root / f"profile-{index}.PRT", settings)
            samples.append(timings)
            print(json.dumps({"iteration": index + 1, "timings": timings}), flush=True)
        names = sorted({name for sample in samples for name in sample})
        report = {
            "repeat": args.repeat,
            "fixture": {"width": 4096, "height": 3072},
            "median_seconds": {name: statistics.median(sample.get(name, 0.0) for sample in samples) for name in names},
            "samples": samples,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report["median_seconds"], indent=2))


if __name__ == "__main__":
    main()
