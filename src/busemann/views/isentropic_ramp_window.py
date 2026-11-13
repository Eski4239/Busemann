"""Isentropic ramp window (M11, addendum G; restyled in M12): a non-modal Tools window showing a
centred Prandtl-Meyer compression fan (inletdesign.isentropic_ramp), alongside the current
multi-ramp design for comparison.

Left panel: "Follow main design", δ / final-Mach choice and the input fields. Centre: the fan
drawn like the main canvas (hatched wall, cowl wedge, shock colour for the terminal normal
shock at the duct entry) with a continuous p/p∞ field and its legend, framed to fill the view.
Right panel: result cards as in the Results panel (recovery; engine face ≈ η × diffuser
recovery; MIL-E-5008B; final Mach; duct entry height; cowl margin; wall length), the
multi-ramp recoveries at the same δ, one computed takeaway and the exports. Every
computation runs on this window's own worker thread; the GUI thread only draws.
"""
import math

from PySide6.QtCore import (
    QObject, QPointF, QRectF, QRunnable, QSizeF, Qt, QThreadPool, QTimer, Signal,
)
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPolygonF, QStaticText
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QPushButton,
    QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..canvas import colors as _colors
from ..canvas import picture as _pic
from ..canvas.hover_card import HoverCard
from ..canvas.scene import color, pen
from ..crashlog import guarded
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import KpiCard, field_label, section_title
from ..widgets.spin_field import SpinField

DEBOUNCE_MS = 120
CACHE_SIZE = 32
FAN_FIELD_STOPS = ("#F7F4EC", "#E8C27A", "#C9622A", "#8A2E1E")   # p/p∞: pale to deep rust
COALESCE_LABEL = "characteristics coalesce into a shock here (not modelled)"
LEGEND_TITLE = "p/p∞"
DEFAULT_DIFFUSER = 0.97              # Inputs.diffuser_recovery default (no main window)
LEFT_W, RIGHT_W = 260, 300
# canvas frame, px: room for the coalesce label above, the h_t label below, the legend right
PAD_LEFT, PAD_TOP, PAD_BOTTOM, LEGEND_W = 28, 64, 36, 76
DUCT_EXTRA = 0.35                    # drawn duct beyond the normal shock, in capture heights
LABEL_W, LABEL_H = 236, 34


class _Signals(QObject):
    done = Signal(int, object)                    # generation, _Result | _Error


class _Result:
    def __init__(self, key, ramp):
        self.key, self.ramp, self.error = key, ramp, None


class _Error:
    def __init__(self, key, message):
        self.key, self.ramp, self.error = key, None, message


class _Job(QRunnable):
    def __init__(self, generation, key, M_inf, gamma, h_c, delta_deg, M_f, n_list):
        super().__init__()
        self.setAutoDelete(False)
        self.generation = generation
        self.args = (key, M_inf, gamma, h_c, delta_deg, M_f, n_list)
        self.signals = _Signals()

    def run(self):
        key, M_inf, gamma, h_c, delta_deg, M_f, n_list = self.args
        try:
            from inletdesign.isentropic_ramp import isentropic_ramp

            ramp = isentropic_ramp(M_inf, gamma, h_c, delta_deg=delta_deg, M_f=M_f,
                                   n_list=n_list)
            result = _Result(key, ramp)
        except Exception as exc:                 # noqa: BLE001 (shown, never raised)
            result = _Error(key, str(exc))
        self.signals.done.emit(self.generation, result)


N_RAMPS_LIST = (1, 2, 3, 4)


