# Design method: Oswatitsch equal strength

## Relations
<!-- SOURCE: Oswatitsch, K.: Pressure Recovery for Missiles with Reaction Propulsion at High Supersonic Speeds (The Efficiency of Shock Diffusers). NACA TM 1140, 1947 (translation of the 1944 report). Not in NACA 1135 or Anderson (pending user confirmation) -->
$$ M_1 \sin\beta_1 = M_2 \sin\beta_2 = \cdots = M_n \sin\beta_n = M_n^\ast $$
<!-- SOURCE: definition used by this tool: total pressure is unchanged between shocks, so the recovery is the product of the shock ratios -->
$$ \eta = \left[\prod_{i=1}^{n} \left(\frac{p_{02}}{p_{01}}\right)_i\right] \left(\frac{p_{02}}{p_{01}}\right)_\mathrm{normal} $$

## This case
@if design.inputs.method == "oswatitsch": @each oblique: $$ M_{n,{{n}}} = {{it.M1:.4f}}\,\sin {{it.beta_deg:.2f}}\degree = {{it.Mn1:.4f}} $$
@if design.inputs.method == "custom": Custom ramp angles: the equal-strength condition is not imposed.
@if design.constrained: The optimum is limited to a cowl angle of {{design.inputs.max_cowl_angle_deg:.1f}}°, so the shock strength is the one that just meets that limit.
$$ \eta = {{design.recovery_total:.4f}}\quad(\mathrm{oblique}\;\mathrm{only}\;{{design.recovery_oblique:.4f}}) $$

## In plain words
The total-pressure loss of a shock grows very steeply with its normal Mach number (roughly with the cube of M_n − 1 for weak shocks). Splitting a compression into several shocks of equal strength therefore loses less than any uneven split: one stronger shock would cost more than the weaker ones save. Oswatitsch showed that, for a chain of oblique shocks followed by a normal shock, recovery is highest when the oblique shocks share the same normal Mach number; the tool searches that common value for the highest overall recovery, here {{design.recovery_total:.4f}}.

## Assumptions
- Two-dimensional, steady, inviscid flow
- Calorically perfect gas (constant γ)
- Shock-on-lip design: all ramp shocks meet at the cowl lip
