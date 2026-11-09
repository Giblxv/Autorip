"""Observacao de hot-folder com journal duravel, locks e recuperacao de arquivamento."""
import os
import time
import traceback
from .config import Settings
from .engine import Rip
from .paths import (ProcessLock, archive_marker_path, move_unique, next_available_path,
                    read_archive_marker, remove_archive_marker, write_archive_marker,
                    file_sha256, find_marked_output, write_json_atomic,
                    source_signature_matches, rip_output_name)
from .prt import read_header

EXTS = (".png", ".tif", ".tiff", ".jpg", ".jpeg")


def _signature(path):
    stat = os.stat(path, follow_symlinks=False)
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


def _stable(path, wait=1.0):
    try:
        first = _signature(path)
        if first is None or first[2] <= 0:
            return False
        time.sleep(max(0, wait))
        return first == _signature(path)
    except OSError:
        return False


def _claim(src, processing_folder):
    return move_unique(src, processing_folder, os.path.basename(src))


def _archive_input(source, target, recovery, label, log):
    try:
        move_unique(source, target)
        remove_archive_marker(source)
        return True, ""
    except Exception as primary:
        try:
            move_unique(source, recovery)
            remove_archive_marker(source)
            warning = f"[AVISO] Falha ao arquivar em {label}; entrada preservada em {os.path.basename(recovery)}."
            log(warning)
            return True, warning
        except Exception as fallback:
            return False, f"falha no destino ({type(primary).__name__}) e no fallback ({type(fallback).__name__})"


def _marker_output_path(marker):
    path = find_marked_output(marker)
    if path is None:
        return None
    try:
        read_header(path)
        return path
    except (OSError, ValueError, TypeError):
        return None


def _write_metadata(output, info):
    fields = ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_dots", "n_rows", "has_alpha")
    write_json_atomic(output + ".meta.json", {key: info[key] for key in fields if key in info}, prefix=".meta.")


def _recover_marked(source, s, log, archive_pending, seen, invalid_journal_alerts=None):
    marker = read_archive_marker(source)
    if marker is None:
        if os.path.lexists(archive_marker_path(source)):
            key = os.path.normcase(os.path.abspath(source))
            first_warning = True
            if invalid_journal_alerts is not None:
                if len(invalid_journal_alerts) >= 256:
                    invalid_journal_alerts.clear()
                first_warning = key not in invalid_journal_alerts
                invalid_journal_alerts.add(key)
            if first_warning:
                log("[AVISO] Journal invalido em " + os.path.basename(source)
                    + "; arte preservada para revisao manual, sem repetir RIP.")
            return True
        if invalid_journal_alerts is not None:
            invalid_journal_alerts.discard(os.path.normcase(os.path.abspath(source)))
        return False
    if invalid_journal_alerts is not None:
        invalid_journal_alerts.discard(os.path.normcase(os.path.abspath(source)))
    if not source_signature_matches(source, marker):
        log(f"[AVISO] Journal sem identidade correspondente; preservando {os.path.basename(source)} em erros.")
        recovery = os.path.join(s.hot_folder, ".autorip_archive_recovery")
        ok, message = _archive_input(source, s.error_folder, recovery, "pasta de erros", log)
        if not ok:
            archive_pending[source] = (s.error_folder, "pasta de erros", 0, time.monotonic() + 1)
            log(f"[AVISO] Entrada pendente de arquivamento: {message}")
        return True
    phase = marker["phase"]
    output = _marker_output_path(marker)
    expected_hash = marker.get("output_sha256")
    if phase == "processing" and not expected_hash:
        remove_archive_marker(source)
        if seen is not None:
            seen.pop(source, None)
        return False
    if phase == "processing" and expected_hash and not output:
        marker.update(phase="error", target="error",
                      error="Publicacao ambigua: hash preparado, mas a saida correspondente nao foi encontrada.")
        try: write_archive_marker(source, marker)
        except OSError: pass
        phase = "error"
    elif phase == "processing" and output:
        marker.update(phase="success", target="done")
        try: write_archive_marker(source, marker)
        except OSError: pass
        phase = "success"
    elif phase == "error" and output:
        marker.update(phase="success", target="done")
        try: write_archive_marker(source, marker)
        except OSError: pass
        phase = "success"
    if phase == "success" and not output:
        log(f"[AVISO] PRT do journal nao confere ou nao foi encontrado; {os.path.basename(source)} vai para erros para revisao.")
        marker.update(phase="error", target="error",
                      error=("Marcador sem hash verificavel; PRT nao pode ser associado com seguranca."
                             if not expected_hash else
                             "PRT correspondente ao hash do journal nao foi encontrado; revisao manual necessaria."))
        try: write_archive_marker(source, marker)
        except OSError: pass
        phase = "error"
    if phase == "success" and output and isinstance(marker.get("info"), dict) and not marker.get("metadata_written"):
        try:
            _write_metadata(output, marker["info"])
            marker["metadata_written"] = True
            write_archive_marker(source, marker)
        except Exception as error:
            log(f"[AVISO] Recuperacao aguardando sidecar ({type(error).__name__}).")
            return True
    target, label = ((s.done_folder, "pasta de concluidos") if phase == "success"
                     else (s.error_folder, "pasta de erros"))
    log(f"[RECUPERACAO] Arquivando sem repetir o RIP: {os.path.basename(source)}")
    ok, message = _archive_input(source, target, os.path.join(s.hot_folder, ".autorip_archive_recovery"), label, log)
    if not ok:
        archive_pending[source] = (target, label, 0, time.monotonic() + 1)
        log(f"[AVISO] Entrada pendente de arquivamento: {message}")
    return True


