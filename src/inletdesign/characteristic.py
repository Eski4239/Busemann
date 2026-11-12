"""Inlet characteristic (recovery vs mass-flow ratio) and buzz onset for a fixed design at one
freestream Mach number (M9c; model note docs/m9c_model.md). Per unit width, plane flow.

- Critical point: the existing result (terminal shock at the duct entry, region n).
- Supercritical branch (quasi-1D, exact): the terminal shock in a diverging subsonic diffuser
  of exit/entry area ratio AR; NACA Report 1135 eq. (80), p. 618 (A*/A, used as its
  reciprocal), eq. (44), p. 616 (p/p_t), eq. (99), p. 619 (p0y/p0x).
- Subcritical branch (quasi-1D, exact while the expelled shock stands in region n): recovery
  constant, MFR = MFR_crit (1 - tau) set by the exit Mach through the mass-flow function.
- Expelled-shock position (approximate): Moeckel, NACA TN 1921 (1949), eqs. (4), (6)/(6a),
  (14), (17), (30)-(36), pp. 7-19, applied to the flow behind the last ramp shock (Busemann
  extension). Rule: every Moeckel quantity referenced to the free stream uses the region-n
  state instead -- the Mach number M_n, the Mach-line asymptotes (Mach angle mu_n), and the
  sonic-line inclination eta = lambda_S(M_n) measured from the region-n flow direction
  theta_n. tau is Moeckel's "fraction of maximum possible inlet mass flow that passes outside
  cowl" (eq. 30, p. 18). Below the dividing streamline the shock is taken normal to theta_n
  (Moeckel: the analysis is independent of the shock below that origin, p. 18).
- Buzz onset (approximate): Ferri & Nucci, NACA RM L50K30 (1951), Summary p. 1, p. 7 and
  Concluding Remarks p. 25 -- buzz starts when the vortex sheet from the shock intersection
  enters the cowl. Tested on conical inlets at M 1.9-2.7; the 2D multi-ramp application is a
  Busemann extension.
- Validity (MOECKEL_MIN_MACH): TN 1921 p. 14, "The theoretical values obtained by the present
  method are not expected to be valid near M0 = 1.0, because the subsonic field becomes very
  large relative to the body (yS/ySB -> infinity) and small variations in the assumed form and
  inclination of the sonic line have a large effect on the computed drag." The report gives
  no number; the lowest two-dimensional Mach number at which it compares the method with
  experiment is M 1.2 (fig. 7, p. 29, reference 5, read from the figure). By the region-n
  rule the limit applies to M_n: below M_n = 1.2 the expelled shock, the subcritical branch
  and the buzz onset are not computed.

Angles in degrees at this API; inputs are api.DesignResult / api.OffDesignResult objects.
"""
import math
from dataclasses import dataclass

from scipy.optimize import brentq

from . import normal_shock as _ns
from . import oblique_shock as _obl

TESTED_MACH = (1.9, 2.7)          # Ferri & Nucci RM L50K30, p. 7 (finding 1)
ZERO_RANGE_TAU = 1e-6             # below this the stable subcritical range is "zero"
TAU_MAX = 0.5
MOECKEL_MIN_MACH = 1.2            # on M_n: TN 1921 p. 14 (why), fig. 7 p. 29 (the number)
OUTSIDE_VALIDITY_NOTE = ("outside the method's validity (flow behind the last ramp near "
                         "Mach 1, Moeckel TN 1921 p. 14)")


# --- quasi-1D relations ----------------------------------------------------------------------

def _validate(M, gamma, minimum=0.0):
    if not math.isfinite(M) or M <= minimum:
        raise ValueError(f"Mach number must be > {minimum:g} (got {M!r})")
    if not math.isfinite(gamma) or gamma <= 1.0:
        raise ValueError(f"gamma must be > 1 (got {gamma!r})")


