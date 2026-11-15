"""Controle da janela; automação e SQLite vivem em uma única thread própria."""
from __future__ import annotations

from collections import deque
from contextlib import closing
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import queue
import sqlite3
import sys
import tempfile
import threading

from . import print_agent as core


def defaults(config_path: Path) -> dict:
    home=config_path.parent
    state_home=Path(os.environ.get("APPDATA",Path.home()))/"AutoRIP"
    program=Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parents[1]
    folders={"output_folder":home/"Saida","printed_folder":home/"Impressos","error_folder":home/"Erro"}
    config=core.Config(program,program/"PrintExpAgent.exe",None,**folders,
                       state_db=state_home/"print-state.sqlite3",log_file=state_home/"print-agent.log")
    values={key:str(value) if isinstance(value,Path) else value for key,value in asdict(config).items()}
    values["printexp_exe"]=""
    # Reutiliza somente as pastas já escolhidas no AutoRIP, sem mudar seu JSON.
    try:
        other=json.loads((home/"autorip.json").read_text(encoding="utf-8"))
        for key in folders:
            if isinstance(other.get(key),str) and other[key].strip():values[key]=other[key]
    except (OSError,ValueError,AttributeError):
        pass
    return values


class EventLog(logging.Handler):
    def __init__(self,service):
        super().__init__();self.service=service
        self.setFormatter(logging.Formatter("%(asctime)s · %(levelname)s · %(message)s",datefmt="%H:%M:%S"))

    def emit(self,record):
        self.service.message(self.format(record))


