"""Confirma mudanças de retícula em workers novos, com PRTs e fontes conferidos."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.util
from importlib.metadata import version
import json
import math
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import time

import numpy as np
from rip_campaign import FILES, ROOT, digest, make_cases
from autorip.config import Settings


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def load_modules(folder):
    modules = {}
    for key in ('prt', 'morph', 'engine'):
        path = folder / (key + '.py')
        spec = importlib.util.spec_from_file_location('autorip._fresh_' + key, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules[key] = module
    modules['engine'].PrtWriter = modules['prt'].PrtWriter
    modules['engine'].morph = modules['morph']
    return modules


def affinity():
    return sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None


def rss():
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmHWM:'):
                return int(line.split()[1]) / 1024
    except OSError:
        return None


def check_deadline(deadline):
    if deadline and time.time() >= deadline:
        raise TimeoutError('Prazo absoluto da investigação atingido')


def worker(args):
    case = json.loads(args.case.read_text())
    modules = load_modules(args.module_dir)
    assert sha(case['path']) == case['source_sha256']
    if case.get('cpu_limit'):
        limit = case['cpu_limit']
        os.cpu_count = lambda: limit
    rip = modules['engine'].Rip(Settings(**case['settings']))
    with tempfile.TemporaryDirectory(prefix='worker-', dir=args.output_root) as folder:
        check_deadline(args.deadline_timestamp)
        wall = time.perf_counter()
        cpu = time.process_time()
        result = rip.process(case['path'], str(Path(folder) / 'output.PRT'),
                             width_cm=case['width'],
                             control=lambda: check_deadline(args.deadline_timestamp))
        seconds = time.perf_counter() - wall
        cpu_seconds = time.process_time() - cpu
        peak = rss()  # Antes de ler o resultado para conferir os hashes.
        path = Path(result.pop('output_path'))
        outputs = dict(prt_sha256=sha(path), metadata=result, bytes=path.stat().st_size)
        assert sha(case['path']) == case['source_sha256']
    print(json.dumps(dict(seconds=seconds, cpu_seconds=cpu_seconds,
                          peak_rss_mib=peak, outputs=outputs, cpu_affinity=affinity(),
                          source_sha256=case['source_sha256'])))


def summarize(scenarios, seed):
    rng = np.random.default_rng(seed)
    paired_logs = []
    stats = {}
    for name, data in scenarios.items():
        old, new = data['samples']
        x = np.asarray([v['seconds'] for v in old])
        y = np.asarray([v['seconds'] for v in new])
        ratios = x / y
        resampled = ratios[rng.integers(0, len(ratios), (5000, len(ratios)))]
        bounds = np.percentile(np.median(resampled, axis=1), [2.5, 97.5])
        stats[name] = dict(baseline_seconds=statistics.median(x),
                           candidate_seconds=statistics.median(y),
                           speedup=statistics.median(x) / statistics.median(y),
                           paired_median_speedup=float(np.median(ratios)),
                           bootstrap_95_low=float(bounds[0]) if len(ratios) >= 5 else None,
                           bootstrap_95_high=float(bounds[1]) if len(ratios) >= 5 else None,
                           peak_rss_mib=[statistics.median(s['peak_rss_mib'] for s in group)
                                         if all(s['peak_rss_mib'] is not None for s in group) else None
                                         for group in (old, new)])
        paired_logs.append(np.log(ratios))
    combined = np.exp(np.mean(paired_logs, axis=0))
    bounds = np.percentile(np.median(combined[rng.integers(0, len(combined), (5000, len(combined)))], axis=1), [2.5, 97.5])
    return dict(geomean_speedup=math.exp(statistics.mean(math.log(v['speedup']) for v in stats.values())),
                bootstrap_95_low=float(bounds[0]) if len(combined) >= 5 else None,
                bootstrap_95_high=float(bounds[1]) if len(combined) >= 5 else None,
                scenarios=stats)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-dir', type=Path)
    parser.add_argument('--candidate-dir', type=Path)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--icc', type=Path)
    parser.add_argument('--pairs', type=int, default=21)
    parser.add_argument('--seed', type=int, default=20261111)
    parser.add_argument('--aa', action='store_true')
    parser.add_argument('--only', nargs='*')
    parser.add_argument('--deadline', help='ISO8601 absoluto com fuso')
    parser.add_argument('--trial-worker', action='store_true')
    parser.add_argument('--module-dir', type=Path)
    parser.add_argument('--case', type=Path)
    parser.add_argument('--output-root', type=Path)
    args = parser.parse_args()
    args.deadline_timestamp = None
    if args.deadline:
        value = datetime.fromisoformat(args.deadline)
        if value.tzinfo is None:
            parser.error('O prazo precisa incluir fuso')
        args.deadline_timestamp = value.timestamp()
        check_deadline(args.deadline_timestamp)
    if args.trial_worker:
        worker(args)
        return
    if not all((args.baseline_dir, args.candidate_dir, args.work_dir, args.icc)) or args.pairs < 1:
        parser.error('Informe os módulos dos dois lados, pasta nova, ICC e pares positivos')
    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    output_root = work / 'outputs'; output_root.mkdir()
    snapshots = []
    for label, folder in [('baseline', args.baseline_dir), ('candidate', args.baseline_dir if args.aa else args.candidate_dir)]:
        bundle = {key: (folder / (key + '.py')).read_text() for key in FILES}
        destination = work / label; destination.mkdir()
        for key, source in bundle.items():
            (destination / (key + '.py')).write_text(source)
        snapshots.append(dict(path=destination, source_hash=digest(bundle)))
    fixture_dir = work / 'fixtures'; fixture_dir.mkdir()
    all_cases = [c for c in make_cases(fixture_dir, str(args.icc.resolve()), 'large-io-v2') if c['timed']]
    cases = [c for c in all_cases if not args.only or c['name'] in args.only]
    if not cases or (args.only and set(args.only) - {c['name'] for c in cases}):
        parser.error('Seleção de cenários vazia ou desconhecida')
    rng = random.Random(args.seed)
    rng.shuffle(cases)
    report = dict(complete=False, started_at_utc=datetime.now(timezone.utc).isoformat(),
                  deadline=args.deadline, pairs=args.pairs, seed=args.seed, aa_control=args.aa,
                  full_timed_corpus=len(cases) == len(all_cases),
                  eligible_for_decision=args.pairs >= 15 and len(cases) == len(all_cases),
                  python=platform.python_version(), platform=platform.platform(),
                  dependencies={name: version(name) for name in ('pillow', 'numpy', 'scipy')},
                  cpu_affinity=affinity(), benchmark_sha256=sha(__file__), icc_sha256=sha(args.icc),
                  source_hashes=[s['source_hash'] for s in snapshots],
                  common_module_sha256={name: sha(ROOT / 'autorip' / (name + '.py')) for name in ('config', 'imaging', 'paths')},
                  scope='Fresh worker, first Rip.process per Rip; imports/init/hash checks excluded; no preview/upload/queue',
                  memory='Process VmHWM including imports/init/native allocations, sampled before output hash; not tracemalloc',
                  scenarios={})
    result_path = work / 'report.json'
    def save():
        temporary = work / 'report.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(result_path)
    save()
    for case in cases:
        case = dict(case, settings=asdict(case['settings']), path=str(case['path']),
                    source_sha256=sha(case['path']))
        path = work / (case['name'] + '.json'); path.write_text(json.dumps(case))
        data = dict(case=case, samples=[[], []], outputs=None)
        orders = [(0, 1), (1, 0)] * ((args.pairs + 1) // 2)
        orders = orders[:args.pairs]; rng.shuffle(orders)
        for order in orders:
            for side in order:
                check_deadline(args.deadline_timestamp)
                command = [sys.executable, str(Path(__file__).resolve()), '--trial-worker',
                           '--module-dir', str(snapshots[side]['path']), '--case', str(path),
                           '--output-root', str(output_root)]
                if args.deadline:
                    command.extend(['--deadline', args.deadline])
                timeout = max(1, min(300, args.deadline_timestamp - time.time())) if args.deadline_timestamp else 300
                value = json.loads(subprocess.check_output(command, text=True, timeout=timeout))
                assert value['cpu_affinity'] == report['cpu_affinity']
                if data['outputs'] is None:
                    data['outputs'] = value['outputs']
                assert value['outputs'] == data['outputs'], case['name']
                data['samples'][side].append(value)
            report['scenarios'][case['name']] = data
            save()
        partial = summarize({case['name']: data}, args.seed)
        print(json.dumps(dict(case=case['name'], **partial['scenarios'][case['name']])), flush=True)
    report['summary'] = summarize(report['scenarios'], args.seed)
    for snapshot in snapshots:
        bundle = {key: (snapshot['path'] / (key + '.py')).read_text() for key in FILES}
        assert digest(bundle) == snapshot['source_hash']
    assert sha(__file__) == report['benchmark_sha256']
    assert all(sha(ROOT / 'autorip' / (name + '.py')) == value
               for name, value in report['common_module_sha256'].items())
    report['complete'] = True
    report['stopped_at_utc'] = datetime.now(timezone.utc).isoformat()
    save()
    print(json.dumps(dict(complete=True, geomean_speedup=report['summary']['geomean_speedup'],
                          bootstrap_95_low=report['summary']['bootstrap_95_low'])), flush=True)


if __name__ == '__main__':
    main()
