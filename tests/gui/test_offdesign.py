"""Off-design tab (M4): tab switch, slider <-> chart cursors, the light off-design job,
CFD overlay rule, regime badge and results card."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")
pytest.importorskip("pyqtgraph")

from busemann.charts import model  # noqa: E402
from inletdesign import api  # noqa: E402

pytestmark = pytest.mark.gui


def _design(qtbot, win, **changes):
    with qtbot.waitSignal(win.state.design_ready, timeout=5000):
        win.state.update(**changes)


def _off(qtbot, win, M):
    with qtbot.waitSignal(win.state.off_design_ready, timeout=5000):
        win.state.update(off_design_mach=M)


def _open_tab(qtbot, win):
    win.tabs.setCurrentWidget(win.offdesign_tab)
    win.offdesign_tab.set_charts_expanded(True)          # collapsed by default (M8.2)
    qtbot.waitUntil(lambda: win.offdesign_tab.canvas.inlet_scene.picture is not None,
                    timeout=3000)
    return win.offdesign_tab


def test_tab_switch_sets_view_and_toolbar_target(qtbot, window):
    assert window.tabs.tabText(1) == "Off-design"
    tab = _open_tab(qtbot, window)
    assert window.state.active_view == "offdesign"
    assert window.current_canvas() is tab.canvas
    assert tab.chip.text() == "Design point: M 3.00, 2 ramps"
    assert tab.slider.range() == (1.2, 4.5) and tab.slider.value() == 3.0
    assert tab.regime() == "on-lip"
    before = window.canvas.scale_factor()
    window.zoom_in_action.trigger()
    assert window.canvas.scale_factor() == before            # design canvas untouched
    window.tabs.setCurrentWidget(window.canvas)
    assert window.state.active_view == "design" and window.current_canvas() is window.canvas


def test_slider_moves_every_chart_cursor_and_the_canvas(qtbot, window):
    tab = _open_tab(qtbot, window)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        tab.slider.slider.setValue(round((2.5 - 1.2) / 0.01))       # user drag position
    assert window.state.inputs.off_design_mach == pytest.approx(2.5)
    for line in tab.charts.cursors.values():
        assert line.value() == pytest.approx(2.5)
    qtbot.waitUntil(lambda: not tab.canvas.is_animating(), timeout=2000)
    pic = tab.canvas.inlet_scene.picture
    assert pic.skeleton.off_design and pic.skeleton.mach == pytest.approx(2.5)
    assert pic.shocks[0].end[0] < pic.skeleton.lip[0]                 # spillage ahead of lip
    assert tab.regime() == "spillage"
    expected = api.off_design_point(api.design(3.0, 2), 2.5)
    assert tab.card.text("capture") == f"{expected.mass_capture_ratio:.3f}"
    assert tab.card.delta("capture") == f"{expected.mass_capture_ratio - 1.0:+.3f}"
    assert tab.card.text("margin") == f"{expected.cowl_margin_deg:+.2f}"
    # the design canvas keeps showing the design point
    assert not window.canvas.inlet_scene.picture.skeleton.off_design


def test_dragging_a_chart_cursor_moves_the_slider(qtbot, window):
    tab = _open_tab(qtbot, window)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        tab.charts.cursors["margin"].setValue(3.25)        # same path as a mouse drag
    assert tab.slider.value() == pytest.approx(3.25)
    assert window.state.inputs.off_design_mach == pytest.approx(3.25)
    assert tab.charts.cursors["capture"].value() == pytest.approx(3.25)
    assert tab.regime() == "shock-in-duct"


def test_off_design_only_change_does_not_recompute_design(qtbot, window):
    _open_tab(qtbot, window)
    design = window.state.design
    with qtbot.assertNotEmitted(window.state.design_ready, wait=200):
        _off(qtbot, window, 2.8)
    assert window.state.design is design
    assert window.state.off_design.M_inf == pytest.approx(2.8)


def test_stale_off_design_results_are_dropped(qtbot, window):
    _open_tab(qtbot, window)
    state = window.state
    results = []
    state.off_design_ready.connect(lambda off, err: results.append(off and off.M_inf))
    for M in (2.5, 2.6, 2.7, 2.8):                  # faster than the debounce
        state.update(off_design_mach=M)
    qtbot.waitUntil(lambda: state.off_design is not None
                    and state.off_design.M_inf == pytest.approx(2.8), timeout=3000)
    assert results == [pytest.approx(2.8)]
    # a late result of an older request is ignored
    old = api.off_design_point(state.design, 2.5)
    state._on_off_design_done(state._off_generation - 1,
                              dict(design=state.design, off=old, off_error=None))
    assert state.off_design.M_inf == pytest.approx(2.8)


def test_below_detachment_shows_error_and_detached_regime(qtbot, window):
    tab = _open_tab(qtbot, window)
    _off(qtbot, window, 2.0)
    assert tab.regime() == "detached"
    assert tab.canvas.overlay.isVisible() and "shock detached" in tab.canvas.error_text
    assert tab.canvas.is_dimmed()
    assert tab.card.text("capture") == "—" and tab.card.text("regime") == "Detached"


def test_design_mach_change_resets_slider_to_design(qtbot, window):
    tab = _open_tab(qtbot, window)
    _off(qtbot, window, 2.5)
    _design(qtbot, window, mach=3.2)
    assert window.state.inputs.off_design_mach is None
    assert tab.slider.value() == pytest.approx(3.2)
    assert tab.slider.range() == (1.2, pytest.approx(4.7))
    assert tab.charts.cursor() == pytest.approx(3.2)


@pytest.mark.parametrize("changes, visible", [
    ({}, True),
    ({"cowl_wedge_deg": 6.0}, False),                      # CFD had a zero-thickness cowl
    ({"mach": 6.7, "n_ramps": 4}, False),                  # X-15
    ({"n_ramps": 3}, False),
    ({"max_cowl_enabled": True}, False),                   # cowl-constrained optimum
    ({"gamma": 1.3}, False),
])
def test_cfd_overlay_only_for_the_validated_design(qtbot, window, changes, visible):
    if changes:
        _design(qtbot, window, **changes)
    charts = _open_tab(qtbot, window).charts
    assert charts.cfd_visible is visible
    assert bool(charts.cfd_items) is visible
    assert charts.cfd_note.isVisibleTo(window) is (not visible)
    if not visible:
        expected = ("CFD validation used a zero-thickness cowl" if "cowl_wedge_deg" in changes
                    else "CFD validation available for the M3 2-ramp design only")
        assert charts.cfd_note.text() == expected


def test_cfd_markers_are_hollow_with_source_tooltips(qtbot, window):
    charts = _open_tab(qtbot, window).charts
    capture, recovery = charts.cfd_items
    assert [p.pos().x() for p in capture.points()] == [2.5, 2.75, 3.0, 3.25]   # no M 3.5
    assert recovery.opts["brush"].color().alpha() == 0                         # hollow
    tip = recovery.points()[3].data()
    assert "Phase 3d inviscid Fluent" in tip and "Mach reflection at lip" in tip
    assert "M 3.5" in tip and "before the terminal shock" in tip
    assert [p.pos().y() for p in recovery.points()] == [0.8466, 0.8283, 0.8011, 0.733]


def test_regime_bands_use_the_wedge(qtbot, window):
    charts = _open_tab(qtbot, window).charts
    assert charts.band_labels == ["2nd ramp shock detached", "spillage",
                                  "overspeed: shocks inside cowl"]
    _design(qtbot, window, cowl_wedge_deg=6.0)
    assert "cowl detached" in charts.band_labels
    cowl = [b for b in charts.bands if b.kind == "cowl"]
    assert cowl[0].hi == pytest.approx(2.6628, abs=1e-3)
    assert "wedge 6°" in charts.legends["margin"].text()
    assert any("upper bound — cowl shock not modelled" in p.replace(" ", " ")
               for p in charts.footer_parts)


def test_above_design_lip_notice_keeps_cfd_out_of_results(qtbot, window):
    """M8.2: CFD comparisons are not in the Results panel; the lip notice's CFD note stays
    available in the Verification tab."""
    _open_tab(qtbot, window)
    _off(qtbot, window, 3.25)
    panel = window.results_panel
    [i] = [k for k, t in enumerate(panel.warning_texts()) if t.startswith("Cowl lip shock")]
    row = panel.warning_rows[i]
    assert "Phase 3d CFD" not in row.toolTip() + row.body.toolTip()
    items = window.state.verification_items()
    assert any("Phase 3d CFD" in it.text for it in items if it.category == "notice")
    # off-design notices are listed only while the off-design view is active
    window.tabs.setCurrentWidget(window.canvas)
    assert not any(t.startswith("Cowl lip shock") for t in panel.warning_texts())


def _quiesce(window):
    """Before a wall-clock measurement: no worker job, no equation render, no garbage."""
    import gc

    from PySide6.QtCore import QThreadPool

    from busemann.explain import warm

    window._warm_timer.stop()
    assert QThreadPool.globalInstance().waitForDone(10000)
    assert warm.join(timeout=30.0)
    gc.collect()


def _drag(qtbot, window, steps=60, measure=False):
    """Drag the off-design slider 2.45 -> 3.04 in 0.01 steps, 8 ms apart. Returns the tab,
    the wall-clock gaps between steps (ms) and the off-design results received. With
    `measure`, the app is quiesced first and the garbage collector is off during the drag."""
    import gc

    tab = _open_tab(qtbot, window)
    was_enabled = gc.isenabled()          # the app's GC guard keeps it off (GUI-thread GC)
    if measure:
        _quiesce(window)
        gc.disable()
    try:
        return _drag_steps(qtbot, window, tab, steps)
    finally:
        if was_enabled:
            gc.enable()


def _drag_steps(qtbot, window, tab, steps):
    import time

    received = []
    window.state.off_design_ready.connect(lambda off, err: received.append(off))
    slider = tab.slider.slider
    slider.setSliderDown(True)
    gaps, last = [], time.perf_counter()
    for k in range(steps):
        slider.setValue(round((2.45 - 1.2) / 0.01) + k)       # 2.45 .. 3.04
        qtbot.wait(8)
        now = time.perf_counter()
        gaps.append((now - last) * 1000.0)
        last = now
    slider.setSliderDown(False)
    qtbot.waitUntil(lambda: window.state.off_design is not None
                    and window.state.off_design.M_inf == pytest.approx(3.04), timeout=5000)
    return tab, gaps, received


def test_slider_drag_coalesces_work_and_ends_on_the_last_value(qtbot, window):
    """Functional part of a drag (no wall-clock limit): debounce and stale-drop coalesce
    the work, and the final state is the last slider position."""
    tab, _, received = _drag(qtbot, window)
    assert len(received) < 60
    assert tab.slider.value() == pytest.approx(3.04)
    assert tab.charts.cursor() == pytest.approx(3.04)


@pytest.mark.perf
def test_slider_drag_stays_responsive(qtbot, window):
    """Wall-clock: the event loop keeps turning during a drag. Step pauses: 95th percentile
    (nearest rank) < 60 ms, and no single pause >= 250 ms."""
    import math

    _, gaps, _ = _drag(qtbot, window, measure=True)
    ordered = sorted(gaps)
    p95 = ordered[math.ceil(0.95 * len(ordered)) - 1]
    message = (f"p95 {p95:.0f} ms, largest step pauses (ms): "
               f"{[round(g) for g in ordered[-5:]]}")
    assert p95 < 60.0, message
    assert ordered[-1] < 250.0, message


# --- M5 STEP 0: results panel follows the slider Mach on this tab ---------------------

def test_kpis_show_slider_mach_values_without_deltas(qtbot, window):
    panel = window.results_panel
    design_text = panel.cards["recovery_total"].text()
    assert panel.title.text().upper() == "RESULTS"
    _open_tab(qtbot, window)
    _off(qtbot, window, 2.5)
    d = window.state.design
    off = api.off_design_point(d, 2.5)
    cards = panel.cards
    assert panel.title.text() == "Results at M∞ 2.50"
    assert cards["recovery_total"].text() == f"{off.recovery_total:.4f}"
    assert cards["M_duct"].text() == f"{off.M_post_terminal:.3f}"
    assert cards["mass_capture"].text() == f"{off.mass_capture_ratio:.3f}"
    assert cards["cowl_margin"].text() == f"{off.cowl_margin_deg:+.2f}"
    # M8.2: no "Δ vs design" lines (the "At slider Mach" card has those)
    assert not any(c.delta_label.isVisibleTo(window) for c in cards.values())
    fs = api.freestream(2.5, altitude_m=window.state.inputs.altitude_m)
    mdot = api.captured_mass_flow(fs, 0.1, off.mass_capture_ratio)
    assert window.state.captured_mass_flow(True) == pytest.approx(mdot)
    # back on the Design tab: design values, no delta lines
    window.tabs.setCurrentWidget(window.canvas)
    assert panel.title.text().upper() == "RESULTS"
    assert cards["recovery_total"].text() == design_text
    assert not cards["recovery_total"].delta_label.isVisibleTo(window)


def test_warnings_grouped_by_design_point_and_slider_mach(qtbot, window):
    panel = window.results_panel
    assert panel.notice_groups() == ["At the design point (M∞ 3.00)"]
    _open_tab(qtbot, window)
    _off(qtbot, window, 3.25)
    assert panel.notice_groups() == ["At the design point (M∞ 3.00)",
                                     "At M∞ 3.25 (off-design)"]
    design_texts = [n[2] for n in window.state.notices() if n[0] == "design"]
    assert any(t.startswith("Cowl near shock detachment (margin 0.28°)") for t in design_texts)
    off = [n for n in window.state.notices() if n[0] == "off"]
    assert any(t.startswith("Cowl lip shock") for _, _, t, _ in off)
    assert all("deg" not in t for t in panel.warning_texts())
    _off(qtbot, window, 2.0)                       # detached ramp shock: error in "off"
    assert "error" in panel.card_levels("off")
    window.tabs.setCurrentWidget(window.canvas)
    assert panel.notice_groups() == ["At the design point (M∞ 3.00)"]


def test_status_bar_splits_design_and_sweep_time(window):
    import re
    assert re.fullmatch(r"design (cached|\d+ ms) · sweep \d+ ms", window.compute_label.text())


def test_chart_legend_wraps_only_between_entries(qtbot, window):
    charts = _open_tab(qtbot, window).charts
    rows = {row for row, _ in charts.legend_entries}
    assert rows == {"bands", "notes"}                       # two clean rows
    for _, text in charts.legend_entries:
        assert " " not in text                              # no breakable space inside
    for label in (charts.band_legend, charts.note_legend):
        assert label.text().count("&nbsp;&nbsp; ") == len(
            [r for r in charts.legend_entries if (r[0] == "bands") == (label is charts.band_legend)]
        ) - 1
