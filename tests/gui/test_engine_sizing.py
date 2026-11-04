"""Engine sizing, MIL-E-5008B KPI and the gap to optimum in the GUI (addendum C1-C3)."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from inletdesign import api  # noqa: E402

pytestmark = pytest.mark.gui


def _wait(qtbot, window, **changes):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(**changes)


def _switch(qtbot, window, mode):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        combo = window.design_panel.capture_mode
        combo.setCurrentIndex(combo.findData(mode))
        combo.activated.emit(combo.currentIndex())


def test_mode_switch_keeps_geometry_and_is_one_undo_step(qtbot, window):
    s = window.state
    before = s.design
    count = window.undo.stack.count()
    _switch(qtbot, window, "mass_flow")
    i = s.inputs
    assert i.capture_mode == "mass_flow" and i.inlet_width_m == 1.0
    assert i.mdot_kgps == pytest.approx(api.mass_flow_total(s.freestream, 0.1, 1.0), rel=1e-15)
    assert s.design.inputs.capture_height == pytest.approx(0.1, abs=1e-12)     # no jump
    assert s.design.geometry == before.geometry
    assert window.undo.stack.count() == count + 1
    panel = window.design_panel
    assert panel.capture.is_locked() and not panel.mdot.is_locked()
    with qtbot.waitSignal(s.design_ready, timeout=5000):
        window.undo.stack.undo()
    assert s.inputs.capture_mode == "height" and window.undo.stack.index() == count
    assert not panel.capture.is_locked() and panel.mdot.is_locked()


def test_mass_flow_drives_the_capture_height(qtbot, window):
    _switch(qtbot, window, "mass_flow")
    s = window.state
    _wait(qtbot, window, mdot_kgps=2.0 * s.inputs.mdot_kgps)
    assert s.design.inputs.capture_height == pytest.approx(0.2, rel=1e-10)
    _switch(qtbot, window, "height")                   # back: the sized height stays
    assert s.inputs.capture_height_m == pytest.approx(0.2, rel=1e-10)
    assert s.design.inputs.capture_height == pytest.approx(0.2, rel=1e-10)


def test_results_show_per_metre_and_total(qtbot, window):
    card = window.results_panel.cards["mass_flow"]
    assert not card.sub_label.isVisibleTo(card)          # no width: per metre only
    _wait(qtbot, window, inlet_width_m=0.5)
    total = window.state.total_mass_flow()
    assert total == pytest.approx(0.5 * window.state.captured_mass_flow(), rel=1e-15)
    sub = card.sub_label.text()
    assert sub.startswith("total ") and "through 0.5000 m" in sub


def test_off_design_supply_demand_chip_and_demand_line(qtbot, window):
    _switch(qtbot, window, "mass_flow")
    tab = window.offdesign_tab
    window.tabs.setCurrentWidget(tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.5)
    card = tab.card
    assert card.values["demanded"].isVisibleTo(card) and card.values["supplied"].isVisibleTo(card)
    s = window.state
    supplied, demanded = s.total_mass_flow(at_off_design=True), s.demanded_mass_flow()
    assert supplied < demanded                              # spillage and lower V below design
    assert card.chip.text() == f"shortfall {100 * (supplied - demanded) / demanded:+.1f} %"
    assert card.chip.property("kind") == "shortfall"
    xs, ys = tab.charts.curves["demand"].getData()
    k = min(range(len(xs)), key=lambda j: abs(xs[j] - 3.0))
    assert len(xs) == len(s.sweep.machs)
    # same altitude, so rho V ~ M: the demand ratio at M is (design M) / M (1 at design)
    assert ys[k] == pytest.approx(3.0 / xs[k], rel=1e-9)
    footer = tab.charts.note_legend.text().replace("\u00a0", " ")
    assert "fixed demand (engine matching not modelled)" in footer


def test_supply_rows_hidden_in_height_mode(qtbot, window):
    tab = window.offdesign_tab
    window.tabs.setCurrentWidget(tab)
    assert not tab.card.values["demanded"].isVisibleTo(tab.card)
    assert "demand" not in tab.charts.curves


def test_mil_kpi_and_diffuser(qtbot, window):
    card = window.results_panel.cards["recovery_total"]
    d = window.state.design
    face = d.recovery_total * 0.97
    mil = api.mil_recovery(3.0)
    assert card.text() == f"{d.recovery_total:.4f}"           # the value stays inviscid
    assert card.note("engine_face") == f"engine face ≈ {face:.4f} (× 0.970 diffuser, estimate)"
    pct = 100 * (face / mil - 1)
    assert card.note("mil") == \
        f"Engine-face estimate {abs(pct):.1f} % below MIL-E-5008B ({mil:.4f})"
    assert card.notes["mil"].property("level") == "error"
    _wait(qtbot, window, diffuser_recovery=1.0)
    assert card.text() == f"{d.recovery_total:.4f}"
    assert "× 1.000" in card.note("engine_face")
    charts = window.offdesign_tab.charts
    xs, ys = charts.curves["mil"].getData()
    assert ys[0] == pytest.approx(api.mil_recovery(xs[0]), rel=1e-15)
    fx, fy = charts.curves["rec_face"].getData()
    tx, ty = charts.curves["rec_tot"].getData()
    assert fy[0] == pytest.approx(ty[0] * 1.0)
    legend = charts.note_legend.text().replace(" ", " ")
    assert "MIL-E-5008B — compare with the engine-face estimate" in legend
    assert "diffuser 1.000" in legend


def test_gap_and_sensitivity_column_custom_only(qtbot, window):
    table = window.design_panel.ramp_table
    card = window.results_panel.cards["recovery_total"]
    assert not table.sensitivity_visible() and card.note("gap") is None
    _wait(qtbot, window, method="custom", custom_angles=(9.0, 10.0))
    d = window.state.design
    gap, _ = api.optimum_gap(d)
    assert card.note("gap") == f"Recovery {gap:.1f} % below the Oswatitsch optimum for 2 ramps"
    assert table.sensitivity_visible()
    sens = api.recovery_sensitivity(d)
    assert [table.text(r, 4) for r in range(2)] == [f"{v:+.4f}" for v in sens]
    _wait(qtbot, window, method="oswatitsch")
    assert not table.sensitivity_visible() and card.note("gap") is None
