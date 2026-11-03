"""QApplication setup and the main window (spec 5 layout: left 300 | canvas | right 320)."""
import sys

from PySide6.QtCore import QEasingCurve, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QHBoxLayout, QLabel, QMainWindow, QProgressBar, QScrollArea, QStackedWidget,
    QTabWidget,
    QToolBar, QToolButton, QVBoxLayout, QWidget,
)

from . import __version__
from .theme import qt as theme
from .canvas import InletCanvas
from .state import AppState
from .theme import tokens
from .views import DesignPanel, FlightPanel, ResultsPanel
from .explain import warm as _warm
from .tooltips import tip
from .undo import InputUndo
from .views.explain_drawer import DRAWER_W, SLIDE_MS, ExplainDrawer
from .views.offdesign_tab import OffDesignTab
from .views.export_controller import ExportController
from .views.project_controller import ProjectController
from .widgets import divider


def _placeholder(title, text, tip_key):
    """A tab that is not built yet: a centred title and one muted line, nothing else."""
    page = QWidget()
    page.setObjectName("placeholderTab")
    v = QVBoxLayout(page)
    v.addStretch(1)
    head = QLabel(title)
    head.setObjectName("placeholderTitle")
    head.setAlignment(Qt.AlignmentFlag.AlignCenter)
    line = QLabel(text)
    line.setObjectName("muted")
    line.setAlignment(Qt.AlignmentFlag.AlignCenter)
    for w in (head, line):
        w.setToolTip(tip(tip_key))
    v.addWidget(head)
    v.addWidget(line)
    v.addStretch(1)
    return page


def _side_panel(object_name, width, *widgets):
    body = QWidget()
    body.setObjectName("panelBody")
    layout = QVBoxLayout(body)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    for i, w in enumerate(widgets):
        if i:
            layout.addWidget(divider())
        layout.addWidget(w)
    layout.addStretch(1)
    scroll = QScrollArea()
    scroll.setObjectName(object_name)
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setWidget(body)
    scroll.setFixedWidth(width)
    return scroll


WARM_DELAY_MS = 1500        # idle time after a design before warming the equation cache


