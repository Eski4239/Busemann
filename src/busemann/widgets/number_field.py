"""Numeric input with a muted mono unit suffix and inline validation (no dialogs, no clamping)."""
import math

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from inletdesign.units import UnitError, accepted_units, parse_quantity

from ..crashlog import guarded
from ..theme import qt as theme

# example typed into the tooltip per quantity kind
_EXAMPLES = {"altitude": "65000 ft", "length": "12 cm", "temperature": "-56.5 C",
             "pressure": "1 atm", "angle": "0.3 rad", "mass_flow": "100 lb/s",
             "dimensionless": "2.2"}


class NumberField(QWidget):
    """Emits value_changed(float) only for valid input; invalid input shows a red underline + message.

    Bounds are checked, never applied: an out-of-range entry is reported, not clamped.
    With a `quantity` kind (units.UNIT_KINDS) the text may carry a unit ("65000 ft"); it is
    converted to the field's unit, and a unit of the wrong kind is reported as an error.
    """

    value_changed = Signal(float)
    cleared = Signal()              # an optional field was emptied

    def __init__(self, value=0.0, decimals=2, minimum=None, maximum=None,
                 min_exclusive=False, unit="", quantity=None, optional=False, parent=None):
        super().__init__(parent)
        self.quantity = quantity
        self.optional = optional          # empty text is a valid "no value" (value() None)
        self._lock_action = None
        self._decimals = decimals
        self._min = minimum
        self._max = maximum
        self._min_exclusive = min_exclusive
        self._value = None if value is None else float(value)
        self._external_error = None

        self.edit = QLineEdit()
        self.edit.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.edit.setFont(theme.mono_font())
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
        row.addWidget(self.edit, 1)
        row.addWidget(self.unit_label)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row)
        layout.addWidget(self.error_label)

        self.edit.editingFinished.connect(self._commit)
        self.edit.returnPressed.connect(self._commit)
        self._show_value()

    # --- public -------------------------------------------------------
    def value(self):
        return self._value

    def set_value(self, value, emit=False):
        self._value = None if value is None else float(value)
        self._show_value()
        self._set_error(self._external_error)  # keep errors reported by the core
        if emit and self._value is not None:
            self.value_changed.emit(self._value)

    def set_placeholder(self, text):
        """Placeholder text; elided to the field width with the full text in the tooltip
        when it does not fit (the tooltip always carries it)."""
        self._placeholder = text or ""
        self._fit_placeholder()

    def placeholder_fits(self):
        text = getattr(self, "_placeholder", "")
        return self._placeholder_room() >= self.edit.fontMetrics().horizontalAdvance(text)

    def _placeholder_room(self):
        icon = 22 if self._lock_action is not None else 0          # leading lock action
        return max(0, self.edit.width() - 2 * 8 - 4 - icon)

    def _fit_placeholder(self):
        text = getattr(self, "_placeholder", "")
        if not text:
            self.edit.setPlaceholderText("")
            self._set_placeholder_tip(None)
            return
        fm = self.edit.fontMetrics()
        if self.edit.width() <= 1 or self.placeholder_fits():
            self.edit.setPlaceholderText(text)
        else:
            self.edit.setPlaceholderText(
                fm.elidedText(text, Qt.TextElideMode.ElideRight, self._placeholder_room()))
        self._set_placeholder_tip(text)

    def _set_placeholder_tip(self, text):
        base = getattr(self, "_base_tooltip", None)
        if base is None:
            base = self.edit.toolTip()
            self._base_tooltip = base
        full = f"{text}\n{base}" if text and base else (text or base)
        self.edit.setToolTip(full)

    @guarded()
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_placeholder", ""):
            self._fit_placeholder()

    def set_locked(self, locked):
        """Read-only with a lock icon: the value is computed from another input."""
        from PySide6.QtWidgets import QLineEdit

        self.edit.setReadOnly(locked)
        self.edit.setFocusPolicy(Qt.FocusPolicy.ClickFocus if locked
                                 else Qt.FocusPolicy.StrongFocus)
        if locked and self._lock_action is None:
            self._lock_action = self.edit.addAction(theme.icon("lock", "text_muted", 14),
                                                    QLineEdit.ActionPosition.LeadingPosition)
        elif not locked and self._lock_action is not None:
            self.edit.removeAction(self._lock_action)
            self._lock_action = None

    def is_locked(self):
        return self.edit.isReadOnly() and self._lock_action is not None

    def set_unit(self, unit):
        self.unit_label.setText(unit)

    def set_range(self, minimum=None, maximum=None):
        self._min, self._max = minimum, maximum

    def set_decimals(self, decimals):
        self._decimals = decimals
        self._show_value()

    def set_external_error(self, message):
        """Error from elsewhere (e.g. the core rejected the value); None clears it."""
        self._external_error = message
        self._set_error(message)

    def error(self):
        return self.error_label.text() if self.error_label.isVisible() else None

    # --- internals ----------------------------------------------------
    def _show_value(self):
        self.edit.setText("" if self._value is None else f"{self._value:.{self._decimals}f}")

    def _set_error(self, message):
        self.edit.setProperty("invalid", bool(message))
        self.edit.style().unpolish(self.edit)
        self.edit.style().polish(self.edit)
        self.error_label.setText(message or "")
        self.error_label.setVisible(bool(message))

    def units_hint(self):
        """'Accepts units: km, m, ft, kft (e.g. 65000 ft).' for the tooltip ('' if none)."""
        if self.quantity is None:
            return ""
        units = accepted_units(self.quantity)
        if not units:
            return "Enter a plain number (no unit)."
        return f"Accepts units: {', '.join(units)} (e.g. {_EXAMPLES[self.quantity]})."

    def setToolTip(self, text):
        """Tooltip text plus the accepted units, on the field, its edit and unit label."""
        hint = self.units_hint()
        full = f"{text}\n{hint}" if text and hint else (text or hint)
        super().setToolTip(full)
        self.edit.setToolTip(full)
        self._base_tooltip = full
        if getattr(self, "_placeholder", ""):
            self._set_placeholder_tip(self._placeholder)
        self.unit_label.setToolTip(full)

    def _validate(self, text):
        if self.quantity is not None:
            try:
                value = parse_quantity(text, self.quantity, self.unit_label.text() or None)
            except UnitError as exc:
                return None, str(exc)
            except ValueError:                 # field unit outside the kind's table
                return None, "Enter a number"
            return self._check_range(value)
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            return None, "Enter a number"
        if not math.isfinite(value):
            return None, "Enter a finite number"
        return self._check_range(value)

    def _check_range(self, value):
        low_bad = self._min is not None and (
            value <= self._min if self._min_exclusive else value < self._min
        )
        if low_bad or (self._max is not None and value > self._max):
            return None, self._range_message()
        return value, None

    def _range_message(self):
        unit = f" {self.unit_label.text()}" if self.unit_label.text() else ""
        fmt = lambda v: f"{v:.{self._decimals}f}".rstrip("0").rstrip(".")  # noqa: E731
        if self._min is not None and self._max is not None:
            op = ">" if self._min_exclusive else "≥"
            return f"Must be {op} {fmt(self._min)} and ≤ {fmt(self._max)}{unit}"
        if self._min is not None:
            return f"Must be {'>' if self._min_exclusive else '≥'} {fmt(self._min)}{unit}"
        return f"Must be ≤ {fmt(self._max)}{unit}"

    def _commit(self):
        if self.edit.isReadOnly():
            return
        if self.optional and not self.edit.text().strip():
            self._set_error(self._external_error)
            if self._value is not None:
                self._value = None
                self.cleared.emit()
            return
        value, message = self._validate(self.edit.text())
        if message:
            self._set_error(message)
            return
        self._set_error(self._external_error)
        changed = value != self._value
        self._value = value
        self._show_value()
        if changed:
            self.value_changed.emit(value)
