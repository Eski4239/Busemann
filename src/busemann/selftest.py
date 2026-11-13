"""`busemann --self-test` (M12 PART 3): prove that an installed or frozen Busemann works,
without showing a window.

Each item loads or computes one thing the app needs and raises on any problem:
- resources: fonts, stylesheet, icons, brand assets, Explain entries and tooltips, the
  bundled example designs, the validation data, the licence texts;
- the core: the validation design (recovery 0.7437), one off-design point, the isentropic
  ramp case;
- the equation warm-up process: one equation rendered by explain.warm's spawn-started render
  process into an empty cache folder. This is the part a frozen build is most likely to
  break (multiprocessing.freeze_support, the child re-launching the exe, matplotlib's data in
  the bundle), so the item proves the render happened in a separate, spawn-started process:
  the start method is "spawn", the worker's process id differs from this one, and this
  process rendered nothing itself;
- a DXF written and read back in a temporary folder.

Every item runs. The summary line goes to stdout (when there is one: a windowed frozen exe has
none) and, with --self-test-log FILE, to that file with one line per item:

    Busemann 1.0.0 self-test: OK (13 checks, 4.2 s)
    Busemann 1.0.0 self-test: FAILED: equation warm-up (spawn): <reason> (1 of 13 failed)

Exit code 0 when every item passes, else the 1-based position of the first failing item.
"""
import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

from . import __version__

VALIDATION_RECOVERY = 0.7437          # M 3, 2 ramps, Oswatitsch (validated against CFD)
ISENTROPIC_CASE = dict(M_inf=3.0, delta_deg=33.789, M_f=1.6375, recovery=0.8809)
WARM_TIMEOUT_S = 120.0                # first spawn of a frozen exe imports matplotlib


class SelfTestError(Exception):
    """A check found a problem (the message names it)."""


def _require(condition, message):
    if not condition:
        raise SelfTestError(message)


# --- resources -------------------------------------------------------------------------------
def check_fonts():
    from .theme import qt as theme
    from .theme import tokens

    families = theme.load_fonts()
    for family in (tokens.FONT_UI, tokens.FONT_MONO):
        _require(family in families, f"font {family!r} not loaded (got {sorted(families)})")
    return f"{len(families)} families"


def check_stylesheet():
    from .theme import qt as theme

    qss = theme.stylesheet()
    _require("$" not in qss.replace("$$", ""), "unfilled $token in the stylesheet")
    return f"{len(qss)} chars"


def check_icons():
    from .paths import resource_path
    from .theme import qt as theme

    names = sorted(p.stem for p in resource_path("icons").glob("*.svg"))
    _require(names, "no icons found")
    for name in names:
        if name.endswith("-muted"):              # pre-tinted copies for QSS url()
            continue
        _require(not theme.icon(name, "text", 16).pixmap(16, 16).isNull(),
                 f"icon {name}.svg did not render")
    return f"{len(names)} icons"


def check_brand():
    from PySide6.QtGui import QPixmap

    from .paths import resource_path
    from .theme import qt as theme

    icon = theme.app_icon()
    sizes = sorted(s.width() for s in icon.availableSizes())
    _require(sizes == sorted(theme.APP_ICON_SIZES), f"app icon sizes {sizes}")
    _require(not theme.svg_pixmap("logo_lockup", 34, 2.0, "logo_lockup_2x.png").isNull(),
             "logo lockup did not render")
    _require(not QPixmap(str(resource_path("brand", "welcome_hero.png"))).isNull(),
             "welcome image did not load")
    _require(resource_path("brand", "busemann.ico").stat().st_size > 0, "busemann.ico empty")
    return f"icon {sizes[0]}–{sizes[-1]} px, lockup, welcome image, .ico"


def check_explain():
    from .explain import content as C
    from .tooltips import tooltips

    for name in C.ENTRY_NAMES:
        entry = C.load(name)
        _require(entry.sources(), f"explain entry {name} has no sourced relation")
    tips = tooltips()
    _require(len(tips) > 100, f"tooltips.json has only {len(tips)} entries")
    return f"{len(C.ENTRY_NAMES)} entries, {len(tips)} tooltips"


