"""File > Export (M6): each action writes its file with metadata; folders are remembered."""
import json

import ezdxf
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

pytestmark = pytest.mark.gui


def _answer(controller, folder, names):
    """Replace the save dialog: record the proposed name, write into `folder`."""
    def ask(title, name, file_filter):
        names.append(name)
        return str(folder / name)
    controller.ask_path = ask


def test_every_export_action_writes_a_file(qtbot, window, tmp_path):
    exports = window.exports
    names = []
    _answer(exports, tmp_path, names)
    exports._update_enabled()
    for key, action in exports.actions.items():
        assert action.isEnabled(), key
        action.trigger()
    files = sorted(p.name for p in tmp_path.iterdir() if p.suffix != ".ini")
    assert files == sorted(names + ["verification_notes.md"])   # beside the DXFs (M8)
    assert names[:3] == ["busemann_M3.00_2ramp_geometry.dxf",
                         "busemann_M3.00_2ramp_cfd_domain.dxf",
                         "busemann_M3.00_2ramp_cfd_offdesign_v2.dxf"]
    assert "busemann_M3.00_2ramp_design.png" in names
    for name in names[:3]:
        props = dict(ezdxf.readfile(tmp_path / name).header.custom_vars)
        assert props["app"] == "Busemann" and "inputs" in props
    data = json.loads((tmp_path / "busemann_M3.00_2ramp_results.json").read_text("utf-8"))
    assert data["design"]["recovery_total"] == window.state.design.recovery_total
    assert data["metadata"]["inputs"]["mach"] == 3.0
    csv_text = (tmp_path / "busemann_M3.00_2ramp_results.csv").read_text("utf-8-sig")
    assert "flow angle [°]" in csv_text and "# stations (design point)" in csv_text


def test_offdesign_canvas_export_uses_offdesign_picture(qtbot, window, tmp_path):
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.5)
    names = []
    _answer(window.exports, tmp_path, names)
    path = window.exports.export_canvas()
    assert path.name == "busemann_M3.00_2ramp_offdesign_M2.50.png" and path.exists()
    window.exports.export_csv()
    text = (tmp_path / "busemann_M3.00_2ramp_results.csv").read_text("utf-8-sig")
    assert "# stations (off-design at M∞ 2.50)" in text


def test_last_folder_is_remembered(qtbot, window, tmp_path):
    exports = window.exports
    folder = tmp_path / "exports"
    folder.mkdir()
    _answer(exports, folder, [])
    exports.export_json()
    assert exports.settings.value("export/last_dir") == str(folder)
    seen = []
    del exports.ask_path                                           # back to the real dialog
    from PySide6.QtWidgets import QFileDialog
    original = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(
        lambda parent, title, start, flt: (seen.append(start) or "", ""))
    try:
        exports.export_json()
    finally:
        QFileDialog.getSaveFileName = original
    assert seen and seen[0].startswith(str(folder))
