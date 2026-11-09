"""Explain mode (M5, restructured in M8.2): a topic tree in the right column and a popup
window with the explanation; the canvas selection highlights its topic; numbers are api
values; equations render; the right panel stays open while Explain is active."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from inletdesign import api  # noqa: E402

pytestmark = pytest.mark.gui


def _open(qtbot, window):
    drawer = window.explain_drawer
    window.explain_action.setChecked(True)
    qtbot.waitUntil(lambda: not window.is_column_animating(), timeout=2000)
    return drawer


def _labels(drawer):
    out = []
    for key in drawer.topic_keys():
        out.append(drawer._items[key].text(0))
    return out


def _click(drawer, key):
    item = drawer._items[key]
    drawer.tree.itemClicked.emit(item, 0)


@pytest.mark.ui
def test_explain_forces_the_right_column_open_and_locks_its_toggle(qtbot, window):
    window.toggle_right.setChecked(False)
    assert not window.right_column.isVisible()
    drawer = _open(qtbot, window)
    assert window.right_column.isVisible() and window.right_column.currentWidget() is drawer
    assert window.toggle_right.isChecked() and not window.toggle_right.isEnabled()
    window.explain_action.setChecked(False)
    qtbot.waitUntil(lambda: not window.is_column_animating(), timeout=2000)
    assert window.toggle_right.isEnabled()
    assert window.right_column.currentWidget() is window.right_panel


@pytest.mark.ui
def test_tree_lists_the_topics_in_order(qtbot, window):
    drawer = _open(qtbot, window)
    assert _labels(drawer) == [
        "Freestream", "Ramp shock 1", "Ramp shock 2", "Regions", "Behind ramp shock 1",
        "Behind ramp shock 2", "Duct", "Terminal shock", "Cowl lip", "Design method",
        "Off-design", "Separation (approximate)"]
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(n_ramps=4)
    assert [t for t in _labels(drawer) if t.startswith("Ramp shock")] == [
        f"Ramp shock {k}" for k in range(1, 5)]


@pytest.mark.ui
@pytest.mark.parametrize("key, entry", [
    (("item", "shock", 0), "oblique_shock"), (("item", "shock", 2), "normal_shock"),
    (("item", "region", 0), "freestream"), (("item", "region", 1), "region"),
    (("item", "region", 3), "duct"), (("item", "cowl", 0), "cowl_design"),
    (("topic", "method", None), "method"), (("topic", "offdesign", None), "offdesign"),
    (("topic", "separation", None), "separation")])
def test_clicking_a_topic_opens_the_popup(qtbot, window, key, entry):
    drawer = _open(qtbot, window)
    assert not drawer.popup.isVisible()
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, key)
    assert drawer.popup.isVisible() and drawer.entry_name == entry
    assert drawer.popup.title.text() == drawer.rendered.title
    assert drawer.images and all(not img.isNull() for img in drawer.images.values())
    window.explain_action.setChecked(False)
    assert not drawer.popup.isVisible()


def test_canvas_selection_highlights_its_topic(qtbot, window):
    drawer = _open(qtbot, window)
    window.canvas.select("shock", 1)
    assert drawer.current_key() == ("item", "shock", 1)
    assert not drawer.popup.isVisible()                       # highlight only
    window.canvas.select("region", 3)
    assert drawer.current_key() == ("item", "region", 3)
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("item", "cowl", 0))
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):   # popup open: it follows
        window.canvas.select("shock", 0)
    assert drawer.entry_name == "oblique_shock"


def test_shock_numbers_are_api_values(qtbot, window):
    drawer = _open(qtbot, window)
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("item", "shock", 1))
    s = api.design(3.0, 2).shock_states[1]
    shown = {sub.path: sub.text for sub in drawer.rendered.substitutions}
    assert shown["sel.Mn1"] == f"{s.Mn1:.4f}" and shown["sel.beta_deg"] == f"{s.beta_deg:.2f}"
    assert shown["sel.M2"] == f"{s.M2:.4f}" and shown["sel.p0_ratio"] == f"{s.p0_ratio:.4f}"
    assert f"{s.Mn1:.4f}" in drawer.body.toPlainText()          # plain-words paragraph


def test_separation_topic_lists_every_shock(qtbot, window):
    drawer = _open(qtbot, window)
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("topic", "separation", None))
    text = drawer.body.toPlainText()
    assert "Ramp shock 1: not applicable" in text and "Ramp shock 2: p₂/p₁ = 2.818" in text
    assert "Terminal normal shock: M₁ = 1.507" in text


def test_cowl_on_off_design_tab_uses_local_rule(qtbot, window):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(cowl_wedge_deg=6.0)
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.55)
    drawer = _open(qtbot, window)
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("item", "cowl", 0))
    assert drawer.entry_name == "cowl_offdesign"
    off = window.state.off_design
    shown = {sub.path: sub.text for sub in drawer.rendered.substitutions}
    assert shown["off.cowl_margin_deg"] == f"{off.cowl_margin_deg:+.2f}"
    assert shown["off.cowl_required_turn_deg"] == "6.00"


@pytest.mark.ui
def test_popup_never_covers_the_tree(qtbot, window):
    from PySide6.QtCore import QRect

    drawer = _open(qtbot, window)
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("topic", "method", None))
    tree = QRect(drawer.mapToGlobal(drawer.rect().topLeft()), drawer.size())
    popup = drawer.popup.frameGeometry()
    assert not popup.intersects(tree)


def test_gui_thread_never_renders_mathtext_during_a_drag(qtbot, window, monkeypatch):
    """Popup open, render process warming: during a 40-step drag of the off-design slider
    the GUI process makes no mathtext call; the popup catches up after the release."""
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
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("item", "cowl", 0))
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


@pytest.mark.ui
def test_popup_text_as_displayed_has_no_raw_symbols(qtbot, window):
    """M8.2 follow-up: audit the exact plain text the popup shows (sources included) for
    every topic of the tree, with the forbidden-token list of tests/test_text_audit.py."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "text_audit", Path(__file__).parents[1] / "test_text_audit.py")
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)

    drawer = _open(qtbot, window)
    problems = []
    for key in drawer.topic_keys():
        if key[0] == "group":
            continue
        with qtbot.waitSignal(drawer.content_changed, timeout=3000):
            _click(drawer, key)
        shown = drawer.popup.title.text() + "\n" + drawer.body.toPlainText()
        problems += audit._violations(f"popup {key}", shown)
    assert problems == []
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("item", "shock", 0))
    shown = drawer.body.toPlainText()
    assert "M₁ sin β" in shown and "M₂ sin(β − θ)" in shown and "sin(beta" not in shown


