import numpy as np

from autorip.prt import pack2, plane_bytes_for
from benchmarks.benchmark_halftone_scheduler import fused_halftone_pack2


def test_fused_halftone_pack2_is_byte_identical():
    rng = np.random.default_rng(91)
    values = rng.random((37, 101), dtype=np.float32)
    thresholds = rng.random((37, 101), dtype=np.float32)
    ratio = 0.4
    plane_bytes = plane_bytes_for(values.shape[1])
    levels = np.where(((values - ratio) / (1.0 - ratio)) > thresholds,
                      np.uint8(3), ((values / ratio) > thresholds).astype(np.uint8))
    expected = pack2(levels, plane_bytes)
    actual = fused_halftone_pack2(values, thresholds, ratio, plane_bytes)
    assert np.array_equal(actual, expected)
