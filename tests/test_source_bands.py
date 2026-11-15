import threading

import numpy as np
import pytest
from PIL import Image

from autorip import engine
from autorip.config import Settings
from test_source_rgba_transform import gamma_profile


@pytest.mark.parametrize("mode", ["RGB","RGBA"])
@pytest.mark.parametrize("readonly", [False,True])
@pytest.mark.parametrize("in_place", [False,True])
def test_faixas_icc_preservam_pixels_alpha_metadados_e_posse(monkeypatch, mode, readonly, in_place):
    pixels = np.random.default_rng(7316).integers(0,256,(193,277,4),dtype=np.uint8)
    source = Image.fromarray(pixels).convert(mode)
    source.info["icc_profile"] = gamma_profile()
    source.readonly = readonly
    before = source.tobytes()
    rip = engine.Rip(Settings())
    convert = rip._source_rgb if mode == "RGB" else rip._source_rgba
    monkeypatch.setattr(engine,"SOURCE_ICC_MIN_PIXELS",1)
    monkeypatch.setattr(engine,"SOURCE_ICC_ROWS",31)
    monkeypatch.setattr(engine,"_memory_budget",lambda:256*1024**2)
    monkeypatch.setattr(engine,"_available_cpu_count",lambda:1)
    serial_input = source.copy()
    expected = convert(serial_input, in_place=False)
    threads = set()
    transform = rip._source_transform
    def tracked(*args, **kwargs):
        threads.add(threading.current_thread().name)
        return transform(*args, **kwargs)
    monkeypatch.setattr(rip,"_source_transform",tracked)
    monkeypatch.setattr(engine,"_available_cpu_count",lambda:4)
    actual = convert(source, in_place=in_place)
    try:
        assert actual.mode == expected.mode
        assert actual.tobytes() == expected.tobytes()
        assert actual.info["icc_profile"] == expected.info["icc_profile"]
        assert any(name.startswith("autorip-source") for name in threads)
        if readonly or not in_place:
            assert source.tobytes() == before
    finally:
        actual.close(); expected.close(); source.close(); serial_input.close()


@pytest.mark.parametrize("mode", ["RGB","RGBA"])
def test_falha_icc_libera_todas_as_faixas_apos_workers_terminarem(monkeypatch, mode):
    source = Image.new(mode,(277,193))
    source.info["icc_profile"] = gamma_profile()
    rip = engine.Rip(Settings())
    monkeypatch.setattr(engine,"SOURCE_ICC_MIN_PIXELS",1)
    monkeypatch.setattr(engine,"SOURCE_ICC_ROWS",31)
    monkeypatch.setattr(engine,"_available_cpu_count",lambda:4)
    monkeypatch.setattr(engine,"_memory_budget",lambda:256*1024**2)
    bands=[]
    crop = Image.Image.crop
    def tracked(*args, **kwargs):
        band = crop(*args, **kwargs); bands.append(band); return band
    def fail(*args, **kwargs):
        raise RuntimeError("band transform failure")
    monkeypatch.setattr(Image.Image,"crop",tracked)
    monkeypatch.setattr(engine.ImageCms,"applyTransform",fail)
    try:
        with pytest.raises(ValueError, match="band transform failure"):
            (rip._source_rgb if mode == "RGB" else rip._source_rgba)(source,in_place=True)
        assert bands
        for band in bands:
            with pytest.raises(ValueError, match="closed"):
                band.getpixel((0,0))
        assert source.getpixel((0,0)) is not None
    finally:
        source.close()


def test_imagem_pequena_usa_transformacao_serial(monkeypatch):
    source = Image.new("RGB",(20,20)); source.info["icc_profile"]=gamma_profile()
    monkeypatch.setattr(engine,"_available_cpu_count",lambda:20)
    assert engine._source_transform_workers(source) == 1
    source.close()
