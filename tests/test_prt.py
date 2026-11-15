import os
import tempfile

import numpy as np
import pytest

from autorip.prt import (HEADER_SIZE, PrtWriter, make_header, pack2, plane_bytes_for,
                         read_header, read_rows, unpack2)


def test_pack_roundtrip():
    a = np.random.default_rng(7).integers(0, 4, (7, 5669), dtype=np.uint8)
    pb = plane_bytes_for(5669)
    assert pb == 1424
    assert np.array_equal(unpack2(pack2(a, pb), 5669), a)


def test_writer_header_e_tamanho():
    path = os.path.join(tempfile.mkdtemp(), "t.PRT")
    writer = PrtWriter(path, 720, 2400, 10, 100)
    writer.write_block([np.full((10, 100), 3, np.uint8)] * 12)
    writer.close()
    header = read_header(path)
    assert (header["dpi_x"], header["dpi_y"], header["n_channels"], header["bits"]) == (720, 2400, 12, 2)
    assert os.path.getsize(path) == HEADER_SIZE + 10 * 12 * header["plane_bytes"]
    assert np.all(read_rows(path, 0, 10)[4] == 3)


def test_rejeita_niveis_ou_dimensoes_invalidos():
    with pytest.raises(ValueError, match="0 e 3"):
        pack2(np.full((2, 4), 4, dtype=np.uint8), 1)
    with pytest.raises(ValueError, match="inteiro positivo"):
        plane_bytes_for(0)
    with pytest.raises(ValueError, match="inteiros positivos"):
        make_header(0, 300, 8, 10, 32)


def test_writer_exige_exatamente_12_planos_e_geometria_consistente(tmp_path):
    writer = PrtWriter(tmp_path / "incompleto.PRT", 300, 300, 2, 8)
    with pytest.raises(ValueError, match="exatamente 12"):
        writer.write_block([np.zeros((2, 8), dtype=np.uint8)] * 11)
    with pytest.raises(ValueError, match="mesma forma"):
        writer.write_block([np.zeros((2, 8), dtype=np.uint8)] * 11 + [np.zeros((2, 7), dtype=np.uint8)])
    writer.f.close()


def test_close_detecta_arquivo_incompleto(tmp_path):
    writer = PrtWriter(tmp_path / "curto.PRT", 300, 300, 3, 8)
    writer.write_block([np.zeros((2, 8), dtype=np.uint8)] * 12)
    with pytest.raises(RuntimeError, match="incompleto"):
        writer.close()


def test_leitor_rejeita_cabecalho_e_corpo_truncados(tmp_path):
    path = tmp_path / "truncado.PRT"
    path.write_bytes(b"abc")
    with pytest.raises(ValueError, match="cabecalho"):
        read_header(path)
    path.write_bytes(make_header(300, 300, 2, 3, 8, 12) + b"\x00")
    with pytest.raises(ValueError, match="corpo"):
        read_header(path)


def test_read_rows_rejeita_intervalo_fora_do_arquivo(tmp_path):
    path = tmp_path / "valido.PRT"
    writer = PrtWriter(path, 300, 300, 2, 8)
    writer.write_block([np.zeros((2, 8), dtype=np.uint8)] * 12)
    writer.close()
    with pytest.raises(ValueError, match="intervalo"):
        read_rows(path, 0, 3)



def test_writer_sincroniza_arquivo_completo_antes_de_fechar(tmp_path, monkeypatch):
    from autorip import prt

    original_fsync = prt.os.fsync
    synchronized = []

    def spy(fd):
        synchronized.append(fd)
        return original_fsync(fd)

    monkeypatch.setattr(prt.os, "fsync", spy)
    writer = PrtWriter(tmp_path / "duravel.PRT", 300, 300, 1, 8)
    writer.write_block([np.zeros((1, 8), dtype=np.uint8)] * 12)
    writer.close()
    assert writer.f.closed
    assert len(synchronized) == 1


def test_rip_nao_publica_arquivo_se_fsync_falhar(tmp_path, sample_png, monkeypatch):
    from autorip import prt
    from autorip.config import Settings
    from autorip.engine import Rip

    def unavailable(_fd):
        raise OSError("falha de sincronizacao")

    monkeypatch.setattr(prt.os, "fsync", unavailable)
    result = tmp_path / "sem-fsync.PRT"
    with pytest.raises(OSError, match="sincronizacao"):
        Rip(Settings(dpi_x=300, dpi_y=300, label_enabled=False)).process(
            str(sample_png), str(result), width_cm=2.54)
    assert not result.exists()
    assert not list(tmp_path.glob("*.part"))


@pytest.mark.parametrize("rows,packed_width", [(1, 1), (7, 8), (23, 1424)])
def test_unpack2_uint8_tabela_preserva_niveis_e_padding(rows, packed_width):
    """Todos os bytes, alinhamentos e cortes mantêm a ordem exata dos 2 bits."""
    rng = np.random.default_rng(rows * 10000 + packed_width)
    raw = rng.integers(0, 256, (rows, packed_width), dtype=np.uint8)
    # Acesso ao memmap da leitura PRT pode entregar matrizes com strides.
    for packed in (raw, raw[:, ::2]):
        for padding in (0, 1, 2, 3):
            dots = packed.shape[1] * 4 - padding
            reference = np.stack(
                [(packed >> 6) & 3, (packed >> 4) & 3,
                 (packed >> 2) & 3, packed & 3], axis=-1
            ).reshape(rows, -1)[:, :dots]
            decoded = unpack2(packed, dots)
            assert decoded.shape == reference.shape
            assert decoded.dtype == reference.dtype
            assert np.array_equal(decoded, reference)


