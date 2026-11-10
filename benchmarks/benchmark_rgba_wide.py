"""Controle de impressão larga com fonte RGBA grande e perfil embutido."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile

from benchmark_source_icc import ROOT, TimingWorker
import numpy as np
from PIL import Image, ImageCms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=7)
    args = parser.parse_args()
    if args.repeat < 7:
        parser.error('Use pelo menos sete repetições')
    commit = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(['git', 'show', commit + ':autorip/engine.py'], cwd=ROOT, text=True)
    for name in ('prt', 'morph'):
        assert (ROOT / 'autorip' / (name + '.py')).read_bytes() == subprocess.check_output(
            ['git', 'show', commit + ':autorip/' + name + '.py'], cwd=ROOT)
    candidate = ROOT / 'autorip/engine.py'
    report = dict(baseline_ref=commit, repeat=args.repeat, source_size=[4096, 3072],
                  source_dpi=[100, 200], scenarios={},
                  source_sha256=dict(baseline=hashlib.sha256(source.encode()).hexdigest(),
                                     candidate=hashlib.sha256(candidate.read_bytes()).hexdigest()),
                  benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    report['timing_processes'] = 'separate persistent workers per implementation/case'
    report['cpu_affinity'] = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None
    with tempfile.TemporaryDirectory(prefix='autorip-rgba-wide-') as folder:
        root = Path(folder)
        baseline = root / 'baseline.py'; baseline.write_text(source)
        y, x = np.indices((3072, 4096), dtype=np.uint16)
        pixels = np.empty((3072, 4096, 4), np.uint8)
        pixels[..., 0] = (x * 3 + y) % 256
        pixels[..., 1] = (x + y * 2) % 256
        pixels[..., 2] = (x * 5 + y * 3) % 256
        pixels[..., 3] = np.linspace(0, 255, 4096, dtype=np.uint8)[None, :]
        image = Image.fromarray(pixels, 'RGBA'); path = root / 'source.tif'
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
        image.save(path, icc_profile=profile, dpi=(100, 200)); image.close()
        del pixels, x, y
        report['profile_sha256'] = hashlib.sha256(profile).hexdigest()
        for width in (5.08, 10.16):
            case = dict(files=[str(path)], width_cm=width, cold=False,
                        settings=dict(label_enabled=False, margin_top_in=.05, margin_bottom_in=.05))
            oracle = None; samples = [[], []]; cpu = [[], []]
            case_path = root / 'timing-case.json'; case_path.write_text(json.dumps(case))
            workers = []
            try:
                for module_path in (baseline, candidate):
                    workers.append(TimingWorker(module_path, case_path))
                for side in range(2):
                    _, outputs, _ = workers[side].run()
                    if oracle is None: oracle = outputs
                    assert outputs == oracle
                for index in range(args.repeat):
                    for side in ((0, 1) if index % 2 == 0 else (1, 0)):
                        elapsed, outputs, cpu_elapsed = workers[side].run()
                        assert outputs == oracle
                        samples[side].append(elapsed); cpu[side].append(cpu_elapsed)
            finally:
                for worker in workers:
                    worker.close()
            old, new = map(statistics.median, samples)
            old_cpu, new_cpu = map(statistics.median, cpu)
            ratios = np.asarray(samples[0]) / np.asarray(samples[1]); rng = np.random.default_rng(194)
            bootstrap = np.median(ratios[rng.integers(0, args.repeat, (3000, args.repeat))], axis=1)
            peaks = {}; case_path = root / 'case.json'; case_path.write_text(json.dumps(case))
            for side, module_path in [('baseline', baseline), ('candidate', candidate)]:
                values = []
                for _ in range(2):
                    result = json.loads(subprocess.check_output([sys.executable,
                        str(ROOT / 'benchmarks/benchmark_source_icc.py'), '--rss-worker', str(module_path),
                        '--case', str(case_path)], text=True))
                    assert result['outputs'] == oracle
                    values.append(result['peak_rss_mib'])
                peaks[side] = dict(samples_mib=values, median_mib=statistics.median(values))
            result = dict(width_cm=width, baseline_seconds=old, candidate_seconds=new,
                          speedup=old/new, raw_seconds=samples, cpu_raw_seconds=cpu,
                          baseline_cpu_seconds=old_cpu, candidate_cpu_seconds=new_cpu,
                          cpu_speedup=old_cpu/new_cpu,
                          paired_bootstrap_95=[float(v) for v in np.percentile(bootstrap, [2.5, 97.5])],
                          peak_rss=peaks, outputs=oracle)
            report['scenarios'][str(width)] = result
            print(json.dumps({str(width): result}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
