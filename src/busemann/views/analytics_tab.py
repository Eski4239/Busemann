"""Analytics tab (M9a, addendum D.1): the recovery trade study, exact within the model.

"Recovery vs turning" at the current design Mach (n = 1-4 cowl-constrained optima and the
isentropic limit, θmax line) and "Recovery vs design Mach" (n = 0-4 optima, MIL-E-5008B, and
the cowl angle with θmax below). Hover a point for its numbers; click one and "Apply this
design" sets n, the design Mach and (when constrained) the max cowl angle as one undo step.
The numbers come from a worker thread, curve by curve, cached by (M, γ).
"""
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from inletdesign import api

from ..analytics import takeaways as T
from ..charts.analytics_charts import TradeChart
from ..crashlog import guarded
from ..theme import tokens
from ..tooltips import tip
from ..widgets import SegmentedControl

VIEWS = (("turning", "Recovery vs turning"), ("mach", "Recovery vs design Mach"),
         ("drag", "Drag (inviscid estimate)"), ("char", "Inlet characteristic"))
PAGES = {"turning": 0, "mach": 1, "drag": 2, "char": 3}
CHAR_TITLE = "Recovery vs mass-flow ratio at M∞ {M:.2f} (approximate)"
BUZZ_LINE_TEXT = "buzz onset (Ferri–Nucci, approximate)"
BUZZ_BAND_TEXT = "buzz (approximate)"
SEPARATION_LINE = ("If the ramp boundary layer separates (the separation check flags it for "
                   "this design), the real stable range is likely smaller than shown (Ferri & "
                   "Nucci, RM L50K30).")
EXTRAPOLATED_TEXT = "Buzz onset extrapolated beyond the tested Mach range (M 1.9–2.7)."
EXTENSION_TIP = ("Ferri–Nucci criterion (NACA RM L50K30): buzz starts when the vortex sheet "
                 "from the shock intersection enters the cowl. Tested on conical inlets at "
                 "M 1.9–2.7; applying it to a 2D multi-ramp inlet is a Busemann extension. "
                 "The expelled-shock position follows Moeckel (NACA TN 1921) in the flow "
                 "behind the last ramp shock.")
DRAG_CAPTION = ("Inviscid estimate: pressure drag only, no skin friction. Coefficients per "
                "unit width on q∞ × capture height; cowl frontal height {h:.2f} × capture "
                "height (Design ▸ Advanced).")
COWL_GAP_TEXT = "cowl shock detached: not computable"
THETA_LINE_TEXT = "cowl shock detaches beyond here"
MIL_CAPTION = ("MIL-E-5008B (dashed orange): compare with the engine-face estimate, "
               "recovery × diffuser {d:.3f}, not with these inviscid curves.")
NO_SELECTION = "Click a point on a curve to pick a design."
ISENTROPIC_NOTE = "Isentropic limit: not a ramp design, so it cannot be applied."


def _ramps(n):
    return "normal shock" if n == 0 else (f"{n} ramp" if n == 1 else f"{n} ramps")


def _angles(ramps):
    return ", ".join(f"{a:.2f}°" for a in ramps) if ramps else "none"


class _Signals(QObject):
    partial = Signal(int, str, object, object)     # generation, kind, key, payload
    done = Signal(int)


class _AnalyticsJob(QRunnable):
    """Every curve of the tab for design Mach M and γ, emitted as it is computed
    (isentropic first, then each ramp count), so the charts fill progressively."""

    def __init__(self, generation, M, gamma):
        super().__init__()
        self.setAutoDelete(False)
        self.generation, self.M, self.gamma = generation, M, gamma
        self.signals = _Signals()

    def run(self):
        emit = self.signals.partial.emit
        g, M, gamma = self.generation, self.M, self.gamma
        try:
            emit(g, "theta", None, api.max_deflection(M, gamma))
            emit(g, "iso", None, api.isentropic_vs_turning(M, gamma))
            for n in api.TRADE_N_TURNING:
                [curve] = api.trade_vs_turning(M, gamma, n_list=(n,))
                emit(g, "turn", n, curve)
            optima = {0: (api.design(M, 0, gamma=gamma).recovery_total, 0.0)}
            optima.update({n: (api.design(M, n, gamma=gamma).recovery_total,
                               api.design(M, n, gamma=gamma).cowl_angle_deg)
                           for n in api.TRADE_N_TURNING})
            emit(g, "optima", None, optima)
            equal, match = {}, {}
            for base in api.TRADE_N_TURNING:
                d_b = optima[base][1]
                equal[base] = {
                    "rec": {m: api.design(M, m, gamma=gamma, max_cowl_angle=d_b).recovery_total
                            for m in api.TRADE_N_TURNING if m > base},
                    "iso": api.isentropic_vs_turning(M, gamma, delta_grid=(d_b,)).recovery[0]}
                match[base] = {m: api.turning_for_recovery(M, m, optima[base][0], gamma)
                               for m in api.TRADE_N_TURNING if m > base}
            emit(g, "equal_turn", None, equal)
            emit(g, "match", None, match)
            for n in api.TRADE_N_MACH:
                trade = api.trade_vs_design_mach(gamma=gamma, n_list=(n,))
                emit(g, "mach", n, trade.curves[0])
            emit(g, "theta_curve", None, (trade.M, trade.theta_max_deg))
        except Exception as exc:                    # noqa: BLE001 (shown, never raised)
            emit(g, "error", None, str(exc))
        self.signals.done.emit(g)


