"""Numeric spin box with up/down arrows, typing with units and hard limits (M8.4).

Used for the Advanced inputs (max cowl angle, cowl lip wedge, diffuser recovery, γ). Unlike
NumberField, the range is a hard limit: the arrows and the wheel stop at it, and a typed value
outside it is clamped, with a muted field note ("Maximum 90°"). A unit typed with the value
("0.3 rad") is converted as in NumberField. The API the panels use is NumberField's: value(),
set_value(v, emit), value_changed, edit, set_external_error(), error().
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QValidator
from PySide6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from inletdesign.units import UnitError, parse_quantity

from ..theme import qt as theme
from .number_field import NumberField

MIN_WIDTH = 96          # px: room for the value and the arrows at every scale


class _UnitSpin(QDoubleSpinBox):
    """QDoubleSpinBox whose text may carry a unit; out-of-range typing is accepted and then
    clamped (Qt's own validator would refuse the keystrokes instead)."""

    def __init__(self, owner):
        super().__init__()
        self._owner = owner
        self.clamped = None          # "min" | "max" after a clamped commit, else None
        self.parse_error = None      # message of the last unparseable commit
        self.interpreted = False     # a typed value was read since the last commit

    def _parse(self, text):
        o = self._owner
        text = text.strip()
        if o.quantity is not None:
            return parse_quantity(text, o.quantity, o.unit_label.text() or None)
        return float(text.replace(",", "."))

    # Qt virtuals: they must return a value of the right type, so each catches its own
    # errors (crashlog.guarded would return None)
    def validate(self, text, pos):
        try:
            self._parse(text)
        except Exception:                                        # noqa: BLE001
            return QValidator.State.Intermediate, text, pos     # keep typing ("0.3 ra")
        return QValidator.State.Acceptable, text, pos

    def fixup(self, text):
        try:
            self._parse(text)
        except UnitError as exc:
            self.parse_error = str(exc)
        except Exception:                                        # noqa: BLE001
            self.parse_error = "Enter a number"
        return text

    def valueFromText(self, text):
        try:
            raw = self._parse(text)
        except Exception:                                        # noqa: BLE001
            return self.value()
        self.parse_error = None
        self.interpreted = True
        self.clamped = "max" if raw > self.maximum() else ("min" if raw < self.minimum()
                                                          else None)
        return min(max(raw, self.minimum()), self.maximum())

    def textFromValue(self, value):
        return f"{value:.{self.decimals()}f}"


class SpinField(QWidget):
    value_changed = Signal(float)

    def __init__(self, value=0.0, decimals=1, minimum=0.0, maximum=90.0, step=0.1,
                 min_exclusive=False, unit="", quantity=None, parent=None):
        super().__init__(parent)
        self.quantity = quantity
        self._min_exclusive = min_exclusive
        self._external_error = None
        self._note = None

        self.spin = _UnitSpin(self)
        self.spin.setObjectName("spinField")
        self.spin.setDecimals(decimals)
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(step)
        self.spin.setKeyboardTracking(False)            # value_changed on commit, not per key
        self.spin.setAccelerated(True)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.spin.setFont(theme.mono_font())
        self.spin.setMinimumWidth(MIN_WIDTH)
        self.spin.setCorrectionMode(QDoubleSpinBox.CorrectionMode.CorrectToPreviousValue)
        self.edit = self.spin.lineEdit()
        self.unit_label = QLabel(unit)
        self.unit_label.setObjectName("unit")
        self.unit_label.setFont(theme.mono_font(11))
        self.unit_label.setMinimumWidth(theme.tokens.space(4))
        self.error_label = QLabel()
        self.error_label.setObjectName("fieldError")
        self.error_label.setWordWrap(True)
        self.error_label.hide()

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.tokens.space(1) // 2)
        row.addWidget(self.spin, 1)
        row.addWidget(self.unit_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
        layout.addWidget(self.error_label)

        self.set_value(value)
        self.spin.valueChanged.connect(self._on_value)
        self.spin.editingFinished.connect(self._after_commit)
        self.edit.editingFinished.connect(self._interpret)    # also when emitted directly

    # --- public (NumberField API) ---------------------------------------------------------
    def value(self):
        return self.spin.value()

    def set_value(self, value, emit=False):
        if value is None:
            return
        self.spin.blockSignals(True)
        self.spin.setValue(float(value))
        self.spin.blockSignals(False)
        self._show_message()
        if emit:
            self.value_changed.emit(self.spin.value())

    def set_external_error(self, message):
        self._external_error = message
        self._show_message()

    def error(self):
        return self.error_label.text() if self.error_label.isVisible() else None

    def note(self):
        """The clamp note shown under the field ("Maximum 90°"), or None."""
        return self._note

    def minimum(self):
        return self.spin.minimum()

    def maximum(self):
        return self.spin.maximum()

    def units_hint(self):
        return NumberField.units_hint(self)

    def setToolTip(self, text):
        hint = self.units_hint()
        full = f"{text}\n{hint}" if text and hint else (text or hint)
        super().setToolTip(full)
        for w in (self.spin, self.edit, self.unit_label):
            w.setToolTip(full)

    # --- internals ------------------------------------------------------------------------
    def _limit_text(self, which):
        value = self.spin.maximum() if which == "max" else self.spin.minimum()
        unit = self.unit_label.text()
        num = f"{value:.{self.spin.decimals()}f}".rstrip("0").rstrip(".")
        sep = "" if unit in ("°", "") else " "
        return f"{'Maximum' if which == 'max' else 'Minimum'} {num}{sep}{unit}"

    def _interpret(self):
        if self.edit.text() != self.spin.textFromValue(self.spin.value()):
            self.spin.interpretText()
        self._after_commit()

    def _on_value(self, value):
        self._note = self._limit_text(self.spin.clamped) if self.spin.clamped else None
        self.spin.clamped = None
        self.spin.interpreted = False  # this commit is handled here
        self._show_message()
        if self._min_exclusive and value <= self.spin.minimum():
            return                     # e.g. recovery 0: shown as an error, not applied
        self.value_changed.emit(value)

    def _after_commit(self):
        if self.spin.parse_error:
            self._note = None
            message, self.spin.parse_error = self.spin.parse_error, None
            self._show_message(message)
            return
        if self.spin.clamped:          # clamped to the value already shown: no valueChanged
            self._note = self._limit_text(self.spin.clamped)
            self.spin.clamped = None
        elif self.spin.interpreted:    # a valid typed value clears the note
            self._note = None
        self.spin.interpreted = False
        self._show_message()

    def _show_message(self, error=None):
        if error is None and self._min_exclusive and self.spin.value() <= self.spin.minimum():
            error = f"Must be > {self.spin.minimum():g}{self.unit_label.text()}"
        error = error or self._external_error
        text = "\n".join(t for t in (self._note, error) if t)     # the clamp note stays
        self.error_label.setObjectName("fieldError" if error else "fieldNote")
        self.error_label.style().unpolish(self.error_label)
        self.error_label.style().polish(self.error_label)
        self.error_label.setText(text)
        self.error_label.setVisible(bool(text))
        self.spin.setProperty("invalid", bool(error))
        self.spin.style().unpolish(self.spin)
        self.spin.style().polish(self.spin)
