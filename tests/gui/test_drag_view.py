"""M9b drag in the GUI: the Analytics "Drag (inviscid estimate)" view, the off-design card
rows, the cowl frontal height input and the Verification item."""
import importlib.util
import math
import re
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from inletdesign import api  # noqa: E402

from busemann.analytics import takeaways as T  # noqa: E402
from busemann.views import analytics_tab as A  # noqa: E402

pytestmark = pytest.mark.gui


def _drag(qtbot, window):
    tab = window.analytics_tab
    if tab._stale or tab.data.get("theta_curve") is None:
        with qtbot.waitSignal(tab.computed, timeout=10000):
            window.tabs.setCurrentWidget(tab)
    else:
        window.tabs.setCurrentWidget(tab)
    tab.set_view("drag")
    qtbot.wait(50)
    return tab


def test_drag_vs_mach_curves_and_design_line(qtbot, window):
    tab = _drag(qtbot, window)
    assert tab.pages.currentIndex() == A.PAGES["drag"]
    chart = tab.drag_chart
    assert set(chart.series) == {"add", "cowl", "total"}
    d, sweep = window.state.design, window.state.sweep
    ds = api.drag_sweep(d, sweep, 0.10)
    assert chart.series["add"]["x"] == ds.machs
    for k, (a, c) in enumerate(zip(ds.cd_add, ds.cd_cowl)):
        got_a, got_c = chart.series["add"]["y"][k], chart.series["cowl"]["y"][k]
        assert (math.isnan(got_a) if a is None else got_a == a)
        assert (math.isnan(got_c) if c is None else got_c == c)
    assert chart.vline.value() == pytest.approx(3.0)
    assert "inviscid estimate: pressure drag only, no skin friction" in \
        tab.drag_caption.text().lower()
    above = [a for M, a in zip(ds.machs, ds.cd_add) if M >= 3.0]
    assert above and all(a == 0.0 for a in above)              # no spillage at/above design
    assert all(a > 0.0 for M, a in zip(ds.machs, ds.cd_add) if M < 3.0 and a is not None)


def test_gaps_are_shaded_and_labelled_where_not_computable(qtbot, window):
    tab = _drag(qtbot, window)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(n_ramps=3)                 # cowl detached at the design Mach
    qtbot.wait(100)
    chart = tab.drag_chart
    labels = [b[2] for b in chart.bands]
    assert "cowl shock detached: not computable" in labels
    lo, hi, _ = next(b for b in chart.bands if b[2].startswith("cowl shock detached"))
    assert lo < 3.05 < hi
    ys = chart.series["cowl"]["y"]
    xs = chart.series["cowl"]["x"]
    assert all(math.isnan(y) for x, y in zip(xs, ys) if lo < x < hi)      # a gap
    assert tab.drag_takeaway.text().endswith("so the cowl drag is not computable.")
    tip = chart.hover_text_at(chart._scene_xy(xs[0], chart.series["add"]["y"][0]))
    assert tip is None or "M∞" in tip


def test_recovery_vs_cowl_drag_hover_and_takeaway(qtbot, window):
    tab = _drag(qtbot, window)
    chart = tab.rc_chart
    assert set(chart.series) == {1, 2, 3, 4, "isentropic"}
    c = tab.data[("turn", 2)]
    j = len(tab._rc_index[2]) // 2
    i = tab._rc_index[2][j]
    cd = api.cowl_drag_vs_turning(3.0, (c.delta_deg[i],))[0]
    text = chart.hover_text_at(chart.view_point_scene(2, j))
    assert text.startswith("2 ramps at M 3.00")
    assert f"Turning (cowl angle) {c.delta_deg[i]:.2f}°" in text
    assert f"Recovery {c.recovery_total[i]:.4f}" in text and f"{cd:.4f}" in text
    theta = api.max_deflection(3.0)
    kept = [c.delta_deg[k] for k in tab._rc_index[3]]
    assert max(kept) < theta                           # past θmax: left out
    optima, match = tab.data["optima"], tab.data["match"]
    matches = {m: api.cowl_drag_vs_turning(3.0, (delta,))[0] for m, delta in match[2].items()}
    cd2 = api.cowl_drag_vs_turning(3.0, (optima[2][1],))[0]
    assert tab.rc_takeaway.text() == T.recovery_vs_cowl(3.0, 2, optima[2][0], cd2, matches)


def test_pick_on_recovery_vs_cowl_drag_applies_the_turning_point(qtbot, window):
    tab = _drag(qtbot, window)
    chart = tab.rc_chart
    j = 10
    i = tab._rc_index[3][j]
    c = tab.data[("turn", 3)]
    chart.pick_at(chart.view_point_scene(3, j))
    assert tab.selection["changes"]["n_ramps"] == 3
    assert tab.selection["changes"]["max_cowl_deg"] == pytest.approx(c.delta_deg[i], abs=1e-5)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        tab.apply_selection()
    assert window.state.design.recovery_total == pytest.approx(c.recovery_total[i], abs=1e-6)


