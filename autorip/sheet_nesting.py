"""Nesting MaxRects para a folha DTF, offline e sem exigir rectpack.

Complementa layout.py: o auto_pack original empacota em faixas (uma fileira apos
a outra). Aqui testamos varias ordens e heuristicas MaxRects (e, se permitido,
rotacao de 90 graus) e devolvemos a folha mais curta entre esses candidatos. O resultado nunca e pior
que o auto_pack, que entra como candidato de base, e e sempre verificado contra
sobreposicao e largura util antes de ser aceito.

Uso:
    from .nesting import nest, utilization
    packed = nest(items, sheet_width_cm=58, margin_cm=0.2, gap_cm=0.2, allow_rotation=True)
    altura = sheet_height(packed)          # de layout.py
    aproveitamento = utilization(packed, 58)
"""
from __future__ import annotations

from dataclasses import asdict
import math
from typing import Iterable

from .layout import (DEFAULT_GAP_CM, DEFAULT_MARGIN_CM, MAX_SHEET_WIDTH_CM, LayoutItem,
                     _dimensions, auto_pack, sheet_height, validate_items)

EPS = 1e-6
ORDERS = ("orig", "area", "height", "width", "side")
HEURISTICS = ("bl", "bssf", "baf")


def _parameters(sheet_width_cm, margin_cm, gap_cm):
    if any(isinstance(v, bool) for v in (sheet_width_cm, margin_cm, gap_cm)):
        raise ValueError("Largura, margem e espaçamento precisam ser números.")
    try:
        width, margin, gap = map(float, (sheet_width_cm, margin_cm, gap_cm))
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Largura, margem e espaçamento inválidos.") from exc
    if (not all(map(math.isfinite, (width, margin, gap)))
            or not 0 < width <= MAX_SHEET_WIDTH_CM or margin < 0
            or 2 * margin >= width or gap < 0):
        raise ValueError("Largura, margem ou espaçamento fora dos limites da folha.")
    return width, margin, gap


def _normalized(item):
    if not isinstance(item, LayoutItem):
        raise ValueError("Cada peça precisa ser um LayoutItem.")
    try:
        angle = float(item.rotation)
        if not math.isfinite(angle) or angle % 90:
            raise ValueError()
        return item.normalized()
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("Dimensões, posições ou rotação inválidas para a peça.") from exc


def _inside(a, b):
    return (a[0] >= b[0] - EPS and a[1] >= b[1] - EPS
            and a[0] + a[2] <= b[0] + b[2] + EPS and a[1] + a[3] <= b[1] + b[3] + EPS)


def _split_free(free, rx, ry, rw, rh):
    out = []
    for fx, fy, fw, fh in free:
        if rx >= fx + fw - EPS or rx + rw <= fx + EPS or ry >= fy + fh - EPS or ry + rh <= fy + EPS:
            out.append((fx, fy, fw, fh))
            continue
        if rx > fx + EPS:
            out.append((fx, fy, rx - fx, fh))
        if rx + rw < fx + fw - EPS:
            out.append((rx + rw, fy, fx + fw - (rx + rw), fh))
        if ry > fy + EPS:
            out.append((fx, fy, fw, ry - fy))
        if ry + rh < fy + fh - EPS:
            out.append((fx, ry + rh, fw, fy + fh - (ry + rh)))
    kept = []
    for i, a in enumerate(out):
        if not any(i != j and _inside(a, b) and (a != b or j < i) for j, b in enumerate(out)):
            kept.append(a)
    return kept


def _score(heuristic, fr, x, y, w, h):
    fx, fy, fw, fh = fr
    if heuristic == "bl":      # canto inferior-esquerdo: menor borda de baixo, depois menor x
        return (y + h, x)
    if heuristic == "bssf":    # melhor encaixe pelo lado curto
        a, b = fw - w, fh - h
        return (min(a, b), max(a, b))
    return (fw * fh - w * h, min(fw - w, fh - h))   # baf: menor sobra de area


def _order_key(name, item):
    w, h = _dimensions(item)
    return {"orig": 0, "area": -(w * h), "height": -h, "width": -w, "side": -max(w, h)}[name]


def _pack_once(items, sheet_w, margin, gap, order, heuristic, allow_rot):
    idx = sorted(range(len(items)), key=lambda i: (_order_key(order, items[i]), i)) if order != "orig" \
        else list(range(len(items)))
    inner_w = sheet_w - 2 * margin + gap          # o gap extra absorve a folga da ultima peca
    try:
        big = math.fsum(max(*_dimensions(it)) + gap for it in items) + 1.0
    except OverflowError as exc:
        raise ValueError("A altura total das peças excede o limite numérico.") from exc
    if not math.isfinite(big):
        raise ValueError("A altura total das peças excede o limite numérico.")
    free = [(0.0, 0.0, inner_w, big)]
    placed = {}
    for i in idx:
        item = items[i]
        w0, h0 = _dimensions(item)
        options = [(w0 + gap, h0 + gap, False)]
        if allow_rot and abs(w0 - h0) > EPS:
            options.append((h0 + gap, w0 + gap, True))
        best = None
        for fr in free:
            for w, h, rot in options:
                if fr[2] + EPS >= w and fr[3] + EPS >= h:
                    key = _score(heuristic, fr, fr[0], fr[1], w, h)
                    if best is None or key < best[0]:
                        best = (key, fr[0], fr[1], w, h, rot)
        if best is None:
            return None
        _, x, y, w, h, rot = best
        free = _split_free(free, x, y, w, h)
        placed[i] = (x, y, rot)
    out = []
    for i, item in enumerate(items):
        x, y, rot = placed[i]
        new = LayoutItem(**asdict(item))
        if rot:
            new.rotation = (item.rotation + 90) % 360
        new.x_cm = round(margin + x, 6)
        new.y_cm = round(margin + y, 6)
        out.append(new)
    return out


