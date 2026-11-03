"""Off-design tab (spec 4.5): the current design frozen, evaluated at a slider Mach.

Header (design-point chip, off-design Mach slider, regime badge), the inlet canvas in
off-design mode, and a strip with the three off-design charts plus a results card.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..canvas import InletCanvas
from ..charts.offdesign_charts import OffDesignCharts
from ..state import off_design_range
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import attach, tip
from ..widgets import LabeledSlider, section_title

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


class OffDesignCard(QFrame):
    """Values at the slider Mach, each with its difference from the design point."""

    ROWS = (("capture", "Capture", "offcard.capture"),
            ("recovery", "Recovery", "offcard.recovery"),
            ("M_duct", "Duct M", "offcard.M_duct"),
            ("margin", "Margin", "offcard.margin"),
            ("regime", "Regime", "offcard.regime"))

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
        self.values, self.deltas = {}, {}
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
            if key == "regime":                       # words, no delta: use both columns
                grid.addWidget(value, r, 1, 1, 2)
            else:
                grid.addWidget(value, r, 1)
                grid.addWidget(delta, r, 2)
            self.values[key], self.deltas[key] = value, delta
        grid.setColumnStretch(1, 1)

    def show_point(self, design, off, regime):
        def put(key, text, delta=""):
            self.values[key].setText(text)
            self.deltas[key].setText(delta)

        if design is None or off is None:
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
        top.addWidget(self.chip, 0)
        top.addStretch(1)
        top.addWidget(self.badge, 0)
        header = QVBoxLayout()
        header.setContentsMargins(tokens.space(2), tokens.space(1), tokens.space(2), 0)
        header.setSpacing(4)
        header.addLayout(top)
        header.addWidget(self.slider)

        self.canvas = InletCanvas(state, mode="offdesign")
        self.charts = OffDesignCharts()
        self.card = OffDesignCard()
        self.card.setFixedWidth(tokens.space(27))
        strip = QWidget()
        strip.setObjectName("offDesignStrip")
        strip.setFixedHeight(tokens.OFFDESIGN_STRIP_H)
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
        for label in (self.charts.band_legend, self.charts.note_legend, self.charts.cfd_note):
            strip_layout.addWidget(label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.space(1))
        layout.addLayout(header)
        layout.addWidget(self.canvas, 1)
        layout.addWidget(strip)

        self.slider.value_changed.connect(self._from_slider)
        self.slider.slider.sliderPressed.connect(lambda: self.canvas.set_animations_enabled(False))
        self.slider.released.connect(lambda: self.canvas.set_animations_enabled(True))
        self.charts.cursor_moved.connect(self._from_chart)
        state.design_ready.connect(lambda *_: self._on_design())
        state.off_design_ready.connect(lambda *_: self._on_off_design())
        state.inputs_changed.connect(lambda *_: self._sync_slider())
        if state.design is not None:
            self._on_design()
            self._on_off_design()

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
        self.charts.set_data(d, self.state.sweep, (lo, hi))
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
        self.card.show_point(self.state.design, off, regime)
        if not self.slider.is_dragging():
            self.charts.set_cursor(self.state.off_design_mach())

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
