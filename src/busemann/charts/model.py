"""Off-design chart data (pure Python, no Qt): curve series, regime bands, CFD overlay.

Everything here is computed from api results only; the chart widgets just draw it.
"""
import json
import math
from dataclasses import dataclass

from scipy.optimize import brentq

from inletdesign import api

from ..paths import resource_path

# Validated case of the Phase 3d CFD (docs/validation_3d.md): the overlay is shown only
# for this design.
CFD_DESIGN = dict(M=3.0, n_ramps=2, method="oswatitsch", gamma=1.4)
CFD_MACH_TOL = 1e-6
CFD_GAMMA_TOL = 1e-9
# band kind -> (colour token, alpha 0..255); shared by the Qt charts and the figure export
BAND_STYLE = {"detached": ("error", 22), "spillage": ("accent", 14),
              "overspeed": ("warn", 18), "cowl": ("error", 40)}
CFD_NOTE = "CFD validation available for the M3 2-ramp design only"
CFD_WEDGE_NOTE = "CFD validation used a zero-thickness cowl"


@dataclass(frozen=True)
class Band:
    kind: str      # "detached" | "spillage" | "overspeed" | "cowl"
    label: str
    lo: float
    hi: float


def load_cfd():
    """Bundled Phase 3d CFD points: dict with source, design, points [{M, capture, ...}]."""
    return load_validation()["cfd_overlay"]


def load_validation():
    """resources/data/validation.json: validation phases (About dialog) and the CFD overlay
    points; the single source of truth for both."""
    return json.loads(resource_path("data", "validation.json").read_text(encoding="utf-8"))


def _validated_geometry(design):
    i = design.inputs
    return (abs(i.M - CFD_DESIGN["M"]) <= CFD_MACH_TOL and i.n_ramps == CFD_DESIGN["n_ramps"]
            and i.method == CFD_DESIGN["method"]
            and abs(i.gamma - CFD_DESIGN["gamma"]) <= CFD_GAMMA_TOL and not design.constrained)


def cfd_applies(design):
    """True when `design` is the validated case: M 3.0, 2 ramps, Oswatitsch, gamma 1.4,
    not cowl-constrained, zero-thickness cowl (wedge 0, as in the Phase 3d CFD)."""
    return (design is not None and _validated_geometry(design)
            and not (design.inputs.cowl_wedge_deg or 0.0))


def cfd_note(design):
    """Why the CFD overlay is hidden (None when it is shown)."""
    if cfd_applies(design):
        return None
    if design is not None and _validated_geometry(design):
        return CFD_WEDGE_NOTE                 # only the lip wedge differs
    return CFD_NOTE


def ordinal(n):
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def detached_ramp(design, mach):
    """1-based index of the first ramp whose shock is detached at `mach`, or None."""
    try:
        api.off_design_point(design, mach)
        return None
    except ValueError as exc:
        text = str(exc)
        if "shock detached at ramp" not in text:
            return None
        return int(text.split("shock detached at ramp")[1].split(":")[0]) + 1


def series(sweep):
    """Curves over the sweep. Detached points are skipped (gaps). The cowl margin gets a
    NaN break where the lip changes flow region (documented jump at the design Mach) and
    where it is undefined (subsonic, aligned lip flow)."""
    out = {k: [] for k in ("M", "capture", "rec_obl", "rec_tot")}
    margin_x, margin_y = [], []
    prev_region = None
    for M, p in zip(sweep.machs, sweep.points):
        if p is None:
            prev_region = None
            continue
        out["M"].append(M)
        out["capture"].append(p.mass_capture_ratio)
        out["rec_obl"].append(p.recovery_oblique)
        out["rec_tot"].append(p.recovery_total)
        if prev_region is not None and p.cowl_lip_region != prev_region:
            margin_x.append(M)
            margin_y.append(math.nan)          # break: a shock crosses the lip
        margin_x.append(M)
        margin_y.append(math.nan if p.cowl_margin_deg is None else p.cowl_margin_deg)
        prev_region = p.cowl_lip_region
    out["margin_M"], out["margin"] = margin_x, margin_y
    return out


def _margin(design, M):
    p = api.off_design_point(design, M)
    return p.cowl_margin_deg


def cowl_detached_intervals(design, sweep, tol=1e-4):
    """[(lo, hi)] of M where the local cowl margin (with the current lip wedge) is < 0.

    Edges inside one lip region are refined with brentq; an edge at a lip-region change
    is the design Mach (where every ramp shock crosses the lip)."""
    pts = [(M, p) for M, p in zip(sweep.machs, sweep.points) if p is not None]
    intervals, start = [], None

    def neg(p):
        return p.cowl_margin_deg is not None and p.cowl_margin_deg < 0.0

    for k, (M, p) in enumerate(pts):
        if k == 0:
            if neg(p):
                start = M
            continue
        M0, p0 = pts[k - 1]
        if neg(p0) == neg(p):
            continue
        if p0.cowl_lip_region != p.cowl_lip_region:
            edge = design.inputs.M
        elif p0.cowl_margin_deg is None or p.cowl_margin_deg is None:
            # margin undefined on one side (subsonic lip flow): bisect where it appears
            a, b = M0, M
            undefined_at_a = p0.cowl_margin_deg is None
            while b - a > tol:
                mid = 0.5 * (a + b)
                if (_margin(design, mid) is None) == undefined_at_a:
                    a = mid
                else:
                    b = mid
            edge = 0.5 * (a + b)
        else:
            edge = brentq(lambda m: _margin(design, m), M0, M, xtol=tol)
        if neg(p):
            start = edge
        else:
            intervals.append((start, edge))
            start = None
    if start is not None:
        intervals.append((start, pts[-1][0]))
    return intervals


def regime_bands(design, sweep, m_min, m_max):
    """Shaded regime bands along M_inf for the off-design charts."""
    M_d = design.inputs.M
    m_det = sweep.detachment_mach
    bands = []
    if m_det > m_min:
        ramp = detached_ramp(design, max(m_min, m_det - 1e-3))
        name = f"{ordinal(ramp)} ramp shock detached" if ramp else "ramp shock detached"
        bands.append(Band("detached", name, m_min, m_det))
    if M_d > max(m_det, m_min):
        bands.append(Band("spillage", "spillage", max(m_det, m_min), M_d))
    if m_max > M_d:
        bands.append(Band("overspeed", "overspeed: shocks inside cowl", M_d, m_max))
    for lo, hi in cowl_detached_intervals(design, sweep):
        bands.append(Band("cowl", "cowl detached", lo, hi))
    return bands
