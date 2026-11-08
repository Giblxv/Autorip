import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

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

        # Testa o envio de rede independentemente do timing do RIP/worker.
        settings.trello_in_list = ""
        job = {"name": "pedido42.png", "out": os.path.join(settings.output_folder, "pedido42.PRT")}
        info = {"width_cm": 3.0, "height_cm": 2.0, "n_dots": 300, "n_rows": 200}
        results = integrations.notify_done(settings, job, info, app.log)
        assert results == {"webhook": True, "Trello": True, "Notion": True, "Jira": True}

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
