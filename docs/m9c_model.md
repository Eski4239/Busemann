# M9c model note: inlet characteristic (recovery vs mass-flow ratio) and buzz

Status: **implemented in M9c** (`src/inletdesign/characteristic.py`, Analytics ▸ Inlet
characteristic; tests `tests/test_characteristic.py`). For a fixed design evaluated at
one freestream Mach M∞ (the design point or an off-design point of the existing model).
Revised after the source review: the references below were read in `references/`, and the
statements marked CONFIRMED were checked by the user's reviewer.

**References (all in `references/`; printed page numbers):**
- NACA Report 1135 (Ames Research Staff, 1953), *Equations, Tables, and Charts for
  Compressible Flow*.
- W. E. Moeckel, *Approximate Method for Predicting Form and Location of Detached Shock Waves
  Ahead of Plane or Axially Symmetric Bodies*, NACA TN 1921, July 1949.
- M. Sibulkin, *Theoretical and Experimental Investigation of Additive Drag*, NACA Report
  1187, 1954 (supersedes NACA RM E51B13, 1951).
- A. Ferri and L. M. Nucci, *The Origin of Aerodynamic Instability of Supersonic Inlets at
  Subcritical Conditions*, NACA RM L50K30, January 26, 1951.
- C. L. Dailey, "Supersonic Diffuser Instability", Journal of the Aeronautical Sciences,
  vol. 22, no. 11, 1955, pp. 733–749 — **PENDING** (not in `references/`; alternative only).

## Summary: what is exact and what is empirical

