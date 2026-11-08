import os, sys, json, threading, tempfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GOT = {}
class F(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_POST(self):
        GOT["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); GOT["key"] = self.headers.get("x-api-key")
        b = json.dumps({"content": [{"type": "text", "text": "Sugestao 1: calibrar curva de branco"}]}).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
srv = ThreadingHTTPServer(("127.0.0.1", 0), F); threading.Thread(target=srv.serve_forever, daemon=True).start()
from autorip.config import Settings
from autorip import agent
s = Settings(); s.anthropic_key = "sk-test"; s.trello_token = "SEGREDO"; s.anthropic_base = f"http://127.0.0.1:{srv.server_address[1]}"
out = agent.ask(s, [{"name": "a.png", "status": "pronto"}], ["log1"])
assert "Sugestao 1" in out and GOT["key"] == "sk-test"
payload = json.dumps(GOT["body"])
assert "SEGREDO" not in payload and "sk-test" not in payload, "segredo vazou"
assert GOT["body"]["tools"][0]["type"] == "web_search_20250305"
print("agente OK")
