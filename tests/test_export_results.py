"""Results and DXF exports (no Qt): metadata header, units in headers, api values."""
import csv
import json

import ezdxf
import pytest

from busemann.export import metadata as M
from busemann.export import results as R
from busemann.inputs import Inputs
from inletdesign import api
from inletdesign.cfd_domain import export_cfd_domain_dxf, export_offdesign_domain_dxf
from inletdesign.export import export_dxf


def _meta():
    return M.metadata(Inputs(mach=3.0, cowl_wedge_deg=2.0), "test")


def test_metadata_fields():
    meta = _meta()
    assert meta["app"] == "Busemann" and meta["app_version"]
    assert meta["exported_utc"].endswith("Z") and meta["inputs"]["cowl_wedge_deg"] == 2.0
    assert meta["git_commit"] is None or len(meta["git_commit"]) >= 7
    assert M.default_name(Inputs(), "design", "png") == "busemann_M3.00_2ramp_design.png"
    assert M.default_name(Inputs(), "offdesign", ".png", 2.5) == \
        "busemann_M3.00_2ramp_offdesign_M2.50.png"


def test_json_has_everything(tmp_path):
    d = api.design(3.0, 2)
    off = api.off_design_point(d, 2.5)
    sweep = api.off_design_sweep(d, 2.4, 3.5, 6)
    fs = api.freestream(3.0, altitude_m=20000.0)
    data = json.loads(R.write_json(tmp_path / "r.json", _meta(), d, fs, off, sweep)
                      .read_text(encoding="utf-8"))
    assert data["metadata"]["inputs"]["mach"] == 3.0
    assert data["design"]["recovery_total"] == d.recovery_total
    assert len(data["design"]["regions"]) == 4 and len(data["design"]["shock_states"]) == 3
    assert data["design"]["notices"][0]["text"].startswith("Cowl near")
    assert data["off_design"]["mass_capture_ratio"] == off.mass_capture_ratio
    assert len(data["sweep"]["points"]) == 6 and data["freestream"]["T"] == fs.T


def test_csv_stations_and_sweep_with_units(tmp_path):
    d = api.design(3.0, 2)
    sweep = api.off_design_sweep(d, 2.0, 3.5, 7)            # first points detached
    path = R.write_csv(tmp_path / "r.csv", _meta(), d.regions, sweep)
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")                    # UTF-8 BOM for spreadsheets
    rows = list(csv.reader(raw.decode("utf-8-sig").splitlines()))
    assert rows[0][0].startswith("# app: Busemann")
    i = rows.index(list(R.STATION_HEADERS))
    assert "flow angle [°]" in rows[i] and "p/p∞ [-]" in rows[i]
    for row, st in zip(rows[i + 1:i + 5], d.regions):
        assert row[0] == st.name and float(row[1]) == pytest.approx(st.M, rel=1e-5)
        assert float(row[5]) == pytest.approx(st.theta_deg, rel=1e-5, abs=1e-9)
    j = rows.index(list(R.SWEEP_HEADERS))
    sweep_rows = rows[j + 1:]
    assert len(sweep_rows) == 7 and sweep_rows[0][1] == "detached"
    last = sweep.points[-1]
    assert float(sweep_rows[-1][2]) == pytest.approx(last.mass_capture_ratio, rel=1e-5)
    assert float(sweep_rows[-1][7]) == pytest.approx(last.cowl_margin_deg, rel=1e-5)


@pytest.mark.parametrize("exporter", ["geometry", "cfd", "cfd_off"])
def test_dxf_exports_carry_metadata(tmp_path, exporter):
    d = api.design(3.0, 2)
    geom = api.inlet_geometry(d)
    meta = _meta()
    path = tmp_path / f"{exporter}.dxf"
    if exporter == "geometry":
        export_dxf(geom, path, metadata=meta)
    elif exporter == "cfd":
        export_cfd_domain_dxf(geom, path, metadata=meta)
    else:
        export_offdesign_domain_dxf(geom, path, metadata=meta)
    doc = ezdxf.readfile(path)
    props = dict(doc.header.custom_vars)
    assert props["app"] == "Busemann" and props["app_version"] == meta["app_version"]
    assert json.loads(props["inputs"])["mach"] == 3.0
    if exporter == "cfd_off":                                 # v2: normal external outlet
        layers = {e.dxf.layer for e in doc.modelspace()}
        assert {"INLET", "FARFIELD_TOP", "OUTLET_EXT", "COWL", "OUTLET", "RAMP",
                "SYMMETRY"} <= layers
