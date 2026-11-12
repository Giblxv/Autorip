"""Integracoes opcionais, downloads limitados e outbox duravel para operacao DTF."""
import base64
import ipaddress
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from .imaging import Image
from .paths import publish_unique_file, safe_filename

IMG = (".png", ".tif", ".tiff", ".jpg", ".jpeg")
MAX_API_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_ATTACHMENT_BYTES = 200 * 1024 * 1024
_OUTBOX_LOCK = threading.RLock()
_OUTBOX_FLUSH_LOCK = threading.Lock()
_TRELLO_SEEN_LIMIT = 10000  # evita crescimento infinito do registro de anexos
OUTBOX_COUNT_CACHE_SECONDS = 5.0


def _trello_seen_path(home):
    return os.path.join(home, "trello_seen.json")


def _load_trello_seen(home):
    """Preserva registros invalidos para inspeção, sem repetir downloads em silencio."""
    try:
        with open(_trello_seen_path(home), encoding="utf-8") as source:
            stored = json.load(source)
    except FileNotFoundError:
        return []
    if (not isinstance(stored, list) or len(stored) > _TRELLO_SEEN_LIMIT
            or any(type(identifier) is not str or not 1 <= len(identifier) <= 128
                   for identifier in stored)
            or len(set(stored)) != len(stored)):
        raise ValueError("Registro de anexos Trello invalido; downloads suspensos para evitar duplicacao.")
    return stored



class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def _req(url, data=None, headers=None, method=None, timeout=20):
    h = {"User-Agent": "AutoRIP/0.6"}
    h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=body, headers=h,
                                     method=method or ("POST" if body is not None else "GET"))
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > MAX_API_RESPONSE_BYTES:
            raise ValueError("Resposta da integracao excede o limite de 16 MiB.")
        raw = response.read(MAX_API_RESPONSE_BYTES + 1)
    if len(raw) > MAX_API_RESPONSE_BYTES:
        raise ValueError("Resposta da integracao excede o limite de 16 MiB.")
    return json.loads(raw) if raw[:1] in (b"{", b"[") else raw


def _trello(s, path, **query):
    parsed = urllib.parse.urlsplit(s.trello_base)
    host = (parsed.hostname or "").lower().rstrip(".")
    if not ((parsed.scheme == "https" and (host == "trello.com" or host.endswith(".trello.com")))
            or (parsed.scheme == "http" and _loopback_host(host))):
        raise ValueError("Base Trello precisa ser HTTPS em trello.com (ou loopback para testes locais).")
    return f"{s.trello_base.rstrip('/')}{path}?{urllib.parse.urlencode(query)}"


def _loopback_host(host):
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _trello_headers(s):
    return {"Authorization": f'OAuth oauth_consumer_key="{s.trello_key}", oauth_token="{s.trello_token}"'}


def _enabled(s):
    names = set()
    if s.webhook_url:
        names.add("webhook")
    if s.trello_key and s.trello_token and s.trello_out_list:
        names.add("Trello")
    if s.notion_token and s.notion_db:
        names.add("Notion")
    if s.jira_url and s.jira_email and s.jira_token and s.jira_project:
        names.add("Jira")
    return names


def enabled_services(s):
    return frozenset(_enabled(s))


def _is_offline(s, offline_check=None):
    try:
        return bool(s.offline_mode or (offline_check and offline_check()))
    except Exception:
        return True


