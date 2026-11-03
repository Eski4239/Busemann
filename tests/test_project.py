"""Project files (no Qt): round trips reproduce identical api results; bad files fail
cleanly; unknown keys warn; the migration hook works."""
import dataclasses
import json

import pytest

from busemann import project as P
from busemann.inputs import Inputs, preset_changes
from inletdesign import api
from inletdesign.presets import PRESETS


def _results(i):
    """Everything the app computes from inputs (as the state's worker does)."""
    fs = (api.freestream(i.mach, altitude_m=i.altitude_m, gamma=i.gamma)
          if i.atmosphere_mode == "altitude"
          else api.freestream(i.mach, p=i.p_pa, T=i.T_k, gamma=i.gamma))
    d = api.design(i.mach, i.n_ramps, capture_height=i.capture_height_m, gamma=i.gamma,
                   ramp_angles=list(i.custom_angles) if i.method == "custom" else None,
                   max_cowl_angle=i.max_cowl_deg if i.max_cowl_enabled else None,
                   cowl_wedge=i.cowl_wedge_deg)
    off = None
    if i.off_design_mach is not None:
        off = api.off_design_point(d, i.off_design_mach)
    return fs, d, off


def _cases():
    for preset in PRESETS:
        yield preset.name, dataclasses.replace(Inputs(), **preset_changes(preset.name))
    yield "custom 4-ramp", Inputs(
        mach=3.4, n_ramps=4, method="custom", custom_angles=(6.0, 7.0, 8.0, 9.0),
        capture_height_m=0.125, units="Imperial", off_design_mach=3.1, cowl_wedge_deg=4.0,
        max_cowl_enabled=True, max_cowl_deg=28.0, atmosphere_mode="manual", p_pa=8000.0,
        T_k=210.0, gamma=1.38)


@pytest.mark.parametrize("label, inputs", list(_cases()), ids=lambda x: str(x)[:20])
def test_round_trip_reproduces_identical_results(tmp_path, label, inputs):
    view = {"layers": {"shocks": True, "regions": False, "dimensions": True, "grid": True},
            "tab": "offdesign"}
    path = P.save(tmp_path / "case.busemann", inputs, view)
    loaded, loaded_view, warnings = P.load(path)
    assert warnings == []
    assert loaded == inputs and loaded_view == view
    assert _results(loaded) == _results(inputs)           # dataclass equality, field by field
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["format"] == "busemann-project" and data["schema"] == 1
    assert data["app_version"] and data["saved_utc"].endswith("Z")
    assert set(data["inputs"]) == {f.name for f in dataclasses.fields(Inputs)} | {"view"}


@pytest.mark.parametrize("text, message", [
    ('{"format": "busemann-project", "schema": 1, "inputs": {"mach": 3.0', "not valid JSON"),
    ("", "not valid JSON"),
    ('{"format": "something-else", "schema": 1, "inputs": {}}', "not a Busemann project"),
    ('[1, 2, 3]', "not a Busemann project"),
    ('{"format": "busemann-project", "schema": 99, "inputs": {}}', "newer Busemann"),
    ('{"format": "busemann-project", "inputs": {}}', "schema"),
    ('{"format": "busemann-project", "schema": 1, "inputs": {"mach": "fast"}}',
     "invalid value 'fast'"),
    ('{"format": "busemann-project", "schema": 1, "inputs": {"n_ramps": 2.5}}', "n_ramps"),
    ('{"format": "busemann-project", "schema": 1, "inputs": []}', "must be an object"),
])
def test_corrupt_files_raise_clear_errors(tmp_path, text, message):
    path = tmp_path / "bad.busemann"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(P.ProjectError, match=message):
        P.load(path)


def test_binary_or_missing_file_raises_clear_errors(tmp_path):
    binary = tmp_path / "image.busemann"
    binary.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00")
    with pytest.raises(P.ProjectError):
        P.load(binary)
    with pytest.raises(P.ProjectError, match="Cannot read"):
        P.load(tmp_path / "missing.busemann")


def test_unknown_keys_warn_and_defaults_fill_in(tmp_path):
    data = {"format": "busemann-project", "schema": 1, "extra": 1,
            "inputs": {"mach": 2.5, "colour": "red",
                       "view": {"tab": "nowhere", "layers": {"ghosts": True}, "zoom": 2}}}
    path = tmp_path / "x.busemann"
    path.write_text(json.dumps(data), encoding="utf-8")
    inputs, view, warnings = P.load(path)
    assert inputs == Inputs(mach=2.5)
    assert view == P.DEFAULT_VIEW
    assert len(warnings) == 5
    assert any("'colour'" in w for w in warnings) and any("'extra'" in w for w in warnings)


def test_migration_hook_runs_older_schemas(monkeypatch):
    def rename_speed(data):                       # pretend schema 1 called mach "speed"
        data = dict(data, schema=2)
        data["inputs"] = dict(data["inputs"])
        data["inputs"]["mach"] = data["inputs"].pop("speed")
        return data

    monkeypatch.setattr(P, "SCHEMA", 2)
    monkeypatch.setattr(P, "MIGRATIONS", {1: rename_speed})
    inputs, _, warnings = P.from_dict(
        {"format": "busemann-project", "schema": 1, "inputs": {"speed": 4.0}})
    assert inputs.mach == 4.0 and warnings == []
    monkeypatch.setattr(P, "MIGRATIONS", {})
    with pytest.raises(P.ProjectError, match="no migration"):
        P.from_dict({"format": "busemann-project", "schema": 1, "inputs": {}})


def test_current_schema_needs_no_migration():
    assert P.SCHEMA == 1 and P.MIGRATIONS == {}
    data = {"format": "busemann-project", "schema": 1, "inputs": {}}
    assert P.migrate(data) is data
