"""Compara variantes vetorizadas do pós-processamento EDT.

Nenhuma variante altera o motor; o script serve para reproduzir a auditoria SIMD.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np
from scipy import ndimage as ndi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autorip.morph import _distance  # noqa: E402


def current(mask, sampling):
    return _distance(mask, sampling)


def scipy_direct(mask, sampling):
    return ndi.distance_transform_edt(mask, sampling=sampling)


def hypot(mask, sampling):
    indices = ndi.distance_transform_edt(mask, sampling=sampling,
                                         return_distances=False,
                                         return_indices=True)
    indices[0] -= np.arange(mask.shape[0], dtype=np.int32)[:, None]
    indices[1] -= np.arange(mask.shape[1], dtype=np.int32)[None, :]
    y = indices[0].astype(np.float64)
    x = indices[1].astype(np.float64)
    y *= sampling[0]
    x *= sampling[1]
    return np.hypot(y, x)


def hypot32(mask, sampling):
    indices = ndi.distance_transform_edt(mask, sampling=sampling,
                                         return_distances=False,
                                         return_indices=True)
    indices[0] -= np.arange(mask.shape[0], dtype=np.int32)[:, None]
    indices[1] -= np.arange(mask.shape[1], dtype=np.int32)[None, :]
    y = indices[0].astype(np.float32)
    x = indices[1].astype(np.float32)
    y *= np.float32(sampling[0])
    x *= np.float32(sampling[1])
    return np.hypot(y, x)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("repeat precisa ser positivo")
    rng = np.random.default_rng(7)
    mask = rng.random((1400, 2200)) > 0.55
    sampling = (1 / 2400, 1 / 720)
    reference = current(mask, sampling)
    report = {"shape": list(mask.shape), "repeat": args.repeat, "variants": {}}
    for name, function in (("current", current), ("scipy_direct", scipy_direct),
                           ("hypot", hypot), ("hypot32", hypot32)):
        samples = []
        peaks = []
        output = None
        for _ in range(args.repeat):
            tracemalloc.start()
            started = time.perf_counter()
            output = function(mask, sampling)
            samples.append(time.perf_counter() - started)
            _, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            peaks.append(peak / 1024 / 1024)
        report["variants"][name] = {
            "median_seconds": statistics.median(samples),
            "samples_seconds": samples,
            "median_peak_mib": statistics.median(peaks),
            "dtype": str(output.dtype),
            "max_abs_error": float(np.max(np.abs(output - reference))),
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
