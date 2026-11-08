"""Regressoes dos previews locais, sem depender de impressora."""
import os

import pytest
from PIL import Image

from autorip import server as server_module


def test_thumb_grava_jpeg_integro_em_ambas_as_pastas(app, sample_png):
    result = app._thumb("job-atomico", str(sample_png), output_name="pedido-001")
    assert result == "/api/thumb?id=job-atomico"

    root = os.path.join(app.home, "thumbs")
    paths = [
        os.path.join(root, "job-atomico.jpg"),
        os.path.join(root, "by_name", "pedido-001.jpg"),
    ]
    for path in paths:
        with Image.open(path) as preview:
            assert preview.format == "JPEG"
            preview.verify()
    assert not list(os.scandir(root))[0].name.startswith(".thumb.")
    assert not any(name.startswith(".thumb.") for name in os.listdir(root))
    assert not any(name.startswith(".thumb.") for name in os.listdir(os.path.join(root, "by_name")))


def test_falha_ao_gerar_thumbnail_preserva_arquivo_anterior(tmp_path, monkeypatch):
    target = tmp_path / "preview.jpg"
    original = b"preview anterior"
    target.write_bytes(original)

    def cannot_encode(*_args, **_kwargs):
        raise OSError("codificacao JPEG falhou")

    monkeypatch.setattr(Image.Image, "save", cannot_encode)
    with pytest.raises(OSError, match="JPEG falhou"):
        server_module._save_thumbnail_atomic(Image.new("RGB", (8, 8)), str(target))

    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".thumb.*.part"))


def test_publicacao_jpeg_ocorre_apos_escrever_todo_temporario(tmp_path, monkeypatch):
    target = tmp_path / "preview.jpg"
    target.write_bytes(b"arquivo anterior")
    original_replace = server_module.os.replace
    observed = []

    def verify_before_replace(temporary, destination):
        if destination == str(target):
            assert target.read_bytes() == b"arquivo anterior"
            with Image.open(temporary) as preview:
                assert preview.format == "JPEG"
                preview.verify()
            observed.append(True)
        return original_replace(temporary, destination)

    monkeypatch.setattr(server_module.os, "replace", verify_before_replace)
    server_module._save_thumbnail_atomic(Image.new("RGB", (8, 8), "blue"), str(target))
    assert observed == [True]
    with Image.open(target) as preview:
        preview.verify()
    assert not list(tmp_path.glob(".thumb.*.part"))


def test_thumb_nao_escreve_em_diretorio_symlink(app, sample_png, tmp_path):
    root = os.path.join(app.home, "thumbs")
    target = tmp_path / "externo"
    target.mkdir()
    try:
        os.symlink(target, root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink indisponivel neste ambiente")

    assert app._thumb("nao-gravar", str(sample_png)) == ""
    assert not list(target.iterdir())
