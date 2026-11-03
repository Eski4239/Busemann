"""Keyboard shortcuts, the cheat sheet and unit-aware fields (M7)."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

pytestmark = pytest.mark.gui


def test_tabs_and_placeholders(window):
    assert [window.tabs.tabText(i) for i in range(4)] == ["Design", "Off-design", "Analytics",
                                                          "Compare"]
    from PySide6.QtWidgets import QLabel
    labels = [lab.text() for lab in window.analytics_tab.findChildren(QLabel)]
    assert any("coming in M9" in t for t in labels)


def test_number_keys_switch_tabs_and_letters_trigger_actions(qtbot, window):
    window.canvas.setFocus()
    for k, key in enumerate((Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_1)):
        qtbot.keyClick(window, key)
        assert window.tabs.currentIndex() == (k + 1) % 4
    qtbot.keyClick(window.canvas, Qt.Key.Key_E)
    qtbot.waitUntil(lambda: not window.is_column_animating(), timeout=2000)
    assert window.explain_drawer.is_open
    qtbot.keyClick(window.canvas, Qt.Key.Key_E)
    assert not window.explain_drawer.is_open
    window.canvas.zoom(3.0)
    scale = window.canvas.scale_factor()
    qtbot.keyClick(window, Qt.Key.Key_F)
    assert window.canvas.scale_factor() != scale            # F fits again
    assert not window.play_action.isEnabled()               # Space: play/pause from M8
    check = window.design_panel.max_cowl_check
    window.design_panel.advanced.toggle.setChecked(True)
    check.setFocus()
    qtbot.waitUntil(check.hasFocus, timeout=1000)
    before = check.isChecked()
    qtbot.keyClick(check, Qt.Key.Key_Space)                 # Space still toggles a checkbox
    assert check.isChecked() is not before


def test_cheat_sheet(qtbot, window):
    qtbot.keyClick(window, Qt.Key.Key_Question, Qt.KeyboardModifier.ShiftModifier)
    overlay = window.shortcuts_overlay
    assert overlay.isVisible()
    keys = [k for k, _ in overlay.rows]
    for expected in ("F", "E", "Space", "1 – 4", "Ctrl+Z", "Ctrl+Shift+Z", "Ctrl+N", "Ctrl+O",
                     "Ctrl+S", "Ctrl+Shift+S", "?"):
        assert expected in keys
    qtbot.keyClick(overlay, Qt.Key.Key_Escape)
    assert not overlay.isVisible()


def test_shortcuts_do_not_fire_while_typing(qtbot, window):
    field = window.flight_panel.altitude.edit
    field.setFocus()
    qtbot.waitUntil(field.hasFocus, timeout=1000)
    field.selectAll()
    for key in (Qt.Key.Key_2, Qt.Key.Key_E, Qt.Key.Key_F, Qt.Key.Key_Question):
        qtbot.keyClick(field, key)
    assert window.tabs.currentIndex() == 0
    assert not window.explain_drawer.is_open and not window.shortcuts_overlay.isVisible()
    assert field.text().endswith("2ef?")                     # the keys went to the field
    before = window.undo.stack.count()
    qtbot.keyClick(field, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.undo.stack.count() == before              # Ctrl+Z undid the typing only


# --- unit-aware inputs ---------------------------------------------------------------------

def test_altitude_accepts_feet_and_rejects_kelvin(qtbot, window):
    field = window.flight_panel.altitude
    field.edit.setText("65000 ft")
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        field.edit.editingFinished.emit()
    assert window.state.inputs.altitude_m == pytest.approx(19812.0)
    assert field.edit.text() == "19.81" and field.error() is None
    field.edit.setText("300 K")
    field.edit.editingFinished.emit()
    assert field.error() == "K is not an altitude"
    assert window.state.inputs.altitude_m == pytest.approx(19812.0)     # unchanged
    assert "Accepts units: km, m, ft, kft" in field.toolTip()


@pytest.mark.parametrize("attr, text, expected, getter", [
    ("pressure", "1 atm", 101325.0, lambda i: i.p_pa),
    ("temperature", "-56.5 C", 216.65, lambda i: i.T_k),
])
def test_manual_atmosphere_fields_accept_units(qtbot, window, attr, text, expected, getter):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(atmosphere_mode="manual")
    field = getattr(window.flight_panel, attr)
    field.edit.setText(text)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        field.edit.editingFinished.emit()
    assert getter(window.state.inputs) == pytest.approx(expected)


def test_mach_and_capture_fields(qtbot, window):
    mach = window.flight_panel.mach.field
    mach.edit.setText("2.2 ft")
    mach.edit.editingFinished.emit()
    assert "not allowed here" in mach.error()
    capture = window.design_panel.capture
    capture.edit.setText("12 cm")
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        capture.edit.editingFinished.emit()
    assert window.state.inputs.capture_height_m == pytest.approx(0.12)
    wedge = window.design_panel.wedge
    wedge.edit.setText("0.05 rad")
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        wedge.edit.editingFinished.emit()
    assert window.state.inputs.cowl_wedge_deg == pytest.approx(2.8648, abs=1e-4)
