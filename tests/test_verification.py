"""Verification list and verification_notes.md (addendum C6 / E, no Qt)."""
import re

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
        # every item ends with the CFD statement; the buzz-separation item uses the user's
        # wording "Verify with CFD or wind-tunnel data." (M9c)
        assert item.text.endswith((f"{V.CFD_STATEMENT}.", "Verify with CFD or wind-tunnel data."))
        assert item.criterion and item.source


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
    assert "| mach | 3 |" in text and V.VALIDATION_SUMMARY in text
    assert not re.search(r"phase\s*3", text, re.I) and "validation_3" not in text


# --- M9c: ramp separation reduces the buzz margin (Ferri & Nucci RM L50K30, p. 7) -----------
def _buzz_items(M, n):
    i = Inputs(mach=M, n_ramps=n)
    return [it for it in V.items(api.design(M, n), i, freestream_for(i, M))
            if it.title == V.BUZZ_SEPARATION_TITLE]


def test_separation_buzz_item_for_the_validation_design():
    [item] = _buzz_items(3.0, 2)                   # ramp shock 2 is flagged
    assert item.severity == "warn" and item.category == "buzz"
    assert item.text == V.BUZZ_SEPARATION_TEXT
    assert item.text.endswith("Verify with CFD or wind-tunnel data.")
    assert item.source.startswith("Ferri & Nucci, NACA RM L50K30 (1951), p. 7 and Concluding "
                                  "Remarks pp. 25–26")
    assert "Busemann extension" in item.source
    assert item.source.endswith("Extrapolated beyond the tested Mach range.")   # M 3.0 > 2.7
    assert "chart" not in (item.text + item.source).lower()       # no chart reference yet


def test_separation_buzz_item_absent_without_a_flagged_ramp_shock_and_no_suffix_below_2_7():
    d = api.design(2.0, 2)
    assert not any(c.flagged for c in d.separation if c.shock.startswith("ramp"))
    assert _buzz_items(2.0, 2) == []
    [item] = _buzz_items(2.5, 2)                   # flagged, inside the tested range
    assert "Extrapolated" not in item.source


def test_separation_buzz_item_in_the_notes(validation_items):
    meta = metadata(Inputs(), "geometry DXF")
    text = N.render(meta, validation_items)
    assert V.BUZZ_SEPARATION_TITLE in text and V.BUZZ_SEPARATION_TEXT in text
