"""Regressoes dos previews locais, sem depender de impressora."""
import os

import pytest
import numpy as np
from PIL import Image, ImageOps

from autorip import server as server_module


def test_thumb_grava_jpeg_integro_em_ambas_as_pastas(app, sample_png):
    result = app._thumb("job-atomico", str(sample_png), output_name="pedido-001")
    assert result == "/api/thumb?id=job-atomico"

    root = os.path.join(app.home, "thumbs")
    paths = [
        os.path.join(root, "job-atomico.jpg"),
        os.path.join(root, "by_name", "pedido-001.jpg"),
    ]
    for path in paths:
        with Image.open(path) as preview:
            assert preview.format == "JPEG"
            preview.verify()
    assert not any(name.startswith(".thumb.") for name in os.listdir(root))
    assert not any(name.startswith(".thumb.") for name in os.listdir(os.path.join(root, "by_name")))


def test_falha_ao_gerar_thumbnail_preserva_arquivo_anterior(tmp_path, monkeypatch):
    target = tmp_path / "preview.jpg"
    original = b"preview anterior"
    target.write_bytes(original)

    def cannot_encode(*_args, **_kwargs):
        raise OSError("codificacao JPEG falhou")

    monkeypatch.setattr(Image.Image, "save", cannot_encode)
    with pytest.raises(OSError, match="JPEG falhou"):
        server_module._save_thumbnail_atomic(Image.new("RGB", (8, 8)), str(target))

    assert target.read_bytes() == original
    assert not list(tmp_path.glob(".thumb.*.part"))


def test_publicacao_jpeg_ocorre_apos_escrever_todo_temporario(tmp_path, monkeypatch):
    target = tmp_path / "preview.jpg"
    target.write_bytes(b"arquivo anterior")
    original_replace = server_module.os.replace
    observed = []

    def verify_before_replace(temporary, destination):
        if destination == str(target):
            assert target.read_bytes() == b"arquivo anterior"
            with Image.open(temporary) as preview:
                assert preview.format == "JPEG"
                preview.verify()
            observed.append(True)
        return original_replace(temporary, destination)

    monkeypatch.setattr(server_module.os, "replace", verify_before_replace)
    server_module._save_thumbnail_atomic(Image.new("RGB", (8, 8), "blue"), str(target))
    assert observed == [True]
    with Image.open(target) as preview:
        preview.verify()
    assert not list(tmp_path.glob(".thumb.*.part"))


