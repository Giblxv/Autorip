import dataclasses
import json
import math
from pathlib import Path
import random
import sys
import xml.etree.ElementTree as ET

from PIL import Image
import pytest

from autorip.layout import LayoutItem, auto_pack, sheet_height, layout_to_svg
from autorip.nesting import nest, nest_layout, nest_sheets, Placements, check_layout, utilization
from autorip import server
from test_server import panel, request


def piece(name, w, h, **kwargs):
    return LayoutItem(name, name, '', 100, 100, w, h, **kwargs)


def test_maxrects_aproveita_espaco_sob_peca_menor_sem_rectpack(monkeypatch):
    monkeypatch.setitem(sys.modules, 'rectpack', None)
    items = [piece('a', 6, 6), piece('b', 4, 4), piece('c', 4, 2)]
    before = [dataclasses.asdict(item) for item in items]
    packed = nest(items, sheet_width_cm=10, margin_cm=0, gap_cm=0)
    assert sheet_height(auto_pack(items, 10, 0, 0), 0) == 8
    assert sheet_height(packed, 0) == 6
    assert check_layout(packed, 10, 0, 0)
    assert utilization(packed, 10, 0, 0) == 1
    assert [dataclasses.asdict(item) for item in items] == before
    assert [item.id for item in packed] == ['a', 'b', 'c']
    assert all(a is not b for a, b in zip(items, packed))


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
def test_peca_que_so_cabe_apos_girar(rotation):
    w, h = (8, 3) if rotation in (0, 180) else (3, 8)
    item = piece('wide', w, h, rotation=rotation)
    with pytest.raises(ValueError):
        nest_layout([item], 4, 0, 0)
    packed = nest_layout([item], 4, 0, 0, True)
    assert packed[0].rotation == (rotation + 90) % 360
    assert sheet_height(packed, 0) == 8
    assert check_layout(packed, 4, 0, 0)
    assert item.rotation == rotation


@pytest.mark.parametrize('seed', range(10))
def test_deterministico_sem_sobreposicao_e_nunca_mais_alto_que_faixas(seed):
    rng = random.Random(seed)
    items = [piece(str(i), rng.uniform(.1, 25), rng.uniform(.1, 40)) for i in range(15)]
    packed = nest_layout(iter(items), allow_rotation=True)
    assert check_layout(packed)
    assert packed == nest_layout(items, allow_rotation=True)
    assert sheet_height(packed) <= sheet_height(auto_pack(items)) + 1e-6
    assert 0 < utilization(packed) <= 1


@pytest.mark.parametrize('kwargs', [dict(sheet_width_cm=0), dict(sheet_width_cm=59),
    dict(sheet_width_cm=float('nan')), dict(margin_cm=-1), dict(margin_cm=29),
    dict(gap_cm=-.1), dict(gap_cm=float('inf')), dict(allow_rotation='sim'),
    dict(sheet_width_cm=True)])
def test_parametros_invalidos_rejeitados(kwargs):
    with pytest.raises(ValueError):
        nest_layout([piece('a', 2, 3)], **kwargs)


@pytest.mark.parametrize('field', ['width_cm', 'height_cm', 'x_cm', 'y_cm'])
@pytest.mark.parametrize('value', [float('nan'), float('inf')])
def test_verificador_rejeita_valores_nao_finitos(field, value):
    item = piece('a', 2, 3)
    setattr(item, field, value)
    assert not check_layout([item])


def test_verificador_gap_margens_rotacao_e_aproveitamento_invalido():
    assert not check_layout([piece('a', 2, 3, rotation=45)])
    assert not check_layout([piece('a', 2, 3, rotation=90.5)])
    assert not check_layout([piece('a', 2, 3, x_cm=-1)])
    assert not check_layout([piece('a', 2, 3, x_cm=57)])
    items = [piece('a', 2, 3, x_cm=.2, y_cm=.2), piece('b', 2, 3, x_cm=2.3, y_cm=.2)]
    assert not check_layout(items)
    assert check_layout(items, gap_cm=.1)
    with pytest.raises(ValueError):
        utilization(items)
    assert nest_layout([]) == [] and utilization([]) == 0


def test_aproveitamento_nao_estoura_com_medidas_grandes_finitas():
    items = [piece('large', 57, 1e308, x_cm=.2, y_cm=.2)]
    assert check_layout(items)
    assert utilization(items) == round(57 / 58, 4)


