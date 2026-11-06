"""verification_notes.md (addendum E), written beside every geometry / CFD export: inputs,
model assumptions, the full Verification list with sources, the validation summary and the
CFD statement. No Qt.
"""
from pathlib import Path

from .. import verification as V
from ..charts.model import load_validation

NOTES_NAME = "verification_notes.md"
CFD_PARAGRAPH = ("All approximate results in this file (separation checks, the MIL-E-5008B "
                 "comparison, the diffuser estimate, off-design values above the design Mach) "
                 "and the inviscid model itself must be verified with a CFD solver before the "
                 "geometry is used.")


def _value(v):
    if isinstance(v, float):
        return f"{v:.6g}"
    if isinstance(v, (tuple, list)):
        return ", ".join(_value(x) for x in v) or "—"
    return "—" if v is None else str(v)


def render(meta, items, validation=None):
    """Markdown text of the notes for an export's metadata dict and verification items."""
    validation = validation if validation is not None else load_validation()
    out = ["# Busemann verification notes", ""]
    what = meta.get("export", "export")
    out += [f"Written with: {what}  ",
            f"Busemann {meta.get('app_version')} (commit {meta.get('git_commit') or '—'}), "
            f"{meta.get('exported_utc')}", ""]
    out += ["## Inputs", "", "| Input | Value |", "|---|---|"]
    out += [f"| {k} | {_value(v)} |" for k, v in meta.get("inputs", {}).items()]
    out += ["", "## Model assumptions", ""]
    out += [f"- {a}" for a in V.ASSUMPTIONS]
    counts = {s: sum(1 for i in items if i.severity == s) for s in V.SEVERITIES}
    out += ["", "## Verification items", "",
            f"{len(items)} items: {counts['error']} errors, {counts['warn']} warnings, "
            f"{counts['info']} notes. Each one {V.CFD_STATEMENT}.", ""]
    for k, item in enumerate(items, start=1):
        out += [f"### {k}. {item.title}", "",
                f"- Severity: {V.SEVERITY_TITLES[item.severity]}",
                f"- Criterion: {item.criterion}",
                f"- Source: {item.source}",
                f"- {item.text}"]
        if item.quote:
            out.append(f"- Validation evidence: {item.quote}")
        out.append("")
    out += ["## Validation summary", "", V.VALIDATION_SUMMARY, "",
            f"Repository: {validation.get('repository', '—')}"]
    out += ["", "## CFD statement", "", CFD_PARAGRAPH, ""]
    return "\n".join(out)


def write_verification_notes(export_path, meta, items, validation=None):
    """Write verification_notes.md in the export's folder; returns its path."""
    path = Path(export_path).with_name(NOTES_NAME)
    path.write_text(render(meta, items, validation), encoding="utf-8")
    return path
