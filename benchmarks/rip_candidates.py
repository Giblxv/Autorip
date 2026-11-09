"""Hipóteses reproduzíveis da campanha; não são importadas pelo AutoRIP."""
import re


def change(bundle, file, before, after):
    if before not in bundle[file]:
        return None
    result = dict(bundle)
    result[file] = result[file].replace(before, after, 1)
    return result if result != bundle else None


def noise32(b):
    return change(b,'engine', 'self.noise = _blue_noise(256, 256, sx=1.0, sy=s.dpi_y / s.dpi_x)',
                  'self.noise = _blue_noise(256, 256, sx=1.0, sy=s.dpi_y / s.dpi_x).astype(np.float32)') if '.astype(np.float32)' not in b['engine'].split('self.noise =',1)[1].splitlines()[0] else None


def zero_planes(b):
    s=b['engine']
    old='planes = [np.zeros((h, n_dots), np.uint8) for _ in range(12)]'
    if old not in s:return None
    s=s.replace(old,'zero = np.zeros((h, n_dots), np.uint8)\n        planes = [zero] * 12',1)
    old='planes[pl][o:o + (r1 - r0)] = self._halftone(cmyk[..., idx[name]], r0, color_thresholds)'
    if old not in s:return None
    s=s.replace(old,'''levels = self._halftone(cmyk[..., idx[name]], r0, color_thresholds)
                if o == 0 and levels.shape[0] == h:
                    planes[pl] = levels
                else:
                    planes[pl] = zero.copy()
                    planes[pl][o:o + levels.shape[0]] = levels''',1)
    s=s.replace('''                dst = planes[s.channel_order.index("K")][ys - a0:ye - a0, lx:lx + lab.shape[1]]''','''                k_plane = s.channel_order.index("K")
                if planes[k_plane] is zero:
                    planes[k_plane] = zero.copy()
                dst = planes[k_plane][ys - a0:ye - a0, lx:lx + lab.shape[1]]''',1)
    return dict(b,engine=s)


def repeated_planes(b):
    return change(b,'prt','''        for index, plane in enumerate(arrays):
            out[:, index, :] = pack2(plane, self.pb)''','''        packed = {}
        for index, plane in enumerate(arrays):
            key = (plane.__array_interface__["data"][0], plane.strides, plane.dtype.str)
            previous = packed.get(key)
            if previous is None:
                out[:, index, :] = pack2(plane, self.pb)
                packed[key] = index
            else:
                out[:, index, :] = out[:, previous, :]''')


def transparent(b):
    s=b['engine'];a=s.find('            alpha = arr[..., 3].astype')
    z=s.find('        for (ly, lx, lab) in labels:',a)
    if a<0 or z<0 or 'if arr[..., 3].any():' in s:return None
    block=s[a:z];s=s[:a]+'            if arr[..., 3].any():\n'+''.join('    '+line if line.strip() else line for line in block.splitlines(keepends=True))+s[z:]
    return dict(b,engine=s)


def zero_halftone(b):
    marker='''        r = self.s.small_drop_ratio
        t ='''
    return change(b,'engine',marker,'''        if not v.any():
            return np.zeros(v.shape, dtype=np.uint8)
        r = self.s.small_drop_ratio
        t =''')


def full_halftone(b):
    marker='''        r = self.s.small_drop_ratio
        t ='''
    if 'if np.all(v >= 1)' in b['engine']:return None
    return change(b,'engine',marker,'''        if np.all(v >= 1):
            return np.full(v.shape, 3, dtype=np.uint8)
        r = self.s.small_drop_ratio
        t =''')


def source_copy(b):
    return change(b,'engine','''            source = ImageOps.exif_transpose(opened)''','''            source = (ImageOps.exif_transpose(opened)
                      if orientation in (2, 3, 4, 5, 6, 7, 8) else opened)''')


def no_morph_pixels(b):
    s=b['morph']
    if 'radius < min(sampling)' in s:return None
    s=s.replace('if not radius or not mask.any():','if not radius or radius < min(sampling) or not mask.any():')
    s=s.replace('mask, radius, _ = _parameters(mask, mm, dpi_x, dpi_y)','mask, radius, sampling = _parameters(mask, mm, dpi_x, dpi_y)')
    s=s.replace('if not radius or not mask.any() or mask.all():','if not radius or radius < min(sampling) or not mask.any() or mask.all():')
    return dict(b,morph=s)


def edt_transpose(b):
    s=b['morph']
    if '_distance(' in s:return None
    s=s.replace('ndi.distance_transform_edt(', '_distance(')
    s+='''\n\ndef _distance(mask, sampling):
    return ndi.distance_transform_edt(np.ascontiguousarray(mask.T), sampling=sampling[::-1]).T
'''
    return dict(b,morph=s)


