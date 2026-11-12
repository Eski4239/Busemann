"""Verification list (addendum C6 / E, no Qt): every approximation and warning of the current
design, each with severity, the criterion used, its source and the CFD statement.

items() feeds the right panel's Verification tab and verification_notes.md (export.notes).
"""
from dataclasses import dataclass

from inletdesign import api
from inletdesign import separation as _sep

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

# Viscous validation CFD (k-omega SST, M 3, 10 kPa, 220 K, capture height 0.1 m) at the
# validated geometry; the report is docs/validation_3b.md (internal, not shown in the UI)
VALIDATION_CFD = {
    "ramp shock 1": "The validation CFD (viscous) at this geometry: no separation on the "
                    "first ramp.",
    "ramp shock 2": ("The validation CFD (viscous) at this geometry: a corner separation "
                     "bubble at the second ramp corner, x = 109.5–125.0 mm, 15.5 mm long "
                     "(0.155 of the capture height), peak reverse wall shear −81.7 Pa."),
    "terminal normal shock": ("The validation CFD did not simulate the terminal shock; a "
                              "Mach 1.5 "
                              "normal shock on the turbulent duct boundary layer is likely "
                              "to cause further separation losses."),
}
# How the solver was checked (About, verification_notes.md); user text, no internal names
VALIDATION_SUMMARY = (
    "How it was checked: every relation in the solver follows NACA Report 1135, and an "
    "automated test suite of over 800 tests checks the results against closed-form values. "
    "The designs were also compared with 2D CFD simulations in Ansys Fluent (density-based "
    "solver, inviscid and k-ω SST viscous runs, with a mesh-refinement check). At the design "
    "point the total-pressure recovery agreed within 0.35%, and below the design Mach within "
    "0.1%, with mass capture within 0.4%. With boundary layers included, recovery was about 2% "
    "lower, mainly because of a separation bubble at the second ramp corner, which Busemann's "
    "separation warning flags. Above the design Mach the CFD showed a Mach reflection at the "
    "cowl lip that this model does not include, so recovery there is an upper bound (the CFD "
    "was 4.9% lower at Mach 3.25).")
MIL_SOURCE = ("MIL-E-5008B (1959), as given by NASA Glenn Research Center, 'Inlet "
              "Performance', https://www.grc.nasa.gov/WWW/BGH/inleth.html (formula confirmed)")
DRAG_SOURCE = ("Additive drag: M. Sibulkin, 'Theoretical and Experimental Investigation "
               "of Additive Drag', NACA Report 1187 (1954), eq. (5)/(5a), p. 2 (change in "
               "total momentum of the entering stream tube; p. 3, the equivalent pressure "
               "integral); the report treats axisymmetric inlets, applied here per unit "
               "width in 2D. Cowl pressure drag: Busemann model choice (oblique-shock "
               "relations, NACA Report 1135)")
BUZZ_TESTED_MACH = (1.9, 2.7)          # Ferri & Nucci RM L50K30 test range (p. 7)
BUZZ_SEPARATION_TITLE = "Ramp separation reduces the buzz margin (approximate)"
BUZZ_SEPARATION_TEXT = (
    "The separation check flags a ramp shock for this design. In tests of external-"
    "compression inlets, separation on the compression surface allowed stable subcritical "
    "operation only for very small reductions in mass flow, so this inlet is likely to buzz "
    "soon after it starts spilling flow. Verify with CFD or wind-tunnel data.")
BUZZ_SEPARATION_SOURCE = (
    "Ferri & Nucci, NACA RM L50K30 (1951), p. 7 and Concluding Remarks pp. 25–26; tests on "
    "conical inlets, M 1.9–2.7. Applying it to a 2D multi-ramp inlet is a Busemann extension.")
