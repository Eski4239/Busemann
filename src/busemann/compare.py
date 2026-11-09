"""Compare (M10, addendum F; no Qt): slot A is a frozen snapshot of a design, slot B the live
design. This module holds the snapshot, the slider-Mach evaluation done on the worker, and
the KPI table: metric list, B − A deltas and the "better" direction of each metric.

    Δ = B − A (display units)        Δ% = 100 (B − A) / |A|

Every unit conversion is a scale factor (inletdesign.units), so Δ% does not depend on the
unit system. A metric without a better direction is never coloured.
"""
import copy
import math
from dataclasses import dataclass

from inletdesign import api
from inletdesign import units as _units

from .inputs import design_sweep, freestream_for

DEFAULT_NAME = "Pinned design"
LIVE_NAME = "Current design"
DASH = "—"
NOT_COMPUTED = "not computed"
IMPORTED_NOTE = "imported geometry — flight conditions unknown, current flight conditions used"
DIFFERENT_CONDITIONS = "A and B use different flight conditions"
METHOD_TEXT = {"oswatitsch": "optimum angles", "custom": "custom angles"}


# --- slots -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class Snapshot:
    """A complete design: every input and its api results (design, freestream, sweep)."""
    inputs: object                 # busemann.inputs.Inputs
    design: object = None          # api.DesignResult, or None (error)
    error: str = None
    freestream: object = None      # api.Freestream, or None
    sweep: object = None           # api.Sweep, or None (no ramps / no design)
    name: str = None
    imported: bool = False         # geometry-only DXF: flight conditions are the current ones

    @property
    def label(self):
        return self.name or DEFAULT_NAME


def pin(inputs, design, error, freestream, sweep, name=None, imported=False):
    """Freeze the live design into a snapshot (deep copy: nothing is shared with the live
    state, so later edits can never reach it)."""
    return Snapshot(*copy.deepcopy((inputs, design, error, freestream, sweep)), name=name,
                    imported=imported)


def snapshot_from_inputs(inputs, name=None, imported=False):
    """Compute a snapshot from inputs alone, as the app does (worker side)."""
    from .project import design_for

    try:
        fs = freestream_for(inputs, inputs.mach)
    except ValueError as exc:
        return Snapshot(inputs, error=str(exc), name=name, imported=imported)
    design = design_for(inputs)
    if design is None:
        return Snapshot(inputs, error=_design_error(inputs), freestream=fs, name=name,
                        imported=imported)
    sweep = design_sweep(design) if design.inputs.n_ramps > 0 else None
    return Snapshot(inputs, design, None, fs, sweep, name, imported)


def _design_error(inputs):
    """The api's message for inputs that give no design."""
    from .inputs import sized_capture_height

    try:
        fs = freestream_for(inputs, inputs.mach)
        api.design(inputs.mach, inputs.n_ramps,
                   capture_height=sized_capture_height(inputs, fs), gamma=inputs.gamma,
                   ramp_angles=list(inputs.custom_angles) if inputs.method == "custom"
                   else None,
                   max_cowl_angle=inputs.max_cowl_deg if inputs.max_cowl_enabled else None,
                   cowl_wedge=inputs.cowl_wedge_deg)
    except ValueError as exc:
        return str(exc)
    return "design failed"


def flight_conditions_differ(a, b):
    """True when the two snapshots fly at different M∞, p∞, T∞ or γ."""
    if a is None or b is None:
        return False
    if a.freestream is not None and b.freestream is not None:
        fa, fb = a.freestream, b.freestream
        return not all(math.isclose(x, y, rel_tol=1e-9, abs_tol=1e-12)
                       for x, y in ((fa.M, fb.M), (fa.p, fb.p), (fa.T, fb.T),
                                    (fa.gamma, fb.gamma)))
    ia, ib = a.inputs, b.inputs
    keys = ("mach", "gamma", "atmosphere_mode") + (
        ("altitude_m",) if ia.atmosphere_mode == "altitude" else ("p_pa", "T_k"))
    return any(getattr(ia, k) != getattr(ib, k) for k in keys)


# --- evaluation at the slider Mach (worker) ----------------------------------------------------

