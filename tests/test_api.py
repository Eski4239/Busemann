import json
import math
import time

import pytest

from inletdesign import api
from inletdesign import atmosphere as atm
from inletdesign import inlet as _inlet
from inletdesign import isentropic as isen
from inletdesign.geometry import design_inlet
from inletdesign.offdesign import off_design


def _json_ok(obj):
    json.dumps(obj.to_dict())


# --- freestream -------------------------------------------------------------

def test_freestream_altitude_matches_atmosphere():
    fs = api.freestream(2.0, altitude_m=11000.0)
    assert fs.mode == "altitude"
    assert fs.p == pytest.approx(float(atm.pressure(11000.0)))
    assert fs.T == pytest.approx(float(atm.temperature(11000.0)))
    assert fs.rho == pytest.approx(fs.p / (atm.R_AIR * fs.T))
    assert fs.V == pytest.approx(2.0 * math.sqrt(1.4 * atm.R_AIR * fs.T))
    assert fs.p0 / fs.p == pytest.approx(float(isen.stagnation_pressure_ratio(2.0)))
    assert fs.T0 / fs.T == pytest.approx(float(isen.stagnation_temperature_ratio(2.0)))
    assert fs.Re_per_m == pytest.approx(fs.rho * fs.V / fs.mu)
    _json_ok(fs)


def test_freestream_manual_mode():
    fs = api.freestream(3.0, p=10000.0, T=220.0)
    assert fs.mode == "manual" and fs.altitude_m is None
    assert fs.p == 10000.0 and fs.T == 220.0
    _json_ok(fs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"p": 1e4},
        {"altitude_m": 1000.0, "p": 1e4, "T": 200.0},
        {"p": -1.0, "T": 200.0},
        {"p": 1e4, "T": 0.0},
        {"altitude_m": 90000.0},
        {"altitude_m": 0.0, "gamma": 1.0},
    ],
)
def test_freestream_invalid_inputs(kwargs):
    with pytest.raises(ValueError):
        api.freestream(2.0, **kwargs)


def test_real_gas_warning_threshold_is_on_T0():
    hot = api.freestream(6.7, altitude_m=31000.0)
    cool = api.freestream(3.2, altitude_m=24000.0)
    assert hot.T0 > api.REAL_GAS_T0_LIMIT and any("real-gas" in w for w in hot.warnings)
    assert cool.T0 < api.REAL_GAS_T0_LIMIT and not cool.warnings


def test_captured_mass_flow_closed_form():
    fs = api.freestream(3.0, p=10000.0, T=220.0)
    assert api.captured_mass_flow(fs, 0.1, 0.9) == pytest.approx(fs.rho * fs.V * 0.1 * 0.9)


# --- design -----------------------------------------------------------------

@pytest.mark.parametrize("M, n", [(3.0, 2), (2.0, 1), (4.0, 3), (2.5, 0), (3.0, 4)])
def test_design_matches_core(M, n):
    r = api.design(M, n, capture_height=0.1)
    geom = design_inlet(M, n, capture_height=0.1)
    states = _inlet.compress(M, geom.ramp_angles_deg)
    assert r.ramp_angles_deg == pytest.approx(geom.ramp_angles_deg)
    assert r.recovery_total == pytest.approx(states[-1].p0_ratio)
    assert r.M_post_terminal == pytest.approx(states[-1].M)
    assert r.throat_height == pytest.approx(geom.throat_height)
    assert r.cowl_angle_deg == pytest.approx(geom.cowl_angle_deg)
    assert len(r.regions) == n + 2  # freestream, n ramp regions, duct
    assert r.regions[0].p0_ratio == 1.0
    assert r.regions[-1].p0_ratio == pytest.approx(r.recovery_total)
    assert r.inputs.method == "oswatitsch"
    # Only cowl-attachment notices are expected here (M3.1 check).
    assert all(w.startswith(("Cowl near", "External cowl")) for w in r.warnings)
    _json_ok(r)


def test_design_custom_angles_round_trip():
    ref = api.design(3.0, 2)
    r = api.design(3.0, 2, ramp_angles=list(ref.ramp_angles_deg))
    assert r.inputs.method == "custom"
    assert r.recovery_total == pytest.approx(ref.recovery_total)


def test_design_custom_detached_message():
    with pytest.raises(ValueError, match="detachment limit"):
        api.design(2.0, 1, ramp_angles=[30.0])


@pytest.mark.parametrize(
    "args, kwargs",
    [
        ((0.9, 2), {}),
        ((3.0, 5), {}),
        ((3.0, 2), {"capture_height": 0.0}),
        ((3.0, 2), {"ramp_angles": [10.0]}),
        ((3.0, 2), {"ramp_angles": [10.0, -1.0]}),
    ],
)
def test_design_invalid_inputs(args, kwargs):
    with pytest.raises(ValueError):
        api.design(*args, **kwargs)


def test_design_custom_subsonic_behind_last_ramp():
    # Find the subsonic band just below detachment for one ramp at M 2 (closed-form check).
    from inletdesign import oblique_shock as obl

    theta_max, _ = obl.max_deflection(2.0)
    theta = float(theta_max) - 1e-3
    M2 = obl.oblique_shock_state(2.0, theta, weak=True)["M2"]
    assert M2 < 1.0  # weak branch is subsonic this close to theta_max
    r = api.design(2.0, 1, ramp_angles=[theta])
    assert api.SUBSONIC_WARNING in r.warnings
    assert r.recovery_total == r.recovery_oblique
    assert r.M_post_terminal == r.M_pre_terminal == pytest.approx(M2)


