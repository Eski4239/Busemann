"""Brand assets in the app (M12 PART 1): window / taskbar icon, welcome header and image,
About heading."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QSize  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from busemann.theme import qt as theme  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture
def app(qtbot):
    from busemann.app import setup_application

    return setup_application(QApplication.instance())


def _same_icon(icon):
    return icon.cacheKey() == theme.app_icon().cacheKey()


def test_app_icon_has_every_size(app):
    icon = theme.app_icon()
    sizes = {(s.width(), s.height()) for s in icon.availableSizes()}
    assert sizes == {(n, n) for n in theme.APP_ICON_SIZES}
    assert theme.APP_ICON_SIZES == (16, 24, 32, 48, 64, 128, 256)
    for n in theme.APP_ICON_SIZES:                     # each size is its own crisp bitmap
        assert icon.pixmap(QSize(n, n), 1.0).size() == QSize(n, n)


def test_icon_is_set_on_the_app_and_every_top_level_window(qtbot, window):
    from busemann.views.welcome_dialog import WelcomeDialog

    assert _same_icon(QApplication.instance().windowIcon())
    assert _same_icon(window.windowIcon())
    about = window.show_about()
    qtbot.addWidget(about)
    iso = window.show_isentropic_ramp()
    welcome = WelcomeDialog()
    qtbot.addWidget(welcome)
    window.explain_action.setChecked(True)
    popup = window.explain_drawer.popup
    for w in (about, iso, welcome, popup):
        assert _same_icon(w.windowIcon()), type(w).__name__
    window.explain_action.setChecked(False)
    about.close()
    iso.close()


def test_welcome_hero_loads_at_dpr_2(qtbot, app):
    from busemann.views import welcome_dialog as W

    dialog = W.WelcomeDialog()
    qtbot.addWidget(dialog)
    pm = dialog.pixmap              # what is set (QLabel.pixmap() is a copy at the screen DPR)
    assert not pm.isNull() and pm.devicePixelRatio() >= 2.0
    assert pm.size() == QSize(520, 330)                  # 2x pixels from the 1040 px file
    assert pm.deviceIndependentSize().toSize() == QSize(260, 165)
    assert dialog.image.size() == QSize(260, 165)
    corner = pm.toImage().pixelColor(0, 0)
    assert corner.alpha() == 0                           # rounded 6 px corner is transparent


def test_logo_lockups_render(qtbot, app):
    from busemann.views import welcome_dialog as W

    for height in (34, 40):
        pm = theme.svg_pixmap("logo_lockup", height, 2.0, fallback="logo_lockup_2x.png")
        assert not pm.isNull() and pm.deviceIndependentSize().height() == pytest.approx(height)
        assert pm.width() > 3 * pm.height()               # the wide lockup, not the mark
    dialog = W.WelcomeDialog()
    qtbot.addWidget(dialog)
    assert dialog.logo.pixmap().deviceIndependentSize().height() == pytest.approx(34)


@pytest.mark.ui
def test_welcome_header_text(qtbot, app):
    from busemann import __version__
    from busemann.views import welcome_dialog as W

    dialog = W.WelcomeDialog()
    qtbot.addWidget(dialog)
    assert dialog.caption.text() == ("Concorde-style intake at Mach 2.02 — temperature field "
                                      "computed with Busemann")
    assert not hasattr(dialog, "title")                  # the lockup replaces the title text
    from PySide6.QtWidgets import QLabel

    texts = [w.text() for w in dialog.findChildren(QLabel)]
    assert f"Version {__version__}" in texts
    assert "Busemann" not in texts and "Supersonic inlet design lab" not in texts


@pytest.mark.ui
def test_about_heading_is_the_lockup(qtbot, window):
    from busemann import __version__

    dialog = window.show_about()
    qtbot.addWidget(dialog)
    assert dialog.logo.pixmap().deviceIndependentSize().height() == pytest.approx(40)
    assert dialog.version_label.text() == f"Version {__version__}"
    assert "<h2" not in dialog.about_label.text()
    dialog.close()
