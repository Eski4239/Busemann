"""Results panel (right, M8.2 declutter): a warnings banner, five compact KPI cards, the flow
regions table, warnings grouped by condition, the canvas selection and an Export button.

Only results live here: source citations and CFD comparisons are in the Verification tab,
the Explain popups and the exported notes. In the off-design view the cards show the values
at the slider Mach (no "Δ vs design" lines: the "At slider Mach" card has those).
"""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractScrollArea, QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from inletdesign import api
from inletdesign import units as _units

from ..crashlog import guarded
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import KpiCard, section_title
from . import format as fmt
from .rows import cowl_rows, region_rows, shock_rows
from .station_table import StationTable

SELECTION_HINT = "Click a region or shock on the canvas to inspect it."
LEVEL_ORDER = ("error", "warn", "info")
_ICON = {"error": ("alert-triangle", "error"), "warn": ("alert-triangle", "warn"),
         "info": ("info", "accent")}
TITLE_MAX = 56


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


def warning_title(text):
    """One-line title of a warning: up to the first ':' or '(' (or ' — '), capped."""
    cut = len(text)
    for mark in (":", " (", " — "):
        k = text.find(mark)
        if 0 < k < cut:
            cut = k
    title = text[:cut].strip()
    if len(title) > TITLE_MAX:
        title = title[:TITLE_MAX - 1].rstrip() + "…"
    return title[:1].upper() + title[1:]


def _total_text(kgps, width, system):
    value = _units.to_display(kgps, "mass_flow", system)
    w = _units.to_display(width, "length", system)
    return (f"total {fmt.sig(value, 4)} {_units.unit_label('mass_flow', system)} "
            f"through {fmt.sig(w, 4)} {_units.unit_label('length', system)}")


class WarningRow(QFrame):
    """A warning collapsed to a one-line title with a severity icon; click (or Enter /
    Space) expands the full text."""

    def __init__(self, level, text, parent=None):
        super().__init__(parent)
        self.setObjectName("warningItem")
        self.setProperty("level", level)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.level, self.text = level, text
        head_tip = f"{tip(f'notice.title.{level}')}\n{tip('notice.row')}"
        self.setToolTip(head_tip)
        v = QVBoxLayout(self)
        v.setContentsMargins(tokens.space(1), 5, tokens.space(1), 5)
        v.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(tokens.space(1))
        icon = QLabel()
        name, colour = _ICON[level]
        icon.setPixmap(theme.icon(name, colour, 16).pixmap(16, 16))
        icon.setToolTip(head_tip)
        self.head = QLabel(warning_title(text))
        self.head.setObjectName("warningHead")
        self.head.setWordWrap(True)
        self.head.setToolTip(head_tip)
        self.chevron = QLabel()
        self.chevron.setToolTip(head_tip)
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(self.head, 1)
        head.addWidget(self.chevron, 0, Qt.AlignmentFlag.AlignTop)
        self.body = QLabel(fmt.nbsp(text[:1].upper() + text[1:]))
        self.body.setObjectName("warningBody")
        self.body.setWordWrap(True)
        self.body.setToolTip(tip("notice.row"))
        self.body.hide()
        v.addLayout(head)
        v.addWidget(self.body)
        self._show_chevron()

    def _show_chevron(self):
        name = "chevron-down" if self.expanded() else "chevron-right"
        self.chevron.setPixmap(theme.icon(name, "text_muted", 14).pixmap(14, 14))

    def expanded(self):
        return not self.body.isHidden()

    def set_expanded(self, on):
        self.body.setVisible(on)
        self._show_chevron()

    def toggle(self):
        self.set_expanded(not self.expanded())

    @guarded()
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()
        super().mouseReleaseEvent(event)

    @guarded()
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.toggle()
            return
        super().keyPressEvent(event)


