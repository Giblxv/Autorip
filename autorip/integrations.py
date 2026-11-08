"""Integracoes de pedidos: Trello (entrada e saida), Notion, Jira e webhook generico. So biblioteca padrao."""
import os, json, base64, urllib.request, urllib.parse, urllib.error

IMG = (".png", ".tif", ".tiff", ".jpg", ".jpeg")


def _req(url, data=None, headers=None, method=None, timeout=20):
    h = {"User-Agent": "AutoRIP/0.3"}; h.update(headers or {})
    body = None
    if data is not None:
        body = json.dumps(data).encode(); h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method=method or ("POST" if body is not None else "GET"))
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read()
        return json.loads(raw) if raw[:1] in (b"{", b"[") else raw


def _trello(s, path, **q):
    q.update(key=s.trello_key, token=s.trello_token)
    return f"{s.trello_base}{path}?{urllib.parse.urlencode(q)}"


def notify_done(s, job, info, log=print):
    """Chamado quando um .PRT fica pronto. Cada servico configurado e tentado de forma independente."""
    title = f"RIP pronto: {job['name']}"
    desc = f"{info.get('width_cm', 0):.2f} x {info.get('height_cm', 0):.2f} cm\nSaida: {job.get('out', '')}"
    if s.webhook_url:
        _try(log, "webhook", lambda: _req(s.webhook_url, dict(event="rip_done", name=job["name"], out=job.get("out"), **info)))
    if s.trello_key and s.trello_token and s.trello_out_list:
        _try(log, "Trello", lambda: _req(_trello(s, "/cards", idList=s.trello_out_list, name=title, desc=desc), method="POST"))
    if s.notion_token and s.notion_db:
        body = {"parent": {"database_id": s.notion_db},
                "properties": {"Name": {"title": [{"text": {"content": title}}]}},
                "children": [{"object": "block", "type": "paragraph",
                              "paragraph": {"rich_text": [{"type": "text", "text": {"content": desc}}]}}]}
        _try(log, "Notion", lambda: _req(f"{s.notion_base}/pages", body, {
            "Authorization": f"Bearer {s.notion_token}", "Notion-Version": "2022-06-28"}))
    if s.jira_url and s.jira_email and s.jira_token and s.jira_project:
        auth = base64.b64encode(f"{s.jira_email}:{s.jira_token}".encode()).decode()
        body = {"fields": {"project": {"key": s.jira_project}, "summary": title, "issuetype": {"name": "Task"},
                           "description": {"type": "doc", "version": 1, "content": [
                               {"type": "paragraph", "content": [{"type": "text", "text": desc}]}]}}}
        _try(log, "Jira", lambda: _req(f"{s.jira_url.rstrip('/')}/rest/api/3/issue", body, {"Authorization": f"Basic {auth}"}))


def _try(log, name, fn):
    try:
        fn(); log(f"Integracao {name}: enviado")
    except Exception as e:
        log(f"Integracao {name}: falhou ({e})")


def pull_trello(s, seen: set, log=print):
    """Baixa para a hot folder os anexos de imagem dos cartoes da lista de entrada (uma vez por anexo)."""
    if not (s.trello_key and s.trello_token and s.trello_in_list):
        return 0
    n = 0
    cards = _req(_trello(s, f"/lists/{s.trello_in_list}/cards", attachments="true", attachment_fields="name,url,id"))
    for card in cards:
        for att in card.get("attachments", []):
            name = att.get("name", "")
            if not name.lower().endswith(IMG) or att["id"] in seen:
                continue
            seen.add(att["id"])
            dst = os.path.join(s.hot_folder, os.path.basename(name))
            url = att["url"]
            hdr = {"Authorization": f'OAuth oauth_consumer_key="{s.trello_key}", oauth_token="{s.trello_token}"'} \
                if "trello.com" in url else {}
            data = _req(urllib.request.Request(url, headers=hdr).full_url, headers=hdr, timeout=120)
            if isinstance(data, (bytes, bytearray)):
                with open(dst + ".part", "wb") as f: f.write(data)
                os.replace(dst + ".part", dst); n += 1
                log(f"Trello: baixado {name} (cartao {card.get('name', '')})")
    return n


# ---------------- modo offline: fila de avisos (outbox) ----------------
def _outbox_path(home): return os.path.join(home, "outbox.json")


def outbox_load(home):
    try:
        with open(_outbox_path(home), encoding="utf-8") as f: return json.load(f)
    except Exception:
        return []


def outbox_add(home, job, info):
    items = outbox_load(home)
    items.append(dict(job={k: job.get(k) for k in ("name", "out")}, info=info))
    with open(_outbox_path(home), "w", encoding="utf-8") as f: json.dump(items, f, ensure_ascii=False)


def outbox_flush(s, home, log=print):
    """Envia os avisos guardados enquanto estava offline (chame apenas quando offline_mode estiver desligado)."""
    items = outbox_load(home)
    if not items: return 0
    for it in items: notify_done(s, it["job"], it["info"], log)
    with open(_outbox_path(home), "w", encoding="utf-8") as f: json.dump([], f)
    log(f"Fila offline: {len(items)} aviso(s) enviado(s)")
    return len(items)
