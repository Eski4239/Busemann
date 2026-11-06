"""Inlet characteristic and buzz onset (M9c, no Qt). Expected values are closed-form
identities, self-consistency checks, or NACA 1135 table values (SOURCE comments).

Sources: NACA Report 1135 eqs. (44), (80), (96), (99); Moeckel, NACA TN 1921 (1949), eqs. (4),
(6)/(6a), (14), (17), (30)-(36), pp. 7-19, applied to the flow behind the last ramp shock
(Busemann extension); Ferri & Nucci, NACA RM L50K30 (1951), p. 7 (finding 2)."""
import math

import pytest

from inletdesign import api
from inletdesign import characteristic as C
from inletdesign import normal_shock as ns
from inletdesign import oblique_shock as obl


@pytest.fixture(scope="module")
def d():
    return api.design(3.0, 2)


def _off(d, M):
    return api.off_design_point(d, M)


# --- quasi-1D relations -------------------------------------------------------------------

def test_area_ratio_matches_naca_1135():
    # SOURCE: NACA 1135 Table II (supersonic flow), p. 635, M = 3.00: A/A* = 4.235;
    # eq. (80), p. 618 gives A*/A, used here as its reciprocal
    assert C.area_ratio(3.0) == pytest.approx(4.235, abs=5e-4)
    assert C.area_ratio(1.0) == pytest.approx(1.0, abs=1e-14)
    for M in (0.3, 0.8, 1.5, 2.5):
        sup = M > 1.0
        assert C.mach_from_area_ratio(C.area_ratio(M), supersonic=sup) == pytest.approx(M, rel=1e-12)


def test_mass_flow_function_identity():
    """mbar(M) x (A/A*)(M) = mbar(1) (closed form, from eq. 80)."""
    top = C.mass_flow_function(1.0)
    for M in (0.2, 0.5, 0.9, 1.4, 2.0, 3.0):
        assert C.mass_flow_function(M) * C.area_ratio(M) == pytest.approx(top, rel=1e-12)
    assert C.mach_from_mass_flow(C.mass_flow_function(0.4)) == pytest.approx(0.4, rel=1e-12)


# --- branches -----------------------------------------------------------------------------

def test_supercritical_branch_limits_and_monotonicity(d):
    off = _off(d, 2.75)
    crit = C.critical_point(d, off, 2.0)
    sup = C.supercritical_branch(d, off, 2.0)
    first, last = sup[0], sup[-1]
    assert (first.mfr, first.recovery, first.p_exit) == pytest.approx(
        (crit.mfr, crit.recovery, crit.p_exit), rel=1e-12)             # meets the critical point
    assert crit.recovery == pytest.approx(off.recovery_total, rel=1e-12)
    assert last.area_shock == pytest.approx(2.0) and len(sup) == 30    # maximum supercritical
    assert all(p.mfr == crit.mfr for p in sup)                          # vertical branch
    rec = [p.recovery for p in sup]
    assert all(b < a for a, b in zip(rec, rec[1:]))
    px = [p.p_exit for p in sup]
    assert all(b < a for a, b in zip(px, px[1:]))
    # recovery is eta_obl x p0y/p0x at the shock Mach (eq. 99)
    for p in sup:
        assert p.recovery == pytest.approx(
            off.recovery_oblique * float(ns.stagnation_pressure_ratio(p.M_shock)), rel=1e-12)


def test_subcritical_branch_limits_and_monotonicity(d):
    off = _off(d, 2.75)
    crit = C.critical_point(d, off, 2.0)
    sub = C.subcritical_branch(d, off, 2.0)
    assert (sub[0].mfr, sub[0].recovery, sub[0].p_exit) == pytest.approx(
        (crit.mfr, crit.recovery, crit.p_exit), rel=1e-12)             # continuity
    for p in sub:
        assert p.recovery == crit.recovery                              # ideal flat branch
        assert p.mfr == pytest.approx(crit.mfr * (1.0 - p.tau), rel=1e-12)
        # mass conservation through the duct exit
        ratio = C.mass_flow_function(p.M_exit) / C.mass_flow_function(crit.M_exit)
        assert ratio == pytest.approx(1.0 - p.tau, rel=1e-10)
    px = [p.p_exit for p in sub]
    assert all(b > a for a, b in zip(px, px[1:]))                      # MFR falls as p_x rises


