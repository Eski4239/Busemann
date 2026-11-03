"""validation.json (single source for the About table and the CFD overlay) and the bundled
licences (no Qt)."""
import importlib.metadata as md
import json

import pytest

from busemann.charts import model
from busemann.paths import resource_path


def test_validation_phases_match_the_reports():
    data = model.load_validation()
    by = {(p["id"], p["metric"]): p for p in data["phases"]}
    # SOURCE: docs/validation_3a.md (outlet p0 -0.35%), docs/validation_3b.md ("reproduces 3a
    # within 0.15% everywhere"), docs/validation_3d.md (below design within 0.1% recovery /
    # 0.4% capture; -4.9% recovery at M 3.25, Mach reflection at the lip); numbers given by
    # the user in the M6 request.
    assert by[("3a", "recovery")]["difference_percent"] == -0.35
    assert by[("3b", "all compared quantities")]["difference_percent"] == 0.15
    assert by[("3d", "recovery / capture")]["difference_percent"] == [0.1, 0.4]
    above = by[("3d", "recovery")]
    assert above["difference_percent"] == -4.9 and "Mach reflection" in above["explanation"]
    assert {p["doc"] for p in data["phases"]} == {"docs/validation_3a.md",
                                                  "docs/validation_3b.md",
                                                  "docs/validation_3d.md"}


def test_cfd_overlay_reads_the_same_file():
    assert model.load_cfd() == model.load_validation()["cfd_overlay"]
    with pytest.raises(FileNotFoundError):
        resource_path("data", "cfd_phase3d.json")           # retired: one source of truth


def _components():
    return json.loads(resource_path("licenses", "components.json").read_text("utf-8"))[
        "components"]


def test_licence_texts_are_bundled_with_the_right_headers():
    heads = {
        "LGPL-3.0.txt": "GNU LESSER GENERAL PUBLIC LICENSE",
        "GPL-3.0.txt": "GNU GENERAL PUBLIC LICENSE",
        "Inter-OFL.txt": "SIL Open Font License, Version 1.1",
        "JetBrainsMono-OFL.txt": "SIL Open Font License, Version 1.1",
        "ezdxf-MIT.txt": "MIT License",
        "matplotlib-LICENSE.txt": "License agreement for matplotlib",
    }
    for name, head in heads.items():
        text = resource_path("licenses", name).read_text(encoding="utf-8")
        assert head in text[:400], name
    assert "Version 3, 29 June 2007" in resource_path("licenses", "LGPL-3.0.txt").read_text(
        encoding="utf-8")[:300]
    for comp in _components():
        for f in comp["files"]:
            assert resource_path("licenses", f).is_file()


def test_stated_licences_match_installed_metadata():
    """The About dialog's licence names agree with what each installed package declares."""
    for comp in _components():
        if not comp["dist"]:
            continue
        try:
            meta = md.metadata(comp["dist"])
        except md.PackageNotFoundError:
            continue                                         # e.g. core CI without PySide6
        declared = " ".join([meta.get("License-Expression") or "", meta.get("License") or ""]
                            + (meta.get_all("Classifier") or []))
        assert comp["metadata_expect"] in declared, (comp["name"], declared[:120])