def run_once(s: Settings, rip: Rip, log=print, seen=None, archive_pending=None,
             invalid_journal_alerts=None):
    """Processa arquivos estaveis e retoma journals sem repetir um RIP ja publicado."""
    s.canonicalize_folders()
    s.validate()
    for directory in (s.hot_folder, s.output_folder, s.printed_folder, s.done_folder, s.error_folder):
        os.makedirs(directory, exist_ok=True)
    processing_folder = os.path.join(s.hot_folder, ".autorip_processing")
    recovery_folder = os.path.join(s.hot_folder, ".autorip_archive_recovery")
    os.makedirs(processing_folder, exist_ok=True)
    if archive_pending is None:
        archive_pending = {}
    if invalid_journal_alerts is None:
        invalid_journal_alerts = set()

    now = time.monotonic()
    for path, data in list(archive_pending.items()):
        if not os.path.lexists(path):
            archive_pending.pop(path, None)
            continue
        target, label, attempt, next_try = data
        if next_try > now:
            continue
        ok, message = _archive_input(path, target, recovery_folder, label, log)
        if ok:
            archive_pending.pop(path, None)
        else:
            attempt += 1
            archive_pending[path] = (target, label, attempt, time.monotonic() + min(60, 2 ** attempt))
            log(f"[AVISO] Entrada pendente de arquivamento: {message}")

    pending = []
    # Recupera trabalhos deixados na pasta de processamento por uma interrupcao.
    for name in sorted(os.listdir(processing_folder)):
        path = os.path.join(processing_folder, name)
        if not name.lower().endswith(EXTS) or path in archive_pending:
            continue
        try:
            signature = _signature(path)
        except OSError:
            # O arquivo pode ter sido movido/apagado apos os.listdir(); outros jobs continuam.
            continue
        if signature is None:
            continue
        if _recover_marked(path, s, log, archive_pending, seen, invalid_journal_alerts):
            continue
        if os.path.lexists(archive_marker_path(path)):
            remove_archive_marker(path)
            if seen is not None:
                seen.pop(path, None)
        pending.append(path)

    # Espera a origem estabilizar e a move sem substituir destinos concorrentes.
    for name in sorted(os.listdir(s.hot_folder)):
        if not name.lower().endswith(EXTS):
            continue
        src = os.path.join(s.hot_folder, name)
        try:
            signature = _signature(src)
        except OSError:
            continue
        if signature is None or signature[2] <= 0 or not _stable(src):
            continue
        try:
            pending.append(_claim(src, processing_folder))
        except OSError:
            continue

    n = 0
    def priority(item):
        try:
            signature = _signature(item)
            size = signature[2] if signature else 2**63 - 1
        except OSError:
            size = 2**63 - 1
        return size, os.path.basename(item).casefold()
    pending.sort(key=priority)
    for src in pending:
        try:
            signature = _signature(src)
        except OSError:
            continue
        if signature is None or signature[2] <= 0 or src in archive_pending:
            continue
        if seen is not None and seen.get(src) == signature:
            continue
        if not _stable(src, wait=0.25):
            continue
        if seen is not None:
            seen[src] = signature

        preferred = None
        marker = {"phase": "processing", "target": "done", "output_dir": s.output_folder,
                  "started_ns": time.time_ns(), "source_signature": list(signature),
                  "metadata_written": False}
        try:
            preferred = next_available_path(s.output_folder, os.path.splitext(os.path.basename(src))[0] + ".PRT")
            marker["output"] = os.path.basename(preferred)
            write_archive_marker(src, marker)
            log(f"[RIP] {os.path.basename(src)} ...")
            def before_publish(temporary_path, preview):
                marker["output_sha256"] = file_sha256(temporary_path)
                marker["info"] = {key: preview[key] for key in
                                   ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_rows", "n_dots", "has_alpha")}
                named = rip_output_name(os.path.basename(src), preview["width_cm"], preview["height_cm"])
                preferred = next_available_path(s.output_folder, named)
                marker["output"] = os.path.basename(preferred)
                write_archive_marker(src, marker)
                return preferred
            info = rip.process(src, preferred, before_publish=before_publish)
            out = info.pop("output_path")
            metadata_written = False
            try:
                _write_metadata(out, info)
                metadata_written = True
            except Exception as metadata_error:
                log(f"[AVISO] Metadados auxiliares nao gravados ({type(metadata_error).__name__}).")
            marker.update(phase="success", target="done", output=os.path.basename(out),
                          info={key: info[key] for key in
                                ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_rows", "n_dots", "has_alpha")},
                          metadata_written=metadata_written)
            journal_persisted = False
            try:
                write_archive_marker(src, marker)
                journal_persisted = True
            except OSError as marker_error:
                log(f"[AVISO] Marcador de sucesso não atualizado ({type(marker_error).__name__}); será validado pelo PRT.")
        except Exception:
            marker.update(phase="error", target="error", error=traceback.format_exc()[-1000:])
            try: write_archive_marker(src, marker)
            except OSError: pass
            log(f"[ERRO] {os.path.basename(src)}\n{traceback.format_exc()}")
            ok, message = _archive_input(src, s.error_folder, recovery_folder, "pasta de erros", log)
            if not ok:
                archive_pending[src] = (s.error_folder, "pasta de erros", 0, time.monotonic() + 1)
                log(f"[ERRO] Entrada pendente de arquivamento: {message}")
            continue

        log(f"[OK ] {out}  {info['width_cm']:.2f}x{info['height_cm']:.2f} cm")
        n += 1
        if metadata_written and journal_persisted:
            ok, message = _archive_input(src, s.done_folder, recovery_folder, "pasta de concluidos", log)
            if not ok:
                archive_pending[src] = (s.done_folder, "pasta de concluidos", 0, time.monotonic() + 1)
                log(f"[AVISO] Entrada pendente de arquivamento: {message}")
        else:
            log(f"[AVISO] Entrada mantida em processamento para recovery: {os.path.basename(src)}")

    if seen is not None:
        for path in list(seen):
            if not os.path.lexists(path):
                seen.pop(path, None)
    return n


def watch(s: Settings, log=print, stop=lambda: False):
    s.validate()
    s.canonicalize_folders()
    s.validate()
    locks = []
    try:
        locks.append(ProcessLock(os.path.join(s.hot_folder, ".autorip.watch.lock")).acquire())
        locks.append(ProcessLock(os.path.join(s.output_folder, ".autorip.output.lock")).acquire())
        rip = Rip(s)
        seen = {}
        archive_pending = {}
        invalid_journal_alerts = set()
        log(f"Observando: {s.hot_folder}")
        while not stop():
            try:
                run_once(s, rip, log, seen, archive_pending, invalid_journal_alerts)
            except Exception:
                log(f"[ERRO] Falha ao varrer a hot-folder\n{traceback.format_exc()}")
            time.sleep(max(0.5, s.poll_seconds))
    finally:
        for lock in reversed(locks):
            lock.release()
