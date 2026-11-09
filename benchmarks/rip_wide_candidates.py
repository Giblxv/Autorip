"""Hipóteses adicionais para largura, alocação e menos CPUs; só no benchmark."""
import re
from rip_candidates import CANDIDATES as ORIGINAL, change, source_copy, noise32


def full_erode(bundle):
    before='''    padded = np.pad(mask, 1, constant_values=False)'''
    after='''    if mask.all():
        rows, columns = mask.shape
        y = np.minimum(np.arange(1, rows + 1), np.arange(rows, 0, -1)) * sampling[0]
        x = np.minimum(np.arange(1, columns + 1), np.arange(columns, 0, -1)) * sampling[1]
        # Reproduza sqrt(square) da EDT, inclusive na fronteira de raio.
        y = np.sqrt(np.square(y))
        x = np.sqrt(np.square(x))
        return (y > radius)[:, None] & (x > radius)[None, :]
    padded = np.pad(mask, 1, constant_values=False)'''
    return change(bundle,'morph',before,after) if 'if mask.all():' not in bundle['morph'].split('def erode',1)[1].split('def close_holes',1)[0] else None


def opaque_white(bundle):
    before='''        # niveis: borda (alpha parcial) = 1, miolo = 3'''
    after='''        if (s.white_density == 1 and np.issubdtype(a.dtype, np.floating)
                and a.min() >= np.asarray(0.9, dtype=a.dtype)):
            return mask.astype(np.uint8) * np.uint8(3)
        # niveis: borda (alpha parcial) = 1, miolo = 3'''
    return change(bundle,'engine',before,after) if 'and a.min() >=' not in bundle['engine'] else None


def normalize_inplace(bundle):
    return change(bundle,'engine','''        a = np.asarray(c, dtype=np.float32) / 255.0''','''        a = np.asarray(c, dtype=np.float32)
        a /= 255.0''')


def density_copy(bundle):
    s=bundle['engine']
    before='''0.5 * (a / 0.9) * s.white_density).astype(np.float32)'''
    return change(bundle,'engine',before,'''0.5 * (a / 0.9) * s.white_density).astype(np.float32, copy=False)''')


def mask_density(bundle):
    return change(bundle,'engine','''        dens = np.where(mask, dens, 0.0)''','''        dens[~mask] = 0.0''')


def estimated_pixel(bundle,value):
    s=re.sub(r'^_BYTES_PER_RENDER_PIXEL = \d+[^\n]*',
             f'_BYTES_PER_RENDER_PIXEL = {value}  # orçamento por pixel de renderização',bundle['engine'],flags=re.M)
    return dict(bundle,engine=s) if s!=bundle['engine'] else None


def fewer_wide(bundle,limit):
    before='''        fd, tmp_path = tempfile.mkstemp('''
    if 'workers = min(workers,' in bundle['engine']:return None
    return change(bundle,'engine',before,f'''        if n_dots >= 4096:
            workers = min(workers, {limit})
        fd, tmp_path = tempfile.mkstemp(''')


def opaque_alpha(bundle):
    s=bundle['engine']
    if 'opaque_alpha =' in s:return None
    before='''                alpha = arr[..., 3].astype(np.float32) / 255.0'''
    if before not in s:return None
    s=s.replace(before,'''                opaque_alpha = arr[..., 3].min() == 255
                alpha = None if opaque_alpha else arr[..., 3].astype(np.float32) / 255.0''',1)
    s=s.replace('''                cmyk *= alpha[..., None]''','''                if alpha is not None:
                    cmyk *= alpha[..., None]''',1)
    s=s.replace('''                    full_alpha[o:o + (r1 - r0)] = alpha''','''                    full_alpha[o:o + (r1 - r0)] = 1.0 if opaque_alpha else alpha''',1)
    return dict(bundle,engine=s)


def edt_transposed(bundle):
    s=bundle['morph'];start=s.find('\ndef _distance(')
    if start<0:return None
    helper='''
def _distance(mask, sampling):
    return ndi.distance_transform_edt(np.ascontiguousarray(mask.T), sampling=sampling[::-1]).T
'''
    s=s[:start]+helper
    return dict(bundle,morph=s) if s!=bundle['morph'] else None


def clip_inplace_ufunc(bundle):
    return change(bundle,'engine','''        return np.clip(a, 0, 1, out=a)''','''        np.minimum(a, 1, out=a)
        np.maximum(a, 0, out=a)
        return a''')


def thread_threshold(bundle,pixels):
    s=re.sub(r'n_dots \* n_rows >= \d[\d_]*',f'n_dots * n_rows >= {pixels}',bundle['engine'],count=1)
    return dict(bundle,engine=s) if s!=bundle['engine'] else None


CANDIDATES=[
 ('full-erode-analytic','Erosão exata de máscara cheia pelas distâncias às bordas',full_erode),
 ('white-opaque-direct','Branco 100% opaco convertido diretamente para níveis 0/3',opaque_white),
 ('cmyk-normalize-inplace','Normalização CMYK no próprio buffer float32',normalize_inplace),
 ('density-copy-false','Eliminar cópia redundante da densidade float32',density_copy),
 ('density-mask-inplace','Aplicar máscara de densidade no próprio buffer',mask_density),
 ('opaque-alpha','Evitar multiplicação e alocação do alfa quando é opaco',opaque_alpha),
 ('source-copy-large','Evitar cópia EXIF desnecessária em arquivos maiores',source_copy),
 ('rank32-wide','Tela exata float32 em largura e concorrência ampliadas',noise32),
 ('wide-limit-3','Três trabalhadores em artes largas, preservando o plano de tiras',lambda b:fewer_wide(b,3)),
 ('wide-limit-2','Dois trabalhadores em artes largas, preservando o plano de tiras',lambda b:fewer_wide(b,2)),
 ('pixel-estimate-80','Reavaliar orçamento de buffers em 80 bytes por pixel',lambda b:estimated_pixel(b,80)),
 ('pixel-estimate-64','Reavaliar orçamento de buffers em 64 bytes por pixel',lambda b:estimated_pixel(b,64)),
 ('edt-transpose-wide','Comparar EDT transposta sob largura ampliada',edt_transposed),
 ('clip-ufunc','Duas ufuncs no lugar de clip',clip_inplace_ufunc),
 ('parallel-threshold-500k','Paralelismo a partir de 500 mil pixels',lambda b:thread_threshold(b,500000)),
 ('parallel-threshold-2m','Paralelismo a partir de dois milhões de pixels',lambda b:thread_threshold(b,2000000)),
]+ORIGINAL
