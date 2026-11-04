"""Typed input with units (units.parse_quantity): every accepted unit and every error."""
import math

import pytest

from inletdesign import units as U
from inletdesign.units import UnitError, parse_quantity


# Expected SI values are exact definitions: 1 ft = 0.3048 m, 1 in = 0.0254 m,
# 1 lbm = 0.45359237 kg, 1 psi = 1 lbf/in^2, 1 atm = 101325 Pa, 1 bar = 1e5 Pa,
# T[K] = T[degC] + 273.15, T[K] = (T[degF] + 459.67) / 1.8, T[K] = T[R] / 1.8, pi rad = 180 deg.
@pytest.mark.parametrize("kind, text, si", [
    ("length", "2 m", 2.0), ("length", "250 cm", 2.5), ("length", "125 mm", 0.125),
    ("length", "0.5 km", 500.0), ("length", "10 ft", 3.048), ("length", "4 in", 0.1016),
    ("altitude", "20 km", 20000.0), ("altitude", "1500 m", 1500.0),
    ("altitude", "65000 ft", 19812.0), ("altitude", "65 kft", 19812.0),
    ("temperature", "220 K", 220.0), ("temperature", "-56.5 °C", 216.65),
    ("temperature", "-56.5 C", 216.65), ("temperature", "32 °F", 273.15),
    ("temperature", "-40 F", 233.15), ("temperature", "491.67 R", 273.15),
    ("temperature", "0 °R", 0.0),
    ("pressure", "10000 Pa", 1e4), ("pressure", "10 kPa", 1e4), ("pressure", "1 bar", 1e5),
    ("pressure", "1 psi", U.LBF / U.INCH**2), ("pressure", "1 atm", 101325.0),
    ("mass_flow", "50 kg/s", 50.0), ("mass_flow", "100 lb/s", 45.359237),
    ("angle", "15 °", 15.0), ("angle", "15 deg", 15.0), ("angle", "1 rad", 180.0 / math.pi),
])
def test_every_unit_converts_to_si(kind, text, si):
    assert parse_quantity(text, kind) == pytest.approx(si, rel=1e-12, abs=1e-12)
    unit = text.split(" ", 1)[1]
    assert unit in U.accepted_units(kind)


@pytest.mark.parametrize("text, kind, field_unit, expected", [
    ("65000 ft", "altitude", "km", 19.812),
    ("20", "altitude", "km", 20.0),                    # bare number: the field's unit
    ("-56.5 C", "temperature", "K", 216.65),
    ("300 K", "temperature", "°R", 540.0),
    ("-40 °C", "temperature", "°F", -40.0),
    ("101.325 kPa", "pressure", "psi", 101325.0 / (U.LBF / U.INCH**2)),
    ("0.1 m", "length", "in", 0.1 / 0.0254),
    ("2,5 bar", "pressure", "kPa", 250.0),            # decimal comma
    ("65000ft", "altitude", "km", 19.812),             # no space
    ("1e5 Pa", "pressure", "kPa", 100.0),
    ("2.2", "dimensionless", None, 2.2),
    (" 3 ", "dimensionless", None, 3.0),
    ("5 KPA", "pressure", "kPa", 5.0),                 # case-insensitive except K
])
def test_conversion_into_the_field_unit(text, kind, field_unit, expected):
    assert parse_quantity(text, kind, field_unit) == pytest.approx(expected, rel=1e-12)


@pytest.mark.parametrize("text, kind, message", [
    ("65000 ft", "temperature", "ft is not a temperature"),
    ("300 K", "altitude", "K is not an altitude"),
    ("2 kPa", "angle", "kPa is not an angle"),
    ("5 lb/s", "length", "lb/s is not a length"),
    ("1 m", "mass_flow", "m is not a mass flow"),
    ("5 parsecs", "length", "unknown unit 'parsecs'"),
    ("abc", "length", "Enter a number"),
    ("", "pressure", "Enter a number"),
    ("2 ft", "dimensionless", "ft is not allowed here"),
    ("inf", "length", "Enter a number"),
])
def test_errors_name_the_problem(text, kind, message):
    with pytest.raises(UnitError, match=message):
        parse_quantity(text, kind, None)


@pytest.mark.parametrize("text", ["220 K", "220K", "220 k", "220 kelvin", "220 degK", "220 °C",
                                  "220 Kelvin"])
def test_temperature_units_in_the_altitude_field_name_the_kind(text):
    """M8.2 bug 3: a temperature typed into the altitude field says what is wrong."""
    with pytest.raises(UnitError) as err:
        parse_quantity(text, "altitude", "km")
    message = str(err.value)
    assert " is not an altitude" in message and "unknown unit" not in message
    assert "(use km, m, ft, kft)" in message


@pytest.mark.parametrize("text, kind, first", [("5 mm", "altitude", "mm"),
                                               ("3 metres", "pressure", "m"),
                                               ("2 feet", "angle", "ft"),
                                               ("1 degrees", "length", "°")])
def test_aliases_of_other_kinds(text, kind, first):
    with pytest.raises(UnitError, match=rf"^{first} is not a"):
        parse_quantity(text, kind, None)


def test_kelvin_is_case_sensitive():
    with pytest.raises(UnitError):
        parse_quantity("300 k", "temperature", "K")          # k is not K


def test_every_display_unit_is_parseable():
    """Each field's display unit (SI and Imperial) is in its kind's table."""
    for quantity, kind in (("altitude", "altitude"), ("length", "length"),
                           ("pressure", "pressure"), ("temperature", "temperature")):
        for system in U.SYSTEMS:
            assert U.unit_label(quantity, system) in U.accepted_units(kind)
