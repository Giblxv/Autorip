import numpy as np
from PIL import Image
import pytest

from autorip.config import Settings
from autorip.experimental_gpu import status, erode
from autorip.experimental_processpool import process_files


def test_gpu_backend_is_optional_and_cpu_input_is_not_mutated():
    mask = np.array([[False, True], [True, True]], dtype=bool)
    original = mask.copy()
    if status()["cuda"]:
        result = erode(mask, 0.01)
        assert result.shape == mask.shape
    else:
        with pytest.raises(RuntimeError, match="Backend CuPy/CUDA indisponível"):
            erode(mask, 0.01)
    assert np.array_equal(mask, original)


def test_processpool_processes_independent_art(tmp_path):
    source = tmp_path / "art.png"
    Image.new("RGBA", (32, 24), (40, 120, 200, 180)).save(source)
    settings = Settings(label_enabled=False, offline_mode=True)
    results = process_files([source], settings, tmp_path / "out", max_workers=1)
    assert len(results) == 1
    output = tmp_path / "out" / "art.PRT"
    assert output.is_file()
    assert results[0]["output_path"] == str(output)
    assert results[0]["n_dots"] > 0
