"""Posse dos rasters grandes: não escrever em mmap nem retê-los em tracebacks."""
from types import SimpleNamespace

from PIL import Image, ImageCms
import pytest

from autorip import engine
from autorip.config import Settings
from test_source_icc_cache import image_with_profile, original_rgba
from test_source_rgba_transform import gamma_profile


@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('readonly', [False, True])
def test_reuso_rgba_exige_buffer_mutavel_e_pedido_explicito(icc, readonly):
    source = Image.new('RGBA', (37, 23), (100, 150, 200, 127))
    if icc:
        source.info['icc_profile'] = gamma_profile()
    source.readonly = readonly
    rip = engine.Rip(Settings())
    expected = original_rgba(source, rip.s) if icc else source.copy()
    before = source.tobytes()
    actual = rip._source_rgba(source, in_place=True)
    try:
        assert actual.tobytes() == expected.tobytes()
        assert (actual is source) == (not readonly)
        if readonly:
            assert source.tobytes() == before
    finally:
        actual.close(); source.close(); expected.close()


@pytest.mark.parametrize('orientation', [1, 6])
@pytest.mark.parametrize('icc', [False, True])
def test_carregador_fecha_arquivo_e_mantem_so_o_raster_entregue(tmp_path, monkeypatch, orientation, icc):
    path = tmp_path / 'source.png'
    with Image.new('RGBA', (37, 23), (100, 150, 200, 127)) as image:
        exif = Image.Exif(); exif[274] = orientation
        image.save(path, exif=exif, icc_profile=gamma_profile() if icc else b'')
    before = path.read_bytes()
    tracked = []
    opened, transpose = engine.Image.open, engine.ImageOps.exif_transpose

    def capture_open(*args, **kwargs):
        image = opened(*args, **kwargs); tracked.append(image); return image

    def capture_transpose(*args, **kwargs):
        image = transpose(*args, **kwargs); tracked.append(image); return image

    monkeypatch.setattr(engine.Image, 'open', capture_open)
    monkeypatch.setattr(engine.ImageOps, 'exif_transpose', capture_transpose)
    result, *_ = engine.Rip(Settings())._load_source(path)
    try:
        assert result.getpixel((0, 0))[3] == 127
        assert result is tracked[-1]
        assert tracked[0].fp is None
        for image in tracked:
            if image is not result:
                with pytest.raises(ValueError, match='closed'):
                    image.getpixel((0, 0))
        # A alteração ICC in-place é apenas no buffer privado decodificado.
        assert path.read_bytes() == before
        renamed = path.with_name('renamed.png')
        path.rename(renamed)
        assert renamed.read_bytes() == before
    finally:
        result.close()


@pytest.mark.parametrize('icc', [False, True])
def test_tiff_mapeado_nao_e_alterado_e_pode_ser_movido(tmp_path, icc):
    path = tmp_path / 'mapped.tif'
    with Image.new('RGBA', (79, 51), (100, 150, 200, 127)) as image:
        image.save(path, compression='raw', icc_profile=gamma_profile() if icc else b'')
    before = path.read_bytes()
    result, *_ = engine.Rip(Settings())._load_source(path)
    try:
        assert result.getpixel((0, 0))[3] == 127 and path.read_bytes() == before
        path.rename(tmp_path / 'moved.tif')
        assert (tmp_path / 'moved.tif').read_bytes() == before
    finally:
        result.close()
@pytest.mark.parametrize('mode', ['RGB', 'RGBX', 'LAB', 'CMYK'])
def test_falha_ao_definir_alpha_opaco_libera_saida_cms(tmp_path, monkeypatch, mode):
    source = image_with_profile('RGB' if mode == 'RGBX' else mode)
    if mode == 'RGBX':
        converted = source.convert('RGBX'); source.close(); source = converted
    outputs = []
    apply = ImageCms.applyTransform

    def tracked(*args, **kwargs):
        result = apply(*args, **kwargs); outputs.append(result); return result

    def fail(*args, **kwargs):
        raise RuntimeError('alpha failure')

    monkeypatch.setattr(ImageCms, 'applyTransform', tracked)
    monkeypatch.setattr(Image.Image, 'putalpha', fail)
    try:
        with pytest.raises(ValueError, match='alpha failure') as retained:
            engine.Rip(Settings())._source_rgba(source)
        assert retained.value.__traceback__ is not None and len(outputs) == 1
        with pytest.raises(ValueError, match='closed'):
            outputs[0].getpixel((0, 0))
        assert source.getpixel((0, 0)) is not None
    finally:
        source.close()


@pytest.mark.parametrize('failure', ['geometry', 'disk', 'prepare', 'render', 'publish', None])
def test_process_fecha_raster_final_inclusive_com_traceback_retido(sample_png, tmp_path, monkeypatch, failure):
    rip = engine.Rip(Settings(dpi_x=72, dpi_y=72, label_enabled=False))
    tracked = []
    load, prepare = rip._load_source, rip._prepare_resampling

    def track_load(*args, **kwargs):
        values = load(*args, **kwargs); tracked.append(values[0]); return values

    def track_prepare(*args):
        image = prepare(*args); tracked.append(image); return image

    def fail(*args, **kwargs):
        raise RuntimeError('pipeline failure')

    monkeypatch.setattr(rip, '_load_source', track_load)
    monkeypatch.setattr(rip, '_prepare_resampling', fail if failure == 'prepare' else track_prepare)
    if failure == 'disk':
        monkeypatch.setattr(engine.shutil, 'disk_usage', lambda path: SimpleNamespace(free=0))
    elif failure == 'render':
        monkeypatch.setattr(rip, '_render', fail)
    target = tmp_path / 'output.PRT'
    arguments = dict(width_cm=-1 if failure == 'geometry' else 2.54,
                     before_publish=fail if failure == 'publish' else None)
    if failure:
        with pytest.raises((ValueError, RuntimeError)) as retained:
            rip.process(str(sample_png), str(target), **arguments)
        assert retained.value.__traceback__ is not None
        assert not target.exists()
    else:
        rip.process(str(sample_png), str(target), **arguments)
        assert target.exists()
    assert tracked and not list(tmp_path.glob('*.part'))
    for image in tracked:
        with pytest.raises(ValueError, match='closed'):
            image.getpixel((0, 0))
