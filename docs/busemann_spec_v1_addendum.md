# Busemann v1 — spec addendum (supersedes the v1 scope in busemann_spec.md §8)

Status: agreed 2026-11-03, revised 2026-11-04 (M8.2, after user testing of M1–M8: less
clutter, DXF design files; see sections I and J). v1 and the former v1.1 ship together in
ONE launch.
All rules in busemann_spec.md §1 still hold (pure core via api.py, never block the UI,
honest warnings, tests green, CLAUDE.md source rule). Visual language: unchanged
(tokens §5). Every addition must keep the UI uncluttered: new things go into tabs,
menus or windows, never extra rows on existing panels unless listed here.

## A. Information architecture

- **Welcome window** (modal, before the main window; M8.2): a 3D render of a generic
  two-ramp inlet on the left; "New design" (Validation case, Blank), "Examples" (the
  Concorde cruise, XB-70, SR-71 and X-15 record presets plus the bundled example designs,
  one list), "Recent" (8) with Open…, and a "Show tour" checkbox (checked on first launch
  only). No "Show at startup" option. Closing it opens the main window with the default
  design.
- **Main tabs:** Design · Off-design · Analytics · Compare, in the toolbar row (left);
  Explain stays in the toolbar (right). The layer toggles (Shocks · Regions · Dimensions ·
  Grid) sit in the row above the canvas.
- **Right panel tabs:** Results · Verification.
- **Tools menu → Isentropic ramp…** opens a separate window.
- **Files:** designs are DXF drawings (section I). No other project format.
- **Exports (M8.4):** geometry DXF (also the save format), CFD domain DXFs (design and
  off-design), Gmsh .geo, results JSON/CSV. No IGES, wall-point CSV or figure
  (PNG/SVG/PDF) export, and NO animation export. Every geometry/CFD export
  also writes `verification_notes.md` next to it (section E). File ▸ Export and the
  Results tab's Export button hold the same actions.

## B. Foundations (M7)

1. Welcome window + 3-step tour (canvas, Explain, Off-design), skippable, never shown
   again once dismissed (stored in QSettings).
2. Undo/redo (Ctrl+Z / Ctrl+Shift+Z) over all design inputs. A slider drag or a canvas
   corner drag is ONE undo step. Loading a project clears history.
3. Unit-aware inputs: every numeric field accepts a value with a unit ("65000 ft",
   "20 km", "-56.5 C", "2.2" for Mach) and converts to the field's unit; invalid input
   shows the M2 field error. Small in-house parser (no new dependency), unit table in
   units.py, tests for every accepted unit.
4. Keyboard shortcuts with a "?" cheat-sheet overlay: F fit, E explain, Space play/pause
   sweep (only while the Off-design canvas or tab background has focus, so focused
   buttons keep Space), Ctrl+Z/Ctrl+Shift+Z, Ctrl+S/O/N, 1–4 main tabs. The mouse wheel
   changes a slider, combo box or number field only while it has focus; otherwise it
   scrolls the panel.
5. Export styling: the matplotlib canvas figure matched the screen. *Withdrawn in M8.4:
   figure exports were removed (section K).*

## C. Designer additions (M8)

1. **Engine sizing.** Capture size has two modes: "Set capture height" (current) or
   "Size to engine mass flow" (inputs: required ṁ in kg/s, inlet width). The chosen mode
   drives the design; the other value is shown read-only. Mass flow per metre stays,
   plus total ṁ when a width exists. Off-design shows supplied vs demanded ṁ at the
   slider Mach (spillage reduces supply) with a surplus/shortfall badge.
2. **MIL-E-5008B reference.** η_MIL = 1 − 0.075 (M∞ − 1)^1.35 for 1 < M∞ ≤ 5,
   η_MIL = 800 / (M∞⁴ + 935) for M∞ > 5. Input "Subsonic diffuser recovery"
   (Advanced, default 0.97, labelled estimate). KPI shows inviscid recovery and the
   engine-face estimate (× diffuser) against η_MIL. Line on the off-design recovery
   chart. SOURCE required (pending until confirmed).
3. **Gap to optimum (custom angles).** "Recovery X % below the Oswatitsch optimum for
   N ramps" plus ∂η/∂θ_k per ramp in the ramp table.
