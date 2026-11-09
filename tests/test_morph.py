import numpy as np
from scipy import ndimage as ndi
from autorip import morph

DX, DY = 720, 2400


def _bloco():
    m = np.zeros((1200, 400), bool)
    m[300:900, 80:320] = True
    return m


def test_erode_aproxima_retangular_e_arredonda_cantos():
    m = _bloco()
    mm = 0.5
    ry, rx = int(round(mm / 25.4 * DY)), int(round(mm / 25.4 * DX))
    old = ndi.binary_erosion(m, structure=np.ones((2 * ry + 1, 2 * rx + 1), bool))
    new = morph.erode(m, mm, DX, DY)
    assert new.sum() >= old.sum()            # disco nunca erode mais que o retangulo
    assert (old != new).sum() < 0.02 * old.sum()


def test_close_holes_fecha_furo_pequeno():
    m = _bloco()
    m[500:510, 150:160] = False
    assert morph.close_holes(m, 0.6, DX, DY)[500:510, 150:160].all()


def test_borda_da_imagem_nao_ganha_branco():
    m = _bloco()
    assert morph.close_holes(m, 0.6, DX, DY)[0].sum() == 0


def test_raio_zero_nao_altera():
    m = _bloco()
    assert morph.erode(m, 0, DX, DY) is m and morph.close_holes(m, 0, DX, DY) is m


def test_mascara_vazia_nunca_ganha_branco():
    for shape in [(1, 1), (13, 31), (200, 100)]:
        empty = np.zeros(shape, bool)
        assert not morph.dilate(empty, 2, DX, DY).any()
        assert not morph.close_holes(empty, 2, DX, DY).any()
        assert not morph.erode(empty, 2, DX, DY).any()


def test_disco_fisico_equivale_a_oraculo_de_kernel():
    rng = np.random.default_rng(101)
    m = rng.random((40, 50)) > 0.4
    for dpi_x, dpi_y in [(300, 300), (72, 9600), (720, 2400)]:
        mm = 0.15
        ry, rx = int(np.ceil(mm / 25.4 * dpi_y)), int(np.ceil(mm / 25.4 * dpi_x))
        yy, xx = np.mgrid[-ry:ry+1, -rx:rx+1]
        disk = (yy / dpi_y)**2 + (xx / dpi_x)**2 <= (mm / 25.4)**2
        assert np.array_equal(morph.dilate(m, mm, dpi_x, dpi_y), ndi.binary_dilation(m, structure=disk))
        assert np.array_equal(morph.erode(m, mm, dpi_x, dpi_y), ndi.binary_erosion(m, structure=disk))
        pad = np.pad(m, ((ry+1, ry+1), (rx+1, rx+1)))
        expected = ndi.binary_closing(pad, structure=disk)[ry+1:ry+1+m.shape[0], rx+1:rx+1+m.shape[1]]
        assert np.array_equal(morph.close_holes(m, mm, dpi_x, dpi_y), expected)


def test_fechamento_preserva_objeto_nas_quatro_bordas():
    full = np.ones((50, 60), bool)
    assert morph.close_holes(full, .3, DX, DY).all()
    assert not morph.erode(full, .3, DX, DY)[0].any()