def check_examples():
    from . import project as P
    from .paths import resource_path

    paths = sorted(resource_path("examples").glob("*.dxf"))
    _require(paths, "no example designs found")
    for path in paths:
        loaded = P.load(path)
        _require(not loaded.imported, f"{path.name} is not a Busemann DXF")
        _require(P.design_for(loaded[0]) is not None, f"{path.name} gives no design")
    return f"{len(paths)} designs"


def check_validation_data():
    from .charts import model as CM
    from .paths import resource_path

    json.loads(resource_path("data", "validation.json").read_text(encoding="utf-8"))
    _require(CM.load_validation(), "validation.json is empty")
    _require(CM.load_cfd(), "validation CFD data missing")
    return "validation.json"


def check_licences():
    from .paths import resource_path

    components = json.loads(resource_path("licenses", "components.json")
                            .read_text(encoding="utf-8"))["components"]
    files = {f for c in components for f in c["files"]}
    for name in sorted(files):
        _require(resource_path("licenses", name).stat().st_size > 0, f"licence {name} empty")
    return f"{len(components)} components, {len(files)} texts"


# --- core --------------------------------------------------------------------------------------
def check_validation_design():
    from inletdesign import api

    d = api.design(3.0, 2)
    _require(abs(d.recovery_total - VALIDATION_RECOVERY) < 5e-5,
             f"recovery {d.recovery_total:.5f}, expected {VALIDATION_RECOVERY}")
    return f"recovery {d.recovery_total:.4f}"


def check_off_design():
    from inletdesign import api

    off = api.off_design_point(api.design(3.0, 2), 2.5)
    _require(0.0 < off.recovery_total <= 1.0, f"recovery {off.recovery_total}")
    _require(0.0 < off.mass_capture_ratio < 1.0, f"mass capture {off.mass_capture_ratio}")
    return f"M∞ 2.50: recovery {off.recovery_total:.4f}, capture {off.mass_capture_ratio:.4f}"


def check_isentropic():
    from inletdesign.isentropic_ramp import isentropic_ramp

    c = ISENTROPIC_CASE
    r = isentropic_ramp(c["M_inf"], delta_deg=c["delta_deg"], capture_height=0.1)
    _require(abs(r.M_f - c["M_f"]) < 1e-4, f"final Mach {r.M_f:.5f}, expected {c['M_f']}")
    _require(abs(r.recovery - c["recovery"]) < 1e-4,
             f"recovery {r.recovery:.5f}, expected {c['recovery']}")
    return f"final Mach {r.M_f:.4f}, recovery {r.recovery:.4f}"


# --- the equation render process ---------------------------------------------------------------
def check_warm_up():
    from inletdesign import api

    from .explain import mathsvg, warm

    texs = warm.equations(api.design(3.0, 2))          # what the app sends to the process
    _require(texs, "no Explain equations for the validation design")
    tex = texs[0]
    previous = os.environ.get("BUSEMANN_CACHE_DIR")
    with tempfile.TemporaryDirectory(prefix="busemann-selftest-") as tmp:
        os.environ["BUSEMANN_CACHE_DIR"] = tmp                 # empty: the render must happen
        try:
            renders_here = mathsvg.render_count
            warm.shutdown()                                     # a fresh pool for this check
            pool = warm._pool()
            method = pool._mp_context.get_start_method()
            _require(method == "spawn", f"render pool start method is {method!r}, not spawn")
            child = pool.submit(os.getpid).result(timeout=WARM_TIMEOUT_S)
            _require(child != os.getpid(), "the render pool runs in this process")
            futures = warm.start([tex], "#111827")
            _require(futures, "no render job was queued (cache folder not empty?)")
            rendered, longest_ms = futures[0].result(timeout=WARM_TIMEOUT_S)
            path = mathsvg.cache_path(tex, "#111827", mathsvg.EQUATION_PT, Path(tmp) / "equations")
            _require(rendered == 1, f"render process rendered {rendered} equations, expected 1")
            _require(path.is_file(), f"no SVG written by the render process ({path.name})")
            svg = path.read_bytes()
            _require(svg.startswith(b"<?xml") and b"<svg" in svg, "the SVG file is not valid")
            _require(mathsvg.render_count == renders_here,
                     "the equation was rendered in this process, not the render process")
        finally:
            warm.shutdown()
            if previous is None:
                os.environ.pop("BUSEMANN_CACHE_DIR", None)
            else:
                os.environ["BUSEMANN_CACHE_DIR"] = previous
    return f"spawn worker pid {child}, {len(svg)} bytes, {longest_ms:.0f} ms"


