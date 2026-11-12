"""Batch proposals must preserve geometry, custom hooks, color order and white."""
from pathlib import Path
import sys
import zipfile

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'benchmarks'))
import rip_campaign as campaign
from rip_color_candidates import CANDIDATES
from autorip.config import Settings


def bundle():
    with zipfile.ZipFile(ROOT / 'tests/fixtures/rip-tuning-baseline.zip') as archive:
        return {key: archive.read(key + '.py').decode('utf-8') for key in campaign.FILES}


@pytest.mark.parametrize('name,hypothesis,proposal', CANDIDATES)
@pytest.mark.parametrize('mode', ['RGB', 'RGBA'])
def test_color_batch_keeps_rendered_planes(tmp_path, name, hypothesis, proposal, mode):
    original = bundle()
    base = campaign.load(original, tmp_path / 'base', 'base_color')
    candidate = campaign.load(proposal(original), tmp_path / 'candidate', 'candidate_color')
    settings = Settings(channel_order=['K', 'Y', 'C', 'M'], white_fill_holes_mm=0,
                        white_choke_mm=0, white_density=.73, mirror=True)
    a, b = (m['engine'].Rip(settings) for m in (base, candidate))
    rng = np.random.default_rng(123)
    pixels = rng.integers(0, 256, (281, 41, 4), dtype=np.uint8)
    image = Image.fromarray(pixels[..., :3] if mode == 'RGB' else pixels, mode)
    try:
        # More than 256 rows exercises every actual chunk boundary; margin and
        # overlapping labels exercise cropped planes and K-plane mutation.
        labels = [(16, 3, np.ones((7, 5), dtype=bool))]
        for start, end in ((0, 280), (9, 279)):
            expected = a._render(image, start, end, 12, 257, 47, labels)
            actual = b._render(image, start, end, 12, 257, 47, labels)
            assert all(np.array_equal(x, y) for x, y in zip(expected, actual))
    finally:
        image.close()


def test_custom_halftone_still_receives_two_dimensional_planes(tmp_path):
    module = campaign.load(CANDIDATES[0][2](bundle()), tmp_path, 'custom_color')
    rip = module['engine'].Rip(Settings(white_enabled=False))
    calls = []
    def custom(values, y0, thresholds=None):
        assert values.ndim == 2
        calls.append(values.shape)
        return np.ones(values.shape, dtype=np.uint8)
    rip._halftone = custom
    image = Image.new('RGB', (7, 9), 'red')
    try:
        planes = rip._render(image, 0, 9, 0, 9, 7, [])
        assert len(calls) == 4
        assert all(np.all(plane == 1) for plane in planes[:4])
    finally:
        image.close()


@pytest.mark.parametrize('name,hypothesis,proposal', CANDIDATES)
def test_each_strategy_executes_its_batch_plan(tmp_path, monkeypatch, name, hypothesis, proposal):
    module = campaign.load(proposal(bundle()), tmp_path, 'observed_batch')
    cls = module['engine'].Rip
    original = cls._halftone
    shapes = []
    def observed(self, values, y0, thresholds=None):
        shapes.append(values.shape)
        return original(self, values, y0, thresholds)
    monkeypatch.setattr(cls, '_halftone', observed)
    monkeypatch.setattr(cls, '_builtin_halftone', observed)
    rip = cls(Settings(white_enabled=False))
    image = Image.new('RGB', (41, 281), (80, 120, 190))
    try:
        rip._render(image, 0, 280, 12, 257, 47, [])
    finally:
        image.close()
    strategy = name.removeprefix('color-batch-')
    if strategy == 'interleaved':
        assert shapes == [(257, 47, 4)]
    elif strategy == 'planar':
        assert shapes == [(4, 257, 47)]
    else:
        rows = int(strategy.split('-')[1])
        assert shapes == [(min(rows, 257-start), 47, 4) for start in range(0, 257, rows)]
