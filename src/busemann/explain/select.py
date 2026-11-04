"""Which Explain entry describes a selection, and the live-value context for it (no Qt).

Every value in the context is an api result object (DesignResult, OffDesignResult,
Freestream, RegionState, ShockState): the drawer formats them, it never computes them.
"""
from inletdesign import api

from .content import OneBased

TOPICS = ("method", "offdesign", "separation")


def separation_lines(checks):
    """One plain line per shock check (the separation entry's "This case")."""
    out = []
    for c in checks:
        name = c.shock[:1].upper() + c.shock[1:]
        if not c.applicable:
            out.append(f"{name}: not applicable (no boundary layer upstream).")
        elif not c.in_range:
            out.append(f"{name}: M₁ = {c.M1:.2f} is outside the criterion's range.")
        elif c.kind == "normal":
            verdict = "separation likely" if c.flagged else "no separation expected"
            out.append(f"{name}: M₁ = {c.M1:.3f} against 1.3, {verdict} "
                       f"({100 * c.margin:+.1f} %).")
        else:
            verdict = "separation likely" if c.flagged else "no separation expected"
            out.append(f"{name}: p₂/p₁ = {c.value:.3f} against {c.threshold:.3f} at "
                       f"M₁ = {c.M1:.3f}, {verdict} ({100 * c.margin:+.1f} %).")
    return out


def entry_for(kind, index, view, n_regions):
    """Entry name for a canvas / table selection. kind: "region" | "shock" | "cowl" | None.
    For shocks, index is the shock index; the last shock is the terminal one when present.
    """
    if kind == "region":
        if index == 0:
            return "freestream"
        return "duct" if index >= n_regions - 1 else "region"
    if kind == "shock":
        return "shock"                       # oblique or normal: decided by the shock kind
    if kind == "cowl":
        return "cowl_offdesign" if view == "offdesign" else "cowl_design"
    return "method"


def build_context(design, off=None, fs=None, off_fs=None, view="design", kind=None,
                  index=None):
    """(entry name, context dict) for the selection on the active view.

    The design view reads the DesignResult, the off-design view the OffDesignResult at the
    slider Mach (falling back to the design if there is none). Region indices past the api's
    regions (the canvas's copy of a subsonic duct) map to the last api region.
    """
    result = off if view == "offdesign" and off is not None else design
    shocks = OneBased(result.shock_states)
    regions = list(result.regions)
    obliques = OneBased([s for s in result.shock_states if s.kind == "oblique"])
    context = {
        "design": design, "off": off, "fs": off_fs if result is off else fs, "res": result,
        "shock": shocks, "region": regions, "oblique": obliques, "shocks": shocks,
        "regions": regions, "view": view, "cfd_lip_note": api.CFD_LIP_NOTE,
    }
    name = entry_for(kind, index, view, len(regions))
    if name in ("freestream", "region", "duct"):
        i = min(index, len(regions) - 1)
        context.update(sel=regions[i], k=i)
        if name == "region" and i == len(regions) - 1:
            name = "duct"
    elif name == "shock":
        sel = result.shock_states[index]
        name = "oblique_shock" if sel.kind == "oblique" else "normal_shock"
        context.update(sel=sel, k=index + 1)
    else:
        context.update(sel=result, k=0)
    return name, context


def topic_context(topic, design, off=None, fs=None, off_fs=None):
    """Context for a topic entry ("method" reads the design, "offdesign" the slider Mach)."""
    view = "offdesign" if topic == "offdesign" else "design"
    _, context = build_context(design, off, fs, off_fs, view)
    context.update(sel=off if topic == "offdesign" else design)
    if topic == "separation":
        context.update(sep_lines=separation_lines(design.separation))
    return topic, context
