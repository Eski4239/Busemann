"""Figure export (no Qt): drawn from the same picture / chart data as the screen."""
import math

import pytest

from busemann.canvas import colors as Col
from busemann.canvas import picture as P
from busemann.charts import model
from busemann.export import figures as F
from inletdesign import api


def _lines(fig, prefix):
    return {ln.get_gid(): ln for ax in fig.axes for ln in ax.get_lines()
            if (ln.get_gid() or "").startswith(prefix)}


@pytest.mark.parametrize("M, n, off_M, wedge", [(3.0, 2, None, 0.0), (3.0, 2, 2.5, 0.0),
                                                (3.0, 2, 3.25, 0.0), (6.7, 4, None, 0.0),
                                                (3.0, 3, 2.9, 6.0)])
def test_canvas_figure_shock_endpoints_equal_picture_data(M, n, off_M, wedge):
    d = api.design(M, n, cowl_wedge=wedge)
    off = api.off_design_point(d, off_M) if off_M else None
    pic = P.build(P.skeleton_from(d, off))
    fig = F.canvas_figure(pic)
    shocks = _lines(fig, "shock-")
    assert len(shocks) == len(pic.shocks)
    for shock in pic.shocks:
        line = shocks[f"shock-{shock.index}"]
        xs, ys = line.get_data()
        assert (xs[0], ys[0]) == pytest.approx(shock.start, abs=1e-12)
        assert (xs[-1], ys[-1]) == pytest.approx(shock.end, abs=1e-12)
        assert (line.get_linestyle() == "--") is (shock.kind == "normal")
    # regions use the canvas colours (same bins, same palette)
    edges = P.mach_bins(min(r.state.M for r in pic.regions), pic.skeleton.regions[0].M)
    fills = Col.bin_colors(edges)
    patches = {p.get_gid(): p for p in fig.axes[0].patches}
    for region in pic.regions:
        rgba = patches[f"region-{region.index}"].get_facecolor()
        hex_fill = "#" + "".join(f"{round(c * 255):02x}" for c in rgba[:3])
        assert hex_fill == fills[P.bin_index(region.state.M, edges)]
    if pic.bow_shock:
        assert "bow-shock" in {ln.get_gid() for ln in fig.axes[0].get_lines()}


def test_chart_figures_plot_the_model_series():
    d = api.design(3.0, 2)
    sweep = api.off_design_sweep(d, api.detachment_mach(d), 4.5, 40)
    s = model.series(sweep)
    cap = _lines(F.chart_figure("capture", d, sweep, 2.5, (1.2, 4.5)), "capture")["capture"]
    assert list(cap.get_xdata()) == s["M"] and list(cap.get_ydata()) == s["capture"]
    rec = _lines(F.chart_figure("recovery", d, sweep), "rec_")
    below = [M for M in s["M"] if M <= 3.0 + 1e-12]
    assert list(rec["rec_tot-below"].get_xdata()) == below
    mar = _lines(F.chart_figure("margin", d, sweep), "margin")["margin"]
    assert [y for y in mar.get_ydata() if not math.isnan(y)] == \
        [y for y in s["margin"] if not math.isnan(y)]
    cfd = _lines(F.chart_figure("capture", d, sweep), "cfd")["cfd"]
    assert list(cfd.get_xdata()) == [p["M"] for p in model.load_cfd()["points"]]
    x15 = api.design(6.7, 4)
    sw15 = api.off_design_sweep(x15, api.detachment_mach(x15), 8.2, 20)
    assert "cfd" not in _lines(F.chart_figure("capture", x15, sw15), "cfd")
    with pytest.raises(ValueError):
        F.chart_figure("nope", d, sweep)


def test_saved_formats_embed_fonts_and_metadata(tmp_path):
    d = api.design(3.0, 2)
    fig = F.canvas_figure(P.build(P.skeleton_from(d)))
    meta = {"app_version": "9.9.9", "git_commit": "abc1234", "inputs": {"mach": 3.0}}
    png = F.save_figure(fig, tmp_path / "f.png", meta)
    svg = F.save_figure(fig, tmp_path / "f.svg", meta)
    pdf = F.save_figure(fig, tmp_path / "f.pdf", meta)
    from PIL import Image
    img = Image.open(png)
    assert img.info["dpi"][0] == pytest.approx(F.PNG_DPI, abs=1)
    assert "abc1234" in img.info["Description"] and img.info["Software"] == "Busemann 9.9.9"
    svg_text = svg.read_text(encoding="utf-8")
    assert "abc1234" in svg_text and "<text" not in svg_text        # glyphs as paths
    pdf_bytes = pdf.read_bytes()
    assert b"FontFile2" in pdf_bytes                                  # TrueType embedded
    assert b"Inter" in pdf_bytes
    with pytest.raises(ValueError, match="format"):
        F.save_figure(fig, tmp_path / "f.jpg", meta)


