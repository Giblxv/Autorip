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
    return _distance(~mask, sampling=sampling) <= radius


def erode(mask, mm, dpi_x, dpi_y):
    """Recua o primeiro plano; a borda externa também participa da erosão."""
    mask, radius, sampling = _parameters(mask, mm, dpi_x, dpi_y)
    if not radius or not mask.any():
        return mask
    if mask.all():
        # O fundo mais próximo está em uma das quatro bordas externas.
        axes = []
        for size, step in zip(mask.shape, sampling):
            distance = np.minimum(np.arange(1, size + 1, dtype=np.float64),
                                  np.arange(size, 0, -1, dtype=np.float64))
            distance *= step
            np.square(distance, out=distance)
            np.sqrt(distance, out=distance)
            axes.append(distance > radius)
        return axes[0][:, None] & axes[1][None, :]
    bounds = _compact_bounds(mask)
    if bounds is not None:
        y0, y1, x0, x1 = bounds
        out = np.zeros(mask.shape, dtype=bool)
        out[y0:y1, x0:x1] = _erode_region(mask[y0:y1, x0:x1], radius, sampling)
        return out
    return _erode_region(mask, radius, sampling)


def _compact_bounds(mask):
    """O suporte pode ser recortado; não materialize coordenadas de todos os pixels."""
    rows = np.flatnonzero(mask.any(axis=1))
    columns = np.flatnonzero(mask.any(axis=0))
    y0, y1 = int(rows[0]), int(rows[-1]) + 1
    x0, x1 = int(columns[0]), int(columns[-1]) + 1
    return (y0, y1, x0, x1) if (y1-y0)*(x1-x0) < mask.size * .75 else None


def _erode_region(mask, radius, sampling):
    padded = np.pad(mask, 1, constant_values=False)
    distance = _distance(padded, sampling=sampling)
    return (distance > radius)[1:-1, 1:-1]


def close_holes(mask, mm, dpi_x, dpi_y):
    """Dilata e erode com disco físico, preservando objetos junto às bordas."""
    mask, radius, _ = _parameters(mask, mm, dpi_x, dpi_y)
    # Fechar uma máscara totalmente preenchida com exterior vazio a preserva.
    if not radius or not mask.any() or mask.all():
        return mask
    bounds = _compact_bounds(mask)
    original_shape = mask.shape
    if bounds is not None:
        y0, y1, x0, x1 = bounds
        mask = mask[y0:y1, x0:x1]
    ry = math.ceil(radius * dpi_y) + 1
    rx = math.ceil(radius * dpi_x) + 1
    padded = np.pad(mask, ((ry, ry), (rx, rx)), constant_values=False)
    closed = erode(dilate(padded, mm, dpi_x, dpi_y), mm, dpi_x, dpi_y)
    # Cópia compacta: não mantém todo o buffer com padding vivo no renderizador.
    result = closed[ry:ry + mask.shape[0], rx:rx + mask.shape[1]]
    if bounds is not None:
        out = np.zeros(original_shape, dtype=bool)
        out[y0:y1, x0:x1] = result
        return out
    return result.copy()


def _distance(mask, sampling):
    indices = ndi.distance_transform_edt(mask, sampling=sampling,
                                         return_distances=False, return_indices=True)
    indices[0] -= np.arange(mask.shape[0], dtype=np.int32)[:, None]
    indices[1] -= np.arange(mask.shape[1], dtype=np.int32)[None, :]
    y = indices[0].astype(np.float64)
    y *= sampling[0]
    np.square(y, out=y)
    # A componente horizontal não precisa de outro raster float64 inteiro.
    rows = max(1, min(mask.shape[0], (1024 * 1024) // (8 * mask.shape[1])))
    scratch = np.empty((rows, mask.shape[1]), dtype=np.float64)
    for start in range(0, mask.shape[0], rows):
        end = min(mask.shape[0], start + rows)
        x = scratch[:end-start]
        np.multiply(indices[1, start:end], sampling[1], out=x)
        np.square(x, out=x)
        np.add(y[start:end], x, out=y[start:end])
    return np.sqrt(y, out=y)
