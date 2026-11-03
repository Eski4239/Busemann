"""Slider with an uppercase label and a live numeric field kept in sync."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from ..theme import qt as theme
from .number_field import NumberField


class LabeledSlider(QWidget):
    """value_changed fires while dragging and on field entry; released fires when the drag ends."""

    value_changed = Signal(float)
    released = Signal()

    def __init__(self, label, minimum, maximum, step, value, decimals=2, unit="",
                 quantity="dimensionless", parent=None):
        super().__init__(parent)
        self._min, self._step = minimum, step
        steps = round((maximum - minimum) / step)

        self.label = QLabel(theme.caps(label))
        self.label.setObjectName("fieldLabel")
        self.label.setFont(theme.label_font())
        self.field = NumberField(value, decimals, minimum, maximum, unit=unit, quantity=quantity)
        self.field.setFixedWidth(theme.tokens.space(12))
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, steps)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(max(1, steps // 20))

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.label, 1, Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self.field, 0, Qt.AlignmentFlag.AlignTop)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(top)
        layout.addWidget(self.slider)

        self._set_slider(value)
        self.slider.valueChanged.connect(self._from_slider)
        self.slider.sliderReleased.connect(self.released)
        self.field.value_changed.connect(self._from_field)

    def value(self):
        return self.field.value()

    def set_value(self, value):
        """Programmatic update; does not emit."""
        self.field.set_value(value)
        self._set_slider(value)

    def set_range(self, minimum, maximum):
        """Change the slider/field range (keeps the step); does not emit."""
        self._min = minimum
        self.slider.blockSignals(True)
        self.slider.setRange(0, round((maximum - minimum) / self._step))
        self.slider.setPageStep(max(1, self.slider.maximum() // 20))
        self.slider.blockSignals(False)
        self.field.set_range(minimum, maximum)
        self._set_slider(self.field.value())

    def range(self):
        return self._min, round(self._min + self.slider.maximum() * self._step, 10)

    def is_dragging(self):
        return self.slider.isSliderDown()

    def _set_slider(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(round((value - self._min) / self._step))
        self.slider.blockSignals(False)

    def _from_slider(self, position):
        value = round(self._min + position * self._step, 10)
        self.field.set_value(value)
        self.value_changed.emit(value)

    def _from_field(self, value):
        self._set_slider(value)
        self.value_changed.emit(value)
