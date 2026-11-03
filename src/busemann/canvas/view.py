"""InletCanvas: the interactive inlet drawing (spec 4.3).

Hover (floating read-out), click selection, wheel zoom about the cursor, middle- or
Space-drag pan, F / double-click fit, layer toggles, grid with scale bar, Mach legend,
150 ms transitions between designs, and a greyed last-valid drawing on errors.
"""
import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QPainter, QPen, QTransform
from PySide6.QtWidgets import QFrame, QGraphicsView, QLabel

from inletdesign import units as _units

from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..views import format as fmt
from ..views.rows import cowl_rows, region_rows, shock_rows
from . import picture as P
from .hover_card import HoverCard
from .scene import M, S, InletScene, color

_ZOOM_STEP = 1.15
_SCALE_LIMITS = (0.02, 400.0)     # screen px per mm
_LEGEND_W = 84                    # legend card width, px
_LEGEND_ROW_H = 20                # px per Mach bin in the legend


def nice_step(x):
    """Smallest 1/2/5 x 10^k that is >= x."""
    if x <= 0:
        return 1.0
    k = math.floor(math.log10(x))
    for m in (1, 2, 5, 10):
        if m * 10**k >= x:
            return m * 10**k
    return 10 ** (k + 1)


class InletCanvas(QGraphicsView):
    selection_changed = Signal(object, object, object)   # kind|None, index|None, payload|None
    picture_changed = Signal()      # the region states shown changed (not per animation frame)

    def __init__(self, state, mode="design", parent=None):
        """mode "design": the shock-on-lip design; "offdesign": its frozen geometry at the
        off-design slider Mach (state.off_design)."""
        super().__init__(parent)
        self.state = state
        self.mode = mode
        self.inlet_scene = InletScene(self)
        self.setScene(self.inlet_scene)
        self.setObjectName("inletCanvas")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setRenderHints(QPainter.RenderHint.Antialiasing
                            | QPainter.RenderHint.TextAntialiasing
                            | QPainter.RenderHint.SmoothPixmapTransform)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.viewport().setMouseTracking(True)

        self.hover_card = HoverCard(self.viewport())
        self.overlay = QLabel(self.viewport())
        self.overlay.setObjectName("canvasOverlay")
        self.overlay.setToolTip(tip("canvas.overlay"))
        self.overlay.setWordWrap(True)
        self.overlay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(tokens.CANVAS_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._frame)
        self._anim.finished.connect(self._on_anim_finished)
        self._from = self._target = self._shown = None

        self.animations_enabled = True
        self.grid_visible = False
        self.error_text = None
        self.selection = (None, None)
        self.hovered = (None, None)
        self._auto_fit = True
        self._pan_from = None
        self._press_at = None
        self._space = False

        if mode == "offdesign":
            state.off_design_ready.connect(lambda *_: self._on_result(state.design,
                                                                      state.design_error))
        else:
            state.design_ready.connect(self._on_result)
        state.inputs_changed.connect(self._on_inputs)
        self._set_overlay("Computing…", error=False)
        if state.design is not None or state.design_error is not None:
            self._on_result(state.design, state.design_error)

    # --- results -------------------------------------------------------------------------
    def _on_result(self, result, error):
        if result is None:
            self._show_error(error or "design failed")
            return
        if self.mode != "offdesign":
            self._clear_error()
            self.show_skeleton(P.skeleton_from(result))
            return
        if self.state.off_design_error:
            if self.inlet_scene.picture is None:      # nothing shown yet: dim the design
                self._render(P.skeleton_from(result))
            self._show_error(self.state.off_design_error)
            return
        if self.state.off_design is None:
            return                                    # not evaluated yet
        self._clear_error()
        self.show_skeleton(P.skeleton_from(result, self.state.off_design))

    def _on_inputs(self, inputs):
        if inputs.units != self.inlet_scene.units and self._shown is not None:
            self.inlet_scene.units = inputs.units
            self._render(self._shown)

    def show_skeleton(self, sk):
        """Display a skeleton, animating from the current one when the topology matches."""
        snap = self._anim.state() == QVariantAnimation.State.Running
        if snap:
            self._anim.stop()          # new result mid-animation: skip straight to it
        prev = self._shown
        self._target = sk
        if (self.animations_enabled and not snap and self.isVisible()
                and P.same_topology(prev, sk)):
            self._from = prev
            if self._auto_fit:
                self.fit(P.build(sk))
            self._anim.start()
        else:
            self._render(sk)
            if self._auto_fit:
                self.fit()

    def _on_anim_finished(self):
        if self._auto_fit:          # labels were re-placed on the final drawing: refit
            self.fit()

    def is_animating(self):
        return self._anim.state() == QVariantAnimation.State.Running

    def _frame(self, t):
        if self._from is not None and self._target is not None:
            self._render(P.interpolate(self._from, self._target, float(t)))

    def _render(self, sk):
        pic = P.build(sk)
        new_states = self._shown is None or sk.regions is not self._shown.regions
        self.inlet_scene.set_picture(pic, self.state.inputs.units)
        self._shown = sk
        r = self.inlet_scene.geometry_rect()
        pad = 20.0 * max(sk.h, 1.0)
        self.setSceneRect(r.adjusted(-pad, -pad, pad, pad))
        self.inlet_scene.layout_labels(self.scale_factor())
        self._refresh_selection()
        self.viewport().update()
        if new_states:
            self.picture_changed.emit()

    def region_states(self):
        """RegionState per drawn region, in canvas index order ([] before the first draw)."""
        pic = self.inlet_scene.picture
        return [r.state for r in pic.regions] if pic is not None else []

    # --- error / overlay -----------------------------------------------------------------
    def _show_error(self, message):
        self._anim.stop()
        self.error_text = message
        self.hover_card.hide()
        if self.inlet_scene.picture is not None:
            self.inlet_scene.set_dimmed(True)
        self._set_overlay(fmt.nbsp(message[:1].upper() + message[1:]), error=True)

    def _clear_error(self):
        self.error_text = None
        self.inlet_scene.set_dimmed(False)
        self.overlay.hide()

    def _set_overlay(self, text, error):
        self.overlay.setText(text)
        self.overlay.setProperty("error", error)
        self.overlay.style().unpolish(self.overlay)
        self.overlay.style().polish(self.overlay)
        self.overlay.show()
        self._place_overlay()

    def _place_overlay(self):
        """Error card: as wide as its text up to a max width, then the text wraps."""
        vp = self.viewport()
        max_w = max(160, min(480, vp.width() - 64))
        margins = self.overlay.contentsMargins()
        pad = margins.left() + margins.right() + 2 * tokens.space(2) + 4
        natural = self.overlay.fontMetrics().horizontalAdvance(self.overlay.text()) + pad
        w = int(min(natural, max_w))
        self.overlay.setFixedWidth(w)
        self.overlay.setFixedHeight(self.overlay.heightForWidth(w))
        self.overlay.move((vp.width() - w) // 2, max(16, (vp.height() - self.overlay.height()) // 2))

    def is_dimmed(self):
        return self.inlet_scene.layers["walls"].opacity() < 1.0

    # --- view control --------------------------------------------------------------------
    def available_rect(self):
        """Viewport area for the drawing: everything left of the legend card."""
        vp = self.viewport().rect()
        if self.legend_visible():
            vp.setRight(vp.right() - (_LEGEND_W + 2 * tokens.LEGEND_INSET_PX))
        return QRectF(vp)

    def fit(self, pic=None):
        """Fill CANVAS_FILL of the limiting dimension of the available area, centred.

        The placed label rects (always the M∞ label, plus dimension labels when shown) are
        part of the bounds; label size in scene units depends on the zoom, so the fit is
        iterated. With a target `pic` (animation start) the last placed label rects are used.
        """
        self._auto_fit = True
        avail = self.available_rect()
        s = self.scale_factor()
        for _ in range(3 if pic is None else 1):
            if pic is not None:
                x0, y0, x1, y1 = pic.bounds()
                for r in self.inlet_scene.label_rects:
                    x0, y0 = min(x0, r[0]), min(y0, r[1])
                    x1, y1 = max(x1, r[2]), max(y1, r[3])
                rect = QRectF(QPointF(x0, -y1), QPointF(x1, -y0))
            else:
                self.inlet_scene.layout_labels(s)
                rect = self.inlet_scene.geometry_rect(include_labels=True)
            s = tokens.CANVAS_FILL * min(avail.width() / max(rect.width(), 1e-9),
                                         avail.height() / max(rect.height(), 1e-9))
            s = min(max(s, _SCALE_LIMITS[0]), _SCALE_LIMITS[1])
        self.setTransform(QTransform.fromScale(s, s))
        vp_centre = QPointF(self.viewport().rect().center())
        offset = (QPointF(avail.center()) - vp_centre) / s        # scene units
        self.centerOn(rect.center() - offset)
        if pic is None:
            self.inlet_scene.layout_labels(s)
            self.viewport().update()

    def legend_visible(self):
        return self.inlet_scene.picture is not None and self.inlet_scene.layer_visible("regions")

    def legend_rect(self):
        rows = max(1, len(self.inlet_scene.mach_edges) - 1)
        vp = self.viewport()
        h = 36 + rows * _LEGEND_ROW_H + 12
        return QRectF(vp.width() - tokens.LEGEND_INSET_PX - _LEGEND_W, tokens.LEGEND_INSET_PX,
                      _LEGEND_W, h)

    def scale_factor(self):
        return self.transform().m11()

    def zoom(self, factor, about_cursor=True):
        s = self.scale_factor()
        factor = min(max(factor, _SCALE_LIMITS[0] / s), _SCALE_LIMITS[1] / s)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse if about_cursor
                                     else QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scale(factor, factor)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._auto_fit = False
        self.inlet_scene.layout_labels(self.scale_factor())

    def zoom_in(self):
        self.zoom(_ZOOM_STEP ** 2, about_cursor=False)

    def zoom_out(self):
        self.zoom(_ZOOM_STEP ** -2, about_cursor=False)

    def set_animations_enabled(self, enabled):
        self.animations_enabled = enabled

    def set_layer_visible(self, name, visible):
        if name == "grid":
            self.grid_visible = visible
        else:
            self.inlet_scene.set_layer_visible(name, visible)
            if name == "shocks" and not visible and self.selection[0] == "shock":
                self.select(None, None)
        if self._auto_fit and self._shown is not None:
            self.fit()
        else:
            self.inlet_scene.layout_labels(self.scale_factor())
        self.viewport().update()

    def layer_visible(self, name):
        return self.grid_visible if name == "grid" else self.inlet_scene.layer_visible(name)

    # --- picking -------------------------------------------------------------------------
    def pick(self, view_pos):
        """(kind, index) under a viewport position: shocks within HOVER_PICK_PX, else regions."""
        pic = self.inlet_scene.picture
        if pic is None:
            return None, None
        p = QPointF(view_pos)
        if self.inlet_scene.layer_visible("shocks"):
            best, best_d = None, tokens.HOVER_PICK_PX
            for shock in pic.shocks:
                a = QPointF(self.mapFromScene(S(shock.start)))
                b = QPointF(self.mapFromScene(S(shock.end)))
                d = _segment_distance(p, a, b)
                if d <= best_d:
                    best, best_d = shock.index, d
            if best is not None:
                return "shock", best
        model = M(self.mapToScene(p.toPoint()))
        if P.point_in_polygon(model, pic.cowl_body):
            return "cowl", 0
        for region in pic.regions:
            if len(region.polygon) >= 3 and P.point_in_polygon(model, region.polygon):
                return "region", region.index
        return None, None

    def payload(self, kind, index):
        pic = self.inlet_scene.picture
        if pic is None or kind is None:
            return None
        if kind == "cowl":
            return pic.skeleton
        items = pic.regions if kind == "region" else pic.shocks
        return items[index].state if index < len(items) else None

    def select(self, kind, index):
        self.selection = (kind, index) if kind is not None else (None, None)
        self.inlet_scene.show_selection(*self.selection)
        self.selection_changed.emit(self.selection[0], self.selection[1],
                                    self.payload(*self.selection))

    def _refresh_selection(self):
        kind, index = self.selection
        if kind is None:
            return
        if self.payload(kind, index) is None:
            self.select(None, None)
        else:
            self.inlet_scene.show_selection(kind, index)
            self.selection_changed.emit(kind, index, self.payload(kind, index))

    # --- hover card ----------------------------------------------------------------------
    def _hover(self, view_pos):
        kind, index = self.pick(view_pos) if self.error_text is None else (None, None)
        self.hovered = (kind, index)
        if kind is None:
            self.hover_card.hide()
            self.viewport().unsetCursor()
            return
        self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        pic = self.inlet_scene.picture
        if kind == "cowl":
            sk = pic.skeleton
            rows = cowl_rows(sk)
            note = (f"drawn thickened for visibility ({P.MIN_DRAWN_WEDGE_DEG:g}° wedge)"
                    if sk.wedge_thickened else "")
            self.hover_card.show_rows("Cowl", rows, QPointF(view_pos).toPoint(), note)
            return
        if kind == "region":
            region = pic.regions[index]
            title, rows = region.name[:1].upper() + region.name[1:], region_rows(
                region.state, self.state.freestream, self.state.inputs.units)
        else:
            shock = pic.shocks[index]
            title, rows = shock.state.name[:1].upper() + shock.state.name[1:], shock_rows(shock.state)
        self.hover_card.show_rows(title, rows, QPointF(view_pos).toPoint())

    # --- events --------------------------------------------------------------------------
    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.zoom(_ZOOM_STEP ** steps)
        event.accept()

    def mousePressEvent(self, event):
        button = event.button()
        if button == Qt.MouseButton.MiddleButton or (
                button == Qt.MouseButton.LeftButton and self._space):
            self._pan_from = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if button == Qt.MouseButton.LeftButton:
            self._press_at = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._pan_from is not None:
            delta = event.position() - self._pan_from
            self._pan_from = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            self._auto_fit = False
            event.accept()
            return
        self._hover(event.position())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pan_from is not None:
            self._pan_from = None
            self.viewport().unsetCursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._press_at is not None:
            moved = (event.position() - self._press_at).manhattanLength()
            self._press_at = None
            if moved < 4 and self.error_text is None:
                self.select(*self.pick(event.position()))
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.fit()
        event.accept()

    def event(self, event):
        # Space pans the canvas while it has focus (before the window's Space shortcut)
        if event.type() == event.Type.ShortcutOverride and event.key() == Qt.Key.Key_Space:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F:
            self.fit()
        elif event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = True
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = False
            self.viewport().unsetCursor()
        else:
            super().keyReleaseEvent(event)

    def leaveEvent(self, event):
        self.hover_card.hide()
        self.hovered = (None, None)
        super().leaveEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlay()
        if self._auto_fit and self._shown is not None:
            self.fit()

    # --- background grid, foreground legend / scale bar ---------------------------------
    def drawBackground(self, painter, rect):
        painter.fillRect(rect, QBrush(color("surface")))
        if not self.grid_visible:
            return
        step = nice_step(40.0 / self.scale_factor())
        p = QPen(color("border"), 0)
        painter.setPen(p)
        x = math.floor(rect.left() / step) * step
        while x <= rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += step
        y = math.floor(rect.top() / step) * step
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += step

    def drawForeground(self, painter, rect):
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.legend_visible() and not self.is_dimmed():
            self._draw_legend(painter)
        if self.grid_visible:
            self._draw_scale_bar(painter)
        painter.restore()

    def _draw_legend(self, painter):
        """Discrete Mach legend on a translucent card, top-right; thin sonic line at M = 1."""
        scene = self.inlet_scene
        edges, colors = scene.mach_edges, scene.mach_colors
        card = self.legend_rect()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(color("border"), 1))
        painter.setBrush(color("surface", tokens.LEGEND_ALPHA))
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), tokens.RADIUS, tokens.RADIUS)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setFont(theme.label_font())
        painter.setPen(color("text_muted"))
        painter.drawText(QRectF(card.left() + 10, card.top() + 8, card.width() - 20, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "MACH")
        x = card.left() + 12
        bar_w = 14
        top = card.top() + 36
        rows = len(edges) - 1
        bottom = top + rows * _LEGEND_ROW_H
        for i in range(rows):                       # highest Mach at the top
            y0 = bottom - (i + 1) * _LEGEND_ROW_H
            painter.fillRect(QRectF(x, y0, bar_w, _LEGEND_ROW_H), colors[i])
        painter.setPen(QPen(color("border"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, top, bar_w, rows * _LEGEND_ROW_H))
        painter.setFont(theme.mono_font(tokens.SIZE_LABEL))
        for i, edge in enumerate(edges):
            y = bottom - i * _LEGEND_ROW_H
            sonic = abs(edge - 1.0) < 1e-9
            painter.setPen(QPen(color("text" if sonic else "text_muted"), 1.5 if sonic else 1))
            if sonic:
                painter.drawLine(QPointF(x - 3, y), QPointF(x + bar_w + 3, y))
            else:
                painter.drawLine(QPointF(x + bar_w, y), QPointF(x + bar_w + 3, y))
            painter.setPen(color("text" if sonic else "text_muted"))
            painter.drawText(QRectF(x + bar_w + 7, y - 8, card.right() - x - bar_w - 10, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{edge:.3g}")

    def _draw_scale_bar(self, painter):
        vp = self.viewport()
        s = self.scale_factor()
        length_mm = nice_step(100.0 / s)
        px = length_mm * s
        x0, y = 20, vp.height() - 24
        painter.setPen(QPen(color("text_muted"), 1))
        painter.drawLine(QPointF(x0, y), QPointF(x0 + px, y))
        for xx in (x0, x0 + px):
            painter.drawLine(QPointF(xx, y - 4), QPointF(xx, y + 4))
        system = self.state.inputs.units
        value = _units.to_display(length_mm / P.MM, "length", system)
        painter.setFont(theme.mono_font(tokens.SIZE_LABEL))
        painter.drawText(QRectF(x0, y - 22, 200, 16), Qt.AlignmentFlag.AlignLeft,
                         f"{fmt.sig(value, 3)} {_units.unit_label('length', system)}")


def _segment_distance(p, a, b):
    ab = b - a
    L2 = ab.x() ** 2 + ab.y() ** 2
    if L2 == 0:
        d = p - a
        return math.hypot(d.x(), d.y())
    t = max(0.0, min(1.0, ((p.x() - a.x()) * ab.x() + (p.y() - a.y()) * ab.y()) / L2))
    q = a + ab * t
    return math.hypot(p.x() - q.x(), p.y() - q.y())
