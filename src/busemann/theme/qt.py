"""Qt theme loading: bundled fonts, the QSS template filled from tokens, and tinted SVG icons."""
from importlib import resources
from string import Template

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QFont, QFontDatabase, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ..paths import resource_path
from . import tokens

_FONT_FILES = (
    "Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf",
    "JetBrainsMono-Regular.ttf", "JetBrainsMono-Medium.ttf", "JetBrainsMono-SemiBold.ttf",
)
_loaded_families = set()


def _resource(*parts):
    return resources.files("busemann").joinpath("resources", *parts)


def load_fonts():
    """Register the bundled fonts with Qt. Returns the set of family names loaded.

    Idempotent: Qt's application font database is process-wide and has no "already
    registered" check, so calling this more than once (e.g. once per MainWindow in tests)
    would re-register every font each time, growing Qt's font database without bound.
    """
    if _loaded_families:
        return set(_loaded_families)
    for name in _FONT_FILES:
        data = _resource("fonts", name).read_bytes()
        font_id = QFontDatabase.addApplicationFontFromData(QByteArray(data))
        if font_id >= 0:
            _loaded_families.update(QFontDatabase.applicationFontFamilies(font_id))
    return set(_loaded_families)


def ui_family():
    return tokens.FONT_UI if tokens.FONT_UI in _loaded_families else tokens.FONT_UI_FALLBACK


def mono_family():
    return tokens.FONT_MONO if tokens.FONT_MONO in _loaded_families else tokens.FONT_MONO_FALLBACK


def ui_font(size=tokens.SIZE_BASE, weight=QFont.Weight.Normal):
    font = QFont(ui_family())
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def label_font(weight=QFont.Weight.Medium):
    """11 px label font with 0.06 em tracking (QSS cannot set letter-spacing). Pair with caps()."""
    font = ui_font(tokens.SIZE_LABEL, weight)
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                          tokens.LABEL_TRACKING_EM * tokens.SIZE_LABEL)
    return font


def caps(text):
    """Uppercase label text, except labels containing symbols (θ1, p∞, γ): case carries meaning."""
    return text if any(ord(c) > 127 for c in text) else text.upper()


def mono_font(size=tokens.SIZE_BASE):
    font = QFont(mono_family())
    font.setPixelSize(size)
    font.setStyleHint(QFont.StyleHint.Monospace)
    return font


def stylesheet():
    text = _resource_text("theme", "style.qss.tmpl")
    values = dict(tokens.COLORS)
    values.update(
        font_ui=ui_family(), font_ui_fallback=tokens.FONT_UI_FALLBACK,
        font_mono=mono_family(), font_mono_fallback=tokens.FONT_MONO_FALLBACK,
        size_base=tokens.SIZE_BASE, size_label=tokens.SIZE_LABEL, size_kpi=tokens.SIZE_KPI,
        radius=tokens.RADIUS, border_w=tokens.BORDER,
        s1=tokens.space(1), s2=tokens.space(2), s3=tokens.space(3),
        # QSS url() needs a file: a copy pre-tinted with text_muted ships in resources/icons
        # (a test keeps its colour equal to the token).
        chevron_down=resource_path("icons", "chevron-down-muted.svg").as_posix(),
        chevron_right=resource_path("icons", "chevron-right-muted.svg").as_posix(),
        chevron_up=resource_path("icons", "chevron-up-muted.svg").as_posix(),
    )
    return Template(text).substitute(values)


def _resource_text(*parts):
    return resources.files("busemann").joinpath(*parts).read_text(encoding="utf-8")


def icon(name, color="text", size=20):
    """QIcon from resources/icons/<name>.svg; currentColor -> token `color`, {{token}} -> that token."""
    svg = _resource("icons", f"{name}.svg").read_text(encoding="utf-8")
    svg = svg.replace("currentColor", tokens.COLORS[color])
    for key, value in tokens.COLORS.items():
        svg = svg.replace("{{" + key + "}}", value)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    result = QIcon()
    for scale in (1, 1.25, 1.5, 2):      # crisp at 100/125/150/200 % display scaling
        pixmap = QPixmap(QSize(round(size * scale), round(size * scale)))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    return result


def apply(app):
    """Load fonts, set the default font and the stylesheet on a QApplication."""
    load_fonts()
    app.setFont(ui_font())
    app.setStyleSheet(stylesheet())
