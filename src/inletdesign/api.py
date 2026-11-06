"""Stable facade over the inletdesign core for applications (GUI, future web).

Every result is a frozen dataclass of plain Python floats, ints, strings and
tuples (no numpy types), so `to_dict()` output is JSON-serialisable. Invalid
input raises ValueError with a message meant to be shown to a user.

Conventions: SI units, angles in degrees, ramp angles incremental (as in
inlet.compress), flow angles cumulative from the freestream direction.
"""
import dataclasses
import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from . import atmosphere as _atm
from . import inlet as _inlet
from . import isentropic as _isen
from . import oblique_shock as _obl
from . import offdesign as _off
from . import separation as _sep
from . import standards as _std
from .geometry import COWL_LIP_PREFIX, build_geometry, cowl_check, design_inlet
from .offdesign import _deprecated_m_duct

REAL_GAS_T0_LIMIT = 800.0  # K; above this, vibrational excitation makes constant gamma questionable
SUBSONIC_WARNING = _off.SUBSONIC_WARNING
METHODS = ("oswatitsch", "custom")
MAX_COWL_WEDGE_DEG = 30.0   # cowl lip outer wedge input range: 0 .. this (deg)


class _Serialisable:
    def to_dict(self):
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class Freestream(_Serialisable):
    M: float
    gamma: float
    mode: str            # "altitude" or "manual"
    altitude_m: float    # None in manual mode
    p: float             # Pa
    T: float             # K
    rho: float           # kg/m^3
    a: float             # m/s
    V: float             # m/s
    p0: float            # Pa
    T0: float            # K
    mu: float            # Pa s
    Re_per_m: float      # 1/m
    warnings: tuple
    R: float = None      # J/(kg K), specific gas constant used
    T0_T: float = None   # stagnation-to-static temperature ratio
    p0_p: float = None   # stagnation-to-static pressure ratio


@dataclass(frozen=True)
class RegionState(_Serialisable):
    name: str
    theta_deg: float     # cumulative flow angle
    beta_deg: float      # angle of the shock entering this region (None for freestream)
    M: float
    p_ratio: float       # p / p_inf
    T_ratio: float       # T / T_inf
    p0_ratio: float      # p0 / p0_inf


@dataclass(frozen=True)
class Notice(_Serialisable):
    level: str           # "info", "warn" or "error"
    text: str
    detail: str = None   # longer explanation (tooltip), or None


@dataclass(frozen=True)
class ShockState(_Serialisable):
    name: str
    kind: str            # "oblique" or "normal"
    beta_deg: float      # shock angle relative to the upstream flow
    theta_deg: float     # flow deflection across the shock
    M1: float            # upstream Mach number
    Mn1: float           # upstream shock-normal Mach number, M1 sin(beta)
    p2_p1: float         # static pressure ratio across the shock
    p0_ratio: float      # p02 / p01 across the shock
    p0_loss: float       # 1 - p02 / p01
    M2: float = None     # downstream Mach number
    Mn2: float = None    # downstream shock-normal Mach number, M2 sin(beta - theta)
    T2_T1: float = None  # static temperature ratio across the shock
    rho2_rho1: float = None  # density ratio across the shock


@dataclass(frozen=True)
class DesignInputs(_Serialisable):
    M: float
    n_ramps: int
    method: str
    ramp_angles_deg: tuple   # custom angles, or () for oswatitsch
    capture_height: float
    gamma: float
    max_cowl_angle_deg: float = None   # optional limit on the Oswatitsch optimum
    cowl_wedge_deg: float = 0.0        # cowl lip outer wedge; 0 = zero-thickness idealisation


@dataclass(frozen=True)
class DesignGeometry(_Serialisable):
    ramp_points: tuple       # ((x, y), ...) including the terminal-shock foot
    lip: tuple
    shocks: tuple            # ((start, end), ...); the last one is the terminal normal shock


@dataclass(frozen=True)
class DesignResult(_Serialisable):
    inputs: DesignInputs
    ramp_angles_deg: tuple
    flow_angles_deg: tuple   # cumulative, starting with 0 (freestream)
    betas_deg: tuple
    regions: tuple           # RegionState, freestream first
    recovery_oblique: float
    recovery_total: float
    M_pre_terminal: float    # behind the last ramp shock, ahead of the terminal normal shock
    M_post_terminal: float   # behind the terminal shock (= M_pre_terminal if no terminal shock)
    throat_height: float
    cowl_angle_deg: float
    mass_capture: float
    geometry: DesignGeometry
    warnings: tuple
    shock_states: tuple = ()  # ShockState per drawn shock: ramps, then the terminal one
    theta_max_freestream_deg: float = None
    cowl_margin_deg: float = None   # theta_max(M_inf) - cowl angle; < 0: cowl shock detached
    notices: tuple = ()             # Notice per warning (same order as warnings)
    constrained: bool = False       # True when the max cowl angle limit is active
    separation: tuple = ()          # separation.SeparationCheck per shock (approximate)
    separation_notices: tuple = ()  # Notice per flagged shock (not in `notices`)

    @property
    def M_duct(self):
        """Deprecated alias of M_post_terminal (its old meaning for a design)."""
        return _deprecated_m_duct(self.M_post_terminal, "M_post_terminal")


