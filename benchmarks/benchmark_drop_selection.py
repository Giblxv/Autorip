"""Mede somente a selecao dos niveis; nao representa o RIP completo.

python benchmarks/benchmark_drop_selection.py --pairs 21 --output /tmp/drop-levels.json
"""
import argparse
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from autorip.engine import Rip
from benchmark_main_refinements import ratio_interval


def original(small, large):
    return np.where(large, np.uint8(3), small.astype(np.uint8))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pairs', type=int, default=21)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    report = dict(python=platform.python_version(), numpy=np.__version__, platform=platform.platform(),
                  pairs=args.pairs, scenarios={})
    rng = np.random.default_rng(3903)
    for shape in [(32, 32), (512, 1440), (512, 4000)]:
        for pattern in ('mixed', 'empty', 'full'):
            small = rng.random(shape) > .35
            large = (rng.random(shape) > .65) if pattern == 'mixed' else np.full(shape, pattern == 'full')
            expected = original(small, large)
            functions = [original, Rip._drop_levels, original]
            samples = [[], [], []]
            for group in range(-1, args.pairs):
                order = list(range(3))
                random.Random(3903 + group).shuffle(order)
                for side in order:
                    start = time.perf_counter()
                    value = functions[side](small, large)
                    elapsed = time.perf_counter() - start
                    np.testing.assert_array_equal(value, expected)
                    if group >= 0:
                        samples[side].append(elapsed)
            peaks = []
            for function in functions:
                tracemalloc.start()
                value = function(small, large)
                peaks.append(tracemalloc.get_traced_memory()[1])
                tracemalloc.stop()
                np.testing.assert_array_equal(value, expected)
            result = dict(shape=shape, pattern=pattern, median_seconds=dict(zip(('baseline', 'candidate', 'control'),
                                                                                  map(statistics.median, samples))),
                          baseline_over_candidate_ci95=ratio_interval(samples[0], samples[1]),
                          control_over_candidate_ci95=ratio_interval(samples[2], samples[1]),
                          baseline_over_control_ci95=ratio_interval(samples[0], samples[2]),
                          traced_peak_bytes=dict(zip(('baseline', 'candidate', 'control'), peaks)), samples=samples)
            name = f'{shape[0]}x{shape[1]}_{pattern}'
            report['scenarios'][name] = result
            print(name, result['median_seconds'], result['traced_peak_bytes'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
