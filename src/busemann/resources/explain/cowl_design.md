# Cowl lip (design point)

## Relations
<!-- SOURCE: NACA Report 1135 (1953), eq. (168), p. 624: shock angle for maximum stream deflection; theta_max follows from eq. (139a), p. 621 -->
$$ \theta_\mathrm{max}(M) = \theta(\beta^*, M),\quad \sin^2\beta^* = \frac{1}{4\gamma M^2}\left[(\gamma + 1) M^2 - 4 + \sqrt{(\gamma + 1)\left((\gamma + 1) M^4 + 8(\gamma - 1) M^2 + 16\right)}\right] $$
<!-- SOURCE: definition used by this tool: the cowl's outer surface turns the freestream by the cowl angle plus the lip wedge; the external cowl shock detaches when this exceeds theta_max -->
$$ \mathrm{margin} = \theta_\mathrm{max}(M_\infty) - (\theta_\mathrm{cowl} + \delta_\mathrm{wedge}) $$

## This case
$$ \mathrm{margin} = {{design.theta_max_freestream_deg:.2f}}\degree - ({{design.cowl_angle_deg:.2f}}\degree + {{design.inputs.cowl_wedge_deg:.2f}}\degree) = {{design.cowl_margin_deg:+.2f}}\degree $$
@if design.cowl_margin_deg < 0: The cowl turns the flow more than θ_max: the external cowl shock is detached (a bow shock stands ahead of the lip; spillage and cowl drag are not modelled).
@if design.cowl_margin_deg >= 0: The external cowl shock is attached, with {{design.cowl_margin_deg:.2f}}° to spare.

## In plain words
At the design point the ramp shocks meet at the lip, so the cowl's outer surface sees undisturbed freestream at M∞ = {{design.inputs.M:.2f}}. It must turn that flow by the cowl angle ({{design.cowl_angle_deg:.2f}}°) plus the lip's wedge angle ({{design.inputs.cowl_wedge_deg:.2f}}°). An attached oblique shock can turn the flow by at most θ_max = {{design.theta_max_freestream_deg:.2f}}°; beyond that the shock detaches. The margin shows how close the design is to that limit.

## Assumptions
- Two-dimensional, steady, inviscid flow
- Calorically perfect gas (constant γ)
- Sharp lip; the wedge is the outer-surface angle (0° = zero-thickness idealisation)
