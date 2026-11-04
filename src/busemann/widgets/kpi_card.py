"""KPI card: uppercase title, large mono value, muted mono unit, optional sub-line."""
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ..theme import qt as theme
from ..tooltips import attach
from ..theme import tokens

EMPTY = "—"
KPI_COMPACT = 17         # px, value font of a compact card


class KpiCard(QFrame):
    def __init__(self, title, key, parent=None, compact=False):
        """`key` names the card's tooltip in tooltips.json (shared by all its labels).
        `compact`: smaller value font and padding (Results panel, M8.2)."""
        super().__init__(parent)
        self.setObjectName("kpiCard")
        self.setProperty("compact", compact)

        self.title = QLabel(theme.caps(title))
        self.title.setObjectName("kpiTitle")
        self.title.setFont(theme.label_font())
        self.value_label = QLabel(EMPTY)
        self.value_label.setObjectName("kpiValue")
        self.value_label.setFont(theme.mono_font(KPI_COMPACT if compact else tokens.SIZE_KPI))
        self.value_label.setProperty("compact", compact)
        self.unit_label = QLabel()
        self.unit_label.setObjectName("unit")
        self.unit_label.setFont(theme.mono_font(tokens.SIZE_LABEL))
        self.sub_label = QLabel()
        self.sub_label.setObjectName("kpiSub")
        self.sub_label.hide()
        self.delta_label = QLabel()
        self.delta_label.setObjectName("kpiDelta")
        self.delta_label.setFont(theme.mono_font(tokens.SIZE_LABEL))
        self.delta_label.hide()
        self.badge = QLabel()
        self.badge.setObjectName("kpiBadge")
        self.badge.setFont(theme.label_font())
        self.badge.hide()

        value_row = QHBoxLayout()
        value_row.setSpacing(tokens.space(1) // 2)
        value_row.addWidget(self.value_label)
        value_row.addWidget(self.unit_label)
        value_row.addStretch(1)
        value_row.addWidget(self.badge)
        layout = QVBoxLayout(self)
        pad = tokens.space(1) if compact else tokens.space(1) + 4
        layout.setContentsMargins(tokens.space(2) - (4 if compact else 0), pad,
                                  tokens.space(2), pad)
        layout.setSpacing(1 if compact else 2)
        layout.addWidget(self.title)
        layout.addLayout(value_row)
        layout.addWidget(self.sub_label)
        layout.addWidget(self.delta_label)
        self._notes_layout = QVBoxLayout()
        self._notes_layout.setContentsMargins(0, 2, 0, 0)
        self._notes_layout.setSpacing(2)
        layout.addLayout(self._notes_layout)
        self.notes = {}                 # key -> QLabel, in display order
        attach(self, key)

    def set_value(self, text, unit="", sub=None):
        self.value_label.setText(text)
        self.unit_label.setText(unit)
        self.sub_label.setText(sub or "")
        self.sub_label.setVisible(bool(sub))

    def set_delta(self, text=None):
        """Small muted "Δ vs design" line under the value; None hides it."""
        self.delta_label.setText(f"Δ vs design {text}" if text else "")
        self.delta_label.setVisible(bool(text))

    def set_badge(self, text=None):
        """Small accent tag next to the value (e.g. CONSTRAINED); None hides it."""
        self.badge.setText(theme.caps(text) if text else "")
        self.badge.setVisible(bool(text))

    def set_notes(self, notes):
        """Extra small lines under the value: [(key, text, level, tooltip)]; level "ok",
        "error" or None (muted). An empty list removes them."""
        keys = [n[0] for n in notes]
        if keys != list(self.notes):            # rebuild only when the set of lines changes
            for label in self.notes.values():
                label.deleteLater()
            self.notes = {}
            for key in keys:
                label = QLabel()
                label.setObjectName("kpiNote")
                label.setWordWrap(True)
                self._notes_layout.addWidget(label)
                self.notes[key] = label
        for key, text, level, tooltip in notes:  # same lines: update in place (slider drags)
            label = self.notes[key]
            if label.text() != text:
                label.setText(text)
            level = level or "muted"
            if label.property("level") != level:
                label.setProperty("level", level)
                label.style().unpolish(label)
                label.style().polish(label)
            if label.toolTip() != tooltip:
                label.setToolTip(tooltip)

    def note(self, key):
        label = self.notes.get(key)
        return label.text() if label is not None else None

    def clear(self, sub=None):
        self.set_value(EMPTY, sub=sub)
        self.set_badge(None)
        self.set_delta(None)
        self.set_notes([])

    def text(self):
        return self.value_label.text()
