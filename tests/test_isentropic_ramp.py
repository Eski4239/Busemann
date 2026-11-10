import math

import numpy as np
import pytest
from scipy.integrate import solve_ivp

from inletdesign import isentropic_ramp as ir
from inletdesign import isentropic as iso
from inletdesign import normal_shock as ns
from inletdesign import prandtl_meyer as pm

M3, DELTA = 3.0, 33.789


def test_nu_at_m3():
    # SOURCE: NACA 1135 Table II, p. 635
    assert pm.nu(M3) == pytest.approx(49.757, abs=1e-3)


def test_recovery_identity_at_m3_delta():
    r = ir.isentropic_ramp(M3, delta_deg=DELTA)
    assert r.M_f == pytest.approx(1.6375, abs=1e-4)
    assert r.recovery == pytest.approx(0.8809, abs=1e-4)


def test_wall_slope_equals_local_flow_angle():
    r = ir.isentropic_ramp(M3, delta_deg=DELTA)
    pts = np.asarray(r.wall_points)
    seg_angles = np.degrees(np.arctan2(np.diff(pts[:, 1]), np.diff(pts[:, 0])))
    thetas = np.linspace(0.0, DELTA, len(pts))
    theta_mid = 0.5 * (thetas[:-1] + thetas[1:])        # each segment's local flow angle
    assert np.max(np.abs(seg_angles - theta_mid)) < 1e-3


def test_mass_flow_through_every_characteristic_matches_capture():
    gamma, h_c = 1.4, 1.0
    r = ir.isentropic_ramp(M3, gamma, h_c, delta_deg=DELTA)
    pts = np.asarray(r.wall_points)
    T0_T_inf = 1.0 + 0.5 * (gamma - 1.0) * M3**2
    rho0_rho_inf = T0_T_inf ** (1.0 / (gamma - 1.0))
    expected = M3 * h_c          # rho_inf V_inf h_c, nondimensionalised by rho_inf a_inf
    lip = np.array(r.lip)
    for i, c in enumerate(r.characteristics, start=1):
        T0_T = 1.0 + 0.5 * (gamma - 1.0) * c.M**2
        rho0_rho = T0_T ** (1.0 / (gamma - 1.0))
        rho_over_rho_inf = rho0_rho_inf / rho0_rho
        a_over_a_inf = np.sqrt(T0_T_inf / T0_T)
        V_over_ainf = c.M * a_over_a_inf
        theta_rad = np.radians(c.theta_deg)
        normal = np.array([-np.sin(theta_rad), np.cos(theta_rad)])
        h_eff = (lip - pts[i]) @ normal
        mass = rho_over_rho_inf * V_over_ainf * h_eff
        assert abs(mass - expected) < 1e-10


def test_delta_zero_is_a_flat_wall_and_pure_normal_shock():
    r = ir.isentropic_ramp(M3, delta_deg=0.0)
    assert r.M_f == pytest.approx(M3)
    assert r.recovery == pytest.approx(ns.stagnation_pressure_ratio(M3), rel=1e-12)
    pts = np.asarray(r.wall_points)
    assert np.allclose(pts[:, 1], 0.0)


def test_geometry_scales_linearly_with_capture_height():
    r1 = ir.isentropic_ramp(M3, capture_height=1.0, delta_deg=DELTA)
    r2 = ir.isentropic_ramp(M3, capture_height=2.0, delta_deg=DELTA)
    pts1, pts2 = np.asarray(r1.wall_points), np.asarray(r2.wall_points)
    assert np.allclose(pts2, 2.0 * pts1, atol=1e-9)
    assert r2.lip == pytest.approx(tuple(2.0 * c for c in r1.lip))
    assert r2.wall_length == pytest.approx(2.0 * r1.wall_length, rel=1e-9)


def test_mf_below_one_point_two_warns_but_does_not_raise():
    # M_inf = 1.8: theta_max (19.18 deg) exceeds the delta that drives M_f below 1.2 (18.5 deg),
    # so this path stays short of cowl detachment while still exercising the low-M_f warning.
    r = ir.isentropic_ramp(1.8, delta_deg=18.5)
    assert r.M_f < ir.MIN_RECOMMENDED_MF
    assert not r.valid
    assert r.warning == ir.LOW_MF_WARNING


def test_mf_below_one_raises():
    nu_inf = pm.nu(M3)
    with pytest.raises(ValueError):
        ir.isentropic_ramp(M3, delta_deg=nu_inf + 1.0)


def test_detached_cowl_raises():
    with pytest.raises(ValueError, match="detached"):
        ir.isentropic_ramp(M3, delta_deg=40.0)


