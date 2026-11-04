"""Designs are DXF files (M8.2, no Qt): a Busemann DXF stores every input as BUSEMANN_*
header properties and reopens exactly; any other DXF is imported from ramp and cowl lines."""
import dataclasses

import ezdxf
import pytest

from busemann import project as P
from busemann.inputs import Inputs, preset_changes
from inletdesign import api
from inletdesign.export import export_dxf
from inletdesign.presets import PRESETS


def _cases():
    for p in PRESETS:
        yield p.name, dataclasses.replace(Inputs(), **preset_changes(p.name))
    yield "custom 4-ramp", Inputs(mach=3.4, n_ramps=4, method="custom",
                                  custom_angles=(6.0, 7.25, 8.5, 9.125), cowl_wedge_deg=3.5,
                                  capture_mode="mass_flow", mdot_kgps=12.3456789,
                                  inlet_width_m=0.731, diffuser_recovery=0.955,
                                  off_design_mach=3.1, units="Imperial")


@pytest.mark.parametrize("label, inputs", list(_cases()), ids=lambda x: str(x)[:20])
def test_round_trip_reproduces_identical_inputs_and_results(tmp_path, label, inputs):
    view = {"layers": {"grid": True, "dimensions": True}, "tab": "offdesign"}
    path = P.save(tmp_path / "d.dxf", inputs, view)
    loaded = P.load(path)
    assert not loaded.imported and loaded[2] == []
    assert loaded[0] == inputs                                      # dataclass equality
    assert loaded[1]["tab"] == "offdesign" and loaded[1]["layers"]["grid"]
    a, b = P.design_for(inputs), P.design_for(loaded[0])
    assert (a is None and b is None) or a == b                     # identical results


def test_saved_file_is_a_dxf_with_geometry_and_namespaced_header(tmp_path):
    path = P.save(tmp_path / "d.dxf", Inputs(mach=3.2))
    doc = ezdxf.readfile(path)
    header = P.custom_header(doc)
    assert header["BUSEMANN_FORMAT"] == "busemann-dxf" and header["BUSEMANN_SCHEMA"] == "1"
    assert header["BUSEMANN_MACH"] == "3.2" and header["BUSEMANN_T_K"] == "220.0"
    for f in dataclasses.fields(Inputs):
        assert f"BUSEMANN_{f.name.upper()}" in header
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert {"RAMP", "COWL", "SHOCKS"} <= layers


def test_invalid_design_saves_the_header_only(tmp_path):
    bad = Inputs(method="custom", custom_angles=(40.0, 40.0))
    path = P.save(tmp_path / "bad.dxf", bad)
    assert len(list(ezdxf.readfile(path).modelspace())) == 0
    assert P.load(path)[0] == bad


@pytest.mark.parametrize("M, n, angles", [(3.0, 2, [9.0, 10.0]), (2.5, 3, [5.0, 6.0, 7.0]),
                                          (6.7, 4, [6.0, 7.0, 8.0, 9.0])])
def test_foreign_dxf_is_imported_as_custom_angles(tmp_path, M, n, angles):
    d = api.design(M, n, capture_height=0.137, ramp_angles=angles)
    path = export_dxf(api.inlet_geometry(d), tmp_path / "other.dxf")   # no BUSEMANN_ keys
    base = Inputs(mach=2.2, altitude_m=15000.0)
    loaded = P.load(path, base=base)
    i = loaded[0]
    assert loaded.imported and loaded[2] == [P.IMPORT_BANNER]
    assert i.method == "custom" and i.n_ramps == n
    assert i.custom_angles == pytest.approx(tuple(angles), abs=1e-9)
    assert i.capture_height_m == pytest.approx(0.137, abs=1e-12)
    assert (i.mach, i.altitude_m) == (2.2, 15000.0)                   # flight from base


def _drawing(tmp_path, ramp=None, cowl=None, ramp_layer="RAMP", cowl_layer="COWL"):
    doc = ezdxf.new()
    msp = doc.modelspace()
    if ramp:
        msp.add_lwpolyline(ramp, dxfattribs={"layer": ramp_layer})
    if cowl:
        msp.add_line(*cowl, dxfattribs={"layer": cowl_layer})
    path = tmp_path / "x.dxf"
    doc.saveas(path)
    return path


