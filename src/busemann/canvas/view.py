"""InletCanvas: the interactive inlet drawing (spec 4.3).

Hover (floating read-out), click selection, wheel zoom about the cursor, middle- or
Space-drag pan, F / double-click fit, layer toggles, grid with scale bar, Mach legend,
150 ms transitions between designs, and a greyed last-valid drawing on errors.

Custom angles (addendum C4): the downstream end of every ramp is a draggable handle. The
drag rotates that ramp about its start corner (theta_k snapped to 0.1°, Shift 0.01°) and a
shaded no-go wedge shows the attached-shock limit theta_max(M_k) at that corner. On the
off-design canvas a Space tap (no pan in between) emits space_tapped (play / pause).
"""
import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QFrame, QGraphicsView, QLabel

from inletdesign import api
from inletdesign import units as _units

from ..crashlog import guarded
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..views import format as fmt
from ..views.rows import cowl_rows, region_rows, shock_rows
from . import colors as _colors
from . import picture as P
from .hover_card import HoverCard
from .scene import M, S, InletScene, color

_ZOOM_STEP = 1.15
_SCALE_LIMITS = (0.02, 400.0)     # screen px per mm
_LEGEND_W = 116                   # legend card width, px (fits '1.95–2.02')
_LEGEND_ROW_H = 20                # px per Mach bin in the legend
_CONT_LEGEND_W = 170              # continuous legend card (off-design view)
_CONT_BAR_H = 150
CONTINUOUS_LEGEND_TITLE = "Mach (off-design view)"
HANDLE_R = 5                      # corner handle radius, px
HANDLE_PICK_PX = 9                # handle pick distance, px
PAN_START_PX = 4                  # a background left drag longer than this pans
SNAP_DEG, FINE_SNAP_DEG = 0.1, 0.01
LIMIT_FADE_MS = 1200              # the "Limit: ..." note fades out over this after release


def snap_angle(theta, fine=False):
    """theta rounded to the drag grid: 0.1°, or 0.01° with Shift."""
    step = FINE_SNAP_DEG if fine else SNAP_DEG
    return round(round(theta / step) * step, 10)


