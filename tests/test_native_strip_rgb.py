from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip


def reference_rgb(strip):
    return Image.fromarray(np.asarray(strip)[..., :3], 'RGB')


def test_all_alpha_and_color_bytes_preserve_rgb_without_compositing():
    yy, xx = np.indices((256, 256), dtype=np.uint16)
    pixels = np.stack([xx, yy, (xx + yy) % 256, (7 * xx + 3 * yy) % 256], axis=-1).astype(np.uint8)
    with Image.fromarray(pixels) as strip:
        with reference_rgb(strip) as expected, Rip._strip_rgb(strip) as actual:
            assert actual.mode == 'RGB' and actual.tobytes() == expected.tobytes()
            # Mesmo com alfa zero, os canais RGB sao extraidos sem fundo/composicao.
            np.testing.assert_array_equal(np.asarray(actual), pixels[..., :3])


@pytest.mark.parametrize('shape', [(1, 1), (1, 257), (257, 1), (31, 33), (512, 1440)])
@pytest.mark.parametrize('metadata', ['empty', 'icc_dpi', 'transparency_key', 'transparency_bytes', 'exif'])
def test_rgb_is_private_and_has_original_metadata_contract(shape, metadata):
    pixels = np.random.default_rng(4100).integers(0, 256, (*shape, 4), dtype=np.uint8)
    with Image.fromarray(pixels) as strip:
        if metadata == 'icc_dpi':
            strip.info.update(icc_profile=b'profile marker', dpi=(300, 150), note={'text': 'unchanged'})
        elif metadata == 'transparency_key':
            strip.info['transparency'] = (20, 30, 40)
        elif metadata == 'transparency_bytes':
            strip.info['transparency'] = bytes(range(256))
        elif metadata == 'exif':
            exif = Image.Exif()
            exif[274] = 6
            strip.info['exif'] = exif.tobytes()
            assert strip.getexif()[274] == 6
        original_info = strip.info
        saved_info = strip.info.copy()
        before = strip.tobytes()
        with reference_rgb(strip) as expected, Rip._strip_rgb(strip) as actual:
            assert actual.mode == expected.mode and actual.size == expected.size
            assert actual.tobytes() == expected.tobytes()
            assert actual.info == expected.info == {}
            assert actual.readonly == expected.readonly == 0
            assert dict(actual.getexif()) == dict(expected.getexif()) == {}
            actual.paste(0, (0, 0, *actual.size))
            assert strip.tobytes() == before
            assert strip.info is original_info and strip.info == saved_info


def test_fully_transparent_render_skips_rgb_extraction():
    rip = Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False))
    def forbidden(*args):
        raise AssertionError('sem pixels visiveis, nao extrair RGB')
    rip._strip_rgb = forbidden
    with Image.new('RGBA', (513, 512), (127, 63, 191, 0)) as source:
        planes = rip._render(source, 0, 512, 0, 512, 513, [])
        assert len(planes) == 12 and all(not plane.any() for plane in planes)


@pytest.mark.parametrize('workers', [1, 4])
@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('orientation', [1, 6])
@pytest.mark.parametrize('file_type', ['png', 'tiff'])
def test_complete_rip_preserves_bytes_with_native_rgb_active(tmp_path, monkeypatch, workers, icc, orientation, file_type):
    pixels = np.random.default_rng(4101).integers(0, 256, (512, 768, 4), dtype=np.uint8)
    source = tmp_path / ('source.' + file_type)
    exif = Image.Exif()
    exif[274] = orientation
    with Image.fromarray(pixels) as image:
        image.save(source, dpi=(100, 200), exif=exif)
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    settings = Settings(dpi_x=720, dpi_y=1200, white_enabled=True, label_enabled=True,
                        icc_path=str(profile) if icc else '', white_density=.45,
                        margin_top_in=.12, margin_bottom_in=.12, mirror=True,
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7],
                        ink_limit=dict(C=35.5, M=0, Y=88.25, K=100))
    monkeypatch.setattr(engine, '_available_cpu_count', lambda: workers)
    baseline, candidate = Rip(settings), Rip(settings)
    baseline._strip_rgb = reference_rgb
    calls = []
    original = candidate._strip_rgb
    def observed(strip):
        rgb = original(strip)
        assert rgb.info == {} and rgb.mode == 'RGB'
        calls.append(True)
        return rgb
    candidate._strip_rgb = observed
    observed_colors = []
    original_cmyk = candidate._to_cmyk
    def cmyk(rgb):
        observed_colors.append(rgb.info.copy())
        return original_cmyk(rgb)
    candidate._to_cmyk = cmyk
    first = baseline.process(str(source), str(tmp_path / 'old.PRT'), width_cm=5.08)
    second = candidate.process(str(source), str(tmp_path / 'new.PRT'), width_cm=5.08)
    a, b = first.pop('output_path'), second.pop('output_path')
    assert calls and observed_colors and all(info == {} for info in observed_colors)
    assert Path(a).read_bytes() == Path(b).read_bytes() and first == second
