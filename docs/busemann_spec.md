# Busemann — product & technical specification (v1)

*Busemann* is a desktop design lab for supersonic external-compression inlets, named after
Adolf Busemann (1901–1986). It wraps the validated `inletdesign` core in an interactive,
polished application. It is a portfolio project: it must look and feel like professional
engineering software and also teach the physics.

Audience: aerospace engineers and recruiters first, students second. Every number must be
credible and traceable, and an optional "explain" layer shows the theory behind it.

---

## 1. Hard rules

1. **Core stays pure.** `src/inletdesign/` (physics) gets no Qt, plotting or file-dialog code.
   The app talks to the core only through `src/inletdesign/api.py`. This keeps a future web
   version possible.
2. **Must package as a single Windows .exe** (PyInstaller, one-file). Avoid anything that
   breaks freezing: no runtime pip installs, no dynamic plugin discovery, resources loaded with
   `importlib.resources`, and no network access.
3. **Never block the UI.** Every interaction recomputes within about 50 ms. Debounce slider
   input (about 30 ms). Anything slower runs in a worker (`QThreadPool`) with a subtle busy
   indicator.
4. **Numbers are honest.** Show warnings whenever a model limit is reached (detached shock,
   overspeed upper bound, subsonic flow behind the ramps, real-gas regime, …). Never silently
   clamp.
5. **Tests stay green.** All existing tests pass. New core code gets unit tests. GUI gets
   `pytest-qt` smoke tests, skipped automatically when no display is available.

## 2. Technology

- Python ≥ 3.11, **PySide6** (Qt 6).
- **Inlet canvas**: `QGraphicsView`/`QGraphicsScene` with vector items. It is fully
  interactive (hover and click regions), animates smoothly, and stays crisp at any zoom.
- **Live charts**: `pyqtgraph`, styled to the theme, with hover crosshair readouts.
- **High-quality exports** (PNG/SVG/PDF figures): matplotlib (already used), *not* in the live
  UI.
- **Equations**: rendered with matplotlib mathtext to cached SVG/PNG pixmaps. No LaTeX install,
  no web engine.
- Packaging: PyInstaller spec file in `packaging/busemann.spec`.
- Entry points: `inletdesign gui` (existing CLI) and a new console script `busemann`.

## 3. Architecture

```
src/inletdesign/            # existing physics core (pure)
    api.py                  # NEW facade: frozen dataclasses, plain floats/lists, JSON-serialisable
    atmosphere.py           # NEW: US Standard Atmosphere 1976, 0–86 km
    units.py                # NEW: SI <-> imperial conversion helpers
    presets.py              # NEW: flight-condition presets (data only)
src/busemann/               # NEW app package (Qt)
    __main__.py, app.py     # QApplication, main window
    state.py                # single AppState (QObject) + signals; holds inputs & latest results
    theme/                  # tokens.py (colours, spacing, fonts), qss template, icons (SVG)
    widgets/                # reusable: LabeledSlider, NumberField (with units), KPI card, Badge, Drawer
    canvas/                 # InletScene, region items, shock items, dimension annotations
    charts/                 # pyqtgraph wrappers with theme + crosshair
    views/                  # FlightPanel, DesignPanel, ResultsPanel, OffDesignView, ExplainDrawer
    export/                 # exporters (DXF, CFD domains, figures, JSON/CSV, project files)
    resources/              # fonts (bundled, OFL licensed), icons, about text
```

Data flow: inputs → `AppState` → (debounced) `api.design()` / `api.off_design_*()` →
results signal → views update. Views never call the core directly.

## 4. Features (v1)

### 4.1 Flight conditions (left panel, top)
- Mach number: slider (1.2–6.0) plus numeric field (2 decimals).
- Atmosphere: **altitude** (0–40 km; ft in imperial), giving p∞, T∞, ρ∞, a∞ from the US
  Standard Atmosphere 1976. Alternatively, a **manual p∞, T∞** mode.
- Ratio of specific heats γ (default 1.4). Advanced section, collapsed by default.
- **Units toggle SI / Imperial**, global, affecting every displayed quantity and input.
- **Presets** dropdown:
  - Concorde cruise (M 2.02, 17 km)
  - XB-70 (M 3.0, 21.3 km)
  - SR-71 (M 3.2, 24 km)
  - X-15 record (M 6.7, 31 km); shows the real-gas warning
  - "Validation case" (M 3.0, p∞ 10 kPa, T∞ 220 K; manual mode)
  Presets are data in `presets.py`, each with a one-line description.
- Derived freestream readout: p∞, T∞, ρ∞, V∞, p0∞, T0∞, Reynolds number per metre.

### 4.2 Design (left panel, bottom)
- Number of ramps 0–4 (segmented control).
- Method: **Oswatitsch optimum** (equal-strength shocks, default) or **custom ramp angles**
  (one numeric field per ramp, validated against detachment).
