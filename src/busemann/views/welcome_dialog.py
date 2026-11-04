"""Welcome window (addendum A/B1, restyled in M8): modal, before the main window.

Left header column: "Busemann", tagline, version and a small inlet drawn from the validation
design's picture data (no image file). Right: "New design" preset cards, Open…, Recent (8)
with design Mach, ramps and date, and the bundled examples. Bottom: "Show tour" (checked on
the first launch only) and "Show at startup" (default on; off skips this window).
`choice` after exec(): ("preset", name) | ("blank",) | ("open", path) | ("example", path) | None
(Esc / close: the default design).
"""
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from inletdesign.presets import get as get_preset

from .. import __version__
from .. import project as P
from ..paths import resource_path
from ..settings import app_settings
from ..theme import qt as theme
from ..theme import tokens
from ..tooltips import tip
from ..widgets import section_title

PRESET_ORDER = ("Validation case", "Concorde cruise", "XB-70", "SR-71", "X-15 record")
EXAMPLES = (("validation_case", "Validation case", "M 3.00 · 2 ramps · Phase 3 CFD freestream"),
            ("x15_four_ramp", "X-15, 4 ramps", "M 6.70 · real-gas warning"),
            ("m3_cowl_constrained", "Cowl-constrained M3", "M 3.00 · 3 ramps · max cowl 30°"))
MAX_RECENT = 8
RECENT_EMPTY = "No recent projects yet. Open a .busemann file or start from a preset."
SHOW_KEY = "welcome/show"


def show_at_startup():
    """The "Show at startup" setting (default on)."""
    return app_settings().value(SHOW_KEY, True, type=bool)


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


class InletThumbnail(QWidget):
    """The validation design (M 3, 2 ramps; the geometry does not depend on p, T) drawn from
    its picture data: Mach-class region fills, walls, amber shocks. QPainter, no image file."""

    def __init__(self, parent=None):
        super().__init__(parent)
        from inletdesign import api

        from ..canvas import colors as Col
        from ..canvas import picture as Pic

        self.setObjectName("inletThumbnail")
        self.setToolTip(tip("welcome.thumbnail"))
        self.setMinimumSize(QSize(tokens.space(24), tokens.space(14)))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.picture = Pic.build(Pic.skeleton_from(api.design(3.0, 2)))
        regions = self.picture.regions
        edges = Pic.mach_bins(min(r.state.M for r in regions), self.picture.skeleton.regions[0].M)
        fills = Col.bin_colors(edges)
        self.region_fills = [fills[Pic.bin_index(r.state.M, edges)] for r in regions]

    def sizeHint(self):
        return QSize(tokens.space(26), tokens.space(15))

    def _transform(self):
        x0, y0, x1, y1 = self.picture.bounds()
        pad = 2
        w, h = self.width() - 2 * pad, self.height() - 2 * pad
        s = min(w / (x1 - x0), h / (y1 - y0))
        ox = pad + (w - s * (x1 - x0)) / 2 - s * x0
        oy = pad + (h - s * (y1 - y0)) / 2 + s * y1
        return lambda p: QPointF(ox + s * p[0], oy - s * p[1])

    def paintEvent(self, event):
        to = self._transform()
        pic = self.picture
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        for region, fill in zip(pic.regions, self.region_fills):
            painter.setBrush(QColor(fill))
            painter.drawPolygon(QPolygonF([to(p) for p in region.polygon]))
        wall = QColor(tokens.COLORS["wall"])
        painter.setBrush(wall)
        painter.drawPolygon(QPolygonF([to(p) for p in pic.cowl_body]))
        path = QPainterPath(to(pic.ramp_surface[0]))
        for p in pic.ramp_surface[1:]:
            path.lineTo(to(p))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(wall, 2.0))
        painter.drawPath(path)
        for shock in pic.shocks:
            pen = QPen(QColor(tokens.COLORS["shock"]), 1.5)
            if shock.kind == "normal":
                pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(to(shock.start), to(shock.end))
        painter.end()


