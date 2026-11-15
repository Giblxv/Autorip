"""RIP 1:1 e controles escalados, com PRT exato e RSS em processos novos.

python benchmarks/benchmark_identity_strips.py --baseline-ref v0.8.33 --pairs 7 --output /tmp/identity.json
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
from autorip.config import Settings
from benchmark_source_preparation import load, run


def fixtures(root, icc=None):
    for name, width, height in [('small', 129, 137), ('serial', 513, 1200), ('tall', 513, 8192)]:
        yy, xx = np.indices((height, width))
        rgba = np.stack([(xx * 3 + yy) % 256, (xx + yy * 7) % 256,
                         (xx * 11 + yy) % 256, (xx * 5 + yy * 3) % 256], axis=-1).astype(np.uint8)
        image = Image.fromarray(rgba)
        image.save(root / f'{name}.png')
        if name == 'tall':
            image.convert('RGB').save(root / 'tall-rgb.png')
        image.close()
    common = dict(dpi_x=300, dpi_y=300, label_enabled=False,
                  margin_top_in=.02, margin_bottom_in=.02, white_enabled=False)
    def case(name, image, width, **settings):
        return dict(name=name, path=str(root / image), width_cm=width / 300 * 2.54,
                    settings=common | settings)
    cases = [case('rgba_one_strip', 'small.png', 129),
            case('rgba_serial', 'serial.png', 513),
            case('rgba_tall', 'tall.png', 513),
            case('rgba_tall_white', 'tall.png', 513, white_enabled=True),
            case('rgb_tall', 'tall-rgb.png', 513),
            case('scaled_rgba_control', 'tall.png', 300)]
    if icc is not None:
        cases.append(case('rgba_tall_output_icc', 'tall.png', 513,
                          icc_path=str(icc), white_enabled=True))
    return cases


def paired(rips, case, root, count):
    oracle = None
    samples = [[], []]
    for side in range(2):
        _, digest, info = run(rips[side], case, root / 'out.PRT')
        if oracle is None:
            oracle = (digest, info)
        assert oracle == (digest, info), case['name']
    for iteration in range(count):
        for side in ((0, 1) if iteration % 2 == 0 else (1, 0)):
            elapsed, digest, info = run(rips[side], case, root / 'out.PRT')
            assert (digest, info) == oracle, case['name']
            samples[side].append(elapsed)
    old, new = map(statistics.median, samples)
    ratios = np.array(samples[0]) / np.array(samples[1])
    rng = np.random.default_rng(19)
    boot = np.median(ratios[rng.integers(0, count, (10000, count))], axis=1)
    return dict(baseline_seconds=old, candidate_seconds=new, speedup=old / new,
                paired_speedup_ci95=np.quantile(boot, [.025, .975]).tolist(),
                samples=samples, prt_sha256=oracle[0], metadata=oracle[1], outputs_equal=True)


def main(fixture_factory=fixtures, description=__doc__):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--pairs', type=int, default=7)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--icc', type=Path)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    ref = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(['git', 'show', f'{ref}:autorip/engine.py'], cwd=ROOT, text=True)
    candidate = ROOT / 'autorip/engine.py'
    shared = {}
    for name in ('prt', 'morph'):
        old = subprocess.check_output(['git', 'show', f'{ref}:autorip/{name}.py'], cwd=ROOT)
        assert (ROOT / f'autorip/{name}.py').read_bytes() == old
        shared[name] = hashlib.sha256(old).hexdigest()
    report = dict(baseline_ref=ref, python=platform.python_version(), numpy=np.__version__,
                  pillow=Image.__version__, platform=platform.platform(), cpu_count=os.cpu_count(),
                  pairs=args.pairs, source_sha256=dict(baseline=hashlib.sha256(source.encode()).hexdigest(),
                                                     candidate=hashlib.sha256(candidate.read_bytes()).hexdigest()),
                  icc_sha256=hashlib.sha256(args.icc.read_bytes()).hexdigest() if args.icc else None,
                  shared_modules_sha256=shared, scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-identity-') as folder:
        root = Path(folder)
        baseline = root / 'baseline.py'
        baseline.write_text(source)
        modules = [load(baseline, 'identity_baseline'), load(candidate, 'identity_candidate')]
        for case in fixture_factory(root, args.icc.resolve() if args.icc else None):
            rips = [module.Rip(Settings(**case['settings'])) for module in modules]
            result = paired(rips, case, root, args.pairs)
            case_path = root / 'case.json'
            case_path.write_text(json.dumps(case))
            peaks = {}
            for name, path in [('baseline', baseline), ('candidate', candidate)]:
                values = []
                for _ in range(2):
                    value = json.loads(subprocess.check_output([
                        sys.executable, str(ROOT / 'benchmarks/benchmark_source_preparation.py'),
                        '--rss-worker', str(path), '--case', str(case_path)], text=True))
                    assert value['sha256'] == result['prt_sha256'] and value['metadata'] == result['metadata']
                    values.append(value['peak_rss_mib'])
                peaks[name] = dict(samples_mib=values, median_mib=statistics.median(values)
                                   if all(value is not None for value in values) else None)
            result['peak_rss'] = peaks
            report['scenarios'][case['name']] = result
            print(case['name'], result['speedup'], peaks, flush=True)
        report['control_aa'] = paired([rips[0], rips[0]], case, root, args.pairs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
