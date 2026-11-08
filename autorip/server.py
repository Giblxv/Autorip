"""Painel local do AutoRIP: servidor HTTP (127.0.0.1) + fila de jobs + modo automatico + senha."""
import os, sys, json, time, math, hashlib, secrets, tempfile, threading, queue, traceback, webbrowser, io, shutil, stat
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode
from dataclasses import asdict
from . import __version__
from .config import Settings
from .engine import Rip, MAX_INPUT_PIXELS
from .prt import read_header
from .watcher import EXTS, _signature, _stable
from .paths import (ProcessLock, safe_filename, move_unique, next_available_path,
                    read_archive_marker, remove_archive_marker, write_archive_marker,
                    file_sha256, find_marked_output, source_signature_matches)
from . import integrations, agent, updater
from PIL import Image, ImageDraw, ImageOps

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
MAX_MANUAL_PENDING_BYTES = 1024 * 1024 * 1024
MIN_FREE_DISK_BYTES = 128 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PENDING_JOBS = 100
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
SECRET_FIELDS = ("trello_key", "trello_token", "notion_token", "jira_token", "anthropic_key")


class InsufficientStorageError(Exception):
    pass


def res_path(*p):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "autorip", *p)


def home_dir():
    h = os.environ.get("AUTORIP_HOME")
    if not h:
        h = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AutoRIP")
    existed = os.path.isdir(h)
    os.makedirs(h, mode=0o700, exist_ok=True)
    if not existed and os.name != "nt":
        try: os.chmod(h, 0o700)
        except OSError: pass
    return h


