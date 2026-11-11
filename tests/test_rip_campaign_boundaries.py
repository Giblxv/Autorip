"""A campanha deve detectar regressões de dilatação em fronteiras físicas."""
from pathlib import Path
import sys

import numpy as np
import pytest


def test_campaign_rejects_hypot_when_it_changes_physical_boundary(tmp_path):
    root = Path(__file__).resolve().parents[1]
    previous = sys.path[:]
    sys.path.insert(0, str(root / 'benchmarks'))
    try:
        import rip_campaign as campaign
        from rip_io_candidates import edt_hypot
    finally:
        sys.path[:] = previous
    bundle = {key: (root / path).read_text() for key, path in campaign.FILES.items()}
    baseline = campaign.load(bundle, tmp_path / 'baseline', 'boundary_old')
    candidate = campaign.load(edt_hypot(bundle), tmp_path / 'hypot', 'boundary_hypot')
    point = np.zeros((13, 19), bool)
    point[6, 9] = True
    radius = .08819444444444444
    old = baseline['morph'].dilate(point, radius, 720, 2400)
    new = candidate['morph'].dilate(point, radius, 720, 2400)
    if np.array_equal(old, new):
        pytest.skip('As duas normas coincidem nesta plataforma para o testemunho')
    assert campaign.micro_correct(baseline, candidate) == 'dilate-physical-boundary'
