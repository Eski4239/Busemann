"""Single application state: inputs, latest results, and the debounced recompute pipeline.

Views change inputs through AppState.update() and listen to its signals; they never call
the core. Freestream is cheap (< 1 ms) and computed on the UI thread. Everything else runs
on one worker thread so the UI never blocks:
- a design job (design, the off-design point at the slider Mach and the 40-point
  off-design sweep) whenever a design input changes;
- a lighter off-design job (one off_design_point on the frozen design) when only the
  off-design Mach changes, so dragging that slider never recomputes the design.
Only the newest request's result is used (generation counters, stale results dropped).
"""
import dataclasses
import time

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal

from inletdesign import api

from .inputs import Inputs, preset_changes  # noqa: F401  (re-exported)
from .theme import tokens

OFF_DESIGN_MIN_MACH = 1.2        # off-design slider lower end
OFF_DESIGN_SPAN = 1.5            # slider upper end = design Mach + this
SWEEP_POINTS = 40


# Fields that do not change any computed result.
_DISPLAY_ONLY = {"units", "preset"}
# Fields evaluated on the frozen design by the light off-design job.
_OFF_DESIGN_ONLY = {"off_design_mach"}


def off_design_range(design_mach):
    """(min, max) of the off-design Mach slider for a design Mach."""
    return OFF_DESIGN_MIN_MACH, round(design_mach + OFF_DESIGN_SPAN, 10)


def _off_point(design, mach):
    try:
        return api.off_design_point(design, mach), None
    except ValueError as exc:
        return None, str(exc)


class _WorkerSignals(QObject):
    done = Signal(int, object)      # generation, payload dict


class _DesignJob(QRunnable):
    def __init__(self, generation, state, inputs):
        super().__init__()
        self.generation, self.state, self.inputs = generation, state, inputs
        self.signals = _WorkerSignals()

    def run(self):
        if self.generation != self.state._generation:   # superseded while queued: skip work
            self.signals.done.emit(self.generation, None)
            return
        i = self.inputs
        t0 = time.perf_counter()
        hits = api._design_cached.cache_info().hits
        out = dict(design=None, error=None, off=None, off_error=None, sweep=None, cached=False)
        try:
            out["design"] = api.design(
                i.mach, i.n_ramps, capture_height=i.capture_height_m, gamma=i.gamma,
                ramp_angles=list(i.custom_angles) if i.method == "custom" else None,
                # passed for custom angles too: the api ignores it there and adds a note
                max_cowl_angle=i.max_cowl_deg if i.max_cowl_enabled else None,
                cowl_wedge=i.cowl_wedge_deg,
            )
        except ValueError as exc:
            out["error"] = str(exc)
        d = out["design"]
        out["design_ms"], out["sweep_ms"] = (time.perf_counter() - t0) * 1000.0, None
        if d is not None:
            out["cached"] = api._design_cached.cache_info().hits > hits
            off_mach = i.off_design_mach if i.off_design_mach is not None else d.inputs.M
            out["off"], out["off_error"] = _off_point(d, off_mach)
            if d.inputs.n_ramps > 0:          # no off-design model without ramps
                t1 = time.perf_counter()
                lo, hi = off_design_range(d.inputs.M)
                m_det = api.detachment_mach(d)
                out["sweep"] = api.off_design_sweep(d, max(lo, m_det), hi, SWEEP_POINTS)
                out["sweep_ms"] = (time.perf_counter() - t1) * 1000.0
        out["ms"] = (time.perf_counter() - t0) * 1000.0
        self.signals.done.emit(self.generation, out)


class _OffDesignJob(QRunnable):
    def __init__(self, generation, state, design, mach):
        super().__init__()
        self.generation, self.state, self.design, self.mach = generation, state, design, mach
        self.signals = _WorkerSignals()

    def run(self):
        if self.generation != self.state._off_generation:
            self.signals.done.emit(self.generation, None)
            return
        off, error = _off_point(self.design, self.mach)
        self.signals.done.emit(self.generation, dict(design=self.design, off=off, off_error=error))


