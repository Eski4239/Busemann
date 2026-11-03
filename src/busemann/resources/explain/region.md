# Region {{k}} (behind ramp shock {{k}})

## Relations
<!-- SOURCE: definition used by this tool: static ratios to the freestream multiply across successive shocks -->
$$ \frac{p_k}{p_\infty} = \frac{p_{k-1}}{p_\infty}\,\left(\frac{p_2}{p_1}\right)_k $$
<!-- SOURCE: definition used by this tool: total pressure is unchanged by the isentropic flow between shocks, so the shock ratios multiply -->
$$ \frac{p_{0,k}}{p_{0\infty}} = \frac{p_{0,k-1}}{p_{0\infty}}\,\left(\frac{p_{02}}{p_{01}}\right)_k $$
<!-- SOURCE: definition used by this tool: each ramp adds its deflection to the flow direction -->
$$ \varphi_k = \varphi_{k-1} + \theta_k $$

## This case
$$ p_{ {{k}} }/p_\infty = {{region[k-1].p_ratio:.4f}} \times {{shock[k].p2_p1:.4f}} = {{sel.p_ratio:.4f}} $$
$$ T_{ {{k}} }/T_\infty = {{sel.T_ratio:.4f}},\quad M_{ {{k}} } = {{sel.M:.4f}} $$
$$ p_{0,{{k}}}/p_{0\infty} = {{region[k-1].p0_ratio:.4f}} \times {{shock[k].p0_ratio:.4f}} = {{sel.p0_ratio:.4f}} $$
$$ \varphi_{ {{k}} } = {{region[k-1].theta_deg:.2f}}\degree + {{shock[k].theta_deg:.2f}}\degree = {{sel.theta_deg:.2f}}\degree $$

## In plain words
Between two shocks the flow is uniform: it runs parallel to ramp {{k}} at {{sel.theta_deg:.2f}}° and Mach {{sel.M:.4f}}. Each shock it has crossed has raised the pressure and lowered the total pressure; the running products give the state here relative to the freestream.

## Assumptions
- Two-dimensional, steady, inviscid flow; uniform between shocks
- Calorically perfect gas (constant γ)
