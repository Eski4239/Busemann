"""Application inputs (no Qt): everything the user sets, saved in project files."""
from dataclasses import dataclass

from inletdesign import api
from inletdesign import presets as _presets


@dataclass(frozen=True)
class Inputs:
    mach: float = 3.0
    atmosphere_mode: str = "altitude"   # "altitude" | "manual"
    altitude_m: float = 20000.0
    p_pa: float = 10000.0
    T_k: float = 220.0
    gamma: float = 1.4
    n_ramps: int = 2
    method: str = "oswatitsch"          # "oswatitsch" | "custom"
    custom_angles: tuple = ()
    capture_height_m: float = 0.1
    units: str = "SI"                   # "SI" | "Imperial"
    preset: str = None                  # name of the applied preset, None once edited
    off_design_mach: float = None       # off-design slider Mach; None = the design Mach
    max_cowl_enabled: bool = False      # limit the Oswatitsch optimum's cowl angle
    max_cowl_deg: float = 30.0
    cowl_wedge_deg: float = 0.0         # cowl lip outer wedge; 0 = zero-thickness idealisation
    capture_mode: str = "height"        # "height": h_c drives | "mass_flow": engine mdot drives
    mdot_kgps: float = None             # required engine mass flow, kg/s (mass_flow mode)
    inlet_width_m: float = None         # inlet width (span), m; None = per metre only
    diffuser_recovery: float = 0.97     # subsonic diffuser p0 ratio (estimate)
    cowl_frontal_height: float = 0.10   # cowl frontal height / h_c (drag estimate only)


CAPTURE_MODES = ("height", "mass_flow")
OFF_DESIGN_MIN_MACH = 1.2        # off-design slider lower end
OFF_DESIGN_SPAN = 1.5            # slider upper end = design Mach + this
SWEEP_POINTS = 40
DEFAULT_WIDTH_M = 1.0                   # width used when sizing starts without one


def preset_changes(name):
    """Input changes that apply the named preset (as the Flight panel does)."""
    p = _presets.get(name)
    changes = dict(mach=p.mach, atmosphere_mode=p.mode, preset=p.name)
    if p.mode == "altitude":
        changes["altitude_m"] = p.altitude_m
    else:
        changes.update(p_pa=p.p_pa, T_k=p.T_k)
    return changes


def freestream_for(inputs, M):
    """Freestream at Mach M in the inputs' atmosphere (altitude or manual p, T)."""
    if inputs.atmosphere_mode == "altitude":
        return api.freestream(M, altitude_m=inputs.altitude_m, gamma=inputs.gamma)
    return api.freestream(M, p=inputs.p_pa, T=inputs.T_k, gamma=inputs.gamma)


def sized_capture_height(inputs, fs):
    """The capture height that drives the design: the input, or (engine sizing) the one that
    passes the required mass flow at the design point (A0/Ac = 1)."""
    if inputs.capture_mode == "mass_flow" and fs is not None and inputs.mdot_kgps \
            and inputs.inlet_width_m:
        return api.capture_height_for_mass_flow(fs, inputs.mdot_kgps, inputs.inlet_width_m)
    return inputs.capture_height_m


def off_design_range(design_mach):
    """(min, max) of the off-design Mach slider for a design Mach."""
    return OFF_DESIGN_MIN_MACH, round(design_mach + OFF_DESIGN_SPAN, 10)


def design_sweep(design):
    """The off-design sweep the app draws for a design: SWEEP_POINTS Machs from the
    detachment Mach (or the slider's lower end) to the slider's upper end."""
    lo, hi = off_design_range(design.inputs.M)
    return api.off_design_sweep(design, max(lo, api.detachment_mach(design)), hi, SWEEP_POINTS)
