from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageCms

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip


def reference_cmyk(rip, rgb):
    color = ImageCms.applyTransform(rgb, rip.transform) if rip.transform is not None else rgb.convert('CMYK')
    values = np.asarray(color, dtype=np.float32) / 255.0
    limits = [rip.s.ink_limit.get(key, 100) / 100 for key in 'CMYK']
    if rip.transform is None and all(value == 1.0 for value in limits):
        return values
    values *= np.asarray(limits, dtype=np.float32)
    return np.clip(values, 0, 1, out=values)


@pytest.mark.parametrize('shape', [(1, 256), (256, 1), (16, 16), (512, 1024)])
@pytest.mark.parametrize('with_transform', [False, True])
@pytest.mark.parametrize('limits', [dict(C=100, M=100, Y=100, K=100),
                                   dict(C=0, M=35.5, Y=88.25, K=100),
                                   dict(C=.01, M=99.99, Y=.3333, K=72.125)])
def test_all_256_bytes_are_bit_exact_after_limits(shape, with_transform, limits, monkeypatch):
    values = np.arange(256, dtype=np.uint8)
    pixels = np.resize(np.stack([values, np.roll(values, 67), values[::-1], np.roll(values, 139)], axis=-1), (*shape, 4))
    color = Image.fromarray(pixels, 'CMYK')
    before = color.tobytes()
    class Source:
        def convert(self, mode):
            assert mode == 'CMYK'
            return color
    source = Source()
    rip = Rip(Settings(ink_limit=limits))
    if with_transform:
        transform = object()
        rip.transform = transform
        def apply(image, selected):
            assert image is source and selected is transform
            return color
        monkeypatch.setattr(engine.ImageCms, 'applyTransform', apply)
    try:
        expected = pixels.astype(np.float32) / 255.0
        expected *= np.asarray([limits[key] / 100 for key in 'CMYK'], dtype=np.float32)
        np.clip(expected, 0, 1, out=expected)
        actual = rip._to_cmyk(source)
        assert actual.dtype == np.float32 and actual.shape == (*shape, 4)
        assert actual.flags.c_contiguous and actual.flags.writeable and actual.flags.owndata
        np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))
        actual[...] = 0
        assert color.tobytes() == before
    finally:
        color.close()


@pytest.mark.parametrize('workers', [1, 4])
@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('alpha', [False, True])
@pytest.mark.parametrize('custom_limits', [False, True])
def test_complete_rip_preserves_bytes_in_large_and_small_float_paths(tmp_path, monkeypatch, workers, icc, alpha, custom_limits):
    pixels = np.random.default_rng(4000).integers(0, 256, (512, 768, 4 if alpha else 3), dtype=np.uint8)
    source = tmp_path / 'source.png'
    with Image.fromarray(pixels) as image:
        image.save(source)
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    options = dict(ink_limit=dict(C=35.5, M=0, Y=88.25, K=100)) if custom_limits else {}
    settings = Settings(dpi_x=720, dpi_y=1200, white_enabled=True, label_enabled=True,
                        icc_path=str(profile) if icc else '', white_density=.45,
                        margin_top_in=.12, margin_bottom_in=.12, mirror=True,
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7], **options)
    monkeypatch.setattr(engine, '_available_cpu_count', lambda: workers)
    baseline, candidate = Rip(settings), Rip(settings)
    baseline._to_cmyk = lambda rgb: reference_cmyk(baseline, rgb)
    calls = []
    original = candidate._to_cmyk
    def observed(rgb):
        calls.append(True)
        return original(rgb)
    candidate._to_cmyk = observed
    # RGB pequeno usa o caminho float32; RGBA maior tambem exercita quatro workers.
    width = 5.08 if alpha else 1.27
    first = baseline.process(str(source), str(tmp_path / 'old.PRT'), width_cm=width)
    second = candidate.process(str(source), str(tmp_path / 'new.PRT'), width_cm=width)
    a, b = first.pop('output_path'), second.pop('output_path')
    assert calls and Path(a).read_bytes() == Path(b).read_bytes() and first == second


@pytest.mark.parametrize('large', [False, True])
def test_direct_float32_division_is_selected_only_for_large_regions(large, monkeypatch):
    shape = (512, 1024, 4) if large else (16, 16, 4)
    pixels = np.resize(np.arange(256, dtype=np.uint8), shape)
    color = Image.fromarray(pixels, 'CMYK')
    class Source:
        def convert(self, mode):
            assert mode == 'CMYK'
            return color
    rip = Rip(Settings())
    original = engine.np.divide
    calls = []
    def observed(values, denominator, **options):
        calls.append((values.dtype, denominator, options.get('dtype')))
        return original(values, denominator, **options)
    monkeypatch.setattr(engine.np, 'divide', observed)
    try:
        actual = rip._to_cmyk(Source())
        expected = pixels.astype(np.float32) / 255.0
        np.testing.assert_array_equal(actual.view(np.uint32), expected.view(np.uint32))
        assert calls == [(np.dtype('uint8'), np.float32(255), np.float32)] if large else not calls
    finally:
        color.close()
