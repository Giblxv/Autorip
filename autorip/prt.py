"""Leitor/gravador do formato .PRT (engenharia de formato a partir de arquivo proprio do usuario).

Layout verificado em 30x20cm_S00229_SM.PRT:
  cabecalho de 48 bytes = 12 dwords little-endian:
    [0x5555, dpi_x, dpi_y, plane_bytes, n_rows, n_dots, 0, n_channels, bits_per_dot, 0, 1, 0]
  corpo: n_rows linhas; cada linha = n_channels planos de plane_bytes bytes;
  cada ponto = 2 bits (0..3), 4 pontos por byte, primeiro ponto no bit mais significativo.
  Canais 0-3 = CMYK, canais 4..11 = branco.
"""
import struct
import numpy as np

HEADER_SIZE = 48
MAGIC = 0x5555


def plane_bytes_for(n_dots: int, align: int = 32) -> int:
    dots = ((n_dots + align - 1) // align) * align   # 5669 -> 5696
    return dots // 4                                   # 5696/4 = 1424


def pack2(a: np.ndarray, plane_bytes: int) -> np.ndarray:
    """(rows, dots) valores 0..3 -> (rows, plane_bytes) uint8."""
    rows, dots = a.shape
    full = plane_bytes * 4
    if dots < full:
        a = np.pad(a, ((0, 0), (0, full - dots)))
    a = a.astype(np.uint8) & 3
    a = a.reshape(rows, plane_bytes, 4)
    return (a[..., 0] << 6) | (a[..., 1] << 4) | (a[..., 2] << 2) | a[..., 3]


def unpack2(b: np.ndarray, n_dots: int) -> np.ndarray:
    d = np.stack([(b >> 6) & 3, (b >> 4) & 3, (b >> 2) & 3, b & 3], axis=-1)
    return d.reshape(b.shape[0], -1)[:, :n_dots]


def make_header(dpi_x, dpi_y, plane_bytes, n_rows, n_dots, n_channels=12, bits=2):
    return struct.pack("<12I", MAGIC, dpi_x, dpi_y, plane_bytes, n_rows, n_dots, 0,
                       n_channels, bits, 0, 1, 0)


def read_header(path):
    with open(path, "rb") as f:
        h = struct.unpack("<12I", f.read(HEADER_SIZE))
    return dict(magic=h[0], dpi_x=h[1], dpi_y=h[2], plane_bytes=h[3], n_rows=h[4],
                n_dots=h[5], n_channels=h[7], bits=h[8])


class PrtWriter:
    """Grava .PRT linha a linha em blocos (baixo uso de memoria)."""

    def __init__(self, path, dpi_x, dpi_y, n_rows, n_dots, n_channels=12):
        self.pb = plane_bytes_for(n_dots)
        self.n_channels = n_channels
        self.n_rows, self.n_dots = n_rows, n_dots
        self.f = open(path, "wb")
        self.f.write(make_header(dpi_x, dpi_y, self.pb, n_rows, n_dots, n_channels))
        self.written = 0

    def write_block(self, planes):
        """planes: lista de n_channels arrays (rows, dots) com valores 0..3."""
        rows = planes[0].shape[0]
        out = np.empty((rows, self.n_channels, self.pb), dtype=np.uint8)
        for i, p in enumerate(planes):
            out[:, i, :] = pack2(p, self.pb)
        self.f.write(out.tobytes())
        self.written += rows

    def close(self):
        self.f.close()
        if self.written != self.n_rows:
            raise RuntimeError(f"linhas gravadas {self.written} != {self.n_rows}")


def read_rows(path, y0, y1):
    h = read_header(path)
    row = h["n_channels"] * h["plane_bytes"]
    m = np.memmap(path, dtype=np.uint8, mode="r", offset=HEADER_SIZE,
                  shape=(h["n_rows"], h["n_channels"], h["plane_bytes"]))
    blk = np.array(m[y0:y1])
    return [unpack2(blk[:, c, :], h["n_dots"]) for c in range(h["n_channels"])]
