"""Mede a extracao RGB de uma tira RGBA; nao representa o RIP completo.

python benchmarks/benchmark_strip_rgb.py --baseline-ref v0.8.40 --pairs 21 --output /tmp/strip-rgb.json
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
from autorip.engine import Rip
from benchmark_main_refinements import ratio_interval


def original(strip, arr):
    return Image.fromarray(arr[..., :3], 'RGB')


def native(strip, arr):
    return Rip._strip_rgb(strip)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--pairs', type=int, default=21)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    old_source = subprocess.check_output(['git', 'show', f'{args.baseline_ref}:autorip/engine.py'], cwd=ROOT)
    assert b'rgb = strip if opaque else Image.fromarray(arr[..., :3], "RGB")' in old_source
    report = dict(baseline_ref=args.baseline_ref, python=platform.python_version(), numpy=np.__version__,
                  pillow=Image.__version__, platform=platform.platform(), pairs=args.pairs,
                  source_sha256=dict(baseline=hashlib.sha256(old_source).hexdigest(),
                                     candidate=hashlib.sha256((ROOT / 'autorip/engine.py').read_bytes()).hexdigest()), scenarios={})
    for height, width in [(32, 32), (512, 1440), (512, 4000)]:
        pixels = np.random.default_rng(4100).integers(0, 256, (height, width, 4), dtype=np.uint8)
        with Image.fromarray(pixels) as strip:
            strip.info.update(icc_profile=b'profile marker', dpi=(300, 150))
            arr = np.asarray(strip)
            with original(strip, arr) as first:
                expected = first.tobytes()
            methods = [original, native, original]
            samples = [[], [], []]
            for group in range(-1, args.pairs):
                order = list(range(3))
                random.Random(group + 4100).shuffle(order)
                for side in order:
                    start = time.perf_counter()
                    value = methods[side](strip, arr)
                    elapsed = time.perf_counter() - start
                    try:
                        assert value.tobytes() == expected and value.info == {}
                    finally:
                        value.close()
                    if group >= 0:
                        samples[side].append(elapsed)
            peaks = []
            for method in methods:
                tracemalloc.start()
                value = method(strip, arr)
                peaks.append(tracemalloc.get_traced_memory()[1])
                tracemalloc.stop()
                value.close()
            result = dict(median_seconds=dict(zip(('baseline', 'candidate', 'control'), map(statistics.median, samples))),
                          baseline_over_candidate_ci95=ratio_interval(samples[0], samples[1]),
                          control_over_candidate_ci95=ratio_interval(samples[2], samples[1]),
                          baseline_over_control_ci95=ratio_interval(samples[0], samples[2]),
                          traced_peak_bytes=dict(zip(('baseline', 'candidate', 'control'), peaks)),
                          packed_rgb_bytes_avoided=height * width * 3,
                          sha256=hashlib.sha256(expected).hexdigest(), samples=samples)
            name = f'{width}x{height}'
            report['scenarios'][name] = result
            print(name, result['median_seconds'], result['traced_peak_bytes'], flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