def notify_done(s, job, info, log=print, offline_check=None, already_sent=()):
    """Tenta cada canal configurado de forma independente e informa o que foi confirmado."""
    required = _enabled(s)
    results = {name: False for name in required}
    already = set(already_sent or ())
    if _is_offline(s, offline_check):
        return results

    filename = safe_filename(job.get("name", "arte"))
    out_name = os.path.basename(job.get("out", ""))
    title = f"RIP pronto: {filename}"
    desc = f"{info.get('width_cm', 0):.2f} x {info.get('height_cm', 0):.2f} cm\nArquivo: {out_name}"

    def send(name, fn):
        if name in already or name not in required or _is_offline(s, offline_check):
            return
        try:
            fn()
            results[name] = True
            log(f"Integracao {name}: enviado")
        except Exception as exc:
            # Nao imprimir URLs, cabecalhos ou query strings que podem conter credenciais.
            log(f"Integracao {name}: falhou ({type(exc).__name__})")

    if "webhook" in required:
        payload = dict(event="rip_done", name=filename, out=out_name,
                       width_cm=info.get("width_cm"), height_cm=info.get("height_cm"),
                       n_dots=info.get("n_dots"), n_rows=info.get("n_rows"))
        send("webhook", lambda: _req(s.webhook_url, payload))

    if "Trello" in required:
        send("Trello", lambda: _req(_trello(s, "/cards", idList=s.trello_out_list,
                                            name=title, desc=desc), headers=_trello_headers(s), method="POST"))

    if "Notion" in required:
        body = {"parent": {"database_id": s.notion_db},
                "properties": {"Name": {"title": [{"text": {"content": title}}]}},
                "children": [{"object": "block", "type": "paragraph",
                              "paragraph": {"rich_text": [{"type": "text", "text": {"content": desc}}]}}]}
        send("Notion", lambda: _req(f"{s.notion_base.rstrip('/')}/pages", body, {
            "Authorization": f"Bearer {s.notion_token}", "Notion-Version": "2022-06-28"}))

    if "Jira" in required:
        auth = base64.b64encode(f"{s.jira_email}:{s.jira_token}".encode()).decode()
        body = {"fields": {"project": {"key": s.jira_project}, "summary": title,
                           "issuetype": {"name": "Task"},
                           "description": {"type": "doc", "version": 1,
                               "content": [{"type": "paragraph", "content":[{"type":"text","text":desc}]}]}}}
        send("Jira", lambda: _req(f"{s.jira_url.rstrip('/')}/rest/api/3/issue", body,
                                   {"Authorization": f"Basic {auth}"}))
    return results


def _allowed_attachment_url(url, allow_loopback=False):
    parsed = urllib.parse.urlsplit(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.username or parsed.password or not host:
        return False
    if parsed.scheme == "http":
        return allow_loopback and _loopback_host(host)
    if parsed.scheme != "https":
        return False
    return (host == "trello.com" or host.endswith(".trello.com")
            or host.endswith(".s3.amazonaws.com")
            or (host.startswith("s3.") and host.endswith(".amazonaws.com")))


def _download_attachment(url, path, headers, timeout=120, allow_loopback=False):
    if not _allowed_attachment_url(url, allow_loopback=allow_loopback):
        raise ValueError("URL do anexo Trello fora da allowlist HTTPS/loopback.")
    request = urllib.request.Request(url, headers={"User-Agent": "AutoRIP/0.6", **headers})

    class SafeRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, response_headers, newurl):
            if not _allowed_attachment_url(newurl, allow_loopback=allow_loopback):
                return None
            redirected = super().redirect_request(req, fp, code, msg, response_headers, newurl)
            if redirected and urllib.parse.urlsplit(req.full_url).hostname != urllib.parse.urlsplit(newurl).hostname:
                redirected.remove_header("Authorization")
            return redirected

    opener = urllib.request.build_opener(SafeRedirect())
    with opener.open(request, timeout=timeout) as response:
        if not _allowed_attachment_url(response.geturl(), allow_loopback=allow_loopback):
            raise ValueError("Redirecionamento do anexo para host nao permitido.")
        content_length = response.headers.get("Content-Length")
        if content_length and content_length.isdigit() and int(content_length) > MAX_ATTACHMENT_BYTES:
            raise ValueError("Anexo Trello excede 200 MiB.")
        total = 0
        with open(path, "wb") as target:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ATTACHMENT_BYTES:
                    raise ValueError("Anexo Trello excede 200 MiB.")
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
    if total == 0:
        raise ValueError("Anexo Trello vazio.")
    with Image.open(path) as image:
        image.verify()
    return total


