"""Bundled example projects load cleanly and show what their names promise."""
import pytest

from busemann import project as P
from busemann.paths import resource_path
from inletdesign import api

EXAMPLES = ("validation_case", "x15_four_ramp", "m3_cowl_constrained")


def _load(name):
    inputs, view, warnings = P.load(resource_path("examples", f"{name}.busemann"))
    assert warnings == []
    return inputs


def _design(i):
    return api.design(i.mach, i.n_ramps, capture_height=i.capture_height_m, gamma=i.gamma,
                      max_cowl_angle=i.max_cowl_deg if i.max_cowl_enabled else None,
                      cowl_wedge=i.cowl_wedge_deg)


def test_validation_case():
    i = _load("validation_case")
    assert (i.mach, i.n_ramps, i.atmosphere_mode, i.p_pa, i.T_k) == (3.0, 2, "manual",
                                                                     10000.0, 220.0)
    assert _design(i).recovery_total == pytest.approx(0.7437, abs=1e-4)


def test_x15_four_ramp_has_real_gas_warning():
    i = _load("x15_four_ramp")
    assert (i.mach, i.n_ramps, i.preset) == (6.7, 4, "X-15 record")
    fs = api.freestream(i.mach, altitude_m=i.altitude_m, gamma=i.gamma)
    assert any(w.startswith("real-gas regime") for w in fs.warnings)


def test_m3_cowl_constrained():
    i = _load("m3_cowl_constrained")
    d = _design(i)
    assert d.constrained and d.cowl_angle_deg == pytest.approx(30.0, abs=1e-6)


def test_examples_are_shipped():
    import tomllib
    from pathlib import Path

    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text("utf-8"))
    assert "resources/examples/*.busemann" in data["tool"]["setuptools"]["package-data"]["busemann"]
    for name in EXAMPLES:
        assert resource_path("examples", f"{name}.busemann").is_file()