| Item | Status within Busemann's model | New inputs |
|---|---|---|
| 1. Critical point | **Exact** (existing shock model) | none |
| 2. Supercritical branch | **Exact quasi-1D** (area–Mach + normal shock) | diffuser exit/entry area ratio A_x/A_e; throttle (exit static pressure) |
| 3a. Subcritical recovery and mass-flow ratio while the shock stands in the last ramp region | **Exact quasi-1D** (ideal, flat branch) | same |
| 3b. Subcritical shock position vs spilled mass flow | **Approximate** (Moeckel's method: assumed hyperbolic shock, straight sonic line at a Mach-dependent angle) | none |
| 4. Buzz onset, Ferri–Nucci | **Approximate** (geometric once 3b is given; experimentally based criterion) | none |
| 4b. Buzz onset, Dailey (alternative, not recommended) | **Empirical** (needs the slope of a real characteristic) | measured slope |

Notation: region k is the flow behind ramp shock k (k = 0 freestream, k = n behind the last
ramp shock); M_n = M_pre_terminal, θ_n its flow direction (the cumulative flow angle shown
in the app's region table); η_obl = recovery behind the ramp
shocks; MFR = A0/Ac (mass-flow ratio, = mass capture of the existing model); A_e = h_t, the
duct entry (throat) height; per unit width throughout.

Standard relations (NACA Report 1135, **CONFIRMED**):
- **Area ratio**, eq. (80), p. 618, which gives A*/A as a function of M; Busemann uses its
  reciprocal A/A* = (1/M) · [ (2/(γ+1)) (1 + (γ−1)/2 · M²) ]^((γ+1)/(2(γ−1))).
  Check value: Table II, M = 3.00, A/A* = 4.235, p. 635.
- **Isentropic static/total pressure**, eq. (44), p. 616:
  p/p_t = (1 + (γ−1)/2 · M²)^(−γ/(γ−1)).
- **Normal-shock downstream Mach**, eq. (96), p. 619:
  M_y² = ((γ−1)M² + 2) / (2γM² − (γ−1)).
- **Normal-shock total-pressure ratio**, eq. (99), p. 619:
  p0y/p0x = [ (γ+1)M² / ((γ−1)M² + 2) ]^(γ/(γ−1)) · [ (γ+1) / (2γM² − (γ−1)) ]^(1/(γ−1)).
  Check value: Table II, M = 3.00, p0y/p0x = .3283, p. 635.
- Mass-flow function m̄(M) = M (1 + (γ−1)/2 · M²)^(−(γ+1)/(2(γ−1))), so that
  ṁ = p0 A m̄(M) √(γ/(R T0)); m̄(M) = m̄(1) · (A*/A)(M) (closed-form identity with eq. 80).

## 1. Critical point

- **Equations.** The existing result at M∞: the ramp shocks as computed, the terminal normal
  shock at the duct entry in region n at Mach M_n.
  η_crit = η_obl · p0y/p0x(M_n) (eq. 99);  MFR_crit = mass capture (1 at and above the design
  Mach, A0/Ac below it).
- **Assumptions.** Those of the existing model: 2D, inviscid, calorically perfect gas,
  straight attached ramp shocks, uniform regions, planar terminal shock at the entry.
- **Inputs.** The design and M∞ (nothing new).
- **Validity range.** Every M∞ where the ramp shocks are attached and M_n > 1. Above the
  design Mach the existing caveat holds (shock-in-duct, recovery an upper bound).
- **Source.** NACA 1135 eq. (99), p. 619; Busemann's existing model.
- **Exact or empirical:** exact within the model; the point the other branches must meet.

## 2. Supercritical branch

The terminal shock moves downstream into the diverging subsonic diffuser; the supersonic flow
entering at M_n accelerates further before the shock.

- **Minimal new geometry input.** The diffuser exit-to-entry area ratio AR = A_x/A_e > 1. No
  area distribution is needed: the shock position is parametrised by the area A_s where it
  stands, A_e ≤ A_s ≤ A_x. The throttle variable is the exit static pressure p_x/p0∞
  (equivalently the exit Mach M_x); it fixes A_s.
- **Equations.**
  1. Sonic area of the supersonic entry flow: A*₁ = A_e · (A*/A)(M_n)  (eq. 80).
  2. Shock Mach: (A/A*)(M_s) = A_s / A*₁, supersonic root (M_s ≥ M_n).
  3. Behind the shock, at fixed ṁ and T0, A* ∝ 1/p0: A*₂ = A*₁ / (p0y/p0x)(M_s)  (eq. 99).
  4. Subsonic exit Mach M_x from (A/A*)(M_x) = A_x / A*₂ = AR · (A/A*)(M_n) · (p0y/p0x)(M_s),
     subsonic root.
  5. Exit pressure: p_x/p0∞ = η_obl · (p0y/p0x)(M_s) · (p/p_t)(M_x)  (eq. 44).
  6. Recovery η = η_obl · (p0y/p0x)(M_s); MFR = MFR_crit (the inlet is started; the capture
     is set upstream).
  Sweep A_s from A_e (critical: M_s = M_n, η = η_crit) to A_x (maximum supercritical); p_x
  falls monotonically along the branch.
- **Assumptions.** Quasi-one-dimensional, uniform entry flow at M_n (true at and above design
  where the whole capture passes region n; below design it is the region-n flow that enters),
  isentropic diffuser except the normal shock, planar shock, no boundary layer
  (shock–boundary-layer interaction, which dominates real supercritical losses, ignored).
- **Inputs.** AR, the throttle p_x/p0∞ (or M_x), γ, the existing design result.
- **Validity range.** M_n > 1; A_x/A*₂ ≥ 1 (otherwise the exit chokes: the branch ends);
  A_s ≤ A_x. Recovery is an upper bound (no viscous loss).
- **Source.** NACA 1135 eqs. (80), p. 618; (44), p. 616; (99), p. 619.
- **Exact or empirical:** exact quasi-1D; the chart labels it "quasi-1D".

## 3. Subcritical branch

The exit pressure rises above its critical value: the normal shock is expelled ahead of the
lip and the subsonic flow behind it spills around the lip, so MFR drops.

### 3a. Recovery and mass-flow ratio (exact quasi-1D)

- **Which region the shock stands in.** First in region n, between the last ramp shock and the
  lip, normal to θ_n near the dividing streamline. The entering flow therefore crosses a normal
  shock at M_n: η = η_obl · (p0y/p0x)(M_n) = η_crit (the ideal, flat branch).
- **Mass-flow ratio vs back-pressure.** The duct is no longer choked; the throttle sets the
  exit Mach: (p/p_t)(M_x) = p_x / (η_crit · p0∞), and
  MFR = MFR_crit · m̄(M_x) / m̄(M_x,crit),
  where M_x,crit is the exit Mach at the critical point (item 2 with A_s = A_e). MFR decreases
  monotonically as p_x rises.
- **Source.** NACA 1135 eqs. (44), (80), (99).

### 3b. Shock position vs spilled mass flow (Moeckel's method, approximate)

Moeckel's method as written (TN 1921), then its application to a ramp inlet.

- **Assumptions (TN 1921, Summary, p. 1; restated on pp. 2, 21):**
  1. the shock between its foremost point and its sonic point is a hyperbola asymptotic to the
     free-stream Mach lines;
  2. the sonic line between the shock and the body is **straight and inclined at an angle
     that depends only on the free-stream Mach number** (not a line drawn from the lip to an
     arbitrary point of the shock).
- **Equations (plane flow), in the report's symbols (symbol list, pp. 3–4; CONFIRMED):**
  M₀ the free-stream Mach number, β = √(M₀² − 1), x the coordinate in the stream direction
  (measured from the intersection of the asymptotes), y normal to it, φ the local inclination
  of the detached shock relative to the x-axis, η the angle between the sonic line and the
  normal to the free-stream direction, λ the angle of a streamline relative to the x-axis
  (λ_d: wedge half-angle for detachment; λ_S: at the shock sonic point), S the shock sonic
  point, SB the body sonic point, τ the fraction of the maximum possible inlet mass flow that
  passes outside the cowl.
  - Shock form, eq. (4), p. 7: β y = √(x² − x₀²) (x₀: vertex to asymptote intersection).
    Shock slope, eq. (5), p. 7: tan φ = x / (β √(x² − x₀²)) = √(x₀² + β² y²) / (β² y).
  - Shock sonic point, eqs. (6)/(6a), p. 8: φ_S is the shock angle at which the flow behind
    the shock is sonic (oblique-shock theory at M₀); from eq. (5),
    y_S = x₀ / (β √(β² tan² φ_S − 1)).
  - Sonic-line inclination (angle between the sonic line and the normal to the upstream flow),
    eq. (17), p. 11 (CONFIRMED): η = ½ (λ_d + λ_S), the mean of the flow inclinations at the
    two ends, with λ_d the wedge half-angle for detachment and λ_S the flow inclination behind
    the shock at S. Both depend only on M₀. Because the two differ only slightly, Moeckel then
    takes, for plane flow, **η = λ_S** (p. 11, CONFIRMED), and uses it in the inlet relations
    (eq. 34).
  - Continuity on the sonic line, eq. (14), p. 10: the mass flow crossing the sonic line at
    sonic speed equals the free-stream mass flow of the stream tube it carries, with the total
    pressure taken on the mass-centroid streamline (plane flow: entering the shock at
    y_c = y_S/2 for a closed body, p. 9), i.e. B ≡ A_s/A₀ = (A*/A)(M₀) · p₀ / p_s,c, with
    p_s,c/p₀ the oblique-shock total-pressure ratio at the centroid's shock angle (eq. 5).
- **Two-dimensional inlets with spillage (TN 1921, pp. 17–20):**
  - The hyperbolic part of the shock starts on the dividing streamline (free-stream position
    y_m) (p. 17); for a sharp cowl lip the body sonic point SB is at the lip (p. 18).
  - Spillage, eq. (30), p. 18: τ = 1 − y_m / y_SB; τ is the report's "fraction of maximum
    possible inlet mass flow that passes outside cowl" (symbol list, p. 4). Moeckel applies the
    method to inlet spillage himself, eqs. (30)–(36), pp. 18–19.
  - Shock referred to the dividing streamline, eqs. (31)–(32), pp. 18–19:
    β (y − y_m) = √(x² − x₀²), with x₀ = β (y_S − y_m) √(β² tan² φ_S − 1).
  - Continuity, eq. (34), p. 19: A_s/A₀ = (y_S − y_SB) / ((y_S − y_m) cos λ_S) = B, so
    eq. (35), p. 19: y_S / y_SB = (1 − (y_m/y_SB) B cos λ_S) / (1 − B cos λ_S).
  - Shock location, eqs. (33)/(36), p. 19: the distance L from the vertex of the shock to the
    lip follows from x_S (eq. 6a), the straight sonic line from S to SB at λ_S
    (x_SB = x_S + (y_S − y_SB) tan λ_S, eq. 11) and L = x_SB − x₀ (eq. 10). Moeckel concludes
    (p. 20) that the distance of the shock from the inlet lip increases linearly with the air
    that passes outside the inlet; figure 12 (p. 32) gives shock location and additive drag
    vs spillage at M₀ = 2.0.
- **Further precedent for inlet spillage at reduced mass-flow ratio:** Sibulkin, NACA Report 1187,
  p. 6 ("the theory of reference 3", Moeckel TN 1921, predicts a linear variation of
  additive drag with mass-flow ratio) and p. 7 (the bow-wave position L/y = K(1 − m/m_max),
  "based upon a derivation in reference 3").
- **Application to Busemann's 2D ramp inlet (Busemann extension, ACCEPTED):**
  - **Rule:** the expelled shock stands in region n (behind the last ramp shock) instead of the
    free stream, so every Moeckel quantity referenced to the free stream uses the region-n state
    instead: the Mach number (M₀ → M_n, β = √(M_n² − 1)), the Mach-line asymptotes (at the
    region-n Mach angle μ_n), and η = λ_S(M_n), measured from the region-n flow direction θ_n.
  - **Citation:** "Moeckel, NACA TN 1921 (1949), eqs. (4), (6)/(6a), (14), (17), (30)–(36),
    pp. 7–19, applied to the flow behind the last ramp shock (Busemann extension)".
  - x along θ_n, y normal to θ_n measured from the last ramp segment (parallel to θ_n), which
    takes the role of Moeckel's symmetry axis (an inviscid wall is a symmetry plane).
  - y_SB = the lip's distance from the last ramp segment, normal to θ_n (sharp lip = SB,
    p. 18); y_m = y_SB (1 − τ), with τ = 1 − MFR/MFR_crit from item 3a.
  - Below the dividing streamline the shock is taken normal to θ_n (x = x₀, 0 ≤ y ≤ y_m):
    Moeckel's analysis "is independent of the nature of the shock below this origin" (p. 18).
  - Output: the shock vertex distance L(τ) ahead of the lip and the hyperbola, which item 4
    intersects with ramp shock n.
- **Validity range (M9c.1).** TN 1921 p. 14, exact words: "The theoretical values
  obtained by the present method are not expected to be valid near M0 = 1.0, because the
  subsonic field becomes very large relative to the body (yS/ySB → ∞) and small variations
  in the assumed form and inclination of the sonic line have a large effect on the computed
  drag. Equation (24) becomes indeterminate for M0 = 1 because cos η, B, and k are all unity
  for sonic free-stream velocity." Also p. 1 (Summary: "except … for free-stream Mach numbers
  close to 1.0") and p. 22 ("The method also fails in the vicinity of sonic free-stream
  velocity"). The report gives no number. The lowest two-dimensional Mach number at which
  it compares the method with experiment is M 1.2 (fig. 7, p. 29, reference 5, read from
  the figure).
  - **Limit (user-confirmed):** by the region-n rule it applies to M_n: **M_n ≥ 1.2**
    (`MOECKEL_MIN_MACH`). Below it the expelled shock, the subcritical branch and the buzz
    onset are not computed; the chart shades the subcritical side "outside the method's
    validity (flow behind the last ramp near Mach 1, Moeckel TN 1921 p. 14)" and the
    takeaway says the stable range is not computed.
  - **Validation design:** M_n = 1.2 at **M∞ = 2.572**, so the band shows for
    2.39 < M∞ < 2.572 (at M∞ ≈ 2.39, M_n reaches 1 and the characteristic is not defined).
  - Best when the sonic line has little curvature (p. 15). Busemann's extension: the shock
    must stay in region n (until it meets ramp shock n).
- **Exact or empirical:** approximate (labelled "approximate").

## 4. Buzz onset

### 4a. Ferri–Nucci criterion (to implement)

- **Statements used (RM L50K30, CONFIRMED):**
  - Summary, p. 1: "the buzz starts when this vortex sheet [originating at a shock
    intersection] is at the lip of the cowling"; "When the flow on the central body is
    unseparated, the vortex sheet moves from outside the cowling inward as the entering flow
    is reduced, and the fluctuations start when the sheet enters the inlet." Concluding
    Remarks, p. 25, restate this.
  - p. 7, finding 2 (CONFIRMED): the stable volume-flow regulation "was a minimum (zero) when the conical
    shock was at the lip of the cowling", and "increased … as the conical shock became farther
    removed from the cowling lip". Concluding Remarks, p. 25: the minimum stable entering
    volume flow is a function of the cowling-position parameter.
