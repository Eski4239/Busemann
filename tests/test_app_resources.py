"""Bundled app resources resolve to real files, from source and under PyInstaller."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Pure Python: runs in the core CI job without PySide6 (the Qt loaders live in theme.qt).
from busemann import paths
from busemann.theme import tokens


def test_chevron_resolves_to_existing_file():
    path = paths.resource_path("icons", "chevron-down-muted.svg")
    assert path.is_file()
    assert path.parent.parent == paths.resource_root()


@pytest.mark.parametrize("name", ["chevron-down-muted.svg", "chevron-right-muted.svg",
                                  "chevron-up-muted.svg"])
def test_pretinted_chevron_matches_token(name):
    svg = paths.resource_path("icons", name).read_text(encoding="utf-8")
    assert f'stroke="{tokens.COLORS["text_muted"]}"' in svg
    assert "currentColor" not in svg


def test_missing_resource_raises():
    with pytest.raises(FileNotFoundError):
        paths.resource_path("icons", "does-not-exist.svg")


def test_frozen_bundle_uses_meipass(tmp_path, monkeypatch):
    icon = tmp_path / "busemann" / "resources" / "icons" / "chevron-down-muted.svg"
    icon.parent.mkdir(parents=True)
    icon.write_text("<svg/>", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.resource_path("icons", "chevron-down-muted.svg") == icon


def test_pyproject_ships_icons_and_fonts():
    """package-data must include every resource kind the app loads by path."""
    import tomllib
    from pathlib import Path

    data = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text("utf-8"))
    patterns = data["tool"]["setuptools"]["package-data"]["busemann"]
    assert "resources/icons/*.svg" in patterns
    assert "resources/fonts/*.ttf" in patterns
    assert "resources/data/*.json" in patterns
    assert "resources/explain/*.md" in patterns and "resources/explain/*.json" in patterns


def test_paths_and_tokens_import_without_qt():
    """busemann.paths and busemann.theme.tokens must not pull in PySide6."""
    code = "\n".join([
        "import sys",
        "sys.modules['PySide6'] = None      # any PySide6 import now raises ImportError",
        "import busemann.paths, busemann.theme, busemann.theme.tokens",
        "assert busemann.theme.tokens.COLORS['accent']",
        "assert busemann.paths.resource_root().is_dir()",
        "print('ok')",
    ])
    src = str(Path(__file__).resolve().parents[1] / "src")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         timeout=60, env={**os.environ, "PYTHONPATH": src})
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "ok"
