"""Novas hipóteses de alocação e escrita; usadas apenas na campanha large-io."""
import re

from rip_candidates import change


ERROR = '        raise ValueError("niveis do plano precisam ser inteiros entre 0 e 3.")\n'


def validation(bundle, mode):
    source = bundle['prt']
    start = source.find('    if not np.issubdtype', source.index('def pack2'))
    end = source.find('    rows, dots = a.shape', start)
    if start < 0 or end < 0:
        return None
    conditions = {
        'unsigned': '(np.issubdtype(a.dtype, np.signedinteger) and np.any(a < 0)) or np.any(a > 3)',
        'minmax': 'a.min() < 0 or a.max() > 3',
        'max-uint8': '(a.max() > 3) if a.dtype == np.uint8 else (np.any(a < 0) or np.any(a > 3))',
        'mask-uint8': 'np.any(a & np.uint8(252)) if a.dtype == np.uint8 else (np.any(a < 0) or np.any(a > 3))',
        'or-uint8': 'np.bitwise_or.reduce(a, axis=None) > 3 if a.dtype == np.uint8 else (np.any(a < 0) or np.any(a > 3))',
    }
    body = ('    if not np.issubdtype(a.dtype, np.integer):\n' + ERROR
            + f'    if {conditions[mode]}:\n' + ERROR)
    result = source[:start] + body + source[end:]
    return dict(bundle, prt=result) if result != source else None


PACK_PREFIX = '''    rows, dots = a.shape
    full = plane_bytes * 4
    if dots < full:
        a = np.pad(a, ((0, 0), (0, full - dots)))
    a = a.astype(np.uint8, copy=False).reshape(rows, plane_bytes, 4)
'''


def packing(bundle, mode):
    source = bundle['prt']
    start = source.index('    rows, dots = a.shape', source.index('def pack2'))
    end = source.index('\n\ndef unpack2', start)
    if mode in ('tail-zero', 'tail-empty', 'tail-ufunc'):
        allocation = ('np.zeros((rows, plane_bytes), dtype=np.uint8)' if mode == 'tail-zero'
                      else 'np.empty((rows, plane_bytes), dtype=np.uint8)')
        body = f'''    rows, dots = a.shape
    a = a.astype(np.uint8, copy=False)
    complete, remaining = divmod(dots, 4)
    out = {allocation}
    out[:, complete:] = 0
    core = a[:, :complete * 4].reshape(rows, complete, 4)
'''
        if mode == 'tail-ufunc':
            body += '''    np.left_shift(core[..., 0], 6, out=out[:, :complete])
    for offset, shift in ((1, 4), (2, 2), (3, 0)):
        np.bitwise_or(out[:, :complete], core[..., offset] << shift, out=out[:, :complete])
'''
        else:
            body += '''    out[:, :complete] = ((core[..., 0] << 6) | (core[..., 1] << 4)
                         | (core[..., 2] << 2) | core[..., 3])
'''
        body += '''    for offset in range(remaining):
        out[:, complete] |= a[:, complete * 4 + offset] << (6 - offset * 2)
    return out
'''
    elif mode == 'einsum':
        body = PACK_PREFIX + '''    return np.einsum('ijk,k->ij', a, np.array([64, 16, 4, 1], dtype=np.uint8), dtype=np.uint8)
'''
    elif mode == 'accumulator':
        body = PACK_PREFIX + '''    out = np.left_shift(a[..., 0], 6)
    np.bitwise_or(out, a[..., 1] << 4, out=out)
    np.bitwise_or(out, a[..., 2] << 2, out=out)
    np.bitwise_or(out, a[..., 3], out=out)
    return out
'''
    elif mode == 'pair-lut':
        body = PACK_PREFIX + '''    pairs = np.ascontiguousarray(a).view('<u2').reshape(rows, plane_bytes, 2)
    return (_PACK_PAIR_LUT[pairs[..., 0]] << 4) | _PACK_PAIR_LUT[pairs[..., 1]]
'''
        if '_PACK_PAIR_LUT =' not in source:
            source += '''\n_PACK_PAIR_VALUES = np.arange(1024, dtype=np.uint16)
_PACK_PAIR_LUT = (((_PACK_PAIR_VALUES & 3) << 2) | ((_PACK_PAIR_VALUES >> 8) & 3)).astype(np.uint8)
del _PACK_PAIR_VALUES
'''
    else:
        raise ValueError(mode)
    result = source[:start] + body + source[end:]
    return dict(bundle, prt=result) if result != source else None