- **Equations (geometric).** With the subcritical shock from item 3b, the triple point T is
  the intersection of the expelled shock (the Moeckel hyperbola, in region n) with ramp shock
  n. The vortex sheet leaves T along the direction at which the flows on its two sides have
  equal pressure: below T the flow crossed ramp shock n and then the expelled shock; above T it
  crosses only the expelled shock, in region n − 1 flow. That direction comes from a
  triple-point (shock-polar) solution within the shock model; the simplest approximation is
  the region-n flow direction θ_n. **Buzz onset** is the largest spillage τ (smallest MFR) at
  which the sheet still passes outside the lip; fluctuations start once it passes below the
  lip, i.e. enters the cowl.
- **Qualitative check (from p. 7, finding 2):** at the design point the ramp shocks focus on
  the lip, so T forms just below and ahead of the lip and the sheet (about along θ_n,
  shallower than shock n) passes inside the lip at once: **almost no stable range for on-lip
  operation**, as Ferri & Nucci found with the conical shock at the lip. Below the design Mach
  the ramp shocks lie ahead of the lip and a finite stable range appears, growing as they move
  further ahead. A test asserts both trends.
- **Second mechanism, NOT modelled (Summary, p. 1; Concluding Remarks, p. 25):** with
  boundary-layer separation on the compression surface a lambda shock forms and gives a second
  vortex sheet inside the inlet; fluctuations start when it approaches the inner cowl surface,
  and "the stable range of regulation of entering volume flow was less than for the previous
  case". p. 7 (CONFIRMED; summarising the tests of their references 1–4): "stable
  subcritical conditions were obtained only for very small entering-flow reductions when
  separation was present on the central body". Busemann does not model it. Shown
  automatically when the existing separation check (`inletdesign.separation`) flags any ramp
  shock for the design:
  - a line under the characteristic chart: "If the ramp boundary layer separates (the
    separation check flags it for this design), the real stable range is likely smaller than
    shown (Ferri & Nucci, RM L50K30).";
  - a Verification item (warning, category "buzz"): "Ramp separation reduces the buzz margin
    (approximate)", source "Ferri & Nucci, NACA RM L50K30 (1951), p. 7 and Concluding
    Remarks pp. 25–26; tests on conical inlets, M 1.9–2.7. Applying it to a 2D multi-ramp
    inlet is a Busemann extension." (+ "Extrapolated beyond the tested Mach range." for
    M∞ > 2.7).
