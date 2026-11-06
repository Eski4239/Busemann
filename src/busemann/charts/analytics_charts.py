"""Analytics trade-study charts (M9a): one pyqtgraph plot with named series, direct end
labels instead of a legend box, a current-design ring, an optional vertical limit line,
nearest-point hover tooltips and click-to-select. Styled like the off-design charts."""
import math

import pyqtgraph as pg
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import QLabel, QToolTip, QVBoxLayout, QWidget

from ..crashlog import guarded
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import field_label
from .offdesign_charts import LEFT_AXIS_W, _pen, _qc

PICK_PX = 8.0             # px: hover / click radius around a point
# ramp count -> colour: a sequential blue ramp (more ramps, darker); 0 (normal shock) muted
N_COLORS = {0: tokens.COLORS["text_muted"], 1: "#93B4F2", 2: "#5B8DEF",
            3: tokens.COLORS["accent"], 4: "#1E3A8A"}
SPECIAL = {"isentropic": tokens.COLORS["text"], "mil": tokens.COLORS["warn"],
           "theta": tokens.COLORS["error"]}


def series_pen(key, width=2.0):
    color = N_COLORS[key] if isinstance(key, int) else SPECIAL[key]
    style = Qt.PenStyle.DashLine if key in ("isentropic", "mil", "theta") else \
        Qt.PenStyle.SolidLine
    pen = pg.mkPen(QColor(color), width=width, style=style)
    pen.setCosmetic(True)
    return pen


