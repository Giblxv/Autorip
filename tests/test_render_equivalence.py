"""Otimizações de buffers não podem alterar níveis, fase ou canais PRT."""
import numpy as np
import pytest
from PIL import Image

from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import read_header, read_rows


def reference_halftone(rip, values, y0):
    height, width = values.shape
    ny, nx = rip.noise.shape
    thresholds = rip.noise[np.ix_((np.arange(height) + y0) % ny, np.arange(width) % nx)]
    ratio = rip.s.small_drop_ratio
    small = (values / ratio) > thresholds
    large = ((values - ratio) / (1-ratio)) > thresholds
    return np.where(large, 3, np.where(small, 1, 0)).astype(np.uint8)


@pytest.mark.parametrize("ratio", [.05, .4, .95])
@pytest.mark.parametrize("y0", [0, 253, 1025])
def test_reticula_equivale_ao_calculo_anterior_nos_limites(ratio, y0):
    rip = Rip(Settings(small_drop_ratio=ratio))
    rng = np.random.default_rng(42)
    thresholds = rip._thresholds(17, 301, y0)
    for values in [rng.random((17,301), dtype=np.float32),
                   np.full((17,301),ratio,dtype=np.float32),
                   np.asarray(thresholds*ratio,dtype=np.float32),
                   np.asarray(thresholds*(1-ratio)+ratio,dtype=np.float32)]:
        for candidate in [values, np.nextafter(values, np.float32(0)),
                          np.nextafter(values, np.float32(1))]:
            expected = reference_halftone(rip,candidate,y0)
            assert np.array_equal(rip._halftone(candidate,y0),expected)
            assert np.array_equal(rip._halftone(candidate,y0,thresholds),expected)


def test_limites_de_tinta_preservam_float32_e_valores():
    rng = np.random.default_rng(22)
    rgb = Image.fromarray(rng.integers(0,256,(40,37,3),dtype=np.uint8),'RGB')
    settings = Settings(ink_limit={'C':35.5,'M':0,'Y':88.25,'K':100})
    rip = Rip(settings)
    original = np.asarray(rgb.convert('CMYK'),dtype=np.float32)/255.0
    limits = np.asarray([settings.ink_limit[channel]/100 for channel in 'CMYK'],dtype=np.float32)
    expected = np.clip(original*limits,0,1)
    result = rip._to_cmyk(rgb)
    assert result.dtype == np.float32 and np.array_equal(result,expected)


@pytest.mark.parametrize("white", [False,True])
def test_rip_preserva_bytes_com_oraculo_anterior_de_reticula(tmp_path, white):
    rng = np.random.default_rng(51)
    path = tmp_path/'source.png'
    pixels = rng.integers(0,256,(87,95,4),dtype=np.uint8)
    Image.fromarray(pixels,'RGBA').save(path)
    settings = Settings(dpi_x=300,dpi_y=720,label_enabled=True,
                        margin_top_in=.15,margin_bottom_in=.15,
                        white_enabled=white, channel_order=['M','Y','K','C'],white_planes=[4,7])
    optimized = Rip(settings)
    original = Rip(settings)
    original._halftone = lambda values,y0,thresholds=None:reference_halftone(original,values,y0)
    first = optimized.process(str(path),str(tmp_path/'optimized.PRT'),width_cm=2.54)
    second = original.process(str(path),str(tmp_path/'original.PRT'),width_cm=2.54)
    assert (tmp_path/'optimized.PRT').read_bytes() == (tmp_path/'original.PRT').read_bytes()
    assert first['n_dots'] == second['n_dots'] == 300


def test_prt_multibloco_preserva_niveis_e_padding(tmp_path):
    from autorip.prt import PrtWriter
    rng = np.random.default_rng(67)
    planes = [rng.integers(0,4,(19,37),dtype=np.uint8) for _ in range(12)]
    path = tmp_path/'multiple.PRT'
    writer = PrtWriter(path,720,2400,19,37)
    writer.write_block([p[:7] for p in planes])
    writer.write_block([p[7:] for p in planes])
    writer.close()
    assert read_header(path)['n_rows'] == 19
    decoded = read_rows(path,0,19)
    assert all(np.array_equal(actual,expected) for actual,expected in zip(decoded,planes))
