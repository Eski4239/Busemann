"""Inviscid pressure drag (M9b, addendum D.2, no Qt): additive (spillage) drag along the
dividing streamline, checked by an independent momentum balance, and the cowl pressure drag
on its frontal height. Coefficients per unit width on q_inf h_c.

SOURCE (additive-drag definition, PENDING user confirmation): M. Sibulkin, "Theoretical and
Experimental Investigation of Additive Drag", NACA Report 1187 (1954; supersedes NACA RM
E51B13, 1951). Expected values here are identities or self-consistency checks."""
import math

import pytest

from inletdesign import api
from inletdesign import oblique_shock as obl


def _below(design, k=4):
    """k Mach numbers between detachment (+margin) and the design Mach."""
    lo = api.detachment_mach(design) + 0.05
    hi = design.inputs.M - 0.02
    return [lo + (hi - lo) * j / (k - 1) for j in range(k)]


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_additive_drag_is_zero_at_and_above_design(n):
    d = api.design(3.0, n)
    for M in (3.0, 3.25, 3.6):
        off = api.off_design_point(d, M)
        assert off.regime in ("on-lip", "shock-in-duct")
        assert api.additive_drag(d, off) == 0.0


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_momentum_balance_matches_the_streamline_integral(n):
    d = api.design(3.0, n)
    worst = 0.0
    for M in _below(d) + [3.0]:
        off = api.off_design_point(d, M)
        a, b = api.additive_drag(d, off), api.additive_drag_momentum(d, off)
        worst = max(worst, abs(a - b))
        assert a == pytest.approx(b, abs=1e-10), (n, M)
    assert worst < 1e-10


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_additive_drag_is_positive_below_design_and_falls_towards_it(n):
    d = api.design(3.0, n)
    values = [api.additive_drag(d, api.off_design_point(d, M)) for M in _below(d)]
    assert all(v > 0.0 for v in values)
    assert all(b < a for a, b in zip(values, values[1:]))


def test_cowl_drag_is_zero_without_turn_in_freestream():
    c = api.cowl_pressure_drag(3.0, 3.0, 1.0, 0.0, 0.10)
    assert c.cd == 0.0 and c.reason is None and c.p_ratio == 1.0


def test_cowl_drag_formula_at_the_design_point():
    d = api.design(3.0, 2)
    off = api.off_design_point(d, 3.0)
    c = api.cowl_drag(off, 0.10)
    p2 = obl.oblique_shock_state(3.0, d.cowl_angle_deg, 1.4)["p2_p1"]
    assert c.turn_deg == pytest.approx(d.cowl_angle_deg, abs=1e-12)
    assert c.cd == pytest.approx((p2 - 1.0) * 0.10 / (0.7 * 9.0), rel=1e-12)   # identity
    assert c.cd == pytest.approx(api.cowl_drag_vs_turning(3.0, (d.cowl_angle_deg,))[0],
                                 rel=1e-12)


def test_cowl_drag_detached_and_subsonic_are_not_computable():
    d = api.design(3.0, 3)                         # cowl 39.6° > θmax 34.1° at M 3
    c = api.cowl_drag(api.off_design_point(d, 3.0))
    assert c.cd is None and c.reason == api.COWL_DETACHED_REASON
    assert "not computable" in c.reason
    s = api.cowl_pressure_drag(2.0, 0.9, 3.0, 5.0)
    assert s.cd is None and s.reason == api.COWL_SUBSONIC_REASON
    assert api.cowl_drag_vs_turning(3.0, (40.0,))[0] is None


def test_cowl_drag_is_linear_in_the_frontal_height():
    off = api.off_design_point(api.design(3.0, 2), 2.75)
    base = api.cowl_drag(off, 0.10).cd
    for dh in (0.05, 0.5, 1.0):
        assert api.cowl_drag(off, dh).cd == pytest.approx(base * dh / 0.10, rel=1e-12)


def test_cowl_drag_below_design_uses_the_local_lip_pressure():
    """Below design the lip sits behind the ramp shocks with no turn: p_c is the local
    pressure, so the cowl face still carries (p_k - p_inf) x dh."""
    d = api.design(3.0, 2)
    off = api.off_design_point(d, 2.5)
    c = api.cowl_drag(off, 0.10)
    p_lip = off.regions[off.cowl_lip_region].p_ratio
    assert c.turn_deg == 0.0
    assert c.cd == pytest.approx((p_lip - 1.0) * 0.10 / (0.7 * 2.5 ** 2), rel=1e-12)


def test_drag_sweep_matches_the_point_functions():
    d = api.design(3.0, 2)
    sweep = api.off_design_sweep(d, 2.4, 3.6, 13)
    ds = api.drag_sweep(d, sweep, 0.2)
    assert ds.machs == sweep.machs
    for M, add, cowl, point in zip(ds.machs, ds.cd_add, ds.cd_cowl, sweep.points):
        assert add == api.additive_drag(d, point)
        assert cowl == api.cowl_drag(point, 0.2).cd


def test_turning_for_recovery_hits_its_target():
    target = api.design(3.0, 2).recovery_total
    for n in (3, 4):
        delta = api.turning_for_recovery(3.0, n, target)
        got = api.design(3.0, n, max_cowl_angle=delta).recovery_total
        assert got == pytest.approx(target, abs=1e-9)
    assert api.turning_for_recovery(3.0, 1, 0.99) is None       # above 1 ramp's optimum


@pytest.mark.parametrize("call", [
    lambda: api.cowl_pressure_drag(3.0, 3.0, 1.0, 5.0, frontal_height=0.0),
    lambda: api.cowl_pressure_drag(3.0, 3.0, 1.0, 5.0, frontal_height=1.5),
    lambda: api.cowl_pressure_drag(3.0, 3.0, 1.0, -1.0),
    lambda: api.cowl_pressure_drag(0.5, 3.0, 1.0, 5.0),
    lambda: api.turning_for_recovery(3.0, 0, 0.5),
    lambda: api.additive_drag(api.design(3.0, 2), None),
])
def test_bad_inputs_raise(call):
    with pytest.raises(ValueError):
        call()


def test_results_serialise():
    import json

    d = api.design(3.0, 2)
    json.dumps(api.cowl_drag(api.off_design_point(d, 2.8)).to_dict())
    ds = api.drag_sweep(d, api.off_design_sweep(d, 2.5, 3.5, 5))
    json.dumps(ds.to_dict())
    assert all(math.isfinite(v) for v in ds.cd_add)
