"""Flight-condition presets (data only).

Each preset sets the freestream Mach number and either a geometric altitude
(standard atmosphere) or a manual static pressure/temperature.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Preset:
    name: str
    mach: float
    description: str
    altitude_m: float = None
    p_pa: float = None
    T_k: float = None

    @property
    def mode(self):
        return "altitude" if self.altitude_m is not None else "manual"


PRESETS = (
    Preset("Concorde cruise", 2.02, "Supersonic airliner cruise.", altitude_m=17000.0),
    Preset("XB-70", 3.0, "Mach 3 bomber prototype cruise.", altitude_m=21300.0),
    Preset("SR-71", 3.2, "Reconnaissance aircraft cruise.", altitude_m=24000.0),
    Preset(
        "X-15 record", 6.7,
        "Rocket-plane speed record; outside the ideal-gas model.", altitude_m=31000.0,
    ),
    Preset(
        "Validation case", 3.0,
        "Freestream used for the Fluent validation runs.", p_pa=10000.0, T_k=220.0,
    ),
)


def get(name):
    """Return the preset with this name; ValueError if unknown."""
    for preset in PRESETS:
        if preset.name == name:
            return preset
    raise ValueError(f"unknown preset {name!r}; known: {[p.name for p in PRESETS]}")
