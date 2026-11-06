"""Trade study (M9a, addendum D.1, no Qt): recovery vs total turning for n ramps and the
isentropic limit, and recovery / cowl angle vs design Mach. Exact within the model."""
import math
import time

import pytest

from inletdesign import api
from inletdesign import normal_shock as ns
from inletdesign import prandtl_meyer as pm


@pytest.fixture(scope="module")
def turning():
    return {c.n: c for c in api.trade_vs_turning(3.0)}


@pytest.fixture(scope="module")
def iso():
    return api.isentropic_vs_turning(3.0)


@pytest.fixture(scope="module")
def mach_trade():
    return api.trade_vs_design_mach()


def test_normal_shock_at_mach_3(mach_trade):
    # SOURCE: NACA 1135 Table II (supersonic flow), p. 635, M = 3.00: normal-shock
    # p0y/p0x = .3283 (tabulated to 4 s.f.); 0.32834 is the closed form to 5 s.f.
    k = mach_trade.M.index(3.0)
    n0 = next(c for c in mach_trade.curves if c.n == 0)
    assert n0.recovery_total[k] == pytest.approx(0.32834, abs=1e-5)
    assert n0.recovery_total[k] == pytest.approx(0.3283, abs=5e-5)
    assert n0.recovery_total[k] == pytest.approx(float(ns.stagnation_pressure_ratio(3.0)),
                                                 rel=1e-12)          # closed form
    assert n0.cowl_deg[k] == 0.0 and n0.ramps_deg[k] == ()


def test_two_ramps_at_mach_3_unconstrained(turning, mach_trade):
    # Values given by the user (4 s.f.), also in test_optimize / test_examples; the exact
    # check is self-consistency with api.design.
    c = turning[2]
    assert c.recovery_total[-1] == pytest.approx(0.7437, abs=5e-5)
    assert c.cowl_opt_deg == pytest.approx(33.79, abs=5e-3)
    d = api.design(3.0, 2)
    assert c.recovery_total[-1] == pytest.approx(d.recovery_total, abs=1e-12)
    assert c.recovery_oblique[-1] == pytest.approx(d.recovery_oblique, abs=1e-12)
    assert c.cowl_opt_deg == pytest.approx(d.cowl_angle_deg, abs=1e-12)
    k = mach_trade.M.index(3.0)
    two = next(m for m in mach_trade.curves if m.n == 2)
    assert two.recovery_total[k] == pytest.approx(d.recovery_total, abs=1e-12)


def test_prandtl_meyer_at_mach_3():
    # SOURCE: NACA 1135 Table II (supersonic flow), p. 635, M = 3.00: nu = 49.757 deg
    # (mu = 19.47 deg = asin(1/3) on the same row).
    assert float(pm.nu(3.0)) == pytest.approx(49.757, abs=5e-4)


def test_isentropic_curve_starts_at_the_normal_shock_and_ends_at_sonic(iso):
    assert iso.delta_deg[0] == 0.0 and iso.M_f[0] == pytest.approx(3.0, abs=1e-9)
    assert iso.recovery[0] == pytest.approx(float(ns.stagnation_pressure_ratio(3.0)),
                                            rel=1e-9)               # identity at delta = 0
    assert iso.delta_deg[-1] == pytest.approx(float(pm.nu(3.0)), abs=1e-9)
    assert iso.M_f[-1] == 1.0 and iso.recovery[-1] == pytest.approx(1.0, abs=1e-12)
    assert all(m >= 1.0 for m in iso.M_f)
    # nu(M_f) = nu(M) - delta at every point (closed-form inverse)
    for d, m in zip(iso.delta_deg[:-1], iso.M_f[:-1]):
        assert float(pm.nu(m)) == pytest.approx(float(pm.nu(3.0)) - d, abs=1e-8)


def test_isentropic_grid_stops_where_the_flow_would_be_subsonic():
    nu3 = float(pm.nu(3.0))
    c = api.isentropic_vs_turning(3.0, delta_grid=(0.0, 10.0, 49.0, 50.0, 60.0))
    assert c.delta_deg == (0.0, 10.0, 49.0) and nu3 < 50.0


def _dominance_margins():
    """(n, delta, isentropic - n-ramp recovery) at every point of every n-ramp curve, for a
    few design Machs, the isentropic value evaluated at exactly the same delta."""
    out = []
    for M in (1.5, 2.0, 3.0, 4.5, 6.7):
        for c in api.trade_vs_turning(M):
            iso = api.isentropic_vs_turning(M, delta_grid=c.delta_deg)
            for d, r_iso, r_n in zip(iso.delta_deg, iso.recovery, c.recovery_total):
                out.append((M, c.n, d, r_iso - r_n))
    return out


def test_isentropic_recovery_bounds_every_ramp_count():
    margins = _dominance_margins()
    violations = [m for m in margins if m[3] < -1e-12]
    assert violations == [], f"isentropic below an n-ramp curve (M, n, delta, margin): " \
                             f"{violations[:10]}"


