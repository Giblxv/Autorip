from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip


@pytest.mark.parametrize('density', [0, .05, .45, 1.])
@pytest.mark.parametrize('threshold', [.0001, .02, .9, 1.])
@pytest.mark.parametrize('shape', [(1, 301), (301, 1), (273, 301)])
def test_boolean_alpha_matches_float32_with_holes_and_choke(density, threshold, shape):
    rip = Rip(Settings(dpi_x=300, dpi_y=720, white_density=density,
                       white_alpha_threshold=threshold))
    alpha = np.random.default_rng(88).random(shape) > .35
    before = alpha.copy()
    expected = rip._white_levels(alpha.astype(np.float32), 253)
    np.testing.assert_array_equal(rip._white_levels(alpha, 253), expected)
    np.testing.assert_array_equal(alpha, before)


@pytest.mark.parametrize('density', [.05, .45, 1.])
@pytest.mark.parametrize('threshold', [0, .02, 1.])
def test_explicit_thresholds_and_custom_halftone_receive_identical_volumes(density, threshold):
    rip = Rip(Settings(dpi_x=300, dpi_y=300, white_density=density,
                       white_alpha_threshold=threshold))
    alpha = np.zeros((273, 301), dtype=bool)
    alpha[25:250, 35:265] = True
    alpha[99:101, 99:101] = False
    screen = np.random.default_rng(88).random(alpha.shape)
    expected = rip._white_levels(alpha.astype(np.float32), -3, screen)
    np.testing.assert_array_equal(rip._white_levels(alpha, -3, screen), expected)
    original = rip._halftone
    volumes = []
    def observed(values, y0, thresholds=None):
        volumes.append(values.copy())
        return original(values, y0, thresholds)
    rip._halftone = observed
    rip._white_levels(alpha.astype(np.float32), -3, screen)
    rip._white_levels(alpha, -3, screen)
    np.testing.assert_array_equal(volumes[0], volumes[1])
    assert volumes[0].dtype == volumes[1].dtype == np.float32


@pytest.mark.parametrize('density', [0, .45, 1.])
@pytest.mark.parametrize('threshold', [0, .02, 1.])
def test_render_uses_binary_alpha_only_for_builtin_white(density, threshold):
    rip = Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False,
                       white_density=density, white_alpha_threshold=threshold))
    image = Image.new('RGB', (301, 273), (45, 123, 211))
    baseline = rip._render(image, 0, 301, 11, 273, 301, [])
    calls = []
    original = rip._white_levels
    def custom(alpha, *args, **kwargs):
        calls.append(alpha.dtype)
        return original(alpha, *args, **kwargs)
    rip._white_levels = custom
    actual = rip._render(image, 0, 301, 11, 273, 301, [])
    for first, second in zip(baseline, actual):
        np.testing.assert_array_equal(first, second)
    assert calls == [np.dtype('float32')]
    image.close()


@pytest.mark.parametrize('workers', [1, 4])
@pytest.mark.parametrize('density', [0, .45, 1.])
@pytest.mark.parametrize('icc', [False, True])
def test_full_rgb_rip_is_identical_with_binary_white_active(tmp_path, monkeypatch, workers, density, icc):
    pixels = np.random.default_rng(88).integers(0, 256, (512, 768, 3), dtype=np.uint8)
    source = tmp_path / 'source.png'
    with Image.fromarray(pixels) as image:
        image.save(source)
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    settings = Settings(dpi_x=720, dpi_y=1200, white_enabled=True, label_enabled=True,
                        icc_path=str(profile) if icc else '', white_density=density,
                        margin_top_in=.12, margin_bottom_in=.12, mirror=True,
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7],
                        ink_limit=dict(C=35.5, M=0, Y=88.25, K=100))
    monkeypatch.setattr(engine, '_available_cpu_count', lambda: workers)
    baseline, candidate = Rip(settings), Rip(settings)
    # Preserve o dtype float64 do plano de limiares da base quando o hook de
    # branco desativa a compactacao da 0.8.37. Os valores continuam identicos.
    old_white = baseline._white_levels
    baseline._white_levels = lambda *a, **kw: old_white(*a, **kw)
    calls = []
    original_binary = candidate._binary_white_levels
    def observed(mask, *args):
        calls.append(mask.dtype)
        return original_binary(mask, *args)
    candidate._binary_white_levels = observed
    first = baseline.process(str(source), str(tmp_path / 'old.PRT'), width_cm=5.08)
    second = candidate.process(str(source), str(tmp_path / 'new.PRT'), width_cm=5.08)
    a, b = first.pop('output_path'), second.pop('output_path')
    assert Path(a).read_bytes() == Path(b).read_bytes() and first == second
    assert calls and all(dtype == np.bool_ for dtype in calls) if density else not calls


