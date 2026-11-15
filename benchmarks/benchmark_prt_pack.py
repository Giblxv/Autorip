"""Compara empacotamento e RIP completo; nunca envia trabalhos para impressora.

python benchmarks/benchmark_prt_pack.py --baseline-ref v0.8.32 --pairs 11 --output /tmp/pack.json
"""
import argparse
import hashlib
import importlib.util
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image
from autorip import engine, prt
from autorip.config import Settings


def compare(actions, pairs, *, operations=1):
    warm = [action() for action in actions]
    assert warm[0][0] == warm[1][0]
    samples = [[], []]
    hashes = set()
    for pair in range(pairs):
        outputs = [None, None]
        for index in ((0, 1) if pair % 2 == 0 else (1, 0)):
            start = time.perf_counter()
            result, check = actions[index]()
            samples[index].append((time.perf_counter() - start - check[0]) / operations)
            outputs[index] = result
        assert outputs[0] == outputs[1]
        hashes.add(str(outputs[0]))
    medians = list(map(statistics.median, samples))
    ratios = np.array(samples[0]) / np.array(samples[1])
    rng = np.random.default_rng(48)
    bootstrap = np.median(ratios[rng.integers(0, pairs, (10000, pairs))], axis=1)
    return dict(baseline_seconds=medians[0], candidate_seconds=medians[1],
                speedup=medians[0] / medians[1], paired_speedup_ci95=np.quantile(bootstrap, [.025, .975]).tolist(),
                baseline_samples=samples[0], candidate_samples=samples[1],
                outputs_equal=True, distinct_outputs=len(hashes))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--pairs', type=int, default=11)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.pairs < 7:
        parser.error('Use pelo menos sete pares')
    ref = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(['git', 'show', f'{ref}:autorip/prt.py'], cwd=ROOT, text=True)
    report = dict(baseline_ref=ref, python=platform.python_version(), numpy=np.__version__,
                  platform=platform.platform(), cpu_count=os.cpu_count(), pairs=args.pairs,
                  packing_operations_per_sample=10,
                  source_sha256=dict(baseline=hashlib.sha256(source.encode()).hexdigest(),
                                     candidate=hashlib.sha256((ROOT / 'autorip/prt.py').read_bytes()).hexdigest()),
                  packing={}, rip={})
    with tempfile.TemporaryDirectory(prefix='autorip-pack-') as folder:
        root = Path(folder)
        module_path = root / 'baseline_prt.py'
        module_path.write_text(source)
        spec = importlib.util.spec_from_file_location('_baseline_prt', module_path)
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        rng = np.random.default_rng(5)
        for rows, width in ((8, 37), (128, 1417), (512, 5669), (512, 12000)):
            for layout in ('contiguous', 'reverse', 'empty'):
                levels = rng.integers(0, 4, (rows, width), dtype=np.uint8)
                if layout == 'reverse':
                    levels = levels[:, ::-1]
                elif layout == 'empty':
                    levels.fill(0)
                pb = prt.plane_bytes_for(width)
                def action(module):
                    def run():
                        for _ in range(10):
                            result = module.pack2(levels, pb)
                        check_start = time.perf_counter()
                        digest = hashlib.sha256(result).hexdigest()
                        return digest, (time.perf_counter() - check_start,)
                    return run
                actions = [action(module) for module in (baseline, prt)]
                result = compare(actions, args.pairs, operations=10)
                peaks = []
                for module in (baseline, prt):
                    tracemalloc.start()
                    try:
                        module.pack2(levels, pb)
                        peaks.append(tracemalloc.get_traced_memory()[1])
                    finally:
                        tracemalloc.stop()
                result['peak_traced_bytes'] = dict(zip(('baseline', 'candidate'), peaks))
                name = f'{rows}x{width}-{layout}'
                report['packing'][name] = result
                print(name, result['speedup'], flush=True)
        # Identica geometria, ICC, fonte e scheduler; varia somente PrtWriter.
        yy, xx = np.indices((384, 768))
        rgb = np.stack([(xx * 3 + yy) % 256, (xx + yy * 7) % 256, (xx * 11 + yy) % 256], axis=-1).astype(np.uint8)
        alpha = ((xx * 5 + yy * 3) % 256).astype(np.uint8)
        for name, mode, dpi, width_cm, white, label in (
            ('small_rgb', 'RGB', (300, 300), 1.1, False, False),
            ('rgba_white', 'RGBA', (720, 1200), 5, True, False),
            ('rgb_no_white', 'RGB', (720, 1200), 5, False, False),
            ('wide_rgb', 'RGB', (720, 600), 21.167, False, False),
            ('wide_rgba_white', 'RGBA', (720, 600), 21.167, True, False),
            ('labels_white', 'RGBA', (720, 1200), 5, True, True),
            ('transparent_rgba', 'RGBA', (720, 1200), 5, True, False),
            ('black_rgb_no_white', 'RGB', (720, 1200), 5, False, False),
        ):
            data = rgb if mode == 'RGB' else np.dstack([rgb, alpha])
            if name in ('transparent_rgba', 'black_rgb_no_white'):
                data = np.zeros_like(data)
            image_path = root / f'{name}.png'
            Image.fromarray(data).save(image_path)
            settings = Settings(dpi_x=dpi[0], dpi_y=dpi[1], white_enabled=white,
                                label_enabled=label, margin_top_in=.1, margin_bottom_in=.1)
            rip = engine.Rip(settings)
            def action(module):
                def run():
                    original = engine.PrtWriter
                    engine.PrtWriter = module.PrtWriter
                    try:
                        info = rip.process(str(image_path), str(root / 'output.PRT'), width_cm=width_cm)
                    finally:
                        engine.PrtWriter = original
                    check_start = time.perf_counter()
                    output = Path(info.pop('output_path'))
                    with output.open('rb') as stream:
                        digest = hashlib.sha256()
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(block)
                    output.unlink()
                    return (digest.hexdigest(), info), (time.perf_counter() - check_start,)
                return run
            actions = [action(module) for module in (baseline, prt)]
            report['rip'][name] = compare(actions, args.pairs)
            print(name, report['rip'][name]['speedup'], flush=True)
        # Controle A/A usa a mesma versao de producao nos dois grupos.
        report['control_aa'] = compare([actions[0], actions[0]], args.pairs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
