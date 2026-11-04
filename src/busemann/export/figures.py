"""Figure export with matplotlib (no Qt): the inlet canvas and the off-design charts.

The canvas figure is drawn from the same canvas.picture.Picture the Qt canvas draws, with the
same Mach bins and colours (canvas.colors); the charts from the same charts.model series,
bands and CFD rule. Light theme; PNG at 300 dpi, SVG (glyphs as paths) and PDF (TrueType
fonts embedded); the export metadata goes into the file's metadata.
"""
import json
from pathlib import Path

import matplotlib
from matplotlib import font_manager
from matplotlib.figure import Figure
from matplotlib.patches import Polygon, Rectangle

from ..canvas import colors as _colors
from ..canvas import picture as P
from ..charts import model
from ..paths import resource_path
from ..theme import tokens

C = tokens.COLORS
PNG_DPI = 300
PAD_IN = 0.06            # fixed margin around the tight bounding box, inches
# line weights: the canvas uses cosmetic pens in screen px; 1 px = 0.75 pt
PX_TO_PT = 0.75
LW = {"wall": 2.0 * PX_TO_PT, "cowl": 1.5 * PX_TO_PT, "shock": 2.0 * PX_TO_PT,
      "region": 1.0 * PX_TO_PT, "streamtube": 1.0 * PX_TO_PT, "arrow": 1.5 * PX_TO_PT}
DASH = (0, (4, 2))       # Qt DashLine (4 on, 2 off, in pen widths)
DOT = (0, (1, 2))        # Qt DotLine
HATCH = "////"           # 45-degree hatching, spacing matched by eye to Qt BDiagPattern
FORMATS = ("png", "svg", "pdf")
RC = {
    "font.family": ["Inter", "DejaVu Sans"],
    "font.size": 9,
    "svg.fonttype": "path",          # SVG: glyphs embedded as outlines
    "pdf.fonttype": 42,              # PDF: TrueType fonts embedded
    "axes.edgecolor": C["border"],
    "axes.labelcolor": C["text"],
    "xtick.color": C["text_muted"],
    "ytick.color": C["text_muted"],
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "hatch.linewidth": 0.75,
    "hatch.color": C["wall"],
}
_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    for name in ("Inter-Regular.ttf", "Inter-Medium.ttf", "Inter-SemiBold.ttf",
                 "JetBrainsMono-Regular.ttf"):
        try:
            font_manager.fontManager.addfont(str(resource_path("fonts", name)))
        except (FileNotFoundError, RuntimeError):
            pass
    _fonts_registered = True


# --- canvas -------------------------------------------------------------------------------

