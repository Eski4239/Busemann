"""Repository front door (M12 PART 6, no Qt): README, CHANGELOG and LICENSE content agree
with the app and every linked image exists."""
import re
from pathlib import Path

from busemann import __version__

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CHANGELOG = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
REPO = "https://github.com/Eski4239/Busemann"


def test_every_linked_image_exists():
    images = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', README) + re.findall(r'<img src="([^"]+)"',
                                                                        README)
    assert len(images) >= 6
    for path in images:
        assert (ROOT / path).is_file(), path
    shots = [p for p in images if p.startswith("docs/screenshots/")]
    assert 3 <= len(shots) <= 4


def test_readme_order_and_sections():
    heads = re.findall(r"^## (.+)$", README, re.M)
    assert heads == ["Download", "Features", "How it works", "Validation", "Build from source",
                     "Licence"]
    assert "### Running tests" in README and 'pytest -m "not perf"' in README
    assert README.index("logo_lockup_stacked_2x.png") < README.index("welcome_hero.png") \
        < README.index("## Download")
    assert 'width="220"' in README


def test_download_section():
    download = README[README.index("## Download"):README.index("## Features")]
    assert f"{REPO}/releases/latest" in download
    assert ("The installer is not code-signed, so Windows SmartScreen may warn on first run: "
            "choose\n  **More info → Run anyway**") in download
    assert "The first launch can take up to a minute while Windows scans the new files." \
        in download
    assert "Windows 10/11 64-bit, ~250 MB disk" in download


def test_validation_is_the_about_paragraph_plus_the_tm_1140_line():
    from busemann import verification as V

    assert V.VALIDATION_SUMMARY in README
    assert "Maximum recoveries agree with Oswatitsch's 1944 results (NACA TM 1140, Fig. 1)" \
        in README
    assert not re.search(r"phase\s*\d", README, re.I)            # no internal phase names


def test_about_readme_and_changelog_state_the_same_test_count():
    from busemann import verification as V          # About shows V.VALIDATION_SUMMARY

    pattern = re.compile(r"over ([\d,]+) (?:automated )?tests")
    counts = {where: pattern.findall(text) for where, text in
              (("About", V.VALIDATION_SUMMARY), ("README", README), ("CHANGELOG", _section()))}
    assert all(counts.values()), counts
    assert {c for found in counts.values() for c in found} == {"1,000"}, counts


def test_how_it_works_cites_both_sources():
    how = README[README.index("## How it works"):README.index("## Validation")]
    assert "NACA Report 1135" in how and "NACA TM 1140" in how and "Oswatitsch" in how


def test_licence_section_and_file():
    assert "[MIT License](LICENSE)" in README
    assert (ROOT / "LICENSE").read_text(encoding="utf-8").startswith("MIT License")


def _section():
    import importlib.util

    spec = importlib.util.spec_from_file_location("changelog_section",
                                                  ROOT / "tools" / "changelog_section.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.section(CHANGELOG, __version__)


def test_changelog_is_written_for_a_visitor():
    body = _section()
    assert CHANGELOG.splitlines()[2] == f"## {__version__} — first release"
    assert body.startswith("Busemann is a desktop design lab")      # what it does, first
    opening = " ".join(body.split("\n\n")[0].split())
    assert ("where its boundary layer is likely to separate (and what that means for buzz), "
            "and what to check with CFD.") in opening
    groups = re.findall(r"^### (.+)$", body, re.M)
    assert groups == ["Design", "Off-design", "Analytics", "Compare", "Isentropic ramp",
                      "Explain and Verification", "Files and export", "Validation",
                      "Engineering"]
    validation = body[body.index("### Validation"):body.index("### Engineering")]
    assert len([ln for ln in validation.splitlines() if ln.startswith("- ")]) == 2
    assert "PART 6" not in body and "placeholder" not in body.lower()
    assert "159efb5" not in body                                  # development note, not here


def test_the_inlet_characteristic_is_not_advertised():
    """Removed before 1.0: neither the README nor the release text mentions it."""
    for text in (README, _section()):
        low = text.lower()
        assert "inlet characteristic" not in low and "buzz onset" not in low
        assert "subcritical" not in low
