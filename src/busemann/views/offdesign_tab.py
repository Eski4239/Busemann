"""Off-design tab (spec 4.5): the current design frozen, evaluated at a slider Mach.

Header (design-point chip, off-design Mach slider, regime badge), the inlet canvas in
off-design mode, and a strip with the three off-design charts plus a results card.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from ..canvas import InletCanvas
from ..charts.offdesign_charts import OffDesignCharts
from ..state import off_design_range
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import attach, tip
from ..widgets import LabeledSlider, section_title
from ..crashlog import guarded

# regime -> (badge text, one-line explanation)
REGIMES = {
    "spillage": ("Spillage", "Below design Mach: the ramp shocks cross the cowl line ahead of "
                             "the lip and part of the streamtube spills."),
    "on-lip": ("On-lip", "Design point: every ramp shock focuses on the cowl lip."),
    "shock-in-duct": ("Shock-in-duct", "Above design Mach: the ramp shocks enter the cowl; "
                                       "reflections inside the duct are not modelled."),
    "detached": ("Detached", "A ramp shock is detached at this Mach: the attached-shock model "
                             "does not apply."),
}
EMPTY = "—"
SUBTITLE = "How this fixed inlet performs at other flight Mach numbers"


def _mass_flow_text(kgps, system):
    from inletdesign import units as _units

    return f"{_units.to_display(kgps, 'mass_flow', system):.3g} " \
           f"{_units.unit_label('mass_flow', system)}"


def supply_chip(supplied, demanded):
    """("surplus" | "shortfall", "+4.2 %"): supplied vs demanded mass flow."""
    pct = 100.0 * (supplied - demanded) / demanded
    return ("surplus" if pct >= 0 else "shortfall"), f"{pct:+.1f} %"


class OffDesignCard(QFrame):
    """Values at the slider Mach, each with its difference from the design point."""

    ROWS = (("capture", "Capture", "offcard.capture"),
            ("recovery", "Recovery", "offcard.recovery"),
            ("M_duct", "Duct M", "offcard.M_duct"),
            ("margin", "Margin", "offcard.margin"),
            ("regime", "Regime", "offcard.regime"),
            ("cd_add", "C<sub>D,add</sub>", "offcard.cd_add"),
            ("cd_cowl", "C<sub>D,cowl</sub>", "offcard.cd_cowl"),
            ("supplied", "ṁ supply", "offcard.supplied"),
            ("demanded", "ṁ demand", "offcard.demanded"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        grid = QGridLayout(self)
        grid.setContentsMargins(tokens.space(2), tokens.space(1) + 4, tokens.space(2),
                                tokens.space(1) + 4)
        grid.setHorizontalSpacing(tokens.space(1))
        grid.setVerticalSpacing(4)
        grid.addWidget(section_title("At slider Mach", "section.at_slider_mach"), 0, 0, 1, 3)
        head = QLabel("Δ vs design")
        head.setToolTip(tip("offcard.delta"))
        head.setObjectName("muted")
        head.setAlignment(Qt.AlignmentFlag.AlignRight)
        grid.addWidget(head, 0, 2)
        self.values, self.deltas, self.names = {}, {}, {}
        for r, (key, label, tip_key) in enumerate(self.ROWS, start=1):
            name = QLabel(label)
            name.setObjectName("readoutLabel")
            name.setToolTip(tip(tip_key))
            value = QLabel(EMPTY)
            value.setObjectName("readoutValue")
            if key != "regime":
                value.setFont(theme.mono_font())
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            delta = QLabel("")
            delta.setObjectName("muted")
            delta.setFont(theme.mono_font(tokens.SIZE_LABEL))
            delta.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            delta.setMinimumWidth(tokens.space(8))
            value.setToolTip(tip(tip_key))
            delta.setToolTip(tip("offcard.delta"))
            grid.addWidget(name, r, 0)
            self.names[key] = name
            if key in ("regime", "supplied", "demanded"):    # no delta: use both columns
                grid.addWidget(value, r, 1, 1, 2)
            else:
                grid.addWidget(value, r, 1)
                grid.addWidget(delta, r, 2)
            self.values[key], self.deltas[key] = value, delta
        grid.setColumnStretch(1, 1)
        self.drag_note = QLabel("")                   # non-uniform cowl-face pressure (M9b)
        self.drag_note.setObjectName("muted")
        self.drag_note.setWordWrap(True)
        self.drag_note.setToolTip(tip("offcard.cd_cowl"))
        self.drag_note.hide()
        grid.addWidget(self.drag_note, len(self.ROWS) + 2, 0, 1, 3)
        self.chip = QLabel()                          # surplus / shortfall chip, own row
        self.chip.setObjectName("supplyChip")
        self.chip.setToolTip(tip("offcard.chip"))
        self.chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(self.chip, len(self.ROWS) + 1, 1, 1, 2, Qt.AlignmentFlag.AlignRight)
        self.show_flows(None, None, "SI")

    def show_flows(self, supplied, demanded, system):
        """Supplied (spillage included) vs the engine's demanded mass flow at the slider
        Mach, with a surplus / shortfall chip. Rows hidden while not sizing to an engine."""
        rows = (("supplied", supplied is not None and demanded is not None),
                ("demanded", demanded is not None))
        for key, visible in rows:
            for w in (self.names[key], self.values[key]):   # (their delta is not shown)
                w.setVisible(visible)
        self.chip.setVisible(rows[0][1])
        if demanded is None:
            return
        self.values["demanded"].setText(_mass_flow_text(demanded, system))
        if supplied is None:
            self.chip.setText("")
            return
        self.values["supplied"].setText(_mass_flow_text(supplied, system))
        kind, text = supply_chip(supplied, demanded)
        self.chip.setText(f"{kind} {text}")
        self.chip.setProperty("kind", kind)
        self.chip.style().unpolish(self.chip)
        self.chip.style().polish(self.chip)

    def show_point(self, design, off, regime, frontal_height=0.10):
        def put(key, text, delta=""):
            self.values[key].setText(text)
            self.deltas[key].setText(delta)

        if design is None or off is None:
            self.drag_note.hide()
            for key, *_ in self.ROWS:
                put(key, EMPTY)
            self.values["regime"].setText(REGIMES[regime][0] if regime in REGIMES else EMPTY)
            return
        put("capture", f"{off.mass_capture_ratio:.3f}", f"{off.mass_capture_ratio - 1.0:+.3f}")
        put("recovery", f"{off.recovery_total:.4f}",
            f"{off.recovery_total - design.recovery_total:+.4f}")
        # Mach entering the subsonic duct (behind the terminal shock, if any)
        m_duct = off.M_post_terminal
        put("M_duct", f"{m_duct:.3f}", f"{m_duct - design.M_post_terminal:+.3f}")
        if off.cowl_margin_deg is None:
            put("margin", EMPTY)
            self.values["margin"].setToolTip("Subsonic flow at the lip: no cowl shock.")
        else:
            put("margin", f"{off.cowl_margin_deg:+.2f}",
                f"{off.cowl_margin_deg - design.cowl_margin_deg:+.2f}")
            self.values["margin"].setToolTip(tip("offcard.margin"))
        put("regime", REGIMES[regime][0])
        self._show_drag(design, off, frontal_height)

    def _show_drag(self, design, off, frontal_height):
        """Inviscid pressure-drag coefficients at the slider Mach (M9b), Δ vs the design."""
        from inletdesign import api

        self.drag_note.hide()
        if not design.inputs.n_ramps:
            for key in ("cd_add", "cd_cowl"):
                self.values[key].setText(EMPTY)
                self.deltas[key].setText("")
            return
        add = api.additive_drag(design, off)
        self.values["cd_add"].setText(f"{add:.4f}")
        self.deltas["cd_add"].setText(f"{add:+.4f}")          # 0 at the design point
        cowl = api.cowl_drag(off, frontal_height, design.inputs.gamma, design=design)
        at_design = api.cowl_pressure_drag(
            design.inputs.M, design.inputs.M, 1.0,
            design.cowl_angle_deg + design.inputs.cowl_wedge_deg, frontal_height,
            design.inputs.gamma).cd
        base = tip("offcard.cd_cowl")
        if cowl.cd is None:
            self.values["cd_cowl"].setText(EMPTY)
            self.deltas["cd_cowl"].setText("")
            self.values["cd_cowl"].setToolTip(f"{cowl.reason[:1].upper()}{cowl.reason[1:]}.")
        else:
            self.values["cd_cowl"].setText(f"{cowl.cd:.4f}")
            self.deltas["cd_cowl"].setText("" if at_design is None else
                                           f"{cowl.cd - at_design:+.4f}")
            self.values["cd_cowl"].setToolTip(base if not cowl.note else
                                              f"{base}\n{cowl.note[:1].upper()}{cowl.note[1:]}.")
            if cowl.note:
                self.drag_note.setText(f"{cowl.note[:1].upper()}{cowl.note[1:]}.")
                self.drag_note.show()

    def text(self, key):
        return self.values[key].text()

    def delta(self, key):
        return self.deltas[key].text()


class OffDesignTab(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setObjectName("offDesignTab")

        self.chip = QLabel()
        self.chip.setObjectName("chip")
        self.chip.setToolTip(tip("offdesign.chip"))
        lo, hi = off_design_range(state.inputs.mach)
        self.slider = LabeledSlider("Off-design Mach", lo, hi, 0.01, state.inputs.mach)
        self.slider.label.setToolTip(tip("label.off_design_mach"))
        attach(self.slider, "field.off_design_mach")
        self.badge = QLabel()
        self.badge.setObjectName("regimeBadge")
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Two rows so the tab fits a narrow centre column (Explain drawer open at 1280 px):
        # chip + regime badge, then the full-width slider.
        top = QHBoxLayout()
        top.setSpacing(tokens.space(2))
        from .playback import Playback, PlaybackControls

        self.playback = Playback(state, self)
        self.playback_controls = PlaybackControls(self.playback)
        top.addWidget(self.chip, 0)
        top.addStretch(1)
        top.addWidget(self.badge, 0)
        header = QVBoxLayout()
        header.setContentsMargins(tokens.space(2), tokens.space(1), tokens.space(2), 0)
        header.setSpacing(4)
        header.addLayout(top)
        self.subtitle = QLabel(SUBTITLE)
        self.subtitle.setObjectName("tabSubtitle")
        self.subtitle.setToolTip(tip("tab.offdesign"))
        header.addWidget(self.subtitle)
        slider_row = QHBoxLayout()
        slider_row.setSpacing(tokens.space(2))
        slider_row.addWidget(self.slider, 1)
        slider_row.addWidget(self.playback_controls, 0, Qt.AlignmentFlag.AlignBottom)
        header.addLayout(slider_row)

        self.canvas = InletCanvas(state, mode="offdesign")
        self.charts = OffDesignCharts()
        self.card = OffDesignCard()
        self.card.setFixedWidth(tokens.space(27))
        strip = QWidget()
        strip.setObjectName("offDesignStrip")
        strip.setFixedHeight(tokens.OFFDESIGN_STRIP_H)
        self.strip = strip
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(tokens.space(2))
        bottom.addWidget(self.charts, 1)
        bottom.addWidget(self.card, 0, Qt.AlignmentFlag.AlignTop)
        # legend rows span the whole strip (charts + card) so entries never get clipped
        strip_layout = QVBoxLayout(strip)
        strip_layout.setContentsMargins(tokens.space(2), 0, tokens.space(2), tokens.space(1))
        strip_layout.setSpacing(2)
        strip_layout.addLayout(bottom, 1)
        for label in (self.charts.note_legend, self.charts.cfd_note):
            strip_layout.addWidget(label)            # band colours: hover tooltips instead
        self.charts.band_legend.hide()

        # one "Charts" bar; collapsed by default (the canvas keeps the room)
        self.charts_toggle = QToolButton()
        self.charts_toggle.setObjectName("chartsBar")
        self.charts_toggle.setCheckable(True)
        self.charts_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.charts_toggle.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.charts_toggle.toggled.connect(self.set_charts_expanded)
        self.set_charts_expanded(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.space(1))
        layout.addLayout(header)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.charts_toggle)
        layout.addWidget(strip)

        # Space plays / pauses while the tab background or the canvas has focus (a focused
        # button keeps Space for itself)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.canvas.space_tapped.connect(self.playback.toggle)
        self.slider.slider.sliderPressed.connect(self.playback.stop)
        self.slider.value_changed.connect(self._from_slider)
        self.slider.slider.sliderPressed.connect(lambda: self.canvas.set_animations_enabled(False))
        self.slider.released.connect(lambda: self.canvas.set_animations_enabled(True))
        self.charts.cursor_moved.connect(self._from_chart)
        state.design_ready.connect(lambda *_: self._on_design())
        state.off_design_ready.connect(lambda *_: self._on_off_design())
        state.inputs_changed.connect(lambda *_: self._sync_slider())
        state.inputs_changed.connect(lambda *_: self._on_frontal_height())
        if state.design is not None:
            self._on_design()
            self._on_off_design()

    def set_charts_expanded(self, expanded):
        """Show or hide the chart strip (charts at least twice the old height when shown)."""
        if self.charts_toggle.isChecked() != expanded:
            self.charts_toggle.setChecked(expanded)
            return
        self.strip.setVisible(expanded)
        self.charts_toggle.setText("Charts" if expanded else "Charts ▸")
        self.charts_toggle.setIcon(theme.icon("chevron-down" if expanded else "chevron-right",
                                              "text_muted", 14))
        self.charts_toggle.setToolTip(f"{tip('offdesign.charts_toggle')}\n"
                                      f"{self.charts.band_help()}")

    def charts_expanded(self):
        return self.charts_toggle.isChecked()

    @guarded()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self.hasFocus():
            self.playback.toggle()
            event.accept()
            return
        super().keyPressEvent(event)

    # --- inputs -------------------------------------------------------------------------
    def _from_slider(self, M):
        self.charts.set_cursor(M)
        self.state.update(off_design_mach=M)

    def _from_chart(self, M):
        M = round(M, 2)
        self.slider.set_value(M)
        self.charts.set_cursor(M)
        self.state.update(off_design_mach=M)

    # --- results ------------------------------------------------------------------------
    def _on_design(self):
        d = self.state.design
        if d is None:
            self.chip.setText("No valid design")
            self.charts.set_data(None, None, self.slider.range())
            return
        self.chip.setText(f"Design point: M {d.inputs.M:.2f}, {d.inputs.n_ramps} "
                          f"ramp{'s' if d.inputs.n_ramps != 1 else ''}")
        lo, hi = off_design_range(d.inputs.M)
        self.slider.set_range(lo, hi)
        M = self.state.off_design_mach()
        self.slider.set_value(M)
        i = self.state.inputs
        mdot = self.state.demanded_mass_flow()
        self.charts.set_data(d, self.state.sweep, (lo, hi), diffuser=i.diffuser_recovery,
                             demand=self.state.demand,
                             mdot_text=None if mdot is None else _mass_flow_text(mdot, i.units))
        self.charts.set_cursor(M)

    def _on_off_design(self):
        off, error = self.state.off_design, self.state.off_design_error
        regime = "detached" if error and "shock detached" in error else (
            off.regime if off is not None else None)
        text, explanation = REGIMES.get(regime, (EMPTY, ""))
        self.badge.setText(text)
        self.badge.setToolTip(explanation or tip("offdesign.badge"))
        self.badge.setProperty("regime", regime or "")
        self.badge.style().unpolish(self.badge)
        self.badge.style().polish(self.badge)
        self.card.show_point(self.state.design, off, regime,
                             self.state.inputs.cowl_frontal_height)
        self.card.show_flows(self.state.total_mass_flow(at_off_design=True),
                             self.state.demanded_mass_flow(), self.state.inputs.units)
        if not self.slider.is_dragging():
            self.charts.set_cursor(self.state.off_design_mach())

    def _on_frontal_height(self):
        """The cowl frontal height changes only the drag rows (no recompute)."""
        h = self.state.inputs.cowl_frontal_height
        if h != getattr(self, "_shown_frontal", h) and self.state.off_design is not None:
            self._on_off_design()
        self._shown_frontal = h

    def _sync_slider(self):
        """Follow programmatic changes of the off-design Mach (not while dragging)."""
        if self.slider.is_dragging():
            return
        M = self.state.off_design_mach()
        if abs(self.slider.value() - M) > 1e-9:
            self.slider.set_value(M)
            self.charts.set_cursor(M)

    def regime(self):
        return self.badge.property("regime")
