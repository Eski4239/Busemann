"""M8.2 bug 2: the inlet width input must drive total ṁ (height mode) and the sizing
(mass-flow mode), through typed input as a user enters it."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from inletdesign import api  # noqa: E402
from inletdesign import units as U  # noqa: E402

pytestmark = pytest.mark.gui


def _type(qtbot, field, text, key=Qt.Key.Key_Return):
    field.edit.setFocus()
    field.edit.selectAll()
    qtbot.keyClicks(field.edit, text)
    qtbot.keyClick(field.edit, key)


def _mode(qtbot, window, mode):
    combo = window.design_panel.capture_mode
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        combo.setCurrentIndex(combo.findData(mode))
        combo.activated.emit(combo.currentIndex())


@pytest.mark.parametrize("key", [Qt.Key.Key_Return, Qt.Key.Key_Tab])
def test_height_mode_width_drives_total_mass_flow(qtbot, window, key):
    s, panel = window.state, window.design_panel
    with qtbot.waitSignal(s.design_ready, timeout=5000):
        _type(qtbot, panel.width_field, "2.5", key)
    per_m = s.captured_mass_flow()
    assert s.inputs.inlet_width_m == 2.5 and s.total_mass_flow() == pytest.approx(2.5 * per_m)
    assert window.results_panel.cards["mass_flow"].sub_label.text().startswith(
        f"total {s.total_mass_flow():.4g}"[:10])
    assert float(panel.mdot.edit.text()) == pytest.approx(2.5 * per_m, abs=1e-3)   # locked ṁ
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(s.off_design_ready, timeout=5000):
        s.update(off_design_mach=2.5)
    assert s.total_mass_flow(at_off_design=True) == pytest.approx(
        2.5 * s.captured_mass_flow(at_off_design=True))


def test_mass_flow_mode_width_rescales_the_capture_height(qtbot, window):
    s, panel = window.state, window.design_panel
    _mode(qtbot, window, "mass_flow")
    mdot = s.inputs.mdot_kgps
    with qtbot.waitSignal(s.design_ready, timeout=5000):
        _type(qtbot, panel.width_field, "4")
    h = s.design.inputs.capture_height
    assert h == pytest.approx(mdot / (s.freestream.rho * s.freestream.V * 4.0), rel=1e-12)
    assert panel.capture.edit.text() == f"{h:.3f}"                  # the locked h_c follows
    assert s.total_mass_flow() == pytest.approx(mdot, rel=1e-12)    # the demand is still met
    labels = [lab.text() for lab in window.canvas.inlet_scene.dim_labels]
    assert f"h_c {h * 1000:.1f} mm" in labels, labels                 # the drawing says so


def test_width_in_imperial_units(qtbot, window):
    s, panel = window.state, window.design_panel
    s.update(units="Imperial")
    with qtbot.waitSignal(s.design_ready, timeout=5000):
        _type(qtbot, panel.width_field, "39.37")                    # inches
    assert s.inputs.inlet_width_m == pytest.approx(39.37 * U.INCH, rel=1e-12)
    assert s.total_mass_flow() == pytest.approx(s.inputs.inlet_width_m *
                                                api.captured_mass_flow(s.freestream, 0.1))


def test_clearing_the_width_in_height_mode_removes_the_total(qtbot, window):
    s, panel = window.state, window.design_panel
    with qtbot.waitSignal(s.design_ready, timeout=5000):
        _type(qtbot, panel.width_field, "2")
    with qtbot.waitSignal(s.design_ready, timeout=5000):
        panel.width_field.edit.setFocus()
        panel.width_field.edit.selectAll()
        qtbot.keyClick(panel.width_field.edit, Qt.Key.Key_Delete)
        qtbot.keyClick(panel.width_field.edit, Qt.Key.Key_Return)
    assert s.inputs.inlet_width_m is None and s.total_mass_flow() is None
