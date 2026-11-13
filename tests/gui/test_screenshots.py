"""`busemann --screenshots DIR` (M12 PART 6): the README images come from the real app, each
saved only after its view has finished computing."""
import pytest

pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

pytestmark = pytest.mark.gui


def test_capture_writes_the_four_readme_images(qtbot, tmp_path, monkeypatch):
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from busemann import screenshots as S
    from busemann.app import setup_application

    monkeypatch.setenv("BUSEMANN_SETTINGS_FILE", str(tmp_path / "settings.ini"))
    app = setup_application(QApplication.instance())
    paths = S.capture(tmp_path / "shots", app)
    assert [p.name for p in paths] == list(S.SHOTS)
    for path in paths:
        image = QImage(str(path))
        assert not image.isNull(), path.name
        assert image.width() >= 900 and image.height() >= 600, (path.name, image.size())


def test_cli_needs_an_output_folder():
    from busemann import screenshots as S

    assert S.main(["--screenshots"]) == 2
