"""Executa a suíte pytest N vezes, falhando se qualquer rodada falhar.

A cada execução, os testes são iniciados em um processo novo, evitando
contaminação do estado global entre rodadas. O relatório preserva resultados
individuais e não apresenta como sucesso execuções incompletas.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile


def run_repeated(rounds: int, output: Path, pytest_args: list[str], timeout_seconds=600) -> int:
    if type(rounds) is not int or rounds < 1 or rounds > 100:
        raise ValueError("A quantidade de rodadas deve estar entre 1 e 100.")
    if (isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
        raise ValueError("O timeout por rodada precisa ser positivo e finito.")
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = ["| Rodada | Resultado | Duração |", "| --- | --- | --- |"]
    failed = 0
    for index in range(1, rounds + 1):
        started = time.monotonic()
        print(f"\n===== REGRESSÃO {index}/{rounds} =====", flush=True)
        try:
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", *pytest_args],
                                    check=False, timeout=timeout_seconds)
            code = result.returncode
        except subprocess.TimeoutExpired:
            print(f"Timeout na rodada {index}: {timeout_seconds}s", file=sys.stderr, flush=True)
            code = 124
        except OSError as exc:
            print(f"Falha ao iniciar pytest: {exc}", file=sys.stderr, flush=True)
            code = 127
        elapsed = time.monotonic() - started
        success = code == 0
        failed += not success
        rows.append(f"| {index}/{rounds} | {'PASS' if success else 'FAIL (' + str(code) + ')'} | {elapsed:.1f}s |")
        print(f"RODADA {index}/{rounds}: {'PASS' if success else 'FAIL'} ({elapsed:.1f}s)", flush=True)
        report = ("# Validação de regressão repetida\n\n"
            + f"Executadas: {index}/{rounds}; falhas: {failed}.\n\n"
            + "\n".join(rows) + "\n")
        # Preserve o último relatório completo se houver interrupção na escrita.
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=".regression-", delete=False) as temporary:
            temporary.write(report)
        try:
            os.replace(temporary.name, output)
        finally:
            try:
                os.unlink(temporary.name)
            except FileNotFoundError:
                pass
    print(f"FINAL: {rounds - failed}/{rounds} rodadas aprovadas.", flush=True)
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Repetir suíte de regressão sem ocultar falhas.")
    parser.add_argument("--rounds", type=int, default=15)
    parser.add_argument("--output", type=Path, default=Path("validation-15x.md"))
    parser.add_argument("--timeout-seconds", type=float, default=600)
    args, pytest_args = parser.parse_known_args()
    if pytest_args and pytest_args[0] == "--":
        pytest_args = pytest_args[1:]
    return run_repeated(args.rounds, args.output, pytest_args, args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
