"""User-facing text audit (M8.2, no Qt): no raw ASCII symbol names ("theta_max", "M_inf",
"M1 sin(beta)", "phi_lip"), no "deg" for degrees, no space before °, in the explain entries,
the tooltips and the notices / errors the core shows. LaTeX ($$ … $$), template paths
({{ … }}) and SOURCE comments are code, not text, and are not scanned."""
import json
import re

import pytest

from busemann.paths import resource_path
from inletdesign import api

FORBIDDEN = {
    "theta_max": r"\btheta_?max\b",
    "M_inf": r"\bM_inf\b|\bM_infinity\b",
    "phi_*": r"\bphi(_\w+)?\b",
    "beta": r"\bbeta\b",
    "theta": r"\btheta\b",
    "gamma": r"\bgamma\b",
    "deg": r"\bdeg\b",                 # "in degrees" is fine English; "deg" is not
    "space before °": r"\d\s+°",
    "sin(": r"\b(sin|cos|tan)\((?=[A-Za-z])",     # sin(beta); sin(β − θ) is fine
    "Mn1/M1 ascii": r"\bMn[12]\b|\bM[12]\b",
    "_inf": r"\b[pT]0?_inf\b|_inf\b",
    "x_max": r"\b[a-zA-Z]+_(max|min)\b",
    "θ_ subscript": r"[θβφ]_",               # write θmax, not θ_max (one style)
}


def _violations(name, text):
    out = []
    for label, pattern in FORBIDDEN.items():
        for m in re.finditer(pattern, text, re.M):
            line = text[:m.start()].count("\n") + 1
            out.append(f"{name}:{line} [{label}] {text.splitlines()[line - 1].strip()[:100]}")
    return out


def _md_prose(text):
    text = re.sub(r"\$\$.*?\$\$", "", text)               # LaTeX equations
    text = re.sub(r"\{\{.*?\}\}", "", text)               # template paths
    text = re.sub(r"<!--.*?-->", "", text)                # SOURCE comments
    return re.sub(r"^@(if|each)[^:]*:", "", text, flags=re.M)   # directives


def test_explain_entries_have_no_raw_symbols():
    from busemann.explain.content import ENTRY_NAMES

    problems = []
    for name in ENTRY_NAMES:
        text = resource_path("explain", f"{name}.md").read_text(encoding="utf-8")
        problems += _violations(f"{name}.md", _md_prose(text))
    assert problems == []


def test_tooltips_have_no_raw_symbols():
    tips = json.loads(resource_path("explain", "tooltips.json").read_text(encoding="utf-8"))
    problems = []
    for key, text in tips.items():
        problems += _violations(f"tooltips[{key}]", text)
    assert problems == []


def _notices():
    """Every notice / warning / error text the core produces over a range of designs."""
    texts = set()
    for M, n, kw in ((3.0, 2, {}), (6.7, 4, {}), (3.0, 3, {"max_cowl_angle": 30.0}),
                     (2.2, 2, {"ramp_angles": [12.0, 14.0]}), (3.0, 2, {"cowl_wedge": 8.0}),
                     (1.6, 1, {}), (4.0, 3, {"ramp_angles": [10.0, 12.0, 14.0]})):
        try:
            d = api.design(M, n, **kw)
        except ValueError as exc:
            texts.add(str(exc))
            continue
        texts.update(n_.text for n_ in d.notices + d.separation_notices)
        for Mo in (1.3, 0.85 * M, M, M + 0.25, M + 1.0):
            try:
                off = api.off_design_point(d, Mo)
            except ValueError as exc:
                texts.add(str(exc))
                continue
            texts.update(n_.text for n_ in off.notices + off.separation_notices)
        fs = api.freestream(M, altitude_m=31000.0)
        texts.update(fs.warnings)
    for bad in ((3.0, 2, [40.0, 40.0]), (1.8, 3, [20.0, 5.0, 5.0]), (3.0, 1, [-1.0])):
        try:
            api.design(bad[0], bad[1], ramp_angles=bad[2])
        except ValueError as exc:
            texts.add(str(exc))
    return sorted(texts)


@pytest.mark.parametrize("text", _notices())
def test_core_messages_have_no_raw_symbols(text):
    assert _violations("message", text) == []


def test_explain_sources_shown_in_the_popup_have_no_raw_symbols():
    """The popup shows each equation's SOURCE line, so it is user-facing text too."""
    import re as _re

    from busemann.explain.content import ENTRY_NAMES

    problems = []
    for name in ENTRY_NAMES:
        text = resource_path("explain", f"{name}.md").read_text(encoding="utf-8")
        for source in _re.findall(r"<!--\s*SOURCE:\s*(.+?)\s*-->", text):
            problems += _violations(f"{name}.md SOURCE", source)
    assert problems == []


def test_rendered_explain_text_has_no_raw_symbols():
    """What the Explain popup shows (after rendering): every SOURCE line, text and bullet
    line and the title, for every case and item of the content tests."""
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "explain_cases", Path(__file__).with_name("test_explain_content.py"))
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    _render_all = cases._render_all

    problems = []
    for label, item, name, _ctx, rendered in _render_all():
        where = f"{label}/{item}/{name}"
        problems += _violations(f"{where} title", rendered.title)
        for section, lines in rendered.sections.items():
            for ln in lines:
                if ln.source:
                    problems += _violations(f"{where} {section} source", ln.source)
                if ln.kind in ("text", "bullet"):
                    problems += _violations(f"{where} {section}", ln.text)
    assert sorted(set(problems)) == []
