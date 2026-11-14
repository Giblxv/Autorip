"""Painel local do AutoRIP: servidor HTTP (127.0.0.1) + fila de jobs + modo automatico + senha."""
import ipaddress
import os, sys, json, time, math, hashlib, secrets, tempfile, threading, queue, traceback, webbrowser, io, shutil, stat
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dataclasses import asdict
from contextlib import contextmanager
from . import __version__
from .watermarks import WatermarkCache
from .layout import LayoutItem, inspect_image, layout_to_svg, sheet_height
from .nesting import nest_layout, utilization
from .config import Settings
from .engine import Rip
from .prt import read_header
from .prints import PrintCatalog
from .watcher import EXTS, _signature, _stable_files
from .paths import (ProcessLock, safe_filename, move_unique, next_available_path,
                    read_archive_marker, remove_archive_marker, write_archive_marker,
                    file_sha256, find_marked_output, source_signature_matches, write_json_atomic)
from . import integrations, agent, updater, printexp_network
from PIL import ImageDraw, ImageOps
from .imaging import Image
import segno

# Uploads de arte nao possuem teto artificial; permanecem protegidos por
# Content-Length valido, espaco livre em disco e validacao do formato pelo Pillow.
MAX_UPLOAD_BYTES = None
MAX_MANUAL_PENDING_BYTES = None
MIN_FREE_DISK_BYTES = 128 * 1024 * 1024
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_PENDING_JOBS = 100
MAX_JOB_HISTORY = 50
MAX_STATE_HISTORY = 12
# Até o Pillow 12, resize(RGBA) descartava reducing_gap ao converter para RGBa.
# Preserve os mesmos pixels ao reduzir diretamente uma origem opaca.
OPAQUE_THUMBNAIL_REDUCING_GAP = 2.0 if int(Image.__version__.split('.', 1)[0]) >= 13 else None
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
SECRET_FIELDS = ("trello_key", "trello_token", "notion_token", "jira_token", "anthropic_key")


class InsufficientStorageError(Exception):
    pass


class QueueFullError(RuntimeError):
    """Capacidade temporariamente ocupada por trabalhos ou entradas em preparação."""


class JobPaused(Exception):
    """Interrupcao cooperativa segura no limite de uma tira de RIP."""


class JobCancelled(Exception):
    """Cancelamento cooperativo sem publicar um PRT parcial."""


def _source_key(path):
    """Identidade de fila comum ao caminho original, aliases e casing Windows."""
    return os.path.normcase(os.path.realpath(path))


def _parse_width_cm(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, bool):
            raise ValueError()
        width = float(value)
        if not math.isfinite(width) or not 0 < width <= 300:
            raise ValueError()
    except (ValueError, TypeError, OverflowError):
        raise ValueError("A largura precisa estar entre 0 e 300 cm.") from None
    return width


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


def _encode_thumbnail(image):
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=82)
    return buffer.getvalue()


def _write_thumbnail_atomic(encoded, destination):
    """Publica os mesmos bytes completos sem repetir a codificação JPEG."""
    directory = os.path.dirname(destination)
    fd, temporary = tempfile.mkstemp(prefix=".thumb.", suffix=".part", dir=directory)
    try:
        with os.fdopen(fd, "wb") as target:
            target.write(encoded)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, destination)
    finally:
        try:
            os.remove(temporary)
        except OSError:
            pass


def _save_thumbnail_atomic(image, destination):
    """Escreve JPEG completo antes de substituir uma miniatura visivel no painel."""
    _write_thumbnail_atomic(_encode_thumbnail(image), destination)


def _thumbnail_owned(image, bounds):
    """Consome um wrapper próprio e entrega somente o raster da miniatura."""
    result = None
    try:
        if image.mode in ("RGB", "L") and "transparency" not in image.info:
            image.thumbnail(bounds, reducing_gap=OPAQUE_THUMBNAIL_REDUCING_GAP)
            converted = image.convert("RGBA")
            image.close()
            image = converted
        else:
            if image.mode != "RGBA":
                converted = image.convert("RGBA")
                image.close()
                image = converted
            image.thumbnail(bounds)
        result = image
        return result
    finally:
        if image is not result:
            image.close()


class _SourcePreview:
    """Miniatura privada por job, capturada antes do ICC e publicada só após o RIP."""
    def __init__(self, bounds=(220, 220)):
        self.bounds = bounds
        self.image = None

    def capture(self, source):
        self.close()
        # Outros modos precisam de uma expansão RGBA completa antes do resize.
        # Retê-los junto à origem aumentaria o pico de RAM; preserve o fallback.
        if (source.readonly or source.mode not in ("RGB", "RGBA", "L")
                or "transparency" in source.info):
            return
        image = None
        try:
            # _new cria apenas um wrapper sobre o core carregado. thumbnail e
            # convert alocam a saída; nenhuma operação escreve nos pixels da origem.
            image = _thumbnail_owned(source._new(source.im), self.bounds)
            if image.im is source.im:
                # Uma RGBA já pequena não foi reduzida: solte a referência ao
                # core que o carregador poderá transformar no próprio buffer.
                independent = image.copy()
                image.close()
                image = independent
            self.image = image
        except Exception:
            if image is not None:
                image.close()
            # A prévia é opcional. O caminho habitual poderá tentar novamente
            # pelo arquivo depois do RIP, sem impedir a impressão.

    def take(self):
        image, self.image = self.image, None
        return image

    def close(self):
        image = self.take()
        if image is not None:
            image.close()


