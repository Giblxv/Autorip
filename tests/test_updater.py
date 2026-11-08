import hashlib
import sys

import pytest

from autorip import updater


def test_updater_restringe_hosts_de_download():
    assert updater._allowed_download_url("https://github.com/Giblxv/Autorip/releases/download/v1/AutoRIP_Setup.exe")
    assert updater._allowed_download_url("https://release-assets.githubusercontent.com/file")
    assert not updater._allowed_download_url("http://github.com/file")
    assert not updater._allowed_download_url("https://evil.example/file")
    assert not updater._allowed_download_url("https://github.com@evil.example/file")


def test_manifest_hash_exige_sha256_valido():
    raw = b"abc123  outro.exe\n" + b"a" * 64 + b"  AutoRIP_Setup.exe\n"
    assert updater._manifest_hash(raw, "AutoRIP_Setup.exe") == "a" * 64
    assert updater._manifest_hash(b"not-a-hash  AutoRIP_Setup.exe\n", "AutoRIP_Setup.exe") is None


def test_stage_nao_faz_rede_em_offline_ou_codigo_fonte(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert updater.stage_latest(str(tmp_path), "0.8.4", offline=True) is None
    assert updater.stage_latest(str(tmp_path), "0.8.4", offline=False) is None


def test_install_staged_rejeita_hash_incorreto(tmp_path, monkeypatch):
    path = tmp_path / "AutoRIP_Setup.exe"
    path.write_bytes(b"installer")
    calls = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *args, **kwargs: calls.append(args))
    state = {"pending": str(path), "sha256": hashlib.sha256(b"outro").hexdigest()}
    assert updater.install_staged(state) is False
    assert calls == []


def test_stage_registra_falha_de_rede_sem_lancar_erro_secundario(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater, "_latest_release", lambda: (_ for _ in ()).throw(OSError("sem rede")))
    assert updater.stage_latest(str(tmp_path), "0.8.5", force=True) is None
    assert (tmp_path / "update_state.json").is_file()


def test_install_staged_executa_somente_hash_conferente(tmp_path, monkeypatch):
    path = tmp_path / "AutoRIP_Setup.exe"
    path.write_bytes(b"installer")
    calls = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    state = {"pending": str(path), "sha256": hashlib.sha256(b"installer").hexdigest()}
    assert updater.install_staged(state) is True
    assert calls and calls[0][0][0] == [str(path), "/VERYSILENT", "/NORESTART"]


@pytest.mark.parametrize("previous", [[], None, "invalido", 42,
    {"checked_at": 10**400}, {"checked_at": 2000}])
def test_cache_invalido_ou_futuro_nao_bloqueia_consulta(tmp_path, monkeypatch, previous):
    import json
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.time, "time", lambda: 1000)
    (tmp_path / "update_state.json").write_text(json.dumps(previous))
    calls = []

    def latest():
        calls.append(True)
        return None

    monkeypatch.setattr(updater, "_latest_release", latest)
    assert updater.stage_latest(str(tmp_path), "0.8.4") is None
    assert calls == [True]
    assert json.loads((tmp_path / "update_state.json").read_text())["checked_at"] == 1000


def test_cache_recente_valido_mantem_intervalo_de_consultas(tmp_path, monkeypatch):
    import json
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater.time, "time", lambda: 1000)
    (tmp_path / "update_state.json").write_text(json.dumps({"checked_at": 990}))

    def forbidden():
        pytest.fail("Cache recente nao deve disparar consulta de rede")

    monkeypatch.setattr(updater, "_latest_release", forbidden)
    assert updater.stage_latest(str(tmp_path), "0.8.4") is None


@pytest.mark.parametrize("tag", ["0.8.7", "v1.2.3", "v1.2.3-rc.1", "1.2.3+build.4"])
def test_tag_semver_segura_e_aceita(tag):
    assert updater._safe_release_tag(tag)


@pytest.mark.parametrize("tag", [
    "../v1.2.3", "v1.2.3/path", r"v1.2.3\\..\\evil", "v1.2.3\x00",
    "v1.2.3/../../install", "v1.2.3" + "a" * 100, "v1.2.3 ext", "",
])
def test_tag_de_release_insegura_e_rejeitada(tag):
    assert not updater._safe_release_tag(tag)


