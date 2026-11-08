import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from autorip import agent
from autorip.config import Settings


def test_agent_envia_apenas_contexto_tecnico_para_endpoint_autorizado():
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received["key"] = self.headers.get("x-api-key")
            body = json.dumps({"content": [{"type": "text", "text": "Sugestao: calibrar curva de branco"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    try:
        settings = Settings(offline_mode=False, anthropic_key="sk-test",
                            trello_token="SEGREDO",
                            anthropic_base=f"http://127.0.0.1:{http.server_address[1]}")
        result = agent.ask(settings, [{"name": "pedido-confidencial.png", "status": "pronto"}],
                           ["/home/cliente/arquivo privado", "webhook_secret=exemplo"])
        payload = json.dumps(received["body"], ensure_ascii=False)
        assert "Sugestao" in result
        assert received["key"] == "sk-test"
        assert "SEGREDO" not in payload and "sk-test" not in payload
        assert "pedido-confidencial" not in payload and "/home/cliente" not in payload
        assert received["body"]["tools"][0]["type"] == "web_search_20250305"
    finally:
        http.shutdown()
        http.server_close()


def test_agente_respeita_modo_offline_sem_chamada():
    settings = Settings(offline_mode=True, anthropic_key="sk-test")
    with pytest.raises(RuntimeError, match="offline"):
        agent.ask(settings, [], [])
