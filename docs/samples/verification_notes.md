# Busemann verification notes

Written with: geometry DXF  
Busemann 1.0.0 (commit release), 2026-11-13T14:20:58Z

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
| cowl_frontal_height | 0.1 |
| diffuser_area_ratio | 2 |

## Model assumptions

- Two-dimensional, steady, inviscid flow; no boundary layers or bleed.
- Calorically perfect gas (constant γ); a warning is shown when T0 makes this optimistic.
- Straight, attached oblique shocks on the weak branch; a terminal normal shock at the throat.
- Shock-on-lip design; off design the geometry is frozen.
- Not modelled: the external cowl shock and its reflections, shock merging, the subsonic diffuser; above the design Mach the recovery is an upper bound.

## Verification items

11 items: 0 errors, 4 warnings, 7 notes. Each one must be verified with a CFD solver.

### 1. Ramp shock 2: separation likely (approximate)

- Severity: Warning
- Criterion: p₂/p₁ ≥ 1 + 0.3 M₁² (2D, turbulent, M₁ ≤ 4.5); p₂/p₁ 2.818 vs incipient 2.527 (M₁ 2.256)
- Source: Korkegi, R. H., AIAA Journal 13(4), 1975, pp. 534–535 (original not consulted; widely cited correlation)
- Ramp shock 2 at the design point: separation likely, +11.5 % from the threshold (approximate — verify with CFD); must be verified with a CFD solver.
- Validation evidence: The validation CFD (viscous) at this geometry: a corner separation bubble at the second ramp corner, x = 109.5–125.0 mm, 15.5 mm long (0.155 of the capture height), peak reverse wall shear −81.7 Pa.

### 2. Terminal normal shock: separation likely (approximate)

- Severity: Warning
- Criterion: M₁ ≥ 1.3 ahead of a normal shock (turbulent); M₁ 1.507 vs 1.3
- Source: Seddon, J. & Goldsmith, E. L., Intake Aerodynamics, 2nd ed., Blackwell, 1999 (original not consulted; widely cited correlation)
- Terminal normal shock at the design point: separation likely, +15.9 % from the threshold (approximate — verify with CFD); must be verified with a CFD solver.
- Validation evidence: The validation CFD did not simulate the terminal shock; a Mach 1.5 normal shock on the turbulent duct boundary layer is likely to cause further separation losses.

### 3. Cowl lip shock attachment margin

- Severity: Warning
- Criterion: θmax(M∞) − (cowl angle + lip wedge) = +0.28° (detached below 0°, warning below 2°)
- Source: Oblique-shock θ–β–M relation, attached-shock limit (NACA Report 1135)
- Zero-thickness or wedge lip idealisation; the external cowl flow, its drag and any bow shock are not modelled; must be verified with a CFD solver.

### 4. Ramp separation reduces the buzz margin (approximate)

- Severity: Warning
- Criterion: Separation check flags ramp shock 2 (approximate, see the separation items)
- Source: Ferri & Nucci, NACA RM L50K30 (1951), p. 7 and Concluding Remarks pp. 25–26; tests on conical inlets, M 1.9–2.7. Applying it to a 2D multi-ramp inlet is a Busemann extension. Extrapolated beyond the tested Mach range.
- The separation check flags a ramp shock for this design. In tests of external-compression inlets, separation on the compression surface allowed stable subcritical operation only for very small reductions in mass flow, so this inlet is likely to buzz soon after it starts spilling flow. Verify with CFD or wind-tunnel data.

### 5. Ramp shock 1: not applicable — no upstream boundary layer

- Severity: Note
- Criterion: Shock / boundary-layer criterion not applied: the shock starts at the sharp leading edge
- Source: — (no criterion applied)
- Ramp shock 1 at the design point: not applicable — no upstream boundary layer (approximate — verify with CFD). It starts at the sharp leading edge, where no boundary layer has grown, so the shock / boundary-layer criterion does not apply; must be verified with a CFD solver.
- Validation evidence: The validation CFD (viscous) at this geometry: no separation on the first ramp.

### 6. Real-gas effects

