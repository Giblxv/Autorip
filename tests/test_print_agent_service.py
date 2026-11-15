import json
import logging
from pathlib import Path
import threading
import time
import sys
from types import SimpleNamespace

import pytest

from agent import print_agent as core
from agent.service import AgentService,defaults


@pytest.fixture
def config_file(tmp_path,monkeypatch):
    monkeypatch.setattr(core,"local_ipv4s",lambda:[])
    monkeypatch.setenv("APPDATA",str(tmp_path/"appdata"))
    path=tmp_path/"print-agent.json"
    values=defaults(path)
    values.update(network_discovery=False,poll_seconds=.5,stable_seconds=.5)
    path.write_text(json.dumps(values),encoding="utf-8")
    return path


def wait(predicate):
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.01)
    raise AssertionError("A operação do agente não terminou")


def shutdown(service):
    service.close();service.thread.join(timeout=5)
    assert not service.thread.is_alive()


def test_salvar_preserva_opcoes_avancadas_e_falha_sem_substituir_config(config_file):
    raw=json.loads(config_file.read_text());raw["open_hotkey"]="^a";raw["custom_option"]="preservar"
    config_file.write_text(json.dumps(raw))
    service=AgentService(config_file)
    try:
        service.save({"poll_seconds":1.5})
        saved=json.loads(config_file.read_text())
        assert saved["open_hotkey"]=="^a" and saved["custom_option"]=="preservar"
        assert saved["auto_print"] is False
        before=config_file.read_bytes()
        for updates in ({"auto_print":"false"},{"poll_seconds":float("nan")},{"printexp_port":0},
                        {"printed_folder":saved["output_folder"]},{"printexp_title_regex":"["}):
            with pytest.raises(ValueError):service.save(updates)
            assert config_file.read_bytes()==before
        assert not list(config_file.parent.glob(".print-agent-*.json"))
    finally:shutdown(service)


def test_monitoramento_e_diagnostico_usam_mesma_thread_sem_bloquear_interface(config_file):
    threads=[]
    def runner(config,log,stop_event,on_jobs,on_started):
        threads.append(threading.get_ident());on_started()
        on_jobs([dict(id=1,filename="arte.PRT",state="aguardando_autorizacao",attempts=0,error=None,updated_at="agora")])
        stop_event.wait(5)
    class Driver:
        def __init__(self,*args):pass
        def connect(self):threads.append(threading.get_ident())
    service=AgentService(config_file,runner=runner,driver_factory=Driver)
    try:
        for _ in range(2):
            service.start();wait(lambda:service.snapshot()["status"]=="monitorando")
            assert service.snapshot()["jobs"][0]["filename"]=="arte.PRT"
            with pytest.raises(RuntimeError):service.start()
            with pytest.raises(RuntimeError):service.save({"auto_print":True})
            with pytest.raises(RuntimeError):service.test()
            service.stop();wait(lambda:service.snapshot()["status"]=="parado")
        service.test();wait(lambda:service.snapshot()["connection"]=="PrintExp acessível")
        assert len(set(threads))==1 and threads[0]!=threading.get_ident()
        wait(lambda:not service.snapshot()["network_busy"])
        snapshot=service.snapshot()
        assert service.snapshot(snapshot["revision"]) is None
    finally:shutdown(service)


def test_encerrar_aguarda_operacao_atual_sem_matar_worker(config_file):
    release=threading.Event()
    def runner(config,log,stop_event,on_jobs,on_started):
        on_started();release.wait(5)
    service=AgentService(config_file,runner=runner)
    try:
        service.start();wait(lambda:service.snapshot()["status"]=="monitorando")
        service.close()
        assert service.snapshot()["status"]=="parando" and service.thread.is_alive()
        assert service.stop_event.is_set()
        release.set();wait(lambda:service.closed)
        with pytest.raises(RuntimeError):service.start()
    finally:release.set();shutdown(service)


