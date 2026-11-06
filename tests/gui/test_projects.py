"""Projects in the app (M6): File menu, dirty flag and title, prompt, recent list, drop and
command-line open."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402

from busemann import project as P  # noqa: E402
from busemann.inputs import Inputs  # noqa: E402

pytestmark = pytest.mark.gui


def _save_file(tmp_path, name="case.dxf", **inputs):
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
    target = tmp_path / "saved.dxf"
    p._write(target)
    assert not p.dirty and window.windowTitle() == "Busemann — saved.dxf"
    window.layer_actions["grid"].setChecked(True)          # view toggles count as changes
    assert p.dirty
    assert P.load(target)[0].mach == 3.2


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
    assert not window.project.dirty and "case.dxf" in window.windowTitle()


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
        p._add_recent(_save_file(tmp_path, f"p{k}.dxf", mach=2.0 + 0.1 * k))
    recent = p.recent()
    assert len(recent) == 8
    assert recent[0].endswith("p9.dxf") and recent[-1].endswith("p2.dxf")
    labels = [a.text() for a in p.recent_menu.actions() if a.text()]
    assert labels[0] == "&1 p9.dxf" and labels[-1] == "Clear recent"
    p.clear_recent()
    assert p.recent() == []


def test_corrupt_file_shows_clear_error(window, tmp_path):
    bad = tmp_path / "bad.dxf"
    bad.write_text("not a drawing", encoding="utf-8")
    shown = []
    window.project.show_error = shown.append
    before = window.state.inputs
    assert window.project.open_path(bad) is False
    assert shown and "bad.dxf" in shown[0]
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
    assert w.project.path.name == "case.dxf"
    w.project.ask_save = lambda: "discard"
    w.close()
    w.state.shutdown()


# --- M8.2: DXF import, examples, CAD exports ------------------------------------------------

def test_foreign_dxf_opens_as_untitled_custom_design_with_banner(qtbot, window, tmp_path):
    from inletdesign import api
    from inletdesign.export import export_dxf

    d = api.design(3.0, 3, ramp_angles=[6.0, 7.0, 8.0])
    path = export_dxf(api.inlet_geometry(d), tmp_path / "from_cad.dxf")
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        assert window.project.open_path(path)
    i = window.state.inputs
    assert i.method == "custom" and i.custom_angles == pytest.approx((6.0, 7.0, 8.0), abs=1e-9)
    assert window.banner.isVisibleTo(window)
    assert window.banner_label.text() == P.IMPORT_BANNER
    assert window.project.path is None and "import from_cad.dxf" in window.windowTitle()
    assert str(path.resolve()) in window.project.recent()
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.project.new()
    assert not window.banner.isVisibleTo(window)


def test_unrecognised_dxf_names_what_is_missing(window, tmp_path):
    import ezdxf

    doc = ezdxf.new()
    doc.modelspace().add_circle((0, 0), 5)
    path = tmp_path / "circle.dxf"
    doc.saveas(path)
    shown = []
    window.project.show_error = shown.append
    assert window.project.open_path(path) is False
    assert shown and "no ramp line found" in shown[0]


def test_examples_open_as_untitled_copies(qtbot, window):
    from busemann.paths import resource_path

    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        assert window.project.open_example(resource_path("examples", "m3_cowl_constrained.dxf"))
    assert window.state.inputs.n_ramps == 3 and window.state.inputs.max_cowl_enabled
    assert window.project.path is None and not window.project.dirty


@pytest.mark.parametrize("action, suffix", [("export_gmsh", ".geo"), ("export_geometry", ".dxf")])
def test_cad_exports_write_notes_beside_them(window, tmp_path, action, suffix):
    window.exports.ask_path = lambda title, name, flt: str(tmp_path / name)
    path = getattr(window.exports, action)()
    assert path.suffix == suffix and path.exists()
    assert path.with_name("verification_notes.md").exists()
    if suffix == ".dxf":                                  # the geometry DXF reopens exactly
        assert P.load(path)[0] == window.state.inputs
