"""M10 Compare tab: pin, unpin, swap (one undo step), load into A (Busemann and foreign DXF) and
B, the frozen pin, edge cases (ramp counts, failed design, units), the shared view, overlay,
off-design curves, Copy table, and that every computation runs on the worker thread."""
import inspect
import threading

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from busemann import compare as C  # noqa: E402
from busemann import project as P  # noqa: E402
from busemann.theme import tokens  # noqa: E402
from busemann.views.compare_tab import _key  # noqa: E402

pytestmark = pytest.mark.gui


def _settle(qtbot, window, pinned=None):
    tab, s = window.compare_tab, window.state

    def done():
        if s.is_busy() or s._timer.isActive() or tab.busy():
            return False
        if not tab.isVisible():
            return True                     # a hidden tab defers its work until shown
        b = tab.evaluated["B"]
        if b is None or _key(b.snapshot.inputs, b.slider_mach) != _key(s.inputs,
                                                                     s.off_design_mach()):
            return False
        if tab.pinned is not None:
            a = tab.evaluated["A"]
            return a is not None and a.snapshot is tab.pinned
        return True

    qtbot.waitUntil(done, timeout=20000)
    return tab


def _open(qtbot, window):
    window.tabs.setCurrentWidget(window.compare_tab)
    return _settle(qtbot, window)


def _pin(qtbot, window):
    window.compare_tab.pin_current()
    return _settle(qtbot, window)


def _change(qtbot, window, **changes):
    with qtbot.waitSignal(window.state.design_ready, timeout=10000):
        window.state.update(**changes)
    return _settle(qtbot, window)


def _cells(tab, label):
    r = [C.plain(row.label) for row in tab.rows].index(label)
    return [tab.table.item(r, c).text() for c in range(5)], tab.table.item(r, 3)


# --- pin / unpin -----------------------------------------------------------------------------

def test_empty_slot_a_and_pin_button_on_the_design_tab_only(qtbot, window):
    assert window.pin_button.isVisibleTo(window)
    tab = _open(qtbot, window)
    assert not window.pin_button.isVisibleTo(window)
    assert tab.pinned is None and tab.a_stack.currentWidget() is tab.empty_a
    from busemann.views.compare_tab import EMPTY_A
    assert tab.empty_a.text() == EMPTY_A
    assert "nothing pinned" in tab.title.text()
    assert not tab.swap_button.isEnabled() and not tab.unpin_button.isEnabled()
    assert all(row.a in ("", C.DASH) for row in tab.rows)


def test_pin_by_button_and_by_p_asks_before_replacing(qtbot, window):
    window.pin_button.click()
    tab = _open(qtbot, window)
    assert tab.pinned.inputs == window.state.inputs and tab.pinned.label == C.DEFAULT_NAME
    assert tab.a_stack.currentWidget() is tab.canvases["A"]
    first = tab.pinned
    _change(qtbot, window, n_ramps=3)
    asked = []
    tab.ask_replace = lambda: asked.append(1) or False
    window.tabs.setCurrentWidget(window.canvas)
    window.canvas.setFocus()
    qtbot.keyClick(window, Qt.Key.Key_P)
    assert asked == [1] and tab.pinned is first                    # "No": pin kept
    tab.ask_replace = lambda: True
    qtbot.keyClick(window, Qt.Key.Key_P)
    assert tab.pinned is not first and tab.pinned.inputs.n_ramps == 3


