"""Agente de melhoria (opcional). Consulta a API da Anthropic com busca na web e devolve SUGESTOES em texto.
Nada e aplicado automaticamente; segredos nunca sao enviados."""
import json, urllib.request, dataclasses

SYSTEM = ("Voce e especialista em RIP e impressao digital DTF e DTF UV (cabecotes Epson i3200, placas Hosonsoft, "
          "software PrintExp, perfis ICC, branco/underbase, meio-tom estocastico). Pesquise na web praticas atuais de "
          "RIPs como Caldera, PrintFactory e FlexiPRINT e proponha melhorias CONCRETAS e priorizadas para o RIP do usuario. "
          "Responda em portugues, curto, com fontes (links) quando usar a web. Diga o que e fato e o que e suposicao.")
SECRET = ("key", "token", "password", "senha")


def safe_settings(s):
    return {k: v for k, v in dataclasses.asdict(s).items() if not any(w in k.lower() for w in SECRET)}


def ask(s, jobs, log_lines, question=None, timeout=120):
    if not s.anthropic_key:
        raise RuntimeError("configure a chave da API em Configuracoes > Agente de IA")
    ctx = {"configuracoes": safe_settings(s), "ultimos_trabalhos": [
        {k: j.get(k) for k in ("name", "status", "error")} for j in jobs[-10:]], "registro": log_lines[-25:]}
    q = question or "Pesquise na internet como aprimorar este RIP DTF e sugira as 5 melhorias de maior impacto."
    body = {"model": s.anthropic_model, "max_tokens": 1500, "system": SYSTEM,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
            "messages": [{"role": "user", "content": q + "\n\nContexto do meu RIP (JSON):\n" + json.dumps(ctx, ensure_ascii=False)}]}
    r = urllib.request.Request(s.anthropic_base.rstrip("/") + "/v1/messages", data=json.dumps(body).encode(), method="POST",
                               headers={"Content-Type": "application/json", "x-api-key": s.anthropic_key,
                                        "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return "\n".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
