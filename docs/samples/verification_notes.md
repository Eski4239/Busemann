# Busemann verification notes

Written with: geometry DXF  
Busemann 0.1.0 (commit 6047750), 2026-11-03T23:43:41Z

## Inputs

| Input | Value |
|---|---|
| mach | 3 |
| atmosphere_mode | manual |
| altitude_m | 20000 |
| p_pa | 10000 |
| T_k | 220 |
| gamma | 1.4 |
| n_ramps | 2 |
| method | oswatitsch |
| custom_angles | — |
| capture_height_m | 0.1 |
| units | SI |
| preset | Validation case |
| off_design_mach | — |
| max_cowl_enabled | False |
| max_cowl_deg | 30 |
| cowl_wedge_deg | 0 |
| capture_mode | height |
| mdot_kgps | — |
| inlet_width_m | — |
| diffuser_recovery | 0.97 |

## Model assumptions

- Two-dimensional, steady, inviscid flow; no boundary layers or bleed.
- Calorically perfect gas (constant γ); a warning is shown when T0 makes this optimistic.
- Straight, attached oblique shocks on the weak branch; a terminal normal shock at the throat.
- Shock-on-lip design; off design the geometry is frozen.
- Not modelled: the external cowl shock and its reflections, shock merging, the subsonic diffuser; above the design Mach the recovery is an upper bound.

## Verification items

8 items: 0 errors, 3 warnings, 5 notes. Each one must be verified with a CFD solver.

### 1. Ramp shock 2: separation likely (approximate)

- Severity: Warning
- Criterion: p₂/p₁ ≥ 1 + 0.3 M₁² (2D, turbulent, M₁ ≤ 4.5); p₂/p₁ 2.818 vs incipient 2.527 (M₁ 2.256)
- Source: Korkegi, R. H., AIAA Journal 13(4), 1975, pp. 534–535 (pending user confirmation)
- Ramp shock 2 at the design point: separation likely, +11.5 % from the threshold (approximate — verify with CFD); must be verified with a CFD solver.
- Validation evidence: Phase 3b viscous CFD at this geometry: a corner separation bubble at the second ramp corner, x = 109.5–125.0 mm, 15.5 mm long (0.155 h_c), peak reverse wall shear −81.7 Pa. (docs/validation_3b.md)

### 2. Terminal normal shock: separation likely (approximate)

- Severity: Warning
- Criterion: M₁ ≥ 1.3 ahead of a normal shock (turbulent); M₁ 1.507 vs 1.3
- Source: Seddon, J. & Goldsmith, E. L., Intake Aerodynamics, 2nd ed., Blackwell, 1999 (pending user confirmation)
- Terminal normal shock at the design point: separation likely, +15.9 % from the threshold (approximate — verify with CFD); must be verified with a CFD solver.
- Validation evidence: Phase 3b: the terminal shock was not simulated; a Mach 1.5 normal shock on the turbulent duct boundary layer is likely to cause further separation losses. (docs/validation_3b.md)

### 3. Cowl lip shock attachment margin

- Severity: Warning
- Criterion: θmax(M∞) − (cowl angle + lip wedge) = +0.28° (detached below 0°, warning below 2°)
- Source: Oblique-shock θ–β–M relation, attached-shock limit (NACA Report 1135)
- Zero-thickness or wedge lip idealisation; the external cowl flow, its drag and any bow shock are not modelled; must be verified with a CFD solver.

### 4. Ramp shock 1: not applicable — no upstream boundary layer

- Severity: Note
- Criterion: Shock / boundary-layer criterion not applied: the shock starts at the sharp leading edge
- Source: — (no criterion applied)
- Ramp shock 1 at the design point: not applicable — no upstream boundary layer (approximate — verify with CFD). It starts at the sharp leading edge, where no boundary layer has grown, so the shock / boundary-layer criterion does not apply; must be verified with a CFD solver.
- Validation evidence: Phase 3b viscous CFD at this geometry: no separation on the first ramp. (docs/validation_3b.md)

### 5. Real-gas effects

- Severity: Note
- Criterion: T0 616 K vs 800 K (constant γ above it is optimistic)
- Source: Busemann model limit (engineering threshold, no published criterion cited)
- Calorically perfect gas with constant γ; vibrational excitation and dissociation are not modelled; must be verified with a CFD solver.

### 6. Recovery above the design Mach is an upper bound

- Severity: Note
- Criterion: Shock-in-duct regime (M∞ > design): cowl shock and duct reflections not modelled
- Source: Phase 3d CFD at M∞ 3.25: Mach reflection at the lip, recovery 4.9 % below the tool (docs/validation_3d.md)
- Above the design Mach the off-design recovery is an upper bound; must be verified with a CFD solver.

### 7. MIL-E-5008B comparison basis

- Severity: Note
- Criterion: η_MIL = 1 − 0.075 (M∞ − 1)^1.35 (1 < M∞ ≤ 5), 800 / (M∞⁴ + 935) (M∞ > 5), compared with the engine-face estimate (inviscid recovery × diffuser), not the inviscid value
- Source: MIL-E-5008B (1959), as given by NASA Glenn Research Center, 'Inlet Performance', https://www.grc.nasa.gov/WWW/BGH/inleth.html (formula confirmed)
- The specification line is a reference, not a model result; must be verified with a CFD solver.

### 8. Subsonic diffuser recovery is an estimate

- Severity: Note
- Criterion: Entered value 0.970 (default 0.97); Busemann does not compute the subsonic diffuser
- Source: User input (estimate)
- The engine-face recovery depends on this estimate; must be verified with a CFD solver.

## Validation summary

Repository: https://github.com/Eski4239/SuperSonic-Inlet-Designer

| Phase | Check | Result | Document |
|---|---|---|---|
| 3a | Inviscid CFD, design point (M 3, 2 ramps) | Outlet total pressure −0.35% vs the tool | docs/validation_3a.md |
| 3b | Mesh check (refined mesh vs 3a) | Reproduces 3a within 0.15% everywhere | docs/validation_3b.md |
| 3d | Off-design, below design Mach (M 2.5–3.0) | Recovery within 0.1%, mass capture within 0.4% | docs/validation_3d.md |
| 3d | Off-design, above design Mach (M 3.25) | Recovery −4.9% vs the tool | docs/validation_3d.md |

## CFD statement

All approximate results in this file (separation checks, the MIL-E-5008B comparison, the diffuser estimate, off-design values above the design Mach) and the inviscid model itself must be verified with a CFD solver before the geometry is used.
