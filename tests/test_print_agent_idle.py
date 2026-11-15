import json
import logging
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from agent import print_agent as core
from agent.service import defaults


@pytest.fixture
def config(tmp_path,monkeypatch):
    monkeypatch.setenv("APPDATA",str(tmp_path))
    path=tmp_path/"print-agent.json";values=defaults(path)
    values.update(network_discovery=False,poll_seconds=.5,stable_seconds=.5)
    path.write_text(json.dumps(values))
    return core.Config.load(path)


def test_estabilidade_compartilhada_cache_invalidacao_e_remocao(config):
    clock=SimpleNamespace(now=0)
    tracker=core.SafeFileTracker(.5,clock=lambda:clock.now)
    files=[]
    for index in range(100):
        path=config.output_folder/f"{index}.PRT";path.write_bytes(b"file")
        files.append((path,core.file_signature(path)))
    assert tracker.ready(files)==[]
    clock.now=.49;assert tracker.ready(files)==[]
    clock.now=.5;assert tracker.ready(files)==files
    for path,signature in files:tracker.handled(path,signature)
    clock.now=500;assert tracker.ready(files)==[]
    changed=files[0][0];changed.write_bytes(b"replacement-longer")
    files[0]=(changed,core.file_signature(changed))
    assert tracker.ready(files)==[]
    clock.now+=.5;assert tracker.ready(files)==[files[0]]
    tracker.ready(files[1:]);assert changed not in tracker.entries
    tracker.ready([]);assert tracker.entries=={}


class StopAfterScans:
    def __init__(self,clock,scans):self.clock=clock;self.scans=scans;self.ticks=0
    def is_set(self):return self.ticks>=self.scans
    def wait(self,seconds):self.clock.now+=seconds;self.ticks+=1;return self.is_set()


def test_monitor_seguro_hash_uma_vez_e_novo_inicio_verifica_antes_de_imprimir(config,monkeypatch):
    clock=SimpleNamespace(now=0);original_tracker=core.SafeFileTracker
    monkeypatch.setattr(core,"SafeFileTracker",lambda seconds:original_tracker(seconds,clock=lambda:clock.now))
    paths=[]
    for index in range(4):
        path=config.output_folder/f"{index}.PRT";path.write_bytes(b"test-file");paths.append(path)
    original_hash=core.sha256;hashed=[]
    def hash_file(path,stop_event=None):
        hashed.append(path.name);return original_hash(path,stop_event)
    monkeypatch.setattr(core,"sha256",hash_file)
    monkeypatch.setattr(core,"stable",lambda *args:pytest.fail("O modo seguro verifica a estabilidade em lote"))
    core.run(config,logging.getLogger("idle-test"),stop_event=StopAfterScans(clock,8))
    assert sorted(hashed)==sorted(path.name for path in paths)
    calls=[]
    class Driver:
        def __init__(self,*args):pass
        def open_job(self,path):calls.append(("open",path.name))
        def start_print(self):calls.append(("print",None))
        def wait_confirmation(self):return True
    stable=[]
    monkeypatch.setattr(core,"stable",lambda path,*args:stable.append(path.name) or True)
    monkeypatch.setattr(core,"PrintExpDriver",Driver)
    config.auto_print=True
    core.run(config,logging.getLogger("idle-test"),once=True)
    assert len(hashed)==8 and sorted(stable)==sorted(path.name for path in paths)
    assert sum(action=="print" for action,name in calls)==4
    assert len(list(config.printed_folder.glob("*.PRT")))==4


def test_impressao_rejeita_assinatura_de_estabilidade_precalculada(config):
    config.auto_print=True;path=config.output_folder/"test.PRT";path.write_bytes(b"prt")
    with pytest.raises(ValueError,match="própria verificação"):
        core.process(path,config,None,None,logging.getLogger("idle-test"),settled_signature=core.file_signature(path))


def test_parar_cancela_hash_entre_blocos_sem_registrar_ou_imprimir(config,monkeypatch):
    path=config.output_folder/"large.PRT";path.write_bytes(b"x"*(3*1024*1024))
    stop=threading.Event();original=core.hashlib.sha256;processed=[]
    class Hash:
        def __init__(self):self.hash=original()
        def update(self,chunk):processed.append(len(chunk));self.hash.update(chunk);stop.set()
        def hexdigest(self):return self.hash.hexdigest()
    monkeypatch.setattr(core.hashlib,"sha256",Hash)
    monkeypatch.setattr(core,"stable",lambda *args:True)
    state=core.State(config.state_db)
    try:
        assert not core.process(path,config,state,None,logging.getLogger("idle-test"),stop_event=stop)
        assert processed==[1024*1024]
        assert state.connection.execute("SELECT count(*) FROM jobs").fetchone()[0]==0
    finally:state.close()


def test_parada_interrompe_espera_de_estabilidade(config):
    path=config.output_folder/"test.PRT";path.write_bytes(b"prt")
    waits=[]
    stop=SimpleNamespace(wait=lambda seconds:waits.append(seconds) or True)
    assert not core.stable(path,30,stop)
    assert waits==[30]


def test_arquivo_alterado_durante_hash_permanece_pendente(config,monkeypatch):
    path=config.output_folder/"test.PRT";path.write_bytes(b"before")
    original=core.sha256
    def changing(path,stop_event=None):
        digest=original(path,stop_event);path.write_bytes(b"changed-content");return digest
    monkeypatch.setattr(core,"sha256",changing);monkeypatch.setattr(core,"stable",lambda *args:True)
    config.auto_print=True;state=core.State(config.state_db)
    try:
        assert not core.process(path,config,state,None,logging.getLogger("idle-test"))
        assert state.connection.execute("SELECT count(*) FROM jobs").fetchone()[0]==0
    finally:state.close()


def test_varredura_ignora_arquivo_removido_e_diretorio_com_extensao_prt(config):
    path=config.output_folder/"existing.PRT";path.write_bytes(b"prt")
    directory=config.output_folder/"folder.PRT";directory.mkdir()
    missing=config.output_folder/"gone.PRT"
    folder=SimpleNamespace(glob=lambda pattern:[missing,directory,path])
    assert core.scan_prts(folder)==[(path,core.file_signature(path))]


def test_leitura_temporariamente_bloqueada_e_retentada(config,monkeypatch):
    path=config.output_folder/"test.PRT";path.write_bytes(b"prt")
    original=core.sha256;attempts=[]
    def blocked(path,stop_event=None):
        attempts.append(path)
        if len(attempts)==1:raise PermissionError("sharing violation")
        return original(path,stop_event)
    monkeypatch.setattr(core,"sha256",blocked);monkeypatch.setattr(core,"stable",lambda *args:True)
    state=core.State(config.state_db)
    try:
        assert not core.process(path,config,state,None,logging.getLogger("idle-test"))
        assert core.process(path,config,state,None,logging.getLogger("idle-test"))
        assert state.state_for(path.name,original(path))=="aguardando_autorizacao"
    finally:state.close()


def test_varredura_lenta_nao_encurta_janela_de_estabilidade(config):
    path=config.output_folder/"test.PRT";path.write_bytes(b"prt")
    files=[(path,core.file_signature(path))];clock=SimpleNamespace(now=10)
    tracker=core.SafeFileTracker(3,clock=lambda:clock.now)
    assert tracker.ready(files,observed_at=0)==[]
    clock.now=20
    assert tracker.ready(files,observed_at=10.2)==[]
    clock.now=30
    assert tracker.ready(files,observed_at=22)==files
