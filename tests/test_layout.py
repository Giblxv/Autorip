from PIL import Image
import pytest

from autorip.layout import (
    MAX_SHEET_WIDTH_CM, auto_pack, inspect_image, layout_to_svg,
    make_item, proportional_size, sheet_height,
)


def test_dimensionamento_proporcional_e_limite_58(tmp_path):
    path = tmp_path / "arte.png"
    Image.new("RGBA", (2000, 1000), (255, 0, 0, 255)).save(path, dpi=(100, 100))
    info = inspect_image(str(path))
    width, height = proportional_size(info, width_cm=57)
    assert width == 57
    assert height == 28.5
    width, height = proportional_size(info, width_cm=80)
    assert width == MAX_SHEET_WIDTH_CM
    assert height == 29


def test_auto_pack_sem_sobreposicao_e_preview(tmp_path):
    path = tmp_path / "arte.png"
    Image.new("RGBA", (100, 50), (0, 0, 0, 255)).save(path)
    info = inspect_image(str(path))
    items = [make_item(info, 20, item_id=f"i{i}") for i in range(5)]
    packed = auto_pack(items, sheet_width_cm=58, margin_cm=1, gap_cm=1)
    assert packed[0].x_cm == 1
    assert packed[2].y_cm > packed[0].y_cm
    assert sheet_height(packed, 1, 1) > 1
    svg = layout_to_svg(packed, sheet_width_cm=58, margin_cm=1, gap_cm=1)
    assert svg.startswith("<svg")
    assert "arte.png" in svg


def test_auto_pack_rejeita_item_largo_demais(tmp_path):
    path = tmp_path / "arte.png"
    Image.new("RGB", (100, 100), "white").save(path)
    info = inspect_image(str(path))
    with pytest.raises(ValueError, match="excede"):
        auto_pack([make_item(info, 57)], sheet_width_cm=57, margin_cm=1)


@pytest.mark.parametrize("fmt", ["PNG", "TIFF"])
def test_inspecao_nao_decodifica_pixels_e_preserva_formato(tmp_path, monkeypatch, fmt):
    from PIL import ImageFile
    path = tmp_path / ("cabecalho." + fmt.lower())
    Image.new("RGBA", (120, 60), (20, 40, 60, 128)).save(path, format=fmt, dpi=(300, 300))

    def forbid_decode(*args, **kwargs):
        pytest.fail("A inspecao de metadados nao deve decodificar pixels")

    monkeypatch.setattr(ImageFile.ImageFile, "load", forbid_decode)
    info = inspect_image(str(path))
    assert (info.width_px, info.height_px) == (120, 60)
    assert info.format == fmt and info.has_alpha


@pytest.mark.parametrize("orientation", [1, 3, 5, 6, 7, 8])
def test_inspecao_exif_preserva_dimensoes_fisicas(tmp_path, orientation):
    path = tmp_path / "orientada.jpg"
    exif = Image.Exif()
    exif[274] = orientation
    Image.new("RGB", (200, 100), "blue").save(path, exif=exif, dpi=(100, 200))
    info = inspect_image(str(path))
    swapped = orientation in (5, 6, 7, 8)
    assert (info.width_px, info.height_px) == ((100, 200) if swapped else (200, 100))
    assert (info.dpi_x, info.dpi_y) == ((200, 100) if swapped else (100, 200))
    assert info.width_cm == pytest.approx(1.27 if swapped else 5.08)
    assert info.height_cm == pytest.approx(5.08 if swapped else 1.27)
    assert info.format == "JPEG"
