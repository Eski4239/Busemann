"""Welcome window (addendum A/B1): modal, before the main window.

Left: "New design" preset cards. Right: Open…, Recent (8) with design Mach, ramps and date,
and the bundled examples. A "Show tour" checkbox is checked on the first launch only.
`choice` after exec(): ("preset", name) | ("blank",) | ("open", path) | ("example", path) | None
(Esc / close: the default design).
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QToolButton, QVBoxLayout, QWidget,
)

from inletdesign.presets import get as get_preset

from .. import project as P
from ..paths import resource_path
from ..settings import app_settings
from ..theme import tokens
from ..tooltips import tip
from ..widgets import section_title

PRESET_ORDER = ("Validation case", "Concorde cruise", "XB-70", "SR-71", "X-15 record")
EXAMPLES = (("validation_case", "Validation case", "M 3.00 · 2 ramps · Phase 3 CFD freestream"),
            ("x15_four_ramp", "X-15, 4 ramps", "M 6.70 · real-gas warning"),
            ("m3_cowl_constrained", "Cowl-constrained M3", "M 3.00 · 3 ramps · max cowl 30°"))
MAX_RECENT = 8


def preset_subtitle(name):
    p = get_preset(name)
    if p.mode == "altitude":
        return f"M {p.mach:.2f} · {p.altitude_m / 1000:.1f} km"
    return f"M {p.mach:.2f} · {p.p_pa / 1000:.1f} kPa, {p.T_k:.0f} K"


def recent_entry(path):
    """(title, subtitle, readable) for a recent project file."""
    path = Path(path)
    try:
        inputs, _, _ = P.load(path)
        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
        ramps = f"{inputs.n_ramps} ramp" + ("s" if inputs.n_ramps != 1 else "")
        return path.name, f"M {inputs.mach:.2f} · {ramps} · {date}", True
    except (P.ProjectError, OSError):
        return path.name, "cannot be read", False


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("welcomeDialog")
        self.setWindowTitle("Busemann")
        self.setModal(True)
        self.resize(880, 560)
        self.setAcceptDrops(True)
        self.choice = None
        self.settings = app_settings()

        # left: new design
        left = QVBoxLayout()
        left.addWidget(section_title("New design", "section.welcome_new"))
        grid = QGridLayout()
        grid.setSpacing(tokens.space(1))
        self.cards = []
        cards = [(name, preset_subtitle(name), ("preset", name)) for name in PRESET_ORDER]
        cards.append(("Blank (defaults)", "M 3.00 · 20.0 km", ("blank",)))
        for k, (title, sub, choice) in enumerate(cards):
            card = QToolButton()
            card.setObjectName("presetCard")
            card.setText(f"{title}\n{sub}")
            card.setToolTip(tip("welcome.preset"))
            card.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            card.setMinimumSize(QSize(tokens.space(24), tokens.space(8)))
            card.clicked.connect(lambda *_, c=choice: self._choose(c))
            grid.addWidget(card, k // 2, k % 2)
            self.cards.append((title, card))
        left.addLayout(grid)
        left.addStretch(1)

        # right: open, recent, examples
        right = QVBoxLayout()
        self.open_button = QPushButton("Open…")
        self.open_button.setToolTip(tip("welcome.open"))
        self.open_button.clicked.connect(self._open)
        right.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignLeft)
        right.addWidget(section_title("Recent", "section.welcome_recent"))
        self.recent_list = self._list("welcome.recent")
        recent = self.settings.value("project/recent", [])
        recent = [recent] if isinstance(recent, str) else list(recent or [])
        for path in recent[:MAX_RECENT]:
            title, sub, ok = recent_entry(path)
            item = self._item(self.recent_list, title, sub, ("open", str(path)))
            if not ok:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        if not recent:
            self._item(self.recent_list, "No recent projects", "", None).setFlags(
                Qt.ItemFlag.NoItemFlags)
        right.addWidget(self.recent_list, 1)
        right.addWidget(section_title("Examples", "section.welcome_examples"))
        self.example_list = self._list("welcome.example")
        for stem, title, sub in EXAMPLES:
            self._item(self.example_list, title, sub,
                       ("example", str(resource_path("examples", f"{stem}.busemann"))))
        rows = self.example_list.sizeHintForRow(0) * self.example_list.count()
        self.example_list.setFixedHeight(rows + 2 * self.example_list.frameWidth() + 2)
        right.addWidget(self.example_list)

        columns = QHBoxLayout()
        columns.setSpacing(tokens.space(3))
        columns.addLayout(left, 3)
        columns.addLayout(right, 2)

        # bottom
        first_launch = not self.settings.value("welcome/launched", False, type=bool)
        self.tour_check = QCheckBox("Show tour")
        self.tour_check.setToolTip(tip("welcome.tour"))
        self.tour_check.setChecked(first_launch)
        bottom = QHBoxLayout()
        bottom.addWidget(self.tour_check)
        bottom.addStretch(1)
        hint = QLabel("Esc opens the default design. You can also drop a .busemann file here.")
        hint.setObjectName("muted")
        hint.setToolTip(tip("welcome.hint"))
        bottom.addWidget(hint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(3), tokens.space(3), tokens.space(3),
                                  tokens.space(2))
        layout.setSpacing(tokens.space(2))
        title = QLabel("Busemann")
        title.setObjectName("welcomeTitle")
        title.setToolTip(tip("welcome.title"))
        layout.addWidget(title)
        layout.addLayout(columns, 1)
        layout.addLayout(bottom)

    def _list(self, tip_key):
        lst = QListWidget()
        lst.setObjectName("welcomeList")
        lst.setToolTip(tip(tip_key))
        lst.itemActivated.connect(self._activated)
        lst.itemClicked.connect(self._activated)
        return lst

    def _item(self, lst, title, sub, choice):
        item = QListWidgetItem(f"{title}\n{sub}" if sub else title)
        item.setData(Qt.ItemDataRole.UserRole, choice)
        item.setToolTip(choice[1] if choice and choice[0] in ("open",) else title)
        lst.addItem(item)
        return item

    def _activated(self, item):
        choice = item.data(Qt.ItemDataRole.UserRole)
        if choice and item.flags() & Qt.ItemFlag.ItemIsEnabled:
            self._choose(tuple(choice))

    def _open(self):
        start = str(self.settings.value("project/last_dir", str(Path.home())))
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start,
                                              "Busemann project (*.busemann)")
        if path:
            self._choose(("open", path))

    def _choose(self, choice):
        self.choice = choice
        self.accept()

    def done(self, result):
        self.settings.setValue("welcome/launched", True)
        super().done(result)

    def reject(self):
        self.choice = None
        super().reject()

    # --- drop a project file -------------------------------------------------------------
    @staticmethod
    def _dropped(mime):
        urls = [u for u in mime.urls() if u.isLocalFile()] if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".busemann"):
            return urls[0].toLocalFile()
        return None

    def dragEnterEvent(self, event):
        if self._dropped(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._dropped(event.mimeData())
        if path:
            event.acceptProposedAction()
            self._choose(("open", path))


def apply_choice(window, choice):
    """Apply a welcome-window choice to the main window's state."""
    import dataclasses

    from ..inputs import Inputs, preset_changes

    project = window.project
    if choice is None:
        return
    kind = choice[0]
    if kind == "preset":
        project.start_from(dataclasses.replace(Inputs(), **preset_changes(choice[1])),
                           f"preset {choice[1]}")
    elif kind == "blank":
        project.start_from(Inputs())
    elif kind == "open":
        project.open_path(choice[1], ask=False)
    elif kind == "example":
        project.open_example(choice[1])

