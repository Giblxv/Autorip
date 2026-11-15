import io
import json
import urllib.error
from types import SimpleNamespace

import pytest

from autorip import agent, ai_accounts
from autorip.config import Settings


def accounts(provider="deepseek", count=1):
    return ai_accounts.normalize([{"provider": provider, "key": f"private-key-{index}"} for index in range(count)])


class Opener:
    def __init__(self, response):
        self.response = response
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = io.BytesIO(json.dumps(self.response).encode())
        response.headers = {}
        return response


def test_contas_repetidas_sem_teto_redacao_e_preservacao_de_chaves():
    saved = accounts(count=137)
    public = ai_accounts.public(saved)
    assert len(public) == 137
    assert all(row["key"] == "" and row["has_key"] for row in public)
    assert "private-key" not in json.dumps(public)
    public[0]["label"] = "Outra conta"
    merged = ai_accounts.merge(public, saved)
    assert [row["key"] for row in merged] == [row["key"] for row in saved]
    assert merged[0]["label"] == "Outra conta"
    assert len(ai_accounts.merge(public[1:], saved)) == 136
    settings = Settings(ai_accounts=merged)
    settings.validate()
    assert ai_accounts.summary(settings)[0]["keys"] == 137


def test_chaves_ativas_do_mesmo_provedor_se_alternam_sem_usar_contas_desativadas():
    saved = accounts(count=3) + accounts("gemini")
    saved[1]["enabled"] = False
    picked = [ai_accounts.select(saved, "deepseek")["key"] for _ in range(6)]
    assert set(picked) == {saved[0]["key"], saved[2]["key"]}
    assert all(left != right for left, right in zip(picked, picked[1:]))
    assert ai_accounts.select(saved, "gemini")["id"] == saved[3]["id"]


def test_trocar_provedor_exige_chave_nova_sem_reutilizar_segredo_errado():
    saved = accounts()
    edited = ai_accounts.public(saved)
    edited[0]["provider"] = "gemini"
    with pytest.raises(ValueError, match="nova chave"):
        ai_accounts.merge(edited, saved)
    edited[0]["key"] = "new-private-key"
    assert ai_accounts.merge(edited, saved)[0]["key"] == "new-private-key"
    assert saved[0]["provider"] == "deepseek"


@pytest.mark.parametrize("change", [{"provider": []}, {"key": "secret\nvalue"}, {"key": "segredo-ç"},
                                      {"enabled": "true"}, {"id": {}}, {"key": ""}])
def test_entrada_invalida_nao_reflete_segredos(change):
    row = {"provider": "deepseek", "key": "private-key", **change}
    with pytest.raises(ValueError) as error:
        ai_accounts.normalize([row])
    assert "secret" not in str(error.value) and "segredo" not in str(error.value)


@pytest.mark.parametrize("provider", ["openai", "deepseek", "grok", "perplexity", "openrouter"])
def test_protocolos_chat_usam_endpoint_fixo_e_chave_so_no_header(provider):
    account = accounts(provider)[0]
    opener = Opener({"choices": [{"message": {"content": "Análise técnica"}}]})
    assert ai_accounts.ask(account, "system", "prompt", 10, opener) == "Análise técnica"
    request = opener.requests[0]
    assert request.full_url == ai_accounts.PROVIDERS[provider][2]
    assert request.get_header("Authorization") == "Bearer " + account["key"]
    assert account["key"] not in request.data.decode()


def test_gemini_envia_chave_por_header_e_modelo_na_rota_oficial():
    account = accounts("gemini")[0]
    opener = Opener({"candidates": [{"content": {"parts": [{"text": "A"}, {"text": "B"}]}}]})
    assert ai_accounts.ask(account, "system", "prompt", 10, opener) == "A\nB"
    request = opener.requests[0]
    assert request.full_url.endswith("gemini-2.5-flash:generateContent")
    assert request.get_header("X-goog-api-key") == account["key"]
    assert "key=" not in request.full_url and account["key"] not in request.data.decode()


def test_manus_cria_tarefa_privada_assincrona_sem_afirmar_resultado_pronto():
    opener = Opener({"ok": True, "task_url": "https://manus.im/app/task-123"})
    account = accounts("manus")[0]
    result = ai_accounts.ask(account, "Somente sugira", "Analisar RIP", 10, opener)
    request = opener.requests[0]
    assert request.full_url == "https://api.manus.ai/v2/task.create"
    assert request.get_header("X-manus-api-key") == account["key"]
    body = json.loads(request.data)
    assert body["share_visibility"] == "private"
    assert body["message"]["content"] == "Somente sugira\n\nAnalisar RIP"
    assert "assíncrona" in result and "https://manus.im/app/task-123" in result


@pytest.mark.parametrize("url", ["http://manus.im/app/x", "https://evil.example/x", "https://secret@manus.im/x"])
def test_manus_rejeita_endereco_de_tarefa_inseguro(url):
    with pytest.raises(RuntimeError, match="não confirmou"):
        ai_accounts.ask(accounts("manus")[0], "s", "p", 10, Opener({"ok": True, "task_url": url}))


def test_agente_multiplos_provedores_envia_so_contexto_tecnico(monkeypatch):
    opener = Opener({"choices": [{"message": {"content": "Sugestão"}}]})
    monkeypatch.setattr(agent.urllib.request, "build_opener", lambda *args: opener)
    settings = Settings(offline_mode=False, ai_accounts=accounts(count=137), trello_token="trello-secret",
                        hot_folder="/cliente/arquivos-confidenciais")
    assert agent.ask(settings, [{"name": "cliente-secreto.png", "status": "pronto"}],
                     ["evento com senha=privada"], provider="deepseek") == "Sugestão"
    payload = opener.requests[0].data.decode()
    for private in ("private-key", "trello-secret", "cliente-secreto", "arquivos-confidenciais", "senha=privada"):
        assert private not in payload
    settings.offline_mode = True
    with pytest.raises(RuntimeError, match="offline"):
        agent.ask(settings, [], [], provider="deepseek")
    assert len(opener.requests) == 1


def test_erros_http_nao_repassam_corpo_do_provedor_ou_chaves():
    def fail(*args, **kwargs):
        raise urllib.error.HTTPError("https://api.deepseek.com", 401, "private-key", {}, io.BytesIO(b"private-key"))
    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        ai_accounts.ask(accounts()[0], "s", "p", 10, SimpleNamespace(open=fail))
    assert "private-key" not in str(error.value)


def test_chave_anthropic_anterior_tambem_participa_da_rotacao(monkeypatch):
    opener = Opener({"content": [{"type": "text", "text": "Sugestão"}]})
    monkeypatch.setattr(agent.urllib.request, "build_opener", lambda *args: opener)
    settings = Settings(offline_mode=False, anthropic_key="legacy-private-key", ai_accounts=accounts("anthropic", 2))
    for _ in range(6):
        assert agent.ask(settings, [], [], provider="anthropic") == "Sugestão"
    keys = [request.get_header("X-api-key") for request in opener.requests]
    assert set(keys) == {"legacy-private-key", "private-key-0", "private-key-1"}
    assert all(keys.count(key) == 2 for key in set(keys))
    assert ai_accounts.summary(settings)[0]["keys"] == 3
