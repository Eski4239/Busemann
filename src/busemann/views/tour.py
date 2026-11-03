"""Three-step first-run tour: a dimmed backdrop with the target highlighted and a small card.

Steps: the canvas (hover, click), the Explain button, the Off-design tab. Next / Back / Skip;
finishing or skipping stores "tour/done" so it never shows again unless Help > Show tour.
"""
from PySide6.QtCore import QRect, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ..settings import app_settings
from ..theme import tokens
from ..tooltips import tip
from .overlay import DimOverlay

CARD_W = 340
STEPS = (
    ("canvas", "The inlet canvas",
     "Hover a flow region or shock to read its state. Click it to select it; the station "
     "table and the results panel follow."),
    ("explain", "Explain",
     "Explain opens a drawer with the governing equations, this case's numbers and a "
     "plain-language note for whatever you selected."),
    ("offdesign", "Off-design",
     "The Off-design tab flies the frozen design at other Mach numbers: spillage, recovery "
     "and the cowl margin along the whole range."),
)


def tour_done():
    return bool(app_settings().value("tour/done", False, type=bool))


class TourOverlay(DimOverlay):
    def __init__(self, window):
        super().__init__(window)
        self.setObjectName("tourOverlay")
        self.step = 0
        self.card.setFixedWidth(CARD_W)
        v = QVBoxLayout(self.card)
        v.setContentsMargins(tokens.space(2), tokens.space(2), tokens.space(2), tokens.space(2))
        v.setSpacing(tokens.space(1))
        self.counter = QLabel()
        self.counter.setObjectName("muted")
        self.title = QLabel()
        self.title.setObjectName("overlayTitle")
        self.body = QLabel()
        self.body.setWordWrap(True)
        for w in (self.counter, self.title, self.body):
            w.setToolTip(tip("tour.card"))
        buttons = QHBoxLayout()
        self.skip_button = QPushButton("Skip")
        self.skip_button.setObjectName("linkButton")
        self.back_button = QPushButton("Back")
        self.next_button = QPushButton("Next")
        self.next_button.setDefault(True)
        buttons.addWidget(self.skip_button)
        buttons.addStretch(1)
        buttons.addWidget(self.back_button)
        buttons.addWidget(self.next_button)
        v.addWidget(self.counter)
        v.addWidget(self.title)
        v.addWidget(self.body)
        v.addLayout(buttons)
        self.skip_button.clicked.connect(self.skip)
        self.back_button.clicked.connect(self.back)
        self.next_button.clicked.connect(self.next)

    # --- navigation --------------------------------------------------------------------------
    def start(self):
        self.step = 0
        self.open()
        self._show_step()

    def next(self):
        if self.step >= len(STEPS) - 1:
            self.finish()
            return
        self.step += 1
        self._show_step()

    def back(self):
        if self.step > 0:
            self.step -= 1
            self._show_step()

    def skip(self):
        self.finish()

    def finish(self):
        app_settings().setValue("tour/done", True)
        self.close_overlay()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.skip()
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.next()
        elif event.key() == Qt.Key.Key_Left:
            self.back()

    # --- layout ----------------------------------------------------------------------------
    def target_rect(self, key=None):
        """Highlighted rect (window coordinates) of a step's target."""
        w = self.window_
        key = key or STEPS[self.step][0]
        if key == "canvas":
            c = w.canvas
            return QRect(c.mapTo(w, c.rect().topLeft()), c.size())
        if key == "explain":
            button = w.explain_button
            return QRect(button.mapTo(w, button.rect().topLeft()), button.size())
        bar = w.tabs.tabBar()
        r = bar.tabRect(w.tabs.indexOf(w.offdesign_tab))
        return QRect(bar.mapTo(w, r.topLeft()), r.size())

    def _show_step(self):
        key, title, body = STEPS[self.step]
        if key == "canvas":
            self.window_.tabs.setCurrentWidget(self.window_.canvas)
        self.counter.setText(f"{self.step + 1} / {len(STEPS)}")
        self.title.setText(title)
        self.body.setText(body)
        self.back_button.setEnabled(self.step > 0)
        self.next_button.setText("Finish" if self.step == len(STEPS) - 1 else "Next")
        self.relayout()

    def relayout(self):
        self.setGeometry(self.window_.rect())
        self.set_hole(self.target_rect())
        self.card.adjustSize()
        hole, area = self.hole, self.rect()
        gap = tokens.space(2)
        x = min(max(hole.left(), gap), area.width() - self.card.width() - gap)
        if hole.bottom() + gap + self.card.height() < area.height():      # below the target
            y = hole.bottom() + gap
        elif hole.top() - gap - self.card.height() > 0:                    # above it
            y = hole.top() - gap - self.card.height()
        else:                          # large target (the canvas): its bottom-right corner
            x = hole.right() - gap - self.card.width()
            y = hole.bottom() - gap - self.card.height()
        self.card.move(x, y)
        self.update()