@dataclass(frozen=True)
class OffDesignResult(_Serialisable):
    M_inf: float
    regime: str
    dx_over_hc: tuple
    mass_capture_ratio: float
    recovery_oblique: float
    M_pre_terminal: float    # behind the last ramp shock, ahead of the terminal normal shock
    recovery_total: float
    warnings: tuple
    ramp_angles_deg: tuple = ()
    betas_deg: tuple = ()
    regions: tuple = ()             # RegionState at this Mach, freestream first
    shock_states: tuple = ()        # ShockState per shock (terminal last, if present)
    capture_streamline: tuple = ()  # ((x, y), ...) from the first crossed shock to the lip
    cowl_angle_deg: float = None
    theta_max_freestream_deg: float = None
    cowl_margin_deg: float = None   # local check at the lip; None: subsonic and aligned
    notices: tuple = ()
    cowl_lip_region: int = None     # region containing the cowl lip (0 = freestream)
    lip_mach: float = None
    lip_flow_angle_deg: float = None
    cowl_required_turn_deg: float = None   # max(0, cowl - lip flow angle) + lip wedge
    cowl_wedge_deg: float = 0.0
    M_post_terminal: float = None   # behind the terminal shock (= pre if no terminal shock)
    theta_max_lip_deg: float = None # theta_max at the lip Mach; None if the lip flow is subsonic
    separation: tuple = ()          # separation.SeparationCheck per shock (approximate)
    separation_notices: tuple = ()  # Notice per flagged shock (not in `notices`)

    @property
    def M_duct(self):
        """Deprecated alias of M_pre_terminal (its old meaning off design)."""
        return _deprecated_m_duct(self.M_pre_terminal, "M_pre_terminal")


@dataclass(frozen=True)
class Sweep(_Serialisable):
    machs: tuple
    points: tuple            # OffDesignResult, or None where a shock detached
    detachment_mach: float   # lowest M_inf with all ramp shocks attached


def _f(x):
    return None if x is None else float(x)


def _pt(p):
    return (float(p[0]), float(p[1]))


def _check_mach(M, minimum=1.0):
    if not isinstance(M, (int, float)) or not math.isfinite(M):
        raise ValueError("Mach number must be a finite number")
    if M <= minimum:
        raise ValueError(f"Mach number must be > {minimum:g} (got {M:g})")


def _check_gamma(gamma):
    if not math.isfinite(gamma) or gamma <= 1.0:
        raise ValueError(f"gamma must be > 1 (got {gamma:g})")


def freestream(M, altitude_m=None, p=None, T=None, gamma=1.4):
    """Dimensional freestream from Mach and either altitude (USSA-1976) or manual p, T.

    V = M a, a = sqrt(gamma R T), p0 = p (p0/p), T0 = T (T0/T), Re/m = rho V / mu (Sutherland).
    """
    _check_mach(M, minimum=0.0)
    _check_gamma(gamma)
    if altitude_m is not None and (p is not None or T is not None):
        raise ValueError("give either an altitude or a manual p and T, not both")
    if altitude_m is not None:
        mode = "altitude"
        p = float(_atm.pressure(altitude_m))
        T = float(_atm.temperature(altitude_m))
        altitude_m = float(altitude_m)
    else:
        if p is None or T is None:
            raise ValueError("give an altitude, or both a manual pressure and temperature")
        if not p > 0:
            raise ValueError(f"pressure must be > 0 Pa (got {p:g})")
        if not T > 0:
            raise ValueError(f"temperature must be > 0 K (got {T:g})")
        mode = "manual"
        p, T = float(p), float(T)

    R = _atm.R_AIR
    rho = p / (R * T)
    a = math.sqrt(gamma * R * T)
    V = M * a
    T0_T = float(_isen.stagnation_temperature_ratio(M, gamma))
    p0_p = float(_isen.stagnation_pressure_ratio(M, gamma))
    T0, p0 = T * T0_T, p * p0_p
    mu = float(_atm.dynamic_viscosity(T))

    warnings = []
    if T0 > REAL_GAS_T0_LIMIT:
        warnings.append(
            f"real-gas regime: T0 = {T0:.0f} K > {REAL_GAS_T0_LIMIT:.0f} K; "
            "vibrational excitation makes the ideal-gas (constant γ) model optimistic"
        )

    return Freestream(
        M=float(M), gamma=float(gamma), mode=mode, altitude_m=altitude_m, p=p, T=T,
        rho=rho, a=a, V=V, p0=p0, T0=T0, mu=mu, Re_per_m=rho * V / mu,
        warnings=tuple(warnings), R=float(R), T0_T=T0_T, p0_p=p0_p,
    )


def captured_mass_flow(fs, capture_height, mass_capture=1.0):
    """mdot' = rho V h_c (A0/Ac)  (kg/s per metre span)."""
    return fs.rho * fs.V * capture_height * mass_capture