@pytest.mark.parametrize('ratio', [.05, .4, .95, np.float64(.4000000001)])
@pytest.mark.parametrize('layout', ['full', 'empty', 'strided'])
def test_uniform_probabilities_match_all_thresholds_and_adjacent_densities(ratio, layout):
    rip = Rip(Settings(small_drop_ratio=ratio))
    rip.s.small_drop_ratio = ratio
    if layout == 'full':
        mask = np.ones((256, 512), dtype=bool)
    elif layout == 'empty':
        mask = np.zeros((256, 512), dtype=bool)
    else:
        mask = (np.random.default_rng(8800).random((256, 1024)) > .5)[:, ::2]
    before = mask.copy()
    mask.setflags(write=False)
    noise = rip.noise
    phase = 253
    original = np.tile(noise, (2, 2))[phase:phase + 256, :512]
    thresholds = (np.array([0, 1, 1390, 32767, 65535]) + .5) / 65536
    densities = [0., .05, .45, 1.]
    for value in np.concatenate([thresholds * ratio, ratio + thresholds * (1 - ratio)]):
        center = np.float32(value)
        densities.extend([float(np.nextafter(center, np.float32(-np.inf))), float(center),
                          float(np.nextafter(center, np.float32(np.inf)))])
    for density in densities:
        if not 0 <= density <= 1:
            continue
        rip.s.white_density = density
        volumes = np.where(mask, np.float32(density), np.float32(0))
        expected = rip._halftone(volumes, phase, original)
        np.testing.assert_array_equal(rip._binary_white_levels(mask, phase), expected)
    np.testing.assert_array_equal(mask, before)
    assert rip.noise is noise and not noise.flags.writeable


@pytest.mark.parametrize('hook', ['_halftone', '_thresholds'])
def test_custom_halftone_and_threshold_methods_keep_original_volume_path(hook):
    rip = Rip(Settings(dpi_x=300, dpi_y=300, white_density=.45))
    alpha = np.zeros((273, 301), dtype=bool)
    alpha[10:260, 20:280] = True
    original = getattr(rip, hook)
    setattr(rip, hook, lambda *a, **kw: original(*a, **kw))
    def forbidden(*args):
        raise AssertionError('hook personalizado precisa manter o caminho completo')
    rip._binary_white_levels = forbidden
    np.testing.assert_array_equal(rip._white_levels(alpha, 253),
                                  rip._white_levels(alpha.astype(np.float32), 253))


@pytest.mark.parametrize('noise_value', [-1., 0., 1., .123456789])
def test_custom_noise_keeps_zero_volume_threshold_semantics(noise_value):
    rip = Rip(Settings(dpi_x=300, dpi_y=300, white_density=.45))
    rip.noise = np.full((256, 256), noise_value)
    rip.noise.setflags(write=False)
    alpha = np.zeros((273, 301), dtype=bool)
    alpha[10:260, 20:280] = True
    def forbidden(*args):
        raise AssertionError('ruido personalizado precisa manter o caminho completo')
    rip._binary_white_levels = forbidden
    np.testing.assert_array_equal(rip._white_levels(alpha, 253),
                                  rip._white_levels(alpha.astype(np.float32), 253))