def astar_over_a(M, gamma=1.4):
    """A*/A = M [ (2/(g+1)) (1 + (g-1)/2 M^2) ]^(-(g+1)/(2(g-1)))  (NACA 1135 eq. 80, p. 618)."""
    _validate(M, gamma)
    return M * ((2.0 / (gamma + 1.0)) * (1.0 + 0.5 * (gamma - 1.0) * M * M)) ** (
        -(gamma + 1.0) / (2.0 * (gamma - 1.0)))


def area_ratio(M, gamma=1.4):
    """A/A* = 1 / (A*/A), the reciprocal of NACA 1135 eq. (80)."""
    return 1.0 / astar_over_a(M, gamma)


def p_over_pt(M, gamma=1.4):
    """p/p_t = (1 + (g-1)/2 M^2)^(-g/(g-1))  (NACA 1135 eq. 44, p. 616)."""
    _validate(M, gamma, minimum=-1e-300)
    return (1.0 + 0.5 * (gamma - 1.0) * M * M) ** (-gamma / (gamma - 1.0))


def mass_flow_function(M, gamma=1.4):
    """mbar(M) = M (1 + (g-1)/2 M^2)^(-(g+1)/(2(g-1))): mdot = p0 A mbar sqrt(g/(R T0))."""
    _validate(M, gamma, minimum=-1e-300)
    return M * (1.0 + 0.5 * (gamma - 1.0) * M * M) ** (-(gamma + 1.0) / (2.0 * (gamma - 1.0)))


def mach_from_area_ratio(ratio, gamma=1.4, supersonic=True):
    """Mach number with A/A* = ratio (>= 1), on the supersonic or subsonic branch."""
    if not math.isfinite(ratio) or ratio < 1.0:
        raise ValueError(f"A/A* must be >= 1 (got {ratio!r})")
    if ratio == 1.0:
        return 1.0
    f = lambda M: area_ratio(M, gamma) - ratio            # noqa: E731
    if supersonic:
        hi = 2.0
        while f(hi) < 0.0:
            hi *= 2.0
        return float(brentq(f, 1.0, hi, xtol=1e-14))
    return float(brentq(f, 1e-12, 1.0, xtol=1e-14))


def mach_from_mass_flow(mbar, gamma=1.4):
    """Subsonic Mach with mass_flow_function(M) = mbar (0 < mbar <= mbar(1))."""
    top = mass_flow_function(1.0, gamma)
    if not 0.0 < mbar <= top * (1.0 + 1e-12):
        raise ValueError(f"mass-flow function must be in (0, {top:.6g}] (got {mbar!r})")
    if mbar >= top:
        return 1.0
    return float(brentq(lambda M: mass_flow_function(M, gamma) - mbar, 0.0, 1.0, xtol=1e-14))


# --- results ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class CharPoint:
    mfr: float               # mass-flow ratio A0/Ac
    recovery: float          # total-pressure recovery p0/p0_inf
    p_exit: float            # exit static pressure p_x / p0_inf (the throttle)
    M_exit: float            # subsonic diffuser exit Mach
    M_shock: float = None    # supercritical: Mach ahead of the terminal shock
    area_shock: float = None  # supercritical: A_s / A_e
    tau: float = None        # subcritical: spilled fraction (Moeckel's tau)


