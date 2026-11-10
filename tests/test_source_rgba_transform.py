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


@pytest.mark.parametrize('intent', range(4))
@pytest.mark.parametrize('bpc', [False, True])
@pytest.mark.parametrize('pattern', ['varied', 'flat'])
def test_rgba_direto_preserva_cor_nao_identidade_alfa_e_fonte(intent, bpc, pattern):
    pixels = np.random.default_rng(114).integers(0, 256, (37, 256, 4), dtype=np.uint8)
    if pattern == 'flat':
        # Mesmo RGB com alfa variável também exercita hits do cache nativo CMS.
        pixels[..., :3] = (100, 150, 200)
    pixels[..., 3] = np.arange(256, dtype=np.uint8)[None, :]
    source = Image.fromarray(pixels, 'RGBA')
    source.info['icc_profile'] = gamma_profile()
    before = source.tobytes()
    rip = Rip(Settings(intent=intent, black_point_comp=bpc))
    expected = original_rgba(source, rip.s)
    try:
        assert np.any(np.asarray(expected)[..., :3] != pixels[..., :3])
        for _ in range(2):
            actual = rip._source_rgba(source)
            try:
                assert actual.mode == 'RGBA' and actual.size == source.size
                assert actual.tobytes() == expected.tobytes()
                assert actual.getchannel('A').tobytes() == pixels[..., 3].tobytes()
            finally:
                actual.close()
        assert source.tobytes() == before
    finally:
        expected.close(); source.close()
