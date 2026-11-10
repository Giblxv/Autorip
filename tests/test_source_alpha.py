"""Alfa e buffers da conversão ICC, incluindo falhas que retêm o traceback."""
import numpy as np
from PIL import Image, ImageCms
import pytest

from autorip.config import Settings
from autorip.engine import Rip
from test_source_icc_cache import original_rgba


def profiled_image(kind):
    pixels = np.random.default_rng(281).integers(0, 256, (19, 256, 4), dtype=np.uint8)
    pixels[..., 3] = np.arange(256, dtype=np.uint8)
    image = Image.fromarray(pixels, 'RGBA')
    if kind == 'PA':
        image = image.convert('PA')
    elif kind == 'palette':
        image = image.convert('P')
        image.info['transparency'] = bytes(range(256))
    elif kind == 'color_key':
        image = image.convert('RGB')
        image.putpixel((0, 0), (0, 0, 0))
        image.info['transparency'] = (0, 0, 0)
    image.info['icc_profile'] = ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()
    return image


@pytest.mark.parametrize('kind', ['RGBA', 'PA', 'palette', 'color_key'])
@pytest.mark.parametrize('intent', range(4))
@pytest.mark.parametrize('bpc', [False, True])
def test_alpha_completo_e_transparencia_preservados(kind, intent, bpc):
    source = profiled_image(kind)
    pixels, info = source.tobytes(), source.info.copy()
    rip = Rip(Settings(intent=intent, black_point_comp=bpc))
    expected = original_rgba(source, rip.s)
    try:
        for _ in range(2):
            actual = rip._source_rgba(source)
            try:
                assert actual.mode == 'RGBA' and actual.size == source.size
                assert actual.tobytes() == expected.tobytes()
                assert actual.getchannel('A').tobytes() == source.convert('RGBA').getchannel('A').tobytes()
            finally:
                actual.close()
        assert source.tobytes() == pixels and source.info == info
    finally:
        source.close(); expected.close()


@pytest.mark.parametrize('kind', ['RGBA', 'palette'])
@pytest.mark.parametrize('failure', [None, 'apply', 'rgba', 'alpha', 'putalpha'])
def test_temporarios_fechados_inclusive_com_traceback_retido(monkeypatch, kind, failure):
    source = profiled_image(kind)
    rip = Rip(Settings())
    # Compile antes de observar somente os rasters desta conversão.
    rip._source_transform(source.info['icc_profile'], 'RGB')
    tracked = []
    convert, apply = Image.Image.convert, ImageCms.applyTransform
    channel, putalpha = Image.Image.getchannel, Image.Image.putalpha

    def convert_tracked(image, mode, *args, **kwargs):
        if failure == 'rgba' and image is not source and mode == 'RGBA':
            raise RuntimeError('falha simulada')
        result = convert(image, mode, *args, **kwargs)
        tracked.append(result)
        return result

    def apply_tracked(*args, **kwargs):
        if failure == 'apply':
            raise RuntimeError('falha simulada')
        result = apply(*args, **kwargs)
        tracked.append(result)
        return result

    def channel_tracked(image, name):
        if failure == 'alpha':
            raise RuntimeError('falha simulada')
        result = channel(image, name)
        tracked.append(result)
        return result

    def putalpha_tracked(image, alpha):
        if failure == 'putalpha':
            raise RuntimeError('falha simulada')
        return putalpha(image, alpha)

    monkeypatch.setattr(Image.Image, 'convert', convert_tracked)
    monkeypatch.setattr(ImageCms, 'applyTransform', apply_tracked)
    monkeypatch.setattr(Image.Image, 'getchannel', channel_tracked)
    monkeypatch.setattr(Image.Image, 'putalpha', putalpha_tracked)
    result = None
    if failure:
        with pytest.raises(ValueError, match='ICC.*falha simulada') as retained:
            rip._source_rgba(source)
        assert retained.value.__traceback__ is not None
    else:
        result = rip._source_rgba(source)
        assert result.getpixel((0, 0)) is not None
    try:
        for temporary in tracked:
            if temporary is result:
                continue
            with pytest.raises(ValueError, match='closed'):
                temporary.getpixel((0, 0))
        assert source.getpixel((0, 0)) is not None
    finally:
        source.close()
        if result is not None:
            result.close()


def test_la_extrai_alpha_sem_expandir_raster(monkeypatch):
    # Isola o alfa LA; sRGB não é um perfil cinza e não é usado como tal.
    source = Image.new('LA', (256, 3))
    source.putdata([(i, i) for _ in range(3) for i in range(256)])
    source.info['icc_profile'] = b'profile-placeholder'
    rip = Rip(Settings())
    monkeypatch.setattr(rip, '_source_transform', lambda *args: object())
    monkeypatch.setattr(ImageCms, 'applyTransform', lambda color, transform: color.convert('RGB'))
    result = rip._source_rgba(source)
    try:
        assert result.getchannel('A').tobytes() == source.getchannel('A').tobytes()
        assert source.getpixel((127, 0)) == (127, 127)
    finally:
        result.close(); source.close()
