"""Off-design Mach sweep playback (addendum C4): ▶ / ⏸, speed 0.5× / 1× / 2×, loop.

A timer advances the off-design Mach from the slider's lower end (1.2) to design + 1.5 at
BASE_RATE Mach per second times the speed; at the end it stops, or starts over with loop on.
Any other input change (or grabbing the slider) stops it.
"""
from PySide6.QtCore import QElapsedTimer, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from ..state import off_design_range
from ..tooltips import tip
from ..widgets import SegmentedControl

BASE_RATE = 0.5          # Mach per second at 1×
TICK_MS = 33
SPEEDS = (("0.5", "0.5×"), ("1", "1×"), ("2", "2×"))
STEP = 0.01              # slider resolution


class Playback(QObject):
    playing_changed = Signal(bool)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.speed = 1.0
        self.loop = False
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._clock = QElapsedTimer()
        self._M = None
        self._last_inputs = state.inputs
        self._own_update = False
        state.inputs_changed.connect(self._on_inputs)

    def is_playing(self):
        return self._timer.isActive()

    def range(self):
        return off_design_range(self.state.design.inputs.M if self.state.design is not None
                                else self.state.inputs.mach)

    def play(self):
        if self.is_playing() or self.state.design is None:
            return
        lo, hi = self.range()
        M = self.state.off_design_mach()
        self._M = lo if M >= hi - 1e-9 or M < lo else M      # from the start at the end
        self._clock.start()
        self._timer.start()
        self.playing_changed.emit(True)

    def stop(self):
        if self.is_playing():
            self._timer.stop()
            self.playing_changed.emit(False)

    def toggle(self):
        self.stop() if self.is_playing() else self.play()

    def advance(self, seconds):
        """Move the Mach on by `seconds` of playback (the timer calls this; tests too)."""
        lo, hi = self.range()
        M = self._M + BASE_RATE * self.speed * seconds
        if M >= hi:
            if self.loop:
                M = lo + (M - hi)
            else:
                M = hi
        self._M = M
        self._set_mach(round(round(M / STEP) * STEP, 10))
        if M >= hi and not self.loop:
            self.stop()

    def _tick(self):
        dt = self._clock.restart() / 1000.0
        self.advance(min(dt, 0.25))               # a stalled frame does not jump far

    def _set_mach(self, M):
        if M == self.state.inputs.off_design_mach:
            return
        self._own_update = True
        try:
            self.state.update(off_design_mach=M)
        finally:
            self._own_update = False

    def _on_inputs(self, inputs):
        old, self._last_inputs = self._last_inputs, inputs
        if not self._own_update and self.is_playing() and inputs != old:
            self.stop()                            # any other input, or a manual Mach


class PlaybackControls(QWidget):
    """▶ / ⏸ button, speed segments and a loop toggle for the Off-design header."""

    def __init__(self, playback, parent=None):
        super().__init__(parent)
        self.playback = playback
        self.play_button = QToolButton()
        self.play_button.setObjectName("playButton")
        self.play_button.setToolTip(tip("playback.play"))
        self.play_button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.play_button.clicked.connect(playback.toggle)
        self.speed = SegmentedControl(list(SPEEDS), "1")
        self.speed.setToolTip(tip("playback.speed"))
        self.speed.changed.connect(lambda key: setattr(playback, "speed", float(key)))
        self.loop_button = QToolButton()
        self.loop_button.setObjectName("layerToggle")
        self.loop_button.setCheckable(True)
        self.loop_button.setToolTip("Loop sweep")
        self.loop_button.setAccessibleName("Loop sweep")
        from ..theme import qt as theme

        self.loop_button.setIcon(theme.icon("loop", "text", 16))
        self.loop_button.toggled.connect(lambda on: setattr(playback, "loop", on))
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(self.play_button)
        row.addWidget(self.speed)
        row.addWidget(self.loop_button)
        playback.playing_changed.connect(self._show)
        self._show(False)

    def _show(self, playing):
        from ..theme import qt as theme

        self.state_text = "Pause" if playing else "Play"
        self.play_button.setIcon(theme.icon("pause" if playing else "play", "accent", 16))
        self.play_button.setAccessibleName(self.state_text)
