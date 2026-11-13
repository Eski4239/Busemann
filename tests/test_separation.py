"""Approximate incipient-separation checks (addendum C5, no Qt).

Criteria and SOURCEs in inletdesign/separation.py (Korkegi 1975; normal-shock M ~ 1.3),
originals not consulted (widely cited correlations). The expected verdicts for the validation design are the Phase 3b
viscous CFD result (docs/validation_3b.md): a corner separation bubble at the second ramp
corner (15.5 mm), none at the first ramp.
"""
import pytest

from inletdesign import api
from inletdesign import separation as S


@pytest.fixture(scope="module")
def checks():
    return {c.shock: c for c in api.design(3.0, 2).separation}


def test_validation_design_flags_the_second_ramp_shock(checks):
    r2 = checks["ramp shock 2"]
    # M1 2.256 and p2/p1 2.818: the values stated for this shock in the M8 request (the
    # model's own design-point output, self-consistency); the verdict is the Phase 3b result
    assert r2.M1 == pytest.approx(2.256, abs=5e-4) and r2.value == pytest.approx(2.818, abs=5e-4)
    assert r2.flagged and r2.in_range


def test_ramp_1_is_not_applicable_and_the_terminal_shock_is_flagged(checks):
    r1 = checks["ramp shock 1"]          # sharp leading edge: no upstream boundary layer
    assert not r1.applicable and not r1.flagged
    assert r1.threshold is None and r1.ratio is None and r1.margin is None
    assert "leading edge" in r1.note
    assert checks["terminal normal shock"].flagged          # M1 1.507 >= 1.3


def test_ramp_1_is_never_assessed_even_when_strong():
    shocks = api.design(3.0, 2, ramp_angles=[20.0, 8.0]).shock_states
    first = S.check_shocks(shocks)[0]
    assert not first.applicable and not first.flagged      # p2/p1 above Korkegi: still n/a


def test_ratio_and_threshold_identities(checks):
    for c in checks.values():
        if not c.applicable:
            continue
        assert c.ratio == pytest.approx(c.value / c.threshold, rel=1e-15)
        assert c.flagged is (c.ratio >= 1.0)
    r2 = checks["ramp shock 2"]
    assert r2.threshold == pytest.approx(1.0 + 0.3 * r2.M1 ** 2, rel=1e-15)
    assert checks["terminal normal shock"].threshold == S.NORMAL_SHOCK_INCIPIENT_MACH


def test_outside_range_gives_no_verdict():
    c = S.check_oblique("ramp shock 2", 5.2, 4.0)
    assert not c.flagged and not c.in_range and "outside" in c.note


def test_notices_are_worded_approximate():
    d = api.design(3.0, 2)
    assert len(d.separation_notices) == 2
    for n in d.separation_notices:
        assert "approximate — verify with CFD" in n.text and "CFD solver" in n.detail
    assert S.KORKEGI_SCOPE in d.separation_notices[0].detail              # oblique: Korkegi
    assert S.KORKEGI_SCOPE == ("correlation for fully turbulent, adiabatic-wall, "
                               "high-Reynolds-number flow")
    assert d.separation_notices[0].text.startswith("Shock-induced separation likely at ramp "
                                                   "shock 2")
    assert not any("separation" in w for w in d.warnings)       # kept out of `notices`


def test_off_design_points_are_checked():
    d = api.design(3.0, 2)
    off = api.off_design_point(d, 2.5)
    assert len(off.separation) == len(off.shock_states)


def test_bad_mach_raises():
    with pytest.raises(ValueError):
        S.korkegi_2d_threshold(0.9)