- Capture height h_c (with units, default 0.1 m).
- Read-only results: ramp angles, shock angles, throat height, cowl angle.

### 4.3 Inlet canvas (centre, main tab "Design")
- Technical-drawing style:
  - ramps as solid dark-grey with 45° hatching;
  - cowl as a thin wedge;
  - shocks as amber lines, the terminal normal shock dashed;
  - capture streamtube as a thin dotted line.
- Flow regions filled with a **very light** sequential tint by local Mach number (perceptually
  uniform, low saturation, legend bar). Toggle on/off.
- **Hover** a region: floating readout of M, p/p∞, T/T∞, p0/p0∞ (and dimensional values in
  current units).
- **Click** a region: selects it (outline highlight) and opens the Explain drawer on that
  region.
- Dimension annotations (h_c, throat, ramp lengths, angles) in engineering style. Toggle.
- Zoom (wheel), pan (drag), fit (F), optional light grid with scale bar.
- Smooth transitions: when inputs change, geometry/shocks interpolate over about 150 ms
  (disable while dragging a slider for responsiveness, enable on release).

### 4.4 Results (right panel)
- KPI cards:
  - total pressure recovery (incl. terminal shock);
  - oblique-only recovery;
  - duct Mach number;
  - mass capture;
  - captured mass flow (kg/s per metre span, or lb/s per ft).
- Region table: region, θ, β, M, p/p∞, T/T∞, p0/p0∞. Copy-to-clipboard button (TSV).
- Warnings list (icons + text), always visible when non-empty.

### 4.5 Off-design explorer (second tab)
- Uses the **current design frozen** as the geometry ("Freeze design" happens automatically
  when switching tab; a chip shows "Design point: M 3.00, 2 ramps").
- Flight-Mach slider over [detachment limit, design + 1.5]; canvas shows the shocks moving
  relative to the lip.
- Regime badge: **Spillage / On-lip / Shock-in-duct / Detached**, colour-coded, with a
  one-line explanation.
- Two pyqtgraph charts vs M∞: mass capture, and recovery (oblique and total). Elements:
  - current-point marker;
  - design-point line;
  - shaded detachment region;
  - overspeed recovery drawn dotted and labelled "upper bound — cowl shock not modelled".
- Optional overlay of the CFD validation points from `docs/validation_3d.md` (M 2.5, 2.75,
  3.0, 3.25) as markers with a "CFD (Fluent, inviscid)" legend entry. Shown only when the
  design matches the validated case (M 3, 2 ramps, Oswatitsch).

### 4.6 Explain mode
- Toggle in the toolbar ("Explain"); the drawer slides in from the right.
- For the selected region or shock, show:
  - the governing relations (θ–β–M, normal-shock, isentropic, Oswatitsch equal-strength
    condition), rendered as equations;
  - the actual numbers substituted for the current case, step by step;
  - a short plain-language note (2–4 sentences) and the key assumptions (2D, inviscid,
    calorically perfect gas, steady).
- Tooltips on every label and KPI explaining the quantity (one sentence plus units).
- Content lives in `resources/explain/*.md` (lightweight markdown subset rendered in a
  `QTextBrowser`), so it is easy to edit.

### 4.7 Export & projects
- File menu:
  - New, Open, Save, Save As for project files `*.busemann`: JSON with inputs, version and
    app version. Recent files list.
  - Export → **Geometry DXF** (existing exporter).
  - Export → **CFD domain** (design-point, or off-design v2 with the normal external outlet).
  - Export → **Figure** (canvas or charts via matplotlib: PNG 300 dpi, SVG, PDF).
  - Export → **Results** (JSON and CSV).
- Every export writes a small metadata header (app version, date, inputs).

### 4.8 About & credibility
- About dialog: what the model assumes, its validation summary (3a: −0.35% recovery; 3b mesh
  check within 0.15%; 3d off-design within 0.1% recovery / 0.4% capture below design, −4.9%
  at M 3.25), links to the docs, licences.

## 5. Visual design ("modern engineering", light)

Feel: like a modern CAD/analysis tool (Onshape, nTop). Calm, precise, technical. **Not**
dark mode. **No** gradients, glassmorphism, neon, purple/AI aesthetics, emojis or
drop-shadow-heavy cards.

Tokens (put in `theme/tokens.py`, used everywhere, no hard-coded colours elsewhere):

| Token | Value | Use |
|---|---|---|
| bg | #F6F7F9 | window background |
| surface | #FFFFFF | panels, canvas |
| border | #E2E5EA | 1 px dividers |
| text | #111827 | primary text |
| text-muted | #6B7280 | labels, units |
| accent | #2563EB | selection, sliders, active tab, links |
| shock | #D97706 | shock lines |
| wall | #374151 | ramps/cowl |
| ok / warn / error | #059669 / #D97706 / #DC2626 | badges, warnings |

