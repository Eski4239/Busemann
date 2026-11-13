"""`busemann --screenshots DIR` (M12 PART 6): save the README screenshots from the real app,
including a frozen or installed build, without driving the GUI by hand.

Opens the validation case in the main window (isolated settings: the user's recent files and
welcome state are not touched), waits until every worker has finished, and saves each view
with QWidget.grab() at the screen's device-pixel ratio:

    readme_design.png       Design tab
    readme_offdesign.png    Off-design tab at M∞ 2.60, charts expanded
    readme_analytics.png    Analytics tab, recovery vs turning
    readme_isentropic.png   Tools ▸ Isentropic ramp

Prints one line per file and exits 0; non-zero with the reason if a view did not finish in
time. The windows are shown while this runs (grab() needs a laid-out, polished window).
"""
import os
import sys
import tempfile
import time
from pathlib import Path

WAIT_S = 60.0
SETTLE_S = 0.8                  # transitions (canvas animations, chart redraws) finish
MAIN_SIZE = (1440, 900)
ISENTROPIC_SIZE = (1200, 760)
OFF_DESIGN_MACH = 2.60
SHOTS = ("readme_design.png", "readme_offdesign.png", "readme_analytics.png",
         "readme_isentropic.png")


class ScreenshotError(Exception):
    pass


def _pump(app, seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.processEvents()
        time.sleep(0.01)


def _wait(app, condition, what, timeout=WAIT_S):
    end = time.perf_counter() + timeout
    while not condition():
        if time.perf_counter() > end:
            raise ScreenshotError(f"{what} did not finish within {timeout:.0f} s")
        app.processEvents()
        time.sleep(0.02)
    _pump(app, SETTLE_S)


def _save(widget, path):
    if not widget.grab().save(str(path)):
        raise ScreenshotError(f"could not write {path}")
    print(f"wrote {path}", flush=True) if sys.stdout is not None else None
    return path


def capture(out_dir, app):
    """Save every screenshot into out_dir; returns the paths."""
    from .app import MainWindow
    from .views.welcome_dialog import apply_choice

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    window = MainWindow()
    window.project.ask_save = lambda: "discard"
    window.resize(*MAIN_SIZE)
    window.show()
    state = window.state
    paths = []
    try:
        apply_choice(window, ("preset", "Validation case"))
        _wait(app, lambda: state.design is not None and not state.is_busy(), "the design")
        paths.append(_save(window, out / SHOTS[0]))

        window.tabs.setCurrentWidget(window.offdesign_tab)
        window.offdesign_tab.set_charts_expanded(True)
        state.update(off_design_mach=OFF_DESIGN_MACH)
        _wait(app, lambda: (state.off_design is not None and not state.is_busy()
                            and abs(state.off_design.M_inf - OFF_DESIGN_MACH) < 1e-9),
              "the off-design view")
        paths.append(_save(window, out / SHOTS[1]))

        window.tabs.setCurrentWidget(window.analytics_tab)
        window.analytics_tab.set_view("turning")
        _pump(app, 0.2)                                 # the tab starts its worker when shown
        _wait(app, lambda: not window.analytics_tab.is_computing(), "the analytics charts")
        paths.append(_save(window, out / SHOTS[2]))

        iso = window.show_isentropic_ramp()
        iso.resize(*ISENTROPIC_SIZE)
        _wait(app, lambda: iso._ramp is not None, "the isentropic ramp")
        paths.append(_save(iso, out / SHOTS[3]))
    finally:
        window.close()
        _pump(app, 0.2)
    return paths


def main(args):
    """Entry from busemann.app.main: `--screenshots DIR`."""
    i = args.index("--screenshots")
    if i + 1 >= len(args):
        print("--screenshots needs an output folder", file=sys.stderr) if sys.stderr else None
        return 2
    out_dir = args[i + 1]
    # never the user's settings (recent files, welcome and tour state)
    os.environ.setdefault("BUSEMANN_SETTINGS_FILE",
                          str(Path(tempfile.mkdtemp(prefix="busemann-shots-")) / "settings.ini"))
    from PySide6.QtWidgets import QApplication

    from .app import setup_application

    app = QApplication.instance() or QApplication(["busemann"])
    setup_application(app)
    try:
        capture(out_dir, app)
    except ScreenshotError as exc:
        print(f"screenshots FAILED: {exc}", file=sys.stderr) if sys.stderr else None
        return 1
    return 0
