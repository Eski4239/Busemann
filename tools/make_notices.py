"""Write THIRD-PARTY-NOTICES.txt for the Windows build (M12 PART 4) from the same
components.json the About dialog lists, so the two cannot drift apart.

    python tools/make_notices.py OUT.txt [--internal _internal]

Each bundled component: name, installed version (from the build environment's package
metadata, when it is a Python package), licence, source URL, the licence text's path inside
the install folder and the component's note. Plus the LGPL statement for Qt (the Qt and
PySide6 libraries are separate, replaceable files) and the OpenBLAS / GCC runtime notice.
"""
import importlib.metadata as md
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENTS = ROOT / "src" / "busemann" / "resources" / "licenses" / "components.json"
INTERNAL = "_internal"          # PyInstaller one-folder: bundled files live under this folder

HEADER = """\
Busemann {version} - third-party notices
{rule}

Busemann itself is released under the MIT License (see LICENSE in this folder).
Copyright (c) 2026 Pablo Goulet Valenti.

This Windows build bundles the components below. Each one is used under its own licence;
the full licence texts are in {licences}\\ (also shown in Busemann under
Help > About Busemann > Licences).
"""

LGPL = """\
Qt and PySide6 (LGPL-3.0)
-------------------------
Busemann uses Qt for Python (PySide6) and the Qt libraries under the GNU Lesser General
Public License version 3. They are not modified and are not linked statically: the Qt
libraries (Qt6*.dll), the Qt plugins and the PySide6 / Shiboken6 modules are separate files
in {internal}\\PySide6\\ and {internal}\\shiboken6\\ of this install folder. You may replace them
with your own compatible build of the same Qt and PySide6 version. The corresponding source
code is available from the URLs listed for "PySide6 / Qt" below.
"""

BLAS = """\
OpenBLAS and the GCC runtime
----------------------------
The NumPy and SciPy Windows builds include OpenBLAS/LAPACK (BSD-3-Clause) and the GCC
runtime libraries (GPL-3.0-or-later WITH GCC-exception-3.1, which permits distribution
with programs under any licence). See numpy-LICENSE.txt and scipy-LICENSE.txt.
"""


def components(path=COMPONENTS):
    return json.loads(Path(path).read_text(encoding="utf-8"))["components"]


def installed_version(dist):
    if not dist:
        return None
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return None


def render(comps, version, internal=INTERNAL, versions=None):
    """The notices text. `versions` maps dist -> version (default: installed metadata)."""
    licences = f"{internal}\\busemann\\resources\\licenses"
    head = HEADER.format(version=version, rule="=" * (len(f"Busemann {version}") + 22),
                         licences=licences)
    out = [head, LGPL.format(internal=internal), BLAS, "Components", "----------", ""]
    for comp in comps:
        v = (versions or {}).get(comp["dist"]) if versions is not None \
            else installed_version(comp["dist"])
        out.append(f"{comp['name']}" + (f" {v}" if v else ""))
        out.append(f"  Licence: {comp['license']}")
        out.append(f"  Source:  {comp['url']}")
        out.append("  Text:    " + ", ".join(f"{licences}\\{f}" for f in comp["files"]))
        if comp.get("note"):
            out.append(f"  Note:    {comp['note']}")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if not args:
        print(__doc__)
        return 2
    internal = INTERNAL
    if "--internal" in args:
        internal = args[args.index("--internal") + 1]
    sys.path.insert(0, str(ROOT / "src"))
    from busemann import __version__

    text = render(components(), __version__, internal)
    Path(args[0]).write_text(text, encoding="utf-8", newline="\r\n")
    print(f"wrote {args[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
