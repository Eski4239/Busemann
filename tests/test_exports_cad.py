"""CFD-tool geometry export (M8.2, M8.4: Gmsh .geo only) and the DXF. Each file is parsed
back and must reproduce the walls (no Qt)."""
import math
import re

import pytest

from inletdesign import api
from inletdesign import export_cad as X


@pytest.fixture(scope="module", params=[(3.0, 2, None), (6.7, 4, None), (3.0, 3, [7.0, 8.0, 9.0])])
def geom(request):
    M, n, angles = request.param
    return api.inlet_geometry(api.design(M, n, ramp_angles=angles))


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
