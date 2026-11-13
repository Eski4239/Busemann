"""The built wheel ships every run-time resource (M12 PART 2a, no Qt).

Builds a wheel with `python -m build` (sdist, then the wheel from it) into a temp folder
(isolated build: needs pip
access to setuptools) and checks that every non-Python file under src/busemann (fonts, icons,
brand, explain entries and tooltips, examples, validation data, licences, the QSS template) is
inside it. Checking against the files on disk, not a hand-kept list, means a new resource that
pyproject's package-data misses fails here.
"""
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("build")

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "busemann"
# the resource groups the app loads at run time; each must have at least one file
RUNTIME_GROUPS = ("resources/fonts/", "resources/icons/", "resources/brand/",
                  "resources/explain/", "resources/examples/", "resources/data/",
                  "resources/licenses/", "theme/")
RUNTIME_FILES = ("resources/explain/tooltips.json", "resources/data/validation.json",
                 "resources/licenses/components.json", "resources/brand/busemann.ico",
                 "resources/brand/app_icon_256.png", "resources/brand/welcome_hero.png",
                 "theme/style.qss.tmpl")


@pytest.fixture(scope="module")
def wheel_names(tmp_path_factory):
    out = tmp_path_factory.mktemp("wheel")
    # sdist, then the wheel from the sdist: built out of tree (no build/ in the repository),
    # and the sdist must carry the resources too
    run = subprocess.run([sys.executable, "-m", "build", "--outdir", str(out), str(ROOT)],
                         capture_output=True, text=True, timeout=600)
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
    (wheel,) = out.glob("*.whl")
    with zipfile.ZipFile(wheel) as zf:
        return wheel.name, set(zf.namelist())


def _resource_files():
    return sorted(p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
                  if p.is_file() and p.suffix not in (".py", ".pyc")
                  and "__pycache__" not in p.parts)


def test_every_resource_file_is_in_the_wheel(wheel_names):
    _, names = wheel_names
    files = _resource_files()
    assert len(files) > 70
    missing = [f for f in files if f"busemann/{f}" not in names]
    assert missing == []


def test_runtime_resource_groups_are_in_the_wheel(wheel_names):
    _, names = wheel_names
    for group in RUNTIME_GROUPS:
        assert any(n.startswith(f"busemann/{group}") for n in names), group
    for f in RUNTIME_FILES:
        assert f"busemann/{f}" in names, f


def test_wheel_version_is_the_app_version(wheel_names):
    from busemann import __version__

    name, _ = wheel_names
    assert f"-{__version__}-" in name
