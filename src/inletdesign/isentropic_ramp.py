"""Isentropic ramp (M11, addendum G): a centred Prandtl-Meyer compression fan whose straight
characteristics all pass through the cowl lip, turning the flow from M_inf to M_f. The fan is
isentropic; the only loss is the terminal normal shock at M_f, so
recovery = p0y/p0x(M_f) = normal_shock.stagnation_pressure_ratio(M_f).

Geometry. Freestream along +x, the leading edge at the origin, flow turning toward +y (same
convention as geometry.build_geometry). At turning angle theta (0 <= theta <= delta, measured
from the freestream direction) the local Mach M(theta) satisfies
nu(M(theta)) = nu(M_inf) - theta                                   (NACA 1135 eq. (171), p. 626)
and the local Mach angle is mu(theta) = arcsin(1/M(theta)). The characteristic at theta is the
straight line through the lip at angle theta + mu(theta) from the freestream (a right-running
Mach line, same ray convention as geometry.py's shock rays from the lip). The lip itself sits
at height h_c above the leading edge, at lip = (h_c / tan(mu(M_inf)), h_c) -- the Mach wave
through the lip at theta = 0, matching geometry.build_geometry's n = 0 case.

Wall relation. The wall is the streamline leaving the leading edge. Across any straight
characteristic the velocity component normal to it equals the local speed of sound
(V sin(mu) = a, the defining property of a Mach line), so one-dimensional continuity along the
stream tube bounded by the wall and the lip-focus point,
rho V A = rho* a* A*                                                 (NACA 1135 eq. (79), p. 618)
applied with A = r (the lip-to-wall distance, since the stream-tube "area" per unit span at
radius r from the focus is just r) and V sin(mu) = a, gives rho a r = const along the wall:
    r / r_inf = [rho(M_inf) a(M_inf)] / [rho(M) a(M)]
             = [(1 + (gamma-1)/2 M^2) / (1 + (gamma-1)/2 M_inf^2)] ** ((gamma+1)/(2(gamma-1)))
    r_inf = h_c / sin(mu(M_inf))
    wall_point(theta) = lip - r(theta) * (cos(theta + mu), sin(theta + mu))
This is the primary, closed-form construction (_wall_point below). An independent cross-check
exists in tests/test_isentropic_ramp.py: integrating the wall as an exact ODE in theta (the
streamline tangent condition alone, with no continuity relation assumed) agrees with this
closed form to 1e-10, confirming eq. (79) was applied correctly.

Field. p/p_inf along a characteristic (constant there, in a simple wave) follows from constant
stagnation pressure through the isentropic fan: p/p_inf = (p0/p)(M_inf) / (p0/p)(M).

Recovery. eta = p0y/p0x(M_f): the fan itself is isentropic (p0 constant through it), so the
only stagnation-pressure loss is the terminal normal shock at M_f.

Validity: M_f >= 1 is required (ValueError otherwise). Below MIN_RECOMMENDED_MF = 1.2 the
result is still returned (not raised) but carries a warning: the terminal shock is very weak
and the design is sensitive (mirrors characteristic.py's MOECKEL_MIN_MACH convention -- a
constant plus a note on the result, not a hard failure). Above the lip, in reality the
characteristics converge and coalesce into a shock; this is not modelled here.
"""
import math
from dataclasses import dataclass, field

import numpy as np

from . import isentropic as iso
from . import normal_shock as ns
from . import prandtl_meyer as pm
from . import standards
from .geometry import cowl_check

MIN_RECOMMENDED_MF = 1.2
LOW_MF_WARNING = "terminal shock very weak, design sensitive"
N_WALL_POINTS = 200


def _validate_inputs(M_inf, gamma, capture_height):
    if not math.isfinite(M_inf) or M_inf <= 1.0:
        raise ValueError(f"M_inf must be > 1 (got {M_inf:g})")
    if not math.isfinite(gamma) or gamma <= 1.0:
        raise ValueError(f"gamma must be > 1 (got {gamma:g})")
    if not math.isfinite(capture_height) or capture_height <= 0.0:
        raise ValueError(f"capture_height must be > 0 (got {capture_height:g})")


@dataclass(frozen=True)
class Characteristic:
    """One characteristic of the fan: direction theta (deg, from freestream), local Mach, and
    p/p_inf (constant along this characteristic in a simple wave)."""
    theta_deg: float
    M: float
    p_over_pinf: float


@dataclass(frozen=True)
class IsentropicRamp:
    """An isentropic-ramp fan from M_inf to M_f, turning delta_deg, at capture height h_c."""
    M_inf: float
    gamma: float
    capture_height: float
    delta_deg: float
    M_f: float
    lip: tuple                       # (x, y)
    wall_points: tuple                # ((x, y), ...), leading edge first, lip-row last
    characteristics: tuple           # Characteristic, one per wall point after the first
    recovery: float                  # p0y / p0x(M_f): the terminal normal shock only
    engine_face_recovery: float      # MIL-E-5008B at M_inf, for comparison
    multi_ramp_recovery: dict = field(default_factory=dict)   # n -> recovery at the same delta
    cowl_margin: float = None
    theta_max_deg: float = None
    valid: bool = True
    warning: str = None

    @property
    def wall_length(self):
        pts = np.asarray(self.wall_points)
        return float(np.sum(np.hypot(*np.diff(pts, axis=0).T)))

    @property
    def lip_to_wall_end(self):
        """Distance from the lip to the last wall point (the fan's throat radius)."""
        lx, ly = self.lip
        wx, wy = self.wall_points[-1]
        return float(math.hypot(lx - wx, ly - wy))


