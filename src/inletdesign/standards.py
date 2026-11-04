"""Specification references for intake performance.

MIL-E-5008B total-pressure recovery: the recovery a supersonic intake is expected to reach,
used as a comparison line for the *engine-face* recovery (inlet shocks x subsonic diffuser).
Scalars and NumPy arrays are both accepted.

# SOURCE (formula confirmed by the user, 2026-11-04): MIL-E-5008B (1959), as given by
#   NASA Glenn Research Center, "Inlet Performance",
#   https://www.grc.nasa.gov/WWW/BGH/inleth.html
"""
import numpy as np

MIL_SUPERSONIC_LIMIT = 5.0     # the (M - 1)^1.35 branch applies for 1 < M <= 5


def _validate(M):
    M = np.asarray(M, dtype=float)
    if np.any(~np.isfinite(M)) or np.any(M < 0):
        raise ValueError("Mach number must be finite and >= 0")
    return M


def mil_e_5008b(M):
    """eta_MIL = 1 (M <= 1);  1 - 0.075 (M - 1)^1.35 (1 < M <= 5);  800 / (M^4 + 935) (M > 5)."""
    M = _validate(M)
    low = 1.0 - 0.075 * np.maximum(M - 1.0, 0.0) ** 1.35
    high = 800.0 / (M**4 + 935.0)
    eta = np.where(M <= 1.0, 1.0, np.where(M <= MIL_SUPERSONIC_LIMIT, low, high))
    return float(eta) if eta.ndim == 0 else eta
