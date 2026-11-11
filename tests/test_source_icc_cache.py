"""Perfis de entrada reutilizados devem preservar a conversão anterior e isolar threads."""
from concurrent.futures import ThreadPoolExecutor
import gc
import io
from pathlib import Path
import threading
import weakref

import numpy as np
from PIL import Image, ImageCms
import pytest

from autorip import engine
from autorip.config import Settings


def original_rgba(source, settings):
    profile = ImageCms.ImageCmsProfile(io.BytesIO(source.info['icc_profile']))
    color = source.convert('RGB') if source.mode in ('RGBA','P','PA') else source.getchannel('L') if source.mode == 'LA' else source
    flags = ImageCms.Flags.BLACKPOINTCOMPENSATION if settings.black_point_comp else 0
    rgb = ImageCms.profileToProfile(color, profile, ImageCms.createProfile('sRGB'), outputMode='RGB',
                                   renderingIntent=settings.intent, flags=flags)
    rgba = rgb.convert('RGBA')
    if source.mode in ('RGBA','LA','PA') or 'transparency' in source.info:
        rgba.putalpha(source.convert('RGBA').getchannel('A'))
    return rgba


def image_with_profile(mode='RGB', variant=0):
    pixels = np.random.default_rng(104).integers(0,256,(29,37,4),dtype=np.uint8)
    image = Image.fromarray(pixels,'RGBA')
    if mode == 'CMYK':
        path = Path(__file__).resolve().parents[1] / 'Sublinks_DTF_E602 LM720x2400 8Pass .icc'
        if not path.is_file():pytest.skip('Perfil de avaliação local não está disponível')
        profile = ImageCms.getOpenProfile(str(path))
        image = ImageCms.profileToProfile(image.convert('RGB'),ImageCms.createProfile('sRGB'),profile,outputMode='CMYK')
    else:
        profile = ImageCms.createProfile('LAB' if mode == 'LAB' else 'sRGB')
    if mode == 'LAB':
        image = ImageCms.profileToProfile(image.convert('RGB'),ImageCms.createProfile('sRGB'),profile,outputMode='LAB')
    elif mode == 'P':
        image = image.convert('P')
        image.info['transparency'] = 0
    elif mode not in ('RGBA','CMYK'):
        image = image.convert(mode)
    wrapper = profile if isinstance(profile,ImageCms.ImageCmsProfile) else ImageCms.ImageCmsProfile(profile)
    embedded = bytearray(wrapper.tobytes())
    # Somente a data do perfil muda; as tabelas de cor continuam válidas.
    embedded[24:26] = (2020 + variant).to_bytes(2,'big')
    image.info['icc_profile'] = bytes(embedded)
    return image


def count_builds(monkeypatch):
    builds = []
    original = engine.Rip._build_source_transform
    def build(*args):
        builds.append(args)
        return original(*args)
    monkeypatch.setattr(engine.Rip,'_build_source_transform',staticmethod(build))
    return builds


@pytest.mark.parametrize('mode',['RGB','RGBA','P','LAB','CMYK'])
@pytest.mark.parametrize('intent',range(4))
@pytest.mark.parametrize('bpc',[False,True])
def test_cache_frio_quente_preserva_pixels_e_prt(tmp_path,mode,intent,bpc):
    settings = Settings(dpi_x=300,dpi_y=600,label_enabled=True,margin_top_in=.12,
                        margin_bottom_in=.12,intent=intent,black_point_comp=bpc,
                        channel_order=['M','Y','K','C'],white_planes=[4,7])
    image = image_with_profile(mode)
    rip = engine.Rip(settings)
    expected = original_rgba(image,settings)
    for _ in range(2):
        actual = rip._source_rgba(image)
        assert actual.tobytes() == expected.tobytes()
        actual.close()
    expected.close()
    path = tmp_path / ('source.tif' if mode in ('LAB','CMYK') else 'source.png')
    image.save(path,icc_profile=image.info['icc_profile'],dpi=(100,200))
    image.close()
    reference = engine.Rip(settings)
    reference._source_rgba = lambda source, **kwargs: original_rgba(source,settings)
    baseline = reference.process(str(path),str(tmp_path/'old.PRT'),.75)
    for index in range(2):
        output = tmp_path / f'new-{index}.PRT'
        info = rip.process(str(path),str(output),.75)
        assert output.read_bytes() == (tmp_path/'old.PRT').read_bytes()
        assert {k:v for k,v in info.items() if k!='output_path'} == {k:v for k,v in baseline.items() if k!='output_path'}


def test_cache_separa_rgb_rgba_e_reutiliza_cada_formato_sem_alterar_alpha(monkeypatch):
    builds = count_builds(monkeypatch)
    rip = engine.Rip(Settings())
    rgb, rgba = image_with_profile(), image_with_profile('RGBA')
    rgba.info['icc_profile'] = rgb.info['icc_profile']
    for image in (rgb,rgba,rgb,rgba):
        result = rip._source_rgba(image)
        expected = original_rgba(image,rip.s)
        assert result.tobytes() == expected.tobytes()
        result.close();expected.close()
    assert len(builds) == 2
    assert {args[1] for args in builds} == {'RGB', 'RGBA'}
    rgb.close();rgba.close()