@pytest.mark.parametrize("previous",["revisao_manual","impressao_solicitada","carregado","carregando","concluido"])
def test_trabalho_sem_confirmacao_nao_e_reenviado(config_file,monkeypatch,previous):
    config=core.Config.load(config_file);config.auto_print=True
    path=config.output_folder/"arte.PRT";path.write_bytes(b"test-prt")
    monkeypatch.setattr(core,"stable",lambda *args:True)
    state=core.State(config.state_db);digest=core.sha256(path)
    state.set(path,digest,previous)
    class Driver:
        def open_job(self,*args):pytest.fail("Não deve reenviar um trabalho pendente de revisão")
    try:
        core.process(path,config,state,Driver(),logging.getLogger("test-agent"))
        assert state.state_for(path.name,digest)==previous and path.exists()
    finally:state.close()


def test_confirmacao_negativa_preserva_arte_para_revisao_e_nao_imprime_novamente(config_file,monkeypatch):
    config=core.Config.load(config_file);config.auto_print=True
    path=config.output_folder/"arte.PRT";path.write_bytes(b"test-prt")
    monkeypatch.setattr(core,"stable",lambda *args:True)
    calls=[]
    class Driver:
        def open_job(self,*args):calls.append("open")
        def start_print(self):calls.append("print")
        def wait_confirmation(self):return False
    state=core.State(config.state_db)
    try:
        for _ in range(2):core.process(path,config,state,Driver(),logging.getLogger("test-agent"))
        assert calls==["open","print"] and path.exists()
        assert state.state_for(path.name,core.sha256(path))=="revisao_manual"
    finally:state.close()


def test_parar_apos_carregar_nao_solicita_impressao(config_file,monkeypatch):
    config=core.Config.load(config_file);config.auto_print=True
    path=config.output_folder/"arte.PRT";path.write_bytes(b"test-prt")
    stop=threading.Event();monkeypatch.setattr(core,"stable",lambda *args:True)
    class Driver:
        def open_job(self,*args):stop.set()
        def start_print(self):pytest.fail("Parada solicitada antes da impressão")
    state=core.State(config.state_db)
    try:
        core.process(path,config,state,Driver(),logging.getLogger("test-agent"),stop_event=stop)
        assert path.exists() and state.state_for(path.name,core.sha256(path))=="revisao_manual"
    finally:state.close()


def test_run_libera_lock_e_sqlite_ao_parar(config_file):
    config=core.Config.load(config_file);stop=threading.Event();events=[]
    core.run(config,logging.getLogger("test-agent"),stop_event=stop,on_started=stop.set,on_jobs=events.append)
    assert events==[[]]
    with config.state_db.with_suffix(".lock").open("a+") as handle:
        core.portalocker.lock(handle,core.portalocker.LOCK_EX|core.portalocker.LOCK_NB)
        core.portalocker.unlock(handle)
    state=core.State(config.state_db)
    try:assert state.state_for("missing","missing") is None
    finally:state.close()


def test_dry_run_explicitamente_solicitado_tem_prioridade(config_file):
    assert core.Config.load(config_file,dry_run=True).dry_run is True


def test_interface_preserva_banco_ja_usado_por_configuracao_antiga(config_file):
    raw=json.loads(config_file.read_text())
    del raw["state_db"];del raw["log_file"]
    config_file.write_text(json.dumps(raw))
    original=core.Config.load(config_file)
    state=core.State(original.state_db)
    state.set(original.output_folder/"antigo.PRT","hash-antigo","revisao_manual");state.close()
    service=AgentService(config_file)
    try:
        wait(lambda:len(service.snapshot()["jobs"])==1)
        assert Path(service.snapshot()["config"]["state_db"])==original.state_db
        service.save({"poll_seconds":1})
        saved=core.Config.load(config_file)
        assert saved.state_db==original.state_db and saved.log_file==original.log_file
        state=core.State(saved.state_db)
        try:assert state.state_for("antigo.PRT","hash-antigo")=="revisao_manual"
        finally:state.close()
    finally:shutdown(service)