@dataclass(frozen=True)
class Evaluated:
    """A snapshot plus everything the table needs (computed off the GUI thread)."""
    snapshot: Snapshot
    slider_mach: float
    stable_range: float = None     # critical − onset A0/Ac at the slider Mach
    stable_note: str = DASH        # cell text when stable_range is None
    stable_reason: str = None      # tooltip: why it is not computed
    cd_cowl: float = None          # C_D,cowl at the design Mach
    cd_reason: str = None
    mdot_span: float = None        # captured kg/s per metre of span
    mdot_total: float = None       # kg/s through the inlet width (None without a width)
    face: float = None             # engine-face estimate: recovery × diffuser recovery
    mil: float = None              # MIL-E-5008B recovery at the design Mach
    sep_flags: int = None

    @property
    def design(self):
        return self.snapshot.design


def evaluate(snapshot, slider_mach):
    """Slider-Mach and derived results of a snapshot (pure; runs on the worker)."""
    d, i = snapshot.design, snapshot.inputs
    if d is None:
        return Evaluated(snapshot, slider_mach)
    out = dict(sep_flags=sum(1 for s in d.separation if s.flagged))
    out["face"] = d.recovery_total * i.diffuser_recovery
    out["mil"] = api.mil_recovery(d.inputs.M)
    M, gamma, wedge = d.inputs.M, d.inputs.gamma, d.inputs.cowl_wedge_deg
    cd = api.cowl_pressure_drag(M, M, 1.0, d.cowl_angle_deg + wedge, i.cowl_frontal_height,
                                gamma)
    out["cd_cowl"], out["cd_reason"] = cd.cd, cd.reason
    if snapshot.freestream is not None:
        h = d.inputs.capture_height
        out["mdot_span"] = api.captured_mass_flow(snapshot.freestream, h, d.mass_capture)
        if i.inlet_width_m:
            out["mdot_total"] = out["mdot_span"] * i.inlet_width_m
    out.update(_stable(d, i, slider_mach))
    return Evaluated(snapshot, slider_mach, **out)


def _stable(d, inputs, M):
    if not d.inputs.n_ramps:
        return dict(stable_reason="no ramps: no inlet characteristic")
    try:
        off = api.off_design_point(d, M)
    except ValueError as exc:
        return dict(stable_reason=str(exc))
    try:
        c = api.inlet_characteristic(d, off, inputs.diffuser_area_ratio)
    except ValueError as exc:
        return dict(stable_note=NOT_COMPUTED, stable_reason=str(exc))
    if not c.valid:
        return dict(stable_note=NOT_COMPUTED, stable_reason=c.note)
    if c.buzz is None:
        return dict(stable_note=NOT_COMPUTED,
                    stable_reason="above the design Mach: the subcritical branch is not "
                                  "modelled")
    return dict(stable_range=max(0.0, c.critical.mfr - c.buzz.mfr))


# --- metrics ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    group: str                     # "inputs" | "results"
    quantity: str = None           # inletdesign.units quantity, or None (no unit)
    digits: int = 3                # decimals shown
    better: str = None             # "higher" | "lower" | None (no better direction)
    why: str = None                # tooltip: why that direction is better
    unit: str = ""                 # fixed unit text when quantity is None
    percent: bool = True           # show Δ%


