from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip


def original_thresholds(rip, height, width, y0):
    ny, nx = rip.noise.shape
    phase = y0 % ny
    ry, rx = (height + phase + ny - 1) // ny, (width + nx - 1) // nx
    tiled = np.broadcast_to(rip.noise[None, :, None, :], (ry, ny, rx, nx)).reshape(ry * ny, rx * nx)
    return tiled[phase:phase + height, :width]


@pytest.mark.parametrize('phase', [0, 253, 1025, -3])
@pytest.mark.parametrize('shape', [(1, 1), (17, 301), (257, 111), (513, 32), (256, 256)])
def test_threshold_values_and_phase_remain_exact(phase, shape):
    rip = Rip(Settings())
    source = rip.noise
    actual = rip._thresholds(*shape, phase)
    np.testing.assert_array_equal(actual, original_thresholds(rip, *shape, phase))
    assert rip.noise is source and rip._opaque_noise is source
    assert source.dtype == np.float64 and not source.flags.writeable
    if rip._threshold_noise32 is not None:
        compact = rip._threshold_noise32
        np.testing.assert_array_equal(compact, source)
        assert compact.nbytes == 256 * 256 * 4 and not compact.flags.writeable
        assert actual.dtype == np.float32
        rip._thresholds(513, 301, phase)
        assert rip._threshold_noise32 is compact
    else:
        assert actual.dtype == np.float64


@pytest.mark.parametrize('dtype', [np.float16, np.float32, np.float64])
@pytest.mark.parametrize('ratio', [.05, .4, .95])
def test_all_noise_values_and_adjacent_volumes(dtype, ratio):
    rip = Rip(Settings(small_drop_ratio=ratio))
    # Todos os 65536 limiares e seus vizinhos na precisao do volume de entrada.
    thresholds = original_thresholds(rip, 256, 512, 253)
    values = thresholds.astype(dtype)
    for offset in [-1, 0, 1]:
        volumes = np.nextafter(values, dtype(-np.inf if offset < 0 else np.inf)) if offset else values
        for inputs in [volumes * ratio, volumes * (1 - ratio) + ratio]:
            before = inputs.copy()
            expected = rip._halftone(inputs, 253, thresholds)
            np.testing.assert_array_equal(rip._halftone(inputs, 253), expected)
            np.testing.assert_array_equal(inputs, before)
    assert rip._threshold_noise32.dtype == np.float32


def test_explicit_thresholds_preserve_custom_precision():
    rip = Rip(Settings())
    volumes = np.full((3, 4), .4, dtype=np.float64)
    custom = np.full((3, 4), .123456789, dtype=np.float64)
    expected = np.where(((volumes - .4) / .6) > custom, np.uint8(3), (volumes / .4 > custom).astype(np.uint8))
    np.testing.assert_array_equal(rip._halftone(volumes, 0, custom), expected)
    assert rip._threshold_noise32 is None


@pytest.mark.parametrize('hook', ['_thresholds', '_halftone', '_white_levels'])
def test_custom_methods_keep_original_dtype(hook):
    rip = Rip(Settings())
    original = getattr(rip, hook)
    setattr(rip, hook, lambda *a, **kw: original(*a, **kw))
    assert rip._thresholds(513, 301, 253).dtype == np.float64
    assert rip._threshold_noise32 is None


@pytest.mark.parametrize('writable', [False, True])
def test_replaced_noise_keeps_original_precision(writable):
    rip = Rip(Settings())
    rip.noise = np.full((256, 256), .123456789)
    rip.noise.setflags(write=writable)
    actual = rip._thresholds(513, 301, 253)
    assert actual.dtype == np.float64 and rip._threshold_noise32 is None
    np.testing.assert_array_equal(actual, original_thresholds(rip, 513, 301, 253))


def test_nonrepresentable_pinned_noise_is_never_rounded():
    rip = Rip(Settings())
    rip.noise = rip._opaque_noise = np.full((256, 256), .123456789)
    rip.noise.setflags(write=False)
    for _ in range(2):
        actual = rip._thresholds(513, 301, 253)
        assert actual.dtype == np.float64 and rip._threshold_noise32 is False
        np.testing.assert_array_equal(actual, original_thresholds(rip, 513, 301, 253))


def test_single_period_has_no_copy_and_opaque_ranks_still_work():
    rip = Rip(Settings())
    actual = rip._thresholds(7, 9, 0)
    assert np.shares_memory(actual, rip.noise) and rip._threshold_noise32 is None
    rip._thresholds(513, 301, 253)
    ranks = rip._threshold_ranks(513, 301, 253)
    np.testing.assert_array_equal((ranks.astype(np.float64) + .5) / 65536,
                                  original_thresholds(rip, 513, 301, 253))
    assert rip.noise is rip._opaque_noise


@pytest.mark.parametrize('ratio', [.05, .4, .95])
@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('workers', [1, 4])
def test_full_transparent_rip_is_identical(tmp_path, monkeypatch, ratio, icc, workers):
    pixels = np.random.default_rng(87).integers(0, 256, (512, 768, 4), dtype=np.uint8)
    source = tmp_path / 'source.png'
    with Image.fromarray(pixels) as image:
        image.save(source)
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    settings = Settings(dpi_x=720, dpi_y=1200, white_enabled=True, label_enabled=True,
                        icc_path=str(profile) if icc else '', small_drop_ratio=ratio,
                        margin_top_in=.12, margin_bottom_in=.12, mirror=True,
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7],
                        ink_limit=dict(C=35.5, M=0, Y=88.25, K=100))
    monkeypatch.setattr(engine, '_available_cpu_count', lambda: workers)
    baseline, candidate = Rip(settings), Rip(settings)
    baseline._thresholds = lambda *a: original_thresholds(baseline, *a)
    first = baseline.process(str(source), str(tmp_path / 'old.PRT'), width_cm=5.08)
    second = candidate.process(str(source), str(tmp_path / 'new.PRT'), width_cm=5.08)
    a, b = first.pop('output_path'), second.pop('output_path')
    assert Path(a).read_bytes() == Path(b).read_bytes() and first == second
    assert candidate._threshold_noise32.dtype == np.float32
