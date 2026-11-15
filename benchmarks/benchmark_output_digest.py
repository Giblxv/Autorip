"""RIP com SHA/journal duráveis; sem rede ou envio à impressora.

python benchmarks/benchmark_output_digest.py --baseline-ref v0.8.34 --pairs 11 --output /tmp/digest.json
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
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
from autorip import engine
from autorip.config import Settings
from autorip.paths import file_sha256, write_json_atomic
from benchmark_main_refinements import baseline, ratio_interval


def fixtures(root):
    yy, xx = np.indices((512, 768))
    data = np.stack([(xx * 3 + yy) % 256, (xx + yy * 7) % 256,
                     (xx * 11 + yy) % 256, (xx * 5 + yy * 3) % 256], axis=-1).astype(np.uint8)
    rgba = Image.fromarray(data)
    rgba.save(root / 'alpha.png')
    rgba.convert('RGB').save(root / 'rgb.png')
    Image.new('RGBA', (256, 256), (0, 0, 0, 0)).save(root / 'transparent.png')
    rgba.close()
    common = dict(label_enabled=False, margin_top_in=.02, margin_bottom_in=.02)
    def case(name, file, width, archive=True, **settings):
        return dict(name=name, path=str(root / file), width_cm=width, archive=archive,
                    settings=common | settings)
    return [case('scaled_rgb', 'rgb.png', 5.08, white_enabled=False),
            case('scaled_rgba_white', 'alpha.png', 5.08),
            case('large_prt_rgb', 'rgb.png', 6000 / 720 * 2.54, dpi_x=720, dpi_y=720, white_enabled=False),
            case('large_prt_transparent', 'transparent.png', 6000 / 720 * 2.54, dpi_x=720, dpi_y=720),
            case('small_manual_control', 'rgb.png', 1.27, archive=False, white_enabled=False)]


def run(rip, case, root):
    journal = root / 'journal.json'
    output = root / 'output.PRT'
    reads = dict(calls=0, bytes=0)
    marker = dict(phase='processing', info={})
    def before_publish(path, info):
        digest = info.get('output_sha256')
        if digest is None:
            reads['calls'] += 1
            reads['bytes'] += os.path.getsize(path)
            digest = file_sha256(path)
        marker.update(output_sha256=digest, info={k:v for k,v in info.items() if k != 'output_sha256'})
        write_json_atomic(str(journal), marker)
    before_publish.requires_output_sha256 = True
    start = time.perf_counter()
    if case['archive']:
        write_json_atomic(str(journal), marker)
    info = rip.process(case['path'], str(output), width_cm=case['width_cm'],
                       before_publish=before_publish if case['archive'] else None)
    actual = Path(info.pop('output_path'))
    write_json_atomic(str(actual) + '.meta.json', info)
    if case['archive']:
        marker.update(phase='success', info=info)
        write_json_atomic(str(journal), marker)
    elapsed = time.perf_counter() - start
    digest = file_sha256(actual)
    if case['archive']:
        assert marker['output_sha256'] == digest
    result = digest, info, actual.stat().st_size
    actual.unlink()
    Path(str(actual) + '.meta.json').unlink()
    journal.unlink(missing_ok=True)
    return elapsed, result, reads


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--pairs', type=int, default=11)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    ref = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    report = dict(baseline_ref=ref, python=platform.python_version(), numpy=np.__version__,
                  pillow=Image.__version__, platform=platform.platform(), available_cpus=engine._available_cpu_count(),
                  pairs=args.pairs, source_sha256={}, cases={})
    for side in ('baseline', 'candidate'):
        report['source_sha256'][side] = {}
        for name in ('engine', 'prt', 'watcher', 'server'):
            path = f'autorip/{name}.py'
            data = subprocess.check_output(['git', 'show', f'{ref}:{path}'], cwd=ROOT) if side == 'baseline' else (ROOT / path).read_bytes()
            report['source_sha256'][side][name] = hashlib.sha256(data).hexdigest()
    with tempfile.TemporaryDirectory(prefix='autorip-digest-') as folder:
        root = Path(folder)
        old = baseline(ref, root)
        for case in fixtures(root):
            rips = [module.Rip(Settings(**case['settings'])) for module in (old, engine)]
            samples = [[], []]
            read_totals = [dict(calls=0, bytes=0), dict(calls=0, bytes=0)]
            expected = None
            for pair in range(-1, args.pairs):
                for side in ((0, 1) if pair % 2 == 0 else (1, 0)):
                    elapsed, result, reads = run(rips[side], case, root)
                    if expected is None:
                        expected = result
                    assert result == expected, (case['name'], side)
                    if pair >= 0:
                        samples[side].append(elapsed)
                        for key, value in reads.items():
                            read_totals[side][key] += value
            medians = list(map(statistics.median, samples))
            result = dict(baseline_seconds=medians[0], candidate_seconds=medians[1],
                          speedup=medians[0] / medians[1], paired_speedup_ci95=ratio_interval(*samples),
                          samples=samples, explicit_hash_readback=dict(zip(('baseline', 'candidate'), read_totals)),
                          sha256=expected[0], metadata=expected[1], bytes=expected[2], outputs_equal=True)
            report['cases'][case['name']] = result
            print(case['name'], result['speedup'], result['paired_speedup_ci95'], read_totals, flush=True)
        # Controle A/A no mesmo caso manual, sem calculo de hash de journal.
        samples = [[], []]
        for pair in range(args.pairs):
            for side in ((0, 1) if pair % 2 == 0 else (1, 0)):
                elapsed, result, _ = run(rips[0], case, root)
                assert result == expected
                samples[side].append(elapsed)
        medians = list(map(statistics.median, samples))
        report['control_aa'] = dict(speedup=medians[0] / medians[1], samples=samples,
                                    paired_speedup_ci95=ratio_interval(*samples))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
