"""Approximate shock / turbulent boundary-layer incipient-separation checks.

Empirical criteria only: they flag where an inviscid design is likely to separate, they do
not predict separation. Every result must be verified with a CFD solver (viscous, turbulent).
Scalars and NumPy arrays are both accepted by the threshold functions.

Criteria (the originals could not be obtained: both are cited as widely used correlations,
original not consulted):

# SOURCE (original not consulted; widely cited correlation): R. H. Korkegi, "Comparison of Shock-Induced Two- and
#   Three-Dimensional Incipient Turbulent Separation", AIAA Journal, Vol. 13, No. 4,
#   April 1975, pp. 534-535. Two-dimensional (compression corner / incident shock)
#   correlation for a turbulent boundary layer at the incipient-separation pressure ratio:
#   p_is / p1 = 1 + 0.3 M1^2  for M1 <= 4.5. Constants recalled from memory. The paper's
#   separate fit above M1 = 4.5 is deliberately NOT encoded (not recalled reliably), so
#   M1 > 4.5 returns "outside the criterion's range" instead of a verdict. A correlation for
#   fully turbulent, adiabatic-wall, high-Reynolds-number flow. Applied to ramp shocks k >= 2
#   only: ramp shock 1 starts at the sharp leading edge, with no upstream boundary layer.
# SOURCE (original not consulted; widely cited correlation): normal shock on a turbulent boundary layer separates
#   incipiently for an upstream Mach number of about 1.3 (classic intake value), e.g.
#   J. Seddon, E. L. Goldsmith, "Intake Aerodynamics", 2nd ed., Blackwell Science, Oxford,
#   1999, chapter on shock / boundary-layer interaction (chapter and page to be confirmed).
"""
from dataclasses import dataclass

import numpy as np

KORKEGI_2D_MAX_MACH = 4.5
NORMAL_SHOCK_INCIPIENT_MACH = 1.3

KORKEGI_CRITERION = "p₂/p₁ ≥ 1 + 0.3 M₁² (2D, turbulent, M₁ ≤ 4.5)"
NOT_CONSULTED = "(original not consulted; widely cited correlation)"
KORKEGI_SOURCE = f"Korkegi, R. H., AIAA Journal 13(4), 1975, pp. 534–535 {NOT_CONSULTED}"
NORMAL_CRITERION = "M₁ ≥ 1.3 ahead of a normal shock (turbulent)"
NORMAL_SOURCE = ("Seddon, J. & Goldsmith, E. L., Intake Aerodynamics, 2nd ed., Blackwell, "
                 f"1999 {NOT_CONSULTED}")
KORKEGI_SCOPE = "correlation for fully turbulent, adiabatic-wall, high-Reynolds-number flow"
WORDING = "approximate — verify with CFD"


def _validate(M):
    M = np.asarray(M, dtype=float)
    if np.any(~np.isfinite(M)) or np.any(M <= 1.0):
        raise ValueError("upstream Mach number must be finite and > 1")
    return M


def korkegi_2d_threshold(M1):
    """p_is/p1 = 1 + 0.3 M1^2  (incipient turbulent separation, 2D, M1 <= 4.5)."""
    M1 = _validate(M1)
    out = 1.0 + 0.3 * M1**2
    return float(out) if out.ndim == 0 else out


@dataclass(frozen=True)
class SeparationCheck:
    shock: str           # "ramp shock 1" ... "terminal normal shock"
    kind: str            # "oblique" | "normal"
    M1: float
    value: float         # compared quantity: p2/p1 (oblique) or M1 (normal)
    threshold: float     # value at incipient separation; None: no verdict
    ratio: float         # value / threshold; >= 1 flags; None: no verdict
    flagged: bool
    in_range: bool       # False: outside the criterion's range, no verdict
    criterion: str
    source: str
    note: str = None     # extra caveat (outside the range, not applicable, ...)
    applicable: bool = True   # False: the criterion does not apply (no verdict, no margin)

    @property
    def margin(self):
        """Fraction above (+) or below (-) the threshold (None without a verdict)."""
        return None if self.ratio is None else self.ratio - 1.0


NOT_APPLICABLE = "not applicable — no upstream boundary layer"


def not_applicable(name, M1, p2_p1):
    """The leading-edge ramp shock: it starts at the sharp leading edge, where no boundary
    layer has grown, so a shock / boundary-layer criterion does not apply."""
    return SeparationCheck(name, "oblique", float(M1), float(p2_p1), None, None, False, True,
                           KORKEGI_CRITERION, KORKEGI_SOURCE,
                           "It starts at the sharp leading edge, where no boundary layer has "
                           "grown, so the shock / boundary-layer criterion does not apply.",
                           applicable=False)


def check_oblique(name, M1, p2_p1):
    """Korkegi 2D check of one ramp shock k >= 2 (p2/p1 across it, M1 ahead of it)."""
    if M1 > KORKEGI_2D_MAX_MACH:
        return SeparationCheck(name, "oblique", float(M1), float(p2_p1), None,
                               None, False, False, KORKEGI_CRITERION, KORKEGI_SOURCE,
                               f"M₁ = {M1:.2f} is outside the criterion's range "
                               f"(M₁ ≤ {KORKEGI_2D_MAX_MACH:g}); no verdict.")
    threshold = korkegi_2d_threshold(M1)
    ratio = float(p2_p1) / threshold
    return SeparationCheck(name, "oblique", float(M1), float(p2_p1), threshold, ratio,
                           ratio >= 1.0, True, KORKEGI_CRITERION, KORKEGI_SOURCE)


def check_normal(name, M1):
    """Normal-shock check: flagged for M1 >= 1.3."""
    ratio = float(M1) / NORMAL_SHOCK_INCIPIENT_MACH
    return SeparationCheck(name, "normal", float(M1), float(M1), NORMAL_SHOCK_INCIPIENT_MACH,
                           ratio, ratio >= 1.0, True, NORMAL_CRITERION, NORMAL_SOURCE)


def check_shocks(shock_states):
    """One SeparationCheck per shock (objects with name, kind, M1, p2_p1), in order."""
    out = []
    for k, s in enumerate(shock_states):
        if s.kind == "normal":
            out.append(check_normal(s.name, s.M1))
        else:
            check = not_applicable if k == 0 else check_oblique      # ramp 1: leading edge
            out.append(check(s.name, s.M1, s.p2_p1))
    return tuple(out)
