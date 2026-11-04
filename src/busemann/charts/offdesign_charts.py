"""Off-design chart strip (spec 4.5): mass capture, recovery and cowl margin against M_inf.

Three pyqtgraph plots with a linked M_inf axis, shaded regime bands, a design-point line,
a movable cursor kept in sync with the off-design slider, and the Phase 3d CFD points
(hollow circles) when the design is the validated case.
"""
import math

import pyqtgraph as pg
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import field_label
from . import model

UPPER_BOUND_TEXT = "upper bound — cowl shock not modelled"
FACE_TEXT = "engine face (estimate): total × diffuser {d:.3f}"
MIL_TEXT = ("MIL-E-5008B — compare with the engine-face estimate (dashed), not the inviscid "
            "total")
DEMAND_TEXT = ("fixed demand (engine matching not modelled): A0/Ac needed for {mdot} at each "
               "M∞ (above the model: shortfall)")
BAND_STYLE = model.BAND_STYLE
CHARTS = (("capture", "Capture A0/Ac", ""),
          ("recovery", "Recovery p0/p0∞", ""),
          ("margin", "Cowl margin", "°"))
TITLE_TIPS = {"capture": "label.chart_capture", "recovery": "label.chart_recovery",
              "margin": "label.chart_margin"}
ENTRY_SEP = "&nbsp;&nbsp; "   # ends in an ordinary space: the only place a row may wrap
LEFT_AXIS_W = 34          # px, same on every chart so the linked M∞ axes line up


def _key(token, glyph):
    return f'<span style="color:{tokens.COLORS[token]}">{glyph}</span>'


def _entry(marker_html, text):
    """(html, plain text) of one legend entry; its spaces are non-breaking."""
    glued = text.replace(" ", "\u00a0")
    return f"{marker_html}&nbsp;{glued}", glued


def _swatch(token, alpha):
    c = _qc(token, alpha)
    return (f'<span style="background-color:rgba({c.red()},{c.green()},{c.blue()},'
            f'{min(1.0, 3 * alpha / 255):.2f})">&nbsp;&nbsp;&nbsp;&nbsp;</span>')


def _qc(token, alpha=255):
    c = QColor(tokens.COLORS[token])
    c.setAlpha(alpha)
    return c


def _pen(token, width=1.5, style=Qt.PenStyle.SolidLine, alpha=255):
    pen = QPen(_qc(token, alpha), width)
    pen.setStyle(style)
    pen.setCosmetic(True)
    return pen


