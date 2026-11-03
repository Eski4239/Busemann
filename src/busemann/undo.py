"""Undo/redo over the design and flight inputs (QUndoStack).

Every change of a tracked Inputs field becomes one command. While a gesture is held (a
slider drag; a canvas corner drag in M8) consecutive changes merge into one command, so a
whole drag is one undo step. View settings (layers, tab), the off-design slider and the unit
system are not part of the history. Loading a project or New clears it.
"""
import dataclasses

from PySide6.QtCore import QObject
from PySide6.QtGui import QUndoCommand, QUndoStack

from inletdesign import units as _units

from .inputs import Inputs

UNTRACKED = {"off_design_mach", "units"}
TRACKED = tuple(f.name for f in dataclasses.fields(Inputs) if f.name not in UNTRACKED)
_GESTURE_ID = 4242            # QUndoCommand.id() of commands recorded inside a gesture

# field -> (label, formatter(value, system))
def _num(fmt):
    return lambda v, system: fmt.format(v)


def _display(quantity, fmt):
    def f(v, system):
        return f"{fmt.format(_units.to_display(v, quantity, system))} " \
               f"{_units.unit_label(quantity, system)}"
    return f


_FIELDS = {
    "mach": ("Mach", _num("{:.2f}")),
    "atmosphere_mode": ("Atmosphere", lambda v, s: {"altitude": "altitude",
                                                     "manual": "manual p, T"}.get(v, v)),
    "altitude_m": ("Altitude", _display("altitude", "{:.2f}")),
    "p_pa": ("p∞", _display("pressure", "{:.3f}")),
    "T_k": ("T∞", _display("temperature", "{:.2f}")),
    "gamma": ("γ", _num("{:.3f}")),
    "n_ramps": ("Ramps", _num("{}")),
    "method": ("Method", lambda v, s: {"oswatitsch": "Oswatitsch", "custom": "custom"}.get(v, v)),
    "custom_angles": ("Ramp angles", lambda v, s: ", ".join(f"{a:.2f}°" for a in v) or "—"),
    "capture_height_m": ("Capture height", _display("length", "{:.3f}")),
    "max_cowl_enabled": ("Max cowl angle", lambda v, s: "on" if v else "off"),
    "max_cowl_deg": ("Max cowl angle", _num("{:.1f}°")),
    "cowl_wedge_deg": ("Cowl lip wedge", _num("{:.1f}°")),
}


def describe(old, new, system="SI"):
    """Undo text for a change between two tracked snapshots (dicts)."""
    changed = [k for k in TRACKED if old.get(k) != new.get(k)]
    if new.get("preset") and new.get("preset") != old.get("preset"):
        return f"Preset {new['preset']}"
    changed = [k for k in changed if k != "preset"]
    if len(changed) == 1:
        key = changed[0]
        label, fmt = _FIELDS[key]
        return f"{label} {fmt(old[key], system)} → {fmt(new[key], system)}"
    if not changed:
        return "Edit inputs"
    return "Edit " + ", ".join(_FIELDS[k][0] for k in changed[:3]) + ("…" if len(changed) > 3
                                                                       else "")


def snapshot(inputs):
    return {k: getattr(inputs, k) for k in TRACKED}


class _InputsCommand(QUndoCommand):
    def __init__(self, undo, old, new, merge):
        super().__init__(describe(old, new, undo.state.inputs.units))
        self.undo_ctl, self.old, self.new, self.merge = undo, old, new, merge
        self._first = True

    def id(self):
        return _GESTURE_ID if self.merge else -1

    def mergeWith(self, other):
        if not (self.merge and other.merge and self.undo_ctl.gesture_serial == other.serial):
            return False
        self.new = other.new
        self.setText(describe(self.old, self.new, self.undo_ctl.state.inputs.units))
        return True

    def redo(self):
        if self._first:                 # pushed after the change already happened
            self._first = False
            return
        self.undo_ctl.apply(self.new)

    def undo(self):
        self.undo_ctl.apply(self.old)


class InputUndo(QObject):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.stack = QUndoStack(self)
        self._snapshot = snapshot(state.inputs)
        self._applying = False
        self._gesture = None
        self.gesture_serial = 0
        state.inputs_changed.connect(self._on_inputs)

    # --- gestures (a whole drag is one step) ------------------------------------------------
    def begin_gesture(self, key):
        self.gesture_serial += 1
        self._gesture = key

    def end_gesture(self):
        self._gesture = None
        self.gesture_serial += 1          # the next change starts a new command

    # --- recording ---------------------------------------------------------------------------
    def _on_inputs(self, inputs):
        new = snapshot(inputs)
        if self._applying or new == self._snapshot:
            self._snapshot = new
            return
        cmd = _InputsCommand(self, self._snapshot, new, merge=self._gesture is not None)
        cmd.serial = self.gesture_serial
        self._snapshot = new
        self.stack.push(cmd)

    def apply(self, fields):
        """Set tracked fields (undo/redo) without recording."""
        self._applying = True
        try:
            changes = {k: v for k, v in fields.items() if getattr(self.state.inputs, k) != v}
            if changes:
                self.state.update(**changes)
        finally:
            self._applying = False
        self._snapshot = snapshot(self.state.inputs)

    def clear(self):
        """New / open project: forget the history and take the current inputs as the base."""
        self.stack.clear()
        self._snapshot = snapshot(self.state.inputs)
        self._gesture = None
