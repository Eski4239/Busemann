"""Application inputs (no Qt): everything the user sets, saved in project files."""
from dataclasses import dataclass

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


def preset_changes(name):
    """Input changes that apply the named preset (as the Flight panel does)."""
    p = _presets.get(name)
    changes = dict(mach=p.mach, atmosphere_mode=p.mode, preset=p.name)
    if p.mode == "altitude":
        changes["altitude_m"] = p.altitude_m
    else:
        changes.update(p_pa=p.p_pa, T_k=p.T_k)
    return changes
