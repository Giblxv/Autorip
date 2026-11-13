"""Benchmark pareado da descompactação PRT (sem impressora).

    python benchmarks/benchmark_prt_unpack.py --pairs 15

Compara apenas unpack2() e controla a variação usando baseline/baseline.
Os números não representam velocidade de RIP, impressão ou end-to-end.
"""
import argparse
import json
import platform
import statistics
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autorip.prt import unpack2


def baseline(packed, n_dots):
    d = np.stack([(packed >> 6) & 3, (packed >> 4) & 3,
                  (packed >> 2) & 3, packed & 3], axis=-1)
    return d.reshape(packed.shape[0], -1)[:, :n_dots]


def paired(a, b, packed, n_dots, pairs):
    old = a(packed, n_dots)
    new = b(packed, n_dots)
    if old.dtype != new.dtype or not np.array_equal(old, new):
        raise RuntimeError("Descompactação não é bit a bit equivalente.")
    elapsed = [[], []]
    functions = (a, b)
    # Alternar ordem a cada par reduz o viés da frequência da CPU.
    for iteration in range(pairs):
        for idx in ((0, 1) if iteration % 2 == 0 else (1, 0)):
            start = time.perf_counter()
            output = functions[idx](packed, n_dots)
            elapsed[idx].append(time.perf_counter() - start)
            del output
    ref, candidate = [statistics.median(samples) for samples in elapsed]
    return {
        "baseline_ms": round(ref * 1000, 4),
        "candidate_ms": round(candidate * 1000, 4),
        "speedup": round(ref / candidate, 4),
        "pairs": pairs,
        "candidate_faster_pairs": sum(y < x for x, y in zip(*elapsed)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pairs", type=int, default=15)
    args = parser.parse_args()
    if args.pairs < 1:
        parser.error("pairs precisa ser positivo")
    rng = np.random.default_rng(90210)
    report = {
        "python": platform.python_version(), "numpy": np.__version__,
        "platform": platform.platform(), "pairs": args.pairs, "scenarios": {},
    }
    for name, shape in (("small", (100, 1024)), ("medium", (1000, 1024)),
                        ("wide", (8000, 1024))):
        packed = rng.integers(0, 256, shape, dtype=np.uint8)
        n_dots = shape[1] * 4 - 3
        # Aquecer os dois caminhos antes das medidas.
        baseline(packed, n_dots)
        unpack2(packed, n_dots)
        report["scenarios"][name] = {
            "AB": paired(baseline, unpack2, packed, n_dots, args.pairs),
            "AA_control": paired(baseline, baseline, packed, n_dots, args.pairs),
        }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
