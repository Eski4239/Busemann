"""M8.4: the Advanced numeric inputs are spin boxes with hard limits (angles 0-90°, recovery
0-1, γ 1-5/3), arrows stepping 0.1° / 0.01, unit-aware typing, a "Maximum 90°" note when a
typed value is clamped, the wheel only when focused, and text wide enough to read."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QStyle, QStyleOptionSpinBox  # noqa: E402

from busemann.theme import tokens  # noqa: E402
from busemann.widgets import SpinField  # noqa: E402

pytestmark = pytest.mark.gui

ANGLES = ("max_cowl", "wedge")


def _advanced(qtbot, window):
    window.resize(1280, 800)
    window.design_panel.advanced.toggle.setChecked(True)
    window.flight_panel.advanced.toggle.setChecked(True)
    window.state.update(max_cowl_enabled=True)          # max cowl field enabled
    qtbot.wait(150)
    return window.design_panel


def _type(field, text):
    field.edit.setText(text)
    field.edit.editingFinished.emit()


def _wheel(widget, steps):
    pos = QPointF(widget.rect().center())
    ev = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                     QPoint(0, 120 * steps), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def test_every_advanced_numeric_field_is_a_spin_box(qtbot, window):
    panel = _advanced(qtbot, window)
    for name in ("max_cowl", "wedge", "diffuser"):
        assert isinstance(getattr(panel, name), SpinField), name
    assert isinstance(window.flight_panel.gamma, SpinField)
    from busemann.widgets import NumberField
    for box in (panel.advanced, window.flight_panel.advanced):
        assert not box.findChildren(NumberField)                 # nothing left un-converted
    for name in ANGLES:
        f = getattr(panel, name)
        assert (f.minimum(), f.maximum(), f.spin.singleStep()) == (0.0, 90.0, 0.1)
    d = panel.diffuser
    assert (d.minimum(), d.maximum(), d.spin.singleStep()) == (0.0, 1.0, 0.01)


@pytest.mark.parametrize("name", ANGLES)
def test_typing_above_90_clamps_with_a_note(qtbot, window, name):
    field = getattr(_advanced(qtbot, window), name)
    _type(field, "120")
    assert field.value() == 90.0 and field.edit.text() == "90.0"
    assert field.note() == "Maximum 90°"
    assert "Maximum 90°" in field.error_label.text() and field.error_label.isVisible()
    _type(field, "120")                                           # again: still noted
    assert field.note() == "Maximum 90°"
    _type(field, "12")                                            # a valid value clears it
    assert field.value() == 12.0 and field.note() is None


def test_typed_units_still_work_and_bad_units_are_reported(qtbot, window):
    wedge = _advanced(qtbot, window).wedge
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        _type(wedge, "0.3 rad")
    assert window.state.inputs.cowl_wedge_deg == pytest.approx(17.1887, abs=1e-4)
    assert wedge.edit.text() == "17.2"
    _type(wedge, "2 rad")                                         # 114.6° -> 90°
    assert wedge.value() == 90.0 and wedge.note() == "Maximum 90°"
    _type(wedge, "2 ft")
    assert "not an angle" in wedge.error() and wedge.value() == 90.0


def test_the_core_physics_check_still_reports_on_the_field(qtbot, window):
    """A lip wedge above 30° is allowed by the field but rejected by the core: the error
    is shown on the wedge field, with the clamp note when there is one."""
    wedge = _advanced(qtbot, window).wedge
    _type(wedge, "45")
    qtbot.waitUntil(lambda: wedge.error() is not None, timeout=5000)
    assert "0-30" in wedge.error() and wedge.note() is None
    _type(wedge, "4")
    qtbot.waitUntil(lambda: wedge.error() is None, timeout=5000)


def test_recovery_clamps_to_one_and_steps_by_a_hundredth(qtbot, window):
    d = _advanced(qtbot, window).diffuser
    _type(d, "1.5")
    assert d.value() == 1.0 and d.note() == "Maximum 1"
    qtbot.waitUntil(lambda: window.state.inputs.diffuser_recovery == 1.0, timeout=5000)
    d.spin.stepUp()
    assert d.value() == 1.0                                       # the arrow stops at 1
    d.spin.stepDown()
    assert d.value() == pytest.approx(0.99)
    _type(d, "-2")
    assert d.value() == 0.0 and d.note() == "Minimum 0" and "Must be > 0" in d.error()
    assert window.state.inputs.diffuser_recovery == pytest.approx(0.99)   # 0 not applied


@pytest.mark.parametrize("name", ANGLES)
def test_up_arrow_stops_at_90(qtbot, window, name):
    field = getattr(_advanced(qtbot, window), name)
    _type(field, "89.9")
    field.spin.stepUp()
    assert field.value() == 90.0
    field.spin.stepUp()
    assert field.value() == 90.0
    field.spin.setFocus()
    qtbot.waitUntil(field.spin.hasFocus, timeout=1000)
    qtbot.keyClick(field.spin, Qt.Key.Key_Up)                    # keyboard arrow
    assert field.value() == 90.0
    assert not (field.spin.stepEnabled() & field.spin.StepEnabledFlag.StepUpEnabled)
    assert field.note() is None                                  # arrows: no note needed


def test_focused_wheel_steps_and_clamps_at_90(qtbot, window):
    field = _advanced(qtbot, window).max_cowl
    _type(field, "89.8")
    field.spin.setFocus()
    qtbot.waitUntil(field.spin.hasFocus, timeout=1000)
    _wheel(field.spin, 1)
    assert field.value() == pytest.approx(89.9)
    for _ in range(5):
        _wheel(field.spin, 1)
    assert field.value() == 90.0                                  # clamped by the wheel
    _wheel(field.spin, -1)
    assert field.value() == pytest.approx(89.9)


def test_unfocused_wheel_does_not_change_the_value(qtbot, window):
    field = _advanced(qtbot, window).diffuser
    assert field.spin.property("_wheel_guard")
    assert field.spin.focusPolicy() == Qt.FocusPolicy.StrongFocus
    window.canvas.setFocus()
    qtbot.waitUntil(lambda: not field.spin.hasFocus(), timeout=1000)
    before = field.value()
    _wheel(field.spin, 1)
    _wheel(field.spin, -3)
    assert field.value() == before


def test_text_is_visible_while_typing(qtbot, window):
    """The M8.3 bug: the fields were 30 px wide, so the text scrolled out of view."""
    panel = _advanced(qtbot, window)
    fields = [panel.max_cowl, panel.wedge, panel.diffuser, window.flight_panel.gamma]
    for f in fields:
        spin = f.spin
        assert spin.width() >= 96, (f, spin.width())
        spin.setFocus()
        qtbot.waitUntil(spin.hasFocus, timeout=1000)
        spin.lineEdit().setText("88.88")
        opt = QStyleOptionSpinBox()
        spin.initStyleOption(opt)
        room = spin.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, opt,
                                           QStyle.SubControl.SC_SpinBoxEditField, spin)
        edit = spin.lineEdit()
        assert edit.fontMetrics().horizontalAdvance("88.888") + 8 <= min(room.width(),
                                                                         edit.width())
        assert edit.palette().color(edit.foregroundRole()).name().lower() == \
            tokens.COLORS["text"].lower()                         # normal text colour
        assert edit.cursorRect().right() <= edit.width()           # caret inside the field
        assert edit.isVisible() and edit.hasFocus()
        f.set_value(f.value())                                     # restore the text
