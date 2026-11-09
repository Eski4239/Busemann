"""M9c in the GUI: the Analytics "Inlet characteristic" view (branches, buzz onset, labels,
separation line, hover, x range, Moeckel validity band), its worker thread, the diffuser
area-ratio input and the buzz Verification items."""
import importlib.util
import inspect
import math
import re
import threading
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from inletdesign import api  # noqa: E402
from inletdesign import characteristic as C  # noqa: E402

from busemann import verification as V  # noqa: E402
from busemann.analytics import takeaways as T  # noqa: E402
from busemann.views import analytics_tab as A  # noqa: E402

pytestmark = pytest.mark.gui


def _char(qtbot, window, M=None):
    if M is not None:
        with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
            window.state.update(off_design_mach=M)
    tab = window.analytics_tab
    if tab._stale or tab.data.get("theta_curve") is None:
        with qtbot.waitSignal(tab.computed, timeout=10000):
            window.tabs.setCurrentWidget(tab)
    else:
        window.tabs.setCurrentWidget(tab)
    with qtbot.waitSignal(tab.char_computed, timeout=10000):
        tab.set_view("char")
    _settle(qtbot, tab)
    return tab


def _settle(qtbot, tab):
    """Until the drawn characteristic is that of the current inputs (worker idle)."""
    qtbot.waitUntil(lambda: not tab.char_busy() and tab.char_data is not None
                    and tab.char_data.key == tab._char_key(), timeout=10000)


def _hover_marker(chart):
    x, y, _ = chart.marker_text
    return chart.hover_text_at(chart._scene_xy(x, y))


def test_branches_buzz_line_and_labels_at_2_75(qtbot, window):
    tab = _char(qtbot, window, 2.75)
    chart = tab.char_chart
    d, off = window.state.design, window.state.off_design
    c = api.inlet_characteristic(d, off, 2.0)
    assert tab.characteristic == c
    assert set(chart.series) == {"super", "sub"}                    # nothing past the onset
    assert chart.series["super"]["y"] == tuple(p.recovery for p in c.supercritical)
    assert chart.marker_text[:2] == (c.critical.mfr, c.critical.recovery)
    assert chart.vline.value() == pytest.approx(c.buzz.mfr)
    assert chart.vline.label.toPlainText() == A.BUZZ_LINE_TEXT
    assert A.BUZZ_BAND_TEXT == "buzz (unsteady, approximate)"
    lo, hi = c.buzz.mfr - 0.05, c.critical.mfr + 0.03               # onset < critical here
    assert chart.x_range == pytest.approx((lo, hi), rel=1e-12)
    assert chart.bands == [(pytest.approx(lo), pytest.approx(c.buzz.mfr), A.BUZZ_BAND_TEXT)]
    (vx0, vx1), (vy0, vy1) = chart.plot.getPlotItem().vb.viewRange()
    assert (vx0, vx1) == pytest.approx((lo, hi), abs=1e-9)
    assert vy0 <= c.critical.recovery <= vy1                         # y follows the data
    assert chart.title.text() == A.CHAR_TITLE.format(M=2.75)
    assert "(approximate)" in chart.title.text()
    assert "supercritical (quasi-1D)" in chart.legend.text()
    assert "subcritical (approximate)" in chart.legend.text()
    # the stable branch ends exactly at the onset
    assert chart.series["sub"]["x"][-1] == pytest.approx(c.buzz.mfr, rel=1e-12)
    assert tab.char_takeaway.text() == T.characteristic(c)
    assert A.EXTRAPOLATED_TEXT in tab.char_caption.text()           # 2.75 > 2.7
    assert "Busemann extension" in tab.char_caption.text()
    assert "Busemann extension" in tab.char_caption.toolTip()
    assert not tab.selection_row.isVisibleTo(tab)                   # nothing to pick