class PresetCard(QFrame):
    """Preset card: left-aligned title (Inter Medium) over a JetBrains Mono subtitle; 1 px
    border, accent on hover and on keyboard focus; click, Enter or Space activates."""

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

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and \
                self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

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
        self.setModal(True)
        self.resize(940, 580)
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
        grid = QGridLayout()
        grid.setSpacing(tokens.space(1))
        self.cards = []
        cards = [(name, preset_subtitle(name), ("preset", name)) for name in PRESET_ORDER]
        cards.append(("Blank (defaults)", "M 3.00 · 20.0 km", ("blank",)))
        for k, (name, sub, choice) in enumerate(cards):
            card = PresetCard(name, sub)
            card.clicked.connect(lambda c=choice: self._choose(c))
            grid.addWidget(card, k // 3, k % 3)
            self.cards.append((name, card))
        main.addLayout(grid)
        main.addSpacing(tokens.space(2))

        lists = QHBoxLayout()
        lists.setSpacing(tokens.space(2))
        lists.addLayout(self._recent_column(), 1)
        lists.addLayout(self._example_column(), 1)
        main.addLayout(lists, 1)

        first_launch = not self.settings.value("welcome/launched", False, type=bool)
        self.tour_check = QCheckBox("Show tour")
        self.tour_check.setToolTip(tip("welcome.tour"))
        self.tour_check.setChecked(first_launch)
        self.startup_check = QCheckBox("Show at startup")
        self.startup_check.setToolTip(tip("welcome.show_startup"))
        self.startup_check.setChecked(show_at_startup())
        bottom = QHBoxLayout()
        bottom.setSpacing(tokens.space(2))
        bottom.addWidget(self.tour_check)
        bottom.addWidget(self.startup_check)
        bottom.addStretch(1)
        main.addLayout(bottom)

    def _header(self):
        header = QFrame()
        header.setObjectName("welcomeHeader")
        header.setFixedWidth(tokens.space(32))
        head = QVBoxLayout(header)
        head.setContentsMargins(tokens.space(3), tokens.space(4), tokens.space(3),
                                tokens.space(2))
        head.setSpacing(4)
        title = QLabel("Busemann")
        title.setObjectName("welcomeTitle")
        title.setFont(theme.ui_font(tokens.SIZE_KPI, QFont.Weight.DemiBold))
        title.setToolTip(tip("welcome.title"))
        tagline = QLabel("Supersonic inlet design lab")
        tagline.setObjectName("welcomeTagline")
        tagline.setToolTip(tip("welcome.title"))
        version = QLabel(f"Version {__version__}")
        version.setObjectName("welcomeVersion")
        version.setFont(theme.mono_font(tokens.SIZE_LABEL))
        version.setToolTip(tip("welcome.version"))
        self.thumbnail = InletThumbnail()
        caption = QLabel("Validation case · M 3.00 · 2 ramps")
        caption.setObjectName("muted")
        caption.setToolTip(tip("welcome.thumbnail"))
        hint = QLabel("Esc opens the default design. You can also drop a .busemann file here.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        hint.setToolTip(tip("welcome.hint"))
        for w in (title, tagline, version):
            head.addWidget(w)
        head.addSpacing(tokens.space(4))
        head.addWidget(self.thumbnail)
        head.addWidget(caption)
        head.addStretch(1)
        head.addWidget(hint)
        return header

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
        else:                                   # short empty state, top-aligned
            col.addWidget(self.recent_empty)
            col.addStretch(1)
        return col

    def _example_column(self):
        col = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(section_title("Examples", "section.welcome_examples"))
        top.addStretch(1)
        spacer = QWidget()                      # aligns the list with the Recent list
        spacer.setFixedHeight(self.open_button.sizeHint().height())
        spacer.setFixedWidth(1)
        top.addWidget(spacer)
        col.addLayout(top)
        self.example_list = self._list("welcome.example")
        for stem, name, sub in EXAMPLES:
            self._item(self.example_list, name, sub,
                       ("example", str(resource_path("examples", f"{stem}.busemann"))))
        rows = self.example_list.sizeHintForRow(0) * self.example_list.count()
        self.example_list.setFixedHeight(rows + 2 * self.example_list.frameWidth() + 2)
        col.addWidget(self.example_list)
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
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start,
                                              "Busemann project (*.busemann)")
        if path:
            self._choose(("open", path))

    def _choose(self, choice):
        self.choice = choice
        self.accept()

    def done(self, result):
        self.settings.setValue("welcome/launched", True)
        self.settings.setValue(SHOW_KEY, self.startup_check.isChecked())
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