- **Validity range and labels.**
  - Ferri & Nucci tested nose (conical, axisymmetric) inlets at M 1.90–2.70 (Summary, p. 1;
    p. 7, finding 1; p. 26). Buzz results at **M∞ > 2.7** are labelled "extrapolated beyond
    the tested range".
  - Applying the criterion to a 2D multi-ramp inlet (triple point on the last ramp shock) is
    **Busemann's extension** of the criterion, stated as such in the chart label and the
    Verification item.
- **Exact or empirical:** approximate (an experimentally established criterion applied to
  the approximate shock position of 3b).

### 4b. Dailey criterion (alternative, not recommended)

- **Statement.** The inlet–duct system becomes dynamically unstable where the slope of the
  subcritical characteristic, dη/dMFR, turns positive.
- **Source.** Dailey 1955 (PENDING, not in `references/`).
- **Why not.** The ideal subcritical branch of 3a is flat (dη/dMFR = 0), so the slope
  criterion is indeterminate within this model; it would need an empirical, viscous
  characteristic.

### Recommendation

**Ferri–Nucci**: it uses the model's own shock geometry plus one approximate ingredient (the
Moeckel standoff), gives a definite onset, can be drawn on the canvas, and is the mechanism
Ferri & Nucci confirmed experimentally; their p. 7 finding (zero stable range with the shock at
the lip) is a direct qualitative check of what the model predicts.

