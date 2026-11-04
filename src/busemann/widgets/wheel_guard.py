"""Mouse wheel over value widgets (M8.2 bug 4).

Sliders, combo boxes and spin boxes change their value on the wheel even without focus, so
scrolling a panel past one changes an input. With the guard they take Qt.StrongFocus (the
wheel never gives focus) and ignore the wheel until focused: the wheel then scrolls the
enclosing panel instead.
"""
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea, QAbstractSlider, QAbstractSpinBox, QApplication, QComboBox, QScrollBar,
)

from ..crashlog import guarded

GUARDED_TYPES = (QAbstractSlider, QComboBox, QAbstractSpinBox)


def _scroll_area(widget):
    w = widget.parentWidget()
    while w is not None:
        if isinstance(w, QAbstractScrollArea):
            return w
        w = w.parentWidget()
    return None


class WheelGuard(QObject):
    @guarded()
    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Wheel or obj.hasFocus():
            return False
        area = _scroll_area(obj)
        if area is not None:
            QApplication.sendEvent(area.verticalScrollBar(), event)
        event.accept()
        return True                         # the unfocused widget never sees the wheel


def install(root, guard=None):
    """Guard every slider / combo / spin box under `root` (scroll bars excluded). Returns the
    guard (keep a reference: the parent `root` owns it)."""
    guard = guard or WheelGuard(root)
    for cls in GUARDED_TYPES:
        for w in root.findChildren(cls):
            if isinstance(w, QScrollBar) or w.property("_wheel_guard"):
                continue
            w.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            w.installEventFilter(guard)
            w.setProperty("_wheel_guard", True)
    return guard
