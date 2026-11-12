"""Collapsible section: a header toggle with a chevron and a content area."""
from PySide6.QtWidgets import QToolButton, QVBoxLayout, QWidget
from PySide6.QtCore import Qt

from ..theme import qt as theme


class CollapsibleSection(QWidget):
    def __init__(self, title, content, collapsed=True, tooltip="", parent=None):
        super().__init__(parent)
        self.toggle = QToolButton()
        self.toggle.setObjectName("sectionToggle")
        self.toggle.setText(theme.caps(title))
        self.toggle.setFont(theme.label_font())
        self.toggle.setCheckable(True)
        self.toggle.setToolTip(tooltip)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.content = content

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self.toggle)
        layout.addWidget(content)

        self.toggle.toggled.connect(self._set_expanded)
        self.toggle.setChecked(not collapsed)
        self._set_expanded(not collapsed)

    def _set_expanded(self, expanded):
        self.content.setVisible(expanded)
        self.toggle.setIcon(theme.icon("chevron-down" if expanded else "chevron-right",
                                       "text_muted", 14))