## 5. What the chart would show

- For the current design at the off-design slider Mach.
- **Axes:** x = mass-flow ratio A0/Ac; y = total-pressure recovery p0/p0∞.
- **Branches:** the supercritical vertical branch (MFR = MFR_crit), labelled "quasi-1D"; the
  critical point (ring marker); the subcritical branch, labelled "(approximate)"; beyond the
  buzz onset the branch dashed and shaded "buzz (approximate)".
- **Buzz marker:** a vertical line "buzz onset (Ferri–Nucci, approximate)"; with
  "extrapolated beyond the tested range" for M∞ > 2.7 and "2D multi-ramp: Busemann's
  extension of the criterion" in its tooltip.
- **Separation line** (only when flagged): the Ferri & Nucci sentence in 4a.
- **Hover:** throttle p_x/p0∞, M_s (supercritical) or the standoff L/y_SB (subcritical), η, MFR.
- **Takeaway (computed):** the stable subcritical range in MFR and the supercritical recovery
  loss at maximum throttle.

## 6. Tests that would validate it

- **Limits.** At A_s = A_e the supercritical branch equals the critical point (η and MFR,
  exact); at A_s = A_x it is the maximum supercritical point; as p_x → p_x,crit from above the
  subcritical MFR → MFR_crit; at τ = 0 the Moeckel shock vertex sits at the critical position
  (L from eq. 36 with y_m = y_SB).