@dataclass(frozen=True)
class MoeckelShock:
    tau: float
    M_n: float
    theta_n_deg: float
    beta: float              # sqrt(M_n^2 - 1)
    phi_S_deg: float         # shock angle with sonic flow behind (relative to theta_n)
    lambda_S_deg: float      # flow inclination behind the shock at S (= eta, plane flow)
    phi_c_deg: float         # shock angle at the mass-centroid streamline
    B: float                 # A_s / A_0, eq. (14)/(34)
    y_SB: float              # lip distance from the last ramp segment (normal to theta_n)
    y_m: float
    y_S: float
    x0: float
    x_S: float
    x_SB: float
    L: float                 # vertex-to-lip distance along theta_n (eq. 10)
    lip: tuple               # world (x, y)

    def world(self, x, y):
        """Local (x along theta_n from the asymptote intersection, y from the ramp line) ->
        world (x, y)."""
        t = math.radians(self.theta_n_deg)
        ex, ey = (math.cos(t), math.sin(t)), (-math.sin(t), math.cos(t))
        dx, dy = x - self.x_SB, y - self.y_SB
        return (self.lip[0] + dx * ex[0] + dy * ey[0], self.lip[1] + dx * ex[1] + dy * ey[1])

    def hyperbola_x(self, Y):
        """eq. (31): beta (y - y_m) = sqrt(x^2 - x0^2), Y = y - y_m >= 0."""
        return math.sqrt(self.x0 * self.x0 + self.beta * self.beta * Y * Y)

    def hyperbola_slope(self, Y):
        """eq. (5): tan(phi) = sqrt(x0^2 + beta^2 Y^2) / (beta^2 Y); phi in degrees."""
        if Y <= 0.0:
            return 90.0
        return math.degrees(math.atan(math.sqrt(self.x0 ** 2 + self.beta ** 2 * Y * Y)
                                      / (self.beta ** 2 * Y)))

    def vertex(self):
        return self.world(self.x0, self.y_m)

    def polyline(self, n=40, extend=1.0):
        """World points: the normal part (ramp line to the dividing streamline), then the
        hyperbola up to the sonic point (and `extend` x Y_S beyond it)."""
        pts = [self.world(self.x0, 0.0), self.world(self.x0, self.y_m)]
        top = (self.y_S - self.y_m) * (1.0 + extend)
        pts += [self.world(self.hyperbola_x(top * k / n), self.y_m + top * k / n)
                for k in range(1, n + 1)]
        return pts


@dataclass(frozen=True)
class BuzzOnset:
    tau: float               # spilled fraction at onset (0: no stable subcritical range)
    mfr: float               # MFR_crit (1 - tau)
    method: str              # "exact" (triple point) or "fallback" (sheet along theta_n)
    triple_point: tuple      # world (x, y) of T at onset, or None
    theta_slip_deg: float    # vortex-sheet direction at onset
    zero_range: bool
    extrapolated: bool       # M_inf outside the tested range M 1.9-2.7
    exact_used: bool         # the exact triple point existed at the onset tau


@dataclass(frozen=True)
class Characteristic:
    M_inf: float
    area_ratio: float
    critical: CharPoint
    supercritical: tuple     # CharPoint, critical first
    subcritical: tuple       # CharPoint, critical first (empty above the design Mach)
    buzz: BuzzOnset          # exact method (point-wise fallback), None if not modelled
    buzz_fallback: BuzzOnset
    note: str = None         # why a part is missing
    valid: bool = True       # False: M_n below MOECKEL_MIN_MACH (no subcritical model)
    M_n: float = None        # Mach number behind the last ramp shock


# --- critical / supercritical / subcritical ---------------------------------------------------

def _states(off):
    n = len(off.ramp_angles_deg)
    if n == 0:
        raise ValueError("the inlet characteristic needs a design with ramps")
    return n, off.regions[: n + 1]


def _critical_exit(M_n, area_ratio_, gamma):
    """Exit Mach and A_x/A*_2 at the critical point (shock at the entry, Mach M_n)."""
    r = area_ratio_ * area_ratio(M_n, gamma) * float(_ns.stagnation_pressure_ratio(M_n, gamma))
    if r < 1.0:
        raise ValueError("the diffuser exit chokes at the critical point (A_x/A*_2 < 1)")
    return mach_from_area_ratio(r, gamma, supersonic=False), r


