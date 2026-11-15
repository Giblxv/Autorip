import numpy as np
import pytest
from PIL import Image

from autorip.config import Settings
from autorip.engine import Rip


def reference_strip(im, width, height, start, end):
    sy = im.height / height
    return im.resize((width, end - start), Image.LANCZOS,
                     box=(0, start * sy, im.width, end * sy))


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "RGBa"])
@pytest.mark.parametrize("bounds", [(0, 91), (0, 37), (1, 64), (17, 18), (78, 91)])
def test_identity_strip_preserves_pixels_mode_metadata_and_source(mode, bounds):
    pixels = np.random.default_rng(36).integers(0, 256, (91, 73, len(mode)), dtype=np.uint8)
    im = Image.fromarray(pixels, mode)
    im.info["dpi"] = (300, 300)
    before = im.tobytes()
    try:
        expected = reference_strip(im, 73, 91, *bounds)
        actual = Rip._resample_strip(im, 73, 91, *bounds)
        try:
            assert actual.mode == expected.mode and actual.size == expected.size
            assert actual.tobytes() == expected.tobytes()
            assert actual.info == expected.info
            actual.paste(0, (0, 0, *actual.size))
            assert im.tobytes() == before
        finally:
            actual.close()
            expected.close()
    finally:
        im.close()


def test_rgba_whole_image_avoids_quantizing_hidden_or_partial_colors():
    im = Image.fromarray(np.array([[[191, 87, 3, 0], [127, 11, 193, 17]]], dtype=np.uint8))
    actual = Rip._resample_strip(im, 2, 1, 0, 1)
    try:
        assert actual.tobytes() == im.tobytes()
        assert actual.tobytes() != im.convert("RGBa").convert("RGBA").tobytes()
    finally:
        actual.close()
        im.close()


@pytest.mark.parametrize("mode", ["RGB", "RGBA", "RGBa", "L"])
@pytest.mark.parametrize("shape", [(53, 37), (113, 141)])
def test_scaled_and_other_modes_keep_original_lanczos(mode, shape):
    pixels = np.random.default_rng(17).integers(0, 256, (91, 73, len(mode)), dtype=np.uint8)
    if mode == "L":
        pixels = pixels[..., 0]
    im = Image.fromarray(pixels, mode)
    width, height = shape
    expected = reference_strip(im, width, height, 1, height - 1)
    actual = Rip._resample_strip(im, width, height, 1, height - 1)
    try:
        assert actual.tobytes() == expected.tobytes()
    finally:
        actual.close()
        expected.close()
        im.close()


def test_dimensions_beyond_float32_integer_precision_keep_resize():
    class LargeImage:
        width, height = 3, 2**24 + 1
        size = (width, height)
        mode = "RGBA"

        def resize(self, size, resample, box):
            assert size == (3, 9)
            assert box == (0, 2**24 - 8, 3, 2**24 + 1)
            return "fallback"

    im = LargeImage()
    assert Rip._resample_strip(im, im.width, im.height, im.height - 9, im.height) == "fallback"


@pytest.mark.parametrize("white", [False, True])
@pytest.mark.parametrize("workers", [1, 4])
def test_identity_full_rip_with_margins_labels_alpha_and_channels_is_identical(tmp_path, monkeypatch, white, workers):
    from autorip import engine
    from pathlib import Path

    pixels = np.random.default_rng(41).integers(0, 256, (1800, 641, 4), dtype=np.uint8)
    path = tmp_path / "identity.png"
    Image.fromarray(pixels).save(path)
    settings = Settings(dpi_x=300, dpi_y=300, white_enabled=white, label_enabled=True,
                        margin_top_in=.15, margin_bottom_in=.15, mirror=True,
                        channel_order=["M", "K", "C", "Y"], white_planes=[4, 7])
    monkeypatch.setattr(engine, "_available_cpu_count", lambda: workers)
    baseline = Rip(settings)
    baseline._resample_strip = reference_strip
    candidate = Rip(settings)
    first = baseline.process(str(path), str(tmp_path / "base.PRT"), width_cm=641 / 300 * 2.54)
    second = candidate.process(str(path), str(tmp_path / "new.PRT"), width_cm=641 / 300 * 2.54)
    a, b = first.pop("output_path"), second.pop("output_path")
    assert Path(a).read_bytes() == Path(b).read_bytes()
    assert first == second
