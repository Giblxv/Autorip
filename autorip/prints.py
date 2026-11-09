"""Catálogo leve da fila PRT, com invalidação por identidade dos arquivos.

O cache é somente para consulta: ações de mover/excluir continuam validando o
arquivo real. Nenhum caminho ou conteúdo é persistido fora do diretório do app.
"""
import os
import stat
import threading
from urllib.parse import urlencode

from .prt import read_header

MAX_CACHED_PRINTS = 512


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _optional_signature(path):
    try:
        info = os.stat(path, follow_symlinks=False)
        return (info.st_mode, *_signature(info))
    except OSError:
        return None


class PrintCatalog:
    def __init__(self):
        self._cache = {}
        self._lock = threading.Lock()

    def list_prints(self, folder, margins, thumbnail_folder, read_metadata):
        with self._lock:
            return self._scan(folder, margins, thumbnail_folder, read_metadata)

    def _scan(self, folder, margins, thumbnail_folder, read_metadata):
        previous, current, result = self._cache, {}, []
        try:
            entries = os.scandir(folder)
        except (FileNotFoundError, NotADirectoryError):
            self._cache = {}
            return []
        with entries:
            for entry in entries:
                if not entry.name.lower().endswith(".prt"):
                    continue
                try:
                    info = entry.stat(follow_symlinks=False)
                    if not stat.S_ISREG(info.st_mode):
                        continue
                    key = (_signature(info), _optional_signature(entry.path + ".meta.json"))
                    cached = previous.get(entry.path)
                    if cached is not None and cached[0] == key:
                        header, metadata = cached[1]
                    else:
                        header = read_header(entry.path)
                        metadata = read_metadata(entry.path)
                    if len(current) < MAX_CACHED_PRINTS:
                        current[entry.path] = (key, (header, metadata))
                    rows = header["n_rows"] - int(sum(margins) * header["dpi_y"])
                    width, height = metadata if metadata else (
                        header["n_dots"] / header["dpi_x"] * 2.54,
                        max(rows, 0) / header["dpi_y"] * 2.54)
                    stem = os.path.splitext(entry.name)[0]
                    thumb = _optional_signature(os.path.join(thumbnail_folder, stem + ".jpg"))
                    version = ".".join(map(str, thumb)) if thumb else "missing"
                    item = dict(name=entry.name, mb=round(info.st_size / 1048576, 1),
                                mtime=int(info.st_mtime), width_cm=round(width, 2),
                                height_cm=round(height, 2),
                                thumb="/api/thumb?" + urlencode({"name": stem, "v": version}))
                    # Preserve nanossegundos para o FIFO e desempate por nome estável.
                    result.append((info.st_mtime_ns, entry.name.casefold(), entry.name, item))
                except (OSError, ValueError, TypeError, KeyError, OverflowError):
                    # Um arquivo que sumiu ou está inválido não bloqueia os demais.
                    continue
        self._cache = current
        result.sort(key=lambda row: row[:3])
        return [row[3] for row in result]
