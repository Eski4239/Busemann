# Cowl lip at M∞ {{off.M_inf:.2f}}

## Relations
<!-- SOURCE: definition used by this tool: the flow reaching the lip is the region containing the lip; its direction phi_lip is already turned by the ramp shocks it has crossed -->
$$ \theta_\mathrm{req} = \max(0,\;\theta_\mathrm{cowl} - \varphi_\mathrm{lip}) + \delta_\mathrm{wedge} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (168), p. 624, with theta_max from eq. (139a), p. 621, evaluated at the lip Mach -->
$$ \mathrm{margin} = \theta_\mathrm{max}(M_\mathrm{lip}) - \theta_\mathrm{req} $$

## This case
The lip lies in region {{off.cowl_lip_region}} (0 = freestream), where M = {{off.lip_mach:.4f}} and the flow direction is {{off.lip_flow_angle_deg:.2f}}°.
$$ \theta_\mathrm{req} = \max(0,\;{{design.cowl_angle_deg:.2f}}\degree - {{off.lip_flow_angle_deg:.2f}}\degree) + {{off.cowl_wedge_deg:.2f}}\degree = {{off.cowl_required_turn_deg:.2f}}\degree $$
@if off.cowl_margin_deg != None: $$ \mathrm{margin} = {{off.theta_max_lip_deg:.2f}}\degree - {{off.cowl_required_turn_deg:.2f}}\degree = {{off.cowl_margin_deg:+.2f}}\degree $$
@if off.cowl_margin_deg == None: The flow at the lip is subsonic (M = {{off.lip_mach:.4f}}): no shock forms there, so there is no margin to compute.

## In plain words
@if off.cowl_lip_region > 0: Below the design Mach the ramp shocks cross the cowl line ahead of the lip, so the lip sits in flow that the ramps have already turned. With a zero-thickness lip that flow is already aligned with the cowl and needs no turning; a lip wedge of {{off.cowl_wedge_deg:.2f}}° still has to be turned.
@if off.cowl_lip_region == 0: At and above the design Mach the ramp shocks reach or pass inside the lip, so the lip meets undisturbed freestream on both faces and must turn it by the full cowl angle plus the wedge.
@if off.regime == "shock-in-duct": {{cfd_lip_note}}
A negative margin means the cowl shock detaches: a bow shock stands ahead of the lip, which this model does not compute.

## Assumptions
- Two-dimensional, steady, inviscid flow
- Calorically perfect gas (constant γ)
- Sharp lip; wedge = outer-surface angle (0° = zero-thickness idealisation)
