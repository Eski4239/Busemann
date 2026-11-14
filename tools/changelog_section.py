"""Release notes for a tag (M12 PART 5, used by .github/workflows/release.yml).

    python tools/changelog_section.py v1.0.0 build/release_notes.md

Checks that the tag is "v" + busemann.__version__ (the single version source), then writes
that version's CHANGELOG.md section (its body, without the "## 1.0.0 ..." heading) to the
output file, with hard-wrapped lines joined (`unwrap`) because GitHub keeps single line
breaks in release descriptions; CHANGELOG.md itself stays wrapped. Exits non-zero with a clear message when the tag does not match the version, or
the CHANGELOG has no (or an empty) section for it, so no release is published without notes.

A section starts at a level-2 heading naming the version ("## 1.0.0 — first release",
"## [1.0.0] - 2026-11-20") and ends at the next level-2 heading.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseError(Exception):
    pass


def app_version(root=ROOT):
    text = (Path(root) / "src" / "busemann" / "__init__.py").read_text(encoding="utf-8")
    return re.search(r'__version__\s*=\s*"([^"]+)"', text).group(1)


def check_tag(tag, version):
    if tag != f"v{version}":
        raise ReleaseError(f"tag {tag!r} does not match busemann.__version__ {version!r} "
                           f"(expected 'v{version}')")


def section(changelog_text, version):
    """Body of the CHANGELOG section for `version` (heading excluded), stripped."""
    heading = re.compile(rf"^##\s+\[?{re.escape(version)}\]?(?=[\s\]]|$)")
    lines = changelog_text.splitlines()
    start = next((i for i, ln in enumerate(lines) if heading.match(ln)), None)
    if start is None:
        raise ReleaseError(f"CHANGELOG.md has no '## {version}' section")
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
               len(lines))
    body = "\n".join(lines[start + 1:end]).strip()
    if not body:
        raise ReleaseError(f"CHANGELOG.md section '## {version}' is empty")
    return body


def _is_start(line):
    """A line that always begins a new output line: a heading or a bullet."""
    stripped = line.lstrip()
    return stripped.startswith("#") or stripped.startswith("- ")


def unwrap(body):
    """Join hard-wrapped lines for the release page, where GitHub keeps single line breaks.

    A continuation line (indented, or plain text directly after a non-blank, non-heading
    line) is appended to the previous line with one space. Blank lines, headings and "- "
    bullet starts stay line starts; fenced code blocks are copied unchanged."""
    out, fenced = [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            out.append(line)
            continue
        prev = out[-1] if out else ""
        if (not fenced and line.strip() and prev.strip() and not _is_start(line)
                and not prev.lstrip().startswith("#") and not prev.lstrip().startswith("```")):
            out[-1] = f"{prev.rstrip()} {line.strip()}"
        else:
            out.append(line)
    return "\n".join(out)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 2:
        print(__doc__)
        return 2
    tag, out = args
    try:
        version = app_version()
        check_tag(tag, version)
        body = unwrap(section((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), version))
    except (ReleaseError, OSError) as exc:
        print(f"release notes: {exc}", file=sys.stderr)
        return 1
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(body + "\n", encoding="utf-8")
    print(f"release notes for {tag}: {len(body.splitlines())} lines -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
