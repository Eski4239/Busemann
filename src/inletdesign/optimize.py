"""Ramp-angle optimization for external-compression inlets.

Two independent methods are provided so they can cross-check each other:
- optimize_equal_strength: the Oswatitsch equal-strength condition (every
  oblique shock shares the same shock-normal Mach number Mn), reduced to a
  1-D search over Mn. This is the primary, fast method.
- optimize_numerical: brute-force n-dimensional Nelder-Mead search over the
  ramp angles directly, used only as a correctness check on the method above.

# SOURCE (confirmed): K. Oswatitsch, "Pressure Recovery for Missiles with Reaction Propulsion
#   at High Supersonic Speeds (The Efficiency of Shock Diffusers)", NACA TM 1140 (1947),
#   translation of Forschungen und Entwicklungen des Heereswaffenamtes, Bericht Nr. 1005,
#   Goettingen, January 1944. Equal-strength condition: eq. (17), p. 13
#   (Ma0 sin g0 = Ma1 sin g1 = ...; "the total-pressure ratios as well as the pressure ratios
#   themselves for all oblique compression shocks are equal"); problem statement p. 6.
#   Notation: TM 1140 writes gamma for the shock angle (our beta) and k for the ratio of
#   specific heats (our gamma); its n counts the terminal normal shock (n shocks = n - 1 ramps).
# Consistency check (documented, not a test: the reference values are read off a printed
#   graph): the maximum recovery at M 3 for 1-4 shocks computed here, 0.328 / 0.581 / 0.744 /
#   0.836 (0, 1, 2, 3 ramps + the normal shock), agrees with TM 1140 Fig. 1, p. 43.
"""
import math

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


def optimize_equal_strength(M_inf, n_ramps, gamma=1.4, max_turn_deg=None, unconstrained=None):
    """Maximize total pressure recovery over Mn under the equal-strength condition.

    Coarse grid scan over (1, M_inf), skipping infeasible Mn, then refines
    with a bounded 1-D minimization around the best grid point.

    max_turn_deg optionally limits the total turning (= cowl angle, sum of ramp
    angles). The total turning rises monotonically with Mn and recovery rises
    with Mn up to the optimum, so an active limit puts the constrained optimum
    where sum(theta) = max_turn_deg (solved with brentq on Mn).

    unconstrained optionally passes a precomputed unconstrained result for the same
    (M_inf, n_ramps, gamma) (the dict this function returns without a limit), so a sweep
    over max_turn_deg solves the unconstrained optimum once.

    Returns:
        dict with keys: ramps (list[float]), Mn (float or None), recovery
        (float), states (list[FlowState]), constrained (bool).
    """
    if n_ramps == 0:
        states = inlet.compress(M_inf, [], gamma)
        return {"ramps": [], "Mn": None, "recovery": states[-1].p0_ratio, "states": states,
                "constrained": False}
    result = dict(unconstrained) if unconstrained is not None else         _optimize_unconstrained(M_inf, n_ramps, gamma)
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


def optimum_near(M_inf, n_ramps, gamma, Mn_guess, window=0.3):
    """Unconstrained equal-strength optimum found by a bounded search for Mn with
    Mn - 1 within (Mn_guess - 1) * (1 +- window): a warm start from a nearby design Mach.
    Infeasible Mn (strong branch, Mn >= M) score 0, as in the full search. Falls back to the
    full grid search when the optimum lands on the window edge or is infeasible, so the
    result equals optimize_equal_strength (without a limit) to the optimiser tolerance.
    """
    eps = 1e-6 * M_inf
    excess = Mn_guess - 1.0
    lo = max(1.0 + eps, 1.0 + excess * (1.0 - window))
    hi = min(M_inf - eps, 1.0 + excess * (1.0 + window))

    if excess > 0.0 and lo < hi:
        res = minimize_scalar(lambda Mn: -fast_recovery(M_inf, n_ramps, Mn, gamma),
                              bounds=(lo, hi), method="bounded")
        Mn = float(res.x)
        edge = 1e-3 * (hi - lo)
        if lo + edge < Mn < hi - edge and fast_recovery(M_inf, n_ramps, Mn, gamma) > 0.0:
            return _result(M_inf, n_ramps, Mn, gamma, False)
    result = _optimize_unconstrained(M_inf, n_ramps, gamma)
    result["constrained"] = False
    return result


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


