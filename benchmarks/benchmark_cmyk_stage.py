"""Mede somente _to_cmyk, com controle A/A e alocacoes fora do cronometro.

python benchmarks/benchmark_cmyk_stage.py --baseline-ref v0.8.39 --pairs 21 --output /tmp/cmyk-stage.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
from autorip import engine
from autorip.config import Settings
from benchmark_main_refinements import baseline, ratio_interval


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--pairs', type=int, default=21)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    report = dict(python=platform.python_version(), numpy=np.__version__, pillow=Image.__version__,
                  platform=platform.platform(), baseline_ref=args.baseline_ref, pairs=args.pairs, scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-cmyk-stage-') as folder:
        old = baseline(args.baseline_ref, Path(folder))
        for width, height in [(32, 32), (1440, 512), (4000, 512)]:
            pixels = np.random.default_rng(4000).integers(0, 256, (height, width, 3), dtype=np.uint8)
            with Image.fromarray(pixels) as rgb:
                for limited in [False, True]:
                    settings = Settings(ink_limit=dict(C=35.5, M=0, Y=88.25, K=100)) if limited else Settings()
                    previous, current = old.Rip(settings), engine.Rip(settings)
                    methods = [previous._to_cmyk, current._to_cmyk, previous._to_cmyk]
                    expected = methods[0](rgb)
                    samples = [[], [], []]
                    for group in range(-1, args.pairs):
                        order = list(range(3))
                        random.Random(group + 4000).shuffle(order)
                        for side in order:
                            start = time.perf_counter()
                            value = methods[side](rgb)
                            elapsed = time.perf_counter() - start
                            np.testing.assert_array_equal(value.view(np.uint32), expected.view(np.uint32))
                            if group >= 0:
                                samples[side].append(elapsed)
                    peaks = []
                    for method in methods:
                        tracemalloc.start()
                        value = method(rgb)
                        peaks.append(tracemalloc.get_traced_memory()[1])
                        tracemalloc.stop()
                        np.testing.assert_array_equal(value.view(np.uint32), expected.view(np.uint32))
                    name = f'{width}x{height}_' + ('limits' if limited else 'unity')
                    result = dict(median_seconds=dict(zip(('baseline', 'candidate', 'control'), map(statistics.median, samples))),
                                  baseline_over_candidate_ci95=ratio_interval(samples[0], samples[1]),
                                  control_over_candidate_ci95=ratio_interval(samples[2], samples[1]),
                                  baseline_over_control_ci95=ratio_interval(samples[0], samples[2]),
                                  traced_peak_bytes=dict(zip(('baseline', 'candidate', 'control'), peaks)),
                                  sha256=hashlib.sha256(memoryview(expected)).hexdigest(), samples=samples)
                    report['scenarios'][name] = result
                    print(name, result['median_seconds'], result['traced_peak_bytes'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
