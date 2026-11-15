import numpy as np
import pytest

from autorip import prt


@pytest.mark.parametrize("width", [1, 2, 3, 4, 31, 32, 33, 1417, 5669])
@pytest.mark.parametrize("layout", ["c", "fortran", "reverse", "broadcast", "readonly"])
def test_empty_plane_returns_private_zero_bytes_including_padding(width, layout):
    levels = np.zeros((7, width), dtype=np.uint8)
    if layout == "fortran":
        levels = np.asfortranarray(levels)
    elif layout == "reverse":
        levels = levels[::-1, ::-1]
    elif layout == "broadcast":
        levels = np.broadcast_to(levels[:1], levels.shape)
    elif layout == "readonly":
        levels.setflags(write=False)
    pb = prt.plane_bytes_for(width) + 3
    packed = prt.pack2(levels, pb)
    assert packed.shape == (7, pb) and packed.dtype == np.uint8
    assert packed.flags.c_contiguous and packed.tobytes() == bytes(7 * pb)
    packed[:] = 255
    assert not levels.any()
    assert not prt.pack2(levels, pb).any()


@pytest.mark.parametrize("level", [1, 2, 3, 4, 255])
def test_last_nonzero_dot_is_never_discarded(level):
    levels = np.zeros((17, 37), dtype=np.uint8)
    levels[-1, -1] = level
    if level > 3:
        with pytest.raises(ValueError, match="0 e 3"):
            prt.pack2(levels, prt.plane_bytes_for(37))
    else:
        packed = prt.pack2(levels, prt.plane_bytes_for(37))
        expected = np.zeros_like(packed)
        expected[-1, 9] = level << 6
        np.testing.assert_array_equal(packed, expected)
    assert levels[-1, -1] == level


def test_multiblock_writer_preserves_shared_empty_planes_and_one_ink_dot(tmp_path):
    width, rows = 37, 13
    empty = np.zeros((rows, width), dtype=np.uint8)
    color = empty.copy()
    color[-1, -1] = 3
    path = tmp_path / "sparse.PRT"
    writer = prt.PrtWriter(path, 720, 2400, rows, width)
    for start, end in ((0, 5), (5, 11), (11, 13)):
        zero = empty[start:end]
        writer.write_block([zero] * 3 + [color[start:end]] + [zero.view()] * 8)
    writer.close()
    expected = np.zeros((rows, 12, writer.pb), dtype=np.uint8)
    expected[-1, 3, 9] = 3 << 6
    assert path.read_bytes()[prt.HEADER_SIZE:] == expected.tobytes()
    assert not empty.any() and color[-1, -1] == 3
