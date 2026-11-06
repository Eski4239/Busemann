"""Floating read-out card shown while hovering a region or shock."""
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QGridLayout, QLabel

from ..theme import qt as theme
from ..theme import tokens


class HoverCard(QFrame):
    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("hoverCard")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setOffset(0, 2)
        c = QColor(tokens.COLORS["text"])
        c.setAlpha(tokens.SHADOW_ALPHA)
        shadow.setColor(c)
        self.setGraphicsEffect(shadow)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(tokens.space(1) + 4, tokens.space(1), tokens.space(1) + 4,
                                      tokens.space(1))
        self._grid.setHorizontalSpacing(tokens.space(1))
        self._grid.setVerticalSpacing(2)
        self._labels = []
        self.title = ""
        self.note = ""
        self.values = {}     # key -> raw float, for tests and future export
        self.hide()

    def show_rows(self, title, rows, at, note=""):
        """rows: (key, label, value float, text, unit). at: viewport position of the cursor.
        note: optional muted line under the rows."""
        for w in self._labels:
            w.deleteLater()
        self._labels = []
        self.title = title
        self.values = {key: value for key, _, value, _, _ in rows}
        head = QLabel(title)
        head.setObjectName("hoverTitle")
        self._grid.addWidget(head, 0, 0, 1, 3)
        self._labels.append(head)
        for r, (_key, label, _value, text, unit) in enumerate(rows, start=1):
            name = QLabel(label)
            name.setTextFormat(Qt.TextFormat.RichText)
            name.setObjectName("readoutLabel")
            val = QLabel(text)
            val.setObjectName("readoutValue")
            val.setFont(theme.mono_font())
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            un = QLabel(unit)
            un.setObjectName("readoutUnit")
            un.setFont(theme.mono_font(tokens.SIZE_LABEL))
            for c, w in enumerate((name, val, un)):
                self._grid.addWidget(w, r, c)
                self._labels.append(w)
        self.note = note
        if note:
            hint = QLabel(note)
            hint.setObjectName("hoverNote")
            self._grid.addWidget(hint, len(rows) + 1, 0, 1, 3)
            self._labels.append(hint)
        self.adjustSize()
        self.move_near(at)
        self.show()
        self.raise_()

    def move_near(self, at):
        parent = self.parentWidget()
        x, y = at.x() + 16, at.y() + 16
        if x + self.width() > parent.width() - 4:
            x = at.x() - 16 - self.width()
        if y + self.height() > parent.height() - 4:
            y = at.y() - 16 - self.height()
        self.move(QPoint(max(4, x), max(4, y)))