def writer_reuse(bundle):
    source = bundle['prt']
    if '_block_buffer' in source:
        return None
    source = source.replace('        self.written = 0', '        self.written = 0\n        self._block_buffer = None', 1)
    source = source.replace('        out = np.empty((rows, self.n_channels, self.pb), dtype=np.uint8)', '''        if self._block_buffer is None or self._block_buffer.shape[0] < rows:
            self._block_buffer = np.empty((rows, self.n_channels, self.pb), dtype=np.uint8)
        out = self._block_buffer[:rows]''', 1)
    # O buffer só pertence ao writer; não fica retido depois de close().
    source = source.replace('''        finally:
            self.f.close()


def read_rows''', '''        finally:
            self._block_buffer = None
            self.f.close()


def read_rows''', 1)
    return dict(bundle, prt=source)


def writer_zero(bundle):
    return change(bundle, 'prt', '''            if previous is None:
                out[:, index, :] = pack2(plane, self.pb)''', '''            if previous is None:
                if np.issubdtype(plane.dtype, np.integer) and not plane.any():
                    out[:, index, :] = 0
                else:
                    out[:, index, :] = pack2(plane, self.pb)''')


def writer_identity(bundle):
    return change(bundle, 'prt', '''        packed = {}
        for index, plane in enumerate(arrays):
            key = (plane.__array_interface__["data"][0], plane.strides, plane.dtype.str)''', '''        packed = {}
        identities = {}
        for index, plane in enumerate(arrays):
            identical = identities.get(id(plane))
            if identical is not None:
                out[:, index, :] = out[:, identical, :]
                continue
            identities[id(plane)] = index
            key = (plane.__array_interface__["data"][0], plane.strides, plane.dtype.str)''')


def writer_layout(bundle):
    return _writer_layout(bundle)


def _writer_layout(bundle):
    result = change(bundle, 'prt', '''        out = np.empty((rows, self.n_channels, self.pb), dtype=np.uint8)''', '''        out = np.empty((self.n_channels, rows, self.pb), dtype=np.uint8).transpose(1, 0, 2)''')
    return change(result, 'prt', 'self.f.write(memoryview(out))', 'self.f.write(memoryview(np.ascontiguousarray(out)))') if result else None


def alpha_inplace(bundle):
    return change(bundle, 'engine', '''                alpha = arr[..., 3].astype(np.float32) / 255.0''', '''                alpha = arr[..., 3].astype(np.float32)
                alpha /= 255.0''')


def alpha_ufunc(bundle):
    return change(bundle, 'engine', '                cmyk *= alpha[..., None]', '                np.multiply(cmyk, alpha[..., None], out=cmyk)')


def ink_identity(bundle):
    return change(bundle, 'engine', '''        a *= np.asarray(lim, dtype=np.float32)''', '''        if any(value != 1.0 for value in lim):
            a *= np.asarray(lim, dtype=np.float32)''')


def ink_cache(bundle):
    return change(bundle, 'engine', '''        a *= np.asarray(lim, dtype=np.float32)''', '''        key = tuple(lim)
        cached = getattr(self, '_ink_multipliers', None)
        if cached is None or cached[0] != key:
            cached = (key, np.asarray(lim, dtype=np.float32))
            self._ink_multipliers = cached
        a *= cached[1]''')


def thresholds(bundle, mode):
    source = bundle['engine']
    start = source.index('        ny, nx = self.noise.shape', source.index('    def _thresholds'))
    end = source.index('\n    def _halftone', start)
    bodies = {
        'indices32': '''        ny, nx = self.noise.shape
        dtype = np.int32 if max(height, width, abs(y0) + height) < 2**31 else np.int64
        return self.noise[np.ix_((np.arange(height, dtype=dtype) + y0) % ny, np.arange(width, dtype=dtype) % nx)]
''',
        'direct-index': '''        ny, nx = self.noise.shape
        rows = (np.arange(height) + y0) % ny
        columns = np.arange(width) % nx
        return self.noise[rows[:, None], columns[None, :]]
''',
        'power-two': '''        ny, nx = self.noise.shape
        rows = np.arange(height) + y0
        columns = np.arange(width)
        rows = (rows & (ny - 1)) if not ny & (ny - 1) else rows % ny
        columns = (columns & (nx - 1)) if not nx & (nx - 1) else columns % nx
        return self.noise[np.ix_(rows, columns)]
''',
    }
    result = source[:start] + bodies[mode] + source[end:]
    return dict(bundle, engine=result) if result != source else None


