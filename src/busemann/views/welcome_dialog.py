"""Welcome window (addendum A/B1; M8.2 layout): modal, before the main window.

Left header: the brand lockup (logo, title, tagline), the version and the welcome image
(resources/brand/welcome_hero.png, made offline by tools/brand). Right:
- "New design": the validation case and a blank design;
- "Examples": the flight presets (Concorde cruise, XB-70, SR-71, X-15 record) and the bundled
  example designs, one list;
- "Recent" (8) with design Mach, ramps and date, and Open…
"Show tour" is checked on the first launch only.
`choice` after exec(): ("preset", name) | ("blank",) | ("open", path) | ("example", path) | None
(Esc / close: the default design).
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from inletdesign.presets import get as get_preset

from .. import __version__
from .. import project as P
from ..crashlog import guarded
from ..paths import resource_path
from ..settings import app_settings
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import section_title

NEW_DESIGNS = (("Validation case", ("preset", "Validation case")),
               ("Blank (defaults)", ("blank",)))
EXAMPLE_PRESETS = ("Concorde cruise", "XB-70", "SR-71", "X-15 record")
# bundled example designs listed under the presets (the validation case and the X-15
# conditions are already a card and a preset, so their DXFs are not listed again)
EXAMPLES = (("m3_cowl_constrained", "Cowl-constrained M3", "M 3.00 · 3 ramps · max cowl 30°"),)
MAX_RECENT = 8
RECENT_EMPTY = "No recent designs yet. Open a DXF or start from a new design."
LOGO, LOGO_FALLBACK, LOGO_H = "logo_lockup", "logo_lockup_2x.png", 34   # brand lockup
HERO = "welcome_hero.png"                  # 1040 x 660, made by tools/brand
HERO_SIZE, HERO_DPR, HERO_RADIUS = (260, 165), 2.0, 6
HERO_CAPTION = "Concorde-style intake at Mach 2.02 — temperature field computed with Busemann"
HEADER_W = 320


def preset_subtitle(name):
    p = get_preset(name)
    if p.mode == "altitude":
        return f"M {p.mach:.2f} · {p.altitude_m / 1000:.1f} km"
    return f"M {p.mach:.2f} · {p.p_pa / 1000:.1f} kPa, {p.T_k:.0f} K"


def recent_entry(path):
    """(title, subtitle, readable) for a recent design file."""
    path = Path(path)
    try:
        loaded = P.load(path)
        inputs = loaded[0]
        date = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
        ramps = f"{inputs.n_ramps} ramp" + ("s" if inputs.n_ramps != 1 else "")
        what = "imported geometry · " if loaded.imported else f"M {inputs.mach:.2f} · "
        return path.name, f"{what}{ramps} · {date}", True
    except (P.ProjectError, OSError):
        return path.name, "cannot be read", False


class PresetCard(QFrame):
    """Card: left-aligned title (Inter Medium) over a JetBrains Mono subtitle; 1 px border,
    accent on hover and on keyboard focus; click, Enter or Space activates."""

    clicked = Signal()

    def __init__(self, title, subtitle, parent=None):
        super().__init__(parent)
        self.setObjectName("presetCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setToolTip(tip("welcome.preset"))
        self.title_label = QLabel(title)
        self.title_label.setObjectName("presetTitle")
        self.title_label.setFont(theme.ui_font(tokens.SIZE_BASE, QFont.Weight.Medium))
        self.sub_label = QLabel(subtitle)
        self.sub_label.setObjectName("presetSub")
        self.sub_label.setFont(theme.mono_font(tokens.SIZE_LABEL))
        for label in (self.title_label, self.sub_label):
            label.setToolTip(self.toolTip())
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.space(2), 12, tokens.space(2), 12)
        layout.setSpacing(2)
        layout.addWidget(self.title_label)
        layout.addWidget(self.sub_label)

    def text(self):
        return f"{self.title_label.text()}\n{self.sub_label.text()}"

    def click(self):
        self.clicked.emit()

    @guarded()
    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and \
                self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    @guarded()
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class WelcomeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("welcomeDialog")
        self.setWindowTitle("Busemann")
        self.setWindowIcon(theme.app_icon())
        self.setModal(True)
        self.resize(980, 600)
        self.setAcceptDrops(True)
        self.choice = None
        self.settings = app_settings()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._header())
        body = QWidget()
        body.setObjectName("welcomeBody")
        layout.addWidget(body, 1)

        main = QVBoxLayout(body)
        main.setContentsMargins(tokens.space(3), tokens.space(3), tokens.space(3),
                                tokens.space(2))
        main.setSpacing(tokens.space(1))
        main.addWidget(section_title("New design", "section.welcome_new"))
        row = QHBoxLayout()
        row.setSpacing(tokens.space(1))
        self.cards = []
        for name, choice in NEW_DESIGNS:
            sub = preset_subtitle(name) if choice[0] == "preset" else "M 3.00 · 20.0 km"
            card = PresetCard(name, sub)
            card.clicked.connect(lambda c=choice: self._choose(c))
            row.addWidget(card, 1)
            self.cards.append((name, card))
        main.addLayout(row)
        main.addSpacing(tokens.space(2))

        lists = QHBoxLayout()
        lists.setSpacing(tokens.space(2))
        lists.addLayout(self._example_column(), 1)
        lists.addLayout(self._recent_column(), 1)
        main.addLayout(lists, 1)

        first_launch = not self.settings.value("welcome/launched", False, type=bool)
        self.tour_check = QCheckBox("Show tour")
        self.tour_check.setToolTip(tip("welcome.tour"))
        self.tour_check.setChecked(first_launch)
        main.addWidget(self.tour_check)

    def _header(self):
        header = QFrame()
        header.setObjectName("welcomeHeader")
        header.setFixedWidth(HEADER_W)
        head = QVBoxLayout(header)
        head.setContentsMargins(tokens.space(3), tokens.space(4), tokens.space(3),
                                tokens.space(2))
        head.setSpacing(4)
        dpr = max(self.devicePixelRatioF() or 1.0, HERO_DPR)
        self.logo = QLabel()
        self.logo.setObjectName("welcomeLogo")
        self.logo.setAccessibleName("Busemann — supersonic inlet design lab")
        self.logo.setToolTip(tip("welcome.title"))
        self.logo.setPixmap(theme.svg_pixmap(LOGO, LOGO_H, dpr, fallback=LOGO_FALLBACK))
        version = QLabel(f"Version {__version__}")
        version.setObjectName("welcomeVersion")
        version.setFont(theme.mono_font(tokens.SIZE_LABEL))
        version.setToolTip(tip("welcome.version"))
        self.image = QLabel()
        self.image.setObjectName("heroImage")
        self.image.setToolTip(tip("welcome.thumbnail"))
        self.pixmap = theme.rounded_pixmap(HERO, *HERO_SIZE, HERO_RADIUS, dpr)
        self.image.setPixmap(self.pixmap)
        self.image.setFixedSize(*HERO_SIZE)
        caption = QLabel(HERO_CAPTION)
        caption.setObjectName("heroCaption")
        caption.setWordWrap(True)
        caption.setFixedWidth(HERO_SIZE[0])
        caption.setToolTip(tip("welcome.thumbnail"))
        self.caption = caption
        hint = QLabel("Esc opens the default design. You can also drop a DXF here.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setToolTip(tip("welcome.hint"))
        head.addWidget(self.logo)
        head.addWidget(version)
        head.addSpacing(tokens.space(4))
        head.addWidget(self.image)
        head.addWidget(caption)
        head.addStretch(1)
        head.addWidget(hint)
        return header

    def _example_column(self):
        col = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(section_title("Examples", "section.welcome_examples"))
        top.addStretch(1)
        spacer = QWidget()                       # aligns the list with the Recent list
        spacer.setFixedSize(QSize(1, QPushButton("Open…").sizeHint().height()))
        top.addWidget(spacer)
        col.addLayout(top)
        self.example_list = self._list("welcome.example")
        for name in EXAMPLE_PRESETS:
            self._item(self.example_list, name, preset_subtitle(name), ("preset", name))
        for stem, name, sub in EXAMPLES:
            self._item(self.example_list, name, sub,
                       ("example", str(resource_path("examples", f"{stem}.dxf"))))
        col.addWidget(self.example_list, 1)
        return col

    def _recent_column(self):
        col = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(section_title("Recent", "section.welcome_recent"))
        top.addStretch(1)
        self.open_button = QPushButton("Open…")
        self.open_button.setObjectName("secondaryButton")
        self.open_button.setToolTip(tip("welcome.open"))
        self.open_button.clicked.connect(self._open)
        top.addWidget(self.open_button)
        col.addLayout(top)
        self.recent_list = self._list("welcome.recent")
        recent = self.settings.value("project/recent", [])
        recent = [recent] if isinstance(recent, str) else list(recent or [])
        for path in recent[:MAX_RECENT]:
            name, sub, ok = recent_entry(path)
            item = self._item(self.recent_list, name, sub, ("open", str(path)))
            if not ok:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
        self.recent_empty = QLabel(RECENT_EMPTY)
        self.recent_empty.setObjectName("emptyState")
        self.recent_empty.setWordWrap(True)
        self.recent_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.recent_empty.setToolTip(tip("welcome.recent_empty"))
        self.recent_empty.setMinimumHeight(tokens.space(10))
        self.recent_list.setVisible(bool(recent))
        self.recent_empty.setVisible(not recent)
        if recent:
            col.addWidget(self.recent_list, 1)
        else:                                    # short empty state, top-aligned
            col.addWidget(self.recent_empty)
            col.addStretch(1)
        return col

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
        path, _ = QFileDialog.getOpenFileName(self, "Open design", start, P.FILTER)
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

    # --- drop a design file ---------------------------------------------------------------
    @staticmethod
    def _dropped(mime):
        urls = [u for u in mime.urls() if u.isLocalFile()] if mime.hasUrls() else []
        if len(urls) == 1 and urls[0].toLocalFile().lower().endswith(".dxf"):
            return urls[0].toLocalFile()
        return None

    @guarded()
    def dragEnterEvent(self, event):
        if self._dropped(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    @guarded()
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
