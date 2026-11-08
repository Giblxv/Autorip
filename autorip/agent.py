"""Agente opcional de melhoria. Pesquisa e sugere; nunca altera configuracoes."""
import ipaddress
import json
import urllib.parse
import urllib.request
import dataclasses

SYSTEM = ("Voce e especialista em RIP e impressao digital DTF e DTF UV (cabecotes Epson i3200, placas Hosonsoft, "
          "software PrintExp, perfis ICC, branco/underbase, meio-tom estocastico). Pesquise na web praticas atuais de "
          "RIPs profissionais e proponha melhorias concretas e priorizadas para o RIP do usuario. "
          "Responda em portugues, separando fatos de hipoteses e incluindo fontes verificaveis.")

_TECHNICAL_FIELDS = (
    "intent", "black_point_comp", "channel_order", "dpi_x", "dpi_y", "mirror",
    "margin_top_in", "margin_bottom_in", "ink_limit", "white_enabled",
    "white_alpha_threshold", "white_choke_mm", "small_drop_ratio", "white_density",
    "white_fill_holes_mm", "white_planes", "label_enabled",
)
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


def safe_settings(s):
    """Lista de permissao: nao envia chaves, URLs de integracao nem caminhos locais."""
    values = dataclasses.asdict(s)
    result = {key: values[key] for key in _TECHNICAL_FIELDS}
    result["icc_profile_configured"] = bool(s.icc_path)
    return result


def _allowed_base(base):
    parsed = urllib.parse.urlsplit(base)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return False
    if parsed.scheme == "https":
        return host == "api.anthropic.com" or host.endswith(".anthropic.com")
    if parsed.scheme == "http":
        if host == "localhost":
            return True
        try:
            return ipaddress.ip_address(host).is_loopback
        except ValueError:
            return False
    return False


def ask(s, jobs, log_lines, question=None, timeout=120, offline_check=None):
    if s.offline_mode or (offline_check and offline_check()):
        raise RuntimeError("Modo offline ligado; nenhuma chamada externa foi iniciada.")
    if not s.anthropic_key:
        raise RuntimeError("Configure a chave da API em Configuracoes > Agente de IA.")
    if not _allowed_base(s.anthropic_base):
        raise RuntimeError("Base Anthropic nao autorizada: use api.anthropic.com em HTTPS.")
    if question is not None and (not isinstance(question, str) or len(question) > 4000):
        raise ValueError("A pergunta precisa ter ate 4.000 caracteres.")

    context = {
        "configuracoes_tecnicas": safe_settings(s),
        "ultimos_trabalhos": [{"status": str(job.get("status", ""))[:30],
                               "teve_erro": bool(job.get("error"))} for job in jobs[-10:]],
        "quantidade_de_eventos_recentes": min(len(log_lines), 25),
    }
    prompt = question or "Pesquise como aprimorar este RIP DTF e sugira as cinco melhorias de maior impacto."
    body = {"model": s.anthropic_model, "max_tokens": 1500, "system": SYSTEM,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}],
            "messages": [{"role": "user", "content": prompt + "\n\nContexto tecnico (JSON):\n" + json.dumps(context, ensure_ascii=False)}]}
    if s.offline_mode or (offline_check and offline_check()):
        raise RuntimeError("Modo offline ativado antes da chamada; nenhuma requisicao foi enviada.")
    request = urllib.request.Request(
        s.anthropic_base.rstrip("/") + "/v1/messages",
        data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": s.anthropic_key,
                 "anthropic-version": "2023-06-01"})
    opener = urllib.request.build_opener(_NoRedirect())
    with opener.open(request, timeout=timeout) as response:
        length = response.headers.get("Content-Length")
        if length and length.isdigit() and int(length) > MAX_RESPONSE_BYTES:
            raise ValueError("Resposta da API acima do limite de 4 MiB.")
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("Resposta da API acima do limite de 4 MiB.")
    data = json.loads(raw)
    return "\n".join(block.get("text", "") for block in data.get("content", [])
                     if block.get("type") == "text").strip()
