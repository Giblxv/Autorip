"""Compare formatos CMS com conversão não identidade e todos os valores de alfa."""
import struct

import numpy as np
from PIL import Image, ImageCms
import pytest

from autorip.config import Settings
from autorip.engine import Rip
from test_source_icc_cache import original_rgba


def gamma_profile():
    profile = bytearray(ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes())
    for index in range(struct.unpack_from('>I', profile, 128)[0]):
        pos = 132 + index * 12
        if profile[pos:pos + 4] == b'rTRC':
            offset = struct.unpack_from('>I', profile, pos + 4)[0]
            assert profile[offset:offset + 4] == b'para'
            struct.pack_into('>i', profile, offset + 12, round(1.8 * 65536))
            return bytes(profile)
    raise AssertionError('Perfil de teste sem TRC paramétrica')


def gray_profile():
    """Perfil GRAY/XYZ sintético com ponto branco e TRC gamma 1,8."""
    base = gamma_profile()
    tags = {}
    for index in range(struct.unpack_from('>I', base, 128)[0]):
        name, offset, size = struct.unpack_from('>4sII', base, 132 + index * 12)
        tags[name] = base[offset:offset + size]
    selected = [(b'desc', tags[b'desc']), (b'wtpt', tags[b'wtpt']), (b'kTRC', tags[b'rTRC'])]
    header = bytearray(base[:128]); header[16:20] = b'GRAY'; header[84:100] = b'\0' * 16
    records, payload = bytearray(), bytearray()
    offset = 132 + 12 * len(selected)
    for name, data in selected:
        records.extend(struct.pack('>4sII', name, offset + len(payload), len(data)))
        payload.extend(data); payload.extend(b'\0' * (-len(payload) % 4))
    result = header + struct.pack('>I', len(selected)) + records + payload
    struct.pack_into('>I', result, 0, len(result))
    return bytes(result)


@pytest.mark.parametrize('intent', range(4))
@pytest.mark.parametrize('bpc', [False, True])
@pytest.mark.parametrize('pattern', ['varied', 'flat'])
@pytest.mark.parametrize('mode', ['RGBA', 'RGB', 'RGBX', 'P', 'PA', 'color_key'])
def test_rgba_direto_preserva_cor_nao_identidade_alfa_e_fonte(intent, bpc, pattern, mode):
    pixels = np.random.default_rng(114).integers(0, 256, (37, 256, 4), dtype=np.uint8)
    if pattern == 'flat':
        # Mesmo RGB com alfa variável também exercita hits do cache nativo CMS.
        pixels[..., :3] = (100, 150, 200)
    pixels[..., 3] = np.arange(256, dtype=np.uint8)[None, :]
    source = Image.fromarray(pixels, 'RGBA')
    if mode == 'RGBX':
        source.close()
        # O byte X contém todos os valores possíveis: ele não é transparência.
        source = Image.frombytes('RGBX', (256, 37), pixels.tobytes())
    elif mode != 'RGBA':
        converted = source.convert('RGB' if mode == 'color_key' else mode)
        source.close(); source = converted
        if mode == 'P':
            source.info['transparency'] = bytes(range(256))
        elif mode == 'color_key':
            source.putpixel((0, 0), (0, 0, 0))
            source.info['transparency'] = (0, 0, 0)
    source.info['icc_profile'] = gamma_profile()
    before = source.tobytes()
    original_info = source.info.copy()
    rip = Rip(Settings(intent=intent, black_point_comp=bpc))
    expected = original_rgba(source, rip.s)
    try:
        with source.convert('RGB') as color:
            assert np.any(np.asarray(expected)[..., :3] != np.asarray(color))
        for _ in range(2):
            actual = rip._source_rgba(source)
            try:
                assert actual.mode == 'RGBA' and actual.size == source.size
                assert actual.tobytes() == expected.tobytes()
                with source.convert('RGBA') as original:
                    assert actual.getchannel('A').tobytes() == original.getchannel('A').tobytes()
            finally:
                actual.close()
        assert source.tobytes() == before and source.info == original_info
    finally:
        expected.close(); source.close()


@pytest.mark.parametrize('mode', ['L', 'LA'])
@pytest.mark.parametrize('intent', range(4))
@pytest.mark.parametrize('bpc', [False, True])
def test_perfil_cinza_real_preserva_cor_e_alfa(mode, intent, bpc):
    data = np.random.default_rng(421).integers(0, 256, (17, 256, 2), dtype=np.uint8)
    data[..., 1] = np.arange(256, dtype=np.uint8)[None, :]
    source = Image.fromarray(data[..., 0] if mode == 'L' else data, mode)
    source.info['icc_profile'] = gray_profile()
    rip = Rip(Settings(intent=intent, black_point_comp=bpc))
    expected = original_rgba(source, rip.s)
    before = source.tobytes()
    try:
        for _ in range(2):
            actual = rip._source_rgba(source)
            try:
                assert actual.tobytes() == expected.tobytes()
                assert actual.getchannel('A').tobytes() == (
                    data[..., 1].tobytes() if mode == 'LA' else b'\xff' * (17 * 256))
            finally:
                actual.close()
        assert source.tobytes() == before
    finally:
        source.close(); expected.close()


@pytest.mark.parametrize('intent', range(4))
@pytest.mark.parametrize('bpc', [False, True])
@pytest.mark.parametrize('pattern', ['varied', 'flat'])
def test_transformacao_in_place_preserva_alfa_e_todos_os_pixels(intent, bpc, pattern):
    data = np.random.default_rng(713).integers(0, 256, (37, 256, 4), dtype=np.uint8)
    if pattern == 'flat':
        data[..., :3] = (100, 150, 200)
    data[..., 3] = np.arange(256, dtype=np.uint8)[None, :]
    with Image.fromarray(data, 'RGBA') as shared:
        source = shared.copy()
    assert not source.readonly
    source.info['icc_profile'] = gamma_profile()
    rip = Rip(Settings(intent=intent, black_point_comp=bpc))
    expected = original_rgba(source, rip.s)
    try:
        result = rip._source_rgba(source, in_place=True)
        assert result is source and result.tobytes() == expected.tobytes()
        assert result.getchannel('A').tobytes() == data[..., 3].tobytes()
    finally:
        source.close(); expected.close()
