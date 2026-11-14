"""Helpers de caminhos para evitar traversal e sobrescrita silenciosa de trabalhos."""
import errno
import ctypes
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import time

_INVALID = re.compile(r'[\x00-\x1f<>:"/\\|?*]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def _canonical_folder(folder):
    return os.path.realpath(folder or os.curdir)


def safe_filename(value, default="arte"):
    raw = str(value or "").replace("\\", "/")
    name = raw.rsplit("/", 1)[-1]
    name = _INVALID.sub("_", name).strip(" .")
    if not name or name in (".", ".."):
        name = default
    stem, extension = os.path.splitext(name)
    if stem.upper() in _RESERVED:
        stem = "_" + stem
    max_length = 180
    if len(extension) >= max_length:
        extension = extension[-(max_length - 1):]
        stem = stem[:1] or "_"
    elif len(stem) + len(extension) > max_length:
        stem = stem[:max(1, max_length - len(extension))]
    return stem + extension


def rip_output_name(source_name, width_cm, height_cm, timestamp=None):
    """Monta o nome final preservando a base da arte e registrando tamanho/hora."""
    safe_source = safe_filename(source_name)
    stem = os.path.splitext(safe_source)[0]
    stamp = time.localtime(time.time() if timestamp is None else timestamp)
    dimensions = f"{float(width_cm):.2f}x{float(height_cm):.2f}cm"
    clock = time.strftime("%Y%m%d-%H%M%S", stamp)
    return safe_filename(f"{stem}_{dimensions}_{clock}.PRT")


def _suffixed_name(safe, index):
    if index == 0:
        return safe
    stem, extension = os.path.splitext(safe)
    suffix = f"_{index:03d}"
    max_extension = max(1, 180 - len(suffix) - 1)
    if len(extension) > max_extension:
        extension = extension[-max_extension:]
    stem = stem[:max(1, 180 - len(suffix) - len(extension))]
    return stem + suffix + extension


def reserve_unique_path(folder, name):
    """Cria um destino exclusivo vazio; o chamador deve preenchê-lo ou removê-lo."""
    folder = _canonical_folder(folder)
    os.makedirs(folder, exist_ok=True)
    safe = safe_filename(name)
    index = 0
    while True:
        candidate_name = _suffixed_name(safe, index)
        candidate = os.path.join(folder, candidate_name)
        try:
            fd = os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            index += 1
            continue
        else:
            os.close(fd)
            return candidate


def reservation_identity(path):
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_size != 0:
        raise ValueError("O destino nao e um placeholder vazio reservado pelo AutoRIP.")
    return info.st_dev, info.st_ino


def remove_reserved_path(path, identity):
    if not identity:
        return False
    try:
        info = os.lstat(path)
        if (stat.S_ISREG(info.st_mode) and info.st_size == 0
                and (info.st_dev, info.st_ino) == tuple(identity)):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def archive_marker_path(source):
    return source + ".autorip.json"


def file_sha256(path, chunk_size=1024 * 1024):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json_atomic(path, value, prefix=".autorip."):
    directory = _canonical_folder(os.path.dirname(path))
    path = os.path.join(directory, os.path.basename(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=directory)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=False, allow_nan=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            try:
                directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
                try: os.fsync(directory_fd)
                finally: os.close(directory_fd)
            except OSError:
                pass
    except BaseException:
        try: os.close(fd)
        except OSError: pass
        try: os.remove(temporary)
        except OSError: pass
        raise


def write_archive_marker(source, marker):
    """Persiste estado de um RIP junto da entrada antes de arquivá-la."""
    if not isinstance(marker, dict):
        raise ValueError("Marcador de arquivo invalido.")
    marker = dict(marker)
    marker["version"] = 1
    write_json_atomic(archive_marker_path(source), marker)


def read_archive_marker(source):
    path = archive_marker_path(source)
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > 8192:
            return None
        with open(path, encoding="utf-8") as marker_file:
            marker = json.load(marker_file)
        if not isinstance(marker, dict) or marker.get("version") != 1:
            return None
        if marker.get("phase") not in ("processing", "success", "error"):
            return None
        if marker.get("target") not in ("done", "error", "notify"):
            return None
        return marker
    except (OSError, ValueError, TypeError):
        return None


def remove_archive_marker(source):
    try:
        os.remove(archive_marker_path(source))
        return True
    except OSError:
        return False


def source_signature_matches(source, marker):
    expected = marker.get("source_signature") if isinstance(marker, dict) else None
    if (not isinstance(expected, list) or len(expected) != 5
            or any(type(value) is not int for value in expected)):
        return False
    try:
        if os.path.islink(source):
            return False
        info = os.stat(source, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode):
            return False
        actual = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]
        return actual == expected
    except OSError:
        return False


def manual_journal_path(output_folder, source):
    canonical = os.path.normcase(os.path.realpath(source))
    key = hashlib.sha256(canonical.encode("utf-8", "surrogatepass")).hexdigest()
    return os.path.join(_canonical_folder(output_folder), ".autorip_manual", key + ".json")


def find_marked_output(marker):
    """Localiza apenas uma saída cujo conteúdo corresponda ao hash persistido antes da publicação."""
    name, folder, expected = marker.get("output"), marker.get("output_dir"), marker.get("output_sha256")
    if (not isinstance(name, str) or safe_filename(name) != name or not name.lower().endswith(".prt")
            or not isinstance(folder, str) or not os.path.isabs(folder)
            or not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected)):
        return None
    folder = os.path.realpath(folder)
    stem, extension = os.path.splitext(name)
    candidates = []
    try:
        for entry in os.scandir(folder):
            if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                continue
            candidate_stem, candidate_ext = os.path.splitext(entry.name)
            if candidate_ext.lower() != extension.lower():
                continue
            if candidate_stem == stem:
                candidates.insert(0, entry.path)
            elif candidate_stem.startswith(stem + "_"):
                suffix = candidate_stem[len(stem) + 1:]
                if suffix and all(part.isdigit() for part in suffix.split("_")):
                    candidates.append(entry.path)
    except OSError:
        return None
    for path in candidates:
        try:
            if os.path.commonpath((folder, os.path.realpath(path))) != folder:
                continue
            if file_sha256(path) == expected:
                return path
        except (OSError, ValueError):
            continue
    return None


