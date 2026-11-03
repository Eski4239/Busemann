"""Keyboard cheat-sheet ("?"): a card listing every shortcut. Esc, a click or any key closes."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout

from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from .overlay import DimOverlay

SHORTCUTS = (
    ("F", "Fit the drawing"),
    ("E", "Explain drawer"),
    ("Space", "Play / pause the off-design sweep (M8)"),
    ("1 – 4", "Design · Off-design · Analytics · Compare"),
    ("Ctrl+Z", "Undo"),
    ("Ctrl+Shift+Z", "Redo"),
    ("Ctrl+N", "New design"),
    ("Ctrl+O", "Open project"),
    ("Ctrl+S", "Save"),
    ("Ctrl+Shift+S", "Save as"),
    ("?", "This cheat sheet"),
)


class ShortcutsOverlay(DimOverlay):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("shortcutsOverlay")
        v = QVBoxLayout(self.card)
        v.setContentsMargins(tokens.space(3), tokens.space(2), tokens.space(3), tokens.space(2))
        v.setSpacing(tokens.space(1))
        title = QLabel("Keyboard shortcuts")
        title.setObjectName("overlayTitle")
        title.setToolTip(tip("overlay.shortcuts"))
        v.addWidget(title)
        grid = QGridLayout()
        grid.setHorizontalSpacing(tokens.space(3))
        grid.setVerticalSpacing(6)
        self.rows = []
        for r, (keys, action) in enumerate(SHORTCUTS):
            k = QLabel(keys)
            k.setObjectName("shortcutKey")
            k.setFont(theme.mono_font())
            k.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            a = QLabel(action)
            a.setObjectName("shortcutAction")
            for w in (k, a):
                w.setToolTip(tip("overlay.shortcuts"))
            grid.addWidget(k, r, 0)
            grid.addWidget(a, r, 1)
            self.rows.append((keys, action))
        v.addLayout(grid)
        hint = QLabel("Shortcuts are off while you type in a field. Press any key to close.")
        hint.setObjectName("muted")
        hint.setToolTip(tip("overlay.shortcuts"))
        v.addWidget(hint)

    def keyPressEvent(self, event):
        self.close_overlay()

    def mousePressEvent(self, event):
        self.close_overlay()