# --- Moeckel's expelled shock --------------------------------------------------------------

def test_moeckel_identities(d):
    off = _off(d, 2.75)
    s = C.moeckel_shock(d, off, 0.1)
    # region-n state (Busemann extension)
    assert s.M_n == off.regions[2].M and s.theta_n_deg == off.regions[2].theta_deg
    # phi_S gives sonic flow behind the shock
    m2, lam = C._m2_behind(s.M_n, s.phi_S_deg, 1.4)
    assert m2 == pytest.approx(1.0, abs=1e-10) and lam == pytest.approx(s.lambda_S_deg)
    # eq. (34): A_s/A_0 = (y_S - y_SB) / ((y_S - y_m) cos lambda_S) = B
    assert (s.y_S - s.y_SB) / ((s.y_S - s.y_m) * math.cos(math.radians(s.lambda_S_deg))) == \
        pytest.approx(s.B, rel=1e-12)
    # eq. (30): tau = 1 - y_m / y_SB
    assert 1.0 - s.y_m / s.y_SB == pytest.approx(0.1, rel=1e-12)
    # the sonic point lies on the hyperbola with the shock angle phi_S there (eqs. 4, 5)
    Y = s.y_S - s.y_m
    assert s.hyperbola_x(Y) == pytest.approx(s.x_S, rel=1e-12)
    assert s.hyperbola_slope(Y) == pytest.approx(s.phi_S_deg, abs=1e-9)
    # asymptotes: the region-n Mach lines
    mu = math.degrees(math.asin(1.0 / s.M_n))
    assert s.hyperbola_slope(1e6 * Y) == pytest.approx(mu, abs=1e-6)
    # eq. (11) with eta = lambda_S (eq. 17, plane flow) and eq. (10)
    assert s.x_SB == pytest.approx(s.x_S + (s.y_S - s.y_SB) * math.tan(
        math.radians(s.lambda_S_deg)), rel=1e-12)
    assert s.L == pytest.approx(s.x_SB - s.x0, rel=1e-12)
    # the lip is the body sonic point
    assert s.world(s.x_SB, s.y_SB) == pytest.approx(d.geometry.lip, abs=1e-15)


def test_moeckel_shock_at_zero_spill_and_linear_in_tau(d):
    off = _off(d, 2.75)
    s0 = C.moeckel_shock(d, off, 0.0)
    assert s0.L == pytest.approx(0.0, abs=1e-15)
    assert s0.vertex() == pytest.approx(d.geometry.lip, abs=1e-15)     # shock at the lip
    L = [C.moeckel_shock(d, off, t).L for t in (0.05, 0.1, 0.2)]
    # TN 1921, p. 20: the shock distance grows linearly with the spilled air
    assert L[1] == pytest.approx(2.0 * L[0], rel=1e-10)
    assert L[2] == pytest.approx(4.0 * L[0], rel=1e-10)


# --- triple point and vortex sheet ---------------------------------------------------------

def _on_line(P, origin, angle_rad):
    return abs(math.cos(angle_rad) * (P[1] - origin[1]) - math.sin(angle_rad) * (P[0] - origin[0]))


@pytest.mark.parametrize("M, tau", [(2.75, 0.02), (2.75, 0.1), (3.0, 0.05)])
def test_triple_point_lies_on_both_shocks(d, M, tau):
    off = _off(d, M)
    s = C.moeckel_shock(d, off, tau)
    T, phi_T, part = C.triple_point(d, off, s)
    o, a = C._last_shock(d, off)
    scale = d.inputs.capture_height
    assert _on_line(T, o, a) < 1e-12 * scale
    if part == "normal":
        t = math.radians(s.theta_n_deg)
        assert _on_line(T, s.world(s.x0, 0.0), t + math.pi / 2) < 1e-12 * scale
        assert phi_T == 90.0
    else:
        # on the hyperbola: local (x, y) satisfy eq. (31)
        t = math.radians(s.theta_n_deg)
        dx, dy = T[0] - s.lip[0], T[1] - s.lip[1]
        x = s.x_SB + dx * math.cos(t) + dy * math.sin(t)
        y = s.y_SB - dx * math.sin(t) + dy * math.cos(t)
        assert s.beta * (y - s.y_m) == pytest.approx(math.sqrt(x * x - s.x0 ** 2), abs=1e-12)


