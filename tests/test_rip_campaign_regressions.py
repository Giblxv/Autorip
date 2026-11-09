"""Regressões independentes dos critérios estatísticos da campanha."""
import numpy as np
from PIL import Image

from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import PrtWriter, read_rows


def test_etiqueta_em_tira_transparente_nao_contamina_outros_canais():
    settings = Settings(dpi_x=300, dpi_y=300, white_enabled=False,
                        channel_order=['M','Y','K','C'])
    rip = Rip(settings)
    image = Image.new('RGBA', (37,12), (0,0,0,0))
    label = np.ones((3,5), dtype=bool)
    planes = rip._render(image,0,12,0,12,37,[(2,4,label)])
    assert np.count_nonzero(planes[2]) == 15
    assert all(not plane.any() for index,plane in enumerate(planes) if index != 2)
    assert np.all(planes[2][2:5,4:9] == 3)


def test_writer_distingue_views_com_mesmo_endereco_e_strides_diferentes(tmp_path):
    original = (np.arange(25,dtype=np.uint8).reshape(5,5)//2%4)
    zero = np.zeros((7,5),dtype=np.uint8)
    planes = [original, original.T] + [zero[1:6]]*10
    path = tmp_path/'views.PRT'
    writer = PrtWriter(path,300,300,5,5)
    writer.write_block(planes)
    writer.close()
    actual = read_rows(path,0,5)
    assert all(np.array_equal(a,b) for a,b in zip(actual,planes))
    assert not np.array_equal(actual[0],actual[1])


def test_distancias_2d_sao_identicas_a_edt_publica():
    from scipy import ndimage as ndi
    from autorip.morph import _distance
    rng = np.random.default_rng(2026)
    for shape in ((1,1),(3,7),(37,29),(128,93)):
        for density in (.05,.5,.95):
            mask = rng.random(shape) < density
            for sampling in ((1/300,1/300),(1/2400,1/720),(1/72,1/9600)):
                assert np.array_equal(_distance(mask,sampling),
                                      ndi.distance_transform_edt(mask,sampling=sampling))
