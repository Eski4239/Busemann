"""Every visible label, KPI, table header, chart axis and toolbar action has a tooltip."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtWidgets import QLabel  # noqa: E402

pytestmark = pytest.mark.gui


def _missing(window):
    return sorted({(lab.objectName(), lab.text()[:40]) for lab in window.findChildren(QLabel)
                   if lab.isVisibleTo(window) and lab.text().strip() and not lab.toolTip()})


def _states(qtbot, window):
    """Walk the app through states that show different labels."""
    for section in (window.flight_panel.advanced, window.design_panel.advanced):
        section.toggle.setChecked(True)
    yield "default"
    window.canvas.select("region", 1)
    yield "region selected"
    window.canvas.select("shock", 0)
    yield "shock selected"
    window.canvas.select("cowl", 0)
    yield "cowl selected"
    window.explain_action.setChecked(True)
    yield "explain drawer"
    window.explain_action.setChecked(False)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(method="custom", custom_angles=(8.0, 9.0), atmosphere_mode="manual")
    yield "custom angles, manual atmosphere"
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=3.25)
    yield "off-design tab"


@pytest.mark.ui
def test_no_visible_label_without_tooltip(qtbot, window):
    for state in _states(qtbot, window):
        qtbot.wait(50)
        assert _missing(window) == [], state


@pytest.mark.ui
def test_table_headers_chart_axes_and_actions_have_tooltips(window):
    table = window.results_panel.station_table
    for c in range(table.columnCount()):
        assert table.horizontalHeaderItem(c).toolTip(), c
    for w in window.offdesign_tab.charts.plots.values():
        item = w.getPlotItem()
        assert item.getAxis("left").toolTip() and item.getAxis("bottom").toolTip()
    for action in (window.toggle_left, window.toggle_right, window.zoom_in_action,
                   window.zoom_out_action, window.fit_action, window.explain_action,
                   *window.layer_actions.values()):
        assert action.toolTip() and action.toolTip() != action.text(), action.text()
    for card in window.results_panel.cards.values():
        assert card.toolTip() and card.value_label.toolTip() == card.toolTip()
