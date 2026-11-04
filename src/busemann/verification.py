"""Verification list (addendum C6 / E, no Qt): every approximation and warning of the current
design, each with severity, the criterion used, its source and the CFD statement.

items() feeds the right panel's Verification tab and verification_notes.md (export.notes).
"""
from dataclasses import dataclass

from inletdesign import api
from inletdesign import separation as _sep

ABOUT = (
    "Busemann is a design lab for two-dimensional external-compression supersonic inlets. "
    "It designs the ramp system for a flight condition (the Oswatitsch equal-strength "
    "optimum or your own angles), draws the shock system, and reports pressure recovery, "
    "mass capture and the flow state in every region, at the design point and off design. "
    "Every relation is analytical (NACA Report 1135) and the model has been checked against "
    "inviscid Fluent CFD."
)
ASSUMPTIONS = (
    "Two-dimensional, steady, inviscid flow; no boundary layers or bleed.",
    "Calorically perfect gas (constant γ); a warning is shown when T0 makes this optimistic.",
    "Straight, attached oblique shocks on the weak branch; a terminal normal shock at the "
    "throat.",
    "Shock-on-lip design; off design the geometry is frozen.",
    "Not modelled: the external cowl shock and its reflections, shock merging, the subsonic "
    "diffuser; above the design Mach the recovery is an upper bound.",
)

CFD_STATEMENT = "must be verified with a CFD solver"
SEVERITIES = ("error", "warn", "info")
SEVERITY_TITLES = {"error": "Error", "warn": "Warning", "info": "Note"}

PHASE_3B_DOC = "docs/validation_3b.md"
# Phase 3b (viscous k-omega SST, M 3, 10 kPa, 220 K, h_c 0.1 m) at the validated geometry
PHASE_3B = {
    "ramp shock 1": "Phase 3b viscous CFD at this geometry: no separation on the first ramp.",
    "ramp shock 2": ("Phase 3b viscous CFD at this geometry: a corner separation bubble at the "
                     "second ramp corner, x = 109.5–125.0 mm, 15.5 mm long (0.155 h_c), "
                     "peak reverse wall shear −81.7 Pa."),
    "terminal normal shock": ("Phase 3b: the terminal shock was not simulated; a Mach 1.5 "
                              "normal shock on the turbulent duct boundary layer is likely "
                              "to cause further separation losses."),
}
MIL_SOURCE = ("MIL-E-5008B (1959), as given by NASA Glenn Research Center, 'Inlet "
              "Performance', https://www.grc.nasa.gov/WWW/BGH/inleth.html (formula confirmed)")
KORKEGI_TOOLTIP = (f"{_sep.KORKEGI_CRITERION}. Source: {_sep.KORKEGI_SOURCE}. "
                   f"Korkegi: {_sep.KORKEGI_SCOPE}.")


@dataclass(frozen=True)
class VerificationItem:
    severity: str        # "error" | "warn" | "info"
    category: str        # "separation" | "cowl" | "real_gas" | "upper_bound" | "mil" | ...
    title: str
    criterion: str
    source: str
    text: str            # ends with the CFD statement
    quote: str = None    # validation evidence that applies (Phase 3b), or None
    tooltip: str = None  # criterion tooltip (e.g. the Korkegi correlation's scope)


def _validated_geometry(design):
    from .charts.model import cfd_applies

    return cfd_applies(design)


def _cfd(text):
    return f"{text.rstrip('.')}; {CFD_STATEMENT}."


def separation_items(checks, design, where="design point"):
    out = []
    quotes = PHASE_3B if where == "design point" and _validated_geometry(design) else {}
    for c in checks:
        name = c.shock[:1].upper() + c.shock[1:]
        if not c.applicable:                    # ramp 1: leading-edge shock, no verdict
            out.append(VerificationItem(
                "info", "separation", f"{name}: {_sep.NOT_APPLICABLE}",
                "Shock / boundary-layer criterion not applied: the shock starts at the sharp "
                "leading edge",
                "— (no criterion applied)",
                _cfd(f"{name} at the {where}: {_sep.NOT_APPLICABLE} ({_sep.WORDING}). "
                     f"{c.note}"), quotes.get(c.shock)))
            continue
        if not c.in_range:
            sev, verdict, detail = "info", "outside the criterion's range", c.note
        elif c.flagged:
            sev, verdict = "warn", "separation likely"
            detail = None
        else:
            sev, verdict, detail = "info", "no separation expected", c.note
        if c.kind == "normal":
            value = f"M₁ {c.M1:.3f} vs {c.threshold:g}"
        elif c.in_range:
            value = f"p₂/p₁ {c.value:.3f} vs incipient {c.threshold:.3f} (M₁ {c.M1:.3f})"
        else:
            value = f"p₂/p₁ {c.value:.3f} at M₁ {c.M1:.3f}"
        margin = f", {100 * c.margin:+.1f} % from the threshold" if c.in_range else ""
        text = (f"{name} at the {where}: {verdict}{margin} ({_sep.WORDING})."
                + (f" {detail}" if detail else ""))
        out.append(VerificationItem(
            sev, "separation", f"{name}: {verdict} (approximate)",
            f"{c.criterion}; {value}", c.source, _cfd(text), quotes.get(c.shock),
            KORKEGI_TOOLTIP if c.kind == "oblique" else None))
    return out


