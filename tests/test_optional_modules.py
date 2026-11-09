import sys
from types import SimpleNamespace

import pytest
from PIL import Image
from autorip.nesting import nest, Placements
from autorip.bgremove import remove_background


def test_nesting_respeita_folha_quantidades_e_nao_sobrepoe():
    placed = nest([("a", 10.0001, 4.0001, 8), ("grande", 99, 99, 1)], 20.5, 20, gap_cm=.2)
    assert len(placed) == 8 and placed.unplaced == ["grande"]
    for i, a in enumerate(placed):
        assert a['x_cm'] + a['largura_cm'] <= 20.5
        assert a['y_cm'] + a['altura_cm'] <= 20
        for b in placed[i+1:]:
            if a['folha'] != b['folha']:
                continue
            assert (a['x_cm']+a['largura_cm'] <= b['x_cm'] or
                    b['x_cm']+b['largura_cm'] <= a['x_cm'] or
                    a['y_cm']+a['altura_cm'] <= b['y_cm'] or
                    b['y_cm']+b['altura_cm'] <= a['y_cm'])


def test_nesting_rotacao_e_resultados_independentes():
    placed = nest([("rotacionada", 8.0001, 3.0001, 1)], 4, 9, gap_cm=0)
    assert placed[0]['girado'] and placed[0]['largura_cm'] == 3.0001
    a, b = Placements(), Placements()
    a.unplaced.append('x')
    assert b.unplaced == []


@pytest.mark.parametrize("items", [[('a',0,3,1)], [('a',3,3,1.5)], [('a',float('inf'),3,1)]])
def test_nesting_rejeita_medidas_e_quantidades_invalidas(items):
    with pytest.raises(ValueError):
        nest(items, 20, 20)


def test_bgremove_exige_modelo_local_antes_de_importar_rembg(tmp_path):
    with pytest.raises(ValueError, match='model_path'):
        remove_background('origem', 'destino')
    with pytest.raises(FileNotFoundError):
        remove_background('origem', 'destino', str(tmp_path/'ausente.onnx'))


def test_bgremove_publica_png_sem_sobrescrever_e_aplica_alpha(tmp_path, monkeypatch):
    source, target = tmp_path/'source.png', tmp_path/'result.png'
    Image.new('RGBA',(10,10),(10,20,30,80)).save(source)
    target.write_bytes(b'original')
    model = tmp_path/'local.onnx'
    model.write_bytes(b'session mock')
    sessions = []
    def new_session(name, **kwargs):
        sessions.append((name,kwargs));return 'local'
    monkeypatch.setitem(sys.modules,'rembg',SimpleNamespace(
        new_session=new_session, remove=lambda im,session:im))
    output = remove_background(str(source), str(target), str(model), alpha_cut=100)
    assert target.read_bytes() == b'original'
    with Image.open(output) as image:
        assert image.mode == 'RGBA' and image.getchannel('A').getextrema() == (0,0)
    assert sessions == [('u2net_custom',{'model_path':str(model)})]
    assert not list(tmp_path.glob('*.part'))
