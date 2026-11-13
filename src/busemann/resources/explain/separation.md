# Separation (approximate)

## Relations
<!-- SOURCE: Korkegi, R. H., AIAA Journal 13(4), 1975, pp. 534–535 (original not consulted; widely cited correlation) -->
$$ \frac{p_{is}}{p_1} = 1 + 0.3\,M_1^2 \qquad (M_1 \leq 4.5) $$
<!-- SOURCE: Seddon, J. & Goldsmith, E. L., Intake Aerodynamics, 2nd ed., 1999 (original not consulted; widely cited correlation) -->
$$ M_1 \geq 1.3 \quad \mathrm{(normal\ shock)} $$

## This case
@each sep_lines: {{it}}

## In plain words
A shock thickens the boundary layer under it, and a strong enough shock makes it separate from the wall. These two empirical limits say when that starts for a turbulent boundary layer: the pressure rise across a ramp shock (from the second ramp on, since the first starts at the sharp leading edge with no boundary layer ahead of it) and the Mach number ahead of the terminal normal shock. They are a warning, not a prediction: a viscous CFD run is needed to know the size of any separated region.

## Assumptions
- Fully turbulent, adiabatic-wall boundary layer at a high Reynolds number
- Two-dimensional interaction (compression corner or incident shock)
- The incipient-separation limit only: the size of a separated region is not predicted
