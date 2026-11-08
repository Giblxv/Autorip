import os
import shutil
import stat
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from autorip import integrations
from conftest import wait_for_job


def test_modo_offline_nao_chama_rede_e_preserva_outbox(app, sample_png, tmp_path, monkeypatch):
    hits = []
    outbox_saved = threading.Event()
    original_add = integrations.outbox_add

    def record_saved_outbox(*args, **kwargs):
        result = original_add(*args, **kwargs)
        outbox_saved.set()
        return result

    monkeypatch.setattr(integrations, "outbox_add", record_saved_outbox)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            hits.append(self.path)
            body = b"{}"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        app.s.webhook_url = f"http://127.0.0.1:{http.server_address[1]}/hook"
        source = tmp_path / "offline.png"
        shutil.copyfile(sample_png, source)
        job = app.enqueue(str(source), 3, move_to_done=False)
        wait_for_job(job)
        # "pronto" indica o PRT pronto; a persistencia da notificacao vem depois.
        assert outbox_saved.wait(timeout=10), "A notificacao offline nao foi persistida"

        assert job["status"] == "pronto" and os.path.exists(job["out"])
        assert hits == []
        items = integrations.outbox_load(app.home)
        assert len(items) == 1 and items[0]["sent"] == []
        outbox_path = os.path.join(app.home, "outbox.json")
        if os.name != "nt":
            assert stat.S_IMODE(os.stat(outbox_path).st_mode) == 0o600

        assert integrations.outbox_flush(app.s, app.home, app.log) == 0
        assert hits == []
        app.s.offline_mode = False
        assert integrations.outbox_flush(app.s, app.home, app.log) == 1
        assert hits == ["/hook"]
        assert integrations.outbox_load(app.home) == []
    finally:
        http.shutdown()
        http.server_close()
