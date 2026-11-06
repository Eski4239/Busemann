"""Reusable themed widgets."""
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QLabel

from ..theme import qt as theme
from ..tooltips import tip
from .collapsible import CollapsibleSection
from .kpi_card import KpiCard
from .labeled_slider import LabeledSlider
from .number_field import NumberField
from .segmented import SegmentedControl
from .spin_field import SpinField


def section_title(text, key):
    """Section heading; `key` names its tooltip in tooltips.json."""
    label = QLabel(theme.caps(text))
    label.setToolTip(tip(key))
    label.setObjectName("sectionTitle")
    label.setFont(theme.label_font(QFont.Weight.DemiBold))
    return label


def field_label(text, key):
    """Uppercase field label; `key` names its tooltip in tooltips.json."""
    label = QLabel(theme.caps(text))
    label.setObjectName("fieldLabel")
    label.setFont(theme.label_font())
    label.setToolTip(tip(key))
    return label


def divider():
    line = QFrame()
    line.setObjectName("divider")
    line.setFrameShape(QFrame.Shape.NoFrame)
    return line


__all__ = [
    "CollapsibleSection", "KpiCard", "LabeledSlider", "NumberField", "SegmentedControl", "SpinField",
    "section_title", "field_label", "divider",
]