class App:
    def __init__(self):
        self.home = home_dir()
        self.cfg_path = os.path.join(self.home, "autorip.json")
        self.auth_path = os.path.join(self.home, "auth.json")
        self.hot_history_path = os.path.join(self.home, "hot_folders.json")
        self.s = Settings.load(self.cfg_path, base=self.home)
        self.s.validate()
        self.rip = Rip(self.s)
        self.auto = self.s.auto_mode
        self.jobs, self.log_lines, self.tokens = [], [], set()
        self.q = queue.Queue()
        self.lock = threading.RLock()
        self.settings_lock = threading.RLock()
        self.print_lock = threading.Lock()
        self.upload_lock = threading.Lock()
        self.login_attempts = {}
        self.archive_pending = {}
        self.queued_sources = set()
        self.source_jobs = {}
        self._watch_locks = []
        self._output_locks = []
        self._active_output_key = None
        self._known_hot_folders = [os.path.normcase(os.path.realpath(self.s.hot_folder))]
        try:
            with open(self.hot_history_path, encoding="utf-8") as source:
                history = json.load(source)
            if isinstance(history, list):
                for folder in history[:100]:
                    if isinstance(folder, str) and folder and os.path.isabs(folder) and os.path.isdir(folder):
                        canonical = os.path.normcase(os.path.realpath(folder))
                        if canonical not in self._known_hot_folders:
                            self._known_hot_folders.append(canonical)
        except (OSError, ValueError):
            pass
        self.inbox = os.path.join(self.home, "manual"); os.makedirs(self.inbox, exist_ok=True)
        self.processing_folder = os.path.join(self.s.hot_folder, ".autorip_processing")
        for d in (self.s.hot_folder, self.s.output_folder, self.s.printed_folder, self.s.done_folder, self.s.error_folder):
            os.makedirs(d, exist_ok=True)
        os.makedirs(self.processing_folder, exist_ok=True)
        if self.rip.icc_error:
            self.log(self.rip.icc_error)
        elif not self.s.icc_path:
            self.log("AVISO: sem perfil ICC; a conversao CMYK generica do Pillow nao substitui o perfil da impressora.")
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._watch, daemon=True).start()
        if getattr(sys, "frozen", False) and self.s.auto_update and not self.s.offline_mode:
            threading.Thread(target=self._check_for_update, daemon=True).start()

    # ---- log / jobs ----
    def _check_for_update(self):
        state = updater.stage_latest(self.home, __version__, offline=self.s.offline_mode, log=self.log)
        if not state or not updater.install_staged(state, log=self.log):
            return
        self.log(f"Atualização {state.get('version', '')} iniciada; o AutoRIP será reiniciado.")
        threading.Timer(1.5, os._exit, args=(0,)).start()

    def log(self, msg):
        with self.lock:
            self.log_lines.append(time.strftime("%H:%M:%S ") + msg); self.log_lines[:] = self.log_lines[-200:]

    @staticmethod
    def _output_lock_key(folder):
        path = os.path.join(folder, ".autorip.output.lock")
        return os.path.normcase(os.path.realpath(path))

    def _prune_output_locks(self):
        current = self._output_lock_key(self.s.output_folder)
        keep = {current}
        if self._active_output_key:
            keep.add(self._active_output_key)
        retained = []
        for lock in self._output_locks:
            key = os.path.normcase(os.path.realpath(lock.path))
            if key in keep:
                retained.append(lock)
            else:
                lock.release()
        self._output_locks[:] = retained

    def _finish_output_use(self):
        with self.settings_lock:
            self._active_output_key = None
            self._prune_output_locks()

    def _archive_input(self, source, target_folder, job, label):
        try:
            archived = move_unique(source, target_folder)
            remove_archive_marker(source)
            self._cleanup_manual_folder(source)
            with self.lock:
                was_pending = self.archive_pending.pop(source, None) is not None
                if job is not None:
                    job["archive_pending"] = False
                    if was_pending:
                        job["error"] = (job.get("error", "") + " Arquivamento recuperado.").strip()[:500]
            return archived
        except Exception as primary_error:
            hot = os.path.normcase(os.path.realpath(self.s.hot_folder))
            recovery = None
            for suffix in ("archive_recovery", "archive_recovery_1", "archive_recovery_2"):
                candidate = os.path.join(self.home, suffix)
                if os.path.normcase(os.path.realpath(candidate)) != hot:
                    recovery = candidate
                    break
            fallback_error = None
            if recovery:
                try:
                    archived = move_unique(source, recovery)
                    remove_archive_marker(source)
                    self._cleanup_manual_folder(source)
                    warning = f"Falha ao arquivar em {label}; entrada preservada em {os.path.basename(recovery)}."
                    with self.lock:
                        was_pending = self.archive_pending.pop(source, None) is not None
                        if job is not None:
                            job["archive_pending"] = False
                            if not was_pending:
                                job["error"] = (job.get("error", "") + " " + warning).strip()[:500]
                    self.log(warning)
                    return archived
                except Exception as exc:
                    fallback_error = exc
            warning = (f"Entrada pendente em processamento: falha ao arquivar em {label} "
                       f"({type(primary_error).__name__}) e no fallback "
                       f"({type(fallback_error).__name__ if fallback_error else 'indisponivel'}).")
            with self.lock:
                pending = self.archive_pending.get(source)
                attempt = pending[4] + 1 if pending else 0
                delay = min(60, 2 ** attempt)
                self.archive_pending[source] = (target_folder, job, label,
                                                time.monotonic() + delay, attempt)
                if job is not None:
                    job["archive_pending"] = True
                    if not pending:
                        job["error"] = (job.get("error", "") + " " + warning).strip()[:500]
            self.log(warning)
            return None

    def _retry_archive_pending(self):
        now = time.monotonic()
        with self.lock:
            due = [(path, data) for path, data in self.archive_pending.items() if data[3] <= now]
        for path, (folder, job, label, _next_try, _attempt) in due:
            if not os.path.lexists(path):
                with self.lock:
                    self.archive_pending.pop(path, None)
                continue
            self._archive_input(path, folder, job, label)

    def _marker_output_path(self, marker):
        path = find_marked_output(marker)
        if path is None:
            return None
        try:
            read_header(path)
            return path
        except (OSError, ValueError, TypeError):
            return None

    def _recover_marked_source(self, source, settings):
        marker = read_archive_marker(source)
        if not marker:
            return False
        if not source_signature_matches(source, marker):
            self.log(f"Aviso: journal sem identidade correspondente; preservando {os.path.basename(source)} em erros.")
            self._archive_input(source, settings.error_folder, None, "pasta de erros")
            return True
        phase = marker["phase"]
        output = self._marker_output_path(marker)
        expected_hash = marker.get("output_sha256")
        if phase == "processing" and not expected_hash:
            # O callback grava o hash antes de publicar; sem hash, nenhuma saída deste job pode existir.
            remove_archive_marker(source)
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
            # Uma fase success sem o PRT do hash exato não é prova suficiente para concluir o job.
            self.log(f"Aviso: PRT do journal nao confere ou nao foi encontrado; entrada {os.path.basename(source)} vai para erros para revisao.")
            marker.update(phase="error", target="error",
                          error=("Marcador sem hash verificavel; PRT nao pode ser associado com seguranca."
                                 if not expected_hash else
                                 "PRT correspondente ao hash do journal nao foi encontrado; revisao manual necessaria."))
            try: write_archive_marker(source, marker)
            except OSError: pass
            phase = "error"
        if phase == "success":
            info = marker.get("info")
            if output and isinstance(info, dict) and not marker.get("metadata_written"):
                try:
                    self._write_output_metadata(output, info)
                    marker["metadata_written"] = True
                    write_archive_marker(source, marker)
                except Exception as metadata_error:
                    self.log(f"Recuperacao aguardando metadados auxiliares ({type(metadata_error).__name__}).")
                    return True
            services = integrations.enabled_services(settings)
            if not marker.get("outbox_handled"):
                if services and isinstance(info, dict) and marker.get("job_id"):
                    try:
                        job = {"id": marker["job_id"], "name": marker.get("name", os.path.basename(source)),
                               "out": output or os.path.join(marker.get("output_dir", ""), marker.get("output", ""))}
                        integrations.outbox_add(self.home, job, info)
                    except Exception as outbox_error:
                        self.log(f"Recuperacao aguardando registro na outbox ({type(outbox_error).__name__}).")
                        return True
                marker["outbox_handled"] = True
                try: write_archive_marker(source, marker)
                except OSError as marker_error:
                    self.log(f"Recuperacao aguardando gravacao do journal ({type(marker_error).__name__}).")
                    return True
                if services and not settings.offline_mode:
                    threading.Thread(target=integrations.outbox_flush,
                                     args=(settings, self.home, self.log), daemon=True).start()
            target, label = settings.done_folder, "pasta de concluidos"
        else:
            target, label = settings.error_folder, "pasta de erros"
        self.log(f"Recuperando entrada sem repetir o RIP: {os.path.basename(source)}")
        self._archive_input(source, target, None, label)
        return True

    def _cleanup_manual_folder(self, source):
        inbox = os.path.realpath(self.inbox)
        parent = os.path.realpath(os.path.dirname(source))
        try:
            inside = parent != inbox and os.path.commonpath((inbox, parent)) == inbox
        except ValueError:
            return
        if not inside:
            return
        # Windows pode manter o arquivo recém-movido aberto por alguns milissegundos
        # devido ao antivírus/indexador. Nunca removemos conteúdo: somente tentamos
        # rmdir em uma pasta que precisa estar vazia, com retry idempotente.
        for attempt in range(10):
            try:
                os.rmdir(parent)
                return
            except FileNotFoundError:
                return
            except OSError:
                if attempt < 9:
                    time.sleep(0.05)

    def _manual_pending_bytes(self):
        total = 0
        for root, directories, files in os.walk(self.inbox, topdown=True, followlinks=False):
            directories[:] = [name for name in directories if not os.path.islink(os.path.join(root, name))]
            for name in files:
                path = os.path.join(root, name)
                try:
                    info = os.lstat(path)
                    if stat.S_ISREG(info.st_mode):
                        total += info.st_size
                except OSError:
                    continue
        return total

    def receive_upload(self, handler, name, width_value):
        with self.upload_lock:
            raw_length = handler.headers.get("Content-Length", "0")
            if not raw_length.isdigit():
                raise ValueError("Content-Length invalido.")
            if len(raw_length) > 12:
                raise OverflowError("Upload excede o limite permitido.")
            length = int(raw_length)
            if length <= 0:
                raise ValueError("O arquivo enviado esta vazio.")
            if length > MAX_UPLOAD_BYTES:
                raise OverflowError("O arquivo excede o limite de 200 MiB.")
            if self._manual_pending_bytes() + length > MAX_MANUAL_PENDING_BYTES:
                raise OverflowError("A fila de uploads pendentes atingiu o limite agregado de 1 GiB.")
            if shutil.disk_usage(self.inbox).free < length + MIN_FREE_DISK_BYTES:
                raise InsufficientStorageError("Espaco livre insuficiente; mantenha ao menos 128 MiB de reserva para o RIP.")
            folder = os.path.join(self.inbox, secrets.token_hex(12))
            os.makedirs(folder, mode=0o700, exist_ok=False)
            path = os.path.join(folder, safe_filename(name))
            try:
                handler._save_request_body(path, MAX_UPLOAD_BYTES)
                with Image.open(path) as image:
                    if image.width * image.height > MAX_INPUT_PIXELS:
                        raise ValueError(f"Imagem acima do limite de {MAX_INPUT_PIXELS:,} pixels.")
                    image.verify()
                width = None
                if width_value:
                    width = float(width_value)
                    if not math.isfinite(width) or width <= 0 or width > 300:
                        raise ValueError("A largura precisa estar entre 0 e 300 cm.")
                return self.enqueue(path, width, move_to_done=True)
            except BaseException:
                try: os.remove(path)
                except OSError: pass
                try: os.rmdir(folder)
                except OSError: pass
                raise

    def enqueue(self, path, width_cm=None, move_to_done=True):
        if width_cm is not None and (isinstance(width_cm, bool) or not isinstance(width_cm, (int, float)) or not math.isfinite(width_cm) or width_cm <= 0 or width_cm > 300):
            raise ValueError("A largura precisa estar entre 0 e 300 cm.")
        job = dict(id=secrets.token_hex(8), name=safe_filename(os.path.basename(path)), status="fila", progress=0.0, out="", error="")
        with self.lock:
            if path in self.queued_sources:
                return self.source_jobs[path]
            if self.q.qsize() >= MAX_PENDING_JOBS:
                raise RuntimeError("Fila cheia: aguarde um trabalho terminar antes de enviar mais artes.")
            self.queued_sources.add(path)
            self.source_jobs[path] = job
            self.jobs.append(job); self.jobs[:] = self.jobs[-50:]
            self.q.put((job, path, width_cm, move_to_done))
        return job

    def _release_source(self, path):
        with self.lock:
            self.queued_sources.discard(path)
            self.source_jobs.pop(path, None)

    def _worker(self):
        while True:
            job, path, width_cm, move = self.q.get()
            with self.settings_lock:
                settings, rip = self.s, self.rip
                self._active_output_key = self._output_lock_key(settings.output_folder)
            with self.lock:
                job["status"] = "processando"
            self.log(f"RIP: {job['name']}")
            out = None
            marker = {"phase": "processing", "target": "done", "job_id": job["id"],
                      "name": job["name"], "output_dir": settings.output_folder,
                      "started_ns": time.time_ns(), "metadata_written": False,
                      "outbox_handled": False, "source_signature": list(_signature(path) or ())}
            try:
                out = next_available_path(settings.output_folder, os.path.splitext(job["name"])[0] + ".PRT")
                marker["output"] = os.path.basename(out)
                if move:
                    write_archive_marker(path, marker)
                def prog(p):
                    with self.lock:
                        job["progress"] = round(p, 3)
                def before_publish(temporary_path, preview):
                    if not move:
                        return
                    marker["output_sha256"] = file_sha256(temporary_path)
                    marker["info"] = {key: preview[key] for key in
                                       ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_rows", "n_dots", "has_alpha")}
                    write_archive_marker(path, marker)
                info = rip.process(path, out, width_cm, progress=prog, before_publish=before_publish)
                out = info.pop("output_path")
            except Exception as e:
                if move:
                    marker.update(phase="error", target="error", error=str(e)[:500])
                    try:
                        write_archive_marker(path, marker)
                    except OSError as marker_error:
                        self.log(f"Aviso: falha ao gravar marcador de recuperação ({type(marker_error).__name__}).")
                with self.lock:
                    job.update(status="erro", error=str(e)[:500])
                self.log(f"ERRO {job['name']}: {type(e).__name__}: {e}")
                traceback.print_exc()
                if move:
                    self._archive_input(path, settings.error_folder, job, "pasta de erros")
                self._release_source(path)
                self._finish_output_use()
                continue

            metadata_written = False
            try:
                self._write_output_metadata(out, info)
                metadata_written = True
            except Exception as metadata_error:
                self.log(f"Aviso: metadados auxiliares nao foram gravados ({type(metadata_error).__name__}).")
            thumb = self._thumb(job["id"], path, output_name=os.path.splitext(os.path.basename(out))[0], settings=settings)
            with self.lock:
                job["thumb"] = thumb
                job.update(status="pronto", progress=1.0, out=out)
            self.log(f"OK: {os.path.basename(out)}  {info['width_cm']:.2f} x {info['height_cm']:.2f} cm")
            services = integrations.enabled_services(settings)
            outbox_handled = not services
            try:
                if services:
                    integrations.outbox_add(self.home, job, info)
                outbox_handled = True
            except Exception as integration_error:
                self.log(f"Aviso: RIP pronto, mas nao foi possivel enfileirar notificacao: {integration_error}")
            journal_persisted = not move
            if move:
                marker.update(phase="success", target="done", output=os.path.basename(out),
                              metadata_written=metadata_written, outbox_handled=outbox_handled)
                try:
                    write_archive_marker(path, marker)
                    journal_persisted = True
                except OSError as marker_error:
                    self.log(f"Aviso: marcador de recuperação não atualizado ({type(marker_error).__name__}).")
            if services and not settings.offline_mode and (
                    not move or (metadata_written and outbox_handled and journal_persisted)):
                offline_check = lambda: self.s.offline_mode
                threading.Thread(target=integrations.outbox_flush,
                                 args=(settings, self.home, self.log),
                                 kwargs={"offline_check": offline_check}, daemon=True).start()
            if move:
                if metadata_written and outbox_handled and journal_persisted:
                    self._archive_input(path, settings.done_folder, job, "pasta de concluidos")
                else:
                    with self.lock:
                        job["archive_pending"] = True
                    self.log(f"Recuperacao pendente; entrada preservada em processamento: {job['name']}")
            self._release_source(path)
            self._finish_output_use()

    def _trello_loop(self):
        seen = set()
        while True:
            try:
                with self.settings_lock:
                    settings = self.s
                if not settings.offline_mode:
                    offline_check = lambda: self.s.offline_mode
                    integrations.outbox_flush(settings, self.home, self.log, offline_check=offline_check)
                    integrations.pull_trello(settings, seen, self.log, offline_check=offline_check)
            except Exception as e: self.log(f"Integracao/entrada: falhou ({type(e).__name__})")
            with self.settings_lock:
                poll_seconds = self.s.poll_seconds
            time.sleep(max(10, poll_seconds * 5))

    def _watch(self):
        threading.Thread(target=self._trello_loop, daemon=True).start()
        while True:
            try:
                self._retry_archive_pending()
                with self.settings_lock:
                    settings = self.s
                    auto = self.auto
                    hot_folders = list(self._known_hot_folders)
                current_hot = os.path.normcase(os.path.realpath(settings.hot_folder))
                if current_hot not in hot_folders:
                    hot_folders.append(current_hot)
                processing_folders = [(folder, os.path.join(folder, ".autorip_processing"))
                                      for folder in hot_folders if os.path.isdir(folder)]
                current_processing = os.path.join(settings.hot_folder, ".autorip_processing")
                os.makedirs(current_processing, exist_ok=True)
                with self.lock:
                    pending_archives = set(self.archive_pending)
                    queued_sources = set(self.queued_sources)
                for hot_folder, processing_folder in processing_folders:
                    if not os.path.isdir(processing_folder):
                        continue
                    for n in sorted(os.listdir(processing_folder)):
                        p = os.path.join(processing_folder, n)
                        if (not n.lower().endswith(EXTS) or os.path.islink(p) or not os.path.isfile(p)
                                or p in queued_sources or p in pending_archives or not _stable(p, wait=0.5)):
                            continue
                        has_marker = os.path.lexists(p + ".autorip.json")
                        if not auto and not has_marker:
                            continue
                        if self._recover_marked_source(p, settings):
                            continue
                        elif auto:
                            self.enqueue(p, move_to_done=True)
                if auto:
                    for n in sorted(os.listdir(settings.hot_folder)):
                        if not n.lower().endswith(EXTS):
                            continue
                        src = os.path.join(settings.hot_folder, n)
                        try:
                            signature = _signature(src)
                        except OSError:
                            continue
                        if signature is None or signature[2] <= 0 or not _stable(src, wait=0.5):
                            continue
                        try:
                            claimed = move_unique(src, current_processing, n)
                        except OSError:
                            continue
                        self.enqueue(claimed, move_to_done=True)
                # Uploads manuais ficam em subpastas privadas; retomá-los também após reinício.
                with self.upload_lock:
                    for root, directories, files in os.walk(self.inbox, topdown=True, followlinks=False):
                        directories[:] = [name for name in directories if not os.path.islink(os.path.join(root, name))]
                        for name in sorted(files):
                            if not name.lower().endswith(EXTS):
                                continue
                            path = os.path.join(root, name)
                            if os.path.islink(path) or not os.path.isfile(path) or not _stable(path, wait=0.5):
                                continue
                            with self.lock:
                                if path in self.queued_sources or path in self.archive_pending:
                                    continue
                            if not self._recover_marked_source(path, settings):
                                self.enqueue(path, move_to_done=True)
            except Exception as e:
                self.log(f"Falha ao observar hot-folder: {type(e).__name__}: {e}")
            with self.settings_lock:
                poll_seconds = self.s.poll_seconds
            time.sleep(max(0.5, poll_seconds))

    # ---- miniaturas ----
    def _thumb(self, jid, path, output_name=None, settings=None, size=220):
        try:
            settings = settings or self.s
            with Image.open(path) as source:
                if source.width * source.height > 80_000_000:
                    return ""
                im = ImageOps.exif_transpose(source).convert("RGBA")
            im.thumbnail((size, size))
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); d = ImageDraw.Draw(bg)
            for y in range(0, im.height, 10):                       # xadrez: mostra a transparencia (= area do branco)
                for x in range(0, im.width, 10):
                    if (x // 10 + y // 10) % 2: d.rectangle((x, y, x + 9, y + 9), fill=(225, 225, 225, 255))
            bg.alpha_composite(im)
            wm = settings.watermark_path
            if wm and os.path.exists(wm):                           # marca d'agua do cliente
                with Image.open(wm) as watermark:
                    w = watermark.convert("RGBA")
                w.thumbnail((im.width // 2, im.height // 2))
                a = w.getchannel("A").point(lambda v: int(v * settings.watermark_opacity)); w.putalpha(a)
                bg.alpha_composite(w, ((im.width - w.width) // 2, (im.height - w.height) // 2))
            d = os.path.join(self.home, "thumbs"); os.makedirs(d, exist_ok=True)
            rgb = bg.convert("RGB"); rgb.save(os.path.join(d, jid + ".jpg"), quality=82)
            nd = os.path.join(d, "by_name"); os.makedirs(nd, exist_ok=True)
            thumb_name = safe_filename(output_name or os.path.splitext(os.path.basename(path))[0])
            rgb.save(os.path.join(nd, thumb_name + ".jpg"), quality=82)
            return f"/api/thumb?id={jid}"
        except Exception:
            return ""

    def _write_output_metadata(self, prt_path, info):
        fields = ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_dots", "n_rows", "has_alpha")
        metadata = {key: info[key] for key in fields if key in info}
        destination = prt_path + ".meta.json"
        directory = os.path.dirname(prt_path)
        fd, temporary = tempfile.mkstemp(prefix=".meta.", suffix=".tmp", dir=directory)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(metadata, target, ensure_ascii=False)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, destination)
        except BaseException:
            try: os.close(fd)
            except OSError: pass
            try: os.remove(temporary)
            except OSError: pass
            raise

    def _read_output_metadata(self, prt_path):
        metadata_path = prt_path + ".meta.json"
        try:
            if os.path.islink(metadata_path) or os.path.getsize(metadata_path) > 4096:
                return None
            with open(metadata_path, encoding="utf-8") as source:
                metadata = json.load(source)
            width, height = metadata.get("width_cm"), metadata.get("height_cm")
            if (isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width)
                    or isinstance(height, bool) or not isinstance(height, (int, float)) or not math.isfinite(height)
                    or width <= 0 or height <= 0):
                return None
            return float(width), float(height)
        except (OSError, ValueError, TypeError, AttributeError, OverflowError):
            return None

    # ---- fila de impressao (arquivos .PRT prontos, aguardando o PrintExp) ----
    def list_prints(self):
        from .prt import read_header
        out = []
        with self.settings_lock:
            settings = self.s
        folder = settings.output_folder
        for n in os.listdir(folder) if os.path.isdir(folder) else []:
            if not n.lower().endswith(".prt"): continue
            f = os.path.join(folder, n)
            try:
                if os.path.islink(f): continue
                st = os.stat(f); h = read_header(f)
                w = h["n_dots"] / h["dpi_x"] * 2.54
                rows = h["n_rows"] - int((settings.margin_top_in + settings.margin_bottom_in) * h["dpi_y"])
                metadata = self._read_output_metadata(f)
                width_cm, height_cm = metadata if metadata else (w, max(rows, 0) / h["dpi_y"] * 2.54)
                out.append(dict(name=n, mb=round(st.st_size / 1048576, 1), mtime=int(st.st_mtime),
                                width_cm=round(width_cm, 2), height_cm=round(height_cm, 2),
                                thumb="/api/thumb?" + urlencode({"name": os.path.splitext(n)[0]})))
            except Exception:
                continue
        out.sort(key=lambda x: x["mtime"])                       # mais antigo primeiro (FIFO)
        return out

    def _print_file(self, name):
        name = safe_filename(name)
        with self.settings_lock:
            folder = self.s.output_folder
        f = os.path.join(folder, name)
        if not name.lower().endswith(".prt") or os.path.islink(f) or not os.path.isfile(f): raise FileNotFoundError(name)
        from .prt import read_header
        read_header(f)
        return f

    def mark_printed(self, name):
        with self.print_lock:
            with self.settings_lock:
                f = self._print_file(name)
                printed_folder = self.s.printed_folder
            moved = move_unique(f, printed_folder)
            metadata = f + ".meta.json"
            if os.path.isfile(metadata) and not os.path.islink(metadata):
                try:
                    move_unique(metadata, printed_folder, os.path.basename(moved) + ".meta.json")
                except Exception as exc:
                    self.log(f"Aviso: PRT movido, mas metadados auxiliares nao foram arquivados ({type(exc).__name__}).")
        self.log(f"Impresso: {os.path.basename(f)}")

    def delete_print(self, name):
        with self.print_lock:
            with self.settings_lock:
                f = self._print_file(name)
            os.remove(f)
            metadata = f + ".meta.json"
            try: os.remove(metadata)
            except OSError: pass
        self.log(f"Removido da fila: {os.path.basename(f)}")

    # ---- senha ----
    def has_pass(self): return os.path.exists(self.auth_path)

    def _hash(self, pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()

    def set_pass(self, pw):
        salt = secrets.token_hex(16)
        directory = os.path.dirname(self.auth_path)
        fd, temporary = tempfile.mkstemp(prefix=".auth.", suffix=".tmp", dir=directory)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(dict(salt=salt, hash=self._hash(pw, salt)), target)
                target.flush(); os.fsync(target.fileno())
            os.replace(temporary, self.auth_path)
        except BaseException:
            try: os.close(fd)
            except OSError: pass
            try: os.remove(temporary)
            except OSError: pass
            raise

    def check_pass(self, pw):
        if not self.has_pass(): return False
        try:
            with open(self.auth_path, encoding="utf-8") as source:
                a = json.load(source)
            return secrets.compare_digest(a["hash"], self._hash(pw, a["salt"]))
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def _save_hot_history(self, folders):
        fd, temporary = tempfile.mkstemp(prefix=".hot-folders.", suffix=".tmp", dir=self.home)
        try:
            if hasattr(os, "fchmod"):
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(list(dict.fromkeys(folders))[-100:], target, ensure_ascii=False)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.hot_history_path)
        except BaseException:
            try: os.close(fd)
            except OSError: pass
            try: os.remove(temporary)
            except OSError: pass
            raise

    def apply_settings(self, d):
        if not isinstance(d, dict):
            raise ValueError("As configuracoes precisam ser um objeto JSON.")
        with self.settings_lock:
            candidate = Settings(**asdict(self.s))
            current = asdict(candidate)
            for key, value in d.items():
                if key not in candidate.__dataclass_fields__:
                    continue
                if key in SECRET_FIELDS and value == "":
                    continue
                expected = type(current[key])
                if expected is float and type(value) is int:
                    value = float(value)
                elif type(value) is not expected:
                    raise ValueError(f"Tipo invalido para a configuracao {key}.")
                setattr(candidate, key, value)
            candidate.canonicalize_folders(self.home)
            candidate.validate()
            new_rip = Rip(candidate)
            if new_rip.icc_error:
                raise ValueError(new_rip.icc_error)
            new_watch_lock = None
            new_output_lock = None
            current_hot = os.path.normcase(self.s.hot_folder)
            candidate_hot = os.path.normcase(candidate.hot_folder)
            current_output = os.path.normcase(self.s.output_folder)
            candidate_output = os.path.normcase(candidate.output_folder)
            candidate_lock_path = os.path.join(candidate.hot_folder, ".autorip.watch.lock")
            candidate_lock_key = os.path.normcase(os.path.realpath(candidate_lock_path))
            held_lock_keys = {os.path.normcase(os.path.realpath(lock.path)) for lock in self._watch_locks}
            if self._watch_locks and candidate_hot != current_hot and candidate_lock_key not in held_lock_keys:
                try:
                    new_watch_lock = ProcessLock(candidate_lock_path).acquire()
                except RuntimeError as exc:
                    raise ValueError("A pasta de entrada ja esta sendo monitorada por outro processo.") from exc
            candidate_output_lock = os.path.join(candidate.output_folder, ".autorip.output.lock")
            output_lock_key = os.path.normcase(os.path.realpath(candidate_output_lock))
            held_output_keys = {os.path.normcase(os.path.realpath(lock.path)) for lock in self._output_locks}
            if self._output_locks and candidate_output != current_output and output_lock_key not in held_output_keys:
                try:
                    new_output_lock = ProcessLock(candidate_output_lock).acquire()
                except RuntimeError as exc:
                    if new_watch_lock:
                        new_watch_lock.release()
                    raise ValueError("A pasta de saida ja esta sendo usada por outro processo.") from exc
            try:
                for key in ("hot_folder", "output_folder", "printed_folder", "done_folder", "error_folder"):
                    os.makedirs(getattr(candidate, key), exist_ok=True)
                history = list(self._known_hot_folders)
                if candidate_hot not in history:
                    history.append(candidate_hot)
                if current_hot not in history:
                    history.append(current_hot)
                if candidate_hot != current_hot:
                    self._save_hot_history(history)
                candidate.save(self.cfg_path)
            except BaseException:
                if new_watch_lock:
                    new_watch_lock.release()
                if new_output_lock:
                    new_output_lock.release()
                raise
            self.s, self.rip = candidate, new_rip
            self.auto = candidate.auto_mode
            self._known_hot_folders = history
            if new_watch_lock:
                self._watch_locks.append(new_watch_lock)
            if new_output_lock:
                self._output_locks.append(new_output_lock)
            self._prune_output_locks()
        self.log("Configuracoes salvas")


APP = None
HTTP_SERVER = None
LAST_CLIENT_SEEN = 0.0
DIRECT_CLOSING = False


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def setup(self):
        super().setup()
        self.connection.settimeout(180)

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, (bytes, bytearray)): body = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(body)

    def _auth(self):
        incoming = self.headers.get("X-Token", "")
        with APP.lock:
            tokens = tuple(APP.tokens)
        return bool(incoming) and any(secrets.compare_digest(incoming, token) for token in tokens)

    def _origin_allowed(self):
        origin = self.headers.get("Origin")
        fetch_site = self.headers.get("Sec-Fetch-Site")
        if fetch_site and fetch_site not in ("same-origin", "none"):
            return False
        if not origin:
            return True  # clientes locais fora do navegador nao enviam Origin
        parsed = urlparse(origin)
        host = self.headers.get("Host", "")
        return parsed.scheme == "http" and parsed.netloc == host and not parsed.username and not parsed.password

    def _json(self, max_bytes=MAX_JSON_BYTES):
        raw_length = self.headers.get("Content-Length", "0")
        if not raw_length.isdigit():
            raise ValueError("Content-Length invalido.")
        length = int(raw_length)
        if length > max_bytes:
            raise OverflowError(f"Corpo JSON acima do limite de {max_bytes} bytes.")
        data = self.rfile.read(length)
        if len(data) != length:
            raise ValueError("Corpo da requisicao incompleto.")
        result = json.loads(data or b"{}")
        if not isinstance(result, dict):
            raise ValueError("O corpo JSON precisa ser um objeto.")
        return result

    def _settings_public(self):
        with APP.settings_lock:
            result = asdict(APP.s)
        result["_secret_configured"] = {key: bool(result.get(key)) for key in SECRET_FIELDS}
        for key in SECRET_FIELDS:
            result[key] = ""
        return result

    def _login_limited(self):
        now = time.monotonic()
        ip = self.client_address[0]
        with APP.lock:
            attempts, blocked_until = APP.login_attempts.get(ip, ([], 0.0))
            attempts = [timestamp for timestamp in attempts if now - timestamp < 60]
            if blocked_until > now:
                APP.login_attempts[ip] = (attempts, blocked_until)
                return True
            APP.login_attempts[ip] = (attempts, 0.0)
            return len(attempts) >= 5

    def _record_login(self, success):
        ip = self.client_address[0]
        now = time.monotonic()
        with APP.lock:
            attempts, _ = APP.login_attempts.get(ip, ([], 0.0))
            attempts = [timestamp for timestamp in attempts if now - timestamp < 60]
            if success:
                APP.login_attempts.pop(ip, None)
            else:
                attempts.append(now)
                APP.login_attempts[ip] = (attempts, now + 60 if len(attempts) >= 5 else 0.0)

    def _issue_token(self):
        token = secrets.token_hex(32)
        with APP.lock:
            if len(APP.tokens) >= 16:
                APP.tokens.clear()
            APP.tokens.add(token)
        return token

    def _save_request_body(self, path, maximum):
        raw_length = self.headers.get("Content-Length", "0")
        if not raw_length.isdigit():
            raise ValueError("Content-Length invalido.")
        length = int(raw_length)
        if length <= 0:
            raise ValueError("O arquivo enviado esta vazio.")
        if length > maximum:
            raise OverflowError(f"O arquivo excede o limite de {maximum // (1024 * 1024)} MiB.")
        remaining = length
        with open(path, "xb") as target:
            while remaining:
                chunk = self.rfile.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Upload incompleto.")
                target.write(chunk)
                remaining -= len(chunk)
            target.flush()
            os.fsync(target.fileno())
        return length

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(res_path("ui", "index.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/state":
            global LAST_CLIENT_SEEN
            LAST_CLIENT_SEEN = time.monotonic()
            with APP.lock:
                jobs = [dict(job) for job in APP.jobs[-12:]]
                logs = list(APP.log_lines[-60:])
            with APP.settings_lock:
                auto = APP.auto
                settings = APP.s
                icc = os.path.basename(settings.icc_path) if settings.icc_path else "(sem perfil ICC — conversao generica)"
                if APP.rip.icc_error:
                    icc += " — erro ao carregar"
                brand = settings.brand_name
                offline = settings.offline_mode
                hot_folder = settings.hot_folder
                output_folder = settings.output_folder
                brand_path = os.path.join(APP.home, "brand")
                brand_dir = os.path.realpath(brand_path)
                logo_path = os.path.join(brand_dir, "logo.png")
                has_logo = (not os.path.islink(brand_path) and not os.path.islink(logo_path)
                            and os.path.isfile(logo_path)
                            and os.path.commonpath((os.path.realpath(APP.home), brand_dir)) == os.path.realpath(APP.home))
            try:
                pending = len(integrations.outbox_load(APP.home))
            except Exception:
                pending = -1
            return self._send(200, dict(version=__version__, auto=auto, has_pass=APP.has_pass(),
                                        jobs=jobs, log=logs, hot_folder=hot_folder, output_folder=output_folder,
                                        icc=icc, brand=brand, offline=offline, pending=pending, has_logo=has_logo))
        if u.path == "/api/prints":
            return self._send(200, APP.list_prints())
        if u.path == "/api/thumb":
            q = parse_qs(u.query); jid = os.path.basename(q.get("id", [""])[0]); nm = os.path.basename(q.get("name", [""])[0])
            thumbs_root = os.path.realpath(os.path.join(APP.home, "thumbs"))
            f = os.path.join(thumbs_root, "by_name", nm + ".jpg") if nm else os.path.join(thumbs_root, jid + ".jpg")
            try:
                inside = os.path.commonpath((thumbs_root, os.path.realpath(f))) == thumbs_root
                valid = inside and not os.path.islink(f) and os.path.isfile(f) and os.path.getsize(f) <= 10 * 1024 * 1024
                return self._send(200, open(f, "rb").read(), "image/jpeg") if valid else self._send(404, {})
            except (OSError, ValueError):
                return self._send(404, {})
        if u.path == "/api/brand-logo":
            brand_path = os.path.join(APP.home, "brand")
            brand_dir = os.path.realpath(brand_path)
            home_real = os.path.realpath(APP.home)
            if os.path.islink(brand_path) or os.path.commonpath((home_real, brand_dir)) != home_real:
                return self._send(404, {})
            f = os.path.join(brand_dir, "logo.png")
            if not os.path.islink(f) and os.path.isfile(f) and os.path.realpath(f) == os.path.join(brand_dir, "logo.png"):
                return self._send(200, open(f, "rb").read(), "image/png")
            return self._send(404, {})
        if u.path == "/api/settings":
            return self._send(200, self._settings_public()) if self._auth() else self._send(401, {"error": "login"})
        self._send(404, {"error": "nao encontrado"})

    def do_POST(self):
        u = urlparse(self.path)
        if not self._origin_allowed():
            return self._send(403, {"error": "origem da requisicao nao autorizada"})
        try:
            if u.path == "/api/auto":
                if not self._auth(): return self._send(401, {"error": "login"})
                on = self._json().get("on")
                if type(on) is not bool: raise ValueError("O estado automatico precisa ser booleano.")
                # Persistir antes de aplicar em memoria: o ultimo estado escolhido
                # pelo operador deve sobreviver a reinicios do aplicativo.
                APP.apply_settings({"auto_mode": on})
                APP.log("Modo automatico " + ("LIGADO" if on else "desligado"))
                return self._send(200, {"auto": on})
            if u.path == "/api/shutdown":
                if not self._auth(): return self._send(401, {"error": "login"})
                self._send(202, {"ok": True, "message": "AutoRIP sera encerrado."})
                threading.Thread(target=shutdown_server, daemon=True).start()
                return
            if u.path == "/api/upload":
                q = parse_qs(u.query)
                name = safe_filename(q.get("name", ["arte.png"])[0])
                if not name.lower().endswith(EXTS):
                    return self._send(400, {"error": "formato nao suportado"})
                job = APP.receive_upload(self, name, q.get("width", [""])[0])
                return self._send(202, job)
            if u.path == "/api/login":
                if self._login_limited(): return self._send(429, {"error": "muitas tentativas; aguarde um minuto"})
                password = self._json(max_bytes=8192).get("password", "")
                if not isinstance(password, str) or len(password) > MAX_PASSWORD_LENGTH:
                    return self._send(400, {"error": f"a senha pode ter no maximo {MAX_PASSWORD_LENGTH} caracteres"})
                success = APP.check_pass(password)
                self._record_login(success)
                if success:
                    return self._send(200, {"token": self._issue_token()})
                return self._send(401, {"error": "senha incorreta"})
            if u.path == "/api/setpass":
                d = self._json(max_bytes=8192); new = d.get("new", "")
                if not isinstance(new, str) or len(new) < MIN_PASSWORD_LENGTH or len(new) > MAX_PASSWORD_LENGTH:
                    return self._send(400, {"error": f"a senha precisa ter entre {MIN_PASSWORD_LENGTH} e {MAX_PASSWORD_LENGTH} caracteres"})
                with APP.lock:
                    if APP.has_pass():
                        if self._login_limited(): return self._send(429, {"error": "muitas tentativas; aguarde um minuto"})
                        current = d.get("password", "")
                        success = isinstance(current, str) and len(current) <= MAX_PASSWORD_LENGTH and APP.check_pass(current)
                        self._record_login(success)
                        if not success: return self._send(401, {"error": "senha atual incorreta"})
                    APP.set_pass(new)
                return self._send(200, {"token": self._issue_token()})
            if u.path == "/api/prints/printed":
                if not self._auth(): return self._send(401, {"error": "login"})
                APP.mark_printed(self._json().get("name", "")); return self._send(200, {"ok": True})
            if u.path == "/api/prints/delete":
                if not self._auth(): return self._send(401, {"error": "login"})
                APP.delete_print(self._json().get("name", "")); return self._send(200, {"ok": True})
            if u.path == "/api/agent":
                if not self._auth(): return self._send(401, {"error": "login"})
                with APP.settings_lock: settings = APP.s
                if settings.offline_mode: return self._send(400, {"error": "Modo offline ligado. Desligue em Configuracoes para usar o agente."})
                try:
                    d = self._json()
                    with APP.lock:
                        jobs, logs = [dict(job) for job in APP.jobs], list(APP.log_lines)
                    question = d.get("question")
                    if question is not None and not isinstance(question, str):
                        raise ValueError("A pergunta precisa ser texto.")
                    offline_check = lambda: APP.s.offline_mode
                    txt = agent.ask(settings, jobs, logs, question or None, offline_check=offline_check)
                    APP.log("Agente de IA: sugestoes geradas"); return self._send(200, {"text": txt})
                except Exception as e:
                    return self._send(502, {"error": str(e)})
            if u.path in ("/api/logo", "/api/watermark"):
                if not self._auth(): return self._send(401, {"error": "login"})
                length = self.headers.get("Content-Length", "0")
                if not length.isdigit() or int(length) <= 0: raise ValueError("arquivo de imagem vazio ou invalido")
                if int(length) > MAX_IMAGE_UPLOAD_BYTES: raise OverflowError("imagem de marca excede 10 MiB")
                data = self.rfile.read(int(length))
                if len(data) != int(length): raise ValueError("upload da imagem incompleto")
                with Image.open(io.BytesIO(data)) as source:
                    if source.width * source.height > 16_000_000: raise ValueError("imagem de marca acima de 16 megapixels")
                    source.load(); image = source.convert("RGBA")
                bd = os.path.join(APP.home, "brand"); os.makedirs(bd, exist_ok=True)
                filename = "logo.png" if u.path == "/api/logo" else "watermark.png"
                f = os.path.join(bd, filename)
                fd, temporary = tempfile.mkstemp(prefix=".brand.", suffix=".tmp", dir=bd); os.close(fd)
                try:
                    image.save(temporary, format="PNG")
                    os.replace(temporary, f)
                finally:
                    try: os.remove(temporary)
                    except OSError: pass
                APP.apply_settings({"brand_logo" if u.path == "/api/logo" else "watermark_path": f})
                return self._send(200, {"ok": True})
            if u.path == "/api/settings":
                if not self._auth(): return self._send(401, {"error": "login"})
                APP.apply_settings(self._json()); return self._send(200, self._settings_public())
        except InsufficientStorageError as e:
            return self._send(507, {"error": str(e)})
        except OverflowError as e:
            return self._send(413, {"error": str(e)})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc(); return self._send(500, {"error": str(e)})
        self._send(404, {"error": "nao encontrado"})


def serve(port=8765, open_browser=True, status_callback=None):
    global APP, HTTP_SERVER, LAST_CLIENT_SEEN
    def report(message):
        if status_callback:
            try:
                status_callback(message)
            except Exception:
                pass

    home_lock = ProcessLock(os.path.join(home_dir(), ".autorip.instance.lock"))
    watch_locks = []
    output_locks = []
    try:
        report("Carregando configuração local…")
        home_lock.acquire()
        home = home_dir()
        initial = Settings.load(os.path.join(home, "autorip.json"), base=home)
        hot_folders = [os.path.normcase(os.path.realpath(initial.hot_folder))]
        try:
            with open(os.path.join(home, "hot_folders.json"), encoding="utf-8") as source:
                history = json.load(source)
            if isinstance(history, list):
                hot_folders.extend(os.path.normcase(os.path.realpath(path)) for path in history
                                   if isinstance(path, str) and os.path.isabs(path) and os.path.isdir(path))
        except (OSError, ValueError):
            pass
        for folder in dict.fromkeys(hot_folders):
            watch_locks.append(ProcessLock(os.path.join(folder, ".autorip.watch.lock")).acquire())
        output_locks.append(ProcessLock(os.path.join(initial.output_folder, ".autorip.output.lock")).acquire())
        APP = App()
        APP._instance_lock = home_lock
        APP._watch_locks.extend(watch_locks)
        APP._output_locks.extend(output_locks)
        report("Worker local iniciado; preparando monitoramento…")
    except RuntimeError as exc:
        for lock in watch_locks:
            lock.release()
        for lock in output_locks:
            lock.release()
        home_lock.release()
        print(f"AutoRIP nao iniciado: {exc}", flush=True)
        report(f"Não foi possível iniciar: {exc}")
        return False
    except BaseException:
        for lock in watch_locks:
            lock.release()
        for lock in output_locks:
            lock.release()
        home_lock.release()
        raise
    srv = None
    for p in range(port, port + 20):
        try: srv = ThreadingHTTPServer(("127.0.0.1", p), H); break
        except OSError: continue
    if srv is None:
        for lock in APP._watch_locks: lock.release()
        for lock in APP._output_locks: lock.release()
        APP._instance_lock.release()
        raise OSError("nenhuma porta local disponivel para o painel AutoRIP")
    HTTP_SERVER = srv
    LAST_CLIENT_SEEN = time.monotonic()
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print("AutoRIP em", url, flush=True)
    report("AutoRIP ativo — monitorando a pasta de entrada")
    if open_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    if open_browser:
        def browser_monitor():
            while HTTP_SERVER is srv:
                if time.monotonic() - LAST_CLIENT_SEEN > 15:
                    srv.shutdown()
                    return
                time.sleep(2)
        threading.Thread(target=browser_monitor, daemon=True).start()
    try:
        if not DIRECT_CLOSING:
            srv.serve_forever()
    finally:
        HTTP_SERVER = None
        srv.server_close()
        for lock in APP._watch_locks: lock.release()
        for lock in APP._output_locks: lock.release()
        APP._instance_lock.release()
        report("AutoRIP encerrado")


def shutdown_server():
    """Solicita o encerramento fora da thread HTTP, como exige BaseServer.shutdown."""
    srv = HTTP_SERVER
    if srv is not None:
        srv.shutdown()


def run_direct():
    """Executa o AutoRIP em janela nativa, sem abrir navegador.

    O servidor HTTP continua sendo apenas um componente local interno para
    reaproveitar worker, integrações e recuperação; ele escuta exclusivamente
    em 127.0.0.1 e não é aberto ao usuário.
    """
    global DIRECT_CLOSING
    DIRECT_CLOSING = False
    stop_event = threading.Event()
    try:
        import tkinter as tk
    except Exception:
        serve(open_browser=False)
        return

    root = tk.Tk()
    root.title("AutoRIP — modo direto")
    root.geometry("560x190")
    root.minsize(460, 150)
    root.configure(bg="#1a1a1a")
    status = tk.StringVar(value="Iniciando AutoRIP local…")
    tk.Label(root, text="AutoRIP", fg="#00aeef", bg="#1a1a1a",
             font=("Segoe UI", 24, "bold")).pack(pady=(18, 4))
    tk.Label(root, textvariable=status, fg="white", bg="#1a1a1a",
             font=("Segoe UI", 10), wraplength=520).pack(pady=4)
    def close_direct():
        global DIRECT_CLOSING
        DIRECT_CLOSING = True
        stop_event.set()
        shutdown_server()
        root.destroy()
    tk.Button(root, text="Encerrar", command=close_direct,
              bg="#ec008c", fg="white", relief="flat", padx=18, pady=7).pack(pady=12)

    def start_local():
        try:
            started = serve(open_browser=False, status_callback=lambda message: root.after(0, status.set, message))
            if started is False and not DIRECT_CLOSING:
                root.after(0, status.set, "Não iniciado. Verifique se já existe outra instância aberta.")
        except Exception as exc:
            try: root.after(0, status.set, f"Falha ao iniciar: {exc}")
            except tk.TclError: pass

    threading.Thread(target=start_local, daemon=True).start()
    root.protocol("WM_DELETE_WINDOW", close_direct)
    root.mainloop()


def main():
    if sys.stdout is None:                                    # .exe sem console
        lf = open(os.path.join(home_dir(), "autorip.log"), "a", buffering=1)
        sys.stdout = sys.stderr = lf
    headless = "--headless" in sys.argv or "--no-browser" in sys.argv
    if headless or "--direct" in sys.argv or (getattr(sys, "frozen", False) and "--web" not in sys.argv):
        run_direct()
    else:
        serve(open_browser=os.environ.get("AUTORIP_NOBROWSER") != "1")
