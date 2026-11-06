# M9c model note: inlet characteristic (recovery vs mass-flow ratio) and buzz

Status: **model proposal only — nothing here is implemented.** For a fixed design evaluated at
one freestream Mach M∞ (the design point or an off-design point of the existing model).
Sources marked **PENDING** must be confirmed before any value is treated as ground truth
(CLAUDE.md source rule).

**Reference availability.** `references/` contains only NACA Report 1135. The other reports
cited below — Sibulkin NACA Report 1187, Ferri & Nucci NACA RM L50K30, Moeckel NACA TN 1921 —
are **not present**, so their equation and page numbers are PENDING. NACA 1135 equation
numbers below were read from the PDF's OCR text, which is garbled; they are marked
"(to confirm)".

## Summary: what is exact and what is empirical

| Item | Status within Busemann's model | New inputs |
|---|---|---|
| 1. Critical point | **Exact** (existing shock model) | none |
| 2. Supercritical branch | **Exact quasi-1D** (area–Mach + normal shock) | diffuser exit/entry area ratio A_x/A_e; throttle (exit static pressure) |
| 3a. Subcritical recovery and mass-flow ratio while the shock stands in the last ramp region | **Exact quasi-1D** (ideal, flat branch) | same |
| 3b. Subcritical shock standoff vs spilled mass flow | **Approximate** (Moeckel's method: assumed shock shape and sonic line) | none |
| 4a. Buzz onset, Ferri–Nucci | **Approximate**: geometry exact once 3b is given; the slip-line direction needs a triple-point solution (exact within the shock model) or the simple "along the local flow" approximation | none |
| 4b. Buzz onset, Dailey | **Empirical**: needs the slope of a real (viscous) subcritical characteristic | measured or empirical slope |

Notation: region k is the flow behind ramp shock k (k = 0 freestream, k = n behind the last
ramp shock); M_n = M_pre_terminal; η_obl = recovery behind the ramp shocks; MFR = A0/Ac
(mass-flow ratio, = mass capture of the existing model); h_t = duct entry (throat) height;
per unit width throughout.

Standard relations used (NACA Report 1135, *Equations, Tables, and Charts for Compressible
Flow*, Ames Research Staff, 1953):
- Area–Mach (isentropic, one-dimensional), eq. (80), p. 618 (to confirm):
  A/A* = (1/M) · [ (2/(γ+1)) (1 + (γ−1)/2 · M²) ]^((γ+1)/(2(γ−1)))
  Check value: Table II, M = 3.00, A/A* = 4.235, p. 635.
- Normal-shock total-pressure ratio, eq. (99), p. 619 (to confirm):
  p0y/p0x = [ (γ+1)M² / ((γ−1)M² + 2) ]^(γ/(γ−1)) · [ (γ+1) / (2γM² − (γ−1)) ]^(1/(γ−1))
  Check value: Table II, M = 3.00, p0y/p0x = .3283, p. 635.
- Normal-shock downstream Mach, M_y² = ((γ−1)M² + 2) / (2γM² − (γ−1)), NACA 1135
  normal-shock relations, pp. 618–619 (equation number to confirm).
- Isentropic static/total pressure, p/p0 = (1 + (γ−1)/2 · M²)^(−γ/(γ−1)), NACA 1135 eq. (44),
  p. 616 (to confirm).
- Mass-flow function m̄(M) = M (1 + (γ−1)/2 · M²)^(−(γ+1)/(2(γ−1))), so that
  ṁ = p0 A m̄(M) √(γ/(R T0)). This follows from the same isentropic relations (closed-form
  identity: m̄(M) ∝ 1/(A/A*)).

## 1. Critical point

- **Equations.** The existing result at M∞: the ramp shocks as computed, the terminal normal
  shock at the duct entry in region n at Mach M_n.
  η_crit = η_obl · p0y/p0x(M_n);  MFR_crit = mass capture (1 at and above the design Mach,
  A0/Ac below it).
- **Assumptions.** Those of the existing model: 2D, inviscid, calorically perfect gas,
  straight attached ramp shocks, uniform regions, planar terminal shock at the entry.
- **Inputs.** The design and M∞ (nothing new).
- **Validity range.** Every M∞ where the ramp shocks are attached and M_n > 1. Above the
  design Mach the existing caveat holds (shock-in-duct, recovery an upper bound).
- **Source.** NACA 1135 eq. (99), p. 619 (to confirm); Busemann's existing model.
- **Exact or empirical:** exact within the model; it is the point the other branches must meet.

## 2. Supercritical branch

The terminal shock moves downstream into the diverging subsonic diffuser; the supersonic flow
entering at M_n accelerates further before the shock.

- **Minimal new geometry input.** The diffuser exit-to-entry area ratio
  AR = A_x / A_e > 1 (A_e = h_t). No area distribution is needed: the shock position is
  parametrised by the area A_s where it stands, A_e ≤ A_s ≤ A_x. The throttle variable is the
  exit static pressure p_x/p0∞ (equivalently the exit Mach M_x); it fixes A_s.
- **Equations.**
  1. Sonic area of the supersonic entry flow: A*₁ = A_e / (A/A*)(M_n).
  2. Shock Mach: (A/A*)(M_s) = A_s / A*₁, supersonic root (M_s ≥ M_n).
  3. Behind the shock, at fixed ṁ and T0, A* ∝ 1/p0: A*₂ = A*₁ / (p0y/p0x)(M_s).
  4. Subsonic exit Mach M_x from (A/A*)(M_x) = A_x / A*₂ = AR · (A/A*)(M_n) · (p0y/p0x)(M_s),
     subsonic root.
  5. Exit pressure: p_x/p0∞ = η_obl · (p0y/p0x)(M_s) · (p/p0)(M_x).
  6. Recovery η = η_obl · (p0y/p0x)(M_s); MFR = MFR_crit (unchanged: the inlet is started and
     the capture is set upstream).
  Sweep A_s from A_e (critical: M_s = M_n, η = η_crit) to A_x (maximum supercritical); p_x
  falls monotonically along the branch.
- **Assumptions.** Quasi-one-dimensional, uniform entry flow at M_n (true at and above design
  where the whole capture passes region n; below design it is the region-n flow that enters),
  isentropic diffuser except the normal shock, planar shock, no boundary layer
  (shock-boundary-layer interaction, which dominates real supercritical losses, ignored).
- **Inputs.** AR, the throttle p_x/p0∞ (or M_x), γ, the existing design result.
- **Validity range.** M_n > 1; A_x/A*₂ ≥ 1 (otherwise the exit chokes: the branch ends);
  A_s ≤ A_x. Recovery is an upper bound (no viscous loss).
- **Source.** NACA 1135 eqs. (80), (99) and the isentropic p/p0, pp. 616–619 (to confirm).
- **Exact or empirical:** exact quasi-1D; the chart labels it "quasi-1D".

## 3. Subcritical branch

The exit pressure rises above its critical value: the normal shock is expelled ahead of the
lip and the subsonic flow behind it spills around the lip, so MFR drops.

- **Which region the shock stands in.** First in region n (between the last ramp shock and
  the lip), normal to the region-n flow direction φ_n. While it stays there the flow it
  processes has Mach M_n, so the recovery of the entering flow is unchanged.
- **Equations (3a, exact quasi-1D).**
  η = η_obl · (p0y/p0x)(M_n) = η_crit (the ideal, flat branch).
  The duct is no longer choked; the throttle sets the exit Mach:
  (p/p0)(M_x) = p_x / (η_crit · p0∞), and
  MFR = MFR_crit · m̄(M_x) / m̄(M_x,crit),
  where M_x,crit is the exit Mach at the critical point (item 2, A_s = A_e).
  MFR decreases monotonically as p_x rises.
- **Shock position vs back-pressure (3b, approximate).** Spilled mass per unit width:
  ṁ_spill = (MFR_crit − MFR) · ρ∞ V∞ h_c. Following Moeckel's method, the spilled flow
  passes a straight sonic line from the lip to the shock; with the sonic state behind a
  normal shock at M_n, ṁ_spill = ρ* a* · L_s, where ρ* a* follows from p0₂ = η_crit p0∞ and T0
  (ρ*a* = ρ0 a0 (2/(γ+1))^((γ+1)/(2(γ−1)))). The sonic-line length L_s and the shock shape
  (Moeckel: a hyperbola asymptotic to the Mach lines of the upstream flow) then give the
  standoff x_s of the shock ahead of the lip.
- **Beyond region n.** When x_s reaches the crossing of the last ramp shock with the shock
  line, the expelled shock also stands in region n − 1 above a triple point; the recovery of
  part of the entering flow drops and the flow becomes unsteady (item 4). This model stops at
  the buzz-onset point.
- **Assumptions.** As item 2 for the duct; for 3b, Moeckel's assumptions: a single detached
  shock of assumed shape, a straight sonic line, the spill passing that line.
- **Inputs.** AR and the throttle (as item 2); no further geometry.
- **Validity range.** From the critical point to buzz onset; MFR between the buzz value and
  MFR_crit. Viscous effects (separation at the shock foot on the ramp) would tilt the real
  branch; the ideal one is flat.
- **Source.** W. E. Moeckel, "Approximate Method for Predicting Form and Location of Detached
  Shock Waves Ahead of Plane or Axially Symmetric Bodies", NACA TN 1921, 1949 — **PENDING**
  (not in `references/`; the method, equations and pages to be checked). Quasi-1D part: NACA
  1135 as in item 2.
- **Exact or empirical:** 3a exact quasi-1D; 3b approximate (labelled "approximate").

## 4. Buzz onset

### 4a. Ferri–Nucci criterion (recommended)

- **Statement.** Buzz starts when the vortex sheet (slip line) springing from the intersection
  of the expelled normal shock with a ramp shock enters the cowl.
- **Equations (geometric).** With the subcritical standoff x_s (item 3b) and the expelled
  shock line normal to φ_n through it, the triple point T is its intersection with ramp shock
  n (or k, if it has moved further). The slip line leaves T in the direction θ_s at which the
  two sides have equal pressure: below T the flow has passed ramp shock n and the normal shock
  (direction φ_n); above T it passes only the strong part of the expelled shock in region n − 1
  flow. θ_s comes from a shock-polar triple-point solution (computable within the shock
  model), or, as the simplest approximation, θ_s ≈ φ_n. Buzz onset is the first MFR at which
  y_slip(x_lip) < y_lip, i.e. the slip line passes below the lip, into the duct.
- **A consequence to note.** At the design point the ramp shocks focus on the lip, so T sits on
  shock n just below and ahead of the lip, and a slip line at about φ_n (shallower than the
  shock) passes below the lip at once: within this straight-shock model Ferri–Nucci predicts
  buzz at the first spillage for on-lip operation. Below the design Mach (the ramp shocks
  cross the cowl line ahead of the lip) the criterion gives a finite stable subcritical range.
- **Assumptions.** Those of item 3b for x_s; straight shocks; the instability mechanism is
  the vortex sheet's entry (Ferri & Nucci's experimental finding).
