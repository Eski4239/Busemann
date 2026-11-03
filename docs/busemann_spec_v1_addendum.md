# Busemann v1 — spec addendum (supersedes the v1 scope in busemann_spec.md §8)

Status: agreed 2026-11-03. v1 and the former v1.1 ship together in ONE launch.
All rules in busemann_spec.md §1 still hold (pure core via api.py, never block the UI,
honest warnings, tests green, CLAUDE.md source rule). Visual language: unchanged
(tokens §5). Every addition must keep the UI uncluttered: new things go into tabs,
menus or windows, never extra rows on existing panels unless listed here.

## A. Information architecture

- **Welcome window** (modal, before the main window): New design (preset cards),
  Open…, Recent (8), Examples, and a "Show tour" checkbox (checked on first launch
  only). Closing it opens the main window with the default design.
- **Main tabs:** Design · Off-design · Analytics · Compare.
- **Right panel tabs:** Results · Verification.
- **Tools menu → Isentropic ramp…** opens a separate window.
- **Exports:** geometry only (geometry DXF, CFD domain DXFs) plus results JSON/CSV and
  figure PNG/SVG/PDF as in M6. NO animation export. Every geometry/CFD export also writes
  `verification_notes.md` next to it (section E).

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
   sweep (M8), Ctrl+Z/Ctrl+Shift+Z, Ctrl+S/O/N, 1–4 main tabs.
5. Export styling: the matplotlib canvas figure matches the screen (wall hatching on the
   flow side only, same spacing feel, tight bounding box, legend bins scaled honestly
   or labelled as discrete classes).

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
   the detachment limit is a shaded no-go zone and recovery / gap update live.
   ▶ button + Space sweeps the off-design Mach (speed 0.5×/1×/2×, loop).
5. **Separation warnings (approximate).** Shock/boundary-layer incipient-separation
   check on every ramp shock and the terminal shock, using published empirical
   criteria (sources required, I confirm each). Always worded "approximate — verify
   with CFD". Phase 3b CFD (15.5 mm bubble) is quoted where it applies.
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
- Compare tab: slot A (pinned or loaded .busemann) beside slot B (built live in the
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
