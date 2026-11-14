"""Planejamento de folha para imposição DTF/DTF UV.

Este módulo trabalha em centímetros e não gera PRT por si só. Ele fornece um
modelo determinístico para preview, edição manual e posterior composição da
folha no motor RIP.
"""
from __future__ import annotations

import html
import math
import os
from dataclasses import asdict, dataclass
from collections.abc import Iterable

from .imaging import Image

MAX_SHEET_WIDTH_CM = 58.0
DEFAULT_MARGIN_CM = 0.20
DEFAULT_GAP_CM = 0.20


@dataclass
class ImageInfo:
    path: str
    name: str
    width_px: int
    height_px: int
    dpi_x: float
    dpi_y: float
    width_cm: float
    height_cm: float
    bytes: int
    format: str
    has_alpha: bool

    def as_dict(self):
        return asdict(self)


@dataclass
class LayoutItem:
    id: str
    name: str
    path: str
    source_width_px: int
    source_height_px: int
    width_cm: float
    height_cm: float
    x_cm: float = 0.0
    y_cm: float = 0.0
    rotation: int = 0
    selected: bool = False

    def normalized(self) -> "LayoutItem":
        rotation = int(self.rotation) % 360
        if rotation not in (0, 90, 180, 270):
            raise ValueError("A rotação precisa ser 0, 90, 180 ou 270 graus.")
        if not all(math.isfinite(float(v)) for v in (self.width_cm, self.height_cm, self.x_cm, self.y_cm)):
            raise ValueError("As dimensões e posições precisam ser números finitos.")
        if self.width_cm <= 0 or self.height_cm <= 0:
            raise ValueError("A imagem precisa ter dimensões positivas na folha.")
        return LayoutItem(**{**asdict(self), "rotation": rotation})

    def as_dict(self):
        return asdict(self)


def _dpi(value, fallback=300.0):
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def inspect_image(path: str) -> ImageInfo:
    """Lê somente cabeçalho/metadados; não materializa a imagem inteira."""
    if os.path.islink(path) or not os.path.isfile(path):
        raise FileNotFoundError(path)
    size = os.path.getsize(path)
    with Image.open(path) as opened:
        # Use o leitor base: PNG.getexif pode decodificar pixels para buscar
        # chunks EXIF apos os dados da imagem, fora do contrato de cabecalho.
        orientation = Image.Image.getexif(opened).get(274, 1)
        dpi = opened.info.get("dpi", (300, 300))
        dpi_x = _dpi(dpi[0] if isinstance(dpi, (tuple, list)) else dpi)
        dpi_y = _dpi(dpi[1] if isinstance(dpi, (tuple, list)) and len(dpi) > 1 else dpi_x)
        width, height = opened.size
        if orientation in (5, 6, 7, 8):
            width, height = height, width
            dpi_x, dpi_y = dpi_y, dpi_x
        mode = opened.mode
        has_alpha = mode in ("RGBA", "LA", "PA") or "transparency" in opened.info
        return ImageInfo(
            path=os.path.realpath(path), name=os.path.basename(path),
            width_px=int(width), height_px=int(height), dpi_x=dpi_x, dpi_y=dpi_y,
            width_cm=width / dpi_x * 2.54, height_cm=height / dpi_y * 2.54,
            bytes=int(size), format=str(opened.format or ""), has_alpha=bool(has_alpha),
        )


def proportional_size(info: ImageInfo, width_cm: float | None = None,
                      height_cm: float | None = None,
                      max_width_cm: float = MAX_SHEET_WIDTH_CM) -> tuple[float, float]:
    """Calcula tamanho proporcional, priorizando largura quando informada."""
    if max_width_cm <= 0 or not math.isfinite(max_width_cm):
        raise ValueError("A largura máxima da folha precisa ser positiva.")
    ratio = info.height_cm / info.width_cm if info.width_cm > 0 else info.height_px / info.width_px
    target_width = width_cm if width_cm is not None else None
    if target_width is None and height_cm is not None:
        target_width = float(height_cm) / ratio
    if target_width is None:
        target_width = info.width_cm
    target_width = float(target_width)
    if not math.isfinite(target_width) or target_width <= 0:
        raise ValueError("A largura desejada precisa ser positiva.")
    target_width = min(target_width, float(max_width_cm))
    target_height = target_width * ratio
    return round(target_width, 6), round(target_height, 6)


def make_item(info: ImageInfo, width_cm: float | None = None, *, item_id: str | None = None,
              max_width_cm: float = MAX_SHEET_WIDTH_CM) -> LayoutItem:
    width, height = proportional_size(info, width_cm=width_cm, max_width_cm=max_width_cm)
    return LayoutItem(
        id=item_id or info.name,
        name=info.name, path=info.path,
        source_width_px=info.width_px, source_height_px=info.height_px,
        width_cm=width, height_cm=height,
    )


