"""Compare the wall-clock performance of the current tree with a reference commit.

    python tools/perf_compare.py [--ref 68253ea] [--runs 5]

For each tree (the working tree, and the reference commit checked out in a temporary git
worktree that is removed afterwards) the measurements run --runs times, each in a fresh
Python process (offscreen Qt), and the script prints median and max over the runs:

- design_ms       median of 20 uncached api designs (M 3, 2 ramps)   [test_design_under_50_ms]
- slider_step_ms  median of 50 off-design points (M 3, 4 ramps)       [test_slider_off_design_point_under_5_ms]
- drag_warm_ms    longest gap between 60 slider steps 8 ms apart, starting 1.6 s after the
                  first design (when the M6 equation warm-up has just started)
                                                                      [test_slider_drag_stays_responsive]
- drag_idle_ms    the same drag after an idle wait (warm-up finished)
- eq_max_ms       longest single-equation mathtext render (trees with an equation warm-up)
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHILD = r'''
import json, os, statistics, sys, time
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from inletdesign import api

def median_ms(fn, runs):
    t = []
    for _ in range(runs):
        t0 = time.perf_counter(); fn(); t.append((time.perf_counter() - t0) * 1000.0)
    return statistics.median(t)

out = {}
uncached = api._design_cached.__wrapped__
out["design_ms"] = median_ms(lambda: uncached(3.0, 2, 0.1, 1.4, None), 20)
d4 = api.design(3.0, 4)
out["slider_step_ms"] = median_ms(lambda: api.off_design_point(d4, 3.137), 50)

from PySide6.QtCore import QEventLoop, QThreadPool, QTimer
from PySide6.QtWidgets import QApplication
from busemann.app import MainWindow, setup_application

def wait(ms):
    loop = QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()

def drag(w):
    w.tabs.setCurrentWidget(w.offdesign_tab)
    slider = w.offdesign_tab.slider.slider
    slider.setSliderDown(True)
    gaps, last = [], time.perf_counter()
    for k in range(60):
        slider.setValue(round((2.45 - 1.2) / 0.01) + k)
        wait(8)
        now = time.perf_counter(); gaps.append((now - last) * 1000.0); last = now
    slider.setSliderDown(False)
    wait(300)
    return max(gaps)

app = QApplication([]); setup_application(app)
w = MainWindow(); w.resize(1440, 900); w.show()
if hasattr(w, "project"):
    w.project.ask_save = lambda: "discard"
t0 = time.perf_counter()
while w.state.design is None:
    wait(20)
wait(max(0, 1600 - round((time.perf_counter() - t0) * 1000)))   # warm-up (M6) just started
out["drag_warm_ms"] = drag(w)
wait(300)
w.state.update(off_design_mach=None, mach=3.0)
QThreadPool.globalInstance().waitForDone(60000)
wait(2500)                                                          # idle: warm-up finished
QThreadPool.globalInstance().waitForDone(60000)
out["drag_idle_ms"] = drag(w)

try:                                     # longest single equation render (fresh cache)
    from busemann.explain import mathsvg, warm
    from busemann.theme import tokens
    s = w.state
    texs = warm.equations(s.design, s.off_design, s.freestream, s.off_freestream)
    render = getattr(mathsvg, "render", None)
    if render is None:                       # in-thread cache (M6 before the process move)
        mathsvg._tex_to_svg.cache_clear()
        render = mathsvg.tex_to_svg
    times = []
    for tex in texs:
        t1 = time.perf_counter(); render(tex, tokens.COLORS["text"])
        times.append((time.perf_counter() - t1) * 1000.0)
    out["eq_max_ms"] = max(times)
    out["eq_count"] = len(times)
    out["eq_total_ms"] = sum(times)
except ImportError:
    pass
w.close()
w.state.shutdown()
print("RESULT " + json.dumps(out))
'''

METRICS = ("design_ms", "slider_step_ms", "drag_warm_ms", "drag_idle_ms", "eq_max_ms")


def measure(tree, runs):
    results = []
    for k in range(runs):
        scratch = Path(tempfile.mkdtemp(prefix="perf_run_"))
        env = dict(os.environ, PYTHONPATH=str(Path(tree) / "src"), QT_QPA_PLATFORM="offscreen",
                   BUSEMANN_SETTINGS_FILE=str(scratch / "settings.ini"),
                   BUSEMANN_CACHE_DIR=str(scratch / "cache"),      # cold equation cache
                   PYTHONIOENCODING="utf-8")
        out = subprocess.run([sys.executable, "-c", CHILD], cwd=tree, env=env,
                             capture_output=True, text=True, timeout=600)
        line = [ln for ln in out.stdout.splitlines() if ln.startswith("RESULT ")]
        if out.returncode != 0 or not line:
            raise RuntimeError(f"measurement failed in {tree}:\n{out.stderr[-2000:]}")
        results.append(json.loads(line[-1][7:]))
        print(f"  {Path(tree).name} run {k + 1}/{runs}: " +
              ", ".join(f"{m} {results[-1][m]:.1f}" for m in METRICS if m in results[-1]),
              flush=True)
    return results


def summary(results):
    rows = {}
    for m in METRICS:
        values = [r[m] for r in results if m in r]
        if values:
            rows[m] = (statistics.median(values), max(values))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="68253ea", help="reference commit (default: M5)")
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args(argv)

    print(f"current tree: {ROOT}")
    current = summary(measure(ROOT, args.runs))
    wt = Path(tempfile.mkdtemp(prefix="perf_ref_")) / "tree"
    subprocess.run(["git", "worktree", "add", "-q", "--detach", str(wt), args.ref], cwd=ROOT,
                   check=True)
    try:
        print(f"reference {args.ref}: {wt}")
        reference = summary(measure(wt, args.runs))
    finally:
        subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=ROOT, check=False)
    print()
    print(f"{'metric':<16} {'current median':>15} {'current max':>12} "
          f"{args.ref + ' median':>15} {args.ref + ' max':>12} {'ratio':>7}")
    for m in METRICS:
        if m not in current:
            continue
        cm, cx = current[m]
        if m in reference:
            rm, rx = reference[m]
            print(f"{m:<16} {cm:>15.1f} {cx:>12.1f} {rm:>15.1f} {rx:>12.1f} {cm / rm:>7.2f}")
        else:
            print(f"{m:<16} {cm:>15.1f} {cx:>12.1f} {'-':>15} {'-':>12} {'':>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