def test_stage_nao_baixa_release_com_tag_insegura(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater, "_latest_release", lambda: {
        "tag": "v999.0.0/caminho", "version": (999, 0, 0),
        "installer_url": "https://github.com/file", "manifest_url": "https://github.com/manifest",
    })
    def forbidden(*args, **kwargs):
        pytest.fail("Release com tag insegura nao pode baixar arquivos")
    monkeypatch.setattr(updater, "_download", forbidden)
    assert updater.stage_latest(str(tmp_path), "0.8.7", force=True) is None
    assert not (tmp_path / "updates").exists()

@pytest.mark.parametrize("url", [
    "https://github.com/Giblxv/Outro/releases/download/v0.8.7/AutoRIP_Setup.exe",
    "https://github.com/atacante/repo/releases/download/v0.8.7/AutoRIP_Setup.exe",
    "https://github.com/Giblxv/Autorip/releases/download/v0.8.6/AutoRIP_Setup.exe",
    "https://github.com/Giblxv/Autorip/releases/download/v0.8.7/SHA256SUMS.txt",
    "https://release-assets.githubusercontent.com/download/AutoRIP_Setup.exe",
    "https://github.com/Giblxv/Autorip/releases/download/v0.8.7/AutoRIP_Setup.exe?token=1",
    "https://github.com:444/Giblxv/Autorip/releases/download/v0.8.7/AutoRIP_Setup.exe",
])
def test_release_nao_aceita_assets_de_outro_repositorio(url):
    assert not updater._release_asset_url(url, "v0.8.7", "AutoRIP_Setup.exe")


def test_release_aceita_asset_do_proprio_repositorio():
    tag = "v0.8.7"
    assert updater._release_asset_url(
        f"https://github.com/Giblxv/Autorip/releases/download/{tag}/AutoRIP_Setup.exe",
        tag, "AutoRIP_Setup.exe")
    assert updater._release_asset_url(
        f"https://github.com/Giblxv/Autorip/releases/download/{tag}/SHA256SUMS.txt",
        tag, "SHA256SUMS.txt")


def test_api_de_release_nao_aceita_instalador_de_outro_repositorio(monkeypatch):
    import io
    import json

    release = {
        "tag_name": "v0.8.7",
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": "AutoRIP_Setup.exe", "browser_download_url":
             "https://github.com/atacante/repo/releases/download/v0.8.7/AutoRIP_Setup.exe"},
            {"name": "SHA256SUMS.txt", "browser_download_url":
             "https://github.com/Giblxv/Autorip/releases/download/v0.8.7/SHA256SUMS.txt"},
        ],
    }

    class FakeResponse(io.BytesIO):
        headers = {}

    class FakeOpener:
        def open(self, request, timeout):
            return FakeResponse(json.dumps(release).encode())

    monkeypatch.setattr(updater.urllib.request, "build_opener", lambda *_args: FakeOpener())
    assert updater._latest_release() is None

def test_stage_falha_de_rede_preserva_aplicacao_e_registra_erro(tmp_path, monkeypatch):
    import json
    import urllib.error
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    def unavailable():
        raise urllib.error.URLError("rede indisponivel")

    monkeypatch.setattr(updater, "_latest_release", unavailable)
    logs = []
    assert updater.stage_latest(str(tmp_path), "0.8.4", log=logs.append) is None
    state = json.loads((tmp_path / "update_state.json").read_text())
    assert state["error"] == "URLError"
    assert any("indisponível" in line for line in logs)
    assert not (tmp_path / "updates").exists()


@pytest.mark.parametrize("failure", ["manifest", "installer"])
def test_stage_remove_download_parcial_apos_falha(tmp_path, monkeypatch, failure):
    from pathlib import Path
    import urllib.error
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(updater, "_latest_release", lambda: {
        "tag": "v1.0.0", "version": (1, 0, 0),
        "manifest_url": "manifest", "installer_url": "installer"})

    def download(url, path, limit):
        if url == failure:
            Path(path).write_bytes(b"download interrompido")
            raise urllib.error.URLError("interrompido")
        Path(path).write_bytes(b"a" * 64 + b"  AutoRIP_Setup.exe\n")

    monkeypatch.setattr(updater, "_download", download)
    assert updater.stage_latest(str(tmp_path), "0.8.4") is None
    assert list((tmp_path / "updates").iterdir()) == []
