"""The allocation shortcut must use the same rounded height as selection."""
from dataclasses import asdict

import pytest

from autorip.layout import LayoutItem, sheet_height
from autorip import sheet_nesting as module


@pytest.mark.parametrize('rotation', [0, 90, 180, 270])
@pytest.mark.parametrize('gap', [0, .000001, .2])
def test_height_filter_preserves_rounding_ties_and_rotations(rotation, gap):
    items = [LayoutItem('a', 'a.png', '', 100, 100, 6.1234567, 4.9999996,
                        rotation=rotation, selected=True),
             LayoutItem('b', 'b.png', '', 100, 100, 3.0000004, 7.0000005)]
    before = [asdict(x) for x in items]
    arguments = (items, 58, .2, gap, 'area', 'bssf', True)
    reference = module._pack_once(*arguments)
    height = sheet_height(reference, .2, gap)
    for limit in (height-module.EPS, height, height+module.EPS/2, height+module.EPS*2):
        result = module._pack_once(*arguments, height_limit=limit)
        if height < limit-module.EPS:
            assert result == reference
        else:
            assert result is None
    assert [asdict(x) for x in items] == before
