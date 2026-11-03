"""Explain drawer (M5): toggle and slide, content follows the selection, numbers are api
values, equations render."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from busemann.views.explain_drawer import DRAWER_W, SLIDE_MS  # noqa: E402
from inletdesign import api  # noqa: E402

pytestmark = pytest.mark.gui


def _open(qtbot, window):
    drawer = window.explain_drawer
    window.explain_action.setChecked(True)
    qtbot.waitUntil(lambda: not window.is_column_animating(), timeout=2000)
    return drawer


def _rect(widget, window):
    from PySide6.QtCore import QRect
    return QRect(widget.mapTo(window, widget.rect().topLeft()), widget.size())


def test_drawer_widens_right_column_instead_of_covering(qtbot, window):
    drawer = window.explain_drawer
    assert window.right_column.width() == 320 and not drawer.is_open
    assert window._column_anim.duration() == SLIDE_MS == 200
    centre_before = window.tabs.width()
    _open(qtbot, window)
    assert window.right_column.width() == DRAWER_W == 420
    assert window.right_column.currentWidget() is drawer and drawer.isVisible()
    assert window.tabs.width() == centre_before - 100           # the centre column shrank
    window.explain_action.setChecked(False)
    qtbot.waitUntil(lambda: not window.is_column_animating(), timeout=2000)
    assert window.right_column.width() == 320
    assert window.right_column.currentWidget() is window.right_panel
    assert window.tabs.width() == centre_before


@pytest.mark.parametrize("size", [(1280, 800), (1440, 900)])
def test_drawer_never_covers_the_centre_column(qtbot, window, size):
    from PySide6.QtWidgets import QWidget

    window.resize(*size)
    window.tabs.setCurrentWidget(window.offdesign_tab)
    _open(qtbot, window)
    qtbot.wait(100)
    assert (window.width(), window.height()) == size
    drawer_rect = _rect(window.explain_drawer, window)
    centre = _rect(window.tabs, window)
    assert not centre.intersects(drawer_rect)
    for w in window.tabs.findChildren(QWidget):
        if w.isVisibleTo(window):
            assert not _rect(w, window).intersects(drawer_rect), (type(w).__name__, w.objectName())
    tab = window.offdesign_tab
    for w in (tab.badge, tab.card, tab.chip, tab.charts.note_legend):
        assert centre.contains(_rect(w, window)), w.objectName()
        assert w.width() >= w.minimumSizeHint().width() - 1


def test_nothing_selected_shows_design_method(qtbot, window):
    drawer = _open(qtbot, window)
    assert window.canvas.selection == (None, None)
    assert drawer.entry_name == "method"
    assert drawer.rendered.title.startswith("Design method")


@pytest.mark.parametrize("kind, index, entry", [
    ("shock", 0, "oblique_shock"), ("shock", 2, "normal_shock"), ("region", 0, "freestream"),
    ("region", 1, "region"), ("region", 3, "duct"), ("cowl", 0, "cowl_design")])
def test_canvas_selection_switches_content(qtbot, window, kind, index, entry):
    drawer = _open(qtbot, window)
    with qtbot.waitSignal(drawer.content_changed, timeout=2000):
        window.canvas.select(kind, index)
    assert drawer.entry_name == entry
    assert drawer.images and all(not img.isNull() for img in drawer.images.values())


def test_table_row_switches_content(qtbot, window):
    drawer = _open(qtbot, window)
    table = window.results_panel.station_table
    with qtbot.waitSignal(drawer.content_changed, timeout=2000):
        table.selectRow(2)
    assert drawer.entry_name == "region" and drawer.rendered.title == "Region 2 (behind ramp shock 2)"


def test_shock_numbers_are_api_values(qtbot, window):
    drawer = _open(qtbot, window)
    window.canvas.select("shock", 1)
    s = api.design(3.0, 2).shock_states[1]
    shown = {sub.path: sub.text for sub in drawer.rendered.substitutions}
    assert shown["sel.Mn1"] == f"{s.Mn1:.4f}" and shown["sel.beta_deg"] == f"{s.beta_deg:.2f}"
    assert shown["sel.M2"] == f"{s.M2:.4f}" and shown["sel.p0_ratio"] == f"{s.p0_ratio:.4f}"
    assert f"{s.Mn1:.4f}" in drawer.body.toPlainText()          # plain-words paragraph


def test_cowl_on_off_design_tab_uses_local_rule(qtbot, window):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(cowl_wedge_deg=6.0)
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.55)
    drawer = _open(qtbot, window)
    with qtbot.waitSignal(drawer.content_changed, timeout=2000):
        window.offdesign_tab.canvas.select("cowl", 0)
    assert drawer.entry_name == "cowl_offdesign"
    off = window.state.off_design
    shown = {sub.path: sub.text for sub in drawer.rendered.substitutions}
    assert shown["off.cowl_margin_deg"] == f"{off.cowl_margin_deg:+.2f}"
    assert shown["off.cowl_required_turn_deg"] == "6.00"


def test_topic_links(qtbot, window):
    drawer = _open(qtbot, window)
    drawer.topics.linkActivated.emit("offdesign")
    assert drawer.entry_name == "offdesign"
    window.canvas.select("shock", 0)
    drawer.topics.linkActivated.emit("method")
    assert drawer.entry_name == "method"
    drawer.topics.linkActivated.emit("selection")
    assert drawer.entry_name == "oblique_shock"


def test_gui_thread_never_renders_mathtext_during_a_drag(qtbot, window, monkeypatch):
    """Drawer open, render process warming: during a 40-step drag of the off-design slider
    the GUI process makes no mathtext call; the drawer catches up after the release."""
    import threading

    from matplotlib import mathtext

    from busemann.explain import mathsvg

    calls = []
    real = mathtext.math_to_image

    def spy(*a, **k):
        calls.append(threading.current_thread() is threading.main_thread())
        return real(*a, **k)

    window.tabs.setCurrentWidget(window.offdesign_tab)
    drawer = _open(qtbot, window)
    window.offdesign_tab.canvas.select("cowl", 0)
    window._warm_equations()                            # render process starts now
    monkeypatch.setattr(mathtext, "math_to_image", spy)
    before = mathsvg.render_count
    slider = window.offdesign_tab.slider.slider
    slider.setSliderDown(True)
    assert window.state.dragging
    for k in range(40):
        slider.setValue(round((2.5 - 1.2) / 0.01) + k)
        qtbot.wait(10)
    qtbot.waitUntil(lambda: window.state.off_design.M_inf == pytest.approx(2.89), timeout=5000)
    assert calls == [] and mathsvg.render_count == before
    assert drawer._pending                              # waiting for the release
    slider.setSliderDown(False)
    assert not window.state.dragging and not drawer._pending
    assert drawer.rendered.title == "Cowl lip at M∞ 2.89"
