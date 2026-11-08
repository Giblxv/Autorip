from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageFile

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import read_header, read_rows


def test_rip_png_emite_prt_com_transparencia_e_base_branca(sample_png, tmp_path):
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0.1,
                        margin_bottom_in=0.1, label_enabled=False)
    output = tmp_path / "amostra.PRT"
    info = Rip(settings).process(str(sample_png), str(output), width_cm=2.54)
    header = read_header(output)
    planes = read_rows(output, 0, header["n_rows"])

    assert header["n_channels"] == 12
    assert header["dpi_x"] == 300 and header["dpi_y"] == 300
    assert header["n_dots"] == 300 and info["has_alpha"] is True
    assert any(np.any(planes[index]) for index in range(4)) and np.any(planes[4])
    assert planes[4][30 + 100, 0] == 0  # alfa transparente permanece sem branco
    assert planes[4][30 + 100, 150] > 0


def test_halftone_tem_fase_continua_entre_blocos():
    rip = Rip(Settings(label_enabled=False))
    values = np.full((128, 64), 0.65, dtype=np.float32)
    first = rip._halftone(values, 960)
    second = rip._halftone(values, 1024)
    assert np.array_equal(first[64:128], second[:64])


def test_fechamento_de_furos_realmente_gera_tinta_branca():
    alpha = np.ones((128, 128), dtype=np.float32)
    alpha[60:68, 60:68] = 0
    filled = Rip(Settings(white_fill_holes_mm=0.3, white_choke_mm=0,
                          label_enabled=False))._white_levels(alpha)
    unchanged = Rip(Settings(white_fill_holes_mm=0, white_choke_mm=0,
                             label_enabled=False))._white_levels(alpha)
    assert np.all(filled[60:68, 60:68] > 0)
    assert np.all(unchanged[60:68, 60:68] == 0)


def test_orientacao_exif_e_aplicada_antes_da_imposicao(tmp_path):
    path = tmp_path / "orientada.jpg"
    image = Image.new("RGB", (200, 100), "blue")
    exif = Image.Exif()
    exif[274] = 6
    image.save(path, exif=exif)
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False)
    info = Rip(settings).process(str(path), str(tmp_path / "exif.PRT"), width_cm=2.54)
    assert info["height_cm"] == pytest.approx(5.08, abs=0.02)


def test_perfil_icc_invalido_falha_explicitamente(sample_png, tmp_path):
    rip = Rip(Settings(icc_path=str(tmp_path / "ausente.icc"), label_enabled=False))
    assert rip.icc_error
    with pytest.raises(RuntimeError, match="Perfil ICC"):
        rip.process(str(sample_png), str(tmp_path / "nao-criar.PRT"), 2.54)


def test_rejeita_imagem_acima_do_limite_sem_decodificar(monkeypatch, sample_png, tmp_path):
    monkeypatch.setattr(engine, "MAX_INPUT_PIXELS", 100)

    def forbid_decode(*args, **kwargs):
        pytest.fail("Imagem acima do limite chegou a decodificacao de pixels")

    monkeypatch.setattr(ImageFile.ImageFile, "load", forbid_decode)
    with pytest.raises(ValueError, match="limite"):
        Rip(Settings(label_enabled=False)).process(str(sample_png), str(tmp_path / "x.PRT"), 2.54)
    assert not (tmp_path / "x.PRT").exists()
    assert not list(tmp_path.glob("*.part"))


def test_verifica_espaco_estimado_antes_de_criar_temporario(monkeypatch, sample_png, tmp_path):
    monkeypatch.setattr(engine.shutil, "disk_usage", lambda path: SimpleNamespace(free=1))
    with pytest.raises(ValueError, match="Espaco insuficiente"):
        Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
            str(sample_png), str(tmp_path / "saida.PRT"), 2.54)
    assert not list(tmp_path.glob("*.part"))


def test_rip_usa_sufixo_sem_alterar_destino_existente(sample_png, tmp_path):
    output = tmp_path / "existente.PRT"
    output.write_bytes(b"arquivo original")
    info = Rip(Settings(label_enabled=False)).process(str(sample_png), str(output), 2.54)
    assert output.read_bytes() == b"arquivo original"
    assert info["output_path"] == str(tmp_path / "existente_001.PRT")
    assert read_header(info["output_path"])["n_channels"] == 12


def test_publicacao_no_clobber_preserva_arquivo_criado_durante_rip(monkeypatch, sample_png, tmp_path):
    output = tmp_path / "corrida.PRT"
    original_link = engine.os.link
    created = {"value": False}

    def create_competing_file(source, destination):
        if destination == str(output) and not created["value"]:
            with open(destination, "wb") as target:
                target.write(b"arquivo de outro processo")
            created["value"] = True
        return original_link(source, destination)

    monkeypatch.setattr(engine.os, "link", create_competing_file)
    info = Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
        str(sample_png), str(output), 2.54)
    assert open(output, "rb").read() == b"arquivo de outro processo"
    assert info["output_path"] == str(tmp_path / "corrida_001.PRT")
    assert read_header(info["output_path"])["n_channels"] == 12
