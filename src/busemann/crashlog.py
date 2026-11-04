"""Crash log and guards (M8.2).

PySide6 6.12 lets a Python exception raised inside a Qt event handler (mousePressEvent,
paint, ...) or a slot propagate into Qt's event dispatch, which leaves the event loop hung:
the window stops responding and Windows then closes it with no message. So:

- `guarded` wraps an event handler: an exception is logged, the handler's recovery hook runs,
  and Qt never sees it;
- `install()` writes native crashes (faulthandler), uncaught exceptions (sys / threading
  excepthooks) and main-thread stalls longer than STALL_S (a watchdog re-armed by a UI timer)
  to crash.log in the Busemann data folder, so a future freeze leaves a stack trace.
"""
import faulthandler
import functools
import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

STALL_S = 10.0          # a main-thread stall this long dumps every thread's stack to the log
_ARM_MS = 1000
_state = {"file": None, "timer": None, "logged": 0}


def log_path():
    base = os.environ.get("BUSEMANN_CRASH_DIR")
    if base:
        return Path(base) / "crash.log"
    root = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(root) / "Busemann" / "crash.log"


def _open():
    if _state["file"] is None:
        path = log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        _state["file"] = open(path, "a", encoding="utf-8", buffering=1)
    return _state["file"]


def log_exception(where, exc_type, exc, tb):
    """Append one traceback to the log (and print it, as Python would)."""
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        f = _open()
        f.write(f"--- {stamp} {where}\n{text}\n")
        f.flush()
    except OSError:
        pass
    _state["logged"] += 1
    if sys.stderr is not None:
        sys.stderr.write(f"[Busemann] {where}:\n{text}")


def logged_count():
    return _state["logged"]


def guarded(recover=None):
    """Decorator for Qt event handlers and slots: never let an exception reach Qt.
    `recover(self)` runs after a logged exception (e.g. end a drag)."""
    def wrap(fn):
        @functools.wraps(fn)
        def inner(self, *args, **kwargs):
            try:
                return fn(self, *args, **kwargs)
            except Exception:                       # noqa: BLE001 (logged, never re-raised)
                log_exception(f"{type(self).__name__}.{fn.__name__}", *sys.exc_info())
                if recover is not None:
                    try:
                        recover(self)
                    except Exception:               # noqa: BLE001
                        log_exception(f"{type(self).__name__} recovery", *sys.exc_info())
                return None
        return inner
    return wrap


def install(app=None):
    """Enable the crash log; with `app`, also the main-thread stall watchdog."""
    try:
        f = _open()
        faulthandler.enable(file=f, all_threads=True)
    except OSError:
        return

    def hook(exc_type, exc, tb):
        log_exception("uncaught", exc_type, exc, tb)

    sys.excepthook = hook
    threading.excepthook = lambda a: log_exception(f"thread {a.thread.name if a.thread else ''}",
                                                  a.exc_type, a.exc_value, a.exc_traceback)
    if app is not None:
        from PySide6.QtCore import QTimer

        timer = QTimer(app)
        timer.timeout.connect(
            lambda: faulthandler.dump_traceback_later(STALL_S, repeat=False, file=f))
        timer.start(_ARM_MS)
        _state["timer"] = timer
        app.aboutToQuit.connect(faulthandler.cancel_dump_traceback_later)
