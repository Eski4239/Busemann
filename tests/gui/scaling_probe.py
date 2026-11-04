"""Subprocess probe for test_scaling.py: build the main window at QT_SCALE_FACTOR (set by the
caller) at its minimum size and report clipped widgets as JSON on stdout.

Usage: python scaling_probe.py [design_tab.png [offdesign_tab.png]]
"""
import json
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QAbstractScrollArea, QApplication, QSizePolicy, QWidget  # noqa: E402

from busemann.app import MainWindow, setup_application, setup_high_dpi  # noqa: E402


def settle(ms=600):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def clipped_widgets(window):
    """Visible widgets smaller than their minimum size hint (layout could not honour it)."""
    problems = []
    ignored = QSizePolicy.Policy.Ignored
    for w in window.findChildren(QWidget):
        if not w.isVisible() or w.window() is not window:
            continue
        if w.parent() is not None and isinstance(w.parent(), QAbstractScrollArea):
            continue                      # scroll-area internals (viewport, bars)
        if type(w.parent()).__name__ == "QLineEdit":
            continue                      # line-edit internals (action buttons, e.g. lock)
        hint = w.minimumSizeHint()
        policy = w.sizePolicy()
        short_w = policy.horizontalPolicy() != ignored and hint.width() > 0 and \
            w.width() < min(hint.width(), w.maximumWidth()) - 1
        short_h = policy.verticalPolicy() != ignored and hint.height() > 0 and \
            w.height() < min(hint.height(), w.maximumHeight()) - 1
        parent = w.parentWidget()
        scroll_content = parent is not None and isinstance(parent.parentWidget(),
                                                           QAbstractScrollArea)
        overflow = parent is not None and not scroll_content and not             parent.rect().adjusted(-1, -1, 1, 1).contains(w.geometry())
        if short_w or short_h or overflow:
            problems.append({"widget": type(w).__name__, "name": w.objectName(),
                             "size": [w.width(), w.height()],
                             "min_hint": [hint.width(), hint.height()],
                             "overflows_parent": bool(overflow)})
    return problems


def panel_overflow(window):
    """Side-panel content wider than its scroll viewport (would be cut off on the right),
    and station-table columns too narrow for their text."""
    problems = [{"widget": "StationTable", "name": f"column {c}", "size": [have, 0],
                 "min_hint": [need, 0]}
                for c, need, have in window.results_panel.station_table.column_overflow()]
    for panel in (window.left_panel, window.right_panel):
        if not panel.isVisible():
            continue
        if hasattr(panel, "currentWidget"):        # right panel: Results | Verification tabs
            panel = panel.currentWidget()
        body = panel.widget()
        if body.minimumSizeHint().width() > panel.viewport().width() + 1:
            problems.append({"widget": "panel body", "name": panel.objectName(),
                             "size": [panel.viewport().width(), 0],
                             "min_hint": [body.minimumSizeHint().width(), 0]})
    return problems


def main():
    setup_high_dpi()
    app = QApplication([])
    setup_application(app)
    window = MainWindow()
    window.resize(window.minimumSize())
    window.show()
    settle()
    for n_ramps in (2, 4):                # 4 ramps: the longest panel content
        window.state.update(n_ramps=n_ramps)
        settle()
    window.state.update(n_ramps=2)
    settle()
    problems = clipped_widgets(window) + panel_overflow(window)
    window.tabs.setCurrentWidget(window.offdesign_tab)       # the off-design tab too
    settle()
    problems += [dict(p, tab="Off-design")
                 for p in clipped_widgets(window) + panel_overflow(window)]
    result = {"dpr": window.devicePixelRatioF(), "size": [window.width(), window.height()],
              "problems": problems}
    window.explain_action.setChecked(True)                     # drawer open: narrow centre
    settle()
    problems += [dict(p, tab="Off-design + Explain")
                 for p in clipped_widgets(window) + panel_overflow(window)]
    if len(sys.argv) > 2:
        window.grab().save(sys.argv[2])
    window.explain_action.setChecked(False)
    settle(400)
    window.tabs.setCurrentWidget(window.canvas)
    settle(200)
    # M8.2: every column of the flow-regions and ramp tables fully visible, including the
    # widest ramp table (custom angles, 4 ramps, with the ∂η/∂θ column)
    window.state.update(n_ramps=4, method="custom", custom_angles=(6.0, 7.0, 8.0, 9.0))
    settle(1500)
    problems += [{"widget": "RampTable", "name": f"row {r} col {c}", "size": [have, 0],
                  "min_hint": [need, 0], "tab": "custom 4 ramps"}
                 for r, c, need, have in window.design_panel.ramp_table.column_overflow()]
    problems += [{"widget": "StationTable", "name": f"column {c}", "size": [have, 0],
                  "min_hint": [need, 0], "tab": "custom 4 ramps"}
                 for c, need, have in window.results_panel.station_table.column_overflow()]
    window.state.update(n_ramps=2, method="oswatitsch")
    settle()
    if len(sys.argv) > 1:
        window.grab().save(sys.argv[1])
    window.state.shutdown()
    print(json.dumps(result))


if __name__ == "__main__":
    main()
