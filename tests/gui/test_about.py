"""About dialog (M6, M8.4): description, maker, assumptions, how it was checked, licences."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

import html  # noqa: E402
import re  # noqa: E402

pytestmark = pytest.mark.gui


@pytest.mark.ui
def test_about_dialog_sections(qtbot, window):
    from busemann.views import about_dialog as A

    dialog = window.show_about()
    qtbot.addWidget(dialog)
    text = dialog.about_label.text()
    assert "I made Busemann" in text and "inviscid" in text
    assert "[your words here]" not in text and len(A.ABOUT_ASSUMPTIONS) == 3
    assert "Who made it and why" in text
    assert A.MAKER_TEXT == (
        "My name is Pablo Goulet Valenti and I made this during my university years in order "
        "to explore the world of high-speed flows. Inlets are a key part of powerplants and "
        "propulsion systems, and being able to build an interactive solver to design these "
        "geometries allows one to learn quite a bit. I hope this tool is useful to you and you "
        "learn something new along the way too!")
    assert html.escape(A.MAKER_TEXT) in text
    assert not dialog.licences.isVisibleTo(dialog)               # licences collapsed
    dialog.licences_toggle.setChecked(True)
    assert dialog.licences.isVisibleTo(dialog)
    assert not hasattr(dialog, "validation_table")                # the table is gone
    assert dialog.validation_info.text() == A.VALIDATION_TEXT
    assert dialog.validation_info.text().startswith("How it was checked: every relation")
    assert "4.9% lower at Mach 3.25" in dialog.validation_info.text()
    assert not re.search(r"phase\s*3", text + dialog.validation_info.text(), re.I)
    names = [dialog.licence_list.item(i).text() for i in range(dialog.licence_list.count())]
    assert any(n.startswith("PySide6 / Qt") and "LGPL-3.0" in n for n in names)
    assert any("SIL OFL 1.1" in n for n in names)
    dialog.licence_list.setCurrentRow(0)
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in dialog.licence_text.toPlainText()
    dialog.close()


@pytest.mark.ui
def test_help_menu_has_about(window):
    menus = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert menus == ["File", "Edit", "Tools", "Help"]
    assert window.about_action.text().replace("&", "") == "About Busemann…"


@pytest.mark.ui
def test_about_text_is_plain():
    import re

    from busemann.views import about_dialog as A

    text = " ".join([A.ABOUT_TEXT, A.MAKER_TEXT, *A.ABOUT_ASSUMPTIONS])
    for word in ("comprehensive", "robust", "powerful", "seamless", "cutting-edge",
                 "state-of-the-art", "leverage"):
        assert word not in text.lower(), word
    assert not re.search(r"—[^—]*—", text)                        # no em-dash chains
    assert "—" not in text
    assert A.ABOUT_TEXT.count(". ") + 1 <= 3                      # 2-3 sentences


@pytest.mark.ui
def test_about_window_uses_the_tokens(qtbot, window):
    from busemann.theme import tokens

    dialog = window.show_about()
    qtbot.addWidget(dialog)
    qtbot.wait(50)
    image = dialog.grab().toImage()
    corner = image.pixelColor(2, 2).name()
    assert corner in (tokens.COLORS["surface"].lower(), tokens.COLORS["bg"].lower()), corner
    dialog.close()
