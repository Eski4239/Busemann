"""Engine sizing (addendum C1, no Qt): capture height from a required mass flow."""
import pytest

from inletdesign import api


@pytest.fixture
def fs():
    return api.freestream(3.0, altitude_m=20000.0)


@pytest.mark.parametrize("h, width", [(0.1, 1.0), (0.137, 0.42), (2.5, 3.3)])
def test_sizing_to_the_captured_mass_flow_reproduces_h_c(fs, h, width):
    # self-consistency: mdot = rho V h w (A0/Ac = 1 at the design point), inverted
    mdot = api.mass_flow_total(fs, h, width)
    assert api.capture_height_for_mass_flow(fs, mdot, width) == pytest.approx(h, abs=1e-12)


def test_total_is_per_metre_times_width(fs):
    assert api.mass_flow_total(fs, 0.1, 2.0, 0.8) == \
        pytest.approx(2.0 * api.captured_mass_flow(fs, 0.1, 0.8), rel=1e-15)


def test_demand_ratio_identities(fs):
    h, w = 0.1, 1.5
    mdot = api.mass_flow_total(fs, h, w)
    assert api.demand_capture_ratio(fs, mdot, h, w) == pytest.approx(1.0, rel=1e-14)
    # a lower freestream Mach (same altitude) needs a larger capture ratio: rho V ~ M
    slow = api.freestream(2.0, altitude_m=20000.0)
    assert api.demand_capture_ratio(slow, mdot, h, w) == pytest.approx(1.5, rel=1e-12)


@pytest.mark.parametrize("args", [(0.0, 1.0), (-1.0, 1.0), (10.0, 0.0), (10.0, float("nan"))])
def test_bad_sizing_inputs_raise(fs, args):
    with pytest.raises(ValueError):
        api.capture_height_for_mass_flow(fs, *args)


def test_sized_state_helper_and_project_round_trip(tmp_path):
    from busemann import project as P
    from busemann.inputs import Inputs, freestream_for, sized_capture_height

    i = Inputs(capture_mode="mass_flow", mdot_kgps=30.0, inlet_width_m=0.8,
               diffuser_recovery=0.95)
    fs = freestream_for(i, i.mach)
    assert sized_capture_height(i, fs) == pytest.approx(30.0 / (fs.rho * fs.V * 0.8), rel=1e-15)
    assert sized_capture_height(Inputs(), fs) == Inputs().capture_height_m
    path = tmp_path / "s.busemann"
    P.save(path, i, None)
    loaded, _, warnings = P.load(path)
    assert loaded == i and warnings == []
