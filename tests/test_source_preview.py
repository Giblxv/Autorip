"""Reutilize o decode sem compartilhar pixels mutáveis nem publicar jobs incompletos."""
from pathlib import Path
import time

import numpy as np
from PIL import Image, ImageOps
import pytest

from autorip.config import Settings
from autorip.engine import Rip
from autorip import server
from conftest import wait_for_job
from test_source_rgba_transform import gamma_profile


@pytest.mark.parametrize('mode,format', [('RGB','PNG'), ('RGB','JPEG'), ('RGB','TIFF'),
                                      ('RGBA','PNG'), ('RGBA','TIFF'), ('L','PNG'),
                                      ('LA','PNG'), ('P','PNG'), ('CMYK','TIFF')])
@pytest.mark.parametrize('orientation', [1, 6, 8])
@pytest.mark.parametrize('size', [(72, 53), (1537, 1089)])
def test_previa_capturada_e_identica_a_leitura_independente(tmp_path, mode, format, orientation, size):
    data = np.random.default_rng(713).integers(0, 256, (size[1], size[0], 4), dtype=np.uint8)
    data[..., 3] = np.linspace(0, 255, size[0], dtype=np.uint8)[None, :]
    path = tmp_path / ('source.' + format.lower())
    exif = Image.Exif(); exif[274] = orientation
    with Image.fromarray(data, 'RGBA') as rgba:
        with rgba.convert(mode) as image:
            if mode == 'P':
                image.info['transparency'] = bytes(range(256))
            image.save(path, format=format, exif=exif)
    before = path.read_bytes()
    with Image.open(path) as source:
        source.load()
        with ImageOps.exif_transpose(source) as oriented:
            expected = oriented.convert('RGBA')
    expected.thumbnail((220, 197))
    preview = server._SourcePreview((220, 197))
    readonly = []
    def capture(source):
        readonly.append(bool(source.readonly))
        preview.capture(source)
    processed, *_ = Rip(Settings())._load_source(path, source_ready=capture)
    supported = mode in ('RGB', 'RGBA', 'L') and not readonly[0]
    actual = preview.image if supported else server._load_thumbnail(path, (220, 197))
    try:
        assert (preview.image is not None) == supported
        assert actual.mode == 'RGBA' and actual.size == expected.size
        assert actual.tobytes() == expected.tobytes()
        assert actual.im is not processed.im
        assert path.read_bytes() == before
        # A prévia não depende da vida útil nem das alterações futuras do RIP.
        processed.close()
        assert actual.tobytes() == expected.tobytes()
        path.rename(path.with_name('renamed.' + format.lower()))
    finally:
        processed.close(); preview.close(); actual.close(); expected.close()


@pytest.mark.parametrize('mode', ['RGB', 'RGBA'])
@pytest.mark.parametrize('size', [(72, 53), (769, 513)])
@pytest.mark.parametrize('orientation', [1, 6])
def test_previa_e_capturada_antes_do_icc_nao_identidade(tmp_path, mode, size, orientation):
    path = tmp_path / 'gamma.png'
    exif = Image.Exif(); exif[274] = orientation
    with Image.new(mode, size, (100, 150, 200, 127) if mode == 'RGBA' else (100, 150, 200)) as image:
        image.save(path, icc_profile=gamma_profile(), exif=exif)
    expected = server._load_thumbnail(path, (220, 220))
    preview = server._SourcePreview()
    processed, *_ = Rip(Settings())._load_source(path, source_ready=preview.capture)
    try:
        assert preview.image is not None and preview.image.tobytes() == expected.tobytes()
        assert processed.getpixel((0, 0))[:3] != (100, 150, 200)
        processed.putpixel((0, 0), (0, 0, 0, 0))
        assert preview.image.tobytes() == expected.tobytes()
    finally:
        preview.close(); processed.close(); expected.close()


@pytest.mark.parametrize('mode', ['RGB', 'RGBA', 'P', 'L', 'LA', 'CMYK'])
@pytest.mark.parametrize('size', [(72, 53), (769, 513)])
def test_wrapper_emprestado_nao_altera_nem_fecha_origem(mode, size):
    preview = server._SourcePreview()
    with Image.new(mode, size) as source:
        if mode == 'P':
            source.info['transparency'] = bytes(range(256))
        before, info, core = source.tobytes(), source.info.copy(), source.im
        preview.capture(source)
        assert source.im is core and source.size == size
        assert source.tobytes() == before and source.info == info
        if mode in ('P', 'LA', 'CMYK'):
            assert preview.image is None
            return
        assert preview.image is not None and preview.image.im is not source.im
        image = preview.take()
        preview.close()
        assert image.getpixel((0, 0)) is not None
        image.close()
        assert source.tobytes() == before


@pytest.mark.parametrize('mode', ['RGB', 'RGBA', 'L'])
def test_captura_nao_copia_raster_grande_antes_de_reduzir(monkeypatch, mode):
    original = Image.Image.copy
    source = Image.new(mode, (1537, 1089))
    def copy(image):
        assert image.size != source.size, 'Cópia de raster grande na captura'
        return original(image)
    monkeypatch.setattr(Image.Image, 'copy', copy)
    preview = server._SourcePreview()
    try:
        preview.capture(source)
        assert preview.image is not None and max(preview.image.size) == 220
        assert source.size == (1537, 1089) and source.getpixel((0, 0)) is not None
    finally:
        preview.close(); source.close()


