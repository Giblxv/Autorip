import numpy as np
import pytest
from PIL import Image

from autorip.engine import Rip
from autorip.config import Settings


@pytest.mark.parametrize("limits", [dict(C=100,M=100,Y=100,K=100),
                                   dict(C=0,M=35.5,Y=88.25,K=100)])
def test_cmyk_preserva_todos_os_bytes_e_limites(limits):
    values=np.arange(256,dtype=np.uint8)
    rgb=Image.fromarray(np.stack(np.broadcast_arrays(values[None,:],values[:,None],np.array(127,np.uint8)),axis=-1))
    try:
        rip=Rip(Settings(ink_limit=limits))
        expected=np.asarray(rgb.convert("CMYK"),dtype=np.float32)/255.0
        expected *= np.asarray([limits[k]/100 for k in "CMYK"],dtype=np.float32)
        np.clip(expected,0,1,out=expected)
        result=rip._to_cmyk(rgb)
        assert result.dtype==np.float32
        np.testing.assert_array_equal(result,expected)
    finally:
        rgb.close()