- **Inputs.** None beyond item 3.
- **Validity range.** Subcritical operation; external-compression inlets with oblique ramp
  shocks (the configuration Ferri & Nucci tested).
- **Source.** A. Ferri and L. M. Nucci, "The Origin of Aerodynamic Instability of Supersonic
  Inlets at Subcritical Conditions", NACA RM L50K30, 1951 — **PENDING** (not in
  `references/`; criterion statement, figures and pages to be checked).

### 4b. Dailey criterion (alternative)

- **Statement.** The inlet–duct system becomes dynamically unstable (buzz) where the slope
  of the subcritical characteristic, dη/dMFR, becomes positive (recovery falling as the mass
  flow falls).
- **Source.** C. L. Dailey, "Supersonic Diffuser Instability", Journal of the Aeronautical
  Sciences, vol. 22, no. 11, 1955, pp. 733–749 — **PENDING** (not in `references/`).
- **Why not as the primary criterion.** The ideal subcritical branch of item 3a is flat
  (dη/dMFR = 0), so Dailey's slope criterion is indeterminate within this model; it needs a
  real characteristic including viscous losses, i.e. empirical data.

### Recommendation

**Ferri–Nucci**: it uses quantities the model already has (the ramp-shock geometry and the
region states) plus one approximate ingredient (the Moeckel standoff), it can be drawn and
explained on the canvas, and it gives a definite onset point. Dailey would only report
"indeterminate" without empirical slope data. Both would be labelled "approximate", and the
on-lip consequence above stated next to the marker.

