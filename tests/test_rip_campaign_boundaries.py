"""A campanha deve detectar regressões de dilatação em fronteiras físicas."""
from pathlib import Path
import sys
import zipfile

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
    # This is a known-bad proposal for the 0.8.24 implementation. Changing the
    # real EDT implementation must not turn the benchmark's control into a
    # requirement to retain that old implementation in production.
    with zipfile.ZipFile(root/'tests/fixtures/rip-tuning-baseline.zip') as archive:
        bundle = {key: archive.read(key+'.py').decode() for key in campaign.FILES}
    assert campaign.digest(bundle)=='4931ab0acb27b5753a0a78e2aaef4dbd1ed5306096afc4b61ef9de1bec8dedd5'
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
