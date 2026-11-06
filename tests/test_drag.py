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


# --- non-uniform cowl-face pressure (a shock intersection within the frontal height) -------
def _on_line(point, origin, angle_deg):
    a = math.radians(angle_deg)
    return abs(math.cos(a) * (point[1] - origin[1]) - math.sin(a) * (point[0] - origin[0]))


def test_validation_design_at_2_55_has_a_shock_intersection_on_the_cowl_face():
    d = api.design(3.0, 2)
    off = api.off_design_point(d, 2.55)
    h = d.inputs.capture_height
    hits = api.cowl_face_intersections(d, off, 0.10)
    assert len(hits) == 1
    (x, y), i, j = hits[0]
    assert (i, j) == (0, 1)
    rise = (y - d.geometry.lip[1]) / h
    assert 0.0 < rise <= 0.10 and rise == pytest.approx(0.097, abs=5e-4)
    for k in (i, j):                    # geometric self-consistency: on both shock lines
        origin = d.geometry.ramp_points[k]
        assert _on_line((x, y), origin, d.flow_angles_deg[k] + off.betas_deg[k]) < 1e-12
    c = api.cowl_drag(off, 0.10, design=d)
    assert c.nonuniform and c.note == api.NONUNIFORM_NOTE
    assert c.cd == api.cowl_drag(off, 0.10).cd                 # the value itself unchanged
    assert not api.cowl_drag(off, 0.10).nonuniform             # no design: not checked


def test_no_cowl_face_note_with_a_smaller_frontal_height_or_at_and_above_design():
    d = api.design(3.0, 2)
    assert api.cowl_face_intersections(d, api.off_design_point(d, 2.55), 0.05) == ()
    for M in (3.0, 3.25):
        off = api.off_design_point(d, M)
        assert api.cowl_face_intersections(d, off, 1.0) == ()
        assert not api.cowl_drag(off, 1.0, design=d).nonuniform


def test_intersections_behind_the_cowl_face_do_not_count():
    """3 ramps at M 2.7: shocks 1-2 meet 0.110 h_c above and 0.008 h_c downstream of the lip.
    With the cowl at 39.6° the face at that height is 0.133 h_c downstream, so the point is
    upstream of it and counts at Δh 0.2; with a near-vertical cowl face (constructed) it lies
    behind the face and is excluded."""
    d = api.design(3.0, 3)
    off = api.off_design_point(d, 2.7)
    h = d.inputs.capture_height
    hits = {(i, j): p for p, i, j in api.cowl_face_intersections(d, off, 0.2)}
    assert (0, 1) in hits and hits[(0, 1)][0] > d.geometry.lip[0]      # downstream of the lip
    x_lip, y_lip = d.geometry.lip
    tan_c = math.tan(math.radians(off.cowl_angle_deg))
    for (x, y) in hits.values():
        assert x <= x_lip + (y - y_lip) / tan_c + 1e-12
    # move the cowl face upstream (a steep cowl, constructed): the downstream point drops out
    import dataclasses
    steep = dataclasses.replace(off, cowl_angle_deg=89.9)
    kept = {(i, j) for _, i, j in api.cowl_face_intersections(d, steep, 0.2)}
    behind = [k for k, (x, y) in hits.items() if x > x_lip + (y - y_lip) / math.tan(
        math.radians(89.9))]
    assert (0, 1) in behind and not set(behind) & kept
    assert (hits[(0, 1)][1] - d.geometry.lip[1]) / h == pytest.approx(0.110, abs=5e-4)


def test_drag_sweep_notes_match_the_point_calls():
    d = api.design(3.0, 2)
    sweep = api.off_design_sweep(d, 2.4, 3.6, 25)
    ds = api.drag_sweep(d, sweep, 0.10)
    assert len(ds.notes) == len(ds.machs)
    for point, note in zip(sweep.points, ds.notes):
        expected = api.cowl_drag(point, 0.10, design=d).note if point is not None else None
        assert note == expected
    assert any(ds.notes) and not any(n for M, n in zip(ds.machs, ds.notes) if M >= 3.0)
