"""Benchmarks dos protótipos ProcessPool e GPU, sem alterar o caminho padrão."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from autorip.config import Settings
from autorip.experimental_gpu import distance_transform_edt, status
from autorip.experimental_processpool import process_files
from autorip.morph import _distance


def make_sources(root, count):
    paths = []
    for index in range(count):
        path = root / f"source-{index}.png"
        image = Image.new("RGBA", (1024, 768), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((30, 30, 994, 738), radius=100, fill=(25, 140, 230, 190))
        image.save(path)
        image.close()
        paths.append(path)
    return paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=2)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("count precisa ser positivo")
    result = {"gpu": status(), "processpool": {}}
    mask = np.zeros((512, 768), dtype=bool)
    mask[40:-40, 60:-60] = True
    try:
        started = time.perf_counter()
        gpu = distance_transform_edt(mask, sampling=(1 / 2400, 1 / 720))
        result["gpu"]["elapsed_seconds"] = time.perf_counter() - started
        result["gpu"]["shape"] = list(gpu.shape)
        result["gpu"]["cpu_equivalent_max_error"] = float(np.max(np.abs(gpu - _distance(mask, (1 / 2400, 1 / 720)))))
    except RuntimeError as exc:
        result["gpu"]["available"] = False
        result["gpu"]["error"] = str(exc)
    with tempfile.TemporaryDirectory(prefix="autorip-processpool-bench-") as folder:
        root = Path(folder)
        sources = make_sources(root, args.count)
        settings = Settings(label_enabled=False, offline_mode=True)
        started = time.perf_counter()
        outputs = process_files(sources, settings, root / "out", max_workers=min(args.count, 2))
        result["processpool"] = {
            "count": args.count,
            "elapsed_seconds": time.perf_counter() - started,
            "outputs": outputs,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
