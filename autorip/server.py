"""Painel local do AutoRIP: servidor HTTP (127.0.0.1) + fila de jobs + modo automatico + senha."""
import os, sys, json, time, hashlib, secrets, shutil, threading, queue, traceback, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from dataclasses import asdict
from . import __version__
from .config import Settings
from .engine import Rip
from .watcher import EXTS
from . import integrations, agent
from PIL import Image, ImageDraw


def res_path(*p):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "autorip", *p)


def home_dir():
    h = os.environ.get("AUTORIP_HOME")
    if not h:
        h = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "AutoRIP")
    os.makedirs(h, exist_ok=True)
    return h


class App:
    def __init__(self):
        self.home = home_dir()
        self.cfg_path = os.path.join(self.home, "autorip.json")
        self.auth_path = os.path.join(self.home, "auth.json")
        self.s = Settings.load(self.cfg_path)
        for k in ("hot_folder", "output_folder", "printed_folder", "done_folder", "error_folder"):      # pastas relativas -> pasta do app
            v = getattr(self.s, k)
            if not os.path.isabs(v):
                setattr(self.s, k, os.path.join(self.home, v))
        self.rip = Rip(self.s)
        self.auto = self.s.auto_mode
        self.jobs, self.log_lines, self.tokens = [], [], set()
        self.q = queue.Queue(); self.lock = threading.Lock(); self.seen = set()
        self.inbox = os.path.join(self.home, "manual"); os.makedirs(self.inbox, exist_ok=True)
        for d in (self.s.hot_folder, self.s.output_folder, self.s.printed_folder, self.s.done_folder, self.s.error_folder):
            os.makedirs(d, exist_ok=True)
        threading.Thread(target=self._worker, daemon=True).start()
        threading.Thread(target=self._watch, daemon=True).start()

    # ---- log / jobs ----
    def log(self, msg):
        with self.lock:
            self.log_lines.append(time.strftime("%H:%M:%S ") + msg); self.log_lines[:] = self.log_lines[-200:]

    def enqueue(self, path, width_cm=None, move_to_done=True):
        job = dict(id=secrets.token_hex(4), name=os.path.basename(path), status="fila", progress=0.0, out="", error="")
        with self.lock:
            self.jobs.append(job); self.jobs[:] = self.jobs[-50:]
        self.q.put((job, path, width_cm, move_to_done))
        return job

    def _worker(self):
        while True:
            job, path, width_cm, move = self.q.get()
            job["status"] = "processando"; self.log(f"RIP: {job['name']}")
            out = os.path.join(self.s.output_folder, os.path.splitext(job["name"])[0] + ".PRT")
            try:
                def prog(p): job["progress"] = round(p, 3)
                info = self.rip.process(path, out, width_cm, progress=prog)
                job["thumb"] = self._thumb(job["id"], path)
                job.update(status="pronto", progress=1.0, out=out)
                self.log(f"OK: {os.path.basename(out)}  {info['width_cm']:.2f} x {info['height_cm']:.2f} cm")
                if self.s.offline_mode:
                    integrations.outbox_add(self.home, job, info)          # guarda para enviar quando houver internet
                else:
                    threading.Thread(target=integrations.notify_done, args=(self.s, dict(job), info, self.log), daemon=True).start()
                if move:
                    shutil.move(path, os.path.join(self.s.done_folder, job["name"]))
            except Exception as e:
                job.update(status="erro", error=str(e)); self.log(f"ERRO {job['name']}: {e}")
                traceback.print_exc()
                if move:
                    try: shutil.move(path, os.path.join(self.s.error_folder, job["name"]))
                    except Exception: pass

    def _trello_loop(self):
        seen = set()
        while True:
            try:
                if not self.s.offline_mode:
                    integrations.outbox_flush(self.s, self.home, self.log)
                    integrations.pull_trello(self.s, seen, self.log)
            except Exception as e: self.log(f"Trello (entrada) falhou: {e}")
            time.sleep(max(10, self.s.poll_seconds * 5))

    def _watch(self):
        threading.Thread(target=self._trello_loop, daemon=True).start()
        while True:
            try:
                if self.auto and os.path.isdir(self.s.hot_folder):
                    for n in sorted(os.listdir(self.s.hot_folder)):
                        p = os.path.join(self.s.hot_folder, n)
                        if n.lower().endswith(EXTS) and p not in self.seen:
                            sz = os.path.getsize(p); time.sleep(0.5)
                            if sz > 0 and sz == os.path.getsize(p):
                                self.seen.add(p); self.enqueue(p)
            except Exception:
                traceback.print_exc()
            time.sleep(max(0.5, self.s.poll_seconds))

    # ---- miniaturas ----
    def _thumb(self, jid, path, size=220):
        try:
            im = Image.open(path).convert("RGBA"); im.thumbnail((size, size))
            bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); d = ImageDraw.Draw(bg)
            for y in range(0, im.height, 10):                       # xadrez: mostra a transparencia (= area do branco)
                for x in range(0, im.width, 10):
                    if (x // 10 + y // 10) % 2: d.rectangle((x, y, x + 9, y + 9), fill=(225, 225, 225, 255))
            bg.alpha_composite(im)
            wm = self.s.watermark_path
            if wm and os.path.exists(wm):                           # marca d'agua do cliente
                w = Image.open(wm).convert("RGBA"); w.thumbnail((im.width // 2, im.height // 2))
                a = w.getchannel("A").point(lambda v: int(v * self.s.watermark_opacity)); w.putalpha(a)
                bg.alpha_composite(w, ((im.width - w.width) // 2, (im.height - w.height) // 2))
            d = os.path.join(self.home, "thumbs"); os.makedirs(d, exist_ok=True)
            rgb = bg.convert("RGB"); rgb.save(os.path.join(d, jid + ".jpg"), quality=82)
            nd = os.path.join(d, "by_name"); os.makedirs(nd, exist_ok=True)
            rgb.save(os.path.join(nd, os.path.splitext(os.path.basename(path))[0] + ".jpg"), quality=82)
            return f"/api/thumb?id={jid}"
        except Exception:
            return ""

    # ---- fila de impressao (arquivos .PRT prontos, aguardando o PrintExp) ----
    def list_prints(self):
        from .prt import read_header
        out = []
        folder = self.s.output_folder
        for n in os.listdir(folder) if os.path.isdir(folder) else []:
            if not n.lower().endswith(".prt"): continue
            f = os.path.join(folder, n)
            try:
                st = os.stat(f); h = read_header(f)
                w = h["n_dots"] / h["dpi_x"] * 2.54
                rows = h["n_rows"] - int((self.s.margin_top_in + self.s.margin_bottom_in) * h["dpi_y"])
                out.append(dict(name=n, mb=round(st.st_size / 1048576, 1), mtime=int(st.st_mtime),
                                width_cm=round(w, 2), height_cm=round(max(rows, 0) / h["dpi_y"] * 2.54, 2),
                                thumb="/api/thumb?name=" + os.path.splitext(n)[0]))
            except Exception:
                continue
        out.sort(key=lambda x: x["mtime"])                       # mais antigo primeiro (FIFO)
        return out

    def _print_file(self, name):
        name = os.path.basename(name)
        f = os.path.join(self.s.output_folder, name)
        if not name.lower().endswith(".prt") or not os.path.isfile(f): raise FileNotFoundError(name)
        return f

    def mark_printed(self, name):
        f = self._print_file(name)
        dst = os.path.join(self.s.printed_folder, os.path.basename(f))
        if os.path.exists(dst): dst = os.path.splitext(dst)[0] + time.strftime("_%H%M%S") + ".PRT"
        shutil.move(f, dst); self.log(f"Impresso: {os.path.basename(f)}")

    def delete_print(self, name):
        f = self._print_file(name); os.remove(f); self.log(f"Removido da fila: {os.path.basename(f)}")

    # ---- senha ----
    def has_pass(self): return os.path.exists(self.auth_path)

    def _hash(self, pw, salt): return hashlib.pbkdf2_hmac("sha256", pw.encode(), bytes.fromhex(salt), 200_000).hex()

    def set_pass(self, pw):
        salt = secrets.token_hex(16)
        json.dump(dict(salt=salt, hash=self._hash(pw, salt)), open(self.auth_path, "w"))

    def check_pass(self, pw):
        if not self.has_pass(): return False
        a = json.load(open(self.auth_path))
        return secrets.compare_digest(a["hash"], self._hash(pw, a["salt"]))

    def apply_settings(self, d):
        cur = asdict(self.s)
        for k, v in d.items():
            if k in cur and type(v) == type(cur[k]):
                setattr(self.s, k, v)
            elif k in cur and isinstance(cur[k], float) and isinstance(v, int):
                setattr(self.s, k, float(v))
        for k in ("hot_folder", "output_folder", "printed_folder", "done_folder", "error_folder"):
            os.makedirs(getattr(self.s, k), exist_ok=True)
        self.s.save(self.cfg_path)
        self.rip = Rip(self.s)
        self.auto = self.s.auto_mode
        self.log("Configuracoes salvas")


APP = None


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="application/json"):
        if not isinstance(body, (bytes, bytearray)): body = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)

    def _auth(self): return self.headers.get("X-Token", "") in APP.tokens

    def _json(self):
        n = int(self.headers.get("Content-Length", 0)); return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            return self._send(200, open(res_path("ui", "index.html"), "rb").read(), "text/html; charset=utf-8")
        if u.path == "/api/state":
            with APP.lock:
                return self._send(200, dict(version=__version__, auto=APP.auto, has_pass=APP.has_pass(),
                                            jobs=APP.jobs[-12:], log=APP.log_lines[-60:],
                                            hot_folder=APP.s.hot_folder, output_folder=APP.s.output_folder,
                                            icc=os.path.basename(APP.s.icc_path) or "(nenhum)", brand=APP.s.brand_name,
                                            offline=APP.s.offline_mode, pending=len(integrations.outbox_load(APP.home)),
                                            has_logo=bool(APP.s.brand_logo and os.path.exists(APP.s.brand_logo))))
        if u.path == "/api/prints":
            return self._send(200, APP.list_prints())
        if u.path == "/api/thumb":
            q = parse_qs(u.query); jid = os.path.basename(q.get("id", [""])[0]); nm = os.path.basename(q.get("name", [""])[0])
            f = os.path.join(APP.home, "thumbs", "by_name", nm + ".jpg") if nm else os.path.join(APP.home, "thumbs", jid + ".jpg")
            return self._send(200, open(f, "rb").read(), "image/jpeg") if os.path.exists(f) else self._send(404, {})
        if u.path == "/api/brand-logo":
            f = APP.s.brand_logo
            return self._send(200, open(f, "rb").read(), "image/png") if f and os.path.exists(f) else self._send(404, {})
        if u.path == "/api/settings":
            return self._send(200, asdict(APP.s)) if self._auth() else self._send(401, {"error": "login"})
        self._send(404, {"error": "nao encontrado"})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/auto":
                APP.auto = bool(self._json().get("on")); APP.log("Modo automatico " + ("LIGADO" if APP.auto else "desligado"))
                return self._send(200, {"auto": APP.auto})
            if u.path == "/api/upload":
                q = parse_qs(u.query); name = os.path.basename(q.get("name", ["arte.png"])[0])
                if not name.lower().endswith(EXTS): return self._send(400, {"error": "formato nao suportado"})
                n = int(self.headers.get("Content-Length", 0)); data = self.rfile.read(n)
                d = os.path.join(APP.inbox, str(int(time.time() * 1000))); os.makedirs(d, exist_ok=True)
                p = os.path.join(d, name)                      # mantem o nome original no .PRT
                open(p, "wb").write(data)
                w = float(q["width"][0]) if q.get("width") and q["width"][0] else None
                job = APP.enqueue(p, w, move_to_done=False)
                return self._send(200, job)
            if u.path == "/api/login":
                if APP.check_pass(self._json().get("password", "")):
                    t = secrets.token_hex(16); APP.tokens.add(t); return self._send(200, {"token": t})
                return self._send(401, {"error": "senha incorreta"})
            if u.path == "/api/setpass":
                d = self._json(); new = d.get("new", "")
                if len(new) < 4: return self._send(400, {"error": "minimo 4 caracteres"})
                if APP.has_pass() and not APP.check_pass(d.get("password", "")):
                    return self._send(401, {"error": "senha atual incorreta"})
                APP.set_pass(new); t = secrets.token_hex(16); APP.tokens.add(t); return self._send(200, {"token": t})
            if u.path == "/api/prints/printed":
                APP.mark_printed(self._json().get("name", "")); return self._send(200, {"ok": True})
            if u.path == "/api/prints/delete":
                if not self._auth(): return self._send(401, {"error": "login"})
                APP.delete_print(self._json().get("name", "")); return self._send(200, {"ok": True})
            if u.path == "/api/agent":
                if not self._auth(): return self._send(401, {"error": "login"})
                if APP.s.offline_mode: return self._send(400, {"error": "Modo offline ligado. Desligue em Configurações para usar o agente."})
                try:
                    txt = agent.ask(APP.s, APP.jobs, APP.log_lines, self._json().get("question") or None)
                    APP.log("Agente de IA: sugestoes geradas"); return self._send(200, {"text": txt})
                except Exception as e:
                    return self._send(502, {"error": str(e)})
            if u.path in ("/api/logo", "/api/watermark"):
                if not self._auth(): return self._send(401, {"error": "login"})
                n = int(self.headers.get("Content-Length", 0)); data = self.rfile.read(n)
                Image.open(__import__("io").BytesIO(data)).verify()                 # garante que e imagem
                bd = os.path.join(APP.home, "brand"); os.makedirs(bd, exist_ok=True)
                f = os.path.join(bd, "logo.png" if u.path == "/api/logo" else "watermark.png"); open(f, "wb").write(data)
                APP.apply_settings({"brand_logo" if u.path == "/api/logo" else "watermark_path": f})
                return self._send(200, {"ok": True})
            if u.path == "/api/settings":
                if not self._auth(): return self._send(401, {"error": "login"})
                APP.apply_settings(self._json()); return self._send(200, asdict(APP.s))
        except Exception as e:
            traceback.print_exc(); return self._send(500, {"error": str(e)})
        self._send(404, {"error": "nao encontrado"})


def serve(port=8765, open_browser=True):
    global APP
    APP = App()
    srv = None
    for p in range(port, port + 20):
        try: srv = ThreadingHTTPServer(("127.0.0.1", p), H); break
        except OSError: continue
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    print("AutoRIP em", url, flush=True)
    if open_browser: threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    srv.serve_forever()


def main():
    if sys.stdout is None:                                    # .exe sem console
        lf = open(os.path.join(home_dir(), "autorip.log"), "a", buffering=1)
        sys.stdout = sys.stderr = lf
    serve(open_browser=os.environ.get("AUTORIP_NOBROWSER") != "1")
