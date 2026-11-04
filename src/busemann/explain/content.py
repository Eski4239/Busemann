"""Explain-mode content: parse the .md entries and fill their live values (no Qt).

Entry format (resources/explain/<name>.md):

    # Title, may use {{k}}
    ## Relations
    <!-- SOURCE: reference, eq. N, p. P (pending user confirmation) -->
    $$ LaTeX (matplotlib mathtext) $$
    ## This case
    $$ ... {{sel.M1:.3f}} ... $$
    ## In plain words
    Plain text, may use {{...}}.
    ## Assumptions
    - one bullet per line

Live values: {{path}} or {{path:format}}. A path is a root name followed by [index]
and/or .attribute steps, e.g. sel.beta_deg, shock[k].Mn1, region[k-1].p_ratio,
design.inputs.cowl_wedge_deg. An index is an integer or k / n with an optional +1 / -1.
Unknown roots, attributes and indices, and None values, raise TemplateError: a missing
value is a bug, never a blank.

Line directives (may be stacked, e.g. "@if off.regime == "spillage": @each oblique: ..."):
    @each <list root>: rest   repeats rest for every item, binding it (item) and n (1-based)
    @if <path> [op literal]: rest   keeps rest when the condition holds
                                    (op: == != < > <= >=; literal: number, "text", None)
Every equation under "Relations" must be preceded by a SOURCE comment.
"""
import ast
import re
from dataclasses import dataclass, field
from importlib import resources

ENTRY_NAMES = ("freestream", "oblique_shock", "region", "normal_shock", "duct", "cowl_design",
               "cowl_offdesign", "method", "offdesign", "separation")
SECTIONS = ("Relations", "This case", "In plain words", "Assumptions")

_TOKEN = re.compile(r"\{\{\s*([^{}:]+?)\s*(?::([^{}]*))?\}\}")
_STEP = re.compile(r"\[([^\]]+)\]|\.([A-Za-z_][A-Za-z0-9_]*)")
_ROOT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_INDEX = re.compile(r"^(-?\d+)$|^([kn])\s*([+-]\s*\d+)?$")
_IF = re.compile(r"^@if\s+(.+?)(?:\s*(==|!=|<=|>=|<|>)\s*(.+?))?\s*:\s*(.*)$")
_EACH = re.compile(r"^@each\s+([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$")
_SOURCE = re.compile(r"^<!--\s*SOURCE:\s*(.+?)\s*-->$")


class TemplateError(ValueError):
    """A live value could not be resolved (unknown key, bad index or None value)."""


class OneBased(list):
    """List indexed from 1 (shock[1] is the first ramp shock)."""

    def at(self, i):
        if not 1 <= i <= len(self):
            raise IndexError(i)
        return self[i - 1]


# --- parsed entry ----------------------------------------------------------------------

@dataclass
class Line:
    kind: str            # "equation" | "text" | "bullet"
    text: str            # template text
    source: str = None   # SOURCE comment of an equation


@dataclass
class Entry:
    name: str
    title: str
    sections: dict       # section name -> [Line]

    def sources(self):
        return [(ln.text, ln.source) for ln in self.sections.get("Relations", [])
                if ln.kind == "equation"]


def entry_text(name):
    return resources.files("busemann").joinpath("resources", "explain", f"{name}.md").read_text(
        encoding="utf-8")


def parse(text, name="entry"):
    title, sections, current, pending_source = None, {}, None, None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        m = _SOURCE.match(line)
        if m:
            pending_source = m.group(1)
            continue
        if line.startswith("<!--"):
            continue                                  # other comments are ignored
        if line.startswith("## "):
            current = line[3:].strip()
            if current not in SECTIONS:
                raise TemplateError(f"{name}: unknown section {current!r}")
            sections[current] = []
            continue
        if line.startswith("# "):
            title = line[2:].strip()
            continue
        if current is None:
            raise TemplateError(f"{name}: text outside a section: {line!r}")
        body = _strip_directives(line)
        if body.startswith("$$") and body.endswith("$$") and len(body) > 4:
            if current == "Relations" and pending_source is None:
                raise TemplateError(f"{name}: equation without a SOURCE comment: {line!r}")
            sections[current].append(Line("equation", line, pending_source))
            pending_source = None
        elif body.startswith("- "):
            sections[current].append(Line("bullet", line))
        else:
            sections[current].append(Line("text", line))
    if title is None:
        raise TemplateError(f"{name}: missing '# title'")
    return Entry(name, title, sections)


