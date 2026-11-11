"""ProcessPool experimental para lotes de artes independentes.

Não é usado pelo servidor padrão. Cada processo cria seu próprio Rip e escreve
um PRT isolado, evitando compartilhar objetos Pillow/LittleCMS entre processos.
"""
from __future__ import annotations

import multiprocessing as mp
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .config import Settings
from .engine import Rip


def _process_one(payload):
    source, destination, settings_data, width_cm = payload
    settings = Settings(**settings_data)
    info = Rip(settings).process(source, destination, width_cm=width_cm)
    return {
        "source": source,
        "output_path": info["output_path"],
        "n_rows": info["n_rows"],
        "n_dots": info["n_dots"],
    }


def process_files(
    sources: Iterable[str | os.PathLike],
    settings: Settings,
    output_dir: str | os.PathLike,
    *,
    width_cm: float | None = None,
    max_workers: int | None = None,
):
    """Processa artes independentes em processos isolados.

    O executor é deliberadamente opt-in. ``settings`` precisa ser serializável
    por dataclass; cada worker recebe uma cópia e não compartilha estado ICC,
    Pillow ou arquivos temporários com os demais workers.
    """
    settings = settings.validate()
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payloads = []
    for source in sources:
        source = Path(source)
        payloads.append((str(source), str(output / f"{source.stem}.PRT"), asdict(settings), width_cm))
    if not payloads:
        return []
    workers = max_workers or min(len(payloads), os.cpu_count() or 1)
    if type(workers) is not int or workers < 1:
        raise ValueError("max_workers precisa ser um inteiro positivo.")
    context = mp.get_context("spawn")
    with ProcessPoolExecutor(max_workers=workers, mp_context=context) as pool:
        return list(pool.map(_process_one, payloads))