def test_constrained_points_turn_exactly_delta(turning):
    for n, c in turning.items():
        assert len(c.delta_deg) == api.TRADE_DELTA_POINTS
        assert c.delta_deg[0] == pytest.approx(api.TRADE_DELTA_MIN, abs=1e-9)
        assert c.delta_deg[-1] == c.cowl_opt_deg and not c.constrained[-1]
        assert all(c.constrained[:-1])
        for d, ramps in zip(c.delta_deg, c.ramps_deg):
            assert len(ramps) == n and sum(ramps) == pytest.approx(d, abs=1e-9)
        # constrained optimum = api.design with that cowl limit (self-consistency)
        k = len(c.delta_deg) // 2
        d = api.design(3.0, n, max_cowl_angle=c.delta_deg[k])
        assert c.recovery_total[k] == pytest.approx(d.recovery_total, abs=1e-9)
        assert all(b > a for a, b in zip(c.recovery_total, c.recovery_total[1:]))


def test_given_turning_grid_is_cut_at_the_optimum():
    [c] = api.trade_vs_turning(3.0, n_list=(1,), delta_grid=(5.0, 10.0, 30.0, 40.0))
    assert c.delta_deg[:2] == pytest.approx((5.0, 10.0)) and c.delta_deg[-1] == c.cowl_opt_deg
    assert len(c.delta_deg) == 3                       # 30 and 40 are past 22.59


def test_recovery_rises_with_ramp_count_at_every_design_mach(mach_trade):
    curves = sorted(mach_trade.curves, key=lambda c: c.n)
    for k, M in enumerate(mach_trade.M):
        values = [c.recovery_total[k] for c in curves]
        assert all(b > a for a, b in zip(values, values[1:])), (M, values)


def test_warm_started_sweep_matches_design(mach_trade):
    """Self-consistency: the warm-started design-Mach sweep equals api.design (recovery to
    1e-9; the cowl angle to 1e-3 deg, because the optimum is flat in Mn and both searches
    stop at the optimiser tolerance)."""
    for c in mach_trade.curves:
        for k in range(0, len(c.M), 6):
            d = api.design(c.M[k], c.n)
            assert c.recovery_total[k] == pytest.approx(d.recovery_total, abs=1e-9)
            assert c.cowl_deg[k] == pytest.approx(d.cowl_angle_deg, abs=1e-3)
            assert sum(c.ramps_deg[k]) == pytest.approx(c.cowl_deg[k], abs=1e-12)


def test_theta_max_curve(mach_trade):
    assert len(mach_trade.theta_max_deg) == len(mach_trade.M) == 59
    assert mach_trade.M[0] == 1.2 and mach_trade.M[-1] == 7.0
    k = mach_trade.M.index(3.0)
    assert mach_trade.theta_max_deg[k] == pytest.approx(api.max_deflection(3.0), abs=1e-12)


@pytest.mark.parametrize("call", [
    lambda: api.trade_vs_turning(0.9),
    lambda: api.trade_vs_turning(3.0, gamma=1.0),
    lambda: api.trade_vs_turning(3.0, n_list=(0,)),
    lambda: api.trade_vs_turning(3.0, n_list=(5,)),
    lambda: api.trade_vs_turning(3.0, delta_grid=(10.0, 5.0)),
    lambda: api.trade_vs_turning(3.0, delta_grid=(-1.0, 5.0)),
    lambda: api.trade_vs_turning(3.0, delta_grid=("a",)),
    lambda: api.isentropic_vs_turning(float("nan")),
    lambda: api.trade_vs_design_mach(M_grid=(1.0, 2.0)),
    lambda: api.trade_vs_design_mach(M_grid=()),
    lambda: api.trade_vs_design_mach(n_list=(2.5,)),
])
def test_bad_inputs_raise(call):
    with pytest.raises(ValueError):
        call()


def test_results_serialise():
    import json

    json.dumps(api.trade_vs_turning(2.0)[0].to_dict())
    json.dumps(api.isentropic_vs_turning(2.0).to_dict())
    json.dumps(api.trade_vs_design_mach(M_grid=(2.0, 3.0)).to_dict())


@pytest.mark.perf
def test_full_tab_data_under_a_second():
    """Every number the Analytics tab shows, from a cold cache, in < 1 s (plugged in)."""
    for f in (api._turning_curve, api._isentropic_cached, api._mach_curve,
              api._theta_max_curve):
        f.cache_clear()
    t = time.perf_counter()
    api.trade_vs_turning(3.0)
    api.isentropic_vs_turning(3.0)
    api.trade_vs_design_mach()
    elapsed = time.perf_counter() - t
    assert elapsed < 1.0, f"{elapsed:.3f} s"
    assert math.isfinite(elapsed)
