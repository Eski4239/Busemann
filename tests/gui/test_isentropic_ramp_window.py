"""Isentropic ramp window (M11): Tools menu wiring, worker-thread computation, hover, and
export/reopen routing. Leak safety is covered separately in test_leaks.py."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

pytestmark = pytest.mark.gui


def _open(qtbot, window):
    win = window.show_isentropic_ramp()
    qtbot.waitUntil(lambda: win.canvas.ramp is not None, timeout=5000)
    return win


def test_tools_menu_opens_the_window(qtbot, window):
    win = _open(qtbot, window)
    assert win.isVisible()
    assert win.canvas.ramp.M_f == pytest.approx(1.6375, abs=1e-3)


@pytest.mark.ui
def test_reopening_from_the_menu_raises_the_same_window(qtbot, window):
    win1 = _open(qtbot, window)
    win2 = window.show_isentropic_ramp()
    assert win1 is win2


def test_follow_main_design_updates_on_design_change(qtbot, window):
    win = _open(qtbot, window)
    assert win.follow_main.isChecked()
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=3.5)
    qtbot.waitUntil(lambda: win.m_inf_field.value() == pytest.approx(3.5), timeout=5000)


def test_delta_mf_toggle_recomputes(qtbot, window):
    win = _open(qtbot, window)
    win.follow_main.setChecked(False)
    win.mf_radio.setChecked(True)
    win.mf_field.set_value(2.0, emit=True)
    qtbot.waitUntil(lambda: win.canvas.ramp is not None and
                    win.canvas.ramp.M_f == pytest.approx(2.0, abs=1e-3), timeout=5000)


def test_low_mf_shows_a_warning(qtbot, window):
    win = _open(qtbot, window)
    win.follow_main.setChecked(False)
    win.m_inf_field.set_value(1.8, emit=True)
    win.delta_field.set_value(18.5, emit=True)
    qtbot.waitUntil(lambda: win.warning_label.text() != "", timeout=5000)
    assert "very weak" in win.warning_label.text()


def test_detached_cowl_shows_an_error(qtbot, window):
    win = _open(qtbot, window)
    win.follow_main.setChecked(False)
    win.m_inf_field.set_value(3.0, emit=True)
    win.delta_field.set_value(40.0, emit=True)
    qtbot.waitUntil(lambda: win.canvas.ramp is None and win.warning_label.text() != "",
                    timeout=5000)
    assert "detached" in win.warning_label.text()


@pytest.mark.ui
def test_hover_shows_x_y_mach_and_pressure_ratio(qtbot, window):
    win = _open(qtbot, window)
    ramp = win.canvas.ramp
    fit = win.canvas._fit()
    mid = ramp.wall_points[len(ramp.wall_points) // 2]
    pos = win.canvas._to_widget(*mid, fit)
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt as _Qt

    event = QMouseEvent(QEvent.Type.MouseMove, pos, _Qt.MouseButton.NoButton,
                        _Qt.MouseButton.NoButton, _Qt.KeyboardModifier.NoModifier)
    win.canvas.mouseMoveEvent(event)
    assert win.canvas.hover_card.isVisible()
    assert set(win.canvas.hover_card.values) == {"x", "y", "M", "p", "i"}


def test_export_dxf_then_open_routes_to_the_isentropic_window(qtbot, window, tmp_path):
    win = _open(qtbot, window)
    path = tmp_path / "ramp.dxf"
    from inletdesign.export import export_isentropic_dxf

    meta = win._export_meta("test")
    export_isentropic_dxf(win._ramp, path, metadata=dict(meta))

    ok = window.project.open_path(path, ask=False)
    assert ok
    assert window.isentropic_window is win
    qtbot.waitUntil(lambda: win.canvas.ramp is not None, timeout=5000)
    assert win.m_inf_field.value() == pytest.approx(win._ramp.M_inf)
    assert not win.follow_main.isChecked()
