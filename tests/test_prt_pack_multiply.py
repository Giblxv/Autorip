"""Equivalencia da escrita 2-bit, sem depender do leitor de producao."""
import numpy as np
import pytest

from autorip.prt import HEADER_SIZE, PrtWriter, pack2, plane_bytes_for


def reference_pack(a, plane_bytes):
    out = np.zeros((len(a), plane_bytes), dtype=np.uint8)
    for offset, shift in enumerate((6, 4, 2, 0)):
        part = a[:, offset::4].astype(np.uint8)
        out[:, :part.shape[1]] |= part << shift
    return out


def test_all_four_dot_patterns_have_exact_wire_bytes():
    expected = np.arange(256, dtype=np.uint8)
    levels = np.stack([(expected >> shift) & 3 for shift in (6, 4, 2, 0)], axis=1)
    before = levels.copy()
    packed = pack2(levels, 1)
    assert packed.tobytes() == expected.tobytes()
    np.testing.assert_array_equal(levels, before)
    assert not np.shares_memory(packed, levels)


@pytest.mark.parametrize("width", [1, 2, 3, 4, 5, 31, 32, 33, 1417])
@pytest.mark.parametrize("layout", ["c", "fortran", "reverse", "slice", "readonly", "broadcast"])
def test_layouts_padding_and_input_ownership(width, layout):
    rng = np.random.default_rng(width)
    a = rng.integers(0, 4, (7, width), dtype=np.uint8)
    if layout == "fortran":
        a = np.asfortranarray(a)
    elif layout == "reverse":
        a = a[::-1, ::-1]
    elif layout == "slice":
        a = rng.integers(0, 4, (14, width * 2), dtype=np.uint8)[::2, ::2]
    elif layout == "readonly":
        a.setflags(write=False)
    elif layout == "broadcast":
        a = np.broadcast_to(a[:1], a.shape)
    before = a.copy()
    for pb in (plane_bytes_for(width), plane_bytes_for(width) + 3):
        result = pack2(a, pb)
        np.testing.assert_array_equal(result, reference_pack(a, pb))
        assert result.flags.c_contiguous and result.dtype == np.uint8
        result[:] = 255
        np.testing.assert_array_equal(a, before)


@pytest.mark.parametrize("dtype", ["i1", "i2", "i8", "u2", ">u2", ">i4", "<u8"])
def test_integer_fallback_keeps_byte_order_and_levels(dtype):
    levels = (np.arange(21).reshape(3, 7) % 4).astype(dtype)
    np.testing.assert_array_equal(pack2(levels, 4), reference_pack(levels, 4))


@pytest.mark.parametrize("bad", [4, 127, 255])
def test_uint8_invalid_levels_are_rejected_without_mutation(bad):
    levels = np.array([[0, 1, 2, bad]], dtype=np.uint8)
    before = levels.copy()
    with pytest.raises(ValueError, match="0 e 3"):
        pack2(levels, 1)
    np.testing.assert_array_equal(levels, before)


def test_readonly_file_mapping_and_unaligned_buffer_are_unchanged(tmp_path):
    path = tmp_path / "levels.bin"
    path.write_bytes(bytes([255]) + bytes([0, 1, 2, 3] * 24))
    mapped = np.memmap(path, dtype=np.uint8, mode="r", offset=1, shape=(3, 32))
    np.testing.assert_array_equal(pack2(mapped, 8), np.full((3, 8), 27, dtype=np.uint8))
    del mapped
    assert path.read_bytes() == bytes([255]) + bytes([0, 1, 2, 3] * 24)


def test_multiblock_writer_keeps_order_padding_aliases_and_input(tmp_path):
    rows, width = 11, 37
    rng = np.random.default_rng(4)
    primary = rng.integers(0, 4, (rows, width), dtype=np.uint8)
    before = primary.copy()
    reverse = primary[:, ::-1]
    zeros = np.zeros_like(primary)
    planes = [primary, reverse, primary.view(), zeros] * 3
    path = tmp_path / "ordered.PRT"
    writer = PrtWriter(path, 720, 2400, rows, width)
    for start, end in ((0, 4), (4, 9), (9, 11)):
        writer.write_block([p[start:end] for p in planes])
    writer.close()
    expected = np.stack([reference_pack(p, writer.pb) for p in planes], axis=1)
    assert path.read_bytes()[HEADER_SIZE:] == expected.tobytes()
    np.testing.assert_array_equal(primary, before)