def edt_indices(b):
    s=b['morph']
    if '_distance(' in s:return None
    s=s.replace('ndi.distance_transform_edt(', '_distance(')
    s+='''\n\ndef _distance(mask, sampling):
    indices = ndi.distance_transform_edt(mask, sampling=sampling,
                                         return_distances=False, return_indices=True)
    indices[0] -= np.arange(mask.shape[0], dtype=np.int32)[:, None]
    indices[1] -= np.arange(mask.shape[1], dtype=np.int32)[None, :]
    y = indices[0].astype(np.float64)
    x = indices[1].astype(np.float64)
    y *= sampling[0]
    x *= sampling[1]
    np.square(y, out=y)
    np.square(x, out=x)
    np.add(y, x, out=y)
    return np.sqrt(y, out=y)
'''
    return dict(b,morph=s)


def squared_distance(b):
    s=b['morph']
    if 'def _distance(' not in s or 'np.sqrt(y, out=y)' not in s:return None
    s=s.replace('return np.sqrt(y, out=y)','return y')
    s=s.replace('sampling=sampling) <= radius','sampling=sampling) <= radius * radius')
    s=s.replace('return (distance > radius)', 'return (distance > radius * radius)')
    return dict(b,morph=s)


def thresholds(b, mode):
    s=b['engine'];a=s.find('        ny, nx = self.noise.shape\n',s.find('    def _thresholds'))
    z=s.find('\n    def _halftone',a)
    if a<0 or z<0:return None
    implementations={
      'take':'''        ny, nx = self.noise.shape
        return self.noise.take((np.arange(height) + y0) % ny, axis=0).take(np.arange(width) % nx, axis=1)
''',
      'tile':'''        ny, nx = self.noise.shape
        rows = self.noise[(np.arange(height) + y0) % ny]
        return np.tile(rows, (1, (width + nx - 1) // nx))[:, :width]
''',
      'tile2d':'''        ny, nx = self.noise.shape
        phase = y0 % ny
        return np.tile(self.noise, ((height + phase + ny - 1) // ny,
                                   (width + nx - 1) // nx))[phase:phase + height, :width]
''',
      'broadcast':'''        ny, nx = self.noise.shape
        phase = y0 % ny
        ry, rx = (height + phase + ny - 1) // ny, (width + nx - 1) // nx
        tiled = np.broadcast_to(self.noise[None, :, None, :], (ry, ny, rx, nx)).reshape(ry * ny, rx * nx)
        return tiled[phase:phase + height, :width]
'''}
    after=s[:a]+implementations[mode]+s[z:]
    return dict(b,engine=after) if after!=s else None


def halftone_assign(b):
    return change(b,'engine','''        return np.where(large, np.uint8(3), small.astype(np.uint8))''','''        levels = small.astype(np.uint8)
        levels[large] = 3
        return levels''')


def halftone_bits(b):
    return change(b,'engine','''        return np.where(large, np.uint8(3), small.astype(np.uint8))''','''        return small.astype(np.uint8) | (large.astype(np.uint8) << 1)''')


def halftone_multiply(b):
    return change(b,'engine','''        small = (v / r) > t
        large = ((v - r) / (1.0 - r)) > t''','''        small = v > (t * r)
        large = v > (t * (1.0 - r) + r)''')


def pack(b, mode):
    s=b['prt'];a=s.find('    rows, dots = a.shape\n',s.find('def pack2'))
    z=s.find('\n\ndef unpack2',a)
    if a<0 or z<0:return None
    prefix='''    rows, dots = a.shape
    full = plane_bytes * 4
    if dots < full:
        a = np.pad(a, ((0, 0), (0, full - dots)))
    a = a.astype(np.uint8, copy=False)
'''
    choices={
      'tree':prefix+'''    pairs = (a[:, 0::2] << 2) | a[:, 1::2]
    return (pairs[:, 0::2] << 4) | pairs[:, 1::2]
''',
      'dot':prefix+'''    return a.reshape(rows, plane_bytes, 4) @ np.array([64, 16, 4, 1], dtype=np.uint8)
''',
      'sum':prefix+'''    return np.sum(a.reshape(rows, plane_bytes, 4) * np.array([64, 16, 4, 1], dtype=np.uint8), axis=2, dtype=np.uint8)
''',
      'packbits':prefix+'''    bits = np.empty((rows, full, 2), dtype=np.uint8)
    bits[:, :, 0] = (a >> 1) & 1
    bits[:, :, 1] = a & 1
    return np.packbits(bits.reshape(rows, full * 2), axis=1, bitorder="big")
''',
      'direct':'''    rows, dots = a.shape
    a = a.astype(np.uint8, copy=False)
    out = np.zeros((rows, plane_bytes), dtype=np.uint8)
    scratch = np.empty((rows, (dots + 3) // 4), dtype=np.uint8)
    for offset, shift in ((0, 6), (1, 4), (2, 2), (3, 0)):
        channel = a[:, offset::4]
        width = channel.shape[1]
        np.left_shift(channel, shift, out=scratch[:, :width])
        np.bitwise_or(out[:, :width], scratch[:, :width], out=out[:, :width])
    return out
''',
      'u32':prefix+'''    words = np.ascontiguousarray(a).view('<u4').reshape(rows, plane_bytes)
    return (((words & 3) << 6) | ((words & 0x300) >> 4) |
            ((words & 0x30000) >> 14) | ((words & 0x3000000) >> 24)).astype(np.uint8)
'''}
    candidate=s[:a]+choices[mode]+s[z:]
    return dict(b,prt=candidate) if candidate!=s else None


