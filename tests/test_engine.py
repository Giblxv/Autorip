from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image, ImageFile

from autorip import engine
from autorip.config import Settings
from autorip.engine import Rip
from autorip.prt import read_header, read_rows


@pytest.mark.parametrize("value", [None, 0, -1, float("nan"), float("inf"), "not-a-number"])
def test_dpi_de_entrada_invalido_usa_padrao_seguro(value):
    assert engine._safe_source_dpi(value) == engine.DEFAULT_SOURCE_DPI


def test_dpi_de_entrada_positivo_e_finito_e_preservado():
    assert engine._safe_source_dpi(144) == 144
    assert engine._safe_source_dpi("720") == 720


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


def test_rip_preserva_128_mib_de_reserva_de_disco(monkeypatch, sample_png, tmp_path):
    # Existe espaco suficiente para o arquivo, mas nao para a reserva minima.
    livre = engine.MIN_FREE_DISK_BYTES + 10
    monkeypatch.setattr(engine.shutil, "disk_usage",
                        lambda path: SimpleNamespace(free=livre))
    destination = tmp_path / "sem-reserva.PRT"
    with pytest.raises(ValueError, match="128 MiB"):
        Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
            str(sample_png), str(destination), 2.54)
    assert not destination.exists()
    assert not list(tmp_path.glob("*.part"))


def test_rejeita_tira_acima_do_orcamento_de_memoria(monkeypatch, sample_png, tmp_path):
    monkeypatch.setattr(engine, "MAX_STRIP_MEMORY_BYTES", 1)
    with pytest.raises(ValueError, match="memória"):
        Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
            str(sample_png), str(tmp_path / "memoria.PRT"), 2.54)
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


@pytest.mark.parametrize("dpi_x,dpi_y", [(300, 300), (720, 1440), (1440, 720)])
def test_reticula_muda_com_grade_de_impressao_sem_alterar_cobertura(dpi_x, dpi_y):
    settings = Settings(dpi_x=dpi_x, dpi_y=dpi_y, label_enabled=False)
    rip = Rip(settings)
    reference = Rip(Settings(label_enabled=False))
    values = np.full((256, 256), 0.65, dtype=np.float32)
    levels = rip._halftone(values, 0)
    original = reference._halftone(values, 0)
    # A disposicao muda, mas o volume e as contagens de gotas sao preservados.
    assert not np.array_equal(levels, original)
    assert np.array_equal(np.bincount(levels.ravel(), minlength=4),
                          np.bincount(original.ravel(), minlength=4))
    # Dobrar os dois DPIs preserva a proporcao fisica e a mesma reticula.
    doubled = Rip(Settings(dpi_x=2 * dpi_x, dpi_y=2 * dpi_y, label_enabled=False))
    assert np.array_equal(levels, doubled._halftone(values, 0))


def test_resolucao_padrao_preserva_reticula_existente():
    rip = Rip(Settings(label_enabled=False))
    assert np.array_equal(rip.noise, engine._blue_noise())


@pytest.mark.parametrize("fmt", ["JPEG", "TIFF"])
@pytest.mark.parametrize("orientation", [1, 6])
@pytest.mark.parametrize("width_cm", [None, 2.54])
def test_rip_preserva_proporcao_fisica_de_dpi_anisotropico(tmp_path, orientation, width_cm, fmt):
    path = tmp_path / "anisotropica.jpg"
    exif = Image.Exif()
    exif[274] = orientation
    Image.new("RGB", (200, 100), "blue").save(path, format=fmt, dpi=(100, 200), exif=exif)
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0,
                        margin_bottom_in=0, label_enabled=False)
    output = tmp_path / "anisotropica.PRT"
    info = Rip(settings).process(str(path), str(output), width_cm=width_cm)
    natural_width, natural_height = (5.08, 1.27) if orientation == 1 else (1.27, 5.08)
    expected_width = natural_width if width_cm is None else width_cm
    expected_height = natural_height * expected_width / natural_width
    header = read_header(output)
    assert info["width_cm"] == pytest.approx(expected_width)
    assert info["height_cm"] == pytest.approx(expected_height, abs=0.01)
    assert header["n_dots"] == round(expected_width / 2.54 * 300)
    assert header["n_rows"] == round(expected_height / 2.54 * 300)


