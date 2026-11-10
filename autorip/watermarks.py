"""Miniaturas de marca reutilizadas, sem reter o raster original ou seus metadados."""
from collections import OrderedDict
import os
import stat
import threading
import time

from PIL import Image

MAX_WATERMARK_CACHE_ENTRIES = 16
MAX_WATERMARK_CACHE_BYTES = 1024 * 1024
WATERMARK_CACHE_SECONDS = 60


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _identity(path):
    entry = os.stat(path, follow_symlinks=False)
    link = _signature(entry) if stat.S_ISLNK(entry.st_mode) else None
    target = os.stat(path) if link is not None else entry
    if not stat.S_ISREG(target.st_mode):
        raise ValueError('A marca precisa ser um arquivo regular.')
    return os.path.normcase(os.path.realpath(path)), _signature(target), link


class WatermarkCache:
    def __init__(self):
        self._images = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()

    def get(self, path, bounds, loader):
        identity = _identity(path)
        key = (identity, tuple(bounds))
        with self._lock:
            cached = self._images.get(key)
            if cached is not None:
                previous, created = cached
                if time.monotonic() - created < WATERMARK_CACHE_SECONDS:
                    self._images.move_to_end(key)
                    return previous.copy()
                self._images.pop(key)
                self._bytes -= previous.width * previous.height * 4
                previous.close()
        # Preserve a abertura por caminho: TIFF RGBA pode usar um caminho de
        # decode diferente quando recebe um objeto de arquivo em vez do nome.
        loaded = loader(path, bounds, orient=False)
        try:
            # Image.copy mantém ICC/EXIF em info. Retenha só os pixels pequenos.
            image = Image.frombytes('RGBA', loaded.size, loaded.tobytes())
        finally:
            loaded.close()
        try:
            stable = _identity(path) == identity
        except (OSError, ValueError):
            stable = False
        size = image.width * image.height * 4
        if not stable or size > MAX_WATERMARK_CACHE_BYTES or MAX_WATERMARK_CACHE_ENTRIES <= 0:
            return image
        with self._lock:
            # Outra thread pode ter preparado esta identidade durante o decode.
            if key not in self._images:
                self._images[key] = (image.copy(), time.monotonic())
                self._bytes += size
            self._images.move_to_end(key)
            while (len(self._images) > MAX_WATERMARK_CACHE_ENTRIES
                   or self._bytes > MAX_WATERMARK_CACHE_BYTES):
                _, (previous, _) = self._images.popitem(last=False)
                self._bytes -= previous.width * previous.height * 4
                previous.close()
        return image
