"""Flight conditions panel (spec 4.1): Mach, atmosphere, gamma, units, presets, freestream read-out."""
from PySide6.QtWidgets import QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from inletdesign import presets as _presets
from inletdesign import units as _units

from ..theme import tokens
from ..widgets import (
    CollapsibleSection, LabeledSlider, NumberField, SegmentedControl, field_label, section_title,
)
from ..inputs import preset_changes
from .readout import Readout
from ..tooltips import attach, tip

MACH_RANGE = (1.2, 7.0)       # slider covers every preset (X-15 is M 6.7)
ALTITUDE_RANGE_M = (0.0, 40000.0)
GAMMA_RANGE = (1.0, 5.0 / 3.0)
CUSTOM = "Custom"

# quantity -> decimals per unit system
_DECIMALS = {
    "altitude": {"SI": 2, "Imperial": 0},
    "pressure": {"SI": 3, "Imperial": 4},
    "temperature": {"SI": 2, "Imperial": 2},
}


class FlightPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        i = state.inputs

        self.units = SegmentedControl([("SI", "SI"), ("Imperial", "Imperial")], i.units)
        self.units.setToolTip(tip("flight.units_toggle"))
        self.preset = QComboBox()
        self.preset.addItem(CUSTOM)
        for p in _presets.PRESETS:
            self.preset.addItem(p.name)
            self.preset.setItemData(self.preset.count() - 1, p.description)
        self.preset_note = QLabel()
        self.preset_note.setObjectName("muted")
        self.preset_note.setToolTip(tip("flight.preset_note"))
        self.preset_note.setWordWrap(True)
        self.preset_note.hide()

        self.mach = LabeledSlider("Mach number", *MACH_RANGE, 0.01, i.mach, decimals=2)
        self.mach.label.setToolTip(tip("label.mach_number"))
        attach(self.mach, "field.mach")

        self.mode = SegmentedControl(
            [("altitude", "Altitude"), ("manual", "Manual p, T")], i.atmosphere_mode
        )
        self.mode.setToolTip(tip("flight.mode"))
        self.altitude = NumberField(0.0)
        self.pressure = NumberField(0.0, min_exclusive=True)
        self.temperature = NumberField(0.0, min_exclusive=True)
        attach(self.altitude, "field.altitude")
        attach(self.pressure, "field.p_inf")
        attach(self.temperature, "field.t_inf")

        self.altitude_row = QWidget()
        alt_form = _form(self.altitude_row)
        alt_form.addRow(field_label("Altitude", "label.altitude"), self.altitude)
        self.manual_row = QWidget()
        man_form = _form(self.manual_row)
        man_form.addRow(field_label("p∞", "label.p_inf"), self.pressure)
        man_form.addRow(field_label("T∞", "label.t_inf"), self.temperature)

        gamma_box = QWidget()
        gamma_form = _form(gamma_box)
        self.gamma = NumberField(i.gamma, decimals=3, minimum=GAMMA_RANGE[0],
                                 maximum=GAMMA_RANGE[1], min_exclusive=True)
        attach(self.gamma, "field.gamma")
        gamma_form.addRow(field_label("γ (cp/cv)", "label.gamma"), self.gamma)
        self.advanced = CollapsibleSection("Advanced", gamma_box, collapsed=True,
                                           tooltip=tip("flight.advanced"))

        self.readout = Readout([
            ("p", "p∞", "pressure", "readout.p"),
            ("T", "T∞", "temperature", "readout.T"),
            ("rho", "ρ∞", "density", "readout.rho"),
            ("V", "V∞", "velocity", "readout.V"),
            ("p0", "p0∞", "pressure", "readout.p0"),
            ("T0", "T0∞", "temperature", "readout.T0"),
            ("Re", "Re / length", "per_length", "readout.Re"),
        ])
        self.error = QLabel()
        self.error.setObjectName("errorText")
        self.error.setToolTip(tip("flight.error"))
        self.error.setWordWrap(True)
        self.error.hide()

        top = QFormLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setHorizontalSpacing(tokens.space(1))
        top.setVerticalSpacing(tokens.space(1))
        top.addRow(field_label("Units", "label.units"), self.units)
        top.addRow(field_label("Preset", "label.preset"), self.preset)
        self.preset.setToolTip(tip("label.preset"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2), tokens.space(2))
        layout.setSpacing(tokens.space(1) + 4)
        layout.addWidget(section_title("Flight conditions", "section.flight_conditions"))
        layout.addLayout(top)
        layout.addWidget(self.preset_note)
        layout.addWidget(self.mach)
        layout.addWidget(field_label("Atmosphere", "label.atmosphere"))
        layout.addWidget(self.mode)
        layout.addWidget(self.altitude_row)
        layout.addWidget(self.manual_row)
        layout.addWidget(self.advanced)
        layout.addWidget(field_label("Freestream", "label.freestream"))
        layout.addWidget(self.readout)
        layout.addWidget(self.error)

        # widgets -> state
        self.units.changed.connect(lambda key: state.update(units=key))
        self.preset.currentTextChanged.connect(self._apply_preset)
        self.mach.value_changed.connect(lambda v: state.update(mach=v, preset=None))
        self.mode.changed.connect(lambda key: state.update(atmosphere_mode=key, preset=None))
        self.altitude.value_changed.connect(
            lambda v: state.update(altitude_m=self._si(v, "altitude"), preset=None))
        self.pressure.value_changed.connect(
            lambda v: state.update(p_pa=self._si(v, "pressure"), preset=None))
        self.temperature.value_changed.connect(
            lambda v: state.update(T_k=self._si(v, "temperature"), preset=None))
        self.gamma.value_changed.connect(lambda v: state.update(gamma=v))

        # state -> widgets
        state.inputs_changed.connect(self.sync)
        state.freestream_ready.connect(self._show_freestream)
        self.sync(i)

    # ------------------------------------------------------------------
    def _si(self, display_value, quantity):
        return _units.from_display(display_value, quantity, self.state.inputs.units)

    def _apply_preset(self, name):
        if name == CUSTOM:
            self.state.update(preset=None)
            return
        self.state.update(**preset_changes(name))

    def _set_field(self, field, value_si, quantity, system, minimum_si=None, maximum_si=None):
        field.set_decimals(_DECIMALS[quantity][system])
        field.set_unit(_units.unit_label(quantity, system))
        field.set_range(
            None if minimum_si is None else _units.to_display(minimum_si, quantity, system),
            None if maximum_si is None else _units.to_display(maximum_si, quantity, system),
        )
        field.set_value(_units.to_display(value_si, quantity, system))

    def sync(self, i):
        """Mirror the state's inputs in the widgets (never emits)."""
        system = i.units
        self.units.set_current(system)
        self.preset.blockSignals(True)
        self.preset.setCurrentText(i.preset or CUSTOM)
        self.preset.blockSignals(False)
        if i.preset:
            self.preset_note.setText(_presets.get(i.preset).description)
        self.preset_note.setVisible(bool(i.preset))

        self.mach.set_value(i.mach)
        self.mode.set_current(i.atmosphere_mode)
        self.altitude_row.setVisible(i.atmosphere_mode == "altitude")
        self.manual_row.setVisible(i.atmosphere_mode == "manual")
        self._set_field(self.altitude, i.altitude_m, "altitude", system, *ALTITUDE_RANGE_M)
        self._set_field(self.pressure, i.p_pa, "pressure", system, 0.0)
        self._set_field(self.temperature, i.T_k, "temperature", system, 0.0)
        self.gamma.set_value(i.gamma)
        self._show_freestream(self.state.freestream, self.state.freestream_error)

    def _show_freestream(self, fs, error):
        system = self.state.inputs.units
        for key in ("p", "T", "rho", "V", "p0", "T0"):
            self.readout.set_si(key, None if fs is None else getattr(fs, key), system)
        self.readout.set_si("Re", None if fs is None else fs.Re_per_m, system, digits=3)
        self.error.setText(error or "")
        self.error.setVisible(bool(error))


def _form(widget):
    form = QFormLayout(widget)
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(tokens.space(1))
    form.setVerticalSpacing(tokens.space(1))
    return form