def test_pin_then_change_the_design_leaves_a_unchanged(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    pinned, design = tab.pinned, tab.pinned.design
    rec_text = _cells(tab, "Total recovery")[0][1]
    assert design is not window.state.design and design == window.state.design  # deep copy
    _change(qtbot, window, n_ramps=3, max_cowl_enabled=True, max_cowl_deg=25.0)
    assert tab.pinned is pinned and tab.pinned.design is design
    assert tab.pinned.inputs.n_ramps == 2 and design.inputs.n_ramps == 2
    assert tab.views["A"].design is design
    assert _cells(tab, "Total recovery")[0][1] == rec_text
    assert _cells(tab, "Total recovery")[0][2] == f"{window.state.design.recovery_total:.4f}"


def test_unpin_clears_a(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    tab.unpin_button.click()
    assert tab.pinned is None and tab.evaluated["A"] is None
    assert tab.a_stack.currentWidget() is tab.empty_a and not tab.overlay_on()


def test_swap_is_one_undo_step_for_the_live_side(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)                                            # A: 2 ramps
    _change(qtbot, window, n_ramps=3, max_cowl_enabled=True, max_cowl_deg=25.0)
    count = window.undo.stack.count()
    with qtbot.waitSignal(window.state.design_ready, timeout=10000):
        tab.swap_button.click()
    _settle(qtbot, window)
    assert window.state.inputs.n_ramps == 2 and not window.state.inputs.max_cowl_enabled
    assert tab.pinned.inputs.n_ramps == 3 and tab.pinned.inputs.max_cowl_enabled
    assert window.undo.stack.count() == count + 1
    with qtbot.waitSignal(window.state.design_ready, timeout=10000):
        window.undo.stack.undo()
    _settle(qtbot, window)
    assert window.state.inputs.n_ramps == 3                         # live side restored
    assert tab.pinned.inputs.n_ramps == 3                          # the pin is not undone


# --- loading --------------------------------------------------------------------------------

def test_load_a_busemann_dxf_into_a_restores_every_input(qtbot, window, tmp_path):
    from busemann.inputs import Inputs

    saved = Inputs(mach=2.6, n_ramps=3, method="custom", custom_angles=(5.0, 6.0, 7.5),
                   capture_height_m=0.25, cowl_wedge_deg=4.0, altitude_m=18000.0)
    path = tmp_path / "case.dxf"
    P.save(path, saved, design=P.design_for(saved))
    tab = _open(qtbot, window)
    assert tab.load_into_a(str(path))
    _settle(qtbot, window)
    assert tab.pinned.inputs == P.load(path)[0]
    assert tab.pinned.inputs.custom_angles == (5.0, 6.0, 7.5)
    assert not tab.pinned.imported and tab.pinned.label == "case"
    assert not tab.imported_note.isVisibleTo(tab)
    assert tab.conditions_note.isVisibleTo(tab)                    # M 2.6, 18 km vs M 3, 20 km
    assert tab.conditions_note.text() == "A and B use different flight conditions"


def test_load_a_foreign_dxf_into_a_uses_the_current_flight_conditions(qtbot, window,
                                                                      tmp_path):
    from inletdesign import api
    from inletdesign.export import export_dxf

    d = api.design(3.0, 3, ramp_angles=[6.0, 7.0, 8.0])
    path = export_dxf(api.inlet_geometry(d), tmp_path / "from_cad.dxf")
    tab = _open(qtbot, window)
    _change(qtbot, window, altitude_m=15000.0)
    assert tab.load_into_a(str(path))
    _settle(qtbot, window)
    a = tab.pinned
    assert a.imported and a.inputs.method == "custom"
    assert a.inputs.custom_angles == pytest.approx((6.0, 7.0, 8.0), abs=1e-9)
    assert a.inputs.altitude_m == 15000.0 and a.inputs.mach == window.state.inputs.mach
    assert tab.imported_note.isVisibleTo(tab) and C.IMPORTED_NOTE in tab.imported_note.text()
    assert "from_cad" in tab.title.text()
    assert not window.banner.isVisibleTo(window)                   # the live design is untouched
    assert window.state.inputs.method == "oswatitsch"


def test_unreadable_dxf_into_a_shows_the_error(qtbot, window, tmp_path):
    import ezdxf

    doc = ezdxf.new()
    doc.modelspace().add_circle((0, 0), 5)
    path = tmp_path / "circle.dxf"
    doc.saveas(path)
    shown = []
    window.project.show_error = shown.append
    tab = _open(qtbot, window)
    assert tab.load_into_a(str(path)) is False
    assert shown and "no ramp line found" in shown[0] and tab.pinned is None


def test_load_into_b_is_file_open(qtbot, window):
    calls = []
    window.project.open = lambda *a: calls.append(a) or True
    tab = _open(qtbot, window)
    tab.load_b_button.click()
    assert calls == [()]


def test_pin_is_not_saved_in_the_dxf(qtbot, window, tmp_path):
    import ezdxf

    _open(qtbot, window)
    _pin(qtbot, window)
    path = tmp_path / "saved.dxf"
    assert window.project._write(path)
    keys = {k for k in P.custom_header(ezdxf.readfile(path)) if k.startswith(P.PREFIX)}
    expected = set(P.header_values(window.state.inputs, window.project.view()))
    assert keys == expected                       # only the live design's inputs and view
    assert not any("PIN" in k or "COMPARE" in k for k in P.custom_header(ezdxf.readfile(path)))


# --- edge cases ------------------------------------------------------------------------------

def test_different_numbers_of_ramps(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    _change(qtbot, window, n_ramps=3)
    cells, _ = _cells(tab, "Ramp 3 angle")
    assert cells[1] == C.DASH and cells[2] != C.DASH and cells[3] == C.DASH
    assert _cells(tab, "Ramps")[0][1:4] == ["2", "3", "+1"]


def test_failed_live_design_greys_b_and_dashes_the_deltas(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    _change(qtbot, window, method="custom", custom_angles=(30.0, 30.0))
    assert window.state.design is None
    canvas = tab.canvases["B"]
    assert canvas.error_text and canvas.is_dimmed()
    results = tab.rows[[r.label for r in tab.rows].index("Results") + 1:]
    assert all(r.delta == C.DASH and r.b == C.DASH for r in results)
    assert tab.canvases["A"].error_text is None


def test_units_switch_converts_both_columns(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    assert _cells(tab, "p∞")[0][1].endswith(" kPa")
    window.state.update(units="Imperial")
    cells = _cells(tab, "p∞")[0]
    assert cells[1].endswith(" psi") and cells[2].endswith(" psi") and cells[3].endswith(" psi")
    assert _cells(tab, "Capture height")[0][1].endswith(" in")
    assert tab.views["A"].inputs.units == "Imperial"


def test_delta_colour_and_tooltip_follow_the_better_direction(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    _change(qtbot, window, n_ramps=3, max_cowl_enabled=True, max_cowl_deg=25.0)
    _, rec = _cells(tab, "Total recovery")
    assert rec.foreground().color() == QColor(tokens.COLORS["warn"])     # B recovers less
    assert rec.toolTip() == C.METRIC["recovery"].why
    _, cowl = _cells(tab, "Cowl angle")
    assert cowl.foreground().color() == QColor(tokens.COLORS["ok"])      # smaller cowl turn
    _, neutral = _cells(tab, "M after terminal shock")
    assert neutral.toolTip() == "" and neutral.foreground().style() == Qt.BrushStyle.NoBrush


# --- view --------------------------------------------------------------------------------------

def test_same_colour_map_and_shared_zoom(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    _change(qtbot, window, mach=2.6, n_ramps=3)
    a, b = tab.canvases["A"], tab.canvases["B"]
    assert a.inlet_scene.mach_edges == b.inlet_scene.mach_edges
    assert a.inlet_scene.mach_edges[-1] == pytest.approx(3.0)       # highest M∞ of the two
    assert a.legend_labels() == b.legend_labels()
    a.zoom(1.5)
    assert b.scale_factor() == pytest.approx(a.scale_factor())
    b.zoom(0.8)
    assert a.scale_factor() == pytest.approx(b.scale_factor())
    assert not a.handles_enabled() and not b.handles_enabled()


def test_overlay_draws_a_dashed_over_b(qtbot, window):
    tab = _open(qtbot, window)
    assert not tab.overlay_button.isEnabled()
    _pin(qtbot, window)
    _change(qtbot, window, n_ramps=3)
    tab.overlay_button.click()
    assert tab.overlay_on() and not tab.columns["A"].isVisibleTo(tab)
    items = tab.overlay_items()
    n_shocks = len(tab.pinned.design.shock_states)
    assert len(items) == 3 + n_shocks
    assert all(i.pen().style() == Qt.PenStyle.DashLine and i.scene() is
               tab.canvases["B"].inlet_scene for i in items)
    tab.overlay_button.click()
    assert tab.overlay_items() == [] and tab.columns["A"].isVisibleTo(tab)


def test_offdesign_curves_collapsed_by_default(qtbot, window):
    tab = _open(qtbot, window)
    assert not tab.curves_expanded() and not tab.curves_strip.isVisibleTo(tab)
    _pin(qtbot, window)
    _change(qtbot, window, n_ramps=3)
    tab.curves_toggle.click()
    assert tab.curves_strip.isVisibleTo(tab)
    for key in ("capture", "recovery", "margin"):
        assert tab.charts.slot_data("A", key) is not None
        assert tab.charts.slot_data("B", key) is not None
    style = {s: tab.charts.curves[(s, "capture")].opts["pen"].style() for s in "AB"}
    assert style == {"A": Qt.PenStyle.DashLine, "B": Qt.PenStyle.SolidLine}
    assert tab.charts.design_lines[("A", "capture")].value() == pytest.approx(3.0)


def test_copy_table(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    tab.copy_button.click()
    text = QApplication.clipboard().text()
    assert text.split("\n")[0] == f"Metric\tA: {C.DEFAULT_NAME}\tB: {C.LIVE_NAME}\tΔ\tΔ%"
    assert "Total recovery\t" in text


def test_text_passes_the_audit(qtbot, window):
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "text_audit", Path(__file__).resolve().parents[1] / "test_text_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    texts = [C.plain(t) for r in tab.rows for t in (r.label, r.a, r.b, r.why or "")]
    from busemann.views.compare_tab import EMPTY_A, OVERLAY_TEXT
    texts += [EMPTY_A, OVERLAY_TEXT, C.IMPORTED_NOTE,
              C.DIFFERENT_CONDITIONS, C.plain(tab.title.text())]
    assert [v for t in texts for v in mod._violations("compare", t)] == []


# --- worker thread (spec 1: the GUI thread only draws) -----------------------------------------

def test_gui_thread_never_computes_a_slot(qtbot, window, monkeypatch, tmp_path):
    tab = _open(qtbot, window)
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

    for name in ("evaluate", "snapshot_from_inputs"):
        monkeypatch.setattr(C, name, wrap(name, getattr(C, name)))
    _pin(qtbot, window)
    for k in range(30):                                            # off-design Mach drag
        window.state.update(off_design_mach=round(2.45 + 0.02 * k, 2))
        qtbot.wait(8)
    _settle(qtbot, window)
    path = tmp_path / "case.dxf"
    P.save(path, window.state.inputs, design=window.state.design)
    tab.ask_replace = lambda: True
    tab.load_into_a(str(path))
    _settle(qtbot, window)
    window.state.update(units="Imperial")                          # redraw from the cache
    assert calls["gui"] == [] and calls["worker"] > 0


def test_narrow_width_stacks_a_above_b(qtbot, window):
    from PySide6.QtWidgets import QBoxLayout

    tab = _open(qtbot, window)
    window.resize(1700, 900)
    qtbot.wait(50)
    assert tab.canvas_host.width() >= 900
    assert tab.columns_layout.direction() == QBoxLayout.Direction.LeftToRight
    window.resize(900, 900)
    qtbot.wait(50)
    assert tab.canvas_host.width() < 900
    assert tab.columns_layout.direction() == QBoxLayout.Direction.TopToBottom
    window.resize(1700, 900)
    qtbot.wait(50)
    assert tab.columns_layout.direction() == QBoxLayout.Direction.LeftToRight


def test_narrow_width_overlay_still_works(qtbot, window):
    tab = _open(qtbot, window)
    _pin(qtbot, window)
    _change(qtbot, window, n_ramps=3)
    window.resize(700, 900)
    qtbot.wait(50)
    tab.overlay_button.click()
    assert tab.overlay_on() and not tab.columns["A"].isVisibleTo(tab)
    tab.overlay_button.click()
    assert not tab.overlay_on() and tab.columns["A"].isVisibleTo(tab)
    assert inspect.isfunction(C.evaluate)