def pull_trello(s, seen: set, log=print, offline_check=None, seen_home=None):
    """Baixa anexos permitidos e, opcionalmente, persiste recibos entre reinicios.

    O registro e gravado somente apos publicar o arquivo. Uma falha de energia
    entre esses dois passos ainda pode exigir reconciliacao manual (at-least-once).
    """
    if not (s.trello_key and s.trello_token and s.trello_in_list) or _is_offline(s, offline_check):
        return 0
    receipts = _load_trello_seen(seen_home) if seen_home is not None else []
    if seen_home is not None:
        # O registro em disco e a referencia entre reinicios; limite tambem
        # o set em memoria ao mesmo horizonte de recibos.
        seen.clear()
    seen.update(receipts)
    os.makedirs(s.hot_folder, exist_ok=True)
    if _is_offline(s, offline_check):
        return 0
    cards = _req(_trello(s, f"/lists/{s.trello_in_list}/cards", attachments="true",
                         attachment_fields="name,url,id"), headers=_trello_headers(s))
    trello_base = urllib.parse.urlsplit(s.trello_base)
    allow_loopback = trello_base.scheme == "http" and _loopback_host(trello_base.hostname or "")
    count = 0
    for card in cards:
        for attachment in card.get("attachments", []):
            if _is_offline(s, offline_check):
                return count
            name = safe_filename(attachment.get("name", ""))
            identifier = attachment.get("id")
            url = attachment.get("url", "")
            if (type(identifier) is not str or not 1 <= len(identifier) <= 128
                    or identifier in seen or not name.lower().endswith(IMG) or not url):
                continue
            if not _allowed_attachment_url(url, allow_loopback=allow_loopback):
                log("Trello: anexo ignorado (URL nao permitida)")
                continue
            host = (urllib.parse.urlsplit(url).hostname or "").lower().rstrip(".")
            headers = {}
            if host == "trello.com" or host.endswith(".trello.com"):
                headers = _trello_headers(s)
            fd, temporary = tempfile.mkstemp(prefix=".trello.", suffix=".part", dir=s.hot_folder)
            os.close(fd)
            try:
                try:
                    _download_attachment(url, temporary, headers, allow_loopback=allow_loopback)
                except Exception as exc:
                    # Um anexo invalido nao bloqueia os proximos; falhas no disco
                    # ao publicar/registrar recibos permanecem fatais.
                    log(f"Trello: anexo ignorado por falha no download ({type(exc).__name__}).")
                    continue
                if _is_offline(s, offline_check):
                    continue
                destination = publish_unique_file(temporary, os.path.join(s.hot_folder, name))
                if seen_home is not None:
                    # Somente marcamos como visto apos um recibo duravel; se
                    # a escrita falhar, alertamos e permitimos reconciliacao.
                    next_receipts = [existing for existing in receipts if existing != identifier]
                    next_receipts.append(identifier)
                    next_receipts = next_receipts[-_TRELLO_SEEN_LIMIT:]
                    _atomic_json(_trello_seen_path(seen_home), next_receipts)
                    receipts = next_receipts
                    seen.clear()
                    seen.update(receipts)
                else:
                    seen.add(identifier)
                count += 1
                log(f"Trello: baixado {os.path.basename(destination)} (cartao {safe_filename(card.get('name', ''))})")
            finally:
                try: os.remove(temporary)
                except OSError: pass
    return count


# ---------------- modo offline: fila de avisos ----------------
def _outbox_path(home):
    return os.path.join(home, "outbox.json")


def _atomic_json(path, value):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".outbox.", suffix=".tmp", dir=directory)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=False)
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, path)
    except BaseException:
        try: os.close(fd)
        except OSError: pass
        try: os.remove(temporary)
        except OSError: pass
        raise


