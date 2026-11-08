"""Atualizador opcional do AutoRIP baseado em releases do GitHub.

O atualizador só aceita a API/release do repositório configurado, baixa o
instalador e confirma seu SHA-256 antes de executá-lo. Em código-fonte ou modo
offline ele não faz chamadas externas.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

REPOSITORY = "Giblxv/Autorip"
API_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_JSON_BYTES = 2 * 1024 * 1024
MAX_INSTALLER_BYTES = 100 * 1024 * 1024
CHECK_INTERVAL_SECONDS = 24 * 60 * 60
_ALLOWED_DOWNLOAD_HOSTS = {
    "github.com", "objects.githubusercontent.com", "github-releases.githubusercontent.com",
    "release-assets.githubusercontent.com",
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        return None


class _SafeReleaseRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, newurl):
        if not _allowed_download_url(newurl):
            return None
        return super().redirect_request(request, response, code, message, headers, newurl)


def _version(value):
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", str(value or "").strip())
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def _safe_release_tag(tag):
    """Release tag SemVer curta; nunca permite separadores de caminho."""
    return (type(tag) is str and len(tag) <= 80
            and re.fullmatch(r"v?\d{1,6}\.\d{1,6}\.\d{1,6}(?:[-+][A-Za-z0-9][A-Za-z0-9.+-]*)?", tag) is not None)


def _allowed_download_url(url):
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme == "https" and not parsed.username and not parsed.password
            and (parsed.hostname or "").lower().rstrip(".") in _ALLOWED_DOWNLOAD_HOSTS)


def _release_asset_url(url, tag, filename):
    """A API deve apontar para artefatos publicados no proprio repositorio.

    CDNs autorizados continuam validos apenas como redirects de _download().
    """
    if (type(url) is not str or type(tag) is not str
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,79}", tag)):
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
        return (parsed.scheme == "https" and parsed.hostname == "github.com"
                and parsed.port is None and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment
                and parsed.path == f"/{REPOSITORY}/releases/download/{tag}/{filename}")
    except ValueError:
        return False


def _read_limited(response, limit):
    length = response.headers.get("Content-Length")
    if length and length.isdigit() and int(length) > limit:
        raise ValueError("Resposta de atualização acima do limite permitido.")
    raw = response.read(limit + 1)
    if len(raw) > limit:
        raise ValueError("Resposta de atualização acima do limite permitido.")
    return raw


def _latest_release(timeout=15):
    request = urllib.request.Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "AutoRIP-updater/0.8",
    })
    opener = urllib.request.build_opener(_NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            data = json.loads(_read_limited(response, MAX_JSON_BYTES))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name")
    assets = data.get("assets")
    if not _safe_release_tag(tag) or not isinstance(assets, list):
        return None
    by_name = {asset.get("name"): asset for asset in assets if isinstance(asset, dict)}
    installer = by_name.get("AutoRIP_Setup.exe")
    manifest = by_name.get("SHA256SUMS.txt")
    if not isinstance(installer, dict) or not isinstance(manifest, dict):
        return None
    installer_url = installer.get("browser_download_url")
    manifest_url = manifest.get("browser_download_url")
    if not (_release_asset_url(installer_url, tag, "AutoRIP_Setup.exe")
            and _release_asset_url(manifest_url, tag, "SHA256SUMS.txt")):
        return None
    return {"tag": tag, "version": _version(tag), "installer_url": installer_url,
            "manifest_url": manifest_url, "published_at": data.get("published_at", "")}


def _download(url, path, limit, timeout=120):
    if not _allowed_download_url(url):
        raise ValueError("URL de atualização fora da allowlist do GitHub.")
    request = urllib.request.Request(url, headers={"User-Agent": "AutoRIP-updater/0.8"})
    opener = urllib.request.build_opener(_SafeReleaseRedirect())
    total = 0
    with opener.open(request, timeout=timeout) as response, open(path, "wb") as target:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise ValueError("Arquivo de atualização acima do limite permitido.")
            target.write(chunk)
        target.flush()
        os.fsync(target.fileno())
    if total <= 0:
        raise ValueError("Arquivo de atualização vazio.")
    return total


def _manifest_hash(raw, filename):
    for line in raw.decode("utf-8", "strict").splitlines():
        fields = line.strip().split()
        if len(fields) >= 2 and fields[-1].replace("\\", "/").rsplit("/", 1)[-1] == filename:
            digest = fields[0].lower()
            if re.fullmatch(r"[0-9a-f]{64}", digest):
                return digest
    return None


def _state_path(home):
    return os.path.join(home, "update_state.json")


def _write_state(home, value):
    os.makedirs(home, mode=0o700, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".update.", suffix=".tmp", dir=home)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as target:
            json.dump(value, target, ensure_ascii=False)
            target.flush(); os.fsync(target.fileno())
        os.replace(temporary, _state_path(home))
    except BaseException:
        try: os.close(fd)
        except OSError: pass
        try: os.remove(temporary)
        except OSError: pass
        raise


def stage_latest(home, current_version, *, offline=False, force=False, log=lambda _message: None):
    """Baixa e prepara o instalador; retorna estado ou None. Nunca executa sozinho."""
    if offline or not getattr(__import__("sys"), "frozen", False):
        return None
    state_file = _state_path(home)
    if not force:
        try:
            with open(state_file, encoding="utf-8") as source:
                previous = json.load(source)
            if isinstance(previous, dict) and "checked_at" in previous:
                age = time.time() - float(previous["checked_at"])
                if 0 <= age < CHECK_INTERVAL_SECONDS:
                    return None
        except (OSError, ValueError, TypeError, OverflowError):
            pass
    checked = {"checked_at": time.time(), "current": str(current_version)}
    manifest_path = installer_path = None
    try:
        release = _latest_release()
        if not release:
            _write_state(home, checked)
            return None
        if not _safe_release_tag(release.get("tag")):
            raise ValueError("Tag de atualização inválida ou insegura.")
        if release["version"] <= _version(current_version):
            _write_state(home, checked)
            return None
        update_dir = os.path.join(home, "updates")
        os.makedirs(update_dir, mode=0o700, exist_ok=True)
        manifest_path = os.path.join(update_dir, ".SHA256SUMS.txt.part")
        installer_path = os.path.join(update_dir, ".AutoRIP_Setup.exe.part")
        _download(release["manifest_url"], manifest_path, MAX_JSON_BYTES)
        expected = _manifest_hash(open(manifest_path, "rb").read(), "AutoRIP_Setup.exe")
        if not expected:
            raise ValueError("Manifesto da release não contém hash do instalador.")
        _download(release["installer_url"], installer_path, MAX_INSTALLER_BYTES)
        digest = hashlib.sha256()
        with open(installer_path, "rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        if digest.hexdigest() != expected:
            raise ValueError("SHA-256 do instalador não confere com o manifesto.")
        final_path = os.path.join(update_dir, f"AutoRIP_Setup-{release['tag']}.exe")
        os.replace(installer_path, final_path)
        try: os.remove(manifest_path)
        except OSError: pass
        checked.update({"pending": final_path, "version": release["tag"], "sha256": expected})
        _write_state(home, checked)
        log(f"Atualização AutoRIP {release['tag']} preparada; reinicie para instalar.")
        return checked
    except Exception as exc:
        for path in (manifest_path, installer_path):
            try:
                if path:
                    os.remove(path)
            except OSError: pass
        checked["error"] = type(exc).__name__
        try: _write_state(home, checked)
        except OSError: pass
        log(f"Atualização automática indisponível ({type(exc).__name__}).")
        return None


def install_staged(state, *, log=lambda _message: None):
    """Inicia o instalador já verificado; o processo atual deve encerrar depois."""
    if not isinstance(state, dict):
        return False
    path = state.get("pending")
    expected = state.get("sha256")
    if not isinstance(path, str) or not os.path.isfile(path) or not isinstance(expected, str):
        return False
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        log("Atualização pendente descartada: SHA-256 não confere.")
        return False
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([path, "/VERYSILENT", "/NORESTART"], close_fds=True,
                     creationflags=flags, stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True