@pytest.mark.parametrize("flags,auto_start",[([],True),(["--gui"],False),(["--gui","--start"],True)])
def test_entrada_abre_interface_sem_executar_worker_cli(config_file,monkeypatch,flags,auto_start):
    calls=[]
    monkeypatch.setattr(sys,"argv",["PrintExpAgent","--config",str(config_file),*flags])
    monkeypatch.setitem(sys.modules,"agent.gui",SimpleNamespace(launch=lambda path,auto_start:calls.append((path,auto_start)) or 0))
    monkeypatch.setattr(core,"run",lambda *args,**kwargs:pytest.fail("Não deve iniciar worker CLI na entrada gráfica"))
    assert core.main()==0
    assert calls==[(config_file,auto_start)]


def test_modo_headless_permanece_disponivel(config_file,monkeypatch):
    calls=[]
    monkeypatch.setattr(sys,"argv",["PrintExpAgent","--config",str(config_file),"--headless"])
    monkeypatch.setattr(core,"setup_logging",lambda path:logging.getLogger("headless-test"))
    monkeypatch.setattr(core,"run",lambda config,log,once:calls.append((config.auto_print,once)))
    assert core.main()==0 and calls==[(False,False)]


def test_salvamento_lento_nao_bloqueia_status_e_encerramento_aguarda_persistencia(config_file,monkeypatch):
    entered=threading.Event();release=threading.Event();errors=[]
    original=core.Config.load
    def delayed(path,*args,**kwargs):
        entered.set();release.wait(5)
        return original(path,*args,**kwargs)
    service=AgentService(config_file)
    monkeypatch.setattr(core.Config,"load",delayed)
    def save():
        try:service.save({"poll_seconds":1.5})
        except Exception as exc:errors.append(exc)
    writer=threading.Thread(target=save);writer.start()
    try:
        assert entered.wait(3)
        started=time.monotonic();snapshot=service.snapshot()
        assert snapshot["status"]=="salvando" and time.monotonic()-started<1
        with pytest.raises(RuntimeError):service.start()
        service.close();assert service.thread.is_alive() and not service.closed
        release.set();writer.join(timeout=5);wait(lambda:service.closed)
        assert not errors and json.loads(config_file.read_text())["poll_seconds"]==1.5
    finally:release.set();writer.join(timeout=5);shutdown(service)


def test_diagnostico_respeita_lock_de_outra_instancia(config_file):
    config=core.Config.load(config_file);calls=[]
    class Driver:
        def __init__(self,*args):pass
        def connect(self):calls.append("connect")
    service=AgentService(config_file,driver_factory=Driver)
    try:
        with core.portalocker.Lock(str(config.state_db.with_suffix(".lock")),mode="a+",timeout=0):
            service.test();wait(lambda:service.snapshot()["status"]=="erro")
            assert not calls and "outra instância" in service.snapshot()["error"]
        service.test();wait(lambda:service.snapshot()["connection"]=="PrintExp acessível")
        assert calls==["connect"]
    finally:shutdown(service)


def test_tela_recebe_modo_e_pastas_efetivamente_carregados(config_file):
    def runner(config,log,stop_event,on_jobs,on_started):
        on_started();stop_event.wait(5)
    service=AgentService(config_file,runner=runner)
    try:
        raw=json.loads(config_file.read_text())
        raw.update(auto_print=True,dry_run=True,output_folder=str(config_file.parent/"new-output"),open_hotkey="^a")
        config_file.write_text(json.dumps(raw))
        service.start();wait(lambda:service.snapshot()["status"]=="monitorando")
        shown=service.snapshot()["config"]
        assert shown["auto_print"] is True and shown["dry_run"] is True
        assert shown["output_folder"]==raw["output_folder"] and shown["open_hotkey"]=="^a"
        service.stop();wait(lambda:service.snapshot()["status"]=="parado")
        service.save({"poll_seconds":1})
        assert json.loads(config_file.read_text())["open_hotkey"]=="^a"
    finally:shutdown(service)