class OffDesignCharts(QWidget):
    cursor_moved = Signal(float)          # M_inf picked on a chart (cursor drag or click)

    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self.plots = {}
        self.legends = {}
        self.cursors = {}
        self.curves = {}
        self.band_items = []
        self.band_labels = []
        self._band_parts, self.footer_parts = [], []
        self.bands = []
        self.cfd_items = []
        self.cfd_visible = False
        self.range = (1.2, 4.5)
        self._guard = False
        self._diffuser = self._demand = self._mdot_text = None

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.space(1))
        tick_font = theme.mono_font(10)
        for key, title, unit in CHARTS:
            box = QVBoxLayout()
            box.setSpacing(2)
            title_label = field_label(f"{title} ({unit})" if unit else title, TITLE_TIPS[key])
            title_label.setWordWrap(True)             # narrow centre column (drawer open)
            box.addWidget(title_label)
            legend = QLabel()
            legend.setObjectName("chartLegend")
            legend.setTextFormat(Qt.TextFormat.RichText)
            legend.setWordWrap(True)          # one line normally; wraps at minimum width
            legend.setToolTip(tip(f"chart.legend.{key}"))
            self.legends[key] = legend
            box.addWidget(legend)
            w = pg.PlotWidget(background=tokens.COLORS["surface"])
            w.setObjectName(f"chart_{key}")
            w.setMinimumHeight(tokens.space(17))
            item = w.getPlotItem()
            item.setMenuEnabled(False)
            item.hideButtons()
            item.setMouseEnabled(x=False, y=False)
            item.showGrid(x=True, y=True, alpha=0.12)
            for name in ("left", "bottom"):
                axis = item.getAxis(name)
                axis.setPen(_pen("border", 1))
                axis.setTextPen(_pen("text_muted", 1))
                axis.setTickFont(tick_font)
            item.getAxis("left").setWidth(LEFT_AXIS_W)
            item.getAxis("left").setToolTip(tip(f"chart.axis.{key}"))
            item.getAxis("bottom").setToolTip(tip("chart.axis.mach"))
            item.getAxis("bottom").setLabel("M∞", color=tokens.COLORS["text_muted"])
            cursor = pg.InfiniteLine(angle=90, movable=True, pen=_pen("accent", 1.5),
                                     hoverPen=_pen("accent", 3))
            cursor.setZValue(20)
            item.addItem(cursor, ignoreBounds=True)
            cursor.sigPositionChanged.connect(lambda line, k=key: self._on_cursor_drag(k))
            w.scene().sigMouseClicked.connect(lambda ev, k=key: self._on_click(k, ev))
            self.plots[key], self.cursors[key] = w, cursor
            box.addWidget(w, 1)
            row.addLayout(box, 1)
        self.plots["recovery"].setXLink(self.plots["capture"])
        self.plots["margin"].setXLink(self.plots["capture"])

        # Two footer rows (regime bands; notes). Inside an entry every space is a
        # non-breaking space, so a row can wrap only between entries, never mid-phrase.
        self.band_legend = QLabel()
        self.note_legend = QLabel()
        for label in (self.band_legend, self.note_legend):
            label.setObjectName("chartLegend")
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
        self.band_legend.setToolTip(tip("chart.legend.bands"))
        self.note_legend.setToolTip(tip("chart.legend.notes"))
        self.cfd_note = QLabel(model.CFD_NOTE)
        self.cfd_note.setToolTip(tip("chart.cfd_note"))
        self.cfd_note.setObjectName("muted")
        self.cfd_note.setWordWrap(True)
        self.cfd_note.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row, 1)
        layout.addWidget(self.band_legend)
        layout.addWidget(self.note_legend)
        layout.addWidget(self.cfd_note)

    # --- data ---------------------------------------------------------------------------
    def clear(self):
        for w in self.plots.values():
            item = w.getPlotItem()
            for it in list(item.items):
                if it not in self.cursors.values():
                    item.removeItem(it)
        self.curves, self.band_items, self.bands, self.cfd_items = {}, [], [], []
        self.band_labels = []                 # band legend entries, in order
        self._band_parts, self.footer_parts = [], []
        self.legend_entries = []              # (row, entry text with NBSPs), for tests
        self.band_legend.setText("")
        self.note_legend.setText("")
        self.cfd_visible = False

    def set_data(self, design, sweep, m_range, diffuser=None, demand=None, mdot_text=None):
        """Rebuild every chart for a design and its sweep over m_range = (min, max).
        diffuser: engine-face curve (recovery x diffuser) and the MIL-E-5008B line;
        demand: (A0/Ac)_demand per sweep Mach (engine sizing), drawn on the capture chart.
        Never emits cursor_moved (cursor bounds may move the cursor lines)."""
        self._guard = True
        self._diffuser, self._demand, self._mdot_text = diffuser, demand, mdot_text
        try:
            self._set_data(design, sweep, m_range)
        finally:
            self._guard = False

    def _set_data(self, design, sweep, m_range):
        self.clear()
        if design is None or sweep is None:
            return
        self.range = m_range
        lo, hi = m_range
        s = model.series(sweep)
        M_d = design.inputs.M
        below = [k for k, M in enumerate(s["M"]) if M <= M_d + 1e-12]
        above = [k for k, M in enumerate(s["M"]) if M >= M_d - 1e-12]

        def pick(values, idx):
            return [s["M"][k] for k in idx], [values[k] for k in idx]

        cap, rec, mar = (self.plots[k].getPlotItem() for k in ("capture", "recovery", "margin"))

        self.curves["capture"] = cap.plot(s["M"], s["capture"], pen=_pen("accent", 2))
        for key, token, width, name in (("rec_tot", "accent", 2, "total"),
                                        ("rec_obl", "text_muted", 1.5, "oblique only")):
            self.curves[key] = rec.plot(*pick(s[key], below), pen=_pen(token, width))
            self.curves[key + "_hi"] = rec.plot(
                *pick(s[key], above), pen=_pen(token, width, Qt.PenStyle.DotLine))
        if self._diffuser is not None:
            self.curves["rec_face"] = rec.plot(
                s["M"], model.engine_face(s["rec_tot"], self._diffuser),
                pen=_pen("accent", 1.2, Qt.PenStyle.DashLine))
            self.curves["mil"] = rec.plot(*model.mil_series(lo, hi),
                                          pen=_pen("wall", 1.2, Qt.PenStyle.DashDotLine))
        if self._demand is not None:
            self.curves["demand"] = cap.plot(*model.demand_series(sweep.machs, self._demand),
                                             pen=_pen("warn", 1.5, Qt.PenStyle.DashLine))
        self.curves["margin"] = mar.plot(s["margin_M"], s["margin"], pen=_pen("accent", 2),
                                         connect="finite")
        mar.addItem(pg.InfiniteLine(pos=0.0, angle=0,
                                    pen=_pen("error", 1, Qt.PenStyle.DashLine)))

        for w in self.plots.values():
            item = w.getPlotItem()
            line = pg.InfiniteLine(pos=M_d, angle=90, pen=_pen("text_muted", 1,
                                                                Qt.PenStyle.DashLine))
            line.setToolTip(f"Design point M {M_d:.2f}")
            item.addItem(line, ignoreBounds=True)
            item.setXRange(lo, hi, padding=0.01)
            self.cursors[w.objectName().removeprefix("chart_")].setBounds((lo, hi))
        cap.setYRange(0.0, 1.05, padding=0)

        self.bands = model.regime_bands(design, sweep, lo, hi)
        self._draw_bands()
        self._draw_cfd(design)
        self._set_legends(design, bool(above))

    def _set_legends(self, design, overspeed):
        """One-line legends per chart; the long notes go in the full-width footer."""
        cfd = f" &nbsp; {_key('text', '○')} CFD" if self.cfd_visible else ""
        # one line per chart; the engine-face, MIL and demand curves are named in the footer
        self.legends["capture"].setText(f"{_key('accent', '━')} model{cfd}")
        self.legends["recovery"].setText(
            f"{_key('accent', '━')} total &nbsp; {_key('text_muted', '━')} oblique{cfd}")
        wedge = design.inputs.cowl_wedge_deg or 0.0
        self.legends["margin"].setText(
            f"{_key('accent', '━')} at the lip, wedge {wedge:g}° &nbsp; "
            f"{_key('error', '╌')} 0")
        notes = []
        if overspeed:
            notes.append(_entry(_key("text_muted", "┅"), f"above design: {UPPER_BOUND_TEXT}"))
        if self._diffuser is not None:
            notes.append(_entry(_key("accent", "╌"), FACE_TEXT.format(d=self._diffuser)))
            notes.append(_entry(_key("wall", "─·"), MIL_TEXT))
        if self._demand:
            notes.append(_entry(_key("warn", "╌"), DEMAND_TEXT.format(mdot=self._mdot_text)))
        if self.cfd_visible:
            notes.append(_entry(_key("text", "○"), "CFD (Fluent, inviscid)"))
        self.footer_parts = [text for _, text in self._band_parts + notes]
        self.legend_entries = ([("bands", t) for _, t in self._band_parts]
                               + [("notes", t) for _, t in notes])
        self.band_legend.setText(ENTRY_SEP.join(html for html, _ in self._band_parts))
        self.note_legend.setText(ENTRY_SEP.join(html for html, _ in notes))

    def _draw_bands(self):
        """Shaded bands on every chart; their labels go in the legend row below."""
        for band in self.bands:
            token, alpha = BAND_STYLE[band.kind]
            for w in self.plots.values():
                region = pg.LinearRegionItem((band.lo, band.hi), movable=False,
                                             brush=_qc(token, alpha), pen=_pen(token, 0, alpha=0))
                region.setZValue(-10)
                region.setToolTip(band.label)
                w.getPlotItem().addItem(region, ignoreBounds=True)
                self.band_items.append(region)
        seen, parts = set(), []
        for band in self.bands:                 # one legend entry per label
            if band.label in seen:
                continue
            seen.add(band.label)
            self.band_labels.append(band.label)
            parts.append(_entry(_swatch(*BAND_STYLE[band.kind]), band.label))
        self._band_parts = parts

    def _draw_cfd(self, design):
        self.cfd_visible = model.cfd_applies(design)
        note = model.cfd_note(design)
        self.cfd_note.setText(note or "")
        self.cfd_note.setVisible(note is not None)
        if not self.cfd_visible:
            return
        data = model.load_cfd()
        for key, field in (("capture", "capture"), ("recovery", "recovery")):
            spots = [dict(pos=(p["M"], p[field]),
                          data=f"{data['source']}\nM∞ {p['M']:.2f}: {field} {p[field]:.4g}"
                               + (" (before the terminal shock)" if field == "recovery" else "")
                               + f"\n{p['note']}")
                     for p in data["points"]]
            scatter = pg.ScatterPlotItem(
                spots=spots, symbol="o", size=9, pen=_pen("text", 1.5),
                brush=pg.mkBrush(0, 0, 0, 0), hoverable=True, hoverSize=11,
                tip=lambda x, y, data: data, name="CFD (Fluent, inviscid)")
            scatter.setZValue(18)
            self.plots[key].getPlotItem().addItem(scatter)
            self.cfd_items.append(scatter)

    # --- cursor ------------------------------------------------------------------------
    def cursor(self):
        return self.cursors["capture"].value()

    def set_cursor(self, M):
        """Move every chart's cursor to M (no cursor_moved emission)."""
        self._guard = True
        try:
            for line in self.cursors.values():
                line.setValue(M)
        finally:
            self._guard = False

    def _on_cursor_drag(self, key):
        if self._guard:
            return
        M = self.cursors[key].value()
        self.set_cursor(M)
        self.cursor_moved.emit(float(M))

    def _on_click(self, key, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        vb = self.plots[key].getPlotItem().getViewBox()
        if not vb.sceneBoundingRect().contains(event.scenePos()):
            return
        M = vb.mapSceneToView(event.scenePos()).x()
        lo, hi = self.range
        M = min(max(M, lo), hi)
        if math.isfinite(M):
            self.set_cursor(M)
            self.cursor_moved.emit(float(M))
