"""Gap to the Oswatitsch optimum and recovery sensitivities (addendum C3, no Qt)."""
import pytest

from inletdesign import api


def test_gap_is_zero_at_the_optimum_angles():
    opt = api.design(3.0, 2)
    same = api.design(3.0, 2, ramp_angles=list(opt.ramp_angles_deg))
    gap, eta_opt = api.optimum_gap(same)
    assert gap == pytest.approx(0.0, abs=1e-9) and eta_opt == opt.recovery_total


def test_gap_definition():
    d = api.design(3.0, 2, ramp_angles=[9.0, 10.0])
    gap, eta_opt = api.optimum_gap(d)
    assert gap == pytest.approx(100.0 * (eta_opt - d.recovery_total) / eta_opt, rel=1e-15)
    assert gap > 0


def test_sensitivity_matches_a_finite_difference():
    d = api.design(3.0, 2, ramp_angles=[9.0, 10.0])
    sens = api.recovery_sensitivity(d, step_deg=0.01)
    assert len(sens) == 2
    # self-consistency: moving theta_1 by 0.2 deg changes eta by about sens * 0.2
    moved = api.design(3.0, 2, ramp_angles=[9.2, 10.0]).recovery_total
    assert moved - d.recovery_total == pytest.approx(sens[0] * 0.2, rel=0.05)
    assert all(s > 0 for s in sens)            # below the optimum: more turning helps here


def test_one_sided_next_to_detachment():
    theta_max = api.max_deflection(3.0)
    d = api.design(3.0, 1, ramp_angles=[theta_max - 0.005])
    sens = api.recovery_sensitivity(d, step_deg=0.01)
    assert sens[0] is not None


def test_bad_step_raises():
    with pytest.raises(ValueError):
        api.recovery_sensitivity(api.design(3.0, 2, ramp_angles=[9.0, 10.0]), step_deg=0.0)
