"""Analytics tab (M9a, addendum D.1): the recovery trade study, exact within the model.

"Recovery vs turning" at the current design Mach (n = 1-4 cowl-constrained optima and the
isentropic limit, θmax line) and "Recovery vs design Mach" (n = 0-4 optima, MIL-E-5008B, and
the cowl angle with θmax below). Hover a point for its numbers; click one and "Apply this
design" sets n, the design Mach and (when constrained) the max cowl angle as one undo step.
The numbers come from a worker thread, curve by curve, cached by (M, γ).
"""
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
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

VIEWS = (("turning", "Recovery vs turning"), ("mach", "Recovery vs design Mach"))
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

        self.pages = QStackedWidget()
        self.pages.addWidget(page_t)
        self.pages.addWidget(page_m)

        self.selection_label = QLabel(NO_SELECTION)
        self.selection_label.setObjectName("muted")
        self.selection_label.setWordWrap(True)
        self.apply_button = QPushButton("Apply this design")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setEnabled(False)
        self.apply_button.setToolTip(tip("analytics.apply"))
        self.apply_button.clicked.connect(self.apply_selection)
        bottom = QHBoxLayout()
        bottom.addWidget(self.selection_label, 1)
        bottom.addWidget(self.apply_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2),
                                  tokens.space(2))
        layout.setSpacing(tokens.space(1))
        layout.addLayout(top)
        layout.addWidget(self.pages, 1)
        layout.addLayout(bottom)

        for chart in (self.turning_chart, self.mach_chart, self.cowl_chart):
            chart.picked.connect(lambda key, i, c=chart: self._on_pick(c, key, i))
        state.design_ready.connect(lambda *_: self._on_design())
        state.inputs_changed.connect(lambda *_: self._update_captions())

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
        self.pages.setCurrentIndex(0 if key == "turning" else 1)
        self._clear_selection()

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
        for chart in (self.turning_chart, self.mach_chart, self.cowl_chart):
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
        self.turning_takeaway.setText(T.turning(M, optima, theta, n))
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
        for chart in (self.turning_chart, self.mach_chart, self.cowl_chart):
            chart.set_selected(None)
        self.selection_label.setText(NO_SELECTION)
        self.apply_button.setEnabled(False)

    def _on_pick(self, chart, key, index):
        for other in (self.turning_chart, self.mach_chart, self.cowl_chart):
            if other is not chart:
                other.set_selected(None)
        if key is None or not isinstance(key, int):
            self._clear_selection()
            return
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