def critical_point(design, off, area_ratio_=2.0):
    gamma = design.inputs.gamma
    n, reg = _states(off)
    M_n = reg[n].M
    if M_n <= 1.0:
        raise ValueError("subsonic flow ahead of the terminal shock: no characteristic")
    M_x, _ = _critical_exit(M_n, area_ratio_, gamma)
    eta = off.recovery_total
    return CharPoint(mfr=float(off.mass_capture_ratio), recovery=float(eta),
                     p_exit=float(eta * p_over_pt(M_x, gamma)), M_exit=float(M_x),
                     M_shock=float(M_n), area_shock=1.0, tau=0.0)


def supercritical_branch(design, off, area_ratio_=2.0, n_points=30):
    """Shock at A_s/A_e from 1 (critical) to AR: M_s from A_s/A*_1 (supersonic root),
    eta = eta_obl p0y/p0x(M_s), A*_2 = A*_1 / p0y/p0x(M_s), M_x from A_x/A*_2 (subsonic),
    p_x/p0_inf = eta p/p_t(M_x). Ends early if the exit chokes."""
    _check_ar(area_ratio_)
    gamma = design.inputs.gamma
    n, reg = _states(off)
    M_n = reg[n].M
    eta_obl = off.recovery_oblique
    out = []
    for k in range(n_points):
        a_s = 1.0 + (area_ratio_ - 1.0) * k / max(n_points - 1, 1)
        M_s = M_n if k == 0 else mach_from_area_ratio(a_s * area_ratio(M_n, gamma), gamma)
        ps = float(_ns.stagnation_pressure_ratio(M_s, gamma))
        r = area_ratio_ * area_ratio(M_n, gamma) * ps
        if r < 1.0:
            break
        M_x = mach_from_area_ratio(r, gamma, supersonic=False)
        eta = eta_obl * ps
        out.append(CharPoint(mfr=float(off.mass_capture_ratio), recovery=float(eta),
                             p_exit=float(eta * p_over_pt(M_x, gamma)), M_exit=float(M_x),
                             M_shock=float(M_s), area_shock=float(a_s)))
    return tuple(out)


def subcritical_branch(design, off, area_ratio_=2.0, tau_max=TAU_MAX, n_points=40):
    """Expelled shock in region n: eta = eta_crit; MFR = MFR_crit (1 - tau); the exit Mach from
    mbar(M_x) = mbar(M_x,crit) (1 - tau); p_x/p0_inf = eta_crit p/p_t(M_x)."""
    _check_ar(area_ratio_)
    crit = critical_point(design, off, area_ratio_)
    gamma = design.inputs.gamma
    m_crit = mass_flow_function(crit.M_exit, gamma)
    out = []
    for k in range(n_points):
        tau = tau_max * k / max(n_points - 1, 1)
        M_x = crit.M_exit if k == 0 else mach_from_mass_flow(m_crit * (1.0 - tau), gamma)
        out.append(CharPoint(mfr=crit.mfr * (1.0 - tau), recovery=crit.recovery,
                             p_exit=float(crit.recovery * p_over_pt(M_x, gamma)),
                             M_exit=float(M_x), tau=float(tau)))
    return tuple(out)


def _check_ar(area_ratio_):
    if not isinstance(area_ratio_, (int, float)) or not math.isfinite(area_ratio_) \
            or not 1.0 <= area_ratio_ <= 4.0:
        raise ValueError(f"diffuser exit/entry area ratio must be 1-4 (got {area_ratio_!r})")


# --- Moeckel's expelled shock in region n ------------------------------------------------------

def _m2_behind(M, beta_deg, gamma):
    d = float(_obl.theta_from_beta(M, beta_deg, gamma))
    mn2 = float(_ns.mach_downstream(M * math.sin(math.radians(beta_deg)), gamma))
    return mn2 / math.sin(math.radians(beta_deg - d)), d


def sonic_shock_angle(M, gamma=1.4):
    """(phi_S, lambda_S): the shock angle with sonic flow behind an oblique shock at M, and
    the flow deflection there (TN 1921, p. 5: known from shock theory for a given M)."""
    _validate(M, gamma, minimum=1.0)
    mu = math.degrees(math.asin(1.0 / M))
    _, b_max = _obl.max_deflection(M, gamma)
    phi = brentq(lambda b: _m2_behind(M, b, gamma)[0] - 1.0, mu + 1e-9, float(b_max),
                 xtol=1e-13)
    return float(phi), float(_m2_behind(M, phi, gamma)[1])