def test_exact_slip_direction_matches_pressure_and_direction(d):
    off = _off(d, 2.75)
    ts = C.slip_direction(off, 90.0)
    up, lo = off.regions[1], off.regions[2]
    pa = up.p_ratio * C._p_branch(up.M, ts - up.theta_deg, 1.4, True)
    pb = lo.p_ratio * C._p_branch(lo.M, ts - lo.theta_deg, 1.4, True)
    assert pa == pytest.approx(pb, rel=1e-9)                           # equal pressure
    # same direction on both sides by construction (one theta_slip); check it is a real
    # polar point on both: deflections within theta_max
    assert abs(ts - up.theta_deg) <= obl.max_deflection(up.M)[0]
    assert abs(ts - lo.theta_deg) <= obl.max_deflection(lo.M)[0]


def test_no_exact_triple_point_on_lip_at_the_design_point(d):
    """At M 3.0 one strong shock from region 1 gives a lower pressure than the two-shock path
    through region 2, so the strong-strong polars do not intersect; the fallback is used."""
    off = _off(d, 3.0)
    assert C.slip_direction(off, 90.0) is None


# --- buzz onset (Ferri & Nucci) --------------------------------------------------------------

def test_on_lip_design_point_has_no_stable_subcritical_range(d):
    # SOURCE: Ferri & Nucci, NACA RM L50K30 (1951), p. 7, finding 2: the stable volume-flow
    # regulation was a minimum (zero) with the shock at the lip of the cowling
    for method in ("exact", "fallback"):
        b = C.buzz_onset(d, _off(d, 3.0), method)
        assert b.zero_range and b.tau == 0.0 and b.mfr == 1.0
        assert b.extrapolated                                          # M 3.0 > 2.7


def test_stable_range_grows_as_the_shocks_move_ahead_of_the_lip(d):
    """Ferri & Nucci p. 7, finding 2 (qualitative): the range grows as the shock moves away
    from the lip. Checked from the design point down to M 2.75; closer to ramp-shock
    detachment M_n -> 1, where Moeckel's method is not valid (TN 1921, p. 14)."""
    for method in ("exact", "fallback"):
        dm = [_off(d, M).mass_capture_ratio * C.buzz_onset(d, _off(d, M), method).tau
              for M in (3.0, 2.95, 2.9, 2.8, 2.75)]
        assert dm[0] == 0.0
        assert all(b > a for a, b in zip(dm, dm[1:])), (method, dm)


def test_buzz_onset_reports_both_methods_and_the_tested_range(d):
    off = _off(d, 2.5)
    e, f = C.buzz_onset(d, off, "exact"), C.buzz_onset(d, off, "fallback")
    assert e.method == "exact" and f.method == "fallback"
    assert e.tau > 0.0 and f.tau > 0.0 and not e.extrapolated           # M 2.5 within 1.9-2.7
    assert e.mfr == pytest.approx(off.mass_capture_ratio * (1.0 - e.tau), rel=1e-12)
    # at the onset the sheet passes through the lip (side ~ 0)
    side, T, theta, _ = C._sheet_state(d, off, e.tau, "exact", {})
    assert abs(side) < 1e-6 * d.inputs.capture_height


def test_characteristic_above_design_has_no_subcritical_model(d):
    c = C.inlet_characteristic(d, _off(d, 3.25), 2.0)
    assert c.subcritical == () and c.buzz is None and c.note == C.ABOVE_DESIGN_NOTE
    assert c.supercritical and c.critical.mfr == 1.0


@pytest.mark.parametrize("call", [
    lambda d: C.supercritical_branch(d, _off(d, 2.75), 0.5),
    lambda d: C.supercritical_branch(d, _off(d, 2.75), 5.0),
    lambda d: C.moeckel_shock(d, _off(d, 2.75), 1.0),
    lambda d: C.moeckel_shock(d, _off(d, 2.75), -0.1),
    lambda d: C.buzz_onset(d, _off(d, 2.75), "guess"),
    lambda d: C.mach_from_area_ratio(0.5),
    lambda d: api.inlet_characteristic(api.design(3.0, 0), None),
    lambda d: api.inlet_characteristic(d, _off(d, 2.39)),            # M_n < 1 behind ramps
])
def test_bad_inputs_raise(d, call):
    with pytest.raises(ValueError):
        call(d)
