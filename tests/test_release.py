"""Release automation (M12 PART 5, no Qt): tools/changelog_section.py (tag check and release
notes) and the settings of .github/workflows/release.yml."""
import importlib.util
from pathlib import Path

import pytest

from busemann import __version__

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def _tool():
    spec = importlib.util.spec_from_file_location("changelog_section",
                                                  ROOT / "tools" / "changelog_section.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SAMPLE = """# Changelog

## 1.1.0 — second

- later thing

## [1.0.0] - 2026-11-20

### Design
- first thing

## 0.9.0
- older
"""


# --- changelog_section.py ----------------------------------------------------------------------
def test_section_is_the_body_up_to_the_next_heading():
    t = _tool()
    assert t.section(SAMPLE, "1.0.0") == "### Design\n- first thing"
    assert t.section(SAMPLE, "1.1.0") == "- later thing"
    assert t.section(SAMPLE, "0.9.0") == "- older"


def test_section_does_not_match_a_longer_version():
    t = _tool()
    with pytest.raises(t.ReleaseError, match="no '## 1.0' section"):
        t.section(SAMPLE, "1.0")
    with pytest.raises(t.ReleaseError, match="no '## 1.1.0.1' section"):
        t.section("## 1.1.0\n- x\n", "1.1.0.1")


def test_missing_or_empty_sections_fail():
    t = _tool()
    with pytest.raises(t.ReleaseError, match="no '## 2.0.0' section"):
        t.section(SAMPLE, "2.0.0")
    with pytest.raises(t.ReleaseError, match="is empty"):
        t.section("## 1.0.0\n\n## 0.9.0\n- x\n", "1.0.0")


def test_tag_must_equal_the_app_version():
    t = _tool()
    t.check_tag("v1.0.0", "1.0.0")
    for bad in ("1.0.0", "v1.0", "v1.0.1", "V1.0.0", "v1.0.0-rc1"):
        with pytest.raises(t.ReleaseError, match="does not match"):
            t.check_tag(bad, "1.0.0")
    assert t.app_version() == __version__


def test_main_writes_the_notes_and_rejects_a_wrong_tag(tmp_path, capsys):
    t = _tool()
    out = tmp_path / "notes" / "release_notes.md"
    assert t.main([f"v{__version__}", str(out)]) == 0
    assert out.read_text(encoding="utf-8").strip() == t.section(
        (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), __version__)
    assert t.main(["v0.0.1", str(tmp_path / "x.md")]) == 1
    assert "does not match" in capsys.readouterr().err
    assert not (tmp_path / "x.md").exists()


def test_changelog_has_a_section_for_this_version():
    body = _tool().section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), __version__)
    assert len(body) > 40


# --- release.yml --------------------------------------------------------------------------------
def test_workflow_runs_on_version_tags_on_windows_with_python_3_14():
    assert 'tags: ["v*"]' in WORKFLOW
    assert "runs-on: windows-2022" in WORKFLOW
    assert 'python-version: "3.14"' in WORKFLOW
    assert "contents: write" in WORKFLOW


def test_workflow_builds_with_the_release_script_and_a_300_s_self_test():
    assert "choco install innosetup" in WORKFLOW
    assert ("./tools/build_release.ps1 -Python python -SelfTestTimeout 300 "
            "-SelfTestLog build/selftest.log") in WORKFLOW
    assert 'python tools/changelog_section.py "$env:GITHUB_REF_NAME" build/release_notes.md' \
        in WORKFLOW
    # the notes (and the tag check) run before the long build
    assert WORKFLOW.index("changelog_section.py") < WORKFLOW.index("build_release.ps1 -Python")


def test_workflow_uploads_the_self_test_log_always():
    step = WORKFLOW[WORKFLOW.index("- name: Upload the self-test log"):]
    step = step[:step.index("- name: Publish")]
    assert "if: always()" in step
    assert "actions/upload-artifact@v4" in step
    assert "path: build/selftest.log" in step


def test_workflow_publishes_the_three_assets_with_the_changelog_notes():
    step = WORKFLOW[WORKFLOW.index("- name: Publish the GitHub Release"):]
    for asset in ('"dist/Busemann-Setup-$version.exe"', '"dist/Busemann-$version-portable.zip"',
                  '"dist/SHA256SUMS.txt"'):
        assert asset in step, asset
    assert '--title "Busemann $version"' in step
    assert "--notes-file build/release_notes.md" in step
    assert "GH_TOKEN: ${{ github.token }}" in step


def test_workflow_parses_as_yaml():
    yaml = pytest.importorskip("yaml")
    data = yaml.safe_load(WORKFLOW)
    job = data["jobs"]["windows"]
    names = [s.get("name") for s in job["steps"]]
    assert names.index("Upload the self-test log") > names.index("Build, self-test and package")
    assert data[True]["push"]["tags"] == ["v*"]           # YAML 1.1: "on" is True


def test_tests_workflow_still_runs_core_and_gui():
    tests = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "core:" in tests and "gui:" in tests and 'pytest -m "not perf" -ra' in tests
