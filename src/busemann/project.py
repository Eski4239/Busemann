"""Busemann project files (*.busemann, JSON; no Qt).

    {"format": "busemann-project", "schema": 1, "app_version": "0.1.0",
     "saved_utc": "2026-11-01T10:00:00Z",
     "inputs": {...every Inputs field..., "view": {"layers": {...}, "tab": "design"}}}

Loading validates the format and schema, migrates older schemas step by step through
MIGRATIONS, coerces value types, and reports unknown keys as warnings (never a crash).
Anything else wrong raises ProjectError with a message fit for an error dialog.
"""
import dataclasses
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .inputs import Inputs

FORMAT = "busemann-project"
SCHEMA = 1
SUFFIX = ".busemann"
LAYERS = ("shocks", "regions", "dimensions", "grid")
TABS = ("design", "offdesign")
DEFAULT_VIEW = {"layers": {"shocks": True, "regions": True, "dimensions": False, "grid": False},
                "tab": "design"}

# schema n -> function(data at schema n) -> data at schema n + 1. Schema 1 is the first
# release, so there is nothing to migrate yet; the hook is exercised by the tests.
MIGRATIONS = {}


class ProjectError(ValueError):
    """The file cannot be opened as a Busemann project; the message says why."""


# --- save -------------------------------------------------------------------------------

def to_dict(inputs, view=None, app_version=__version__):
    data = dataclasses.asdict(inputs)
    data["custom_angles"] = list(inputs.custom_angles)
    data["view"] = _clean_view(view or DEFAULT_VIEW)
    return {
        "format": FORMAT, "schema": SCHEMA, "app_version": app_version,
        "saved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "inputs": data,
    }


def save(path, inputs, view=None):
    path = Path(path)
    text = json.dumps(to_dict(inputs, view), indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")
    return path


# --- load -------------------------------------------------------------------------------

def load(path):
    """(Inputs, view, warnings) from a project file; ProjectError if it cannot be used."""
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectError(f"Cannot read {path.name}: {exc.strerror or exc}") from exc
    except UnicodeDecodeError as exc:
        raise ProjectError(f"{path.name} is not a text file (not a Busemann project)") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProjectError(f"{path.name} is not valid JSON (line {exc.lineno}, column "
                           f"{exc.colno}): the file may be truncated or corrupt") from exc
    return from_dict(data, path.name)


def from_dict(data, name="project"):
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ProjectError(f"{name} is not a Busemann project (missing \"format\": "
                           f"\"{FORMAT}\")")
    schema = data.get("schema")
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < 1:
        raise ProjectError(f"{name}: missing or invalid schema version ({schema!r})")
    if schema > SCHEMA:
        raise ProjectError(f"{name} was saved by a newer Busemann (schema {schema}; this "
                           f"version reads up to schema {SCHEMA})")
    data = migrate(data)
    raw = data.get("inputs")
    if not isinstance(raw, dict):
        raise ProjectError(f"{name}: \"inputs\" must be an object")
    warnings = [f"unknown top-level key {k!r} ignored" for k in data
                if k not in ("format", "schema", "app_version", "saved_utc", "inputs")]
    view, view_warnings = _read_view(raw.get("view"))
    warnings += view_warnings
    fields = {f.name: f for f in dataclasses.fields(Inputs)}
    values = {}
    for key, value in raw.items():
        if key == "view":
            continue
        if key not in fields:
            warnings.append(f"unknown input {key!r} ignored")
            continue
        values[key] = _coerce(key, value, fields[key], name)
    return Inputs(**values), view, warnings


def migrate(data):
    """Apply MIGRATIONS until the data is at SCHEMA."""
    while data["schema"] < SCHEMA:
        step = MIGRATIONS.get(data["schema"])
        if step is None:
            raise ProjectError(f"no migration from schema {data['schema']}")
        data = step(dict(data))
    return data


def _coerce(key, value, field, name):
    default = field.default
    if value is None and (default is None):
        return None
    kind = type(default) if default is not None else float if key == "off_design_mach" else str
    try:
        if kind is bool:
            if not isinstance(value, bool):
                raise TypeError
            return value
        if kind is int:
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError
            return value
        if kind is float:
            if isinstance(value, bool) or not isinstance(value, (int, float)) \
                    or not math.isfinite(value):
                raise TypeError
            return float(value)
        if kind is tuple:
            if not isinstance(value, list) or not all(
                    isinstance(v, (int, float)) and not isinstance(v, bool) for v in value):
                raise TypeError
            return tuple(float(v) for v in value)
        if not isinstance(value, str):
            raise TypeError
        return value
    except TypeError:
        raise ProjectError(f"{name}: input {key!r} has an invalid value {value!r} "
                           f"(expected {kind.__name__})") from None


def _clean_view(view):
    layers = dict(DEFAULT_VIEW["layers"])
    layers.update({k: bool(v) for k, v in (view.get("layers") or {}).items() if k in LAYERS})
    tab = view.get("tab") if view.get("tab") in TABS else "design"
    return {"layers": layers, "tab": tab}


def _read_view(view):
    if view is None:
        return dict(DEFAULT_VIEW, layers=dict(DEFAULT_VIEW["layers"])), []
    warnings = []
    if not isinstance(view, dict):
        return _read_view(None)[0], ["\"view\" is not an object; default view used"]
    for k in view:
        if k not in ("layers", "tab"):
            warnings.append(f"unknown view setting {k!r} ignored")
    for k in (view.get("layers") or {}):
        if k not in LAYERS:
            warnings.append(f"unknown layer {k!r} ignored")
    if "tab" in view and view["tab"] not in TABS:
        warnings.append(f"unknown tab {view['tab']!r}; Design tab used")
    return _clean_view(view), warnings