## 5. What the chart would show

- A new Analytics view (or an off-design chart), for the current design at the off-design
  slider Mach.
- **Axes:** x = mass-flow ratio A0/Ac; y = total-pressure recovery p0/p0∞ (and the engine-face
  estimate as in the existing charts, if wanted).
- **Branches:** the supercritical vertical branch (MFR = MFR_crit, η from η_crit down to the
  maximum-supercritical value), labelled "quasi-1D"; the critical point (ring marker); the
  subcritical branch (η = η_crit, MFR decreasing), labelled "(approximate)"; beyond the buzz
  onset the subcritical branch dashed and shaded "buzz (approximate)".
- **Buzz marker:** a vertical line at the Ferri–Nucci onset MFR, "buzz onset (Ferri–Nucci,
  approximate)".
- **Hover:** throttle p_x/p0∞, M_s (supercritical) or the standoff x_s/h_c (subcritical), η, MFR.
- **Takeaway (computed):** for example the stable subcritical range in MFR and the
  supercritical recovery loss at maximum throttle.

## 6. Tests that would validate it

- **Limits.** At A_s = A_e the supercritical branch equals the critical point (η and MFR,
  exact); at A_s = A_x it is the maximum supercritical point; as p_x → p_x,crit from above the
  subcritical MFR → MFR_crit.
- **Continuity.** Both branches meet at the critical point: η, MFR and p_x continuous.
- **Monotonicity.** η decreases along the supercritical branch with A_s; MFR decreases with
  p_x on the subcritical branch; the standoff x_s grows with the spilled mass.
- **Conservation.** Mass flow equal at the entry, the shock and the exit (quasi-1D); the
  p0 ratio across the shock equals NACA 1135 eq. (99).
- **Closed-form cross-checks.** Area–Mach against NACA 1135 Table II (A/A* = 4.235 at
  M = 3.00, p. 635); normal shock p0y/p0x = .3283 at M = 3.00 (p. 635).
- **Identity.** m̄(M) · (A/A*)(M) is constant (closed-form).
- **Comparison with the cited experiments** — PENDING until the reports are in
  `references/`: Ferri & Nucci's measured buzz-onset mass-flow ratios (RM L50K30) and
  Moeckel's measured shock standoff distances (TN 1921), with the case geometries taken from
  the reports.

## New inputs this would need

1. Subsonic diffuser exit-to-entry area ratio A_x/A_e (Design ▸ Advanced; a spin box, range
   to be agreed, e.g. 1.0–4.0).
2. A throttle definition for the chart's parameter: the exit static pressure p_x/p0∞ (swept
   automatically over the characteristic; no user input needed unless an operating point is
   wanted).
