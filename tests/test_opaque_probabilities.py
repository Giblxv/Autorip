import numpy as np
import pytest
from PIL import Image

from autorip.config import Settings
from autorip.engine import Rip


@pytest.mark.parametrize("ratio", [.05, .4, .95])
@pytest.mark.parametrize("limits", [(1., 1., 1., 1.), (0., .355, .8825, 1.), (.125, .25, .5, .99999)])
def test_all_256_cutoffs_match_search_of_all_original_thresholds(ratio, limits):
    small, large = Rip._opaque_cutoffs(ratio, limits)
    # A mesma entrada uint8 da conversao CMYK, normalizada como no motor legado.
    raw = np.repeat(np.arange(256, dtype=np.uint8)[:, None], 4, axis=1)
    values = raw.astype(np.float32) / 255.0
    values *= np.asarray(limits, dtype=np.float32)
    values = np.clip(values, 0, 1)
    original_thresholds = (np.arange(65536, dtype=np.float64) + .5) / 65536
    np.testing.assert_array_equal(small.T, np.searchsorted(original_thresholds, values / ratio))
    np.testing.assert_array_equal(large.T, np.searchsorted(original_thresholds, (values - ratio) / (1.0 - ratio)))
    assert small.dtype == np.uint32 and large.dtype == np.uint32
    assert small.flags.c_contiguous and large.flags.c_contiguous
    assert not small.flags.writeable and not large.flags.writeable


@pytest.mark.parametrize("ratio", [.05, .4, .95])
@pytest.mark.parametrize("limits", [dict(C=100, M=100, Y=100, K=100), dict(C=0, M=35.5, Y=88.25, K=100)])
def test_opaque_levels_match_reference_at_adjacent_thresholds(ratio, limits):
    rip = Rip(Settings(small_drop_ratio=ratio, ink_limit=limits))
    # Varia cada byte RGB; a prova da tabela acima inclui tambem todo o canal K.
    values = np.arange(256, dtype=np.uint8)
    pixels = np.stack([values, np.roll(values, 67), values[::-1]], axis=1)[None, ...]
    source = Image.fromarray(pixels)
    before = source.tobytes()
    volumes = rip._to_cmyk(source)
    cutoff_tables = rip._opaque_cutoffs(ratio, tuple(limits[key] / 100 for key in "CMYK"))
    raw = np.asarray(source.convert("CMYK"))
    for channel in range(4):
        for table in cutoff_tables:
            boundary = table[channel][raw[..., channel]].astype(np.int64)
            for offset in (-1, 0, 1):
                ranks = np.clip(boundary + offset, 0, 65535).astype(np.uint16)
                threshold = (ranks.astype(np.float64) + .5) / 65536
                actual = rip._opaque_color_levels(source, ranks)
                for index in range(4):
                    expected = rip._halftone(volumes[..., index], 0, threshold)
                    np.testing.assert_array_equal(actual[index], expected)
                    assert actual[index].dtype == np.uint8
    assert source.tobytes() == before
    source.close()


def test_probability_cache_is_bounded_readonly_and_keyed_by_all_parameters():
    Rip._opaque_cutoffs.cache_clear()
    first = Rip._opaque_cutoffs(.4, (1., 1., 1., 1.))
    assert first is Rip._opaque_cutoffs(.4, (1., 1., 1., 1.))
    changed = Rip._opaque_cutoffs(.5, (1., 1., 1., 1.))
    assert not np.array_equal(first[0], changed[0])
    changed_limit = Rip._opaque_cutoffs(.4, (0., 1., 1., 1.))
    assert not np.array_equal(first[0][0], changed_limit[0][0])
    with pytest.raises(ValueError):
        first[0][0, 0] = 17
    for value in range(32):
        Rip._opaque_cutoffs(.4, (value / 100, 1., 1., 1.))
    assert Rip._opaque_cutoffs.cache_info().currsize == 16


@pytest.mark.parametrize("phase", [0, 253, 1025, -3])
@pytest.mark.parametrize("shape", [(1, 1), (17, 301), (257, 111), (513, 32)])
def test_rank_plane_is_lossless_at_period_edges(phase, shape):
    rip = Rip(Settings())
    ranks = rip._threshold_ranks(*shape, phase)
    np.testing.assert_array_equal((ranks.astype(np.float64) + .5) / 65536,
                                  rip._thresholds(*shape, phase))
    assert ranks.dtype == np.uint16 and not rip._opaque_ranks.flags.writeable


