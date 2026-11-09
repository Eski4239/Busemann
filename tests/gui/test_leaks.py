"""Regression guard for three confirmed leaks that made a pytest session running hundreds of
MainWindows progressively slower:
  1. load_fonts() re-registered the bundled fonts with Qt on every setup_application() call
     instead of once (src/busemann/theme/qt.py).
  2. MainWindow.__init__ reconnected app.aboutToQuit on every window instead of once
     (src/busemann/app.py, now done in setup_application()).
  3. MainWindow never set WA_DeleteOnClose, so close() only hid the window — the object (and
     every lambda that captured `self` when connecting a signal in __init__) stayed alive for
     the rest of the process (src/busemann/app.py).
"""
import gc
import weakref

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

import shiboken6  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

pytestmark = pytest.mark.gui

BATCH = 20


def test_opening_and_closing_many_windows_does_not_leak(qtbot):
    from busemann.app import MainWindow, setup_application

    app = QApplication.instance()
    setup_application(app)
    font_calls = []
    orig_add = QFontDatabase.addApplicationFontFromData

    def _counted(data):
        font_calls.append(1)
        return orig_add(data)

    QFontDatabase.addApplicationFontFromData = staticmethod(_counted)
    try:
        for _ in range(BATCH):
            setup_application(app)
            win = MainWindow()
            win.project.ask_save = lambda: "discard"
            win.show()
            qtbot.waitUntil(lambda: win.state.design is not None, timeout=5000)
            ref = weakref.ref(win)
            win.project.ask_save = lambda: "discard"
            win.close()
            win.state.shutdown()
            del win
            app.processEvents()      # let the deferred WA_DeleteOnClose delete run
            gc.collect()
            survivor = ref()
            assert survivor is None or not shiboken6.isValid(survivor), (
                "a MainWindow survived close() + gc.collect()")
    finally:
        QFontDatabase.addApplicationFontFromData = orig_add

    # setup_application() ran BATCH + 1 times (once above, once per loop); fonts must have
    # been registered exactly once, not once per call.
    assert len(font_calls) == 0, (
        f"load_fonts() re-registered fonts after the first setup_application() call "
        f"({len(font_calls)} extra QFontDatabase.addApplicationFontFromData calls)")