def _strip_directives(line):
    while True:
        m = _IF.match(line) or _EACH.match(line)
        if not m:
            return line
        line = m.groups()[-1]


def load(name):
    return parse(entry_text(name), name)


# --- rendering ---------------------------------------------------------------------------

@dataclass
class Substitution:
    path: str
    spec: str
    value: object
    text: str


@dataclass
class RenderedLine:
    kind: str
    text: str
    source: str = None


@dataclass
class Rendered:
    name: str
    title: str
    sections: dict                          # section -> [RenderedLine]
    substitutions: list = field(default_factory=list)


def render(entry, context):
    """Fill an Entry with live values from `context` (dict of roots)."""
    subs = []
    title = _fill(entry.title, context, subs, entry.name)
    out = {}
    for section, lines in entry.sections.items():
        rendered = []
        for ln in lines:
            for text in _expand(ln.text, context, entry.name):
                body = _fill(text[0], dict(context, **text[1]), subs, entry.name)
                if ln.kind == "equation":
                    body = body.strip()[2:-2].strip()
                elif ln.kind == "bullet":
                    body = body[2:].strip()
                rendered.append(RenderedLine(ln.kind, body, ln.source))
        out[section] = rendered
    return Rendered(entry.name, title, out, subs)


def _expand(line, context, name):
    """Apply @if / @each: yields (text, extra bindings)."""
    m = _IF.match(line)
    if m:
        path, op, literal, rest = m.groups()
        value = resolve(path, context, name, allow_none=True)
        if op is not None:
            try:
                rhs = ast.literal_eval(literal)
            except (ValueError, SyntaxError) as exc:
                raise TemplateError(f"{name}: bad literal {literal!r} in @if") from exc
            ok = {"==": value == rhs, "!=": value != rhs}.get(op)
            if ok is None:
                if value is None or rhs is None:
                    raise TemplateError(f"{name}: cannot compare None in @if {path}")
                ok = {"<": value < rhs, ">": value > rhs, "<=": value <= rhs,
                      ">=": value >= rhs}[op]
        else:
            ok = bool(value)
        if ok:
            yield from _expand(rest, context, name)
        return
    m = _EACH.match(line)
    if m:
        root, rest = m.groups()
        items = resolve(root, context, name)
        for n, item in enumerate(items, start=1):
            for text, extra in _expand(rest, dict(context, it=item, n=n), name):
                yield text, dict({"it": item, "n": n}, **extra)
        return
    yield line, {}


def _fill(text, context, subs, name):
    def one(m):
        path, spec = m.group(1).strip(), (m.group(2) or "").strip()
        value = resolve(path, context, name)
        try:
            shown = format(value, spec)
        except (ValueError, TypeError) as exc:
            raise TemplateError(f"{name}: cannot format {path} with {spec!r}") from exc
        subs.append(Substitution(path, spec, value, shown))
        return shown
    return _TOKEN.sub(one, text)


def resolve(path, context, name="entry", allow_none=False):
    """Value of a template path in `context`; TemplateError if anything is missing (or None,
    unless allow_none, as @if conditions do)."""
    m = _ROOT.match(path)
    if not m or m.group(0) not in context:
        raise TemplateError(f"{name}: unknown key {path!r}")
    value = context[m.group(0)]
    rest = path[m.end():]
    pos = 0
    while pos < len(rest):
        step = _STEP.match(rest, pos)
        if not step:
            raise TemplateError(f"{name}: bad key syntax {path!r}")
        index, attr = step.groups()
        try:
            if attr is not None:
                if attr.startswith("_") or not hasattr(value, attr):
                    raise AttributeError(attr)
                value = getattr(value, attr)
            else:
                i = _index(index.strip(), context)
                value = value.at(i) if isinstance(value, OneBased) else value[i]
        except (AttributeError, IndexError, TypeError, KeyError) as exc:
            raise TemplateError(f"{name}: unknown key {path!r}") from exc
        pos = step.end()
    if value is None and not allow_none:
        raise TemplateError(f"{name}: {path!r} is None here")
    return value


def _index(text, context):
    m = _INDEX.match(text)
    if not m:
        raise TemplateError(f"bad index {text!r}")
    if m.group(1) is not None:
        return int(m.group(1))
    base = context.get(m.group(2))
    if not isinstance(base, int):
        raise TemplateError(f"index {text!r}: {m.group(2)} is not bound")
    return base + int((m.group(3) or "0").replace(" ", ""))
