"""`busemann --self-test` (M12 PART 3), from source: every item passes, the equation is
rendered by a separate spawn-started process, and a failing item gives a non-zero exit code
that names it."""
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("PySide6")

from busemann import __version__, selftest  # noqa: E402

pytestmark = pytest.mark.gui

SUMMARY_OK = re.compile(rf"^Busemann {re.escape(__version__)} self-test: OK "
                        rf"\({len(selftest.CHECKS)} checks, \d+\.\d s\)$")


def _run_cli(tmp_path, *extra):
    log = tmp_path / "selftest.log"
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
               BUSEMANN_SETTINGS_FILE=str(tmp_path / "settings.ini"))
    proc = subprocess.Popen([sys.executable, "-m", "busemann", "--self-test",
                             "--self-test-log", str(log), *extra],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    out, err = proc.communicate(timeout=300)
    return proc, out, err, log


def test_self_test_passes_from_source(tmp_path):
    proc, out, err, log = _run_cli(tmp_path)
    assert proc.returncode == 0, out + err
    lines = out.strip().splitlines()
    assert SUMMARY_OK.match(lines[-1]), lines[-1]
    text = log.read_text(encoding="utf-8").splitlines()
    assert text[0] == lines[-1]                                # summary first in the log
    names = [name for name, _ in selftest.CHECKS]
    assert len(text) == 1 + len(names)
    for name, line in zip(names, text[1:]):
        assert line.startswith(f"  ok      {name}: "), line
    for item in ("fonts", "icons", "brand assets", "explain entries and tooltips",
                 "example designs", "validation data", "licences", "validation design",
                 "off-design point", "isentropic ramp", "equation warm-up (spawn)",
                 "DXF write and read"):
        assert item in names
    assert "recovery 0.7437" in log.read_text(encoding="utf-8")


def test_equation_is_rendered_by_a_separate_spawned_process(tmp_path):
    proc, out, err, log = _run_cli(tmp_path)
    assert proc.returncode == 0, out + err
    line = next(ln for ln in log.read_text(encoding="utf-8").splitlines()
                if "equation warm-up (spawn)" in ln)
    worker = int(re.search(r"spawn worker pid (\d+)", line).group(1))
    assert worker != proc.pid                                  # not the self-test process
    assert re.search(r", \d+ bytes, ", line)                    # an SVG was written


def test_a_failing_item_gives_its_position_and_name(tmp_path, monkeypatch, qtbot):
    from busemann import app

    def broken():
        raise selftest.SelfTestError("resource missing")
    checks = list(selftest.CHECKS[:2]) + [("broken item", broken)] + list(selftest.CHECKS[2:4])
    monkeypatch.setattr(selftest, "CHECKS", tuple(checks))
    log = tmp_path / "selftest.log"
    code = app.main(["--self-test", "--self-test-log", str(log)])
    assert code == 3                                           # 1-based position
    summary = log.read_text(encoding="utf-8").splitlines()[0]
    assert summary == (f"Busemann {__version__} self-test: FAILED: broken item: "
                       f"resource missing (1 of {len(checks)} failed)")
    assert "  ok      fonts: " in log.read_text(encoding="utf-8")    # the others still ran


def test_unexpected_exceptions_are_named_with_their_place():
    def boom():
        return {}["missing"]
    code, summary, lines = selftest.run((("ok item", lambda: "fine"), ("boom item", boom)))
    assert code == 2
    assert "FAILED: boom item: KeyError: 'missing' (test_selftest.py:" in summary
    assert lines[0].startswith("  ok      ok item: fine")


class _ThreadPool(ThreadPoolExecutor):
    """Looks like a spawn pool but runs in this process (what a broken frozen build might do
    if the render work silently fell back to the GUI process)."""
    import multiprocessing as _mp
    _mp_context = _mp.get_context("spawn")


def test_warm_up_check_fails_if_the_render_pool_is_not_a_separate_process(monkeypatch, qtbot):
    from busemann.explain import warm

    pool = _ThreadPool(max_workers=1)
    monkeypatch.setattr(warm, "_pool", lambda: pool)
    try:
        code, summary, _ = selftest.run((("equation warm-up (spawn)", selftest.check_warm_up),))
    finally:
        pool.shutdown()
    assert code == 1
    assert "FAILED: equation warm-up (spawn): the render pool runs in this process" in summary


def test_warm_up_check_fails_if_the_pool_is_not_spawn(monkeypatch, qtbot):
    import multiprocessing

    from busemann.explain import warm

    class _Other(ThreadPoolExecutor):
        _mp_context = multiprocessing.get_context()      # the platform default, faked below

    monkeypatch.setattr(_Other._mp_context, "get_start_method", lambda *a, **k: "fork")
    pool = _Other(max_workers=1)
    monkeypatch.setattr(warm, "_pool", lambda: pool)
    try:
        code, summary, _ = selftest.run((("equation warm-up (spawn)", selftest.check_warm_up),))
    finally:
        pool.shutdown()
    assert code == 1 and "start method is 'fork', not spawn" in summary


def test_warm_up_check_restores_the_cache_folder(monkeypatch, qtbot, tmp_path):
    monkeypatch.setenv("BUSEMANN_CACHE_DIR", str(tmp_path / "mine"))
    code, summary, _ = selftest.run((("equation warm-up (spawn)", selftest.check_warm_up),))
    assert code == 0, summary
    assert os.environ["BUSEMANN_CACHE_DIR"] == str(tmp_path / "mine")
    assert not (tmp_path / "mine").exists()              # rendered into a temporary folder