def moeckel_shock(design, off, tau):
    """Moeckel's 2D-inlet detached shock (TN 1921 eqs. (4), (6)/(6a), (14), (17), (30)-(36))
    in the flow behind the last ramp shock (Busemann extension: M_n, mu_n, eta = lambda_S(M_n)
    from theta_n). tau: spilled fraction, 0 <= tau < 1."""
    if not math.isfinite(tau) or not 0.0 <= tau < 1.0:
        raise ValueError(f"spilled fraction tau must be in [0, 1) (got {tau!r})")
    gamma = design.inputs.gamma
    n, reg = _states(off)
    M_n, theta_n = reg[n].M, reg[n].theta_deg
    if M_n <= 1.0:
        raise ValueError("subsonic flow behind the last ramp shock: no detached-shock model")
    beta = math.sqrt(M_n * M_n - 1.0)
    phi_S, lam_S = sonic_shock_angle(M_n, gamma)
    t_s = math.tan(math.radians(phi_S))
    r = beta * math.sqrt(beta * beta * t_s * t_s - 1.0)          # x0 / (y_S - y_m), eq. (32)
    tan_c = math.sqrt(r * r + 0.25 * beta * beta) / (0.5 * beta * beta)   # eq. (5) at Y_S/2
    phi_c = math.degrees(math.atan(tan_c))
    p0c = float(_ns.stagnation_pressure_ratio(M_n * math.sin(math.radians(phi_c)), gamma))
    B = astar_over_a(M_n, gamma) / p0c                          # eq. (14)
    bc = B * math.cos(math.radians(lam_S))
    if bc >= 1.0:
        raise ValueError(f"Moeckel's continuity relation has no solution at M {M_n:.3f} "
                         "(B cos(lambda_S) >= 1)")
    pts = design.geometry.ramp_points
    lip = tuple(float(c) for c in design.geometry.lip)
    t = math.radians(theta_n)
    o = pts[n - 1]                                              # last ramp segment origin
    y_SB = (lip[0] - o[0]) * -math.sin(t) + (lip[1] - o[1]) * math.cos(t)
    y_m = y_SB * (1.0 - tau)                                    # eq. (30)
    y_S = y_SB * (1.0 - (y_m / y_SB) * bc) / (1.0 - bc)         # eq. (35)
    x0 = r * (y_S - y_m)                                        # eq. (32)
    x_S = math.sqrt(x0 * x0 + beta * beta * (y_S - y_m) ** 2)   # eq. (6a) / (31)
    x_SB = x_S + (y_S - y_SB) * math.tan(math.radians(lam_S))   # eq. (11), eta = lambda_S
    return MoeckelShock(tau=float(tau), M_n=float(M_n), theta_n_deg=float(theta_n),
                        beta=beta, phi_S_deg=phi_S, lambda_S_deg=lam_S, phi_c_deg=phi_c,
                        B=B, y_SB=y_SB, y_m=y_m, y_S=y_S, x0=x0, x_S=x_S, x_SB=x_SB,
                        L=x_SB - x0, lip=lip)


# --- triple point and vortex sheet (Ferri & Nucci) --------------------------------------------

def _last_shock(design, off):
    n = len(off.ramp_angles_deg)
    o = design.geometry.ramp_points[n - 1]
    return o, math.radians(design.flow_angles_deg[n - 1] + off.betas_deg[n - 1])


