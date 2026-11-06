"""M8.2 Results panel: five compact cards, the warnings banner, grouped collapsible warnings,
no citations, the flow-regions table and the Export button."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

pytestmark = pytest.mark.gui


def test_only_the_five_cards(window):
    assert list(window.results_panel.cards) == ["recovery_total", "mass_capture", "mass_flow",
                                                "M_duct", "cowl_margin"]
    cards = window.results_panel.cards
    assert cards["M_duct"].title.text() == "M AFTER TERMINAL SHOCK"
    assert cards["cowl_margin"].text() == f"{window.state.design.cowl_margin_deg:+.2f}"
    assert not cards["recovery_total"].property("compact")             # big value
    assert all(card.property("compact") for k, card in cards.items() if k != "recovery_total")
    assert cards["recovery_total"].note("mil").startswith("Engine face ≈ ")


def test_banner_counts_warnings_and_scrolls_to_them(qtbot, window):
    panel = window.results_panel
    n = sum(1 for lv in panel.warning_levels() if lv in ("warn", "error"))
    assert n > 0 and panel.banner.isVisibleTo(window)
    assert panel.banner.text() == f"{n} warnings — review before using these results"
    window.resize(1280, 700)
    scroll = window.right_panel.currentWidget()
    scroll.verticalScrollBar().setValue(0)
    qtbot.wait(50)
    panel.banner.click()
    qtbot.wait(50)
    assert scroll.verticalScrollBar().value() > 0                  # scrolled to the warnings


def test_groups_and_collapsible_rows(qtbot, window):
    panel = window.results_panel
    assert panel.notice_groups() == ["At the design point (M∞ 3.00)"]
    row = panel.warning_rows[0]
    assert not row.expanded() and row.head.text()
    assert len(row.head.text()) <= 56 and "(" not in row.head.text()
    row.toggle()
    assert row.expanded() and row.body.text().replace(" ", " ") == \
        row.text[:1].upper() + row.text[1:]
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=3.25)
    assert panel.notice_groups() == ["At the design point (M∞ 3.00)",
                                     "At M∞ 3.25 (off-design)"]


def test_no_citations_or_cfd_comparisons_in_results(qtbot, window):
    panel = window.results_panel
    window.tabs.setCurrentWidget(window.offdesign_tab)
    with qtbot.waitSignal(window.state.off_design_ready, timeout=5000):
        window.state.update(off_design_mach=3.25)
    from PySide6.QtWidgets import QLabel

    text = " ".join(lab.text() + " " + lab.toolTip() for lab in panel.findChildren(QLabel))
    text += " ".join(row.toolTip() for row in panel.warning_rows)
    for word in ("Korkegi", "Seddon", "NACA", "Phase 3", "Fluent", "CFD at", "MIL-E-5008B (1959)"):
        assert word not in text, word


def test_flow_regions_heading_and_export_menu(window):
    from PySide6.QtWidgets import QLabel

    panel = window.results_panel
    titles = [lab.text() for lab in panel.findChildren(QLabel)]
    assert "FLOW REGIONS" in titles and "STATIONS" not in titles
    menu = panel.export_button.menu()
    assert menu is window.project.export_menu                      # same actions as File
    texts = [a.text() for a in menu.actions() if a.text()]
    for name in ("Geometry DXF…", "Geometry IGES…", "Wall points CSV…", "Gmsh geometry (.geo)…",
                 "Results JSON…", "Results CSV…", "Canvas figure…"):
        assert name in texts, name
