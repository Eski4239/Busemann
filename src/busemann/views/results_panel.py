"""Results panel (right): KPI cards, warnings, and the canvas selection. Region table in M4."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from inletdesign import api
from inletdesign import units as _units

from ..theme import qt as theme
from ..theme import tokens
from ..widgets import KpiCard, section_title
from . import format as fmt
from .rows import cowl_rows, region_rows, shock_rows
from .station_table import StationTable
from ..tooltips import tip

SELECTION_HINT = "Click a region or shock on the canvas to inspect it."

# One card per severity, most severe first: level -> (title, icon, colour token)
NOTICE_LEVELS = {
    "error": ("Errors", "alert-triangle", "error"),
    "warn": ("Warnings", "alert-triangle", "warn"),
    "info": ("Notes", "info", "accent"),
}
_ROW_NAMES = {"error": "errorRow", "warn": "warningRow", "info": "infoRow"}


def recovery_notes(recovery, M, diffuser):
    """KPI lines for the recovery card: engine-face estimate and the MIL-E-5008B comparison
    (the MIL line applies to the engine face, not to the inviscid value)."""
    face = recovery * diffuser
    mil = api.mil_recovery(M)
    pct = 100.0 * (face / mil - 1.0)
    side = "above" if pct >= 0 else "below"
    return [
        ("engine_face", f"engine face ≈ {face:.4f} (× {diffuser:.3f} diffuser, estimate)",
         None, tip("kpi.engine_face")),
        ("mil", f"Engine-face estimate {abs(pct):.1f} % {side} MIL-E-5008B ({mil:.4f})",
         "ok" if pct >= 0 else "error", tip("kpi.mil")),
    ]


def gap_note(gap_pct, n_ramps):
    """'Recovery 1.3 % below the Oswatitsch optimum for 2 ramps'."""
    ramps = f"{n_ramps} ramp" + ("s" if n_ramps != 1 else "")
    side = "below" if gap_pct >= 0 else "above"
    return ("gap", f"Recovery {abs(gap_pct):.1f} % {side} the Oswatitsch optimum for {ramps}",
            None, tip("kpi.gap"))


def _total_text(kgps, width, system):
    value = _units.to_display(kgps, "mass_flow", system)
    w = _units.to_display(width, "length", system)
    return (f"total {fmt.sig(value, 4)} {_units.unit_label('mass_flow', system)} "
            f"through {fmt.sig(w, 4)} {_units.unit_label('length', system)}")


class ResultsPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        self.cards = {
            "recovery_total": KpiCard("Total pressure recovery", "kpi.recovery_total"),
            "recovery_oblique": KpiCard("Oblique-only recovery", "kpi.recovery_oblique"),
            "M_duct": KpiCard("Duct Mach number", "kpi.M_duct"),
            "mass_capture": KpiCard("Mass capture", "kpi.mass_capture"),
            "mass_flow": KpiCard("Captured mass flow", "kpi.mass_flow"),
        }

        # Container of the notice cards (one per severity); its "level" is the worst one.
        self.warnings_box = QWidget()
        self.warnings_box.setObjectName("noticeCards")
        self._warnings_layout = QVBoxLayout(self.warnings_box)
        self._warnings_layout.setContentsMargins(0, 0, 0, 0)
        self._warnings_layout.setSpacing(tokens.space(1))
        self.warnings_box.hide()
        self._warning_labels = []      # row widgets, in display order
        self.notice_cards = []         # QFrame per shown severity, in display order
        self.notice_headers = []       # group sub-headers ("Design point", "At M∞ …")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2), tokens.space(2))
        layout.setSpacing(tokens.space(1))
        self.title = section_title("Results", "section.results")
        layout.addWidget(self.title)
        for card in self.cards.values():
            layout.addWidget(card)
        layout.addSpacing(tokens.space(1))
        stations_head = QHBoxLayout()
        stations_head.setContentsMargins(0, 0, 0, 0)
        stations_head.addWidget(section_title("Stations", "section.stations"), 1)
        self.copy_button = QPushButton("Copy table")
        self.copy_button.setObjectName("linkButton")
        self.copy_button.setToolTip(tip("stations.copy"))
        self.copy_button.clicked.connect(self.copy_table)
        stations_head.addWidget(self.copy_button)
        layout.addLayout(stations_head)
        self.station_table = StationTable()
        self.station_table.setToolTip(tip("stations.table"))
        layout.addWidget(self.station_table)
        layout.addSpacing(tokens.space(1))
        layout.addWidget(self.warnings_box)
        layout.addSpacing(tokens.space(1))
        layout.addWidget(section_title("Selection", "section.selection"))
        self.selection_title = QLabel(SELECTION_HINT)
        self.selection_title.setObjectName("selectionHint")
        self.selection_title.setToolTip(tip("selection.hint"))
        self.selection_title.setWordWrap(True)
        self.selection_box = QWidget()
        self._selection_grid = QGridLayout(self.selection_box)
        self._selection_grid.setContentsMargins(0, 0, 0, 0)
        self._selection_grid.setHorizontalSpacing(tokens.space(1))
        self._selection_grid.setVerticalSpacing(4)
        self._selection_grid.setColumnStretch(1, 1)
        self._selection_widgets = []
        self.selection_values = {}
        self._selection = (None, None, None)
        layout.addWidget(self.selection_title)
        layout.addWidget(self.selection_box)
        layout.addStretch(1)

        state.design_ready.connect(lambda *_: self.refresh())
        state.freestream_ready.connect(lambda *_: self.refresh())
        state.inputs_changed.connect(lambda *_: self.refresh())
        state.off_design_ready.connect(lambda *_: self.refresh())
        state.view_changed.connect(lambda *_: self.refresh())
        self._warnings_stale = False
        state.dragging_changed.connect(
            lambda dragging: None if dragging or not self._warnings_stale else self.refresh())
        self.refresh()

    def refresh(self):
        if self.state.active_view == "offdesign" and self.state.design is not None:
            self._show_off_design()
        else:
            self._show_design()
        if self.state.dragging and self.notice_cards:
            self._warnings_stale = True          # rebuilt when the slider drag ends
        else:
            self._warnings_stale = False
            self._set_warnings(self.state.notices())
        if self._selection[0] is not None:       # dimensional values follow the unit system
            self.show_selection(*self._selection)

    def _show_off_design(self):
        """KPIs of the frozen design at the slider Mach, each with its change from design."""
        d, off = self.state.design, self.state.off_design
        system = self.state.inputs.units
        M = self.state.off_design_mach()
        self.title.setText(theme.caps(f"Results at M∞ {M:.2f}"))
        if off is None:
            reason = "no off-design result at this Mach"
            if self.state.off_design_error and "shock detached" in self.state.off_design_error:
                reason = "a ramp shock is detached at this Mach"
            for card in self.cards.values():
                card.clear(sub=reason)
            return
        has_terminal = any(s.kind == "normal" for s in off.shock_states)
        cards = self.cards
        cards["recovery_total"].set_value(
            f"{off.recovery_total:.4f}", "p0/p0∞",
            "incl. terminal normal shock" if has_terminal else "no terminal shock (subsonic)")
        cards["recovery_total"].set_badge(None)
        cards["recovery_total"].set_delta(f"{off.recovery_total - d.recovery_total:+.4f}")
        cards["recovery_total"].set_notes(recovery_notes(
            off.recovery_total, off.M_inf, self.state.inputs.diffuser_recovery))
        cards["recovery_oblique"].set_value(f"{off.recovery_oblique:.4f}", "p0/p0∞",
                                            f"{d.inputs.n_ramps} oblique shock(s)")
        cards["recovery_oblique"].set_delta(f"{off.recovery_oblique - d.recovery_oblique:+.4f}")
        cards["M_duct"].set_value(f"{off.M_post_terminal:.3f}", "",
                                  "behind terminal normal shock" if has_terminal
                                  else "behind last ramp shock")
        cards["M_duct"].set_delta(f"{off.M_post_terminal - d.M_post_terminal:+.3f}")
        cards["mass_capture"].set_value(f"{off.mass_capture_ratio:.3f}", "A0/Ac",
                                        f"regime: {off.regime}")
        cards["mass_capture"].set_delta(f"{off.mass_capture_ratio - d.mass_capture:+.3f}")
        mdot, mdot_design = (self.state.captured_mass_flow(True),
                             self.state.captured_mass_flow())
        if mdot is None:
            cards["mass_flow"].clear()
        else:
            unit = _units.unit_label("mass_flow_per_span", system)
            cards["mass_flow"].set_value(
                fmt.sig(_units.to_display(mdot, "mass_flow_per_span", system), 4), unit)
            total = self.state.total_mass_flow(at_off_design=True)
            if total is not None:
                cards["mass_flow"].sub_label.setText(
                    _total_text(total, self.state.inputs.inlet_width_m, system))
                cards["mass_flow"].sub_label.show()
            if mdot_design is not None:
                diff = _units.to_display(mdot - mdot_design, "mass_flow_per_span", system)
                cards["mass_flow"].set_delta(f"{diff:+.4g} {unit}")

    def _show_design(self):
        d = self.state.design
        system = self.state.inputs.units
        self.title.setText(theme.caps("Results"))
        for card in self.cards.values():
            card.set_delta(None)
        if d is None:
            for card in self.cards.values():
                card.clear()
        else:
            subsonic = d.M_post_terminal < 1.0 and not any(r.beta_deg == 90.0 for r in d.regions)
            self.cards["recovery_total"].set_value(
                f"{d.recovery_total:.4f}", "p0/p0∞",
                "no terminal shock (subsonic)" if subsonic else "incl. terminal normal shock")
            self.cards["recovery_total"].set_badge("constrained" if d.constrained else None)
            self.cards["recovery_total"].badge.setToolTip(
                f"Oswatitsch optimum limited to a cowl angle of "
                f"{d.inputs.max_cowl_angle_deg or 0:.1f}°" if d.constrained else "")
            notes = recovery_notes(d.recovery_total, d.inputs.M,
                                   self.state.inputs.diffuser_recovery)
            if d.inputs.method == "custom" and self.state.gap is not None:
                notes.append(gap_note(self.state.gap[0], d.inputs.n_ramps))
            self.cards["recovery_total"].set_notes(notes)
            self.cards["recovery_oblique"].set_value(
                f"{d.recovery_oblique:.4f}", "p0/p0∞", f"{d.inputs.n_ramps} oblique shock(s)")
            self.cards["M_duct"].set_value(f"{d.M_post_terminal:.3f}", "",
                                           "behind last ramp shock" if subsonic
                                           else "behind terminal normal shock")
            self.cards["mass_capture"].set_value(f"{d.mass_capture:.3f}", "A0/Ac",
                                                 "shock-on-lip design point")
        mdot = self.state.captured_mass_flow()
        if mdot is None:
            self.cards["mass_flow"].clear()
        else:
            total = self.state.total_mass_flow()
            self.cards["mass_flow"].set_value(
                fmt.sig(_units.to_display(mdot, "mass_flow_per_span", system), 4),
                _units.unit_label("mass_flow_per_span", system),
                None if total is None else
                _total_text(total, self.state.inputs.inlet_width_m, system))

    def _set_warnings(self, notices):
        """notices: [(group, level, text, detail)]. Groups "design" ("Design point") and
        "off" ("At M∞ X.XX"), each with a sub-header and one card per level, most severe
        first. detail becomes the row tooltip."""
        for w in self.notice_cards + self.notice_headers:
            w.deleteLater()
        self.notice_cards, self.notice_headers, self._warning_labels = [], [], []
        levels = [lv for lv in NOTICE_LEVELS if any(n[1] == lv for n in notices)]
        self.warnings_box.setProperty("level", levels[0] if levels else None)
        groups = [("design", "Design point"),
                  ("off", f"At M∞ {self.state.off_design_mach():.2f}")]
        for group, caption in groups:
            items = [n[1:] for n in notices if n[0] == group]
            if not items:
                continue
            header = QLabel(caption)
            header.setObjectName("noticeGroup")
            header.setToolTip(tip(f"notice.group.{group}"))
            self._warnings_layout.addWidget(header)
            self.notice_headers.append(header)
            self._add_notice_cards(items, group)
        self.warnings_box.setVisible(bool(notices))

    def _add_notice_cards(self, notices, group):
        """notices: [(level, text, detail)] of one group: one card per level."""
        shown = [lv for lv in NOTICE_LEVELS if any(n[0] == lv for n in notices)]
        for level in shown:
            title, icon_name, colour = NOTICE_LEVELS[level]
            items = [n for n in notices if n[0] == level]
            card = QFrame()
            card.setObjectName("noticeCard")
            card.setProperty("level", level)
            card.setProperty("group", group)
            v = QVBoxLayout(card)
            v.setContentsMargins(tokens.space(1) + 4, tokens.space(1), tokens.space(1) + 4,
                                 tokens.space(1))
            v.setSpacing(tokens.space(1) // 2)
            head = QWidget()
            hh = QHBoxLayout(head)
            hh.setContentsMargins(0, 0, 0, 0)
            hh.setSpacing(tokens.space(1))
            icon = QLabel()
            icon.setPixmap(theme.icon(icon_name, colour, 16).pixmap(16, 16))
            caption = QLabel(f"{title} ({len(items)})")
            caption.setObjectName("noticeTitle")
            caption.setToolTip(tip(f"notice.title.{level}"))
            caption.setProperty("level", level)
            hh.addWidget(icon)
            hh.addWidget(caption, 1)
            v.addWidget(head)
            for _, text, detail in items:
                label = QLabel(fmt.nbsp(text[0].upper() + text[1:]))
                label.setObjectName(_ROW_NAMES[level])
                label.setProperty("level", level)
                label.setWordWrap(True)
                label.setToolTip(detail or tip("notice.row"))
                v.addWidget(label)
                self._warning_labels.append(label)
            self._warnings_layout.addWidget(card)
            self.notice_cards.append(card)

    def copy_table(self):
        QApplication.clipboard().setText(self.station_table.to_tsv())

    # --- canvas selection ------------------------------------------------------------------
    def show_selection(self, kind, index, payload):
        self._selection = (kind, index, payload)
        self.station_table.select_row(index if kind == "region" else None)
        for w in self._selection_widgets:
            w.deleteLater()
        self._selection_widgets = []
        self.selection_values = {}
        if kind is None or payload is None:
            self.selection_title.setObjectName("selectionHint")
            self.selection_title.setText(SELECTION_HINT)
            self.selection_title.setToolTip(tip("selection.hint"))
            self._repolish(self.selection_title)
            return
        if kind == "region":
            rows = region_rows(payload, self.state.freestream, self.state.inputs.units)
            title = payload.name
        elif kind == "cowl":
            rows, title = cowl_rows(payload), "cowl"
        else:
            rows, title = shock_rows(payload), payload.name
        self.selection_title.setObjectName("hoverTitle")
        self.selection_title.setToolTip(tip("selection.title"))
        self.selection_title.setText(title[:1].upper() + title[1:])
        self._repolish(self.selection_title)
        for r, (key, label, value, text, unit) in enumerate(rows):
            self.selection_values[key] = value
            name = QLabel(label)
            name.setObjectName("readoutLabel")
            val = QLabel(text)
            val.setObjectName("readoutValue")
            val.setFont(theme.mono_font())
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            un = QLabel(unit)
            un.setObjectName("readoutUnit")
            un.setFont(theme.mono_font(tokens.SIZE_LABEL))
            un.setMinimumWidth(tokens.space(7))
            for c, w in enumerate((name, val, un)):
                w.setToolTip(tip(f"row.{key}"))
                self._selection_grid.addWidget(w, r, c)
                self._selection_widgets.append(w)

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def warning_texts(self):
        return [label.text().replace("\u00a0", " ") for label in self._warning_labels]

    def warning_levels(self):
        return [label.property("level") for label in self._warning_labels]

    def card_levels(self, group=None):
        return [card.property("level") for card in self.notice_cards
                if group is None or card.property("group") == group]

    def notice_groups(self):
        return [h.text() for h in self.notice_headers]

    @staticmethod
    def _row_label(row):
        return row