METRICS = (
    Metric("mach", "M∞", "inputs", digits=2),
    Metric("altitude", "Altitude", "inputs", "altitude", 3),
    Metric("p", "p∞", "inputs", "pressure", 3),
    Metric("T", "T∞", "inputs", "temperature", 2),
    Metric("n_ramps", "Ramps", "inputs", digits=0, percent=False),
    Metric("method", "Method", "inputs", percent=False),
    Metric("ramp", "Ramp {k} angle", "inputs", digits=2, unit="°"),
    Metric("capture_height", "Capture height", "inputs", "length", 4),
    Metric("width", "Inlet width", "inputs", "length", 3),
    Metric("wedge", "Cowl lip wedge", "inputs", digits=1, unit="°", percent=False),
    Metric("recovery", "Total recovery", "results", digits=4, better="higher",
           why="Higher is better: more of the free-stream total pressure reaches the engine."),
    Metric("face", "Engine face vs MIL-E-5008B", "results", digits=3, better="higher",
           why="Higher is better: the engine-face estimate (recovery × diffuser) is compared "
               "with MIL-E-5008B."),
    Metric("mass_capture", "Mass capture A0/Ac", "results", digits=3, better="higher",
           why="Higher is better: less of the captured streamtube spills around the cowl."),
    Metric("mdot_span", "Captured ṁ per span", "results", "mass_flow_per_span", 3),
    Metric("mdot_total", "Captured ṁ", "results", "mass_flow", 3),
    Metric("M_post", "M after terminal shock", "results", digits=3),
    Metric("cowl_angle", "Cowl angle", "results", digits=2, unit="°", better="lower",
           why="Lower is better: a smaller cowl turn means less external cowl drag."),
    Metric("cowl_margin", "Cowl margin", "results", digits=2, unit="°", better="higher",
           why="Higher is better: the cowl lip shock is further from detaching.",
           percent=False),
    Metric("cd_cowl", "Cowl drag coefficient at design", "results", digits=4, better="lower",
           why="Lower is better: less cowl pressure drag at the design Mach."),
    Metric("sep_flags", "Separation flags", "results", digits=0, better="lower",
           why="Lower is better: fewer shocks predicted to separate the boundary layer "
               "(approximate).", percent=False),
    Metric("stable", "Stable subcritical range at M∞ {M:.2f}", "results", digits=3,
           better="higher",
           why="Higher is better: the inlet can spill more before buzz (approximate)."),
)
METRIC = {m.key: m for m in METRICS}


@dataclass(frozen=True)
class Row:
    label: str
    a: str
    b: str
    delta: str = ""
    pct: str = ""
    verdict: str = None            # "better" | "worse" (B against A) | None (neutral)
    why: str = None                # tooltip of a coloured Δ
    a_tip: str = None
    b_tip: str = None
    section: bool = False          # a section heading row ("Inputs", "Results")


def _ramp_angles(ev):
    s = ev.snapshot
    if s.design is not None:
        return tuple(s.design.ramp_angles_deg)
    if s.inputs.method == "custom":
        return tuple(s.inputs.custom_angles)
    return ()


def _value(ev, key, k=None):
    """SI value of a metric for one slot: float, text, or None (not available)."""
    if ev is None:
        return None
    s, d, i = ev.snapshot, ev.snapshot.design, ev.snapshot.inputs
    fs = s.freestream
    if key == "mach":
        return i.mach
    if key == "altitude":
        return i.altitude_m if i.atmosphere_mode == "altitude" else None
    if key == "p":
        return fs.p if fs is not None else (i.p_pa if i.atmosphere_mode == "manual" else None)
    if key == "T":
        return fs.T if fs is not None else (i.T_k if i.atmosphere_mode == "manual" else None)
    if key == "n_ramps":
        return i.n_ramps
    if key == "method":
        text = METHOD_TEXT.get(i.method, i.method)
        if i.method == "oswatitsch" and i.max_cowl_enabled:
            text += f", cowl ≤ {i.max_cowl_deg:.1f}°"
        return text
    if key == "ramp":
        angles = _ramp_angles(ev)
        return angles[k] if k < len(angles) else None
    if key == "capture_height":
        return d.inputs.capture_height if d is not None else i.capture_height_m
    if key == "width":
        return i.inlet_width_m
    if key == "wedge":
        return i.cowl_wedge_deg
    if d is None:
        return None
    return {"recovery": d.recovery_total, "face": ev.face, "mass_capture": d.mass_capture,
            "mdot_span": ev.mdot_span, "mdot_total": ev.mdot_total,
            "M_post": d.M_post_terminal, "cowl_angle": d.cowl_angle_deg,
            "cowl_margin": d.cowl_margin_deg, "cd_cowl": ev.cd_cowl,
            "sep_flags": ev.sep_flags, "stable": ev.stable_range}[key]


def _display(m, v, units):
    return _units.to_display(v, m.quantity, units) if m.quantity else v


def _unit(m, units):
    if m.quantity:
        return " " + _units.unit_label(m.quantity, units)
    return (" " if m.unit and m.unit != "°" else "") + m.unit


