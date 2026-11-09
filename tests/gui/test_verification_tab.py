"""Verification tab, its badge, separation notices and the notes beside exports (C5/C6/E)."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from busemann import verification as V  # noqa: E402
from busemann.export.notes import NOTES_NAME  # noqa: E402

pytestmark = pytest.mark.gui


def test_tabs_and_badge(qtbot, window):
    tabs = window.right_panel
    assert tabs.tabText(0) == "Results"
    items = window.state.verification_items()
    n = V.badge_count(items)
    assert n > 0 and tabs.tabText(1) == f"Verification ({n})"
    panel = window.verification_panel
    assert panel.titles() == [i.title for i in items] and len(panel.cards) == len(items)
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        window.state.update(mach=2.0, n_ramps=1)
    n2 = V.badge_count(window.state.verification_items())
    assert tabs.tabText(1) == (f"Verification ({n2})" if n2 else "Verification")


def test_separation_notices_in_results_without_sources(window):
    """M8.2: the Results panel shows the warning; the source and the validation CFD quote are in
    the Verification tab."""
    texts = window.results_panel.warning_texts()
    sep = [t for t in texts if t.startswith("Shock-induced separation likely")]
    assert len(sep) == 2 and all("approximate — verify with CFD" in t for t in sep)
    assert not any("Korkegi" in t for t in texts)
    items = window.state.verification_items()
    r2 = next(i for i in items if i.title.startswith("Ramp shock 2"))
    assert "15.5 mm" in r2.quote and "Korkegi" in r2.source


@pytest.mark.parametrize("export", ["export_geometry", "export_cfd", "export_cfd_offdesign"])
def test_every_geometry_and_cfd_export_writes_the_notes(qtbot, window, tmp_path, export):
    window.exports.ask_path = lambda title, name, flt: str(tmp_path / name)
    path = getattr(window.exports, export)()
    notes = path.with_name(NOTES_NAME)
    assert notes.exists()
    text = notes.read_text(encoding="utf-8")
    for item in window.state.verification_items():
        assert item.title in text and item.source in text
    assert "must be verified with a CFD solver" in text


@pytest.mark.ui
def test_no_validation_phase_names_in_the_verification_tab(qtbot, window):
    """M8.4: every label and tooltip in the Verification and Results panels, at the design
    point and above the design Mach (lip notice)."""
    import re

    from PySide6.QtWidgets import QLabel, QWidget

    def texts():
        out = []
        for panel in (window.verification_panel, window.results_panel):
            for w in panel.findChildren(QWidget):
                out.append(w.toolTip())
                if isinstance(w, QLabel):
                    out.append(w.text())
        return out

    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=3.25)
    window.tabs.setCurrentWidget(window.offdesign_tab)
    qtbot.wait(200)
    for state in ("off-design", "design"):
        hits = [t for t in texts() if re.search(r"phase\s*3", t, re.I)]
        assert hits == [], state
        window.tabs.setCurrentWidget(window.canvas)
        qtbot.wait(200)
    assert any("validation CFD" in t for t in texts())
