"""Isentropic ramp window (M11, addendum G): a non-modal Tools window showing a centred
Prandtl-Meyer compression fan (inletdesign.isentropic_ramp), alongside the current multi-ramp
design for comparison.

Left: delta/M_f toggle, h_c and M_inf fields (a "follow main design" checkbox keeps M_inf,
gamma and h_c synced to the main window's design). Centre: a zoomed canvas with the wall,
characteristics, lip and a continuous p/p_inf field. Right: results (M_f, recovery, engine-face
estimate vs MIL-E-5008B, multi-ramp recoveries at the same delta, cowl margin, wall length) and
one computed takeaway. Every computation (including the multi-ramp comparison) runs on this
window's own worker thread; the GUI thread only draws.
"""
import math

from PySide6.QtCore import QObject, QPointF, QRectF, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QRadioButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ..canvas import colors as _colors
from ..canvas.hover_card import HoverCard
from ..crashlog import guarded
from ..theme import qt as theme
from ..theme import tokens
from ..widgets.spin_field import SpinField

DEBOUNCE_MS = 120
CACHE_SIZE = 32
FAN_FIELD_STOPS = ("#F7F4EC", "#E8C27A", "#C9622A", "#8A2E1E")   # p/p_inf: pale to deep rust
COALESCE_LABEL = "characteristics coalesce into a shock here (not modelled)"


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