def density_buffer(bundle):
    before = '''        dens = np.where(a >= 0.9, s.white_density, 0.5 * (a / 0.9) * s.white_density).astype(np.float32)'''
    after = '''        dens = a / 0.9
        dens *= 0.5
        dens *= s.white_density
        dens[a >= 0.9] = s.white_density
        dens = dens.astype(np.float32, copy=False)'''
    return change(bundle, 'engine', before, after)


def no_fill_assignment(bundle):
    return change(bundle, 'engine', '''        dens[mask & ~original_mask] = s.white_density''', '''        if s.white_fill_holes_mm > 0:
            dens[mask & ~original_mask] = s.white_density''')


def morphology_padding(bundle):
    return change(bundle, 'morph', '''    padded = np.pad(mask, ((ry, ry), (rx, rx)), constant_values=False)''', '''    padded = np.zeros((mask.shape[0] + 2 * ry, mask.shape[1] + 2 * rx), dtype=bool)
    padded[ry:ry + mask.shape[0], rx:rx + mask.shape[1]] = mask''')


def edt_coordinates(bundle):
    source = bundle['morph']
    if '_coordinate_vector' in source:
        return None
    source = source.replace('np.arange(mask.shape[0], dtype=np.int32)', '_coordinate_vector(mask.shape[0])')
    source = source.replace('np.arange(mask.shape[1], dtype=np.int32)', '_coordinate_vector(mask.shape[1])')
    source += '''\n\nfrom functools import lru_cache

def _coordinate_vector(size):
    return _small_coordinate_vector(size) if size <= 32768 else np.arange(size, dtype=np.int32)

@lru_cache(maxsize=8)
def _small_coordinate_vector(size):
    coordinates = np.arange(size, dtype=np.int32)
    coordinates.flags.writeable = False
    return coordinates
'''
    return dict(bundle, morph=source)


def edt_scale_first(bundle):
    return change(bundle, 'morph', '''    y = indices[0].astype(np.float64)
    x = indices[1].astype(np.float64)
    y *= sampling[0]
    x *= sampling[1]''', '''    y = np.multiply(indices[0], sampling[0], dtype=np.float64)
    x = np.multiply(indices[1], sampling[1], dtype=np.float64)''')


def edt_hypot(bundle):
    return change(bundle, 'morph', '''    np.square(y, out=y)
    np.square(x, out=x)
    np.add(y, x, out=y)
    return np.sqrt(y, out=y)''', '''    return np.hypot(y, x, out=y)''')


def conservative_memory(bundle, value):
    source = re.sub(r'^MAX_STRIP_MEMORY_BYTES = .+$', f'MAX_STRIP_MEMORY_BYTES = {value} * 1024 * 1024', bundle['engine'], flags=re.M)
    return dict(bundle, engine=source) if source != bundle['engine'] else None


def writer_sparse_empty(bundle):
    before = '        out = np.empty((rows, self.n_channels, self.pb), dtype=np.uint8)'
    after = '''        first = arrays[0]
        if np.issubdtype(first.dtype, np.integer):
            signature = (first.__array_interface__["data"][0], first.strides, first.dtype.str)
            if (all((plane.__array_interface__["data"][0], plane.strides, plane.dtype.str) == signature
                    for plane in arrays[1:]) and not first.any()):
                self.f.seek(rows * self.n_channels * self.pb, os.SEEK_CUR)
                self.written += rows
                return
        out = np.empty((rows, self.n_channels, self.pb), dtype=np.uint8)'''
    result = change(bundle, 'prt', before, after)
    if result is None:
        return None
    # seek não estende o arquivo se o último bloco estiver vazio.
    # flush/validação precedem truncate; fsync continua obrigatório depois dele.
    return change(result, 'prt', '            # Publicar o arquivo somente apos sincronizar seus bytes com o disco.',
                  '            self.f.truncate(actual_size)\n            # Publicar o arquivo somente apos sincronizar seus bytes com o disco.')


