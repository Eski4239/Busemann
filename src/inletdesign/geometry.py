"""2D external-compression inlet geometry under the shock-on-lip design condition:
every oblique shock (and the terminal normal shock) passes through the cowl lip
point L. Pure geometry from the optimizer's ramp angles; no plotting or export.

Coordinate system: freestream along +x, ramp leading edge at the origin, ramps
turn the flow toward +y, cowl above the ramps. Ramp angles are incremental, as
in inlet.compress(): the cumulative flow direction after ramp i is
phi_i = sum of the first i ramp angles (phi_0 = 0, the freestream direction).
"""
from dataclasses import dataclass

import numpy as np

from . import oblique_shock as obl


@dataclass
class InletGeometry:
    ramp_points: list
    lip: tuple
    shocks: list
    capture_height: float
    throat_height: float
    cowl_angle_deg: float
    ramp_angles_deg: list
    betas_deg: list
    M_inf: float
    scale: float
    constrained: bool = False


def _line_intersect(p1, dir1_deg, p2, dir2_deg):
    """Intersection of the ray from p1 (direction dir1_deg) with the ray from p2 (direction dir2_deg)."""
    p1 = np.array(p1, dtype=float)
    p2 = np.array(p2, dtype=float)
    d1 = np.array([np.cos(np.radians(dir1_deg)), np.sin(np.radians(dir1_deg))])
    d2 = np.array([np.cos(np.radians(dir2_deg)), np.sin(np.radians(dir2_deg))])
    A = np.array([d1, -d2]).T
    b = p2 - p1
    t, _ = np.linalg.solve(A, b)
    return p1 + t * d1


def build_geometry(M_inf, ramp_angles_deg, capture_height=1.0, scale=1.0, gamma=1.4):
    """Construct shock-on-lip 2D inlet geometry from given incremental ramp angles.

    Reuses oblique_shock.beta_from_theta/oblique_shock_state for the shock
    angles and the advancing Mach at each ramp; no shock-relation formulas are
    re-derived here.

    Raises:
        ValueError: if the resulting ramp corners are not strictly increasing
            in x (infeasible/self-intersecting design).
    """
    n_ramps = len(ramp_angles_deg)

    phis = [0.0]
    betas = []
    M = M_inf
    for theta_deg in ramp_angles_deg:
        beta_deg = obl.beta_from_theta(M, theta_deg, gamma)
        betas.append(beta_deg)
        state = obl.oblique_shock_state(M, theta_deg, gamma, weak=True)
        M = state["M2"]
        phis.append(phis[-1] + theta_deg)

    if n_ramps == 0:
        lip = (0.0, capture_height)
        corners = [(0.0, 0.0), (0.0, 0.0)]
        shocks = [(corners[1], lip)]
    else:
        lip = (capture_height / np.tan(np.radians(betas[0])), capture_height)

        corners = [np.array([0.0, 0.0])]
        for i in range(1, n_ramps):
            shock_dir = phis[i] + betas[i]
            corner = _line_intersect(corners[i - 1], phis[i], lip, shock_dir)
            corners.append(corner)

        phi_n = phis[n_ramps]
        normal_shock_dir = phi_n + 90.0
        terminal_foot = _line_intersect(corners[n_ramps - 1], phi_n, lip, normal_shock_dir)
        corners.append(terminal_foot)

        corners = [tuple(c) for c in corners]
        shocks = [(corners[i], lip) for i in range(n_ramps)]
        shocks.append((corners[n_ramps], lip))

    if n_ramps > 0:
        xs = [p[0] for p in corners]
        if any(xs[i + 1] <= xs[i] for i in range(len(xs) - 1)):
            raise ValueError(
                f"ramp corners are not strictly increasing in x ({xs}): infeasible design"
            )

    throat_height = float(np.hypot(lip[0] - corners[-1][0], lip[1] - corners[-1][1]))
    cowl_angle_deg = phis[-1]

    ramp_points = [(p[0] * scale, p[1] * scale) for p in corners]
    lip_scaled = (lip[0] * scale, lip[1] * scale)
    shocks_scaled = [
        ((a[0] * scale, a[1] * scale), (b[0] * scale, b[1] * scale)) for a, b in shocks
    ]

    return InletGeometry(
        ramp_points=ramp_points,
        lip=lip_scaled,
        shocks=shocks_scaled,
        capture_height=capture_height * scale,
        throat_height=throat_height * scale,
        cowl_angle_deg=cowl_angle_deg,
        ramp_angles_deg=list(ramp_angles_deg),
        betas_deg=betas,
        M_inf=M_inf,
        scale=scale,
    )


def design_inlet(M_inf, n_ramps, capture_height=1.0, scale=1.0, gamma=1.4, max_cowl_deg=None):
    """Runs optimize_equal_strength (optionally cowl-angle limited) then build_geometry.

    The returned geometry carries `constrained` (True when the cowl limit was active).
    """
    from . import optimize as opt

    result = opt.optimize_equal_strength(M_inf, n_ramps, gamma, max_turn_deg=max_cowl_deg)
    geom = build_geometry(M_inf, result["ramps"], capture_height, scale, gamma)
    geom.constrained = result["constrained"]
    return geom


COWL_MARGIN_WARN_DEG = 2.0


def cowl_check(M, turn_deg, gamma=1.4, where="M∞"):
    """External cowl attachment: margin = theta_max(M) - turn (deg).

    The cowl turns the flow arriving at the lip (Mach M) by turn_deg; past theta_max the
    external cowl shock detaches. At the design point M is M_inf and the turn is the cowl
    angle; off design `where` names the local Mach ("local M"). Returns
    (theta_max, margin, level, message), level is "error" (margin < 0),
    "warn" (0 <= margin < COWL_MARGIN_WARN_DEG) or None.
    """
    theta_max, _ = obl.max_deflection(M, gamma)
    margin = theta_max - turn_deg
    if margin < 0.0:
        return theta_max, margin, "error", (
            f"External cowl shock detached (cowl turns {turn_deg:.2f}°, "
            f"θmax = {theta_max:.2f}° at {where} = {M:.2f}): bow shock, "
            "spillage and cowl drag not modelled"
        )
    if margin < COWL_MARGIN_WARN_DEG:
        return theta_max, margin, "warn", f"Cowl near shock detachment (margin {margin:.2f}°)"
    return theta_max, margin, None, None


COWL_LIP_PREFIX = "Cowl lip shock"


def cowl_lip_message(margin, level):
    """Above design Mach the lip sees freestream on both faces: a strong lip shock interacts
    with the ramp shocks (Mach reflection, seen in the validation CFD at M 3.25)."""
    state = "detached" if level == "error" else "near detachment"
    return (f"{COWL_LIP_PREFIX} {state} (θmax − turn = {margin:.2f}°): Mach reflection at "
            "the lip likely; recovery below the ideal value")
