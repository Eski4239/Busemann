"""Busemann project files are DXF drawings (M8.2; no Qt).

Save writes the design geometry (layers RAMP, COWL, SHOCKS, millimetres, as the geometry
export) and stores every input as a DXF custom header property:

    BUSEMANN_FORMAT = "busemann-dxf"      BUSEMANN_SCHEMA = 1
    BUSEMANN_APP_VERSION = "1.0.0"        BUSEMANN_SAVED_UTC = "2026-11-04T10:00:00Z"
    BUSEMANN_<FIELD> = JSON of each Inputs field (BUSEMANN_MACH = 3.0, ...)
    BUSEMANN_VIEW = JSON {"layers": {...}, "tab": "design"}

JSON keeps floats exact (repr), so a Busemann DXF reopens to the identical design. Any other
DXF is imported from its ramp and cowl lines (`import_geometry`) as a custom-angle design;
its flight conditions are unknown. ProjectError carries a message fit for an error dialog.
"""
import dataclasses
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .inputs import Inputs, freestream_for, sized_capture_height

FORMAT = "busemann-dxf"
SCHEMA = 1
SUFFIX = ".dxf"
PREFIX = "BUSEMANN_"
FILTER = "DXF drawing (*.dxf)"
LAYERS = ("shocks", "regions", "dimensions", "grid")
TABS = ("design", "offdesign")
DEFAULT_VIEW = {"layers": {"shocks": True, "regions": True, "dimensions": False, "grid": False},
                "tab": "design"}
IMPORT_BANNER = "Imported geometry — flight conditions unknown, set them in the left panel"
MAX_RAMPS = 4
MAX_PLAUSIBLE_H_M = 5.0     # a larger capture height in a "metres" drawing is read as mm
_INSUNITS_TO_M = {0: 1e-3, 1: 0.0254, 2: 0.3048, 4: 1e-3, 5: 1e-2, 6: 1.0}  # 0: unitless -> mm

# schema n -> function(data at schema n) -> data at schema n + 1 (none yet).
MIGRATIONS = {}


class ProjectError(ValueError):
    """The file cannot be opened as a design; the message says why."""


class Loaded(tuple):
    """(inputs, view, warnings), plus `.imported` (True: geometry-only DXF import)."""

    def __new__(cls, inputs, view, warnings, imported=False):
        obj = super().__new__(cls, (inputs, view, warnings))
        obj.imported = imported
        return obj


# --- design of a set of inputs (as the app computes it) ----------------------------------

def design_for(inputs):
    """api.design for the inputs (sized capture height, custom angles, cowl limits), or None
    when the inputs give no valid design."""
    from inletdesign import api

    try:
        fs = freestream_for(inputs, inputs.mach)
        h = sized_capture_height(inputs, fs)
        return api.design(inputs.mach, inputs.n_ramps, capture_height=h, gamma=inputs.gamma,
                          ramp_angles=list(inputs.custom_angles)
                          if inputs.method == "custom" else None,
                          max_cowl_angle=inputs.max_cowl_deg if inputs.max_cowl_enabled
                          else None, cowl_wedge=inputs.cowl_wedge_deg)
    except ValueError:
        return None


# --- save -------------------------------------------------------------------------------

