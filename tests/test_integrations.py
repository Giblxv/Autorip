import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from autorip import integrations
from autorip.config import Settings
from conftest import wait_for_job


def test_trello_download_e_integracoes_de_saida_nao_expoem_tokens(app, sample_png):
    received = []
    png = sample_png.read_bytes()
    port_holder = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, value, content_type="application/json", status=200):
            body = value if isinstance(value, bytes) else json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            received.append(("GET", self.path, self.headers.get("Authorization", "")))
            if self.path.startswith("/1/lists/L_IN/cards"):
                return self._reply([{"name": "Pedido 42", "attachments": [
                    {"id": "a1", "name": "pedido42.png", "url": f"http://127.0.0.1:{port_holder['port']}/file/pedido42.png"},
                    {"id": "a2", "name": "nota.pdf", "url": f"http://127.0.0.1:{port_holder['port']}/file/nota.pdf"},
                ]}])
            if self.path.startswith("/file/pedido42.png"):
                return self._reply(png, "image/png")
            self._reply({})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            received.append(("POST", self.path, self.headers.get("Authorization", ""), body[:200]))
            self._reply({"id": "x"})

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port_holder["port"] = http.server_address[1]
    base = f"http://127.0.0.1:{http.server_address[1]}"
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        settings = app.s
        settings.trello_base = base + "/1"
        settings.trello_key, settings.trello_token = "KEY_PRIVATE", "TOKEN_PRIVATE"
        settings.trello_in_list, settings.trello_out_list = "L_IN", "L_OUT"
        settings.notion_base, settings.notion_token, settings.notion_db = base + "/notion", "NOTION_PRIVATE", "DB"
        settings.jira_url, settings.jira_email, settings.jira_token, settings.jira_project = base, "a@example.test", "JIRA_PRIVATE", "RIP"
        settings.webhook_url = base + "/hook"
        settings.offline_mode = False

        downloaded = integrations.pull_trello(settings, set(), app.log)
        artifact = os.path.join(settings.hot_folder, "pedido42.png")
        assert downloaded == 1 and os.path.isfile(artifact)
        assert integrations._allowed_attachment_url("http://example.invalid/file.png") is False
        assert received[0][2].startswith("OAuth ")
        assert "key=" not in received[0][1] and "token=" not in received[0][1]

        # Testa também o envio direto sem depender do agendamento do worker.
        settings.trello_in_list = ""
        job = {"name": "pedido42.png", "out": os.path.join(settings.output_folder, "pedido42.PRT")}
        info = {"width_cm": 3.0, "height_cm": 2.0, "n_dots": 300, "n_rows": 200}
        results = integrations.notify_done(settings, job, info, app.log)
        assert results == {"webhook": True, "Trello": True, "Notion": True, "Jira": True}

        worker_job = app.enqueue(artifact, 3)
        wait_for_job(worker_job)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and integrations.outbox_load(app.home):
            time.sleep(0.05)
        assert integrations.outbox_load(app.home) == []

        posts = [(urlsplit(row[1]).path, row[2]) for row in received if row[0] == "POST"]
        paths = {path for path, _ in posts}
        assert {"/hook", "/1/cards", "/notion/pages", "/rest/api/3/issue"}.issubset(paths)
        assert any(auth.startswith("OAuth ") for path, auth in posts if path == "/1/cards")
        assert any(auth.startswith("Basic ") for path, auth in posts if path.endswith("/issue"))
        assert all("key=" not in row[1] and "token=" not in row[1] for row in received)
    finally:
        http.shutdown()
        http.server_close()