@pytest.mark.parametrize('bound',['entries','bytes'])
def test_lru_evita_crescimento_e_preserva_perfis_mais_usados(monkeypatch,bound):
    images = [image_with_profile(variant=i) for i in range(3)]
    if bound == 'entries':
        monkeypatch.setattr(engine,'MAX_SOURCE_TRANSFORMS',2)
    else:
        monkeypatch.setattr(engine,'MAX_SOURCE_PROFILE_BYTES',len(images[0].info['icc_profile'])*2)
    builds = count_builds(monkeypatch)
    rip = engine.Rip(Settings())
    for index in (0,1,0,2,1):
        rip._source_rgba(images[index]).close()
    assert len(builds) == 4  # A volta de 0 era hit; 1 precisou ser reconstruído após a expulsão.
    assert len(rip._source_transforms.cache) == 2
    assert rip._source_transforms.profile_bytes <= engine.MAX_SOURCE_PROFILE_BYTES
    for image in images:image.close()


def test_perfil_maior_que_orcamento_continua_funcionando_sem_cache(monkeypatch):
    image = image_with_profile('LAB')
    monkeypatch.setattr(engine,'MAX_SOURCE_PROFILE_BYTES',len(image.info['icc_profile'])-1)
    builds = count_builds(monkeypatch)
    rip = engine.Rip(Settings())
    for _ in range(2):
        result = rip._source_rgba(image)
        expected = original_rgba(image,rip.s)
        assert result.tobytes()==expected.tobytes()
        result.close();expected.close()
    assert len(builds)==2 and not hasattr(rip._source_transforms,'cache')
    image.close()


def test_chave_inclui_intencao_bpc_e_conteudo_do_perfil(monkeypatch):
    images = [image_with_profile('LAB',variant=i) for i in range(2)]
    builds = count_builds(monkeypatch)
    rip = engine.Rip(Settings())
    for intent,bpc,index in [(1,True,0),(0,True,0),(0,False,0),(0,False,1),(1,True,0)]:
        rip.s.intent,rip.s.black_point_comp = intent,bpc
        result = rip._source_rgba(images[index]);expected = original_rgba(images[index],rip.s)
        assert result.tobytes()==expected.tobytes()
        result.close();expected.close()
    assert len(builds)==4
    for image in images:image.close()


def test_perfil_invalido_e_modo_incompativel_nao_reutilizam_transformacao_valida(monkeypatch):
    builds = count_builds(monkeypatch)
    image = image_with_profile();embedded=image.info['icc_profile']
    rip = engine.Rip(Settings())
    rip._source_rgba(image).close()
    image.info['icc_profile']=b'invalid profile'
    for _ in range(2):
        with pytest.raises(ValueError,match='ICC.*entrada'):rip._source_rgba(image)
    gray=image.convert('LA');gray.info['icc_profile']=embedded
    with pytest.raises(ValueError,match='ICC.*entrada'):rip._source_rgba(gray)
    image.info['icc_profile']=embedded
    rip._source_rgba(image).close()
    assert len(builds)==4 and len(rip._source_transforms.cache)==1
    image.close();gray.close()


@pytest.mark.parametrize('mode', ['LAB', 'RGBA'])
def test_threads_nao_compartilham_transformacoes_e_liberam_cache_ao_sair(monkeypatch, mode):
    rip = engine.Rip(Settings())
    original_build=engine.Rip._build_source_transform
    original_apply=ImageCms.applyTransform
    owners, references = {},[]
    lock=threading.Lock();barrier=threading.Barrier(2)
    def build(*args):
        transform=original_build(*args)
        with lock:
            owners[id(transform)]=threading.get_ident()
            references.append(weakref.ref(transform))
        return transform
    def apply(image,transform,*args,**kwargs):
        assert owners[id(transform)]==threading.get_ident()
        return original_apply(image,transform,*args,**kwargs)
    monkeypatch.setattr(engine.Rip,'_build_source_transform',staticmethod(build))
    monkeypatch.setattr(ImageCms,'applyTransform',apply)
    def work(index):
        image=image_with_profile(mode)
        try:
            barrier.wait(timeout=10)
            values=[]
            for _ in range(3):
                result=rip._source_rgba(image);values.append(result.tobytes());result.close()
            return values
        finally:image.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(work,range(2)))
    assert len(references)==2 and len({v for group in values for v in group})==1
    gc.collect()
    assert all(ref() is None for ref in references)


def test_arte_sem_icc_nao_cria_cache(monkeypatch):
    def forbid(*args):pytest.fail('Transformação ICC consultada sem perfil')
    monkeypatch.setattr(engine.Rip,'_source_transform',forbid)
    image=Image.new('RGBA',(5,7),(40,120,200,127));rip=engine.Rip(Settings())
    result=rip._source_rgba(image)
    assert result.tobytes()==image.tobytes() and not hasattr(rip._source_transforms,'cache')
    image.close();result.close()
