"""Oblique shock relations for a calorically perfect gas.

All functions take the upstream Mach number M1 (dimensionless, M1 >= 1) and
ratio of specific heats gamma (default 1.4, air). Angles are in DEGREES at
this public API (converted to radians internally). Oblique shock states are
obtained by decomposing the flow into the shock-normal Mach number
Mn1 = M1*sin(beta) and reusing the normal_shock relations on that component.
Reference: NACA Report 1135, oblique shock relations (theta-beta-M chart).
Notation: theta = flow deflection, beta = shock angle (NACA 1135 uses the reverse).
"""
import math

import numpy as np

from . import normal_shock as ns


def _validate(M1, gamma):
    if gamma <= 1.0:
        raise ValueError("gamma must be > 1")
    if isinstance(M1, (int, float)):  # fast path: this module sits in the optimiser's inner loop
        if not M1 >= 1.0:
            raise ValueError("M1 must be >= 1 (oblique shock requires supersonic upstream flow)")
        return float(M1)
    M1 = np.asarray(M1, dtype=float)
    if np.any(M1 < 1.0):
        raise ValueError("M1 must be >= 1 (oblique shock requires supersonic upstream flow)")
    return M1


def _mach_angle_deg(M1):
    return np.degrees(np.arcsin(1.0 / M1))


def theta_from_beta(M1, beta_deg, gamma=1.4):
    """theta-beta-M relation: tan(theta) = 2*cot(beta)*(M1^2*sin(beta)^2 - 1) / (M1^2*(gamma+cos(2*beta)) + 2)."""
    M1 = _validate(M1, gamma)
    beta = np.radians(beta_deg)
    numerator = M1**2 * np.sin(beta) ** 2 - 1.0
    denominator = M1**2 * (gamma + np.cos(2.0 * beta)) + 2.0
    tan_theta = 2.0 / np.tan(beta) * numerator / denominator
    return np.degrees(np.arctan(tan_theta))


def _beta_at_max_deg(M1, gamma):
    """sin^2(beta*) = [(g+1)M^2 - 4 + sqrt((g+1)((g+1)M^4 + 8(g-1)M^2 + 16))] / (4 g M^2)
    (closed form of d(theta)/d(beta) = 0)."""
    M2 = M1 * M1
    gp1 = gamma + 1.0
    root = np.sqrt(gp1 * (gp1 * M2 * M2 + 8.0 * (gamma - 1.0) * M2 + 16.0))
    sin2 = (gp1 * M2 - 4.0 + root) / (4.0 * gamma * M2)
    return np.degrees(np.arcsin(np.sqrt(np.minimum(sin2, 1.0))))


def max_deflection(M1, gamma=1.4):
    """theta_max and the beta at which it occurs: beta* in closed form, theta_max = theta_from_beta(beta*)."""
    M1 = _validate(M1, gamma)
    beta_at_max = _beta_at_max_deg(M1, gamma)
    theta_max = theta_from_beta(M1, beta_at_max, gamma)
    if np.ndim(M1) == 0:
        return float(theta_max), float(beta_at_max)
    return theta_max, beta_at_max