# --- off-design -------------------------------------------------------------

def test_off_design_point_matches_core():
    d = api.design(3.0, 2, capture_height=0.1)
    p = api.off_design_point(d, 2.75)
    ref = off_design(design_inlet(3.0, 2, capture_height=0.1), 2.75)
    assert p.mass_capture_ratio == pytest.approx(ref.mass_capture_ratio)
    assert p.recovery_total == pytest.approx(ref.recovery_total)
    assert p.regime == ref.regime
    _json_ok(p)


def test_off_design_point_detached_message():
    d = api.design(3.0, 2)
    with pytest.raises(ValueError, match="shock detached"):
        api.off_design_point(d, 1.5)


def test_sweep_detachment_brackets_first_attached_point():
    d = api.design(3.0, 2)
    sweep = api.off_design_sweep(d, 2.0, 3.5, 61)
    _json_ok(sweep)
    first = next(i for i, p in enumerate(sweep.points) if p is not None)
    assert first > 0
    assert sweep.machs[first - 1] < sweep.detachment_mach <= sweep.machs[first]
    assert all(p is None for p in sweep.points[:first])
    assert all(p is not None for p in sweep.points[first:])


def test_sweep_invalid_inputs():
    d = api.design(3.0, 2)
    with pytest.raises(ValueError):
        api.off_design_sweep(d, 3.0, 2.0, 10)
    with pytest.raises(ValueError):
        api.off_design_sweep(d, 2.0, 3.0, 1)


@pytest.mark.perf
def test_sweep_performance_100_points():
    d = api.design(3.0, 2)
    t0 = time.perf_counter()
    api.off_design_sweep(d, 2.0, 4.5, 100)
    assert time.perf_counter() - t0 < 0.5


# --- shock states and off-design drawing data (M3) ------------------------------------

def test_shock_states_consistent_with_regions():
    d = api.design(3.0, 3)
    assert [s.kind for s in d.shock_states] == ["oblique"] * 3 + ["normal"]
    for i, s in enumerate(d.shock_states):
        up, down = d.regions[i], d.regions[i + 1]
        assert s.M1 == pytest.approx(up.M)
        assert s.p2_p1 == pytest.approx(down.p_ratio / up.p_ratio)
        assert s.p0_ratio * up.p0_ratio == pytest.approx(down.p0_ratio)
        assert s.p0_loss == pytest.approx(1.0 - s.p0_ratio)
        assert s.Mn1 == pytest.approx(up.M * math.sin(math.radians(s.beta_deg)))
    assert d.shock_states[-1].Mn1 == pytest.approx(d.shock_states[-1].M1)


def test_off_design_regions_and_streamline_serialise():
    d = api.design(3.0, 2, capture_height=0.1)
    r = api.off_design_point(d, 2.5)
    json.dumps(r.to_dict())
    assert len(r.regions) == 4 and len(r.shock_states) == 3
    assert r.regions[-1].p0_ratio == pytest.approx(r.recovery_total)
    assert r.capture_streamline[-1] == pytest.approx(d.geometry.lip)
    assert r.capture_streamline[0][1] == pytest.approx(r.mass_capture_ratio * 0.1)


def test_off_design_at_design_mach_reproduces_design_states():
    d = api.design(3.0, 2)
    r = api.off_design_point(d, 3.0)
    for a, b in zip(r.regions, d.regions):
        assert a.M == pytest.approx(b.M, rel=1e-9)
    assert r.betas_deg == pytest.approx(d.betas_deg, abs=1e-9)


# --- M5: M_duct renamed; the deprecated alias was removed in M12 ---------------------

def test_pre_and_post_terminal_mach():
    d = api.design(3.0, 2)
    assert d.M_pre_terminal == pytest.approx(d.regions[-2].M)        # behind ramp shock 2
    assert d.M_post_terminal == pytest.approx(d.regions[-1].M)       # behind terminal shock
    assert d.M_post_terminal < 1.0 < d.M_pre_terminal
    off = api.off_design_point(d, 2.5)
    assert off.M_pre_terminal == pytest.approx(off.regions[-2].M)
    assert off.M_post_terminal == pytest.approx(off.regions[-1].M)
    for r in (d, off):
        data = r.to_dict()
        assert {"M_pre_terminal", "M_post_terminal"} <= set(data) and "M_duct" not in data
        assert not hasattr(r, "M_duct")                               # alias removed (M12)


def test_shock_and_freestream_explain_fields_are_consistent():
    """Closed-form identities between the M5 fields and the existing ones."""
    d = api.design(3.0, 2)
    for s, up, down in zip(d.shock_states, d.regions, d.regions[1:]):
        assert s.M2 == down.M
        assert s.Mn2 == pytest.approx(down.M * math.sin(math.radians(s.beta_deg - s.theta_deg)))
        assert s.p2_p1 == pytest.approx(s.rho2_rho1 * s.T2_T1)          # ideal gas
        assert s.T2_T1 == pytest.approx(down.T_ratio / up.T_ratio)
    fs = api.freestream(3.0, altitude_m=20000.0)
    assert fs.T0 == pytest.approx(fs.T * fs.T0_T) and fs.p0 == pytest.approx(fs.p * fs.p0_p)
    assert fs.a == pytest.approx(math.sqrt(fs.gamma * fs.R * fs.T))
