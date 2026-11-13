"""M10 Compare model (no Qt): snapshots, metric list, B − A deltas, better directions, edge
cases (different ramp counts, failed designs, units). Expected values are self-consistency
checks against the api results and the unit table, not reference data."""
import dataclasses

import pytest

from busemann import compare as C
from busemann.inputs import Inputs
from inletdesign import api
from inletdesign import units as U

THREE = Inputs(n_ramps=3, max_cowl_enabled=True, max_cowl_deg=25.0)


@pytest.fixture(scope="module")
def pair():
    a = C.evaluate(C.snapshot_from_inputs(Inputs()), 2.75)
    b = C.evaluate(C.snapshot_from_inputs(THREE), 2.75)
    return a, b


def _rows(a, b, units="SI"):
    return {C.plain(r.label): r for r in C.table(a, b, units)}


def test_metric_list_and_better_directions():
    keys = [m.key for m in C.METRICS]
    assert keys == ["mach", "altitude", "p", "T", "n_ramps", "method", "ramp", "capture_height",
                    "width", "wedge", "recovery", "face", "mass_capture", "mdot_span",
                    "mdot_total", "M_post", "cowl_angle", "cowl_margin", "cd_cowl",
                    "sep_flags"]
    better = {m.key: m.better for m in C.METRICS if m.better}
    assert better == {"recovery": "higher", "face": "higher", "mass_capture": "higher",
                      "cowl_angle": "lower", "cowl_margin": "higher", "cd_cowl": "lower",
                      "sep_flags": "lower"}
    assert all(m.why and m.why.startswith(("Higher", "Lower")) for m in C.METRICS if m.better)
    assert all(m.group == "inputs" for m in C.METRICS if m.better is None and m.key in
               ("mach", "altitude", "p", "T", "n_ramps", "method", "ramp"))


def test_snapshot_matches_the_api_design():
    s = C.snapshot_from_inputs(THREE)
    d = api.design(3.0, 3, capture_height=0.1, max_cowl_angle=25.0)
    assert s.design.recovery_total == d.recovery_total and s.design.constrained
    assert s.sweep is not None and s.sweep.machs[-1] == pytest.approx(4.5)
    assert s.label == C.DEFAULT_NAME and C.Snapshot(Inputs(), name="x").label == "x"


def test_delta_is_b_minus_a_and_colour_follows_the_better_direction(pair):
    a, b = pair
    rows = _rows(a, b)
    rec = rows["Total recovery"]
    da, db = a.design.recovery_total, b.design.recovery_total
    assert rec.a == f"{da:.4f}" and rec.b == f"{db:.4f}"
    assert rec.delta == f"{db - da:+.4f}"
    assert rec.pct == f"{100 * (db - da) / da:+.1f} %"
    assert rec.verdict == ("better" if db > da else "worse") and rec.why
    cowl = rows["Cowl angle"]                          # lower is better
    assert b.design.cowl_angle_deg < a.design.cowl_angle_deg and cowl.verdict == "better"
    assert rows["Separation flags"].verdict == ("better" if b.sep_flags < a.sep_flags
                                                else "worse" if b.sep_flags > a.sep_flags
                                                else None)
    for neutral in ("M∞", "Altitude", "Ramps", "M after terminal shock", "Captured ṁ per span"):
        assert rows[neutral].verdict is None and rows[neutral].why is None
    assert rows["Mass capture A0/Ac"].verdict is None          # equal (1.000 on lip)


def test_engine_face_cell_and_mil(pair):
    a, b = pair
    row = _rows(a, b)["Engine face vs MIL-E-5008B"]
    face = a.design.recovery_total * a.snapshot.inputs.diffuser_recovery
    assert row.a == f"{face:.3f} vs {api.mil_recovery(3.0):.3f}"


def test_no_inlet_characteristic_row(pair):
    """The inlet characteristic (stable subcritical range) was removed before 1.0."""
    labels = [r.label for r in C.table(*pair)]
    assert not any("subcritical" in lb.lower() or "stable" in lb.lower() for lb in labels)
    assert not hasattr(pair[0], "stable_range")