def ramp_theta(pivot, pointer, flow_in_deg):
    """Incremental ramp angle (deg) that points a ramp starting at `pivot` towards `pointer`
    (model coordinates, y up), given the flow direction arriving at that corner."""
    return math.degrees(math.atan2(pointer[1] - pivot[1], pointer[0] - pivot[0])) - flow_in_deg


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
    space_tapped = Signal()         # off-design canvas: Space pressed and released, no pan
    corner_drag_started = Signal(int)
    corner_drag_finished = Signal()

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
        self._space_panned = False
        self._bg_press = False       # the left press landed on empty background
        self.corner_drag = None      # dict while a ramp corner is dragged
        self.hovered_handle = None
        self.limit_note = None       # "Limit: ..." beside a stopped handle
        self._limit_k = None
        self._limit_opacity = 1.0
        self._limit_fade = QVariantAnimation(self)
        self._limit_fade.setDuration(LIMIT_FADE_MS)
        self._limit_fade.setStartValue(1.0)
        self._limit_fade.setEndValue(0.0)
        self._limit_fade.valueChanged.connect(self._on_limit_fade)

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
    @guarded(lambda self: self.abort_interaction())
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
        if self.mode == "offdesign":           # continuous colours, fixed over the sweep
            self.inlet_scene.continuous_range = self.continuous_range(sk)
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
            w = _CONT_LEGEND_W if self.mode == "offdesign" else _LEGEND_W
            vp.setRight(vp.right() - (w + 2 * tokens.LEGEND_INSET_PX))
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

    def continuous_range(self, sk=None):
        """(lo, hi) of the off-design colour scale: the lowest region Mach to M∞ of the point
        shown (it follows the slider)."""
        sk = sk if sk is not None else self._shown
        if sk is None:
            return tokens.MACH_CONTINUOUS_LO, 3.0
        machs = [r.M for r in sk.regions]
        lo, hi = min(machs), max(sk.mach, max(machs))
        return lo, max(hi, lo + 1e-6)

    def legend_rect(self):
        vp = self.viewport()
        if self.inlet_scene.continuous_range is not None:
            h = 36 + self.continuous_bar_height() + 12
            return QRectF(vp.width() - tokens.LEGEND_INSET_PX - _CONT_LEGEND_W,
                          tokens.LEGEND_INSET_PX, _CONT_LEGEND_W, h)
        rows = max(1, len(self.inlet_scene.mach_edges) - 1)
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

    def selection_screen_rect(self):
        """Global (screen) rect of the selected item, or None (nothing selected)."""
        from PySide6.QtCore import QRect

        kind, index = self.selection
        pic = self.inlet_scene.picture
        if kind is None or pic is None:
            return None
        if kind == "region" and index < len(pic.regions):
            pts = pic.regions[index].polygon
        elif kind == "shock" and index < len(pic.shocks):
            pts = [pic.shocks[index].start, pic.shocks[index].end]
        elif kind == "cowl":
            pts = pic.cowl_body
        else:
            return None
        view = [self.viewportTransform().map(S(p)) for p in pts]
        xs, ys = [p.x() for p in view], [p.y() for p in view]
        top_left = self.viewport().mapToGlobal(QPointF(min(xs), min(ys)).toPoint())
        return QRect(top_left.x(), top_left.y(), max(1, round(max(xs) - min(xs))),
                     max(1, round(max(ys) - min(ys)))).adjusted(-4, -4, 4, 4)

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

    # --- ramp corner handles (custom angles) ---------------------------------------------
    def handles_enabled(self):
        d = self.state.design
        return (self.mode == "design" and d is not None and self._shown is not None
                and self.state.inputs.method == "custom" and d.inputs.n_ramps > 0
                and self.error_text is None and len(self._shown.corners) == d.inputs.n_ramps)

    def corner_handles(self):
        """[(k, pivot_mm, handle_mm)]: ramp k turns about pivot; its handle is its end."""
        if not self.handles_enabled():
            return []
        sk = self._shown
        ends = list(sk.corners[1:]) + [sk.foot]
        return [(k, sk.corners[k], ends[k]) for k in range(len(sk.corners))]

    def handle_view_pos(self, k):
        for j, _, end in self.corner_handles():
            if j == k:
                return QPointF(self.mapFromScene(S(end)))
        return None

    def handle_at(self, view_pos):
        best, best_d = None, HANDLE_PICK_PX
        for k, _, end in self.corner_handles():
            q = QPointF(self.mapFromScene(S(end)))
            d = math.hypot(q.x() - view_pos.x(), q.y() - view_pos.y())
            if d <= best_d:
                best, best_d = k, d
        return best

    def start_corner_drag(self, k):
        d = self.state.design
        _, pivot, _ = self.corner_handles()[k]
        M_k = d.regions[k].M
        bounds = api.ramp_angle_bounds(d, k)          # fixed for the whole drag
        self.corner_drag = dict(k=k, pivot=pivot, flow_in=d.flow_angles_deg[k], M=M_k,
                                theta_max=api.max_deflection(M_k, d.inputs.gamma),
                                bounds=bounds, theta=d.ramp_angles_deg[k], at_limit=None,
                                auto_fit=self._auto_fit, animations=self.animations_enabled)
        self._auto_fit = False             # the view must not rescale under the pointer
        self.animations_enabled = False    # each drag step snaps (no 150 ms transitions)
        self._limit_fade.stop()
        self.limit_note = None
        self.hover_card.hide()
        self.corner_drag_started.emit(k)
        self.viewport().update()

    def drag_corner_to(self, view_pos, fine=False):
        """Set theta_k from a pointer position: snapped (0.1°, Shift 0.01°) and clamped to the
        ramp's fixed bounds (api.ramp_angle_bounds), so the design stays valid. At a bound
        the handle stops and `limit_note` says why. Returns the angle used."""
        drag = self.corner_drag
        inverse, _ = self.viewportTransform().inverted()      # sub-pixel, unlike mapToScene
        pointer = M(inverse.map(QPointF(view_pos)))
        step = FINE_SNAP_DEG if fine else SNAP_DEG
        raw = ramp_theta(drag["pivot"], pointer, drag["flow_in"])
        b = drag["bounds"]
        lo = math.ceil(b.lo / step - 1e-9) * step
        hi = math.floor(b.hi / step + 1e-9) * step
        theta = snap_angle(raw, fine)
        if theta >= hi:
            theta, drag["at_limit"] = hi, "hi"
        elif theta <= lo:
            theta, drag["at_limit"] = lo, "lo"
        else:
            drag["at_limit"] = None
        theta = round(theta, 10)
        self.limit_note = self._limit_text(drag) if drag["at_limit"] else None
        if theta != drag["theta"]:
            drag["theta"] = theta
            angles = list(self.state.inputs.custom_angles)
            angles[drag["k"]] = theta
            self.state.update(custom_angles=tuple(angles))
        self.viewport().update()
        return theta

    @staticmethod
    def _limit_text(drag):
        if drag["at_limit"] == "lo":
            return f"Limit: {drag['bounds'].lo:g}° minimum"
        return f"Limit: {drag['bounds'].detail}"

    def abort_interaction(self):
        """After a logged error in a handler: end any drag or pan so the canvas stays usable."""
        self._pan_from = None
        self._press_at = None
        self._bg_press = False
        if self.corner_drag is not None:
            self.finish_corner_drag()
        self.viewport().unsetCursor()

    def finish_corner_drag(self):
        if self.corner_drag is None:
            return
        drag = self.corner_drag
        self.corner_drag = None
        self._auto_fit = drag["auto_fit"]
        self.animations_enabled = drag["animations"]
        if self.limit_note:                # the limit note fades out after release
            self._limit_k = drag["k"]
            self._limit_fade.start()
        self.corner_drag_finished.emit()
        self.viewport().update()

    def _draw_handles(self, painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        drag = self.corner_drag
        if drag is not None:
            self._draw_no_go(painter, drag)
        for k, _, end in self.corner_handles():
            q = QPointF(self.mapFromScene(S(end)))
            active = (drag is not None and drag["k"] == k) or self.hovered_handle == k
            stopped = drag is not None and drag["k"] == k and drag["at_limit"]
            painter.setPen(QPen(color("warn" if stopped else "accent"), 2))
            painter.setBrush(color("warn" if stopped else "accent") if active
                             else color("surface"))
            painter.drawEllipse(q, HANDLE_R, HANDLE_R)
        self._draw_limit_note(painter)

    def _draw_limit_note(self, painter):
        """Small inline warning beside the stopped handle (fades after release)."""
        if not self.limit_note:
            return
        k = self.corner_drag["k"] if self.corner_drag is not None else self._limit_k
        q = self.handle_view_pos(k)
        if q is None:
            return
        opacity = 1.0 if self.corner_drag is not None else self._limit_opacity
        if opacity <= 0.0:
            return
        painter.save()
        painter.setOpacity(opacity)
        painter.setFont(theme.ui_font(tokens.SIZE_LABEL))
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(self.limit_note) + 16
        box = QRectF(q.x() + 10, q.y() - 30, w, 20)
        painter.setPen(QPen(color("warn"), 1))
        painter.setBrush(color("surface"))
        painter.drawRoundedRect(box, tokens.RADIUS, tokens.RADIUS)
        painter.setPen(color("text"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, self.limit_note)
        painter.restore()

    def _on_limit_fade(self, value):
        self._limit_opacity = float(value)
        if self._limit_opacity <= 0.0:
            self.limit_note = None
        self.viewport().update()

    def _draw_no_go(self, painter, drag):
        """Shaded wedge past the ramp's upper bound (detachment limit, 30° cap or a downstream
        limit), from that direction to 90° past the incoming flow at the corner."""
        pv = QPointF(self.mapFromScene(S(drag["pivot"])))
        end = self.handle_view_pos(drag["k"])
        r = max(80.0, 1.4 * math.hypot(end.x() - pv.x(), end.y() - pv.y())) if end else 120.0
        start, stop = self.no_go_angles()
        rect = QRectF(pv.x() - r, pv.y() - r, 2 * r, 2 * r)
        path = QPainterPath(pv)
        path.arcTo(rect, start, stop - start)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color("error", 0.12))
        painter.drawPath(path)
        a = math.radians(start)
        edge = QPointF(pv.x() + r * math.cos(a), pv.y() - r * math.sin(a))
        dashed = QPen(color("error"), 1.25)
        dashed.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(dashed)
        painter.drawLine(pv, edge)
        painter.setFont(theme.mono_font(tokens.SIZE_LABEL))
        painter.setPen(color("text"))
        painter.drawText(QRectF(pv.x() + 8, pv.y() + 6, 260, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         f"θ{drag['k'] + 1} {drag['theta']:.2f}°")

    def no_go_angles(self):
        """(start, end) absolute directions (deg, model) of the shaded wedge while dragging."""
        drag = self.corner_drag
        if drag is None:
            return None
        return drag["flow_in"] + drag["bounds"].hi, drag["flow_in"] + 90.0

    # --- events --------------------------------------------------------------------------
    @guarded(lambda self: self.abort_interaction())
    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120.0
        if steps:
            self.zoom(_ZOOM_STEP ** steps)
        event.accept()

    @guarded(lambda self: self.abort_interaction())
    def mousePressEvent(self, event):
        button = event.button()
        if button == Qt.MouseButton.LeftButton and not self._space:
            k = self.handle_at(event.position())
            if k is not None:
                self.start_corner_drag(k)
                event.accept()
                return
        if button == Qt.MouseButton.MiddleButton or (
                button == Qt.MouseButton.LeftButton and self._space):
            self._space_panned = self._space_panned or self._space
            self._pan_from = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if button == Qt.MouseButton.LeftButton:
            self._press_at = event.position()
            # on empty background a left drag pans (an item press stays a click / select)
            self._bg_press = self.pick(event.position())[0] is None
        super().mousePressEvent(event)

    @guarded(lambda self: self.abort_interaction())
    def mouseMoveEvent(self, event):
        if self.corner_drag is not None:
            fine = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.drag_corner_to(event.position(), fine)
            event.accept()
            return
        k = self.handle_at(event.position())
        if k != self.hovered_handle:
            self.hovered_handle = k
            self.viewport().update()
        if k is not None:
            self.hover_card.hide()
            self.viewport().setCursor(Qt.CursorShape.SizeAllCursor)
            event.accept()
            return
        if (self._pan_from is None and self._bg_press and self._press_at is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position() - self._press_at).manhattanLength() >= PAN_START_PX):
            self._pan_from = self._press_at          # background drag: start panning
            self.hover_card.hide()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
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

    @guarded(lambda self: self.abort_interaction())
    def mouseReleaseEvent(self, event):
        if self.corner_drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self.finish_corner_drag()
            event.accept()
            return
        if self._pan_from is not None:
            self._pan_from = None
            self._press_at = None
            self._bg_press = False
            self.viewport().unsetCursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton and self._press_at is not None:
            moved = (event.position() - self._press_at).manhattanLength()
            self._press_at = None
            if moved < 4 and self.error_text is None:
                self.select(*self.pick(event.position()))
        super().mouseReleaseEvent(event)

    @guarded(lambda self: self.abort_interaction())
    def mouseDoubleClickEvent(self, event):
        self.fit()
        event.accept()

    def event(self, event):
        # Space pans the canvas while it has focus (before the window's Space shortcut)
        if event.type() == event.Type.ShortcutOverride and event.key() == Qt.Key.Key_Space:
            event.accept()
            return True
        return super().event(event)

    @guarded(lambda self: self.abort_interaction())
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_F:
            self.fit()
        elif event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = True
            self._space_panned = False
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            super().keyPressEvent(event)

    @guarded(lambda self: self.abort_interaction())
    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space = False
            self.viewport().unsetCursor()
            if self.mode == "offdesign" and not self._space_panned:
                self.space_tapped.emit()            # a tap plays / pauses; hold+drag pans
        else:
            super().keyReleaseEvent(event)

    @guarded(lambda self: self.abort_interaction())
    def leaveEvent(self, event):
        self.hover_card.hide()
        self.hovered = (None, None)
        super().leaveEvent(event)

    @guarded(lambda self: self.abort_interaction())
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlay()
        if self._auto_fit and self._shown is not None:
            self.fit()

    # --- background grid, foreground legend / scale bar ---------------------------------
    @guarded(lambda self: self.abort_interaction())
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

    @guarded(lambda self: self.abort_interaction())
    def drawForeground(self, painter, rect):
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        if self.legend_visible() and not self.is_dimmed():
            self._draw_legend(painter)
        if self.grid_visible:
            self._draw_scale_bar(painter)
        if self.corner_handles():
            self._draw_handles(painter)
        painter.restore()

    def _draw_legend(self, painter):
        """Discrete Mach legend on a translucent card, top-right; thin sonic line at M = 1.
        The off-design view draws its continuous scale instead."""
        scene = self.inlet_scene
        if scene.continuous_range is not None:
            self._draw_continuous_legend(painter)
            return
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
        painter.setPen(color("text_muted"))
        for i in range(rows):                       # class label centred on its block
            y0 = bottom - (i + 1) * _LEGEND_ROW_H
            painter.drawText(QRectF(x + bar_w + 7, y0, card.right() - x - bar_w - 10,
                                    _LEGEND_ROW_H),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             P.class_label(edges[i], edges[i + 1]))
        if any(abs(e - 1.0) < 1e-9 for e in edges):  # thin dark sonic line at M = 1
            k = next(i for i, e in enumerate(edges) if abs(e - 1.0) < 1e-9)
            y = bottom - k * _LEGEND_ROW_H
            painter.setPen(QPen(color("text"), 1.5))
            painter.drawLine(QPointF(x - 3, y), QPointF(x + bar_w + 3, y))

    def continuous_bar_height(self):
        """Bar height of the continuous legend: 150 px, less when the canvas is short (the
        card always fits the viewport, so both ends and the sonic line stay visible)."""
        room = self.viewport().height() - 2 * tokens.LEGEND_INSET_PX - 36 - 12
        return max(48, min(_CONT_BAR_H, room))

    def continuous_ticks(self):
        """Tick values of the continuous legend: both ends, M = 1 when inside, and round
        values in between."""
        lo, hi = self.inlet_scene.continuous_range
        step = nice_step((hi - lo) / 4.0)
        ticks = {round(lo, 6), round(hi, 6)}
        if lo < 1.0 < hi:
            ticks.add(1.0)
        k = math.ceil(lo / step)
        while k * step < hi - 0.35 * step:
            v = round(k * step, 6)
            if all(abs(v - t) > 0.35 * step for t in ticks):
                ticks.add(v)
            k += 1
        return sorted(ticks)

    def _draw_continuous_legend(self, painter):
        lo, hi = self.inlet_scene.continuous_range
        card = self.legend_rect()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(QPen(color("border"), 1))
        painter.setBrush(color("surface", tokens.LEGEND_ALPHA))
        painter.drawRoundedRect(card.adjusted(0.5, 0.5, -0.5, -0.5), tokens.RADIUS, tokens.RADIUS)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setFont(theme.label_font())
        painter.setPen(color("text_muted"))
        painter.drawText(QRectF(card.left() + 10, card.top() + 8, card.width() - 20, 16),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         CONTINUOUS_LEGEND_TITLE)
        x, bar_w = card.left() + 12, 14
        bar_h = self.continuous_bar_height()
        top, bottom = card.top() + 36, card.top() + 36 + bar_h

        def y_of(M):                         # linear in M, highest Mach at the top
            return bottom - (M - lo) / (hi - lo) * bar_h

        for py in range(int(top), int(bottom)):
            M = lo + (bottom - py - 0.5) / bar_h * (hi - lo)
            painter.fillRect(QRectF(x, py, bar_w, 1), QColor(_colors.continuous(M, lo, hi)))
        painter.setPen(QPen(color("border"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(x, top, bar_w, bar_h))
        painter.setFont(theme.mono_font(tokens.SIZE_LABEL))
        ticks = self.continuous_ticks()
        ends = (ticks[0], ticks[-1])
        self.legend_tick_labels = []           # labels drawn (tests)
        for M in ticks:
            y = y_of(M)
            sonic = abs(M - 1.0) < 1e-9
            painter.setPen(QPen(color("text" if sonic else "text_muted"), 1.5 if sonic else 1))
            if sonic:
                painter.drawLine(QPointF(x - 3, y), QPointF(x + bar_w + 3, y))
            else:
                painter.drawLine(QPointF(x + bar_w, y), QPointF(x + bar_w + 3, y))
            # the end labels always show; an inner label too close to one is left out
            if M not in ends and any(abs(y - y_of(e)) < 13 for e in ends):
                continue
            painter.setPen(color("text" if sonic else "text_muted"))
            painter.drawText(QRectF(x + bar_w + 7, y - 8, card.right() - x - bar_w - 10, 16),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             f"{M:.3g}")
            self.legend_tick_labels.append(f"{M:.3g}")

    def legend_labels(self):
        """The class labels the legend draws, lowest Mach first (tests)."""
        edges = self.inlet_scene.mach_edges
        return [P.class_label(a, b) for a, b in zip(edges, edges[1:])]

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