class AgentService:
    def __init__(self,config_path: Path,runner=core.run,driver_factory=core.PrintExpDriver):
        self.path=Path(config_path);self.runner=runner;self.driver_factory=driver_factory
        self.lock=threading.RLock();self.commands=queue.Queue();self.stop_event=threading.Event()
        self.save_done=threading.Event();self.save_done.set()
        self.status="parado";self.connection="Não verificado";self.error="";self.revision=0
        self.jobs=[];self.logs=deque(maxlen=200);self.addresses=[];self.network_busy=False
        self.closed=False;self.closing=False;self.file_handler=None
        self.values=defaults(self.path)
        try:
            if self.path.exists():
                raw=json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw,dict):raise ValueError("A configuração precisa ser um objeto JSON.")
                for key in ("program_dir","agent_exe","printexp_exe","output_folder","printed_folder","error_folder","state_db","log_file"):
                    if raw.get(key):raw[key]=str(Path(raw[key]).expanduser().resolve())
                self.values.update(raw)
        except (OSError,ValueError,TypeError) as exc:
            self.error=f"Não foi possível carregar as configurações: {exc}"
        self.log=logging.Logger("PrintExpAgent.UI",level=logging.INFO);self.log.addHandler(EventLog(self))
        self.thread=threading.Thread(target=self._work,name="printexp-automation",daemon=True);self.thread.start()
        self.commands.put(("history",dict(self.values)))
        self.refresh_network()

    def message(self,text):
        with self.lock:self.logs.append(text);self.revision+=1

    def update(self,**values):
        with self.lock:
            if any(getattr(self,key)!=value for key,value in values.items()):
                for key,value in values.items():setattr(self,key,value)
                self.revision+=1

    def snapshot(self,since=None):
        with self.lock:
            if since==self.revision:return None
            return dict(revision=self.revision,status=self.status,connection=self.connection,error=self.error,
                        jobs=[dict(row) for row in self.jobs],logs=list(self.logs),addresses=[dict(row) for row in self.addresses],
                        network_busy=self.network_busy,config=dict(self.values),closing=self.closing)

    def save(self,updates):
        with self.lock:
            if self.closing or self.closed or self.status in ("salvando","iniciando","monitorando","parando","testando"):
                raise RuntimeError("Pare o monitoramento antes de alterar as configurações.")
            values={**self.values,**updates}
            self.status="salvando";self.revision+=1;self.save_done.clear()
        try:
            for key in ("program_dir","agent_exe","printexp_exe","output_folder","printed_folder","error_folder","state_db","log_file"):
                if values.get(key):
                    value=Path(values[key]).expanduser()
                    values[key]=str((value if value.is_absolute() else self.path.parent/value).resolve())
            self.path.parent.mkdir(parents=True,exist_ok=True)
            fd,name=tempfile.mkstemp(prefix=".print-agent-",suffix=".json",dir=self.path.parent)
            temporary=Path(name)
            try:
                if hasattr(os,"fchmod"):os.fchmod(fd,0o600)
                with os.fdopen(fd,"w",encoding="utf-8") as target:
                    json.dump(values,target,ensure_ascii=False,indent=2);target.flush();os.fsync(target.fileno())
                core.Config.load(temporary)
                os.replace(temporary,self.path)
            finally:
                temporary.unlink(missing_ok=True)
            self.update(values=values,status="parado",error="",connection="Não verificado")
            self.message("Configurações salvas. O modo de impressão só muda no próximo início.")
            self.commands.put(("history",dict(values)))
        except Exception as exc:
            self.update(status="parado",error=str(exc))
            raise
        finally:self.save_done.set()

    def start(self):
        self._submit("start","iniciando")

    def test(self):
        self._submit("test","testando")

    def _submit(self,command,status):
        with self.lock:
            if self.closing or self.closed:raise RuntimeError("O agente está encerrado. Abra a interface novamente.")
            if self.status in ("salvando","iniciando","monitorando","parando","testando"):
                raise RuntimeError("Uma operação já está em andamento.")
            if not self.path.is_file():raise ValueError("Salve as configurações antes de iniciar.")
            self.stop_event.clear();self.status=status;self.error="";self.revision+=1
            self.commands.put((command,dict(self.values)))

    def stop(self):
        with self.lock:
            self.stop_event.set()
            if self.status in ("iniciando","monitorando"):self.status="parando";self.revision+=1

    def close(self):
        with self.lock:
            if self.closing:return
            self.closing=True;self.revision+=1;self.stop()
            self.commands.put(("close",None))

    def refresh_network(self):
        with self.lock:
            if self.network_busy or self.closing:return
            self.network_busy=True;self.revision+=1
        def read():
            try:self.update(addresses=core.local_ipv4s())
            except Exception:self.message("IPv4 indisponível. Confira o adaptador Wi-Fi/Ethernet.")
            finally:self.update(network_busy=False)
        threading.Thread(target=read,name="printexp-ipv4",daemon=True).start()

    def _history(self,values):
        try:
            path=Path(values["state_db"]).expanduser().resolve()
            if not path.exists():self.update(jobs=[]);return
            with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=.1)) as connection:
                connection.row_factory=sqlite3.Row
                rows=connection.execute("SELECT id,filename,state,attempts,error,updated_at FROM jobs ORDER BY updated_at DESC,id DESC LIMIT 200").fetchall()
                self.update(jobs=[dict(row) for row in rows])
        except (sqlite3.Error,ValueError,OSError,TypeError,KeyError):
            self.message("Histórico indisponível no momento; será atualizado ao iniciar.")

    def _work(self):
        com=None
        try:
            if os.name=="nt" and core.Application is not None:
                import comtypes
                comtypes.CoInitialize();com=comtypes
            while True:
                command,values=self.commands.get()
                if command=="close":self.save_done.wait();break
                if command=="history":self._history(values);continue
                try:
                    config=core.Config.load(self.path)
                    if self.file_handler is None or self.file_handler.baseFilename!=str(config.log_file):
                        if self.file_handler:
                            self.log.removeHandler(self.file_handler);self.file_handler.close()
                        self.file_handler=logging.FileHandler(config.log_file,encoding="utf-8")
                        self.file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
                        self.log.addHandler(self.file_handler)
                    if command=="test":
                        if core.portalocker is None:raise RuntimeError("portalocker não está instalado.")
                        try:
                            with core.portalocker.Lock(str(config.state_db.with_suffix(".lock")),mode="a+",timeout=0):
                                driver=self.driver_factory(config,self.log);driver.connect()
                        except core.portalocker.exceptions.LockException as exc:
                            raise RuntimeError("Pare a outra instância do agente antes de testar a conexão.") from exc
                        self.update(connection="PrintExp acessível")
                        self.log.info("Conexão com o PrintExp verificada. Nenhum trabalho foi enviado.")
                    else:
                        self.runner(config,self.log,stop_event=self.stop_event,on_jobs=lambda rows:self.update(jobs=rows),
                                    on_started=lambda:self.update(status="parando" if self.stop_event.is_set() else "monitorando"))
                    self.update(status="parado")
                except Exception as exc:
                    self.update(status="erro",error=str(exc))
                    self.log.exception("Operação interrompida: %s",exc)
        except Exception as exc:
            self.update(status="erro",error=f"Falha ao preparar a automação: {exc}")
        finally:
            if self.file_handler:self.file_handler.close()
            if com is not None:com.CoUninitialize()
            with self.lock:self.closed=True;self.revision+=1
