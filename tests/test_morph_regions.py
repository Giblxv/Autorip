import numpy as np
import pytest
from scipy import ndimage as ndi

from autorip import morph


def oracle_erode(mask, radius, sampling):
    padded = np.pad(mask, 1, constant_values=False)
    return (ndi.distance_transform_edt(padded, sampling=sampling) > radius)[1:-1,1:-1]


@pytest.mark.parametrize("dpi", [(300,300), (720,2400), (72,9600)])
@pytest.mark.parametrize("mm", [0.01,0.1,0.3,1.0])
def test_mascara_cheia_preserva_distancia_exata_ate_borda(dpi, mm):
    for shape in [(1,1), (1,37), (43,1), (127,199)]:
        mask = np.ones(shape, bool)
        expected = oracle_erode(mask, mm/25.4, (1/dpi[1],1/dpi[0]))
        np.testing.assert_array_equal(morph.erode(mask,mm,*dpi), expected)


@pytest.mark.parametrize("edge", ["center", "top", "left", "bottom", "right"])
@pytest.mark.parametrize("dpi", [(300,300), (720,2400), (72,9600)])
def test_regiao_reduzida_preserva_furos_e_objetos_na_borda(edge, dpi):
    rng = np.random.default_rng(202615)
    mask = np.zeros((131,173),bool)
    y,x = {"center":(40,60),"top":(0,60),"left":(40,0),"bottom":(94,60),"right":(40,132)}[edge]
    mask[y:y+37,x:x+41] = rng.random((37,41)) > .25
    mm = .15
    radius=mm/25.4; sampling=(1/dpi[1],1/dpi[0])
    np.testing.assert_array_equal(morph.erode(mask,mm,*dpi),oracle_erode(mask,radius,sampling))
    ry,rx = int(np.ceil(radius*dpi[1]))+1,int(np.ceil(radius*dpi[0]))+1
    padded = np.pad(mask,((ry,ry),(rx,rx)))
    expanded = ndi.distance_transform_edt(~padded,sampling=sampling) <= radius
    closed = oracle_erode(expanded,radius,sampling)
    np.testing.assert_array_equal(morph.close_holes(mask,mm,*dpi),closed[ry:ry+131,rx:rx+173])
