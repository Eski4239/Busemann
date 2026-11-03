"""About dialog (M6): description, assumptions, validation table, licences."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from busemann.charts import model  # noqa: E402

pytestmark = pytest.mark.gui


def test_about_dialog_tabs(qtbot, window):
    dialog = window.show_about()
    qtbot.addWidget(dialog)
    assert [dialog.tabs.tabText(i) for i in range(3)] == ["About", "Validation", "Licences"]
    assert "Busemann" in dialog.about_label.text() and "inviscid" in dialog.about_label.text()
    table = dialog.validation_table
    phases = model.load_validation()["phases"]
    assert table.rowCount() == len(phases)
    assert [table.item(r, 2).text() for r in range(table.rowCount())] == \
        [p["result"] for p in phases]
    assert "Mach reflection" in dialog.validation_info.text()
    assert "validation_3b.md" in dialog.validation_info.text()
    assert "validation_3d.md" in dialog.validation_info.text()
    names = [dialog.licence_list.item(i).text() for i in range(dialog.licence_list.count())]
    assert any(n.startswith("PySide6 / Qt") and "LGPL-3.0" in n for n in names)
    assert any("SIL OFL 1.1" in n for n in names)
    dialog.licence_list.setCurrentRow(0)
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in dialog.licence_text.toPlainText()
    dialog.close()


def test_help_menu_has_about(window):
    menus = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert menus == ["File", "Edit", "Help"]
    assert window.about_action.text().replace("&", "") == "About Busemann…"
