"""MIL-E-5008B recovery (addendum C2, no Qt).

Expected values are closed-form evaluations of the formula stated in the spec addendum C2
(SOURCE in inletdesign/standards.py: MIL-E-5008B as given by NASA Glenn Research Center,
"Inlet Performance"; formula confirmed by the user). They test the implementation.
"""
import numpy as np
import pytest

from inletdesign import api
from inletdesign.standards import mil_e_5008b


def test_branches_closed_form():
    assert mil_e_5008b(0.8) == 1.0 and mil_e_5008b(1.0) == 1.0
    assert mil_e_5008b(3.0) == pytest.approx(1.0 - 0.075 * 2.0 ** 1.35, rel=1e-15)
    assert mil_e_5008b(5.0) == pytest.approx(1.0 - 0.075 * 4.0 ** 1.35, rel=1e-15)
    assert mil_e_5008b(6.0) == pytest.approx(800.0 / (6.0 ** 4 + 935.0), rel=1e-15)


def test_arrays_and_monotonic():
    M = np.linspace(1.0, 8.0, 50)
    eta = mil_e_5008b(M)
    assert eta.shape == M.shape and np.all(np.diff(eta) <= 0)
    assert api.mil_recovery(3.0) == mil_e_5008b(3.0)


@pytest.mark.parametrize("M", [-1.0, float("nan"), float("inf")])
def test_bad_mach_raises(M):
    with pytest.raises(ValueError):
        mil_e_5008b(M)
