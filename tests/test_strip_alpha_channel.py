import gc
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip


def reference_alpha(strip):
    return np.asarray(strip)[..., 3]


@pytest.mark.parametrize('shape', [(1, 1), (1, 257), (257, 1), (31, 33), (512, 1440)])
@pytest.mark.parametrize('alpha_kind', ['zero', 'opaque', 'all_bytes'])
def test_alpha_values_storage_and_source_lifetime(shape, alpha_kind):
    pixels = np.random.default_rng(4200).integers(0, 256, (*shape, 4), dtype=np.uint8)
    pixels[..., 3] = (0 if alpha_kind == 'zero' else 255 if alpha_kind == 'opaque'
                      else np.arange(shape[0] * shape[1]).reshape(shape) % 256)
    strip = Image.fromarray(pixels)
    strip.info.update(icc_profile=b'profile marker', dpi=(300, 150), note={'text': 'original'})
    metadata = strip.info.copy()
    before = strip.tobytes()
    expected = reference_alpha(strip)
    actual = Rip._strip_alpha(strip)
    np.testing.assert_array_equal(actual, expected)
    assert actual.dtype == np.uint8 and actual.shape == shape
    assert actual.flags.c_contiguous and not actual.flags.writeable
    assert strip.info == metadata and strip.tobytes() == before
    strip.close()
    del strip
    gc.collect()
    np.testing.assert_array_equal(actual, expected)
    # O calculo float32 seguinte deve conservar todos os bits, nao so a tolerancia.
    np.testing.assert_array_equal((actual.astype(np.float32) / 255.0).view(np.uint32),
                                  (expected.astype(np.float32) / 255.0).view(np.uint32))


def test_transparent_strip_still_skips_color_and_white():
    rip = Rip(Settings(label_enabled=False))
    def forbidden(*args):
        raise AssertionError('faixa totalmente transparente nao precisa de cor/branco')
    rip._strip_rgb = forbidden
    rip._to_cmyk = forbidden
    rip._white_levels = forbidden
    with Image.new('RGBA', (513, 512), (127, 63, 191, 0)) as source:
        planes = rip._render(source, 0, 512, 0, 512, 513, [])
    assert len(planes) == 12 and all(not plane.any() for plane in planes)


@pytest.mark.parametrize('workers', [1, 4])
@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('file_type', ['png', 'tiff'])
def test_complete_rip_matches_full_rgba_alpha_copy(tmp_path, monkeypatch, workers, icc, mirror, file_type):
    pixels = np.random.default_rng(4201).integers(0, 256, (512, 768, 4), dtype=np.uint8)
    pixels[0, :8, 3] = [0, 1, 127, 128, 229, 230, 254, 255]
    source = tmp_path / ('source.' + file_type)
    with Image.fromarray(pixels) as image:
        image.save(source, dpi=(100, 200))
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    settings = Settings(dpi_x=720, dpi_y=1200, white_enabled=True, label_enabled=True,
                        icc_path=str(profile) if icc else '', white_density=.45,
                        margin_top_in=.12, margin_bottom_in=.12, mirror=mirror,
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7],
                        ink_limit=dict(C=35.5, M=0, Y=88.25, K=100))
    monkeypatch.setattr(engine, '_available_cpu_count', lambda: workers)
    baseline, candidate = Rip(settings), Rip(settings)
    baseline._strip_alpha = reference_alpha
    calls = []
    original = candidate._strip_alpha
    def observed(strip):
        alpha = original(strip)
        calls.append(alpha.shape)
        return alpha
    candidate._strip_alpha = observed
    first = baseline.process(str(source), str(tmp_path / 'old.PRT'), width_cm=5.08)
    second = candidate.process(str(source), str(tmp_path / 'new.PRT'), width_cm=5.08)
    a, b = first.pop('output_path'), second.pop('output_path')
    assert calls and Path(a).read_bytes() == Path(b).read_bytes() and first == second