- Severity: Note
- Criterion: T0 616 K vs 800 K (constant γ above it is optimistic)
- Source: Busemann model limit (engineering threshold, no published criterion cited)
- Calorically perfect gas with constant γ; vibrational excitation and dissociation are not modelled; must be verified with a CFD solver.

### 7. Recovery above the design Mach is an upper bound

- Severity: Note
- Criterion: Shock-in-duct regime (M∞ > design): cowl shock and duct reflections not modelled
- Source: The validation CFD at M∞ 3.25: Mach reflection at the lip, recovery 4.9 % below the tool
- Above the design Mach the off-design recovery is an upper bound; must be verified with a CFD solver.

### 8. MIL-E-5008B comparison basis

- Severity: Note
- Criterion: η_MIL = 1 − 0.075 (M∞ − 1)^1.35 (1 < M∞ ≤ 5), 800 / (M∞⁴ + 935) (M∞ > 5), compared with the engine-face estimate (inviscid recovery × diffuser), not the inviscid value
- Source: MIL-E-5008B (1959), as given by NASA Glenn Research Center, 'Inlet Performance', https://www.grc.nasa.gov/WWW/BGH/inleth.html (formula confirmed)
- The specification line is a reference, not a model result; must be verified with a CFD solver.

### 9. Subsonic diffuser recovery is an estimate

- Severity: Note
- Criterion: Entered value 0.970 (default 0.97); Busemann does not compute the subsonic diffuser
- Source: User input (estimate)
- The engine-face recovery depends on this estimate; must be verified with a CFD solver.

### 10. Drag is an inviscid pressure-drag estimate

- Severity: Note
- Criterion: Additive drag: (p − p∞) along the dividing streamline from the free stream to the lip; cowl drag: the oblique-shock pressure on the cowl's outer face over a frontal height of 0.10 × capture height; coefficients on q∞ × capture height
- Source: Additive drag: M. Sibulkin, 'Theoretical and Experimental Investigation of Additive Drag', NACA Report 1187 (1954), eq. (5)/(5a), p. 2 (change in total momentum of the entering stream tube; p. 3, the equivalent pressure integral); the report treats axisymmetric inlets, applied here per unit width in 2D. Cowl pressure drag: Busemann model choice (oblique-shock relations, NACA Report 1135)
- It excludes skin friction, subcritical spillage (terminal shock expelled), the cowl beyond its frontal height and 3D effects; must be verified with a CFD solver.

### 11. Inlet characteristic and buzz onset are approximate

- Severity: Note
- Criterion: Supercritical branch quasi-1D (diffuser exit/entry area ratio 2.00); expelled-shock position by Moeckel's method in the flow behind the last ramp shock; buzz onset when the vortex sheet from the shock intersection enters the cowl
- Source: NACA Report 1135 eqs. (44), (80), (99); Moeckel, NACA TN 1921 (1949), eqs. (4), (6)/(6a), (14), (17), (30)–(36), pp. 7–19, applied to the flow behind the last ramp shock (Busemann extension); Ferri & Nucci, NACA RM L50K30 (1951), Summary p. 1, p. 7 and Concluding Remarks p. 25 (conical inlets, M 1.9–2.7; 2D multi-ramp application is a Busemann extension)
- The ideal subcritical branch is flat and ignores viscous losses; the buzz onset is an estimate; must be verified with a CFD solver.

## Validation summary

How it was checked: every relation in the solver follows NACA Report 1135, and an automated test suite of over 1,000 tests checks the results against closed-form values. The designs were also compared with 2D CFD simulations in Ansys Fluent (density-based solver, inviscid and k-ω SST viscous runs, with a mesh-refinement check). At the design point the total-pressure recovery agreed within 0.35%, and below the design Mach within 0.1%, with mass capture within 0.4%. With boundary layers included, recovery was about 2% lower, mainly because of a separation bubble at the second ramp corner, which Busemann's separation warning flags. Above the design Mach the CFD showed a Mach reflection at the cowl lip that this model does not include, so recovery there is an upper bound (the CFD was 4.9% lower at Mach 3.25).

Repository: https://github.com/Eski4239/Busemann

## CFD statement

All approximate results in this file (separation checks, the MIL-E-5008B comparison, the diffuser estimate, off-design values above the design Mach) and the inviscid model itself must be verified with a CFD solver before the geometry is used.