def test_import_by_shape_when_layers_have_other_names(tmp_path):
    path = _drawing(tmp_path, ramp=[(0, 0), (100, 15.838), (200, 52.236)],
                    cowl=((190, 100), (240, 130)), ramp_layer="0", cowl_layer="0")
    loaded = P.load(path)               # ezdxf.new() says metres; the size says millimetres
    i = loaded[0]
    assert i.n_ramps == 2 and i.capture_height_m == pytest.approx(0.1)
    assert any("read as millimetres" in w for w in loaded[2])


@pytest.mark.parametrize("ramp, cowl, message", [
    (None, ((0, 100), (50, 120)), "no ramp line found"),
    ([(0, 0), (100, 10), (200, 40)], None, "no cowl line found"),
    ([(0, 0), (100, 10), (90, 40)], ((0, 100), (50, 120)), "not in increasing x"),
    ([(0, 0), (100, 20), (200, 30)], ((150, 100), (200, 120)), "turn the flow towards"),
    ([(0, 0), (10, 1), (20, 3), (30, 6), (40, 10), (50, 15)], ((40, 50), (60, 60)),
     "up to 4 ramps"),
])
def test_unrecognised_geometry_names_what_is_missing(tmp_path, ramp, cowl, message):
    with pytest.raises(P.ProjectError, match=message):
        P.load(_drawing(tmp_path, ramp, cowl))


def test_not_a_dxf_and_missing_file(tmp_path):
    bad = tmp_path / "bad.dxf"
    bad.write_text("this is not a drawing", encoding="utf-8")
    with pytest.raises(P.ProjectError):
        P.load(bad)
    with pytest.raises(P.ProjectError, match="not found"):
        P.load(tmp_path / "missing.dxf")


def test_unknown_properties_warn_and_defaults_fill_in(tmp_path):
    doc = ezdxf.new()
    doc.header.custom_vars.append("BUSEMANN_FORMAT", "busemann-dxf")
    doc.header.custom_vars.append("BUSEMANN_SCHEMA", "1")
    doc.header.custom_vars.append("BUSEMANN_MACH", "2.5")
    doc.header.custom_vars.append("BUSEMANN_WARP_DRIVE", "true")
    doc.header.custom_vars.append("OTHER_TOOL_KEY", "ignored silently")
    path = tmp_path / "partial.dxf"
    doc.saveas(path)
    inputs, view, warnings = P.load(path)
    assert inputs == Inputs(mach=2.5)
    assert warnings == ["unknown property 'BUSEMANN_WARP_DRIVE' ignored"]


@pytest.mark.parametrize("key, text, message", [
    ("BUSEMANN_MACH", "\"fast\"", "invalid value"),
    ("BUSEMANN_N_RAMPS", "2.5", "invalid value"),
    ("BUSEMANN_MACH", "{not json", "not valid"),
])
def test_bad_values_raise_clear_errors(tmp_path, key, text, message):
    doc = ezdxf.new()
    for k, v in (("BUSEMANN_FORMAT", "busemann-dxf"), ("BUSEMANN_SCHEMA", "1"), (key, text)):
        doc.header.custom_vars.append(k, v)
    path = tmp_path / "bad.dxf"
    doc.saveas(path)
    with pytest.raises(P.ProjectError, match=message):
        P.load(path)


def test_newer_schema_is_refused(tmp_path):
    doc = ezdxf.new()
    doc.header.custom_vars.append("BUSEMANN_FORMAT", "busemann-dxf")
    doc.header.custom_vars.append("BUSEMANN_SCHEMA", "99")
    path = tmp_path / "new.dxf"
    doc.saveas(path)
    with pytest.raises(P.ProjectError, match="newer Busemann"):
        P.load(path)


def test_migration_hook_runs_older_schemas(monkeypatch):
    calls = []

    def step(data):
        calls.append(data["schema"])
        data["header"]["BUSEMANN_MACH"] = "2.7"
        return dict(data, schema=1)

    monkeypatch.setattr(P, "SCHEMA", 1)
    monkeypatch.setitem(P.MIGRATIONS, 0, step)
    data = P.migrate({"schema": 0, "header": {}})
    assert calls == [0] and data["schema"] == 1 and data["header"]["BUSEMANN_MACH"] == "2.7"