@pytest.mark.parametrize("dtype", [np.int16, np.uint16, np.int64])
def test_unpack2_outros_inteiros_preservam_dtype_e_semantica(dtype):
    values = np.array([[0, 255, 170, 85], [3, 127, 15, 64]], dtype=dtype)
    expected = np.stack(
        [(values >> 6) & 3, (values >> 4) & 3,
         (values >> 2) & 3, values & 3], axis=-1
    ).reshape(2, -1)[:, :13]
    result = unpack2(values, 13)
    assert result.dtype == dtype
    assert np.array_equal(result, expected)


def test_unpack2_todos_256_bytes_e_layout_nao_contiguo():
    raw = np.arange(256, dtype=np.uint8).reshape(16, 16)
    for packed in (raw, raw[:, ::2], raw.T):
        for padding in range(4):
            n_dots = packed.shape[1] * 4 - padding
            expected = np.stack(
                [(packed >> 6) & 3, (packed >> 4) & 3,
                 (packed >> 2) & 3, packed & 3], axis=-1
            ).reshape(packed.shape[0], -1)[:, :n_dots]
            result = unpack2(packed, n_dots)
            assert result.dtype == np.uint8
            assert np.array_equal(result, expected)


def _unpack2_scalar_reference(packed, n_dots):
    """Oráculo independente da aritmética NumPy de 32 bits e do byteorder."""
    return [[(int(value) >> shift) & 3
             for value in row for shift in (6, 4, 2, 0)][:n_dots]
            for row in packed]


@pytest.mark.parametrize("layout", ["C", "F", "reverse_rows", "reverse_columns",
                                    "transpose_strided", "broadcast"])
@pytest.mark.parametrize("padding", range(4))
def test_unpack2_preserva_ordem_dos_bits_sem_modificar_entrada(layout, padding):
    source = np.arange(256, dtype=np.uint8).reshape(16, 16)
    layouts = {
        "C": source,
        "F": np.asfortranarray(source),
        "reverse_rows": source[::-1],
        "reverse_columns": source[:, ::-1],
        "transpose_strided": source.T[::2, ::-1],
        "broadcast": np.broadcast_to(source[0], (7, 16)),
    }
    packed = layouts[layout]
    before = packed.copy()
    packed.setflags(write=False)
    n_dots = packed.shape[1] * 4 - padding
    expected = np.array(_unpack2_scalar_reference(packed, n_dots), dtype=np.uint8)

    decoded = unpack2(packed, n_dots)

    assert decoded.dtype == np.uint8
    np.testing.assert_array_equal(decoded, expected)
    np.testing.assert_array_equal(packed, before)
    assert not packed.flags.writeable
    assert not np.shares_memory(decoded, packed)


@pytest.mark.parametrize("dtype", ["<u2", ">u2", "<i2", ">i2",
                                   "<u4", ">u4", "<i8", ">i8"])
def test_unpack2_fallback_preserva_inteiros_com_byteorder_explicito(dtype):
    packed = np.array([[0, 255, 170, 85], [3, 127, 15, 64]], dtype=dtype)
    if packed.dtype.kind == "i":
        packed[1, :2] = [-1, -32768]
    original_bytes = packed.tobytes()
    # O fallback anterior usa np.stack, cujo resultado tem byteorder nativo.
    expected_dtype = packed.dtype.newbyteorder("=")
    expected = np.array(_unpack2_scalar_reference(packed, 13), dtype=expected_dtype)

    decoded = unpack2(packed, 13)

    assert decoded.dtype == expected_dtype
    np.testing.assert_array_equal(decoded, expected)
    assert packed.tobytes() == original_bytes


def test_unpack2_memmap_somente_leitura_preserva_bytes_no_disco(tmp_path):
    raw = np.arange(256, dtype=np.uint8).reshape(8, 32)
    path = tmp_path / "packed.bin"
    original_bytes = raw.tobytes()
    path.write_bytes(original_bytes)
    mapped = np.memmap(path, mode="r", dtype=np.uint8, shape=raw.shape)
    try:
        packed = mapped[::-1, ::-2]
        for padding in range(4):
            n_dots = packed.shape[1] * 4 - padding
            decoded = unpack2(packed, n_dots)
            np.testing.assert_array_equal(
                decoded, _unpack2_scalar_reference(packed, n_dots))
            assert not np.shares_memory(decoded, mapped)
        del packed
    finally:
        del mapped
    assert path.read_bytes() == original_bytes


def test_read_rows_preserva_canais_linhas_parciais_e_padding(tmp_path):
    path = tmp_path / "partial.PRT"
    planes = np.random.default_rng(73).integers(0, 4, (12, 5, 37), dtype=np.uint8)
    writer = PrtWriter(path, 720, 2400, 5, 37)
    try:
        writer.write_block(list(planes[:, :2]))
        writer.write_block(list(planes[:, 2:]))
    finally:
        writer.close()
    before = path.read_bytes()

    result = read_rows(path, 1, 4)

    assert len(result) == 12
    for channel, decoded in enumerate(result):
        assert decoded.dtype == np.uint8
        assert decoded.shape == (3, 37)
        np.testing.assert_array_equal(decoded, planes[channel, 1:4])
    assert path.read_bytes() == before