@pytest.mark.parametrize("canonical", [False, True])
def test_custom_noise_keeps_legacy_pipeline(canonical):
    rip = Rip(Settings(dpi_x=300, dpi_y=300, white_enabled=False, label_enabled=False))
    rip.noise = np.full((256, 256), (.5 / 65536) if canonical else .123456789)
    rip.noise.setflags(write=False)
    def forbidden(*args):
        raise AssertionError("ruido personalizado deve manter o caminho original")
    rip._opaque_color_levels = forbidden
    image = Image.new("RGB", (1024, 512), (47, 139, 201))
    rip._render(image, 0, 512, 0, 512, 1024, [])
    image.close()


def test_noncanonical_noise_disables_rank_conversion_without_rounding():
    rip = Rip(Settings())
    rip.noise = np.full((256, 256), .123456789)
    rip.noise.setflags(write=False)
    assert rip._threshold_ranks(7, 9, 0) is None
    assert rip._threshold_ranks(7, 9, 0) is None


@pytest.mark.parametrize("hook", ["_to_cmyk", "_halftone", "_thresholds"])
def test_custom_hooks_keep_original_pipeline(hook):
    rip = Rip(Settings(dpi_x=300, dpi_y=300, white_enabled=False, label_enabled=False))
    original = getattr(rip, hook)
    calls = []
    def custom(*args, **kwargs):
        calls.append(True)
        return original(*args, **kwargs)
    setattr(rip, hook, custom)
    def forbidden(*args):
        raise AssertionError("o hook personalizado foi ignorado")
    rip._opaque_color_levels = forbidden
    image = Image.new("RGB", (1024, 512), (47, 139, 201))
    rip._render(image, 0, 512, 0, 512, 1024, [])
    assert calls
    image.close()


def test_numpy_ratio_keeps_legacy_scalar_promotion():
    rip = Rip(Settings(dpi_x=300, dpi_y=300, white_enabled=False, label_enabled=False))
    rip.s.small_drop_ratio = np.float64(.4000000001)
    def forbidden(*args):
        raise AssertionError("ratio numpy deve manter o caminho original")
    rip._opaque_color_levels = forbidden
    image = Image.new("RGB", (1024, 512), (47, 139, 201))
    rip._render(image, 0, 512, 0, 512, 1024, [])
    image.close()


@pytest.mark.parametrize("ratio", [.05, .4, .95])
@pytest.mark.parametrize("icc", [False, True])
@pytest.mark.parametrize("workers", [1, 4])
def test_full_rgb_rip_matches_legacy_with_lut_active(tmp_path, monkeypatch, ratio, icc, workers):
    from pathlib import Path
    from autorip import engine

    pixels = np.random.default_rng(74).integers(0, 256, (512, 768, 3), dtype=np.uint8)
    source = tmp_path / "source.png"
    Image.fromarray(pixels).save(source)
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    settings = Settings(dpi_x=720, dpi_y=1200, white_enabled=icc, label_enabled=True,
                        icc_path=str(profile) if icc else '', small_drop_ratio=ratio,
                        margin_top_in=.12, margin_bottom_in=.12, mirror=True,
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7],
                        ink_limit=dict(C=35.5, M=0, Y=88.25, K=100))
    monkeypatch.setattr(engine, '_available_cpu_count', lambda: workers)
    baseline = Rip(settings)
    original_halftone = baseline._halftone
    baseline._halftone = lambda *a, **kw: original_halftone(*a, **kw)
    candidate = Rip(settings)
    calls = []
    original_lookup = candidate._opaque_color_levels
    def observed(*args):
        calls.append(True)
        return original_lookup(*args)
    candidate._opaque_color_levels = observed
    first = baseline.process(str(source), str(tmp_path / 'old.PRT'), width_cm=5.08)
    second = candidate.process(str(source), str(tmp_path / 'new.PRT'), width_cm=5.08)
    a, b = first.pop('output_path'), second.pop('output_path')
    assert Path(a).read_bytes() == Path(b).read_bytes()
    assert first == second and calls
