"""Off-design Mach sweep playback and its Space rules (addendum C4)."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from busemann.views import playback as PB  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture
def tab(qtbot, window):
    window.tabs.setCurrentWidget(window.offdesign_tab)
    return window.offdesign_tab


def test_play_advances_at_the_chosen_speed_and_stops_at_the_end(qtbot, window, tab):
    pb = tab.playback
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=2.0)
    tab.playback_controls.play_button.click()
    assert pb.is_playing() and tab.playback_controls.state_text == "Pause"
    pb._timer.stop()                                   # drive it by hand: deterministic
    pb.advance(1.0)                                    # 1×: 0.5 Mach per second
    assert window.state.inputs.off_design_mach == pytest.approx(2.5)
    tab.playback_controls.speed.button("2").click()
    pb.advance(0.5)                                    # 2×: +0.5
    assert window.state.inputs.off_design_mach == pytest.approx(3.0)
    tab.playback_controls.speed.button("0.5").click()
    pb.advance(1.0)                                    # 0.5×: +0.25
    assert window.state.inputs.off_design_mach == pytest.approx(3.25)
    pb._timer.start()
    pb.advance(10.0)                                   # past the end: stop at design + 1.5
    assert window.state.inputs.off_design_mach == pytest.approx(4.5) and not pb.is_playing()
    assert tab.playback_controls.state_text == "Play"


def test_loop_wraps_to_the_start(qtbot, window, tab):
    pb = tab.playback
    tab.playback_controls.loop_button.setChecked(True)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=4.4)
    pb.play()
    pb._timer.stop()
    pb._timer.start()
    pb.advance(0.4)                                    # 4.4 + 0.2 -> wraps past 4.5
    assert window.state.inputs.off_design_mach == pytest.approx(1.2 + 0.1) and pb.is_playing()
    pb.stop()


def test_play_from_the_end_restarts_at_1_2(qtbot, window, tab):
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=4.5)
    tab.playback.play()
    tab.playback.advance(0.0)
    assert window.state.inputs.off_design_mach == pytest.approx(1.2)
    tab.playback.stop()


@pytest.mark.parametrize("change", [dict(mach=2.8), dict(n_ramps=3), dict(off_design_mach=2.2)])
def test_any_input_stops_it(qtbot, window, tab, change):
    tab.playback.play()
    window.state.update(**change)
    assert not tab.playback.is_playing()


def test_space_on_canvas_and_tab_background_but_not_on_a_button(qtbot, window, tab):
    pb = tab.playback
    canvas = tab.canvas
    canvas.setFocus()
    qtbot.waitUntil(canvas.hasFocus, timeout=1000)
    qtbot.keyClick(canvas, Qt.Key.Key_Space)           # tap: play
    assert pb.is_playing()
    qtbot.keyClick(canvas, Qt.Key.Key_Space)           # tap again: pause
    assert not pb.is_playing()
    tab.setFocus()
    qtbot.waitUntil(tab.hasFocus, timeout=1000)
    qtbot.keyClick(tab, Qt.Key.Key_Space)
    assert pb.is_playing()
    pb.stop()
    loop = tab.playback_controls.loop_button
    loop.setFocus()
    qtbot.waitUntil(loop.hasFocus, timeout=1000)
    qtbot.keyClick(loop, Qt.Key.Key_Space)             # the button keeps Space
    assert loop.isChecked() and not pb.is_playing()


def test_space_hold_and_drag_pans_without_playing(qtbot, window, tab):
    canvas = tab.canvas
    canvas.setFocus()
    qtbot.waitUntil(canvas.hasFocus, timeout=1000)
    qtbot.keyPress(canvas, Qt.Key.Key_Space)
    centre = canvas.viewport().rect().center()
    qtbot.mousePress(canvas.viewport(), Qt.MouseButton.LeftButton, pos=centre)
    qtbot.mouseRelease(canvas.viewport(), Qt.MouseButton.LeftButton, pos=centre)
    qtbot.keyRelease(canvas, Qt.Key.Key_Space)
    assert not tab.playback.is_playing()


def test_window_action_and_constants(window):
    assert PB.BASE_RATE == 0.5
    window.play_action.trigger()
    assert window.tabs.currentWidget() is window.offdesign_tab
    assert window.offdesign_tab.playback.is_playing()
    window.play_action.trigger()
    assert not window.offdesign_tab.playback.is_playing()
