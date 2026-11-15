"""Contas de IA sem teto de quantidade; segredos não voltam ao navegador."""
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid

PROVIDERS = {
    "anthropic": ("Claude / Anthropic", "claude-sonnet-4-6", "https://api.anthropic.com"),
    "openai": ("ChatGPT / OpenAI", "gpt-4.1-mini", "https://api.openai.com/v1/chat/completions"),
    "gemini": ("Gemini / Google", "gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/models/"),
    "deepseek": ("DeepSeek", "deepseek-chat", "https://api.deepseek.com/chat/completions"),
    "manus": ("Manus", "standard", "https://api.manus.ai/v2/task.create"),
    "grok": ("Grok / xAI", "grok-3-mini", "https://api.x.ai/v1/chat/completions"),
    "perplexity": ("Perplexity", "sonar", "https://api.perplexity.ai/chat/completions"),
    "openrouter": ("OpenRouter", "openai/gpt-4.1-mini", "https://openrouter.ai/api/v1/chat/completions"),
}
_rotation = {}
_lock = threading.Lock()
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def normalize(accounts):
    if not isinstance(accounts, list):
        raise ValueError("As contas de IA precisam ser uma lista.")
    result, ids = [], set()
    for value in accounts:
        if not isinstance(value, dict) or not isinstance(value.get("provider"), str) or value["provider"] not in PROVIDERS:
            raise ValueError("Escolha um provedor de IA válido.")
        provider = value["provider"]
        identifier, model = value.get("id"), value.get("model")
        item = {"id": uuid.uuid4().hex if identifier is None or identifier == "" else identifier, "provider": provider,
                "label": value.get("label", ""), "model": PROVIDERS[provider][1] if model is None or model == "" else model,
                "key": value.get("key", ""), "enabled": value.get("enabled", True)}
        for name in ("id", "label", "model", "key"):
            if not isinstance(item[name], str) or any(char in item[name] for char in ("\x00", "\r", "\n")):
                raise ValueError("Os campos da conta de IA precisam ser textos válidos de uma linha.")
            item[name] = item[name].strip()
        if not item["id"] or item["id"] in ids:
            raise ValueError("Cada conta de IA precisa de um identificador único.")
        if type(item["enabled"]) is not bool:
            raise ValueError("O estado da conta de IA precisa ser booleano.")
        if item["enabled"] and not item["key"]:
            raise ValueError("Preencha a chave de API ou desative a conta de IA.")
        if not item["key"].isascii():
            raise ValueError("A chave de API precisa conter apenas caracteres ASCII.")
        ids.add(item["id"]); result.append(item)
    return result


def merge(submitted, saved):
    if not isinstance(submitted, list):
        raise ValueError("As contas de IA precisam ser uma lista.")
    previous = {item["id"]: item for item in saved}
    result = []
    for row in submitted:
        if not isinstance(row, dict):
            raise ValueError("Conta de IA inválida.")
        item = dict(row)
        identifier = item.get("id")
        if identifier is not None and not isinstance(identifier, str):
            raise ValueError("O identificador da conta de IA precisa ser texto.")
        existing = previous.get(identifier)
        if existing and not item.get("key"):
            if item.get("provider") != existing["provider"]:
                raise ValueError("Informe uma nova chave ao trocar o provedor da conta.")
            item["key"] = existing["key"]
        result.append(item)
    return normalize(result)


def public(accounts):
    return [dict(item, key="", has_key=bool(item["key"])) for item in accounts]


def catalog():
    return [dict(id=key, name=values[0], model=values[1], asynchronous=key=="manus")
            for key, values in PROVIDERS.items()]


def summary(settings):
    counts = dict.fromkeys(PROVIDERS, 0)
    for item in settings.ai_accounts:
        if item["enabled"] and item["key"]:
            counts[item["provider"]] += 1
    if settings.anthropic_key:
        counts["anthropic"] += 1
    return [dict(id=key, name=PROVIDERS[key][0], keys=count) for key,count in counts.items() if count]


def select(accounts, provider=None):
    if provider is not None and not isinstance(provider, str):
        raise ValueError("Provedor de IA inválido.")
    if provider in (None, "", "auto"):
        provider = next((item["provider"] for item in accounts if item["enabled"] and item["key"]), None)
    elif provider not in PROVIDERS:
        raise ValueError("Provedor de IA inválido.")
    candidates = [item for item in accounts if item["provider"]==provider and item["enabled"] and item["key"]]
    if not candidates:
        return None
    with _lock:
        position = _rotation.get(provider, 0)
        _rotation[provider] = position + 1
    return candidates[position % len(candidates)]


def request_json(url, body, headers, timeout, opener):
    request = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type":"application/json", **headers})
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(MAX_RESPONSE_BYTES+1)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"O provedor recusou a consulta (HTTP {exc.code}). Confira chave, modelo e cota.") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("Não foi possível conectar ao provedor de IA.") from None
    if len(raw)>MAX_RESPONSE_BYTES:
        raise ValueError("Resposta da API acima do limite de 4 MiB.")
    try:
        data=json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError("O provedor retornou uma resposta inválida.") from None
    if not isinstance(data, dict):
        raise ValueError("O provedor retornou uma resposta inválida.")
    return data


def ask(account, system, prompt, timeout, opener):
    provider, key, model = account["provider"], account["key"], account["model"]
    endpoint=PROVIDERS[provider][2]
    if provider=="manus":
        data=request_json(endpoint,{"message":{"content":system+"\n\n"+prompt},
                          "agent_profile":model,"share_visibility":"private","locale":"pt-BR"},
                          {"x-manus-api-key":key},timeout,opener)
        url=data.get("task_url", "")
        parsed=urllib.parse.urlsplit(url) if isinstance(url,str) else None
        if not data.get("ok") or not parsed or parsed.scheme!="https" or parsed.hostname not in ("manus.im","manus.ai") or parsed.username or parsed.password:
            raise RuntimeError("O Manus não confirmou a criação da tarefa.")
        return "Pesquisa criada no Manus. A tarefa é assíncrona; acompanhe o resultado na sua conta:\n"+url
    if provider=="gemini":
        url=endpoint+urllib.parse.quote(model.removeprefix("models/"),safe="")+":generateContent"
        data=request_json(url,{"systemInstruction":{"parts":[{"text":system}]},
             "contents":[{"role":"user","parts":[{"text":prompt}]}],
             "generationConfig":{"maxOutputTokens":2048}}, {"x-goog-api-key":key},timeout,opener)
        candidates=data.get("candidates") or []
        text="\n".join(part.get("text","") for part in candidates[0].get("content",{}).get("parts",[])) if candidates else ""
    else:
        data=request_json(endpoint,{"model":model,"max_tokens":1500,
             "messages":[{"role":"system","content":system},{"role":"user","content":prompt}]},
             {"Authorization":"Bearer "+key},timeout,opener)
        choices=data.get("choices") or []
        text=choices[0].get("message",{}).get("content","") if choices else ""
        if isinstance(text,list):text="\n".join(part.get("text","") for part in text if isinstance(part,dict))
    if not isinstance(text,str) or not text.strip():
        raise RuntimeError("O provedor não retornou texto. Confira o modelo selecionado.")
    return text.strip()
