"""Canvas colours as hex strings (no Qt), used by the Qt scene and the tests."""
import colorsys

from ..theme import tokens


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _hex(rgb):
    return "#" + "".join(f"{round(min(max(c, 0.0), 1.0) * 255):02x}" for c in rgb)


def mix(a, b, f):
    """Linear blend of two hex colours (f = 0 -> a, 1 -> b)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex(tuple(x + (y - x) * f for x, y in zip(ra, rb)))


def darker(hex_color, factor=tokens.REGION_BORDER_DARKER):
    """Like QColor.darker(factor): HSV value divided by factor/100."""
    h, s, v = colorsys.rgb_to_hsv(*_rgb(hex_color))
    return _hex(colorsys.hsv_to_rgb(h, s, v * 100.0 / factor))


def bin_colors(edges):
    """One hex colour per Mach bin: sand below M = 1 (lightest next to sonic), blues above."""
    sub = [i for i in range(len(edges) - 1) if edges[i + 1] <= 1.0 + 1e-12]
    sup = [i for i in range(len(edges) - 1) if i not in sub]
    out = [None] * (len(edges) - 1)
    for rank, i in enumerate(reversed(sub)):            # rank 0 = just below M = 1
        out[i] = tokens.MACH_SUBSONIC[min(rank, len(tokens.MACH_SUBSONIC) - 1)].lower()
    stops = tokens.MACH_SUPERSONIC
    for rank, i in enumerate(sup):
        x = (rank / (len(sup) - 1) if len(sup) > 1 else 0.0) * (len(stops) - 1)
        k = min(int(x), len(stops) - 2)
        out[i] = mix(stops[k], stops[k + 1], x - k)
    return out


def _ramp(stops, t):
    t = min(max(t, 0.0), 1.0) * (len(stops) - 1)
    k = min(int(t), len(stops) - 2)
    return mix(stops[k], stops[k + 1], t - k)


def ramp(stops, t):
    """Linear colour ramp across `stops` (hex strings), t in [0, 1] clamped at the ends."""
    return _ramp(stops, t)


def continuous(M, lo, hi):
    """Off-design canvas fill: continuous diverging map with the break at M = 1 (sub: from
    MACH_CONTINUOUS_SUB[0] at M = 1 to [-1] at lo; super: [0] at M = 1 to [-1] at hi)."""
    if M <= 1.0:
        return _ramp(tokens.MACH_CONTINUOUS_SUB, (1.0 - M) / max(1.0 - lo, 1e-9))
    return _ramp(tokens.MACH_CONTINUOUS_SUPER, (M - 1.0) / max(hi - 1.0, 1e-9))