def test_etiquetas_nao_se_misturam_em_rips_simultaneos(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, local

    entradas = []
    for nome in ("ALFA-TESTE.png", "BETA-TESTE.png"):
        path = tmp_path / nome
        Image.new("RGBA", (64, 64), (255, 255, 255, 255)).save(path)
        entradas.append(path)

    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0.3,
                        margin_bottom_in=0.3, label_enabled=True,
                        white_enabled=False)
    referencias = []
    for index, path in enumerate(entradas):
        destino = tmp_path / f"referencia-{index}.PRT"
        Rip(settings).process(str(path), str(destino), width_cm=2.54)
        referencias.append(destino.read_bytes())
    assert referencias[0] != referencias[1]  # a etiqueta distingue as artes

    rip = Rip(settings)
    original = rip._render
    barrier = Barrier(2)
    thread_state = local()

    def render_simultaneo(*args, **kwargs):
        if not getattr(thread_state, "entered", False):
            thread_state.entered = True
            barrier.wait(timeout=10)
        return original(*args, **kwargs)

    monkeypatch.setattr(rip, "_render", render_simultaneo)
    saidas = [tmp_path / "paralelo-alfa.PRT", tmp_path / "paralelo-beta.PRT"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(rip.process, str(src), str(dest), 2.54)
                   for src, dest in zip(entradas, saidas)]
        for future in futures:
            future.result(timeout=30)

    for resultado, esperado in zip(saidas, referencias):
        assert resultado.read_bytes() == esperado

@pytest.mark.parametrize("width_cm", [0, -1, float("nan"), float("inf")])
def test_rejeita_largura_explicita_invalida(sample_png, tmp_path, width_cm):
    output = tmp_path / "largura-invalida.PRT"
    settings = Settings(dpi_x=300, dpi_y=300, label_enabled=False)
    with pytest.raises(ValueError, match="largura de impressão"):
        Rip(settings).process(str(sample_png), str(output), width_cm=width_cm)
    assert not output.exists()
    assert not list(tmp_path.glob("*.part"))


def test_largura_omitida_usa_dpi_da_imagem(tmp_path):
    source = tmp_path / "dpi.png"
    Image.new("RGB", (100, 50), "blue").save(source, dpi=(100, 100))
    output = tmp_path / "dpi.PRT"
    info = Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
        str(source), str(output))
    assert info["width_cm"] == pytest.approx(2.54, abs=0.002)
    assert read_header(output)["n_dots"] == 300

@pytest.mark.parametrize("dpi_x,dpi_y", [(720, 72), (72, 720)])
def test_fechamento_branco_funciona_com_raio_zero_em_um_eixo(dpi_x, dpi_y):
    alpha = np.ones((64, 64), dtype=np.float32)
    alpha[31:34, 31:34] = 0
    settings = Settings(dpi_x=dpi_x, dpi_y=dpi_y, white_fill_holes_mm=0.1,
                        white_choke_mm=0, label_enabled=False)
    levels = Rip(settings)._white_levels(alpha)
    assert np.all(levels[31:34, 31:34] == 3)
    # A operacao nao deve recortar o bloco nem apagar bordas opacas.
    assert levels.shape == alpha.shape
    assert np.all(levels == 3)

def test_rip_converte_tiff_lab_com_perfil_icc_embutido(tmp_path):
    from PIL import ImageCms
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB", 6500))
    lab = Image.new("LAB", (24, 24), (150, 180, 200))
    source = tmp_path / "lab.tif"
    lab.save(source, icc_profile=profile.tobytes())
    rgb = ImageCms.profileToProfile(lab, profile, ImageCms.createProfile("sRGB"), outputMode="RGB")
    reference = tmp_path / "srgb.png"
    rgb.save(reference, icc_profile=b"")
    settings = Settings(dpi_x=300, dpi_y=300, margin_top_in=0, margin_bottom_in=0,
                        label_enabled=False, white_choke_mm=0, white_fill_holes_mm=0)
    rip = Rip(settings)
    actual, expected = tmp_path / "lab.PRT", tmp_path / "srgb.PRT"
    rip.process(str(source), str(actual), width_cm=1)
    rip.process(str(reference), str(expected), width_cm=1)
    assert actual.read_bytes() == expected.read_bytes()