def test_on_lip_case_has_no_stable_range(qtbot, window):
    tab = _char(qtbot, window, 3.0)
    c, chart = tab.characteristic, tab.char_chart
    assert c.buzz.zero_range and c.buzz.mfr == 1.0 and not c.buzz.exact_used
    assert "no stable subcritical range" in tab.char_takeaway.text()
    crit = c.critical.mfr
    assert chart.x_range == pytest.approx((crit - 0.05, crit + 0.05), rel=1e-12)
    assert chart.bands == [(pytest.approx(crit - 0.05), pytest.approx(crit), A.BUZZ_BAND_TEXT)]
    text = _hover_marker(chart)
    assert A.NO_TRIPLE_POINT in text
    assert re.sub("<[^>]+>", "", A.NO_TRIPLE_POINT) == (
        "no regular triple point; vortex sheet taken along θn")


def test_below_the_validity_limit_the_band_replaces_the_onset(qtbot, window):
    tab = _char(qtbot, window, 2.5)
    c, chart = tab.characteristic, tab.char_chart
    assert not c.valid and c.M_n < C.MOECKEL_MIN_MACH
    assert set(chart.series) == {"super"} and chart.vline is None
    assert A.VALIDITY_BAND_TEXT == ("outside the method's validity (flow behind the last ramp "
                                    "near Mach 1, Moeckel TN 1921 p. 14)")
    crit = c.critical.mfr
    assert chart.bands == [(pytest.approx(crit - 0.05), pytest.approx(crit),
                            A.VALIDITY_BAND_TEXT)]
    assert "stable subcritical range is not computed" in tab.char_takeaway.text()
    assert "TN 1921 p. 14" in tab.char_caption.text()
    assert not tab.char_separation.isVisibleTo(tab)


def test_no_extrapolation_label_inside_the_tested_range(qtbot, window):
    tab = _char(qtbot, window, 2.6)
    assert A.EXTRAPOLATED_TEXT not in tab.char_caption.text()
    assert not tab.characteristic.buzz.extrapolated


def test_separation_line_follows_the_separation_check(qtbot, window):
    tab = _char(qtbot, window, 2.75)
    d = window.state.design
    assert any(s.shock.startswith("ramp") and s.flagged for s in d.separation)
    assert tab.char_separation.isVisibleTo(tab)
    assert tab.char_separation.text() == A.SEPARATION_LINE
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=2.0)                    # 2 ramps at M 2.0: nothing flagged
    qtbot.waitUntil(lambda: window.state.off_design is not None, timeout=5000)
    qtbot.wait(300)
    assert not any(s.shock.startswith("ramp") and s.flagged
                   for s in window.state.design.separation)
    tab.update_characteristic()
    _settle(qtbot, tab)
    assert not tab.char_separation.isVisibleTo(tab)


def test_hover_shows_throttle_spill_and_shock_position(qtbot, window):
    tab = _char(qtbot, window, 2.75)
    chart = tab.char_chart
    stable = chart.series["sub"]
    k = len(stable["x"]) // 2
    text = chart.hover_text_at(chart.view_point_scene("sub", k))
    assert text.startswith("Subcritical (approximate)")
    assert "Throttle p<sub>x</sub>/p<sub>0∞</sub>" in text and "Spilled fraction τ" in text
    assert "ahead of the lip (Moeckel)" in text
    onset = chart.hover_text_at(chart.view_point_scene("sub", len(stable["x"]) - 1))
    assert "buzz onset (Ferri–Nucci, approximate)" in onset
    sup = chart.hover_text_at(chart.view_point_scene("super", 5))
    assert "Supercritical (quasi-1D)" in sup and "Shock Mach" in sup


def test_area_ratio_input_redraws_without_a_redesign(qtbot, window):
    tab = _char(qtbot, window, 2.75)
    field = window.design_panel.diffuser_ratio
    assert (field.minimum(), field.maximum(), field.spin.singleStep()) == (1.0, 4.0, 0.1)
    generation = window.state._generation
    field.edit.setText("3")
    field.edit.editingFinished.emit()
    qtbot.waitUntil(lambda: tab.characteristic is not None and
                    tab.characteristic.area_ratio == 3.0, timeout=3000)
    assert window.state._generation == generation
    assert tab.characteristic.supercritical[-1].area_shock == pytest.approx(3.0)
    field.edit.setText("9")
    field.edit.editingFinished.emit()
    assert field.value() == 4.0 and field.note() == "Maximum 4"


