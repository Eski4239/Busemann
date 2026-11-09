"""Windows display scaling (M3.1): the main window at 150 % has no clipped widgets.

QT_SCALE_FACTOR must be set before the QApplication exists and pytest-qt shares one app per
session, so the window is built in a subprocess (scaling_probe.py) and reports JSON.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

pytestmark = pytest.mark.gui
PROBE = Path(__file__).with_name("scaling_probe.py")


@pytest.mark.ui
@pytest.mark.parametrize("scale", ["1.25", "1.5"])
def test_main_window_not_clipped_at_display_scale(window, scale):
    # `window` fixture only to reuse its platform-availability skip
    env = dict(os.environ, QT_SCALE_FACTOR=scale, QT_QPA_PLATFORM="offscreen")
    out = subprocess.run([sys.executable, str(PROBE)], env=env, capture_output=True, text=True,
                         timeout=120)
    assert out.returncode == 0, out.stderr
    result = json.loads(out.stdout.strip().splitlines()[-1])
    assert result["dpr"] == pytest.approx(float(scale))
    assert result["size"] == [1280, 800]           # minimum window size respected
    assert result["problems"] == []


@pytest.mark.ui
def test_probe_detects_a_clipped_widget(qtbot):
    from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

    sys.path.insert(0, str(PROBE.parent))
    try:
        from scaling_probe import clipped_widgets
    finally:
        sys.path.pop(0)
    win = QWidget()
    box = QWidget(win)
    QHBoxLayout(box).addWidget(QLabel("a label that needs far more room than it gets"))
    box.setFixedSize(40, 20)           # parent too small: the label is cut off
    qtbot.addWidget(win)
    win.show()
    assert "QLabel" in [p["widget"] for p in clipped_widgets(win)]
