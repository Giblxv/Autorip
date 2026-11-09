import os
import shutil

import pytest

from autorip.prt import PrtWriter
from conftest import wait_for_job


def test_fila_preserva_colisoes_e_move_prt_com_seguranca(app, sample_png, tmp_path):
    first_source = tmp_path / "one" / "mesma.png"
    second_source = tmp_path / "two" / "mesma.png"
    first_source.parent.mkdir()
    second_source.parent.mkdir()
    shutil.copyfile(sample_png, first_source)
    shutil.copyfile(sample_png, second_source)

    first = app.enqueue(str(first_source), 3, move_to_done=False)
    second = app.enqueue(str(second_source), 3, move_to_done=False)
    wait_for_job(first)
    wait_for_job(second)

    assert first["status"] == second["status"] == "pronto"
    prints = app.list_prints()
    assert {item["name"] for item in prints} == {"mesma.PRT", "mesma_001.PRT"}
    assert all(abs(item["width_cm"] - 3.0) < 0.05 for item in prints)
    assert abs(prints[0]["height_cm"] - 2.0) < 0.05
    assert os.path.exists(os.path.join(app.home, "thumbs", first["id"] + ".jpg"))
    assert os.path.exists(os.path.join(app.home, "thumbs", "by_name", "mesma.jpg"))
    assert os.path.exists(os.path.join(app.home, "thumbs", "by_name", "mesma_001.jpg"))
    app.s.margin_top_in = app.s.margin_bottom_in = 1.0
    assert app.list_prints()[0]["height_cm"] == 2.0  # usa sidecar do RIP, não margens atuais

    app.mark_printed("mesma.PRT")
    assert os.path.exists(os.path.join(app.s.printed_folder, "mesma.PRT"))
    app.delete_print("mesma_001.PRT")
    assert app.list_prints() == []

    with pytest.raises(FileNotFoundError):
        app.mark_printed("../../etc/passwd")


def test_fila_ignora_symlink_para_fora_da_pasta(app, tmp_path):
    outside = tmp_path / "outside.PRT"
    writer = PrtWriter(outside, 300, 300, 1, 8)
    import numpy as np
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    link = os.path.join(app.s.output_folder, "externo.PRT")
    try:
        os.symlink(outside, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink indisponivel neste sistema")
    assert all(item["name"] != "externo.PRT" for item in app.list_prints())
    with pytest.raises(FileNotFoundError):
        app.mark_printed("externo.PRT")


def test_miniatura_url_encodeia_caracteres_especiais_do_nome(app):
    import numpy as np
    name = "arte#%&=.PRT"
    path = os.path.join(app.s.output_folder, name)
    writer = PrtWriter(path, 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    with open(path + ".meta.json", "w", encoding="utf-8") as target:
        target.write('{"width_cm":' + "9" * 1000 + ',"height_cm":2}')
    item = next(entry for entry in app.list_prints() if entry["name"] == name)
    assert item["thumb"] == "/api/thumb?name=arte%23%25%26%3D&v=missing"


@pytest.mark.parametrize("orientation", [1, 6, 8])
def test_miniatura_respeita_orientacao_exif(app, tmp_path, orientation):
    from PIL import Image
    path = tmp_path / "orientada.jpg"
    image = Image.new("RGB", (100, 50), "red")
    image.paste("blue", (50, 0, 100, 50))
    exif = Image.Exif()
    exif[274] = orientation
    image.save(path, exif=exif)
    assert app._thumb("exif-test", str(path), output_name="orientada")
    for thumb in [os.path.join(app.home, "thumbs", "exif-test.jpg"),
                  os.path.join(app.home, "thumbs", "by_name", "orientada.jpg")]:
        with Image.open(thumb) as preview:
            assert preview.size == ((100, 50) if orientation == 1 else (50, 100))
            red, _, blue = preview.getpixel((10, 10))
            assert (red > blue) == (orientation != 8)
