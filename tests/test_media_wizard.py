import io
from pathlib import Path

import pytest

from tools import media_security as wizard


class FakeResponse:
    def __init__(self, payload, content_length=None):
        self.stream = io.BytesIO(payload)
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size=-1):
        return self.stream.read(size)


def test_manifest_sha256_exige_nome_exato_e_hash_unico():
    digest = "a" * 64
    assert wizard.manifest_sha256(f"{digest}  pacote.zip\n", "pacote.zip") == digest
    with pytest.raises(ValueError):
        wizard.manifest_sha256(f"{digest}  outro.zip\n", "pacote.zip")
    with pytest.raises(ValueError):
        wizard.manifest_sha256("not-a-checksum  pacote.zip\n", "pacote.zip")


def test_download_publica_atomically_e_remove_parte_incompleta(monkeypatch, tmp_path):
    target = tmp_path / "bundle.zip"
    target.write_bytes(b"versao anterior")
    monkeypatch.setattr(wizard.urllib.request, "urlopen",
                        lambda *_args, **_kwargs: FakeResponse(b"novo", content_length=4))
    result = wizard.download("https://example.test/bundle.zip", target, lambda _message: None, 8)
    assert result == target
    assert target.read_bytes() == b"novo"
    assert not Path(str(target) + ".part").exists()

    def oversized(*_args, **_kwargs):
        return FakeResponse(b"12345", content_length=5)

    monkeypatch.setattr(wizard.urllib.request, "urlopen", oversized)
    with pytest.raises(ValueError, match="limite"):
        wizard.download("https://example.test/bundle.zip", target, lambda _message: None, 4)
    assert target.read_bytes() == b"novo"
    assert not Path(str(target) + ".part").exists()