CANDIDATES = [
    ('alpha-buffer-normalize', 'Normalizar alfa no buffer privado float32', alpha_inplace),
    ('density-private-buffer', 'Construir densidade de branco num buffer privado', density_buffer),
    ('pack-validate-minmax', 'Validar níveis com reduções min/max sem máscaras temporárias', lambda b: validation(b, 'minmax')),
    ('pack-tail-empty', 'Empacotar grupos completos e só preencher o final alinhado', lambda b: packing(b, 'tail-empty')),
    ('writer-reuse-buffer', 'Reaproveitar buffer de escrita ao longo das tiras e liberar no fechamento', writer_reuse),
    ('writer-zero-plane', 'Preencher plano vazio sem passar pelo empacotamento', writer_zero),
    ('pack-validate-unsigned', 'Dispensar comparação negativa para dtype sem sinal', lambda b: validation(b, 'unsigned')),
    ('pack-validate-max8', 'Redução max direta para níveis uint8', lambda b: validation(b, 'max-uint8')),
    ('pack-validate-mask8', 'Validar limites uint8 por máscara de bits', lambda b: validation(b, 'mask-uint8')),
    ('pack-validate-or8', 'Validar limites uint8 por redução OR', lambda b: validation(b, 'or-uint8')),
    ('pack-tail-zero', 'Separar grupos completos com saída inicialmente zerada', lambda b: packing(b, 'tail-zero')),
    ('pack-tail-ufunc', 'Empacotar grupos completos usando acumulador de ufunc', lambda b: packing(b, 'tail-ufunc')),
    ('pack-pair-lut', 'Codificar pares uint16 com tabela limitada a 1024 entradas', lambda b: packing(b, 'pair-lut')),
    ('pack-einsum', 'Agrupar quatro níveis por einsum uint8', lambda b: packing(b, 'einsum')),
    ('pack-accumulator', 'Combinar bits em acumulador uint8 reutilizado', lambda b: packing(b, 'accumulator')),
    ('writer-identity-cache', 'Atalho para repetição do mesmo objeto de plano', writer_identity),
    ('writer-planar-layout', 'Comparar escrita por planos contíguos com cópia final intercalada', writer_layout),
    ('writer-sparse-empty', 'Saltar blocos integralmente vazios e materializar o tamanho final antes de fsync', writer_sparse_empty),
    ('ink-identity-limit', 'Dispensar multiplicação quando os quatro limites são identidade', ink_identity),
    ('ink-multiplier-cache', 'Reutilizar escala CMYK conferindo a configuração a cada tira', ink_cache),
    ('alpha-multiply-ufunc', 'Aplicar alfa por ufunc com saída explícita', alpha_ufunc),
    ('threshold-indices32', 'Índices periódicos em int32 quando representáveis', lambda b: thresholds(b, 'indices32')),
    ('threshold-direct-index', 'Indexar tela por broadcasting direto de índices', lambda b: thresholds(b, 'direct-index')),
    ('threshold-power-two', 'Usar máscara binária nos períodos que são potência de dois', lambda b: thresholds(b, 'power-two')),
    ('white-no-fill-assignment', 'Dispensar máscara de preenchimento quando fechamento é zero', no_fill_assignment),
    ('close-padding-buffer', 'Construir padding do fechamento por alocação e cópia explícitas', morphology_padding),
    ('edt-coordinate-cache', 'Reutilizar vetores de coordenadas imutáveis num cache limitado', edt_coordinates),
    ('edt-convert-scale', 'Converter e escalar coordenadas numa única ufunc', edt_scale_first),
    ('edt-hypot', 'Calcular norma física com hypot, exigindo igualdade nas fronteiras', edt_hypot),
    ('memory-budget-384', 'Comparar orçamento mais conservador de tiras: 384 MiB', lambda b: conservative_memory(b, 384)),
    ('memory-budget-256', 'Comparar orçamento mais conservador de tiras: 256 MiB', lambda b: conservative_memory(b, 256)),
]