class AnalyticsTab(QWidget):
    computed = Signal()           # every curve of the current (M, γ) has arrived

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.setObjectName("analyticsTab")
        self.state = state
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._generation = 0
        self._jobs = {}
        self._cache = {}          # (M, γ) -> list of (kind, key, payload)
        self._key = None          # (M, γ) shown
        self._stale = True
        self.data = {}            # kind/key -> payload of the shown (M, γ)
        self.selection = None     # dict describing the picked point, or None
        self.partials_seen = []   # kinds in arrival order (tests: progressive drawing)

        self.view = SegmentedControl(list(VIEWS), "turning")
        self.view.setToolTip(tip("analytics.view"))
        self.view.changed.connect(self.set_view)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        top = QHBoxLayout()
        top.addWidget(self.view)
        top.addStretch(1)
        top.addWidget(self.status)

        self.turning_chart = TradeChart("Recovery vs total turning", "analytics.turning",
                                        "Total turning = cowl angle (°)", "Recovery p0/p0∞")
        self.turning_takeaway = self._takeaway("analytics.takeaway")
        page_t = QWidget()
        vt = QVBoxLayout(page_t)
        vt.setContentsMargins(0, 0, 0, 0)
        vt.addWidget(self.turning_chart, 1)
        vt.addWidget(self.turning_takeaway)

        self.mach_chart = TradeChart("Recovery vs design Mach", "analytics.mach",
                                     "Design Mach M∞", "Recovery p0/p0∞", min_height=180,
                                     end_labels=False)
        self.mil_caption = QLabel("")
        self.mil_caption.setObjectName("chartLegend")
        self.mil_caption.setWordWrap(True)
        self.mil_caption.setToolTip(tip("analytics.mil"))
        self.mach_takeaway = self._takeaway("analytics.takeaway")
        self.cowl_chart = TradeChart("Cowl angle vs design Mach", "analytics.cowl",
                                     "Design Mach M∞", "Cowl angle (°)", min_height=110,
                                     end_labels=False)
        self.cowl_takeaway = self._takeaway("analytics.takeaway")
        page_m = QWidget()
        vm = QVBoxLayout(page_m)
        vm.setContentsMargins(0, 0, 0, 0)
        vm.addWidget(self.mach_chart, 3)
        vm.addWidget(self.mil_caption)
        vm.addWidget(self.mach_takeaway)
        vm.addWidget(self.cowl_chart, 2)
        vm.addWidget(self.cowl_takeaway)

        self.drag_chart = TradeChart("Drag vs M∞ (inviscid estimate)", "analytics.drag_mach",
                                     "M∞", "C<sub>D</sub>",
                                     min_height=170, end_labels=False)
        self.drag_takeaway = self._takeaway("analytics.takeaway")
        self.rc_chart = TradeChart("Recovery vs cowl drag at the design Mach",
                                   "analytics.drag_recovery",
                                   "C<sub>D,cowl</sub> (inviscid estimate)", "Recovery p0/p0∞",
                                   min_height=170)
        self.rc_takeaway = self._takeaway("analytics.takeaway")
        self.drag_caption = QLabel("")
        self.drag_caption.setObjectName("chartLegend")
        self.drag_caption.setWordWrap(True)
        self.drag_caption.setToolTip(tip("analytics.drag"))
        page_d = QWidget()
        vd = QVBoxLayout(page_d)
        vd.setContentsMargins(0, 0, 0, 0)
        vd.addWidget(self.drag_chart, 1)
        vd.addWidget(self.drag_takeaway)
        vd.addWidget(self.rc_chart, 1)
        vd.addWidget(self.rc_takeaway)
        vd.addWidget(self.drag_caption)
        self._rc_index = {}       # n -> turning-curve indices drawn on the recovery-drag chart

        self.pages = QStackedWidget()
        self.pages.addWidget(page_t)
        self.pages.addWidget(page_m)
        self.pages.addWidget(page_d)

        # M9c: inlet characteristic and buzz onset at the off-design slider Mach
        self.char_chart = TradeChart(CHAR_TITLE.format(M=3.0), "analytics.char",
                                     "Mass-flow ratio A0/Ac", "Recovery p0/p0∞",
                                     min_height=200, end_labels=False)
        self.char_caption = QLabel("")
        self.char_caption.setObjectName("chartLegend")
        self.char_caption.setWordWrap(True)
        self.char_caption.setToolTip(EXTENSION_TIP)
        self.char_separation = QLabel(SEPARATION_LINE)
        self.char_separation.setObjectName("chartLegend")
        self.char_separation.setWordWrap(True)
        self.char_separation.setToolTip(tip("analytics.char_separation"))
        self.char_separation.hide()
        self.char_takeaway = self._takeaway("analytics.takeaway")
        page_c = QWidget()
        vc = QVBoxLayout(page_c)
        vc.setContentsMargins(0, 0, 0, 0)
        vc.addWidget(self.char_chart, 1)
        vc.addWidget(self.char_takeaway)
        vc.addWidget(self.char_caption)
        vc.addWidget(self.char_separation)
        self.pages.addWidget(page_c)
        self.characteristic = None
        self._char_timer = QTimer(self)
        self._char_timer.setSingleShot(True)
        self._char_timer.setInterval(120)            # coalesce slider updates
        self._char_timer.timeout.connect(self.update_characteristic)

        self.selection_label = QLabel(NO_SELECTION)
        self.selection_label.setObjectName("muted")
        self.selection_label.setWordWrap(True)
        self.apply_button = QPushButton("Apply this design")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip(tip("analytics.apply"))
        self.apply_button.clicked.connect(self.apply_selection)
        self.selection_row = QWidget()
        bottom = QHBoxLayout(self.selection_row)
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addWidget(self.selection_label, 1)
        bottom.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2),
                                  tokens.space(2))
        layout.setSpacing(tokens.space(1))
        layout.addLayout(top)
        layout.addWidget(self.pages, 1)
        layout.addWidget(self.selection_row)

        for chart in self._charts():
            chart.picked.connect(lambda key, i, c=chart: self._on_pick(c, key, i))
        state.design_ready.connect(lambda *_: self._on_design())
        state.inputs_changed.connect(lambda *_: self._update_captions())
        state.inputs_changed.connect(lambda *_: self._on_inputs())
        state.off_design_ready.connect(lambda *_: self._schedule_characteristic())

    def _charts(self):
        return (self.turning_chart, self.mach_chart, self.cowl_chart, self.drag_chart,
                self.rc_chart, self.char_chart)

    def _schedule_characteristic(self):
        if self.current_view() == "char":
            self._char_timer.start()

    def _on_inputs(self):
        """The cowl frontal height changes only the drag page, the diffuser area ratio only
        the characteristic (no recompute)."""
        if self.current_view() == "char" and \
                self.state.inputs.diffuser_area_ratio != getattr(self, "_drawn_ar", None):
            self._char_timer.start()
        h = self.state.inputs.cowl_frontal_height
        if h != getattr(self, "_drawn_frontal", None) and self.current_view() == "drag":
            self.update_drag()

    @staticmethod
    def _takeaway(tip_key):
        label = QLabel("")
        label.setObjectName("takeaway")
        label.setWordWrap(True)
        label.setToolTip(tip(tip_key))
        return label

    # --- view -------------------------------------------------------------------------------
    def set_view(self, key):
        self.view.set_current(key)
        self.pages.setCurrentIndex(PAGES[key])
        self.selection_row.setVisible(key != "char")      # nothing to pick there
        self._clear_selection()
        if key == "drag":
            self.update_drag()
        if key == "char":
            self.update_characteristic()

    def current_view(self):
        return self.view.current()

    @guarded()
    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self.refresh()

    # --- computation ------------------------------------------------------------------------
    def _design_key(self):
        d = self.state.design
        if d is None:
            return None
        return (round(d.inputs.M, 10), round(d.inputs.gamma, 10))

    def _on_design(self):
        key = self._design_key()
        if key != self._key:
            self._stale = True
            if self.isVisible():
                self.refresh()
        else:
            self._update_markers()
            self._update_takeaways()
            if self.current_view() == "drag":
                self.update_drag()

    def refresh(self):
        """Recompute (or replay from the cache) the curves of the current design's (M, γ)."""
        key = self._design_key()
        self._stale = False
        if key is None:
            return
        self._key = key
        self._generation += 1
        self.data = {}
        self.partials_seen = []
        self._clear_selection()
        for chart in self._charts():
            chart.clear()
        if key in self._cache:
            for kind, k, payload in self._cache[key]:
                self._apply_partial(kind, k, payload)
            self._finish()
            return
        self.status.setText("Computing…")
        job = _AnalyticsJob(self._generation, *key)
        job.signals.partial.connect(self._on_partial)
        job.signals.done.connect(self._on_done)
        self._jobs[self._generation] = job
        self._cache_building = []
        self._pool.start(job)

    def _on_partial(self, generation, kind, key, payload):
        if generation != self._generation:
            return                                   # stale (M, γ): dropped
        self._cache_building.append((kind, key, payload))
        self._apply_partial(kind, key, payload)

    def _on_done(self, generation):
        self._jobs.pop(generation, None)
        if generation != self._generation:
            return
        if "error" not in self.data:
            self._cache[self._key] = list(self._cache_building)
        self._finish()

    def _finish(self):
        self.status.setText(self.data.get("error", ""))
        self._update_markers()
        self._update_takeaways()
        if self.current_view() == "drag":
            self.update_drag()
        self.computed.emit()

    def is_computing(self):
        return bool(self._jobs)

    def wait(self, msecs=5000):
        """Tests: block until the worker is idle."""
        return self._pool.waitForDone(msecs)

    def shutdown(self):
        self._generation += 1
        self._pool.clear()
        self._pool.waitForDone(2000)

    # --- drawing ----------------------------------------------------------------------------
    def _apply_partial(self, kind, key, payload):
        self.partials_seen.append(kind if key is None else f"{kind}:{key}")
        self.data[kind if key is None else (kind, key)] = payload
        M = self._key[0]
        if kind == "theta":
            self.turning_chart.set_vline(payload, THETA_LINE_TEXT)
        elif kind == "iso":
            c = payload
            self.turning_chart.set_series(
                "isentropic", c.delta_deg, c.recovery, pickable=False, label="isentropic",
                text=lambda i, c=c: (f"Isentropic limit at M {M:.2f}\nTurning {c.delta_deg[i]:.2f}°"
                                     f"\nMach after compression {c.M_f[i]:.3f}\n"
                                     f"Recovery {c.recovery[i]:.4f}\n{ISENTROPIC_NOTE}"))
        elif kind == "turn":
            c = payload
            self.turning_chart.set_series(key, c.delta_deg, c.recovery_total,
                                          label=_ramps(key), text=lambda i, c=c: self._turn_text(c, i))
        elif kind == "mach":
            c = payload
            self.mach_chart.set_series(key, c.M, c.recovery_total, label=_ramps(key),
                                       text=lambda i, c=c: self._mach_text(c, i))
            if key > 0:
                self.cowl_chart.set_series(key, c.M, c.cowl_deg, label=_ramps(key),
                                           text=lambda i, c=c: self._cowl_text(c, i))
        elif kind == "theta_curve":
            machs, theta = payload
            self.cowl_chart.set_series(
                "theta", machs, theta, pickable=False, label="θmax(M∞): the cowl shock detaches above it",
                width=1.5, text=lambda i: (f"θmax at M {machs[i]:.2f}: {theta[i]:.2f}°\n"
                                           "a cowl turning above it detaches the cowl shock"))
            mil = [api.mil_recovery(m) for m in machs]
            self.mach_chart.set_series(
                "mil", machs, mil, pickable=False, label="MIL-E-5008B", width=1.5,
                text=lambda i: (f"MIL-E-5008B at M {machs[i]:.2f}: {mil[i]:.4f}\n"
                                "compare with the engine-face estimate (recovery × diffuser)"))
        elif kind == "error":
            self.status.setText(payload)

    def _diffuser(self):
        return self.state.inputs.diffuser_recovery

    def _turn_text(self, c, i):
        lines = [f"{_ramps(c.n)} at M {self._key[0]:.2f}",
                 f"Turning (cowl angle) {c.delta_deg[i]:.2f}°",
                 f"Recovery {c.recovery_total[i]:.4f} (oblique only {c.recovery_oblique[i]:.4f})",
                 f"Ramp angles: {_angles(c.ramps_deg[i])}"]
        lines.append("cowl-constrained optimum" if c.constrained[i] else "unconstrained optimum")
        return "\n".join(lines)

    def _mach_text(self, c, i):
        d = self._diffuser()
        lines = [f"{_ramps(c.n)} at M {c.M[i]:.2f}",
                 f"Recovery {c.recovery_total[i]:.4f}, engine face ≈ {c.recovery_total[i] * d:.4f}",
                 f"Cowl angle {c.cowl_deg[i]:.2f}°"]
        if c.n:
            lines.append(f"Ramp angles: {_angles(c.ramps_deg[i])}")
        return "\n".join(lines)

    def _cowl_text(self, c, i):
        return (f"{_ramps(c.n)} at M {c.M[i]:.2f}\nCowl angle {c.cowl_deg[i]:.2f}°\n"
                f"Ramp angles: {_angles(c.ramps_deg[i])}")

    def _update_markers(self):
        d = self.state.design
        if d is None or self._key is None:
            return
        here = (f"This design: {_ramps(d.inputs.n_ramps)} at M {d.inputs.M:.2f}\n"
                f"Cowl angle {d.cowl_angle_deg:.2f}°, recovery {d.recovery_total:.4f}")
        same = self._design_key() == self._key
        self.turning_chart.set_marker(d.cowl_angle_deg if same else None, d.recovery_total, here)
        self.mach_chart.set_marker(d.inputs.M, d.recovery_total, here)
        self.cowl_chart.set_marker(d.inputs.M, d.cowl_angle_deg, here)

    def _update_takeaways(self):
        optima, theta = self.data.get("optima"), self.data.get("theta")
        d = self.state.design
        if optima is None or theta is None or d is None:
            for label in (self.turning_takeaway, self.mach_takeaway, self.cowl_takeaway):
                label.setText("")
            return
        M, n = self._key[0], d.inputs.n_ramps
        equal = self.data.get("equal_turn")
        self.turning_takeaway.setText(
            T.turning(M, optima, theta, n, equal[T.turning_base(n)]) if equal else "")
        self.mach_takeaway.setText(T.design_mach(M, optima, n))
        self.cowl_takeaway.setText(T.cowl(M, optima, theta, n))
        self._update_captions()

    def _update_captions(self):
        self.mil_caption.setText(MIL_CAPTION.format(d=self._diffuser()))
        if self.data.get("theta_curve") is not None:
            self._update_markers()

    # --- selection and apply ----------------------------------------------------------------
    def _clear_selection(self):
        self.selection = None
        for chart in self._charts():
            chart.set_selected(None)
        self.selection_label.setText(NO_SELECTION)
        self.apply_button.setEnabled(False)

    def _on_pick(self, chart, key, index):
        for other in self._charts():
            if other is not chart:
                other.set_selected(None)
        if key is None or not isinstance(key, int):
            self._clear_selection()
            return
        if chart is self.rc_chart:                 # same design as the turning-curve point
            index = self._rc_index[key][index]
            chart = self.turning_chart
        if chart is self.turning_chart:
            c = self.data[("turn", key)]
            constrained = c.constrained[index]
            changes = dict(mach=self._key[0], n_ramps=key, method="oswatitsch",
                           max_cowl_enabled=bool(constrained))
            if constrained:
                changes["max_cowl_deg"] = round(c.delta_deg[index], 6)
            what = (f"{_ramps(key)} at M {self._key[0]:.2f}, cowl limit "
                    f"{c.delta_deg[index]:.2f}°" if constrained else
                    f"{_ramps(key)} at M {self._key[0]:.2f}, unconstrained optimum")
            rec = c.recovery_total[index]
        else:
            c = self.data[("mach", key)]
            changes = dict(mach=round(c.M[index], 6), n_ramps=key, method="oswatitsch",
                           max_cowl_enabled=False)
            what = f"{_ramps(key)} at M {c.M[index]:.2f}, unconstrained optimum"
            rec = c.recovery_total[index]
        self.selection = dict(changes=changes, text=what, recovery=rec)
        self.selection_label.setText(f"Selected: {what} (recovery {rec:.4f})")
        self.apply_button.setEnabled(True)

    def apply_selection(self):
        """One state.update call = one undo step."""
        if self.selection is None:
            return
        changes = self.selection["changes"]
        self.state.update(**changes)
        self.selection_label.setText(f"Applied: {self.selection['text']}.")
        self.apply_button.setEnabled(False)
        self.selection = None

    # --- drag page (M9b) --------------------------------------------------------------------
    def update_drag(self):
        """Drag vs M∞ from the design's off-design sweep, and recovery vs cowl drag along the
        turning curves at the design Mach. Closed form, on the GUI thread (a few ms)."""
        d, sweep = self.state.design, self.state.sweep
        dh = self.state.inputs.cowl_frontal_height
        self._drawn_frontal = dh
        self.drag_caption.setText(DRAG_CAPTION.format(h=dh))
        if d is None:
            return
        M, gamma, wedge = d.inputs.M, d.inputs.gamma, d.inputs.cowl_wedge_deg
        at_design = api.cowl_pressure_drag(M, M, 1.0, d.cowl_angle_deg + wedge, dh, gamma)
        self._draw_drag_vs_mach(d, sweep, dh, at_design)
        self._draw_recovery_vs_cowl(d, dh, at_design)

    def _draw_drag_vs_mach(self, d, sweep, dh, at_design):
        chart = self.drag_chart
        for key in ("add", "cowl", "total"):
            if key in chart.series:
                chart.plot.getPlotItem().removeItem(chart.series.pop(key)["item"])
        chart.set_bands([])
        if sweep is None or not d.inputs.n_ramps:
            chart.set_marker(None, None, "")
            self.drag_takeaway.setText("No off-design sweep for this design (no ramps), so "
                                       "no drag estimate." if not d.inputs.n_ramps else "")
            return
        ds = api.drag_sweep(d, sweep, dh)
        machs = ds.machs
        total = [None if a is None or c is None else a + c
                 for a, c in zip(ds.cd_add, ds.cd_cowl)]

        def text(i):
            lines = [f"M∞ {machs[i]:.3f}"]
            lines.append(f"{T.CD_ADD} " + ("—" if ds.cd_add[i] is None
                                           else f"{ds.cd_add[i]:.4f}"))
            lines.append(f"{T.CD_COWL} " + (f"{ds.cd_cowl[i]:.4f}" if ds.cd_cowl[i] is not None
                                            else f"— ({ds.reasons[i]})"))
            if total[i] is not None:
                lines.append(f"Sum {total[i]:.4f}")
            if ds.notes[i]:
                lines.append(ds.notes[i][:1].upper() + ds.notes[i][1:])
            lines.append(api.DRAG_LABEL)
            return "<br>".join(lines)

        chart.set_series("add", machs, ds.cd_add, text, label=f"additive {T.CD_ADD}",
                         pickable=False)
        chart.set_series("cowl", machs, ds.cd_cowl, text, label=f"cowl {T.CD_COWL}",
                         pickable=False)
        chart.set_series("total", machs, total, text, label="sum", pickable=False)
        chart.set_vline(d.inputs.M, "design Mach", token="text_muted")
        chart.set_bands(_gaps(machs, ds.cd_cowl, ds.reasons))
        chart.plot.getPlotItem().enableAutoRange()
        chart.place_band_text()
        cd = at_design.cd
        chart.set_marker(d.inputs.M, cd, f"This design at M {d.inputs.M:.2f}<br>"
                         f"{T.CD_COWL} " + ("—" if cd is None else f"{cd:.4f}"))
        self.drag_takeaway.setText(T.drag_vs_mach(d.inputs.M, machs, ds.cd_add, cd))

    def _draw_recovery_vs_cowl(self, d, dh, at_design):
        chart = self.rc_chart
        if self._key is None or ("turn", 1) not in self.data:
            return
        M, gamma, wedge = self._key[0], self._key[1], d.inputs.cowl_wedge_deg
        for key in list(chart.series):
            chart.plot.getPlotItem().removeItem(chart.series[key]["item"])
            if chart.series[key]["label"] is not None:
                chart.plot.getPlotItem().removeItem(chart.series[key]["label"])
        chart.series = {}
        chart.set_selected(None)
        self._rc_index = {}
        for n in api.TRADE_N_TURNING:
            c = self.data.get(("turn", n))
            if c is None:
                continue
            cds = api.cowl_drag_vs_turning(M, c.delta_deg, gamma, wedge, dh)
            keep = [i for i, v in enumerate(cds) if v is not None]
            self._rc_index[n] = keep
            chart.set_series(
                n, [cds[i] for i in keep], [c.recovery_total[i] for i in keep],
                label=_ramps(n),
                text=lambda j, c=c, keep=keep, cds=cds: self._rc_text(c, keep[j], cds))
        iso = self.data.get("iso")
        if iso is not None:
            cds = api.cowl_drag_vs_turning(M, iso.delta_deg, gamma, wedge, dh)
            keep = [i for i, v in enumerate(cds) if v is not None]
            chart.set_series(
                "isentropic", [cds[i] for i in keep], [iso.recovery[i] for i in keep],
                pickable=False, label="isentropic",
                text=lambda j, keep=keep, cds=cds: (
                    f"Isentropic limit at M {M:.2f}<br>Turning {iso.delta_deg[keep[j]]:.2f}°"
                    f"<br>Recovery {iso.recovery[keep[j]]:.4f}<br>{T.CD_COWL} "
                    f"{cds[keep[j]]:.4f}<br>{ISENTROPIC_NOTE}"))
        same = self._design_key() == self._key
        cd = at_design.cd
        chart.set_marker(cd if same else None, d.recovery_total,
                         f"This design: {_ramps(d.inputs.n_ramps)} at M {d.inputs.M:.2f}<br>"
                         f"Recovery {d.recovery_total:.4f}, {T.CD_COWL} "
                         + ("—" if cd is None else f"{cd:.4f}"))
        optima, match = self.data.get("optima"), self.data.get("match")
        if optima is None or match is None:
            return
        base = T.turning_base(d.inputs.n_ramps)
        cd_base = api.cowl_drag_vs_turning(M, (optima[base][1],), gamma, wedge, dh)[0]
        matches = {m: None if delta is None else
                   api.cowl_drag_vs_turning(M, (delta,), gamma, wedge, dh)[0]
                   for m, delta in match[base].items()}
        self.rc_takeaway.setText(T.recovery_vs_cowl(M, d.inputs.n_ramps, optima[base][0],
                                                    cd_base, matches))

    def _rc_text(self, c, i, cds):
        return "<br>".join([
            f"{_ramps(c.n)} at M {self._key[0]:.2f}",
            f"Turning (cowl angle) {c.delta_deg[i]:.2f}°",
            f"Recovery {c.recovery_total[i]:.4f}",
            f"{T.CD_COWL} {cds[i]:.4f} (inviscid estimate)",
            f"Ramp angles: {_angles(c.ramps_deg[i])}"])

    # --- inlet characteristic (M9c) ---------------------------------------------------------
    def update_characteristic(self):
        """Characteristic and buzz onset of the design at the off-design slider Mach (closed
        form plus small root-finds on the GUI thread, ~0.1 s; coalesced by a timer)."""
        d, off = self.state.design, self.state.off_design
        ar = self.state.inputs.diffuser_area_ratio
        self._drawn_ar = ar
        chart = self.char_chart
        chart.clear()
        self.char_separation.setVisible(False)
        self.characteristic = None
        if d is None or off is None or not d.inputs.n_ramps:
            self.char_takeaway.setText("No characteristic: the design needs ramps and an "
                                       "attached off-design point.")
            self.char_caption.setText("")
            return
        try:
            c = api.inlet_characteristic(d, off, ar)
        except ValueError as exc:
            self.char_takeaway.setText(f"No characteristic at M∞ {off.M_inf:.2f}: {exc}.")
            self.char_caption.setText("")
            return
        self.characteristic = c
        chart.title.setText(CHAR_TITLE.format(M=c.M_inf))
        crit = c.critical

        def sup_text(i):
            p = c.supercritical[i]
            return "<br>".join([
                "Supercritical (quasi-1D)", f"Throttle p<sub>x</sub>/p<sub>0∞</sub> "
                f"{p.p_exit:.4f}", f"Shock Mach {p.M_shock:.3f} at A/A<sub>e</sub> "
                f"{p.area_shock:.2f}", f"Recovery {p.recovery:.4f}", f"A0/Ac {p.mfr:.4f}"])

        chart.set_series("super", [p.mfr for p in c.supercritical],
                         [p.recovery for p in c.supercritical], sup_text,
                         label="supercritical (quasi-1D)", pickable=False)
        crit_text = (f"Critical point at M∞ {c.M_inf:.2f}<br>Recovery {crit.recovery:.4f}"
                     f"<br>A0/Ac {crit.mfr:.4f}<br>Throttle p<sub>x</sub>/p<sub>0∞</sub> "
                     f"{crit.p_exit:.4f}")
        chart.set_marker(crit.mfr, crit.recovery, crit_text)
        if c.buzz is None:
            self.char_takeaway.setText(T.characteristic(c))
            self.char_caption.setText(c.note[:1].upper() + c.note[1:] + ".")
            return
        tau_b = c.buzz.tau

        def sub_text(points):
            def text(i):
                p = points[i]
                shock = api.moeckel_shock(d, off, p.tau) if p.tau else None
                lines = ["Subcritical (approximate)", f"Throttle p<sub>x</sub>/p<sub>0∞</sub> "
                         f"{p.p_exit:.4f}", f"Spilled fraction τ {p.tau:.3f}"]
                if shock is not None:
                    lines.append(f"Shock {shock.L / d.inputs.capture_height:.3f} × capture "
                                 "height ahead of the lip (Moeckel)")
                lines += [f"Recovery {p.recovery:.4f}", f"A0/Ac {p.mfr:.4f}"]
                if p.tau >= tau_b:
                    lines.append("past the buzz onset (Ferri–Nucci, approximate)")
                return "<br>".join(lines)
            return text

        stable = [p for p in c.subcritical if p.tau <= tau_b]
        if not stable or stable[-1].tau < tau_b:
            stable = stable + [_point_at(c, tau_b, d.inputs.gamma)]
        beyond = [stable[-1]] + [p for p in c.subcritical if p.tau > tau_b]
        chart.set_series("sub", [p.mfr for p in stable], [p.recovery for p in stable],
                         sub_text(stable), label="subcritical (approximate)", pickable=False)
        chart.set_series("buzz", [p.mfr for p in beyond], [p.recovery for p in beyond],
                         sub_text(beyond), label="beyond buzz onset (approximate)",
                         pickable=False)
        chart.set_vline(c.buzz.mfr, BUZZ_LINE_TEXT)
        chart.set_bands([(min(p.mfr for p in beyond), c.buzz.mfr, BUZZ_BAND_TEXT)])
        chart.plot.getPlotItem().enableAutoRange()
        chart.place_band_text()
        self.char_takeaway.setText(T.characteristic(c))
        parts = [f"Buzz onset A0/Ac {c.buzz.mfr:.4f} "
                 f"({'exact triple point' if c.buzz.exact_used else 'sheet along the region-n flow'}"
                 f"); θ<sub>n</sub> fallback {c.buzz_fallback.mfr:.4f}."]
        if c.buzz.extrapolated:
            parts.append(EXTRAPOLATED_TEXT)
        parts.append("2D multi-ramp application of the criterion: Busemann extension.")
        self.char_caption.setText(" ".join(parts))
        flagged = any(s.shock.startswith("ramp") and s.flagged for s in d.separation)
        self.char_separation.setVisible(flagged)


