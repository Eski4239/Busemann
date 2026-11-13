"""File > Export (M6, M8.4): each action writes its file with metadata; folders are
remembered. No IGES, point CSV or figure exports since M8.4."""
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
    assert names == ["busemann_M3.00_2ramp_geometry.dxf",
                     "busemann_M3.00_2ramp_geometry.geo",
                     "busemann_M3.00_2ramp_cfd_domain.dxf",
                     "busemann_M3.00_2ramp_cfd_offdesign_v2.dxf",
                     "busemann_M3.00_2ramp_results.json",
                     "busemann_M3.00_2ramp_results.csv"]
    assert not any(n.endswith((".igs", ".png", ".svg", ".pdf")) for n in names)
    geometry = dict(ezdxf.readfile(tmp_path / names[0]).header.custom_vars)
    assert geometry["app"] == "Busemann" and geometry["BUSEMANN_MACH"] == "3.0"  # reopens
    for name in names[2:4]:
        props = dict(ezdxf.readfile(tmp_path / name).header.custom_vars)
        assert props["app"] == "Busemann" and "inputs" in props
    data = json.loads((tmp_path / "busemann_M3.00_2ramp_results.json").read_text("utf-8"))
    assert data["design"]["recovery_total"] == window.state.design.recovery_total
    assert data["metadata"]["inputs"]["mach"] == 3.0
    csv_text = (tmp_path / "busemann_M3.00_2ramp_results.csv").read_text("utf-8-sig")
    assert "flow angle [°]" in csv_text and "# stations (design point)" in csv_text


def test_offdesign_results_csv_uses_the_offdesign_point(qtbot, window, tmp_path):
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.5)
    names = []
    _answer(window.exports, tmp_path, names)
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


# --- M12 PART 2.3: a file that cannot be written is reported, never raised ------------------
def _readonly(path):
    import os
    import stat

    path.write_text("old", encoding="utf-8")
    os.chmod(path, stat.S_IREAD)


def _restore(path):
    import os
    import stat

    if path.exists():
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


class _Locked:
    """Hold a file open with no sharing (another program has it open): Windows only."""

    def __init__(self, path):
        import ctypes
        from ctypes import wintypes

        path.write_text("old", encoding="utf-8")
        create = ctypes.windll.kernel32.CreateFileW
        create.restype = wintypes.HANDLE
        self.close = ctypes.windll.kernel32.CloseHandle
        GENERIC_READ, OPEN_EXISTING = 0x80000000, 3
        self.handle = create(str(path), GENERIC_READ, 0, None, OPEN_EXISTING, 0, None)
        assert self.handle not in (None, wintypes.HANDLE(-1).value)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close(self.handle)


def _fail_every_export(window, tmp_path, block):
    """Every export action against a blocked target: one clear message each, None, no raise."""
    exports = window.exports
    exports._update_enabled()
    shown = []
    exports.show_error = shown.append
    for key, slot in (("geometry", exports.export_geometry), ("gmsh", exports.export_gmsh),
                      ("cfd", exports.export_cfd), ("cfd_off", exports.export_cfd_offdesign),
                      ("json", exports.export_json), ("csv", exports.export_csv)):
        target = tmp_path / f"blocked_{key}.out"
        exports.ask_path = lambda title, name, flt, t=target: str(t)
        with block(target):
            assert slot() is None, key
        assert shown, key
        text = shown.pop()
        assert text.startswith(f"Could not write {target.name}: "), text
        assert text.endswith(". Is it open in another program?"), text
        assert window.statusBar().currentMessage() == text
    return shown


def test_export_to_read_only_files_reports_each_failure(qtbot, window, tmp_path):
    from contextlib import contextmanager

    @contextmanager
    def readonly(path):
        _readonly(path)
        try:
            yield
        finally:
            _restore(path)
    _fail_every_export(window, tmp_path, readonly)


@pytest.mark.skipif(__import__("sys").platform != "win32", reason="Windows file locking")
def test_export_to_a_locked_file_reports_each_failure(qtbot, window, tmp_path):
    _fail_every_export(window, tmp_path, _Locked)


def test_export_error_text_names_the_file_and_reason():
    from busemann.views.export_controller import error_text

    assert error_text("C:/x/a.dxf", PermissionError(13, "Permission denied")) == \
        "Could not write a.dxf: Permission denied. Is it open in another program?"
    assert error_text("b.csv", ValueError("bad value.")) == \
        "Could not write b.csv: bad value. Is it open in another program?"
    assert error_text("c.dxf", ezdxf.DXFError()) == \
        "Could not write c.dxf: DXFError. Is it open in another program?"


def test_save_to_a_read_only_file_reports(qtbot, window, tmp_path):
    target = tmp_path / "design.dxf"
    _readonly(target)
    shown = []
    window.project.show_save_error = shown.append
    try:
        assert window.project._write(target) is False
    finally:
        _restore(target)
    assert shown and shown[0].startswith("Could not write design.dxf: ")
