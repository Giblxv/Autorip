"""Origem e reamostragem devem preservar pixels, dimensões físicas e todos os bytes PRT."""
import numpy as np
import pytest
from PIL import Image, ImageCms, ImageOps

from autorip import engine
from autorip.config import Settings


def original_load(rip, path):
    """Oráculo do carregamento anterior à reutilização dos buffers de origem."""
    with Image.open(path) as opened:
        orientation = opened.getexif().get(274, 1)
        source = ImageOps.exif_transpose(opened)
        try:
            has_alpha = source.mode in ("RGBA", "LA", "PA") or "transparency" in source.info
            dpi = source.info.get("dpi", (300.0, 300.0))
            x, y = engine._safe_source_dpi(dpi[0]), engine._safe_source_dpi(dpi[1])
            if orientation in (5, 6, 7, 8):
                x, y = y, x
            source.load()
            return rip._source_rgba(source), has_alpha, x, y
        finally:
            source.close()


KINDS = [("RGBA", "PNG"), ("RGB", "JPEG"), ("LA", "PNG"), ("P", "PNG"),
         ("RGBA", "TIFF"), ("CMYK", "TIFF"), ("RGB-ICC", "PNG"), ("LAB-ICC", "TIFF")]


def make_image(path, mode, fmt, orientation):
    pixels = np.random.default_rng(81).integers(0, 256, (29, 37, 4), dtype=np.uint8)
    image = Image.fromarray(pixels, "RGBA")
    profile = None
    if mode == "RGB-ICC":
        image = image.convert("RGB")
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    elif mode == "LAB-ICC":
        rgb = ImageCms.createProfile("sRGB")
        lab = ImageCms.createProfile("LAB")
        image = ImageCms.profileToProfile(image.convert("RGB"), rgb, lab, outputMode="LAB")
        profile = ImageCms.ImageCmsProfile(lab).tobytes()
    elif mode == "P":
        image = image.convert("P")
        image.info["transparency"] = 0
    elif mode != "RGBA":
        image = image.convert(mode)
    exif = Image.Exif()
    exif[274] = orientation
    options = dict(format=fmt, exif=exif, dpi=(100, 200))
    if profile:
        options["icc_profile"] = profile
    image.save(path, **options)
    image.close()


@pytest.mark.parametrize("mode,fmt", KINDS)
@pytest.mark.parametrize("orientation", range(1, 9))
def test_origem_e_prt_identicos_com_exif_alpha_dpi_e_icc(tmp_path, mode, fmt, orientation):
    source = tmp_path / "source.image"
    make_image(source, mode, fmt, orientation)
    settings = Settings(dpi_x=300, dpi_y=600, margin_top_in=.12,
                        margin_bottom_in=.12, label_enabled=True,
                        channel_order=["M", "Y", "K", "C"], white_planes=[4, 7])
    rip = engine.Rip(settings)
    expected, alpha, x, y = original_load(rip, source)
    actual, actual_alpha, actual_x, actual_y = rip._load_source(source)
    assert (actual_alpha, actual_x, actual_y) == (alpha, x, y)
    assert actual.mode == "RGBA" and actual.size == expected.size
    assert actual.tobytes() == expected.tobytes()
    actual.close()
    expected.close()

    # Reconstrua também a preparação anterior ao resize, inclusive o atalho 1:1.
    reference = engine.Rip(settings)
    reference._load_source = lambda path: original_load(reference, path)
    reference._prepare_resampling = lambda image, dots, rows: image
    first = reference.process(str(source), str(tmp_path / "old.PRT"), width_cm=.75)
    second = rip.process(str(source), str(tmp_path / "new.PRT"), width_cm=.75)
    assert (tmp_path / "old.PRT").read_bytes() == (tmp_path / "new.PRT").read_bytes()
    assert {k: v for k, v in first.items() if k != "output_path"} == {
        k: v for k, v in second.items() if k != "output_path"}


@pytest.mark.parametrize("orientation", [1, 6])
@pytest.mark.parametrize("fail", [False, True])
def test_origens_fechadas_antes_do_render_ou_apos_falha(tmp_path, monkeypatch, orientation, fail):
    source = tmp_path / "source.png"
    make_image(source, "RGBA", "PNG", orientation)
    tracked = []
    opened, transpose = engine.Image.open, engine.ImageOps.exif_transpose

    def track_open(*args, **kwargs):
        image = opened(*args, **kwargs)
        tracked.append(image)
        return image

    def track_transpose(*args, **kwargs):
        image = transpose(*args, **kwargs)
        tracked.append(image)
        return image

    monkeypatch.setattr(engine.Image, "open", track_open)
    monkeypatch.setattr(engine.ImageOps, "exif_transpose", track_transpose)
    rip = engine.Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False))
    if fail:
        monkeypatch.setattr(rip, "_source_rgba", lambda image: (_ for _ in ()).throw(ValueError("ICC simulado")))
        with pytest.raises(ValueError, match="ICC simulado"):
            rip._load_source(source)
    else:
        actual, *_ = rip._load_source(source)
        assert actual.getpixel((0, 0)) is not None
        actual.close()
    for image in tracked:
        with pytest.raises(ValueError, match="closed"):
            image.getpixel((0, 0))


@pytest.mark.parametrize("size", [(37, 29), (120, 900)])
@pytest.mark.parametrize("scale", [1, .7, 1.3])
def test_reuso_de_alpha_preserva_resize_e_atalho_um_para_um(tmp_path, size, scale):
    path = tmp_path / "alpha.png"
    pixels = np.random.default_rng(17).integers(0, 256, (size[1], size[0], 4), dtype=np.uint8)
    Image.fromarray(pixels, "RGBA").save(path)
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False)
    old, new = engine.Rip(settings), engine.Rip(settings)
    old._prepare_resampling = lambda image, dots, rows: image
    width = size[0] / 300 * 2.54 * scale
    old.process(str(path), str(tmp_path / "old.PRT"), width)
    new.process(str(path), str(tmp_path / "new.PRT"), width)
    assert (tmp_path / "old.PRT").read_bytes() == (tmp_path / "new.PRT").read_bytes()
