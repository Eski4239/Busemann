"""Offline 3D render of a generic two-ramp inlet for the welcome window (M8.2).

    python tools/render_inlet_3d.py [out.png]

The validation geometry (M 3, 2 ramps, Oswatitsch) extruded to a finite width: shaded ramp
surfaces, a thin cowl plate, the far side wall translucent and the near one cut away, the ramp
and terminal shocks as translucent sheets, and streamlines entering the capture area that turn
at each ramp shock (using the model's flow angles) and run into the duct. matplotlib only (a
development dependency; the app just shows the PNG). Default output:
src/busemann/resources/images/inlet_3d.png
"""
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Line3DCollection, Poly3DCollection  # noqa: E402

from busemann.theme import tokens  # noqa: E402
from inletdesign import api  # noqa: E402

OUT = ROOT / "src" / "busemann" / "resources" / "images" / "inlet_3d.png"
C = tokens.COLORS


def _intersect(p, ang_deg, a, b):
    """Point where the ray from p at ang_deg meets the line through a, b (None if parallel)."""
    d = (math.cos(math.radians(ang_deg)), math.sin(math.radians(ang_deg)))
    e = (b[0] - a[0], b[1] - a[1])
    den = d[0] * e[1] - d[1] * e[0]
    if abs(den) < 1e-12:
        return None
    t = ((a[0] - p[0]) * e[1] - (a[1] - p[1]) * e[0]) / den
    return (p[0] + t * d[0], p[1] + t * d[1]) if t > 0 else None


def streamline(design, y0, x_start, duct_len):
    """2D streamline at height y0: turns to each region's flow angle at each shock."""
    flow = design.flow_angles_deg
    shocks = design.geometry.shocks
    pts, p, ang = [(x_start, y0)], (x_start, y0), 0.0
    for k, (a, b) in enumerate(shocks[:-1]):          # ramp shocks
        q = _intersect(p, ang, a, b)
        if q is None:
            break
        pts.append(q)
        p, ang = q, flow[k + 1]
    a, b = shocks[-1]                                  # terminal normal shock
    q = _intersect(p, ang, a, b)
    if q is not None:
        pts.append(q)
        p = q
    pts.append((p[0] + duct_len * math.cos(math.radians(ang)),
                p[1] + duct_len * math.sin(math.radians(ang))))
    return pts


def render(out=OUT, width_px=1100, height_px=800):
    d = api.design(3.0, 2)
    g = d.geometry
    h = d.inputs.capture_height
    W = 1.3 * h                                         # extrusion width
    ramp = [tuple(p) for p in g.ramp_points]
    lip = tuple(g.lip)
    phi = math.radians(d.cowl_angle_deg)
    duct = 0.9 * h
    cowl_end = (lip[0] + duct * math.cos(phi), lip[1] + duct * math.sin(phi))
    foot = ramp[-1]
    ramp_end = (foot[0] + duct * math.cos(phi), foot[1] + duct * math.sin(phi))
    ramp_full = ramp + [ramp_end]

    fig = Figure(figsize=(width_px / 150, height_px / 150), dpi=150)
    fig.patch.set_facecolor(C["surface"])
    ax = fig.add_axes((0, 0, 1, 1), projection="3d")
    ax.set_facecolor(C["surface"])
    ax.computed_zorder = False              # explicit order: side wall, ramp, sheets, flow, cowl

    def quad(a, b, z0=0.0, z1=W):
        return [(a[0], z0, a[1]), (b[0], z0, b[1]), (b[0], z1, b[1]), (a[0], z1, a[1])]

    # ramp surfaces, shaded by their angle (steeper = darker)
    faces, shades = [], []
    for k, (a, b) in enumerate(zip(ramp_full, ramp_full[1:])):
        faces.append(quad(a, b))
        shades.append(0.55 + 0.12 * k)
    ramp_poly = Poly3DCollection(faces, linewidths=0.6, edgecolors=C["wall"])
    ramp_poly.set_facecolor([(0.72 - 0.08 * k, 0.75 - 0.08 * k, 0.80 - 0.08 * k, 1.0)
                             for k in range(len(faces))])
    ramp_poly.set_zorder(1)
    ax.add_collection3d(ramp_poly)
    # cowl: a thin plate from the lip into the duct
    t = 0.035 * h
    n = (-math.sin(phi), math.cos(phi))
    top_lip = (lip[0] + t * n[0], lip[1] + t * n[1])
    top_end = (cowl_end[0] + t * n[0], cowl_end[1] + t * n[1])
    cowl = Poly3DCollection([quad(lip, cowl_end), quad(top_lip, top_end),
                             quad(lip, top_lip)], linewidths=0.6, edgecolors=C["wall"])
    cowl.set_facecolor((0.62, 0.65, 0.70, 1.0))
    cowl.set_zorder(5)
    ax.add_collection3d(cowl)
    # far side wall (z = 0), translucent: the region between ramp and cowl lines
    outline = [(-0.05 * h, 0.0)] + ramp_full + [cowl_end, lip, (-0.05 * h, lip[1])]
    side = Poly3DCollection([[(x, 0.0, y) for x, y in outline]], linewidths=0.4,
                            edgecolors=(0.42, 0.45, 0.5, 0.6))
    side.set_facecolor((0.85, 0.88, 0.93, 0.25))
    side.set_zorder(0)
    ax.add_collection3d(side)
    # shock sheets (translucent amber)
    sheets = Poly3DCollection([quad(a, b) for a, b in g.shocks], linewidths=0.8,
                              edgecolors=C["shock"])
    sheets.set_facecolor((0.85, 0.47, 0.02, 0.16))
    sheets.set_zorder(2)
    ax.add_collection3d(sheets)
    # streamlines entering the capture area
    segs = []
    for z in (0.25 * W, 0.5 * W, 0.75 * W):
        for y0 in (0.12 * h, 0.35 * h, 0.6 * h, 0.85 * h):
            pts = streamline(d, y0, -0.9 * h, 0.8 * duct)
            segs += [[(a[0], z, a[1]), (b[0], z, b[1])] for a, b in zip(pts, pts[1:])]
    flow = Line3DCollection(segs, colors=C["accent"], linewidths=1.1, alpha=0.95)
    flow.set_zorder(3)
    ax.add_collection3d(flow)

    xs = [p[0] for p in outline] + [-0.9 * h, ramp_end[0]]
    ys = [p[1] for p in outline]
    ax.set_xlim(min(xs), max(xs))
    ax.set_ylim(-0.1 * W, 1.1 * W)
    ax.set_zlim(min(ys) - 0.05 * h, max(ys) + 0.1 * h)
    ax.set_box_aspect((max(xs) - min(xs), 1.2 * W, max(ys) - min(ys) + 0.15 * h), zoom=1.15)
    ax.view_init(elev=26, azim=-62)
    ax.set_axis_off()
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=C["surface"])
    _trim(out)
    return out


def _trim(path, pad=12):
    """Crop the PNG to its drawn content plus a small margin."""
    from PIL import Image, ImageChops

    img = Image.open(path).convert("RGB")
    box = ImageChops.difference(img, Image.new("RGB", img.size, C["surface"])).getbbox()
    if box:
        l, t, r, b = box
        img = img.crop((max(0, l - pad), max(0, t - pad), min(img.width, r + pad),
                        min(img.height, b + pad)))
    img.save(path, optimize=True)


if __name__ == "__main__":
    print("wrote", render(sys.argv[1] if len(sys.argv) > 1 else OUT))