def _positive(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be > 0 (got {value!r})")
    return float(value)


def capture_height_for_mass_flow(fs, mdot, width, mass_capture=1.0):
    """h_c = mdot / (rho V w (A0/Ac))  (m): the capture height that passes mdot (kg/s) through
    an inlet of width w (m). At the design point A0/Ac = 1 (shock on lip)."""
    mdot, width = _positive("required mass flow", mdot), _positive("inlet width", width)
    return mdot / (fs.rho * fs.V * width * _positive("mass capture", mass_capture))


def mass_flow_total(fs, capture_height, width, mass_capture=1.0):
    """mdot = rho V h_c w (A0/Ac)  (kg/s)."""
    return captured_mass_flow(fs, capture_height, mass_capture) * _positive("inlet width", width)


def demand_capture_ratio(fs, mdot, capture_height, width):
    """(A0/Ac)_demand = mdot / (rho V h_c w): the mass capture an engine demanding mdot (kg/s)
    needs at this freestream; above the inlet's A0/Ac the inlet falls short."""
    return _positive("required mass flow", mdot) / (
        fs.rho * fs.V * _positive("capture height", capture_height)
        * _positive("inlet width", width))


def mil_recovery(M):
    """MIL-E-5008B total-pressure recovery at M (see inletdesign.standards for the SOURCE)."""
    _check_mach(M, minimum=0.0)
    return float(_std.mil_e_5008b(M))


def max_deflection(M, gamma=1.4):
    """theta_max (deg) of an attached oblique shock at Mach M (detachment limit)."""
    _check_mach(M)
    _check_gamma(gamma)
    return float(_obl.max_deflection(M, gamma)[0])


def _separation(shocks):
    """SeparationChecks for the shocks, and a Notice per flagged one (approximate)."""
    checks = _sep.check_shocks(shocks)
    notices = []
    for c in checks:
        if not c.flagged:
            continue
        if c.kind == "normal":
            what = f"M₁ {c.M1:.2f} ≥ {c.threshold:g}"
            where = "the terminal normal shock"
        else:
            what = f"p₂/p₁ {c.value:.2f} ≥ {c.threshold:.2f}"
            where = c.shock
        notices.append(Notice(
            "warn", f"Shock-induced separation likely at {where} ({what}) — {_sep.WORDING}",
            f"Criterion: {c.criterion}. Source: {c.source}."
            + (f" Korkegi: {_sep.KORKEGI_SCOPE}." if c.kind == "oblique" else "")
            + " Empirical incipient-separation check for a turbulent boundary layer; it must "
            "be verified with a CFD solver."))
    return checks, tuple(notices)


def _validate_custom_angles(M, n_ramps, ramp_angles, gamma):
    angles = tuple(float(a) for a in ramp_angles)
    if len(angles) != n_ramps:
        raise ValueError(f"expected {n_ramps} ramp angles, got {len(angles)}")
    Mi = M
    for i, theta in enumerate(angles):
        if not math.isfinite(theta) or theta <= 0:
            raise ValueError(f"ramp {i + 1}: angle must be > 0° (got {theta:g}°)")
        theta_max, _ = _obl.max_deflection(Mi, gamma)
        if theta >= theta_max:
            raise ValueError(
                f"ramp {i + 1}: {theta:.2f}° exceeds the detachment limit "
                f"{float(theta_max):.2f}° at M = {Mi:.3f}"
            )
        Mi = _obl.oblique_shock_state(Mi, theta, gamma, weak=True)["M2"]
        if Mi <= 1.0 and i < n_ramps - 1:
            raise ValueError(
                f"flow is subsonic (M = {Mi:.3f}) behind ramp {i + 1}; "
                "no further ramp shocks are possible"
            )
    return angles


def _shock(name, kind, upstream, downstream, beta, theta):
    return ShockState(
        name=name, kind=kind, beta_deg=float(beta), theta_deg=float(theta),
        M1=upstream.M, Mn1=float(upstream.M * math.sin(math.radians(beta))),
        p2_p1=downstream.p_ratio / upstream.p_ratio,
        p0_ratio=downstream.p0_ratio / upstream.p0_ratio,
        p0_loss=1.0 - downstream.p0_ratio / upstream.p0_ratio,
        M2=float(downstream.M),
        Mn2=float(downstream.M * math.sin(math.radians(beta - theta))),
        T2_T1=downstream.T_ratio / upstream.T_ratio,
        rho2_rho1=(downstream.p_ratio / downstream.T_ratio) / (upstream.p_ratio / upstream.T_ratio),
    )


def _flow_states(M, angles, betas, flow, gamma):
    """Region states (freestream first) and shock states for the ramps + terminal normal shock.

    If the flow behind the last ramp is subsonic there is no terminal shock: the duct takes
    that state and recovery_total = recovery_oblique.
    Returns (regions, shocks, recovery_oblique, recovery_total, M_pre, M_post, subsonic).
    """
    ramp_states = _inlet.compress_ramps(M, list(angles), gamma)
    regions = [RegionState("freestream", 0.0, None, float(M), 1.0, 1.0, 1.0)]
    for i, st in enumerate(ramp_states):
        regions.append(
            RegionState(f"behind shock {i + 1}", float(flow[i + 1]), float(betas[i]),
                        float(st.M), float(st.p_ratio), float(st.T_ratio), float(st.p0_ratio))
        )
    shocks = [_shock(f"ramp shock {i + 1}", "oblique", regions[i], regions[i + 1],
                     betas[i], angles[i]) for i in range(len(angles))]
    recovery_oblique = float(ramp_states[-1].p0_ratio) if ramp_states else 1.0
    M_before_terminal = regions[-1].M

    subsonic = M_before_terminal < 1.0
    if subsonic:
        recovery_total, M_post = recovery_oblique, M_before_terminal
    else:
        terminal = _inlet.compress(M, list(angles), gamma)[-1]
        recovery_total = float(terminal.p0_ratio)
        M_post = float(terminal.M)
        regions.append(
            RegionState("duct (behind normal shock)", float(flow[-1]), 90.0, M_post,
                        float(terminal.p_ratio), float(terminal.T_ratio), recovery_total)
        )
        shocks.append(_shock("terminal normal shock", "normal", regions[-2], regions[-1],
                             90.0, 0.0))
    return (tuple(regions), tuple(shocks), recovery_oblique, recovery_total,
            float(M_before_terminal), float(M_post), subsonic)


@lru_cache(maxsize=256)
def _design_cached(M, n_ramps, capture_height, gamma, ramp_angles, max_cowl=None, wedge=0.0):
    if ramp_angles is None:
        method = "oswatitsch"
        geom = design_inlet(M, n_ramps, capture_height=capture_height, gamma=gamma,
                            max_cowl_deg=max_cowl)
    else:
        method = "custom"
        try:
            geom = build_geometry(M, list(ramp_angles), capture_height, gamma=gamma)
        except ValueError as exc:
            raise ValueError(f"infeasible ramp layout: {exc}") from exc

    angles = tuple(float(a) for a in geom.ramp_angles_deg)
    betas = tuple(float(b) for b in geom.betas_deg)
    flow = [0.0]
    for a in angles:
        flow.append(flow[-1] + a)

    regions, shocks, recovery_oblique, recovery_total, M_pre, M_post, subsonic = _flow_states(
        M, angles, betas, flow, gamma)
    notices = [Notice("warn", SUBSONIC_WARNING)] if subsonic else []
    # the lip's outer surface turns the freestream by the cowl angle plus the lip wedge
    theta_max_inf, cowl_margin, cowl_level, cowl_message = cowl_check(
        M, float(geom.cowl_angle_deg) + wedge, gamma)
    if cowl_message:
        notices.append(Notice(cowl_level, cowl_message))
    if ramp_angles is not None and max_cowl is not None:
        notices.append(Notice("info", "max cowl angle applies to the Oswatitsch optimum only; "
                                      "ignored for custom angles"))

    geometry = DesignGeometry(
        ramp_points=tuple(_pt(p) for p in geom.ramp_points),
        lip=_pt(geom.lip),
        shocks=tuple((_pt(a), _pt(b)) for a, b in geom.shocks),
    )
    separation, separation_notices = _separation(shocks)
    inputs = DesignInputs(
        M=float(M), n_ramps=int(n_ramps), method=method,
        ramp_angles_deg=() if ramp_angles is None else angles,
        capture_height=float(capture_height), gamma=float(gamma),
        max_cowl_angle_deg=None if max_cowl is None else float(max_cowl),
        cowl_wedge_deg=float(wedge),
    )
    return DesignResult(
        inputs=inputs, ramp_angles_deg=angles, flow_angles_deg=tuple(flow), betas_deg=betas,
        regions=tuple(regions), recovery_oblique=recovery_oblique,
        recovery_total=recovery_total, M_pre_terminal=M_pre, M_post_terminal=M_post,
        throat_height=float(geom.throat_height), cowl_angle_deg=float(geom.cowl_angle_deg),
        mass_capture=1.0, geometry=geometry, warnings=tuple(n.text for n in notices),
        shock_states=shocks, theta_max_freestream_deg=float(theta_max_inf),
        cowl_margin_deg=float(cowl_margin), notices=tuple(notices),
        constrained=bool(getattr(geom, "constrained", False)),
        separation=separation, separation_notices=separation_notices,
    )


def design(M, n_ramps, capture_height=0.1, gamma=1.4, ramp_angles=None, max_cowl_angle=None,
           cowl_wedge=0.0):
    """Shock-on-lip design at Mach M.

    ramp_angles=None uses the Oswatitsch equal-strength optimum, optionally limited to
    a total turning (cowl angle) <= max_cowl_angle deg; otherwise the given incremental
    ramp angles (one per ramp) are checked against detachment and used directly.
    cowl_wedge (deg, 0-30) is the cowl lip's outer wedge angle, added to the turn the cowl
    imposes; 0 is the zero-thickness idealisation. The result reports the external-cowl
    detachment margin. Results are cached.
    """
    _check_mach(M)
    _check_gamma(gamma)
    if not isinstance(n_ramps, int) or not 0 <= n_ramps <= 4:
        raise ValueError(f"number of ramps must be an integer 0-4 (got {n_ramps!r})")
    if not math.isfinite(capture_height) or capture_height <= 0:
        raise ValueError(f"capture height must be > 0 (got {capture_height:g})")
    angles = None
    if ramp_angles is not None:
        angles = _validate_custom_angles(M, n_ramps, ramp_angles, gamma)
    if max_cowl_angle is not None:
        if not math.isfinite(max_cowl_angle) or max_cowl_angle <= 0:
            raise ValueError(f"max cowl angle must be > 0° (got {max_cowl_angle:g}°)")
        max_cowl_angle = round(float(max_cowl_angle), 10)
    if not isinstance(cowl_wedge, (int, float)) or not math.isfinite(cowl_wedge) \
            or not 0.0 <= cowl_wedge <= MAX_COWL_WEDGE_DEG:
        raise ValueError(
            f"cowl lip wedge must be 0-{MAX_COWL_WEDGE_DEG:g}° (got {cowl_wedge!r})")
    # Round the cache key so float noise from sliders/unit conversions reuses entries.
    return _design_cached(round(float(M), 10), n_ramps, round(float(capture_height), 12),
                          round(float(gamma), 10), angles, max_cowl_angle,
                          round(float(cowl_wedge), 10))


def _wedge(design_result):
    return design_result.inputs.cowl_wedge_deg or 0.0


def inlet_geometry(design_result):
    """The core InletGeometry of a design (for the DXF / CFD-domain exporters)."""
    return _geometry_of(design_result)


def _geometry_of(design_result):
    i = design_result.inputs
    return build_geometry(i.M, list(design_result.ramp_angles_deg), i.capture_height,
                          gamma=i.gamma)


CFD_LIP_NOTE = ("Observed in the validation CFD at M∞ 3.25: Mach reflection at the lip, "
                "recovery 4.9% below the ideal value.")


def _notice(text):
    """Level of a core warning text: cowl detachment is an error, the rest are warnings."""
    error = text.startswith(("External cowl shock detached", f"{COWL_LIP_PREFIX} detached"))
    detail = CFD_LIP_NOTE if text.startswith(COWL_LIP_PREFIX) else None
    return Notice("error" if error else "warn", text, detail)


def _convert_off(r, design_result):
    angles = tuple(float(a) for a in design_result.ramp_angles_deg)
    betas = tuple(float(b) for b in r.betas_deg)
    regions, shocks, *_ = _flow_states(float(r.M_inf), angles, betas,
                                       design_result.flow_angles_deg, design_result.inputs.gamma)
    separation, separation_notices = _separation(shocks)
    return OffDesignResult(
        M_inf=float(r.M_inf), regime=r.regime,
        dx_over_hc=tuple(float(d) for d in r.dx_over_hc),
        mass_capture_ratio=float(r.mass_capture_ratio),
        recovery_oblique=float(r.recovery_oblique), M_pre_terminal=float(r.M_pre_terminal),
        M_post_terminal=float(r.M_post_terminal), theta_max_lip_deg=_f(r.theta_max_lip_deg),
        recovery_total=float(r.recovery_total), warnings=tuple(r.warnings),
        ramp_angles_deg=angles, betas_deg=betas, regions=regions, shock_states=shocks,
        capture_streamline=tuple(_pt(p) for p in r.capture_streamline),
        cowl_angle_deg=float(r.cowl_angle_deg),
        theta_max_freestream_deg=float(r.theta_max_freestream_deg),
        cowl_margin_deg=_f(r.cowl_margin_deg),
        notices=tuple(_notice(w) for w in r.warnings),
        cowl_lip_region=int(r.cowl_lip_region), lip_mach=float(r.lip_mach),
        lip_flow_angle_deg=float(r.lip_flow_angle_deg),
        cowl_required_turn_deg=float(r.cowl_required_turn_deg),
        cowl_wedge_deg=float(r.cowl_wedge_deg),
        separation=separation, separation_notices=separation_notices,
    )


def off_design_point(design_result, M):
    """Evaluate the frozen design geometry at freestream Mach M.

    Raises ValueError (message contains "shock detached") if a ramp shock detaches.
    """
    _check_mach(M)
    return _convert_off(_off.off_design(_geometry_of(design_result), float(M),
                                        design_result.inputs.gamma, _wedge(design_result)),
                        design_result)


def _attached(design_result, M):
    gamma = design_result.inputs.gamma
    Mi = M
    for theta in design_result.ramp_angles_deg:
        if Mi <= 1.0:  # subsonic ahead of a further ramp: no attached shock possible
            return False
        theta_max, _ = _obl.max_deflection(Mi, gamma)
        if theta >= theta_max:
            return False
        Mi = _obl.oblique_shock_state(Mi, theta, gamma, weak=True)["M2"]
    return True  # subsonic behind the LAST ramp is allowed (no terminal shock)


def detachment_mach(design_result, tol=1e-5):
    """Lowest M_inf (to tol) at which every ramp shock of the design is attached (bisection)."""
    lo, hi = 1.0 + 1e-9, design_result.inputs.M
    if _attached(design_result, lo):
        return 1.0
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if _attached(design_result, mid):
            hi = mid
        else:
            lo = mid
    return float(hi)


def off_design_sweep(design_result, M_min, M_max, n):
    """Evaluate n equally spaced Mach numbers in [M_min, M_max]; None where detached.

    Raises ValueError for a 0-ramp design (no off-design model)."""
    _check_mach(M_min)
    if not M_max > M_min:
        raise ValueError("M_max must be greater than M_min")
    if not isinstance(n, int) or n < 2:
        raise ValueError("n must be an integer >= 2")
    geom = _geometry_of(design_result)
    gamma = design_result.inputs.gamma
    machs = tuple(float(m) for m in np.linspace(M_min, M_max, n))
    points = []
    for M in machs:
        try:
            points.append(_convert_off(_off.off_design(geom, M, gamma, _wedge(design_result)),
                                       design_result))
        except ValueError as exc:
            if "shock detached" not in str(exc):
                raise
            points.append(None)
    return Sweep(machs=machs, points=tuple(points), detachment_mach=detachment_mach(design_result))


def _redesign(design_result, angles):
    i = design_result.inputs
    return design(i.M, i.n_ramps, capture_height=i.capture_height, gamma=i.gamma,
                  ramp_angles=list(angles), cowl_wedge=i.cowl_wedge_deg)


def optimum_gap(design_result):
    """(gap %, optimum recovery): 100 (eta_opt - eta) / eta_opt against the Oswatitsch
    (equal-strength) design at the same Mach, ramps, gamma and capture height. Negative
    when the design beats it."""
    i = design_result.inputs
    opt = design(i.M, i.n_ramps, capture_height=i.capture_height, gamma=i.gamma,
                 cowl_wedge=i.cowl_wedge_deg)
    eta_opt = opt.recovery_total
    return 100.0 * (eta_opt - design_result.recovery_total) / eta_opt, eta_opt


RAMP_MIN_DEG = 0.5            # lower bound of a dragged ramp angle
RAMP_MAX_DEG = 30.0           # fixed upper bound
DETACH_MARGIN_DEG = 0.5       # stay this far below the detachment limit (every ramp)
MIN_THROAT_FRACTION = 0.05    # throat height >= this x capture height


@dataclass(frozen=True)
class AngleBounds(_Serialisable):
    lo: float                 # deg
    hi: float                 # deg
    reason: str               # what sets hi: "maximum" | "detachment" | "downstream"
    limit_deg: float          # the value behind `reason` (theta_max(M_k), 30, or hi)
    detail: str               # short user text, e.g. "detachment at 28.75°"


def _geometry_ok(d):
    pts, lip = d.geometry.ramp_points, d.geometry.lip
    xs = [p[0] for p in pts]
    return (all(b > a for a, b in zip(xs, xs[1:])) and all(p[1] < lip[1] for p in pts)
            and d.throat_height >= MIN_THROAT_FRACTION * d.inputs.capture_height)


def _angles_ok(design_result, k, theta):
    """The design stays valid with theta_k = theta: every ramp attached with the margin,
    supersonic flow ahead of every ramp, sane geometry."""
    angles = list(design_result.ramp_angles_deg)
    angles[k] = theta
    try:
        d = _redesign(design_result, angles)
    except ValueError:
        return False
    for j in range(k + 1, len(angles)):
        M_j = d.regions[j].M
        if M_j <= 1.0 or angles[j] > float(_obl.max_deflection(M_j, d.inputs.gamma)[0]) \
                - DETACH_MARGIN_DEG:
            return False
    return _geometry_ok(d)


def ramp_angle_bounds(design_result, k, tol=1e-3):
    """Bounds of ramp k's incremental angle (deg) for interactive editing, other angles fixed:
    lo = 0.5°; hi = min(theta_max(M_k) - 0.5°, 30°, the largest angle keeping the whole design
    valid: downstream ramps attached with 0.5° margin and supersonic flow ahead of each,
    corners in increasing x below the lip, throat >= 5 % h_c). M_k (ahead of ramp k) depends
    only on the upstream angles. Bisection for the downstream limit."""
    n = design_result.inputs.n_ramps
    if not 0 <= k < n:
        raise ValueError(f"ramp index must be 0-{n - 1} (got {k})")
    M_k = design_result.regions[k].M
    t_max = float(_obl.max_deflection(M_k, design_result.inputs.gamma)[0])
    hi, reason, limit = RAMP_MAX_DEG, "maximum", RAMP_MAX_DEG
    if t_max - DETACH_MARGIN_DEG < hi:
        hi, reason, limit = t_max - DETACH_MARGIN_DEG, "detachment", t_max
    lo = RAMP_MIN_DEG
    if not _angles_ok(design_result, k, hi):
        good, bad = lo, hi
        if not _angles_ok(design_result, k, good):
            good = design_result.ramp_angles_deg[k]          # current angle is valid
        while bad - good > tol:
            mid = 0.5 * (good + bad)
            good, bad = (mid, bad) if _angles_ok(design_result, k, mid) else (good, mid)
        hi, reason, limit = good, "downstream", good
    detail = {"maximum": f"{RAMP_MAX_DEG:g}° maximum",
              "detachment": f"detachment at {limit:.2f}°",
              "downstream": (f"ramp {k + 2} reaches its limit at {limit:.2f}°" if k + 1 < n
                             else f"throat closes at {limit:.2f}°")}[reason]
    return AngleBounds(lo=lo, hi=float(hi), reason=reason, limit_deg=float(limit), detail=detail)


def recovery_sensitivity(design_result, step_deg=0.01):
    """d(eta_total)/d(theta_k) per degree for each ramp, by central differences through
    design(..., ramp_angles=...):  (eta(theta_k + h) - eta(theta_k - h)) / 2h.
    One-sided where a side is infeasible (detachment, theta <= 0); None if both are."""
    if not math.isfinite(step_deg) or step_deg <= 0:
        raise ValueError(f"step must be > 0° (got {step_deg!r})")
    base = tuple(design_result.ramp_angles_deg)
    eta0 = design_result.recovery_total

    def eta(k, delta):
        angles = list(base)
        angles[k] += delta
        try:
            return _redesign(design_result, angles).recovery_total
        except ValueError:
            return None

    out = []
    for k in range(len(base)):
        up, down = eta(k, step_deg), eta(k, -step_deg)
        if up is not None and down is not None:
            out.append((up - down) / (2.0 * step_deg))
        elif up is not None:
            out.append((up - eta0) / step_deg)
        elif down is not None:
            out.append((eta0 - down) / step_deg)
        else:
            out.append(None)
    return tuple(out)


# --- trade study (M9a, Analytics tab; exact within the model) --------------------------------

TRADE_N_TURNING = (1, 2, 3, 4)
TRADE_N_MACH = (0, 1, 2, 3, 4)
TRADE_MACH_GRID = tuple(round(1.2 + 0.1 * k, 10) for k in range(59))    # 1.2 .. 7.0
TRADE_DELTA_MIN = 0.5      # deg: first point of a default turning grid
TRADE_DELTA_POINTS = 40


@dataclass(frozen=True)
class TurningCurve(_Serialisable):
    """Cowl-constrained Oswatitsch optimum vs total turning delta (= cowl angle) for n ramps.
    The last point is the unconstrained optimum (delta = cowl_opt_deg)."""
    n: int
    delta_deg: tuple
    recovery_total: tuple
    recovery_oblique: tuple
    ramps_deg: tuple         # per point: incremental ramp angles
    constrained: tuple       # per point: True where the cowl limit is active
    cowl_opt_deg: float      # unconstrained optimum's cowl angle


@dataclass(frozen=True)
class IsentropicCurve(_Serialisable):
    """Isentropic compression by delta: nu(M_f) = nu(M) - delta, then a normal shock at M_f.
    Ends at M_f = 1 (delta = nu(M))."""
    delta_deg: tuple
    M_f: tuple
    recovery: tuple


@dataclass(frozen=True)
class MachCurve(_Serialisable):
    """Unconstrained Oswatitsch optimum vs design Mach for n ramps (n = 0: normal shock)."""
    n: int
    M: tuple
    recovery_total: tuple
    cowl_deg: tuple
    ramps_deg: tuple


@dataclass(frozen=True)
class MachTrade(_Serialisable):
    curves: tuple            # MachCurve per n
    M: tuple                 # the design-Mach grid
    theta_max_deg: tuple     # theta_max(M) over the grid (cowl-shock detachment)


def _check_n_list(n_list, allowed):
    n_list = tuple(n_list)
    if not n_list or any(not isinstance(n, int) or n not in allowed for n in n_list):
        raise ValueError(f"ramp counts must be integers in {allowed} (got {n_list!r})")
    return n_list


def _check_grid(grid, name, minimum=None):
    try:
        grid = tuple(float(x) for x in grid)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a sequence of numbers") from exc
    if not grid or any(not math.isfinite(x) for x in grid):
        raise ValueError(f"{name} must be a non-empty sequence of finite numbers")
    if any(b <= a for a, b in zip(grid, grid[1:])):
        raise ValueError(f"{name} must be increasing")
    if minimum is not None and grid[0] < minimum:
        raise ValueError(f"{name} values must be ≥ {minimum:g} (got {grid[0]:g})")
    return tuple(round(x, 10) for x in grid)


def _unconstrained(M, n, gamma):
    from . import optimize as _opt

    return _opt.optimize_equal_strength(M, n, gamma)


@lru_cache(maxsize=64)
def _turning_curve(M, gamma, n, delta_grid):
    from . import optimize as _opt

    opt = _unconstrained(M, n, gamma)
    cowl = float(sum(opt["ramps"]))
    if delta_grid is None:
        grid = tuple(float(d) for d in np.linspace(TRADE_DELTA_MIN, cowl, TRADE_DELTA_POINTS))
    else:
        grid = tuple(d for d in delta_grid if 0.0 < d < cowl) + (cowl,)
    deltas, total, oblique, ramps, constrained = [], [], [], [], []
    for k, d in enumerate(grid):
        last = k == len(grid) - 1
        r = opt if last else _opt.constrained_optimum(M, n, gamma, d, opt)
        states = r["states"]
        deltas.append(cowl if last else float(sum(r["ramps"])))
        total.append(float(states[-1].p0_ratio))
        oblique.append(float(states[-2].p0_ratio))
        ramps.append(tuple(float(a) for a in r["ramps"]))
        constrained.append(not last and bool(r.get("constrained")))
    return TurningCurve(n=n, delta_deg=tuple(deltas), recovery_total=tuple(total),
                        recovery_oblique=tuple(oblique), ramps_deg=tuple(ramps),
                        constrained=tuple(constrained), cowl_opt_deg=cowl)


def trade_vs_turning(M, gamma=1.4, n_list=TRADE_N_TURNING, delta_grid=None):
    """Recovery vs total turning delta (deg) at design Mach M, for each n in n_list: the
    cowl-constrained Oswatitsch optimum at each delta, from a small delta up to n's
    unconstrained cowl angle (inclusive). delta_grid=None uses 40 points from 0.5 deg.
    Returns a tuple of TurningCurve (one per n, cached per n)."""
    _check_mach(M)
    _check_gamma(gamma)
    n_list = _check_n_list(n_list, TRADE_N_TURNING)
    grid = None if delta_grid is None else _check_grid(delta_grid, "turning grid", 0.0)
    M, gamma = round(float(M), 10), round(float(gamma), 10)
    return tuple(_turning_curve(M, gamma, n, grid) for n in n_list)


@lru_cache(maxsize=64)
def _isentropic_cached(M, gamma, delta_grid):
    from . import normal_shock as _ns
    from . import prandtl_meyer as _pm

    nu_inf = float(_pm.nu(M, gamma))
    if delta_grid is None:
        delta_grid = tuple(float(d) for d in np.linspace(0.0, nu_inf, 81))
    deltas, machs, rec = [], [], []
    for d in delta_grid:
        if d > nu_inf:
            break                                     # M_f < 1: the curve stops at sonic
        nu_f = max(nu_inf - d, 0.0)
        Mf = 1.0 if nu_f == 0.0 else _pm.mach_from_nu(nu_f, gamma)
        deltas.append(float(d))
        machs.append(float(Mf))
        rec.append(float(_ns.stagnation_pressure_ratio(Mf, gamma)))
    return IsentropicCurve(delta_deg=tuple(deltas), M_f=tuple(machs), recovery=tuple(rec))


def isentropic_vs_turning(M, gamma=1.4, delta_grid=None):
    """Isentropic-compression limit vs turning delta (deg): nu(M_f) = nu(M) - delta
    (Prandtl-Meyer), recovery = normal-shock p0 ratio at M_f. Valid for M_f >= 1 only, so the
    curve stops at delta = nu(M). delta_grid=None uses 81 points from 0 to nu(M)."""
    _check_mach(M)
    _check_gamma(gamma)
    grid = None if delta_grid is None else _check_grid(delta_grid, "turning grid", 0.0)
    return _isentropic_cached(round(float(M), 10), round(float(gamma), 10), grid)


@lru_cache(maxsize=32)
def _mach_curve(M_grid, gamma, n):
    from . import optimize as _opt

    rec, cowl, ramps = [], [], []
    found = []                       # optimal Mn so far: warm start, linearly extrapolated
    for M in M_grid:
        if n == 0:
            r = _opt.optimize_equal_strength(M, 0, gamma)
        elif not found:
            r = _unconstrained(M, n, gamma)
        else:
            guess = found[-1] if len(found) < 2 else 2.0 * found[-1] - found[-2]
            r = _opt.optimum_near(M, n, gamma, guess)
        if n:
            found.append(r["Mn"])
        rec.append(float(r["states"][-1].p0_ratio))
        cowl.append(float(sum(r["ramps"])))
        ramps.append(tuple(float(a) for a in r["ramps"]))
    return MachCurve(n=n, M=M_grid, recovery_total=tuple(rec), cowl_deg=tuple(cowl),
                     ramps_deg=tuple(ramps))


@lru_cache(maxsize=16)
def _theta_max_curve(M_grid, gamma):
    return tuple(float(_obl.max_deflection(M, gamma)[0]) for M in M_grid)


def trade_vs_design_mach(M_grid=TRADE_MACH_GRID, gamma=1.4, n_list=TRADE_N_MACH):
    """Unconstrained Oswatitsch recovery and cowl angle vs design Mach for each n in n_list
    (n = 0: a normal shock only), plus theta_max(M) over the grid. Cached per n."""
    _check_gamma(gamma)
    n_list = _check_n_list(n_list, TRADE_N_MACH)
    grid = _check_grid(M_grid, "design-Mach grid")
    if grid[0] <= 1.0:
        raise ValueError(f"design Mach values must be > 1 (got {grid[0]:g})")
    gamma = round(float(gamma), 10)
    return MachTrade(curves=tuple(_mach_curve(grid, gamma, n) for n in n_list), M=grid,
                     theta_max_deg=_theta_max_curve(grid, gamma))
