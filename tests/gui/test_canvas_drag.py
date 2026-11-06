"""Ramp-corner dragging (addendum C4): snapped angles, the no-go wedge, one undo step."""
import math

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402

from inletdesign import api  # noqa: E402

from busemann.canvas.scene import S  # noqa: E402
from busemann.canvas.view import ramp_theta, snap_angle  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture
def custom(qtbot, window):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(method="custom", custom_angles=(9.0, 10.0))
    qtbot.waitUntil(lambda: not window.canvas.is_animating(), timeout=2000)
    return window


def _pointer(canvas, k, theta):
    """Viewport point that points ramp k at incremental angle theta from its start corner."""
    _, pivot, end = canvas.corner_handles()[k]
    flow_in = canvas.state.design.flow_angles_deg[k]
    if canvas.corner_drag is not None:          # the drag turns about the frozen pivot
        pivot, flow_in = canvas.corner_drag["pivot"], canvas.corner_drag["flow_in"]
    L = 4.0 * math.hypot(end[0] - pivot[0], end[1] - pivot[1])   # far: pixel rounding
    a = math.radians(flow_in + theta)
    target = (pivot[0] + L * math.cos(a), pivot[1] + L * math.sin(a))
    return canvas.viewportTransform().map(S(target))


def _mouse(canvas, kind, pos, buttons, modifiers=Qt.KeyboardModifier.NoModifier):
    button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else \
        Qt.MouseButton.NoButton
    ev = QMouseEvent(kind, pos, canvas.viewport().mapToGlobal(pos), button, buttons, modifiers)
    {QEvent.Type.MouseButtonPress: canvas.mousePressEvent,
     QEvent.Type.MouseMove: canvas.mouseMoveEvent,
     QEvent.Type.MouseButtonRelease: canvas.mouseReleaseEvent}[kind](ev)


def test_helpers():
    assert ramp_theta((0.0, 0.0), (1.0, math.tan(math.radians(20.0))), 5.0) == \
        pytest.approx(15.0, abs=1e-12)
    assert snap_angle(10.04) == 10.0 and snap_angle(10.06) == 10.1
    assert snap_angle(10.044, fine=True) == 10.04


def test_handles_only_in_custom_mode(qtbot, window):
    assert window.canvas.corner_handles() == []
    assert window.offdesign_tab.canvas.corner_handles() == []


def test_drag_sets_snapped_angle_shows_no_go_and_is_one_undo_step(qtbot, custom):
    canvas, state = custom.canvas, custom.state
    count = custom.undo.stack.count()
    start = canvas.handle_view_pos(1)
    _mouse(canvas, QEvent.Type.MouseButtonPress, start, Qt.MouseButton.LeftButton)
    assert canvas.corner_drag is not None and canvas.corner_drag["k"] == 1 and state.dragging
    for theta in (10.5, 11.2, 12.04):
        _mouse(canvas, QEvent.Type.MouseMove, _pointer(canvas, 1, theta),
               Qt.MouseButton.LeftButton)
    assert state.inputs.custom_angles == (9.0, 12.0)                  # snapped to 0.1°
    M_k = state.design.regions[1].M if state.design else None
    t_max = canvas.corner_drag["theta_max"]
    assert t_max == pytest.approx(api.max_deflection(M_k), abs=1e-12)
    flow_in = canvas.corner_drag["flow_in"]
    hi = canvas.corner_drag["bounds"].hi                 # the stop: below detachment
    assert hi <= t_max - 0.5 + 1e-12
    assert canvas.no_go_angles() == pytest.approx((flow_in + hi, flow_in + 90.0))
    custom.grab()                                                     # paints the wedge
    _mouse(canvas, QEvent.Type.MouseMove, _pointer(canvas, 1, 12.04), Qt.MouseButton.LeftButton,
           Qt.KeyboardModifier.ShiftModifier)
    assert state.inputs.custom_angles == (9.0, 12.04)                 # Shift: 0.01°
    _mouse(canvas, QEvent.Type.MouseButtonRelease, _pointer(canvas, 1, 12.04),
           Qt.MouseButton.NoButton)
    assert canvas.corner_drag is None and not state.dragging
    qtbot.waitUntil(lambda: state.design is not None
                    and state.design.ramp_angles_deg == (9.0, 12.04)
                    and state.sensitivity is not None, timeout=5000)
    assert custom.undo.stack.count() == count + 1                     # one undo step
    with qtbot.waitSignal(state.design_ready, timeout=5000):
        custom.undo.stack.undo()
    assert state.inputs.custom_angles == (9.0, 10.0)


