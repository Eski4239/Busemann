"""Geometry exports for CFD tools (M8.2): IGES lines, a point CSV and a Gmsh .geo.

The walls are the ones the DXF export draws: the ramp polyline (leading edge to the
terminal-shock foot) and the cowl line from the lip (0.4 h_c long at the cowl angle). No new
dependencies: each format is written as text.

- IGES 5.3, fixed 80-column records, one entity type 110 (line) per wall segment, z = 0,
  millimetres (unit flag 2) like the DXF.
- CSV: x, y in metres, one block per wall ("# wall: ramp" then "x_m,y_m" rows).
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


# --- point CSV ----------------------------------------------------------------------------

def export_points_csv(geom, path, metadata=None):
    path = Path(path)
    out = [f"# {line}" for line in _comment_lines(metadata)]
    out.append("# units: m")
    for name, pts in walls(geom).items():
        out += ["", f"# wall: {name}", "x_m,y_m"]
        out += [f"{x!r},{y!r}" for x, y in pts]
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return path


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


# --- IGES ---------------------------------------------------------------------------------

def _hollerith(text):
    return f"{len(text)}H{text}"


def _section(lines, letter):
    """Fixed-format records: data in columns 1-72, section letter at 73, sequence 74-80."""
    return [f"{line:<72}{letter}{k:7d}" for k, line in enumerate(lines, start=1)]


def _wrap_tokens(tokens, width):
    """Join parameter tokens with "," (";" after the last), wrapped at `width` columns
    between tokens (a Hollerith string such as 1H, is never split)."""
    out, line = [], ""
    for k, token in enumerate(tokens):
        piece = token + (";" if k == len(tokens) - 1 else ",")
        if line and len(line) + len(piece) > width:
            out.append(line)
            line = ""
        line += piece
    if line:
        out.append(line)
    return out


def export_iges(geom, path, metadata=None):
    """IGES 5.3 with one line entity (type 110) per wall segment, in millimetres."""
    path = Path(path)
    mm = 1000.0
    start = _section([line[:72] for line in _comment_lines(metadata)], "S")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d.%H%M%S")
    segs = segments(geom)
    max_coord = max(abs(c) * mm for _, a, b in segs for c in (*a, *b)) or 1.0
    g = ["1H,", "1H;", _hollerith("Busemann"), _hollerith(path.name), _hollerith("Busemann"),
         _hollerith("inletdesign"), "32", "38", "6", "308", "15", _hollerith("Busemann"),
         "1.0", "2", "2HMM", "1", "1.0", _hollerith(stamp), "1.0E-6", f"{max_coord:.6g}",
         _hollerith("Busemann"), _hollerith("Busemann"), "11", "0", _hollerith(stamp)]
    global_ = _section(_wrap_tokens(g, 72), "G")
    directory, params = [], []
    for k, (_, a, b) in enumerate(segs):
        p_line = len(params) + 1
        record = ["110", f"{a[0] * mm:.9g}", f"{a[1] * mm:.9g}", "0.",
                  f"{b[0] * mm:.9g}", f"{b[1] * mm:.9g}", "0."]
        de = 2 * k + 1
        chunks = _wrap_tokens(record, 64)
        params += [f"{c:<64}{de:8d}" for c in chunks]
        directory.append(f"{110:8d}{p_line:8d}{0:8d}{0:8d}{0:8d}{0:8d}{0:8d}{0:8d}"
                         f"{'00000000':>8}")
        directory.append(f"{110:8d}{0:8d}{0:8d}{len(chunks):8d}{0:8d}{'':8}{'':8}"
                         f"{'LINE':>8}{0:8d}")
    d_sec = _section(directory, "D")
    p_sec = _section(params, "P")
    terminate = [f"S{len(start):7d}G{len(global_):7d}D{len(d_sec):7d}P{len(p_sec):7d}"
                 f"{'':<40}T{1:7d}"]
    path.write_text("\n".join(start + global_ + d_sec + p_sec + terminate) + "\n",
                    encoding="ascii")
    return path