def canvas_figure(picture, title=None, width_in=7.0):
    """Figure of a canvas Picture (model units: mm, y up). Shock lines have gid "shock-<i>"."""
    _register_fonts()
    with matplotlib.rc_context(RC):
        x0, y0, x1, y1 = picture.bounds()
        h = picture.skeleton.h
        pad = 0.08 * max(x1 - x0, y1 - y0)
        aspect = (y1 - y0 + 2 * pad) / (x1 - x0 + 2 * pad)
        fig = Figure(figsize=(width_in, max(2.5, width_in * aspect + 0.6)))
        ax = fig.add_axes((0.02, 0.06, 0.82, 0.86))
        ax.set_aspect("equal")
        ax.set_axis_off()
        ax.set_xlim(x0 - pad, x1 + pad)
        ax.set_ylim(y0 - pad, y1 + pad)

        machs = [r.state.M for r in picture.regions]
        edges = P.mach_bins(min(machs), picture.skeleton.regions[0].M)
        fills = _colors.bin_colors(edges)
        for region in picture.regions:
            fill = fills[P.bin_index(region.state.M, edges)]
            ax.add_patch(Polygon(region.polygon, closed=True, facecolor=fill,
                                 edgecolor=_colors.darker(fill), linewidth=LW["region"],
                                 zorder=1, gid=f"region-{region.index}"))
        # walls exactly as on the canvas: the ramp is a hatch-only band under a solid wall
        # line (no outline), the cowl a hatched wedge with an outline
        ax.add_patch(Polygon(picture.ramp_body, closed=True, facecolor="none",
                             edgecolor=C["wall"], hatch=HATCH, linewidth=0.0, zorder=3,
                             gid="ramp"))
        ax.add_patch(Polygon(picture.cowl_body, closed=True, facecolor="none",
                             edgecolor=C["wall"], hatch=HATCH, linewidth=LW["cowl"], zorder=3,
                             gid="cowl"))
        xs, ys = zip(*picture.ramp_surface)
        ax.plot(xs, ys, color=C["wall"], linewidth=LW["wall"], zorder=4, gid="ramp-surface",
                solid_capstyle="round", solid_joinstyle="round")
        for shock in picture.shocks:
            ax.plot([shock.start[0], shock.end[0]], [shock.start[1], shock.end[1]],
                    color=C["shock"], linewidth=LW["shock"], zorder=5,
                    gid=f"shock-{shock.index}", solid_capstyle="round",
                    linestyle=DASH if shock.kind == "normal" else "-")
        if picture.bow_shock:
            xs, ys = zip(*picture.bow_shock)
            ax.plot(xs, ys, color=C["shock"], linewidth=LW["shock"], linestyle=DASH, zorder=5,
                    gid="bow-shock")
        if len(picture.streamtube) > 1:
            xs, ys = zip(*picture.streamtube)
            ax.plot(xs, ys, color=C["text_muted"], linewidth=LW["streamtube"], linestyle=DOT,
                    zorder=4, gid="streamtube")
        if picture.arrow:
            (tx, ty), (hx, hy) = picture.arrow
            ax.annotate("", xy=(hx, hy), xytext=(tx, ty), zorder=6,
                        arrowprops=dict(arrowstyle="-|>,head_length=0.9,head_width=0.35",
                                        color=C["text"], lw=LW["arrow"], mutation_scale=12))
            ax.text(0.5 * (tx + hx), ty + 0.1 * h, f"M∞ = {picture.skeleton.mach:.2f}",
                    ha="center", va="bottom", color=C["text"], fontsize=9, zorder=6,
                    fontfamily=["JetBrains Mono", "DejaVu Sans Mono"],
                    bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="none", alpha=0.85))
        fig.legend_labels = _mach_legend(fig, edges, fills)
        if title:
            fig.text(0.02, 0.97, title, ha="left", va="top", fontsize=10, color=C["text"],
                     fontweight="semibold")
        fig.text(0.02, 0.015, "Busemann · inviscid 2D model · regions coloured by Mach number",
                 fontsize=7, color=C["text_muted"])
        return fig


class_label = P.class_label


def _mach_legend(fig, edges, fills):
    """Discrete classes: one equal-height block per Mach bin, labelled with its range (not a
    continuous scale), highest Mach on top; a dark line marks the sonic boundary."""
    lax = fig.add_axes((0.86, 0.2, 0.03, 0.6))
    labels = []
    for i, fill in enumerate(fills):
        lax.add_patch(Rectangle((0, i), 1, 1, facecolor=fill, edgecolor=_colors.darker(fill),
                                linewidth=LW["region"]))
        labels.append(class_label(edges[i], edges[i + 1]))
    lax.set_xlim(0, 1)
    lax.set_ylim(0, len(fills))
    lax.set_xticks([])
    lax.set_yticks([i + 0.5 for i in range(len(fills))])
    lax.set_yticklabels(labels, fontsize=7)
    lax.tick_params(axis="y", length=0, pad=4)
    lax.yaxis.tick_right()
    if 1.0 in edges:
        lax.axhline(edges.index(1.0), color=C["text"], linewidth=LW["wall"])
    lax.set_title("Mach", fontsize=8, color=C["text_muted"], pad=4)
    for side in lax.spines.values():
        side.set_visible(False)
    return labels


# --- off-design charts ---------------------------------------------------------------------

CHART_LABELS = {"capture": ("Mass capture A0/Ac [-]", "capture"),
                "recovery": ("Total-pressure recovery p0/p0∞ [-]", "recovery"),
                "margin": ("Cowl margin at the lip [°]", "margin")}


