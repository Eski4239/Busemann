"""Geometry export for CFD tools (M8.2; M8.4 keeps only Gmsh .geo): wall outlines.

The walls are the ones the DXF export draws: the ramp polyline (leading edge to the
terminal-shock foot) and the cowl line from the lip (0.4 h_c long at the cowl angle). No new
dependencies: each format is written as text.

- Gmsh .geo: Point / Line in metres with Physical Curve "RAMP" and "COWL".
"""
import math
from datetime import datetime, timezone
from pathlib import Path

WALLS = ("ramp", "cowl")


def walls(geom):
    """{"ramp": [(x, y), ...], "cowl": [lip, end]} in metres."""
    cowl_len = 0.4 * geom.capture_height
    a = math.radians(geom.cowl_angle_deg)
    lip = (float(geom.lip[0]), float(geom.lip[1]))
    end = (lip[0] + cowl_len * math.cos(a), lip[1] + cowl_len * math.sin(a))
    return {"ramp": [(float(x), float(y)) for x, y in geom.ramp_points], "cowl": [lip, end]}


def segments(geom):
    """[(wall, (x0, y0), (x1, y1)), ...] in metres."""
    out = []
    for name, pts in walls(geom).items():
        out += [(name, a, b) for a, b in zip(pts, pts[1:])]
    return out


def _comment_lines(metadata):
    lines = [f"Busemann geometry export {datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}"]
    for key in ("app_version", "git_commit", "export"):
        if metadata and metadata.get(key):
            lines.append(f"{key}: {metadata[key]}")
    return lines


# --- Gmsh .geo ----------------------------------------------------------------------------

def export_gmsh_geo(geom, path, metadata=None, lc=None):
    """Gmsh geometry script; lc = characteristic mesh length (default h_c / 50)."""
    path = Path(path)
    lc = lc or geom.capture_height / 50.0
    out = [f"// {line}" for line in _comment_lines(metadata)]
    out += ["// units: m", f"lc = {lc!r};"]
    point_id = line_id = 0
    groups = {}
    for name, pts in walls(geom).items():
        ids = []
        for x, y in pts:
            point_id += 1
            out.append(f"Point({point_id}) = {{{x!r}, {y!r}, 0, lc}};")
            ids.append(point_id)
        lines = []
        for a, b in zip(ids, ids[1:]):
            line_id += 1
            out.append(f"Line({line_id}) = {{{a}, {b}}};")
            lines.append(line_id)
        groups[name] = lines
    for name, lines in groups.items():
        out.append(f'Physical Curve("{name.upper()}") = {{{", ".join(map(str, lines))}}};')
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path
