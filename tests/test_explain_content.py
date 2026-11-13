"""Explain-mode content (no Qt): every entry parses and renders, keys are checked, every
equation is sourced, and every number shown comes from the api result objects."""
import re

import pytest

from busemann.explain import content as C
from busemann.explain.select import build_context, topic_context
from inletdesign import api

NUMBER = re.compile(r"[-+−]?\d+\.\d+")


def _fs(M):
    return api.freestream(M, altitude_m=20000.0)


def _items(result):
    """Every selectable item of a result: (kind, index)."""
    n_regions, n_shocks = len(result.regions), len(result.shock_states)
    return ([("region", i) for i in range(n_regions)] + [("shock", i) for i in range(n_shocks)]
            + [("cowl", 0), (None, None)])


def _cases():
    """(label, design, off, view) for the cases the drawer must handle."""
    d = api.design(3.0, 2)
    x15 = api.design(6.7, 4)
    wedge = api.design(3.0, 2, cowl_wedge=6.0)
    yield "default", d, api.off_design_point(d, 3.0), "design"
    yield "default-off-2.5", d, api.off_design_point(d, 2.5), "offdesign"
    yield "default-off-3.25", d, api.off_design_point(d, 3.25), "offdesign"
    yield "x15", x15, api.off_design_point(x15, 6.7), "design"
    yield "wedge6-off-2.55", wedge, api.off_design_point(wedge, 2.55), "offdesign"
    yield "subsonic-lip-2.40", d, api.off_design_point(d, 2.40), "offdesign"
    yield "custom", api.design(2.5, 1, ramp_angles=[10.0]), None, "design"
    yield "constrained", api.design(3.0, 3, max_cowl_angle=30.0), None, "design"


def _render_all():
    for label, d, off, view in _cases():
        result = off if view == "offdesign" else d
        fs, off_fs = _fs(d.inputs.M), (_fs(off.M_inf) if off is not None else None)
        for kind, index in _items(result):
            name, ctx = build_context(d, off, fs, off_fs, view, kind, index)
            yield label, (kind, index), name, ctx, C.render(C.load(name), ctx)
        for topic in ("method", "offdesign", "separation"):
            if topic == "offdesign" and off is None:
                continue
            name, ctx = topic_context(topic, d, off, fs, off_fs)
            yield label, topic, name, ctx, C.render(C.load(name), ctx)


def test_every_entry_parses_with_sourced_relations():
    for name in C.ENTRY_NAMES:
        entry = C.load(name)
        assert set(entry.sections) == set(C.SECTIONS), name
        sources = entry.sources()
        assert sources, name
        for tex, source in sources:
            assert source, (name, tex)
            assert (source.startswith(("NACA Report 1135", "Oswatitsch", "Korkegi",
                                       "Seddon"))
                    or source.startswith("definition used by this tool")), (name, source)
            assert "pending" not in source.lower(), (name, source)  # final state (M12)
            if source.startswith("Oswatitsch"):                     # confirmed (M12)
                assert "NACA TM 1140" in source and "eq. (17), p. 13" in source
                assert "Bericht Nr. 1005" in source
            if source.startswith(("Korkegi", "Seddon")):          # originals not obtained
                assert "(original not consulted; widely cited correlation)" in source
        text = C.entry_text(name)
        assert "Connection with normal shock" not in text           # no such NACA heading
        assert r"^\circ" not in text                               # use \degree (no gap)


def test_every_entry_renders_for_every_case_and_item():
    seen = set()
    for label, item, name, ctx, rendered in _render_all():
        seen.add(name)
        assert rendered.title and rendered.sections["This case"], (label, item)
        assert "{{" not in str(rendered.sections) and "}}" not in rendered.title
    assert seen == set(C.ENTRY_NAMES)