def test_frontal_height_rescales_the_cowl_drag_without_a_recompute(qtbot, window):
    tab = _drag(qtbot, window)
    field = window.design_panel.cowl_height
    assert (field.minimum(), field.maximum(), field.spin.singleStep()) == (0.01, 1.0, 0.01)
    before = list(tab.drag_chart.series["cowl"]["y"])
    generation = window.state._generation
    field.edit.setText("0.2")
    field.edit.editingFinished.emit()
    qtbot.waitUntil(lambda: window.state.inputs.cowl_frontal_height == 0.2, timeout=2000)
    assert window.state._generation == generation                 # no redesign
    after = tab.drag_chart.series["cowl"]["y"]
    for a, b in zip(before, after):
        if not math.isnan(a):
            assert b == pytest.approx(2.0 * a, rel=1e-12)
    assert "0.20 × capture height" in tab.drag_caption.text()
    field.edit.setText("3")
    field.edit.editingFinished.emit()
    assert field.value() == 1.0 and field.note() == "Maximum 1"
    with qtbot.waitSignal(window.state.design_ready, timeout=5000, raising=False):
        window.undo.stack.undo()
    qtbot.waitUntil(lambda: window.state.inputs.cowl_frontal_height == 0.2, timeout=2000)


def test_offdesign_card_drag_rows(qtbot, window):
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.5)
    card = window.offdesign_tab.card
    d, off = window.state.design, window.state.off_design
    assert card.text("cd_add") == f"{api.additive_drag(d, off):.4f}"
    assert card.text("cd_add") == "0.2043"                     # validation design, M 2.5
    cowl = api.cowl_drag(off, 0.10)
    assert card.text("cd_cowl") == f"{cowl.cd:.4f}"
    assert card.names["cd_add"].text() == "C<sub>D,add</sub>"
    assert "no skin friction" in card.names["cd_add"].toolTip()
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(n_ramps=3)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=3.0)
    assert card.text("cd_cowl") == "—"
    assert card.values["cd_cowl"].toolTip().startswith("Cowl shock detached")


def test_verification_item_and_notes(window, tmp_path):
    items = window.state.verification_items()
    drag = [i for i in items if i.category == "drag"]
    assert len(drag) == 1
    item = drag[0]
    for word in ("skin friction", "subcritical spillage", "frontal height", "3D effects"):
        assert word in item.text
    assert "NACA Report 1187" in item.source and "eq. (5)/(5a), p. 2" in item.source
    assert "per unit width" in item.source and "pending" not in item.source
    from busemann.export import notes as N
    from busemann.export.metadata import metadata
    text = N.render(metadata(window.state.inputs, "geometry DXF"), items)
    assert item.title in text and item.text in text


@pytest.mark.ui
def test_drag_text_has_no_raw_symbols():
    spec = importlib.util.spec_from_file_location(
        "text_audit", Path(__file__).resolve().parents[1] / "test_text_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    d = api.design(3.0, 2)
    ds = api.drag_sweep(d, api.off_design_sweep(d, 2.4, 3.6, 13))
    texts = [T.drag_vs_mach(3.0, ds.machs, ds.cd_add, 0.112), A.DRAG_CAPTION.format(h=0.1),
             A.gap_label(api.COWL_DETACHED_REASON), A.gap_label(api.COWL_SUBSONIC_REASON),
             api.DRAG_LABEL]
    problems = [v for t in texts for v in mod._violations("drag", re.sub("<[^>]+>", "", t))]
    assert problems == [] and not any("_" in t for t in texts)


def test_nonuniform_cowl_face_note_in_card_hover_and_verification(qtbot, window, tmp_path):
    """Validation design at M 2.55: the ramp shocks meet 0.097 h_c above the lip, inside the
    default cowl frontal height (0.10)."""
    note = api.NONUNIFORM_NOTE[:1].upper() + api.NONUNIFORM_NOTE[1:]
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.55)
    card = window.offdesign_tab.card
    assert card.drag_note.isVisibleTo(card) and card.drag_note.text() == note + "."
    assert note in card.values["cd_cowl"].toolTip()
    items = window.state.verification_items()
    face = [i for i in items if i.title.startswith("Cowl drag: non-uniform face pressure")]
    assert len(face) == 1 and "M∞ 2.55" in face[0].title and note in face[0].text
    from busemann.export import notes as N
    from busemann.export.metadata import metadata
    assert face[0].title in N.render(metadata(window.state.inputs, "geometry DXF"), items)
    # the drag-vs-M∞ hover carries it where it applies
    tab = window.analytics_tab
    with qtbot.waitSignal(tab.computed, timeout=10000):
        window.tabs.setCurrentWidget(tab)
    tab.set_view("drag")
    ds = api.drag_sweep(window.state.design, window.state.sweep, 0.10)
    k = next(i for i, n in enumerate(ds.notes) if n)
    chart = tab.drag_chart
    text = chart.series["add"]["text"](k)
    assert note in text
    clear = next(i for i, n in enumerate(ds.notes) if not n and ds.cd_cowl[i] is not None)
    assert note not in chart.series["add"]["text"](clear)
    # at the design Mach: no note anywhere
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=3.0)
    assert not card.drag_note.isVisibleTo(card)
    assert not [i for i in window.state.verification_items()
                if i.title.startswith("Cowl drag: non-uniform")]
    # a smaller frontal height clears it at M 2.55 too
    window.state.update(cowl_frontal_height=0.05)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.55)
    assert not card.drag_note.isVisibleTo(card)
