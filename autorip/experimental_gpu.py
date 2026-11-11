"""Backend experimental opcional para morfologia/EDT em GPU.

CuPy e cupyx são opcionais. Em máquinas sem CUDA o módulo permanece importável
e informa indisponibilidade; o motor CPU não é alterado.
"""
from __future__ import annotations

import numpy as np


def status():
    result = {"cupy": False, "cuda": False, "numba": False, "reason": ""}
    try:
        import cupy as cp
        result["cupy"] = True
        try:
            result["cuda"] = cp.cuda.runtime.getDeviceCount() > 0
        except Exception as exc:
            result["reason"] = f"CuPy presente, CUDA indisponível: {exc}"
    except Exception as exc:
        result["reason"] = f"CuPy não instalado: {exc}"
    try:
        import numba.cuda
        result["numba"] = bool(numba.cuda.is_available())
    except Exception:
        pass
    return result


def _cupy_or_raise():
    try:
        import cupy as cp
        import cupyx.scipy.ndimage as cndi
    except Exception as exc:
        raise RuntimeError("Backend CuPy/CUDA indisponível; use a implementação CPU.") from exc
    try:
        if cp.cuda.runtime.getDeviceCount() < 1:
            raise RuntimeError("Nenhum dispositivo CUDA encontrado.")
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError("Não foi possível consultar CUDA.") from exc
    return cp, cndi


def distance_transform_edt(mask, sampling=(1.0, 1.0)):
    """Calcula EDT na GPU e retorna ndarray NumPy para comparação determinística."""
    cp, cndi = _cupy_or_raise()
    device_mask = cp.asarray(np.asarray(mask, dtype=bool))
    result = cndi.distance_transform_edt(device_mask, sampling=sampling)
    return cp.asnumpy(result)


def dilate(mask, radius, sampling=(1.0, 1.0)):
    """Dilation experimental em GPU a partir de EDT do fundo."""
    array = np.asarray(mask, dtype=bool)
    if radius < 0:
        raise ValueError("radius precisa ser não negativo")
    if not radius or not array.any():
        return array.copy()
    return distance_transform_edt(~array, sampling=sampling) <= radius


def erode(mask, radius, sampling=(1.0, 1.0)):
    """Erosion experimental em GPU com padding de borda compatível com CPU."""
    array = np.asarray(mask, dtype=bool)
    if radius < 0:
        raise ValueError("radius precisa ser não negativo")
    if not radius or not array.any():
        return array.copy()
    padded = np.pad(array, 1, constant_values=False)
    distance = distance_transform_edt(padded, sampling=sampling)
    return (distance > radius)[1:-1, 1:-1]
