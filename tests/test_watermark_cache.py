"""Pré-processamento de marcas: mesmos JPEGs, identidade de arquivo e buffers isolados."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import subprocess
import sys
import threading
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from autorip import server
from autorip.config import Settings
from autorip import watermarks


def write_mark(path, color=(230,40,70,127)):
    image=Image.new('RGBA',(64,48),color);image.save(path);image.close()


def counted_loader():
    calls=[]
    def load(source,bounds,**kwargs):
        calls.append(True)
        return server._load_thumbnail(source,bounds,**kwargs)
    return calls,load


@pytest.mark.parametrize('mode,fmt',[('RGBA','PNG'),('RGB','PNG'),('LA','PNG'),('P','PNG'),
                                    ('RGB','JPEG'),('CMYK','JPEG'),('RGBA','TIFF'),('RGB','TIFF')])
@pytest.mark.parametrize('orientation',[1,3,6,8])
@pytest.mark.parametrize('opacity',[0,.35,1])
def test_cache_frio_quente_preserva_jpeg_alpha_formato_e_regra_exif(tmp_path,mode,fmt,orientation,opacity):
    source=tmp_path/'art.png';Image.new('RGBA',(160,120),(20,130,210,150)).save(source)
    pixels=np.random.default_rng(20261110).integers(0,256,(151,203,4),dtype=np.uint8)
    image=Image.fromarray(pixels,'RGBA').convert(mode)
    if mode=='P':image.info['transparency']=3
    exif=Image.Exif();exif[274]=orientation
    mark=tmp_path/'mark.image';image.save(mark,format=fmt,exif=exif);image.close()
    settings=Settings(watermark_path=str(mark),watermark_opacity=opacity)
    reference=SimpleNamespace(home=str(tmp_path/'old'),s=settings)
    candidate=SimpleNamespace(home=str(tmp_path/'new'),s=settings,_watermark_cache=watermarks.WatermarkCache())
    assert server.App._thumb(reference,'ref',str(source))
    expected=(tmp_path/'old/thumbs/ref.jpg').read_bytes()
    for index in range(2):
        assert server.App._thumb(candidate,f'new-{index}',str(source))
        assert (tmp_path/f'new/thumbs/new-{index}.jpg').read_bytes()==expected
    assert len(candidate._watermark_cache._images)==1


def test_copias_independentes_e_evicao_nao_invalidam_consumidor(tmp_path,monkeypatch):
    monkeypatch.setattr(watermarks,'MAX_WATERMARK_CACHE_ENTRIES',1)
    first,second=tmp_path/'first.png',tmp_path/'second.png';write_mark(first);write_mark(second,(20,140,220,127))
    cache=watermarks.WatermarkCache();calls,loader=counted_loader()
    image=cache.get(first,(16,16),loader);original=image.tobytes()
    saved=next(iter(cache._images.values()))[0]
    image.putpixel((0,0),(0,0,0,0))
    again=cache.get(first,(16,16),loader)
    assert again.tobytes()==original and len(calls)==1
    cache.get(second,(16,16),loader).close()
    with pytest.raises(ValueError,match='closed'):saved.getpixel((0,0))
    assert again.tobytes()==original
    image.close();again.close()


def test_opacidade_e_aplicada_a_copia_sem_recarregar_marca(tmp_path,monkeypatch):
    source,mark=tmp_path/'art.png',tmp_path/'mark.png';write_mark(source);write_mark(mark)
    settings=Settings(watermark_path=str(mark),watermark_opacity=.2)
    app=SimpleNamespace(home=str(tmp_path/'cached'),s=settings,_watermark_cache=watermarks.WatermarkCache())
    original=server._load_thumbnail;calls=[]
    def load(*args,**kwargs):
        if kwargs.get('orient') is False:calls.append(True)
        return original(*args,**kwargs)
    monkeypatch.setattr(server,'_load_thumbnail',load)
    values=[]
    for index,opacity in enumerate([.2,.8]):
        settings.watermark_opacity=opacity
        assert server.App._thumb(app,str(index),str(source))
        values.append((tmp_path/f'cached/thumbs/{index}.jpg').read_bytes())
    assert len(calls)==1 and values[0]!=values[1]


@pytest.mark.parametrize('replace',[False,True])
def test_marca_modificada_ou_substituida_invalida_cache(tmp_path,replace):
    path=tmp_path/'mark.png';write_mark(path)
    cache=watermarks.WatermarkCache();calls,loader=counted_loader()
    first=cache.get(path,(16,16),loader);before=first.tobytes();first.close();info=path.stat()
    if replace:
        other=tmp_path/'new.png';write_mark(other,(10,150,240,127))
        os.utime(other,ns=(info.st_atime_ns,info.st_mtime_ns));os.replace(other,path)
    else:
        write_mark(path,(10,150,240,127));os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1_000_000_000))
    second=cache.get(path,(16,16),loader)
    assert second.tobytes()!=before and len(calls)==2
    second.close()


def test_remover_marca_nao_reutiliza_pixels_antigos(tmp_path):
    path=tmp_path/'mark.png';write_mark(path)
    cache=watermarks.WatermarkCache();_,loader=counted_loader()
    cache.get(path,(16,16),loader).close();path.unlink()
    with pytest.raises(FileNotFoundError):cache.get(path,(16,16),loader)


def test_link_para_marca_trocado_nao_reutiliza_alvo_antigo(tmp_path):
    first,second,link=tmp_path/'first.png',tmp_path/'second.png',tmp_path/'mark-link.png'
    write_mark(first);write_mark(second,(20,140,230,190))
    try:os.symlink(first,link)
    except (OSError,NotImplementedError):pytest.skip('Symlink indisponível')
    cache=watermarks.WatermarkCache();calls,loader=counted_loader()
    old=cache.get(link,(16,16),loader);before=old.tobytes();old.close()
    link.unlink();os.symlink(second,link)
    current=cache.get(link,(16,16),loader)
    assert current.tobytes()!=before and len(calls)==2
    current.close()


def test_alteracao_durante_decode_nao_entra_no_cache(tmp_path):
    path=tmp_path/'mark.png';write_mark(path)
    cache=watermarks.WatermarkCache();original=server._load_thumbnail
    def changed(source,bounds,**kwargs):
        image=original(source,bounds,**kwargs);info=path.stat()
        os.utime(path,ns=(info.st_atime_ns,info.st_mtime_ns+1_000_000_000))
        return image
    cache.get(path,(16,16),changed).close()
    assert not cache._images and cache._bytes==0
    cache.get(path,(16,16),original).close()
    assert len(cache._images)==1


@pytest.mark.parametrize('limit',['entries','bytes'])
def test_cache_lru_limitado_por_entradas_e_payload(tmp_path,monkeypatch,limit):
    marks=[tmp_path/f'{i}.png' for i in range(3)]
    for path in marks:write_mark(path)
    # 16 × 12 pixels RGBA por miniatura.
    if limit=='entries':monkeypatch.setattr(watermarks,'MAX_WATERMARK_CACHE_ENTRIES',2)
    else:monkeypatch.setattr(watermarks,'MAX_WATERMARK_CACHE_BYTES',16*12*4*2)
    cache=watermarks.WatermarkCache();calls,loader=counted_loader()
    for index in [0,1,0,2,1]:cache.get(marks[index],(16,16),loader).close()
    assert len(calls)==4 and len(cache._images)==2
    assert cache._bytes<=watermarks.MAX_WATERMARK_CACHE_BYTES


def test_marca_preparada_acima_do_orcamento_continua_funcionando(tmp_path,monkeypatch):
    path=tmp_path/'mark.png';write_mark(path)
    monkeypatch.setattr(watermarks,'MAX_WATERMARK_CACHE_BYTES',1)
    cache=watermarks.WatermarkCache();calls,loader=counted_loader()
    for _ in range(2):cache.get(path,(16,16),loader).close()
    assert len(calls)==2 and not cache._images and cache._bytes==0


def test_expiracao_independe_de_metadados_e_nao_estende_vida_em_hits(tmp_path,monkeypatch):
    path=tmp_path/'mark.png';write_mark(path)
    clock=[10.0];monkeypatch.setattr(watermarks,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    cache=watermarks.WatermarkCache();calls,loader=counted_loader()
    cache.get(path,(16,16),loader).close()
    clock[0]=69;cache.get(path,(16,16),loader).close();assert len(calls)==1
    clock[0]=70;cache.get(path,(16,16),loader).close();assert len(calls)==2


def test_metadados_grandes_nao_ficam_retidos_no_payload(tmp_path):
    path=tmp_path/'mark.png';write_mark(path)
    def load(*args,**kwargs):
        image=server._load_thumbnail(*args,**kwargs)
        image.info.update(icc_profile=b'x'*2_000_000,exif=b'x'*300_000)
        return image
    cache=watermarks.WatermarkCache();result=cache.get(path,(16,16),load)
    stored=next(iter(cache._images.values()))[0]
    assert result.info==stored.info=={} and cache._bytes==16*12*4
    result.close()


def test_falha_do_loader_nao_deixa_entrada_invalida(tmp_path):
    path=tmp_path/'mark.png';write_mark(path);seen=[]
    def fail(source,*args,**kwargs):
        seen.append(source);raise ValueError('decode simulado')
    cache=watermarks.WatermarkCache()
    with pytest.raises(ValueError,match='simulado'):cache.get(path,(16,16),fail)
    assert seen and not cache._images and cache._bytes==0
    cache.get(path,(16,16),server._load_thumbnail).close()


def test_decodes_simultaneos_retornam_copias_e_contam_uma_entrada(tmp_path):
    path=tmp_path/'mark.png';write_mark(path)
    cache=watermarks.WatermarkCache();barrier=threading.Barrier(2)
    def load(*args,**kwargs):
        barrier.wait(timeout=10);return server._load_thumbnail(*args,**kwargs)
    with ThreadPoolExecutor(max_workers=2) as pool:
        images=list(pool.map(lambda _:cache.get(path,(16,16),load),range(2)))
    original=images[0].tobytes();images[0].putpixel((0,0),(0,0,0,0))
    assert images[1].tobytes()==original and len(cache._images)==1 and cache._bytes==16*12*4
    cache.get(path,(16,16),server._load_thumbnail).close()
    for image in images:image.close()


def test_bounds_distintos_nao_reutilizam_geometria_errada(tmp_path):
    path=tmp_path/'mark.png';write_mark(path)
    cache=watermarks.WatermarkCache();calls,loader=counted_loader()
    first=cache.get(path,(16,16),loader);second=cache.get(path,(32,32),loader)
    assert first.size==(16,12) and second.size==(32,24) and len(calls)==2
    first.close();second.close()


@pytest.mark.skipif(not hasattr(os,'mkfifo'),reason='FIFO não existe nesta plataforma')
def test_fifo_e_recusado_sem_bloquear_worker(tmp_path):
    path=tmp_path/'fifo';os.mkfifo(path)
    code="""import sys
from autorip.watermarks import WatermarkCache
try:
    WatermarkCache().get(sys.argv[1],(16,16),lambda *a,**k:None)
except ValueError as error:
    assert 'regular' in str(error)
else:
    raise AssertionError('FIFO foi aceito')
"""
    result=subprocess.run([sys.executable,'-c',code,str(path)],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
