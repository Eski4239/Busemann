"""Verification list and verification_notes.md (addendum C6 / E, no Qt)."""
import pytest

from inletdesign import api

from busemann import verification as V
from busemann.export import notes as N
from busemann.export.metadata import metadata
from busemann.inputs import Inputs, freestream_for


@pytest.fixture(scope="module")
def validation_items():
    i = Inputs()
    return V.items(api.design(3.0, 2), i, freestream_for(i, 3.0))


def test_categories_present_and_ordered(validation_items):
    cats = {i.category for i in validation_items}
    assert {"separation", "cowl", "real_gas", "upper_bound", "mil", "diffuser"} <= cats
    ranks = [V.SEVERITIES.index(i.severity) for i in validation_items]
    assert ranks == sorted(ranks)
    for item in validation_items:
        assert item.text.endswith(f"{V.CFD_STATEMENT}.") and item.criterion and item.source


def test_validation_case_separation_and_phase_3b_quotes(validation_items):
    sep = {i.title.split(":")[0]: i for i in validation_items if i.category == "separation"}
    assert sep["Ramp shock 2"].severity == "warn" and "15.5 mm" in sep["Ramp shock 2"].quote
    r1 = sep["Ramp shock 1"]
    assert r1.title == "Ramp shock 1: not applicable — no upstream boundary layer"
    assert r1.severity == "info" and "%" not in r1.text and "p₂/p₁" not in r1.criterion
    assert "no separation on the first ramp" in r1.quote and r1.tooltip is None
    assert "adiabatic-wall" in sep["Ramp shock 2"].tooltip
    assert sep["Terminal normal shock"].severity == "warn"
    assert all("approximate — verify with CFD" in i.text for i in sep.values())
    assert V.badge_count(validation_items) == sum(
        1 for i in validation_items if i.severity in ("warn", "error"))


def test_no_phase_3b_quote_for_another_geometry():
    i = Inputs(mach=2.5, n_ramps=3)
    items = V.items(api.design(2.5, 3), i, freestream_for(i, 2.5))
    assert all(it.quote is None for it in items if it.category == "separation")


def test_off_design_items_and_upper_bound():
    d = api.design(3.0, 2)
    off = api.off_design_point(d, 3.25)
    i = Inputs()
    items = V.items(d, i, freestream_for(i, 3.0), off, freestream_for(i, 3.25))
    ub = next(it for it in items if it.category == "upper_bound")
    assert ub.severity == "warn"
    assert any("M∞ 3.25" in it.text for it in items if it.category == "separation")


def test_notes_contain_every_item_and_the_cfd_statement(tmp_path, validation_items):
    meta = metadata(Inputs(), "geometry DXF")
    path = N.write_verification_notes(tmp_path / "x.dxf", meta, validation_items)
    assert path == tmp_path / "verification_notes.md"
    text = path.read_text(encoding="utf-8")
    for item in validation_items:
        assert item.title in text and item.source in text and item.criterion in text
    for a in V.ASSUMPTIONS:
        assert a in text
    assert "## CFD statement" in text and N.CFD_PARAGRAPH in text
    assert "| mach | 3 |" in text and "Phase" in text and "validation_3b.md" in text
