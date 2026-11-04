"""Verification tab (addendum C6): every approximation and warning, each with severity, the
criterion used, its source and "must be verified with a CFD solver"."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import verification as V
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import section_title

_ICONS = {"error": ("alert-triangle", "error"), "warn": ("alert-triangle", "warn"),
          "info": ("info", "accent")}


class VerificationPanel(QWidget):
    count_changed = Signal(int)          # warnings + errors (the tab badge)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.items = []
        self.cards = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2),
                                  tokens.space(2))
        layout.setSpacing(tokens.space(1))
        layout.addWidget(section_title("Verification", "section.verification"))
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        self.summary.setWordWrap(True)
        self.summary.setToolTip(tip("verification.summary"))
        layout.addWidget(self.summary)
        self._list = QVBoxLayout()
        self._list.setSpacing(tokens.space(1))
        layout.addLayout(self._list)
        layout.addStretch(1)
        for signal in (state.design_ready, state.off_design_ready, state.freestream_ready):
            signal.connect(lambda *_: self.refresh())
        state.view_changed.connect(lambda *_: self.refresh())
        state.inputs_changed.connect(lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        if self.state.dragging and self.items:
            return                               # rebuilt when the drag ends
        self.items = self.state.verification_items()
        for card in self.cards:
            card.deleteLater()
        self.cards = [self._card(item) for item in self.items]
        for card in self.cards:
            self._list.addWidget(card)
        n = V.badge_count(self.items)
        self.summary.setText(
            f"{len(self.items)} items, {n} need attention. Every approximate result here "
            f"{V.CFD_STATEMENT}." if self.items else "No design.")
        self.count_changed.emit(n)

    def _card(self, item):
        card = QFrame()
        card.setObjectName("verificationCard")
        card.setProperty("level", item.severity)
        v = QVBoxLayout(card)
        v.setContentsMargins(tokens.space(1) + 4, tokens.space(1), tokens.space(1) + 4,
                             tokens.space(1))
        v.setSpacing(3)
        head = QHBoxLayout()
        head.setSpacing(tokens.space(1))
        icon = QLabel()
        name, colour = _ICONS[item.severity]
        icon.setPixmap(theme.icon(name, colour, 16).pixmap(16, 16))
        icon.setToolTip(V.SEVERITY_TITLES[item.severity])
        title = QLabel(item.title)
        title.setObjectName("noticeTitle")
        title.setProperty("level", item.severity)
        title.setWordWrap(True)
        title.setToolTip(tip("verification.title"))
        head.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(title, 1)
        v.addLayout(head)
        rows = [("Criterion", item.criterion, "verification.criterion", "verificationText"),
                ("Source", item.source, "verification.source", "verificationSource"),
                (None, item.text, "verification.text", "verificationText")]
        if item.quote:
            rows.append(("Validation", item.quote, "verification.quote", "verificationQuote"))
        for caption, text, key, obj in rows:
            label = QLabel(f"{caption}: {text}" if caption else text)
            label.setObjectName(obj)
            label.setWordWrap(True)
            label.setToolTip(item.tooltip if key == "verification.criterion" and item.tooltip
                             else tip(key))
            if obj == "verificationSource":
                label.setFont(theme.mono_font(tokens.SIZE_LABEL))
            v.addWidget(label)
        return card

    def titles(self):
        return [i.title for i in self.items]
