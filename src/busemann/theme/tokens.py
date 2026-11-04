"""Design tokens (spec section 5). The only place colours, spacing and type sizes are defined."""

COLORS = {
    "bg": "#F6F7F9",          # window background
    "surface": "#FFFFFF",     # panels, canvas
    "border": "#E2E5EA",      # 1 px dividers
    "text": "#111827",        # primary text
    "text_muted": "#6B7280",  # labels, units
    "accent": "#2563EB",      # selection, sliders, active tab, links
    "shock": "#D97706",       # shock lines
    "wall": "#374151",        # ramps / cowl
    "ok": "#059669",
    "warn": "#D97706",
    "error": "#DC2626",
}

SPACING = 8          # px grid unit
RADIUS = 6           # px, maximum corner radius
BORDER = 1           # px

FONT_UI = "Inter"
FONT_MONO = "JetBrains Mono"
FONT_UI_FALLBACK = "Segoe UI"
FONT_MONO_FALLBACK = "Consolas"

SIZE_BASE = 13       # px
SIZE_LABEL = 11      # px, uppercase labels
LABEL_TRACKING_EM = 0.06
SIZE_KPI = 22        # px

LEFT_PANEL_WIDTH = 300
RIGHT_PANEL_WIDTH = 320
MIN_WINDOW = (1280, 800)

DEBOUNCE_MS = 30
OFFDESIGN_STRIP_H = 440   # px, chart strip under the off-design canvas (when expanded)


def space(n=1):
    """n grid units in px."""
    return n * SPACING


# --- inlet canvas ---------------------------------------------------------------------
# Diverging Mach map at M = 1, low saturation so amber shocks and grey walls stay legible.
# Subsonic: warm sand, lightest next to M = 1 (index 0) and darker away from it.
# Supersonic: light -> darker blue with Mach (interpolated across the supersonic bins).
MACH_SUBSONIC = ("#F7F0E5", "#E6D2B5")   # CIEDE2000 9.6 apart (test: >= 8)
MACH_SUPERSONIC = ("#E9F0F8", "#D3E1F1", "#BCD0E9", "#A4BFE0", "#8DAED7")
# Off-design canvas (M8.2): continuous, higher-contrast diverging map at M = 1.
# Subsonic stops from M = 1 down to the low end; supersonic stops from M = 1 up to the top.
MACH_CONTINUOUS_SUB = ("#FDDBC7", "#E58267", "#B2182B")
MACH_CONTINUOUS_SUPER = ("#D1E5F0", "#92C5DE", "#4393C3", "#2166AC", "#0B3A75")
MACH_CONTINUOUS_LO = 0.3     # bottom of the off-design colour scale
REGION_BORDER_DARKER = 112   # QColor.darker() factor for the 1 px region outline
LEGEND_INSET_PX = 16
LEGEND_ALPHA = 0.9
CANVAS_FILL = 0.85           # fit: drawing fills 85% of the limiting viewport dimension
REGION_ALPHA = 0.9
CANVAS_ANIM_MS = 150
HOVER_PICK_PX = 6        # shock pick distance, screen px
SHADOW_ALPHA = 28        # hover card shadow (0-255), subtle
