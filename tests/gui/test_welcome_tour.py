"""Welcome window and tour (M7)."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402

from busemann import project as P  # noqa: E402
from busemann.inputs import Inputs  # noqa: E402
from busemann.settings import app_settings  # noqa: E402
from busemann.views import welcome_dialog as W  # noqa: E402
from busemann.views.tour import STEPS, tour_done  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.fixture
def welcome(qtbot):
    from PySide6.QtWidgets import QApplication

    from busemann.app import setup_application

    setup_application(QApplication.instance())
    dialog = W.WelcomeDialog()
    qtbot.addWidget(dialog)
    return dialog


def test_sections_new_design_examples_recent(welcome):
    """M8.2: "New design" = validation case + blank; "Examples" = the four flight presets
    plus the bundled example designs, one list; "Recent"."""
    assert [t for t, _ in welcome.cards] == ["Validation case", "Blank (defaults)"]
    assert "M 3.00 · 10.0 kPa, 220 K" in welcome.cards[0][1].text()
    items = [welcome.example_list.item(k) for k in range(welcome.example_list.count())]
    titles = [it.text().splitlines()[0] for it in items]
    assert titles[:4] == ["Concorde cruise", "XB-70", "SR-71", "X-15 record"]
    assert len(titles) == 7
    kinds = [it.data(Qt.ItemDataRole.UserRole)[0] for it in items]
    assert kinds == ["preset"] * 4 + ["example"] * 3
    assert all(it.data(Qt.ItemDataRole.UserRole)[1].endswith(".dxf") for it in items[4:])
    assert not hasattr(welcome, "startup_check")            # "Show at startup" removed


def test_tour_box_checked_on_first_launch_only(qtbot, welcome):
    assert welcome.tour_check.isChecked()
    welcome.reject()
    second = W.WelcomeDialog()
    qtbot.addWidget(second)
    assert not second.tour_check.isChecked()


def test_recent_rows_show_mach_ramps_and_date(qtbot, tmp_path):
    path = tmp_path / "wing.dxf"
    P.save(path, Inputs(mach=2.4, n_ramps=3), None)
    app_settings().setValue("project/recent", [str(path), str(tmp_path / "gone.dxf")])
    dialog = W.WelcomeDialog()
    qtbot.addWidget(dialog)
    first = dialog.recent_list.item(0).text()
    assert first.startswith("wing.dxf\nM 2.40 · 3 ramps · 20")
    gone = dialog.recent_list.item(1)
    assert "cannot be read" in gone.text() and not gone.flags() & Qt.ItemFlag.ItemIsEnabled


@pytest.mark.parametrize("pick, expected", [
    (lambda d: d.cards[0][1].click(), ("preset", "Validation case")),
    (lambda d: d.cards[1][1].click(), ("blank",)),
    (lambda d: d._activated(d.example_list.item(1)), ("preset", "XB-70")),
    (lambda d: d._activated(d.example_list.item(5)), ("example",)),
    (lambda d: d.reject(), None),
])
def test_each_choice(welcome, pick, expected):
    pick(welcome)
    if expected is None:
        assert welcome.choice is None
    else:
        assert welcome.choice[:len(expected)] == expected


def test_choices_are_applied_to_the_main_window(qtbot, window):
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        W.apply_choice(window, ("preset", "SR-71"))
    assert window.state.inputs.mach == 3.2 and window.state.inputs.preset == "SR-71"
    assert window.windowTitle() == "Busemann — Untitled (from preset SR-71)"
    from busemann.paths import resource_path
    with qtbot.waitSignal(window.state.design_ready, timeout=5000):
        W.apply_choice(window, ("example", str(resource_path("examples",
                                                             "x15_four_ramp.dxf"))))
    assert window.state.inputs.mach == 6.7 and window.project.path is None
    assert "from example x15_four_ramp" in window.windowTitle()
    before = window.state.inputs
    W.apply_choice(window, None)                        # Esc: keep the default design
    assert window.state.inputs == before


def test_drop_on_welcome_opens_the_file(welcome, tmp_path):
    path = tmp_path / "d.dxf"
    P.save(path, Inputs(), None)
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    welcome.dropEvent(QDropEvent(QPointF(5, 5), Qt.DropAction.CopyAction, mime,
                                 Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier))
    from pathlib import Path
    assert welcome.choice[0] == "open" and Path(welcome.choice[1]) == path


def test_main_shows_welcome_unless_a_path_is_given(qtbot, monkeypatch, tmp_path):
    import busemann.app as app_module

    shown, windows = [], []
    monkeypatch.setattr(W.WelcomeDialog, "exec",
                        lambda self: shown.append(1) or self._choose(("preset", "XB-70")))
    monkeypatch.setattr(app_module.QApplication, "exec", lambda self: 0)
    real = app_module.MainWindow
    monkeypatch.setattr(app_module, "MainWindow",
                        lambda *a, **k: windows.append(real(*a, **k)) or windows[-1])
    assert app_module.main([]) == 0
    w = windows[-1]
    qtbot.addWidget(w)
    assert shown == [1] and w.isVisible()
    qtbot.waitUntil(lambda: w.state.inputs.mach == 3.0 and w.state.inputs.preset == "XB-70",
                    timeout=3000)
    path = tmp_path / "x.dxf"
    P.save(path, Inputs(mach=2.2), None)
    assert app_module.main([str(path)]) == 0
    w2 = windows[-1]
    qtbot.addWidget(w2)
    assert shown == [1]                                  # not shown again for a path
    qtbot.waitUntil(lambda: w2.state.inputs.mach == 2.2, timeout=3000)
    for win in (w, w2):
        win.project.ask_save = lambda: "discard"
        win.tour.hide()
        win.close()
        win.state.shutdown()


# --- tour -----------------------------------------------------------------------------------

def test_tour_steps_highlight_their_targets(qtbot, window):
    tour = window.tour
    tour.start()
    assert tour.isVisible() and tour.counter.text() == "1 / 3"
    targets = []
    for k in range(len(STEPS)):
        assert tour.title.text() == STEPS[k][1]
        rect = tour.target_rect()
        assert tour.hole.contains(rect)
        card = tour.card.geometry()
        if STEPS[k][0] == "canvas":                         # large target: card in a corner
            assert rect.contains(card) and card.right() > rect.center().x()                 and card.bottom() > rect.center().y()
        else:                                               # the card never hides the target
            assert not card.intersects(rect)
        targets.append(rect)
        if k < len(STEPS) - 1:
            tour.next()
    assert window.explain_button.geometry().size() == targets[1].size()
    assert tour.next_button.text() == "Finish"
    tour.back()
    assert tour.counter.text() == "2 / 3"
    tour.next()
    tour.next()                                             # Finish
    assert not tour.isVisible() and tour_done()


def test_skip_stores_done_and_help_reopens(qtbot, window):
    tour = window.tour
    tour.start()
    tour.skip_button.click()
    assert not tour.isVisible() and tour_done()
    window.tour_action.trigger()
    assert tour.isVisible() and tour.step == 0
    qtbot.keyClick(tour, Qt.Key.Key_Escape)
    assert not tour.isVisible()


# --- M8 restyle ------------------------------------------------------------------------------

def test_header_shows_the_3d_render(welcome):
    from busemann.paths import resource_path

    assert resource_path("images", "inlet_3d.png").is_file()
    assert not welcome.pixmap.isNull() and welcome.pixmap.width() > 400
    shown = welcome.image.pixmap()
    assert shown is not None and not shown.isNull()


def test_cards_are_title_plus_mono_subtitle_and_focusable(qtbot, welcome):
    from busemann.theme import qt as theme

    name, card = welcome.cards[0]
    assert card.title_label.text() == name and card.title_label.font().weight() == 500
    assert card.sub_label.font().family() == theme.mono_family()
    assert card.title_label.alignment() & Qt.AlignmentFlag.AlignLeft
    assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
    qtbot.keyClick(card, Qt.Key.Key_Space)
    assert welcome.choice == ("preset", name)
    assert welcome.open_button.objectName() == "secondaryButton"


def test_recent_empty_state(welcome):
    assert not welcome.recent_list.isVisibleTo(welcome)
    assert welcome.recent_empty.isVisibleTo(welcome)
    assert welcome.recent_empty.text() == W.RECENT_EMPTY
