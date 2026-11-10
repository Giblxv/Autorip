"""Controles RGBA: impressão larga e pressão sobre o cache de perfis mistos."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import struct
import subprocess
import sys
import tempfile

from benchmark_source_icc import ROOT, TimingWorker, builds, load
import numpy as np
from PIL import Image, ImageCms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeat', type=int, default=7)
    parser.add_argument('--cases', nargs='+', choices=['5.08', '10.16', 'small_rgba', 'small_no_icc', 'cache_pressure'])
    args = parser.parse_args()
    if args.repeat < 7:
        parser.error('Use pelo menos sete repetições')
    commit = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    source = subprocess.check_output(['git', 'show', commit + ':autorip/engine.py'], cwd=ROOT, text=True)
    for name in ('prt', 'morph'):
        assert (ROOT / 'autorip' / (name + '.py')).read_bytes() == subprocess.check_output(
            ['git', 'show', commit + ':autorip/' + name + '.py'], cwd=ROOT)
    candidate = ROOT / 'autorip/engine.py'
    report = dict(baseline_ref=commit, repeat=args.repeat, large_source_size=[4096, 3072],
                  cache_pressure_source_size=[320, 240], source_dpi=[100, 200], scenarios={},
                  source_sha256=dict(baseline=hashlib.sha256(source.encode()).hexdigest(),
                                     candidate=hashlib.sha256(candidate.read_bytes()).hexdigest()),
                  benchmark_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    report['timing_processes'] = 'separate persistent workers per implementation/case'
    affinity = sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None
    report['cpu_affinity'] = affinity
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
        settings = dict(label_enabled=False, margin_top_in=.05, margin_bottom_in=.05)
        cases = [(str(width), dict(files=[str(path)], width_cm=width, cold=False,
                                  settings=settings)) for width in (5.08, 10.16)]
        small_files = []; plain_files = []
        sy, sx = np.indices((240, 320), dtype=np.uint16)
        for index in range(4):
            pixels = np.empty((240, 320, 4), np.uint8)
            pixels[..., 0] = (sx * 3 + sy + index * 17) % 256
            pixels[..., 1] = (sx + sy * 2 + index * 11) % 256
            pixels[..., 2] = (sx * 5 + sy * 3) % 256
            pixels[..., 3] = np.linspace(0, 255, 320, dtype=np.uint8)[None, :]
            artwork = Image.fromarray(pixels, 'RGBA')
            try:
                for embedded, paths, prefix in [(profile, small_files, 'small'), (b'', plain_files, 'plain')]:
                    target = root / f'{prefix}-{index}.png'
                    artwork.save(target, icc_profile=embedded, dpi=(100, 200)); paths.append(str(target))
            finally:
                artwork.close()
        cases.extend([(name, dict(files=files, width_cm=1.27, cold=False, settings=settings))
                      for name, files in [('small_rgba', small_files), ('small_no_icc', plain_files)]])
        # O mesmo perfil ocupa dois contextos no candidato. Dezesseis entradas
        # alternadas excedem o limite de oito, mesmo cabendo no orçamento de bytes.
        files = []; profile_hashes = []
        small = Image.new('RGBA', (320, 240), (100, 150, 200, 127))
        try:
            for index in range(8):
                embedded = bytearray(profile)
                for tag in range(struct.unpack_from('>I', embedded, 128)[0]):
                    pos = 132 + tag * 12
                    if embedded[pos:pos + 4] == b'rTRC':
                        offset = struct.unpack_from('>I', embedded, pos + 4)[0]
                        assert embedded[offset:offset + 4] == b'para'
                        struct.pack_into('>i', embedded, offset + 12, round((1.4 + index * .1) * 65536))
                        break
                else:
                    raise AssertionError('Perfil sem TRC paramétrica')
                profile_hashes.append(hashlib.sha256(embedded).hexdigest())
                for mode in ('RGB', 'RGBA'):
                    colored = small.convert(mode)
                    target = root / f'pressure-{index}-{mode}.tif'
                    try:
                        colored.save(target, icc_profile=bytes(embedded), dpi=(100, 200))
                    finally:
                        colored.close()
                    files.append(str(target))
        finally:
            small.close()
        report['cache_pressure_profile_sha256'] = profile_hashes
        cases.append(('cache_pressure', dict(files=files, width_cm=1.27, cold=False, settings=settings)))
        for name, case in cases:
            if args.cases and name not in args.cases:
                continue
            # Estes controles têm menos de 1 MP de saída e já renderizam em uma
            # thread. Fixar ambos os workers na mesma CPU remove a migração entre
            # núcleos como variável; os controles largos mantêm a afinidade inicial.
            if affinity is not None:
                os.sched_setaffinity(0, [affinity[0]] if name in ('small_rgba', 'small_no_icc', 'cache_pressure') else affinity)
            case_affinity = sorted(os.sched_getaffinity(0)) if affinity is not None else None
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
            result = dict(width_cm=case['width_cm'], files=len(case['files']), cpu_affinity=case_affinity,
                          baseline_seconds=old, candidate_seconds=new,
                          speedup=old/new, raw_seconds=samples, cpu_raw_seconds=cpu,
                          baseline_cpu_seconds=old_cpu, candidate_cpu_seconds=new_cpu,
                          cpu_speedup=old_cpu/new_cpu,
                          paired_bootstrap_95=[float(v) for v in np.percentile(bootstrap, [2.5, 97.5])],
                          peak_rss=peaks, outputs=oracle)
            if name == 'cache_pressure':
                result['transform_builds'] = {
                    side: builds(load(module_path, 'pressure-' + side), case, root)
                    for side, module_path in [('baseline', baseline), ('candidate', candidate)]}
            report['scenarios'][name] = result
            print(json.dumps({name: result}), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
