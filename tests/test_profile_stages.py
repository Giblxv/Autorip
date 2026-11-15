"""O perfil deve observar o mesmo caminho de carga usado pelo programa."""
import pytest
from PIL import Image

from autorip.config import Settings
from autorip.engine import Rip
from benchmarks.profile_stages import run_once


def test_profile_preserva_caminho_rgb_nativo(tmp_path, monkeypatch):
    source = tmp_path / "rgb.png"
    Image.new("RGB", (64, 48), (30, 120, 210)).save(source)
    original = Rip._source_rgb
    calls = []

    def source_rgb(self, image, **kwargs):
        calls.append((image.mode, kwargs))
        return original(self, image, **kwargs)

    monkeypatch.setattr(Rip, "_source_rgb", source_rgb)
    _, timings = run_once(source, tmp_path / "profile.PRT", Settings(
        dpi_x=72, dpi_y=72, label_enabled=False, white_enabled=False,
        margin_top_in=0, margin_bottom_in=0))

    assert calls == [("RGB", {"in_place": True})]
    assert timings["load_source"] > 0


def test_profile_restaura_loader_nativo_apos_falha(tmp_path):
    loader, builtin = Rip._load_source, Rip._builtin_load_source
    with pytest.raises(FileNotFoundError):
        run_once(tmp_path / "missing.png", tmp_path / "profile.PRT", Settings())
    assert Rip._load_source is loader
    assert Rip._builtin_load_source is builtin
