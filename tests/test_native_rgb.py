"""RGB opaco mantém cor, posse e PRTs sem expandir o raster inteiro para RGBA."""
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from autorip import engine
from autorip.config import Settings
from test_source_rgba_transform import gamma_profile


def make_rgb(path, *, icc=False, orientation=1):
    pixels = np.random.default_rng(510).integers(0, 256, (61, 79, 3), dtype=np.uint8)
    image = Image.fromarray(pixels, 'RGB')
    exif = Image.Exif(); exif[274] = orientation
    try:
        image.save(path, exif=exif, dpi=(300, 300),
                   icc_profile=gamma_profile() if icc else b'')
    finally:
        image.close()


@pytest.mark.parametrize('extension', ['png', 'jpg', 'tif'])
@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('orientation', [1, 6])
@pytest.mark.parametrize('readonly', [False, True])
def test_native_rgb_keeps_pixels_and_file_ownership(tmp_path, monkeypatch, extension, icc, orientation, readonly):
    path = tmp_path / ('source.' + extension)
    make_rgb(path, icc=icc, orientation=orientation)
    original_bytes = path.read_bytes()
    rip = engine.Rip(Settings())
    expected, *old_metadata = rip._load_source(path)
    converted = expected.convert('RGB')
    opened = []
    real_open = engine.Image.open

    def tracked_open(*args, **kwargs):
        image = real_open(*args, **kwargs)
        opened.append(image)
        return image

    seen = {}
    def before_icc(source):
        source.readonly = readonly
        seen.update(core_id=id(source.im), pixels=source.tobytes(), mode=source.mode)

    monkeypatch.setattr(engine.Image, 'open', tracked_open)
    actual, *new_metadata = rip._load_source(path, source_ready=before_icc, native_opaque=True)
    try:
        assert actual.mode == 'RGB' and new_metadata == old_metadata
        assert actual.tobytes() == converted.tobytes()
        assert (id(actual.im) == seen['core_id']) == (not readonly)
        assert seen['mode'] == 'RGB' and opened[0].fp is None
        # O wrapper entregue não depende do objeto ImageFile nem do arquivo.
        for image in opened:
            with pytest.raises(ValueError, match='closed'):
                image.getpixel((0, 0))
        renamed = path.with_name('moved.' + extension)
        path.rename(renamed)
        assert renamed.read_bytes() == original_bytes
        assert actual.tobytes() == converted.tobytes()
    finally:
        actual.close(); converted.close(); expected.close()


def test_rgb_and_rgba_transforms_do_not_share_an_incompatible_cache_entry():
    source = Image.new('RGB', (79, 61), (100, 150, 200))
    source.info['icc_profile'] = gamma_profile()
    original = source.tobytes()
    rip = engine.Rip(Settings())
    try:
        for _ in range(3):
            rgba = rip._source_rgba(source)
            rgb = rip._source_rgb(source)
            expanded = rgb.convert('RGBA')
            try:
                assert rgb.mode == 'RGB' and rgba.mode == 'RGBA'
                assert expanded.tobytes() == rgba.tobytes()
                assert source.tobytes() == original
            finally:
                expanded.close(); rgba.close(); rgb.close()
    finally:
        source.close()


@pytest.mark.parametrize('kind', ['color-key', 'rgba', 'palette'])
def test_non_native_modes_keep_rgba_and_transparency(tmp_path, kind):
    path = tmp_path / 'source.png'
    if kind == 'color-key':
        image = Image.new('RGB', (7, 5), (1, 2, 3))
        image.info['transparency'] = (1, 2, 3)
    elif kind == 'rgba':
        image = Image.new('RGBA', (7, 5), (1, 2, 3, 127))
    else:
        image = Image.new('P', (7, 5), 0)
        image.info['transparency'] = 0
    try:
        image.save(path)
    finally:
        image.close()
    rip = engine.Rip(Settings())
    expected, *_ = rip._load_source(path)
    actual, *_ = rip._load_source(path, native_opaque=True)
    try:
        assert actual.mode == 'RGBA' and actual.tobytes() == expected.tobytes()
    finally:
        actual.close(); expected.close()


@pytest.mark.parametrize('icc', [False, True])
@pytest.mark.parametrize('orientation', [1, 6])
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('width', [None, 1.27])
@pytest.mark.parametrize('output_icc', [False, True])
def test_native_rgb_prt_matches_canonical_rgba_path(tmp_path, icc, orientation, mirror, width, output_icc):
    path = tmp_path / 'source.png'
    make_rgb(path, icc=icc, orientation=orientation)
    profile = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
    settings = Settings(dpi_x=300, dpi_y=300, label_enabled=True,
                        mirror=mirror, margin_top_in=.12, margin_bottom_in=.12,
                        icc_path=str(profile) if output_icc else '',
                        channel_order=['M', 'Y', 'K', 'C'], white_planes=[4, 7])
    baseline = engine.Rip(settings)
    load = baseline._load_source
    # O hook legado exerce a conversão RGBA anterior, sem entrar no atalho nativo.
    baseline._load_source = lambda source: load(source)
    old = baseline.process(str(path), str(tmp_path / 'old.PRT'), width_cm=width)
    actual = engine.Rip(settings).process(str(path), str(tmp_path / 'new.PRT'), width_cm=width)
    assert (tmp_path / 'old.PRT').read_bytes() == (tmp_path / 'new.PRT').read_bytes()
    assert {k: v for k, v in old.items() if k != 'output_path'} == {k: v for k, v in actual.items() if k != 'output_path'}
