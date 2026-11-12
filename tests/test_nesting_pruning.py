"""Keep pruning order, duplicate ties and the existing EPS comparisons exact."""
import pytest

from autorip.sheet_nesting import EPS, _split_free


@pytest.mark.parametrize('free,box,expected',[
    ([(0.,0.,10.,10.)],(0.,0.,5.,5.),[(5.,0.,5.,10.),(0.,5.,10.,5.)]),
    ([(0.,0.,10.,10.)]*12,(0.,0.,5.,5.),[(5.,0.,5.,10.),(0.,5.,10.,5.)]),
    ([(0.,0.,10.,10.)]*4+[(1.,1.,8.,8.)]*4,(20.,20.,1.,1.),[(0.,0.,10.,10.)]),
    ([(0.,0.,10.,10.),(EPS/2,EPS/2,10.,10.)]*4,(20.,20.,1.,1.),[]),
])
def test_pruning_preserves_reference_geometry(free,box,expected):
    original=list(free)
    assert _split_free(free,*box)==expected
    assert free==original