def fan_geometry(ramp):
    """Model geometry of the drawing (metres, y up): the wall surface continued as the duct
    floor, the cowl wedge, the terminal normal shock at the duct entry (foot, lip)."""
    h = ramp.capture_height
    delta = ramp.delta_deg
    flow = (math.cos(math.radians(delta)), math.sin(math.radians(delta)))
    normal = (-flow[1], flow[0])
    wall_end = ramp.wall_points[-1]
    mu_f = math.asin(min(1.0, 1.0 / ramp.M_f))
    ahead = ramp.lip_to_wall_end * math.cos(mu_f)    # wall end -> normal-shock foot, along flow
    floor_len = ahead + DUCT_EXTRA * h
    floor_end = (wall_end[0] + floor_len * flow[0], wall_end[1] + floor_len * flow[1])
    surface = list(ramp.wall_points) + [floor_end]
    band = _pic.wall_band(surface, h)
    cowl, cowl_inner_end, cowl_outer_end = _pic.cowl_wedge(
        ramp.lip, delta, h, 0.0, length=DUCT_EXTRA)
    foot = (ramp.lip[0] - ramp.throat_height * normal[0],
            ramp.lip[1] - ramp.throat_height * normal[1])
    return dict(surface=surface, band=band, cowl=cowl, foot=foot, wall_end=wall_end,
                floor_end=floor_end, cowl_outer_end=cowl_outer_end)