class _FanCanvas(QWidget):
    """Zoomed, self-contained paint of the fan: wall, characteristics, lip, p/p_inf field."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumSize(320, 320)
        self.ramp = None
        self.hover_card = HoverCard(parent if parent is not None else self)
        self._transform = None          # (scale, origin) world -> widget

    def set_ramp(self, ramp):
        self.ramp = ramp
        self.update()

    def _fit(self):
        """World -> widget affine map, +y up, margin, fit the fan + lip + leading edge."""
        if self.ramp is None:
            return None
        xs = [p[0] for p in self.ramp.wall_points] + [self.ramp.lip[0]]
        ys = [p[1] for p in self.ramp.wall_points] + [self.ramp.lip[1]]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        w, h = max(x1 - x0, 1e-9), max(y1 - y0, 1e-9)
        margin = 0.18
        avail_w, avail_h = self.width() * (1 - 2 * margin), self.height() * (1 - 2 * margin)
        scale = min(avail_w / w, avail_h / h)
        ox = self.width() / 2 - scale * (x0 + x1) / 2
        oy = self.height() / 2 + scale * (y0 + y1) / 2
        return scale, ox, oy

    def _to_widget(self, x, y, fit):
        scale, ox, oy = fit
        return QPointF(ox + scale * x, oy - scale * y)

    def _to_world(self, px, py, fit):
        scale, ox, oy = fit
        return ((px - ox) / scale, (oy - py) / scale)

    @guarded()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(tokens.COLORS["bg"]))
        if self.ramp is None:
            painter.end()
            return
        fit = self._fit()
        self._draw_field(painter, fit)
        self._draw_characteristics(painter, fit)
        self._draw_wall(painter, fit)
        self._draw_lip(painter, fit)
        self._draw_coalesce_label(painter, fit)
        painter.end()

    def _draw_field(self, painter, fit):
        ramp = self.ramp
        if not ramp.characteristics:
            return
        p_max = max(c.p_over_pinf for c in ramp.characteristics)
        lip = ramp.lip
        pts = [ramp.wall_points[0]] + [c for c in ramp.wall_points[1:]]
        for i in range(len(ramp.characteristics) - 1):
            c0, c1 = ramp.characteristics[i], ramp.characteristics[i + 1]
            w0, w1 = ramp.wall_points[i + 1], ramp.wall_points[i + 2]
            colour = QColor(_colors.ramp(FAN_FIELD_STOPS, c0.p_over_pinf / p_max))
            painter.setBrush(colour)
            painter.setPen(Qt.PenStyle.NoPen)
            poly = [self._to_widget(*w0, fit), self._to_widget(*w1, fit),
                    self._to_widget(*lip, fit)]
            painter.drawPolygon(poly)

    def _draw_characteristics(self, painter, fit):
        pen = QPen(QColor(tokens.COLORS["border"]))
        pen.setWidthF(0.6)
        painter.setPen(pen)
        lip = self._to_widget(*self.ramp.lip, fit)
        for i, pt in enumerate(self.ramp.wall_points):
            if i == 0 or i % 8:
                continue
            painter.drawLine(self._to_widget(*pt, fit), lip)

    def _draw_wall(self, painter, fit):
        pen = QPen(QColor(tokens.COLORS["text"]))
        pen.setWidthF(2.0)
        painter.setPen(pen)
        pts = [self._to_widget(*p, fit) for p in self.ramp.wall_points]
        for a, b in zip(pts, pts[1:]):
            painter.drawLine(a, b)
        # hatching, coarse ticks perpendicular to the wall
        hatch_pen = QPen(QColor(tokens.COLORS["border"]))
        hatch_pen.setWidthF(1.0)
        painter.setPen(hatch_pen)
        step = max(1, len(pts) // 24)
        for i in range(0, len(pts) - 1, step):
            ax, ay = pts[i].x(), pts[i].y()
            bx, by = pts[i + 1].x(), pts[i + 1].y()
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / length * 8, dx / length * 8
            painter.drawLine(QPointF(ax, ay), QPointF(ax + nx, ay + ny))

    def _draw_lip(self, painter, fit):
        lip = self._to_widget(*self.ramp.lip, fit)
        painter.setBrush(QColor(tokens.COLORS["accent"]))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(lip, 4, 4)

    def _draw_coalesce_label(self, painter, fit):
        lip = self._to_widget(*self.ramp.lip, fit)
        painter.setFont(theme.ui_font(tokens.SIZE_LABEL))
        painter.setPen(QColor(tokens.COLORS["text_muted"]))
        rect = QRectF(lip.x() - 110, lip.y() - 46, 220, 28)
        painter.setBrush(QColor(tokens.COLORS["surface"]))
        painter.setPen(QColor(tokens.COLORS["border"]))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QColor(tokens.COLORS["text_muted"]))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                         COALESCE_LABEL)

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


class IsentropicRampWindow(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle("Isentropic ramp")
        self.setMinimumSize(900, 600)
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

        self.follow_main = QCheckBox("Follow main design")
        self.follow_main.setChecked(True)
        self.follow_main.toggled.connect(self._on_follow_toggled)

        self.delta_radio = QRadioButton("δ (total turning)")
        self.mf_radio = QRadioButton("M_f (final Mach)")
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

        left = QVBoxLayout()
        left.addWidget(self.follow_main)
        left.addWidget(self.delta_radio)
        left.addWidget(self.delta_field)
        left.addWidget(self.mf_radio)
        left.addWidget(self.mf_field)
        left.addWidget(QLabel("M∞"))
        left.addWidget(self.m_inf_field)
        left.addWidget(QLabel("h_c (capture height)"))
        left.addWidget(self.h_c_field)
        left.addStretch(1)
        left_panel = QWidget()
        left_panel.setLayout(left)
        left_panel.setFixedWidth(240)

        self.canvas = _FanCanvas(self)

        self.result_labels = {}
        right = QVBoxLayout()
        for key, title in (("mf", "M_f"), ("recovery", "Recovery"),
                           ("engine_face", "Engine-face (MIL-E-5008B)"),
                           ("cowl_margin", "Cowl margin"), ("wall_length", "Wall length")):
            lab = QLabel("—")
            lab.setObjectName("isentropicResult")
            right.addWidget(QLabel(title))
            right.addWidget(lab)
            self.result_labels[key] = lab
        self.multi_ramp_label = QLabel("—")
        self.multi_ramp_label.setWordWrap(True)
        right.addWidget(QLabel("Multi-ramp recovery at the same δ"))
        right.addWidget(self.multi_ramp_label)
        self.takeaway_label = QLabel("")
        self.takeaway_label.setWordWrap(True)
        self.takeaway_label.setObjectName("isentropicTakeaway")
        right.addWidget(self.takeaway_label)
        self.warning_label = QLabel("")
        self.warning_label.setWordWrap(True)
        self.warning_label.setObjectName("isentropicWarning")
        right.addWidget(self.warning_label)
        self.export_dxf_button = QPushButton("Export DXF…")
        self.export_dxf_button.clicked.connect(self.export_dxf)
        self.export_geo_button = QPushButton("Export Gmsh (.geo)…")
        self.export_geo_button.clicked.connect(self.export_geo)
        right.addWidget(self.export_dxf_button)
        right.addWidget(self.export_geo_button)
        right.addStretch(1)
        right_panel = QWidget()
        right_panel.setLayout(right)
        right_panel.setFixedWidth(260)

        row = QHBoxLayout(self)
        row.addWidget(left_panel)
        row.addWidget(self.canvas, 1)
        row.addWidget(right_panel)

        if main_window is not None:
            main_window.state.design_ready.connect(self._on_main_design_ready)
        self._sync_from_main()
        self._schedule()

    # --- inputs -----------------------------------------------------------------------------
    def _on_follow_toggled(self, checked):
        self.m_inf_field.setEnabled(not checked)
        self.h_c_field.setEnabled(not checked)
        if checked:
            self._sync_from_main()
        self._schedule()

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

    def _apply(self, result):
        if result.error:
            self._ramp = None
            self.canvas.set_ramp(None)
            self.warning_label.setText(result.error)
            for lab in self.result_labels.values():
                lab.setText("—")
            self.multi_ramp_label.setText("—")
            self.takeaway_label.setText("")
            return
        ramp = result.ramp
        self._ramp = ramp
        self.canvas.set_ramp(ramp)
        self.result_labels["mf"].setText(f"{ramp.M_f:.4f}")
        self.result_labels["recovery"].setText(f"{ramp.recovery:.4f}")
        self.result_labels["engine_face"].setText(f"{ramp.engine_face_recovery:.4f}")
        self.result_labels["cowl_margin"].setText(f"{ramp.cowl_margin:.2f}°")
        self.result_labels["wall_length"].setText(f"{ramp.wall_length * 1000:.2f} mm")
        parts = [f"n={n}: {r:.4f}" for n, r in sorted(ramp.multi_ramp_recovery.items())]
        self.multi_ramp_label.setText(", ".join(parts) if parts else "—")
        compare_n = (max(ramp.multi_ramp_recovery, key=lambda n: ramp.multi_ramp_recovery[n])
                    if ramp.multi_ramp_recovery else None)
        if compare_n is not None:
            compare_r = ramp.multi_ramp_recovery[compare_n]
            self.takeaway_label.setText(
                f"At δ = {ramp.delta_deg:.1f}° the isentropic ramp recovers {ramp.recovery:.3f} "
                f"vs {compare_r:.3f} for {compare_n} ramps.")
        self.warning_label.setText(ramp.warning or "")

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

    def export_dxf(self):
        if self._ramp is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export isentropic ramp DXF", "", "DXF drawing (*.dxf)")
        if not path:
            return
        try:
            from inletdesign.export import export_isentropic_dxf

            from ..export.notes import write_verification_notes

            meta = self._export_meta("isentropic ramp DXF")
            export_isentropic_dxf(self._ramp, path, metadata=dict(meta))
            write_verification_notes(path, meta, ())
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def export_geo(self):
        if self._ramp is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export isentropic ramp Gmsh geometry", "", "Gmsh geometry (*.geo)")
        if not path:
            return
        try:
            from inletdesign.export_cad import export_isentropic_geo

            from ..export.notes import write_verification_notes

            meta = self._export_meta("isentropic ramp Gmsh .geo")
            export_isentropic_geo(self._ramp, path, metadata=meta)
            write_verification_notes(path, meta, ())
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

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
