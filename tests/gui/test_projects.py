"""Projects in the app (M6): File menu, dirty flag and title, prompt, recent list, drop and
command-line open."""
import json

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402

from busemann import project as P  # noqa: E402
from busemann.inputs import Inputs  # noqa: E402

pytestmark = pytest.mark.gui


def _save_file(tmp_path, name="case.busemann", **inputs):
    path = tmp_path / name
    P.save(path, Inputs(**inputs), {"layers": {"dimensions": True}, "tab": "offdesign"})
    return path


def _design(qtbot, window, **changes):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(**changes)


def test_file_menu_has_the_spec_actions(window):
    texts = [a.text().replace("&", "") for a in window.project.file_menu.actions()]
    assert texts[:2] == ["New", "Open…"]
    for name in ("Open Recent", "Save", "Save As…", "Export", "Quit"):
        assert name in texts
    p = window.project
    assert p.save_as_action.shortcut().toString() == "Ctrl+Shift+S"
    assert p.quit_action.shortcut().toString() == "Ctrl+Q"


def test_dirty_flag_and_title(qtbot, window, tmp_path):
    p = window.project
    assert not p.dirty and window.windowTitle() == "Busemann — Untitled"
    _design(qtbot, window, mach=3.2)
    assert p.dirty and window.windowTitle().endswith(" •")
    target = tmp_path / "saved.busemann"
    p._write(target)
    assert not p.dirty and window.windowTitle() == "Busemann — saved.busemann"
    window.layer_actions["grid"].setChecked(True)          # view toggles count as changes
    assert p.dirty
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["inputs"]["mach"] == 3.2


def test_open_applies_inputs_and_view_and_is_clean(qtbot, window, tmp_path):
    path = _save_file(tmp_path, mach=3.4, n_ramps=3, cowl_wedge_deg=2.0, off_design_mach=3.0)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        assert window.project.open_path(path)
    assert window.state.inputs == Inputs(mach=3.4, n_ramps=3, cowl_wedge_deg=2.0,
                                         off_design_mach=3.0)
    assert window.state.design.inputs.n_ramps == 3
    assert window.tabs.currentWidget() is window.offdesign_tab
    assert window.layer_actions["dimensions"].isChecked()
    assert window.design_panel.wedge.value() == 2.0             # panels follow
    assert not window.project.dirty and "case.busemann" in window.windowTitle()


def test_prompt_on_new_cancel_keeps_state(qtbot, window):
    p = window.project
    _design(qtbot, window, mach=3.3)
    asked = []
    p.ask_save = lambda: asked.append(1) or "cancel"
    assert p.new() is False
    assert asked and window.state.inputs.mach == 3.3 and p.dirty
    p.ask_save = lambda: "discard"
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        assert p.new() is True
    assert window.state.inputs == Inputs() and not p.dirty


def test_quit_with_unsaved_changes_can_be_cancelled(qtbot, window):
    _design(qtbot, window, mach=3.3)
    window.project.ask_save = lambda: "cancel"
    window.close()
    assert window.isVisible()


def test_recent_list_order_and_cap(qtbot, window, tmp_path):
    p = window.project
    for k in range(10):
        p._add_recent(_save_file(tmp_path, f"p{k}.busemann", mach=2.0 + 0.1 * k))
    recent = p.recent()
    assert len(recent) == 8
    assert recent[0].endswith("p9.busemann") and recent[-1].endswith("p2.busemann")
    labels = [a.text() for a in p.recent_menu.actions() if a.text()]
    assert labels[0] == "&1 p9.busemann" and labels[-1] == "Clear recent"
    p.clear_recent()
    assert p.recent() == []


def test_corrupt_file_shows_clear_error(window, tmp_path):
    bad = tmp_path / "bad.busemann"
    bad.write_text('{"format": "busemann-project", "schema": 1, "inputs": {', encoding="utf-8")
    shown = []
    window.project.show_error = shown.append
    before = window.state.inputs
    assert window.project.open_path(bad) is False
    assert shown and "not valid JSON" in shown[0]
    assert window.state.inputs == before


def test_drop_a_project_file_opens_it(qtbot, window, tmp_path):
    path = _save_file(tmp_path, mach=2.6)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime,
                       Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.dropEvent(event)
    assert window.state.inputs.mach == 2.6
    other = QMimeData()
    other.setUrls([QUrl.fromLocalFile(str(tmp_path / "x.txt"))])
    assert window._dropped_project(other) is None


def test_command_line_path_opens_project(qtbot, monkeypatch, tmp_path):
    import busemann.app as app_module

    path = _save_file(tmp_path, mach=2.8)
    windows = []
    real = app_module.MainWindow

    def capture(*a, **k):
        w = real(*a, **k)
        windows.append(w)
        return w

    monkeypatch.setattr(app_module, "MainWindow", capture)
    monkeypatch.setattr(app_module.QApplication, "exec", lambda self: 0)
    assert app_module.main([str(path)]) == 0
    w = windows[0]
    qtbot.addWidget(w)
    qtbot.waitUntil(lambda: w.state.inputs.mach == 2.8, timeout=3000)
    assert w.project.path.name == "case.busemann"
    w.project.ask_save = lambda: "discard"
    w.close()
    w.state.shutdown()