def _beta_cubic_deg(M1, theta_deg, gamma, weak):
    """Root of the theta-beta-M cubic in tan(beta) (trigonometric form):
    tan(beta) = [M^2 - 1 + 2 lam cos((4 pi d + acos(chi)) / 3)] / [3 (1 + (g-1)/2 M^2) tan(theta)],
    lam = sqrt((M^2-1)^2 - 3 (1 + (g-1)/2 M^2)(1 + (g+1)/2 M^2) tan^2 theta),
    chi = [(M^2-1)^3 - 9 (1 + (g-1)/2 M^2)(1 + (g-1)/2 M^2 + (g+1)/4 M^4) tan^2 theta] / lam^3,
    d = 1 weak, d = 0 strong."""
    M2 = M1 * M1
    t = np.tan(np.radians(theta_deg))
    a = 1.0 + 0.5 * (gamma - 1.0) * M2
    b = 1.0 + 0.5 * (gamma + 1.0) * M2
    lam = np.sqrt(np.maximum((M2 - 1.0) ** 2 - 3.0 * a * b * t * t, 0.0))
    with np.errstate(divide="ignore", invalid="ignore"):
        chi = ((M2 - 1.0) ** 3 - 9.0 * a * (a + 0.25 * (gamma + 1.0) * M2 * M2) * t * t) / lam**3
    chi = np.clip(np.nan_to_num(chi, nan=1.0), -1.0, 1.0)
    delta = 1.0 if weak else 0.0
    tan_beta = (M2 - 1.0 + 2.0 * lam * np.cos((4.0 * np.pi * delta + np.arccos(chi)) / 3.0)) / (
        3.0 * a * t
    )
    if weak:
        # The trigonometric form cancels catastrophically as theta -> 0 (numerator and
        # denominator both -> 0). Polish on the cubic itself,
        # f(x) = a t x^3 - (M^2 - 1) x^2 + b t x + 1, which is well conditioned at the weak
        # root; start from tan(mu) (the theta = 0 root) when the estimate is unusable.
        x_mu = 1.0 / np.sqrt(M2 - 1.0)
        x = np.where(np.isfinite(tan_beta) & (tan_beta > x_mu), tan_beta, x_mu)
        for _ in range(8):
            f = ((a * t * x - (M2 - 1.0)) * x + b * t) * x + 1.0
            df = (3.0 * a * t * x - 2.0 * (M2 - 1.0)) * x + b * t
            x = x - f / df
        tan_beta = x
    return np.degrees(np.arctan(tan_beta))


def beta_from_theta(M1, theta_deg, gamma=1.4, weak=True):
    """Invert the theta-beta-M relation for beta, selecting the weak or strong root
    (analytic cubic in tan(beta), see _beta_cubic_deg)."""
    M1 = _validate(M1, gamma)
    theta_max, beta_at_max = max_deflection(M1, gamma)
    if theta_deg > theta_max:
        raise ValueError(
            f"θ = {float(theta_deg):.2f}° exceeds θmax = {float(theta_max):.2f}° at "
            f"M₁ = {float(M1):.3f}: the shock detaches (no attached oblique-shock solution)"
        )
    mach_angle = float(_mach_angle_deg(M1))
    if theta_deg <= 0.0:
        return mach_angle if weak else 90.0
    beta = float(_beta_cubic_deg(M1, theta_deg, gamma, weak))
    # The two roots meet at theta_max; keep each on its own side of beta* against rounding.
    return min(beta, beta_at_max) if weak else max(beta, beta_at_max)


def oblique_shock_state(M1, theta_deg, gamma=1.4, weak=True):
    """Full post-shock state for the oblique shock solving the given deflection theta.

    Returns a dict with keys: beta, M2, p2_p1, T2_T1, rho2_rho1, p02_p01
    (beta in degrees). Computed by applying normal_shock relations to the
    shock-normal Mach number Mn1 = M1*sin(beta), then recovering M2 via
    M2 = Mn2 / sin(beta - theta).
    """
    beta_deg = beta_from_theta(M1, theta_deg, gamma, weak)
    beta = np.radians(beta_deg)
    Mn1 = M1 * np.sin(beta)
    Mn2 = ns.mach_downstream(Mn1, gamma)
    p2_p1 = ns.pressure_ratio(Mn1, gamma)
    T2_T1 = ns.temperature_ratio(Mn1, gamma)
    rho2_rho1 = ns.density_ratio(Mn1, gamma)
    p02_p01 = ns.stagnation_pressure_ratio(Mn1, gamma)
    M2 = Mn2 / np.sin(np.radians(beta_deg - theta_deg))
    return {
        "beta": float(beta_deg),
        "M2": float(M2),
        "p2_p1": float(p2_p1),
        "T2_T1": float(T2_T1),
        "rho2_rho1": float(rho2_rho1),
        "p02_p01": float(p02_p01),
    }
