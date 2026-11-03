"""Results export: JSON (full api results) and CSV (station table + off-design sweep). No Qt.

Both start with the export metadata (app version, git commit, UTC date, all inputs). CSV is
UTF-8 with a byte-order mark so spreadsheet programs show ° and ∞ correctly; units are in
the headers.
"""
import csv
import io
import json
from pathlib import Path

STATION_HEADERS = ("Region", "M [-]", "p/p∞ [-]", "T/T∞ [-]", "p0/p0∞ [-]", "flow angle [°]")
SWEEP_HEADERS = ("M∞ [-]", "regime", "A0/Ac [-]", "recovery total [-]", "recovery oblique [-]",
                 "M pre-terminal [-]", "M post-terminal [-]", "cowl margin [°]")


def _dict(obj):
    return None if obj is None else obj.to_dict()


def results_dict(metadata, design, freestream=None, off_design=None, sweep=None):
    """Everything computed for the current inputs, JSON-ready."""
    return {
        "metadata": metadata,
        "freestream": _dict(freestream),
        "design": _dict(design),
        "off_design": _dict(off_design),
        "sweep": _dict(sweep),
    }


def write_json(path, metadata, design, freestream=None, off_design=None, sweep=None):
    path = Path(path)
    data = results_dict(metadata, design, freestream, off_design, sweep)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def csv_text(metadata, regions, sweep=None, view="design"):
    """CSV with metadata comment lines, the station table, then the off-design sweep."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    for key, value in metadata.items():
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        w.writerow([f"# {key}: {text}"])
    w.writerow([f"# stations ({view})"])
    w.writerow(STATION_HEADERS)
    for st in regions:
        w.writerow([st.name, f"{st.M:.6g}", f"{st.p_ratio:.6g}", f"{st.T_ratio:.6g}",
                    f"{st.p0_ratio:.6g}", f"{st.theta_deg:.6g}"])
    if sweep is not None:
        w.writerow([])
        w.writerow(["# off-design sweep (empty rows: a ramp shock is detached)"])
        w.writerow(SWEEP_HEADERS)
        for M, p in zip(sweep.machs, sweep.points):
            if p is None:
                w.writerow([f"{M:.6g}", "detached", "", "", "", "", "", ""])
                continue
            margin = "" if p.cowl_margin_deg is None else f"{p.cowl_margin_deg:.6g}"
            w.writerow([f"{M:.6g}", p.regime, f"{p.mass_capture_ratio:.6g}",
                        f"{p.recovery_total:.6g}", f"{p.recovery_oblique:.6g}",
                        f"{p.M_pre_terminal:.6g}", f"{p.M_post_terminal:.6g}", margin])
    return buf.getvalue()


def write_csv(path, metadata, regions, sweep=None, view="design"):
    path = Path(path)
    path.write_text(csv_text(metadata, regions, sweep, view), encoding="utf-8-sig")
    return path