def test_outbox_retem_servico_falho_sem_reenviar_o_confirmado(tmp_path):
    counts = {"webhook": 0, "trello": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            if self.path.startswith("/1/cards"):
                counts["trello"] += 1
                status = 500 if counts["trello"] == 1 else 200
            else:
                counts["webhook"] += 1
                status = 200
            body = b"{}"
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{http.server_address[1]}"
        settings = Settings(offline_mode=False, webhook_url=base + "/hook",
                            trello_base=base + "/1", trello_key="K", trello_token="T",
                            trello_out_list="OUT")
        integrations.outbox_add(str(tmp_path), {"name": "a.png", "out": "/private/a.PRT"},
                                {"width_cm": 3, "height_cm": 2})
        assert integrations.outbox_flush(settings, str(tmp_path), lambda _msg: None) == 0
        pending = integrations.outbox_load(str(tmp_path))
        assert pending[0]["sent"] == ["webhook"]
        assert integrations.outbox_flush(settings, str(tmp_path), lambda _msg: None) == 1
        assert counts == {"webhook": 1, "trello": 2}
        assert integrations.outbox_load(str(tmp_path)) == []
    finally:
        http.shutdown()
        http.server_close()


def test_outbox_nao_descarta_aviso_se_todos_os_canais_forem_desativados(tmp_path):
    settings = Settings(offline_mode=False)
    integrations.outbox_add(str(tmp_path), {"name": "a.png", "out": "a.PRT"}, {"width_cm": 3})
    assert integrations.outbox_flush(settings, str(tmp_path), lambda _message: None) == 0
    assert len(integrations.outbox_load(str(tmp_path))) == 1


def test_outbox_add_e_idempotente_por_job_id(tmp_path):
    job = {"id": "rip-123", "name": "a.png", "out": "a.PRT"}
    info = {"width_cm": 3, "height_cm": 2}
    assert integrations.outbox_add(str(tmp_path), job, info) is True
    assert integrations.outbox_add(str(tmp_path), job, info) is False
    assert len(integrations.outbox_load(str(tmp_path))) == 1
    assert integrations.outbox_load(str(tmp_path))[0]["job_id"] == "rip-123"


def test_trello_anexo_invalido_nao_bloqueia_proximo_do_mesmo_lote(
        tmp_path, sample_png, monkeypatch):
    import shutil

    hot = tmp_path / "hot"
    hot.mkdir()
    settings = Settings(offline_mode=False, hot_folder=str(hot), trello_key="K",
                        trello_token="T", trello_in_list="L")
    cards = [{"name": "Pedidos", "attachments": [
        {"id": "ruim", "name": "corrompida.png",
         "url": "https://trello.com/1/bad.png?private=nao-expor"},
        {"id": "bom", "name": "valida.png",
         "url": "https://trello.com/1/good.png"},
    ]}]
    monkeypatch.setattr(integrations, "_req", lambda *_a, **_kw: cards)
    attempts, logs = [], []

    def download(url, path, headers, **kwargs):
        attempts.append(url)
        if "bad.png" in url:
            raise ValueError("URL confidencial: private=nao-expor")
        shutil.copyfile(sample_png, path)

    monkeypatch.setattr(integrations, "_download_attachment", download)
    seen = set()
    assert integrations.pull_trello(settings, seen, logs.append) == 1
    assert seen == {"bom"}
    assert (hot / "valida.png").is_file()
    assert not (hot / "corrompida.png").exists()
    assert not list(hot.glob(".trello.*.part"))
    assert len(attempts) == 2
    assert any("ValueError" in line for line in logs)
    assert all("private=nao-expor" not in line for line in logs)


def test_trello_falha_de_publicacao_nao_registra_anexo_como_baixado(
        tmp_path, sample_png, monkeypatch):
    import shutil

    hot = tmp_path / "hot"
    hot.mkdir()
    settings = Settings(offline_mode=False, hot_folder=str(hot), trello_key="K",
                        trello_token="T", trello_in_list="L")
    cards = [{"name": "Pedido", "attachments": [
        {"id": "pendente", "name": "pedido.png",
         "url": "https://trello.com/1/file.png"}]}]
    monkeypatch.setattr(integrations, "_req", lambda *_a, **_kw: cards)
    monkeypatch.setattr(integrations, "_download_attachment",
                        lambda url, path, headers, **kw: shutil.copyfile(sample_png, path))

    def cannot_publish(*args):
        raise OSError("disco cheio ao publicar")

    monkeypatch.setattr(integrations, "publish_unique_file", cannot_publish)
    seen = set()
    with pytest.raises(OSError, match="disco cheio"):
        integrations.pull_trello(settings, seen)
    assert not seen
    assert not list(hot.glob(".trello.*.part"))


def test_outbox_preserva_canal_pendente_apos_desativacao_parcial(tmp_path, monkeypatch):
    settings = Settings(offline_mode=False, webhook_url="https://example.invalid/hook",
                        trello_key="K", trello_token="T", trello_out_list="OUT")
    integrations.outbox_add(str(tmp_path), {"id": "pending", "name": "arte.png"}, {})
    calls = []

    def notify(s, job, info, log, offline_check=None, already_sent=()):
        missing = set(integrations.enabled_services(s)) - set(already_sent)
        calls.append(missing)
        return {name: name == "webhook" for name in missing}

    monkeypatch.setattr(integrations, "notify_done", notify)
    assert integrations.outbox_flush(settings, str(tmp_path)) == 0
    settings.trello_token = ""
    assert integrations.outbox_flush(settings, str(tmp_path)) == 0
    pending = integrations.outbox_load(str(tmp_path))
    assert len(pending) == 1 and pending[0]["sent"] == ["webhook"]
    settings.trello_token = "T"
    monkeypatch.setattr(integrations, "notify_done",
                        lambda s, job, info, log, **kwargs: {"Trello": True})
    assert integrations.outbox_flush(settings, str(tmp_path)) == 1
    assert integrations.outbox_load(str(tmp_path)) == []
    assert calls[0] == {"webhook", "Trello"}



def test_outbox_registra_destinos_ainda_em_modo_offline(tmp_path, monkeypatch):
    integrations.outbox_add(str(tmp_path), {"id": "offline"}, {},
                            services={"webhook", "Trello"})
    settings = Settings(offline_mode=False, webhook_url="https://example.invalid/hook")
    monkeypatch.setattr(integrations, "notify_done", lambda *args, **kwargs: {"webhook": True})
    assert integrations.outbox_flush(settings, str(tmp_path)) == 0
    item = integrations.outbox_load(str(tmp_path))[0]
    assert item["required"] == ["Trello", "webhook"]
    assert item["sent"] == ["webhook"]
