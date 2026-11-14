import json

import logging

import pytest

import agent.print_agent as print_agent
from agent.print_agent import Config, PrintExpDriver, State, UIPICompatibilityError, ensure_uipi_compatible, move_unique, sha256


def test_sha256_and_move_unique(tmp_path):
    source = tmp_path / "pedido.PRT"
    source.write_bytes(b"prt-test")
    assert sha256(source)

    target = tmp_path / "impressos"
    target.mkdir()
    (target / source.name).write_bytes(b"old")
    moved = move_unique(source, target)

    assert moved.name == "pedido_1.PRT"
    assert moved.read_bytes() == b"prt-test"


def test_state_is_persistent(tmp_path):
    db = tmp_path / "state.sqlite3"
    source = tmp_path / "pedido.PRT"
    source.write_bytes(b"data")
    digest = sha256(source)

    state = State(db)
    state.set(source, digest, "detectado")
    state.close()

    reopened = State(db)
    assert reopened.state_for(source.name, digest) == "detectado"
    reopened.close()


def test_config_defaults_to_safe_mode(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    monkeypatch.setenv("APPDATA", str(appdata))
    folders = [tmp_path / name for name in ("out", "printed", "error")]
    config_path = tmp_path / "print-agent.json"
    config_path.write_text(
        json.dumps(
            {
                "program_dir": str(tmp_path),
                "agent_exe": str(tmp_path / "PrintExpAgent.exe"),
                "printexp_exe": "",
                "output_folder": str(folders[0]),
                "printed_folder": str(folders[1]),
                "error_folder": str(folders[2]),
            }
        ),
        encoding="utf-8",
    )

    config = Config.load(config_path)
    assert config.state_db.parent == appdata / "AutoRIP"
    assert config.log_file.parent == appdata / "AutoRIP"
    assert config.auto_print is False
    assert config.dry_run is False
    assert config.uipi_guard is True
    assert all(folder.exists() for folder in folders)


@pytest.mark.parametrize(
    ("agent_level", "target_level"),
    [(0x2000, 0x2000), (0x3000, 0x2000), (None, 0x4000), (0x2000, None)],
)
def test_uipi_allows_equal_lower_or_unknown_levels(agent_level, target_level):
    ensure_uipi_compatible(agent_level, target_level)


def test_uipi_blocks_lower_integrity_agent():
    with pytest.raises(UIPICompatibilityError, match="mesmo nível de privilégio"):
        ensure_uipi_compatible(0x2000, 0x3000)


def test_driver_checks_uipi_before_focus(tmp_path, monkeypatch):
    folders = [tmp_path / name for name in ("out", "printed", "error")]
    config = Config(
        program_dir=tmp_path,
        agent_exe=tmp_path / "agent.exe",
        printexp_exe=None,
        output_folder=folders[0],
        printed_folder=folders[1],
        error_folder=folders[2],
        state_db=tmp_path / "state.sqlite3",
        log_file=tmp_path / "agent.log",
    )
    config.validate()
    driver = PrintExpDriver(config, logging.getLogger("test-print-agent"))

    class Window:
        def wait(self, *_args, **_kwargs):
            return None

        def process_id(self):
            return 321

        def set_focus(self):
            raise AssertionError("set_focus não deve ocorrer após bloqueio UIPI")

    driver.window = Window()
    monkeypatch.setattr(print_agent, "process_integrity_level", lambda pid=None: 0x3000 if pid == 321 else 0x2000)
    with pytest.raises(UIPICompatibilityError):
        driver._check_uipi()
