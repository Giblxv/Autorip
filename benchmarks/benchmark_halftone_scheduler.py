"""Benchmarks experimentais de halftone/packing e scheduler de tiras.

Uso:
  python benchmarks/benchmark_halftone_scheduler.py --mode all --repeat 3

O benchmark nunca altera o caminho de produção: apenas compara funções locais e
monkeypatches temporariamente os limites do scheduler durante cada RIP.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import statistics
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

# Permite executar o arquivo diretamente a partir da raiz do checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import pack2, plane_bytes_for


def fused_halftone_pack2(values, thresholds, ratio, plane_bytes):
    """Calcula níveis e packing 2-bit sem materializar a matriz de níveis."""
    values = np.asarray(values, dtype=np.float32)
    thresholds = np.asarray(thresholds, dtype=np.float32)
    rows, dots = values.shape
    full = plane_bytes * 4
    if dots < full:
        values = np.pad(values, ((0, 0), (0, full - dots)))
        thresholds = np.pad(thresholds, ((0, 0), (0, full - dots)))
    small = (values / ratio) > thresholds
    large = ((values - ratio) / (1.0 - ratio)) > thresholds
    levels = np.where(large, np.uint8(3), small.astype(np.uint8))
    grouped = levels.reshape(rows, plane_bytes, 4)
    return (grouped[..., 0] << 6) | (grouped[..., 1] << 4) | (grouped[..., 2] << 2) | grouped[..., 3]


def benchmark_fusion(repeat):
    rng = np.random.default_rng(44)
    rows, dots = 1024, 4096
    values = rng.random((rows, dots), dtype=np.float32)
    thresholds = rng.random((rows, dots), dtype=np.float32)
    ratio = 0.4
    pb = plane_bytes_for(dots)
    baseline_times, candidate_times = [], []
    baseline_out = candidate_out = None
    for _ in range(repeat):
        t = time.perf_counter()
        levels = np.where(((values - ratio) / (1.0 - ratio)) > thresholds,
                          np.uint8(3), ((values / ratio) > thresholds).astype(np.uint8))
        baseline_out = pack2(levels, pb)
        baseline_times.append(time.perf_counter() - t)
        t = time.perf_counter()
        candidate_out = fused_halftone_pack2(values, thresholds, ratio, pb)
        candidate_times.append(time.perf_counter() - t)
    return {
        "rows": rows, "dots": dots, "repeat": repeat,
        "baseline_median_seconds": statistics.median(baseline_times),
        "fused_median_seconds": statistics.median(candidate_times),
        "speedup": statistics.median(baseline_times) / statistics.median(candidate_times),
        "byte_identical": bool(np.array_equal(baseline_out, candidate_out)),
        "baseline_sha256": hashlib.sha256(baseline_out.tobytes()).hexdigest(),
        "fused_sha256": hashlib.sha256(candidate_out.tobytes()).hexdigest(),
    }


def _fixture(path):
    rng = np.random.default_rng(2026)
    pixels = rng.integers(0, 256, (1000, 1000, 4), dtype=np.uint8)
    Image.fromarray(pixels, "RGBA").save(path)


def benchmark_scheduler(repeat):
    results = []
    old_workers, old_strip = engine.RENDER_WORKERS_MAX, engine.STRIP
    try:
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / "scheduler.png"
            _fixture(source)
            settings = Settings(dpi_x=720, dpi_y=2400, margin_top_in=0,
                                margin_bottom_in=0, label_enabled=False,
                                white_enabled=False)
            for workers in (1, 2, 4):
                for strip in (256, 512, 1024):
                    times = []
                    hashes = []
                    for index in range(repeat):
                        engine.RENDER_WORKERS_MAX = workers
                        engine.STRIP = strip
                        destination = directory / f"w{workers}-s{strip}-{index}.PRT"
                        started = time.perf_counter()
                        Rip(settings).process(str(source), str(destination), width_cm=5.08)
                        times.append(time.perf_counter() - started)
                        hashes.append(hashlib.sha256(destination.read_bytes()).hexdigest())
                    results.append({
                        "workers": workers, "strip_rows": strip, "repeat": repeat,
                        "median_seconds": statistics.median(times),
                        "min_seconds": min(times), "max_seconds": max(times),
                        "byte_identical": len(set(hashes)) == 1,
                        "sha256": hashes[0],
                    })
    finally:
        engine.RENDER_WORKERS_MAX, engine.STRIP = old_workers, old_strip
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("fusion", "scheduler", "all"), default="all")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = {}
    if args.mode in ("fusion", "all"):
        result["fusion"] = benchmark_fusion(args.repeat)
    if args.mode in ("scheduler", "all"):
        result["scheduler"] = benchmark_scheduler(args.repeat)
    text = json.dumps(result, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
