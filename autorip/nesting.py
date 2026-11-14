"""Encaixe de LayoutItem offline e compatibilidade com a API rectpack anterior.

Não compõe imagens nem gera PRT. Medidas e posições são em centímetros.
"""
import math
from itertools import chain
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from .layout import LayoutItem
from .sheet_nesting import check_layout, nest as nest_layout, utilization  # noqa: F401


class Placements(list):
    def __init__(self):
        super().__init__()
        self.unplaced = []


def _positive(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} precisa ser positivo e finito.")
    return Decimal(str(value))


def nest_sheets(items, sheet_w_cm, sheet_h_cm, gap_cm=0.5, allow_rotate=True, max_sheets=50):
    """Cada item é (nome, largura, altura, quantidade); retorna Placements."""
    sheet_w = _positive(sheet_w_cm, "Largura da folha")
    sheet_h = _positive(sheet_h_cm, "Altura da folha")
    if isinstance(gap_cm, bool) or not isinstance(gap_cm, (int, float)) or not math.isfinite(gap_cm) or gap_cm < 0:
        raise ValueError("O espacamento precisa ser positivo ou zero e finito.")
    if type(max_sheets) is not int or not 1 <= max_sheets <= 1000:
        raise ValueError("max_sheets precisa ser inteiro entre 1 e 1000.")
    if type(allow_rotate) is not bool:
        raise ValueError("allow_rotate precisa ser booleano.")
    gap = Decimal(str(gap_cm))
    unit = Decimal("0.001")
    meta = {}
    for name, width, height, quantity in items:
        w, h = _positive(width, "Largura"), _positive(height, "Altura")
        if type(quantity) is not int or quantity < 0 or len(meta) + quantity > 10000:
            raise ValueError("Quantidades precisam ser inteiras, com no maximo 10000 pecas.")
        for _ in range(quantity):
            meta[len(meta)] = (str(name), float(w), float(h),
                               (w + gap).quantize(unit, rounding=ROUND_CEILING),
                               (h + gap).quantize(unit, rounding=ROUND_CEILING))
    try:
        from rectpack import newPacker, PackingBin, SORT_AREA
        from rectpack.maxrects import MaxRectsBssf
    except ImportError as exc:
        raise RuntimeError("Instale o modulo opcional: pip install rectpack") from exc
    packer = newPacker(rotation=allow_rotate, bin_algo=PackingBin.BFF,
                       pack_algo=MaxRectsBssf, sort_algo=SORT_AREA)
    for rid, (_, _, _, w, h) in meta.items():
        packer.add_rect(w, h, rid)
    packer.add_bin((sheet_w + gap).quantize(unit, rounding=ROUND_FLOOR),
                   (sheet_h + gap).quantize(unit, rounding=ROUND_FLOOR), count=max_sheets)
    packer.pack()
    out = Placements()
    placed = set()
    for sheet, x, y, width, height, rid in packer.rect_list():
        name, ow, oh, packed_w, packed_h = meta[rid]
        rotated = width != packed_w and width == packed_h
        placed.add(rid)
        out.append(dict(folha=sheet, nome=name, x_cm=float(x), y_cm=float(y),
                        largura_cm=oh if rotated else ow,
                        altura_cm=ow if rotated else oh, girado=rotated))
    out.unplaced = [meta[rid][0] for rid in meta if rid not in placed]
    return out


def nest(items, *args, **kwargs):
    """LayoutItem usa MaxRects offline; tuplas preservam a API rectpack anterior.

    Use nest_layout/nest_sheets para escolher a API explicitamente, inclusive
    quando a coleção está vazia e os parâmetros são posicionais.
    """
    iterator = iter(items)
    missing = object()
    first = next(iterator, missing)
    legacy_keys = {'sheet_w_cm', 'sheet_h_cm', 'allow_rotate', 'max_sheets'}
    layout = (isinstance(first, LayoutItem) if first is not missing else
              len(args) < 2 and not legacy_keys.intersection(kwargs))
    values = () if first is missing else chain((first,), iterator)
    return (nest_layout if layout else nest_sheets)(values, *args, **kwargs)
