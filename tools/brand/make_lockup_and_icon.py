"""Writes the logo+title lockups (text converted to outlines, Inter SemiBold from src/busemann/resources/fonts)
and the app icon (the logo on a light tile). Run from src/busemann/resources/brand with the fonts copied alongside."""
from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
import re
NAVY="#1E293B"; SHOCK="#D97706"; MUTED="#64748B"
UP='M7,8 C22,9 34,15 44,22 L59,22 L59,15 C46,10 30,5 7,4 Z'
LO='M7,56 C22,55 34,49 44,42 L59,42 L59,49 C46,54 30,59 7,60 Z'
def mark(fg,shock,waves=True,wave_op=.55,chev=3.6):
    w=f'<polyline points="8,9 33,32 8,55" fill="none" stroke="{shock}" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round" opacity="{wave_op}"/>' if waves else ''
    return f'<path d="{UP}" fill="{fg}"/><path d="{LO}" fill="{fg}"/>{w}<polyline points="44,22.5 33,32 44,41.5" fill="none" stroke="{shock}" stroke-width="{chev}" stroke-linejoin="round" stroke-linecap="round"/>'
def text_path(font, s, size, tracking=0.0):
    f=TTFont(font); gs=f.getGlyphSet(); cmap=f.getBestCmap(); upm=f['head'].unitsPerEm; sc=size/upm
    x=0; paths=[]
    for ch in s:
        gn=cmap[ord(ch)]; pen=SVGPathPen(gs); tp=TransformPen(pen,(sc,0,0,-sc,x,0)); gs[gn].draw(tp)
        paths.append(pen.getCommands()); x+=gs[gn].width*sc+tracking*size
    return " ".join(paths), x-tracking*size
def lockup(fg=NAVY, shock=SHOCK, sub=MUTED, stacked=False):
    name,wn=text_path("Inter-SemiBold.ttf","Busemann",40,-0.012)
    tag,wt=text_path("Inter-SemiBold.ttf","SUPERSONIC INLET DESIGN",10.6,0.16)
    if not stacked:
        W=64+14+max(wn,wt)+4; H=64
        body=(f'<g>{mark(fg,shock)}</g><g transform="translate(78,40)"><path d="{name}" fill="{fg}"/></g>'
              f'<g transform="translate(79.5,56)"><path d="{tag}" fill="{sub}"/></g>')
    else:
        W=max(wn,wt,64)+8; H=128
        mx=(W-64)/2
        body=(f'<g transform="translate({mx},0)">{mark(fg,shock)}</g><g transform="translate({(W-wn)/2},{64+12+30})"><path d="{name}" fill="{fg}"/></g>'
              f'<g transform="translate({(W-wt)/2},{124})"><path d="{tag}" fill="{sub}"/></g>')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.1f} {H}" width="{W:.1f}" height="{H}">{body}</svg>', W, H
out={}
out["logo_lockup.svg"]=lockup()
out["logo_lockup_white.svg"]=lockup(fg="#FFFFFF",shock="#FBBF24",sub="#CBD5E1")
out["logo_lockup_stacked.svg"]=lockup(stacked=True)
for k,(s,W,H) in out.items(): open(k,"w").write(s); print(k,round(W),H)
# app icon = the logo itself on a light tile (same colours as the mark)
def tile_icon(small):
    m=mark(NAVY,SHOCK,waves=not small,chev=4.8 if small else 3.6)
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">'
            '<defs><linearGradient id="t" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#EEF2F7"/></linearGradient></defs>'
            '<rect x="1" y="1" width="62" height="62" rx="14" fill="url(#t)" stroke="#CBD5E1" stroke-width="1.5"/>'
            f'<g transform="translate(5.5,5.5) scale(.83)">{m}</g></svg>')
open("app_icon.svg","w").write(tile_icon(False)); open("app_icon_small.svg","w").write(tile_icon(True))
