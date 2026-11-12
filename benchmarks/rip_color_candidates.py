"""Evaluate contiguous CMYK halftoning without changing arithmetic or strip geometry."""


def color_batch(bundle, strategy):
    source = bundle['engine']
    marker = '    # ---------- branco ----------'
    anchor = '                idx = {"C": 0, "M": 1, "Y": 2, "K": 3}'
    if '_builtin_halftone' in source or marker not in source or anchor not in source:
        return None
    source = source.replace(marker, '    _builtin_halftone = _halftone\n\n' + marker, 1)
    if strategy == 'interleaved':
        compute = '                    color_levels = self._halftone(cmyk, r0, color_thresholds[..., None])\n'
    elif strategy == 'planar':
        compute = ('                    planar = np.ascontiguousarray(np.moveaxis(cmyk, -1, 0))\n'
                   '                    color_levels = np.moveaxis(self._halftone(planar, r0, color_thresholds[None, ...]), 0, -1)\n'
                   '                    del planar\n')
    elif strategy.startswith('rows-'):
        rows = int(strategy.split('-')[1])
        if rows not in (32, 64, 128, 256):
            raise ValueError(strategy)
        compute = ('                    color_levels = np.empty(cmyk.shape, dtype=np.uint8)\n'
                   f'                    for start in range(0, cmyk.shape[0], {rows}):\n'
                   f'                        end = min(cmyk.shape[0], start + {rows})\n'
                   '                        color_levels[start:end] = self._halftone(\n'
                   '                            cmyk[start:end], r0 + start, color_thresholds[start:end, :, None])\n')
    else:
        raise ValueError(strategy)
    start = source.index(anchor)
    source = (source[:start] + '                color_levels = None\n'
              '                if getattr(self._halftone, "__func__", None) is Rip._builtin_halftone:\n'
              + compute + source[start:])
    source = source.replace('levels = self._halftone(cmyk[..., idx[name]], r0, color_thresholds)',
                            'levels = (color_levels[..., idx[name]] if color_levels is not None\n'
                            '                              else self._halftone(cmyk[..., idx[name]], r0, color_thresholds))', 1)
    source = source.replace('del color_thresholds, thresholds, cmyk, rgb, arr, strip',
                            'del color_levels, color_thresholds, thresholds, cmyk, rgb, arr, strip', 1)
    return dict(bundle, engine=source)


CANDIDATES = [
    (f'color-batch-{strategy}', f'Batch CMYK halftoning using {strategy} memory traversal',
     lambda bundle, strategy=strategy: color_batch(bundle, strategy))
    for strategy in ('interleaved', 'planar', 'rows-32', 'rows-64', 'rows-128', 'rows-256')
]
