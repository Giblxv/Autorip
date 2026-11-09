"""Executa a suíte pytest N vezes, falhando se qualquer rodada falhar.

A cada execução, os testes são iniciados em um processo novo, evitando
contaminação do estado global entre rodadas. O relatório preserva resultados
individuais e não apresenta como sucesso execuções incompletas.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


def run_repeated(rounds: int, output: Path, pytest_args: list[str]) -> int:
    if rounds < 1 or rounds > 100:
        raise ValueError("A quantidade de rodadas deve estar entre 1 e 100.")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = ["| Rodada | Resultado | Duração |", "| --- | --- | --- |"]
    failed = 0
    for index in range(1, rounds + 1):
        started = time.monotonic()
        print(f"\n===== REGRESSÃO {index}/{rounds} =====", flush=True)
        try:
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", *pytest_args],
                                    check=False)
            code = result.returncode
        except OSError as exc:
            print(f"Falha ao iniciar pytest: {exc}", file=sys.stderr, flush=True)
            code = 127
        elapsed = time.monotonic() - started
        success = code == 0
        failed += not success
        rows.append(f"| {index}/{rounds} | {'PASS' if success else 'FAIL (' + str(code) + ')'} | {elapsed:.1f}s |")
        print(f"RODADA {index}/{rounds}: {'PASS' if success else 'FAIL'} ({elapsed:.1f}s)", flush=True)
        output.write_text(
            "# Validação de regressão repetida\n\n"
            + f"Executadas: {index}/{rounds}; falhas: {failed}.\n\n"
            + "\n".join(rows) + "\n",
            encoding="utf-8",
        )
    print(f"FINAL: {rounds - failed}/{rounds} rodadas aprovadas.", flush=True)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Repetir suíte de regressão sem ocultar falhas.")
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("validation-15x.md"))
    args, pytest_args = parser.parse_known_args()
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    return run_repeated(args.rounds, args.output, pytest_args)


if __name__ == "__main__":
    raise SystemExit(main())