def strip(b, rows):
    s=re.sub(r'^STRIP = \d+[^\n]*', f'STRIP = {rows}  # limite da tira, sujeito ao orçamento de memória', b['engine'],flags=re.M)
    return dict(b,engine=s) if s!=b['engine'] else None


def channel_copy(b):
    return change(b,'engine','self._halftone(cmyk[..., idx[name]], r0, color_thresholds)',
                  'self._halftone(np.ascontiguousarray(cmyk[..., idx[name]]), r0, color_thresholds)')


def mirror_first(b):
    return change(b,'engine','''            strip = im.resize((n_dots, r1 - r0), Image.LANCZOS, box=box)
            if s.mirror:
                strip = strip.transpose(Image.FLIP_LEFT_RIGHT)''','''            source = im.transpose(Image.FLIP_LEFT_RIGHT) if s.mirror else im
            strip = source.resize((n_dots, r1 - r0), Image.LANCZOS, box=box)''')


def cmyk_lut(b):
    return change(b,'engine','''        a = np.asarray(c, dtype=np.float32) / 255.0''','''        table = np.arange(256, dtype=np.float32) / 255.0
        a = table[np.asarray(c)]''')


def cmyk_reciprocal(b):
    return change(b,'engine','''        a = np.asarray(c, dtype=np.float32) / 255.0''','''        a = np.asarray(c, dtype=np.float32) * np.float32(1.0 / 255.0)''')


def erode_padding(b):
    return change(b,'morph','''    padded = np.pad(mask, 1, constant_values=False)''','''    padded = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2), dtype=bool)
    padded[1:-1, 1:-1] = mask''')


def close_view(b):
    return change(b,'morph','''return closed[ry:ry + mask.shape[0], rx:rx + mask.shape[1]].copy()''','''return closed[ry:ry + mask.shape[0], rx:rx + mask.shape[1]]''')


def clip_redundant(b):
    return change(b,'engine','''        return np.clip(a, 0, 1, out=a)''','''        return a''')


CANDIDATES = [
 ('rank-float32','Ranks dyádicos da retícula em float32',noise32),
 ('shared-zero-planes','Compartilhar plano vazio e alocar somente canais usados',zero_planes),
 ('pack-identical-views','Empacotar uma vez os planos com memória idêntica',repeated_planes),
 ('skip-transparent-strips','Não converter nem reticular tiras totalmente transparentes',transparent),
 ('zero-halftone','Atalho exato para canal sem tinta',zero_halftone),
 ('source-copy','Evitar cópia EXIF quando não há orientação a aplicar',source_copy),
 ('subpixel-morph','Evitar EDT quando o disco contém somente o pixel central',no_morph_pixels),
 ('edt-indices','Construir distâncias em buffers 2-D a partir de índices públicos',edt_indices),
 ('edt-transpose','Transpor os eixos da EDT com amostragem física invertida',edt_transpose),
 ('threshold-take','Expandir tela com duas operações take',lambda b:thresholds(b,'take')),
 ('threshold-tile','Expandir linhas com tile e recortar colunas',lambda b:thresholds(b,'tile')),
 ('threshold-tile2d','Repetir matriz periódica em dois eixos',lambda b:thresholds(b,'tile2d')),
 ('threshold-broadcast','Expandir tela por broadcast 4-D e reshape',lambda b:thresholds(b,'broadcast')),
 ('pack-tree','Empacotamento hierárquico em pares de pixels',lambda b:pack(b,'tree')),
 ('pack-direct','Empacotar sem preencher a imagem até a largura alinhada',lambda b:pack(b,'direct')),
 ('pack-dot','Produto escalar uint8 para agrupar quatro pixels',lambda b:pack(b,'dot')),
 ('pack-sum','Soma ponderada uint8 para empacotamento',lambda b:pack(b,'sum')),
 ('pack-bits','Empacotamento vetorizado com packbits',lambda b:pack(b,'packbits')),
 ('pack-u32','Leitura de grupos de quatro pixels como palavras uint32',lambda b:pack(b,'u32')),
 ('halftone-assign','Escrever gotas grandes por máscara sobre saída uint8',halftone_assign),
 ('halftone-bits','Combinar níveis por operações bit a bit',halftone_bits),
 ('halftone-full','Atalho para canal inteiramente saturado',full_halftone),
 ('channel-contiguous','Copiar canal CMYK para acesso contíguo antes da retícula',channel_copy),
 ('cmyk-lut','Normalizar CMYK com tabela exata de 256 entradas',cmyk_lut),
 ('clip-redundant','Eliminar clip após limites de tinta validados',clip_redundant),
 ('padding-explicit','Padding de erosão com zeros e cópia explícitos',erode_padding),
 ('close-view','Reutilizar view do fechamento em vez de copiar o recorte',close_view),
 ('squared-distances','Comparar distâncias quadráticas sem raiz',squared_distance),
 ('halftone-multiply','Multiplicar o limiar em vez de dividir o volume',halftone_multiply),
 ('cmyk-reciprocal','Multiplicar por recíproco de 255',cmyk_reciprocal),
 ('mirror-before-resize','Espelhar antes da reamostragem',mirror_first),
] + [(f'strip-{n}',f'Tiras de até {n} linhas, conservando limite de memória',lambda b,n=n:strip(b,n))
     for n in (256,768,1024,1536,2048,384,640,896,1280,3072)]


