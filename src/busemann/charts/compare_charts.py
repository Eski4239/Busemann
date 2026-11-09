"""Compare tab off-design curves (M10): mass capture, total recovery and cowl margin against
M∞ for slot A (dashed) and slot B (solid) on shared axes, each with its own design-Mach line.
The curves come from each slot's off-design sweep (computed on a worker); nothing here calls
the core.
"""
import math

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import field_label
from . import model
from .offdesign_charts import LEFT_AXIS_W, _pen

CHARTS = (("capture", "Capture A0/Ac", "capture", "M"),
          ("recovery", "Recovery p0/p0∞", "rec_tot", "M"),
          ("margin", "Cowl margin (°)", "margin", "margin_M"))
SLOT_STYLE = {"A": ("wall", Qt.PenStyle.DashLine), "B": ("accent", Qt.PenStyle.SolidLine)}
LEGEND_TEXT = ("A (dashed) and B (solid): each design's own sweep; vertical lines mark "
               "each design Mach")


class CompareCharts(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        pg.setConfigOptions(antialias=True)
        self.plots, self.curves, self.design_lines = {}, {}, {}
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.space(1))
        tick_font = theme.mono_font(10)
        for key, title, _, _ in CHARTS:
            box = QVBoxLayout()
            box.setSpacing(2)
            label = field_label(title, f"label.chart_{key}")
            label.setWordWrap(True)
            box.addWidget(label)
            w = pg.PlotWidget(background=tokens.COLORS["surface"])
            w.setObjectName(f"compare_chart_{key}")
            w.setMinimumHeight(180)
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
            self.plots[key] = w
            box.addWidget(w, 1)
            row.addLayout(box, 1)
        self.plots["recovery"].setXLink(self.plots["capture"])
        self.plots["margin"].setXLink(self.plots["capture"])
        self.legend = QLabel(LEGEND_TEXT)
        self.legend.setObjectName("muted")
        self.legend.setWordWrap(True)
        self.legend.setToolTip(tip("compare.curves"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(row, 1)
        layout.addWidget(self.legend)

    def set_slot(self, slot, snapshot):
        """Draw (or remove) one slot's curves; snapshot None or without a sweep clears it."""
        for key, w in self.plots.items():
            item = w.getPlotItem()
            for it in (self.curves.pop((slot, key), None), self.design_lines.pop((slot, key),
                                                                                  None)):
                if it is not None:
                    item.removeItem(it)
        if snapshot is None or snapshot.sweep is None or snapshot.design is None:
            return
        s = model.series(snapshot.sweep)
        token, style = SLOT_STYLE[slot]
        M_d = snapshot.design.inputs.M
        for key, _, ykey, xkey in CHARTS:
            item = self.plots[key].getPlotItem()
            ys = [math.nan if y is None else y for y in s[ykey]]
            curve = item.plot(s[xkey], ys, pen=_pen(token, 2.0, style), connect="finite",
                              name=slot)
            curve.setZValue(10 if slot == "B" else 5)
            line = pg.InfiniteLine(pos=M_d, angle=90, movable=False,
                                   pen=_pen(token, 1.0, style, alpha=160))
            item.addItem(line, ignoreBounds=True)
            self.curves[(slot, key)], self.design_lines[(slot, key)] = curve, line

    def slot_data(self, slot, key):
        """(x, y) drawn for a slot on a chart, or None (tests)."""
        curve = self.curves.get((slot, key))
        return None if curve is None else curve.getData()
