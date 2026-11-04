"""M8.2 bug 1: a corner drag froze the app, then Windows closed it.

PySide6 6.12 lets an exception raised in a Qt event handler or slot propagate into Qt's
event dispatch, which hangs the event loop. Every canvas handler, the AppState entry points
and the worker jobs are now guarded (busemann.crashlog): the exception is logged, the drag
ends, and the app keeps responding.
"""
import math
import time

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from busemann import crashlog  # noqa: E402
from busemann.canvas.scene import S  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture
def custom(qtbot, window):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(method="custom", custom_angles=(9.0, 10.0))
    qtbot.waitUntil(lambda: not window.canvas.is_animating(), timeout=2000)
    return window


def _send(canvas, kind, pos, button, buttons):
    QApplication.sendEvent(canvas.viewport(), QMouseEvent(
        kind, pos, canvas.viewport().mapToGlobal(pos), button, buttons,
        Qt.KeyboardModifier.NoModifier))


def _pointer(canvas, theta, r=150.0):
    drag = canvas.corner_drag
    a = math.radians(drag["flow_in"] + theta)
    p = drag["pivot"]
    return canvas.viewportTransform().map(S((p[0] + r * math.cos(a), p[1] + r * math.sin(a))))


def test_an_exception_mid_drag_is_logged_and_the_drag_ends(qtbot, custom, monkeypatch):
    canvas, state = custom.canvas, custom.state
    before = crashlog.logged_count()
    calls = {"n": 0}
    real = canvas.drag_corner_to

    def flaky(pos, fine=False):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("injected failure in the drag")
        return real(pos, fine)

    monkeypatch.setattr(canvas, "drag_corner_to", flaky)
    _send(canvas, QEvent.Type.MouseButtonPress, canvas.handle_view_pos(1),
          Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    assert state.dragging
    for theta in (10.5, 11.0, 11.5, 12.0):
        if canvas.corner_drag is None:
            break
        _send(canvas, QEvent.Type.MouseMove, _pointer(canvas, theta), Qt.MouseButton.NoButton,
              Qt.MouseButton.LeftButton)
    assert crashlog.logged_count() == before + 1
    assert canvas.corner_drag is None and not state.dragging      # recovered, not stuck
    qtbot.wait(50)                                                 # the event loop still runs
    with qtbot.waitSignal(state.design_ready, timeout=5000):       # and the app still works
        state.update(custom_angles=(9.5, 10.0))
    assert state.design is not None


@pytest.mark.qt_no_exception_capture          # see what PySide itself does with the exception
def test_a_failing_listener_does_not_stop_the_pipeline(qtbot, custom):
    """PySide prints a slot's exception and continues the emit (only exceptions escaping
    overridden event handlers hang the loop, and those are guarded)."""
    state = custom.state

    def bad(*_):
        raise RuntimeError("injected failure in a listener")

    state.design_ready.connect(bad)
    try:
        with qtbot.waitSignal(state.design_ready, timeout=5000):
            state.update(custom_angles=(9.0, 11.0))
    finally:
        state.design_ready.disconnect(bad)
    with qtbot.waitSignal(state.design_ready, timeout=5000):
        state.update(custom_angles=(9.0, 12.0))
    assert state.design.ramp_angles_deg == (9.0, 12.0)


def test_a_failing_worker_job_reports_an_error(qtbot, custom, monkeypatch):
    from inletdesign import api

    def boom(design):
        raise RuntimeError("injected worker failure")

    monkeypatch.setattr(api, "optimum_gap", boom)
    with qtbot.waitSignal(custom.state.design_ready, timeout=5000) as blocker:
        custom.state.update(custom_angles=(9.0, 10.5))
    assert blocker.args[0] is None and "internal error" in blocker.args[1]
    monkeypatch.undo()
    with qtbot.waitSignal(custom.state.design_ready, timeout=5000):
        custom.state.update(custom_angles=(9.0, 10.0))
    assert custom.state.design is not None


def test_dense_drag_never_stalls_the_ui(qtbot, custom):
    """300 moves ~1 ms apart over the full angle range: no step blocks the UI for > 1 s."""
    canvas = custom.canvas
    _send(canvas, QEvent.Type.MouseButtonPress, canvas.handle_view_pos(0),
          Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton)
    worst, last = 0.0, time.perf_counter()
    for j in range(300):
        theta = 1.0 + 40.0 * abs(math.sin(j / 300 * math.pi))
        _send(canvas, QEvent.Type.MouseMove, _pointer(canvas, theta), Qt.MouseButton.NoButton,
              Qt.MouseButton.LeftButton)
        QApplication.processEvents()
        now = time.perf_counter()
        worst, last = max(worst, now - last), now
    _send(canvas, QEvent.Type.MouseButtonRelease, _pointer(canvas, 5.0),
          Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton)
    assert worst < 1.0, f"longest UI step {worst * 1000:.0f} ms"
    qtbot.waitUntil(lambda: custom.state.design is not None, timeout=5000)


def test_garbage_collection_runs_on_the_gui_thread_only(qtbot, window):
    """The full suite crashed with "access violation ... Garbage-collecting" on a pooled
    worker thread: the cyclic GC freed Qt objects there. Automatic GC is off; a GUI-thread
    timer collects instead."""
    import gc
    import threading
    import weakref

    from busemann import gc_guard

    assert not gc.isenabled() and gc_guard._guard is not None
    collected_on = []

    class Cycle:
        pass

    a, b = Cycle(), Cycle()
    a.b, b.a = b, a
    gone = weakref.finalize(a, lambda: collected_on.append(threading.current_thread()))
    del a, b
    gc_guard._guard.thresholds = (-1, -1, -1)            # full collection at the next tick
    try:
        qtbot.waitUntil(lambda: not gone.alive, timeout=3000)
    finally:
        gc_guard._guard.thresholds = gc.get_threshold()
    assert collected_on == [threading.main_thread()]
