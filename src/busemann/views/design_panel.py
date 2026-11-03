"""Design panel (spec 4.2): ramps, method, custom angles, capture height, read-only geometry."""
import re

from PySide6.QtWidgets import QCheckBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from inletdesign import units as _units

from ..theme import tokens
from ..widgets import CollapsibleSection, NumberField, SegmentedControl, field_label, section_title
from . import format as fmt
from .ramp_table import RampTable
from .readout import Readout
from ..tooltips import attach, tip

MAX_RAMPS = 4
DEFAULT_CUSTOM_ANGLE = 8.0
_DECIMALS_LENGTH = {"SI": 3, "Imperial": 2}
_RAMP_ERROR = re.compile(r"^ramp (\d+):")


class DesignPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        i = state.inputs

        self.ramps = SegmentedControl([(str(n), str(n)) for n in range(MAX_RAMPS + 1)],
                                      str(i.n_ramps))
        self.ramps.setToolTip(tip("design.ramps"))
        self.method = SegmentedControl(
            [("oswatitsch", "Oswatitsch optimum"), ("custom", "Custom angles")], i.method
        )
        self.method.setToolTip(tip("design.method"))

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

        self.capture = NumberField(i.capture_height_m, minimum=0.0, min_exclusive=True,
                                   quantity="length")
        attach(self.capture, "field.capture_height")

        # Advanced: optional limit on the cowl angle of the Oswatitsch optimum (off by default).
        self.max_cowl_check = QCheckBox("Max cowl angle")
        self.max_cowl_check.setToolTip(tip("design.max_cowl"))
        self.max_cowl = NumberField(i.max_cowl_deg, decimals=1, minimum=0.0, maximum=90.0,
                                    min_exclusive=True, unit="°", quantity="angle")
        self.wedge = NumberField(i.cowl_wedge_deg, decimals=1, minimum=0.0, maximum=30.0,
                                 unit="°", quantity="angle")
        attach(self.wedge, "field.wedge")
        attach(self.max_cowl, "field.max_cowl")
        advanced_box = QWidget()
        grid = QFormLayout(advanced_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(tokens.space(1))
        grid.setVerticalSpacing(tokens.space(1))
        grid.addRow(self.max_cowl_check, self.max_cowl)
        grid.addRow(field_label("Cowl lip wedge", "label.cowl_lip_wedge"), self.wedge)
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
        form.addRow(field_label("Ramps", "label.ramps"), self.ramps)
        form.addRow(field_label("Capture height", "label.capture_height"), self.capture)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2), tokens.space(2))
        layout.setSpacing(tokens.space(1) + 4)
        layout.addWidget(section_title("Design", "section.design"))
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
        self.capture.set_decimals(_DECIMALS_LENGTH[system])
        self.capture.set_unit(_units.unit_label("length", system))
        self.capture.set_value(_units.to_display(i.capture_height_m, "length", system))
        self._show_design(self.state.design, self.state.design_error)

    def _show_design(self, result, error):
        system = self.state.inputs.units
        self._show_error(error)
        if result is None:
            self.ramp_table.clear()
            for key in ("cowl", "margin"):
                self.readout.set_text(key, "—")
            self.readout.set_si("throat", None, system)
            return
        self.ramp_table.set_rows([
            (theta, beta, result.regions[k + 1].M)
            for k, (theta, beta) in enumerate(zip(result.ramp_angles_deg, result.betas_deg))
        ])
        self.readout.set_si("throat", result.throat_height, system)
        self.readout.set_text("cowl", f"{result.cowl_angle_deg:.2f}", "°")
        self.readout.set_text("margin", f"{result.cowl_margin_deg:+.2f}", "°")

    def _show_error(self, error):
        """Route a core error to the ramp field it names, else show it under the method."""
        for field in self.angle_fields:
            field.set_external_error(None)
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
