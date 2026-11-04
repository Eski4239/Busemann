"""External cowl detachment check and the max-cowl-angle constrained optimum (M3.1)."""
import json

import numpy as np
import pytest
from scipy.optimize import brentq

from inletdesign import api
from inletdesign import oblique_shock as obl
from inletdesign.geometry import COWL_MARGIN_WARN_DEG, cowl_check


def _cowl_notices(result):
    return [n for n in result.notices
            if n.text.startswith(("Cowl near", "External cowl", "Cowl lip"))]


# SOURCE: M3.1 review request (user-stated expectations: M3 2-ramp margin 0.28 +/- 0.01 deg,
# X-15 4-ramp detached, 1-ramp M2 no warning); the margin itself is the identity
# theta_max(M_inf) - sum(ramp angles).
def test_m3_two_ramp_is_near_detachment():
    d = api.design(3.0, 2)
    assert d.cowl_margin_deg == pytest.approx(0.28, abs=0.01)
    assert d.theta_max_freestream_deg == pytest.approx(obl.max_deflection(3.0)[0])
    assert d.cowl_margin_deg == pytest.approx(d.theta_max_freestream_deg - d.cowl_angle_deg)
    [notice] = _cowl_notices(d)
    assert notice.level == "warn"
    assert notice.text == f"Cowl near shock detachment (margin {d.cowl_margin_deg:.2f}°)"


def test_x15_four_ramp_cowl_is_detached():
    d = api.design(6.7, 4)
    assert d.cowl_margin_deg < 0
    [notice] = _cowl_notices(d)
    assert notice.level == "error"
    assert notice.text.startswith("External cowl shock detached (cowl turns 59.50°, "
                                  f"θmax = {d.theta_max_freestream_deg:.2f}° at M∞ = 6.70)")
    assert "bow shock, spillage and cowl drag not modelled" in notice.text


def test_one_ramp_m2_has_no_cowl_warning():
    d = api.design(2.0, 1)
    assert d.cowl_margin_deg > COWL_MARGIN_WARN_DEG
    assert not _cowl_notices(d)


def test_cowl_check_levels_are_closed_form():
    theta_max = obl.max_deflection(2.5)[0]
    assert cowl_check(2.5, theta_max - 3.0)[2] is None
    assert cowl_check(2.5, theta_max - 1.0)[2] == "warn"
    assert cowl_check(2.5, theta_max + 0.5)[2] == "error"


def test_off_design_cowl_check_uses_flow_at_the_lip():
    d = api.design(3.0, 2)
    # below design both ramp shocks cross ahead of the lip: the lip sits in the duct region,
    # whose flow already runs at the cowl angle, so the cowl turns nothing
    for M in (2.6, 2.75):
        r = api.off_design_point(d, M)
        assert r.regime == "spillage" and r.cowl_lip_region == 2
        assert r.lip_flow_angle_deg == pytest.approx(d.cowl_angle_deg, abs=1e-12)
        assert r.cowl_required_turn_deg == pytest.approx(0.0, abs=1e-9)
        assert r.lip_mach == pytest.approx(r.regions[2].M)
        assert r.cowl_margin_deg == pytest.approx(obl.max_deflection(r.lip_mach)[0])
        assert not _cowl_notices(r)
        json.dumps(r.to_dict())
    # at design the lip is on the shocks: upstream (freestream) side, same as the design check
    on = api.off_design_point(d, 3.0)
    assert on.cowl_lip_region == 0
    assert on.cowl_margin_deg == pytest.approx(d.cowl_margin_deg, abs=1e-9)
    assert [n.level for n in _cowl_notices(on)] == ["warn"]
    # above design the shocks enter the cowl: the lip meets freestream
    for M in (3.25, 3.5):
        r = api.off_design_point(d, M)
        assert r.cowl_lip_region == 0
        assert r.cowl_margin_deg == pytest.approx(obl.max_deflection(M)[0] - d.cowl_angle_deg)
        assert r.cowl_margin_deg > 0