class _FanCanvas(QWidget):
    """Self-contained paint of the fan: field, characteristics, wall, cowl, terminal shock,
    labels and the p/p∞ legend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fanCanvas")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMouseTracking(True)
        self.setMinimumSize(360, 320)
        self.setToolTip(tip("iso.canvas"))
        self.ramp = None
        self.geometry_ = None
        self.hover_card = HoverCard(parent if parent is not None else self)
        self.label_rects = {}           # name -> QRectF of each painted label (tests)
        self.painted_texts = []          # every string painted (text audit)
        self.legend_rect = QRectF()

    def set_ramp(self, ramp):
        self.ramp = ramp
        self.geometry_ = fan_geometry(ramp) if ramp is not None else None
        self.update()

    def drawing_rect(self):
        """Widget area the drawing is fitted into (label padding and the legend excluded)."""
        return QRectF(PAD_LEFT, PAD_TOP, max(self.width() - PAD_LEFT - LEGEND_W - 8, 1.0),
                      max(self.height() - PAD_TOP - PAD_BOTTOM, 1.0))

    def _bounds(self):
        g = self.geometry_
        pts = [*self.ramp.wall_points, self.ramp.lip, g["floor_end"], g["cowl_outer_end"],
               *g["band"]]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), max(xs), min(ys), max(ys)

    def _fit(self):
        """World -> widget map (scale, ox, oy), +y up: ramp, fan, lip and duct entry fill the
        drawing rect at one scale, centred."""
        if self.ramp is None:
            return None
        x0, x1, y0, y1 = self._bounds()
        area = self.drawing_rect()
        w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        scale = min(area.width() / w, area.height() / h)
        ox = area.center().x() - scale * (x0 + x1) / 2
        oy = area.center().y() + scale * (y0 + y1) / 2
        return scale, ox, oy

    def _to_widget(self, x, y, fit):
        scale, ox, oy = fit
        return QPointF(ox + scale * x, oy - scale * y)

    def _to_world(self, px, py, fit):
        scale, ox, oy = fit
        return ((px - ox) / scale, (oy - py) / scale)

    def _poly(self, points, fit):
        return QPolygonF([self._to_widget(*p, fit) for p in points])

    @guarded()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), color("surface"))
        self.label_rects, self.painted_texts = {}, []
        if self.ramp is None:
            painter.end()
            return
        fit = self._fit()
        self._draw_field(painter, fit)
        self._draw_characteristics(painter, fit)
        self._draw_walls(painter, fit)
        self._draw_terminal_shock(painter, fit)
        self._draw_flow_label(painter)
        self._draw_coalesce_label(painter, fit)
        self._draw_legend(painter)
        painter.end()

    # --- field ---------------------------------------------------------------------------
    def _p_range(self):
        ps = [c.p_over_pinf for c in self.ramp.characteristics] or [1.0]
        return 1.0, max(max(ps), 1.0)

    def _field_color(self, p):
        lo, hi = self._p_range()
        return QColor(_colors.ramp(FAN_FIELD_STOPS, (p - lo) / max(hi - lo, 1e-12)))

    def _draw_field(self, painter, fit):
        ramp, g = self.ramp, self.geometry_
        painter.setPen(Qt.PenStyle.NoPen)
        for i, c in enumerate(ramp.characteristics):
            w0, w1 = ramp.wall_points[i], ramp.wall_points[i + 1]
            painter.setBrush(self._field_color(c.p_over_pinf))
            painter.drawPolygon(self._poly((w0, w1, ramp.lip), fit))
        # uniform flow at the final Mach between the last characteristic and the normal shock
        painter.setBrush(self._field_color(self._p_range()[1]))
        painter.drawPolygon(self._poly((g["wall_end"], g["foot"], ramp.lip), fit))

    def _draw_characteristics(self, painter, fit):
        painter.setPen(pen("border", 0.8))
        lip = self._to_widget(*self.ramp.lip, fit)
        last = len(self.ramp.wall_points) - 1
        for i, pt in enumerate(self.ramp.wall_points):
            if i % 8 and i != last:
                continue
            painter.drawLine(self._to_widget(*pt, fit), lip)

    # --- walls (as the main canvas: canvas.scene / canvas.picture) --------------------------
    def _draw_walls(self, painter, fit):
        g = self.geometry_
        hatch = QBrush(color("wall"), Qt.BrushStyle.BDiagPattern)    # 45° wall hatching
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(hatch)
        painter.drawPolygon(self._poly(g["band"], fit))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen("wall", 2.0))
        painter.drawPolyline(self._poly(g["surface"], fit))
        painter.setBrush(hatch)
        painter.setPen(pen("wall", 1.5))
        painter.drawPolygon(self._poly(g["cowl"], fit))

    def _draw_terminal_shock(self, painter, fit):
        g = self.geometry_
        foot, lip = self._to_widget(*g["foot"], fit), self._to_widget(*self.ramp.lip, fit)
        painter.setPen(pen("shock", 2.0))
        painter.drawLine(foot, lip)
        # label below the duct floor (clear of the hatching), with a leader to the shock foot
        text = f"h<sub>t</sub> {self.ramp.throat_height * 1000.0:.2f} mm"
        at = QPointF(foot.x() + 14, foot.y() + 30)
        rect = self._rich_text(painter, "h_t", text, at, boxed=True)
        painter.setPen(pen("shock", 1.0, Qt.PenStyle.DotLine))
        painter.drawLine(foot, QPointF(rect.left() + 4, rect.top()))

    def _draw_flow_label(self, painter):
        text = f"M∞ {self.ramp.M_inf:.2f} →"
        self._plain_text(painter, "flow", text, QRectF(PAD_LEFT, PAD_TOP - 30, 120, 18),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "text")

    def _draw_coalesce_label(self, painter, fit):
        lip = self._to_widget(*self.ramp.lip, fit)
        x = min(max(lip.x() - LABEL_W / 2, 8.0), self.width() - LEGEND_W - 8 - LABEL_W)
        y = min(max(lip.y() - LABEL_H - 16, 8.0), self.height() - LABEL_H - 8)
        rect = QRectF(x, y, LABEL_W, LABEL_H)
        painter.setPen(pen("border", 1.0, Qt.PenStyle.DotLine))
        painter.drawLine(QPointF(min(max(lip.x(), rect.left()), rect.right()), rect.bottom()),
                         lip)
        painter.setBrush(color("surface"))
        painter.setPen(pen("border", 1.0))
        painter.drawRoundedRect(rect, 4, 4)
        self._plain_text(painter, "coalesce", COALESCE_LABEL, rect.adjusted(6, 2, -6, -2),
                         Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, "text_muted")
        self.label_rects["coalesce"] = rect

    def _draw_legend(self, painter):
        lo, hi = self._p_range()
        bar_h = min(170.0, max(self.height() - PAD_TOP - PAD_BOTTOM, 40.0))
        bar = QRectF(self.width() - LEGEND_W + 8, PAD_TOP, 12, bar_h)
        gradient = QLinearGradient(bar.bottomLeft(), bar.topLeft())
        for k, stop in enumerate(FAN_FIELD_STOPS):
            gradient.setColorAt(k / (len(FAN_FIELD_STOPS) - 1), QColor(stop))
        painter.setPen(pen("border", 1.0))
        painter.setBrush(QBrush(gradient))
        painter.drawRect(bar)
        align = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        self._plain_text(painter, "legend_title", LEGEND_TITLE,
                         QRectF(bar.left(), bar.top() - 22, LEGEND_W - 12, 16), align, "text")
        self._plain_text(painter, "legend_max", f"{hi:.2f}",
                         QRectF(bar.right() + 6, bar.top() - 8, 44, 16), align, "text_muted")
        self._plain_text(painter, "legend_min", f"{lo:.2f}",
                         QRectF(bar.right() + 6, bar.bottom() - 8, 44, 16), align, "text_muted")
        self.legend_rect = QRectF(bar.left(), bar.top() - 22, LEGEND_W - 12, bar_h + 30)

    # --- text helpers ----------------------------------------------------------------------
    def _plain_text(self, painter, name, text, rect, flags, colour):
        painter.setFont(theme.ui_font(tokens.SIZE_LABEL))
        painter.setPen(color(colour))
        painter.drawText(rect, flags, text)
        self.painted_texts.append(text)
        self.label_rects.setdefault(name, rect)

    def _rich_text(self, painter, name, html, at, boxed=False):
        """Rich text (real subscripts) at `at`, kept inside the widget; returns its rect."""
        static = QStaticText(html)
        static.setTextFormat(Qt.TextFormat.RichText)
        static.setTextWidth(-1)
        painter.setFont(theme.ui_font(tokens.SIZE_LABEL))
        static.prepare(painter.transform(), painter.font())
        size = static.size()
        x = min(max(at.x(), 4.0), self.width() - LEGEND_W - size.width() - 8)
        y = min(max(at.y(), 4.0), self.height() - size.height() - 6)
        rect = QRectF(QPointF(x, y), QSizeF(size))
        if boxed:
            painter.setBrush(color("surface"))
            painter.setPen(pen("border", 1.0))
            painter.drawRoundedRect(rect.adjusted(-4, -2, 4, 2), 4, 4)
        painter.setPen(color("text"))
        painter.drawStaticText(rect.topLeft(), static)
        self.painted_texts.append(html)
        self.label_rects[name] = rect.adjusted(-4, -2, 4, 2) if boxed else rect
        return rect

    # --- hover -----------------------------------------------------------------------------
    @guarded()
    def mouseMoveEvent(self, event):
        fit = self._fit()
        if fit is None or self.ramp is None:
            self.hover_card.hide()
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        wx, wy = self._to_world(pos.x(), pos.y(), fit)
        best, best_d = None, 1e9
        for i, (pt, c) in enumerate(zip(self.ramp.wall_points[1:], self.ramp.characteristics)):
            d = math.hypot(pt[0] - wx, pt[1] - wy)
            if d < best_d:
                best_d, best = d, (i, pt, c)
        if best is None or best_d > 0.15 * max(self.ramp.wall_length, 1e-9):
            self.hover_card.hide()
            return
        i, pt, c = best
        rows = [
            ("x", "x", pt[0], f"{pt[0] * 1000:.2f}", "mm"),
            ("y", "y", pt[1], f"{pt[1] * 1000:.2f}", "mm"),
            ("M", "M", c.M, f"{c.M:.4f}", ""),
            ("p", "p/p∞", c.p_over_pinf, f"{c.p_over_pinf:.4f}", ""),
            ("i", "characteristic", i, f"{i}", ""),
        ]
        self.hover_card.show_rows("Fan field", rows, pos.toPoint())

    @guarded()
    def leaveEvent(self, event):
        self.hover_card.hide()
        super().leaveEvent(event)


def _rich_field_label(html, key):
    """Field label with real subscripts (field_label() uppercases plain ASCII text)."""
    label = QLabel(html)
    label.setObjectName("fieldLabel")
    label.setFont(theme.label_font())
    label.setTextFormat(Qt.TextFormat.RichText)
    label.setToolTip(tip(key))
    return label


def _card(title_html, key, compact=True):
    card = KpiCard("", key, compact=compact)
    card.title.setTextFormat(Qt.TextFormat.RichText)
    card.title.setText(title_html)
    return card


class IsentropicRampWindow(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setObjectName("isentropicWindow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Isentropic ramp")
        self.setWindowIcon(theme.app_icon())
        self.setMinimumSize(1000, 640)
        self.main_window = main_window
        self._ramp = None
        self._gamma = 1.4

        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._gen = 0
        self._jobs = {}
        self._cache = {}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self._recompute)

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(self._build_inputs())
        self.canvas = _FanCanvas(self)
        row.addWidget(self.canvas, 1)
        row.addWidget(self._build_results())

        if main_window is not None:
            main_window.state.design_ready.connect(self._on_main_design_ready)
            # bound method, not a lambda: Qt drops it when this window is deleted
            main_window.state.inputs_changed.connect(self._on_main_inputs)
        self._sync_from_main()
        self._schedule()

    # --- panels ------------------------------------------------------------------------------
    def _build_inputs(self):
        self.follow_main = QCheckBox("Follow main design")
        self.follow_main.setToolTip(tip("iso.follow"))
        self.follow_main.setChecked(True)
        self.follow_main.toggled.connect(self._on_follow_toggled)

        self.delta_radio = QRadioButton("Total turning δ")
        self.mf_radio = QRadioButton("Final Mach number")
        for radio in (self.delta_radio, self.mf_radio):
            radio.setToolTip(tip("iso.specify"))
        self.delta_radio.setChecked(True)
        self._toggle_group = QButtonGroup(self)
        self._toggle_group.addButton(self.delta_radio)
        self._toggle_group.addButton(self.mf_radio)
        self.delta_radio.toggled.connect(self._on_toggle_changed)

        self.delta_field = SpinField(value=33.789, decimals=3, minimum=0.0, maximum=90.0,
                                     step=0.1, unit="°", quantity="angle")
        self.mf_field = SpinField(value=1.6375, decimals=4, minimum=1.0, maximum=10.0,
                                  step=0.01, unit="", quantity="dimensionless")
        self.mf_field.setEnabled(False)
        self.delta_field.value_changed.connect(lambda _v: self._schedule())
        self.mf_field.value_changed.connect(lambda _v: self._schedule())
        self.m_inf_field = SpinField(value=3.0, decimals=3, minimum=1.001, maximum=20.0,
                                     step=0.1, unit="", quantity="dimensionless")
        self.h_c_field = SpinField(value=0.1, decimals=4, minimum=1e-6, maximum=10.0,
                                   step=0.01, unit="m", quantity="length")
        self.m_inf_field.value_changed.connect(lambda _v: self._schedule())
        self.h_c_field.value_changed.connect(lambda _v: self._schedule())
        self.m_inf_field.setEnabled(False)
        self.h_c_field.setEnabled(False)
        for field, key in ((self.delta_field, "iso.delta"), (self.mf_field, "iso.mf"),
                           (self.m_inf_field, "iso.m_inf"), (self.h_c_field, "iso.h_c")):
            field.setToolTip(tip(key))

        panel = QFrame()
        panel.setObjectName("leftPanel")
        panel.setFixedWidth(LEFT_W)
        v = QVBoxLayout(panel)
        v.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2), tokens.space(2))
        v.setSpacing(tokens.space(1))
        v.addWidget(section_title("Inputs", "iso.section_inputs"))
        v.addWidget(self.follow_main)
        v.addSpacing(4)
        v.addWidget(field_label("Specify by", "iso.specify"))
        v.addWidget(self.delta_radio)
        v.addWidget(self.mf_radio)
        v.addSpacing(4)
        self.input_labels = [
            _rich_field_label("TOTAL TURNING δ", "iso.delta"),
            _rich_field_label("FINAL MACH M<sub>f</sub>", "iso.mf"),
            _rich_field_label("FREESTREAM M∞", "iso.m_inf"),
            _rich_field_label("CAPTURE HEIGHT h<sub>c</sub>", "iso.h_c"),
        ]
        for label, field in zip(self.input_labels, (self.delta_field, self.mf_field,
                                                    self.m_inf_field, self.h_c_field)):
            v.addWidget(label)
            v.addWidget(field)
        v.addStretch(1)
        return panel

    def _build_results(self):
        self.cards = {
            "recovery": KpiCard("Total pressure recovery", "iso.recovery"),
            "engine_face": _card("ENGINE FACE ≈ η × DIFFUSER RECOVERY", "iso.engine_face"),
            "mil": _card("MIL-E-5008B", "iso.mil"),
            "final_mach": _card("FINAL MACH M<sub>f</sub>", "iso.final_mach"),
            "h_t": _card("DUCT ENTRY HEIGHT h<sub>t</sub>", "iso.h_t"),
            "cowl_margin": _card("COWL MARGIN", "iso.cowl_margin"),
            "wall_length": _card("WALL LENGTH", "iso.wall_length"),
        }
        self.multi_ramp_label = QLabel("—")
        self.multi_ramp_label.setObjectName("multiRamp")
        self.multi_ramp_label.setTextFormat(Qt.TextFormat.RichText)
        self.multi_ramp_label.setToolTip(tip("iso.multi"))
        self.takeaway_label = QLabel("")
        self.takeaway_label.setWordWrap(True)
        self.takeaway_label.setObjectName("isentropicTakeaway")
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("isentropicWarning")
        self.export_dxf_button = QPushButton("Export DXF…")
        self.export_dxf_button.clicked.connect(self.export_dxf)
        self.export_geo_button = QPushButton("Export Gmsh (.geo)…")
        self.export_geo_button.clicked.connect(self.export_geo)
        for button in (self.export_dxf_button, self.export_geo_button):
            button.setObjectName("secondaryButton")
            button.setToolTip(tip("iso.export"))

        body = QWidget()
        body.setObjectName("panelBody")
        v = QVBoxLayout(body)
        v.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2), tokens.space(2))
        v.setSpacing(tokens.space(1))
        v.addWidget(section_title("Results", "iso.section_results"))
        for card in self.cards.values():
            v.addWidget(card)
        v.addSpacing(tokens.space(1))
        v.addWidget(section_title("Multi-ramp at the same δ", "iso.multi"))
        v.addWidget(self.multi_ramp_label)
        v.addWidget(self.takeaway_label)
        v.addWidget(self.warning_label)
        v.addStretch(1)
        v.addWidget(self.export_dxf_button)
        v.addWidget(self.export_geo_button)
        scroll = QScrollArea()
        scroll.setObjectName("rightScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(body)
        scroll.setFixedWidth(RIGHT_W)
        return scroll

    # --- inputs -----------------------------------------------------------------------------
    def _on_follow_toggled(self, checked):
        self.m_inf_field.setEnabled(not checked)
        self.h_c_field.setEnabled(not checked)
        if checked:
            self._sync_from_main()
        self._schedule()

    def _on_main_inputs(self, *_):
        self._show_cards()               # the diffuser recovery may have changed

    def _on_main_design_ready(self, design, _error):
        if self.follow_main.isChecked() and design is not None:
            self._sync_from_main()
            self._schedule()

    def _sync_from_main(self):
        if self.main_window is None or self.main_window.state.design is None:
            return
        design = self.main_window.state.design
        self.m_inf_field.set_value(design.inputs.M)
        self.h_c_field.set_value(design.inputs.capture_height)
        self._gamma = design.inputs.gamma
        if self.follow_main.isChecked():
            self.delta_field.set_value(design.cowl_angle_deg)

    def diffuser_recovery(self):
        """The main window's subsonic diffuser recovery (Design ▸ Advanced)."""
        if self.main_window is None:
            return DEFAULT_DIFFUSER
        return self.main_window.state.inputs.diffuser_recovery

    def load_from_header(self, header):
        """Load this window's inputs from an isentropic-ramp DXF's BUSEMANN_* header
        (project_controller._open_as_isentropic routes such a file here on Open)."""
        import json

        self.follow_main.setChecked(False)
        self.m_inf_field.set_value(json.loads(header["BUSEMANN_M_INF"]))
        self._gamma = json.loads(header["BUSEMANN_GAMMA"])
        self.h_c_field.set_value(json.loads(header["BUSEMANN_CAPTURE_HEIGHT"]))
        self.delta_radio.setChecked(True)
        self.delta_field.set_value(json.loads(header["BUSEMANN_DELTA_DEG"]))
        self._schedule()

    def _current_key(self):
        M_inf = self.m_inf_field.value()
        gamma = self._gamma
        h_c = self.h_c_field.value()
        use_delta = self.delta_radio.isChecked()
        delta = self.delta_field.value() if use_delta else None
        M_f = None if use_delta else self.mf_field.value()
        return (round(M_inf, 10), round(gamma, 10), round(h_c, 10),
                None if delta is None else round(delta, 10),
                None if M_f is None else round(M_f, 10))

    def _on_toggle_changed(self, delta_checked):
        self.delta_field.setEnabled(delta_checked)
        self.mf_field.setEnabled(not delta_checked)
        self._schedule()

    def _schedule(self):
        self._timer.start()

    # --- worker -------------------------------------------------------------------------------
    @guarded()
    def _recompute(self):
        key = self._current_key()
        if key in self._cache:
            self._apply(self._cache[key])
            return
        self._gen += 1
        self._pool.clear()
        M_inf, gamma, h_c, delta, M_f = key
        job = _Job(self._gen, key, M_inf, gamma, h_c, delta, M_f, N_RAMPS_LIST)
        job.signals.done.connect(self._on_done)
        self._jobs[self._gen] = job
        self._pool.start(job)

    def _on_done(self, generation, result):
        self._jobs.pop(generation, None)
        self._cache[result.key] = result
        while len(self._cache) > CACHE_SIZE:
            self._cache.pop(next(iter(self._cache)))
        if generation != self._gen or result.key != self._current_key():
            return
        self._apply(result)

    def _set_warning(self, text, level="error"):
        self.warning_label.setText(text[:1].upper() + text[1:] if text else "")
        self.warning_label.setProperty("level", level)
        self.warning_label.style().unpolish(self.warning_label)
        self.warning_label.style().polish(self.warning_label)

    def _apply(self, result):
        if result.error:
            self._ramp = None
            self.canvas.set_ramp(None)
            self._set_warning(result.error, "error")
            for card in self.cards.values():
                card.clear()
            self.multi_ramp_label.setText("—")
            self.takeaway_label.setText("")
            return
        ramp = result.ramp
        self._ramp = ramp
        self.canvas.set_ramp(ramp)
        self._show_cards()
        rows = [f"{n} ramp{'s' if n != 1 else ''}&nbsp;&nbsp;{r:.4f}"
                for n, r in sorted(ramp.multi_ramp_recovery.items())]
        self.multi_ramp_label.setText("<br>".join(rows) if rows else "—")
        compare_n = (max(ramp.multi_ramp_recovery, key=lambda n: ramp.multi_ramp_recovery[n])
                     if ramp.multi_ramp_recovery else None)
        if compare_n is not None:
            compare_r = ramp.multi_ramp_recovery[compare_n]
            self.takeaway_label.setText(
                f"At δ = {ramp.delta_deg:.1f}° the isentropic ramp recovers {ramp.recovery:.3f} "
                f"vs {compare_r:.3f} for {compare_n} ramps.")
        self._set_warning(ramp.warning or "", "warn")

    def _show_cards(self):
        ramp = self._ramp
        if ramp is None:
            return
        diffuser = self.diffuser_recovery()
        face, mil = ramp.engine_face_recovery(diffuser), ramp.mil_recovery
        c = self.cards
        c["recovery"].set_value(f"{ramp.recovery:.4f}")
        c["engine_face"].set_value(f"{face:.3f}", sub=f"Diffuser recovery {diffuser:.2f} "
                                                      "(main design, estimate)")
        pct = 100.0 * (face / mil - 1.0)
        c["mil"].set_value(f"{mil:.3f}", sub=(f"Engine face {abs(pct):.1f} % "
                                              f"{'above' if pct >= 0 else 'below'} it"))
        c["final_mach"].set_value(f"{ramp.M_f:.4f}")
        c["h_t"].set_value(f"{ramp.throat_height * 1000.0:.2f}", "mm")
        c["cowl_margin"].set_value(f"{ramp.cowl_margin:+.2f}", "°")
        c["wall_length"].set_value(f"{ramp.wall_length * 1000.0:.2f}", "mm")

    # --- export -------------------------------------------------------------------------------
    def _export_meta(self, what):
        from datetime import datetime, timezone

        from .. import __version__
        from ..export.metadata import git_commit

        ramp = self._ramp
        return {
            "app": "Busemann", "app_version": __version__, "git_commit": git_commit(),
            "exported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "export": what,
            "inputs": {"M_inf": ramp.M_inf, "gamma": ramp.gamma,
                       "capture_height": ramp.capture_height, "delta_deg": ramp.delta_deg},
        }

    def ask_path(self, title, file_filter):
        """Save dialog (replaced in tests)."""
        path, _ = QFileDialog.getSaveFileName(self, title, "", file_filter)
        return path or None

    def show_error(self, text):
        """Export error message (replaced in tests)."""
        from .export_controller import show_export_error

        show_export_error(self, text)

    def _export(self, title, file_filter, what, writer):
        if self._ramp is None:
            return None
        path = self.ask_path(title, file_filter)
        if not path:
            return None
        from ..export.notes import write_verification_notes
        from .export_controller import write_guarded

        meta = self._export_meta(what)

        def write():
            writer(self._ramp, path, dict(meta))
            write_verification_notes(path, meta, ())
        return write_guarded(path, write, self.show_error)

    def export_dxf(self):
        from inletdesign.export import export_isentropic_dxf

        return self._export("Export isentropic ramp DXF", "DXF drawing (*.dxf)",
                            "isentropic ramp DXF",
                            lambda ramp, path, meta: export_isentropic_dxf(ramp, path,
                                                                           metadata=meta))

    def export_geo(self):
        from inletdesign.export_cad import export_isentropic_geo

        return self._export("Export isentropic ramp Gmsh geometry", "Gmsh geometry (*.geo)",
                            "isentropic ramp Gmsh .geo",
                            lambda ramp, path, meta: export_isentropic_geo(ramp, path,
                                                                           metadata=meta))

    # --- lifecycle ------------------------------------------------------------------------
    def shutdown(self):
        self._timer.stop()
        self._gen += 1
        self._pool.clear()
        self._pool.waitForDone(2000)

    @guarded()
    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)
