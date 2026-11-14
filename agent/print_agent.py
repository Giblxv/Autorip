from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

if not __package__ and not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from autorip.printexp_network import advertise_receiver, local_ipv4s

try:
    import portalocker
except ImportError:  # pragma: no cover - mensagem amigável no computador do usuário
    portalocker = None

try:
    from pywinauto import Application, Desktop
    from pywinauto.keyboard import send_keys
except ImportError:  # pragma: no cover - mensagem amigável no computador do usuário
    Application = Desktop = send_keys = None

VERSION = "0.1.1"
DEFAULT_POLL_SECONDS = 2.0
DEFAULT_STABLE_SECONDS = 3.0
DEFAULT_CONFIRM_TIMEOUT = 120.0


@dataclass
class Config:
    program_dir: Path
    agent_exe: Path
    printexp_exe: Path | None
    output_folder: Path
    printed_folder: Path
    error_folder: Path
    state_db: Path
    log_file: Path
    auto_print: bool = False
    dry_run: bool = False
    network_discovery: bool = True
    printexp_port: int = 9100
    poll_seconds: float = DEFAULT_POLL_SECONDS
    stable_seconds: float = DEFAULT_STABLE_SECONDS
    confirm_timeout: float = DEFAULT_CONFIRM_TIMEOUT
    printexp_title_regex: str = r".*PrintExp.*"
    open_hotkey: str = "^o"
    print_hotkey: str = "^p"
    confirmation_regexes: tuple[str, ...] = (
        r"completed",
        r"conclu[ií]do",
        r"finished",
        r"finalizado",
        r"printed",
        r"impresso",
    )

    @classmethod
    def load(cls, path: Path, dry_run: bool = False) -> "Config":
        with path.open(encoding="utf-8") as source:
            raw = json.load(source)
        if not isinstance(raw, dict):
            raise ValueError("A configuração do agente deve ser um objeto JSON.")

        def required_path(name: str) -> Path:
            value = raw.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"Configuração ausente: {name}")
            return Path(value).expanduser().resolve()

        printexp_value = raw.get("printexp_exe", "")
        printexp = Path(printexp_value).expanduser().resolve() if printexp_value else None
        state_dir = Path(os.environ.get("APPDATA", Path.home())) / "AutoRIP"
        state_db = Path(raw.get("state_db", state_dir / "print-state.sqlite3")).expanduser().resolve()
        log_file = Path(raw.get("log_file", state_dir / "print-agent.log")).expanduser().resolve()
        regexes = raw.get("confirmation_regexes", list(cls.confirmation_regexes))
        if not isinstance(regexes, list) or any(not isinstance(item, str) for item in regexes):
            raise ValueError("confirmation_regexes deve ser uma lista de textos.")

        config = cls(
            program_dir=required_path("program_dir"),
            agent_exe=required_path("agent_exe"),
            printexp_exe=printexp,
            output_folder=required_path("output_folder"),
            printed_folder=required_path("printed_folder"),
            error_folder=required_path("error_folder"),
            state_db=state_db,
            log_file=log_file,
            auto_print=bool(raw.get("auto_print", False)),
            dry_run=bool(raw.get("dry_run", dry_run)),
            network_discovery=raw.get("network_discovery", True),
            printexp_port=raw.get("printexp_port", 9100),
            poll_seconds=float(raw.get("poll_seconds", DEFAULT_POLL_SECONDS)),
            stable_seconds=float(raw.get("stable_seconds", DEFAULT_STABLE_SECONDS)),
            confirm_timeout=float(raw.get("confirm_timeout", DEFAULT_CONFIRM_TIMEOUT)),
            printexp_title_regex=str(raw.get("printexp_title_regex", cls.printexp_title_regex)),
            open_hotkey=str(raw.get("open_hotkey", cls.open_hotkey)),
            print_hotkey=str(raw.get("print_hotkey", cls.print_hotkey)),
            confirmation_regexes=tuple(regexes),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if type(self.network_discovery) is not bool:
            raise ValueError('network_discovery precisa ser booleano.')
        if type(self.printexp_port) is not int or not 1 <= self.printexp_port <= 65535:
            raise ValueError('printexp_port precisa estar entre 1 e 65535.')
        if self.poll_seconds < 0.5 or self.stable_seconds < 0.5:
            raise ValueError("poll_seconds e stable_seconds devem ser pelo menos 0.5.")
        if self.confirm_timeout < 5:
            raise ValueError("confirm_timeout deve ser pelo menos 5 segundos.")
        if self.output_folder == self.printed_folder or self.output_folder == self.error_folder:
            raise ValueError("output_folder, printed_folder e error_folder devem ser diferentes.")
        self.output_folder.mkdir(parents=True, exist_ok=True)
        self.printed_folder.mkdir(parents=True, exist_ok=True)
        self.error_folder.mkdir(parents=True, exist_ok=True)
        self.state_db.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)


