"""Compare tab (M10, addendum F): slot A, a frozen pinned or loaded design, beside slot B, the
live design driven by the left panel. No input panel in the tab.

Header (names, Swap, Load into A/B, Unpin, Overlay), two canvases on the same scale, Mach
colour map and legend with shared zoom and pan (or one canvas with A's outline dashed over
B), the KPI table (A | B | Δ | Δ%, Δ coloured only by each metric's better direction) and
the off-design curves of both, collapsed by default. Every computation runs on this tab's
worker thread (debounced, stale results dropped, cached by inputs and slider Mach); the GUI
thread only draws.
"""
import dataclasses
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QBoxLayout, QFileDialog, QGraphicsPathItem, QHBoxLayout,
    QHeaderView, QLabel, QMessageBox, QPushButton, QSizePolicy, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from .. import compare as C
from .. import project as P
from ..canvas import InletCanvas
from ..canvas import picture as _pic
from ..canvas.scene import _path
from ..charts.compare_charts import CompareCharts
from ..crashlog import guarded
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..undo import TRACKED

DEBOUNCE_MS = 120
CACHE_SIZE = 64
EMPTY_A = "Nothing pinned — press Pin (P) on the Design tab, or Load into A…"
OVERLAY_TEXT = "A: dashed outline over B"
CURVES_TEXT = "Off-design curves"
COLUMNS = ("Metric", "A", "B", "Δ", "Δ%")
STACK_WIDTH = 900


class SlotView(QObject):
    """State-like source for an InletCanvas showing one Compare slot (read-only)."""
    design_ready = Signal(object, object)
    off_design_ready = Signal(object, object)
    inputs_changed = Signal(object)

    def __init__(self, live, parent=None):
        super().__init__(parent)
        self.live = live
        self.snapshot = None
        self.design = self.design_error = self.freestream = None
        self.off_design = self.off_design_error = None
        live.inputs_changed.connect(self._on_live_inputs)
        self._units = live.inputs.units

    @property
    def inputs(self):
        base = self.snapshot.inputs if self.snapshot is not None else self.live.inputs
        return dataclasses.replace(base, units=self.live.inputs.units)

    def update(self, **_changes):
        """Compare slots are read-only (no corner drags in compare mode)."""

    def show(self, snapshot):
        self.snapshot = snapshot
        self.design = snapshot.design if snapshot is not None else None
        self.design_error = snapshot.error if snapshot is not None else None
        self.freestream = snapshot.freestream if snapshot is not None else None
        if snapshot is not None:
            self.design_ready.emit(self.design, self.design_error)

    def _on_live_inputs(self, inputs):
        if inputs.units != self._units:
            self._units = inputs.units
            self.inputs_changed.emit(self.inputs)


class _Signals(QObject):
    done = Signal(str, int, object)             # slot, generation, Evaluated


class _SlotJob(QRunnable):
    def __init__(self, slot, generation, kind, args):
        super().__init__()
        self.setAutoDelete(False)
        self.slot, self.generation, self.kind, self.args = slot, generation, kind, args
        self.signals = _Signals()

    def run(self):
        try:
            if self.kind == "load":                 # inputs -> snapshot -> evaluation
                inputs, name, imported, M = self.args
                result = C.evaluate(C.snapshot_from_inputs(inputs, name, imported), M)
            else:
                snapshot, M = self.args
                result = C.evaluate(snapshot, M)
        except Exception as exc:                    # noqa: BLE001 (shown, never raised)
            import sys

            from ..crashlog import log_exception

            log_exception("compare job", *sys.exc_info())
            snap = self.args[0] if self.kind != "load" else C.Snapshot(self.args[0])
            result = C.Evaluated(dataclasses.replace(snap, design=None,
                                                     error=f"internal error: {exc}"),
                                 self.args[-1])
        self.signals.done.emit(self.slot, self.generation, result)


def _key(inputs, M):
    """Cache key: what determines a slot's results (display-only fields dropped)."""
    return (dataclasses.replace(inputs, units="SI", off_design_mach=None, preset=None),
            round(float(M), 10))


