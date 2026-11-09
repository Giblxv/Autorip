"""Morfologia circular em milímetros, respeitando os dois eixos de DPI.

EDT evita kernels retangulares grandes. Fora da imagem sempre é fundo;
nenhuma operação pode criar branco em uma máscara inteiramente vazia.
"""
import math

import numpy as np
from scipy import ndimage as ndi


def _parameters(mask, mm, dpi_x, dpi_y):
    if not all(math.isfinite(v) and v > 0 for v in (dpi_x, dpi_y)):
        raise ValueError("O DPI precisa ser positivo e finito.")
    if not math.isfinite(mm) or mm < 0:
        raise ValueError("O raio precisa ser positivo ou zero e finito.")
    mask = np.asarray(mask, dtype=bool)
    if mask.ndim != 2 or not mask.size:
        raise ValueError("A mascara precisa ser uma matriz 2-D nao vazia.")
    return mask, mm / 25.4, (1.0 / dpi_y, 1.0 / dpi_x)


def dilate(mask, mm, dpi_x, dpi_y):
    mask, radius, sampling = _parameters(mask, mm, dpi_x, dpi_y)
    if not radius or not mask.any():
        return mask
    # Sem primeiro plano, EDT(~mask) mediria uma borda virtual e criaria tinta.
    return ndi.distance_transform_edt(~mask, sampling=sampling) <= radius


def erode(mask, mm, dpi_x, dpi_y):
    """Recua o primeiro plano; a borda externa também participa da erosão."""
    mask, radius, sampling = _parameters(mask, mm, dpi_x, dpi_y)
    if not radius or not mask.any():
        return mask
    padded = np.pad(mask, 1, constant_values=False)
    distance = ndi.distance_transform_edt(padded, sampling=sampling)
    return (distance > radius)[1:-1, 1:-1]


def close_holes(mask, mm, dpi_x, dpi_y):
    """Dilata e erode com disco físico, preservando objetos junto às bordas."""
    mask, radius, _ = _parameters(mask, mm, dpi_x, dpi_y)
    if not radius or not mask.any():
        return mask
    ry = math.ceil(radius * dpi_y) + 1
    rx = math.ceil(radius * dpi_x) + 1
    padded = np.pad(mask, ((ry, ry), (rx, rx)), constant_values=False)
    closed = erode(dilate(padded, mm, dpi_x, dpi_y), mm, dpi_x, dpi_y)
    # Cópia compacta: não mantém todo o buffer com padding vivo no renderizador.
    return closed[ry:ry + mask.shape[0], rx:rx + mask.shape[1]].copy()
