"""SI <-> imperial display-unit conversion.

All core quantities are SI. Each quantity has one display unit per system;
every conversion is a pure scale factor (display = SI * factor), so there are
no offsets (temperatures are absolute: K and degrees Rankine).

Exact definitions: 1 ft = 0.3048 m, 1 in = 0.0254 m, 1 lbm = 0.45359237 kg,
1 lbf = 1 lbm * 9.80665 m/s^2, 1 degR = 1/1.8 K.
"""
import numpy as np

FT = 0.3048
INCH = 0.0254
LBM = 0.45359237
LBF = LBM * 9.80665
PSI = LBF / INCH**2

SYSTEMS = ("SI", "Imperial")

# quantity -> {system: (label, display units per SI unit)}
_UNITS = {
    "altitude": {"SI": ("km", 1e-3), "Imperial": ("ft", 1.0 / FT)},
    "length": {"SI": ("m", 1.0), "Imperial": ("in", 1.0 / INCH)},
    "pressure": {"SI": ("kPa", 1e-3), "Imperial": ("psi", 1.0 / PSI)},
    "temperature": {"SI": ("K", 1.0), "Imperial": ("°R", 1.8)},
    "density": {"SI": ("kg/m³", 1.0), "Imperial": ("lbm/ft³", FT**3 / LBM)},
    "velocity": {"SI": ("m/s", 1.0), "Imperial": ("ft/s", 1.0 / FT)},
    "mass_flow_per_span": {"SI": ("kg/s/m", 1.0), "Imperial": ("lbm/s/ft", FT / LBM)},
    "per_length": {"SI": ("1/m", 1.0), "Imperial": ("1/ft", FT)},
    "viscosity": {"SI": ("Pa·s", 1.0), "Imperial": ("lbf·s/ft²", FT**2 / LBF)},
}

QUANTITIES = tuple(_UNITS)


def _lookup(quantity, system):
    if system not in SYSTEMS:
        raise ValueError(f"unit system must be one of {SYSTEMS}, got {system!r}")
    if quantity not in _UNITS:
        raise ValueError(f"unknown quantity {quantity!r}; known: {QUANTITIES}")
    return _UNITS[quantity][system]


def unit_label(quantity, system):
    """Display unit label, e.g. unit_label('pressure', 'SI') -> 'kPa'."""
    return _lookup(quantity, system)[0]


def to_display(value_si, quantity, system):
    """display = SI * factor."""
    factor = _lookup(quantity, system)[1]
    value = np.asarray(value_si, dtype=float) * factor
    return float(value) if value.ndim == 0 else value


def from_display(value, quantity, system):
    """SI = display / factor."""
    factor = _lookup(quantity, system)[1]
    value = np.asarray(value, dtype=float) / factor
    return float(value) if value.ndim == 0 else value


# --- typed input with units ------------------------------------------------------------------
# kind -> {unit: (scale, offset)} with  SI = value * scale + offset.  Kinds and their SI base:
# length m, altitude m, temperature K, pressure Pa, mass_flow kg/s, angle deg (the app's
# angle unit), dimensionless (no units).
ATM = 101325.0
BAR = 1.0e5
UNIT_KINDS = {
    "length": {"m": (1.0, 0.0), "cm": (0.01, 0.0), "mm": (0.001, 0.0), "km": (1000.0, 0.0),
               "ft": (FT, 0.0), "in": (INCH, 0.0)},
    "altitude": {"km": (1000.0, 0.0), "m": (1.0, 0.0), "ft": (FT, 0.0),
                 "kft": (1000.0 * FT, 0.0)},
    "temperature": {"K": (1.0, 0.0), "°C": (1.0, 273.15), "C": (1.0, 273.15),
                    "°F": (1.0 / 1.8, 273.15 - 32.0 / 1.8), "F": (1.0 / 1.8, 273.15 - 32.0 / 1.8),
                    "R": (1.0 / 1.8, 0.0), "°R": (1.0 / 1.8, 0.0)},
    "pressure": {"Pa": (1.0, 0.0), "kPa": (1000.0, 0.0), "bar": (BAR, 0.0), "psi": (PSI, 0.0),
                 "atm": (ATM, 0.0)},
    "mass_flow": {"kg/s": (1.0, 0.0), "lb/s": (LBM, 0.0)},
    "angle": {"°": (1.0, 0.0), "deg": (1.0, 0.0), "rad": (180.0 / np.pi, 0.0)},
    "dimensionless": {},
}
_KIND_NAMES = {"length": "length", "altitude": "altitude", "temperature": "temperature",
               "pressure": "pressure", "mass_flow": "mass flow", "angle": "angle",
               "dimensionless": "number"}
_NUMBER = r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?"


class UnitError(ValueError):
    """Typed input could not be read; the message is shown under the field."""


def accepted_units(kind):
    """Units accepted for a kind, in table order."""
    return list(UNIT_KINDS[kind])


def parse_quantity(text, kind, field_unit=None):
    """Value of typed text ("65000 ft", "-56.5 C", "2.2") in the field's unit.

    A bare number is taken in `field_unit`. Units of another kind or unknown units raise
    UnitError with a short message ("ft is not a temperature")."""
    import re

    if kind not in UNIT_KINDS:
        raise ValueError(f"unknown kind {kind!r}")
    m = re.fullmatch(rf"\s*({_NUMBER})\s*(.*?)\s*", text or "")
    if not m:
        raise UnitError("Enter a number")
    value = float(m.group(1).replace(",", "."))
    if not np.isfinite(value):
        raise UnitError("Enter a finite number")
    unit = m.group(2)
    table = UNIT_KINDS[kind]
    if not unit:
        return value
    if kind == "dimensionless":
        raise UnitError(f"{unit} is not allowed here: enter a plain number")
    if unit not in table:
        lowered = {u.lower(): u for u in table}
        if unit.lower() in lowered and unit not in ("K", "k"):
            unit = lowered[unit.lower()]                   # "KPA", "Deg" -> "kPa", "deg"
        else:
            others = [k for k, t in UNIT_KINDS.items() if unit in t]
            if others:
                name = _KIND_NAMES[kind]
                article = "an" if name[0] in "aeiou" else "a"
                raise UnitError(f"{unit} is not {article} {name}")
            raise UnitError(f"unknown unit '{unit}'")
    scale, offset = table[unit]
    si = value * scale + offset
    if field_unit is None or not field_unit:
        return si
    if field_unit not in table:
        raise ValueError(f"field unit {field_unit!r} is not a {kind} unit")
    f_scale, f_offset = table[field_unit]
    return (si - f_offset) / f_scale
