"""Leitor/gravador do formato .PRT inferido de arquivo de referencia do usuario.

O layout deve ser tratado como especifico do equipamento e ainda precisa de prova
em uma impressora real; esta rotina valida a estrutura interna, nao a compatibilidade
com todo RIP/controlador.
"""
import os
import struct
import numpy as np

HEADER_SIZE = 48
MAGIC = 0x5555
MAX_CHANNELS = 12


def plane_bytes_for(n_dots: int, align: int = 32) -> int:
    if type(n_dots) is not int or n_dots <= 0:
        raise ValueError("n_dots precisa ser um inteiro positivo.")
    if type(align) is not int or align <= 0 or align % 4:
        raise ValueError("align precisa ser um inteiro positivo, multiplo de 4.")
    dots = ((n_dots + align - 1) // align) * align
    return dots // 4


def pack2(a: np.ndarray, plane_bytes: int) -> np.ndarray:
    """Codifica uma matriz 2-D com niveis inteiros 0..3 em quatro pontos por byte."""
    a = np.asarray(a)
    if a.ndim != 2 or a.shape[0] <= 0 or a.shape[1] <= 0:
        raise ValueError("cada plano precisa ser uma matriz 2-D nao vazia.")
    if type(plane_bytes) is not int or plane_bytes <= 0 or a.shape[1] > plane_bytes * 4:
        raise ValueError("plane_bytes nao comporta a largura do plano.")
    if not np.issubdtype(a.dtype, np.integer) or np.any(a < 0) or np.any(a > 3):
        raise ValueError("niveis do plano precisam ser inteiros entre 0 e 3.")
    rows, dots = a.shape
    full = plane_bytes * 4
    if dots < full:
        a = np.pad(a, ((0, 0), (0, full - dots)))
    a = a.astype(np.uint8, copy=False).reshape(rows, plane_bytes, 4)
    return (a[..., 0] << 6) | (a[..., 1] << 4) | (a[..., 2] << 2) | a[..., 3]


def unpack2(b: np.ndarray, n_dots: int) -> np.ndarray:
    b = np.asarray(b)
    if b.ndim != 2 or not np.issubdtype(b.dtype, np.integer):
        raise ValueError("dados compactados precisam ser uma matriz 2-D de inteiros.")
    if type(n_dots) is not int or n_dots <= 0 or n_dots > b.shape[1] * 4:
        raise ValueError("n_dots nao cabe nos bytes fornecidos.")
    d = np.stack([(b >> 6) & 3, (b >> 4) & 3, (b >> 2) & 3, b & 3], axis=-1)
    return d.reshape(b.shape[0], -1)[:, :n_dots]


def make_header(dpi_x, dpi_y, plane_bytes, n_rows, n_dots, n_channels=12, bits=2):
    values = (dpi_x, dpi_y, plane_bytes, n_rows, n_dots, n_channels, bits)
    if any(type(value) is not int or value <= 0 or value >= 2**32 for value in values):
        raise ValueError("campos do cabecalho PRT precisam ser inteiros positivos de 32 bits.")
    if n_channels > MAX_CHANNELS or bits != 2 or plane_bytes * 4 < n_dots:
        raise ValueError("dimensoes, canais ou profundidade de pontos invalidos para PRT.")
    return struct.pack("<12I", MAGIC, dpi_x, dpi_y, plane_bytes, n_rows, n_dots, 0,
                       n_channels, bits, 0, 1, 0)


def read_header(path):
    with open(path, "rb") as f:
        raw = f.read(HEADER_SIZE)
        file_size = os.fstat(f.fileno()).st_size
    if len(raw) != HEADER_SIZE:
        raise ValueError("cabecalho PRT truncado.")
    h = struct.unpack("<12I", raw)
    result = dict(magic=h[0], dpi_x=h[1], dpi_y=h[2], plane_bytes=h[3], n_rows=h[4],
                  n_dots=h[5], n_channels=h[7], bits=h[8])
    if result["magic"] != MAGIC:
        raise ValueError("assinatura PRT invalida.")
    if any(result[k] <= 0 for k in ("dpi_x", "dpi_y", "plane_bytes", "n_rows", "n_dots", "n_channels")):
        raise ValueError("dimensoes PRT precisam ser positivas.")
    if result["n_channels"] > MAX_CHANNELS or result["bits"] != 2:
        raise ValueError("quantidade de canais ou profundidade PRT nao suportada.")
    if result["n_dots"] > result["plane_bytes"] * 4:
        raise ValueError("plane_bytes nao comporta n_dots no cabecalho PRT.")
    minimum_size = HEADER_SIZE + result["n_rows"] * result["n_channels"] * result["plane_bytes"]
    if file_size < minimum_size:
        raise ValueError("corpo PRT truncado.")
    return result


class PrtWriter:
    """Grava .PRT em blocos e rejeita planos incompletos ou fora da geometria."""

    def __init__(self, path, dpi_x, dpi_y, n_rows, n_dots, n_channels=12):
        self.pb = plane_bytes_for(n_dots)
        self.n_channels = n_channels
        self.n_rows, self.n_dots = n_rows, n_dots
        header = make_header(dpi_x, dpi_y, self.pb, n_rows, n_dots, n_channels)
        self.f = open(path, "wb")
        self.written = 0
        try:
            self.f.write(header)
        except BaseException:
            self.f.close()
            raise

    def write_block(self, planes):
        if self.f.closed:
            raise ValueError("o arquivo PRT ja foi fechado.")
        if not isinstance(planes, (list, tuple)) or len(planes) != self.n_channels:
            raise ValueError(f"o bloco precisa conter exatamente {self.n_channels} planos.")
        arrays = [np.asarray(plane) for plane in planes]
        if any(plane.ndim != 2 for plane in arrays):
            raise ValueError("todos os planos precisam ser matrizes 2-D.")
        rows = arrays[0].shape[0]
        if rows <= 0 or rows > self.n_rows - self.written:
            raise ValueError("quantidade de linhas excede o restante declarado no PRT.")
        if any(plane.shape != (rows, self.n_dots) for plane in arrays):
            raise ValueError("todos os planos precisam ter a mesma forma (linhas, n_dots).")
        out = np.empty((rows, self.n_channels, self.pb), dtype=np.uint8)
        for index, plane in enumerate(arrays):
            out[:, index, :] = pack2(plane, self.pb)
        self.f.write(out.tobytes())
        self.written += rows

    def close(self):
        if self.f.closed:
            return
        expected_size = HEADER_SIZE + self.n_rows * self.n_channels * self.pb
        actual_size = self.f.tell()
        self.f.flush()
        self.f.close()
        if self.written != self.n_rows or actual_size != expected_size:
            raise RuntimeError(f"arquivo PRT incompleto: {self.written}/{self.n_rows} linhas, {actual_size}/{expected_size} bytes.")


def read_rows(path, y0, y1):
    h = read_header(path)
    if type(y0) is not int or type(y1) is not int or y0 < 0 or y1 < y0 or y1 > h["n_rows"]:
        raise ValueError("intervalo de linhas fora dos limites do PRT.")
    if y0 == y1:
        return [np.empty((0, h["n_dots"]), dtype=np.uint8) for _ in range(h["n_channels"])]
    mapped = np.memmap(path, dtype=np.uint8, mode="r", offset=HEADER_SIZE,
                       shape=(h["n_rows"], h["n_channels"], h["plane_bytes"]))
    block = np.array(mapped[y0:y1])
    del mapped
    return [unpack2(block[:, channel, :], h["n_dots"]) for channel in range(h["n_channels"])]