def items(design, inputs, fs=None, off=None, off_fs=None):
    """Every verification item of the design point (and of `off`, the off-design point at
    the slider Mach, when given). Most severe first, stable within a severity."""
    if design is None:
        return []
    out = separation_items(design.separation, design)
    # cowl lip: external shock attachment
    margin = design.cowl_margin_deg
    sev = "error" if margin < 0 else "warn" if margin < 2.0 else "info"
    out.append(VerificationItem(
        sev, "cowl", "Cowl lip shock " + ("detached" if margin < 0 else "attachment margin"),
        f"θmax(M∞) − (cowl angle + lip wedge) = {margin:+.2f}° (detached below 0°, "
        "warning below 2°)",
        "Oblique-shock θ–β–M relation, attached-shock limit (NACA Report 1135)",
        _cfd("Zero-thickness or wedge lip idealisation; the external cowl flow, its drag and "
             "any bow shock are not modelled")))
    # real gas
    T0 = fs.T0 if fs is not None else None
    real = T0 is not None and T0 > api.REAL_GAS_T0_LIMIT
    out.append(VerificationItem(
        "warn" if real else "info", "real_gas",
        "Real-gas effects" + (" (outside the ideal-gas model)" if real else ""),
        f"T0 {'—' if T0 is None else f'{T0:.0f} K'} vs {api.REAL_GAS_T0_LIMIT:.0f} K "
        "(constant γ above it is optimistic)",
        "Busemann model limit (engineering threshold, no published criterion cited)",
        _cfd("Calorically perfect gas with constant γ; vibrational excitation and "
             "dissociation are not modelled")))
    # upper-bound recovery above design
    above = off is not None and off.M_inf > design.inputs.M + 1e-9
    out.append(VerificationItem(
        "warn" if above else "info", "upper_bound",
        "Recovery above the design Mach is an upper bound",
        "Shock-in-duct regime (M∞ > design): cowl shock and duct reflections not modelled",
        "Phase 3d CFD at M∞ 3.25: Mach reflection at the lip, recovery 4.9 % below the tool "
        "(docs/validation_3d.md)",
        _cfd("Above the design Mach the off-design recovery is an upper bound")))
    # MIL comparison basis and the diffuser estimate
    out.append(VerificationItem(
        "info", "mil", "MIL-E-5008B comparison basis",
        "η_MIL = 1 − 0.075 (M∞ − 1)^1.35 (1 < M∞ ≤ 5), 800 / (M∞⁴ + 935) (M∞ > 5), compared "
        "with the engine-face estimate (inviscid recovery × diffuser), not the inviscid value",
        MIL_SOURCE,
        _cfd("The specification line is a reference, not a model result")))
    out.append(VerificationItem(
        "info", "diffuser", "Subsonic diffuser recovery is an estimate",
        f"Entered value {inputs.diffuser_recovery:.3f} (default 0.97); Busemann does not "
        "compute the subsonic diffuser",
        "User input (estimate)",
        _cfd("The engine-face recovery depends on this estimate")))
    # other model notices of the design point (subsonic duct, cowl angle limit, ...)
    covered = ("External cowl shock", "Cowl near shock detachment", "real-gas")
    notices = [(n, "design point") for n in design.notices]
    if off is not None:
        notices += [(n, f"M∞ {off.M_inf:.2f}") for n in off.notices]
    for n, where in notices:
        if not n.text.startswith(covered):
            out.append(VerificationItem(
                n.level, "notice", f"{n.text[:1].upper()}{n.text[1:]} ({where})",
                "Model check", "Busemann inviscid model", _cfd(n.detail or n.text)))
    if off is not None:
        out += separation_items(off.separation, design, f"M∞ {off.M_inf:.2f}")
    rank = {s: k for k, s in enumerate(SEVERITIES)}
    return sorted(out, key=lambda i: rank[i.severity])


def badge_count(item_list):
    """Warnings and errors (the Verification tab badge)."""
    return sum(1 for i in item_list if i.severity in ("error", "warn"))
