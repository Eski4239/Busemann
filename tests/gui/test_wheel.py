"""M8.2 bug 4: the mouse wheel changes sliders / combo boxes only when they have focus;
otherwise it scrolls the panel."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QComboBox, QSlider  # noqa: E402

pytestmark = pytest.mark.gui


def _wheel(widget, steps=-1):
    pos = QPointF(widget.rect().center())
    ev = QWheelEvent(pos, QPointF(widget.mapToGlobal(pos.toPoint())), QPoint(0, 0),
                     QPoint(0, 120 * steps), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def test_every_value_widget_is_guarded(window):
    for cls in (QSlider, QComboBox):
        widgets = [w for w in window.findChildren(cls) if w.isVisibleTo(window)]
        assert widgets
        for w in widgets:
            assert w.focusPolicy() == Qt.FocusPolicy.StrongFocus, w.objectName()
            assert w.property("_wheel_guard")


@pytest.mark.parametrize("getter", [lambda w: w.flight_panel.mach.slider,
                                    lambda w: w.design_panel.capture_mode])
def test_unfocused_wheel_scrolls_the_panel_not_the_value(qtbot, window, getter):
    window.resize(1280, 700)                       # left panel needs scrolling
    qtbot.wait(100)
    widget = getter(window)
    bar = window.left_panel.verticalScrollBar()
    assert bar.maximum() > 0
    window.canvas.setFocus()
    qtbot.waitUntil(lambda: not widget.hasFocus(), timeout=1000)
    value = widget.value() if isinstance(widget, QSlider) else widget.currentIndex()
    bar.setValue(bar.maximum() // 2)
    before = bar.value()
    _wheel(widget, -1)
    now = widget.value() if isinstance(widget, QSlider) else widget.currentIndex()
    assert now == value                            # the value did not change
    assert bar.value() != before                   # the panel scrolled


def test_focused_slider_takes_the_wheel(qtbot, window):
    slider = window.flight_panel.mach.slider
    slider.setFocus()
    qtbot.waitUntil(slider.hasFocus, timeout=1000)
    value = slider.value()
    _wheel(slider, 1)
    assert slider.value() != value