def header_values(inputs, view=None, app_version=__version__):
    """{BUSEMANN_*: text} for the DXF header."""
    values = {f"{PREFIX}FORMAT": FORMAT, f"{PREFIX}SCHEMA": str(SCHEMA),
              f"{PREFIX}APP_VERSION": app_version,
              f"{PREFIX}SAVED_UTC": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    for f in dataclasses.fields(Inputs):
        value = getattr(inputs, f.name)
        if isinstance(value, tuple):
            value = list(value)
        values[f"{PREFIX}{f.name.upper()}"] = json.dumps(value, ensure_ascii=False)
    values[f"{PREFIX}VIEW"] = json.dumps(_clean_view(view or DEFAULT_VIEW))
    return values


def save(path, inputs, view=None, design=None, metadata=None):
    """Write the design DXF with every input in the header. Without a valid design (the
    inputs give an error) the DXF holds the header only. Returns the path."""
    import ezdxf

    from inletdesign import api
    from inletdesign.export import write_metadata, write_geometry

    path = Path(path)
    design = design if design is not None else design_for(inputs)
    doc = ezdxf.new(dxfversion="R2010")
    write_metadata(doc, header_values(inputs, view))
    if metadata:
        write_metadata(doc, metadata)
    doc.header["$INSUNITS"] = 4                      # mm
    if design is not None:
        write_geometry(doc, api.inlet_geometry(design))
    doc.saveas(path)
    return path


# --- load -------------------------------------------------------------------------------

def _read_doc(path):
    import ezdxf

    path = Path(path)
    if not path.exists():
        raise ProjectError(f"Cannot read {path.name}: file not found")
    try:
        return ezdxf.readfile(path)
    except IOError as exc:
        raise ProjectError(f"Cannot read {path.name}: {exc}") from exc
    except ezdxf.DXFStructureError as exc:
        raise ProjectError(f"{path.name} is not a valid DXF drawing ({exc})") from exc


def custom_header(doc):
    """{name: text} of the DXF custom header properties."""
    return {str(k): str(v) for k, v in doc.header.custom_vars}


def load(path, base=None):
    """Loaded(inputs, view, warnings, imported) from a DXF. A Busemann DXF restores every
    input; any other DXF is imported from its geometry, keeping `base`'s flight conditions
    (default Inputs()). ProjectError if neither works."""
    path = Path(path)
    doc = _read_doc(path)
    header = custom_header(doc)
    if f"{PREFIX}SCHEMA" not in header and f"{PREFIX}FORMAT" not in header:
        inputs, warnings = import_geometry(doc, base or Inputs(), path.name)
        return Loaded(inputs, dict(DEFAULT_VIEW, layers=dict(DEFAULT_VIEW["layers"])),
                      warnings, imported=True)
    return Loaded(*from_header(header, path.name))


def from_header(header, name="project"):
    """(inputs, view, warnings) from the BUSEMANN_* header properties."""
    if header.get(f"{PREFIX}FORMAT") != FORMAT:
        raise ProjectError(f"{name}: BUSEMANN_FORMAT is {header.get(f'{PREFIX}FORMAT')!r}, "
                           f"expected {FORMAT!r}")
    try:
        schema = int(header.get(f"{PREFIX}SCHEMA", ""))
    except ValueError:
        raise ProjectError(f"{name}: missing or invalid BUSEMANN_SCHEMA "
                           f"({header.get(f'{PREFIX}SCHEMA')!r})") from None
    if schema < 1:
        raise ProjectError(f"{name}: invalid BUSEMANN_SCHEMA {schema}")
    if schema > SCHEMA:
        raise ProjectError(f"{name} was saved by a newer Busemann (schema {schema}; this "
                           f"version reads up to schema {SCHEMA})")
    data = {"schema": schema, "header": dict(header)}
    data = migrate(data)
    header = data["header"]
    fields = {f.name.upper(): f for f in dataclasses.fields(Inputs)}   # T_k -> T_K
    meta = {"FORMAT", "SCHEMA", "APP_VERSION", "SAVED_UTC", "VIEW"}
    warnings, values = [], {}
    for key, text in header.items():
        if not key.startswith(PREFIX):
            continue                                     # other drawing properties
        short = key[len(PREFIX):]
        if short in meta:
            continue
        field = fields.get(short)
        if field is None:
            warnings.append(f"unknown property {key!r} ignored")
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            raise ProjectError(f"{name}: {key} is not valid ({text!r})") from None
        values[field.name] = _coerce(field.name, value, field, name)
    try:
        view_raw = json.loads(header.get(f"{PREFIX}VIEW", "null"))
    except json.JSONDecodeError:
        view_raw = "invalid"
    view, view_warnings = _read_view(view_raw)
    return Inputs(**values), view, warnings + view_warnings


def migrate(data):
    """Apply MIGRATIONS until the data is at SCHEMA."""
    while data["schema"] < SCHEMA:
        step = MIGRATIONS.get(data["schema"])
        if step is None:
            raise ProjectError(f"no migration from schema {data['schema']}")
        data = step(dict(data))
    return data


_OPTIONAL_FLOATS = {"off_design_mach", "mdot_kgps", "inlet_width_m"}


def _coerce(key, value, field, name):
    default = field.default
    if value is None and (default is None):
        return None
    kind = type(default) if default is not None else float if key in _OPTIONAL_FLOATS else str
    try:
        if kind is bool:
            if not isinstance(value, bool):
                raise TypeError
            return value
        if kind is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError
            return value
        if kind is float:
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value):
                raise TypeError
            return float(value)
        if kind is tuple:
            if not isinstance(value, list) or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
                raise TypeError
            return tuple(float(v) for v in value)
        if not isinstance(value, str):
            raise TypeError
        return value
    except TypeError:
        raise ProjectError(f"{name}: input {key!r} has an invalid value {value!r} "
                           f"(expected {kind.__name__})") from None


