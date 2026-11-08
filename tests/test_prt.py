import numpy as np, os, tempfile
from autorip.prt import pack2, unpack2, plane_bytes_for, PrtWriter, read_header, read_rows

def test_pack_roundtrip():
    a = np.random.randint(0, 4, (7, 5669)).astype(np.uint8)
    pb = plane_bytes_for(5669); assert pb == 1424
    assert (unpack2(pack2(a, pb), 5669) == a).all()

def test_writer_header_and_size():
    p = os.path.join(tempfile.mkdtemp(), "t.PRT")
    w = PrtWriter(p, 720, 2400, 10, 100)
    w.write_block([np.full((10, 100), 3, np.uint8)] * 12); w.close()
    h = read_header(p)
    assert (h["dpi_x"], h["dpi_y"], h["n_channels"], h["bits"]) == (720, 2400, 12, 2)
    assert os.path.getsize(p) == 48 + 10 * 12 * h["plane_bytes"]
    assert (read_rows(p, 0, 10)[4] == 3).all()
