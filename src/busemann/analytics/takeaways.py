"""One-line takeaways under the Analytics charts (M9a), computed from the trade-study numbers
(no Qt, no hard-coded values). `optima` maps n -> (total recovery, cowl angle deg) of the
unconstrained Oswatitsch optimum at the design Mach M; theta_max is θmax(M∞) in degrees."""


def _ramps(n):
    return f"{n} ramp" if n == 1 else f"{n} ramps"


def turning_base(n):
    """The ramp count the turning takeaway starts from (a normal shock has no turning)."""
    return min(max(n, 1), 4)


def _join(items):
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" and {items[-1]}"


def turning(M, optima, theta_max, n, equal_turn):
    """Equal-turning comparison first, then the unconstrained optima.

    equal_turn: {"rec": {m: recovery of the m-ramp optimum limited to the base design's cowl
    turn, for m > base}, "iso": isentropic recovery at that turn}."""
    base = turning_base(n)
    r_b, c_b = optima[base]
    more = [m for m in sorted(equal_turn["rec"]) if m > base]
    text = f"At the same {c_b:.1f}° cowl turn as {_ramps(base)} ({r_b:.3f}), "
    if more:
        give = [f"{_ramps(m)} {'gives' if m == 1 else 'give'} {equal_turn['rec'][m]:.3f}"
                if k == 0 else f"{_ramps(m)} {equal_turn['rec'][m]:.3f}"
                for k, m in enumerate(more)]
        text += _join(give) + f"; an isentropic ramp gives {equal_turn['iso']:.3f}."
    else:
        text += f"an isentropic ramp gives {equal_turn['iso']:.3f}."
    shown = more or [base]
    turns = [f"{optima[m][1]:.1f}°" for m in shown]
    if len(shown) == 1:
        text += f" Unconstrained, the {shown[0]}-ramp optimum turns {turns[0]}"
    else:
        text += f" Unconstrained, {_join([str(m) for m in shown])} ramps turn {_join(turns)}"
    past = [m for m in shown if optima[m][1] > theta_max]
    if len(past) == len(shown):
        text += f", past θmax ({theta_max:.1f}°), so the cowl shock detaches."
    elif past:
        text += (f"; {_join([str(m) for m in past])} {'ramp' if past == [1] else 'ramps'} "
                 f"{'passes' if len(past) == 1 else 'pass'} θmax ({theta_max:.1f}°), so "
                 "its cowl shock detaches." if len(past) == 1 else
                 f"; {_join([str(m) for m in past])} ramps pass θmax ({theta_max:.1f}°), so "
                 "their cowl shocks detach.")
    else:
        text += f", inside θmax ({theta_max:.1f}°)."
    return text


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


# --- drag (M9b): rich text, C<sub>D,…</sub> --------------------------------------------------
CD_ADD = "C<sub>D,add</sub>"
CD_COWL = "C<sub>D,cowl</sub>"


def drag_vs_mach(M_design, machs, cd_add, cowl_at_design):
    """cowl_at_design: C_D,cowl at the design Mach, or None (not computable)."""
    below = [(M, a) for M, a in zip(machs, cd_add)
             if a is not None and M < M_design - 1e-9 and a > 0.0]
    if below:
        M_peak, a_peak = max(below, key=lambda t: t[1])
        text = (f"Below the design Mach, spillage adds up to {CD_ADD} {a_peak:.3f} "
                f"(M {M_peak:.2f}); at M {M_design:.2f} it is 0")
    else:
        text = f"No spillage in this range, so {CD_ADD} is 0"
    if cowl_at_design is None:
        return text + (", and the cowl shock is detached there, so the cowl drag is not "
                       "computable.")
    return text + f" and the cowl adds {CD_COWL} {cowl_at_design:.3f}."


def recovery_vs_cowl(M, n, recovery, cd, matches):
    """matches: {m: C_D,cowl at which m ramps (m > base) reach the same recovery}; values
    may be None (that turn detaches the cowl shock)."""
    base = turning_base(n)
    if cd is None:
        text = (f"At M {M:.2f}, the {base}-ramp optimum ({recovery:.3f}) detaches the cowl "
                "shock, so its cowl drag is not computable")
    else:
        text = f"At M {M:.2f}, {_ramps(base)} recover{'s' if base == 1 else ''} " \
               f"{recovery:.3f} for {CD_COWL} {cd:.3f}"
    parts = [f"{_ramps(m)} at {CD_COWL} {v:.3f}" for m, v in sorted(matches.items())
             if v is not None]
    if parts:
        return text + "; the same recovery costs " + _join(parts) + "."
    return text + ("." if base == 4 else "; no other ramp count reaches it with an attached "
                   "cowl shock.")
