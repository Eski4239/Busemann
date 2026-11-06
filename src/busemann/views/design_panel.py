"""Design panel (spec 4.2): ramps, method, custom angles, capture size, read-only geometry.

Capture size (addendum C1): "Set capture height" drives h_c directly; "Size to engine mass
flow" drives it from the required mdot and the inlet width. The quantity that does not drive
the design is shown read-only with a lock icon.
"""
import re

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from inletdesign import units as _units

from ..theme import tokens
from ..widgets import (
    CollapsibleSection, NumberField, SegmentedControl, SpinField, field_label, section_title,
)
from . import format as fmt
from .ramp_table import RampTable
from .readout import Readout
from ..tooltips import attach, tip

MAX_RAMPS = 4
DEFAULT_CUSTOM_ANGLE = 8.0
_DECIMALS_LENGTH = {"SI": 3, "Imperial": 2}
_RAMP_ERROR = re.compile(r"^ramp (\d+):")
NO_WIDTH_TEXT = "set a width first"
CAPTURE_MODE_LABELS = (("height", "Set capture height"),
                       ("mass_flow", "Size to engine mass flow"))


class DesignPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        i = state.inputs

        self.ramps = SegmentedControl([(str(n), str(n)) for n in range(MAX_RAMPS + 1)],
                                      str(i.n_ramps))
        self.ramps.setToolTip(tip("design.ramps"))
        self.method = SegmentedControl(
            [("oswatitsch", "Optimum angles"), ("custom", "Custom angles")], i.method
        )
        self.method.setToolTip(tip("design.method"))
        self.method.button("oswatitsch").setToolTip(tip("design.method_optimum"))
        self.method.button("custom").setToolTip(tip("design.method_custom"))

        self.custom_box = QWidget()
        custom_form = _form(self.custom_box)
        self.angle_fields = []
        self.angle_labels = []
        for k in range(MAX_RAMPS):
            field = NumberField(DEFAULT_CUSTOM_ANGLE, decimals=2, minimum=0.0, maximum=60.0,
                                min_exclusive=True, unit="°", quantity="angle")
            attach(field, "field.custom_angle")
            label = field_label(f"θ{k + 1}", "field.custom_angle")
            custom_form.addRow(label, field)
            field.value_changed.connect(lambda _v: self._push_custom_angles())
            self.angle_fields.append(field)
            self.angle_labels.append(label)
        self.custom_error = QLabel()
        self.custom_error.setObjectName("fieldError")
        self.custom_error.setToolTip(tip("design.custom_error"))
        self.custom_error.setWordWrap(True)
        self.custom_error.hide()

        # a combo box: the two labels do not fit side by side in the 300 px panel
        self.capture_mode = QComboBox()
        for key, text in CAPTURE_MODE_LABELS:
            self.capture_mode.addItem(text, key)
        self.capture_mode.setToolTip(tip("design.capture_mode"))
        self.capture = NumberField(i.capture_height_m, minimum=0.0, min_exclusive=True,
                                   quantity="length")
        attach(self.capture, "field.capture_height")
        self.mdot = NumberField(i.mdot_kgps, decimals=3, minimum=0.0, min_exclusive=True,
                                unit="kg/s", quantity="mass_flow", optional=True)
        attach(self.mdot, "field.mdot")
        self.width_field = NumberField(i.inlet_width_m, decimals=3, minimum=0.0, min_exclusive=True,
                                 quantity="length", optional=True)
        self.width_field.set_placeholder("optional")
        attach(self.width_field, "field.inlet_width")

        # Advanced: optional limit on the cowl angle of the Oswatitsch optimum (off by default).
        self.max_cowl_check = QCheckBox("Max cowl angle")
        self.max_cowl_check.setToolTip(tip("design.max_cowl"))
        # M8.4: spin boxes with hard limits (angles 0-90°, recovery 0-1); the core's physics
        # checks (e.g. a lip wedge above 30°) still report on the field
        self.max_cowl = SpinField(i.max_cowl_deg, decimals=1, minimum=0.0, maximum=90.0,
                                  step=0.1, min_exclusive=True, unit="°", quantity="angle")
        self.wedge = SpinField(i.cowl_wedge_deg, decimals=1, minimum=0.0, maximum=90.0,
                               step=0.1, unit="°", quantity="angle")
        attach(self.wedge, "field.wedge")
        attach(self.max_cowl, "field.max_cowl")
        advanced_box = QWidget()
        grid = QFormLayout(advanced_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(tokens.space(1))
        grid.setVerticalSpacing(tokens.space(1))
        # a long label goes above its field, so the field keeps the panel width (the 30 px
        # fields of M8.3 scrolled their text out of view)
        grid.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        grid.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.advanced_form = grid
        grid.addRow(self.max_cowl_check, self.max_cowl)
        grid.addRow(field_label("Cowl lip wedge", "label.cowl_lip_wedge"), self.wedge)
        self.diffuser = SpinField(i.diffuser_recovery, decimals=3, minimum=0.0, maximum=1.0,
                                  step=0.01, min_exclusive=True, quantity="dimensionless")
        attach(self.diffuser, "field.diffuser")
        grid.addRow(field_label("Diffuser recovery (estimate)", "label.diffuser"), self.diffuser)
        self.advanced = CollapsibleSection("Advanced", advanced_box, collapsed=True,
                                           tooltip=tip("design.advanced"))

        self.ramp_table = RampTable()
        self.ramp_table.setToolTip(tip("ramp_table.row"))
        self.readout = Readout([
            ("throat", "Throat height", "length", "readout.throat"),
            ("cowl", "Cowl angle", None, "readout.cowl"),
            ("margin", "Cowl margin", None, "readout.margin"),
        ])

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(tokens.space(1))
        form.setVerticalSpacing(tokens.space(1))
        form_top = QFormLayout()
        form_top.setContentsMargins(0, 0, 0, 0)
        form_top.setHorizontalSpacing(tokens.space(1))
        form_top.addRow(field_label("Ramps", "label.ramps"), self.ramps)
        form.addRow(field_label("Capture height", "label.capture_height"), self.capture)
        form.addRow(field_label("Required ṁ", "label.mdot"), self.mdot)
        form.addRow(field_label("Inlet width", "label.inlet_width"), self.width_field)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2), tokens.space(2))
        layout.setSpacing(tokens.space(1) + 4)
        layout.addWidget(section_title("Design", "section.design"))
        layout.addLayout(form_top)
        layout.addWidget(field_label("Capture size", "label.capture_mode"))
        layout.addWidget(self.capture_mode)
        layout.addLayout(form)
        layout.addWidget(field_label("Method", "label.method"))
        layout.addWidget(self.method)
        layout.addWidget(self.custom_box)
        layout.addWidget(self.custom_error)
        layout.addWidget(self.advanced)
        layout.addWidget(field_label("Geometry", "label.geometry"))
        layout.addWidget(self.ramp_table)
        layout.addWidget(self.readout)

        self.ramps.changed.connect(lambda key: self._set_ramps(int(key)))
        self.method.changed.connect(self._set_method)
        self.max_cowl_check.toggled.connect(lambda on: state.update(max_cowl_enabled=on))
        self.max_cowl.value_changed.connect(lambda v: state.update(max_cowl_deg=v))
        self.wedge.value_changed.connect(lambda v: state.update(cowl_wedge_deg=v))
        self.capture.value_changed.connect(
            lambda v: state.update(capture_height_m=_units.from_display(v, "length",
                                                                          state.inputs.units)))
        self.capture_mode.activated.connect(
            lambda k: state.set_capture_mode(self.capture_mode.itemData(k)))
        self.mdot.value_changed.connect(
            lambda v: state.update(mdot_kgps=_units.from_display(v, "mass_flow",
                                                                   state.inputs.units)))
        self.width_field.value_changed.connect(
            lambda v: state.update(inlet_width_m=_units.from_display(v, "length",
                                                                       state.inputs.units)))
        self.width_field.cleared.connect(lambda: state.update(inlet_width_m=None))
        self.diffuser.value_changed.connect(lambda v: state.update(diffuser_recovery=v))
        state.inputs_changed.connect(self.sync)
        state.design_ready.connect(self._show_design)
        self.sync(i)

    # --- widgets -> state ------------------------------------------------
    def _seed_angles(self, n):
        """Custom angles for n ramps: keep current ones, else the last optimum, else a default."""
        current = list(self.state.inputs.custom_angles)
        if len(current) < n and self.state.design is not None:
            optimum = list(self.state.design.ramp_angles_deg)
            current = current + optimum[len(current):n]
        fill = current[-1] if current else DEFAULT_CUSTOM_ANGLE
        return tuple(round(a, 2) for a in (current + [fill] * n)[:n])

    def _set_ramps(self, n):
        changes = {"n_ramps": n}
        if self.state.inputs.method == "custom":
            changes["custom_angles"] = self._seed_angles(n)
        self.state.update(**changes)

    def _set_method(self, method):
        changes = {"method": method}
        if method == "custom":
            changes["custom_angles"] = self._seed_angles(self.state.inputs.n_ramps)
        self.state.update(**changes)

    def _push_custom_angles(self):
        n = self.state.inputs.n_ramps
        self.state.update(custom_angles=tuple(f.value() for f in self.angle_fields[:n]))

    # --- state -> widgets ------------------------------------------------
    def sync(self, i):
        system = i.units
        self.ramps.set_current(str(i.n_ramps))
        self.method.set_current(i.method)
        custom = i.method == "custom" and i.n_ramps > 0
        self.custom_box.setVisible(custom)
        for k, (field, label) in enumerate(zip(self.angle_fields, self.angle_labels)):
            visible = custom and k < i.n_ramps
            field.setVisible(visible)
            label.setVisible(visible)
            if visible and k < len(i.custom_angles):
                field.set_value(i.custom_angles[k])
        self.max_cowl_check.blockSignals(True)
        self.max_cowl_check.setChecked(i.max_cowl_enabled)
        self.max_cowl_check.blockSignals(False)
        self.max_cowl.set_value(i.max_cowl_deg)
        self.wedge.set_value(i.cowl_wedge_deg)
        self.max_cowl.setEnabled(i.max_cowl_enabled and i.method != "custom")
        self.diffuser.set_value(i.diffuser_recovery)
        for field in (self.capture, self.width_field):
            field.set_decimals(_DECIMALS_LENGTH[system])
            field.set_unit(_units.unit_label("length", system))
        self.mdot.set_unit(_units.unit_label("mass_flow", system))
        self.width_field.set_value(None if i.inlet_width_m is None else
                             _units.to_display(i.inlet_width_m, "length", system))
        sizing = i.capture_mode == "mass_flow"
        self.capture_mode.setCurrentIndex(self.capture_mode.findData(i.capture_mode))
        self.capture.set_locked(sizing)
        self.mdot.set_locked(not sizing)
        self.width_field.optional = not sizing                 # sizing needs a width
        self.width_field.set_placeholder("optional" if not sizing else "")
        self._show_sizing()
        self._show_design(self.state.design, self.state.design_error)

    def _show_sizing(self):
        """Capture height and required mdot: the driving one from the inputs, the locked
        one computed (sized height / what the design captures through the width)."""
        i, system = self.state.inputs, self.state.inputs.units
        if i.capture_mode == "mass_flow":
            self.capture.set_value(_units.to_display(self.state.capture_height(), "length",
                                                     system))
            self.mdot.set_value(None if i.mdot_kgps is None else
                                _units.to_display(i.mdot_kgps, "mass_flow", system))
            self.mdot.set_placeholder("")
        else:
            self.capture.set_value(_units.to_display(i.capture_height_m, "length", system))
            total = self.state.total_mass_flow()
            self.mdot.set_value(None if total is None else
                                _units.to_display(total, "mass_flow", system))
            self.mdot.set_placeholder(NO_WIDTH_TEXT)

    def _show_design(self, result, error):
        system = self.state.inputs.units
        self._show_sizing()
        self._show_error(error)
        if result is None:
            self.ramp_table.clear()
            for key in ("cowl", "margin"):
                self.readout.set_text(key, "—")
            self.readout.set_si("throat", None, system)
            return
        custom = result.inputs.method == "custom"
        self.ramp_table.set_rows([
            (theta, beta, result.regions[k + 1].M)
            for k, (theta, beta) in enumerate(zip(result.ramp_angles_deg, result.betas_deg))
        ], self.state.sensitivity if custom else None)
        self.readout.set_si("throat", result.throat_height, system)
        self.readout.set_text("cowl", f"{result.cowl_angle_deg:.2f}", "°")
        self.readout.set_text("margin", f"{result.cowl_margin_deg:+.2f}", "°")

    def _show_error(self, error):
        """Route a core error to the ramp field it names, else show it under the method."""
        for field in (*self.angle_fields, self.wedge, self.max_cowl):
            field.set_external_error(None)
        if error and error.startswith(("cowl lip wedge", "max cowl angle")):
            field = self.wedge if error.startswith("cowl lip wedge") else self.max_cowl
            field.set_external_error(fmt.nbsp(error[:1].upper() + error[1:]))
            self.custom_error.hide()
            return
        target = None
        if error and self.state.inputs.method == "custom":
            match = _RAMP_ERROR.match(error)
            if match and int(match.group(1)) <= MAX_RAMPS:
                target = self.angle_fields[int(match.group(1)) - 1]
        if target is not None:
            detail = error.split(":", 1)[1].strip()
            target.set_external_error(fmt.nbsp(detail[:1].upper() + detail[1:]))
            self.custom_error.hide()
        else:
            self.custom_error.setText(fmt.nbsp(error or ""))
            self.custom_error.setVisible(bool(error))


def _form(widget):
    form = QFormLayout(widget)
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(tokens.space(1))
    form.setVerticalSpacing(tokens.space(1))
    return form
