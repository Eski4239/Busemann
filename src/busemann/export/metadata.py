"""Metadata header carried by every export: app version, git commit, UTC date, all inputs."""
import dataclasses
import subprocess
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from .. import __version__


@lru_cache(maxsize=1)
def git_commit():
    """Short commit hash of the source tree, or None (not a git checkout, frozen app, no git)."""
    if getattr(sys, "frozen", False):
        return None
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(__file__).parent,
                             capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    commit = out.stdout.strip()
    return commit if out.returncode == 0 and commit else None


def metadata(inputs, what=""):
    """Dict for export headers. `what` names the export (e.g. "geometry DXF")."""
    data = {
        "app": "Busemann",
        "app_version": __version__,
        "git_commit": git_commit(),
        "exported_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": dataclasses.asdict(inputs),
    }
    if what:
        data["export"] = what
    return data


def default_name(inputs, kind, ext, off_mach=None):
    """busemann_M3.00_2ramp_<kind>[_M2.50].<ext>"""
    stem = f"busemann_M{inputs.mach:.2f}_{inputs.n_ramps}ramp_{kind}"
    if off_mach is not None:
        stem += f"_M{off_mach:.2f}"
    return f"{stem}.{ext.lstrip('.')}"