def test_x15_still_detached_at_its_own_mach():
    d = api.design(6.7, 4)
    r = api.off_design_point(d, 6.7)
    assert r.cowl_lip_region == 0
    assert r.cowl_margin_deg == pytest.approx(d.cowl_margin_deg, abs=1e-9)
    assert r.cowl_margin_deg < 0
    assert [n.level for n in _cowl_notices(r)] == ["error"]


def test_subsonic_aligned_lip_flow_has_no_margin():
    d = api.design(3.0, 2)
    r = api.off_design_point(d, 2.40)          # just above ramp-2 detachment (M 2.386)
    assert r.lip_mach < 1.0 and r.cowl_required_turn_deg == pytest.approx(0.0, abs=1e-9)
    assert r.cowl_margin_deg is None and not _cowl_notices(r)


# Documented jumps of the margin along M_inf for the M3 2-ramp design: the lip changes region
# only when a ramp shock crosses it. All shocks focus on the lip at the design Mach, so they
# all cross there together: the single jump is at M 3.0 (duct region -> freestream).
M3_MARGIN_JUMPS = [3.0]


def test_margin_is_continuous_except_where_a_shock_crosses_the_lip():
    d = api.design(3.0, 2)
    machs = np.round(np.arange(2.40, 3.5 + 1e-9, 0.005), 6)
    pts = [api.off_design_point(d, float(M)) for M in machs]
    jumps = []
    for M0, a, M1, b in zip(machs, pts, machs[1:], pts[1:]):
        if a.cowl_lip_region != b.cowl_lip_region:
            jumps.append(float(M1))
            continue
        if a.cowl_margin_deg is None or b.cowl_margin_deg is None:
            assert (a.cowl_margin_deg is None) == (a.lip_mach < 1.0)
            continue
        assert abs(b.cowl_margin_deg - a.cowl_margin_deg) < 0.6, (M0, M1)
    assert jumps == pytest.approx(M3_MARGIN_JUMPS)
    # margin is None only where the lip flow is subsonic (just above detachment)
    assert all((p.cowl_margin_deg is None) == (p.lip_mach < 1.0) for p in pts)
    assert any(p.cowl_margin_deg is None for p in pts)


# --- max cowl angle ------------------------------------------------------------------

def test_constrained_design_respects_limit():
    free = api.design(3.0, 2)
    d = api.design(3.0, 2, max_cowl_angle=30.0)
    assert d.constrained and not free.constrained
    assert d.cowl_angle_deg <= 30.0 + 1e-9
    assert d.cowl_angle_deg == pytest.approx(30.0, abs=1e-6)     # active limit binds
    assert d.recovery_total < free.recovery_total
    assert d.inputs.max_cowl_angle_deg == 30.0
    json.dumps(d.to_dict())


def test_recovery_falls_monotonically_as_limit_tightens():
    limits = np.linspace(33.0, 10.0, 24)
    recoveries = [api.design(3.0, 2, max_cowl_angle=float(L)).recovery_total for L in limits]
    assert all(b < a for a, b in zip(recoveries, recoveries[1:]))
    assert recoveries[0] <= api.design(3.0, 2).recovery_total


def test_inactive_limit_leaves_design_unchanged():
    free = api.design(3.0, 3)
    loose = api.design(3.0, 3, max_cowl_angle=80.0)
    assert not loose.constrained
    assert loose.ramp_angles_deg == free.ramp_angles_deg
    assert loose.recovery_total == free.recovery_total


def test_invalid_limit_and_custom_angles():
    with pytest.raises(ValueError, match="max cowl angle"):
        api.design(3.0, 2, max_cowl_angle=0.0)
    d = api.design(3.0, 2, ramp_angles=[10.0, 12.0], max_cowl_angle=15.0)
    assert not d.constrained
    assert any("ignored for custom angles" in w for w in d.warnings)


# --- STEP 0b: cowl lip wedge -------------------------------------------------------------

