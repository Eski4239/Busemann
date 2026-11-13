"""About Busemann (spec 4.8): what it is, model assumptions, how it was checked, licences.

Licences from resources/licenses (components.json + the bundled texts),
with versions and declared licences read from the installed package metadata.
"""
import html
import importlib.metadata as md
import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QScrollArea, QTextBrowser,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import __version__
from .. import verification as V
from ..paths import resource_path
from ..theme import qt as theme
from ..theme import tokens

LOGO, LOGO_FALLBACK, LOGO_H = "logo_lockup", "logo_lockup_2x.png", 40
OWN_LICENCE = "Busemann itself: MIT License, Copyright (c) 2026 Pablo Goulet Valenti."

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


ABOUT_TEXT = (
    "I made Busemann to design the ramps of a two-dimensional supersonic inlet and see what "
    "its shocks do. You give it a flight Mach number and the air it flies in; it finds the ramp "
    "angles (or takes yours), draws the shock system and shows the pressure recovery, the mass "
    "capture and the flow in every region. It does the same for the fixed inlet at other Mach "
    "numbers.")
MAKER_TEXT = (
    "My name is Pablo Goulet Valenti and I made this during my university years in order to "
    "explore the world of high-speed flows. Inlets are a key part of powerplants and propulsion "
    "systems, and being able to build an interactive solver to design these geometries allows "
    "one to learn quite a bit. I hope this tool is useful to you and you learn something new "
    "along the way too!")
VALIDATION_TEXT = V.VALIDATION_SUMMARY
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
        self.setWindowIcon(theme.app_icon())
        self.resize(680, 620)
        body = QWidget()
        v = QVBoxLayout(body)
        v.setContentsMargins(tokens.space(3), tokens.space(2), tokens.space(3), tokens.space(2))
        v.setSpacing(tokens.space(1))
        v.addWidget(self._about_section())
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

    def _show_licences(self, on):
        self.licences.setVisible(on)
        self.licences_toggle.setText("Licences" if on else "Licences ▸")

    def _about_section(self):
        items = "".join(f"<li>{html.escape(a)}</li>" for a in ABOUT_ASSUMPTIONS)
        self.logo = QLabel()
        self.logo.setObjectName("aboutLogo")
        self.logo.setAccessibleName("Busemann — supersonic inlet design lab")
        self.logo.setPixmap(theme.svg_pixmap(
            LOGO, LOGO_H, max(self.devicePixelRatioF() or 1.0, 2.0), fallback=LOGO_FALLBACK))
        self.version_label = QLabel(f"Version {__version__}")
        self.version_label.setObjectName("aboutVersion")
        self.version_label.setFont(theme.mono_font(tokens.SIZE_LABEL))
        text = QLabel(
            f"<p>{html.escape(ABOUT_TEXT)}</p>"
            f"<p><b>Who made it and why</b></p><p>{html.escape(MAKER_TEXT)}</p>"
            f"<p><b>What it assumes</b></p><ul>{items}</ul>")
        text.setWordWrap(True)
        text.setTextFormat(Qt.TextFormat.RichText)
        text.setAlignment(Qt.AlignmentFlag.AlignTop)
        text.setToolTip("What Busemann does and what it assumes.")
        self.about_label = text
        section = QWidget()
        v = QVBoxLayout(section)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        v.addWidget(self.logo)
        v.addWidget(self.version_label)
        v.addSpacing(tokens.space(1))
        v.addWidget(text)
        return section

    def _validation_tab(self):
        info = QLabel(VALIDATION_TEXT)
        info.setWordWrap(True)
        info.setTextFormat(Qt.TextFormat.PlainText)
        info.setToolTip("How the solver was checked against closed-form values and CFD.")
        self.validation_info = info
        return info

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
        own = QLabel(OWN_LICENCE)
        own.setObjectName("muted")
        own.setToolTip("Busemann itself is open source under the MIT License (LICENSE file in "
                       "the install folder and the repository).")
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