def next_available_path(folder, name):
    """Retorna o primeiro nome livre; a publicação final ainda deve ser no-clobber."""
    folder = _canonical_folder(folder)
    os.makedirs(folder, exist_ok=True)
    safe = safe_filename(name)
    index = 0
    while True:
        candidate_name = _suffixed_name(safe, index)
        candidate = os.path.join(folder, candidate_name)
        if not os.path.lexists(candidate):
            return candidate
        index += 1


def publish_unique_file(source, preferred_path):
    """Publica sem substituir: hard-link ou staging privado + rename atomico sem clobber."""
    folder = _canonical_folder(os.path.dirname(preferred_path))
    preferred_path = os.path.join(folder, os.path.basename(preferred_path))
    os.makedirs(folder, exist_ok=True)
    safe = safe_filename(os.path.basename(preferred_path))
    for index in range(1_000_000):
        name = _suffixed_name(safe, index)
        destination = os.path.join(folder, name)
        try:
            os.link(source, destination)
            return destination
        except FileExistsError:
            continue
        except OSError as link_error:
            if link_error.errno == errno.EXDEV:
                raise
            # Nunca copie diretamente para o nome final: o PrintExp pode observar
            # um PRT parcial. Primeiro grave um temporario oculto e sincronize.
            fd, temporary = tempfile.mkstemp(prefix=".publish.", suffix=".part", dir=folder)
            try:
                with os.fdopen(fd, "wb") as target, open(source, "rb") as origin:
                    shutil.copyfileobj(origin, target, 1024 * 1024)
                    target.flush()
                    os.fsync(target.fileno())
                for fallback_index in range(index, 1_000_000):
                    final = os.path.join(folder, _suffixed_name(safe, fallback_index))
                    try:
                        _rename_noreplace(temporary, final)
                        return final
                    except FileExistsError:
                        continue
                    except NotImplementedError as exc:
                        raise OSError(
                            errno.ENOTSUP,
                            "Publicacao atomica sem sobrescrita indisponivel neste filesystem.",
                            final,
                        ) from exc
                raise FileExistsError("Nao foi possivel encontrar nome livre para publicar.")
            finally:
                try:
                    os.remove(temporary)
                except OSError:
                    pass
    raise FileExistsError("Nao foi possivel reservar um nome unico depois de 1.000.000 tentativas.")


