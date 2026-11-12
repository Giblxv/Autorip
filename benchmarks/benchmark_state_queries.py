"""Consulta HTTP real de estado, com outbox fixa e workers novos por amostra."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location('autorip._state_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def worker(args):
    integration = load(args.integration, 'integration')
    server = load(args.server, 'server')
    server.integrations = integration
    os.environ['AUTORIP_HOME'] = str(args.home)
    os.environ['AUTORIP_BIND_HOST'] = '127.0.0.1'
    os.environ.pop('AUTORIP_ALLOWED_HOSTS', None)

    class App(server.App):
        def _worker(self):
            pass
        def _watch(self):
            pass

    app = App()
    app.tokens.add('benchmark-only')
    app.log_lines = []
    server.APP = app
    http = ThreadingHTTPServer(('127.0.0.1', 0), server.H)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{http.server_address[1]}/api/state'
    decodes = [0]
    original = integration.outbox_load

    def tracked(home):
        decodes[0] += 1
        return original(home)

    integration.outbox_load = tracked
    outputs = []
    try:
        cold_started = time.perf_counter()
        with urlopen(Request(url, headers={'X-Token': 'benchmark-only'}), timeout=30) as response:
            data = response.read()
            assert response.status == 200
        cold_seconds = time.perf_counter() - cold_started
        outputs.append(hashlib.sha256(data).hexdigest())
        cold_decodes = decodes[0]
        seconds = []
        cpu_start = time.process_time()
        for _ in range(args.requests):
            if args.cadence:
                time.sleep(args.cadence)
            started = time.perf_counter()
            with urlopen(Request(url, headers={'X-Token': 'benchmark-only'}), timeout=30) as response:
                data = response.read()
                assert response.status == 200
            seconds.append(time.perf_counter() - started)
            outputs.append(hashlib.sha256(data).hexdigest())
        assert len(set(outputs)) == 1
        result = dict(seconds=seconds, median_seconds=statistics.median(seconds),
                      cold_seconds=cold_seconds, cpu_seconds=time.process_time() - cpu_start,
                      steady_decodes=decodes[0] - cold_decodes,
                      response_sha256=outputs[0], pending=json.loads(data)['pending'])
        print(json.dumps(result))
    finally:
        http.shutdown(); http.server_close(); thread.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true')
    parser.add_argument('--server', type=Path); parser.add_argument('--integration', type=Path)
    parser.add_argument('--home', type=Path); parser.add_argument('--baseline-ref', default='v0.8.22')
    parser.add_argument('--output', type=Path); parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--requests', type=int, default=12); parser.add_argument('--seed', type=int, default=20261111)
    parser.add_argument('--aa', action='store_true')
    parser.add_argument('--cadence', type=float, default=0)
    parser.add_argument('--only', type=int, nargs='+')
    args = parser.parse_args()
    if args.worker:
        return worker(args)
    assert args.output and args.repeat >= 3 and args.requests >= 5
    assert args.cadence >= 0
    commit = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    report = dict(baseline_ref=commit, repeat=args.repeat, requests=args.requests, aa=args.aa,
                  python=platform.python_version(), benchmark_sha256=sha(__file__),
                  cadence_seconds=args.cadence,
                  scope='Sequential authenticated HTTP /api/state; fresh process per side/trial; one cold request separate from steady requests',
                  sampling='Random paired order, all samples retained; no notifications sent; imports/setup excluded', scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-state-bench-') as directory:
        folder = Path(directory); sources = {}
        for name in ['server', 'integrations']:
            baseline = folder / (name + '.py')
            baseline.write_bytes(subprocess.check_output(['git', 'show', f'{commit}:autorip/{name}.py'], cwd=ROOT))
            sources[name] = [baseline, baseline if args.aa else ROOT / 'autorip' / (name + '.py')]
        report['source_sha256'] = {name: [sha(p) for p in paths] for name, paths in sources.items()}
        rng = random.Random(args.seed)
        for count in [-1, 0, 32, 2000, 10000]:
            if args.only and count not in args.only:
                continue
            home = folder / str(count); home.mkdir()
            config = dict(auto_mode=False, auto_update=False, offline_mode=True, label_enabled=False)
            for name in ['hot_folder', 'output_folder', 'printed_folder', 'done_folder', 'error_folder']:
                path = home / name; path.mkdir(); config[name] = str(path)
            (home / 'autorip.json').write_text(json.dumps(config))
            if count >= 0:
                items = [dict(id=f'notice-{i}', job_id=f'job-{i}', job=dict(name=f'arte-{i}.png', out=f'arte-{i}.PRT'),
                              info=dict(width_cm=58.0, height_cm=82.0, n_dots=16441, n_rows=77480),
                              sent=[], required=['webhook', 'Trello']) for i in range(count)]
                (home / 'outbox.json').write_text(json.dumps(items))
            samples = [[], []]; oracle = None
            for _ in range(args.repeat):
                order = [0, 1]; rng.shuffle(order)
                for side in order:
                    value = json.loads(subprocess.check_output([
                        sys.executable, str(Path(__file__).resolve()), '--worker',
                        '--server', str(sources['server'][side]), '--integration', str(sources['integrations'][side]),
                        '--home', str(home), '--requests', str(args.requests),
                        '--cadence', str(args.cadence)], text=True,
                        timeout=max(90, args.requests * args.cadence + 60)))
                    assert value['pending'] == max(0, count)
                    if oracle is None: oracle = value['response_sha256']
                    assert value['response_sha256'] == oracle
                    samples[side].append(value)
            medians = [statistics.median(v['median_seconds'] for v in group) for group in samples]
            result = dict(samples=samples, median_seconds=medians, speedup=medians[0] / medians[1],
                          response_sha256=oracle)
            report['scenarios'][str(count)] = result
            print(json.dumps(dict(count=count, speedup=result['speedup'], medians=medians)), flush=True)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
        assert report['source_sha256'] == {name: [sha(p) for p in paths] for name, paths in sources.items()}
    report['complete'] = True
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