class WarningBanner(QFrame):
    """"⚠ N warnings — review before using these results" (wraps; click scrolls)."""

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("warningBanner")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tip("results.banner"))
        row = QHBoxLayout(self)
        row.setContentsMargins(tokens.space(1), 6, tokens.space(1), 6)
        row.setSpacing(tokens.space(1))
        icon = QLabel()
        icon.setPixmap(theme.icon("alert-triangle", "warn", 16).pixmap(16, 16))
        icon.setToolTip(self.toolTip())
        self.label = QLabel()
        self.label.setObjectName("warningBannerText")
        self.label.setWordWrap(True)
        self.label.setToolTip(self.toolTip())
        row.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        row.addWidget(self.label, 1)

    def setText(self, text):
        self.label.setText(text)

    def text(self):
        return self.label.text()

    def click(self):
        self.clicked.emit()

    @guarded()
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ResultsPanel(QWidget):
    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state

        self.banner = WarningBanner()
        self.banner.clicked.connect(self.scroll_to_warnings)
        self.banner.hide()

        self.cards = {
            "recovery_total": KpiCard("Total pressure recovery", "kpi.recovery_total",
                                      compact=True),
            "mass_capture": KpiCard("Mass capture", "kpi.mass_capture", compact=True),
            "mass_flow": KpiCard("Captured mass flow", "kpi.mass_flow", compact=True),
            "M_duct": KpiCard("M after terminal shock", "kpi.M_duct", compact=True),
            "cowl_margin": KpiCard("Cowl margin", "kpi.cowl_margin", compact=True),
        }

        self.warnings_box = QWidget()
        self.warnings_box.setObjectName("noticeCards")
        self._warnings_layout = QVBoxLayout(self.warnings_box)
        self._warnings_layout.setContentsMargins(0, 0, 0, 0)
        self._warnings_layout.setSpacing(4)
        self.warnings_box.hide()
        self.warning_rows = []         # WarningRow per warning, in display order
        self.notice_headers = []       # group headers

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2),
                                  tokens.space(2))
        layout.setSpacing(tokens.space(1))
        layout.addWidget(self.banner)
        self.title = section_title("Results", "section.results")
        layout.addWidget(self.title)
        for card in self.cards.values():
            layout.addWidget(card)
        layout.addSpacing(tokens.space(1))
        regions_head = QHBoxLayout()
        regions_head.setContentsMargins(0, 0, 0, 0)
        regions_head.addWidget(section_title("Flow regions", "section.stations"), 1)
        self.copy_button = QPushButton("Copy table")
        self.copy_button.setObjectName("linkButton")
        self.copy_button.setToolTip(tip("stations.copy"))
        self.copy_button.clicked.connect(self.copy_table)
        regions_head.addWidget(self.copy_button)
        layout.addLayout(regions_head)
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
        self.export_button = QPushButton("Export")
        self.export_button.setObjectName("exportButton")
        self.export_button.setToolTip(tip("results.export"))
        self.export_button.setIcon(theme.icon("chevron-down", "text", 14))
        layout.addSpacing(tokens.space(1))
        layout.addWidget(self.export_button)

        state.design_ready.connect(lambda *_: self.refresh())
        state.freestream_ready.connect(lambda *_: self.refresh())
        state.inputs_changed.connect(lambda *_: self.refresh())
        state.off_design_ready.connect(lambda *_: self.refresh())
        state.view_changed.connect(lambda *_: self.refresh())
        self._warnings_stale = False
        self._last_notices = None
        state.dragging_changed.connect(
            lambda dragging: None if dragging or not self._warnings_stale else self.refresh())
        self.refresh()

    def set_export_menu(self, menu):
        """The same actions as File ▸ Export (the menu is shared)."""
        self.export_button.setMenu(menu)

    def refresh(self):
        if self.state.active_view == "offdesign" and self.state.design is not None:
            self._show_off_design()
        else:
            self._show_design()
        if self.state.dragging and self.warning_rows:
            self._warnings_stale = True          # rebuilt when the drag ends
        else:
            self._warnings_stale = False
            self._set_warnings(self.state.notices())
        if self._selection[0] is not None:       # dimensional values follow the unit system
            self.show_selection(*self._selection)

    # --- cards ----------------------------------------------------------------------------
    def _mass_flow_card(self, mdot, total):
        system = self.state.inputs.units
        card = self.cards["mass_flow"]
        if mdot is None:
            card.clear()
            return
        card.set_value(fmt.sig(_units.to_display(mdot, "mass_flow_per_span", system), 4),
                       _units.unit_label("mass_flow_per_span", system),
                       None if total is None else
                       _total_text(total, self.state.inputs.inlet_width_m, system))

    def _margin_card(self, margin, sub):
        card = self.cards["cowl_margin"]
        if margin is None:
            card.set_value("—", "°", "subsonic flow at the lip: no cowl shock")
            return
        card.set_value(f"{margin:+.2f}", "°", sub)
        card.set_notes([("margin_state", "cowl shock detached" if margin < 0 else
                         "close to detachment" if margin < 2.0 else "attached",
                         "error" if margin < 0 else None, tip("kpi.cowl_margin"))])

    def _show_off_design(self):
        """KPIs of the frozen design at the slider Mach."""
        d, off = self.state.design, self.state.off_design
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
        cards["recovery_total"].set_notes(recovery_notes(
            off.recovery_total, off.M_inf, self.state.inputs.diffuser_recovery))
        cards["M_duct"].set_value(f"{off.M_post_terminal:.3f}", "",
                                  "behind the terminal normal shock" if has_terminal
                                  else "behind the last ramp shock")
        cards["mass_capture"].set_value(f"{off.mass_capture_ratio:.3f}", "A0/Ac",
                                        f"regime: {off.regime}")
        self._mass_flow_card(self.state.captured_mass_flow(True),
                             self.state.total_mass_flow(at_off_design=True))
        self._margin_card(off.cowl_margin_deg, "at the lip, local flow")
        for card in cards.values():
            card.set_delta(None)

    def _show_design(self):
        d = self.state.design
        self.title.setText(theme.caps("Results"))
        for card in self.cards.values():
            card.set_delta(None)
        if d is None:
            for card in self.cards.values():
                card.clear()
            return
        subsonic = d.M_post_terminal < 1.0 and not any(r.beta_deg == 90.0 for r in d.regions)
        self.cards["recovery_total"].set_value(
            f"{d.recovery_total:.4f}", "p0/p0∞",
            "no terminal shock (subsonic)" if subsonic else "incl. terminal normal shock")
        self.cards["recovery_total"].set_badge("constrained" if d.constrained else None)
        self.cards["recovery_total"].badge.setToolTip(
            f"Optimum angles limited to a cowl angle of "
            f"{d.inputs.max_cowl_angle_deg or 0:.1f}°" if d.constrained else "")
        notes = recovery_notes(d.recovery_total, d.inputs.M, self.state.inputs.diffuser_recovery)
        if d.inputs.method == "custom" and self.state.gap is not None:
            notes.append(gap_note(self.state.gap[0], d.inputs.n_ramps))
        self.cards["recovery_total"].set_notes(notes)
        self.cards["M_duct"].set_value(f"{d.M_post_terminal:.3f}", "",
                                       "behind the last ramp shock" if subsonic
                                       else "behind the terminal normal shock")
        self.cards["mass_capture"].set_value(f"{d.mass_capture:.3f}", "A0/Ac",
                                             "shock-on-lip design point")
        self._mass_flow_card(self.state.captured_mass_flow(), self.state.total_mass_flow())
        self._margin_card(d.cowl_margin_deg, "θmax(M∞) − cowl turn")

    # --- warnings --------------------------------------------------------------------------
    def group_caption(self, group):
        if group == "design":
            M = self.state.design.inputs.M if self.state.design else self.state.inputs.mach
            return f"At the design point (M∞ {M:.2f})"
        return f"At M∞ {self.state.off_design_mach():.2f} (off-design)"

    def _set_warnings(self, notices):
        """notices: [(group, level, text, detail)]; one header per group, then one
        collapsible row per warning (most severe first). Details (sources, CFD) are not
        shown here: they are in the Verification tab."""
        key = tuple((g, lv, t) for g, lv, t, _ in notices) + (self.group_caption("off"),)
        if key == self._last_notices:
            return                                # unchanged: keep the expanded state
        self._last_notices = key
        expanded = {row.text for row in self.warning_rows if row.expanded()}
        for w in self.warning_rows + self.notice_headers:
            w.deleteLater()
        self.warning_rows, self.notice_headers = [], []
        for group in ("design", "off"):
            items = [n for n in notices if n[0] == group]
            if not items:
                continue
            header = QLabel(self.group_caption(group))
            header.setObjectName("noticeGroup")
            header.setToolTip(tip(f"notice.group.{group}"))
            self._warnings_layout.addWidget(header)
            self.notice_headers.append(header)
            for level in LEVEL_ORDER:
                for _, lv, text, _detail in items:
                    if lv != level:
                        continue
                    row = WarningRow(level, text)
                    row.setProperty("group", group)
                    row.set_expanded(text in expanded)
                    self._warnings_layout.addWidget(row)
                    self.warning_rows.append(row)
        self.warnings_box.setVisible(bool(notices))
        levels = [lv for lv in LEVEL_ORDER if any(n_[1] == lv for n_ in notices)]
        self.warnings_box.setProperty("level", levels[0] if levels else None)   # worst
        n = sum(1 for _, lv, _, _ in notices if lv in ("warn", "error"))
        self.banner.setText(f"{n} warning{'s' if n != 1 else ''} — review before using "
                            "these results")
        self.banner.setVisible(n > 0)

    def scroll_to_warnings(self):
        w = self.parentWidget()
        while w is not None and not isinstance(w, QAbstractScrollArea):
            w = w.parentWidget()
        if w is not None and hasattr(w, "ensureWidgetVisible"):
            w.ensureWidgetVisible(self.warnings_box, 0, tokens.space(2))
        if self.warning_rows:
            self.warning_rows[0].setFocus()

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

    # --- test helpers ----------------------------------------------------------------------
    def warning_texts(self):
        """Full warning texts as shown when expanded (first letter capitalised)."""
        return [row.text[:1].upper() + row.text[1:] for row in self.warning_rows]

    def warning_titles(self):
        return [row.head.text() for row in self.warning_rows]

    def warning_levels(self):
        return [row.level for row in self.warning_rows]

    def card_levels(self, group=None):
        """Distinct severities shown (per group), most severe first."""
        levels = [row.level for row in self.warning_rows
                  if group is None or row.property("group") == group]
        return [lv for lv in LEVEL_ORDER if lv in levels]

    def notice_groups(self):
        return [h.text() for h in self.notice_headers]