def test_drag_stops_at_the_upper_bound_with_a_note_and_comes_back(qtbot, custom):
    canvas, state = custom.canvas, custom.state
    canvas.start_corner_drag(1)                          # ramp 2: detachment-limited
    b = canvas.corner_drag["bounds"]
    assert b.reason == "detachment"
    theta = canvas.drag_corner_to(_pointer(canvas, 1, b.hi + 15.0))
    assert theta == pytest.approx(math.floor(b.hi * 10 + 1e-9) / 10)
    assert canvas.limit_note == f"Limit: detachment at {b.limit_deg:.2f}°"
    assert canvas.limit_note.startswith("Limit: detachment at ")
    custom.grab()                                        # paints the note
    back = canvas.drag_corner_to(_pointer(canvas, 1, 12.0))
    assert back == 12.0 and canvas.limit_note is None    # dragging back works at once
    canvas.drag_corner_to(_pointer(canvas, 1, b.hi + 5.0))
    canvas.finish_corner_drag()
    assert canvas.limit_note is not None                 # still visible after release...
    qtbot.waitUntil(lambda: canvas.limit_note is None, timeout=3000)   # ...then fades out
    qtbot.waitUntil(lambda: state.design is not None and state.design_error is None,
                    timeout=5000)


def test_drag_stops_at_the_lower_bound(qtbot, custom):
    canvas = custom.canvas
    canvas.start_corner_drag(0)
    theta = canvas.drag_corner_to(_pointer(canvas, 0, -10.0))
    assert theta == 0.5 and canvas.limit_note == "Limit: 0.5° minimum"
    canvas.finish_corner_drag()


def test_downstream_limit_keeps_the_design_valid(qtbot, window):
    """Raising ramp 1 at M 1.8 with 3 ramps used to make the flow behind it subsonic: the
    design errored and every handle vanished mid-drag."""
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=1.8, n_ramps=3, method="custom", custom_angles=(5.0, 5.0, 5.0))
    canvas, state = window.canvas, window.state
    canvas.start_corner_drag(0)
    b = canvas.corner_drag["bounds"]
    assert b.reason == "downstream" and b.detail.startswith("ramp 2 reaches its limit")
    canvas.drag_corner_to(_pointer(canvas, 0, 40.0))
    canvas.finish_corner_drag()
    qtbot.waitUntil(lambda: state.design is not None
                    and state.design.ramp_angles_deg[0] == state.inputs.custom_angles[0],
                    timeout=5000)
    assert state.design_error is None and len(canvas.corner_handles()) == 3


@pytest.mark.parametrize("M, n", [(3.0, 2), (1.8, 3), (2.2, 4), (2.5, 4)])
def test_full_sweep_of_every_handle_never_errors(qtbot, window, M, n):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=M, n_ramps=n, method="custom", custom_angles=(5.0,) * n)
    canvas, state = window.canvas, window.state
    for k in range(n):
        qtbot.waitUntil(lambda: len(canvas.corner_handles()) == n, timeout=5000)
        canvas.start_corner_drag(k)
        for theta in (1.0, 10.0, 20.0, 35.0, 60.0, 3.0):
            canvas.drag_corner_to(_pointer(canvas, k, theta))
        canvas.finish_corner_drag()
        qtbot.waitUntil(lambda: state.design is not None
                        and state.design.ramp_angles_deg == state.inputs.custom_angles,
                        timeout=5000)
        assert state.design_error is None


def test_recovery_and_gap_update_live(qtbot, custom):
    canvas, state = custom.canvas, custom.state
    gap0 = state.gap[0]
    canvas.start_corner_drag(0)
    canvas.drag_corner_to(_pointer(canvas, 0, 12.0))
    qtbot.waitUntil(lambda: state.design.ramp_angles_deg[0] == 12.0, timeout=5000)
    assert state.gap is not None and state.gap[0] != gap0               # during the drag
    card = custom.results_panel.cards["recovery_total"]
    assert card.text() == f"{state.design.recovery_total:.4f}"
    assert card.note("gap").startswith("Gap to optimum ")
    canvas.finish_corner_drag()


def test_method_buttons_are_named_and_explained(window):
    method = window.design_panel.method
    assert method.button("oswatitsch").text() == "Optimum angles"
    assert method.button("oswatitsch").toolTip() == (
        "Oswatitsch optimum: equal-strength shocks, maximum total-pressure recovery for this "
        "number of ramps.")
    assert method.button("custom").toolTip() == "Set each ramp angle yourself."