BUZZ_EXTRAPOLATED = " Extrapolated beyond the tested Mach range."
CHARACTERISTIC_SOURCE = (
    "NACA Report 1135 eqs. (44), (80), (99); Moeckel, NACA TN 1921 (1949), eqs. (4), "
    "(6)/(6a), (14), (17), (30)–(36), pp. 7–19, applied to the flow behind the last ramp shock "
    "(Busemann extension); Ferri & Nucci, NACA RM L50K30 (1951), Summary p. 1, p. 7 and "
    "Concluding Remarks p. 25 (conical inlets, M 1.9–2.7; 2D multi-ramp application is a "
    "Busemann extension)")
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
    quote: str = None    # validation evidence that applies (the validation CFD), or None
    tooltip: str = None  # criterion tooltip (e.g. the Korkegi correlation's scope)


def _validated_geometry(design):
    from .charts.model import cfd_applies

    return cfd_applies(design)


def _cfd(text):
    return f"{text.rstrip('.')}; {CFD_STATEMENT}."


def separation_items(checks, design, where="design point"):
    out = []
    quotes = VALIDATION_CFD if where == "design point" and _validated_geometry(design) else {}
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
        "The validation CFD at M∞ 3.25: Mach reflection at the lip, recovery 4.9 % below "
        "the tool",
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
    # M9b: what the drag estimate leaves out
    out.append(VerificationItem(
        "info", "drag", "Drag is an inviscid pressure-drag estimate",
        "Additive drag: (p − p∞) along the dividing streamline from the free stream to the "
        "lip; cowl drag: the oblique-shock pressure on the cowl's outer face over a frontal "
        f"height of {getattr(inputs, 'cowl_frontal_height', 0.10):.2f} × capture height; "
        "coefficients on q∞ × capture height",
        DRAG_SOURCE,
        _cfd("It excludes skin friction, subcritical spillage (terminal shock expelled), the "
             "cowl beyond its frontal height and 3D effects")))
    # M9c: the characteristic and the buzz onset are approximate (Analytics)
    if design.inputs.n_ramps:
        out.append(VerificationItem(
            "info", "buzz", "Inlet characteristic and buzz onset are approximate",
            "Supercritical branch quasi-1D (diffuser exit/entry area ratio "
            f"{getattr(inputs, 'diffuser_area_ratio', 2.0):.2f}); expelled-shock position by "
            "Moeckel's method in the flow behind the last ramp shock; buzz onset when the "
            "vortex sheet from the shock intersection enters the cowl",
            CHARACTERISTIC_SOURCE,
            _cfd("The ideal subcritical branch is flat and ignores viscous losses; the buzz "
                 "onset is an estimate")))
    # M9c: ramp separation shortens the stable subcritical range (Ferri & Nucci)
    flagged = [c.shock for c in design.separation if c.shock.startswith("ramp") and c.flagged]
    if flagged:
        M_ref = off.M_inf if off is not None else design.inputs.M
        source = BUZZ_SEPARATION_SOURCE + (BUZZ_EXTRAPOLATED if M_ref > BUZZ_TESTED_MACH[1]
                                           else "")
        out.append(VerificationItem(
            "warn", "buzz", BUZZ_SEPARATION_TITLE,
            "Separation check flags " + ", ".join(flagged) + " (approximate, see the "
            "separation items)",
            source, BUZZ_SEPARATION_TEXT))
    if off is not None and design.inputs.n_ramps:
        h = getattr(inputs, "cowl_frontal_height", 0.10)
        hits = api.cowl_face_intersections(design, off, h)
        if hits:
            rise = max(p[1] for p, _, _ in hits) - design.geometry.lip[1]
            out.append(VerificationItem(
                "info", "drag", f"Cowl drag: non-uniform face pressure at M∞ {off.M_inf:.2f}",
                f"{len(hits)} ramp-shock intersection(s) within the cowl frontal height "
                f"({h:.2f} × capture height) above the lip, the highest "
                f"{rise / design.inputs.capture_height:.3f} × capture height above it; merged "
                "shocks approximated by the straight ramp-shock extensions",
                "Busemann model limit (geometric check, no published criterion cited)",
                _cfd(api.NONUNIFORM_NOTE[:1].upper() + api.NONUNIFORM_NOTE[1:])))
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
