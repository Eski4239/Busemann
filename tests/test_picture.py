"""Canvas drawing model (pure Python): regions, shocks, off-design behaviour, interpolation.

Expected values are geometric identities or api self-consistency checks only.
"""
import math

import pytest

from inletdesign import api
from busemann.canvas import picture as P


def _pic(M=3.0, n=2, off_M=None):
    d = api.design(M, n)
    off = api.off_design_point(d, off_M) if off_M is not None else None
    return d, P.build(P.skeleton_from(d, off))


@pytest.mark.parametrize("n", range(5))
def test_region_count_is_n_ramps_plus_two(n):
    _, pic = _pic(n=n)
    assert len(pic.regions) == n + 2
    assert len(pic.shocks) == n + 1            # ramp shocks + terminal normal shock


@pytest.mark.parametrize("M, n, off_M", [(3.0, 0, None), (3.0, 2, None), (3.0, 4, None),
                                         (6.7, 4, None), (3.0, 2, 2.5), (3.0, 2, 3.5)])
def test_regions_tile_the_flow_domain(M, n, off_M):
    _, pic = _pic(M, n, off_M)
    areas = [P.polygon_area(r.polygon) for r in pic.regions]
    assert all(a > 0 for a in areas)
    assert sum(areas) == pytest.approx(P.polygon_area(pic.domain), rel=1e-9)


@pytest.mark.parametrize("n", range(1, 5))
def test_design_shocks_focus_on_lip(n):
    _, pic = _pic(n=n)
    for shock in pic.shocks:
        assert shock.end == pytest.approx(pic.skeleton.lip, abs=1e-9)


def test_region_states_come_from_api():
    d, pic = _pic(n=3)
    for region, state in zip(pic.regions, d.regions):
        assert region.state == state
    assert pic.regions[-1].state.name.startswith("duct")


def test_below_design_mach_shocks_land_ahead_of_lip():
    _, pic = _pic(off_M=2.5)
    lip_x = pic.skeleton.lip[0]
    first = pic.shocks[0]
    assert first.end[1] == pytest.approx(pic.skeleton.h, abs=1e-6)   # crosses the cowl line
    assert first.end[0] < lip_x                                       # spillage
    assert pic.streamtube[0][1] < pic.skeleton.h                      # captured streamtube


def test_above_design_mach_shocks_enter_the_cowl():
    _, pic = _pic(off_M=3.5)
    lip, foot = pic.skeleton.lip, pic.skeleton.foot
    for shock in pic.shocks[:-1]:
        # ends on the terminal line foot-lip, below the lip
        cross = (lip[0] - foot[0]) * (shock.end[1] - foot[1]) - (lip[1] - foot[1]) * (
            shock.end[0] - foot[0])
        assert cross == pytest.approx(0.0, abs=1e-6)
        assert shock.end[1] < lip[1]


def test_subsonic_behind_last_ramp_has_no_terminal_shock():
    d = api.design(3.0, 2)
    M = next(m / 1000 for m in range(2390, 2410) if api.off_design_point(d, m / 1000).M_pre_terminal < 1)
    pic = P.build(P.skeleton_from(d, api.off_design_point(d, M)))
    assert [s.kind for s in pic.shocks] == ["oblique", "oblique"]
    assert len(pic.regions) == 4
    assert pic.regions[-1].state.M == pytest.approx(pic.regions[-2].state.M)


def test_interpolation_endpoints_and_midpoint():
    a = P.skeleton_from(api.design(3.0, 2))
    b = P.skeleton_from(api.design(3.4, 2))
    assert P.interpolate(a, b, 0.0).lip == a.lip
    assert P.interpolate(a, b, 1.0) is b
    mid = P.interpolate(a, b, 0.5)
    assert mid.lip[0] == pytest.approx(0.5 * (a.lip[0] + b.lip[0]))
    assert mid.regions == b.regions                 # numbers shown are the target's
    c = P.skeleton_from(api.design(3.0, 3))
    assert P.interpolate(a, c, 0.5) is c            # different topology: snap


def test_dimensions_cover_spec_items():
    _, pic = _pic(n=2)
    labels = {d.label for d in pic.dimensions}
    assert {"θ<sub>1</sub>", "θ<sub>2</sub>", "L<sub>1</sub>", "L<sub>2</sub>", "h<sub>c</sub>",
            "h<sub>t</sub>", "lip"} <= labels                    # rich-text subscripts (M8.4)
    h_c = next(d for d in pic.dimensions if d.label == "h<sub>c</sub>")
    assert h_c.value == pytest.approx(0.1)
    h_t = next(d for d in pic.dimensions if d.label == "h<sub>t</sub>")
    assert h_t.value == pytest.approx(api.design(3.0, 2).throat_height)