class CompareTab(QWidget):
    compare_computed = Signal()        # a slot evaluation arrived and was drawn

    def __init__(self, state, window=None, parent=None):
        super().__init__(parent)
        self.setObjectName("compareTab")
        self.state, self.window = state, window
        self.pinned = None             # Snapshot of slot A, or None
        self.live = None               # Snapshot of slot B (the live design)
        self.evaluated = {"A": None, "B": None}
        self._wanted = {"A": None, "B": None}    # cache key each slot should show
        self._gen = {"A": 0, "B": 0}
        self._jobs = {}
        self._cache = {}
        self._pending = set()
        self._pending_load = None      # (inputs, name, imported) for slot A
        self._syncing = False
        self._overlay_items = []
        self.rows = []
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._run_pending)

        # --- header ---------------------------------------------------------------------
        self.title = QLabel()
        self.title.setObjectName("compareTitle")
        self.title.setTextFormat(Qt.TextFormat.RichText)
        self.title.setToolTip(tip("compare.title"))
        self.swap_button = self._button("Swap A ↔ B", "compare.swap", self.swap)
        self.load_a_button = self._button("Load into A…", "compare.load_a",
                                          lambda: self.load_into_a())
        self.load_b_button = self._button("Load into B…", "compare.load_b", self.load_into_b)
        self.unpin_button = self._button("Unpin", "compare.unpin", self.unpin)
        self.overlay_button = QToolButton()
        self.overlay_button.setObjectName("layerToggle")
        self.overlay_button.setText("Overlay")
        self.overlay_button.setCheckable(True)
        self.overlay_button.setToolTip(tip("compare.overlay"))
        self.overlay_button.toggled.connect(self.set_overlay)
        head = QHBoxLayout()                      # names on one row, actions on the next
        head.setSpacing(tokens.space(1))
        head.addWidget(self.title, 1)
        actions = QHBoxLayout()
        actions.setSpacing(tokens.space(1))
        for w in (self.swap_button, self.load_a_button, self.load_b_button,
                  self.unpin_button):
            actions.addWidget(w)
        actions.addStretch(1)
        actions.addWidget(self.overlay_button)
        self.conditions_note = QLabel(C.DIFFERENT_CONDITIONS)
        self.conditions_note.setObjectName("muted")
        self.conditions_note.setToolTip(tip("compare.conditions"))
        self.imported_note = QLabel("A: " + C.IMPORTED_NOTE)
        self.imported_note.setObjectName("muted")
        self.imported_note.setWordWrap(True)
        self.imported_note.setToolTip(tip("banner.imported"))
        header = QVBoxLayout()
        header.setContentsMargins(tokens.space(2), tokens.space(1), tokens.space(2), 0)
        header.setSpacing(2)
        header.addLayout(head)
        header.addLayout(actions)
        header.addWidget(self.conditions_note)
        header.addWidget(self.imported_note)

        # --- canvases ---------------------------------------------------------------------
        self.views = {"A": SlotView(state, self), "B": SlotView(state, self)}
        self.canvases = {}
        self.captions = {}
        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(tokens.space(1))
        self.columns = {}
        for slot in ("A", "B"):
            canvas = InletCanvas(self.views[slot], mode="compare")
            canvas.set_animations_enabled(False)
            canvas.set_layer_visible("dimensions", False)    # labels would crowd two drawings
            canvas.setMinimumSize(160, 200)
            self.canvases[slot] = canvas
            caption = QLabel(slot)
            caption.setObjectName("muted")
            self.captions[slot] = caption
            caption.setToolTip(tip(f"compare.canvas_{slot.lower()}"))
            box = QWidget()
            v = QVBoxLayout(box)
            v.setContentsMargins(0, 0, 0, 0)
            v.setSpacing(2)
            v.addWidget(caption)
            if slot == "A":
                self.a_stack = QStackedWidget()
                self.empty_a = QLabel(EMPTY_A)
                self.empty_a.setObjectName("muted")
                self.empty_a.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.empty_a.setWordWrap(True)
                self.empty_a.setToolTip(tip("compare.empty"))
                self.a_stack.addWidget(self.empty_a)
                self.a_stack.addWidget(canvas)
                v.addWidget(self.a_stack, 1)
            else:
                self.overlay_label = QLabel(OVERLAY_TEXT)
                self.overlay_label.setObjectName("muted")
                self.overlay_label.setToolTip(tip("compare.overlay"))
                self.overlay_label.hide()
                v.addWidget(self.overlay_label)
                v.addWidget(canvas, 1)
            self.columns[slot] = box
            columns.addWidget(box, 1)
        a, b = self.canvases["A"], self.canvases["B"]
        a.extra_bounds = lambda: self._bounds(b)
        b.extra_bounds = lambda: self._bounds(a) if self.pinned is not None else None
        a.view_moved.connect(lambda: self._sync(a, b))
        b.view_moved.connect(lambda: self._sync(b, a))
        self.columns_layout = columns
        canvas_host = QWidget()
        canvas_host.setLayout(columns)
        self.canvas_host = canvas_host

        # --- KPI table ----------------------------------------------------------------------
        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setObjectName("compareTable")
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.table.setToolTip(tip("compare.table"))
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in range(1, len(COLUMNS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
        self.copy_button = self._button("Copy table", "compare.copy", self.copy_table)
        table_box = QWidget()
        tv = QVBoxLayout(table_box)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(4)
        tv.addWidget(self.table, 1)
        copy_row = QHBoxLayout()
        copy_row.addStretch(1)
        copy_row.addWidget(self.copy_button)
        tv.addLayout(copy_row)

        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(canvas_host)
        self.splitter.addWidget(table_box)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([3000, 2000])

        # --- off-design curves (collapsed by default) ---------------------------------------
        self.charts = CompareCharts()
        self.curves_strip = QWidget()
        sl = QVBoxLayout(self.curves_strip)
        sl.setContentsMargins(tokens.space(2), 0, tokens.space(2), tokens.space(1))
        sl.addWidget(self.charts)
        self.curves_strip.setFixedHeight(280)
        self.curves_toggle = QToolButton()
        self.curves_toggle.setObjectName("chartsBar")
        self.curves_toggle.setCheckable(True)
        self.curves_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.curves_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.curves_toggle.setToolTip(tip("compare.curves"))
        self.curves_toggle.toggled.connect(self.set_curves_expanded)
        self.set_curves_expanded(False)

        body = QVBoxLayout()
        body.setContentsMargins(tokens.space(2), 0, tokens.space(2), 0)
        body.addWidget(self.splitter, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.space(1))
        layout.addLayout(header)
        layout.addLayout(body, 1)
        layout.addWidget(self.curves_toggle)
        layout.addWidget(self.curves_strip)

        state.design_ready.connect(lambda *_: self._on_live_design())
        state.inputs_changed.connect(self._on_inputs)
        self._slider_mach = state.off_design_mach()
        self._units = state.inputs.units
        self._on_live_design()
        self._refresh_header()

    def _button(self, text, tip_key, slot):
        b = QPushButton(text)
        b.setToolTip(tip(tip_key))
        b.clicked.connect(lambda *_: slot())
        return b

    # --- dialogs (replaced in tests) -----------------------------------------------------------
    def ask_replace(self):
        answer = QMessageBox.question(
            self, "Replace pinned design",
            f"Replace the pinned design ({self.pinned.label}) in slot A?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def ask_open_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load into A", "", P.FILTER)
        return path or None

    # --- slot A actions -----------------------------------------------------------------------
    def _settled(self):
        s = self.state
        return not s.is_busy() and not s._timer.isActive()

    def _project_name(self):
        project = getattr(self.window, "project", None)
        return project.path.stem if project is not None and project.path else None

    def _live_snapshot(self, name=None):
        s = self.state
        return C.pin(s.inputs, s.design, s.design_error, s.freestream, s.sweep, name)

    def pin_current(self):
        """Freeze the live design into slot A (asks before replacing a pin)."""
        if self.pinned is not None and not self.ask_replace():
            return False
        name = self._project_name()
        if self._settled():
            self._set_pinned(self._live_snapshot(name))
        else:                                   # results not current yet: compute A itself
            self._load_a(self.state.inputs, name, False)
        if self.window is not None:
            self.window.statusBar().showMessage(
                f"Pinned {name or 'the current design'} as A (Compare tab)", 4000)
        return True

    def load_into_a(self, path=None):
        """Load a DXF into slot A: a Busemann DXF restores every input; any other DXF is
        imported from its geometry with the current flight conditions."""
        if path is None:
            path = self.ask_open_path()
            if not path:
                return False
        if self.pinned is not None and not self.ask_replace():
            return False
        try:
            loaded = P.load(path, base=self.state.inputs)
        except P.ProjectError as exc:
            if self.window is not None:
                self.window.project.show_error(str(exc))
            return False
        self._load_a(loaded[0], Path(path).stem, loaded.imported)
        return True

    def load_into_b(self):
        """The live design: the same as File ▸ Open."""
        return self.window.project.open() if self.window is not None else False

    def unpin(self):
        self._gen["A"] += 1
        self._pending_load = None
        self._pending.discard("A")
        self.pinned = None
        self.evaluated["A"] = None
        self._wanted["A"] = None
        self._show_canvas("A")
        self.set_overlay(False)
        self._draw()

    def swap(self):
        """Slot A becomes the live design (one undo step) and the live design is pinned."""
        if self.pinned is None:
            return False
        a = self.pinned
        old = self.state.inputs
        name = self._project_name()
        if self._settled():
            self._set_pinned(self._live_snapshot(name))
        else:
            self._load_a(old, name, False)
        changes = {k: getattr(a.inputs, k) for k in TRACKED
                   if getattr(a.inputs, k) != getattr(old, k)}
        if changes:
            self.state.update(**changes)            # one inputs change = one undo step
        return True

    def _set_pinned(self, snapshot):
        self._gen["A"] += 1
        self._pending_load = None
        self.pinned = snapshot
        self._schedule("A")
        self._show_canvas("A")
        self._draw()

    def _load_a(self, inputs, name, imported):
        inputs = dataclasses.replace(inputs, off_design_mach=None)
        self._gen["A"] += 1
        self._pending_load = (inputs, name, imported)
        self._schedule("A")

    # --- live slot B --------------------------------------------------------------------------
    def _on_live_design(self):
        s = self.state
        if (s.design is None and s.design_error is None) or s._timer.isActive():
            return                       # nothing computed yet, or newer inputs are pending
        self.live = C.Snapshot(s.inputs, s.design, s.design_error, s.freestream, s.sweep,
                               C.LIVE_NAME)
        self._show_canvas("B")
        self._schedule("B")
        M = s.off_design_mach()            # a new design Mach moves the slider Mach too
        if M != self._slider_mach:
            self._slider_mach = M
            self._schedule("A")

    def _on_inputs(self, inputs):
        M = self.state.off_design_mach()
        if M != self._slider_mach:
            self._slider_mach = M
            self._schedule("A", "B")
        if inputs.units != self._units:
            self._units = inputs.units
            self._draw_table()

    # --- worker -------------------------------------------------------------------------------
    def busy(self):
        """Work in flight or due (pending work waits while the tab is hidden)."""
        return bool(self._jobs) or self._timer.isActive() or (bool(self._pending)
                                                              and self.isVisible())

    def _schedule(self, *slots):
        self._pending.update(slots)
        self._timer.start()

    def _run_pending(self):
        if not self.isVisible():
            return                                  # runs when the tab is shown
        for slot in sorted(self._pending):
            self._run(slot)
        self._pending.clear()

    @guarded()
    def showEvent(self, event):
        super().showEvent(event)
        if self._pending and not self._timer.isActive():
            self._timer.start()

    def _run(self, slot):
        M = self._slider_mach
        if slot == "A" and self._pending_load is not None:
            inputs, name, imported = self._pending_load
            key = _key(inputs, M)
            if key in self._cache and self._cache[key].snapshot.imported == imported:
                ev = self._cache[key]
                self._pending_load = None
                self.pinned = dataclasses.replace(ev.snapshot, name=name, imported=imported)
                self._accept("A", dataclasses.replace(ev, snapshot=self.pinned))
                return
            self._start(slot, key, "load", (inputs, name, imported, M))
            return
        snapshot = self.pinned if slot == "A" else self.live
        if snapshot is None:
            return
        key = _key(snapshot.inputs, M)
        if key in self._cache:
            self._accept(slot, dataclasses.replace(self._cache[key], snapshot=snapshot))
            return
        self._start(slot, key, "eval", (snapshot, M))

    def _start(self, slot, key, kind, args):
        self._gen[slot] += 1
        self._wanted[slot] = key
        job = _SlotJob(slot, self._gen[slot], kind, args)
        job.signals.done.connect(self._on_done)
        self._jobs[(slot, self._gen[slot])] = job
        self._pool.start(job)

    def _on_done(self, slot, generation, ev):
        self._jobs.pop((slot, generation), None)
        key = _key(ev.snapshot.inputs, ev.slider_mach)
        if not (ev.snapshot.error or "").startswith("internal error"):
            self._cache[key] = ev
            while len(self._cache) > CACHE_SIZE:
                self._cache.pop(next(iter(self._cache)))
        if generation != self._gen[slot]:
            return                                  # stale: dropped
        if slot == "A" and self._pending_load is not None:
            self._pending_load = None
            self.pinned = ev.snapshot
        self._accept(slot, ev)

    def _accept(self, slot, ev):
        self.evaluated[slot] = ev
        self._wanted[slot] = _key(ev.snapshot.inputs, ev.slider_mach)
        if slot == "A":
            self._show_canvas("A")
        self._draw()
        self.compare_computed.emit()

    def shutdown(self):
        self._timer.stop()
        for slot in self._gen:
            self._gen[slot] += 1
        self._pool.clear()
        self._pool.waitForDone(2000)

    # --- drawing ------------------------------------------------------------------------------
    def _show_canvas(self, slot):
        """Show a slot's snapshot on its canvas (only when it changed)."""
        snapshot = self.pinned if slot == "A" else self.live
        view = self.views[slot]
        if slot == "A":
            self.a_stack.setCurrentIndex(1 if snapshot is not None else 0)
        if snapshot is view.snapshot:
            return
        self._shared_mach_range(slot, snapshot)
        view.show(snapshot)

    def _shared_mach_range(self, changed=None, snapshot=None):
        """Both canvases use one Mach colour scale: lowest region Mach to the highest M∞."""
        snaps = {"A": self.pinned, "B": self.live}
        if changed is not None:
            snaps[changed] = snapshot
        designs = [s.design for s in snaps.values() if s is not None and s.design is not None]
        rng = None
        if designs:
            rng = (min(r.M for d in designs for r in d.regions), max(d.inputs.M for d in designs))
        for slot, canvas in self.canvases.items():
            scene = canvas.inlet_scene
            if scene.fixed_mach_range != rng:
                scene.fixed_mach_range = rng
                if canvas._shown is not None and slot != changed:
                    canvas._render(canvas._shown)

    def _draw(self):
        self._refresh_header()
        self._draw_table()
        self.charts.set_slot("A", self.pinned)
        self.charts.set_slot("B", self.live)
        self._draw_overlay()

    def _refresh_header(self):
        a = self.pinned.label if self.pinned is not None else "nothing pinned"
        self.title.setText(f"<b>A:</b> {a} &nbsp;vs&nbsp; <b>B:</b> {C.LIVE_NAME}")
        self.captions["A"].setText(f"A: {a} (dashed in the curves)")
        self.captions["B"].setText(f"B: {C.LIVE_NAME} (solid in the curves)")
        has_pin = self.pinned is not None
        for w in (self.swap_button, self.unpin_button, self.overlay_button):
            w.setEnabled(has_pin)
        self.conditions_note.setVisible(C.flight_conditions_differ(self.pinned, self.live))
        self.imported_note.setVisible(has_pin and self.pinned.imported)

    def _draw_table(self):
        units = self.state.inputs.units
        self.rows = C.table(self.evaluated["A"] if self.pinned is not None else None,
                            self.evaluated["B"], units)
        t = self.table
        t.clearSpans()
        t.setRowCount(len(self.rows))
        bold = QFont(t.font())
        bold.setBold(True)
        colours = {"better": QColor(tokens.COLORS["ok"]), "worse": QColor(tokens.COLORS["warn"])}
        for r, row in enumerate(self.rows):
            cells = (row.label, row.a, row.b, row.delta, row.pct)
            for c, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if c:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight
                                          | Qt.AlignmentFlag.AlignVCenter)
                if row.section:
                    item.setFont(bold)
                if c == 1 and row.a_tip:
                    item.setToolTip(row.a_tip)
                if c == 2 and row.b_tip:
                    item.setToolTip(row.b_tip)
                if c >= 3 and row.verdict:
                    item.setForeground(colours[row.verdict])
                    item.setToolTip(row.why)
                t.setItem(r, c, item)
            if row.section:
                t.setSpan(r, 0, 1, len(COLUMNS))
        t.resizeRowsToContents()

    def copy_table(self):
        a = self.pinned.label if self.pinned is not None else "A"
        QApplication.clipboard().setText(C.to_tsv(self.rows, f"A: {a}", f"B: {C.LIVE_NAME}"))

    def set_curves_expanded(self, expanded):
        if self.curves_toggle.isChecked() != expanded:
            self.curves_toggle.setChecked(expanded)
            return
        self.curves_strip.setVisible(expanded)
        self.curves_toggle.setText(CURVES_TEXT if expanded else CURVES_TEXT + " ▸")
        self.curves_toggle.setIcon(theme.icon("chevron-down" if expanded else "chevron-right",
                                              "text_muted", 14))

    def curves_expanded(self):
        return self.curves_toggle.isChecked()

    @guarded()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        target = (QBoxLayout.Direction.TopToBottom if self.canvas_host.width() < STACK_WIDTH
                  else QBoxLayout.Direction.LeftToRight)
        if self.columns_layout.direction() != target:
            self.columns_layout.setDirection(target)

    # --- overlay and shared view -----------------------------------------------------------
    def set_overlay(self, on):
        on = bool(on) and self.pinned is not None
        if self.overlay_button.isChecked() != on:
            self.overlay_button.setChecked(on)
            return
        self.columns["A"].setVisible(not on)
        self.overlay_label.setVisible(on)
        self._draw_overlay()
        self.canvases["B"].fit()

    def overlay_on(self):
        return self.overlay_button.isChecked()

    def _draw_overlay(self):
        scene = self.canvases["B"].inlet_scene
        for item in self._overlay_items:
            scene.removeItem(item)
        self._overlay_items = []
        if not self.overlay_on() or self.pinned is None or self.pinned.design is None:
            return
        pic = _pic.build(_pic.skeleton_from(self.pinned.design))
        pen = QPen(QColor(tokens.COLORS["wall"]), 1.2)
        pen.setCosmetic(True)
        pen.setStyle(Qt.PenStyle.DashLine)
        shock_pen = QPen(pen)
        shock_pen.setColor(QColor(tokens.COLORS["shock"]))
        lines = [(pic.ramp_surface, pen), (pic.cowl_inner, pen), (pic.cowl_outer, pen)]
        lines += [((s.start, s.end), shock_pen) for s in pic.shocks]
        for points, p in lines:
            if len(points) < 2:
                continue
            item = QGraphicsPathItem(_path(points))
            item.setPen(p)
            item.setZValue(1000)
            scene.addItem(item)
            self._overlay_items.append(item)

    def overlay_items(self):
        return list(self._overlay_items)

    @staticmethod
    def _bounds(canvas):
        if canvas.inlet_scene.picture is None:
            return None
        return canvas.inlet_scene.geometry_rect()

    def _sync(self, src, dst):
        if self._syncing or not dst.isVisible() or dst._shown is None:
            return
        self._syncing = True
        try:
            dst.follow(src)
        finally:
            self._syncing = False
