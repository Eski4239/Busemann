import os

import pytest

# Headless by default; set QT_QPA_PLATFORM yourself to watch the tests run.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session", autouse=True)
def _stop_render_process():
    """The equation render process (explain.warm) is stopped at the end of the session."""
    yield
    from busemann.explain import warm

    warm.shutdown()


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Recent files / last folders go to a temporary ini, never the user's settings."""
    monkeypatch.setenv("BUSEMANN_SETTINGS_FILE", str(tmp_path / "settings.ini"))


def _platform_available():
    try:
        from PySide6.QtCore import QLibraryInfo
    except ImportError:
        return False
    name = os.environ["QT_QPA_PLATFORM"].split(":")[0]
    plugins = os.path.join(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath), "platforms")
    return os.path.isdir(plugins) and any(f.startswith(f"q{name}") for f in os.listdir(plugins))


@pytest.fixture
def window(qtbot):
    if not _platform_available():
        pytest.skip(f"Qt platform {os.environ['QT_QPA_PLATFORM']!r} unavailable")
    from PySide6.QtWidgets import QApplication

    from busemann.app import MainWindow, setup_application

    setup_application(QApplication.instance())
    win = MainWindow()
    # pytest-qt closes widgets before fixture teardown: never block on the save prompt
    win.project.ask_save = lambda: "discard"
    qtbot.addWidget(win)
    win.resize(1440, 900)
    win.show()
    qtbot.waitUntil(lambda: win.state.design is not None, timeout=5000)
    yield win
    win.project.ask_save = lambda: "discard"      # never block on the save prompt
    win.close()                                   # stops the equation warm-up
    win.state.shutdown()
    from PySide6.QtCore import QThreadPool

    QThreadPool.globalInstance().waitForDone(10000)
