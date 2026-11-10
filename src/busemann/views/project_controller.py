"""File menu and project lifecycle (spec 4.7): New, Open, Save, Save As, Recent, Quit,
dirty tracking ("•" in the title) and the save prompt. Projects are DXF drawings (M8.2): a
Busemann DXF reopens exactly; any other DXF is imported from its ramp and cowl lines as an
untitled custom-angle design with the "flight conditions unknown" banner."""
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QFileDialog, QMessageBox

from .. import project as P
from ..inputs import Inputs
from ..settings import app_settings

MAX_RECENT = 8
FILTER = P.FILTER


class ProjectController(QObject):
    dirty_changed = Signal(bool)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.state = window.state
        self.path = None
        self.dirty = False
        self._loading = False
        self.settings = app_settings()

        menu = window.menuBar().addMenu("&File")
        self.file_menu = menu
        self.new_action = self._action("&New", QKeySequence.StandardKey.New, self.new)
        self.open_action = self._action("&Open…", QKeySequence.StandardKey.Open,
                                        lambda: self.open())
        self.save_action = self._action("&Save", QKeySequence.StandardKey.Save,
                                        lambda: self.save())
        self.save_as_action = self._action("Save &As…", QKeySequence("Ctrl+Shift+S"),
                                           lambda: self.save_as())
        for a in (self.new_action, self.open_action):
            menu.addAction(a)
        self.recent_menu = menu.addMenu("Open &Recent")
        menu.addSeparator()
        menu.addAction(self.save_action)
        menu.addAction(self.save_as_action)
        menu.addSeparator()
        self.export_menu = menu.addMenu("&Export")
        menu.addSeparator()
        self.quit_action = self._action("&Quit", QKeySequence("Ctrl+Q"), window.close)
        menu.addAction(self.quit_action)
        self._rebuild_recent()

        self.state.inputs_changed.connect(lambda *_: self.mark_dirty())
        window.tabs.currentChanged.connect(lambda *_: self.mark_dirty())
        for action in window.layer_actions.values():
            action.toggled.connect(lambda *_: self.mark_dirty())
        self.update_title()

    def _action(self, text, shortcut, slot):
        action = QAction(text, self.window)
        action.setShortcut(shortcut)
        action.triggered.connect(lambda *_: slot())
        return action

    # --- dirty flag and title -------------------------------------------------------------
    def mark_dirty(self):
        if not self._loading:
            self._set_dirty(True)

    def _set_dirty(self, dirty):
        if dirty != self.dirty:
            self.dirty = dirty
            self.dirty_changed.emit(dirty)
        self.update_title()

    def name(self):
        if self.path:
            return self.path.name
        origin = getattr(self, "origin", None)
        return f"Untitled (from {origin})" if origin else "Untitled"

    def update_title(self):
        self.window.setWindowTitle(f"Busemann — {self.name()}" + (" •" if self.dirty else ""))

    # --- view state ----------------------------------------------------------------------
    def view(self):
        w = self.window
        return {"layers": {k: a.isChecked() for k, a in w.layer_actions.items()},
                "tab": "offdesign" if w.tabs.currentWidget() is w.offdesign_tab else "design"}

    def _apply(self, inputs, view):
        w = self.window
        self._loading = True
        try:
            for key, on in view["layers"].items():
                if key in w.layer_actions:
                    w.layer_actions[key].setChecked(on)
            w.tabs.setCurrentWidget(w.offdesign_tab if view["tab"] == "offdesign" else w.canvas)
            self.state.load_inputs(inputs)
        finally:
            self._loading = False

    def _clear_history(self):
        undo = getattr(self.window, "undo", None)
        if undo is not None:
            undo.clear()

    def start_from(self, inputs, label=None):
        """Start a new untitled design from given inputs (welcome window: preset, example)."""
        self._apply(inputs, dict(P.DEFAULT_VIEW, layers=dict(P.DEFAULT_VIEW["layers"])))
        self.window.show_banner(None)
        self.path = None
        self.origin = label
        self._set_dirty(False)
        self._clear_history()

    def open_example(self, path):
        """Load a bundled example as an untitled copy (Save never writes into the app)."""
        try:
            inputs, view, _ = P.load(path, base=self.state.inputs)
        except P.ProjectError as exc:
            self.show_error(str(exc))
            return False
        self._apply(inputs, view)
        self.window.show_banner(None)
        self.path = None
        self.origin = f"example {Path(path).stem}"
        self._set_dirty(False)
        self._clear_history()
        return True

    # --- prompt --------------------------------------------------------------------------
    def ask_save(self):
        """Save / Discard / Cancel for unsaved changes (replaced in tests)."""
        box = QMessageBox(QMessageBox.Icon.Question, "Unsaved changes",
                          f"Save changes to {self.name()}?",
                          QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                          | QMessageBox.StandardButton.Cancel, self.window)
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        answer = box.exec()
        return {QMessageBox.StandardButton.Save: "save",
                QMessageBox.StandardButton.Discard: "discard"}.get(
            QMessageBox.StandardButton(answer), "cancel")

    def maybe_save(self):
        """True when it is fine to drop the current project (saved, discarded or clean)."""
        if not self.dirty:
            return True
        answer = self.ask_save()
        if answer == "save":
            return self.save()
        return answer == "discard"

    # --- actions -------------------------------------------------------------------------
    def new(self):
        if not self.maybe_save():
            return False
        self._apply(Inputs(), dict(P.DEFAULT_VIEW, layers=dict(P.DEFAULT_VIEW["layers"])))
        self.window.show_banner(None)
        self.path = None
        self.origin = None
        self._set_dirty(False)
        self._clear_history()
        return True

    def open(self, path=None):
        if not self.maybe_save():
            return False
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self.window, "Open project",
                                                  self._last_dir(), FILTER)
            if not path:
                return False
        return self.open_path(path, ask=False)

    def _open_as_isentropic(self, path):
        """If `path` is an isentropic-ramp DXF (M11), load it into the Tools > Isentropic
        ramp window and return True; otherwise return False without side effects."""
        try:
            doc = P._read_doc(path)
        except P.ProjectError:
            return False
        header = P.custom_header(doc)
        from inletdesign.export import ISENTROPIC_FORMAT

        if header.get("BUSEMANN_FORMAT") != ISENTROPIC_FORMAT:
            return False
        win = self.window.show_isentropic_ramp()
        win.load_from_header(header)
        self._add_recent(path)
        self.settings.setValue("project/last_dir", str(path.parent))
        return True

    def open_path(self, path, ask=True):
        """Open a project file (command line, drop, recent). Errors show a dialog.

        An isentropic-ramp DXF (BUSEMANN_FORMAT = "busemann-isentropic-dxf", M11) is routed to
        the Tools > Isentropic ramp window instead of being imported as a multi-ramp design."""
        if ask and not self.maybe_save():
            return False
        path = Path(path)
        if self._open_as_isentropic(path):
            return True
        try:
            loaded = P.load(path, base=self.state.inputs)
        except P.ProjectError as exc:
            self.show_error(str(exc))
            return False
        inputs, view, warnings = loaded
        self._apply(inputs, view)
        self._clear_history()
        self._add_recent(path)
        self.settings.setValue("project/last_dir", str(path.parent))
        if loaded.imported:                # geometry only: an untitled design, never saved over
            self.path = None
            self.origin = f"import {path.name}"
            self._set_dirty(True)
            self.window.show_banner(P.IMPORT_BANNER)
            extra = [w for w in warnings if w != P.IMPORT_BANNER]
            if extra:
                self.show_warnings(extra)
            return True
        self.window.show_banner(None)
        self.path = path
        self.origin = None
        self._set_dirty(False)
        if warnings:
            self.window.statusBar().showMessage(f"Opened {path.name} with {len(warnings)} "
                                                "warning(s)", 8000)
            self.show_warnings(warnings)
        return True

    def save(self):
        if self.path is None:
            return self.save_as()
        return self._write(self.path)

    def save_as(self):
        start = str(Path(self._last_dir()) / (self.path.name if self.path else
                                               "untitled.dxf"))
        path, _ = QFileDialog.getSaveFileName(self.window, "Save project", start, FILTER)
        if not path:
            return False
        path = Path(path)
        if path.suffix.lower() != P.SUFFIX:
            path = path.with_suffix(P.SUFFIX)
        return self._write(path)

    def _write(self, path):
        try:
            P.save(path, self.state.inputs, self.view(), design=self.state.design,
                   metadata=self._metadata())
        except OSError as exc:
            self.show_error(f"Cannot save {path.name}: {exc.strerror or exc}")
            return False
        self.path = Path(path)
        self.origin = None
        self._set_dirty(False)
        self._add_recent(self.path)
        self.settings.setValue("project/last_dir", str(self.path.parent))
        self.window.statusBar().showMessage(f"Saved {self.path.name}", 4000)
        return True

    def _metadata(self):
        from ..export.metadata import metadata

        meta = metadata(self.state.inputs, "Busemann design (DXF)")
        meta.pop("inputs", None)                     # the inputs are the BUSEMANN_* keys
        return meta

    # --- dialogs (replaced in tests) -------------------------------------------------------
    def show_error(self, text):
        QMessageBox.critical(self.window, "Cannot open project", text)

    def show_warnings(self, warnings):
        QMessageBox.information(self.window, "Project opened with warnings",
                                "\n".join(f"• {w}" for w in warnings))

    # --- recent ----------------------------------------------------------------------------
    def recent(self):
        value = self.settings.value("project/recent", [])
        if isinstance(value, str):
            value = [value]
        return [str(v) for v in (value or [])]

    def _add_recent(self, path):
        path = str(Path(path).resolve())
        items = [p for p in self.recent() if p != path]
        self.settings.setValue("project/recent", [path] + items[:MAX_RECENT - 1])
        self._rebuild_recent()

    def clear_recent(self):
        self.settings.setValue("project/recent", [])
        self._rebuild_recent()

    def _rebuild_recent(self):
        self.recent_menu.clear()
        items = self.recent()
        for i, path in enumerate(items, start=1):
            action = self.recent_menu.addAction(f"&{i} {Path(path).name}")
            action.setToolTip(path)
            action.setData(path)
            action.triggered.connect(lambda *_, p=path: self.open_path(p))
        if items:
            self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction("Clear recent")
        clear.setEnabled(bool(items))
        clear.triggered.connect(self.clear_recent)

    def _last_dir(self):
        return str(self.settings.value("project/last_dir", str(Path.home())))

    # --- startup / drop -------------------------------------------------------------------
    def open_later(self, path):
        """Open a path once the event loop runs (command line)."""
        QTimer.singleShot(0, lambda: self.open_path(path, ask=False))
