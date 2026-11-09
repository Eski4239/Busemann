"""Results-panel station table (M4): rows per canvas region, canvas <-> table selection,
Copy table (TSV), and following the active tab."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from busemann.views.station_table import ratio_text  # noqa: E402
from inletdesign import api  # noqa: E402

pytestmark = pytest.mark.gui


def _table(window):
    return window.results_panel.station_table


def test_rows_match_every_canvas_region(window):
    table = _table(window)
    d = api.design(3.0, 2)
    assert table.rowCount() == len(d.regions) == len(window.canvas.inlet_scene.picture.regions)
    assert [table.text(r, 0) for r in range(table.rowCount())] == ["∞", "1", "2", "duct"]
    for r, st in enumerate(d.regions):
        assert table.text(r, 1) == f"{st.M:.3f}"
        assert table.text(r, 2) == ratio_text(st.p_ratio)
        assert table.text(r, 3) == ratio_text(st.T_ratio)
        assert table.text(r, 4) == f"{st.p0_ratio:.4f}"
        assert table.text(r, 5) == f"{st.theta_deg:.1f}"
        assert table.item(r, 0).toolTip() == st.name
    # monospaced, right-aligned numbers
    assert table.item(0, 1).textAlignment() & Qt.AlignmentFlag.AlignRight
    assert table.font().fixedPitch() or "Mono" in table.font().family()


@pytest.mark.ui
def test_canvas_click_highlights_row(qtbot, window):
    canvas = window.canvas
    region = canvas.inlet_scene.picture.regions[2]
    with qtbot.waitSignal(canvas.selection_changed):
        canvas.select("region", 2)
    assert _table(window).selected_row() == 2
    shock = canvas.inlet_scene.picture.shocks[0]
    canvas.select("shock", shock.index)
    assert _table(window).selected_row() is None
    assert region.index == 2


def test_row_click_selects_canvas_region(qtbot, window):
    table = _table(window)
    rect = table.visualItemRect(table.item(1, 2))
    qtbot.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
    assert window.canvas.selection == ("region", 1)
    assert window.results_panel.selection_values["M"] == pytest.approx(
        api.design(3.0, 2).regions[1].M)
    # and back: no feedback loop, the row stays the only selection
    assert table.selected_row() == 1


def test_copy_table_puts_tsv_on_clipboard(qtbot, window):
    window.results_panel.copy_button.click()
    text = QApplication.clipboard().text()
    lines = text.splitlines()
    assert lines[0].split("\t") == ["Region", "M", "p/p_inf", "T/T_inf", "p0/p0_inf",
                                    "flow angle (°)"]
    d = api.design(3.0, 2)
    assert len(lines) == 1 + len(d.regions)
    for line, st in zip(lines[1:], d.regions):
        cells = line.split("\t")
        assert cells[0] == st.name
        assert float(cells[1]) == pytest.approx(st.M, rel=1e-5)
        assert float(cells[4]) == pytest.approx(st.p0_ratio, rel=1e-5)
        assert float(cells[5]) == pytest.approx(st.theta_deg, rel=1e-5, abs=1e-9)


def test_table_follows_the_off_design_tab(qtbot, window):
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.5)
    off_canvas = window.offdesign_tab.canvas
    qtbot.waitUntil(lambda: off_canvas.inlet_scene.picture is not None
                    and off_canvas.inlet_scene.picture.skeleton.mach == pytest.approx(2.5),
                    timeout=3000)
    table = _table(window)
    off = api.off_design_point(api.design(3.0, 2), 2.5)
    qtbot.waitUntil(lambda: table.text(0, 1) == f"{off.regions[0].M:.3f}", timeout=2000)
    assert table.text(1, 1) == f"{off.regions[1].M:.3f}"
    # selection sync uses the off-design canvas while its tab is shown
    table.selectRow(2)
    assert off_canvas.selection == ("region", 2)
    assert window.canvas.selection == (None, None)
    window.tabs.setCurrentWidget(window.canvas)
    assert table.text(0, 1) == "3.000"
    assert table.selected_row() is None


def test_ratio_text_keeps_four_significant_digits():
    assert [ratio_text(x) for x in (1.0, 6.5321, 12.6136, 158.424, 469.181, 1234.5)] == [
        "1.000", "6.532", "12.61", "158.4", "469.2", "1234"]


@pytest.mark.ui
@pytest.mark.parametrize("changes", [{}, {"n_ramps": 4}, {"mach": 6.7, "n_ramps": 4},
                                     {"n_ramps": 0}, {"mach": 2.0, "n_ramps": 1}])
def test_no_clipped_columns_at_1440x900(qtbot, window, changes):
    if changes:
        with qtbot.waitSignal(window.state.design_ready, timeout=5000):
            window.state.update(**changes)
    table = _table(window)
    assert window.width() == 1440 and window.height() == 900
    assert table.column_overflow() == []
    window.tabs.setCurrentWidget(window.offdesign_tab)          # off-design numbers too
    qtbot.waitUntil(lambda: table.rowCount() > 0, timeout=2000)
    assert table.column_overflow() == []
