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
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import Qt as _Qt

    # the overload with the global position (the one without it is deprecated in Qt 6)
    event = QMouseEvent(QEvent.Type.MouseMove, pos, win.canvas.mapToGlobal(pos),
                        _Qt.MouseButton.NoButton, _Qt.MouseButton.NoButton,
                        _Qt.KeyboardModifier.NoModifier)
    win.canvas.mouseMoveEvent(event)
    assert win.canvas.hover_card.isVisible()
    assert set(win.canvas.hover_card.values) == {"x", "y", "M", "p", "i"}


def _set(qtbot, win, M_inf=3.0, delta=33.789, h_c=0.1):
    win.follow_main.setChecked(False)
    win.m_inf_field.set_value(M_inf, emit=True)
    win.h_c_field.set_value(h_c, emit=True)
    win.delta_radio.setChecked(True)
    win.delta_field.set_value(delta, emit=True)
    qtbot.waitUntil(lambda: win._ramp is not None
                    and win._ramp.delta_deg == pytest.approx(delta)
                    and win._ramp.capture_height == pytest.approx(h_c), timeout=5000)


# --- M12 PART 2.1: engine face and MIL-E-5008B are two values ------------------------------
def test_engine_face_and_mil_are_two_rows(qtbot, window):
    """At M 3, δ 33.789°: engine face = η × diffuser recovery = 0.8809 × 0.97 = 0.854; the
    MIL-E-5008B reference is 0.809 (both closed form, see test_isentropic_ramp.py)."""
    win = _open(qtbot, window)
    _set(qtbot, win)
    assert win.cards["engine_face"].text() == "0.854"
    assert win.cards["mil"].text() == "0.809"
    assert win.cards["recovery"].text() == "0.8809"
    assert win.cards["engine_face"].text() != win.cards["mil"].text()


def test_engine_face_follows_the_main_diffuser_recovery(qtbot, window):
    win = _open(qtbot, window)
    _set(qtbot, win)
    window.state.update(diffuser_recovery=0.9)
    qtbot.waitUntil(lambda: win.cards["engine_face"].text() == f"{0.9 * win._ramp.recovery:.3f}",
                    timeout=5000)
    assert win.cards["mil"].text() == "0.809"                   # the reference does not move


# --- M12 PART 2.2: duct entry height, legend, framing ---------------------------------------
def test_duct_entry_height_is_shown(qtbot, window):
    win = _open(qtbot, window)
    _set(qtbot, win)
    assert win.cards["h_t"].text() == "30.26" and win.cards["h_t"].unit_label.text() == "mm"


@pytest.mark.parametrize("size", [(1000, 640), (1440, 900)])
def test_drawing_fills_the_view_and_labels_stay_inside(qtbot, window, size):
    from PySide6.QtCore import QRectF

    win = _open(qtbot, window)
    _set(qtbot, win)
    win.resize(*size)
    win.show()
    qtbot.wait(50)
    canvas = win.canvas
    canvas.grab()                                            # paint once
    inside = QRectF(canvas.rect())
    for name, rect in canvas.label_rects.items():
        assert inside.contains(rect), (name, rect, inside)
    assert inside.contains(canvas.legend_rect)
    fit = canvas._fit()
    g = canvas.geometry_
    pts = [canvas._to_widget(*p, fit) for p in
           (*win._ramp.wall_points, win._ramp.lip, g["floor_end"], g["cowl_outer_end"], g["foot"])]
    area = canvas.drawing_rect().adjusted(-1, -1, 1, 1)
    assert all(area.contains(p) for p in pts)
    xs, ys = [p.x() for p in pts], [p.y() for p in pts]
    filled = max((max(xs) - min(xs)) / area.width(), (max(ys) - min(ys)) / area.height())
    assert filled > 0.9                                      # framed to the view, not a corner
    assert not canvas.label_rects["coalesce"].intersects(canvas.legend_rect)


@pytest.mark.ui
def test_legend_and_drawn_labels(qtbot, window):
    win = _open(qtbot, window)
    _set(qtbot, win)
    win.canvas.grab()
    texts = win.canvas.painted_texts
    assert "p/p∞" in texts and "1.00" in texts
    assert f"{win._ramp.characteristics[-1].p_over_pinf:.2f}" in texts
    assert any(t.startswith("h<sub>t</sub> 30.26 mm") for t in texts)


@pytest.mark.ui
def test_window_uses_the_token_background(qtbot, window):
    from busemann.theme import tokens

    win = _open(qtbot, window)
    win.resize(1000, 640)
    win.show()
    qtbot.wait(50)
    image = win.grab().toImage()
    canvas_at = win.canvas.geometry().center()
    assert image.pixelColor(2, image.height() - 3).name() == tokens.COLORS["surface"].lower()
    assert win.objectName() == "isentropicWindow"
    assert win.canvas.grab().toImage().pixelColor(3, 3).name() == \
        tokens.COLORS["surface"].lower(), canvas_at


@pytest.mark.ui
def test_window_text_has_no_raw_symbols(qtbot, window):
    """Text audit (M8.2 rules) over everything this window shows: labels, buttons, card
    titles and values, painted canvas text, hover rows and warnings."""
    import importlib.util
    import re
    from pathlib import Path

    from PySide6.QtWidgets import QAbstractButton, QLabel

    spec = importlib.util.spec_from_file_location(
        "text_audit", Path(__file__).parents[1] / "test_text_audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    win = _open(qtbot, window)
    _set(qtbot, win)
    win.canvas.grab()
    texts = [w.text() for w in win.findChildren(QLabel) + win.findChildren(QAbstractButton)]
    texts += win.canvas.painted_texts
    win.m_inf_field.set_value(1.8, emit=True)                 # the low-final-Mach warning
    win.delta_field.set_value(18.5, emit=True)
    qtbot.waitUntil(lambda: win.warning_label.text() != "", timeout=5000)
    texts.append(win.warning_label.text())
    win.delta_field.set_value(60.0, emit=True)                # an error from the core
    qtbot.waitUntil(lambda: win._ramp is None, timeout=5000)
    texts.append(win.warning_label.text())
    texts += [label for _k, label, *_ in (("x", "x"), ("y", "y"), ("M", "M"), ("p", "p/p∞"),
                                          ("i", "characteristic"))]
    plain = [re.sub(r"<[^>]+>", "", t) for t in texts if t]
    problems = [p for t in plain for p in audit._violations("isentropic window", t)]
    assert problems == []
    assert not [t for t in plain if "_" in t]                # real subscripts, not M_f
    assert any("<sub>f</sub>" in t for t in texts) and any("<sub>c</sub>" in t for t in texts)
    assert any("<sub>t</sub>" in t for t in texts)


# --- M12 PART 2.3: export errors -------------------------------------------------------------
def test_isentropic_export_to_a_read_only_file_reports(qtbot, window, tmp_path):
    import os
    import stat

    win = _open(qtbot, window)
    target = tmp_path / "ramp.dxf"
    target.write_text("old", encoding="utf-8")
    os.chmod(target, stat.S_IREAD)
    shown = []
    win.ask_path = lambda title, flt: str(target)
    win.show_error = shown.append
    try:
        assert win.export_dxf() is None
    finally:
        os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
    assert shown and shown[0].startswith("Could not write ramp.dxf: ")
    assert shown[0].endswith("Is it open in another program?")


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
