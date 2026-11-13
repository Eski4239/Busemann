"""One version (M12 PART 2.5, no Qt): busemann.__version__ is the single source; pyproject
reads it, the installed metadata follows it, and no other file hard-codes another version."""
import importlib.metadata as md
import re
import tomllib
from pathlib import Path

from busemann import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_version_is_1_0_0():
    assert __version__ == "1.0.0"
    assert re.fullmatch(r"\d+\.\d+\.\d+", __version__)


def test_pyproject_reads_the_version_from_the_package():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in data["project"]
    assert "version" in data["project"]["dynamic"]
    assert data["tool"]["setuptools"]["dynamic"]["version"] == {"attr": "busemann.__version__"}


def test_installed_metadata_agrees():
    assert md.version("supersonic-inlet-designer") == __version__


def test_export_metadata_uses_the_version():
    from busemann.export.metadata import metadata
    from busemann.inputs import Inputs

    assert metadata(Inputs(), "geometry DXF")["app_version"] == __version__


def test_no_other_version_is_hard_coded():
    """Files that state the app version must state this one (packaging and docs included)."""
    pattern = re.compile(r"""(?:__version__|app_version|APP_VERSION|AppVersion|"version")\s*[=:]\s*"""
                         r"""["'](\d+\.\d+\.\d+)["']""")
    files = [ROOT / "pyproject.toml", ROOT / "README.md"]
    for folder in ("src", "packaging", "tools", ".github"):
        if (ROOT / folder).exists():
            files += [p for p in (ROOT / folder).rglob("*")
                      if p.suffix in (".py", ".toml", ".iss", ".spec", ".ps1", ".yml", ".md")]
    wrong = [f"{p.relative_to(ROOT)}: {m.group(1)}" for p in files if p.is_file()
             for m in pattern.finditer(p.read_text(encoding="utf-8", errors="replace"))
             if m.group(1) != __version__]
    assert wrong == []