def check_layout(items: Iterable[LayoutItem], sheet_width_cm: float = MAX_SHEET_WIDTH_CM,
                 margin_cm: float = DEFAULT_MARGIN_CM, gap_cm: float = DEFAULT_GAP_CM) -> bool:
    """True se todas as pecas estao dentro da largura util e sem sobreposicao (respeitando o gap)."""
    try:
        sheet_width_cm, margin_cm, gap_cm = _parameters(sheet_width_cm, margin_cm, gap_cm)
        items = validate_items((_normalized(item) for item in items), sheet_width_cm, margin_cm)
    except (TypeError, ValueError, OverflowError, AttributeError):
        return False
    boxes = []
    for it in items:
        w, h = _dimensions(it)
        if not math.isfinite(it.x_cm + w) or not math.isfinite(it.y_cm + h):
            return False
        if it.x_cm < margin_cm - EPS or it.y_cm < margin_cm - EPS:
            return False
        if it.x_cm + w > sheet_width_cm - margin_cm + EPS:
            return False
        boxes.append((it.x_cm, it.y_cm, w, h))
    for i in range(len(boxes)):
        ax, ay, aw, ah = boxes[i]
        for j in range(i + 1, len(boxes)):
            bx, by, bw, bh = boxes[j]
            if (ax < bx + bw + gap_cm - EPS and bx < ax + aw + gap_cm - EPS
                    and ay < by + bh + gap_cm - EPS and by < ay + ah + gap_cm - EPS):
                return False
    return True


def nest(items: Iterable[LayoutItem], sheet_width_cm: float = MAX_SHEET_WIDTH_CM,
         margin_cm: float = DEFAULT_MARGIN_CM, gap_cm: float = DEFAULT_GAP_CM,
         allow_rotation: bool = False) -> list[LayoutItem]:
    """Melhor posicionamento encontrado (folha mais curta). Mantem a ordem de entrada."""
    if type(allow_rotation) is not bool:
        raise ValueError("Permitir rotação precisa ser booleano.")
    sheet_width_cm, margin_cm, gap_cm = _parameters(sheet_width_cm, margin_cm, gap_cm)
    base_items = []
    for original in items:
        item = _normalized(original)
        w, h = _dimensions(item)
        if allow_rotation and w > sheet_width_cm - 2 * margin_cm + EPS and h <= sheet_width_cm - 2 * margin_cm + EPS:
            item.rotation = (item.rotation + 90) % 360
        base_items.append(item)
    base_items = validate_items(base_items, sheet_width_cm, margin_cm)
    best = auto_pack(base_items, sheet_width_cm, margin_cm, gap_cm)       # candidato de base
    best_h = sheet_height(best, margin_cm, gap_cm)
    if not math.isfinite(best_h) or not check_layout(best, sheet_width_cm, margin_cm, gap_cm):
        raise ValueError("Não foi possível criar uma folha válida.")
    if not base_items:
        return best
    for rot in ((False, True) if allow_rotation else (False,)):
        for order in ORDERS:
            for heuristic in HEURISTICS:
                cand = _pack_once(base_items, float(sheet_width_cm), float(margin_cm), gap_cm,
                                  order, heuristic, rot)
                if cand is None:
                    continue
                h = sheet_height(cand, margin_cm, gap_cm)
                if h < best_h - EPS and check_layout(cand, sheet_width_cm, margin_cm, gap_cm):
                    best, best_h = cand, h
    return best


def utilization(items: Iterable[LayoutItem], sheet_width_cm: float = MAX_SHEET_WIDTH_CM,
                margin_cm: float = DEFAULT_MARGIN_CM, gap_cm: float = DEFAULT_GAP_CM) -> float:
    """Fracao (0..1) da area da folha ocupada pelas artes."""
    sheet_width_cm, margin_cm, gap_cm = _parameters(sheet_width_cm, margin_cm, gap_cm)
    items = list(items)
    if not check_layout(items, sheet_width_cm, margin_cm, gap_cm):
        raise ValueError("O layout precisa respeitar largura, posições e espaçamento.")
    if not items:
        return 0.0
    height = sheet_height(items, margin_cm, gap_cm)
    # Dividir antes de multiplicar evita inf/inf em medidas finitas muito grandes.
    occupied = math.fsum((w / sheet_width_cm) * (h / height)
                         for w, h in (_dimensions(i) for i in items))
    return round(min(1.0, occupied), 4)
