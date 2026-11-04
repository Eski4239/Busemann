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


def test_separation_notices_in_results_quote_phase_3b(window):
    texts = window.results_panel.warning_texts()
    sep = [t for t in texts if t.startswith("Shock-induced separation likely")]
    assert len(sep) == 2 and all("approximate — verify with CFD" in t for t in sep)
    labels = [lab for lab in window.results_panel._warning_labels
              if lab.text().replace(" ", " ").startswith("Shock-induced separation "
                                                              "likely at ramp shock 2")]
    assert "15.5 mm" in labels[0].toolTip() and "validation_3b.md" in labels[0].toolTip()


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