def triple_point(design, off, shock, search=3.0):
    """Intersection T of ramp shock n with the expelled shock (normal part first, then the
    hyperbola up to `search` x Y_S above the dividing streamline): (T, phi_T, part) or
    (None, None, None)."""
    o, a = _last_shock(design, off)

    def side(P):
        return math.cos(a) * (P[1] - o[1]) - math.sin(a) * (P[0] - o[0])

    f = lambda y: side(shock.world(shock.x0, y))                 # noqa: E731
    if f(0.0) * f(shock.y_m) <= 0.0:
        y = brentq(f, 0.0, shock.y_m, xtol=1e-15) if f(0.0) != f(shock.y_m) else shock.y_m
        return shock.world(shock.x0, y), 90.0, "normal"
    g = lambda Y: side(shock.world(shock.hyperbola_x(Y), shock.y_m + Y))   # noqa: E731
    top = max(shock.y_S - shock.y_m, 1e-9 * shock.y_SB) * search
    steps = 400
    prev, y_prev = g(0.0), 0.0
    for k in range(1, steps + 1):
        Y = top * k / steps
        cur = g(Y)
        if prev * cur <= 0.0:
            Yr = brentq(g, y_prev, Y, xtol=1e-15)
            return (shock.world(shock.hyperbola_x(Yr), shock.y_m + Yr),
                    shock.hyperbola_slope(Yr), "hyperbola")
        prev, y_prev = cur, Y
    return None, None, None


def _p_branch(M, delta, gamma, strong):
    delta = abs(delta)
    t_max = float(_obl.max_deflection(M, gamma)[0])
    if delta > t_max:
        return None
    if delta < 1e-12:
        return float(_ns.pressure_ratio(M, gamma)) if strong else 1.0
    b = float(_obl.beta_from_theta(M, delta, gamma, weak=not strong))
    mn = M * math.sin(math.radians(b))
    return 1.0 + 2.0 * gamma / (gamma + 1.0) * (mn * mn - 1.0)


def slip_direction(off, phi_T, gamma=1.4):
    """Exact vortex-sheet direction at the triple point (shock polars): region n-1 flow through
    one strong shock vs region n flow through the expelled shock, on the branch its local angle
    phi_T gives (strong if phi_T >= the shock angle of maximum deflection at M_n); equal
    pressure and direction. Returns theta_slip (deg) or None if the polars do not intersect."""
    n = len(off.ramp_angles_deg)
    up, lo = off.regions[n - 1], off.regions[n]
    strong = phi_T >= float(_obl.max_deflection(lo.M, gamma)[1])

    def f(ts):
        pa = _p_branch(up.M, ts - up.theta_deg, gamma, True)
        pb = _p_branch(lo.M, ts - lo.theta_deg, gamma, strong)
        if pa is None or pb is None:
            return None
        return up.p_ratio * pa - lo.p_ratio * pb

    step = 0.05
    grid = [lo.theta_deg - 45.0 + step * k for k in range(int(90.0 / step) + 1)]
    vals = [(t, f(t)) for t in grid]
    roots = []
    for (t0, v0), (t1, v1) in zip(vals, vals[1:]):
        if v0 is not None and v1 is not None and v0 * v1 < 0.0:
            roots.append(brentq(f, t0, t1, xtol=1e-12))
    if not roots:
        return None
    return float(min(roots, key=lambda r: abs(r - lo.theta_deg)))


def _sheet_side(lip, T, theta_deg):
    """> 0: the lip lies above the sheet from T at theta, i.e. the sheet enters the cowl."""
    c, s = math.cos(math.radians(theta_deg)), math.sin(math.radians(theta_deg))
    return c * (lip[1] - T[1]) - s * (lip[0] - T[0])