# --- M7: the export is drawn like the canvas ---------------------------------------------

def test_walls_and_line_weights_match_the_canvas():
    d = api.design(3.0, 2)
    fig = F.canvas_figure(P.build(P.skeleton_from(d)))
    patches = {p.get_gid(): p for p in fig.axes[0].patches}
    assert patches["ramp"].get_linewidth() == 0.0 and patches["ramp"].get_hatch()   # band only
    assert patches["cowl"].get_linewidth() == pytest.approx(1.5 * F.PX_TO_PT)       # outlined
    lines = {ln.get_gid(): ln for ln in fig.axes[0].get_lines()}
    assert lines["ramp-surface"].get_linewidth() == pytest.approx(2.0 * 0.75)
    assert lines["shock-0"].get_linewidth() == pytest.approx(2.0 * 0.75)
    region = patches["region-1"]
    assert region.get_linewidth() == pytest.approx(0.75)


def test_legend_is_discrete_classes_with_ranges():
    d = api.design(3.0, 2)
    pic = P.build(P.skeleton_from(d))
    fig = F.canvas_figure(pic)
    edges = P.mach_bins(min(r.state.M for r in pic.regions), pic.skeleton.regions[0].M)
    assert fig.legend_labels == [f"{a:.3g}–{b:.3g}" for a, b in zip(edges, edges[1:])]
    legend_ax = fig.axes[1]
    heights = {round(p.get_height(), 9) for p in legend_ax.patches}
    assert heights == {1.0}                                   # equal-height blocks
    assert [t.get_text() for t in legend_ax.get_yticklabels()] == fig.legend_labels


def test_png_has_a_tight_fixed_margin(tmp_path):
    from PIL import Image, ImageChops

    d = api.design(3.0, 2)
    path = F.save_figure(F.canvas_figure(P.build(P.skeleton_from(d)), "title"),
                         tmp_path / "t.png", {})
    img = Image.open(path).convert("RGB")
    box = ImageChops.difference(img, Image.new("RGB", img.size, "white")).getbbox()
    margin_px = F.PAD_IN * F.PNG_DPI
    left, top, right, bottom = box
    # tight: the fixed margin plus at most the text boxes' own padding (font descent)
    for gap in (left, top, img.width - right, img.height - bottom):
        assert gap <= margin_px + 12


def test_streamtube_is_dotted_like_the_canvas():
    d = api.design(3.0, 2)
    pic = P.build(P.skeleton_from(d, api.off_design_point(d, 2.5)))
    lines = {ln.get_gid(): ln for ln in F.canvas_figure(pic).axes[0].get_lines()}
    assert lines["streamtube"].get_linewidth() == pytest.approx(0.75)
    offset, dashes = lines["streamtube"]._unscaled_dash_pattern     # custom dash: Qt DotLine
    assert (offset, tuple(dashes)) == (F.DOT[0], F.DOT[1])


def test_chart_export_has_the_engine_face_mil_and_demand_curves():
    d = api.design(3.0, 2)
    sweep = api.off_design_sweep(d, api.detachment_mach(d), 4.5, 40)
    rec = _lines(F.chart_figure("recovery", d, sweep, diffuser=0.97), "")
    s = model.series(sweep)
    assert list(rec["rec_face"].get_ydata()) == [v * 0.97 for v in s["rec_tot"]]
    xs, ys = model.mil_series(min(sweep.machs), max(sweep.machs))
    assert list(rec["mil"].get_ydata()) == ys
    demand = tuple(1.0 for _ in sweep.machs)
    cap = _lines(F.chart_figure("capture", d, sweep, demand=demand), "demand")
    assert list(cap["demand"].get_xdata()) == list(sweep.machs)
    assert "rec_face" not in _lines(F.chart_figure("recovery", d, sweep), "rec_face")
