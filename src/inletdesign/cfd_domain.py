"""CFD fluid-domain outline export for CFD meshing (SpaceClaim/Fluent import).

Two exporters:
- export_cfd_domain_dxf: the design-point domain only -- the captured
  streamtube at the shock-on-lip design condition, extended downstream by a
  straight constant-area duct.
- export_offdesign_domain_dxf: the same internal domain, extended with an
  external spill region above the cowl line, upstream of the lip only, so an
  off-design (spillage) shock has somewhere physical to go. No outer cowl
  surface is modeled: upstream of the lip the flow is supersonic, so an outer
  cowl shape cannot influence what's captured, and a realistic outer cowl
  here would need a large incidence angle (>= the cowl's own flow-turning
  angle) that would itself detach at the design Mach. This external region
  is only valid while the first ramp shock stays attached and crosses
  OUTLET_EXT below the far-field top boundary (i.e. exits through OUTLET_EXT,
  not FARFIELD_TOP) -- callers evaluating very low M_inf should check this
  with offdesign.off_design() first.
"""
import math

import ezdxf

from .export import write_metadata


def _to_mm(point):
    return (point[0] * 1000.0, point[1] * 1000.0)


def export_cfd_domain_dxf(geom, path, duct_length_factor=2.0, metadata=None):
    """Write a closed 2D fluid-domain outline (mm, DXF R2010) with one layer per boundary.

    Layers: INLET, SYMMETRY, RAMP, OUTLET, COWL, TOP_FREESTREAM. The outline is
    one closed loop: INLET -> TOP_FREESTREAM -> COWL -> OUTLET -> RAMP ->
    SYMMETRY -> back to INLET's start.

    Raises:
        ValueError: if the resulting loop does not close (start and end
            points differ by more than 1e-9, in geometry units).
    """
    h_c = geom.capture_height
    tip = geom.ramp_points[0]
    terminal_foot = geom.ramp_points[-1]
    lip = geom.lip
    phi_n = geom.cowl_angle_deg
    dir_n = (math.cos(math.radians(phi_n)), math.sin(math.radians(phi_n)))

    inlet_bottom = (tip[0] - 1.0 * h_c, 0.0)
    inlet_top = (tip[0] - 1.0 * h_c, h_c)
    ramp_duct_end = (
        terminal_foot[0] + duct_length_factor * h_c * dir_n[0],
        terminal_foot[1] + duct_length_factor * h_c * dir_n[1],
    )
    cowl_inner_end = (
        lip[0] + duct_length_factor * h_c * dir_n[0],
        lip[1] + duct_length_factor * h_c * dir_n[1],
    )

    ramp_polyline = list(geom.ramp_points) + [ramp_duct_end]

    full_loop = (
        [inlet_bottom, inlet_top, lip, cowl_inner_end, ramp_duct_end]
        + list(reversed(geom.ramp_points[:-1]))
        + [tip, inlet_bottom]
    )
    closure_gap = math.hypot(
        full_loop[0][0] - full_loop[-1][0], full_loop[0][1] - full_loop[-1][1]
    )
    if closure_gap > 1e-9:
        raise ValueError(f"CFD domain outline does not close (gap={closure_gap})")

    boundaries = [
        ("INLET", [inlet_bottom, inlet_top]),
        ("TOP_FREESTREAM", [lip, inlet_top]),
        ("COWL", [cowl_inner_end, lip]),
        ("OUTLET", [ramp_duct_end, cowl_inner_end]),
        ("RAMP", ramp_polyline),
        ("SYMMETRY", [inlet_bottom, tip]),
    ]

    doc = ezdxf.new(dxfversion="R2010")
    write_metadata(doc, metadata)
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()

    layer_colors = {
        "INLET": 1,
        "SYMMETRY": 2,
        "RAMP": 7,
        "OUTLET": 3,
        "COWL": 5,
        "TOP_FREESTREAM": 6,
    }
    for name, color in layer_colors.items():
        doc.layers.add(name, color=color)

    for layer_name, points in boundaries:
        points_mm = [_to_mm(p) for p in points]
        if len(points_mm) == 2:
            msp.add_line(points_mm[0], points_mm[1], dxfattribs={"layer": layer_name})
        else:
            msp.add_lwpolyline(points_mm, dxfattribs={"layer": layer_name})

    doc.saveas(path)
    return path