def _dimensions(item: LayoutItem):
    if item.rotation in (90, 270):
        return item.height_cm, item.width_cm
    return item.width_cm, item.height_cm


def validate_items(items: Iterable[LayoutItem], sheet_width_cm: float = MAX_SHEET_WIDTH_CM,
                   margin_cm: float = DEFAULT_MARGIN_CM):
    sheet_width_cm = float(sheet_width_cm)
    margin_cm = float(margin_cm)
    if not math.isfinite(sheet_width_cm) or sheet_width_cm <= 0 or sheet_width_cm > MAX_SHEET_WIDTH_CM:
        raise ValueError(f"A largura da folha deve ficar entre 0 e {MAX_SHEET_WIDTH_CM:g} cm.")
    if not math.isfinite(margin_cm) or margin_cm < 0 or margin_cm * 2 >= sheet_width_cm:
        raise ValueError("A margem da folha é inválida.")
    normalized = [item.normalized() for item in items]
    for item in normalized:
        width, _ = _dimensions(item)
        if width > sheet_width_cm - 2 * margin_cm + 1e-6:
            raise ValueError(f"A imagem {item.name} excede a largura útil da folha; reduza seu tamanho.")
    return normalized


def auto_pack(items: Iterable[LayoutItem], sheet_width_cm: float = MAX_SHEET_WIDTH_CM,
              margin_cm: float = DEFAULT_MARGIN_CM, gap_cm: float = DEFAULT_GAP_CM) -> list[LayoutItem]:
    """Empacota por faixas, preservando dimensões e evitando sobreposição."""
    gap_cm = float(gap_cm)
    if not math.isfinite(gap_cm) or gap_cm < 0:
        raise ValueError("O espaçamento precisa ser zero ou positivo.")
    ordered = validate_items(items, sheet_width_cm, margin_cm)
    x = margin_cm
    y = margin_cm
    row_height = 0.0
    packed = []
    for original in ordered:
        item = LayoutItem(**asdict(original))
        width, height = _dimensions(item)
        if x > margin_cm and x + width > sheet_width_cm - margin_cm + 1e-6:
            x = margin_cm
            y += row_height + gap_cm
            row_height = 0.0
        item.x_cm = round(x, 6)
        item.y_cm = round(y, 6)
        packed.append(item)
        x += width + gap_cm
        row_height = max(row_height, height)
    return packed


def sheet_height(items: Iterable[LayoutItem], margin_cm: float = DEFAULT_MARGIN_CM,
                 gap_cm: float = DEFAULT_GAP_CM) -> float:
    max_bottom = float(margin_cm)
    for item in items:
        _, height = _dimensions(item)
        max_bottom = max(max_bottom, item.y_cm + height)
    return round(max_bottom + float(margin_cm), 6)


def layout_to_svg(items: Iterable[LayoutItem], sheet_width_cm: float = MAX_SHEET_WIDTH_CM,
                  margin_cm: float = DEFAULT_MARGIN_CM, gap_cm: float = DEFAULT_GAP_CM) -> str:
    """Gera preview leve, sem carregar os bitmaps; o frontend pode substituir imagens por thumbs."""
    items = validate_items(items, sheet_width_cm, margin_cm)
    height = max(sheet_height(items, margin_cm, gap_cm), margin_cm * 2)
    def esc(value):
        return html.escape(str(value), quote=True)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {sheet_width_cm:g} {height:g}" '
             f'width="{sheet_width_cm:g}cm" height="{height:g}cm">',
             '<rect width="100%" height="100%" fill="#f7f0dc" stroke="#1a1a1a" stroke-width="0.08"/>']
    for index, item in enumerate(items):
        width, item_height = _dimensions(item)
        # O retangulo ja representa a caixa ocupada apos a rotacao.
        parts.append(f'<g transform="translate({item.x_cm:g} {item.y_cm:g})" data-rotation="{item.rotation}">')
        parts.append(f'<rect width="{width:g}" height="{item_height:g}" rx="0.12" fill="#00aeef" fill-opacity=".22" stroke="#1a1a1a" stroke-width=".06"/>')
        label = esc(item.name[:32])
        parts.append(f'<text x="{width/2:g}" y="{item_height/2:g}" text-anchor="middle" dominant-baseline="middle" font-size="{max(.22, min(.8, width/12)):g}" fill="#1a1a1a">{label}</text>')
        parts.append('</g>')
    parts.append('</svg>')
    return ''.join(parts)
