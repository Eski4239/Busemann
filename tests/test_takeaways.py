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


def _equal_turn(M, optima, base):
    d = optima[base][1]
    return {"rec": {m: api.design(M, m, max_cowl_angle=d).recovery_total
                    for m in range(base + 1, 5)},
            "iso": api.isentropic_vs_turning(M, delta_grid=(d,)).recovery[0]}


def test_turning_takeaway_at_mach_3(m3):
    optima, th = m3
    eq = _equal_turn(3.0, optima, 2)
    text = T.turning(3.0, optima, th, 2, eq)
    assert text == (
        f"At the same {optima[2][1]:.1f}° cowl turn as 2 ramps ({optima[2][0]:.3f}), "
        f"3 ramps give {eq['rec'][3]:.3f} and 4 ramps {eq['rec'][4]:.3f}; an isentropic ramp "
        f"gives {eq['iso']:.3f}. Unconstrained, 3 and 4 ramps turn {optima[3][1]:.1f}° and "
        f"{optima[4][1]:.1f}°, past θmax ({th:.1f}°), so the cowl shock detaches.")
    # the user's example at M 3 (rounded as displayed)
    assert text.startswith("At the same 33.8° cowl turn as 2 ramps (0.744), 3 ramps give 0.8")
    assert "an isentropic ramp gives 0.881" in text and "39.6° and 42.8°" in text


def test_turning_takeaway_other_counts(m3):
    optima, th = m3
    one = T.turning(3.0, optima, th, 1, _equal_turn(3.0, optima, 1))
    assert one.startswith("At the same 22.6° cowl turn as 1 ramp (0.581), 2 ramps give")
    assert "3 and 4 ramps pass θmax (34.1°), so their cowl shocks detach." in one
    assert T.turning(3.0, optima, th, 0, _equal_turn(3.0, optima, 1)) == one   # base 1
    four = T.turning(3.0, optima, th, 4, _equal_turn(3.0, optima, 4))
    assert "an isentropic ramp gives" in four and "the 4-ramp optimum turns 42.8°" in four
    inside = {0: (0.3, 0.0), 1: (0.5, 10.0), 2: (0.6, 12.0), 3: (0.7, 13.0), 4: (0.8, 14.0)}
    eq = {"rec": {3: 0.65, 4: 0.66}, "iso": 0.7}
    assert T.turning(2.0, inside, 30.0, 2, eq).endswith(", inside θmax (30.0°).")


@pytest.mark.parametrize("n, base", [(0, 1), (1, 1), (3, 3), (4, 4)])
def test_turning_base(n, base):
    assert T.turning_base(n) == base


def test_drag_takeaways(m3):
    d = api.design(3.0, 2)
    sweep = api.off_design_sweep(d, 2.4, 3.6, 13)
    ds = api.drag_sweep(d, sweep, 0.10)
    cowl = api.cowl_drag_vs_turning(3.0, (d.cowl_angle_deg,))[0]
    text = T.drag_vs_mach(3.0, ds.machs, ds.cd_add, cowl)
    peak = max(a for M, a in zip(ds.machs, ds.cd_add) if M < 3.0)
    assert f"{T.CD_ADD} {peak:.3f}" in text and f"{T.CD_COWL} {cowl:.3f}." in text
    assert T.drag_vs_mach(3.0, ds.machs, ds.cd_add, None).endswith("not computable.")
    m3_match = {m: api.cowl_drag_vs_turning(
        3.0, (api.turning_for_recovery(3.0, m, d.recovery_total),))[0] for m in (3, 4)}
    rv = T.recovery_vs_cowl(3.0, 2, d.recovery_total, cowl, m3_match)
    assert rv == (f"At M 3.00, 2 ramps recover {d.recovery_total:.3f} for {T.CD_COWL} "
                  f"{cowl:.3f}; the same recovery costs 3 ramps at {T.CD_COWL} "
                  f"{m3_match[3]:.3f} and 4 ramps at {T.CD_COWL} {m3_match[4]:.3f}.")
    assert "not computable" in T.recovery_vs_cowl(3.0, 3, 0.836, None, {4: None})


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
