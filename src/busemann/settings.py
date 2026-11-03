"""Persistent app settings (recent projects, last export folder).

Native QSettings by default; BUSEMANN_SETTINGS_FILE=<path.ini> redirects them (tests use a
temporary file so they never touch the user's settings)."""
import os

from PySide6.QtCore import QSettings


def app_settings():
    path = os.environ.get("BUSEMANN_SETTINGS_FILE")
    if path:
        return QSettings(path, QSettings.Format.IniFormat)
    return QSettings("Busemann", "Busemann")
