# supersonic-inlet-designer

An open-source Python tool for designing 2D external-compression supersonic inlets (Mach 2-6) from compressible-flow theory, with relations verified against [NACA Report 1135, "Equations, Tables, and Charts for Compressible Flow"](https://ntrs.nasa.gov/citations/19930091059) (NASA NTRS) and later validated against Fluent CFD results.

A local copy of NACA 1135 is kept in `references/` for development but is gitignored (not committed) — use the NTRS link above to obtain it.

## Roadmap

- **Phase 0 — Scaffolding**: project structure, function stubs, test skeletons, tooling (this phase).
- **Phase 1 — Compressible flow relations**: implement and verify isentropic, normal shock, oblique shock, and Prandtl-Meyer relations against NACA 1135.
- **Phase 2 — Inlet geometry and design logic**: compose the flow relations into 2D external-compression inlet design (ramp angles, shock-on-lip conditions, geometry export).
- **Phase 3 — CFD validation**: validate designed inlet geometries against Fluent simulations.

## Setup (Windows)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e .
pip install -r requirements.txt
pytest
```

### Running tests

Plain `pytest` runs a fast local default: the physics/CLI core plus the GUI tests that check
program correctness (threading, undo, file round-trips, validated numbers). GUI tests that only
check what a user sees immediately (label text, pixel geometry, styling) are marked
`@pytest.mark.ui` and skipped locally by default, same as the `perf`-marked timing tests. To run
everything, matching CI:

```powershell
pytest -m "not perf"   # everything except timing-sensitive perf tests
pytest -m ""            # literally everything
```

## Quick start

After `pip install -e .`, the `inletdesign` command is available on the PATH (inside the venv).

Design a single inlet (M=3, 2 ramps) and write a schematic, a DXF, and a JSON summary:

```powershell
inletdesign design --mach 3.0 --ramps 2 --out results/m3_2r
```

This prints a table of ramp/shock angles, per-region Mach number and pressure recovery to the
terminal, and writes `results/m3_2r.png`, `results/m3_2r.dxf`, and `results/m3_2r.json`. The PNG
is a light, technical line drawing of the inlet (ramp, cowl, shocks, Mach labels per region), for
example:

![example inlet design](results/m3_2r.png)

Sweep optimum pressure recovery against freestream Mach number for several ramp counts:

```powershell
inletdesign curve --ramps 0 1 2 3 --mach-min 1.5 --mach-max 4.0 --step 0.1 --out results/curve
```

This writes `results/curve.csv` (one row per feasible Mach/ramp-count combination) and
`results/curve.png` (recovery vs. M∞, one line per ramp count).
