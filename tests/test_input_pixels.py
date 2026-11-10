"""Artes acima dos antigos tetos da aplicação e do Pillow entram em todo fluxo."""
import io
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import ImageFile
import pytest

from autorip import bgremove, integrations, server
from autorip.config import Settings
from autorip.engine import Rip
from conftest import ROOT
from test_admission import Handler, idle_app


@pytest.mark.parametrize("module", ["autorip.engine", "autorip.server", "autorip.layout",
                                   "autorip.integrations", "autorip.bgremove"])
def test_entrada_isolada_aceita_png_acima_do_teto_do_pillow(module, large_artwork_png):
    # Um processo por módulo evita que a importação de outro ponto de entrada
    # esconda uma política de imagem não inicializada. Não decodifica o raster.
    code = """
import importlib, sys, warnings
from PIL import Image
warnings.simplefilter('error', Image.DecompressionBombWarning)
importlib.import_module(sys.argv[1])
with Image.open(sys.argv[2]) as image:
    assert image.size == (20000, 20000)
    image.verify()
"""
    result = subprocess.run([sys.executable, "-c", code, module, str(large_artwork_png)],
                            cwd=ROOT, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("entry", ["rip", "thumbnail", "background"])
def test_arte_grande_chega_ao_decoder_sem_cota(entry, large_artwork_png, tmp_path, monkeypatch):
    class DecodeReached(Exception):
        pass

    def reached(*args, **kwargs):
        raise DecodeReached("pixels serão decodificados")

    monkeypatch.setattr(ImageFile.ImageFile, "load", reached)
    with pytest.raises(DecodeReached):
        if entry == "rip":
            Rip(Settings(label_enabled=False)).process(
                str(large_artwork_png), str(tmp_path / "large.PRT"), 2.54)
        elif entry == "thumbnail":
            server._load_thumbnail(large_artwork_png, (220, 220))
        else:
            model = tmp_path / "local.onnx"
            model.write_bytes(b"test model")
            monkeypatch.setitem(sys.modules, "rembg", SimpleNamespace(
                new_session=lambda *args, **kwargs: object(),
                remove=lambda image, **kwargs: image))
            bgremove.remove_background(str(large_artwork_png), str(tmp_path / "out.png"), str(model))
    assert not list(tmp_path.glob("*.PRT"))
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("entry", ["upload", "hot_folder", "planner"])
def test_admissao_de_arte_grande_sem_decodificar(entry, idle_app, large_artwork_png, monkeypatch):
    def forbid_decode(*args, **kwargs):
        pytest.fail("A admissão/planejamento não deve materializar os pixels")

    monkeypatch.setattr(ImageFile.ImageFile, "load", forbid_decode)
    if entry == "upload":
        job = idle_app.receive_upload(Handler(large_artwork_png.read_bytes()), "large.png", "2.54")
    else:
        path = Path(idle_app.s.hot_folder) / "large.png"
        shutil.copyfile(large_artwork_png, path)
        if entry == "planner":
            plan = idle_app.plan_layout({"items": [{"name": path.name, "width_cm": 2.54}]})
            assert len(plan["items"]) == 1
            assert plan["items"][0]["source_width_px"] == 20000
            assert plan["items"][0]["source_height_px"] == 20000
            assert path.exists()
            return
        job = idle_app.enqueue_hot_file(path.name, "2.54")
    assert job["status"] == "fila"
    assert idle_app.q.qsize() == 1
    assert not idle_app._admission_reservations


def test_trello_verifica_arte_grande_sem_decodificar(large_artwork_png, tmp_path, monkeypatch):
    raw = large_artwork_png.read_bytes()
    url = "https://trello.com/large.png"

    class Response(io.BytesIO):
        headers = {"Content-Length": str(len(raw))}

        def geturl(self):
            return url

    monkeypatch.setattr(integrations.urllib.request, "build_opener", lambda *args: SimpleNamespace(
        open=lambda *args, **kwargs: Response(raw)))

    def forbid_decode(*args, **kwargs):
        pytest.fail("Validar um anexo não deve decodificar seus pixels")

    monkeypatch.setattr(ImageFile.ImageFile, "load", forbid_decode)
    target = tmp_path / "download.png"
    assert integrations._download_attachment(url, str(target), {}) == len(raw)
    assert target.read_bytes() == raw