def test_both_or_neither_delta_and_mf_raises():
    with pytest.raises(ValueError):
        ir.isentropic_ramp(M3, delta_deg=10.0, M_f=2.0)
    with pytest.raises(ValueError):
        ir.isentropic_ramp(M3)


def _wall_via_ode(M_inf, gamma, h_c, delta_deg):
    """Independent cross-check of the closed-form wall (NACA 1135 eq. 79): integrate the wall
    as an exact ODE in theta using ONLY the streamline-tangent condition (the wall point stays
    on the characteristic through the lip, and moves along the local flow direction) -- no
    continuity relation assumed. Agreement with the closed form confirms eq. (79) was applied
    correctly, independent of this alternate derivation."""
    nu_inf_rad = math.radians(pm.nu(M_inf, gamma))
    mu_inf = math.asin(1.0 / M_inf)
    lip = (h_c / math.tan(mu_inf), h_c)

    def M_at(theta_rad):
        theta_deg = math.degrees(theta_rad)
        nu_th = math.degrees(nu_inf_rad) - theta_deg
        return 1.0 if nu_th <= 1e-12 else pm.mach_from_nu(nu_th, gamma)

    def dmu_dtheta(M):
        dnu_dM = math.sqrt(M * M - 1.0) / (M * (1.0 + 0.5 * (gamma - 1.0) * M * M))
        dM_dtheta = -1.0 / dnu_dM
        dmu_dM = -1.0 / (M * math.sqrt(M * M - 1.0))
        return dmu_dM * dM_dtheta

    def ode(theta, y):
        M = M_at(theta)
        if M <= 1.0 + 1e-9:
            return [0.0, 0.0]
        mu = math.asin(1.0 / M)
        b = theta + mu
        bp = 1.0 + dmu_dtheta(M)
        ex, ey = math.cos(theta), math.sin(theta)
        ebx, eby = math.cos(b), math.sin(b)
        eb_perp_x, eb_perp_y = -math.sin(b), math.cos(b)
        sin_mu = ex * eby - ey * ebx
        lip_px, lip_py = lip[0] - y[0], lip[1] - y[1]
        ds_dtheta = (lip_px * eb_perp_y - lip_py * eb_perp_x) * bp / sin_mu
        return [ds_dtheta * ex, ds_dtheta * ey]

    sol = solve_ivp(ode, [0.0, math.radians(delta_deg)], [0.0, 0.0],
                    rtol=1e-13, atol=1e-16, method="DOP853")
    return sol.y[:, -1]


def test_closed_form_wall_matches_independent_ode_integration():
    r = ir.isentropic_ramp(M3, delta_deg=DELTA)
    ode_end = _wall_via_ode(M3, 1.4, 1.0, DELTA)
    closed_end = np.array(r.wall_points[-1])
    assert np.max(np.abs(ode_end - closed_end)) < 1e-10


# SOURCE (closed form confirmed by the user, 2026-11-10): NACA 1135 eq. (79) p. 618
# (one-dimensional continuity) applied with A = r, V sin(mu) = a, giving rho*a*r = const
# along the wall; nu(M) from eq. (171) p. 626. Reference values computed from this relation.
def test_reference_values_at_m3_delta_hc_100mm():
    h_c = 0.1          # m
    r = ir.isentropic_ramp(M3, capture_height=h_c, delta_deg=DELTA)
    assert r.M_f == pytest.approx(1.63748, abs=1e-5)

    lip_mm = tuple(c * 1000.0 for c in r.lip)
    # shift so the lip sits at the origin, matching the reference frame
    le_mm = (r.wall_points[0][0] * 1000.0 - lip_mm[0],
             r.wall_points[0][1] * 1000.0 - lip_mm[1])
    end_mm = (r.wall_points[-1][0] * 1000.0 - lip_mm[0],
              r.wall_points[-1][1] * 1000.0 - lip_mm[1])

    assert le_mm == pytest.approx((-282.843, -100.000), abs=5e-4)
    assert end_mm == pytest.approx((-15.781, -46.970), abs=5e-4)
    assert r.lip_to_wall_end * 1000.0 == pytest.approx(49.551, abs=1e-3)
    assert r.wall_length * 1000.0 == pytest.approx(275.61, abs=5e-3)

    AAstar_inf = iso.area_mach_ratio(M3)
    AAstar_f = iso.area_mach_ratio(r.M_f)
    h_t = h_c * (AAstar_f / AAstar_inf)
    assert h_t * 1000.0 == pytest.approx(30.26, abs=1e-2)
