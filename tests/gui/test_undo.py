"""Undo/redo (M7): a drag is one step, undo restores identical api results, redo is cleared
by a new edit, project load / New clear the history, view settings are not recorded."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from busemann import project as P  # noqa: E402
from busemann.inputs import Inputs, preset_changes  # noqa: E402

pytestmark = pytest.mark.gui


def _wait_design(qtbot, window, action):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        action()


def test_slider_drag_is_one_step_and_undo_restores_results(qtbot, window):
    stack = window.undo.stack
    original = window.state.design
    slider = window.flight_panel.mach.slider
    start = slider.value()
    slider.setSliderDown(True)
    for k in range(1, 21):                                  # 20 drag steps, 3.00 -> 2.80
        slider.setValue(start - k)
        qtbot.wait(5)
    slider.setSliderDown(False)
    qtbot.waitUntil(lambda: window.state.design is not None
                    and window.state.design.inputs.M == pytest.approx(2.80), timeout=5000)
    assert stack.count() == 1
    assert window.undo_action.text() == "Undo Mach 3.00 → 2.80"
    _wait_design(qtbot, window, window.undo_action.trigger)
    assert window.state.inputs.mach == 3.0
    assert window.state.design == original                  # identical api results
    assert window.redo_action.text() == "Redo Mach 3.00 → 2.80"
    _wait_design(qtbot, window, window.redo_action.trigger)
    assert window.state.inputs.mach == pytest.approx(2.80)


def test_new_edit_after_undo_clears_redo(qtbot, window):
    _wait_design(qtbot, window, lambda: window.state.update(n_ramps=3))
    _wait_design(qtbot, window, window.undo_action.trigger)
    assert window.undo.stack.canRedo()
    _wait_design(qtbot, window, lambda: window.state.update(n_ramps=4))
    assert not window.undo.stack.canRedo()
    assert window.undo_action.text() == "Undo Ramps 2 → 4"


def test_field_edit_and_preset_are_single_steps(qtbot, window):
    field = window.flight_panel.altitude
    field.edit.setText("65000 ft")
    _wait_design(qtbot, window, field.edit.editingFinished.emit)
    assert window.state.inputs.altitude_m == pytest.approx(19812.0)
    assert window.undo.stack.count() == 1
    assert window.undo_action.text() == "Undo Altitude 20.00 km → 19.81 km"
    _wait_design(qtbot, window,
                 lambda: window.state.update(**preset_changes("Concorde cruise")))
    assert window.undo.stack.count() == 2
    assert window.undo_action.text() == "Undo Preset Concorde cruise"
    _wait_design(qtbot, window, window.undo_action.trigger)
    assert window.state.inputs.mach == 3.0 and window.state.inputs.preset is None


def test_view_settings_and_off_design_mach_are_not_recorded(qtbot, window):
    window.layer_actions["grid"].setChecked(True)
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.6)
    window.state.update(units="Imperial")
    assert window.undo.stack.count() == 0


def test_open_and_new_clear_history(qtbot, window, tmp_path):
    _wait_design(qtbot, window, lambda: window.state.update(n_ramps=3))
    assert window.undo.stack.count() == 1
    path = tmp_path / "p.dxf"
    P.save(path, Inputs(mach=2.5), None)
    _wait_design(qtbot, window, lambda: window.project.open_path(path, ask=False))
    assert window.undo.stack.count() == 0
    _wait_design(qtbot, window, lambda: window.state.update(mach=2.7))
    _wait_design(qtbot, window, window.project.new)
    assert window.undo.stack.count() == 0 and not window.undo.stack.canRedo()


def test_edit_menu_and_shortcuts(window):
    texts = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert texts[:2] == ["File", "Edit"]
    assert window.undo_action.shortcut().toString() == "Ctrl+Z"
    assert "Ctrl+Shift+Z" in [s.toString() for s in window.redo_action.shortcuts()]