def outbox_load(home):
    path = _outbox_path(home)
    try:
        with open(path, encoding="utf-8") as source:
            items = json.load(source)
    except FileNotFoundError:
        return []
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise ValueError("Arquivo de outbox invalido; os avisos locais foram preservados.")
    for item in items:
        sent = item.get("sent", [])
        if not isinstance(sent, list) or any(not isinstance(name, str) for name in sent):
            raise ValueError("Campo de status invalido na outbox; os avisos locais foram preservados.")
        required = item.get("required", [])
        if not isinstance(required, list) or any(not isinstance(name, str) for name in required):
            raise ValueError("Destinos invalidos na outbox; os avisos locais foram preservados.")
    return items


class OutboxCounter:
    """Uma contagem validada, sem reter trabalhos ou disputar o lock de envio."""
    def __init__(self):
        self._lock = threading.Lock()
        self._cached = None

    @staticmethod
    def _signature(path):
        try:
            info = os.stat(path)
        except FileNotFoundError:
            return None
        return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
                info.st_mtime_ns, info.st_ctime_ns)

    def count(self, home):
        home = os.path.abspath(home)
        path = _outbox_path(home)
        with self._lock:
            try:
                signature = self._signature(path)
                cached = self._cached
                if (cached is not None and cached[0] == path and cached[1] == signature
                        and time.monotonic() - cached[3] < OUTBOX_COUNT_CACHE_SECONDS):
                    return cached[2]
                self._cached = None
                count = len(outbox_load(home))
                # Troca/remoção durante a leitura não deve fixar um snapshot velho.
                if self._signature(path) == signature:
                    self._cached = (path, signature, count, time.monotonic())
                return count
            except BaseException:
                self._cached = None
                raise


def outbox_add(home, job, info, *, services=None):
    with _OUTBOX_LOCK:
        items = outbox_load(home)
        job_id = job.get("id")
        if job_id and any(item.get("job_id") == job_id for item in items):
            return False
        item = {"id": secrets.token_hex(12), "job_id": job_id,
                "job": {k: job.get(k) for k in ("name", "out")},
                "info": info, "sent": []}
        if services is not None:
            item["required"] = sorted(set(services))
        items.append(item)
        _atomic_json(_outbox_path(home), items)
        return True


def outbox_flush(s, home, log=print, offline_check=None):
    """Retenta cada servico pendente e remove somente notificacoes confirmadas."""
    if _is_offline(s, offline_check):
        return 0
    active = _enabled(s)
    if not active:
        return 0
    with _OUTBOX_FLUSH_LOCK:
        with _OUTBOX_LOCK:
            items = outbox_load(home)
            changed = False
            for item in items:
                targets = sorted(set(item.get("required", [])) | active)
                if item.get("required") != targets:
                    item["required"] = targets
                    changed = True
                if not item.get("id"):
                    item["id"] = secrets.token_hex(12)
                    changed = True
            if changed:
                _atomic_json(_outbox_path(home), items)
        if not items:
            return 0
        updates = {}
        completed_ids = set()
        for item in items:
            if _is_offline(s, offline_check):
                break
            required = set(item["required"])
            job, info = item.get("job", {}), item.get("info", {})
            sent = set(item.get("sent", []))
            if not isinstance(job, dict) or not isinstance(info, dict):
                continue
            if required.issubset(sent):
                completed_ids.add(item["id"])
                continue
            results = notify_done(s, job, info, log, offline_check=offline_check, already_sent=sent)
            sent.update(name for name, ok in results.items() if ok)
            if required.issubset(sent):
                completed_ids.add(item["id"])
            else:
                updates[item["id"]] = sorted(sent)
        with _OUTBOX_LOCK:
            current = outbox_load(home)
            remaining = []
            for item in current:
                identifier = item.get("id")
                if identifier in completed_ids:
                    continue
                if identifier in updates:
                    item["sent"] = updates[identifier]
                remaining.append(item)
            _atomic_json(_outbox_path(home), remaining)
        completed = len(completed_ids)
        if completed:
            log(f"Fila offline: {completed} aviso(s) confirmado(s)")
        return completed
