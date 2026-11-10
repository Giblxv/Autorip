"""Testes do orquestrador das 15 rodadas, sem subprocessos reais."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import repeat_regression


def test_repeticoes_executam_todas_as_rodadas_em_processos_separados(tmp_path, monkeypatch):
    calls = []
    def fake_run(argv, check):
        calls.append((argv, check))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(repeat_regression.subprocess, "run", fake_run)
    output = tmp_path / "report.md"
    assert repeat_regression.run_repeated(15, output, ["tests/test_config.py"]) == 0
    assert len(calls) == 15
    assert all(call[0][-1] == "tests/test_config.py" and call[1] is False for call in calls)
    report = output.read_text(encoding="utf-8")
    assert "Executadas: 15/15; falhas: 0" in report
    assert "| 15/15 | PASS |" in report


def test_falha_intermediaria_nao_e_mascarada(tmp_path, monkeypatch):
    calls = []
    def fake_run(argv, check):
        calls.append(argv)
        return SimpleNamespace(returncode=3 if len(calls) == 4 else 0)
    monkeypatch.setattr(repeat_regression.subprocess, "run", fake_run)
    output = tmp_path / "report.md"
    assert repeat_regression.run_repeated(5, output, []) == 1
    assert len(calls) == 5
    assert "falhas: 1" in output.read_text(encoding="utf-8")
    assert "FAIL (3)" in output.read_text(encoding="utf-8")


@pytest.mark.parametrize("rounds", [0, -1, 101])
def test_limite_de_rodadas(tmp_path, rounds):
    with pytest.raises(ValueError, match="rodadas"):
        repeat_regression.run_repeated(rounds, tmp_path / "report.md", [])