@pytest.mark.parametrize('mode', ['RGB', 'L'])
def test_chave_de_cor_mantem_fallback_sem_expandir_durante_o_rip(mode):
    with Image.new(mode, (769, 513)) as source:
        source.info['transparency'] = (0, 0, 0) if mode == 'RGB' else 0
        preview = server._SourcePreview()
        preview.capture(source)
        assert preview.image is None and source.getpixel((0, 0)) is not None


@pytest.mark.parametrize('mode', ['RGB', 'RGBA', 'L'])
def test_raster_somente_leitura_mantem_previa_independente(mode):
    with Image.new(mode, (769, 513)) as source:
        source.readonly = 1
        before, core = source.tobytes(), source.im
        preview = server._SourcePreview()
        preview.capture(source)
        assert preview.image is None and source.readonly == 1
        assert source.im is core and source.tobytes() == before


@pytest.mark.parametrize('orientation', [1, 6])
def test_erro_no_observador_libera_origem_com_traceback_retido(tmp_path, monkeypatch, orientation):
    path = tmp_path / 'source.png'
    exif = Image.Exif(); exif[274] = orientation
    with Image.new('RGBA', (769, 513)) as image:
        image.save(path, exif=exif)
    tracked = []
    original = Image.open
    def opened(*args, **kwargs):
        image = original(*args, **kwargs); tracked.append(image); return image
    def fail(source):
        tracked.append(source)
        raise RuntimeError('observer failure')
    monkeypatch.setattr(Image, 'open', opened)
    with pytest.raises(RuntimeError, match='observer failure') as retained:
        Rip(Settings())._load_source(path, source_ready=fail)
    assert retained.value.__traceback__ is not None
    for image in tracked:
        with pytest.raises(ValueError, match='closed'):
            image.getpixel((0, 0))


def test_worker_nao_reabre_origem_para_previa(app, sample_png, monkeypatch):
    loaded = []
    original = server._load_thumbnail
    def load(path, *args, **kwargs):
        loaded.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(server, '_load_thumbnail', load)
    job = app.enqueue(str(sample_png), width_cm=2.54, move_to_done=False)
    wait_for_job(job)
    assert job['status'] == 'pronto' and job['thumb']
    assert str(sample_png) not in loaded
    root = Path(app.home) / 'thumbs'
    assert (root / (job['id'] + '.jpg')).read_bytes() == (root / 'by_name/amostra.jpg').read_bytes()


@pytest.mark.parametrize('mode', ['P', 'LA', 'CMYK'])
def test_worker_preserva_fallback_dos_modos_que_exigem_expansao(app, tmp_path, monkeypatch, mode):
    path = tmp_path / 'source.tiff'
    with Image.new(mode, (300, 200)) as source:
        source.save(path)
    loaded, original = [], server._load_thumbnail
    def load(path, *args, **kwargs):
        loaded.append(str(path))
        return original(path, *args, **kwargs)
    monkeypatch.setattr(server, '_load_thumbnail', load)
    job = app.enqueue(str(path), width_cm=2.54, move_to_done=False)
    wait_for_job(job)
    assert job['status'] == 'pronto' and job['thumb']
    assert loaded.count(str(path)) == 1


def test_falha_opcional_na_captura_usa_leitura_habitual(app, sample_png, monkeypatch):
    original, calls = Image.Image.thumbnail, []
    def fail_once(image, *args, **kwargs):
        calls.append(image)
        if len(calls) == 1:
            raise RuntimeError('optional preview failure')
        return original(image, *args, **kwargs)
    monkeypatch.setattr(Image.Image, 'thumbnail', fail_once)
    job = app.enqueue(str(sample_png), width_cm=2.54, move_to_done=False)
    wait_for_job(job)
    assert job['status'] == 'pronto' and job['thumb'] and len(calls) == 2
    with pytest.raises(ValueError, match='closed'):
        calls[0].getpixel((0, 0))


@pytest.mark.parametrize('failure,status', [(server.JobPaused, 'pausado'),
                                          (server.JobCancelled, 'cancelado'),
                                          (ValueError, 'erro')])
def test_worker_libera_previa_se_rip_nao_concluir(app, sample_png, monkeypatch, failure, status):
    images = []
    original = server._SourcePreview.capture
    def capture(holder, source):
        original(holder, source)
        assert holder.image is not None
        images.append(holder.image)
    def fail(*args, **kwargs):
        with Image.new('RGBA', (72, 53), (100, 150, 200, 127)) as source:
            kwargs['source_ready'](source)
        raise failure('injected failure')
    monkeypatch.setattr(server._SourcePreview, 'capture', capture)
    monkeypatch.setattr(app.rip, 'process', fail)
    job = app.enqueue(str(sample_png), width_cm=2.54, move_to_done=False)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and job['status'] != status:
        time.sleep(.05)
    assert job['status'] == status and len(images) == 1
    with pytest.raises(ValueError, match='closed'):
        images[0].getpixel((0, 0))
    assert not (Path(app.home) / 'thumbs').exists()
    assert not list(Path(app.s.output_folder).glob('*.PRT'))


def test_falha_na_publicacao_fecha_previa_recebida(app, sample_png, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('JPEG publication failure')
    monkeypatch.setattr(server, '_encode_thumbnail', fail)
    prepared = Image.new('RGBA', (72, 53), (100, 150, 200, 127))
    assert app._thumb('failed', str(sample_png), prepared=prepared) == ''
    with pytest.raises(ValueError, match='closed'):
        prepared.getpixel((0, 0))