def test_rip_rejeita_perfil_icc_embutido_invalido(tmp_path):
    source = tmp_path / "invalido.png"
    Image.new("RGB", (20, 20), "blue").save(source, icc_profile=b"perfil invalido")
    output = tmp_path / "invalido.PRT"
    with pytest.raises(ValueError, match="ICC.*entrada"):
        Rip(Settings(label_enabled=False)).process(str(source), str(output), width_cm=1)
    assert not output.exists()
    assert not list(tmp_path.glob("*.part"))



def test_perfil_rgb_embutido_preserva_alpha(tmp_path):
    from PIL import ImageCms
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    source = tmp_path / "alpha-icc.png"
    image = Image.new("RGBA", (12, 12), (80, 140, 200, 128))
    image.putpixel((0, 0), (200, 0, 0, 0))
    image.save(source, icc_profile=profile)
    with Image.open(source) as opened:
        converted = Rip(Settings())._source_rgba(opened)
        assert converted.mode == "RGBA"
        assert converted.getchannel("A").tobytes() == image.getchannel("A").tobytes()
        assert converted.getpixel((6, 6))[:3] == (80, 140, 200)


def test_perfil_incompativel_com_modo_da_arte_falha(tmp_path):
    from PIL import ImageCms
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("LAB")).tobytes()
    source = tmp_path / "perfil-incompativel.png"
    Image.new("RGB", (20, 20), "blue").save(source, icc_profile=profile)
    with pytest.raises(ValueError, match="ICC.*entrada"):
        Rip(Settings()).process(str(source), str(tmp_path / "nao-criar.PRT"), width_cm=1)

def test_etiqueta_nome_longo_nao_perde_final_com_dimensoes():
    settings = Settings(dpi_x=300, dpi_y=300, mirror=False)
    labels = Rip(settings)._make_labels("W" * 170 + ".png", 20, 10, 2362, 120, 100, 120)
    assert len(labels) == 2
    for _, _, pixels in labels:
        assert np.any(pixels[:, int(pixels.shape[1] * 0.8):])
        assert pixels.shape[1] <= 2362


def test_morfologia_nao_cria_emendas_entre_tiras(tmp_path, monkeypatch):
    # Pixels de entrada e saída 1:1 isolam a morfologia da reamostragem.
    image = Image.new("RGBA", (120, 900), (40, 100, 200, 255))
    alpha = np.full((900, 120), 255, dtype=np.uint8)
    alpha[490:540, 50:65] = 0
    alpha[100:800, :12] = 0
    image.putalpha(Image.fromarray(alpha))
    path = tmp_path / "seams.png"
    image.save(path)
    settings = Settings(dpi_x=300, dpi_y=2400, label_enabled=False,
                        margin_top_in=0, margin_bottom_in=0,
                        white_fill_holes_mm=.31, white_choke_mm=.11)
    rip = Rip(settings)
    rgba = rip._source_rgba(image)
    whole = rip._render(rgba, 0, 900, 0, 900, 120, [])[4]
    fill = int(np.ceil(settings.white_fill_holes_mm / 25.4 * settings.dpi_y))
    choke = int(np.ceil(settings.white_choke_mm / 25.4 * settings.dpi_y))
    halo = 2 * fill + choke + 2
    parts = []
    for start in range(0, 900, 137):
        end = min(start + 137, 900)
        a0, a1 = max(0, start-halo), min(900, end+halo)
        part = rip._render(rgba, a0, a1, 0, 900, 120, [])[4]
        parts.append(part[start-a0:end-a0])
    assert np.array_equal(np.concatenate(parts), whole)
