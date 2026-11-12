"""Compare deterministic sheet planning in fresh workers with explicit sources."""
import argparse
from dataclasses import asdict
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autorip.layout import LayoutItem, layout_to_svg


def fixture(count, seed, pattern='random'):
    rng = random.Random(seed)
    return [LayoutItem(str(i), f'art-{i}.png', f'/synthetic/art-{i}.png',
                       100, 200, 6.0 if pattern=='repeated' else rng.uniform(1, 15),
                       4.0 if pattern=='repeated' else rng.uniform(1, 20),
                       rotation=0 if pattern=='repeated' else (i % 4) * 90, selected=i % 3 == 0)
            for i in range(count)]


def load(path):
    spec = importlib.util.spec_from_file_location('autorip._measured_sheet', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def checksum(output):
    payload = json.dumps([asdict(x) for x in output], sort_keys=True)
    return hashlib.sha256((payload + layout_to_svg(output)).encode()).hexdigest()


def worker(args):
    module = load(args.source)
    items = fixture(args.count, args.seed, args.pattern)
    before = [asdict(x) for x in items]
    def run():
        return module.nest(items, allow_rotation=True)
    first = run()
    assert module.check_layout(first)
    expected = checksum(first)
    samples = []
    for _ in range(args.repeats):
        start = time.perf_counter()
        output = run()
        samples.append(time.perf_counter() - start)
        assert checksum(output) == expected
    peak = None
    if not args.skip_memory:
        tracemalloc.start()
        output = run()
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert checksum(output) == expected
    assert [asdict(x) for x in items] == before
    print(json.dumps(dict(seconds=samples, median=statistics.median(samples),
                          peak_bytes=peak, result_sha256=expected,
                          source_sha256=hashlib.sha256(args.source.read_bytes()).hexdigest())))


def summarize(cases):
    import numpy as np
    rng = np.random.default_rng(20261112)
    result = {}
    for name, pairs in cases.items():
        old = [p['baseline']['median'] for p in pairs]
        new = [p['candidate']['median'] for p in pairs]
        ratio = np.asarray(old) / np.asarray(new)
        bootstrap = np.median(ratio[rng.integers(0, len(ratio), (5000, len(ratio)))], axis=1)
        result[name] = dict(baseline_seconds=statistics.median(old),
                            candidate_seconds=statistics.median(new),
                            speedup=statistics.median(old) / statistics.median(new),
                            bootstrap_95=[float(x) for x in np.percentile(bootstrap, [2.5, 97.5])])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pairs', type=int, default=3)
    parser.add_argument('--counts', type=int, nargs='+', default=[0, 1, 8, 40, 120])
    parser.add_argument('--seed', type=int, default=20261112)
    parser.add_argument('--aa', action='store_true')
    parser.add_argument('--skip-memory', action='store_true')
    parser.add_argument('--pattern',choices=['random','repeated'],default='random')
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--source', type=Path)
    parser.add_argument('--count', type=int)
    parser.add_argument('--repeats', type=int)
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    assert args.pairs > 0 and args.baseline and args.candidate and args.output
    paths = dict(baseline=args.baseline.resolve(),
                 candidate=(args.baseline if args.aa else args.candidate).resolve())
    report = dict(complete=False, aa_control=args.aa, pairs=args.pairs,pattern=args.pattern,
                  driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  cases={}, sources={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in paths.items()},
                  memory_metric='tracemalloc, excludes some native allocations',
                  cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,'sched_getaffinity') else None)
    rng = random.Random(args.seed)
    for count in args.counts:
        pairs = report['cases'][str(count)] = []
        for trial in range(args.pairs):
            order = list(paths)
            rng.shuffle(order)
            record = dict(trial=trial, order=order)
            for side in order:
                command = [sys.executable, __file__, '--worker', '--source', str(paths[side]),
                           '--count', str(count), '--seed', str(args.seed + count),
                           '--pattern',args.pattern,
                           '--repeats', '32' if count <= 8 else '5']
                if args.skip_memory:
                    command.append('--skip-memory')
                run = subprocess.run(command, text=True, capture_output=True, check=True)
                value = json.loads(run.stdout)
                assert value['source_sha256'] == report['sources'][side]
                record[side] = value
            assert record['baseline']['result_sha256'] == record['candidate']['result_sha256']
            pairs.append(record)
            print(json.dumps(dict(count=count, trial=trial+1, identical=True)), flush=True)
    report.update(complete=True, summary=summarize(report['cases']))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['summary'], indent=2))


if __name__ == '__main__':
    main()
