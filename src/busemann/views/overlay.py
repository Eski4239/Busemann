"""Dimmed full-window overlay with an optional highlighted hole and a card (tour, shortcuts).

Same visual language as the rest of the app: surface card, 1 px border, 6 px radius, no
shadow; the backdrop is the text colour at low opacity.
"""
from PySide6.QtCore import QEvent, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QWidget

from ..theme import tokens

DIM_ALPHA = 0.45
HOLE_PAD = 6


class DimOverlay(QWidget):
    closed = Signal()

    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("dimOverlay")
        self.window_ = window
        self.hole = None                          # QRect in overlay coordinates, or None
        self.card = QFrame(self)
        self.card.setObjectName("overlayCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        window.installEventFilter(self)
        self.hide()

    def eventFilter(self, obj, event):
        if obj is self.window_ and event.type() == QEvent.Type.Resize and self.isVisible():
            self.relayout()
        return False

    def open(self):
        self.setGeometry(self.window_.rect())
        self.show()
        self.raise_()
        self.relayout()
        self.setFocus()

    def close_overlay(self):
        if self.isVisible():
            self.hide()
            self.closed.emit()

    def relayout(self):
        """Subclasses place the hole and the card; default: centred card."""
        self.setGeometry(self.window_.rect())
        self.card.adjustSize()
        r = self.rect()
        self.card.move(r.center().x() - self.card.width() // 2,
                       r.center().y() - self.card.height() // 2)
        self.update()

    def set_hole(self, widget_or_rect):
        """Highlight a widget (or a QRect in window coordinates)."""
        if widget_or_rect is None:
            self.hole = None
            return
        if isinstance(widget_or_rect, QRect):
            rect = widget_or_rect
        else:
            w = widget_or_rect
            rect = QRect(w.mapTo(self.window_, w.rect().topLeft()), w.size())
        self.hole = rect.adjusted(-HOLE_PAD, -HOLE_PAD, HOLE_PAD, HOLE_PAD)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        dim = QColor(tokens.COLORS["text"])
        dim.setAlphaF(DIM_ALPHA)
        path = QPainterPath()
        path.addRect(QRectF(self.rect()))
        if self.hole is not None:
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(self.hole), tokens.RADIUS, tokens.RADIUS)
            path = path.subtracted(hole)
        p.fillPath(path, dim)
        if self.hole is not None:
            p.setPen(QPen(QColor(tokens.COLORS["accent"]), 1.5))
            p.drawRoundedRect(QRectF(self.hole), tokens.RADIUS, tokens.RADIUS)
