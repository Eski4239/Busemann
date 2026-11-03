# Terminal normal shock

## Relations
<!-- SOURCE: NACA Report 1135 (1953), eq. (93), p. 619 -->
$$ \frac{p_2}{p_1} = \frac{2\gamma M_1^2 - (\gamma - 1)}{\gamma + 1} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (95), p. 619 -->
$$ \frac{T_2}{T_1} = \frac{\left[2\gamma M_1^2 - (\gamma - 1)\right]\left[(\gamma - 1) M_1^2 + 2\right]}{(\gamma + 1)^2 M_1^2} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (96), p. 619 -->
$$ M_2^2 = \frac{(\gamma - 1) M_1^2 + 2}{2\gamma M_1^2 - (\gamma - 1)} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (99), p. 619 -->
$$ \frac{p_{02}}{p_{01}} = \left[\frac{(\gamma + 1) M_1^2}{(\gamma - 1) M_1^2 + 2}\right]^{\frac{\gamma}{\gamma - 1}} \left[\frac{\gamma + 1}{2\gamma M_1^2 - (\gamma - 1)}\right]^{\frac{1}{\gamma - 1}} $$

## This case
$$ M_1 = {{sel.M1:.4f}} \;\Rightarrow\; M_2 = {{sel.M2:.4f}} $$
$$ p_2/p_1 = {{sel.p2_p1:.4f}},\quad T_2/T_1 = {{sel.T2_T1:.4f}} $$
$$ p_{02}/p_{01} = {{sel.p0_ratio:.4f}}\quad(\mathrm{loss}\;{{sel.p0_loss:.4f}}) $$

## In plain words
After the ramp shocks the flow is still supersonic (M = {{sel.M1:.4f}}). The terminal normal shock at the throat makes it subsonic (M = {{sel.M2:.4f}}) so it can enter the diffuser. A normal shock is the strongest possible shock for its Mach number, which is why the ramps first slow the flow down: the closer M1 is to 1, the smaller this loss.

## Assumptions
- One-dimensional, steady, inviscid flow through the shock
- Calorically perfect gas (constant γ)
- Shock positioned at the throat (terminal shock stable at the cowl lip)
