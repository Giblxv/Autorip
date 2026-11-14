"""Downloads limitados e verificações de integridade do assistente de mídia."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path


def validate_https_url(url: str) -> urllib.parse.SplitResult:
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("A URL do artefato precisa usar HTTPS sem credenciais embutidas.")
    return parsed


def download(url: str, target: Path, report, max_bytes: int):
    validate_https_url(url)
    target.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": "AutoRIP-Media-Wizard"})
    temporary = target.with_name(target.name + ".part")
    try:
        with urllib.request.urlopen(request, timeout=60) as source, temporary.open("wb") as destination:
            total = int(source.headers.get("Content-Length", "0") or 0)
            if total < 0 or total > max_bytes:
                raise ValueError(f"Download excede o limite permitido para {target.name}.")
            expected_space = total if total else max_bytes
            if shutil.disk_usage(target.parent).free < expected_space + 128 * 1024**2:
                raise OSError("Espaço livre insuficiente para preparar a mídia com segurança.")
            received = 0
            while True:
                block = source.read(1024 * 1024)
                if not block:
                    break
                received += len(block)
                if received > max_bytes:
                    raise ValueError(f"Download excede o limite permitido para {target.name}.")
                destination.write(block)
                if total:
                    report(f"Baixando {target.name}: {received / total:.0%}")
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary, target)
    except BaseException:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    return target


def fetch_text(url: str, max_bytes: int) -> str:
    """Lê um manifesto pequeno com o mesmo limite e política HTTPS do downloader."""
    validate_https_url(url)
    request = urllib.request.Request(url, headers={"User-Agent": "AutoRIP-Media-Wizard"})
    with urllib.request.urlopen(request, timeout=60) as source:
        total = int(source.headers.get("Content-Length", "0") or 0)
        if total < 0 or total > max_bytes:
            raise ValueError("Manifesto remoto excede o limite permitido.")
        payload = source.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ValueError("Manifesto remoto excede o limite permitido.")
    return payload.decode("utf-8", "strict")


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_sha256(manifest: str, filename: str) -> str:
    matches = []
    for line in manifest.splitlines():
        fields = line.strip().split(maxsplit=1)
        if len(fields) == 2:
            digest, listed = fields
            listed = listed.lstrip("* ")
            if listed == filename:
                matches.append(digest.lower())
    if len(matches) != 1 or not re.fullmatch(r"[0-9a-f]{64}", matches[0]):
        raise ValueError(f"Checksum ausente ou ambíguo para {filename}.")
    return matches[0]


def verify_rufus_signature(path: Path):
    """Exige assinatura Authenticode válida do fornecedor esperado no Windows."""
    if os.name != "nt":
        return
    script = (
        "param($p); $s = Get-AuthenticodeSignature -LiteralPath $p; "
        "if ($s.Status -ne 'Valid') { exit 1 }; "
        "if ($s.SignerCertificate.Subject -notmatch 'Akeo Consulting') { exit 2 }"
    )
    result = subprocess.run(
        [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
         "-NoProfile", "-NonInteractive", "-Command", script, str(path)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    if result.returncode:
        raise RuntimeError("A assinatura Authenticode do Rufus não foi validada.")