@pytest.mark.ui
@pytest.mark.parametrize("kind, index", [("region", 0), ("region", 3), ("shock", 0),
                                         ("shock", 2), ("cowl", 0)])
def test_popup_never_covers_the_selected_canvas_item(qtbot, window, kind, index):
    from PySide6.QtCore import QRect

    window.resize(1440, 900)
    drawer = _open(qtbot, window)
    window.canvas.select(kind, index)
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, (("item", kind, index) if kind != "cowl" else ("item", "cowl", 0)))
    item = window.canvas.selection_screen_rect()
    popup = QRect(drawer.popup.pos(), drawer.popup.size())
    tree = QRect(drawer.mapToGlobal(drawer.rect().topLeft()), drawer.size())
    assert item is not None and not popup.intersects(item), (popup, item)
    assert not popup.intersects(tree)


@pytest.mark.ui
def test_popup_is_a_movable_token_styled_tool_window(qtbot, window):
    from PySide6.QtCore import Qt

    drawer = _open(qtbot, window)
    with qtbot.waitSignal(drawer.content_changed, timeout=3000):
        _click(drawer, ("topic", "method", None))
    popup = drawer.popup
    assert popup.windowFlags() & Qt.WindowType.Tool and not popup.isModal()
    assert popup.objectName() == "explainPopup"
    bg = popup.palette().color(popup.backgroundRole()).name()
    from busemann.theme import tokens
    assert popup.grab().toImage().pixelColor(3, popup.height() // 2).name() == \
        tokens.COLORS["surface"].lower() or bg == tokens.COLORS["surface"].lower()


@pytest.mark.ui
def test_topic_tree_style(qtbot, window):
    drawer = _open(qtbot, window)
    qtbot.wait(50)
    tree = drawer.tree
    item = drawer._items[("item", "region", 0)]
    assert tree.visualItemRect(item).height() == 28
    from PySide6.QtGui import QFontInfo
    from PySide6.QtWidgets import QApplication

    from busemann.theme import qt as theme

    info = QFontInfo(tree.font())
    assert info.pixelSize() == 13 and info.family() == theme.ui_family()
    sheet = QApplication.instance().styleSheet()
    assert "chevron-right-muted.svg" in sheet and "#explainTree::item" in sheet