def _point_at(c, tau, gamma):
    """The subcritical point at exactly tau (the buzz onset) on the ideal flat branch."""
    from inletdesign import characteristic as _char

    crit = c.critical
    m_crit = _char.mass_flow_function(crit.M_exit, gamma)
    M_x = _char.mach_from_mass_flow(m_crit * (1.0 - tau), gamma) if tau > 0 else crit.M_exit
    return _char.CharPoint(mfr=crit.mfr * (1.0 - tau), recovery=crit.recovery,
                           p_exit=crit.recovery * _char.p_over_pt(M_x, gamma), M_exit=M_x,
                           tau=tau)


def gap_label(reason):
    """'cowl shock detached: not computable in this model' -> '…: not computable'."""
    return (reason or COWL_GAP_TEXT).replace(" in this model", "")


def _gaps(xs, values, reasons):
    """Contiguous x ranges where values is None (one per reason), widened to the midpoints
    of the neighbouring samples: [(lo, hi, label), ...]."""
    out, start = [], None
    for k in range(len(values) + 1):
        missing = k < len(values) and values[k] is None
        same = missing and start is not None and reasons[k] == reasons[start]
        if start is not None and not same:
            end = k - 1
            lo = xs[start] if start == 0 else 0.5 * (xs[start - 1] + xs[start])
            hi = xs[end] if end == len(xs) - 1 else 0.5 * (xs[end] + xs[end + 1])
            out.append((lo, hi, gap_label(reasons[start])))
            start = None
        if missing and start is None:
            start = k
    return out

