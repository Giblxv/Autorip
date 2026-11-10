"""Mede RIP completo e RSS isolado, preservando SHA-256 e metadados do PRT.

python benchmarks/benchmark_source_preparation.py --baseline-ref ced6b2f --output /tmp/source.json
"""
import argparse
import hashlib
import importlib.util
import json
import math
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
from PIL import Image, ImageDraw
from autorip.config import Settings


def load(path, name):
    spec = importlib.util.spec_from_file_location('autorip._source_bench_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(rip, case, destination):
    started = time.perf_counter()
    info = rip.process(case['path'], str(destination), width_cm=case['width_cm'])
    elapsed = time.perf_counter() - started
    path = Path(info.pop('output_path'))
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    finally:
        path.unlink()
    return elapsed, digest, info


def rss():
    if sys.platform.startswith('linux'):
        line = next(s for s in Path('/proc/self/status').read_text().splitlines() if s.startswith('VmHWM:'))
        return int(line.split()[1]) / 1024
    try:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value / (1024**2 if sys.platform == 'darwin' else 1024)
    except ImportError:
        return None


def fixtures(root, icc):
    image = Image.new('RGBA', (4096, 3072), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((100, 100, 3996, 2972), radius=450, fill=(25, 140, 230, 190))
    draw.ellipse((1200, 400, 3000, 2200), fill=(240, 55, 110, 90))
    image.save(root / 'large.png')
    image.resize((640, 480)).save(root / 'small.png')
    rgb = image.convert('RGB')
    rgb.save(root / 'large.jpg', quality=93)
    exif = Image.Exif()
    exif[274] = 6
    rgb.save(root / 'oriented.jpg', quality=93, exif=exif, dpi=(100, 200))
    image.save(root / 'large.tiff', compression='raw', dpi=(100, 200))
    image.close()
    rgb.close()
    common = dict(label_enabled=False, margin_top_in=.05, margin_bottom_in=.05)
    def case(name, path, width_cm=1.27, **settings):
        return dict(name=name, path=str(root / path), width_cm=width_cm, settings=common | settings)
    cases = [case('small_rgba', 'small.png'), case('large_rgba', 'large.png'),
             case('large_rgba_parallel', 'large.png', 2.54), case('large_jpeg', 'large.jpg'),
             case('oriented_jpeg', 'oriented.jpg'), case('rgba_tiff', 'large.tiff')]
    if icc:
        cases.append(case('output_icc', 'large.png', icc_path=icc))
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='ced6b2f')
    parser.add_argument('--repeat', type=int, default=7)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--icc', type=Path)
    parser.add_argument('--rss-worker', type=Path)
    parser.add_argument('--case', type=Path)
    args = parser.parse_args()
    if args.rss_worker:
        case = json.loads(args.case.read_text())
        module = load(args.rss_worker, 'worker')
        rip = module.Rip(Settings(**case['settings']))
        with tempfile.TemporaryDirectory(prefix='autorip-source-rss-') as folder:
            _, digest, info = run(rip, case, Path(folder) / 'out.PRT')
            print(json.dumps(dict(peak_rss_mib=rss(),sha256=digest,metadata=info)))
        return
    if args.repeat < 5 or args.output is None:
        parser.error('Use --output e pelo menos cinco repetições')
    commit = subprocess.check_output(['git','rev-parse',args.baseline_ref],cwd=ROOT,text=True).strip()
    baseline_text = subprocess.check_output(['git','show',commit+':autorip/engine.py'],cwd=ROOT,text=True)
    candidate = ROOT / 'autorip/engine.py'
    shared = {}
    for name in ('morph', 'prt'):
        path = ROOT / 'autorip' / (name + '.py')
        reference = subprocess.check_output(['git','show',commit+':autorip/'+name+'.py'],cwd=ROOT,text=True)
        if path.read_text() != reference:
            parser.error('Este benchmark de preparação exige morph.py/prt.py idênticos à base')
        shared[name] = hashlib.sha256(reference.encode()).hexdigest()
    report = dict(baseline_ref=commit,python=platform.python_version(),platform=platform.platform(),
                  pillow=Image.__version__,numpy=np.__version__,repeat=args.repeat,cpu_count=os.cpu_count(),
                  source_sha256=dict(baseline=hashlib.sha256(baseline_text.encode()).hexdigest(),
                                     candidate=hashlib.sha256(candidate.read_bytes()).hexdigest()),
                  shared_modules_sha256=shared,
                  icc_sha256=hashlib.sha256(args.icc.read_bytes()).hexdigest() if args.icc else None,
                  rss_metric='VmHWM in fresh Linux workers; ru_maxrss on other Unix; unavailable on Windows',
                  scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-source-bench-') as folder:
        root = Path(folder)
        baseline = root / 'baseline.py'
        baseline.write_text(baseline_text)
        modules = [load(baseline,'baseline'), load(candidate,'candidate')]
        for case in fixtures(root, str(args.icc.resolve()) if args.icc else None):
            rips = [module.Rip(Settings(**case['settings'])) for module in modules]
            samples = [[], []]
            oracle = None
            for side in range(2):
                _, digest, info = run(rips[side], case, root / 'out.PRT')
                if oracle is None:
                    oracle = (digest, info)
                assert oracle == (digest, info), case['name']
            for iteration in range(args.repeat):
                for side in ((0,1) if iteration % 2 == 0 else (1,0)):
                    elapsed, digest, info = run(rips[side], case, root / 'out.PRT')
                    assert oracle == (digest, info), case['name']
                    samples[side].append(elapsed)
            ratios = np.array(samples[0]) / np.array(samples[1])
            rng = np.random.default_rng(194)
            bootstrap = np.median(ratios[rng.integers(0,args.repeat,(3000,args.repeat))],axis=1)
            old, new = map(statistics.median, samples)
            case_path = root / 'case.json'
            case_path.write_text(json.dumps(case))
            peaks = {}
            for name, source in [('baseline',baseline),('candidate',candidate)]:
                values = []
                for _ in range(2):
                    peak = json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),
                        '--rss-worker',str(source),'--case',str(case_path)],text=True))
                    assert (peak['sha256'],peak['metadata']) == oracle, case['name']
                    values.append(peak['peak_rss_mib'])
                peaks[name] = dict(samples_mib=values,median_mib=statistics.median(values) if all(v is not None for v in values) else None)
            result = dict(baseline_seconds=old,candidate_seconds=new,speedup=old/new,raw_seconds=samples,
                          paired_bootstrap_95=[float(v) for v in np.percentile(bootstrap,[2.5,97.5])],
                          peak_rss=peaks,prt_sha256=oracle[0],metadata=oracle[1])
            report['scenarios'][case['name']] = result
            print(json.dumps({case['name']:result}),flush=True)
        report['geomean_speedup'] = math.exp(statistics.mean(math.log(r['speedup']) for r in report['scenarios'].values()))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')


if __name__ == '__main__':
    main()
