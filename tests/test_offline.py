import os, sys, json, threading, time, tempfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HITS = []
class F(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0))); HITS.append(self.path)
        b = b"{}"; self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b)
srv = ThreadingHTTPServer(("127.0.0.1", 0), F); threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_address[1]}"
os.environ["AUTORIP_HOME"] = tempfile.mkdtemp()
from autorip.server import App
from autorip import integrations
app = App(); s = app.s; s.auto_mode = False; app.auto = False
s.icc_path = "/mnt/user-data/uploads/Sublinks_DTF_E602_LM720x2400_8Pass_.icc"; app.rip = type(app.rip)(s)
s.webhook_url = base + "/hook"; assert s.offline_mode is True           # offline por padrao
png = os.environ.get("TEST_PNG", "/tmp/teste.png")
job = app.enqueue(png, 3, move_to_done=False)
for _ in range(60):
    if job["status"] in ("pronto", "erro"): break
    time.sleep(0.5)
assert job["status"] == "pronto" and os.path.exists(job["out"]), "o RIP precisa funcionar offline"
time.sleep(1); assert HITS == [], "offline nao pode chamar a rede"
assert len(integrations.outbox_load(app.home)) == 1, "aviso deve ficar na fila"
s.offline_mode = False
assert integrations.outbox_flush(s, app.home, app.log) == 1; time.sleep(0.5)
assert HITS == ["/hook"] and integrations.outbox_load(app.home) == []
print("offline OK")