- **Continuity.** Both branches meet at the critical point: η, MFR and p_x continuous.
- **Monotonicity.** η decreases along the supercritical branch with A_s; MFR decreases with
  p_x on the subcritical branch; L grows linearly with τ (TN 1921, p. 20).
- **Conservation.** Mass flow equal at entry, shock and exit (quasi-1D); Moeckel's continuity
  eq. (34) satisfied by the computed y_S.
- **Closed-form cross-checks.** Area ratio against NACA 1135 Table II (A/A* = 4.235 at
  M = 3.00, p. 635); p0y/p0x = .3283 at M = 3.00 (p. 635); m̄(M)·(A/A*)(M) constant.
- **Comparisons with the cited reports:**
  - Moeckel figure 12 (p. 32): 2D-inlet shock location vs spillage at M₀ = 2.0, applied with
    region n replaced by a free stream at M 2.0 (a flat-plate "ramp" of zero angle) —
    values to be digitised and confirmed by the user before use.
  - Ferri & Nucci p. 7, finding 2 (qualitative): zero stable range with the shock on the lip;
    the stable range grows as the shocks move ahead of the lip (lower M∞ for a fixed design).
  - Ferri & Nucci minimum-stable-flow data (figs. 25–62) are for conical inlets; a
    quantitative comparison would need an axisymmetric version and is not proposed.

## New inputs this would need

1. Subsonic diffuser exit-to-entry area ratio A_x/A_e (Design ▸ Advanced; a spin box, range to
   be agreed, e.g. 1.0–4.0).
2. A throttle definition for the chart's parameter: the exit static pressure p_x/p0∞ (swept
   automatically over the characteristic; no user input needed unless an operating point is
   wanted).

## Results for the validation design (M 3.0 design, 2 ramps; diffuser area ratio 2)

| M∞ | M_n | τ_b exact | A0/Ac at onset, exact | τ_b θ_n fallback | A0/Ac, fallback |
|---|---|---|---|---|---|
| 2.5 | 1.130 | not computed: M_n below 1.2 (outside the method's validity) | | | |
| 2.6 | 1.224 | 0.0540 | 0.7728 | 0.0580 | 0.7696 |
| 2.75 | 1.342 | 0.0461 | 0.8459 | 0.0559 | 0.8373 |
| 3.0 (on-lip) | 1.507 | 0 | 1.0000 | 0 | 1.0000 |

- At M 3.0 the strong–strong shock polars do not intersect (one strong shock from region 1
  gives a lower pressure than the two-shock path through region 2), so the exact triple
  point has no solution and the θ_n fallback is used; both give a zero stable range,
  consistent with Ferri & Nucci p. 7, finding 2.
- The stable range ΔMFR = MFR_crit τ_b grows from 0 at the design point to about 0.044 near
  M 2.6–2.7 as the shocks move ahead of the lip (Ferri & Nucci's trend). Below M∞ 2.572
  (M_n < 1.2) it is no longer computed (validity limit above); before M9c.1 it appeared to
  shrink there, an artefact of the method near Mach 1. The tests check the trend from the
  design point down to M 2.75.

