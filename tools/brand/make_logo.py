"""Writes the logo SVG variants into the current folder (run tools/brand/render_pngs.js afterwards)."""
NAVY="#1E293B"; SHOCK="#D97706"; ACC="#2563EB"
UP='M7,8 C22,9 34,15 44,22 L59,22 L59,15 C46,10 30,5 7,4 Z'
LO='M7,56 C22,55 34,49 44,42 L59,42 L59,49 C46,54 30,59 7,60 Z'
def svg(fg=NAVY, shock=SHOCK, waves=True, tile=None, wave_op=.55, chev_w=3.6):
    t=f'<rect width="64" height="64" rx="14" fill="{tile}"/>' if tile else ''
    w=(f'<polyline points="8,9 33,32 8,55" fill="none" stroke="{shock}" stroke-width="3.2" '
       f'stroke-linejoin="round" stroke-linecap="round" opacity="{wave_op}"/>') if waves else ''
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">{t}'
            f'<path d="{UP}" fill="{fg}"/><path d="{LO}" fill="{fg}"/>{w}'
            f'<polyline points="44,22.5 33,32 44,41.5" fill="none" stroke="{shock}" stroke-width="{chev_w}" '
            f'stroke-linejoin="round" stroke-linecap="round"/></svg>')
files={
 "logo.svg": svg(),                                   # full colour, on light backgrounds
 "logo_small.svg": svg(waves=False, chev_w=4.6),      # 16-32 px: no Mach waves (stays legible)
 "logo_mono.svg": svg(fg="#111827", shock="#111827"), # one colour (print, README badges)
 "logo_white.svg": svg(fg="#FFFFFF", shock="#FBBF24"),# on dark/blue backgrounds
 "app_icon.svg": svg(fg="#FFFFFF", shock="#FBBF24", tile=ACC, wave_op=.6),
 "app_icon_small.svg": svg(fg="#FFFFFF", shock="#FBBF24", tile=ACC, waves=False, chev_w=4.8),
}
for k,v in files.items(): open(k,"w").write(v)