def test_unknown_keys_and_none_values_fail_loudly():
    d = api.design(3.0, 2)
    _, ctx = build_context(d, None, _fs(3.0), None, "design", "shock", 0)
    for bad in ("{{sel.not_a_field}}", "{{nope.M1}}", "{{shock[9].M1}}", "{{region[k+7].M}}",
                "{{sel._asdict}}", "{{off.M_inf}}"):            # off is None here
        entry = C.parse(f"# t\n## This case\n{bad}\n", "bad")
        with pytest.raises(C.TemplateError):
            C.render(entry, ctx)
    with pytest.raises(C.TemplateError, match="SOURCE"):
        C.parse("# t\n## Relations\n$$ x = 1 $$\n", "unsourced")
    with pytest.raises(C.TemplateError, match="unknown section"):
        C.parse("# t\n## Other\ntext\n", "badsection")


def _api_value(path, d, off, fs, kind, index):
    """Independent lookup of a template path on the api objects (not the app's resolver)."""
    result = off if off is not None else d
    roots = {"design": d, "off": off, "fs": fs, "res": result,
             "cfd_lip_note": api.CFD_LIP_NOTE}
    if kind == "shock":
        roots.update(sel=result.shock_states[index], k=index + 1)
    elif kind == "region":
        roots.update(sel=result.regions[index], k=index)
    else:
        roots.update(sel=result, k=0)
    head, *steps = re.findall(r"[A-Za-z_]\w*|\[[^\]]+\]", path)
    k = roots["k"]
    if head in ("shock", "shocks"):
        value = list(result.shock_states)
        one_based = True
    elif head in ("region", "regions"):
        value, one_based = list(result.regions), False
    else:
        value, one_based = roots[head], False
    for step in steps:
        if step.startswith("["):
            i = eval(step[1:-1], {}, {"k": k})          # noqa: S307 - test-only, k/n arithmetic
            value = value[i - 1] if one_based else value[i]
            one_based = False
        else:
            value = getattr(value, step)
    return value


def test_every_number_in_the_default_case_is_an_api_value():
    d = api.design(3.0, 2)
    off = api.off_design_point(d, 3.0)
    fs = _fs(3.0)
    checked = 0
    for kind, index in _items(d):
        name, ctx = build_context(d, off, fs, None, "design", kind, index)
        rendered = C.render(C.load(name), ctx)
        shown = [s.text for s in rendered.substitutions]
        # 1) each substitution equals the api value at the displayed precision
        for sub in rendered.substitutions:
            if sub.path.startswith(("it.", "n")) or sub.path == "k":
                continue                     # loop bindings: checked through their own paths
            expected = _api_value(sub.path, d, None, fs, kind, index)
            assert sub.text == format(expected, sub.spec), (name, sub.path)
            checked += 1
        # 2) no number appears that did not come from a substitution
        for section in ("This case", "In plain words"):
            for line in rendered.sections[section]:
                for number in NUMBER.findall(line.text):
                    bare = number.lstrip("+-−")
                    assert any(bare in text for text in shown), (name, section, number)
    assert checked > 60


def test_loop_bindings_are_api_values():
    d = api.design(3.0, 2)
    name, ctx = topic_context("method", d, None, _fs(3.0), None)
    rendered = C.render(C.load(name), ctx)
    mn = [s for s in rendered.substitutions if s.path == "it.Mn1"]
    assert [s.text for s in mn] == [f"{s.Mn1:.4f}" for s in d.shock_states if s.kind == "oblique"]


def test_every_equation_renders_with_mathtext():
    from busemann.explain.mathsvg import tex_to_svg

    tex_seen = set()
    for _, _, _, _, rendered in _render_all():
        for lines in rendered.sections.values():
            tex_seen.update(ln.text for ln in lines if ln.kind == "equation")
    for tex in sorted(tex_seen):
        svg = tex_to_svg(tex)
        assert svg.startswith(b"<?xml") and b"<svg" in svg, tex
    assert len(tex_seen) > 40
