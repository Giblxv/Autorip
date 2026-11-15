"""Confirma os casos largos com branco em processos novos, com controle A/A.

python benchmarks/benchmark_white_fresh.py --baseline-ref v0.8.37 --pairs 7 --output /tmp/white-fresh.json
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
import tempfile

from benchmark_opaque_white import fixtures
from benchmark_main_refinements import ratio_interval

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--pairs', type=int, default=7)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    old = subprocess.check_output(['git', 'show', f'{args.baseline_ref}:autorip/engine.py'], cwd=ROOT)
    current = ROOT / 'autorip/engine.py'
    report = dict(baseline_ref=subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip(),
                  python=platform.python_version(), pairs=args.pairs, tracing_enabled=False,
                  source_sha256=dict(baseline=hashlib.sha256(old).hexdigest(),
                                     candidate=hashlib.sha256(current.read_bytes()).hexdigest()), scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-white-fresh-') as folder:
        root = Path(folder)
        previous = root / 'previous.py'
        previous.write_bytes(old)
        for case in fixtures(root):
            if case['name'] not in {'rgb_wide_white', 'rgb_wide_white_45'}:
                continue
            path = root / 'case.json'
            path.write_text(json.dumps(case))
            samples = [[], [], []]
            expected = None
            for group in range(args.pairs):
                order = list(range(3))
                random.Random(8800 + group).shuffle(order)
                for side in order:
                    value = json.loads(subprocess.check_output([
                        sys.executable, str(ROOT / 'benchmarks/benchmark_rgba_fallback.py'),
                        '--worker-source', str(current if side == 1 else previous),
                        '--worker-case', str(path), '--worker-output', str(root / 'out.PRT'), '--no-trace'], text=True))
                    signature = value['sha256'], value['metadata']
                    if expected is None:
                        expected = signature
                    assert signature == expected
                    assert value['lookup_calls'] > 0 and value['ranks_cached']
                    assert value['binary_white_calls'] > 0 if side == 1 else value['binary_white_calls'] == 0
                    samples[side].append(value)
            times = [[value['elapsed_seconds'] for value in side] for side in samples]
            result = dict(median_seconds=dict(zip(('baseline', 'candidate', 'control'), map(statistics.median, times))),
                          baseline_over_candidate_ci95=ratio_interval(times[0], times[1]),
                          control_over_candidate_ci95=ratio_interval(times[2], times[1]),
                          baseline_over_control_ci95=ratio_interval(times[0], times[2]),
                          rss_median_mib=dict(zip(('baseline', 'candidate', 'control'),
                                                 [statistics.median(value['rss_mib'] for value in side) for side in samples])),
                          sha256=expected[0], metadata=expected[1], samples=samples)
            report['scenarios'][case['name']] = result
            print(json.dumps(dict(case=case['name'], **{key: val for key, val in result.items() if key != 'samples'})), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