def _text(m, v, units):
    if v is None:
        return DASH
    if isinstance(v, str):
        return v
    x = _display(m, v, units)
    return f"{x:.{m.digits}f}{_unit(m, units)}"


def _cell(m, ev, v, units):
    """(text, tooltip) of one slot's cell."""
    if ev is None:
        return DASH, None
    if m.key == "face" and v is not None:
        return f"{v:.3f} vs {ev.mil:.3f}", (f"Engine-face estimate {v:.4f} (recovery × "
                                            f"diffuser {ev.snapshot.inputs.diffuser_recovery:.3f}"
                                            f"); MIL-E-5008B {ev.mil:.4f} at M∞ "
                                            f"{ev.design.inputs.M:.2f}.")
    if m.key == "stable" and v is None and ev.design is not None:
        reason = ev.stable_reason
        return ev.stable_note, (reason[:1].upper() + reason[1:] + ".") if reason else None
    if m.key == "cd_cowl" and v is None and ev.design is not None and ev.cd_reason:
        return DASH, ev.cd_reason[:1].upper() + ev.cd_reason[1:] + "."
    if v is None and ev.design is None and METRIC[m.key].group == "results":
        return DASH, ev.snapshot.error
    return _text(m, v, units), None


def _row(m, a, b, units, label=None, k=None):
    va, vb = _value(a, m.key, k), _value(b, m.key, k)
    ta, tip_a = _cell(m, a, va, units)
    tb, tip_b = _cell(m, b, vb, units)
    row = dict(label=label or m.label, a=ta, b=tb, a_tip=tip_a, b_tip=tip_b)
    if not (isinstance(va, (int, float)) and isinstance(vb, (int, float))) or \
            isinstance(va, bool) or isinstance(vb, bool) or \
            (m.group == "results" and (a.design is None or b.design is None)):
        return Row(delta=DASH if (a is not None or b is not None) else "", pct="", **row)
    da, db = _display(m, va, units), _display(m, vb, units)
    diff = db - da
    equal = abs(vb - va) <= 1e-9 * max(abs(va), abs(vb), 1e-12)
    delta = f"{0.0 if equal else diff:+.{m.digits}f}{_unit(m, units)}"
    pct = ""
    if m.percent:
        pct = DASH if va == 0 else f"{0.0 if equal else 100.0 * (vb - va) / abs(va):+.1f} %"
    verdict = None
    if m.better and not equal:
        higher = vb > va
        verdict = "better" if higher == (m.better == "higher") else "worse"
    return Row(delta=delta, pct=pct, verdict=verdict, why=m.why if verdict else None, **row)


def table(a, b, units="SI"):
    """Rows of the KPI table for two Evaluated slots (either may be None: empty slot)."""
    rows = [Row("Inputs", "", "", section=True)]
    for m in METRICS:
        if m.group != "inputs":
            continue
        if m.key == "ramp":
            n = max(len(_ramp_angles(e)) for e in (a, b) if e is not None) if (a is not None or b is not None) else 0
            rows += [_row(m, a, b, units, m.label.format(k=k + 1), k) for k in range(n)]
            continue
        rows.append(_row(m, a, b, units))
    rows.append(Row("Results", "", "", section=True))
    M = next((e.slider_mach for e in (b, a) if e is not None), None)
    for m in METRICS:
        if m.group != "results":
            continue
        if m.key == "mdot_total" and not any(e is not None and e.snapshot.inputs.inlet_width_m
                                             for e in (a, b)):
            continue
        label = m.label.format(M=M) if m.key == "stable" and M is not None else None
        if m.key == "stable" and M is None:
            label = "Stable subcritical range"
        rows.append(_row(m, a, b, units, label))
    return rows


def plain(text):
    """Table text without rich-text tags (copy, tests)."""
    import re

    return re.sub("<[^>]+>", "", text)


def to_tsv(rows, a_label="A", b_label="B"):
    """The table as tab-separated text (Copy table)."""
    lines = ["\t".join(("Metric", a_label, b_label, "Δ", "Δ%"))]
    for r in rows:
        lines.append("\t".join(plain(x) for x in (r.label, r.a, r.b, r.delta, r.pct)))
    return "\n".join(lines)
