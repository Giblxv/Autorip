"""Diagnostico instrumentado do controle RGBA, sem substituir os ensaios normais.

python benchmarks/benchmark_rgba_fallback.py --baseline-ref v0.8.35 --repeat 6 --output /tmp/rgba-memory.json
"""
import argparse
import json
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autorip.config import Settings
from benchmark_opaque_lut import fixtures
from benchmark_source_preparation import load, run, rss


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='v0.8.35')
    parser.add_argument('--repeat', type=int, default=6)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--worker-source', type=Path)
    parser.add_argument('--worker-case', type=Path)
    parser.add_argument('--worker-output', type=Path)
    parser.add_argument('--no-trace', action='store_true', help='Medir RSS sem tracemalloc')
    args = parser.parse_args()
    if args.worker_source:
        case = json.loads(args.worker_case.read_text())
        rip = load(args.worker_source, 'rss_probe').Rip(Settings(**case['settings']))
        calls = []
        binary_calls = []
        selection_calls = []
        strip_rgb_calls = []
        if hasattr(rip, '_opaque_color_levels'):
            original = rip._opaque_color_levels
            def tracked(*values):
                calls.append(True)
                return original(*values)
            rip._opaque_color_levels = tracked
        if hasattr(rip, '_binary_white_levels'):
            original_binary = rip._binary_white_levels
            def tracked_binary(*values):
                binary_calls.append(True)
                return original_binary(*values)
            rip._binary_white_levels = tracked_binary
        if hasattr(rip, '_drop_levels'):
            original_selection = rip._drop_levels
            def tracked_selection(*values):
                selection_calls.append(True)
                return original_selection(*values)
            rip._drop_levels = tracked_selection
        if hasattr(rip, '_strip_rgb'):
            original_strip_rgb = rip._strip_rgb
            def tracked_strip_rgb(*values):
                strip_rgb_calls.append(True)
                return original_strip_rgb(*values)
            rip._strip_rgb = tracked_strip_rgb
        original_process = rip.process
        cpu_samples = []
        def timed_process(*values, **options):
            start = time.process_time()
            try:
                return original_process(*values, **options)
            finally:
                cpu_samples.append(time.process_time() - start)
        rip.process = timed_process
        if not args.no_trace:
            tracemalloc.start()
        elapsed, digest, info = run(rip, case, args.worker_output)
        peak = None if args.no_trace else tracemalloc.get_traced_memory()[1]
        if not args.no_trace:
            tracemalloc.stop()
        print(json.dumps(dict(rss_mib=rss(), elapsed_seconds=elapsed, process_cpu_seconds=cpu_samples[0],
                              traced_peak_bytes=peak, sha256=digest,
                              metadata=info, lookup_calls=len(calls),
                              binary_white_calls=len(binary_calls),
                              drop_selection_calls=len(selection_calls),
                              strip_rgb_calls=len(strip_rgb_calls),
                              ranks_cached=getattr(rip, '_opaque_ranks', None) is not None)))
        return
    if args.repeat < 1 or args.output is None:
        parser.error('Use --output e um repeat positivo')
    with tempfile.TemporaryDirectory(prefix='autorip-rgba-probe-') as folder:
        root = Path(folder)
        case = next(case for case in fixtures(root) if case['name'] == 'rgba_control')
        case_path = root / 'case.json'
        case_path.write_text(json.dumps(case))
        old = subprocess.check_output(['git', 'show', f'{args.baseline_ref}:autorip/engine.py'], cwd=ROOT)
        baseline = root / 'baseline.py'
        baseline.write_bytes(old)
        sources = [baseline, ROOT / 'autorip/engine.py', baseline]
        results = [[], [], []]
        expected = None
        for group in range(args.repeat):
            order = list(range(3))
            random.Random(group + 73).shuffle(order)
            for side in order:
                value = json.loads(subprocess.check_output([
                    sys.executable, str(Path(__file__).resolve()), '--worker-source', str(sources[side]),
                    '--worker-case', str(case_path), '--worker-output', str(root / 'out.PRT'),
                    *(['--no-trace'] if args.no_trace else [])], text=True))
                assert value['lookup_calls'] == 0 and not value['ranks_cached']
                assert value['binary_white_calls'] == 0
                signature = value['sha256'], value['metadata']
                if expected is None:
                    expected = signature
                assert signature == expected
                results[side].append(value)
        report = {key:dict(rss_median_mib=statistics.median(value['rss_mib'] for value in values),
                           elapsed_median_seconds=statistics.median(value['elapsed_seconds'] for value in values),
                           traced_median_bytes=(None if args.no_trace else statistics.median(value['traced_peak_bytes'] for value in values)),
                           samples=values) for key, values in zip(('baseline', 'candidate', 'control'), results)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