def chart_figure(kind, design, sweep, cursor_mach=None, m_range=None, width_in=6.0,
                 diffuser=None, demand=None):
    """One off-design chart ("capture" | "recovery" | "margin") from charts.model data.
    diffuser: engine-face curve and the MIL-E-5008B line (recovery); demand: the engine's
    (A0/Ac)_demand per sweep Mach (capture), as on screen."""
    if kind not in CHART_LABELS:
        raise ValueError(f"unknown chart {kind!r}")
    _register_fonts()
    s = model.series(sweep)
    lo, hi = m_range or (min(sweep.machs), max(sweep.machs))
    M_d = design.inputs.M
    with matplotlib.rc_context(RC):
        fig = Figure(figsize=(width_in * 1.35, 0.62 * width_in))
        ax = fig.add_axes((0.09, 0.14, 0.62, 0.74))
        labelled = set()
        for band in model.regime_bands(design, sweep, lo, hi):
            token, alpha = model.BAND_STYLE[band.kind]      # same tint as on screen
            ax.axvspan(band.lo, band.hi, color=C[token], alpha=alpha / 255, linewidth=0,
                       zorder=0, label=None if band.label in labelled else band.label)
            labelled.add(band.label)
        if kind == "capture":
            ax.plot(s["M"], s["capture"], color=C["accent"], lw=1.8, label="model", gid="capture")
            if demand is not None:
                ax.plot(*model.demand_series(sweep.machs, demand), color=C["warn"], lw=1.4,
                        linestyle="--", label="fixed demand (engine matching not modelled)",
                        gid="demand")
        elif kind == "recovery":
            below = [k for k, M in enumerate(s["M"]) if M <= M_d + 1e-12]
            above = [k for k, M in enumerate(s["M"]) if M >= M_d - 1e-12]
            for key, colour, name in (("rec_tot", C["accent"], "total"),
                                      ("rec_obl", C["text_muted"], "oblique only")):
                ax.plot([s["M"][k] for k in below], [s[key][k] for k in below], color=colour,
                        lw=1.8, label=name, gid=f"{key}-below")
                ax.plot([s["M"][k] for k in above], [s[key][k] for k in above], color=colour,
                        lw=1.8, linestyle=":", gid=f"{key}-above")
            if diffuser is not None:
                ax.plot(s["M"], model.engine_face(s["rec_tot"], diffuser), color=C["accent"],
                        lw=1.1, linestyle="--", label=f"engine face (× {diffuser:.3f}, estimate)",
                        gid="rec_face")
                ax.plot(*model.mil_series(lo, hi), color=C["wall"], lw=1.1, linestyle="-.",
                        label="MIL-E-5008B (vs engine-face estimate)", gid="mil")
        else:
            ax.plot(s["margin_M"], s["margin"], color=C["accent"], lw=1.8,
                    label=f"at the lip, wedge {design.inputs.cowl_wedge_deg or 0:g}°",
                    gid="margin")
            ax.axhline(0.0, color=C["error"], lw=1.0, linestyle="--")
        if model.cfd_applies(design) and kind in ("capture", "recovery"):
            pts = model.load_cfd()["points"]
            field = "capture" if kind == "capture" else "recovery"
            ax.plot([p["M"] for p in pts], [p[field] for p in pts], linestyle="none",
                    marker="o", markersize=6, markerfacecolor="none",
                    markeredgecolor=C["text"], label="CFD (Fluent, inviscid)", gid="cfd")
        ax.axvline(M_d, color=C["text_muted"], lw=1.0, linestyle="--")
        if cursor_mach is not None:
            ax.axvline(cursor_mach, color=C["accent"], lw=1.0)
        ax.set_xlim(lo, hi)
        ax.set_xlabel("Freestream Mach number M∞ [-]")
        ax.set_ylabel(CHART_LABELS[kind][0])
        ax.grid(alpha=0.25)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), fontsize=7, frameon=False)
        note = model.cfd_note(design) if kind != "margin" else None
        fig.text(0.09, 0.93, f"Design M {M_d:.2f}, {design.inputs.n_ramps} ramps"
                 + (" · above design: upper bound (cowl shock not modelled)"
                    if kind == "recovery" else "") + (f" · {note}" if note else ""),
                 fontsize=7, color=C["text_muted"])
        return fig


# --- saving ------------------------------------------------------------------------------------

def save_figure(fig, path, metadata=None):
    """Save as PNG (300 dpi), SVG or PDF by extension, with the export metadata embedded."""
    path = Path(path)
    fmt = path.suffix.lower().lstrip(".")
    if fmt not in FORMATS:
        raise ValueError(f"figure format must be one of {FORMATS} (got {path.suffix!r})")
    meta = metadata or {}
    summary = json.dumps(meta, ensure_ascii=False)
    creator = f"Busemann {meta.get('app_version', '')}".strip()
    if fmt == "png":
        info = {"Software": creator, "Description": summary}
    elif fmt == "pdf":
        info = {"Creator": creator, "Subject": summary, "Title": path.stem}
    else:
        info = {"Creator": creator, "Description": summary, "Title": path.stem}
    with matplotlib.rc_context(RC):
        fig.savefig(path, format=fmt, dpi=PNG_DPI if fmt == "png" else None, metadata=info,
                    facecolor="white", bbox_inches="tight", pad_inches=PAD_IN)
    return path
