from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip


def original_selection(small, large):
    return np.where(large, np.uint8(3), small.astype(np.uint8))


def test_all_four_boolean_combinations_include_large_without_small():
    small = np.array([[False, False], [True, True]])
    large = np.array([[False, True], [False, True]])
    np.testing.assert_array_equal(Rip._drop_levels(small, large), [[0, 3], [1, 3]])


@pytest.mark.parametrize('shape', [(), (0,), (1, 1), (31, 33), (512, 513)])
@pytest.mark.parametrize('layout', ['C', 'F', 'strided', 'reverse', 'broadcast'])
def test_layouts_are_exact_readonly_and_independent(shape, layout):
    rng = np.random.default_rng(3903)
    if layout == 'strided' and shape:
        backing = tuple(n * 2 for n in shape)
        small = (rng.random(backing) > .35)[tuple(slice(None, None, 2) for _ in shape)]
        large = (rng.random(backing) > .65)[tuple(slice(None, None, 2) for _ in shape)]
    else:
        small, large = rng.random(shape) > .35, rng.random(shape) > .65
        small, large = np.asarray(small), np.asarray(large)
        if layout == 'F':
            small, large = np.array(small, order='F'), np.array(large, order='F')
        elif layout == 'reverse' and shape:
            small, large = small[..., ::-1], large[..., ::-1]
        elif layout == 'broadcast':
            small, large = np.broadcast_to(True, shape), np.broadcast_to(False, shape)
    first, second = small.copy(), large.copy()
    small.setflags(write=False)
    large.setflags(write=False)
    actual = Rip._drop_levels(small, large)
    np.testing.assert_array_equal(actual, original_selection(small, large))
    assert actual.shape == shape and actual.dtype == np.uint8 and actual.flags.writeable
    assert not np.shares_memory(actual, small) and not np.shares_memory(actual, large)
    actual[...] = 2
    np.testing.assert_array_equal(small, first)
    np.testing.assert_array_equal(large, second)


def test_noncanonical_boolean_bytes_match_numpy_selection():
    values = np.array([0, 1, 2, 3, 127, 128, 255], dtype=np.uint8)
    small = np.tile(values, (257, 1)).view(np.bool_)
    large = small[:, ::-1]
    np.testing.assert_array_equal(Rip._drop_levels(small, large), original_selection(small, large))


def test_masked_boolean_arrays_keep_where_data_semantics():
    small = np.ma.array([True, False, True, False], mask=[True, False, True, False])
    large = np.ma.array([False, True, True, False], mask=[False, True, False, True])
    actual = Rip._drop_levels(small, large)
    assert type(actual) is np.ndarray
    np.testing.assert_array_equal(actual, original_selection(small, large))


@pytest.mark.parametrize('dtype', [np.float16, np.float32, np.float64])
@pytest.mark.parametrize('ratio', [.05, .4, .95, np.float64(.4000000001)])
def test_halftone_preserves_arbitrary_thresholds_nan_and_ratio(dtype, ratio):
    rip = Rip(Settings())
    rip.s.small_drop_ratio = ratio
    volumes = np.random.default_rng(3904).uniform(-1, 2, (31, 33)).astype(dtype)
    volumes.flat[:5] = [0, 1, -np.inf, np.inf, np.nan]
    thresholds = np.random.default_rng(3905).uniform(-2, 2, volumes.shape)
    thresholds.flat[:5] = [0, 1, np.nan, -np.inf, np.inf]
    before = volumes.copy()
    with np.errstate(invalid='ignore', over='ignore'):
        small = (volumes / ratio) > thresholds
        large = ((volumes - ratio) / (1 - ratio)) > thresholds
        expected = original_selection(small, large)
        actual = rip._halftone(volumes, -3, thresholds)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(volumes, before)
    assert actual.dtype == np.uint8


@pytest.mark.parametrize('workers', [1, 4])
@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('alpha', [False, True])
@pytest.mark.parametrize('ratio', [.05, .95])
def test_full_rip_has_identical_bytes_with_selection_active(tmp_path, monkeypatch, workers, icc, alpha, ratio):
    shape = (512, 768, 4 if alpha else 3)
    pixels = np.random.default_rng(3906).integers(0, 256, shape, dtype=np.uint8)
    source = tmp_path / 'source.png'
    with Image.fromarray(pixels) as image:
        image.save(source)
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    settings = Settings(dpi_x=720, dpi_y=1200, white_enabled=True, label_enabled=True,
                        icc_path=str(profile) if icc else '', white_density=.45, small_drop_ratio=ratio,
                        margin_top_in=.12, margin_bottom_in=.12, mirror=True,
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7],
                        ink_limit=dict(C=35.5, M=0, Y=88.25, K=100))
    monkeypatch.setattr(engine, '_available_cpu_count', lambda: workers)
    baseline, candidate = Rip(settings), Rip(settings)
    baseline._drop_levels = original_selection
    calls = []
    original = candidate._drop_levels
    def observed(small, large):
        calls.append((small.dtype, large.dtype))
        return original(small, large)
    candidate._drop_levels = observed
    first = baseline.process(str(source), str(tmp_path / 'old.PRT'), width_cm=5.08)
    second = candidate.process(str(source), str(tmp_path / 'new.PRT'), width_cm=5.08)
    a, b = first.pop('output_path'), second.pop('output_path')
    assert calls and all(x == y == np.bool_ for x, y in calls)
    assert Path(a).read_bytes() == Path(b).read_bytes() and first == second