def _load_thumbnail(path, bounds, *, orient=True):
    image = result = None
    with Image.open(path) as source:
        try:
            # A orientação PNG/TIFF pode estar disponível somente após o load.
            source.load()
            orientation = source.getexif().get(274, 1) if orient else 1
            image = ImageOps.exif_transpose(source) if orientation in (2, 3, 4, 5, 6, 7, 8) else source
            if image is not source:
                source.close()
            image = _thumbnail_owned(image, bounds)
            result = image.copy() if image is source else image
            return result
        finally:
            if image is not None and image is not source and image is not result:
                image.close()
            source.close()


class App:
    def __init__(self):
        self.home = home_dir()
        self.cfg_path = os.path.join(self.home, "autorip.json")
        self.auth_path = os.path.join(self.home, "auth.json")
        self.hot_history_path = os.path.join(self.home, "hot_folders.json")
        self.s = Settings.load(self.cfg_path, base=self.home)
        self.s.validate()
        self.rip = Rip(self.s)
        self._watermark_cache = WatermarkCache()
        self._layout_lock = threading.Lock()
        self.auto = self.s.auto_mode
        self.jobs, self.log_lines, self.tokens = [], [], set()
        self.q = queue.Queue()
        self.lock = threading.RLock()
        self.settings_lock = threading.RLock()
        self.print_lock = threading.Lock()
        self.printexp_network_lock = threading.Lock()
        self.print_catalog = PrintCatalog()
        self._outbox_counter = integrations.OutboxCounter()
        self.upload_lock = threading.Lock()
        self.upload_receive_lock = threading.Lock()
        self.login_attempts = {}
        self.archive_pending = {}
        self.invalid_journal_alerts = set()
        self.queued_sources = set()
        self._admission_reservations = set()
        self.source_jobs = {}
        self.job_controls = {}
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
        # A estabilidade e o snapshot do watcher podem anteceder um enqueue.
        # Reconsulte a fila viva antes de tocar no journal de um job ativo/pausado.
        with self.lock:
            if _source_key(source) in self.queued_sources:
                return True
        marker = read_archive_marker(source)
        if marker is None:
            if os.path.lexists(source + ".autorip.json"):
                with self.lock:
                    first_warning = source not in self.invalid_journal_alerts
                    if first_warning:
                        if len(self.invalid_journal_alerts) >= 256:
                            self.invalid_journal_alerts.clear()
                        self.invalid_journal_alerts.add(source)
                if first_warning:
                    self.log("ATENCAO: journal invalido em " + os.path.basename(source)
                             + "; arte preservada para revisao manual, sem repetir RIP.")
                return True
            with self.lock:
                self.invalid_journal_alerts.discard(source)
            return False
        with self.lock:
            self.invalid_journal_alerts.discard(source)
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
                        integrations.outbox_add(self.home, job, info, services=services)
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
        # rmdir em uma pasta vazia e limpeza do sidecar conhecido, com retry.
        for attempt in range(10):
            try:
                if not os.path.lexists(source):
                    try: os.remove(source + ".request.json")
                    except FileNotFoundError: pass
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
        width = _parse_width_cm(width_value)
        raw_length = handler.headers.get("Content-Length", "0")
        if not raw_length.isdigit():
            raise ValueError("Content-Length invalido.")
        length = int(raw_length)
        if length <= 0:
            raise ValueError("O arquivo enviado esta vazio.")
        # Recepção continua serializada para verificar disco entre envios; o
        # observador só compartilha o lock curto de publicação, não o de rede.
        with self._reserve_admission() as reservation, self.upload_receive_lock:
            if shutil.disk_usage(self.inbox).free < length + MIN_FREE_DISK_BYTES:
                raise InsufficientStorageError("Espaco livre insuficiente; mantenha ao menos 128 MiB de reserva para o RIP.")
            folder = os.path.join(self.inbox, secrets.token_hex(12))
            os.makedirs(folder, mode=0o700, exist_ok=False)
            path = os.path.join(folder, safe_filename(name))
            temporary = os.path.join(folder, ".upload.part")
            request_path = path + ".request.json"
            try:
                handler._save_request_body(temporary, MAX_UPLOAD_BYTES)
                with Image.open(temporary) as image:
                    image.verify()
                # Persista a medida ANTES de tornar a imagem visível à recuperação.
                write_json_atomic(request_path, {"version": 1, "width_cm": width,
                                                "sha256": file_sha256(temporary)})
                with self.upload_lock:
                    try:
                        os.replace(temporary, path)
                        return self.enqueue(path, width, move_to_done=True, _reservation=reservation)
                    except BaseException:
                        # Não libere para recuperação uma imagem cujo pedido
                        # falhou; o sidecar e o restante são limpos abaixo.
                        try: os.remove(path)
                        except OSError: pass
                        raise
            except BaseException:
                for candidate in (temporary, path, request_path):
                    try: os.remove(candidate)
                    except OSError: pass
                try: os.rmdir(folder)
                except OSError: pass
                raise

    def _enqueue_manual_recovery(self, path):
        request_path = path + ".request.json"
        width = None  # Compatibilidade com uploads anteriores sem sidecar.
        if os.path.lexists(request_path):
            try:
                if os.path.islink(request_path) or os.path.getsize(request_path) > 8192:
                    raise ValueError("sidecar invalido")
                with open(request_path, encoding="utf-8") as source:
                    request = json.load(source)
                if not isinstance(request, dict) or request.get("version") != 1:
                    raise ValueError("versao invalida")
                width = request["width_cm"]
                if width is not None and (isinstance(width, bool) or not isinstance(width, (int, float))
                                          or not math.isfinite(width) or not 0 < width <= 300):
                    raise ValueError("largura invalida")
                if request.get("sha256") != file_sha256(path):
                    raise ValueError("identidade da imagem nao confere")
            except (OSError, ValueError, KeyError, TypeError):
                with self.lock:
                    first_warning = request_path not in self.invalid_journal_alerts
                    if len(self.invalid_journal_alerts) >= 256:
                        self.invalid_journal_alerts.clear()
                    self.invalid_journal_alerts.add(request_path)
                if first_warning:
                    self.log("ATENCAO: parametros de upload invalidos; arte preservada para revisao: "
                             + os.path.basename(path))
                return None
        return self.enqueue(path, width, move_to_done=True)

    def list_hot_files(self):
        with self.settings_lock:
            folder = os.path.realpath(self.s.hot_folder)
        result = []
        try:
            names = sorted(os.listdir(folder), key=str.casefold)
        except OSError:
            return result
        for name in names:
            if name.startswith(".") or not name.lower().endswith(EXTS):
                continue
            path = os.path.join(folder, name)
            try:
                info = os.lstat(path)
                if not stat.S_ISREG(info.st_mode) or os.path.islink(path):
                    continue
                result.append({"name": safe_filename(name), "size": info.st_size,
                               "mtime": info.st_mtime})
            except OSError:
                continue
        return result

    def plan_layout(self, data):
        """Planeja uma fotografia da hot folder sem mover ou enfileirar as artes."""
        if not isinstance(data, dict):
            raise ValueError("Informe as opções e as artes da folha.")
        width = data.get("sheet_width_cm", 58)
        margin = data.get("margin_cm", .2)
        gap = data.get("gap_cm", .2)
        rotate = data.get("allow_rotation", False)
        # Valide a geometria antes de consultar arquivos.
        nest_layout([], width, margin, gap, rotate)
        width, margin, gap = map(float, (width, margin, gap))
        requested = data.get("items")
        if not isinstance(requested, list) or not 1 <= len(requested) <= 100:
            raise ValueError("Selecione de 1 a 100 peças por planejamento.")
        checked, total = [], 0
        for item in requested:
            if not isinstance(item, dict):
                raise ValueError("Cada arte precisa informar nome, largura e quantidade.")
            name, quantity = item.get("name"), item.get("quantity", 1)
            if (not isinstance(name, str) or not name or len(name) > 255
                    or safe_filename(name) != name or name.startswith(".")
                    or not name.lower().endswith(EXTS)):
                raise ValueError("Selecione um arquivo de imagem da hot folder.")
            if type(quantity) is not int or quantity < 1 or total + quantity > 100:
                raise ValueError("O planejamento permite até 100 peças, contando as cópias.")
            total += quantity
            checked.append((name, _parse_width_cm(item.get("width_cm")), quantity))
        with self.settings_lock:
            folder = os.path.realpath(self.s.hot_folder)
        items = []
        for index, (name, requested_width, quantity) in enumerate(checked):
            source = os.path.join(folder, name)
            if (os.path.commonpath((folder, os.path.realpath(source))) != folder
                    or os.path.islink(source) or _signature(source) is None):
                raise FileNotFoundError("Uma arte não está mais na hot folder; atualize a lista.")
            before = _signature(source)
            try:
                info = inspect_image(source)
            except FileNotFoundError:
                raise FileNotFoundError("Uma arte saiu da hot folder; atualize a lista.") from None
            except (OSError, ValueError) as exc:
                raise ValueError(f"Não foi possível ler as dimensões de {name}.") from exc
            if before != _signature(source):
                raise ValueError("Uma arte mudou durante a leitura; tente novamente.")
            w = requested_width if requested_width is not None else min(info.width_cm, width - 2 * margin)
            h = w * info.height_cm / info.width_cm
            for copy in range(quantity):
                items.append(LayoutItem(f"{index}:{copy}", name, "", info.width_px,
                                        info.height_px, w, h))
        packed = nest_layout(items, width, margin, gap, rotate)
        return {"items": [item.as_dict() for item in packed], "sheet_width_cm": width,
                "sheet_height_cm": sheet_height(packed, margin, gap),
                "margin_cm": margin, "gap_cm": gap,
                "utilization": utilization(packed, width, margin, gap),
                "svg": layout_to_svg(packed, width, margin, gap)}

    def enqueue_hot_file(self, name, width_value=""):
        width = _parse_width_cm(width_value)
        safe_name = safe_filename(name)
        with self.settings_lock:
            folder = os.path.realpath(self.s.hot_folder)
            processing = os.path.join(folder, ".autorip_processing")
        source = os.path.join(folder, safe_name)
        return self._enqueue_hot_source(source, processing, width)

    def _enqueue_hot_source(self, source, processing, width=None):
        if not os.path.isfile(source) or os.path.islink(source):
            raise FileNotFoundError("Arquivo nao encontrado na hot folder.")
        with self._reserve_admission() as reservation:
            claimed = move_unique(source, processing, os.path.basename(source))
            return self.enqueue(claimed, width, move_to_done=True, _reservation=reservation)

    def _queue_used(self):
        """Com self.lock adquirido: inclui entradas ainda não publicadas na fila."""
        return len(self.queued_sources) + len(self._admission_reservations)

    def _has_capacity(self):
        with self.lock:
            return self._queue_used() < MAX_PENDING_JOBS

    @contextmanager
    def _reserve_admission(self):
        reservation = object()
        with self.lock:
            if self._queue_used() >= MAX_PENDING_JOBS:
                raise QueueFullError("Fila cheia: aguarde um trabalho terminar antes de enviar mais artes.")
            self._admission_reservations.add(reservation)
        try:
            yield reservation
        finally:
            with self.lock:
                self._admission_reservations.discard(reservation)

    def _retained_jobs(self, history_limit):
        """Com self.lock adquirido: mantém ativos e os últimos N finalizados."""
        kept = []
        finished = 0
        for job in reversed(self.jobs):
            if job.get("id") not in self.job_controls:
                if finished >= history_limit:
                    continue
                finished += 1
            kept.append(job)
        return kept[::-1]

    def _schedule_job(self, control):
        """Com self.lock adquirido: no máximo uma referência pendente por job."""
        if not control["queued"]:
            control["queued"] = True
            self.q.put(control["item"])

    def enqueue(self, path, width_cm=None, move_to_done=True, *, _reservation=None):
        if width_cm is not None and (isinstance(width_cm, bool) or not isinstance(width_cm, (int, float)) or not math.isfinite(width_cm) or width_cm <= 0 or width_cm > 300):
            raise ValueError("A largura precisa estar entre 0 e 300 cm.")
        job = dict(id=secrets.token_hex(8), name=safe_filename(os.path.basename(path)), status="fila", progress=0.0, out="", error="")
        control = {"pause": threading.Event(), "cancel": threading.Event(), "queued": False,
                   "item": (job, path, width_cm, move_to_done)}
        source_key = _source_key(path)
        with self.lock:
            if source_key in self.queued_sources:
                return self.source_jobs[source_key]
            if _reservation is not None:
                if _reservation not in self._admission_reservations:
                    raise RuntimeError("Reserva de admissao indisponivel.")
                self._admission_reservations.remove(_reservation)
            elif self._queue_used() >= MAX_PENDING_JOBS:
                raise QueueFullError("Fila cheia: aguarde um trabalho terminar antes de enviar mais artes.")
            self.queued_sources.add(source_key)
            self.source_jobs[source_key] = job
            self.job_controls[job["id"]] = control
            self.jobs.append(job)
            self.jobs[:] = self._retained_jobs(MAX_JOB_HISTORY)
            self._schedule_job(control)
        return job

    def _release_source(self, path):
        source_key = _source_key(path)
        with self.lock:
            self.queued_sources.discard(source_key)
            job = self.source_jobs.pop(source_key, None)
            if job:
                self.job_controls.pop(job.get("id"), None)
                # Uma arte pausada antiga pode terminar depois das mais novas.
                # O histórico deve refletir a conclusão, não apenas o enqueue.
                if job in self.jobs:
                    self.jobs.remove(job)
                    self.jobs.append(job)
            self.jobs[:] = self._retained_jobs(MAX_JOB_HISTORY)

    def control_job(self, job_id, action):
        if action not in ("pause", "resume", "cancel"):
            raise ValueError("Acao de fila invalida.")
        with self.lock:
            job = next((item for item in self.jobs if item.get("id") == job_id), None)
            control = self.job_controls.get(job_id)
            if job is None or control is None:
                raise ValueError("Trabalho nao encontrado ou ja finalizado.")
            if control["cancel"].is_set():
                if action == "cancel":
                    return dict(job)
                raise ValueError("O cancelamento deste trabalho ja foi solicitado.")
            status = job.get("status")
            if action == "pause":
                if status not in ("fila", "processando"):
                    raise ValueError("Somente trabalhos na fila ou em processamento podem ser pausados.")
                control["pause"].set()
                job["status"] = "pausando" if status == "processando" else "pausado"
                self.log(f"Fila: pausa solicitada para {job['name']}")
                return dict(job)
            if action == "resume":
                if status != "pausado":
                    raise ValueError("Somente trabalhos pausados podem ser retomados.")
                control["pause"].clear()
                job["status"] = "fila"
                self._schedule_job(control)
                self.log(f"Fila: retomando {job['name']} desde o inicio seguro")
                return dict(job)
            if status in ("pronto", "erro", "cancelado"):
                raise ValueError("O trabalho ja terminou.")
            control["cancel"].set()
            job["status"] = "cancelando"
            # Pausados podem já ter saído de q. Acorde o worker para arquivar
            # a entrada e liberar a capacidade, sem I/O no handler HTTP.
            self._schedule_job(control)
            self.log(f"Fila: cancelamento solicitado para {job['name']}")
            return dict(job)

    def _cancel_job(self, job, path, move, settings, message):
        remove_archive_marker(path)
        if move and os.path.isfile(path) and not os.path.islink(path):
            self._archive_input(path, settings.error_folder, job, "pasta de erros")
        with self.lock:
            job.update(status="cancelado", error=message, progress=job.get("progress", 0.0))
        self.log(f"CANCELADO {job['name']}: {message}")
        self._release_source(path)
        self._finish_output_use()

    def _worker(self):
        while True:
            job, path, width_cm, move = self.q.get()
            with self.lock:
                control = self.job_controls.get(job["id"])
                if control is None or not control["queued"]:
                    continue
                control["queued"] = False
                if control["cancel"].is_set():
                    action = "cancel"
                elif control["pause"].is_set():
                    action = "pause"
                    job["status"] = "pausado"
                else:
                    action = "run"
                    job["status"] = "processando"
            with self.settings_lock:
                settings, rip = self.s, self.rip
                self._active_output_key = self._output_lock_key(settings.output_folder)
            if action == "cancel":
                self._cancel_job(job, path, move, settings, "Cancelado antes do processamento.")
                continue
            if action == "pause":
                self.log(f"PAUSADO {job['name']}")
                self._finish_output_use()
                continue
            self.log(f"RIP: {job['name']}")
            out = None
            # A entrada pode desaparecer depois de entrar na fila; essa falha nao
            # pode encerrar o unico worker e bloquear os pedidos seguintes.
            try:
                source_signature = _signature(path)
            except OSError:
                source_signature = None
            marker = {"phase": "processing", "target": "done", "job_id": job["id"],
                      "name": job["name"], "output_dir": settings.output_folder,
                      "started_ns": time.time_ns(), "metadata_written": False,
                      "outbox_handled": False, "source_signature": list(source_signature or ())}
            source_preview = _SourcePreview()
            try:
                if source_signature is None:
                    raise FileNotFoundError("Arte da fila ausente ou insegura para processamento.")
                out = next_available_path(settings.output_folder, os.path.splitext(job["name"])[0] + ".PRT")
                marker["output"] = os.path.basename(out)
                if move:
                    write_archive_marker(path, marker)
                def prog(p, job=job):
                    with self.lock:
                        job["progress"] = round(p, 3)
                def before_publish(temporary_path, preview, move=move, marker=marker, path=path):
                    if not move:
                        return
                    marker["output_sha256"] = file_sha256(temporary_path)
                    marker["info"] = {key: preview[key] for key in
                                       ("width_cm", "height_cm", "dpi_x", "dpi_y", "n_rows", "n_dots", "has_alpha")}
                    write_archive_marker(path, marker)
                def control_check(control=control):
                    if control and control["cancel"].is_set():
                        raise JobCancelled()
                    if control and control["pause"].is_set():
                        raise JobPaused()
                info = rip.process(path, out, width_cm, progress=prog,
                                   before_publish=before_publish, control=control_check,
                                   source_ready=source_preview.capture)
                out = info.pop("output_path")
            except JobPaused:
                source_preview.close()
                remove_archive_marker(path)
                with self.lock:
                    cancelling = control["cancel"].is_set()
                    if cancelling:
                        job["status"] = "cancelando"
                    else:
                        job["status"] = "pausado"
                        job["error"] = "Pausado com segurança; retoma desde o início do RIP."
                if not cancelling:
                    self.log(f"PAUSADO {job['name']}")
                self._finish_output_use()
                continue
            except JobCancelled:
                source_preview.close()
                self._cancel_job(job, path, move, settings, "Cancelado pelo operador.")
                continue
            except Exception as e:
                source_preview.close()
                # Nao cria journal fantasma nem arquivamento pendente para uma
                # entrada removida enquanto aguardava o worker.
                archive_source = move and os.path.isfile(path) and not os.path.islink(path)
                if archive_source:
                    marker.update(phase="error", target="error", error=str(e)[:500])
                    try:
                        write_archive_marker(path, marker)
                    except OSError as marker_error:
                        self.log(f"Aviso: falha ao gravar marcador de recuperação ({type(marker_error).__name__}).")
                with self.lock:
                    job.update(status="erro", error=str(e)[:500])
                self.log(f"ERRO {job['name']}: {type(e).__name__}: {e}")
                traceback.print_exc()
                if archive_source:
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
            thumb = self._thumb(job["id"], path, output_name=os.path.splitext(os.path.basename(out))[0], settings=settings,
                                prepared=source_preview.take())
            with self.lock:
                job["thumb"] = thumb
                job.update(status="pronto", progress=1.0, out=out)
            self.log(f"OK: {os.path.basename(out)}  {info['width_cm']:.2f} x {info['height_cm']:.2f} cm")
            services = integrations.enabled_services(settings)
            outbox_handled = not services
            try:
                if services:
                    integrations.outbox_add(self.home, job, info, services=services)
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
                    integrations.pull_trello(settings, seen, self.log,
                                            offline_check=offline_check, seen_home=self.home)
            except Exception as e: self.log(f"Integracao/entrada: falhou ({type(e).__name__})")
            with self.settings_lock:
                poll_seconds = self.s.poll_seconds
            time.sleep(max(10, poll_seconds * 5))

    def _watch(self):
        threading.Thread(target=self._trello_loop, daemon=True).start()
        while True:
            try:
                self._scan_inputs()
            except Exception as e:
                self.log(f"Falha ao observar hot-folder: {type(e).__name__}: {e}")
            with self.settings_lock:
                poll_seconds = self.s.poll_seconds
            time.sleep(max(0.5, poll_seconds))

    def _scan_inputs(self):
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
            pending_archives = {_source_key(path) for path in self.archive_pending}
            queued_sources = set(self.queued_sources)
            accepting = self._queue_used() < MAX_PENDING_JOBS
        recovery_candidates = []
        for hot_folder, processing_folder in processing_folders:
            if not os.path.isdir(processing_folder):
                continue
            for n in sorted(os.listdir(processing_folder)):
                p = os.path.join(processing_folder, n)
                if (not n.lower().endswith(EXTS) or os.path.islink(p) or not os.path.isfile(p)
                        or _source_key(p) in queued_sources or _source_key(p) in pending_archives):
                    continue
                has_marker = os.path.lexists(p + ".autorip.json")
                if not has_marker and (not auto or not accepting):
                    continue
                recovery_candidates.append(p)
        for p, _ in _stable_files(recovery_candidates, wait=0.5):
            if not self._recover_marked_source(p, settings) and auto:
                try:
                    self.enqueue(p, move_to_done=True)
                except QueueFullError:
                    continue
        if auto and self._has_capacity():
            candidates = (os.path.join(settings.hot_folder, n)
                          for n in sorted(os.listdir(settings.hot_folder))
                          if n.lower().endswith(EXTS))
            for src, _ in _stable_files(candidates, wait=0.5):
                try:
                    self._enqueue_hot_source(src, current_processing)
                except QueueFullError:
                    break
                except OSError:
                    continue
        # Uploads manuais ficam em subpastas privadas; retomá-los também após reinício.
        manual_candidates = []
        for root, directories, files in os.walk(self.inbox, topdown=True, followlinks=False):
            directories[:] = [name for name in directories if not os.path.islink(os.path.join(root, name))]
            for name in sorted(files):
                if not name.lower().endswith(EXTS):
                    continue
                path = os.path.join(root, name)
                with self.lock:
                    if (_source_key(path) in self.queued_sources
                            or _source_key(path) in {_source_key(p) for p in self.archive_pending}):
                        continue
                if not self._has_capacity() and not os.path.lexists(path + ".autorip.json"):
                    continue
                manual_candidates.append(path)
        for path, _ in _stable_files(manual_candidates, wait=0.5):
            with self.upload_lock:
                if not self._recover_marked_source(path, settings) and self._has_capacity():
                    try:
                        self._enqueue_manual_recovery(path)
                    except QueueFullError:
                        continue

    # ---- miniaturas ----
    def _thumb(self, jid, path, output_name=None, settings=None, size=220, prepared=None):
        im = prepared
        try:
            settings = settings or self.s
            thumbs = os.path.join(self.home, "thumbs"); os.makedirs(thumbs, exist_ok=True)
            if os.path.islink(thumbs):
                return ""
            by_name = os.path.join(thumbs, "by_name"); os.makedirs(by_name, exist_ok=True)
            if os.path.islink(by_name):
                return ""
            if im is None:
                im = _load_thumbnail(path, (size, size))
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); d = ImageDraw.Draw(bg)
            for y in range(0, im.height, 10):                       # xadrez: mostra a transparencia (= area do branco)
                for x in range(0, im.width, 10):
                    if (x // 10 + y // 10) % 2: d.rectangle((x, y, x + 9, y + 9), fill=(225, 225, 225, 255))
            bg.alpha_composite(im)
            wm = settings.watermark_path
            if wm and os.path.exists(wm):                           # marca d'agua do cliente
                # A orientação da marca não era aplicada; preserve essa regra.
                bounds = (im.width // 2, im.height // 2)
                cache = getattr(self, "_watermark_cache", None)
                w = (cache.get(wm, bounds, _load_thumbnail) if cache is not None
                     else _load_thumbnail(wm, bounds, orient=False))
                a = w.getchannel("A").point(lambda v: int(v * settings.watermark_opacity)); w.putalpha(a)
                bg.alpha_composite(w, ((im.width - w.width) // 2, (im.height - w.height) // 2))
            rgb = bg.convert("RGB")
            thumb_name = safe_filename(output_name or os.path.splitext(os.path.basename(path))[0])
            encoded = _encode_thumbnail(rgb)
            _write_thumbnail_atomic(encoded, os.path.join(thumbs, jid + ".jpg"))
            _write_thumbnail_atomic(encoded, os.path.join(by_name, thumb_name + ".jpg"))
            return f"/api/thumb?id={jid}"
        except Exception:
            return ""
        finally:
            if im is not None:
                im.close()

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
        with self.settings_lock:
            settings = self.s
            folder = settings.output_folder
            margins = (settings.margin_top_in, settings.margin_bottom_in)
        return self.print_catalog.list_prints(
            folder, margins, os.path.join(self.home, "thumbs", "by_name"),
            self._read_output_metadata)

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

            # Apaga tambem os previews do PRT excluido, sem seguir symlinks.
            thumbs_root = os.path.join(self.home, "thumbs")
            preview_names = [("by_name", os.path.splitext(os.path.basename(f))[0] + ".jpg")]
            with self.lock:
                for job in self.jobs:
                    if job.get("out") == f:
                        preview_names.append(("", job["id"] + ".jpg"))
                        job["thumb"] = ""
            if not os.path.islink(thumbs_root):
                for subdir, filename in preview_names:
                    folder = os.path.join(thumbs_root, subdir)
                    thumb = os.path.join(folder, filename)
                    if (not os.path.islink(folder) and not os.path.islink(thumb)
                            and os.path.isfile(thumb)):
                        try:
                            os.remove(thumb)
                        except OSError:
                            self.log("Aviso: miniatura antiga nao pode ser removida.")
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
            # Uma troca de senha invalida tokens antigos (incluindo de outras abas).
            with self.lock:
                self.tokens.clear()
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


def _bind_host():
    """Host de escuta; mantém loopback por padrão e só abre LAN por opt-in."""
    value = os.environ.get("AUTORIP_BIND_HOST", "127.0.0.1").strip()
    return value or "127.0.0.1"


def _allowed_hosts(bind_host):
    configured = os.environ.get("AUTORIP_ALLOWED_HOSTS", "").split(",")
    values = {item.strip().lower().rstrip(".") for item in configured if item.strip()}
    if not values:
        values = {"127.0.0.1", "localhost"}
    if bind_host not in ("0.0.0.0", "::"):
        values.add(bind_host.lower().rstrip("."))
    return values


def _mobile_connection_url():
    """URL QR somente para IPv4 privado/link-local que o listener realmente aceita."""
    bind_host = _bind_host().strip().lower().rstrip(".")
    public_host = os.environ.get("AUTORIP_PUBLIC_HOST", "").strip()
    candidate = public_host or bind_host
    try:
        address = ipaddress.IPv4Address(candidate)
        bound = ipaddress.IPv4Address(bind_host)
    except ipaddress.AddressValueError:
        return None
    if address.is_loopback or address.is_unspecified or not (address.is_private or address.is_link_local):
        return None
    if not bound.is_unspecified and (bound.is_loopback or bound != address):
        return None
    if address.compressed.lower() not in _allowed_hosts(bind_host):
        return None
    if HTTP_SERVER is None:
        return None
    port = int(HTTP_SERVER.server_address[1])
    if not 1 <= port <= 65535:
        return None
    return f"http://{address.compressed}:{port}/"


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
        self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers(); self.wfile.write(body)

    def _auth(self):
        incoming = self.headers.get("X-Token", "")
        with APP.lock:
            tokens = tuple(APP.tokens)
        return bool(incoming) and any(secrets.compare_digest(incoming, token) for token in tokens)

    def _host_allowed(self):
        """Aceita apenas hosts explicitamente autorizados e a porta real."""
        try:
            parsed = urlparse("//" + self.headers.get("Host", ""))
            return (parsed.hostname and parsed.hostname.lower().rstrip(".") in _allowed_hosts(_bind_host())
                    and parsed.port == self.server.server_address[1]
                    and not parsed.username and not parsed.password
                    and not parsed.path and not parsed.query and not parsed.fragment)
        except ValueError:
            return False

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

    def _save_request_body(self, path, maximum=None):
        raw_length = self.headers.get("Content-Length", "0")
        if not raw_length.isdigit():
            raise ValueError("Content-Length invalido.")
        length = int(raw_length)
        if length <= 0:
            raise ValueError("O arquivo enviado esta vazio.")
        if maximum is not None and length > maximum:
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
        if not self._host_allowed():
            return self._send(403, {"error": "host local nao autorizado"})
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(res_path("ui", "index.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path in ("/planner.js", "/printexp-network.js"):
            with open(res_path("ui", u.path[1:]), "rb") as source:
                return self._send(200, source.read(), "application/javascript; charset=utf-8")
        mobile_qr_assets = {
            "/mobile-android-qr.png": "mobile-android-qr.png",
            "/mobile-ios-guide-qr.png": "mobile-ios-guide-qr.png",
        }
        if u.path in mobile_qr_assets:
            try:
                path = res_path("ui", mobile_qr_assets[u.path])
                with open(path, "rb") as image:
                    data = image.read(256 * 1024 + 1)
                if len(data) > 256 * 1024:
                    return self._send(404, {"error": "nao encontrado"})
                return self._send(200, data, "image/png")
            except OSError:
                return self._send(404, {"error": "nao encontrado"})
        if u.path == "/api/state":
            global LAST_CLIENT_SEEN
            LAST_CLIENT_SEEN = time.monotonic()
            if not self._auth():
                # Mantem o monitor do browser vivo na tela de login, sem expor
                # filas, nomes de artes, logs ou caminhos de producao.
                return self._send(200, dict(version=__version__, has_pass=APP.has_pass(),
                                            brand="AutoRIP", has_logo=False, locked=True))
            with APP.lock:
                jobs = [dict(job) for job in APP._retained_jobs(MAX_STATE_HISTORY)]
                queue_used = APP._queue_used()
                queue_preparing = len(APP._admission_reservations)
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
                pending = APP._outbox_counter.count(APP.home)
            except Exception:
                pending = -1
            return self._send(200, dict(version=__version__, auto=auto, has_pass=APP.has_pass(),
                                        jobs=jobs, log=logs, hot_folder=hot_folder, output_folder=output_folder,
                                        icc=icc, brand=brand, offline=offline, pending=pending, has_logo=has_logo,
                                        queue_used=queue_used, queue_limit=MAX_PENDING_JOBS,
                                        queue_preparing=queue_preparing))
        if u.path == "/api/prints":
            return self._send(200, APP.list_prints()) if self._auth() else self._send(401, {"error": "login"})
        if u.path == "/api/hot-files":
            return self._send(200, APP.list_hot_files()) if self._auth() else self._send(401, {"error": "login"})
        if u.path == "/api/thumb":
            if not self._auth(): return self._send(401, {"error": "login"})
            q = parse_qs(u.query); jid = os.path.basename(q.get("id", [""])[0]); nm = os.path.basename(q.get("name", [""])[0])
            thumbs_path = os.path.join(APP.home, "thumbs")
            if os.path.islink(thumbs_path):
                return self._send(404, {})
            thumbs_root = os.path.realpath(thumbs_path)
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
        if u.path == "/api/printexp/network":
            if not self._auth(): return self._send(401, {"error": "login"})
            try:
                return self._send(200, {"local_ipv4s": printexp_network.local_ipv4s()})
            except OSError:
                return self._send(503, {"error": "Consulta de IPv4 indisponível; use configuração manual."})
        if u.path == "/api/mobile/qr":
            if not self._auth():
                return self._send(401, {"error": "login"})
            url = _mobile_connection_url()
            if not url:
                return self._send(409, {"error": "Para gerar o QR, inicie o AutoRIP usando AUTORIP_BIND_HOST com o IPv4 privado deste computador. Se usar 0.0.0.0, defina também AUTORIP_PUBLIC_HOST e inclua esse IP em AUTORIP_ALLOWED_HOSTS."})
            image = io.BytesIO()
            segno.make_qr(url, error="M").save(image, kind="svg", scale=7, border=4)
            return self._send(200, {"url": url, "svg": image.getvalue().decode("utf-8")})
        self._send(404, {"error": "nao encontrado"})

    def do_POST(self):
        if not self._host_allowed():
            return self._send(403, {"error": "host local nao autorizado"})
        u = urlparse(self.path)
        if not self._origin_allowed():
            return self._send(403, {"error": "origem da requisicao nao autorizada"})
        try:
            if u.path in ("/api/printexp/discover", "/api/printexp/check"):
                if not self._auth(): return self._send(401, {"error": "login"})
                data = self._json(max_bytes=2048)
                if not APP.printexp_network_lock.acquire(blocking=False):
                    return self._send(429, {"error": "Uma verificação de rede está em andamento; aguarde."})
                try:
                    if u.path.endswith("/discover"):
                        return self._send(200, {"receivers": printexp_network.discover_receivers()})
                    return self._send(200, printexp_network.check_connection(data.get("host"), data.get("port")))
                finally:
                    APP.printexp_network_lock.release()
            if u.path == "/api/layout/plan":
                if not self._auth(): return self._send(401, {"error": "login"})
                if not APP._layout_lock.acquire(blocking=False):
                    return self._send(429, {"error": "Um planejamento está em andamento; aguarde."})
                try:
                    result = APP.plan_layout(self._json(max_bytes=65536))
                finally:
                    APP._layout_lock.release()
                return self._send(200, result)
            if u.path == "/api/auto":
                if not self._auth(): return self._send(401, {"error": "login"})
                on = self._json().get("on")
                if type(on) is not bool: raise ValueError("O estado automatico precisa ser booleano.")
                # Persistir a escolha antes de alterar o estado em memoria.
                APP.apply_settings({"auto_mode": on})
                APP.log("Modo automatico " + ("LIGADO" if on else "desligado"))
                return self._send(200, {"auto": on})
            if u.path == "/api/shutdown":
                if not self._auth(): return self._send(401, {"error": "login"})
                self._send(202, {"ok": True, "message": "AutoRIP sera encerrado."})
                threading.Thread(target=shutdown_server, daemon=True).start()
                return
            if u.path == "/api/jobs/control":
                if not self._auth(): return self._send(401, {"error": "login"})
                data = self._json(max_bytes=8192)
                job_id, action = data.get("id"), data.get("action")
                if not isinstance(job_id, str) or not isinstance(action, str):
                    raise ValueError("O controle precisa informar id e acao.")
                return self._send(200, APP.control_job(job_id, action))
            if u.path == "/api/hot-files/enqueue":
                if not self._auth(): return self._send(401, {"error": "login"})
                data = self._json(max_bytes=8192)
                name, width = data.get("name"), data.get("width", "")
                if not isinstance(name, str) or not name:
                    raise ValueError("Informe o nome do arquivo da hot folder.")
                if not isinstance(width, (str, int, float)) or isinstance(width, bool):
                    raise ValueError("A largura precisa ser numerica.")
                return self._send(202, APP.enqueue_hot_file(name, width))
            if u.path == "/api/upload":
                if not self._auth(): return self._send(401, {"error": "login"})
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
        except QueueFullError as e:
            return self._send(429, {"error": str(e)})
        except FileNotFoundError as e:
            return self._send(404, {"error": str(e)})
        except InsufficientStorageError as e:
            return self._send(507, {"error": str(e)})
        except OverflowError as e:
            return self._send(413, {"error": str(e)})
        except ValueError as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:
            traceback.print_exc(); return self._send(500, {"error": str(e)})
        self._send(404, {"error": "nao encontrado"})


def _can_close_idle_browser(app):
    """Autoriza desligamento por inatividade apenas quando nao ha producao.

    A queda de polling do navegador nao significa fim de um RIP ou das
    integracoes em execucao. O comando explicito /api/shutdown permanece.
    """
    with app.settings_lock:
        automatic = app.auto
        settings = app.s
        trello_active = (not settings.offline_mode and bool(settings.trello_key)
                         and bool(settings.trello_token) and bool(settings.trello_in_list))
    with app.lock:
        pending = bool(app.queued_sources or app.archive_pending
                       or getattr(app, "_admission_reservations", ())) or not app.q.empty()
    return not (automatic or trello_active or pending)


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
    bind_host = _bind_host()
    srv = None
    for p in range(port, port + 20):
        try: srv = ThreadingHTTPServer((bind_host, p), H); break
        except OSError: continue
    if srv is None:
        for lock in APP._watch_locks: lock.release()
        for lock in APP._output_locks: lock.release()
        APP._instance_lock.release()
        raise OSError("nenhuma porta local disponivel para o painel AutoRIP")
    HTTP_SERVER = srv
    LAST_CLIENT_SEEN = time.monotonic()
    display_host = os.environ.get("AUTORIP_PUBLIC_HOST", bind_host)
    url = f"http://{display_host}:{srv.server_address[1]}/"
    print("AutoRIP em", url, flush=True)
    report("AutoRIP ativo — monitorando a pasta de entrada")
    if open_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    if open_browser:
        def browser_monitor():
            while HTTP_SERVER is srv:
                if (time.monotonic() - LAST_CLIENT_SEEN > 15
                        and _can_close_idle_browser(APP)):
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

    try:
        root = tk.Tk()
    except tk.TclError:
        serve(open_browser=False)
        return
    root.title("AutoRIP — modo direto")
    root.geometry("600x240")
    root.minsize(460, 220)
    root.configure(bg="#1a1a1a")
    messages = queue.Queue()
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
    def open_panel():
        srv = HTTP_SERVER
        if srv is not None:
            webbrowser.open(f"http://127.0.0.1:{srv.server_address[1]}/")

    tk.Button(root, text="Abrir painel e configurações", command=open_panel,
              bg="#00aeef", fg="#1a1a1a", relief="flat", padx=18, pady=7).pack(pady=4)
    tk.Button(root, text="Encerrar", command=close_direct,
              bg="#ec008c", fg="white", relief="flat", padx=18, pady=7).pack(pady=12)

    def start_local():
        try:
            started = serve(open_browser=False, status_callback=messages.put)
            if started is False and not DIRECT_CLOSING:
                messages.put("Não iniciado. Verifique se já existe outra instância aberta.")
        except Exception as exc:
            messages.put(f"Falha ao iniciar: {exc}")

    def refresh_status():
        if stop_event.is_set():
            return
        while True:
            try: status.set(messages.get_nowait())
            except queue.Empty: break
        if HTTP_SERVER is not None:
            with APP.lock:
                active = sum(job["status"] == "processando" for job in APP.jobs)
            with APP.settings_lock:
                automatic, offline = APP.auto, APP.s.offline_mode
            status.set(f"Pronto — Automático {'ligado' if automatic else 'desligado'} | "
                       f"RIP: {active} | Na fila: {APP.q.qsize()} | {'Offline' if offline else 'Rede habilitada'}")
        root.after(500, refresh_status)

    root.after(100, refresh_status)
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