def pipeline(b, workers):
    s=b['engine']
    if 'RENDER_WORKERS_MAX =' in s:
        after=re.sub(r'RENDER_WORKERS_MAX = \d+',f'RENDER_WORKERS_MAX = {workers}',s)
        return dict(b,engine=after) if after!=s else None
    start=s.find('            y = 0\n            while y < n_rows:')
    end=s.find('            wr.close()',start)
    if start<0 or end<0:return None
    original=s[start:end]
    fallback=''.join('    '+line if line.strip() else line for line in original.splitlines(keepends=True))
    code='''            if workers == 1:
FALLBACK            else:
                from collections import deque
                from concurrent.futures import ThreadPoolExecutor
                ranges = iter(range(0, n_rows, strip_rows))
                pending = deque()
                with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="autorip-render") as pool:
                    def submit():
                        start = next(ranges, None)
                        if start is None:
                            return
                        end = min(n_rows, start + strip_rows)
                        a0, a1 = max(0, start - halo), min(n_rows, end + halo)
                        future = pool.submit(self._render, im, a0, a1, top, art_rows, n_dots, labels)
                        pending.append((start, end, a0, future))
                    for _ in range(workers):
                        submit()
                    while pending:
                        start, end, a0, future = pending.popleft()
                        planes_full = future.result()
                        offset = start - a0
                        block = [plane[offset:offset + end - start] for plane in planes_full]
                        wr.write_block(block)
                        del block, planes_full, future
                        if progress:
                            progress(end / n_rows)
                        submit()
'''.replace('FALLBACK',fallback)
    s=s[:start]+code+s[end:]
    s=s.replace('STRIP = 512',f'RENDER_WORKERS_MAX = {workers}\nSTRIP = 512',1)
    if 'RENDER_WORKERS_MAX =' not in s:
        s=re.sub(r'(^STRIP =)',f'RENDER_WORKERS_MAX = {workers}\n\\1',s,count=1,flags=re.M)
    s=s.replace('''        available_rows = MAX_STRIP_MEMORY_BYTES // max(1, n_dots * _BYTES_PER_RENDER_PIXEL) - 2 * halo''','''        workers = (min(RENDER_WORKERS_MAX, os.cpu_count() or 1)
                   if n_rows >= STRIP * 3 and n_dots * n_rows >= 1_000_000 else 1)
        available_rows = MAX_STRIP_MEMORY_BYTES // workers // max(1, n_dots * _BYTES_PER_RENDER_PIXEL) - 2 * halo
        if workers > 1 and available_rows < 1:
            workers = 1
            available_rows = MAX_STRIP_MEMORY_BYTES // max(1, n_dots * _BYTES_PER_RENDER_PIXEL) - 2 * halo''',1)
    s=s.replace('''                self.transform = ImageCms.buildTransform(''','''                # LittleCMS: transforme compartilhada por threads exige desativar cache de pixel.
                flags |= ImageCms.Flags.NOCACHE
                self.transform = ImageCms.buildTransform(''',1)
    return dict(b,engine=s)


# São configurações genuínas de concorrência; não diminuem resolução ou qualidade.
CANDIDATES[8:8] = [(f'pipeline-{n}',f'Renderização ordenada em até {n} threads com orçamento global',
                    lambda b,n=n:pipeline(b,n)) for n in (2,3,4)]
