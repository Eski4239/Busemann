"""Brand files (M12 PART 1, no Qt): the assets ship with the package and the old 3D render
is gone everywhere."""
from pathlib import Path

from busemann.paths import resource_path

ROOT = Path(__file__).resolve().parents[1]


def test_brand_assets_are_bundled():
    for n in (16, 24, 32, 48, 64, 128, 256):
        assert resource_path("brand", f"app_icon_{n}.png").is_file()
    for name in ("logo_lockup.svg", "logo_lockup_2x.png", "welcome_hero.png", "busemann.ico"):
        assert resource_path("brand", name).is_file()
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for pattern in ("resources/brand/*.svg", "resources/brand/*.png", "resources/brand/*.ico"):
        assert pattern in pyproject


def test_old_icon_and_render_are_removed():
    assert not (ROOT / "src/busemann/resources/icons/busemann.svg").exists()
    assert not (ROOT / "src/busemann/resources/images").exists()
    assert not (ROOT / "tools" / ("render_inlet" + "_3d.py")).exists()


def test_no_reference_to_the_old_render_remains():
    old = "inlet" + "_3d"                     # split so this file does not match itself
    files = [ROOT / "pyproject.toml", ROOT / "README.md"]
    for folder in ("src", "tests", "tools", "docs"):
        files += [p for p in (ROOT / folder).rglob("*")
                  if p.suffix in (".py", ".md", ".json", ".toml", ".qss", ".tmpl", ".txt")]
    hits = [str(p.relative_to(ROOT)) for p in files
            if p.is_file() and p.name != "m12_brief.md"
            and old in p.read_text(encoding="utf-8", errors="replace")]
    assert hits == []
