import csv
import json

import pytest

from inletdesign import inlet as _inlet
from inletdesign.cli import main
from inletdesign.geometry import design_inlet


def test_design_creates_files_and_matches(tmp_path):
    out = tmp_path / "m3_2r"
    code = main(["design", "--mach", "3.0", "--ramps", "2", "--out", str(out)])
    assert code == 0

    png_path = out.with_suffix(".png")
    dxf_path = out.with_suffix(".dxf")
    json_path = out.with_suffix(".json")
    assert png_path.exists()
    assert dxf_path.exists()
    assert json_path.exists()

    with open(json_path) as f:
        data = json.load(f)

    geom = design_inlet(3.0, 2)
    states = _inlet.compress(3.0, geom.ramp_angles_deg)
    expected_recovery = states[-1].p0_ratio

    assert data["recovery"] == pytest.approx(expected_recovery, abs=1e-12)


def test_curve_creates_files_with_expected_rows(tmp_path):
    out = tmp_path / "curve"
    code = main(
        [
            "curve", "--ramps", "0", "1", "2", "3",
            "--mach-min", "1.5", "--mach-max", "4.0", "--step", "0.1",
            "--out", str(out),
        ]
    )
    assert code == 0

    csv_path = out.with_suffix(".csv")
    png_path = out.with_suffix(".png")
    assert csv_path.exists()
    assert png_path.exists()

    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    ramp_counts_present = {int(r["n_ramps"]) for r in rows}
    assert ramp_counts_present == {0, 1, 2, 3}

    match = None
    for r in rows:
        if int(r["n_ramps"]) == 2 and abs(float(r["M_inf"]) - 3.0) < 1e-6:
            match = r
            break
    assert match is not None
    assert float(match["recovery"]) == pytest.approx(0.7437, rel=1e-3)


def test_design_invalid_mach_returns_2(tmp_path):
    out = tmp_path / "bad"
    code = main(["design", "--mach", "0.5", "--ramps", "2", "--out", str(out)])
    assert code == 2
    assert not list(tmp_path.iterdir())


def test_design_invalid_ramps_returns_2(tmp_path):
    out = tmp_path / "bad"
    code = main(["design", "--mach", "3.0", "--ramps", "-1", "--out", str(out)])
    assert code == 2
    assert not list(tmp_path.iterdir())


def test_curve_invalid_mach_range_returns_2(tmp_path):
    out = tmp_path / "bad"
    code = main(
        [
            "curve", "--ramps", "1",
            "--mach-min", "4", "--mach-max", "2", "--step", "0.1",
            "--out", str(out),
        ]
    )
    assert code == 2
    assert not list(tmp_path.iterdir())


def test_help_exits_zero():
    for argv in (["--help"], ["design", "--help"], ["curve", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main(argv)
        assert exc_info.value.code == 0


def test_offdesign_output_survives_a_cp1252_pipe():
    """Cowl warnings contain θmax / M∞; piped Windows stdout (cp1252) must not crash."""
    import os
    import subprocess
    import sys
    from pathlib import Path

    src = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ, PYTHONIOENCODING="cp1252",
               PYTHONPATH=src + os.pathsep + os.environ.get("PYTHONPATH", ""))
    out = subprocess.run(
        [sys.executable, "-c", "import sys; from inletdesign.cli import main; "
         "sys.exit(main(['offdesign', '--design-mach', '6.7', '--ramps', '4', '--mach', '6.7']))"],
        env=env, capture_output=True, timeout=60)
    assert out.returncode == 0, out.stderr.decode("cp1252", "replace")
    assert b"External cowl shock detached" in out.stdout