def _clean_view(view):
    layers = dict(DEFAULT_VIEW["layers"])
    layers.update({k: bool(v) for k, v in (view.get("layers") or {}).items() if k in LAYERS})
    tab = view.get("tab") if view.get("tab") in TABS else "design"
    return {"layers": layers, "tab": tab}


def _read_view(view):
    if view is None:
        return dict(DEFAULT_VIEW, layers=dict(DEFAULT_VIEW["layers"])), []
    warnings = []
    if not isinstance(view, dict):
        return _read_view(None)[0], ["BUSEMANN_VIEW is not valid; default view used"]
    for k in view:
        if k not in ("layers", "tab"):
            warnings.append(f"unknown view setting {k!r} ignored")
    for k in (view.get("layers") or {}):
        if k not in LAYERS:
            warnings.append(f"unknown layer {k!r} ignored")
    if "tab" in view and view["tab"] not in TABS:
        warnings.append(f"unknown tab {view['tab']!r}; Design tab used")
    return _clean_view(view), warnings


# --- import of a geometry-only DXF ---------------------------------------------------------

def _points(entity):
    kind = entity.dxftype()
    if kind == "LINE":
        return [tuple(entity.dxf.start)[:2], tuple(entity.dxf.end)[:2]]
    if kind == "LWPOLYLINE":
        return [tuple(p[:2]) for p in entity.get_points("xy")]
    if kind == "POLYLINE":
        return [tuple(v.dxf.location)[:2] for v in entity.vertices]
    return []


def _chain(segments, tol):
    """Join polylines / lines into one open chain of points (in x order)."""
    segs = [s for s in segments if len(s) >= 2]
    if not segs:
        return []
    chain = list(min(segs, key=lambda s: min(p[0] for p in s)))
    if chain[0][0] > chain[-1][0]:
        chain.reverse()
    rest = [s for s in segs if s is not None]
    rest.remove(min(segs, key=lambda s: min(p[0] for p in s)))
    grown = True
    while rest and grown:
        grown = False
        for s in list(rest):
            for cand in (s, s[::-1]):
                if math.dist(cand[0], chain[-1]) <= tol:
                    chain += cand[1:]
                    rest.remove(s)
                    grown = True
                    break
            if grown:
                break
    out = [chain[0]]
    for p in chain[1:]:                                  # drop repeats and straight joints
        if math.dist(p, out[-1]) > tol:
            out.append(p)
    return out