class MainWindow(QMainWindow):
    def __init__(self, state=None, parent=None):
        super().__init__(parent)
        self.warm_futures = []
        self.state = state or AppState(parent=self)
        self.setWindowTitle("Busemann")
        self.setWindowIcon(theme.icon("busemann", "accent", 64))
        self.setMinimumSize(*tokens.MIN_WINDOW)

        self.flight_panel = FlightPanel(self.state)
        self.design_panel = DesignPanel(self.state)
        self.results_panel = ResultsPanel(self.state)
        self.left_panel = _side_panel("leftPanel", tokens.LEFT_PANEL_WIDTH,
                                      self.flight_panel, self.design_panel)
        self.right_panel = _side_panel("rightPanel", tokens.RIGHT_PANEL_WIDTH, self.results_panel)
        # Right column: results, or the Explain drawer (column widens, centre shrinks).
        self.right_panel.setMinimumWidth(0)
        self.right_panel.setMaximumWidth(16777215)
        self.right_column = QStackedWidget()
        self.right_column.setObjectName("rightColumn")
        self.right_column.setFixedWidth(tokens.RIGHT_PANEL_WIDTH)
        self.right_column.addWidget(self.right_panel)
        self.explain_drawer = ExplainDrawer(self.state, self.right_column)
        self.right_column.addWidget(self.explain_drawer)
        self._column_anim = QVariantAnimation(self)
        self._column_anim.setDuration(SLIDE_MS)
        self._column_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._column_anim.valueChanged.connect(
            lambda w: self.right_column.setFixedWidth(round(w)))
        self._column_anim.finished.connect(self._on_column_anim_done)

        self.canvas = InletCanvas(self.state)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self.canvas, "Design")
        self.offdesign_tab = OffDesignTab(self.state)
        self.tabs.addTab(self.offdesign_tab, "Off-design")
        self.analytics_tab = _placeholder(
            "Analytics", "Trade studies, drag and buzz estimates — coming in M9.",
            "placeholder.analytics")
        self.compare_tab = _placeholder(
            "Compare", "Side-by-side design comparison — coming in M10.", "placeholder.compare")
        self.tabs.addTab(self.analytics_tab, "Analytics")
        self.tabs.addTab(self.compare_tab, "Compare")
        self.tabs.currentChanged.connect(self._on_tab)

        centre = QWidget()
        centre.setObjectName("canvasHost")
        row = QHBoxLayout(centre)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self.left_panel)
        row.addWidget(self.tabs, 1)
        row.addWidget(self.right_column)
        self.setCentralWidget(centre)

        self._build_toolbar()
        self._build_status_bar()
        self.undo = InputUndo(self.state, self)
        self.project = ProjectController(self)
        self.exports = ExportController(self, self.project.export_menu)
        self._build_edit_menu()
        help_menu = self.menuBar().addMenu("&Help")
        self.help_menu = help_menu
        self._build_shortcuts(help_menu)
        self.about_action = help_menu.addAction("&About Busemann…")
        self.about_action.triggered.connect(self.show_about)
        self.setAcceptDrops(True)

        # Transitions animate on discrete changes, not while the Mach slider is dragged.
        slider = self.flight_panel.mach.slider
        slider.sliderPressed.connect(lambda: self.canvas.set_animations_enabled(False))
        slider.sliderReleased.connect(lambda: self.canvas.set_animations_enabled(True))
        for s in (slider, self.offdesign_tab.slider.slider):
            s.sliderPressed.connect(lambda: self.state.set_dragging(True))
            s.sliderReleased.connect(lambda: self.state.set_dragging(False))
        # a whole Mach-slider drag is one undo step
        slider.sliderPressed.connect(lambda: self.undo.begin_gesture("mach"))
        slider.sliderReleased.connect(self.undo.end_gesture)
        for canvas in self.canvases():
            canvas.selection_changed.connect(
                lambda *sel, c=canvas: self._on_selection(c, *sel))
            canvas.picture_changed.connect(lambda c=canvas: self._on_picture(c))
        self.results_panel.station_table.row_clicked.connect(
            lambda row: self.current_canvas().select("region", row))

        # Fill the equation cache in a separate render process once a design has been idle
        # for WARM_DELAY_MS (the drawer then opens without rendering); any input change
        # cancels the queue.
        self._warm_timer = QTimer(self)
        self._warm_timer.setSingleShot(True)
        self._warm_timer.setInterval(WARM_DELAY_MS)
        self._warm_timer.timeout.connect(self._warm_equations)
        self.state.design_ready.connect(lambda *_: self._warm_timer.start())
        # any input change (e.g. a slider drag) stops a running warm-up at once
        self.state.inputs_changed.connect(lambda *_: self._stop_warm())
        app = QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(_warm.shutdown)

        self.state.busy_changed.connect(self.busy.setVisible)
        self.state.compute_time_changed.connect(lambda _ms: self._update_status())
        self.state.inputs_changed.connect(lambda _i: self._update_status())
        self._update_status()
        self.state.recompute_now()

    def _build_toolbar(self):
        bar = QToolBar("Main")
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.addToolBar(bar)
        self.toggle_left = QAction(theme.icon("panel-left", "text"), "Show inputs panel", self)
        self.toggle_left.setToolTip(tip("toolbar.toggle_left"))
        self.toggle_left.setShortcut(QKeySequence("Ctrl+["))
        self.toggle_right = QAction(theme.icon("panel-right", "text"), "Show results panel", self)
        self.toggle_right.setToolTip(tip("toolbar.toggle_right"))
        self.toggle_right.setShortcut(QKeySequence("Ctrl+]"))
        for action, panel in ((self.toggle_left, self.left_panel),
                              (self.toggle_right, self.right_column)):
            action.setCheckable(True)
            action.setChecked(True)
            action.toggled.connect(panel.setVisible)
            bar.addAction(action)

        bar.addSeparator()
        self.zoom_in_action = QAction(theme.icon("zoom-in", "text"), "Zoom in", self)
        self.zoom_in_action.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.zoom_in_action.setToolTip(tip("toolbar.zoom_in"))
        self.zoom_in_action.triggered.connect(lambda: self.current_canvas().zoom_in())
        self.zoom_out_action = QAction(theme.icon("zoom-out", "text"), "Zoom out", self)
        self.zoom_out_action.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.zoom_out_action.setToolTip(tip("toolbar.zoom_out"))
        self.zoom_out_action.triggered.connect(lambda: self.current_canvas().zoom_out())
        self.fit_action = QAction(theme.icon("maximize", "text"), "Fit drawing (F)", self)
        self.fit_action.setShortcut(QKeySequence("F"))
        self.fit_action.triggered.connect(lambda: self.current_canvas().fit())
        self.fit_action.setToolTip(tip("toolbar.fit"))
        for action in (self.zoom_in_action, self.zoom_out_action, self.fit_action):
            bar.addAction(action)

        bar.addSeparator()
        self.layer_actions = {}
        for name, label, on in (("shocks", "Shocks", True), ("regions", "Regions", True),
                                ("dimensions", "Dimensions", False), ("grid", "Grid", False)):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(on)
            action.setToolTip(tip("toolbar.layer"))
            action.toggled.connect(lambda v, n=name: self._set_layer(n, v))
            self._set_layer(name, on)
            button = QToolButton()
            button.setObjectName("layerToggle")
            button.setDefaultAction(action)
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            bar.addWidget(button)
            self.layer_actions[name] = action

        bar.addSeparator()
        self.explain_action = QAction("Explain", self)
        self.explain_action.setShortcut(QKeySequence("E"))
        self.explain_action.setCheckable(True)
        self.explain_action.setToolTip(tip("toolbar.explain"))
        self.explain_action.toggled.connect(self._toggle_explain)
        self.explain_drawer.close_button.clicked.connect(
            lambda: self.explain_action.setChecked(False))
        button = QToolButton()
        button.setObjectName("layerToggle")
        button.setDefaultAction(self.explain_action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        bar.addWidget(button)
        self.explain_button = button

    def canvases(self):
        return (self.canvas, self.offdesign_tab.canvas)

    def current_canvas(self):
        return self.offdesign_tab.canvas if self.tabs.currentWidget() is self.offdesign_tab             else self.canvas

    def _set_layer(self, name, visible):
        for canvas in self.canvases():
            canvas.set_layer_visible(name, visible)

    def _on_tab(self, _index):
        view = "offdesign" if self.tabs.currentWidget() is self.offdesign_tab else "design"
        self.state.set_active_view(view)
        canvas = self.current_canvas()
        self.results_panel.station_table.set_regions(canvas.region_states())
        self.results_panel.show_selection(*canvas.selection, canvas.payload(*canvas.selection))
        if self.explain_drawer.is_open:
            self.explain_drawer.show_item(*canvas.selection)

    def _on_selection(self, canvas, kind, index, payload):
        """Results panel, station table and Explain drawer follow the visible tab's canvas."""
        if canvas is self.current_canvas():
            self.results_panel.show_selection(kind, index, payload)
            if self.explain_drawer.is_open:
                self.explain_drawer.show_item(kind, index)

    def _toggle_explain(self, on):
        """Open: show the drawer in the right column and widen it to DRAWER_W; close: narrow
        it back, then show the results again (200 ms, the centre column follows)."""
        if on:
            self.explain_drawer.show_item(*self.current_canvas().selection)
            self.right_column.setCurrentWidget(self.explain_drawer)
            self.explain_drawer.open()
            target = DRAWER_W
        else:
            self.explain_drawer.close_drawer()
            target = tokens.RIGHT_PANEL_WIDTH
        self._column_anim.stop()
        self._column_anim.setStartValue(float(self.right_column.width()))
        self._column_anim.setEndValue(float(target))
        self._column_anim.start()

    def _on_column_anim_done(self):
        if not self.explain_drawer.is_open:
            self.right_column.setCurrentWidget(self.right_panel)

    def _warm_equations(self):
        s = self.state
        if s.design is None:
            return
        texs = _warm.equations(s.design, s.off_design, s.freestream, s.off_freestream)
        self.warm_futures = _warm.start(texs, tokens.COLORS["text"])

    def _stop_warm(self):
        self._warm_timer.stop()
        _warm.cancel()

    def _build_shortcuts(self, help_menu):
        """Window-level keys (they do not fire while a text field has focus: QLineEdit
        takes printable keys and its own undo/redo first)."""
        from .views.shortcuts_overlay import ShortcutsOverlay

        self.shortcuts_overlay = ShortcutsOverlay(self)
        from .views.tour import TourOverlay

        self.tour = TourOverlay(self)
        self.tour_action = help_menu.addAction("Show &tour")
        self.tour_action.triggered.connect(self.tour.start)
        self.shortcuts_action = help_menu.addAction("&Keyboard shortcuts")
        self.shortcuts_action.setShortcuts([QKeySequence("?"), QKeySequence("Shift+?")])
        self.shortcuts_action.triggered.connect(self.shortcuts_overlay.open)
        help_menu.addSeparator()
        self.addAction(self.shortcuts_action)
        self.play_action = QAction("Play / pause sweep", self)
        self.play_action.setShortcut(QKeySequence("Space"))
        self.play_action.triggered.connect(self.toggle_play)     # wired up in M8
        # disabled until M8: an enabled Space shortcut would take Space away from focused
        # buttons and checkboxes (keyboard activation)
        self.play_action.setEnabled(False)
        self.addAction(self.play_action)
        self.tab_actions = []
        for k in range(4):
            action = QAction(f"Tab {k + 1}", self)
            action.setShortcut(QKeySequence(str(k + 1)))
            action.triggered.connect(lambda *_, i=k: self.tabs.setCurrentIndex(i))
            self.addAction(action)
            self.tab_actions.append(action)
        for action in (self.fit_action, self.explain_action):
            self.addAction(action)

    def toggle_play(self):
        """Space: play / pause the off-design Mach sweep (M8). Nothing yet."""
        self.play_requests = getattr(self, "play_requests", 0) + 1

    def _build_edit_menu(self):
        menu = self.menuBar().addMenu("&Edit")
        self.edit_menu = menu
        self.undo_action = self.undo.stack.createUndoAction(self, "Undo")
        self.undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self.redo_action = self.undo.stack.createRedoAction(self, "Redo")
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Shift+Z"),
                                       QKeySequence.StandardKey.Redo])
        menu.addAction(self.undo_action)
        menu.addAction(self.redo_action)
        self.addAction(self.undo_action)
        self.addAction(self.redo_action)

    def show_about(self):
        from .views.about_dialog import AboutDialog

        self.about_dialog = AboutDialog(self)
        self.about_dialog.open()
        return self.about_dialog

    def is_column_animating(self):
        return self._column_anim.state() == QVariantAnimation.State.Running

    def _on_picture(self, canvas):
        if canvas is self.current_canvas():
            self.results_panel.station_table.set_regions(canvas.region_states())
            self.results_panel.station_table.select_row(
                canvas.selection[1] if canvas.selection[0] == "region" else None)

    def _build_status_bar(self):
        status = self.statusBar()
        status.setSizeGripEnabled(False)
        self.busy = QProgressBar()
        self.busy.setObjectName("busy")
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setFixedWidth(tokens.space(10))
        self.busy.hide()
        self.compute_label = QLabel()
        self.model_label = QLabel()
        self.units_label = QLabel()
        separator = QLabel("·")
        for label, key in ((self.compute_label, "status.compute"),
                           (self.model_label, "status.model"),
                           (self.units_label, "status.units"), (separator, "status.sep")):
            label.setToolTip(tip(key))
        status.addWidget(self.compute_label)
        status.addWidget(self.busy)
        status.addPermanentWidget(self.model_label)
        status.addPermanentWidget(separator)
        status.addPermanentWidget(self.units_label)

    def _update_status(self):
        s = self.state
        if s.compute_ms is None:
            text = "Computing…"
        else:
            design = "design cached" if s.compute_cached else f"design {s.design_ms:.0f} ms"
            sweep = f" · sweep {s.sweep_ms:.0f} ms" if s.sweep_ms is not None else ""
            text = design + sweep
        self.compute_label.setText(text)
        self.model_label.setText(f"Ideal gas, γ = {self.state.inputs.gamma:.2f}")
        self.units_label.setText(self.state.inputs.units)

    # --- drag and drop a project file --------------------------------------------------------
    @staticmethod
    def _dropped_project(mime):
        urls = [u for u in mime.urls() if u.isLocalFile()] if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".busemann"):
            return urls[0].toLocalFile()
        return None

    def dragEnterEvent(self, event):
        if self._dropped_project(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._dropped_project(event.mimeData())
        if path:
            event.acceptProposedAction()
            self.project.open_path(path)

    def closeEvent(self, event):
        if not self.project.maybe_save():
            event.ignore()
            return
        self.project.dirty = False                 # decided: later closes must not ask again
        self._warm_timer.stop()
        self._stop_warm()                              # stop a running warm-up
        self.state.shutdown()
        super().closeEvent(event)


def setup_application(app):
    app.setApplicationName("Busemann")
    app.setApplicationVersion(__version__)
    theme.apply(app)
    return app


def setup_high_dpi():
    """Fractional Windows display scaling (125 %, 150 %) as-is: PassThrough rounding.
    Must run before the QApplication is created."""
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)


def main(argv=None):
    """Start the app; `busemann path/to/file.busemann` opens that project."""
    import multiprocessing

    multiprocessing.freeze_support()          # equation render process in a frozen build
    from .explain.mathsvg import prune_cache

    prune_cache()                             # equation cache: drop old files, cap the size
    setup_high_dpi()
    args = sys.argv[1:] if argv is None else list(argv)
    app = QApplication.instance() or QApplication(["busemann", *args])
    setup_application(app)
    window = MainWindow()                   # hidden while the welcome window is up
    window.resize(1440, 900)
    paths = [a for a in args if not a.startswith("-")]
    if paths:                               # a file on the command line skips the welcome
        window.show()
        window.project.open_later(paths[0])
        return app.exec()
    from .views.welcome_dialog import WelcomeDialog, apply_choice

    welcome = WelcomeDialog()
    welcome.exec()
    apply_choice(window, welcome.choice)
    window.show()
    if welcome.tour_check.isChecked():      # checked by default on the first launch only
        QTimer.singleShot(300, window.tour.start)
    return app.exec()