def test_missing_ramps_show_a_dash(pair):
    a, b = pair
    rows = _rows(a, b)
    assert rows["Ramp 3 angle"].a == C.DASH and rows["Ramp 3 angle"].b != C.DASH
    assert rows["Ramp 3 angle"].delta == C.DASH
    assert rows["Ramp 1 angle"].a == f"{a.design.ramp_angles_deg[0]:.2f}°"
    assert "Ramp 4 angle" not in rows


@pytest.mark.parametrize("bad", [Inputs(n_ramps=2, method="custom", custom_angles=(30.0, 30.0)),
                                 Inputs(mach=0.8)])
def test_failed_design_in_either_slot_gives_dashes(pair, bad):
    good = pair[0]
    ev = C.evaluate(C.snapshot_from_inputs(bad), 2.75)
    assert ev.design is None and ev.snapshot.error
    for a, b in ((good, ev), (ev, good)):
        rows = C.table(a, b)
        results = rows[[r.label for r in rows].index("Results") + 1:]
        assert all(r.delta == C.DASH and r.verdict is None for r in results)
        side = [r.b if b is ev else r.a for r in results]
        assert all(t == C.DASH for t in side)


def test_empty_slot_a(pair):
    rows = C.table(None, pair[1])
    assert all(r.a in (C.DASH, "") for r in rows) and all(r.verdict is None for r in rows)


def test_units_convert_both_columns_and_keep_the_percentages(pair):
    a, b = pair
    si, imp = _rows(a, b, "SI"), _rows(a, b, "Imperial")
    p_a = U.to_display(a.snapshot.freestream.p, "pressure", "Imperial")
    assert imp["p∞"].a == f"{p_a:.3f} psi" and imp["p∞"].b.endswith(" psi")
    assert imp["Altitude"].a.endswith(" ft") and imp["Capture height"].b.endswith(" in")
    assert imp["T∞"].a.endswith(" °R") and imp["Captured ṁ per span"].a.endswith(" lbm/s/ft")
    for label in si:
        assert si[label].pct == imp[label].pct and si[label].verdict == imp[label].verdict


def test_total_mass_flow_row_only_with_a_width(pair):
    a, b = pair
    assert "Captured ṁ" not in _rows(a, b)
    wide = C.evaluate(C.snapshot_from_inputs(dataclasses.replace(THREE, inlet_width_m=2.0)),
                      2.75)
    row = _rows(a, wide)["Captured ṁ"]
    assert row.a == C.DASH and row.b == f"{wide.mdot_span * 2.0:.3f} kg/s"


def test_flight_conditions_differ():
    a, b = C.snapshot_from_inputs(Inputs()), C.snapshot_from_inputs(THREE)
    assert not C.flight_conditions_differ(a, b)
    for change in (dict(mach=2.8), dict(altitude_m=15000.0), dict(gamma=1.3),
                   dict(atmosphere_mode="manual", p_pa=5529.0, T_k=230.0)):
        other = C.snapshot_from_inputs(dataclasses.replace(Inputs(), **change))
        assert C.flight_conditions_differ(a, other), change
    assert not C.flight_conditions_differ(None, b)


def test_pin_is_a_deep_copy():
    s = C.snapshot_from_inputs(THREE)
    p = C.pin(s.inputs, s.design, s.error, s.freestream, s.sweep, "case")
    assert p.design == s.design and p.sweep == s.sweep and p.inputs == s.inputs
    assert p.design is not s.design and p.sweep is not s.sweep
    assert p.design.regions[0] is not s.design.regions[0]
    assert p.sweep.points[-1] is not s.sweep.points[-1] and p.name == "case"


def test_tsv(pair):
    rows = C.table(*pair)
    text = C.to_tsv(rows, "A: x", "B: y")
    lines = text.split("\n")
    assert lines[0] == "Metric\tA: x\tB: y\tΔ\tΔ%"
    assert len(lines) == len(rows) + 1 and all(line.count("\t") == 4 for line in lines)
    assert "<" not in text