def test_thumb_nao_escreve_em_diretorio_symlink(app, sample_png, tmp_path):
    root = os.path.join(app.home, "thumbs")
    target = tmp_path / "externo"
    target.mkdir()
    try:
        os.symlink(target, root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink indisponivel neste ambiente")

    assert app._thumb("nao-gravar", str(sample_png)) == ""
    assert not list(target.iterdir())


@pytest.mark.parametrize('mode,format', [('RGBA','PNG'),('RGB','PNG'),('LA','PNG'),('P','PNG'),
                                       ('RGB','JPEG'),('CMYK','JPEG'),('RGBA','TIFF'),('RGB','TIFF')])
@pytest.mark.parametrize('orientation', range(1,9))
def test_thumbnail_preserva_pixels_da_referencia_pillow(tmp_path,mode,format,orientation):
    pixels=np.random.default_rng(20261109).integers(0,256,(317,463,4),dtype=np.uint8)
    image=Image.fromarray(pixels,'RGBA').convert(mode)
    if mode=='P':image.info['transparency']=3
    exif=Image.Exif();exif[274]=orientation
    path=tmp_path/('input.'+format.lower())
    image.save(path,format=format,exif=exif)
    with Image.open(path) as original:
        reference=ImageOps.exif_transpose(original).convert('RGBA')
    reference.thumbnail((220,220))
    actual=server_module._load_thumbnail(path,(220,220))
    assert actual.size==reference.size
    assert np.array_equal(np.asarray(actual),np.asarray(reference))


def test_marca_preserva_regra_de_nao_aplicar_orientacao(tmp_path):
    path=tmp_path/'watermark.png'
    data=np.random.default_rng(78).integers(0,256,(320,400,4),dtype=np.uint8)
    exif=Image.Exif();exif[274]=6
    Image.fromarray(data,'RGBA').save(path,exif=exif)
    with Image.open(path) as source:reference=source.convert('RGBA')
    reference.thumbnail((110,110))
    actual=server_module._load_thumbnail(path,(110,110),orient=False)
    assert np.array_equal(np.asarray(actual),np.asarray(reference))


def test_duas_miniaturas_usam_uma_codificacao_e_os_mesmos_bytes(app,sample_png,monkeypatch):
    original=server_module._encode_thumbnail
    encoded=[]
    def record(image):
        value=original(image);encoded.append(value);return value
    monkeypatch.setattr(server_module,'_encode_thumbnail',record)
    assert app._thumb('one-encode',str(sample_png),output_name='one-encode-output')
    assert len(encoded)==1
    from pathlib import Path
    root=Path(app.home)/'thumbs'
    assert (root/'one-encode.jpg').read_bytes()==encoded[0]
    assert (root/'by_name'/'one-encode-output.jpg').read_bytes()==encoded[0]


@pytest.mark.parametrize('mode,fmt', [('RGB', 'PNG'), ('RGB', 'JPEG'), ('L', 'PNG'), ('L', 'JPEG')])
@pytest.mark.parametrize('orientation', [1, 2, 6, 8])
def test_previa_opaca_grande_preserva_filtro_e_reducao_em_duas_etapas(tmp_path, mode, fmt, orientation):
    shape = (1089, 1537, 3) if mode == 'RGB' else (1089, 1537)
    data = np.random.default_rng(321).integers(0, 256, shape, dtype=np.uint8)
    path = tmp_path / ('large.' + fmt.lower())
    exif = Image.Exif(); exif[274] = orientation
    with Image.fromarray(data, mode) as source:
        source.save(path, format=fmt, exif=exif)
    before = path.read_bytes()
    with Image.open(path) as source:
        expected = ImageOps.exif_transpose(source).convert('RGBA')
    expected.thumbnail((220, 197))
    actual = server_module._load_thumbnail(path, (220, 197))
    try:
        assert actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()
        assert path.read_bytes() == before
    finally:
        actual.close(); expected.close()


@pytest.mark.parametrize('mode', ['L', 'RGB'])
@pytest.mark.parametrize('orientation', [1, 6])
def test_chave_de_transparencia_grande_preserva_alfa(tmp_path, mode, orientation):
    shape = (1089, 1537, 3) if mode == 'RGB' else (1089, 1537)
    data = np.random.default_rng(312).integers(0, 256, shape, dtype=np.uint8)
    path = tmp_path / 'key.png'
    exif = Image.Exif(); exif[274] = orientation
    with Image.fromarray(data, mode) as source:
        source.save(path, exif=exif, transparency=(0, 0, 0) if mode == 'RGB' else 0)
    with Image.open(path) as source:
        expected = ImageOps.exif_transpose(source).convert('RGBA')
    expected.thumbnail((220, 197))
    actual = server_module._load_thumbnail(path, (220, 197))
    try:
        assert actual.size == expected.size and actual.tobytes() == expected.tobytes()
    finally:
        actual.close(); expected.close()


@pytest.mark.parametrize('mode,fmt', [('RGB', 'PNG'), ('RGBA', 'PNG'), ('CMYK', 'TIFF')])
@pytest.mark.parametrize('orientation', [1, 6])
def test_erro_na_previa_fecha_rasters_mesmo_com_traceback_retido(tmp_path, monkeypatch, mode, fmt, orientation):
    path = tmp_path / ('failed.' + fmt.lower())
    exif = Image.Exif(); exif[274] = orientation
    with Image.new(mode, (513, 769)) as source:
        source.save(path, format=fmt, exif=exif)
    tracked = []
    opened, transpose, convert = Image.open, ImageOps.exif_transpose, Image.Image.convert

    def track_open(*args, **kwargs):
        image = opened(*args, **kwargs); tracked.append(image); return image

    def track_transpose(*args, **kwargs):
        image = transpose(*args, **kwargs); tracked.append(image); return image

    def track_convert(*args, **kwargs):
        image = convert(*args, **kwargs); tracked.append(image); return image

    def fail(*args, **kwargs):
        raise RuntimeError('preview failure')

    monkeypatch.setattr(Image, 'open', track_open)
    monkeypatch.setattr(ImageOps, 'exif_transpose', track_transpose)
    monkeypatch.setattr(Image.Image, 'convert', track_convert)
    monkeypatch.setattr(Image.Image, 'thumbnail', fail)
    with pytest.raises(RuntimeError, match='preview failure') as retained:
        server_module._load_thumbnail(path, (220, 220))
    assert retained.value.__traceback__ is not None and tracked
    for image in tracked:
        with pytest.raises(ValueError, match='closed'):
            image.getpixel((0, 0))
