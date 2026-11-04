"""CFD-tool geometry exports (M8.2): IGES (entity 110), point CSV, Gmsh .geo. Each file is
parsed back with a minimal reader and must reproduce the walls (no Qt)."""
import math
import re

import pytest

from inletdesign import api
from inletdesign import export_cad as X


@pytest.fixture(scope="module", params=[(3.0, 2, None), (6.7, 4, None), (3.0, 3, [7.0, 8.0, 9.0])])
def geom(request):
    M, n, angles = request.param
    return api.inlet_geometry(api.design(M, n, ramp_angles=angles))


def _read_iges(text):
    """Minimal IGES reader: section records by column 73, 110 entities from D + P."""
    lines = text.rstrip("\n").split("\n")
    assert all(len(l) == 80 for l in lines), {len(l) for l in lines}
    sections = {}
    for l in lines:
        sections.setdefault(l[72], []).append(l)
    assert list(sections) == ["S", "G", "D", "P", "T"]
    for letter, recs in sections.items():
        assert [int(r[73:]) for r in recs] == list(range(1, len(recs) + 1))
    t = sections["T"][0]
    counts = {t[i]: int(t[i + 1:i + 8]) for i in range(0, 32, 8)}
    assert counts == {k: len(sections[k]) for k in "SGDP"}
    g = "".join(r[:72] for r in sections["G"])
    assert g.startswith("1H,,1H;,") and "2HMM" in g
    d = sections["D"]
    entities = []
    for k in range(0, len(d), 2):
        etype, p_start = int(d[k][0:8]), int(d[k][8:16])
        p_count = int(d[k + 1][24:32])
        recs = sections["P"][p_start - 1:p_start - 1 + p_count]
        assert all(int(r[64:72]) == k + 1 for r in recs)              # back pointer to D
        params = "".join(r[:64] for r in recs).strip().rstrip(";").split(",")
        assert int(params[0]) == etype == 110
        entities.append(tuple(float(v) for v in params[1:7]))
    return entities


def test_iges_lines_match_the_walls(geom, tmp_path):
    path = X.export_iges(geom, tmp_path / "w.igs", {"app_version": "9.9", "export": "IGES"})
    entities = _read_iges(path.read_text(encoding="ascii"))
    segs = X.segments(geom)
    assert len(entities) == len(segs)
    for (x0, y0, z0, x1, y1, z1), (_, a, b) in zip(entities, segs):
        assert (x0, y0, x1, y1) == pytest.approx((a[0] * 1e3, a[1] * 1e3, b[0] * 1e3,
                                                  b[1] * 1e3), rel=1e-8, abs=1e-9)
        assert z0 == z1 == 0.0


def test_points_csv_blocks(geom, tmp_path):
    path = X.export_points_csv(geom, tmp_path / "w.csv")
    blocks, current = {}, None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# wall: "):
            current = line[len("# wall: "):]
            blocks[current] = []
        elif current and line and not line.startswith("#") and line != "x_m,y_m":
            x, y = line.split(",")
            blocks[current].append((float(x), float(y)))
    assert blocks == X.walls(geom)                                     # exact (repr floats)


def test_gmsh_geo_points_and_lines(geom, tmp_path):
    path = X.export_gmsh_geo(geom, tmp_path / "w.geo")
    text = path.read_text(encoding="utf-8")
    points = {int(i): (float(x), float(y)) for i, x, y in re.findall(
        r"Point\((\d+)\) = \{([^,]+), ([^,]+), 0, lc\};", text)}
    lines = {int(i): (int(a), int(b)) for i, a, b in re.findall(
        r"Line\((\d+)\) = \{(\d+), (\d+)\};", text)}
    phys = {name: [int(v) for v in ids.split(",")] for name, ids in re.findall(
        r'Physical Curve\("(\w+)"\) = \{([\d, ]+)\};', text)}
    assert set(phys) == {"RAMP", "COWL"}
    for name, pts in X.walls(geom).items():
        drawn = [(points[lines[i][0]], points[lines[i][1]]) for i in phys[name.upper()]]
        assert drawn == list(zip(pts, pts[1:]))
    assert re.search(r"^lc = [\d.e-]+;$", text, re.M)


def test_dxf_still_parses_with_ezdxf(geom, tmp_path):
    import ezdxf

    from inletdesign.export import export_dxf

    path = export_dxf(geom, tmp_path / "w.dxf")
    doc = ezdxf.readfile(path)
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert {"RAMP", "COWL"} <= layers
    ramp = next(e for e in doc.modelspace() if e.dxf.layer == "RAMP")
    pts = [(x / 1e3, y / 1e3) for x, y in ramp.get_points("xy")]
    assert pts == pytest.approx([tuple(p) for p in geom.ramp_points], abs=1e-12)
    assert math.isclose(doc.header["$INSUNITS"], 4)
