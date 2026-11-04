"""About Busemann (spec 4.8): what it is, model assumptions, validation evidence, licences.

The validation table comes from resources/data/validation.json (the same file the off-design
CFD overlay reads); licences from resources/licenses (components.json + the bundled texts),
with versions and declared licences read from the installed package metadata.
"""
import html
import importlib.metadata as md
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QListWidget,
    QScrollArea, QTableWidget, QTableWidgetItem, QTextBrowser, QToolButton, QVBoxLayout,
    QWidget,
)

from .. import __version__
from ..charts.model import load_validation
from ..paths import resource_path
from ..theme import tokens



def components():
    return json.loads(resource_path("licenses", "components.json").read_text(encoding="utf-8"))[
        "components"]


def installed(dist):
    """(version, declared licence) from the installed package metadata, or (None, None)."""
    if not dist:
        return None, None
    try:
        meta = md.metadata(dist)
    except md.PackageNotFoundError:
        return None, None
    declared = meta.get("License-Expression")
    if not declared:
        classifiers = [c.split("::")[-1].strip() for c in (meta.get_all("Classifier") or [])
                       if c.startswith("License ::")]
        declared = "; ".join(classifiers) or (meta.get("License") or "").splitlines()[0]
    return meta.get("Version"), declared


def doc_link(rel, repository):
    """Local file link when the docs sit next to the source tree, else the GitHub page."""
    local = Path(__file__).resolve().parents[3] / rel
    if local.exists():
        return local.as_uri()
    return f"{repository}/blob/main/{rel}"


ABOUT_TEXT = (
    "I made Busemann to design the ramps of a two-dimensional supersonic inlet and see what "
    "its shocks do. You give it a flight Mach number and the air it flies in; it finds the ramp "
    "angles (or takes yours), draws the shock system and shows the pressure recovery, the mass "
    "capture and the flow in every region. It does the same for the fixed inlet at other Mach "
    "numbers.")
MAKER_TEXT = "Who made it and why: [your words here]"
ABOUT_ASSUMPTIONS = (
    "Two-dimensional, steady, inviscid flow of a calorically perfect gas (constant γ).",
    "Straight attached shocks: the ramp shocks meet at the cowl lip at the design Mach, and a "
    "normal shock at the throat makes the flow subsonic.",
    "Not modelled: boundary layers, the cowl's own shock and its reflections, and the "
    "subsonic diffuser. Above the design Mach the recovery is an upper bound.",
)


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("aboutDialog")
        self.setWindowTitle("About Busemann")
        self.resize(680, 620)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(tokens.space(3), tokens.space(2), tokens.space(3), tokens.space(2))
        v.setSpacing(tokens.space(1))
        v.addWidget(self._about_section())
        v.addWidget(self._heading("How it was checked"))
        v.addWidget(self._validation_tab())
        self.licences_toggle = QToolButton()
        self.licences_toggle.setObjectName("sectionToggle")
        self.licences_toggle.setCheckable(True)
        self.licences_toggle.setText("Licences ▸")
        self.licences_toggle.setToolTip("Show the licences of the components Busemann uses.")
        self.licences = self._licences_tab()
        self.licences.hide()
        self.licences_toggle.toggled.connect(self._show_licences)
        v.addWidget(self.licences_toggle)
        v.addWidget(self.licences, 1)
        v.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout = QVBoxLayout(self)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)

    @staticmethod
    def _heading(text):
        label = QLabel(text)
        label.setObjectName("drawerTitle")
        label.setToolTip(text)
        return label

    def _show_licences(self, on):
        self.licences.setVisible(on)
        self.licences_toggle.setText("Licences" if on else "Licences ▸")

    def _about_section(self):
        items = "".join(f"<li>{html.escape(a)}</li>" for a in ABOUT_ASSUMPTIONS)
        text = QLabel(
            f"<h2 style='margin-bottom:2px'>Busemann {html.escape(__version__)}</h2>"
            f"<p>{html.escape(ABOUT_TEXT)}</p>"
            f"<p><i>{html.escape(MAKER_TEXT)}</i></p>"
            f"<p><b>What it assumes</b></p><ul>{items}</ul>")
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setAlignment(Qt.AlignmentFlag.AlignTop)
        text.setToolTip("What Busemann does and what it assumes.")
        self.about_label = text
        return text

    def _validation_tab(self):
        data = load_validation()
        phases = data["phases"]
        table = QTableWidget(len(phases), 3)
        table.setObjectName("validationTable")
        table.setHorizontalHeaderLabels(["Phase", "Case", "Result"])
        for c, tip in enumerate(("Validation phase", "What was compared",
                                 "Difference between CFD and the tool")):
            table.horizontalHeaderItem(c).setToolTip(tip)
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setWordWrap(True)
        for r, ph in enumerate(phases):
            for c, text in enumerate((ph["id"], ph["title"], ph["result"])):
                item = QTableWidgetItem(text)
                item.setToolTip(ph.get("explanation", ph["result"]))
                table.setItem(r, c, item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.resizeRowsToContents()
        self.validation_table = table
        explained = [ph for ph in phases if ph.get("explanation")]
        notes = "".join(f"<p><b>{html.escape(ph['title'])}:</b> {html.escape(ph['explanation'])}"
                        "</p>" for ph in explained)
        repo = data["repository"]
        links = " · ".join(
            f"<a href='{doc_link(rel, repo)}'>{html.escape(rel)}</a>"
            for rel in ("docs/validation_3b.md", "docs/validation_3d.md"))
        info = QLabel(f"{notes}<p>Reports: {links}</p>")
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.RichText)
        info.setOpenExternalLinks(True)
        info.setToolTip("Why the above-design case differs, and the full validation reports.")
        self.validation_info = info
        table.setMinimumHeight(table.verticalHeader().length()
                               + table.horizontalHeader().height() + 6)
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(table)
        v.addWidget(info)
        return page

    def _licences_tab(self):
        self.licence_list = QListWidget()
        self.licence_list.setToolTip("Third-party components shipped with Busemann.")
        self.licence_text = QTextBrowser()
        self.licence_text.setObjectName("licenceText")
        self.licence_rows = []
        for comp in components():
            version, declared = installed(comp["dist"])
            label = f"{comp['name']}" + (f" {version}" if version else "") + \
                f" — {comp['license']}"
            self.licence_list.addItem(label)
            self.licence_rows.append(dict(comp, version=version, declared=declared))
        self.licence_list.currentRowChanged.connect(self._show_licence)
        self.licence_list.setCurrentRow(0)
        self.licence_list.setMaximumWidth(tokens.space(36))
        own = QLabel("Busemann's own source code: no licence has been chosen yet.")
        own.setObjectName("muted")
        own.setToolTip("The repository does not contain a LICENSE file for Busemann itself.")
        self.licence_text.setMinimumHeight(tokens.space(30))
        page = QWidget()
        h = QHBoxLayout()
        h.addWidget(self.licence_list)
        h.addWidget(self.licence_text, 1)
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.addLayout(h, 1)
        v.addWidget(own)
        return page

    def _show_licence(self, row):
        if row < 0:
            return
        comp = self.licence_rows[row]
        texts = [resource_path("licenses", f).read_text(encoding="utf-8", errors="replace")
                 for f in comp["files"]]
        head = (f"{comp['name']} {comp['version'] or ''}\nLicence: {comp['license']}\n"
                + (f"Package metadata: {comp['declared']}\n" if comp["declared"] else "")
                + (f"{comp['note']}\n" if comp["note"] else ""))
        self.licence_text.setPlainText(head + "\n" + ("\n\n" + "=" * 72 + "\n\n").join(texts))