class AppState(QObject):
    inputs_changed = Signal(object)            # Inputs
    freestream_ready = Signal(object, object)  # Freestream|None, error|None
    design_ready = Signal(object, object)      # DesignResult|None, error|None
    off_design_ready = Signal(object, object)  # OffDesignResult|None, error|None
    view_changed = Signal(str)                 # "design" | "offdesign"
    dragging_changed = Signal(bool)            # a Mach slider is being dragged
    busy_changed = Signal(bool)
    compute_time_changed = Signal(float)       # ms, freestream + design of the last result

    def __init__(self, inputs=None, parent=None):
        super().__init__(parent)
        self._inputs = inputs or Inputs()
        self.freestream = None
        self.freestream_error = None
        self.design = None
        self.design_error = None
        self.off_design = None
        self.off_design_error = None
        self.sweep = None                # api.Sweep of the current design, or None
        self.compute_ms = None
        self.design_ms = None            # freestream + design (+ off-design point), ms
        self.sweep_ms = None             # off-design sweep, ms (None: no sweep)
        self.compute_cached = False      # last design came from the api cache
        self.off_freestream = None       # freestream at the off-design Mach
        self.active_view = "design"
        self.dragging = False
        self._fs_ms = 0.0
        self._generation = 0
        self._off_generation = 0
        self._busy = False
        self._jobs = {}
        self._off_jobs = {}

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(tokens.DEBOUNCE_MS)
        self._timer.timeout.connect(self.recompute_now)
        self._off_timer = QTimer(self)
        self._off_timer.setSingleShot(True)
        self._off_timer.setInterval(tokens.DEBOUNCE_MS)
        self._off_timer.timeout.connect(self.recompute_off_design_now)

    # --- inputs ---------------------------------------------------------
    @property
    def inputs(self):
        return self._inputs

    def update(self, **changes):
        """Change inputs; schedules a debounced recompute unless only display fields changed.

        A new design Mach resets the off-design slider to the design point."""
        if "mach" in changes and "off_design_mach" not in changes:
            changes["off_design_mach"] = None
        new = dataclasses.replace(self._inputs, **changes)
        if new == self._inputs:
            return
        changed = {k for k in changes if getattr(new, k) != getattr(self._inputs, k)}
        self._inputs = new
        self.inputs_changed.emit(new)
        computed = changed - _DISPLAY_ONLY
        if not computed:
            return
        if computed <= _OFF_DESIGN_ONLY and self.design is not None and \
                not self._timer.isActive():
            self._off_timer.start()
        else:
            self._timer.start()

    def load_inputs(self, inputs):
        """Replace every input at once (project open / New) and recompute everything."""
        self._timer.stop()
        self._off_timer.stop()
        self._inputs = inputs
        self.inputs_changed.emit(inputs)
        self.recompute_now()

    def off_design_mach(self):
        """Mach the off-design view evaluates: the slider value, or the design Mach."""
        if self._inputs.off_design_mach is not None:
            return self._inputs.off_design_mach
        return self.design.inputs.M if self.design is not None else self._inputs.mach

    def set_dragging(self, dragging):
        """A Mach slider drag starts/ends (expensive views wait for the end)."""
        if dragging != self.dragging:
            self.dragging = dragging
            self.dragging_changed.emit(dragging)

    def set_active_view(self, view):
        if view != self.active_view:
            self.active_view = view
            self.view_changed.emit(view)

    # --- derived quantities ---------------------------------------------
    def captured_mass_flow(self, at_off_design=False):
        """Captured mass flow per span at the design Mach, or at the off-design Mach."""
        if at_off_design:
            if self.off_freestream is None or self.off_design is None:
                return None
            return api.captured_mass_flow(self.off_freestream, self._inputs.capture_height_m,
                                          self.off_design.mass_capture_ratio)
        if self.freestream is None or self.design is None:
            return None
        return api.captured_mass_flow(self.freestream, self._inputs.capture_height_m,
                                      self.design.mass_capture)

    def notices(self):
        """(group, level, text, detail) for every current model-limit message.

        group "design": freestream + design point; group "off": the off-design point at the
        slider Mach, only while the off-design view is active. level is "info", "warn" or
        "error"; detail is a longer explanation (tooltip) or None. Duplicates are dropped
        within a group."""
        design = []
        if self.freestream is not None:
            design.extend(("warn", w, None) for w in self.freestream.warnings)
        if self.design is not None:
            design.extend((n.level, n.text, n.detail) for n in self.design.notices)
        groups = [("design", design)]
        if self.active_view == "offdesign":
            off = []
            if self.off_freestream is not None:
                off.extend(("warn", w, None) for w in self.off_freestream.warnings)
            if self.off_design is not None:
                off.extend((n.level, n.text, n.detail) for n in self.off_design.notices)
            if self.off_design_error:
                no_model = self.off_design_error == api._off.NO_RAMPS_MESSAGE
                off.append(("info" if no_model else "error", self.off_design_error, None))
            groups.append(("off", off))
        out = []
        for group, items in groups:
            seen = set()
            for level, text, detail in items:
                if text not in seen:
                    seen.add(text)
                    out.append((group, level, text, detail))
        return out

    def warnings(self):
        out = []
        if self.freestream is not None:
            out.extend(self.freestream.warnings)
        if self.design is not None:
            out.extend(self.design.warnings)
        return out

    def is_busy(self):
        return self._busy

    # --- pipeline -------------------------------------------------------
    def recompute_now(self):
        self._timer.stop()
        self._off_timer.stop()
        i = self._inputs
        t0 = time.perf_counter()
        try:
            if i.atmosphere_mode == "altitude":
                fs = api.freestream(i.mach, altitude_m=i.altitude_m, gamma=i.gamma)
            else:
                fs = api.freestream(i.mach, p=i.p_pa, T=i.T_k, gamma=i.gamma)
            self.freestream, self.freestream_error = fs, None
        except ValueError as exc:
            self.freestream, self.freestream_error = None, str(exc)
        self._fs_ms = (time.perf_counter() - t0) * 1000.0
        self.freestream_ready.emit(self.freestream, self.freestream_error)

        self._generation += 1
        self._off_generation += 1         # pending off-design jobs are now stale
        job = _DesignJob(self._generation, self, i)
        job.signals.done.connect(self._on_design_done)
        self._jobs[self._generation] = job   # keep signals alive until delivered
        self._set_busy(True)
        self._pool.start(job)

    def recompute_off_design_now(self):
        """Evaluate the frozen design at the current off-design Mach (worker thread)."""
        self._off_timer.stop()
        if self.design is None:
            return
        self._off_generation += 1
        job = _OffDesignJob(self._off_generation, self, self.design, self.off_design_mach())
        job.signals.done.connect(self._on_off_design_done)
        self._off_jobs[self._off_generation] = job
        self._pool.start(job)

    def _on_design_done(self, generation, out):
        self._jobs.pop(generation, None)
        if generation != self._generation or out is None:
            return
        self.design, self.design_error = out["design"], out["error"]
        self.off_design, self.off_design_error = out["off"], out["off_error"]
        self.sweep = out["sweep"]
        self.compute_ms = self._fs_ms + out["ms"]
        self.design_ms = self._fs_ms + out["design_ms"]
        self.sweep_ms = out["sweep_ms"]
        self.compute_cached = out["cached"]
        self._update_off_freestream()
        self._set_busy(False)
        self.design_ready.emit(self.design, self.design_error)
        self.off_design_ready.emit(self.off_design, self.off_design_error)
        self.compute_time_changed.emit(self.compute_ms)

    def _on_off_design_done(self, generation, out):
        self._off_jobs.pop(generation, None)
        if generation != self._off_generation or out is None or out["design"] is not self.design:
            return                      # stale: a newer slider value or a new design exists
        self.off_design, self.off_design_error = out["off"], out["off_error"]
        self._update_off_freestream()
        self.off_design_ready.emit(self.off_design, self.off_design_error)

    def _update_off_freestream(self):
        """Freestream at the off-design Mach (same atmosphere); cheap, UI thread."""
        self.off_freestream = None
        if self.off_design is None:
            return
        i = self._inputs
        try:
            if i.atmosphere_mode == "altitude":
                self.off_freestream = api.freestream(self.off_design.M_inf,
                                                     altitude_m=i.altitude_m, gamma=i.gamma)
            else:
                self.off_freestream = api.freestream(self.off_design.M_inf, p=i.p_pa, T=i.T_k,
                                                     gamma=i.gamma)
        except ValueError:
            self.off_freestream = None

    def _set_busy(self, busy):
        if busy != self._busy:
            self._busy = busy
            self.busy_changed.emit(busy)

    def shutdown(self):
        self._timer.stop()
        self._off_timer.stop()
        self._generation += 1
        self._off_generation += 1
        self._pool.waitForDone(2000)