def test_geometry_helpers():
    square = [(0, 0), (2, 0), (2, 2), (0, 2)]
    assert P.polygon_area(square) == pytest.approx(4.0)
    assert P.polygon_centroid(square) == pytest.approx((1.0, 1.0))
    assert P.point_in_polygon((1, 1), square) and not P.point_in_polygon((3, 1), square)
    half = P.clip_half_plane(square, (1, 0), (1, 0), keep_positive=True)
    assert P.polygon_area(half) == pytest.approx(2.0)
    assert P.ray_exit((1, 1), (1, 0), square) == pytest.approx(1.0)
    assert math.isinf(P.ray_exit((5, 5), (1, 0), square))


# --- M3.1: Mach bins, bow shock, flow-side angle arcs, label placement -----------------

@pytest.mark.parametrize("min_M, M_inf", [(0.699, 3.0), (0.628, 6.7), (0.8, 1.5), (0.9, 1.2),
                                          (0.3, 2.0), (0.62, 4.5)])
def test_mach_bins_diverge_at_sonic(min_M, M_inf):
    edges = P.mach_bins(min_M, M_inf)
    assert edges[0] == min(0.5, min_M) and edges[-1] == M_inf
    assert 1.0 in edges
    assert all(b > a for a, b in zip(edges, edges[1:]))
    assert 4 <= len(edges) - 1 <= P.MAX_BINS
    assert P.bin_index(min_M, edges) < edges.index(1.0) <= P.bin_index(M_inf - 1e-9, edges) + 1


def test_bow_shock_only_when_cowl_detached():
    _, attached = _pic(3.0, 2)
    assert not attached.skeleton.cowl_detached and attached.bow_shock == []
    _, detached = _pic(6.7, 4)
    assert detached.skeleton.cowl_detached and len(detached.bow_shock) > 2
    lip = detached.skeleton.lip
    assert min(p[0] for p in detached.bow_shock) < lip[0]      # stands ahead of the lip
    x0, y0, x1, y1 = detached.bounds()
    assert all(x0 <= p[0] <= x1 and y0 <= p[1] <= y1 for p in detached.bow_shock)


@pytest.mark.parametrize("n", [1, 2, 4])
def test_angle_arcs_lie_on_the_flow_side(n):
    _, pic = _pic(3.0, n)
    for d in (d for d in pic.dimensions if d.kind == "angle"):
        q = d.points[0]
        mid = math.radians(0.5 * (d.angles[0] + d.angles[1]))
        probe = (q[0] + math.cos(mid) * 0.5 * d.radius, q[1] + math.sin(mid) * 0.5 * d.radius)
        assert any(P.point_in_polygon(probe, r.polygon) for r in pic.regions)
        assert d.angles[1] - d.angles[0] == pytest.approx(d.value)


def test_place_labels_avoids_obstacles_and_each_other():
    wall = [(0, 0), (100, 0), (100, -5), (0, -5)]
    shock = ((0, 0), (100, 50))
    labels = [((50, 1), 40, 14, "center"), ((50, 1), 40, 14, "center")]   # same spot twice
    placed = P.place_labels(labels, polygons=[wall], segments=[shock], scale=1.0)
    (c1, r1), (c2, r2) = placed
    for r in (r1, r2):
        assert not P.rect_hits_polygon(r, wall)
        assert not P.rect_hits_segment(r, *shock)
    assert not P._rect_overlaps_rect(r1, r2)


def test_rect_collision_helpers():
    rect = (0, 0, 10, 10)
    assert P.rect_hits_segment(rect, (-5, 5), (15, 5))
    assert not P.rect_hits_segment(rect, (-5, 20), (15, 20))
    assert P.rect_hits_polygon(rect, [(5, 5), (20, 5), (20, 20)])
    assert P.rect_hits_polygon(rect, [(-10, -10), (20, -10), (20, 20), (-10, 20)])  # inside
    assert not P.rect_hits_polygon(rect, [(20, 20), (30, 20), (30, 30)])


# --- M4 STEP 0b: cowl lip wedge drawn at its real angle (2 deg minimum) -------------------

@pytest.mark.parametrize("wedge, drawn, thickened", [(0.0, 2.0, True), (1.0, 2.0, True),
                                                     (2.0, 2.0, False), (6.0, 6.0, False),
                                                     (12.5, 12.5, False)])
def test_cowl_drawn_with_actual_wedge(wedge, drawn, thickened):
    d = api.design(3.0, 2, cowl_wedge=wedge)
    pic = P.build(P.skeleton_from(d))
    assert pic.skeleton.cowl_wedge_deg == wedge
    assert pic.skeleton.wedge_thickened is thickened
    lip, end = pic.cowl_outer
    angle = math.degrees(math.atan2(end[1] - lip[1], end[0] - lip[0])) - d.cowl_angle_deg
    assert angle == pytest.approx(drawn, abs=1e-9)
