"""Lista da hot folder e polling HTTP com 1/4 clientes, em dados temporarios.

python benchmarks/benchmark_hot_listing.py --baseline-ref v0.8.43 --pairs 11 --output /tmp/hot-listing.json
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import itertools
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
import tracemalloc
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from benchmark_main_refinements import ratio_interval


def load(path, name):
    spec = importlib.util.spec_from_file_location('autorip._hot_listing_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def app_for(module, folder):
    app = module.App.__new__(module.App)
    app.s = SimpleNamespace(hot_folder=str(folder))
    app.settings_lock = threading.RLock()
    app.lock = threading.RLock()
    app._hot_listing_lock = threading.Lock()
    app.tokens = {'listing-' + str(i) for i in range(4)}
    return app


def orders(count, seed):
    values = list(itertools.islice(itertools.cycle(itertools.permutations(range(3))), count))
    random.Random(seed).shuffle(values)
    return values


def encoded(value):
    return json.dumps(value, separators=(',', ':')).encode()


def summarize(samples):
    values = [[statistics.median(group) for group in side] for side in samples]
    return dict(median_seconds=dict(zip(('baseline', 'candidate', 'control'), map(statistics.median, values))),
                baseline_over_candidate_ci95=ratio_interval(values[0], values[1]),
                control_over_candidate_ci95=ratio_interval(values[2], values[1]),
                baseline_over_control_ci95=ratio_interval(values[0], values[2]), samples=samples)


def http_get(url, token, tag=None):
    headers = {'X-Token': token}
    if tag:
        headers['If-None-Match'] = tag
    try:
        response = urlopen(Request(url, headers=headers), timeout=30)
    except HTTPError as error:
        response = error
    with response:
        return response.status, response.read(), response.headers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-ref', default='v0.8.43')
    parser.add_argument('--pairs', type=int, default=11)
    parser.add_argument('--calls', type=int, default=5)
    parser.add_argument('--http-pairs', type=int, default=7)
    parser.add_argument('--http-calls', type=int, default=2)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--probe', type=Path, help='Executa uma varredura para rastreamento externo de syscalls')
    parser.add_argument('--folder', type=Path)
    args = parser.parse_args()
    if args.probe:
        if not args.folder:
            parser.error('--probe exige --folder')
        module = load(args.probe, 'probe')
        result = app_for(module, args.folder).list_hot_files()
        print(json.dumps(dict(entries=len(result), sha256=hashlib.sha256(encoded(result)).hexdigest())))
        return
    if not args.output:
        parser.error('--output obrigatorio para o benchmark')
    if args.pairs < 7 or args.calls < 3 or args.http_pairs < 5 or args.http_calls < 2:
        parser.error('Use pelo menos 7 grupos diretos, 3 chamadas, 5 grupos HTTP e 2 consultas/cliente')
    before = subprocess.check_output(['git', 'show', f'{args.baseline_ref}:autorip/server.py'], cwd=ROOT)
    current = ROOT / 'autorip/server.py'
    report = dict(baseline_ref=args.baseline_ref, baseline_commit=subprocess.check_output(['git', 'rev-parse', args.baseline_ref+'^{commit}'], cwd=ROOT, text=True).strip(),
                  python=platform.python_version(), platform=platform.platform(), pairs=args.pairs,
                  calls_per_direct_group=args.calls, http_pairs=args.http_pairs, http_calls_per_client=args.http_calls,
                  source_sha256=dict(baseline=hashlib.sha256(before).hexdigest(), candidate=hashlib.sha256(current.read_bytes()).hexdigest()),
                  scope='Direct production method and authenticated HTTP 304 polling; loopback CPU includes both server and clients; imports/fixture creation excluded', direct={}, http={})
    with tempfile.TemporaryDirectory(prefix='autorip-hot-listing-') as directory:
        root = Path(directory)
        old = root / 'previous.py'; old.write_bytes(before)
        modules = [load(old, 'baseline'), load(current, 'candidate'), load(old, 'control')]
        folders = {}
        for count, ignored in ((0, 0), (100, 0), (1000, 0), (1000, 1000), (10000, 0), (10000, 10000)):
            name = f'{count}_images_{ignored}_ignored'
            folder = root / name; folder.mkdir(); folders[name] = folder
            for i in range(count):
                (folder / f'arte-{i:05}.PNG').write_bytes(b'art')
            for i in range(ignored):
                (folder / f'ignored-{i:05}.txt').write_bytes(b'ignored')
            apps = [app_for(module, folder) for module in modules]
            expected = apps[0].list_hot_files()
            oracle = encoded(expected)
            for app in apps:
                assert encoded(app.list_hot_files()) == oracle
            samples = [[], [], []]
            cpu = [[], [], []]
            for order in orders(args.pairs, count + ignored + 44):
                for side in order:
                    values = []; cpu_values = []
                    for _ in range(args.calls):
                        cpu_start = time.process_time(); start = time.perf_counter()
                        result = apps[side].list_hot_files()
                        elapsed = time.perf_counter() - start; cpu_elapsed = time.process_time() - cpu_start
                        assert result == expected
                        values.append(elapsed); cpu_values.append(cpu_elapsed)
                    samples[side].append(values); cpu[side].append(cpu_values)
            peaks = []
            for app in apps:
                tracemalloc.start(); result = app.list_hot_files()
                peaks.append(tracemalloc.get_traced_memory()[1]); tracemalloc.stop()
            result = summarize(samples)
            result.update(cpu=summarize(cpu), traced_peak_bytes=dict(zip(('baseline', 'candidate', 'control'), peaks)),
                          response_sha256=hashlib.sha256(oracle).hexdigest(), entries=count, outputs_equal=True)
            report['direct'][name] = result
            print('direct', name, result['median_seconds'], flush=True)
        os.environ['AUTORIP_BIND_HOST'] = '127.0.0.1'
        os.environ.pop('AUTORIP_ALLOWED_HOSTS', None)
        for count in (1000, 10000):
            folder = folders[f'{count}_images_{count}_ignored']
            apps = [app_for(module, folder) for module in modules]
            servers = []; threads = []
            try:
                for module, app in zip(modules, apps):
                    module.APP = app
                    http = ThreadingHTTPServer(('127.0.0.1', 0), module.H)
                    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start()
                    servers.append(http); threads.append(thread)
                urls = [f'http://127.0.0.1:{http.server_port}/api/hot-files' for http in servers]
                tags = []; oracle = None
                for url in urls:
                    status, body, headers = http_get(url, 'listing-0')
                    assert status == 200
                    if oracle is None:
                        oracle = body
                    assert body == oracle
                    tags.append(headers['ETag'])
                assert len(set(tags)) == 1
                for clients in (1, 4):
                    samples = [[], [], []]; cpu = [[], [], []]
                    with ThreadPoolExecutor(max_workers=clients) as pool:
                        for order in orders(args.http_pairs, count + clients):
                            for side in order:
                                def run_client(index):
                                    values = []
                                    for _ in range(args.http_calls):
                                        start = time.perf_counter()
                                        status, body, headers = http_get(urls[side], 'listing-'+str(index), tags[side])
                                        values.append(time.perf_counter() - start)
                                        assert status == 304 and not body and headers['ETag'] == tags[side]
                                    return values
                                cpu_start = time.process_time()
                                values = list(pool.map(run_client, range(clients)))
                                cpu[side].append([time.process_time() - cpu_start])
                                samples[side].append([value for group in values for value in group])
                    result = summarize(samples)
                    result.update(batch_cpu=summarize(cpu), clients=clients, status=304, response_bytes=0,
                                  response_sha256=hashlib.sha256(oracle).hexdigest(), outputs_equal=True)
                    name = f'{count}_images_{clients}_clients'
                    report['http'][name] = result
                    print('http', name, result['median_seconds'], flush=True)
            finally:
                for http in servers:
                    http.shutdown(); http.server_close()
                for thread in threads:
                    thread.join()
    assert hashlib.sha256(current.read_bytes()).hexdigest() == report['source_sha256']['candidate']
    report['complete'] = True
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