# --- fast equal-strength chain for trade-study searches (M9a) -------------------------------
# Equal strength fixes beta_i = asin(Mn / M_i) directly, so every ramp is closed form: theta
# from the theta-beta-M relation, M_{i+1} = Mn2 / sin(beta - theta), the oblique p0 ratio is
# the normal-shock p0 ratio at Mn. No cubic for beta(theta) is solved (oblique_shock_state
# does that), which makes a search ~10x cheaper. Only the searches use it; the reported
# results are rebuilt with equal_strength_ramps / inlet.compress.

def _normal_p0(M, g):
    """Normal-shock p02/p01 (closed form, as normal_shock.stagnation_pressure_ratio)."""
    m2 = M * M
    rho = (g + 1.0) * m2 / ((g - 1.0) * m2 + 2.0)
    p = 1.0 + 2.0 * g / (g + 1.0) * (m2 - 1.0)
    return rho ** (g / (g - 1.0)) * p ** (-1.0 / (g - 1.0))


def _chain(M_inf, n_ramps, Mn, g):
    """(ramp angles deg, Mach ahead of the terminal shock, total recovery), or None where
    equal_strength_ramps would raise (Mn <= 1, Mn >= M_i, strong branch)."""
    M = M_inf
    angles = []
    for _ in range(n_ramps):
        if Mn <= 1.0 or Mn >= M:
            return None
        beta = math.asin(Mn / M)
        m2 = M * M
        gp1 = g + 1.0
        sin2 = (gp1 * m2 - 4.0 + math.sqrt(gp1 * (gp1 * m2 * m2 + 8.0 * (g - 1.0) * m2 + 16.0))
                ) / (4.0 * g * m2)
        if beta > math.asin(math.sqrt(min(sin2, 1.0))):
            return None                              # strong branch
        tan_t = 2.0 / math.tan(beta) * (m2 * math.sin(beta) ** 2 - 1.0) / \
            (m2 * (g + math.cos(2.0 * beta)) + 2.0)
        theta = math.atan(tan_t)
        mn2 = math.sqrt((1.0 + 0.5 * (g - 1.0) * Mn * Mn) / (g * Mn * Mn - 0.5 * (g - 1.0)))
        M = mn2 / math.sin(beta - theta)
        angles.append(math.degrees(theta))
    recovery = _normal_p0(Mn, g) ** n_ramps * (_normal_p0(M, g) if M > 1.0 else 1.0)
    return angles, M, recovery


def fast_recovery(M_inf, n_ramps, Mn, gamma=1.4):
    r = _chain(M_inf, n_ramps, Mn, gamma)
    return 0.0 if r is None else r[2]


def fast_turning(M_inf, n_ramps, Mn, gamma=1.4):
    r = _chain(M_inf, n_ramps, Mn, gamma)
    return None if r is None else sum(r[0])


def _result(M_inf, n_ramps, Mn, gamma, constrained):
    ramps = equal_strength_ramps(M_inf, n_ramps, Mn, gamma)
    states = inlet.compress(M_inf, ramps, gamma)
    return {"ramps": ramps, "Mn": float(Mn), "recovery": states[-1].p0_ratio,
            "states": states, "constrained": constrained}


def constrained_optimum(M_inf, n_ramps, gamma, max_turn_deg, unconstrained):
    """The cowl-constrained optimum of optimize_equal_strength (sum(theta) = max_turn_deg,
    brentq on Mn below the unconstrained Mn), with the root found on the fast chain."""
    if max_turn_deg >= sum(unconstrained["ramps"]):
        return dict(unconstrained, constrained=False)
    Mn = brentq(lambda m: fast_turning(M_inf, n_ramps, m, gamma) - max_turn_deg,
                1.0 + 1e-9, unconstrained["Mn"], xtol=1e-12)
    return _result(M_inf, n_ramps, Mn, gamma, True)