def test_buzz_verification_items(window):
    items = window.state.verification_items()
    titles = [i.title for i in items]
    assert V.BUZZ_SEPARATION_TITLE in titles                 # validation design is flagged
    assert "Inlet characteristic and buzz onset are approximate" in titles
    info = next(i for i in items if i.title.startswith("Inlet characteristic"))
    assert "NACA TN 1921" in info.source and "RM L50K30" in info.source
    assert "Busemann extension" in info.source


@pytest.mark.ui
def test_characteristic_text_audit(qtbot, window):
    spec = importlib.util.spec_from_file_location(
        "text_audit", Path(__file__).resolve().parents[1] / "test_text_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tab = _char(qtbot, window, 2.75)
    chart = tab.char_chart
    texts = [tab.char_takeaway.text(), tab.char_caption.text(), tab.char_separation.text(),
             chart.title.text(), chart.legend.text(), A.EXTENSION_TIP, A.BUZZ_BAND_TEXT,
             A.VALIDITY_BAND_TEXT, A.NO_TRIPLE_POINT]
    for key, s in chart.series.items():
        texts += [s["text"](i) for i in range(0, len(s["x"]), 5)]
    plain = [re.sub("<[^>]+>", "", t) for t in texts]
    assert [v for t in plain for v in mod._violations("characteristic", t)] == []
    assert not any("_" in t or re.search(r"phase\s*3", t, re.I) for t in plain)
    assert all(math.isfinite(x) for x in chart.series["super"]["x"])


@pytest.mark.ui
def test_text_below_the_validity_limit_passes_the_audit(qtbot, window):
    spec = importlib.util.spec_from_file_location(
        "text_audit", Path(__file__).resolve().parents[1] / "test_text_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tab = _char(qtbot, window, 2.5)
    plain = [re.sub("<[^>]+>", "", t) for t in (tab.char_takeaway.text(),
                                                 tab.char_caption.text())]
    assert [v for t in plain for v in mod._violations("characteristic", t)] == []
    assert not any("_" in t for t in plain)


# --- worker thread (spec 1: no GUI-thread job over 50 ms) ----------------------------------

def test_gui_thread_never_runs_the_characteristic_during_a_slider_drag(qtbot, window,
                                                                        monkeypatch):
    """Every function of inletdesign.characteristic is wrapped to record its thread; a
    60-step drag of the off-design slider (2.45 -> 3.04) with the characteristic view open
    must run all of them on the worker."""
    tab = _char(qtbot, window, 2.75)
    calls = {"gui": [], "worker": 0}
    main = threading.main_thread()

    def wrap(name, fn):
        def recorder(*args, **kwargs):
            if threading.current_thread() is main:
                calls["gui"].append(name)
            else:
                calls["worker"] += 1
            return fn(*args, **kwargs)
        return recorder

    for name, fn in list(vars(C).items()):
        if inspect.isfunction(fn) and fn.__module__ == C.__name__:
            monkeypatch.setattr(C, name, wrap(name, fn))
    slider = window.offdesign_tab.slider.slider
    slider.setSliderDown(True)
    for k in range(60):
        slider.setValue(round((2.45 - 1.2) / 0.01) + k)            # 2.45 .. 3.04
        qtbot.wait(8)
    slider.setSliderDown(False)
    qtbot.waitUntil(lambda: window.state.off_design is not None
                    and window.state.off_design.M_inf == pytest.approx(3.04), timeout=5000)
    _settle(qtbot, tab)
    assert tab.characteristic is not None and tab.characteristic.M_inf == pytest.approx(3.04)
    assert calls["gui"] == []
    assert calls["worker"] > 0
    # redraw from the cache and hover need no model calls either
    tab.update_characteristic()
    chart = tab.char_chart
    chart.hover_text_at(chart.view_point_scene("super", 3))
    assert calls["gui"] == []
