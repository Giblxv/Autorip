import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import read_header


def artwork(tmp_path):
    path=tmp_path/'parallel.png'
    pixels=np.random.default_rng(782).integers(0,256,(103,77,4),dtype=np.uint8)
    Image.fromarray(pixels,'RGBA').save(path)
    return path


def test_workers_respeitam_a_afinidade_do_processo(monkeypatch):
    monkeypatch.setattr(engine.os, 'cpu_count', lambda: 16)
    monkeypatch.setattr(engine.os, 'sched_getaffinity', lambda _: {1, 3, 5})
    assert engine._available_cpu_count() == 3


def test_workers_usam_cpu_reportada_quando_afinidade_nao_existe(monkeypatch):
    monkeypatch.setattr(engine.os, 'cpu_count', lambda: 2)
    monkeypatch.delattr(engine.os, 'sched_getaffinity', raising=False)
    assert engine._available_cpu_count() == 2


@pytest.mark.parametrize('with_icc',[False,True])
def test_paralelismo_preserva_bytes_ordem_e_progresso(tmp_path,monkeypatch,with_icc):
    path=artwork(tmp_path)
    kwargs={}
    if with_icc:
        profile=Path(__file__).resolve().parents[1]/'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
        if not profile.is_file():pytest.skip('Perfil de avaliação local não está disponível')
        kwargs['icc_path']=str(profile)
    settings=Settings(label_enabled=True,margin_top_in=.15,margin_bottom_in=.15,
                      white_density=.6,white_planes=[4,7],**kwargs)
    monkeypatch.setattr(engine.os,'cpu_count',lambda:4)
    monkeypatch.setattr(engine,'RENDER_WORKERS_MAX',1)
    first=Rip(settings).process(str(path),str(tmp_path/'serial.PRT'),width_cm=2.54)
    names=set()
    original=Rip._render
    lock=threading.Lock()
    def recorded(*args,**kwargs):
        with lock:names.add(threading.current_thread().name)
        return original(*args,**kwargs)
    monkeypatch.setattr(Rip,'_render',recorded)
    monkeypatch.setattr(engine,'RENDER_WORKERS_MAX',4)
    progress=[]
    second=Rip(settings).process(str(path),str(tmp_path/'parallel.PRT'),width_cm=2.54,progress=progress.append)
    assert Path(first['output_path']).read_bytes()==Path(second['output_path']).read_bytes()
    assert any(name.startswith('autorip-render') for name in names)
    assert progress==sorted(progress) and progress[-1]==1.0


def test_falha_de_tira_paralela_nao_publica_prt_parcial(tmp_path,monkeypatch):
    path=artwork(tmp_path)
    original=Rip._render
    def interrupted(self,im,a0,*args):
        if a0>0:raise OSError('tira interrompida')
        return original(self,im,a0,*args)
    monkeypatch.setattr(Rip,'_render',interrupted)
    monkeypatch.setattr(engine.os,'cpu_count',lambda:4)
    with pytest.raises(OSError,match='tira interrompida'):
        Rip(Settings(label_enabled=False)).process(str(path),str(tmp_path/'failed.PRT'),width_cm=2.54)
    assert not list(tmp_path.glob('*.PRT'))
    assert not list(tmp_path.glob('*.part'))


def test_orcamento_compartilhado_recua_para_uma_thread(tmp_path,monkeypatch):
    path=artwork(tmp_path)
    monkeypatch.setattr(engine.os,'cpu_count',lambda:4)
    monkeypatch.setattr(engine,'MAX_STRIP_MEMORY_BYTES',30*1024*1024)
    names=set()
    original=Rip._render
    def recorded(*args,**kwargs):
        names.add(threading.current_thread().name)
        return original(*args,**kwargs)
    monkeypatch.setattr(Rip,'_render',recorded)
    info=Rip(Settings(label_enabled=False)).process(str(path),str(tmp_path/'bounded.PRT'),width_cm=2.54)
    assert not any(name.startswith('autorip-render') for name in names)
    assert read_header(info['output_path'])['n_dots']==720


@pytest.mark.parametrize('workers',[1,4])
@pytest.mark.parametrize('stop_after',[0,1])
@pytest.mark.parametrize('action',['pause','cancel'])
def test_controle_interrompe_antes_da_publicacao_inclusive_na_ultima_tira(tmp_path,monkeypatch,workers,stop_after,action):
    from autorip.server import JobPaused, JobCancelled
    exception = JobPaused if action == 'pause' else JobCancelled
    path=artwork(tmp_path)
    monkeypatch.setattr(engine,'RENDER_WORKERS_MAX',workers)
    monkeypatch.setattr(engine.os,'cpu_count',lambda:4)
    progress=[];published=[]
    def control():
        if progress and progress[-1]>=stop_after:
            raise exception()
    with pytest.raises(exception):
        Rip(Settings(label_enabled=False)).process(
            str(path),str(tmp_path/'controlled.PRT'),width_cm=2.54,
            progress=progress.append,control=control,
            before_publish=lambda *args:published.append(True))
    assert progress and not published
    assert not list(tmp_path.glob('*.PRT')) and not list(tmp_path.glob('*.part'))
    assert path.exists()