def _sheet_state(design, off, tau, method, cache=None):
    """(side, T, theta_slip, exact_used) at spilled fraction tau; side < 0 is stable. `cache`
    keeps the exact slip direction per polar branch (it depends only on the region states)."""
    shock = moeckel_shock(design, off, tau)
    T, phi_T, _ = triple_point(design, off, shock)
    n = len(off.ramp_angles_deg)
    theta_n = off.regions[n].theta_deg
    if T is None:
        return -1.0, None, None, False                  # no intersection: no vortex sheet
    theta, exact = theta_n, False
    if method == "exact":
        strong = phi_T >= float(_obl.max_deflection(off.regions[n].M, design.inputs.gamma)[1])
        if cache is not None and strong in cache:
            ts = cache[strong]
        else:
            ts = slip_direction(off, phi_T, design.inputs.gamma)
            if cache is not None:
                cache[strong] = ts
        if ts is not None:
            theta, exact = ts, True
    return _sheet_side(shock.lip, T, theta), T, theta, exact


def buzz_onset(design, off, method="exact", tau_max=TAU_MAX):
    """Ferri-Nucci onset: the smallest spilled fraction tau at which the vortex sheet from the
    triple point passes inside the lip (enters the cowl). method "exact" uses the shock-polar
    triple point (falling back to theta_n where it has no solution); "fallback" always takes
    the sheet along theta_n."""
    if method not in ("exact", "fallback"):
        raise ValueError(f"method must be 'exact' or 'fallback' (got {method!r})")
    M_n = off.regions[len(off.ramp_angles_deg)].M
    if M_n < MOECKEL_MIN_MACH:
        raise ValueError(f"M {M_n:.3f} behind the last ramp shock is below "
                         f"{MOECKEL_MIN_MACH:g}: {OUTSIDE_VALIDITY_NOTE}")
    crit_mfr = float(off.mass_capture_ratio)
    extrapolated = not TESTED_MACH[0] <= off.M_inf <= TESTED_MACH[1]
    grid = [ZERO_RANGE_TAU] + [tau_max * k / 80 for k in range(1, 81)]
    cache = {}
    prev = None
    for tau in grid:
        side, T, theta, exact = _sheet_state(design, off, tau, method, cache)
        if side > 0.0:
            if prev is None:                            # inside at the first point: no range
                return BuzzOnset(0.0, crit_mfr, method, T, theta, True, extrapolated, exact)
            lo, hi = prev, tau
            for _ in range(60):
                mid = 0.5 * (lo + hi)
                if _sheet_state(design, off, mid, method, cache)[0] > 0.0:
                    hi = mid
                else:
                    lo = mid
            side, T, theta, exact = _sheet_state(design, off, hi, method, cache)
            return BuzzOnset(float(hi), crit_mfr * (1.0 - hi), method, T, theta,
                             hi < ZERO_RANGE_TAU, extrapolated, exact)
        prev = tau
    return BuzzOnset(float(tau_max), crit_mfr * (1.0 - tau_max), method, None, None, False,
                     extrapolated, False)


# --- the whole characteristic ------------------------------------------------------------------

ABOVE_DESIGN_NOTE = ("subcritical branch and buzz onset not modelled above the design Mach "
                     "(shock-in-duct: the lip sees the free stream)")


def inlet_characteristic(design, off, area_ratio_=2.0):
    """Critical point, supercritical and subcritical branches and the buzz onset (exact and
    fallback) of `design` at the off-design point `off`."""
    _check_ar(area_ratio_)
    crit = critical_point(design, off, area_ratio_)
    sup = supercritical_branch(design, off, area_ratio_)
    M_n = float(off.regions[len(off.ramp_angles_deg)].M)
    if off.regime == "shock-in-duct":
        return Characteristic(float(off.M_inf), float(area_ratio_), crit, sup, (), None, None,
                              ABOVE_DESIGN_NOTE, M_n=M_n)
    if M_n < MOECKEL_MIN_MACH:
        return Characteristic(float(off.M_inf), float(area_ratio_), crit, sup, (), None, None,
                              OUTSIDE_VALIDITY_NOTE, valid=False, M_n=M_n)
    sub = subcritical_branch(design, off, area_ratio_)
    return Characteristic(float(off.M_inf), float(area_ratio_), crit, sup, sub,
                          buzz_onset(design, off, "exact"), buzz_onset(design, off, "fallback"),
                          M_n=M_n)