def _r_over_rinf(M, M_inf, gamma):
    """r/r_inf = [rho(M_inf) a(M_inf)] / [rho(M) a(M)], from rho*a*r = const along the wall
    (NACA 1135 eq. (79), one-dimensional continuity, applied with A = r, V sin(mu) = a)."""
    num = 1.0 + 0.5 * (gamma - 1.0) * M * M
    den = 1.0 + 0.5 * (gamma - 1.0) * M_inf * M_inf
    return (num / den) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))


def _wall_point(theta_deg, M, lip, r_inf, M_inf, gamma):
    r = r_inf * _r_over_rinf(M, M_inf, gamma)
    mu = math.asin(1.0 / M)
    ang = math.radians(theta_deg) + mu
    return (lip[0] - r * math.cos(ang), lip[1] - r * math.sin(ang))


def _build_wall(M_inf, gamma, capture_height, delta_deg):
    mu_inf = math.asin(1.0 / M_inf)
    lip = (capture_height / math.tan(mu_inf), capture_height)
    r_inf = capture_height / math.sin(mu_inf)
    nu_inf = pm.nu(M_inf, gamma)

    thetas_deg = np.linspace(0.0, delta_deg, N_WALL_POINTS) if delta_deg > 0.0 else \
        np.zeros(N_WALL_POINTS)
    wall = []
    for theta_deg in thetas_deg:
        if theta_deg <= 0.0:
            M = M_inf
        else:
            nu_th = nu_inf - theta_deg
            M = 1.0 if nu_th <= 1e-12 else pm.mach_from_nu(nu_th, gamma)
        wall.append(_wall_point(theta_deg, M, lip, r_inf, M_inf, gamma))
    return lip, thetas_deg, wall


def isentropic_ramp(M_inf, gamma=1.4, capture_height=1.0, delta_deg=None, M_f=None,
                    n_list=(1, 2, 3, 4)):
    """Build an isentropic-ramp fan. Give exactly one of delta_deg or M_f.

    Raises ValueError if both or neither are given, if the implied M_f < 1, or if the implied
    cowl turn (delta_deg) detaches the external cowl shock (geometry.cowl_check).
    """
    if (delta_deg is None) == (M_f is None):
        raise ValueError("give exactly one of delta_deg or M_f")
    _validate_inputs(M_inf, gamma, capture_height)

    nu_inf = pm.nu(M_inf, gamma)
    if delta_deg is None:
        if not math.isfinite(M_f) or M_f < 1.0:
            raise ValueError(f"M_f must be >= 1 (got {M_f:g})")
        nu_f = pm.nu(M_f, gamma)
        delta_deg = nu_inf - nu_f
        if delta_deg < 0.0:
            raise ValueError(f"M_f ({M_f:g}) must be <= M_inf ({M_inf:g})")
    else:
        if delta_deg < 0.0:
            raise ValueError(f"delta_deg must be >= 0 (got {delta_deg:g})")
        nu_f = nu_inf - delta_deg
        if nu_f < 0.0:
            raise ValueError(
                f"delta_deg ({delta_deg:g}) exceeds nu(M_inf) ({nu_inf:g}): "
                "would require M_f < 1")
        M_f = 1.0 if nu_f <= 1e-12 else pm.mach_from_nu(nu_f, gamma)

    theta_max, cowl_margin, level, message = cowl_check(M_inf, delta_deg, gamma)
    if level == "error":
        raise ValueError(message)

    valid, warning = True, None
    if M_f < MIN_RECOMMENDED_MF:
        valid, warning = False, LOW_MF_WARNING

    lip, thetas_deg, wall = _build_wall(M_inf, gamma, capture_height, delta_deg)

    p0_over_p_inf = iso.stagnation_pressure_ratio(M_inf, gamma)
    characteristics = []
    for theta_deg in thetas_deg[1:]:
        M_th = M_inf if theta_deg <= 0.0 else pm.mach_from_nu(nu_inf - theta_deg, gamma)
        p_over_pinf = p0_over_p_inf / iso.stagnation_pressure_ratio(M_th, gamma)
        characteristics.append(Characteristic(float(theta_deg), float(M_th),
                                              float(p_over_pinf)))

    recovery = float(ns.stagnation_pressure_ratio(M_f, gamma))
    engine_face_recovery = float(standards.mil_e_5008b(M_inf))

    from . import api as _api
    multi_ramp_recovery = {}
    for n in n_list:
        curve = _api.trade_vs_turning(M_inf, gamma, n_list=(n,), delta_grid=(delta_deg,))[0]
        if delta_deg >= curve.cowl_opt_deg:
            # delta_deg at or past n's own unconstrained optimum: the curve's cowl-limited
            # point is capped there, not at delta_deg -- use the unconstrained value directly.
            multi_ramp_recovery[n] = float(curve.recovery_total[-1])
        else:
            idx = min(range(len(curve.delta_deg)),
                      key=lambda i: abs(curve.delta_deg[i] - delta_deg))
            multi_ramp_recovery[n] = float(curve.recovery_total[idx])

    return IsentropicRamp(
        M_inf=float(M_inf), gamma=float(gamma), capture_height=float(capture_height),
        delta_deg=float(delta_deg), M_f=float(M_f), lip=lip, wall_points=tuple(wall),
        characteristics=tuple(characteristics), recovery=recovery,
        engine_face_recovery=engine_face_recovery, multi_ramp_recovery=multi_ramp_recovery,
        cowl_margin=float(cowl_margin), theta_max_deg=float(theta_max), valid=valid,
        warning=warning)