def export_offdesign_domain_dxf(
    geom, path, duct_length_factor=2.0, top_height_factor=2.0, ext_outlet="normal",
    metadata=None,
):
    """Write a closed 2D fluid-domain outline including an external spill region.

    See the module docstring for the rationale (no outer cowl surface, and
    when this domain is valid).

    Layers: INLET, FARFIELD_TOP, OUTLET_EXT, COWL, OUTLET, RAMP, SYMMETRY.

    ext_outlet selects the shape of OUTLET_EXT:
    - "normal" (default): a straight line from the lip, up and upstream, at
      angle phi_cowl + 90 deg from +x, until y = H. It is normal to the
      turned flow direction (33.8 deg for the M3 / 2-ramp design), so the
      normal Mach M*cos(phi_flow - phi_cowl) across it is supersonic for all
      attached-shock cases (M 2.5-3.5) and the result does not depend on the
      boundary condition imposed there.
    - "vertical": the previous shape, x = lip.x from the lip to y = H. Kept
      for reference.

    Closed loop: inlet_bottom -> (inlet_x, H) -> (x_ext_top, H) -> lip ->
    cowl_inner_end -> ramp_duct_end -> ramp points reversed -> tip -> inlet_bottom.

    Raises:
        ValueError: if ext_outlet is not "normal"/"vertical", if H <= lip.y,
            if x_ext_top <= inlet_x, or if the loop does not close (1e-9 tolerance).
    """
    if ext_outlet not in ("normal", "vertical"):
        raise ValueError(f"ext_outlet must be 'normal' or 'vertical', got {ext_outlet!r}")

    h_c = geom.capture_height
    tip = geom.ramp_points[0]
    terminal_foot = geom.ramp_points[-1]
    lip = geom.lip
    phi_n = geom.cowl_angle_deg
    dir_n = (math.cos(math.radians(phi_n)), math.sin(math.radians(phi_n)))

    H = top_height_factor * h_c
    inlet_x = tip[0] - 1.0 * h_c
    inlet_bottom = (inlet_x, 0.0)
    inlet_top_H = (inlet_x, H)
    if H <= lip[1]:
        raise ValueError(f"far-field top H={H} must be above the lip (y={lip[1]})")

    if ext_outlet == "vertical":
        farfield_top_end = (lip[0], H)
    else:
        a = math.radians(phi_n + 90.0)
        t = (H - lip[1]) / math.sin(a)
        farfield_top_end = (lip[0] + t * math.cos(a), H)
        if farfield_top_end[0] <= inlet_x:
            raise ValueError(
                f"OUTLET_EXT top x={farfield_top_end[0]} is not downstream of the inlet "
                f"(x={inlet_x}); reduce top_height_factor"
            )

    ramp_duct_end = (
        terminal_foot[0] + duct_length_factor * h_c * dir_n[0],
        terminal_foot[1] + duct_length_factor * h_c * dir_n[1],
    )
    cowl_inner_end = (
        lip[0] + duct_length_factor * h_c * dir_n[0],
        lip[1] + duct_length_factor * h_c * dir_n[1],
    )

    ramp_polyline = list(geom.ramp_points) + [ramp_duct_end]

    full_loop = (
        [inlet_bottom, inlet_top_H, farfield_top_end, lip, cowl_inner_end, ramp_duct_end]
        + list(reversed(geom.ramp_points[:-1]))
        + [tip, inlet_bottom]
    )
    closure_gap = math.hypot(
        full_loop[0][0] - full_loop[-1][0], full_loop[0][1] - full_loop[-1][1]
    )
    if closure_gap > 1e-9:
        raise ValueError(f"off-design CFD domain outline does not close (gap={closure_gap})")

    boundaries = [
        ("INLET", [inlet_bottom, inlet_top_H]),
        ("FARFIELD_TOP", [inlet_top_H, farfield_top_end]),
        (
            "OUTLET_EXT",
            [farfield_top_end, lip] if ext_outlet == "vertical" else [lip, farfield_top_end],
        ),
        ("COWL", [cowl_inner_end, lip]),
        ("OUTLET", [ramp_duct_end, cowl_inner_end]),
        ("RAMP", ramp_polyline),
        ("SYMMETRY", [inlet_bottom, tip]),
    ]

    doc = ezdxf.new(dxfversion="R2010")
    write_metadata(doc, metadata)
    doc.header["$INSUNITS"] = 4
    msp = doc.modelspace()

    layer_colors = {
        "INLET": 1,
        "FARFIELD_TOP": 4,
        "OUTLET_EXT": 3,
        "COWL": 5,
        "OUTLET": 3,
        "RAMP": 7,
        "SYMMETRY": 2,
    }
    for name, color in layer_colors.items():
        doc.layers.add(name, color=color)

    for layer_name, points in boundaries:
        points_mm = [_to_mm(p) for p in points]
        if len(points_mm) == 2:
            msp.add_line(points_mm[0], points_mm[1], dxfattribs={"layer": layer_name})
        else:
            msp.add_lwpolyline(points_mm, dxfattribs={"layer": layer_name})

    doc.saveas(path)
    return path
