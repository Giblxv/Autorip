import json
import sys
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_png(tmp_path):
    path = tmp_path / "amostra.png"
    image = Image.new("RGBA", (300, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((20, 20, 280, 180), radius=25, fill=(20, 120, 220, 255))
    image.save(path)
    return path


@pytest.fixture
def app_home(tmp_path, monkeypatch):
    home = tmp_path / "autorip-home"
    home.mkdir()
    config = {
        "auto_mode": False,
        "offline_mode": True,
        "label_enabled": False,
        "dpi_x": 300,
        "dpi_y": 300,
        "margin_top_in": 0.1,
        "margin_bottom_in": 0.1,
        "hot_folder": str(tmp_path / "hot"),
        "output_folder": str(tmp_path / "out"),
        "printed_folder": str(tmp_path / "printed"),
        "done_folder": str(tmp_path / "done"),
        "error_folder": str(tmp_path / "error"),
    }
    (home / "autorip.json").write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("AUTORIP_HOME", str(home))
    return home


@pytest.fixture
def app(app_home):
    from autorip.server import App
    instance = App()
    instance.auto = False
    return instance


def wait_for_job(job, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if job.get("status") in ("pronto", "erro"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job nao terminou em {timeout}s: {job}")
