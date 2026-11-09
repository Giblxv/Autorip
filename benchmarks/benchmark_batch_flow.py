"""Mede admissão do painel e RIP completo da CLI; não faz rede nem publica.

python benchmarks/benchmark_batch_flow.py --baseline-ref 104725c --output /tmp/batch.json
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import queue
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import Image, ImageDraw
from autorip.config import Settings
from autorip.engine import Rip


def load(path, name):
    spec = importlib.util.spec_from_file_location(f"autorip._batch_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScanFinished(BaseException):
    pass


def panel_scan(module, settings, root, count):
    # Executa o observador de produção por uma passagem. O worker fica parado:
    # esta medição cobre somente detecção/claim/admissão, não renderização.
    app = module.App.__new__(module.App)
    app.s = settings
    app.auto = True
    app.settings_lock = threading.RLock()
    app.lock = threading.RLock()
    app.upload_lock = threading.Lock()
    app._known_hot_folders = [os.path.normcase(os.path.realpath(settings.hot_folder))]
    app.archive_pending = {}
    app.queued_sources = set()
    app._admission_reservations = set()
    app.source_jobs = {}
    app.job_controls = {}
    app.jobs = []
    app.q = queue.Queue()
    app.inbox = str(root / "manual")
    Path(app.inbox).mkdir()
    app._trello_loop = lambda: None
    messages = []
    app.log = messages.append

    def finish(_seconds):
        raise ScanFinished()

    original_time = module.time
    module.time = SimpleNamespace(sleep=finish, monotonic=time.monotonic, time_ns=time.time_ns)
    try:
        try:
            module.App._watch(app)
        except ScanFinished:
            pass
    finally:
        module.time = original_time
    assert not messages, messages
    assert app.q.qsize() == count and len(app.jobs) == count
    names = [job['name'] for job in app.jobs]
    assert names == [f"art-{i:02}.png" for i in range(count)]
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', required=True)
    parser.add_argument('--repeat', type=int, default=7)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.repeat < 5:
        parser.error('Use pelo menos cinco repetições pareadas')
    baseline_ref = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    with tempfile.TemporaryDirectory(prefix='autorip-batch-') as folder:
        root = Path(folder)
        sources = {}
        modules = {}
        for side in ('baseline', 'candidate'):
            sources[side] = {}
            for name in ('watcher', 'server'):
                rel = f'autorip/{name}.py'
                source = (subprocess.check_output(['git', 'show', f'{baseline_ref}:{rel}'], cwd=ROOT, text=True)
                          if side == 'baseline' else (ROOT / rel).read_text())
                sources[side][name] = source
                path = root / f'{side}-{name}.py'
                path.write_text(source)
                modules[side, name] = load(path, f'{side}_{name}')
            # O servidor antigo deve importar a estabilidade antiga também.
            modules[side, 'server']._signature = modules[side, 'watcher']._signature
            modules[side, 'server']._stable = modules[side, 'watcher']._stable
            if hasattr(modules[side, 'watcher'], '_stable_files'):
                modules[side, 'server']._stable_files = modules[side, 'watcher']._stable_files
        image = Image.new('RGBA', (256, 192), (0, 0, 0, 0))
        ImageDraw.Draw(image).rounded_rectangle((9, 9, 247, 183), radius=25, fill=(30, 140, 210, 230))
        report = dict(baseline_ref=baseline_ref, python=platform.python_version(), platform=platform.platform(),
                      repeat=args.repeat, cpu_count=os.cpu_count(),
                      source_sha256={side: {name: hashlib.sha256(source.encode()).hexdigest()
                                           for name, source in bundle.items()} for side, bundle in sources.items()},
                      scenarios={}, output_equivalence={})

        def run(side, kind, count, index):
            trial = root / f'{kind}-{count}-{index}-{side}'
            trial.mkdir()
            settings = Settings(label_enabled=False, margin_top_in=0, margin_bottom_in=0,
                                poll_seconds=.5, auto_update=False, offline_mode=True,
                                **{key: str(trial / key) for key in ('hot_folder', 'output_folder',
                                   'done_folder', 'error_folder', 'printed_folder')})
            Path(settings.hot_folder).mkdir()
            for i in range(count):
                image.save(Path(settings.hot_folder) / f'art-{i:02}.png')
            rip = Rip(settings) if kind == 'cli_rip' else None
            start = time.perf_counter()
            if kind == 'cli_rip':
                processed = modules[side, 'watcher'].run_once(settings, rip, log=lambda _: None)
                assert processed == count
            else:
                panel_scan(modules[side, 'server'], settings, trial, count)
            elapsed = time.perf_counter() - start
            if kind == 'cli_rip':
                assert len(list(Path(settings.done_folder).glob('*.png'))) == count
                assert not list(Path(settings.error_folder).iterdir())
                files = sorted(Path(settings.output_folder).glob('*.PRT'))
                assert len(files) == count
                signature = {p.name: {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(),
                                     'metadata': json.loads(Path(str(p) + '.meta.json').read_text())} for p in files}
                key = f'{kind}_{count}'
                if key not in report['output_equivalence']:
                    report['output_equivalence'][key] = signature
                assert signature == report['output_equivalence'][key]
            return elapsed

        for kind, count in (('panel_admission', 1), ('panel_admission', 16), ('cli_rip', 1), ('cli_rip', 8)):
            samples = {'baseline': [], 'candidate': []}
            for side in samples:
                run(side, kind, count, 'warmup')
            for iteration in range(args.repeat):
                order = ('baseline', 'candidate') if iteration % 2 == 0 else ('candidate', 'baseline')
                for side in order:
                    samples[side].append(run(side, kind, count, iteration))
            old, new = (statistics.median(samples[side]) for side in ('baseline', 'candidate'))
            ratios = np.array(samples['baseline']) / np.array(samples['candidate'])
            rng = np.random.default_rng(624)
            bootstrap = np.median(ratios[rng.integers(0, args.repeat, (3000, args.repeat))], axis=1)
            result = dict(raw_seconds=samples, baseline_seconds=old, candidate_seconds=new,
                          speedup=old / new, paired_bootstrap_95=[float(v) for v in np.percentile(bootstrap, [2.5, 97.5])])
            report['scenarios'][f'{kind}_{count}'] = result
            print(json.dumps({f'{kind}_{count}': result}), flush=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