def test_compatibilidade_com_api_anterior_e_colecao_vazia():
    for fn in (nest, nest_sheets):
        out = fn([('a', 3, 4, 2)], 10, 20)
        assert isinstance(out, Placements) and len(out) == 2 and not out.unplaced
    assert isinstance(nest([], 10, 20), Placements)
    assert nest([], sheet_width_cm=10) == []


def test_svg_escapa_nome_de_arquivo():
    packed = nest_layout([piece('<script>alert(1)</script>.png', 5, 3)])
    svg = layout_to_svg(packed)
    root = ET.fromstring(svg)
    assert not root.findall('.//{http://www.w3.org/2000/svg}script')
    assert '<script>' not in svg


def art(app, name='art.png'):
    path = Path(app.s.hot_folder) / name
    Image.new('RGBA', (100, 200), (10, 50, 100, 127)).save(path, dpi=(100, 200))
    return path


def test_planejamento_por_http_preserva_fonte_fila_e_medidas_fisicas(panel, app):
    source = art(app)
    original = source.read_bytes()
    app.tokens.add('plan-token')
    status, body, _ = request(panel, '/api/layout/plan', 'POST', json.dumps({
        'sheet_width_cm': 10, 'margin_cm': .5, 'gap_cm': .2,
        'items': [{'name': source.name, 'width_cm': 3, 'quantity': 3}]}).encode(), {'X-Token': 'plan-token'})
    assert status == 200, body
    result = json.loads(body)
    assert len(result['items']) == 3
    assert all(i['width_cm'] == 3 and math.isclose(i['height_cm'], 3, rel_tol=.001) for i in result['items'])
    assert all(i['path'] == '' for i in result['items'])
    assert 0 < result['utilization'] <= 1
    assert source.read_bytes() == original and not app.jobs
    assert not list(Path(app.s.output_folder).glob('*.PRT'))
    ET.fromstring(result['svg'])
    assert str(app.home) not in body.decode()


@pytest.mark.parametrize('data', [None, [], {}, {'items': []},
    {'items': [{'name': '../art.png'}]}, {'items': [{'name': 'art.png', 'quantity': True}]},
    {'items': [{'name': 'art.png', 'quantity': 1.5}]}, {'items': [{'name': 'art.png', 'quantity': 101}]},
    {'items': [{'name': 'art.png', 'width_cm': 'nan'}]},
    {'sheet_width_cm': 'nan', 'items': [{'name': 'art.png'}]},
    {'items': [{'name': 'art.png'}] * 101}])
def test_planejamento_valida_antes_de_abrir_arquivos(app, monkeypatch, data):
    def forbid(*args):
        pytest.fail('Não deve ler arquivo com parâmetros inválidos')
    monkeypatch.setattr(server, 'inspect_image', forbid)
    with pytest.raises(ValueError):
        app.plan_layout(data)


def test_http_exige_login_bloqueia_concorrencia_e_libera_apos_erro(panel, app):
    body = json.dumps({'items': []}).encode()
    assert request(panel, '/api/layout/plan', 'POST', body)[0] == 401
    app.tokens.add('plan-token'); headers = {'X-Token': 'plan-token'}
    with app._layout_lock:
        assert request(panel, '/api/layout/plan', 'POST', body, headers)[0] == 429
    assert request(panel, '/api/layout/plan', 'POST', body, headers)[0] == 400
    assert app._layout_lock.acquire(blocking=False)
    app._layout_lock.release()
    assert request(panel, '/planner.js')[0] == 200


def test_arquivos_ausentes_invalidos_e_links_rejeitados(app, tmp_path):
    with pytest.raises(FileNotFoundError):
        app.plan_layout({'items': [{'name': 'missing.png'}]})
    bad = Path(app.s.hot_folder) / 'bad.png'; bad.write_bytes(b'not image')
    with pytest.raises(ValueError, match='dimensões'):
        app.plan_layout({'items': [{'name': bad.name}]})
    outside = tmp_path / 'outside.png'; Image.new('RGB', (10, 10)).save(outside)
    link = Path(app.s.hot_folder) / 'link.png'
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip('Links não disponíveis neste ambiente')
    with pytest.raises(FileNotFoundError):
        app.plan_layout({'items': [{'name': link.name}]})
