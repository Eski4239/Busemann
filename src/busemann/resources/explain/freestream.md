# Freestream

## Relations
<!-- SOURCE: NACA Report 1135 (1953), eq. (2), p. 614: thermal equation of state p = rho R T -->
$$ \rho_\infty = \frac{p_\infty}{R\,T_\infty} $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (29b), p. 616: speed of sound a^2 = gamma p / rho = gamma R T -->
$$ a_\infty = \sqrt{\gamma R\,T_\infty} $$
<!-- SOURCE: NACA Report 1135 (1953), p. 616: definition of the Mach number M = V / a -->
$$ V_\infty = M_\infty\,a_\infty $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (43), p. 616: T / T_t as a function of M -->
$$ \frac{T_0}{T} = 1 + \frac{\gamma - 1}{2}\,M^2 $$
<!-- SOURCE: NACA Report 1135 (1953), eq. (44), p. 616: p / p_t as a function of M -->
$$ \frac{p_0}{p} = \left(1 + \frac{\gamma - 1}{2}\,M^2\right)^{\gamma/(\gamma - 1)} $$
<!-- SOURCE: definition used by this tool (unit Reynolds number; mu from Sutherland's law as in the U.S. Standard Atmosphere 1976) -->
$$ Re/\ell = \rho_\infty V_\infty / \mu_\infty $$

## This case
$$ \rho_\infty = \frac{ {{fs.p:.1f}} }{ {{fs.R:.2f}} \times {{fs.T:.2f}} } = {{fs.rho:.5f}}\;\mathrm{kg/m^3} $$
$$ a_\infty = \sqrt{ {{fs.gamma:.2f}} \times {{fs.R:.2f}} \times {{fs.T:.2f}} } = {{fs.a:.1f}}\;\mathrm{m/s} $$
$$ V_\infty = {{fs.M:.2f}} \times {{fs.a:.1f}} = {{fs.V:.1f}}\;\mathrm{m/s} $$
$$ T_0/T = {{fs.T0_T:.4f}},\quad T_0 = {{fs.T0:.1f}}\;\mathrm{K} $$
$$ p_0/p = {{fs.p0_p:.4f}},\quad p_0 = {{fs.p0:.0f}}\;\mathrm{Pa} $$
$$ Re/\ell = {{fs.Re_per_m:.4g}}\;\mathrm{m^{-1}} $$

## In plain words
The freestream is the undisturbed air ahead of the inlet at M∞ = {{fs.M:.2f}}. Its static pressure and temperature come from the atmosphere model (or your manual values); everything else follows from the ideal-gas law and the isentropic relations. The stagnation values are what the air would reach if brought to rest without losses: the inlet's job is to recover as much of p0 as possible.

## Assumptions
- Two-dimensional, steady, inviscid flow
- Calorically perfect gas (constant γ = {{fs.gamma:.2f}})
- Values shown in SI regardless of the unit setting
