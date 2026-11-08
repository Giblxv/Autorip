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