# --- files -------------------------------------------------------------------------------------
def check_dxf_round_trip():
    import dataclasses

    from . import project as P
    from .inputs import Inputs, preset_changes

    inputs = dataclasses.replace(Inputs(), **preset_changes("Validation case"))
    with tempfile.TemporaryDirectory(prefix="busemann-selftest-") as tmp:
        path = Path(tmp) / "selftest.dxf"
        P.save(path, inputs)
        loaded = P.load(path)
        header = P.custom_header(P._read_doc(path))
    _require(loaded[0] == inputs, "inputs read back differ from the inputs saved")
    _require(header.get("BUSEMANN_APP_VERSION") == __version__,
             f"saved app version {header.get('BUSEMANN_APP_VERSION')!r}")
    return "inputs identical after save and load"


CHECKS = (
    ("fonts", check_fonts),
    ("stylesheet", check_stylesheet),
    ("icons", check_icons),
    ("brand assets", check_brand),
    ("explain entries and tooltips", check_explain),
    ("example designs", check_examples),
    ("validation data", check_validation_data),
    ("licences", check_licences),
    ("validation design", check_validation_design),
    ("off-design point", check_off_design),
    ("isentropic ramp", check_isentropic),
    ("equation warm-up (spawn)", check_warm_up),
    ("DXF write and read", check_dxf_round_trip),
)


def _reason(exc):
    if isinstance(exc, SelfTestError):
        return str(exc)
    frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
    where = f" ({Path(frame.filename).name}:{frame.lineno})" if frame else ""
    return f"{type(exc).__name__}: {exc}{where}"


def run(checks=CHECKS, log=None):
    """Run every check; returns (exit code, summary line, per-check lines)."""
    lines, failures = [], []
    t_all = time.perf_counter()
    for k, (name, fn) in enumerate(checks, start=1):
        t0 = time.perf_counter()
        try:
            detail = fn()
            lines.append(f"  ok      {name}: {detail} ({time.perf_counter() - t0:.2f} s)")
        except Exception as exc:                   # noqa: BLE001 - reported, never raised
            failures.append((k, name, _reason(exc)))
            lines.append(f"  FAILED  {name}: {_reason(exc)} ({time.perf_counter() - t0:.2f} s)")
    total = time.perf_counter() - t_all
    head = f"Busemann {__version__} self-test: "
    if failures:
        k, name, reason = failures[0]
        summary = f"{head}FAILED: {name}: {reason} ({len(failures)} of {len(checks)} failed)"
        code = k
    else:
        summary = f"{head}OK ({len(checks)} checks, {total:.1f} s)"
        code = 0
    return code, summary, lines


def _emit(summary, lines, log_path):
    if sys.stdout is not None:                    # a windowed frozen exe has no stdout
        try:
            print(summary, flush=True)
        except OSError:
            pass
    if log_path:
        Path(log_path).write_text("\n".join([summary, *lines, ""]), encoding="utf-8")


def main(args, checks=None):
    """Entry from busemann.app.main: `--self-test [--self-test-log FILE]`. No window is
    shown; a QApplication exists for the fonts, icons and stylesheet."""
    log_path = None
    if "--self-test-log" in args:
        i = args.index("--self-test-log")
        log_path = args[i + 1] if i + 1 < len(args) else None
    try:
        from PySide6.QtWidgets import QApplication

        from .app import setup_application

        app = QApplication.instance() or QApplication(["busemann"])
        setup_application(app)
    except Exception as exc:                       # noqa: BLE001 - Qt itself is broken
        summary = f"Busemann {__version__} self-test: FAILED: Qt: {_reason(exc)}"
        _emit(summary, [], log_path)
        return 100
    code, summary, lines = run(checks if checks is not None else CHECKS)
    _emit(summary, lines, log_path)
    return code