def _straighten(pts, tol_deg=1e-6):
    """Remove collinear interior points (a line drawn in pieces is one ramp)."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a = math.atan2(pts[i][1] - out[-1][1], pts[i][0] - out[-1][0])
        b = math.atan2(pts[i + 1][1] - pts[i][1], pts[i + 1][0] - pts[i][0])
        if abs(math.degrees(b - a)) > tol_deg:
            out.append(pts[i])
    out.append(pts[-1])
    return out


def import_geometry(doc, base, name="drawing"):
    """(Inputs, warnings) of a custom-angle design read from ramp and cowl lines.

    Ramp: entities on a layer whose name contains "RAMP" (any case), otherwise the longest
    open polyline. Cowl: entities on a layer containing "COWL", otherwise a single line
    lying above the ramp. The ramp starts at its lowest-x point (the leading edge, where the
    freestream is taken along +x); each corner's turn is a ramp angle; the lip (the cowl's
    upstream end) gives the capture height above the leading edge."""
    msp = doc.modelspace()
    scale = _INSUNITS_TO_M.get(int(doc.header.get("$INSUNITS", 0)), 1e-3)
    entities = [e for e in msp if e.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE")]
    by_layer = {}
    for e in entities:
        by_layer.setdefault(e.dxf.layer.upper(), []).append(e)
    ramp_e = [e for layer, es in by_layer.items() if "RAMP" in layer for e in es]
    cowl_e = [e for layer, es in by_layer.items() if "COWL" in layer for e in es]
    if not ramp_e:
        polys = [e for e in entities if e.dxftype() in ("LWPOLYLINE", "POLYLINE")
                 and len(_points(e)) >= 3]
        if polys:
            ramp_e = [max(polys, key=lambda e: sum(
                math.dist(a, b) for a, b in zip(_points(e), _points(e)[1:])))]
    if not ramp_e:
        raise ProjectError(f"{name}: no ramp line found (expected a polyline or lines from "
                           "the leading edge, or a layer named RAMP)")
    span = max(max(abs(c) for p in _points(e) for c in p) for e in ramp_e) or 1.0
    tol = 1e-6 * span
    ramp = _straighten(_chain([_points(e) for e in ramp_e], tol))
    if len(ramp) < 2:
        raise ProjectError(f"{name}: the ramp line has fewer than two distinct points")
    if any(b[0] <= a[0] for a, b in zip(ramp, ramp[1:])):
        raise ProjectError(f"{name}: ramp corners are not in increasing x")
    if not cowl_e:
        lines = [e for e in entities if e.dxftype() == "LINE" and e not in ramp_e]
        above = [e for e in lines if min(p[1] for p in _points(e)) > max(p[1] for p in ramp[:1])]
        if len(above) == 1:
            cowl_e = above
    if not cowl_e:
        raise ProjectError(f"{name}: no cowl line found (expected a line above the ramp, or a "
                           "layer named COWL)")
    cowl_pts = [p for e in cowl_e for p in _points(e)]
    lip = min(cowl_pts, key=lambda p: p[0])
    le = ramp[0]
    dirs = [math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) for a, b in zip(ramp, ramp[1:])]
    angles = [dirs[0]] + [b - a for a, b in zip(dirs, dirs[1:])]
    n = len(angles)
    if n > MAX_RAMPS:
        raise ProjectError(f"{name}: the ramp line has {n} corners; Busemann handles up to "
                           f"{MAX_RAMPS} ramps")
    if any(a <= 0 for a in angles):
        raise ProjectError(f"{name}: every ramp must turn the flow towards the cowl (got "
                           f"{', '.join(f'{a:.2f}°' for a in angles)})")
    h = (lip[1] - le[1]) * scale
    if not h > 0:
        raise ProjectError(f"{name}: the cowl lip is not above the leading edge")
    warnings = [IMPORT_BANNER]
    if scale == 1.0 and h > MAX_PLAUSIBLE_H_M:          # unit header says m, size says mm
        h *= 1e-3
        warnings.append(f"{name}: the drawing units say metres but the capture height would "
                        f"be {h * 1e3:.0f} m; read as millimetres ({h:.4g} m)")
    inputs = dataclasses.replace(
        base, method="custom", n_ramps=n, custom_angles=tuple(angles), capture_height_m=h,
        capture_mode="height", preset=None, off_design_mach=None)
    return inputs, warnings
