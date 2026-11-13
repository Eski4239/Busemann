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


# --- M8.4: internal validation-phase names ("Phase 3b", "phase 3d") never reach the user ---
PHASE = re.compile(r"phase\s*3", re.I)


def _phase_texts():
    """(where, text) of every user-facing string that could name a validation phase."""
    from dataclasses import fields

    from busemann import verification as V
    from busemann.charts import model as CM
    from busemann.explain.content import ENTRY_NAMES
    from busemann.export import notes as N
    from busemann.export.metadata import metadata
    from busemann.inputs import Inputs, freestream_for
    from inletdesign import presets

    out = [("tooltips.json", resource_path("explain", "tooltips.json").read_text(encoding="utf-8")),
           ("validation.json", resource_path("data", "validation.json").read_text(encoding="utf-8")),
           ("chart CFD note", CM.CFD_NOTE), ("chart CFD wedge note", CM.CFD_WEDGE_NOTE),
           ("chart CFD source", CM.load_cfd()["source"]), ("cowl lip note", api.CFD_LIP_NOTE),
           ("validation summary", V.VALIDATION_SUMMARY)]
    out += [(f"{n}.md", resource_path("explain", f"{n}.md").read_text(encoding="utf-8"))
            for n in ENTRY_NAMES]
    out += [(f"preset {p.name}", f"{p.name} {p.description}") for p in presets.PRESETS]
    out += [(f"quote {k}", q) for k, q in V.VALIDATION_CFD.items()]
    out += [("message", t) for t in _notices()]
    i = Inputs()
    d = api.design(3.0, 2)
    for Mo in (2.5, 3.0, 3.25):
        off = api.off_design_point(d, Mo)
        out += [("off-design detail", n.detail or "") for n in off.notices + off.separation_notices]
        items = V.items(d, i, freestream_for(i, 3.0), off, freestream_for(i, Mo))
        for it in items:
            out += [(f"item {it.title}", str(getattr(it, f.name) or "")) for f in fields(it)]
        out.append(("verification_notes.md",
                    N.render(metadata(i, "geometry DXF"), items)))
    out += [("design detail", n.detail or "") for n in d.notices + d.separation_notices]
    return out


def test_no_user_facing_string_names_a_validation_phase():
    hits = [f"{where}: {text[:120]!r}" for where, text in _phase_texts() if PHASE.search(text)]
    assert hits == []
    assert any("the validation CFD" in t for _, t in _phase_texts())    # rephrased, not lost


# --- M12: every source is in its final state; "pending" never reaches the user -------------
PENDING = re.compile(r"\bpending\b", re.I)


def _user_texts():
    """The validation-phase corpus plus the About texts, the separation source constants and
    the rendered Explain sources."""
    from inletdesign import separation as S

    out = list(_phase_texts())
    out += [("Korkegi source", S.KORKEGI_SOURCE), ("normal-shock source", S.NORMAL_SOURCE)]
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "explain_cases", Path(__file__).with_name("test_explain_content.py"))
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    for label, item, name, _ctx, rendered in cases._render_all():
        out += [(f"{label}/{item}/{name} source", ln.source)
                for lines in rendered.sections.values() for ln in lines if ln.source]
    try:
        from busemann.views import about_dialog as A
    except ImportError:                          # no Qt: the core texts are still checked
        return out
    out += [("About", t) for t in (A.ABOUT_TEXT, A.MAKER_TEXT, A.VALIDATION_TEXT,
                                     *A.ABOUT_ASSUMPTIONS)]
    return out


def test_no_user_facing_string_says_pending():
    hits = sorted({f"{where}: {text[:120]!r}" for where, text in _user_texts()
                   if PENDING.search(text)})
    assert hits == []


# --- M8.4: canvas dimension labels and hover / selection rows use real subscripts ---------
CASES = ((3.0, 1), (3.0, 2), (3.0, 3), (6.7, 4))


def test_canvas_dimension_labels_have_no_underscores():
    from busemann.canvas import picture as P

    texts = []
    for M, n in CASES:
        pic = P.build(P.skeleton_from(api.design(M, n)))
        texts += [(f"M{M} n{n}", dim.label) for dim in pic.dimensions]
    assert texts and [f"{w}: {t!r}" for w, t in texts if "_" in t] == []
    assert ("M3.0 n2", "h<sub>c</sub>") in texts and ("M3.0 n2", "h<sub>t</sub>") in texts


def test_hover_and_selection_rows_have_no_underscores():
    pytest.importorskip("PySide6")              # busemann.views imports Qt
    from busemann.canvas import picture as P
    from busemann.inputs import Inputs, freestream_for
    from busemann.views.rows import cowl_rows, region_rows, shock_rows

    texts = []
    for M, n in CASES:
        d = api.design(M, n)
        sk = P.skeleton_from(d)
        pic = P.build(sk)
        fs = freestream_for(Inputs(mach=M, n_ramps=n), M)
        for r in d.regions:
            texts += [(f"M{M} n{n} region", row[1]) for row in region_rows(r, fs, "SI")]
        for s in pic.shocks:
            texts += [(f"M{M} n{n} shock", row[1]) for row in shock_rows(s.state)]
        texts += [(f"M{M} n{n} cowl", row[1]) for row in cowl_rows(sk)]
    assert texts and [f"{w}: {t!r}" for w, t in texts if "_" in t] == []
    assert any(t == "M<sub>n1</sub>" for _, t in texts)
