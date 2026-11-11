"""RIP e prévias de 30/90 MP, conferindo decode compartilhado e saídas iguais."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import random
import statistics
import struct
import subprocess
import sys
import tempfile
import time
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
from PIL import ImageCms
from autorip.imaging import Image
from autorip.config import Settings


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location('autorip._large_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def gamma_profile():
    data = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    for index in range(struct.unpack_from('>I', data, 128)[0]):
        pos = 132 + index * 12
        if data[pos:pos + 4] == b'rTRC':
            offset = struct.unpack_from('>I', data, pos + 4)[0]
            struct.pack_into('>i', data, offset + 12, round(1.8 * 65536))
            return bytes(data)
    raise AssertionError('Perfil sem TRC paramétrica')


def png(path, size, mode, profile=b'', orientation=1):
    """Gera linhas variadas sem materializar um raster gigante no processo pai."""
    width, height = size
    x = np.arange(width, dtype=np.uint32)
    channels = {'RGB': 3, 'RGBA': 4, 'L': 1}[mode]
    pixels = np.empty((width, channels), np.uint8)
    with path.open('wb') as stream:
        stream.write(b'\x89PNG\r\n\x1a\n')

        def chunk(kind, data):
            stream.write(struct.pack('>I', len(data)) + kind + data)
            stream.write(struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))

        chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, {'L': 0, 'RGB': 2, 'RGBA': 6}[mode], 0, 0, 0))
        chunk(b'pHYs', struct.pack('>IIB', round(100 / .0254), round(200 / .0254), 1))
        if profile:
            chunk(b'iCCP', b'ICC Profile\0\0' + zlib.compress(profile))
        if orientation != 1:
            exif = Image.Exif(); exif[274] = orientation
            chunk(b'eXIf', exif.tobytes()[6:])
        encoder = zlib.compressobj(level=1)
        for y in range(height):
            pixels[:, 0] = (x * 3 + y) % 256
            if channels >= 3:
                pixels[:, 1] = (x + y * 2) % 256
                pixels[:, 2] = (x * 5 + y * 3) % 256
            if channels == 4:
                pixels[:, 3] = np.linspace(0, 255, width, dtype=np.uint8)
            encoded = encoder.compress(b'\0' + pixels.tobytes())
            if encoded:
                chunk(b'IDAT', encoded)
        chunk(b'IDAT', encoder.flush())
        chunk(b'IEND', b'')


def fixtures(folder, icc):
    manifest = folder / 'cases.json'
    if manifest.exists():
        cases = json.loads(manifest.read_text())
        assert all(Path(c['path']).is_file() and sha(c['path']) == c['source_sha256'] for c in cases)
        return cases
    folder.mkdir(parents=True, exist_ok=True)
    profile = gamma_profile()
    cases = []
    settings = dict(label_enabled=False, margin_top_in=.05, margin_bottom_in=.05)

    def add(name, path, mode, size, phases, width=5.08):
        cases.append(dict(name=name, path=str(path.resolve()), mode=mode, source_size=list(size),
                          source_sha256=sha(path), source_bytes=path.stat().st_size,
                          width_cm=width, phases=phases, settings=settings))

    big = (10000, 9000)
    for name, mode, embedded, orientation, phases in [
        ('rgb_icc_90mp', 'RGB', profile, 1, ['rip', 'preview', 'job']),
        ('rgba_icc_90mp', 'RGBA', profile, 1, ['rip', 'job']),
        ('rgba_exif_90mp', 'RGBA', profile, 6, ['rip', 'preview', 'job']),
        ('rgba_plain_90mp', 'RGBA', b'', 1, ['rip', 'job']),
        ('rgb_plain_90mp', 'RGB', b'', 1, ['rip', 'job']),
        ('gray_90mp', 'L', b'', 1, ['preview', 'job']),
    ]:
        path = folder / (name + '.png')
        png(path, big, mode, embedded, orientation)
        add(name, path, mode, big, phases)
    jpeg = folder / 'rgb_icc_90mp.jpg'
    with Image.open(folder / 'rgb_icc_90mp.png') as source:
        source.save(jpeg, quality=90, icc_profile=profile, dpi=(100, 200))
    add('jpeg_icc_90mp', jpeg, 'RGB', big, ['job'])
    add('wide_rgb_icc_90mp', folder / 'rgb_icc_90mp.png', 'RGB', big, ['job'], width=10.16)

    small = folder / 'rgb_small.png'
    png(small, (320, 240), 'RGB', profile)
    add('small_rgb_icc', small, 'RGB', (320, 240), ['job'], width=1.27)
    medium = (6000, 5000)
    rgb = folder / 'rgb_30mp.png'
    png(rgb, medium, 'RGB', ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    with Image.open(rgb) as source:
        for mode, output_profile in [('LAB', ImageCms.ImageCmsProfile(ImageCms.createProfile('LAB')))] + (
                [('CMYK', ImageCms.getOpenProfile(str(icc)))] if icc else []):
            path = folder / (mode.lower() + '_30mp.tif')
            converted = ImageCms.profileToProfile(source, ImageCms.createProfile('sRGB'), output_profile, outputMode=mode)
            try:
                converted.save(path, icc_profile=output_profile.tobytes(), dpi=(100, 200))
            finally:
                converted.close()
            add(mode.lower() + '_icc_30mp', path, mode, medium, ['rip'] if mode == 'LAB' else ['rip', 'preview', 'job'])
    mapped = folder / 'mapped_rgba_30mp.tif'
    with Image.new('RGBA', medium, (100, 150, 200, 127)) as source:
        source.save(mapped, compression='raw', icc_profile=profile, dpi=(100, 200))
    add('mapped_rgba_icc_30mp', mapped, 'RGBA', medium, ['rip', 'preview', 'job'])
    for c in cases:
        with Image.open(c['path']) as image:
            c['profile_sha256'] = hashlib.sha256(image.info.get('icc_profile', b'')).hexdigest()
    manifest.write_text(json.dumps(cases, indent=2) + '\n')
    return cases


def rss():
    path = Path('/proc/self/status')
    if path.is_file():
        line = next(s for s in path.read_text().splitlines() if s.startswith('VmHWM:'))
        return int(line.split()[1]) / 1024
    return None


def worker(args):
    case = json.loads(args.case.read_text())
    engine = load(args.engine, 'engine')
    server = load(args.server, 'server')
    settings = Settings(**case['settings'])
    rip = engine.Rip(settings) if args.phase != 'preview' else None
    preview = server._SourcePreview() if args.phase == 'job' and hasattr(server, '_SourcePreview') else None
    source_opens = 0
    original_open = Image.open
    def tracked_open(file, *positional, **keywords):
        nonlocal source_opens
        if isinstance(file, (str, Path)) and str(file) == case['path']:
            source_opens += 1
        return original_open(file, *positional, **keywords)
    Image.open = tracked_open
    with tempfile.TemporaryDirectory(prefix='autorip-large-worker-') as folder:
        root = Path(folder)
        app = server.App.__new__(server.App); app.home = folder; app.s = settings
        started = time.perf_counter(); cpu_started = time.process_time()
        info = None
        if rip is not None:
            callback = dict(source_ready=preview.capture) if preview is not None else {}
            info = rip.process(case['path'], str(root / 'output.PRT'), width_cm=case['width_cm'], **callback)
        if args.phase != 'rip':
            prepared = dict(prepared=preview.take()) if preview is not None else {}
            assert app._thumb('large', case['path'], output_name='large', settings=settings, **prepared), case['name']
        seconds = time.perf_counter() - started; cpu_seconds = time.process_time() - cpu_started
        outputs = {}
        if info is not None:
            outputs['prt_sha256'] = sha(info.pop('output_path'))
            outputs['metadata'] = info
        if args.phase != 'rip':
            paths = [root / 'thumbs/large.jpg', root / 'thumbs/by_name/large.jpg']
            assert sha(paths[0]) == sha(paths[1])
            outputs['preview_sha256'] = sha(paths[0])
            with Image.open(paths[0]) as preview:
                outputs['preview_size'] = list(preview.size)
        assert sha(case['path']) == case['source_sha256'], 'A entrada foi alterada'
        print(json.dumps(dict(seconds=seconds, cpu_seconds=cpu_seconds, peak_rss_mib=rss(),
                              source_opens=source_opens, outputs=outputs)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', action='store_true'); parser.add_argument('--engine', type=Path)
    parser.add_argument('--server', type=Path); parser.add_argument('--case', type=Path); parser.add_argument('--phase')
    parser.add_argument('--baseline-ref', default='v0.8.19'); parser.add_argument('--fixtures', type=Path)
    parser.add_argument('--icc', type=Path); parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--seed', type=int, default=713); parser.add_argument('--output', type=Path)
    parser.add_argument('--only', nargs='+'); parser.add_argument('--aa', action='store_true')
    args = parser.parse_args()
    if args.worker:
        worker(args); return
    if args.output is None or args.fixtures is None or args.repeat < 3:
        parser.error('Use --output, --fixtures e pelo menos três repetições')
    commit = subprocess.check_output(['git', 'rev-parse', args.baseline_ref], cwd=ROOT, text=True).strip()
    shared = {}
    for name in ('config', 'imaging', 'prt', 'morph'):
        data = subprocess.check_output(['git', 'show', commit + ':autorip/' + name + '.py'], cwd=ROOT)
        assert data == (ROOT / 'autorip' / (name + '.py')).read_bytes(), name + ' mudou'
        shared[name] = hashlib.sha256(data).hexdigest()
    cases = fixtures(args.fixtures.resolve(), args.icc.resolve() if args.icc else None)
    rgb = next(c for c in cases if c['name'] == 'rgb_icc_90mp')
    cases.append(dict(rgb, name='large_output_rgb_90mp', width_cm=25.4, phases=['job']))
    if args.icc:
        cases.append(dict(rgb, name='output_icc_rgb_90mp', phases=['job'],
                          settings=dict(rgb['settings'], icc_path=str(args.icc.resolve())),
                          output_profile_sha256=sha(args.icc)))
    report = dict(baseline_ref=commit, repeat=args.repeat, seed=args.seed, aa_control=args.aa,
                  python=platform.python_version(), pillow=Image.__version__, numpy=np.__version__,
                  cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
                  sampling='Fresh independent process for every side/trial; randomized order; first job per Rip',
                  scope='Rip.process + optional two published JPEG previews; imports/init/verification excluded from time',
                  source_open_metric='Pillow Image.open calls for the source; excludes internal OS opens',
                  candidate_preview='Capture loaded pre-ICC RGB/RGBA/opaque gray in job phase; fallback for other modes',
                  shared_modules_sha256=shared, benchmark_sha256=sha(__file__), scenarios={})
    with tempfile.TemporaryDirectory(prefix='autorip-large-bench-') as folder:
        root = Path(folder); modules = {}; hashes = {}
        for name in ('engine', 'server'):
            path = root / ('baseline_' + name + '.py')
            path.write_bytes(subprocess.check_output(['git', 'show', commit + ':autorip/' + name + '.py'], cwd=ROOT))
            modules[name] = [path, path if args.aa else ROOT / 'autorip' / (name + '.py')]
            hashes[name] = [sha(p) for p in modules[name]]
        report['source_sha256'] = hashes
        rng = random.Random(args.seed)
        for case in cases:
            for phase in case['phases']:
                key = case['name'] + '/' + phase
                if args.only and key not in args.only:
                    continue
                case_path = root / 'case.json'; case_path.write_text(json.dumps(case))
                samples = [[], []]; oracle = None
                for trial in range(args.repeat):
                    order = [0, 1]; rng.shuffle(order)
                    for side in order:
                        raw = subprocess.check_output([sys.executable, str(Path(__file__).resolve()), '--worker',
                            '--engine', str(modules['engine'][side]), '--server', str(modules['server'][side]),
                            '--case', str(case_path), '--phase', phase], text=True, timeout=300)
                        value = json.loads(raw)
                        if oracle is None:
                            oracle = value['outputs']
                        assert value['outputs'] == oracle, key + ' divergiu'
                        samples[side].append(value)
                old, new = [statistics.median(v['seconds'] for v in group) for group in samples]
                old_cpu, new_cpu = [statistics.median(v['cpu_seconds'] for v in group) for group in samples]
                peaks = [statistics.median(v['peak_rss_mib'] for v in group) if all(v['peak_rss_mib'] is not None for v in group) else None for group in samples]
                result = dict(source=case, phase=phase, baseline_seconds=old, candidate_seconds=new,
                              speedup=old/new, cpu_speedup=old_cpu/new_cpu, peak_rss_mib=peaks,
                              samples=samples, outputs=oracle)
                report['scenarios'][key] = result
                print(json.dumps(dict(scenario=key, speedup=result['speedup'], peak_rss_mib=peaks)), flush=True)
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(report, indent=2) + '\n')
    assert report['scenarios'], 'Nenhum cenário selecionado'
    report['complete'] = True
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
