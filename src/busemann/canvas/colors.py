"""Canvas colours as hex strings (no Qt), shared by the Qt scene and the matplotlib export
so the screen and an exported figure cannot diverge."""
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