# SOURCE: M4 STEP 0b request (user-stated expectations: M3 2-ramp with a 6 deg lip wedge is
# detached at M 2.45 and 2.5, attached at 2.75; at design the margin drops by exactly 6 deg).
def test_wedge_six_detaches_below_attach_mach():
    d = api.design(3.0, 2, cowl_wedge=6.0)
    for M in (2.45, 2.5):
        r = api.off_design_point(d, M)
        assert r.cowl_margin_deg < 0 and r.cowl_wedge_deg == 6.0
        assert r.cowl_required_turn_deg == pytest.approx(6.0, abs=1e-9)
        assert [n.level for n in _cowl_notices(r)] == ["error"]
    attached = api.off_design_point(d, 2.75)
    assert attached.cowl_margin_deg > 0
    assert all(n.level != "error" for n in attached.notices)
    attach = brentq(lambda M: api.off_design_point(d, M).cowl_margin_deg, 2.5, 2.75, xtol=1e-10)
    assert 2.5 < attach < 2.75      # 2.66280 (reported in M4 STEP 0b)
    json.dumps(attached.to_dict())


def test_wedge_lowers_design_margin_by_exactly_its_angle():
    free, wedged = api.design(3.0, 2), api.design(3.0, 2, cowl_wedge=6.0)
    assert wedged.cowl_margin_deg == pytest.approx(free.cowl_margin_deg - 6.0, abs=1e-12)
    assert wedged.inputs.cowl_wedge_deg == 6.0
    on0, on6 = api.off_design_point(free, 3.0), api.off_design_point(wedged, 3.0)
    assert on6.cowl_margin_deg == pytest.approx(on0.cowl_margin_deg - 6.0, abs=1e-12)
    # capture and recovery do not depend on the wedge
    assert (on6.mass_capture_ratio, on6.recovery_total) == (on0.mass_capture_ratio,
                                                            on0.recovery_total)


def test_zero_wedge_is_the_default_everywhere():
    a, b = api.design(3.0, 2), api.design(3.0, 2, cowl_wedge=0.0)
    assert a is b                                       # same cache entry
    sweep = api.off_design_sweep(a, 2.4, 3.5, 23)
    for M, p in zip(sweep.machs, sweep.points):
        q = api._convert_off(api._off.off_design(api._geometry_of(a), M, 1.4), a)
        assert p == q


def test_invalid_wedge_raises():
    for bad in (-1.0, 31.0, float("nan")):
        with pytest.raises(ValueError, match="cowl lip wedge"):
            api.design(3.0, 2, cowl_wedge=bad)


def test_subsonic_lip_flow_with_wedge_has_no_margin():
    d = api.design(3.0, 2, cowl_wedge=6.0)
    r = api.off_design_point(d, 2.40)
    assert r.lip_mach < 1.0 and r.cowl_margin_deg is None and not _cowl_notices(r)


# --- STEP 0c: above-design wording -------------------------------------------------------

def test_above_design_message_points_at_mach_reflection():
    d = api.design(3.0, 2)
    r = api.off_design_point(d, 3.25)
    [n] = _cowl_notices(r)
    assert n.level == "warn"
    assert n.text == (f"Cowl lip shock near detachment (θmax − turn = "
                      f"{r.cowl_margin_deg:.2f}°): Mach reflection at the lip likely; "
                      "recovery below the ideal value")
    assert f"{r.cowl_margin_deg:.2f}" == "1.82"
    assert n.detail == ("Observed in Phase 3d CFD at M∞ 3.25: Mach reflection at the lip, "
                        "recovery 4.9% below the ideal value.")
    # at the design point the design-check wording is kept
    [on] = _cowl_notices(api.off_design_point(d, 3.0))
    assert on.text.startswith("Cowl near shock detachment") and on.detail is None
    # detached above design: error, same wording family
    [err] = _cowl_notices(api.off_design_point(api.design(3.0, 2, cowl_wedge=6.0), 3.25))
    assert err.level == "error" and err.text.startswith("Cowl lip shock detached")