class TradeChart(QWidget):
    """picked(key, index) on a click within PICK_PX of a point (None, -1 on empty space)."""

    picked = Signal(object, int)

    def __init__(self, title, tip_key, x_label, y_label, min_height=280, end_labels=True,
                 parent=None):
        """end_labels: name each curve at its right end (room is added on the x axis);
        otherwise a one-line legend under the title names them."""
        super().__init__(parent)
        self.end_labels = end_labels
        self.series = {}          # key -> dict(x, y, text(i), item, label)
        self.selected = None      # (key, index)
        self.last_hover = None    # text of the last hover tooltip
        self.vline = None
        self.title = field_label(title, tip_key)
        self.legend = QLabel()
        self.legend.setObjectName("chartLegend")
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.legend.setWordWrap(True)
        self.legend.setToolTip(tip(tip_key))
        self.legend.setVisible(not end_labels)
        self.plot = pg.PlotWidget(background=tokens.COLORS["surface"])
        self.plot.setMinimumHeight(min_height)
        item = self.plot.getPlotItem()
        item.setMenuEnabled(False)
        item.hideButtons()
        item.setMouseEnabled(x=False, y=False)
        item.showGrid(x=True, y=True, alpha=0.12)
        tick_font = theme.mono_font(10)
        for name, label in (("left", y_label), ("bottom", x_label)):
            axis = item.getAxis(name)
            axis.setPen(_pen("border", 1))
            axis.setTextPen(_pen("text_muted", 1))
            axis.setTickFont(tick_font)
            axis.setLabel(label, color=tokens.COLORS["text_muted"])
        item.getAxis("left").setWidth(LEFT_AXIS_W + 14)
        self.plot.setToolTip(tip(tip_key))
        self.marker = pg.ScatterPlotItem(size=12, pen=pg.mkPen(_qc("text"), width=2),
                                         brush=pg.mkBrush(_qc("surface")), symbol="o")
        self.marker.setZValue(30)
        item.addItem(self.marker)
        self.sel_marker = pg.ScatterPlotItem(size=16, pen=pg.mkPen(_qc("accent"), width=2.5),
                                             brush=pg.mkBrush(0, 0, 0, 0), symbol="o")
        self.sel_marker.setZValue(31)
        item.addItem(self.sel_marker)
        self.marker_text = None
        self.plot.scene().sigMouseMoved.connect(self._on_move)
        self.plot.scene().sigMouseClicked.connect(self._on_click)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(self.title)
        layout.addWidget(self.legend)
        layout.addWidget(self.plot, 1)

    # --- data -------------------------------------------------------------------------------
    def clear(self):
        item = self.plot.getPlotItem()
        for s in self.series.values():
            item.removeItem(s["item"])
            if s["label"] is not None:
                item.removeItem(s["label"])
        self.series = {}
        self.set_selected(None)
        if self.vline is not None:
            item.removeItem(self.vline)
            self.vline = None

    def set_series(self, key, xs, ys, text, label=None, pickable=True, width=2.0):
        """Draw (or replace) a curve. text(i) -> hover text of point i."""
        item = self.plot.getPlotItem()
        if key in self.series:
            old = self.series.pop(key)
            item.removeItem(old["item"])
            if old["label"] is not None:
                item.removeItem(old["label"])
        curve = pg.PlotDataItem(list(xs), list(ys), pen=series_pen(key, width))
        curve.setZValue(10 if isinstance(key, int) else 8)
        item.addItem(curve)
        text_item = None
        if label and xs and self.end_labels:
            color = N_COLORS[key] if isinstance(key, int) else SPECIAL[key]
            text_item = pg.TextItem(label, color=QColor(color), anchor=(0.0, 0.5))
            text_item.setFont(theme.mono_font(10))
            text_item.setPos(xs[-1], ys[-1])
            item.addItem(text_item)
        self.series[key] = dict(x=tuple(xs), y=tuple(ys), text=text, item=curve,
                                label=text_item, pickable=pickable, name=label)
        self._layout_axes()

    def _layout_axes(self):
        xs = [x for s in self.series.values() for x in s["x"]]
        if not xs:
            return
        lo, hi = min(xs), max(xs)
        pad = 0.16 * (hi - lo) if self.end_labels else 0.02 * (hi - lo)
        for s in self.series.values():          # clear of the design ring at a curve's end
            if s["label"] is not None:
                s["label"].setPos(s["x"][-1] + 0.02 * (hi - lo), s["y"][-1])
        self.plot.getPlotItem().setXRange(lo, hi + pad, padding=0.01)
        if not self.end_labels:
            self.legend.setText(self.legend_html())

    def legend_html(self):
        """Legend entries in key order: ramp counts, then the dashed reference lines."""
        def order(k):
            return (0, k) if isinstance(k, int) else (1, str(k))

        parts = []
        for key in sorted(self.series, key=order):
            s = self.series[key]
            if not s["name"]:
                continue
            color = N_COLORS[key] if isinstance(key, int) else SPECIAL[key]
            glyph = "╌╌" if not isinstance(key, int) else "━━"
            parts.append(f'<span style="white-space:nowrap"><span style="color:{color}">'
                         f'{glyph}</span>&nbsp;{s["name"]}</span>')
        return "&nbsp;&nbsp; ".join(parts)

    def set_vline(self, x, label, token="error"):
        item = self.plot.getPlotItem()
        if self.vline is not None:
            item.removeItem(self.vline)
        self.vline = pg.InfiniteLine(
            pos=x, angle=90, movable=False, pen=_pen(token, 1.2, Qt.PenStyle.DashLine),
            label=label, labelOpts={"position": 0.08, "color": tokens.COLORS[token],
                                    "anchors": [(1.0, 1.0), (1.0, 1.0)]})
        self.vline.label.setFont(theme.mono_font(10))
        self.vline.setZValue(5)
        item.addItem(self.vline, ignoreBounds=True)

    def set_marker(self, x, y, text):
        """The current design (a ring); text = its hover text."""
        if x is None or y is None or not (math.isfinite(x) and math.isfinite(y)):
            self.marker.setData([])
            self.marker_text = None
            return
        self.marker.setData([x], [y])
        self.marker_text = (x, y, text)

    def set_selected(self, sel):
        self.selected = sel
        if sel is None or sel[0] not in self.series:
            self.selected = None
            self.sel_marker.setData([])
            return
        s = self.series[sel[0]]
        self.sel_marker.setData([s["x"][sel[1]]], [s["y"][sel[1]]])

    # --- picking ----------------------------------------------------------------------------
    def _scene_xy(self, x, y):
        return self.plot.getPlotItem().vb.mapViewToScene(QPointF(x, y))

    def view_point_scene(self, key, index):
        s = self.series[key]
        return self._scene_xy(s["x"][index], s["y"][index])

    def nearest(self, scene_pos, pickable_only=False):
        """(key, index, distance px) of the point nearest to scene_pos, or None."""
        best = None
        for key, s in self.series.items():
            if pickable_only and not s["pickable"]:
                continue
            for i, (x, y) in enumerate(zip(s["x"], s["y"])):
                p = self._scene_xy(x, y)
                d = math.hypot(p.x() - scene_pos.x(), p.y() - scene_pos.y())
                if best is None or d < best[2]:
                    best = (key, i, d)
        return best

    def hover_text_at(self, scene_pos):
        if self.marker_text is not None:
            x, y, text = self.marker_text
            p = self._scene_xy(x, y)
            if math.hypot(p.x() - scene_pos.x(), p.y() - scene_pos.y()) <= PICK_PX:
                return text
        hit = self.nearest(scene_pos)
        if hit is None or hit[2] > PICK_PX:
            return None
        return self.series[hit[0]]["text"](hit[1])

    @guarded()      # runs inside pyqtgraph's scene mouse handler
    def _on_move(self, scene_pos):
        text = self.hover_text_at(scene_pos)
        self.last_hover = text
        if text:
            QToolTip.showText(QCursor.pos(), text, self.plot)
        else:
            QToolTip.hideText()

    def pick_at(self, scene_pos):
        hit = self.nearest(scene_pos, pickable_only=True)
        if hit is None or hit[2] > PICK_PX:
            self.set_selected(None)
            self.picked.emit(None, -1)
            return
        self.set_selected(hit[:2])
        self.picked.emit(hit[0], hit[1])

    @guarded()
    def _on_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.pick_at(event.scenePos())
