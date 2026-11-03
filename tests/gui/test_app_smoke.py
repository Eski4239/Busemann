import re

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

pytestmark = pytest.mark.gui


def _wait_design(qtbot, win):
    """Wait for the next accepted design result (debounce + worker)."""
    with qtbot.waitSignal(win.state.design_ready, timeout=5000):
        pass


def _type(qtbot, field, text):
    field.edit.selectAll()
    qtbot.keyClicks(field.edit, text)
    qtbot.keyClick(field.edit, Qt.Key.Key_Return)


def test_app_starts_with_layout_and_kpis(window):
    assert window.windowTitle() == "Busemann — Untitled"
    assert window.minimumWidth() == 1280 and window.minimumHeight() == 800
    assert window.left_panel.width() == 300
    assert window.right_panel.width() == 320
    assert window.results_panel.cards["recovery_total"].text() != "—"
    assert window.results_panel.cards["mass_flow"].text() != "—"


def test_changing_mach_updates_kpis(qtbot, window):
    before = window.results_panel.cards["recovery_total"].text()
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        _type(qtbot, window.flight_panel.mach.field, "2.00")
    assert window.state.inputs.mach == 2.0
    assert window.results_panel.cards["recovery_total"].text() != before


def test_slider_moves_mach(qtbot, window):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.flight_panel.mach.slider.setValue(window.flight_panel.mach.slider.maximum())
    assert window.state.inputs.mach == pytest.approx(7.0)
    assert window.flight_panel.mach.field.value() == pytest.approx(7.0)


def test_out_of_range_mach_is_reported_not_clamped(qtbot, window):
    _type(qtbot, window.flight_panel.mach.field, "9.5")
    assert window.flight_panel.mach.field.error() is not None
    assert window.state.inputs.mach == 3.0


def test_x15_preset_shows_real_gas_warning(qtbot, window):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.flight_panel.preset.setCurrentText("X-15 record")
    assert window.state.inputs.mach == 6.7
    assert any("Real-gas" in w for w in window.results_panel.warning_texts())
    assert window.results_panel.warnings_box.isVisibleTo(window)


def test_units_toggle_relabels(qtbot, window):
    window.flight_panel.units.button("Imperial").click()
    assert window.state.inputs.units == "Imperial"
    assert window.flight_panel.readout.unit("p") == "psi"
    assert window.flight_panel.altitude.unit_label.text() == "ft"
    assert window.design_panel.capture.unit_label.text() == "in"
    assert window.results_panel.cards["mass_flow"].unit_label.text() == "lbm/s/ft"
    assert window.units_label.text() == "Imperial"


def test_manual_atmosphere_mode(qtbot, window):
    window.flight_panel.mode.button("manual").click()
    assert window.flight_panel.manual_row.isVisibleTo(window)
    with qtbot.waitSignal(window.state.freestream_ready, timeout=5000):
        _type(qtbot, window.flight_panel.pressure, "10")   # kPa
    assert window.state.freestream.p == pytest.approx(10000.0)


def test_custom_angle_detachment_shown_inline(qtbot, window):
    window.state.update(mach=2.0, n_ramps=1)
    _wait_design(qtbot, window)
    window.design_panel.method.button("custom").click()
    _wait_design(qtbot, window)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        _type(qtbot, window.design_panel.angle_fields[0], "30")
    error = window.design_panel.angle_fields[0].error()
    assert error and "detachment limit" in error
    assert window.results_panel.cards["recovery_total"].text() == "—"


def test_panels_collapse(window):
    window.toggle_left.trigger()
    assert not window.left_panel.isVisible()
    window.toggle_right.trigger()
    assert not window.right_panel.isVisible()
    window.toggle_left.trigger()
    assert window.left_panel.isVisible()


def test_status_bar(window):
    # the start-up design may already be in the api cache from an earlier test
    text = window.compute_label.text()
    assert re.fullmatch(r"design (cached|\d+ ms) · sweep \d+ ms", text), text
    assert window.model_label.text() == "Ideal gas, γ = 1.40"


def test_inletdesign_gui_subcommand_launches_app(monkeypatch):
    import busemann.app
    from inletdesign.cli import main

    calls = []
    monkeypatch.setattr(busemann.app, "main", lambda argv: calls.append(argv) or 0)
    assert main(["gui"]) == 0
    assert calls == [[]]


def test_status_says_cached_on_a_cache_hit(qtbot, window):
    from inletdesign import api

    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=3.137)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=3.0)                     # computed at start-up: cached
    assert window.compute_label.text().startswith("design cached · sweep ")
    assert window.state.compute_cached
    api._design_cached.cache_clear()
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=3.137)
    assert re.fullmatch(r"design \d+ ms · sweep \d+ ms",           # cache was cleared
                        window.compute_label.text())
    assert not window.state.compute_cached
