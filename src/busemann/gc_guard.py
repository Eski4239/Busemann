"""Garbage collection on the GUI thread only (M8.2 crash fix).

Python's cyclic garbage collector runs in whichever thread happens to allocate when a
threshold is crossed. When that is a worker thread (the design / off-design jobs allocate a
lot of numpy arrays), the collector can free Qt objects that live on the GUI thread (widgets
in reference cycles through lambdas or bound slots) from the wrong thread: an access
violation, so the app freezes and closes. Seen in the full test run as
"Windows fatal exception: access violation ... Garbage-collecting" on a pooled thread.

The guard turns automatic collection off and runs it from a QTimer on the GUI thread with
the same generation thresholds (the pattern of pyqtgraph's GarbageCollector).
"""
import gc

from PySide6.QtCore import QObject, QTimer

INTERVAL_MS = 500
FULL_EVERY = 40          # ticks: a full collection every 20 s (old cycles, Python 3.14)
_guard = None


class GcGuard(QObject):
    def __init__(self, parent=None, interval_ms=INTERVAL_MS):
        super().__init__(parent)
        self.thresholds = gc.get_threshold()
        self._ticks = 0
        gc.disable()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check)
        self.timer.start(interval_ms)

    def check(self):
        """Collect the generations whose counts passed their thresholds (GUI thread), and
        everything every FULL_EVERY ticks."""
        self._ticks += 1
        if self._ticks % FULL_EVERY == 0:
            gc.collect()
            return
        counts = gc.get_count()
        if counts[0] > self.thresholds[0]:
            generation = 0
            if counts[1] > self.thresholds[1]:
                generation = 1
                if counts[2] > self.thresholds[2]:
                    generation = 2
            gc.collect(generation)

    def stop(self):
        self.timer.stop()
        gc.enable()


def install(app):
    """Install once per QApplication (idempotent). Returns the guard."""
    global _guard
    if _guard is None:
        _guard = GcGuard(app)
    return _guard
