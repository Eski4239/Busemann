"""InletScene: Qt graphics items for a Picture (scene units are mm; scene y = -model y)."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainterPath, QPen, QPolygonF, QTransform
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsPathItem, QGraphicsPolygonItem, QGraphicsRectItem, QGraphicsScene,
    QGraphicsTextItem,
)

from inletdesign import units as _units

from ..theme import qt as theme
from ..theme import tokens
from . import colors as _colors
from . import picture as P
from ..crashlog import guarded

LAYERS = ("regions", "walls", "shocks", "streamtube", "dimensions", "annotations", "selection")
TOGGLEABLE = ("shocks", "regions", "dimensions", "grid")
_Z = {name: i for i, name in enumerate(LAYERS)}
BOW_SHOCK_TOOLTIP = ("Illustrative only: the external cowl shock is detached, so a bow shock "
                     "stands ahead of the lip. Its position and the spillage/drag it causes "
                     "are not modelled.")


def S(p):
    """Model (x, y-up, mm) -> scene point."""
    return QPointF(p[0], -p[1])


def M(qp):
    """Scene point -> model (x, y-up, mm)."""
    return (qp.x(), -qp.y())


def color(name, alpha=None):
    c = QColor(tokens.COLORS[name])
    if alpha is not None:
        c.setAlphaF(alpha)
    return c


def pen(name, width=1.0, style=Qt.PenStyle.SolidLine, alpha=None):
    p = QPen(color(name, alpha), width, style)
    p.setCosmetic(True)               # width in screen px at any zoom / display scale
    p.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return p


def bin_colors(edges):
    """One QColor per Mach bin (see canvas.colors)."""
    return [QColor(c) for c in _colors.bin_colors(edges)]


def length_text(metres, system):
    """Drawing lengths: mm with 1 decimal (SI), inches with 2 decimals (Imperial)."""
    if system == "Imperial":
        return f"{metres / _units.INCH:.2f} in"
    return f"{metres * 1000.0:.1f} mm"


def _poly(points):
    return QPolygonF([S(p) for p in points])


def _path(points):
    path = QPainterPath()
    if points:
        path.moveTo(S(points[0]))
        for p in points[1:]:
            path.lineTo(S(p))
    return path


class _Layer(QGraphicsRectItem):
    """Invisible parent: visibility and opacity propagate to its children."""

    def __init__(self, z):
        super().__init__(QRectF())
        self.setPen(Qt.PenStyle.NoPen)
        self.setZValue(z)


class Label(QGraphicsTextItem):
    """Mono label of constant screen size, centred on its position, on a surface pill.
    Text may be rich text (M8.4: real subscripts, h<sub>c</sub>); text() is the plain text."""

    PAD_X, PAD_Y, RADIUS = 4.0, 2.0, 4.0

    def __init__(self, text="", parent=None, size=tokens.SIZE_LABEL, color_name="text_muted"):
        super().__init__(parent)
        self.document().setDocumentMargin(0)
        self.setFont(theme.mono_font(size))
        self.setDefaultTextColor(color(color_name))
        self.setText(text)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations)
        self.preferred = (0.0, 0.0)     # model mm
        self.anchor = "center"
        self.attach = None              # model point the label describes (leader target)
        self.leader = None              # QGraphicsPathItem shown when the label is displaced
        self._recentre()

    def boundingRect(self):
        r = super().boundingRect()
        return r.adjusted(-self.PAD_X, -self.PAD_Y, self.PAD_X, self.PAD_Y)

    @guarded()
    def paint(self, painter, option, widget=None):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color("surface", 0.85))
        painter.drawRoundedRect(self.boundingRect(), self.RADIUS, self.RADIUS)
        super().paint(painter, option, widget)

    def setText(self, text):
        if "<" in text:
            self.setHtml(text)
        else:
            self.setPlainText(text)

    def text(self):
        return self.toPlainText()

    def set(self, text, model_pt, anchor="center"):
        self.setText(text)
        self.preferred, self.anchor = model_pt, anchor
        self.setPos(S(model_pt))
        self._recentre()

    def size_px(self):
        r = self.boundingRect()
        return r.width(), r.height()

    def _recentre(self):
        r = super().boundingRect()
        self.setTransform(QTransform.fromTranslate(-r.width() / 2, -r.height() / 2))


class InletScene(QGraphicsScene):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackgroundBrush(QBrush(color("surface")))
        self.layers = {name: _Layer(_Z[name]) for name in LAYERS}
        for layer in self.layers.values():
            self.addItem(layer)
        self.picture = None
        self.units = "SI"
        self.region_items = []
        self.shock_items = []
        self._dim_items = []
        self.dim_labels = []          # Label items of the dimension layer, placement order
        self.mach_edges = [0.5, 1.0]
        self.mach_colors = []
        self.continuous_range = None  # (lo, hi): continuous Mach colours (off-design view)
        self.label_rects = []         # placed label rects (model mm), after layout_labels
        self._callouts = []           # (leader item, anchor point, Label)
        self._build_static()

    # --- static items ------------------------------------------------------------------
    def _build_static(self):
        walls = self.layers["walls"]
        hatch = QBrush(color("wall"), Qt.BrushStyle.BDiagPattern)   # 45 deg wall hatching
        self.ramp_body = QGraphicsPolygonItem(walls)
        self.ramp_body.setBrush(hatch)
        self.ramp_body.setPen(Qt.PenStyle.NoPen)
        self.ramp_surface = QGraphicsPathItem(walls)
        self.ramp_surface.setPen(pen("wall", 2.0))
        self.cowl_body = QGraphicsPolygonItem(walls)
        self.cowl_body.setBrush(hatch)
        self.cowl_body.setPen(pen("wall", 1.5))

        self.bow_shock = QGraphicsPathItem(self.layers["shocks"])
        self.bow_shock.setPen(pen("shock", 2.0, Qt.PenStyle.DashLine))
        self.bow_shock.setToolTip(BOW_SHOCK_TOOLTIP)
        self.bow_shock.hide()

        self.streamtube = QGraphicsPathItem(self.layers["streamtube"])
        self.streamtube.setPen(pen("text_muted", 1.0, Qt.PenStyle.DotLine))

        ann = self.layers["annotations"]
        self.arrow = QGraphicsPathItem(ann)
        self.arrow.setPen(pen("text", 1.5))
        self.arrow.setBrush(QBrush(color("text")))
        self.arrow_label = Label("", ann, size=tokens.SIZE_BASE, color_name="text")

        sel = self.layers["selection"]
        self.selection_item = QGraphicsPathItem(sel)
        self.selection_item.setPen(pen("accent", 2.5))
        self.selection_item.hide()

    # --- update ------------------------------------------------------------------------
    def set_picture(self, pic, units=None):
        """Update every item in place from a Picture (rebuilding lists only on count change)."""
        self.picture = pic
        if units is not None:
            self.units = units
        self.ramp_body.setPolygon(_poly(pic.ramp_body))
        self.ramp_surface.setPath(_path(pic.ramp_surface))
        self.cowl_body.setPolygon(_poly(pic.cowl_body))
        self.streamtube.setPath(_path(pic.streamtube))
        self.bow_shock.setPath(_path(pic.bow_shock))
        self.bow_shock.setVisible(bool(pic.bow_shock))
        self._set_regions(pic)
        self._set_shocks(pic)
        self._set_arrow(pic)
        self._set_dimensions(pic)

    def _set_regions(self, pic):
        layer = self.layers["regions"]
        while len(self.region_items) < len(pic.regions):
            self.region_items.append(QGraphicsPolygonItem(layer))
        while len(self.region_items) > len(pic.regions):
            self.removeItem(self.region_items.pop())
        machs = [r.state.M for r in pic.regions]
        self.mach_edges = P.mach_bins(min(machs), pic.skeleton.regions[0].M)
        self.mach_colors = bin_colors(self.mach_edges)
        for item, region in zip(self.region_items, pic.regions):
            if self.continuous_range is not None:        # off-design view: continuous map
                fill = QColor(_colors.continuous(region.state.M, *self.continuous_range))
            else:
                fill = QColor(self.mach_colors[P.bin_index(region.state.M, self.mach_edges)])
            item.setPolygon(_poly(region.polygon))
            item.setBrush(QBrush(fill))
            border = QPen(QColor(_colors.darker(fill.name())), 1.0)
            border.setCosmetic(True)
            border.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            item.setPen(border)

    def region_fill(self, index):
        return self.region_items[index].brush().color()

    def _set_shocks(self, pic):
        layer = self.layers["shocks"]
        while len(self.shock_items) < len(pic.shocks):
            self.shock_items.append(QGraphicsPathItem(layer))
        while len(self.shock_items) > len(pic.shocks):
            self.removeItem(self.shock_items.pop())
        for item, shock in zip(self.shock_items, pic.shocks):
            style = Qt.PenStyle.DashLine if shock.kind == "normal" else Qt.PenStyle.SolidLine
            item.setPen(pen("shock", 2.0, style))
            item.setPath(_path([shock.start, shock.end]))

    def _set_arrow(self, pic):
        tail, head = pic.arrow
        h = pic.skeleton.h
        size = 0.045 * h
        path = _path([tail, head])
        tip = QPolygonF([S(head), S((head[0] - 1.8 * size, head[1] + 0.7 * size)),
                         S((head[0] - 1.8 * size, head[1] - 0.7 * size))])
        path.addPolygon(tip)
        path.closeSubpath()
        self.arrow.setPath(path)
        self.arrow_label.set(f"M∞ = {pic.skeleton.mach:.2f}",
                             (0.5 * (tail[0] + head[0]), tail[1] + 0.1 * h))

    # --- dimensions --------------------------------------------------------------------
    def _set_dimensions(self, pic):
        layer = self.layers["dimensions"]
        for item in self._dim_items:
            self.removeItem(item)
        self._dim_items, self.dim_labels, self._callouts = [], [], []
        h = pic.skeleton.h
        line_pen = pen("text_muted", 1.0)
        ext_pen = pen("text_muted", 0.8, alpha=0.7)
        tick = 0.03 * h

        def add(item):
            item.setParentItem(layer)
            self._dim_items.append(item)
            return item

        def label(text, d, attach=None):
            item = add(Label())
            item.set(text, d.text_at, d.anchor)
            item.attach = attach
            if attach is not None:
                item.leader = add(QGraphicsPathItem())
                item.leader.setPen(pen("text_muted", 0.8, alpha=0.8))
                item.leader.hide()
            self.dim_labels.append(item)
            return item

        for d in pic.dimensions:
            if d.kind == "linear":
                a, b, d0, d1 = d.points
                ux, uy = d1[0] - d0[0], d1[1] - d0[1]
                L = math.hypot(ux, uy) or 1.0
                ux, uy = ux / L, uy / L
                ext = QPainterPath()
                for p, q in ((a, d0), (b, d1)):
                    vx, vy = q[0] - p[0], q[1] - p[1]
                    vl = math.hypot(vx, vy) or 1.0
                    ext.moveTo(S(p))
                    ext.lineTo(S((q[0] + vx / vl * tick, q[1] + vy / vl * tick)))
                add(QGraphicsPathItem(ext)).setPen(ext_pen)
                dim = _path([d0, d1])
                for p, sgn in ((d0, 1.0), (d1, -1.0)):       # filled arrowheads, inward
                    nx, ny = -uy, ux
                    dim.addPolygon(QPolygonF([
                        S(p),
                        S((p[0] + sgn * ux * 2.2 * tick + nx * 0.6 * tick,
                           p[1] + sgn * uy * 2.2 * tick + ny * 0.6 * tick)),
                        S((p[0] + sgn * ux * 2.2 * tick - nx * 0.6 * tick,
                           p[1] + sgn * uy * 2.2 * tick - ny * 0.6 * tick)),
                    ]))
                    dim.closeSubpath()
                item = add(QGraphicsPathItem(dim))
                item.setPen(line_pen)
                item.setBrush(QBrush(color("text_muted")))
                label(f"{d.label} {length_text(d.value, self.units)}", d,
                      attach=((d0[0] + d1[0]) / 2, (d0[1] + d1[1]) / 2))
            elif d.kind == "angle":
                c = d.points[0]
                a0, a1 = d.angles
                ref = QPainterPath()
                ref.moveTo(S(c))
                ref.lineTo(S((c[0] + math.cos(math.radians(a0)) * d.radius * 1.35,
                              c[1] + math.sin(math.radians(a0)) * d.radius * 1.35)))
                add(QGraphicsPathItem(ref)).setPen(pen("text_muted", 0.8, Qt.PenStyle.DashLine))
                arc = QPainterPath()
                rect = QRectF(c[0] - d.radius, -c[1] - d.radius, 2 * d.radius, 2 * d.radius)
                arc.arcMoveTo(rect, a0)
                arc.arcTo(rect, a0, a1 - a0)
                add(QGraphicsPathItem(arc)).setPen(line_pen)
                mid = math.radians(0.5 * (a0 + a1))
                label(f"{d.label} {d.value:.2f}°", d,
                      attach=(c[0] + math.cos(mid) * d.radius, c[1] + math.sin(mid) * d.radius))
            else:  # callout
                p = d.points[0]
                lead = add(QGraphicsPathItem())
                lead.setPen(line_pen)
                x, y = (length_text(v, self.units) for v in d.extra)
                item = label(f"{d.label} ({x.split()[0]}, {y})", d)
                self._callouts.append((lead, p, item))
        self._update_callouts()

    def _update_callouts(self):
        for lead, p, item in self._callouts:
            path = _path([p, P_model(item.pos())])
            path.addEllipse(S(p), 0.012 * self.picture.skeleton.h, 0.012 * self.picture.skeleton.h)
            lead.setPath(path)

    # --- label layout (collision pass) ---------------------------------------------------
    def obstacles(self):
        pic = self.picture
        polygons = [pic.ramp_body, pic.cowl_body]
        segments = []
        if self.layers["shocks"].isVisible():
            segments += [(s.start, s.end) for s in pic.shocks]
            segments += list(zip(pic.bow_shock, pic.bow_shock[1:]))
        return polygons, segments

    def layout_labels(self, scale):
        """Place the M∞ label and (if shown) dimension labels at `scale` px/mm, avoiding
        hatching, shocks and each other. Stores the placed rects (model mm)."""
        if self.picture is None:
            return
        labels = [self.arrow_label]
        if self.layers["dimensions"].isVisible():
            labels += self.dim_labels
        polygons, segments = self.obstacles()
        specs = [(lab.preferred, *lab.size_px(), lab.anchor) for lab in labels]
        placed = P.place_labels(specs, polygons, segments, scale)
        self.label_rects = []
        for lab, (centre, rect) in zip(labels, placed):
            lab.setPos(S(centre))
            self.label_rects.append(rect)
            if lab.leader is not None:
                self._set_leader(lab, centre, rect)
        self._update_callouts()

    @staticmethod
    def _set_leader(lab, centre, rect):
        """Leader from the described point to the nearest edge of a label that had to move."""
        ax, ay = lab.attach
        inside = rect[0] <= ax <= rect[2] and rect[1] <= ay <= rect[3]
        near = (min(max(ax, rect[0]), rect[2]), min(max(ay, rect[1]), rect[3]))
        far = math.hypot(near[0] - ax, near[1] - ay) > 0.6 * (rect[3] - rect[1])
        if inside or not far:
            lab.leader.hide()
            return
        lab.leader.setPath(_path([lab.attach, near]))
        lab.leader.show()

    # --- visibility / state ------------------------------------------------------------
    def set_layer_visible(self, name, visible):
        if name in self.layers:
            self.layers[name].setVisible(visible)

    def layer_visible(self, name):
        return self.layers[name].isVisible()

    def set_dimmed(self, dimmed):
        for name in LAYERS:
            if name != "selection":
                self.layers[name].setOpacity(0.4 if dimmed else 1.0)

    def show_selection(self, kind, index):
        pic = self.picture
        if pic is None or kind is None:
            self.selection_item.hide()
            return
        if kind == "region" and index < len(pic.regions):
            path = _path(pic.regions[index].polygon)
            path.closeSubpath()
        elif kind == "shock" and index < len(pic.shocks):
            path = _path([pic.shocks[index].start, pic.shocks[index].end])
        elif kind == "cowl":
            path = _path(pic.cowl_body)
            path.closeSubpath()
        else:
            self.selection_item.hide()
            return
        self.selection_item.setPath(path)
        self.selection_item.show()

    def geometry_rect(self, include_labels=False):
        """Scene rect of the drawing (walls, flow domain, bow shock) plus, optionally, the
        placed label rects from the last layout_labels()."""
        if self.picture is None:
            return QRectF(-50, -50, 100, 100)
        x0, y0, x1, y1 = self.picture.bounds()
        if include_labels:
            for r in self.label_rects:
                x0, y0, x1, y1 = min(x0, r[0]), min(y0, r[1]), max(x1, r[2]), max(y1, r[3])
        return QRectF(QPointF(x0, -y1), QPointF(x1, -y0))


def P_model(qp):
    return (qp.x(), -qp.y())