class State:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
              id INTEGER PRIMARY KEY,
              filename TEXT NOT NULL,
              path TEXT NOT NULL,
              sha256 TEXT NOT NULL,
              state TEXT NOT NULL,
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              UNIQUE(filename, sha256)
            )
            """
        )
        self.connection.commit()

    def state_for(self, filename: str, sha256: str) -> str | None:
        row = self.connection.execute(
            "SELECT state FROM jobs WHERE filename=? AND sha256=?", (filename, sha256)
        ).fetchone()
        return row[0] if row else None

    def set(self, path: Path, sha256: str, state: str, error: str | None = None) -> None:
        self.connection.execute(
            """
            INSERT INTO jobs(filename,path,sha256,state,error)
            VALUES(?,?,?,?,?)
            ON CONFLICT(filename,sha256) DO UPDATE SET
              path=excluded.path, state=excluded.state, error=excluded.error,
              attempts=jobs.attempts+1, updated_at=CURRENT_TIMESTAMP
            """,
            (path.name, str(path), sha256, state, error),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()


class PrintExpDriver:
    def __init__(self, config: Config, log: logging.Logger):
        self.config = config
        self.log = log
        self.app: Any = None
        self.window: Any = None

    def connect(self) -> None:
        if Application is None or Desktop is None:
            raise RuntimeError("pywinauto não está instalado.")

        if self.config.printexp_exe and self.config.printexp_exe.exists():
            try:
                self.app = Application(backend="uia").connect(path=str(self.config.printexp_exe), timeout=10)
            except Exception:
                self.log.info("PrintExp não estava aberto; iniciando o executável configurado.")
                self.app = Application(backend="uia").start(str(self.config.printexp_exe))
        else:
            self.app = Application(backend="uia").connect(
                title_re=self.config.printexp_title_regex, timeout=10
            )

        self.window = self.app.window(title_re=self.config.printexp_title_regex)
        self.window.wait("visible", timeout=15)
        self.window.set_focus()

    def inspect(self) -> list[str]:
        """Retorna os identificadores visíveis para calibrar uma instalação nova."""
        if self.window is None:
            self.connect()
        try:
            return [str(item) for item in self.window.descendants()]
        except Exception as exc:
            raise RuntimeError("Não foi possível inspecionar os controles do PrintExp.") from exc

    def open_job(self, path: Path) -> None:
        if self.window is None:
            self.connect()
        self.log.info("Abrindo %s no PrintExp", path.name)
        self.window.set_focus()
        send_keys(self.config.open_hotkey)
        dialog = self._file_dialog()
        edit = dialog.child_window(control_type="Edit", found_index=0)
        edit.set_edit_text(str(path))
        dialog.child_window(title_re=r".*(Open|Abrir).*", control_type="Button").click()
        time.sleep(1)
        self._wait_job_visible(path)

    def start_print(self) -> None:
        if self.window is None:
            raise RuntimeError("PrintExp não está conectado.")
        self.log.info("Solicitando impressão no PrintExp")
        self.window.set_focus()
        send_keys(self.config.print_hotkey)

    def wait_confirmation(self) -> bool:
        deadline = time.monotonic() + self.config.confirm_timeout
        patterns = [re.compile(item, re.IGNORECASE) for item in self.config.confirmation_regexes]
        while time.monotonic() < deadline:
            texts = self._visible_texts()
            joined = "\n".join(texts)
            if any(pattern.search(joined) for pattern in patterns):
                return True
            if any(re.search(r"error|erro|failed|falha", text, re.IGNORECASE) for text in texts):
                raise RuntimeError("O PrintExp exibiu uma mensagem de erro.")
            time.sleep(2)
        raise TimeoutError("Não foi possível confirmar a conclusão no PrintExp.")

    def _file_dialog(self) -> Any:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            dialogs = Desktop(backend="uia").windows(title_re=r".*(Open|Abrir).*", visible_only=True)
            if dialogs:
                return dialogs[-1]
            time.sleep(0.25)
        raise TimeoutError("A janela de abertura de arquivo do PrintExp não apareceu.")

    def _wait_job_visible(self, path: Path) -> None:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if path.stem.lower() in " ".join(self._visible_texts()).lower():
                return
            time.sleep(1)
        raise TimeoutError(f"O PrintExp não confirmou o carregamento de {path.name}.")

    def _visible_texts(self) -> list[str]:
        if self.window is None:
            return []
        try:
            return [item.window_text() for item in self.window.descendants() if item.is_visible()]
        except Exception:
            return [self.window.window_text()]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable(path: Path, seconds: float) -> bool:
    try:
        first = path.stat()
    except OSError:
        return False
    time.sleep(seconds)
    try:
        second = path.stat()
    except OSError:
        return False
    return first.st_size > 0 and (first.st_size, first.st_mtime_ns) == (second.st_size, second.st_mtime_ns)


def move_unique(source: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    candidate = destination_dir / source.name
    index = 1
    while candidate.exists():
        candidate = destination_dir / f"{source.stem}_{index}{source.suffix}"
        index += 1
    shutil.move(str(source), str(candidate))
    return candidate


def setup_logging(path: Path) -> logging.Logger:
    logger = logging.getLogger("PrintExpAgent")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.addHandler(logging.StreamHandler())
    return logger


def process(path: Path, config: Config, state: State, driver: PrintExpDriver, log: logging.Logger) -> None:
    if not stable(path, config.stable_seconds):
        log.warning("Arquivo não estabilizou: %s", path.name)
        return
    digest = sha256(path)
    previous = state.state_for(path.name, digest)
    if previous == "concluido":
        log.info("Ignorando trabalho já concluído: %s", path.name)
        return

    state.set(path, digest, "detectado")
    if config.dry_run or not config.auto_print:
        state.set(path, digest, "aguardando_autorizacao")
        log.info("Modo seguro: %s aguardando auto_print=true (dry_run=%s)", path.name, config.dry_run)
        return

    try:
        state.set(path, digest, "carregando")
        driver.open_job(path)
        state.set(path, digest, "carregado")
        driver.start_print()
        state.set(path, digest, "impressao_solicitada")
        driver.wait_confirmation()
        state.set(path, digest, "concluido")
        destination = move_unique(path, config.printed_folder)
        log.info("Impressão confirmada: %s", destination.name)
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        state.set(path, digest, "revisao_manual", message)
        log.exception("Trabalho colocado em revisão manual: %s", path.name)


def run(config: Config, log: logging.Logger, once: bool = False) -> None:
    lock_path = config.state_db.with_suffix(".lock")
    lock_handle = lock_path.open("a+")
    if portalocker is None:
        raise RuntimeError("portalocker não está instalado.")
    try:
        portalocker.lock(lock_handle, portalocker.LOCK_EX | portalocker.LOCK_NB)
    except portalocker.exceptions.LockException as exc:
        raise RuntimeError("O agente PrintExp já está em execução.") from exc

    state = State(config.state_db)
    driver = PrintExpDriver(config, log)
    try:
        log.info("PrintExpAgent %s iniciado", VERSION)
        log.info("Monitorando %s", config.output_folder)
        with (advertise_receiver(config.printexp_port, log) if config.network_discovery and not once else nullcontext()):
            while True:
                for path in sorted(config.output_folder.glob("*.PRT"), key=lambda item: item.stat().st_mtime):
                    process(path, config, state, driver, log)
                if once:
                    return
                time.sleep(config.poll_seconds)
    finally:
        state.close()
        portalocker.unlock(lock_handle)
        lock_handle.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Agente local de automação do PrintExp")
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--dry-run", action="store_true", help="não abre nem imprime trabalhos")
    parser.add_argument("--once", action="store_true", help="processa os PRTs existentes e encerra")
    parser.add_argument("--inspect", action="store_true", help="lista controles visíveis do PrintExp e encerra")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.add_argument('--network-info', type=Path, help='grava os IPv4 locais em JSON e encerra, sem imprimir')
    parser.add_argument('--network-discovery', action='store_true', help='anuncia este computador na LAN sem observar ou imprimir arquivos')
    parser.add_argument('--print-port', type=int, default=9100, help='porta candidata anunciada para o PrintExp')
    args = parser.parse_args()

    if args.network_info:
        import zeroconf
        args.network_info.write_text(json.dumps({'local_ipv4s': local_ipv4s(), 'discovery_library': zeroconf.__version__, 'agent_version': VERSION}, ensure_ascii=False), encoding='utf-8')
        return 0
    if args.network_discovery:
        if not 1 <= args.print_port <= 65535:
            parser.error('--print-port precisa estar entre 1 e 65535')
        try:
            with advertise_receiver(args.print_port):
                while True:
                    time.sleep(1)
        except KeyboardInterrupt:
            return 0

    default_config = Path(os.environ.get("APPDATA", Path.home())) / "AutoRIP" / "print-agent.json"
    config_path = (args.config or default_config).expanduser().resolve()
    if not config_path.exists():
        print(f"Configuração não encontrada: {config_path}", file=sys.stderr)
        return 2

    config = Config.load(config_path, dry_run=args.dry_run)
    log = setup_logging(config.log_file)
    try:
        if args.inspect:
            driver = PrintExpDriver(config, log)
            for control in driver.inspect():
                print(control)
        else:
            run(config, log, once=args.once)
    except KeyboardInterrupt:
        log.info("Agente encerrado")
    except Exception as exc:
        log.exception("Falha fatal: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
