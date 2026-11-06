"""Analytics takeaways (M9a, no Qt): computed from the trade numbers, never hard-coded.
The numbers below are the model's own output (self-consistency) or synthetic inputs that
exercise the wording; none is a reference value."""
import pytest

from busemann.analytics import takeaways as T
from inletdesign import api


@pytest.fixture(scope="module")
def m3():
    optima = {n: (api.design(3.0, n).recovery_total, api.design(3.0, n).cowl_angle_deg)
              for n in range(5)}
    return optima, api.max_deflection(3.0)


def test_turning_takeaway_at_mach_3(m3):
    optima, th = m3
    text = T.turning(3.0, optima, th, 2)
    d_rec = optima[3][0] - optima[2][0]
    d_cowl = optima[3][1] - optima[2][1]
    assert text == (f"At M 3.00, going from 2 to 3 ramps adds {d_rec:.3f} recovery but needs "
                    f"{d_cowl:.1f}° more cowl turning (past θmax {th:.1f}°: the cowl shock "
                    "detaches).")
    assert "detaches" not in T.turning(3.0, optima, th, 0)     # 1 -> 2: 33.8° < 34.1°


@pytest.mark.parametrize("n, pair", [(0, (1, 2)), (1, (1, 2)), (3, (3, 4)), (4, (3, 4))])
def test_turning_pair(n, pair):
    assert T.turning_pair(n) == pair


def test_design_mach_takeaway(m3):
    optima, _ = m3
    r0, r2, r4 = optima[0][0], optima[2][0], optima[4][0]
    assert T.design_mach(3.0, optima, 2) == (
        f"At M 3.00, 2 ramps recover {r2:.3f}: {r2 - r0:.3f} above a normal shock and "
        f"{r4 - r2:.3f} below 4 ramps.")
    assert T.design_mach(3.0, optima, 1).startswith("At M 3.00, 1 ramp recovers")
    assert "below 4 ramps" not in T.design_mach(3.0, optima, 4)
    assert T.design_mach(3.0, optima, 0) == (
        f"At M 3.00, a normal shock recovers {r0:.3f}; 4 ramps reach {r4:.3f}.")


def test_cowl_takeaway(m3):
    optima, th = m3
    c2 = optima[2][1]
    assert T.cowl(3.0, optima, th, 2) == (
        f"At M 3.00, the 2-ramp optimum turns {c2:.1f}°, {th - c2:.1f}° inside θmax "
        f"({th:.1f}°); the 3- and 4-ramp optima exceed it.")
    assert T.cowl(3.0, optima, th, 3).endswith("; the 4-ramp optimum also exceeds it.")
    assert "past θmax" in T.cowl(3.0, optima, th, 4)


def test_cowl_takeaway_wording_cases():
    synthetic = {0: (0.3, 0.0), 1: (0.5, 10.0), 2: (0.6, 20.0), 3: (0.7, 25.0), 4: (0.8, 28.0)}
    assert T.cowl(2.0, synthetic, 40.0, 2).endswith("; every ramp count up to 4 stays inside it.")
    over = {0: (0.3, 0.0), 1: (0.5, 41.0), 2: (0.6, 45.0), 3: (0.7, 47.0), 4: (0.8, 48.0)}
    assert T.cowl(2.0, over, 40.0, 0).endswith("; the 1-, 2-, 3- and 4-ramp optima exceed it.")
