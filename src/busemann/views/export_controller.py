"""File > Export menu (spec 4.7, M8.4): geometry DXF (also the save format), CFD domain
DXFs, Gmsh .geo and the results (JSON, CSV).

Every export carries the metadata header (export.metadata). Save dialogs remember the last
folder and propose names like busemann_M3.00_2ramp_geometry.dxf.

M12: every write goes through write_guarded(): a file that cannot be written (read-only,
locked by another program, bad folder, ezdxf error) shows one clear message and returns None;
nothing raises and nothing fails silently. The isentropic window's exports use it too.
"""
from pathlib import Path

import ezdxf
from PySide6.QtCore import QObject
from PySide6.QtWidgets import QFileDialog, QMessageBox

from inletdesign import api
from inletdesign.cfd_domain import export_cfd_domain_dxf, export_offdesign_domain_dxf

from ..export import results as R
from ..export.metadata import default_name, metadata
from ..settings import app_settings

EXPORT_ERRORS = (OSError, ValueError, ezdxf.DXFError)


def error_text(path, exc):
    """'Could not write <file>: <reason>. Is it open in another program?'"""
    reason = (exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)) \
        or type(exc).__name__
    return (f"Could not write {Path(path).name}: {reason.rstrip('.')}. "
            "Is it open in another program?")


def show_export_error(parent, text):
    """Modal warning in the token style (QMessageBox picks up the app stylesheet)."""
    box = QMessageBox(QMessageBox.Icon.Warning, "Export failed", text,
                      QMessageBox.StandardButton.Ok, parent)
    box.setObjectName("exportError")
    box.exec()


def write_guarded(path, write, report):
    """Run write(); on an export error call report(error_text) and return None, else path."""
    try:
        write()
    except EXPORT_ERRORS as exc:
        report(error_text(path, exc))
        return None
    return path


class ExportController(QObject):
    def __init__(self, window, menu):
        super().__init__(window)
        self.window = window
        self.state = window.state
        self.settings = app_settings()
        self.actions = {}
        add = self._add
        add(menu, "geometry", "Geometry DXF…", self.export_geometry)
        add(menu, "gmsh", "Gmsh geometry (.geo)…", self.export_gmsh)
        add(menu, "cfd", "CFD domain DXF (design)…", self.export_cfd)
        add(menu, "cfd_off", "CFD domain DXF (off-design v2)…", self.export_cfd_offdesign)
        menu.addSeparator()
        add(menu, "json", "Results JSON…", self.export_json)
        add(menu, "csv", "Results CSV…", self.export_csv)
        menu.aboutToShow.connect(self._update_enabled)

    def _add(self, menu, key, text, slot):
        action = menu.addAction(text)
        action.triggered.connect(lambda *_: slot())
        self.actions[key] = action

    def _update_enabled(self):
        ok = self.state.design is not None
        for action in self.actions.values():
            action.setEnabled(ok)
        has_ramps = ok and self.state.design.inputs.n_ramps > 0
        self.actions["cfd_off"].setEnabled(has_ramps)

    # --- dialogs ---------------------------------------------------------------------------
    def ask_path(self, title, name, file_filter):
        """Save dialog starting in the last export folder (replaced in tests)."""
        start = str(Path(self.settings.value("export/last_dir", str(Path.home()))) / name)
        path, _ = QFileDialog.getSaveFileName(self.window, title, start, file_filter)
        return path or None

    def _path(self, title, name, file_filter):
        path = self.ask_path(title, name, file_filter)
        if path:
            self.settings.setValue("export/last_dir", str(Path(path).parent))
        return Path(path) if path else None

    def show_error(self, text):
        """Shows an export error (replaced in tests, like ask_path)."""
        show_export_error(self.window, text)

    def _report(self, text):
        self.window.statusBar().showMessage(text, 8000)
        self.show_error(text)

    def _write(self, path, write):
        """Run write() for `path`; the status line on success, the error message otherwise."""
        if write_guarded(path, write, self._report) is None:
            return None
        self.window.statusBar().showMessage(f"Exported {path.name}", 5000)
        return path

    def _meta(self, what):
        return metadata(self.state.inputs, what)

    def _notes(self, export_path, meta):
        """verification_notes.md beside a geometry / CFD export (addendum E)."""
        from ..export.notes import write_verification_notes

        return write_verification_notes(export_path, meta, self.state.verification_items())

    def _is_off(self):
        return self.state.active_view == "offdesign" and self.state.off_design is not None

    # --- exports -------------------------------------------------------------------------
    def export_geometry(self):
        path = self._path("Export geometry DXF", default_name(self.state.inputs, "geometry",
                                                               "dxf"), "DXF drawing (*.dxf)")
        if not path:
            return None
        from .. import project as P

        meta = self._meta("geometry DXF")
        meta.pop("inputs", None)                     # the inputs go in as BUSEMANN_* keys

        def write():
            P.save(path, self.state.inputs, self.window.project.view(),
                   design=self.state.design, metadata=meta)     # reopens as the design
            self._notes(path, meta)
        return self._write(path, write)

    def _cad(self, title, kind, ext, file_filter, writer, what):
        path = self._path(title, default_name(self.state.inputs, kind, ext), file_filter)
        if not path:
            return None
        meta = self._meta(what)

        def write():
            writer(api.inlet_geometry(self.state.design), path, meta)
            self._notes(path, meta)
        return self._write(path, write)

    def export_gmsh(self):
        from inletdesign.export_cad import export_gmsh_geo

        return self._cad("Export Gmsh geometry", "geometry", "geo", "Gmsh geometry (*.geo)",
                         export_gmsh_geo, "Gmsh .geo (m)")

    def export_cfd(self):
        path = self._path("Export CFD domain DXF", default_name(self.state.inputs,
                                                                 "cfd_domain", "dxf"),
                          "DXF drawing (*.dxf)")
        if not path:
            return None
        meta = self._meta("CFD domain DXF (design point)")

        def write():
            export_cfd_domain_dxf(api.inlet_geometry(self.state.design), path,
                                  metadata=meta)
            self._notes(path, meta)
        return self._write(path, write)

    def export_cfd_offdesign(self):
        path = self._path("Export off-design CFD domain DXF",
                          default_name(self.state.inputs, "cfd_offdesign_v2", "dxf"),
                          "DXF drawing (*.dxf)")
        if not path:
            return None
        meta = self._meta("CFD domain DXF (off-design v2, normal OUTLET_EXT)")

        def write():
            export_offdesign_domain_dxf(
                api.inlet_geometry(self.state.design), path, ext_outlet="normal",
                metadata=meta)
            self._notes(path, meta)
        return self._write(path, write)

    def export_json(self):
        path = self._path("Export results JSON",
                          default_name(self.state.inputs, "results", "json"), "JSON (*.json)")
        if not path:
            return None
        s = self.state
        return self._write(path, lambda: R.write_json(
            path, self._meta("results JSON"), s.design, s.freestream, s.off_design, s.sweep))

    def export_csv(self):
        path = self._path("Export results CSV",
                          default_name(self.state.inputs, "results", "csv"), "CSV (*.csv)")
        if not path:
            return None
        s = self.state
        off = self._is_off()
        regions = (s.off_design if off else s.design).regions
        view = f"off-design at M∞ {s.off_design.M_inf:.2f}" if off else "design point"
        return self._write(path, lambda: R.write_csv(
            path, self._meta("results CSV"), regions, s.sweep, view))