Typography:
- UI text: **Inter** (bundled, OFL).
- Numbers and units: **JetBrains Mono** (bundled, OFL), tabular figures.
- Sizes: 13 px base, 11 px labels in small caps, 22 px KPI values.

Layout:
- 8 px spacing grid, 6 px corner radius maximum, 1 px borders.
- Main window: left panel 300 px | canvas (flex) | right panel 320 px. Panels are
  collapsible. Minimum window 1280 × 800. High-DPI aware.

Micro-details:
- Units shown in muted mono after every value.
- Sliders show their value live.
- Inputs validate inline (red underline plus message) without dialogs.
- Status bar: compute time in ms, model ("ideal gas, γ = 1.40"), units.

Icons: simple 1.5 px-stroke SVG line icons (e.g. Lucide, ISC licence) bundled in
`resources/icons`.

App icon: a minimal mark of two oblique shock lines meeting at a cowl lip, in accent blue
on white.

## 6. Core additions for v1

- **Bug fix** in `offdesign.py`: just above second-shock detachment (M 2.39–2.40 for the
  validation design), the flow behind the last ramp shock is subsonic, and the terminal
  normal-shock step raises. In that case: no terminal shock; recovery_total =
  recovery_oblique; M_pre_terminal = M_post_terminal = that subsonic value; warning "flow subsonic behind last ramp
  shock; no terminal normal shock". Test: sweep M 2.39→3.5 in steps of 0.005 — every point
  returns a result or raises the documented "shock detached" ValueError, nothing else.
- `api.py`:
  - `design(...) -> DesignResult` (inputs, angles, per-region states, recoveries,
    M_pre_terminal / M_post_terminal, throat, geometry polylines, warnings). (M5: the
    ambiguous `M_duct` was renamed; its deprecated alias was removed in M12.)
  - `off_design_point(design, M) -> OffDesignResult`;
  - `off_design_sweep(design, M_min, M_max, n) -> Sweep` (points plus detachment Mach);
  - `freestream(M, altitude | (p, T), gamma) -> Freestream` (dimensional quantities).

  All outputs are JSON-serialisable (no numpy types). Validation errors use clear messages.
- `atmosphere.py`: US Standard Atmosphere 1976, 0–86 km. Tests against tabulated values at
  0, 11, 20, 32, 47 km (≤ 0.1%).
- `units.py`: conversions with tests (round trips).
- `presets.py`.

## 7. Testing & quality

- Unit tests for every new core module.
- GUI smoke tests (`pytest-qt`):
  - app starts;
  - changing Mach updates the KPIs;
  - switching tabs works;
  - export to a temp folder produces files;
  - project save/load round-trips.

  Mark with `@pytest.mark.gui`; skip when `QT_QPA_PLATFORM` is unavailable. CI runs the core
  tests; GUI tests run headless with `QT_QPA_PLATFORM=offscreen` if possible.
- Performance tests with generous limits (design < 50 ms, 100-point sweep < 500 ms).
- No warnings in the console on start-up.

## 8. Milestones (stop and report after each)

| # | Scope | Done when |
|---|---|---|
| M1 | Core: bug fix, `api.py`, `atmosphere.py`, `units.py`, `presets.py` + tests | all tests green |
| M2 | App shell: window, theme tokens, fonts, layout, Flight + Design panels wired to state, KPI cards | `busemann` opens, inputs update KPIs live |
| M3 | Inlet canvas: drawing, region tints, hover readouts, click selection, zoom/pan, annotations, animation | canvas matches §4.3 |
| M4 | Results table + warnings, Off-design tab with charts and regime badge (+ CFD overlay) | §4.4–4.5 complete |
| M5 | Explain mode (drawer, equations, tooltips, content files) | §4.6 complete |
| M6 | Export & projects, About dialog | §4.7–4.8 complete |
| M7 | Polish pass, PyInstaller one-file .exe, README with screenshots/GIF | `.exe` runs on a clean Windows machine |

## 9. Roadmap after v1 (do NOT build in v1, but do not block it)

1. Design comparison (0–4 ramps side by side, recovery-vs-Mach map, saved snapshots).
2. Report generator (one-click PDF).
3. Flight envelope analysis: trajectory (Mach vs altitude) mapped to recovery, capture and
   required geometry along the flight.
4. Inlet–engine matching (inlet mass flow vs simple compressor demand at RPM/altitude;
   critical/subcritical/supercritical operation).
5. Buzz & unstart checks (Kantrowitz starting limit, Ferri/Dailey-type buzz criteria) with
   clear "empirical/approximate" labelling.
6. Real-gas toggle `[ Ideal gas γ = 1.4 | High-temperature air ]`:
   - first thermally perfect air (vibrational γ(T) curve fits);
   - then equilibrium chemistry via Cantera, as an optional dependency.
7. 3D inlet view (extruded / axisymmetric, later waverider/Busemann inlet).
8. Web version (core reused via `api.py`).
