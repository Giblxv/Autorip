import os
from pathlib import Path
from urllib.parse import parse_qs,urlsplit

import numpy as np
from PIL import Image

from autorip import prints
from autorip.prt import PrtWriter


def output(app, name='art.PRT', dots=32):
    path = Path(app.s.output_folder)/name
    writer = PrtWriter(path,300,300,20,dots)
    writer.write_block([np.zeros((20,dots),dtype=np.uint8)]*12)
    writer.close()
    return path


def test_consultas_sem_mudancas_nao_reabrem_cabecalhos_nem_sidecars(app,monkeypatch):
    output(app)
    calls=[]
    original=prints.read_header
    def load(path): calls.append(path);return original(path)
    monkeypatch.setattr(prints,'read_header',load)
    metadata=[]
    original_metadata=app._read_output_metadata
    def read_meta(path): metadata.append(path);return original_metadata(path)
    monkeypatch.setattr(app,'_read_output_metadata',read_meta)
    first=app.list_prints()
    assert all(app.list_prints()==first for _ in range(5))
    assert len(calls)==len(metadata)==1


def test_sidecar_novo_e_alterado_invalidam_cache(app):
    path=output(app)
    assert app.list_prints()[0]['width_cm'] != 8
    app._write_output_metadata(str(path),dict(width_cm=8,height_cm=4))
    assert app.list_prints()[0]['width_cm']==8
    app._write_output_metadata(str(path),dict(width_cm=7,height_cm=3))
    assert app.list_prints()[0]['width_cm']==7
    Path(str(path)+'.meta.json').unlink()
    assert app.list_prints()[0]['width_cm'] != 7


def test_prt_substituido_ou_truncado_e_revalidado(app):
    path=output(app)
    assert app.list_prints()[0]['width_cm']==.27
    staged=output(app,'replacement.PRT',300)
    os.replace(staged,path)
    assert app.list_prints()[0]['width_cm']==2.54
    path.write_bytes(b'invalid')
    assert app.list_prints()==[]


def test_margens_alteradas_recalculam_fallback_sem_reler_prt(app):
    output(app)
    app.s.margin_top_in=app.s.margin_bottom_in=0
    before=app.list_prints()[0]['height_cm']
    app.s.margin_top_in=.05
    assert app.list_prints()[0]['height_cm']<before


def test_miniatura_nova_no_mesmo_nome_altera_url_do_cache(app):
    output(app)
    first=app.list_prints()[0]['thumb']
    folder=Path(app.home)/'thumbs'/'by_name'
    folder.mkdir(parents=True,exist_ok=True)
    thumb=folder/'art.jpg'
    Image.new('RGB',(16,16),'red').save(thumb)
    second=app.list_prints()[0]['thumb']
    replacement=folder/'new.jpg'
    Image.new('RGB',(16,16),'blue').save(replacement)
    os.replace(replacement,thumb)
    third=app.list_prints()[0]['thumb']
    assert len({first,second,third})==3
    assert parse_qs(urlsplit(third).query)['name']==['art']


def test_fifo_preserva_ordem_dentro_do_mesmo_segundo(app):
    # Cria primeiro o mais novo para que ordem de listagem não decida a fila.
    newer=output(app,'newer.PRT');older=output(app,'older.PRT')
    base=1700000000*10**9
    os.utime(newer,ns=(base+900_000_000,base+900_000_000))
    os.utime(older,ns=(base+100_000_000,base+100_000_000))
    assert [p['name'] for p in app.list_prints()]==['older.PRT','newer.PRT']


def test_limite_cache_e_remocao_de_arquivos(app,monkeypatch):
    monkeypatch.setattr(prints,'MAX_CACHED_PRINTS',2)
    for i in range(4):output(app,f'art{i}.PRT')
    assert len(app.list_prints())==4 and len(app.print_catalog._cache)==2
    for path in Path(app.s.output_folder).glob('*.PRT'):path.unlink()
    assert app.list_prints()==[] and app.print_catalog._cache=={}


def test_consultas_concorrentes_compartilham_cache(app,monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    output(app)
    calls=[]
    original=prints.read_header
    def read(path):calls.append(path);return original(path)
    monkeypatch.setattr(prints,'read_header',read)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:app.list_prints(),range(12)))
    assert all(result==results[0] for result in results)
    assert len(calls)==1
