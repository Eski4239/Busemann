"""M8.2 layout: tabs in the toolbar row, layer toggles above the canvas, background-drag pan,
the off-design subtitle, collapsible larger charts, the off-design continuous Mach map and
the loop icon."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QToolButton  # noqa: E402

from busemann.canvas import colors as Col  # noqa: E402
from busemann.charts import offdesign_charts as OC  # noqa: E402
from busemann.views import offdesign_tab as OT  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.mark.ui
def test_tabs_sit_in_the_toolbar_and_layers_above_the_canvas(window):
    bar = window.tabs.tabBar()
    assert bar.parentWidget() is window.toolbar or window.toolbar.isAncestorOf(bar)
    assert [bar.tabText(i) for i in range(bar.count())] == ["Design", "Off-design",
                                                            "Analytics", "Compare"]
    toolbar_buttons = [b for b in window.toolbar.findChildren(QToolButton)]
    assert window.explain_button in toolbar_buttons
    assert bar.mapTo(window, bar.rect().topLeft()).x() < \
        window.explain_button.mapTo(window, window.explain_button.rect().topLeft()).x()
    layer_buttons = window.view_row.findChildren(QToolButton)
    assert {b.defaultAction() for b in layer_buttons} == (set(window.layer_actions.values())
                                                          | {window.pin_action})  # M10 Pin
    assert not any(b.defaultAction() in window.layer_actions.values() for b in toolbar_buttons
                   if not window.view_row.isAncestorOf(b))
    bar.setCurrentIndex(1)
    assert window.tabs.currentWidget() is window.offdesign_tab


@pytest.mark.ui
def test_offdesign_tab_tooltip_and_subtitle(window):
    sentence = "How this fixed inlet performs at other flight Mach numbers"
    assert window.tabs.tabToolTip(1).startswith(sentence)
    assert window.offdesign_tab.subtitle.text() == sentence


@pytest.mark.ui
def test_charts_collapsed_by_default_and_larger_when_expanded(qtbot, window):
    tab = window.offdesign_tab
    window.tabs.setCurrentWidget(tab)
    qtbot.wait(100)
    assert not tab.charts_expanded() and not tab.strip.isVisibleTo(window)
    assert tab.charts_toggle.text() == "Charts ▸"
    canvas_collapsed = tab.canvas.height()
    tab.charts_toggle.click()
    qtbot.wait(100)
    assert tab.strip.isVisibleTo(window) and tab.charts_toggle.text() == "Charts"
    for plot in tab.charts.plots.values():
        assert plot.height() >= 2 * 136
    assert tab.canvas.height() < canvas_collapsed
    assert not tab.charts.band_legend.isVisibleTo(window)         # bands: hover tooltip
    assert "Shaded bands:" in tab.charts_toggle.toolTip()
    assert "spillage" in tab.charts.legends["capture"].toolTip()


def test_offdesign_canvas_uses_a_continuous_map_with_its_own_legend(qtbot, window):
    tab = window.offdesign_tab
    window.tabs.setCurrentWidget(tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.55)
    qtbot.waitUntil(lambda: not tab.canvas.is_animating(), timeout=2000)
    scene = tab.canvas.inlet_scene
    lo, hi = scene.continuous_range
    off = window.state.off_design
    machs = [r.M for r in off.regions]
    assert (lo, hi) == pytest.approx((min(machs), 2.55))        # [min region M, M∞]
    for item, region in zip(scene.region_items, scene.picture.regions):
        assert item.brush().color().name() == Col.continuous(region.state.M, lo, hi)
    ticks = tab.canvas.continuous_ticks()
    assert ticks[0] == pytest.approx(lo, abs=1e-6) and ticks[-1] == pytest.approx(hi)
    assert 1.0 in ticks                                           # sonic line inside
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=3.25)
    qtbot.waitUntil(lambda: not tab.canvas.is_animating(), timeout=2000)
    assert scene.continuous_range[1] == pytest.approx(3.25)      # follows the slider
    assert window.canvas.inlet_scene.continuous_range is None      # design canvas: classes
    window.grab()                                                   # paints the legend
    from busemann.canvas.view import CONTINUOUS_LEGEND_TITLE
    assert CONTINUOUS_LEGEND_TITLE == "Mach (off-design view)"


def test_continuous_map_is_diverging_and_monotonic():
    from busemann.canvas.colors import _rgb

    sub = [_rgb(Col.continuous(M, 0.3, 4.5)) for M in (1.0, 0.8, 0.5, 0.3)]
    sup = [_rgb(Col.continuous(M, 0.3, 4.5)) for M in (1.0001, 2.0, 3.0, 4.5)]
    assert all(b[2] <= a[2] + 1e-9 for a, b in zip(sub, sub[1:]))        # redder below
    assert all(sum(b) <= sum(a) + 1e-9 for a, b in zip(sup, sup[1:]))    # darker above


@pytest.mark.ui
def test_loop_button_is_an_icon(window):
    loop = window.offdesign_tab.playback_controls.loop_button
    assert loop.text() == "" and not loop.icon().isNull()
    assert loop.toolTip() == "Loop sweep"


def _mouse(canvas, kind, pos, buttons):
    button = Qt.MouseButton.LeftButton if kind != QEvent.Type.MouseMove else \
        Qt.MouseButton.NoButton
    QApplication.sendEvent(canvas.viewport(), QMouseEvent(
        kind, pos, canvas.viewport().mapToGlobal(pos.toPoint()), button, buttons,
        Qt.KeyboardModifier.NoModifier))


def test_left_drag_on_empty_background_pans_and_a_click_still_selects(qtbot, window):
    canvas = window.canvas
    canvas.zoom(2.0)                                 # room to scroll
    qtbot.wait(50)
    empty = QPointF(8, canvas.viewport().height() - 8)
    assert canvas.pick(empty) == (None, None)
    h0 = canvas.horizontalScrollBar().value()
    _mouse(canvas, QEvent.Type.MouseButtonPress, empty, Qt.MouseButton.LeftButton)
    for dx in (5, 20, 60):
        _mouse(canvas, QEvent.Type.MouseMove, empty + QPointF(dx, 0), Qt.MouseButton.LeftButton)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, empty + QPointF(60, 0),
           Qt.MouseButton.NoButton)
    assert canvas.horizontalScrollBar().value() != h0
    assert canvas.selection == (None, None)
    canvas.fit()
    qtbot.wait(50)
    # a click (no movement) on a region still selects it
    region = canvas.inlet_scene.picture.regions[1]
    from busemann.canvas import picture as P
    from busemann.canvas.scene import S
    centre = canvas.viewportTransform().map(S(P.polygon_centroid(region.polygon)))
    _mouse(canvas, QEvent.Type.MouseButtonPress, centre, Qt.MouseButton.LeftButton)
    _mouse(canvas, QEvent.Type.MouseButtonRelease, centre, Qt.MouseButton.NoButton)
    assert canvas.selection == ("region", 1)


def test_new_constants_are_used():
    assert OC.PLOT_MIN_H >= 2 * 136
    assert OT.SUBTITLE.startswith("How this fixed inlet")


@pytest.mark.ui
def test_continuous_legend_fits_a_short_canvas(qtbot, window):
    tab = window.offdesign_tab
    window.tabs.setCurrentWidget(tab)
    tab.set_charts_expanded(True)                    # short canvas
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.55)
    qtbot.wait(100)
    card = tab.canvas.legend_rect()
    assert card.bottom() <= tab.canvas.viewport().height()       # both ends visible
    tab.canvas.viewport().repaint()
    labels = tab.canvas.legend_tick_labels
    lo, hi = tab.canvas.inlet_scene.continuous_range
    assert labels[0] == f"{lo:.3g}" and labels[-1] == f"{hi:.3g}"   # both ends labelled
