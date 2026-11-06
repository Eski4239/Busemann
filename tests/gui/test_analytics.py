"""Analytics tab (M9a): the trade-study charts, hover, pick + Apply (one undo step),
computed takeaways, progressive worker results and the (M, γ) cache."""
import importlib.util
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from inletdesign import api  # noqa: E402

from busemann.analytics import takeaways as T  # noqa: E402
from busemann.views import analytics_tab as A  # noqa: E402

pytestmark = pytest.mark.gui


def _open(qtbot, window):
    tab = window.analytics_tab
    if tab.data.get("theta_curve") is None or tab._stale:
        with qtbot.waitSignal(tab.computed, timeout=10000):
            window.tabs.setCurrentWidget(tab)
    else:
        window.tabs.setCurrentWidget(tab)
    qtbot.wait(50)
    return tab


def _audit():
    spec = importlib.util.spec_from_file_location(
        "text_audit", Path(__file__).resolve().parents[1] / "test_text_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._violations


def test_turning_view_draws_every_curve_and_the_theta_max_line(qtbot, window):
    tab = _open(qtbot, window)
    chart = tab.turning_chart
    assert set(chart.series) == {1, 2, 3, 4, "isentropic"}
    curves = {c.n: c for c in api.trade_vs_turning(3.0)}
    for n, c in curves.items():
        assert chart.series[n]["x"] == c.delta_deg and chart.series[n]["y"] == c.recovery_total
    assert chart.vline.value() == pytest.approx(api.max_deflection(3.0), abs=1e-12)
    assert chart.vline.label.toPlainText() == "cowl shock detaches beyond here"
    d = window.state.design
    assert chart.marker_text[:2] == (d.cowl_angle_deg, d.recovery_total)
    assert not window.view_row.isVisibleTo(window)                  # canvas toggles hidden
    zoom = (window.zoom_in_action, window.zoom_out_action, window.fit_action)
    assert not any(a.isVisible() for a in zoom) and not window.zoom_separator.isVisible()
    window.tabs.setCurrentWidget(window.compare_tab)
    assert not any(a.isVisible() for a in zoom) and not window.view_row.isVisibleTo(window)
    for page in (window.canvas, window.offdesign_tab):
        window.tabs.setCurrentWidget(page)
        assert window.view_row.isVisibleTo(window) and all(a.isVisible() for a in zoom)


def test_design_mach_view_curves_mil_and_cowl_chart(qtbot, window):
    tab = _open(qtbot, window)
    tab.set_view("mach")
    assert tab.pages.currentIndex() == 1
    assert set(tab.mach_chart.series) == {0, 1, 2, 3, 4, "mil"}
    assert set(tab.cowl_chart.series) == {1, 2, 3, 4, "theta"}
    trade = api.trade_vs_design_mach()
    k = trade.M.index(3.0)
    assert tab.cowl_chart.series["theta"]["y"][k] == pytest.approx(trade.theta_max_deg[k])
    assert tab.mach_chart.series["mil"]["y"][k] == pytest.approx(api.mil_recovery(3.0))
    assert "recovery × diffuser 0.970" in tab.mil_caption.text()
    window.state.update(diffuser_recovery=0.95)
    qtbot.wait(50)
    assert "recovery × diffuser 0.950" in tab.mil_caption.text()
    assert "MIL-E-5008B" in tab.mach_chart.legend.text()


def test_hover_shows_n_turning_recovery_and_ramps(qtbot, window):
    tab = _open(qtbot, window)
    chart = tab.turning_chart
    c = tab.data[("turn", 3)]
    i = 10
    pos = chart.view_point_scene(3, i)
    text = chart.hover_text_at(pos)
    assert text.startswith("3 ramps at M 3.00")
    assert f"Turning (cowl angle) {c.delta_deg[i]:.2f}°" in text
    assert f"Recovery {c.recovery_total[i]:.4f}" in text
    assert "Ramp angles: " + ", ".join(f"{a:.2f}°" for a in c.ramps_deg[i]) in text
    assert "cowl-constrained optimum" in text
    chart._on_move(pos)
    assert chart.last_hover == text
    iso = tab.data["iso"]
    iso_text = chart.hover_text_at(chart.view_point_scene("isentropic", 40))
    assert "Isentropic limit" in iso_text and A.ISENTROPIC_NOTE in iso_text
    assert f"{iso.recovery[40]:.4f}" in iso_text


def test_pick_and_apply_is_one_undo_step(qtbot, window):
    tab = _open(qtbot, window)
    chart = tab.turning_chart
    c = tab.data[("turn", 3)]
    i = 25                                              # cowl-constrained point
    before = window.state.inputs
    chart.pick_at(chart.view_point_scene(3, i))
    assert chart.selected == (3, i) and tab.apply_button.isEnabled()
    assert tab.selection_label.text().startswith("Selected: 3 ramps at M 3.00, cowl limit")
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        tab.apply_button.click()
    i_now = window.state.inputs
    assert (i_now.n_ramps, i_now.method, i_now.max_cowl_enabled) == (3, "oswatitsch", True)
    assert i_now.max_cowl_deg == pytest.approx(c.delta_deg[i], abs=1e-5)
    assert window.state.design.recovery_total == pytest.approx(c.recovery_total[i], abs=1e-6)
    assert not tab.apply_button.isEnabled()
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.undo.stack.undo()                       # ONE step restores everything
    after = window.state.inputs
    for field in ("n_ramps", "method", "max_cowl_enabled", "max_cowl_deg", "mach"):
        assert getattr(after, field) == getattr(before, field), field


def test_pick_on_design_mach_chart_sets_mach_and_n(qtbot, window):
    tab = _open(qtbot, window)
    tab.set_view("mach")
    chart = tab.mach_chart
    c = tab.data[("mach", 4)]
    k = c.M.index(4.5)
    chart.pick_at(chart.view_point_scene(4, k))
    assert tab.selection["changes"] == dict(mach=4.5, n_ramps=4, method="oswatitsch",
                                            max_cowl_enabled=False)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        tab.apply_selection()
    assert window.state.design.inputs.M == pytest.approx(4.5)
    assert window.state.design.recovery_total == pytest.approx(c.recovery_total[k], abs=1e-9)


def test_isentropic_points_cannot_be_applied(qtbot, window):
    tab = _open(qtbot, window)
    chart = tab.turning_chart
    iso = tab.data["iso"]
    chart.pick_at(chart.view_point_scene("isentropic", len(iso.delta_deg) - 1))
    assert tab.selection is None and not tab.apply_button.isEnabled()
    assert tab.selection_label.text() == A.NO_SELECTION


def test_takeaways_are_the_computed_helpers(qtbot, window):
    tab = _open(qtbot, window)
    optima, theta = tab.data["optima"], tab.data["theta"]
    equal = tab.data["equal_turn"]
    assert tab.turning_takeaway.text() == T.turning(3.0, optima, theta, 2, equal[2])
    assert tab.turning_takeaway.text().startswith("At the same 33.8° cowl turn as 2 ramps")
    assert tab.mach_takeaway.text() == T.design_mach(3.0, optima, 2)
    assert tab.cowl_takeaway.text() == T.cowl(3.0, optima, theta, 2)
    assert optima[2][0] == pytest.approx(window.state.design.recovery_total, abs=1e-12)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(n_ramps=3)                 # same (M, γ): only the text changes
    assert not tab.is_computing()
    assert tab.turning_takeaway.text() == T.turning(3.0, optima, theta, 3, equal[3])


def test_progressive_results_cache_and_stale_generations(qtbot, window):
    tab = _open(qtbot, window)
    seen = tab.partials_seen
    assert seen.index("iso") < seen.index("turn:1") < seen.index("turn:4") < \
        seen.index("mach:0") < seen.index("theta_curve")
    # a new design Mach recomputes; partials of an older generation are dropped
    with qtbot.waitSignal(tab.computed, timeout=10000):
        window.state.update(mach=2.5)
    assert tab._key[0] == 2.5 and tab.turning_chart.series[2]["x"][-1] == \
        pytest.approx(api.design(2.5, 2).cowl_angle_deg)
    old = tab._generation - 1
    tab._on_partial(old, "turn", 2, api.trade_vs_turning(3.0, n_list=(2,))[0])
    assert tab.turning_chart.series[2]["x"][-1] == \
        pytest.approx(api.design(2.5, 2).cowl_angle_deg)            # unchanged
    # back to M 3: replayed from the cache, no worker job
    with qtbot.waitSignal(tab.computed, timeout=10000):
        window.state.update(mach=3.0)
    assert not tab.is_computing() and (3.0, 1.4) in tab._cache


def test_no_raw_symbols_or_phase_names_in_analytics_text(qtbot, window):
    violations = _audit()
    tab = _open(qtbot, window)
    texts = [tab.turning_takeaway.text(), tab.mach_takeaway.text(), tab.cowl_takeaway.text(),
             tab.mil_caption.text(), tab.selection_label.text(), A.ISENTROPIC_NOTE,
             A.THETA_LINE_TEXT, A.NO_SELECTION]
    for chart in (tab.turning_chart, tab.mach_chart, tab.cowl_chart):
        for key, s in chart.series.items():
            texts += [s["text"](i) for i in range(0, len(s["x"]), 7)]
            texts.append(s["name"] or "")
    tab.set_view("mach")
    texts += [tab.mach_chart.legend.text(), tab.cowl_chart.legend.text()]
    problems = [v for t in texts for v in violations("analytics", t)]
    assert problems == []
    assert not any(re.search(r"phase\s*3", t, re.I) or "_" in t for t in texts
                   if "<span" not in t)
