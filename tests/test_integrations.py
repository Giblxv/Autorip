import os, sys, json, threading, time, tempfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RECV = []
PNG = open(os.environ.get("TEST_PNG", "/tmp/teste.png"), "rb").read()

class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _ok(self, obj, ctype="application/json"):
        b = obj if isinstance(obj, bytes) else json.dumps(obj).encode()
        self.send_response(200); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        RECV.append(("GET", self.path))
        if "/lists/L_IN/cards" in self.path:
            return self._ok([{"name": "Pedido 42", "attachments": [
                {"id": "a1", "name": "pedido42.png", "url": f"http://127.0.0.1:{PORT}/file/pedido42.png"},
                {"id": "a2", "name": "nota.pdf", "url": f"http://127.0.0.1:{PORT}/file/nota.pdf"}]}])
        if self.path.startswith("/file/"): return self._ok(PNG, "image/png")
        self._ok({})
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0)); body = self.rfile.read(n)
        RECV.append(("POST", self.path, self.headers.get("Authorization", ""), body[:200])); self._ok({"id": "x"})

srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{PORT}"

home = tempfile.mkdtemp(); os.environ["AUTORIP_HOME"] = home
from autorip.server import App
app = App(); s = app.s
s.icc_path = "/mnt/user-data/uploads/Sublinks_DTF_E602_LM720x2400_8Pass_.icc"; app.rip = type(app.rip)(s)
s.auto_mode = False; app.auto = False; s.offline_mode = False
s.trello_base = base + "/1"; s.trello_key = "K"; s.trello_token = "T"; s.trello_in_list = "L_IN"; s.trello_out_list = "L_OUT"
s.notion_base = base + "/notion"; s.notion_token = "N"; s.notion_db = "DB"
s.jira_url = base; s.jira_email = "a@b.c"; s.jira_token = "J"; s.jira_project = "RIP"; s.webhook_url = base + "/hook"

from autorip import integrations
n = integrations.pull_trello(s, set(), app.log)
assert n == 1 and os.path.exists(os.path.join(s.hot_folder, "pedido42.png")), "entrada Trello falhou"
job = app.enqueue(os.path.join(s.hot_folder, "pedido42.png"), 3)
for _ in range(60):
    if job["status"] in ("pronto", "erro"): break
    time.sleep(0.5)
assert job["status"] == "pronto", job
time.sleep(1.5)
paths = [r[1].split("?")[0] for r in RECV if r[0] == "POST"]
print(sorted(paths)); print(job.get("thumb"))
for p in ("/hook", "/1/cards", "/notion/pages", "/rest/api/3/issue"): assert p in paths, p
assert any(r[2].startswith("Basic ") for r in RECV if r[0] == "POST" and "issue" in r[1])
assert os.path.exists(os.path.join(home, "thumbs", job["id"] + ".jpg"))
print("integracoes OK"); print("\n".join(app.log_lines))
