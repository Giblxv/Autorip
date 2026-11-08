import hashlib
import sys

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


def test_install_staged_executa_somente_hash_conferente(tmp_path, monkeypatch):
    path = tmp_path / "AutoRIP_Setup.exe"
    path.write_bytes(b"installer")
    calls = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)))
    state = {"pending": str(path), "sha256": hashlib.sha256(b"installer").hexdigest()}
    assert updater.install_staged(state) is True
    assert calls and calls[0][0][0] == [str(path), "/VERYSILENT", "/NORESTART"]