4. **Canvas interaction.** In custom mode ramp corners are draggable; while dragging,
   the limit is a shaded no-go zone and recovery / gap update live. Each θ_k has fixed
   bounds for the whole drag: 0.5° to min(θmax at the local Mach − 0.5°, 30°), cut further
   where a downstream ramp would detach (with 0.5° margin), the flow ahead of a ramp would
   turn subsonic, or the geometry would cross (corners in increasing x, below the lip,
   throat ≥ 5 % of h_c); so the design never fails during a drag and the handles never
   disappear. At a bound the handle stops and a small note ("Limit: detachment at
   28.75°") fades out after release. Left-drag on empty background pans. ▶ button + Space
   sweeps the off-design Mach (speed 0.5×/1×/2×, loop icon).
5. **Separation warnings (approximate).** Shock/boundary-layer incipient-separation
   check on every ramp shock and the terminal shock, using published empirical
   criteria (sources required, I confirm each). Always worded "approximate — verify
   with CFD". The validation CFD (15.5 mm bubble) is quoted where it applies.
6. **Verification tab** (right panel): every approximation and warning (separation,
   buzz, cowl detachment, real gas, upper-bound recovery, drag estimates), each with
   severity, the criterion used, its source and "must be verified with a CFD solver".

## D. Analytics tab (M9) — all approximate items titled "(approximate)"

1. **Trade study:** recovery vs number of ramps 0–4 plus the isentropic (n → ∞) limit,
   at the current design Mach; second axis: cowl angle. Optional sweep over design Mach.
2. **Cowl and additive (spillage) drag (approximate):** cowl external pressure drag and
   additive drag vs M∞ for the current design; "not computable" where the cowl shock is
   detached. Sources required.
3. **Inlet characteristic and buzz (approximate):** recovery vs mass-flow ratio
   (supercritical / critical / subcritical), buzz onset marked with a named empirical
   criterion (e.g. Ferri–Nucci or Dailey). Sources required; model choices reviewed
   before implementation.

## E. Verification notes export

`verification_notes.md` written with every geometry/CFD export: inputs, model
assumptions, the full Verification-tab list with sources, the validation summary, and
the statement that all approximate results must be verified with a CFD solver.

## F. Compare view (M10)

- "Pin" in the Design tab freezes the current design into slot A.
- Compare tab: slot A (pinned or loaded design DXF) beside slot B (built live in the
  tab with a compact input panel, or loaded). Side-by-side canvases, optional overlay
  of outlines, KPI table with Δ and %, off-design curves of both on shared axes.

## G. Isentropic ramp window (M11)

- Separate window. Isentropic (Prandtl–Meyer simple-wave) compression surface whose
  characteristics focus on the cowl lip, for a chosen final Mach or total turning.
- Zoomed view of the ramp and lip with an exact pressure (and Mach) contour field:
  in a simple wave p is constant along each straight characteristic.
- Exports the contour as geometry DXF (+ verification notes). Comparison line to the
  multi-ramp design's recovery.

## H. Release (M12)

One-folder PyInstaller build wrapped in an Inno Setup installer (LGPL-compliant,
PySide6-Essentials only), MIT LICENSE, README with screenshots/GIF, GitHub release.

## I. Design files: DXF (M8.2)

The `.busemann` JSON format is removed (menu items, drag-and-drop and examples).

- **Save / Save As** write a DXF drawing (R2010, millimetres, `$INSUNITS = 4`) with the
  geometry on the layers of the geometry export (RAMP polyline from the leading edge to the
  terminal-shock foot, COWL line from the lip, SHOCKS) and every input as a DXF custom
  header property:
  - `BUSEMANN_FORMAT = busemann-dxf`, `BUSEMANN_SCHEMA = 1`, `BUSEMANN_APP_VERSION`,
    `BUSEMANN_SAVED_UTC`;
  - `BUSEMANN_<FIELD>` for every input (`BUSEMANN_MACH`, `BUSEMANN_T_K`,
    `BUSEMANN_CUSTOM_ANGLES`, …), each value JSON-encoded so floats round-trip exactly;
  - `BUSEMANN_VIEW` (layer toggles, active tab).
  An invalid design is saved as the header only. Unknown `BUSEMANN_*` keys load with a
  warning; a newer schema is refused; older schemas migrate step by step (hook kept).
- **Open** a Busemann DXF: every input is restored exactly (round-trip tests for every
  preset and a custom 4-ramp design).
- **Open** any other DXF: the ramp and cowl lines are imported as a custom-angle design.
  Ramp: entities on a layer whose name contains RAMP, else the longest open polyline;
  cowl: a layer containing COWL, else a single line above the ramp. The leading edge is
  the ramp's lowest-x point with the freestream along +x; each corner's turn is a ramp
  angle (1–4 ramps, all turning towards the cowl); the lip (the cowl's upstream end) gives
  h_c. Units from `$INSUNITS` (mm when unitless; a "metres" drawing whose capture height
  would exceed 5 m is read as millimetres, with a warning). The design opens untitled
  (Save never writes over the source drawing) with the banner "Imported geometry —
  flight conditions unknown, set them in the left panel". Unrecognised geometry gives an
  error naming what is missing (no ramp line, no cowl line, corners not in increasing x,
  more than 4 ramps, a ramp turning away from the cowl).
- Recent list, welcome window, title and dirty tracking work on DXF paths. Bundled
  examples are DXFs (`tools/make_examples.py`).
- **CFD-tool export** (with `verification_notes.md`): Gmsh `.geo` (Point / Line in m,
  Physical Curve RAMP and COWL). The IGES and point-CSV exports of M8.2 were removed in
  M8.4 (section K).

## J. M8.2 revision (after user testing)

1. **Robustness.** PySide6 6.12 lets an exception escaping an overridden Qt event handler
   hang the event loop (the app freezes, then Windows closes it). Every event-handler
   override is wrapped (`busemann.crashlog.guarded`, enforced by a test), the worker jobs
   report unexpected exceptions as errors, and `crash.log` (Busemann data folder) records
   tracebacks, native crashes and UI stalls over 10 s.
2. **Results panel:** total recovery (engine-face vs MIL line), mass capture, captured ṁ,
   M after the terminal shock and cowl margin, as smaller cards; in the off-design view
   the values at the slider Mach without Δ lines. No source citations or CFD comparisons
   (they live in Verification, Explain and the exported notes). "Stations" is now "Flow
   regions"; every column of it and of the ramp table is fully visible at 1280×800 and at
   150 %. An Export button with the full export menu ends the tab.
3. **Warnings:** a compact banner at the top of the right panel ("N warnings — review
   before using these results", click scrolls to them); groups "At the design point
   (M∞ 3.00)" and "At M∞ 2.55 (off-design)"; each warning a one-line title with a
   severity icon, expandable to the full text.
4. **Off-design tab:** subtitle "How this fixed inlet performs at other flight Mach
   numbers"; charts collapsed under one "Charts ▸" bar, at least twice the former height
   when expanded; band colours explained in hover tooltips instead of text rows; a
   continuous, higher-contrast Mach colour map on the off-design canvas (sonic line kept)
   with its own legend "Mach (off-design view)".
5. **Explain:** a topic tree in the right column (Freestream; Ramp shock 1…N; Regions;
   Terminal shock; Cowl lip; Design method; Off-design; Separation (approximate)); a click
   opens a popup with the relations, this case's numbers, plain words and assumptions.
   The canvas selection highlights its topic. Explain forces the right column open and
   disables its hide toggle until Explain closes. User-facing text uses symbols (θmax, M∞,
   M₁ sin β, °), checked by a test over the explain entries, tooltips and core messages.
6. **Method buttons:** "Optimum angles" (tooltip "Oswatitsch optimum: equal-strength
   shocks, maximum total-pressure recovery for this number of ramps") and "Custom
   angles" ("Set each ramp angle yourself").
7. **About:** short, first person: what Busemann is, who made it and why, three
   assumptions, how it was checked, licences collapsed (M8.4 text: section K).

## K. M8.4 revision

1. **About ▸ Who made it and why:** "My name is Pablo Goulet Valenti and I made this
   during my university years in order to explore the world of high-speed flows. Inlets
   are a key part of powerplants and propulsion systems, and being able to build an
   interactive solver to design these geometries allows one to learn quite a bit. I hope
   this tool is useful to you and you learn something new along the way too!"
2. **About ▸ How it was checked:** one paragraph replaces the validation table (NACA
   Report 1135 relations, over 800 automated tests, Ansys Fluent 2D CFD inviscid and
   k-ω SST with a mesh check; design point within 0.35 %, below design within 0.1 %
   recovery and 0.4 % capture, viscous about 2 % lower with the second-corner bubble,
   above design an upper bound, CFD 4.9 % lower at Mach 3.25). The same paragraph is
   the validation summary of `verification_notes.md`.
3. **No internal phase names** ("Phase 3a/3b/3d") in any user-facing text: About,
   tooltips, Explain, Verification, the notes, warnings and the chart CFD markers say
   "the validation CFD" with the same numbers. A test fails on any user string matching
   `/phase\s*3/i`. The validation reports stay in `docs/` but are not linked from the UI.
4. **Advanced numeric inputs** (max cowl angle, cowl lip wedge, diffuser recovery, γ) are
   spin boxes: arrows plus unit-aware typing, at least 96 px wide, label above the field
   when it does not fit beside it. Hard limits: angles 0–90° (step 0.1°), diffuser
   recovery 0–1 (step 0.01), γ 1–5/3 (step 0.01). A typed value outside the limits is
   clamped with the field note "Maximum 90°" (or the limit reached); the arrows and the
   wheel stop at the limit; the wheel works only when the field has focus. Physics checks
   for allowed but unwise values stay (e.g. the core's 0–30° lip-wedge range is reported
   on the field; recovery 0 and a max cowl angle of 0 are shown as errors, not applied).
5. **Exports trimmed:** IGES, wall-point CSV and the figure exports (canvas and
   off-design charts, PNG/SVG/PDF) are removed. matplotlib stays a dependency: the
   Explain equations are rendered with its mathtext (and the core CLI plot and
   `tools/render_inlet_3d.py` use it).
6. **Canvas dimension labels** use real subscripts (h<sub>c</sub>, h<sub>t</sub>,
   L<sub>1</sub>, θ<sub>1</sub>, rich text), and so do the hover / selection read-out
   labels (M<sub>n1</sub>, p<sub>2</sub>/p<sub>1</sub>). A test scans them for "_".
