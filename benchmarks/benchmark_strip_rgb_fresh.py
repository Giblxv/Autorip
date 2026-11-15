"""Confirma extracao RGB em processos novos: tempo, CPU, RSS e controles A/A.

python benchmarks/benchmark_strip_rgb_fresh.py --baseline-ref v0.8.40 --pairs 11 --output /tmp/strip-rgb-fresh.json
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

from benchmark_cmyk_direct import fixtures
from benchmark_main_refinements import ratio_interval

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--pairs', type=int, default=11)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    old = subprocess.check_output(['git', 'show', f'{args.baseline_ref}:autorip/engine.py'], cwd=ROOT)
    current = ROOT / 'autorip/engine.py'
    report = dict(baseline_ref=args.baseline_ref, python=platform.python_version(), pairs=args.pairs,
                  source_sha256=dict(baseline=hashlib.sha256(old).hexdigest(),
                                     candidate=hashlib.sha256(current.read_bytes()).hexdigest()), scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-strip-fresh-') as folder:
        root = Path(folder)
        previous = root / 'previous.py'
        previous.write_bytes(old)
        for case in fixtures(root):
            if case['name'] not in {'rgba_identity', 'rgba_wide', 'rgba_scaled_white', 'large_rgb_control'}:
                continue
            case_path = root / 'case.json'
            case_path.write_text(json.dumps(case))
            samples = [[], [], []]
            expected = None
            for group in range(args.pairs):
                order = list(range(3))
                random.Random(group + 4100).shuffle(order)
                for side in order:
                    value = json.loads(subprocess.check_output([
                        sys.executable, str(ROOT / 'benchmarks/benchmark_rgba_fallback.py'),
                        '--worker-source', str(current if side == 1 else previous), '--worker-case', str(case_path),
                        '--worker-output', str(root / 'out.PRT'), '--no-trace'], text=True))
                    signature = value['sha256'], value['metadata']
                    if expected is None:
                        expected = signature
                    assert signature == expected
                    active = side == 1 and case['name'] != 'large_rgb_control'
                    assert value['strip_rgb_calls'] > 0 if active else value['strip_rgb_calls'] == 0
                    samples[side].append(value)
            result = dict(sha256=expected[0], metadata=expected[1], samples=samples)
            for field in ('elapsed_seconds', 'process_cpu_seconds', 'rss_mib'):
                values = [[value[field] for value in group] for group in samples]
                result[field] = dict(median=dict(zip(('baseline', 'candidate', 'control'), map(statistics.median, values))))
                if field != 'rss_mib':
                    result[field].update(baseline_over_candidate_ci95=ratio_interval(values[0], values[1]),
                                         control_over_candidate_ci95=ratio_interval(values[2], values[1]),
                                         baseline_over_control_ci95=ratio_interval(values[0], values[2]))
            report['scenarios'][case['name']] = result
            print(case['name'], {name: value for name, value in result.items() if name != 'samples'}, flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
