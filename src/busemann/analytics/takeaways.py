"""One-line takeaways under the Analytics charts (M9a), computed from the trade-study numbers
(no Qt, no hard-coded values). `optima` maps n -> (total recovery, cowl angle deg) of the
unconstrained Oswatitsch optimum at the design Mach M; theta_max is θmax(M∞) in degrees."""


def _ramps(n):
    return f"{n} ramp" if n == 1 else f"{n} ramps"


def turning_pair(n):
    """The two ramp counts the turning takeaway compares: n -> n + 1, or 3 -> 4 at n = 4
    (and 1 -> 2 for n = 0, which has no turning)."""
    if n >= 4:
        return 3, 4
    return max(n, 1), max(n, 1) + 1


def turning(M, optima, theta_max, n):
    a, b = turning_pair(n)
    (ra, ca), (rb, cb) = optima[a], optima[b]
    text = (f"At M {M:.2f}, going from {a} to {_ramps(b)} adds {rb - ra:.3f} recovery but "
            f"needs {cb - ca:.1f}° more cowl turning")
    if cb > theta_max:
        text += f" (past θmax {theta_max:.1f}°: the cowl shock detaches)"
    return text + "."


def design_mach(M, optima, n):
    r0, r4 = optima[0][0], optima[4][0]
    if n == 0:
        return f"At M {M:.2f}, a normal shock recovers {r0:.3f}; 4 ramps reach {r4:.3f}."
    r = optima[n][0]
    verb = "recovers" if n == 1 else "recover"
    text = f"At M {M:.2f}, {_ramps(n)} {verb} {r:.3f}: {r - r0:.3f} above a normal shock"
    if n < 4:
        text += f" and {r4 - r:.3f} below 4 ramps"
    return text + "."


def cowl(M, optima, theta_max, n):
    over = [k for k in sorted(optima) if k > 0 and optima[k][1] > theta_max]
    if n == 0:
        text = f"At M {M:.2f}, a normal shock needs no cowl turning"
    else:
        c = optima[n][1]
        side = (f"{theta_max - c:.1f}° inside θmax ({theta_max:.1f}°)" if c <= theta_max
                else f"{c - theta_max:.1f}° past θmax ({theta_max:.1f}°)")
        text = f"At M {M:.2f}, the {n}-ramp optimum turns {c:.1f}°, {side}"
    others = [k for k in over if k != n]
    if others:
        also = " also" if n in over else ""
        if len(others) == 1:
            text += f"; the {others[0]}-ramp optimum{also} exceeds it"
        else:
            names = ", ".join(f"{k}-" for k in others[:-1]) + f" and {others[-1]}-ramp"
            text += f"; the {names} optima{also} exceed it"
    elif n not in over:
        text += "; every ramp count up to 4 stays inside it"
    return text + "."
