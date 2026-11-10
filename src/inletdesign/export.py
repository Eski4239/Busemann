"""DXF export of an InletGeometry via ezdxf.

This module (and plotting.py) are the only places in the package that import
ezdxf; physics and geometry modules stay free of output-format dependencies.
"""
import math

import ezdxf


def _to_mm(point):
    return (point[0] * 1000.0, point[1] * 1000.0)


def write_metadata(doc, metadata):
    """Store export metadata as DXF custom header properties (CAD: drawing properties).

    metadata: dict of name -> value; values are written as text (nested values as JSON).
    Adds no entities or layers, so meshing tools see the same drawing."""
    if not metadata:
        return
    import json

    for key, value in metadata.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        doc.header.custom_vars.append(str(key), text)


def export_dxf(geom, path, units="mm", include_shocks=True, metadata=None):
    """Export an InletGeometry as a DXF (R2010, millimetres). Returns path.

    metadata: optional dict written as custom header properties (see write_metadata)."""
    doc = ezdxf.new(dxfversion="R2010")
    write_metadata(doc, metadata)
    doc.header["$INSUNITS"] = 4  # mm
    write_geometry(doc, geom, include_shocks)
    doc.saveas(path)
    return path


def write_geometry(doc, geom, include_shocks=True):
    """Layers RAMP (polyline from the leading edge), COWL (line from the lip) and SHOCKS,
    in millimetres, added to an ezdxf document."""
    doc.layers.add("RAMP", color=7)
    doc.layers.add("COWL", color=5)
    if include_shocks:
        doc.layers.add("SHOCKS", color=1)

    msp = doc.modelspace()

    ramp_pts_mm = [_to_mm(p) for p in geom.ramp_points]
    msp.add_lwpolyline(ramp_pts_mm, dxfattribs={"layer": "RAMP"})

    cowl_len = 0.4 * geom.capture_height
    cowl_end = (
        geom.lip[0] + cowl_len * math.cos(math.radians(geom.cowl_angle_deg)),
        geom.lip[1] + cowl_len * math.sin(math.radians(geom.cowl_angle_deg)),
    )
    msp.add_line(_to_mm(geom.lip), _to_mm(cowl_end), dxfattribs={"layer": "COWL"})

    if include_shocks:
        for p0, p1 in geom.shocks:
            msp.add_line(_to_mm(p0), _to_mm(p1), dxfattribs={"layer": "SHOCKS"})


ISENTROPIC_FORMAT = "busemann-isentropic-dxf"
ISENTROPIC_SCHEMA = 1


def export_isentropic_dxf(ramp, path, metadata=None):
    """Export an isentropic_ramp.IsentropicRamp wall contour as a DXF (R2010, millimetres).

    The header carries BUSEMANN_FORMAT = "busemann-isentropic-dxf" (distinct from the main
    design's "busemann-dxf") plus every input needed to rebuild the fan (M_inf, gamma, h_c,
    delta_deg), so the main window's Open routes this file to the isentropic ramp window
    instead of importing it as a multi-ramp design. Returns path."""
    doc = ezdxf.new(dxfversion="R2010")
    header = dict(metadata or {})
    header.update({
        "BUSEMANN_FORMAT": ISENTROPIC_FORMAT,
        "BUSEMANN_SCHEMA": ISENTROPIC_SCHEMA,
        "BUSEMANN_M_INF": ramp.M_inf,
        "BUSEMANN_GAMMA": ramp.gamma,
        "BUSEMANN_CAPTURE_HEIGHT": ramp.capture_height,
        "BUSEMANN_DELTA_DEG": ramp.delta_deg,
    })
    write_metadata(doc, header)
    doc.header["$INSUNITS"] = 4  # mm
    doc.layers.add("WALL", color=7)
    msp = doc.modelspace()
    msp.add_lwpolyline([_to_mm(p) for p in ramp.wall_points], dxfattribs={"layer": "WALL"})
    doc.saveas(path)
    return path
