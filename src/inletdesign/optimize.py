"""Ramp-angle optimization for external-compression inlets.

Two independent methods are provided so they can cross-check each other:
- optimize_equal_strength: the Oswatitsch equal-strength condition (every
  oblique shock shares the same shock-normal Mach number Mn), reduced to a
  1-D search over Mn. This is the primary, fast method.
- optimize_numerical: brute-force n-dimensional Nelder-Mead search over the
  ramp angles directly, used only as a correctness check on the method above.
"""
import numpy as np
from scipy.optimize import brentq, minimize, minimize_scalar

from . import inlet
from . import oblique_shock as obl


def equal_strength_ramps(M_inf, n_ramps, Mn, gamma=1.4):
    """Ramp angles giving every oblique shock the same shock-normal Mach Mn.

    Sequentially, for each ramp: beta_i = asin(Mn / M_i) (the definition of
    shock-normal Mach), theta_i = theta_from_beta(M_i, beta_i) recovers the
    deflection that produces that beta, then M_i advances via
    oblique_shock_state before the next ramp.

    beta_i must land on the weak branch (beta_i <= the beta at theta_max for
    M_i): theta alone cannot distinguish a weak from a strong shock, and
    downstream consumers (oblique_shock_state, inlet.compress) always
    reconstruct the weak solution from theta, so a strong-branch beta_i would
    silently be replaced by a different, incorrect weak shock.

    Raises:
        ValueError: if Mn <= 1 or Mn >= M_i at any ramp (including M_inf), or
            if beta_i = asin(Mn / M_i) falls on the strong branch.
    """
    M = M_inf
    angles = []
    for _ in range(n_ramps):
        if Mn <= 1.0 or Mn >= M:
            raise ValueError(f"Mn={Mn} must satisfy 1 < Mn < M={M}")
        beta_deg = np.degrees(np.arcsin(Mn / M))
        _, beta_at_theta_max = obl.max_deflection(M, gamma)
        if beta_deg > beta_at_theta_max:
            raise ValueError(
                f"Mn={Mn} at M={M} requires beta={beta_deg:.4f} deg, which is on the "
                f"strong branch (β at θmax = {beta_at_theta_max:.4f}°); "
                "equal-strength ramps require weak, attached shocks"
            )
        theta_deg = obl.theta_from_beta(M, beta_deg, gamma)
        angles.append(float(theta_deg))
        state = obl.oblique_shock_state(M, theta_deg, gamma, weak=True)
        M = state["M2"]
    return angles


def optimize_equal_strength(M_inf, n_ramps, gamma=1.4, max_turn_deg=None):
    """Maximize total pressure recovery over Mn under the equal-strength condition.

    Coarse grid scan over (1, M_inf), skipping infeasible Mn, then refines
    with a bounded 1-D minimization around the best grid point.

    max_turn_deg optionally limits the total turning (= cowl angle, sum of ramp
    angles). The total turning rises monotonically with Mn and recovery rises
    with Mn up to the optimum, so an active limit puts the constrained optimum
    where sum(theta) = max_turn_deg (solved with brentq on Mn).

    Returns:
        dict with keys: ramps (list[float]), Mn (float or None), recovery
        (float), states (list[FlowState]), constrained (bool).
    """
    if n_ramps == 0:
        states = inlet.compress(M_inf, [], gamma)
        return {"ramps": [], "Mn": None, "recovery": states[-1].p0_ratio, "states": states,
                "constrained": False}
    result = _optimize_unconstrained(M_inf, n_ramps, gamma)
    result["constrained"] = False
    if max_turn_deg is None or sum(result["ramps"]) <= max_turn_deg:
        return result
    if not max_turn_deg > 0:
        raise ValueError(f"max cowl angle must be > 0° (got {max_turn_deg:g}°)")

    def excess(Mn):
        return sum(equal_strength_ramps(M_inf, n_ramps, Mn, gamma)) - max_turn_deg

    Mn = brentq(excess, 1.0 + 1e-9, result["Mn"], xtol=1e-12)
    ramps = equal_strength_ramps(M_inf, n_ramps, Mn, gamma)
    states = inlet.compress(M_inf, ramps, gamma)
    return {"ramps": ramps, "Mn": float(Mn), "recovery": states[-1].p0_ratio,
            "states": states, "constrained": True}


def _optimize_unconstrained(M_inf, n_ramps, gamma):

    def recovery_for_Mn(Mn):
        try:
            ramps = equal_strength_ramps(M_inf, n_ramps, Mn, gamma)
            states = inlet.compress(M_inf, ramps, gamma)
            return states[-1].p0_ratio, ramps, states
        except ValueError:
            return 0.0, None, None

    eps = 1e-6 * M_inf
    grid = np.linspace(1.0, M_inf, 202)[1:-1]
    best_recovery, best_Mn = -1.0, None
    for Mn in grid:
        recovery, _, _ = recovery_for_Mn(Mn)
        if recovery > best_recovery:
            best_recovery, best_Mn = recovery, Mn

    if best_Mn is None:
        raise ValueError("no feasible equal-strength ramp solution found")

    grid_step = grid[1] - grid[0]
    lo = max(1.0 + eps, best_Mn - grid_step)
    hi = min(M_inf - eps, best_Mn + grid_step)
    result = minimize_scalar(
        lambda Mn: -recovery_for_Mn(Mn)[0], bounds=(lo, hi), method="bounded"
    )
    best_Mn = float(result.x)
    recovery, ramps, states = recovery_for_Mn(best_Mn)
    if ramps is None:
        # refinement landed on an infeasible point; fall back to the grid optimum
        best_Mn = float(grid[np.argmax([recovery_for_Mn(m)[0] for m in grid])])
        recovery, ramps, states = recovery_for_Mn(best_Mn)

    return {"ramps": ramps, "Mn": best_Mn, "recovery": recovery, "states": states}


def optimize_numerical(M_inf, n_ramps, gamma=1.4):
    """Cross-check optimize_equal_strength via direct Nelder-Mead over ramp angles.

    Started from the equal-strength solution and two other starting points;
    infeasible designs are penalized with recovery 0 during the search. This
    is an independent cross-check, not the primary optimization method.

    Returns:
        dict with the same keys as optimize_equal_strength, but Mn is always None.
    """
    if n_ramps == 0:
        states = inlet.compress(M_inf, [], gamma)
        return {"ramps": [], "Mn": None, "recovery": states[-1].p0_ratio, "states": states}

    def neg_recovery(angles):
        if np.any(np.asarray(angles) <= 0):
            return 0.0
        try:
            states = inlet.compress(M_inf, list(angles), gamma)
            return -states[-1].p0_ratio
        except ValueError:
            return 0.0

    seed_eq = optimize_equal_strength(M_inf, n_ramps, gamma)["ramps"]
    candidates = [
        seed_eq,
        [a * 0.5 for a in seed_eq],
        [a * 1.5 for a in seed_eq],
    ]

    best_result = None
    best_recovery = -1.0
    for start in candidates:
        result = minimize(neg_recovery, x0=np.array(start), method="Nelder-Mead")
        if -result.fun > best_recovery:
            best_result = result
            best_recovery = -result.fun

    ramps = list(best_result.x)
    states = inlet.compress(M_inf, ramps, gamma)
    return {"ramps": ramps, "Mn": None, "recovery": states[-1].p0_ratio, "states": states}
