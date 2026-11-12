import json
from pathlib import Path

from agent.print_agent import Config, State, move_unique, sha256


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


def test_config_defaults_to_safe_mode(tmp_path):
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
    assert config.auto_print is False
    assert config.dry_run is False
    assert all(folder.exists() for folder in folders)
