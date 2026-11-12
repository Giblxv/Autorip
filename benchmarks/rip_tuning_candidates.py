"""Bounded scheduling search; equivalent execution plans never count as rounds."""
import hashlib
import json
import os
import random
import re
import textwrap
from types import SimpleNamespace

from PIL import Image


def tune(bundle, workers, strip, threshold):
    source = bundle['engine']
    for name, value in [('RENDER_WORKERS_MAX', workers), ('STRIP', strip)]:
        source, count = re.subn(rf'^{name} = \d+[^\n]*', f'{name} = {value}', source, flags=re.M)
        if count != 1:
            return None
    source, count = re.subn(r'n_dots \* n_rows >= \d[\d_]*',
                            f'n_dots * n_rows >= {threshold}', source, count=1)
    if count != 1:
        return None
    return dict(bundle, engine=source) if source != bundle['engine'] else None


def geometry(case, module):
    with Image.open(case['path']) as image:
        width, height = image.size
        orientation = Image.Image.getexif(image).get(274, 1)
        dpi = image.info.get('dpi', (module.DEFAULT_SOURCE_DPI, module.DEFAULT_SOURCE_DPI))
        try:
            dx, dy = dpi[0], dpi[1]
        except (IndexError, TypeError):
            dx = dy = module.DEFAULT_SOURCE_DPI
        dx, dy = module._safe_source_dpi(dx), module._safe_source_dpi(dy)
        if orientation in (5, 6, 7, 8):
            width, height, dx, dy = height, width, dy, dx
    settings = case['settings']
    dots = int(round(case['width'] / 2.54 * settings.dpi_x))
    art_rows = int(round(((height / dy) / (width / dx)) * case['width'] / 2.54 * settings.dpi_y))
    top = int(round(settings.margin_top_in * settings.dpi_y))
    bottom = int(round(settings.margin_bottom_in * settings.dpi_y))
    return dict(n_dots=dots, art_rows=art_rows, n_rows=top + art_rows + bottom)


def execution_plan(bundle, module, cases):
    """Run the actual planning statements with raster preparation replaced by identity.

    This deliberately includes any accepted wide-worker cap after preparation.
    It allocates no image planes and does not time the proposal.
    """
    source = bundle['engine']
    start = source.index('            fill_rows =', source.index('    def process('))
    stop = source.index('            fd, tmp_path = tempfile.mkstemp(', start)
    code = compile(textwrap.dedent(source[start:stop]), '<actual-rip-planning>', 'exec')
    plans = []
    original_cpu = os.cpu_count
    try:
        for case in cases:
            os.cpu_count = (lambda: case['cpu_limit']) if case.get('cpu_limit') else original_cpu
            values = dict(geometry(case, module), s=case['settings'], im=None,
                          self=SimpleNamespace(s=case['settings'], _prepare_resampling=lambda im, *_: im))
            exec(code, dict(module.__dict__), values)
            plans.append(dict(name=case['name'], workers=values['workers'],
                              strip_rows=values['strip_rows'], halo=values['halo'],
                              n_dots=values['n_dots'], n_rows=values['n_rows']))
    finally:
        os.cpu_count = original_cpu
    checksum = hashlib.sha256(json.dumps(plans, sort_keys=True).encode()).hexdigest()
    return checksum, plans


def _candidates():
    configurations = [(w, s, t) for w in (1, 2, 3, 4)
                      for s in (64, 96, 128, 160, 192, 256, 320, 384, 512, 640, 768, 1024, 1536)
                      for t in (100000, 1000000, 1500000, 2000000, 4000000, 8000000, 12000000)]
    random.Random(20261112).shuffle(configurations)
    for workers, strip, threshold in configurations:
        def proposal(bundle, w=workers, s=strip, t=threshold):
            return tune(bundle, w, s, t)
        proposal.is_scheduling_tuning = True
        name = f'tune-w{workers}-s{strip}-t{threshold}'
        hypothesis = f'Avaliar {workers} trabalhadores, tiras de {strip} linhas e limiar de {threshold} pixels'
        yield name, hypothesis, proposal


CANDIDATES = list(_candidates())