def _remove_if_identity(path, identity):
    try:
        current = os.lstat(path)
        if (current.st_dev, current.st_ino) == tuple(identity):
            os.remove(path)
            return True
    except OSError:
        pass
    return False


def _rename_noreplace(source, destination):
    if os.name == "nt":
        os.rename(source, destination)  # Windows falha se o destino já existe.
        return
    if sys.platform.startswith("linux"):
        try:
            renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
        except AttributeError:
            raise NotImplementedError
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        result = renameat2(-100, os.fsencode(source), -100, os.fsencode(destination), 1)  # RENAME_NOREPLACE
        if result == 0:
            return
        error = ctypes.get_errno()
        unsupported = {errno.ENOSYS, errno.EINVAL, getattr(errno, "EOPNOTSUPP", errno.EINVAL),
                       getattr(errno, "ENOTSUP", errno.EINVAL)}
        if error in unsupported:
            raise NotImplementedError
        raise OSError(error, os.strerror(error), destination)
    raise NotImplementedError


def _rename_unique(source, preferred):
    folder = _canonical_folder(os.path.dirname(preferred))
    safe = safe_filename(os.path.basename(preferred))
    for index in range(1_000_000):
        destination = os.path.join(folder, _suffixed_name(safe, index))
        try:
            _rename_noreplace(source, destination)
            return destination
        except FileExistsError:
            continue
        except NotImplementedError:
            destination = publish_unique_file(source, preferred)
            info = os.lstat(destination)
            try:
                os.remove(source)
            except OSError:
                _remove_if_identity(destination, (info.st_dev, info.st_ino))
                raise
            return destination
    raise FileExistsError("Nao foi possivel encontrar nome livre para mover o arquivo.")


def move_unique(source, folder, name=None):
    """Move sem sobrescrever; em volumes diferentes, copia para temporário e publica no-clobber."""
    folder = _canonical_folder(folder)
    os.makedirs(folder, exist_ok=True)
    if os.path.islink(source) or not os.path.isfile(source):
        raise ValueError("A origem do movimento precisa ser um arquivo regular, nao um symlink.")
    preferred = os.path.join(folder, safe_filename(name or os.path.basename(source)))
    try:
        return _rename_unique(source, preferred)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        before = os.stat(source, follow_symlinks=False)
        fd, temporary = tempfile.mkstemp(prefix=".move.", suffix=".part", dir=folder)
        try:
            with open(source, "rb") as origin, os.fdopen(fd, "wb") as target:
                shutil.copyfileobj(origin, target, 1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            after = os.stat(source, follow_symlinks=False)
            if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                    after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
                raise RuntimeError("A origem foi alterada durante o arquivamento.")
            shutil.copystat(source, temporary, follow_symlinks=False)
            destination = _rename_unique(temporary, preferred)
        finally:
            try: os.remove(temporary)
            except OSError: pass
    destination_stat = os.lstat(destination)
    try:
        os.remove(source)
    except OSError:
        _remove_if_identity(destination, (destination_stat.st_dev, destination_stat.st_ino))
        raise
    return destination


class ProcessLock:
    """Lock advisory não bloqueante entre processos, com um byte de estado no Windows."""

    def __init__(self, path):
        self.path = os.path.realpath(path)
        self._file = None

    def acquire(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        self._file = os.fdopen(fd, "r+b")
        try:
            if os.name == "nt":
                import msvcrt
                self._file.seek(0, os.SEEK_END)
                if self._file.tell() == 0:
                    self._file.write(b"\0")
                    self._file.flush()
                self._file.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            self._file.close()
            self._file = None
            raise RuntimeError(f"recurso ja esta sendo usado por outro processo: {self.path}") from exc
        return self

    def release(self):
        if self._file is None:
            return
        fd = self._file.fileno()
        try:
            if os.name == "nt":
                import msvcrt
                self._file.seek(0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, traceback):
        self.release()
