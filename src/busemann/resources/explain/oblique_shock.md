# Ramp shock {{k}}

## Relations
<!-- SOURCE: NACA Report 1135 (1953), p. 621, 'Useful relations' paragraph ('Because an oblique shock wave acts as a normal shock...'): the normal component is M₁ sin β; NACA writes θ for the shock angle, our β -->
$$ M_{n1} = M_1 \sin\beta $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (139a), p. 621, with NACA's θ (shock angle) written β and δ (deflection) written θ -->
$$ \tan\theta = 2\cot\beta\;\frac{M_1^2 \sin^2\beta - 1}{M_1^2(\gamma + \cos 2\beta) + 2} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (128), p. 621 -->
$$ \frac{p_2}{p_1} = \frac{2\gamma M_1^2 \sin^2\beta - (\gamma - 1)}{\gamma + 1} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (96), p. 619, applied to the normal components as stated on p. 621 -->
$$ M_{n2}^2 = \frac{(\gamma - 1) M_{n1}^2 + 2}{2\gamma M_{n1}^2 - (\gamma - 1)} $$
<!-- SOURCE: NACA Report 1135 (1953), p. 621, 'Useful relations' paragraph ('Because an oblique shock wave acts as a normal shock...'): downstream normal component M₂ sin(β − θ) -->
$$ M_2 = \frac{M_{n2}}{\sin(\beta - \theta)} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (99), p. 619, with M₁ replaced by M₁ sin β (p. 621) -->
$$ \frac{p_{02}}{p_{01}} = \left[\frac{(\gamma + 1) M_{n1}^2}{(\gamma - 1) M_{n1}^2 + 2}\right]^{\frac{\gamma}{\gamma - 1}} \left[\frac{\gamma + 1}{2\gamma M_{n1}^2 - (\gamma - 1)}\right]^{\frac{1}{\gamma - 1}} $$

## This case
$$ M_{n1} = {{sel.M1:.4f}}\,\sin {{sel.beta_deg:.2f}}\degree = {{sel.Mn1:.4f}} $$
$$ \theta = {{sel.theta_deg:.2f}}\degree \;\Rightarrow\; \beta = {{sel.beta_deg:.2f}}\degree\;\;(M_1 = {{sel.M1:.4f}}) $$
$$ p_2/p_1 = {{sel.p2_p1:.4f}},\quad T_2/T_1 = {{sel.T2_T1:.4f}},\quad \rho_2/\rho_1 = {{sel.rho2_rho1:.4f}} $$
$$ M_2 = \frac{ {{sel.Mn2:.4f}} }{ \sin({{sel.beta_deg:.2f}}\degree - {{sel.theta_deg:.2f}}\degree) } = {{sel.M2:.4f}} $$
$$ p_{02}/p_{01} = {{sel.p0_ratio:.4f}}\quad(\mathrm{loss}\;{{sel.p0_loss:.4f}}) $$

## In plain words
Ramp {{k}} turns the flow by θ = {{sel.theta_deg:.2f}}°, and the flow answers with a straight oblique shock at β = {{sel.beta_deg:.2f}}° to the oncoming stream. Only the velocity component normal to the shock is slowed down, so the shock behaves like a normal shock of Mach {{sel.Mn1:.4f}}. That weak normal Mach number is why the loss is small: total pressure drops only by a factor {{sel.p0_ratio:.4f}}. Of the two mathematical solutions for β, the weak one is used, as observed on attached ramp shocks.

## Assumptions
- Two-dimensional, steady, inviscid flow; straight attached shock (weak branch)
- Calorically perfect gas (constant γ)
- Uniform flow on each side of the shock
