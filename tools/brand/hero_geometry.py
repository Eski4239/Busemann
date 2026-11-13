"""Geometry of the Concorde-style welcome-image intake: Busemann two-ramp Oswatitsch design at M 2.02
(ramps 10.56 / 11.35 deg, recovery 0.954), drawn ramps-up as on an under-wing intake."""
import numpy as np, math
TEXT="#111827"; MUTED="#6B7280"; ACC="#2563EB"; SHOCK="#D97706"; WALL="#374151"; BG="#F6F7F9"; SURF="#FFFFFF"; BORDER="#E2E5EA"
NAVY="#1E293B"
# ---------------- logos ----------------
def busemann_inlet(fg=NAVY, shock=SHOCK, bg=None, flow=None):
    b=f'<rect width="64" height="64" rx="14" fill="{bg}"/>' if bg else ''
    fl=''
    if flow:
        fl=''.join(f'<line x1="2" y1="{y}" x2="9" y2="{y}" stroke="{flow}" stroke-width="2.2" stroke-linecap="round"/>' for y in (26,32,38))
    up='M7,8 C22,9 34,15 44,22 L59,22 L59,15 C46,10 30,5 7,4 Z'
    lo='M7,56 C22,55 34,49 44,42 L59,42 L59,49 C46,54 30,59 7,60 Z'
    return f'''<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">{b}{fl}
<path d="{up}" fill="{fg}"/><path d="{lo}" fill="{fg}"/>
<polyline points="8,9 33,32 8,55" fill="none" stroke="{shock}" stroke-width="3.2" stroke-linejoin="round" stroke-linecap="round" opacity=".55"/>
<polyline points="44,22.5 33,32 44,41.5" fill="none" stroke="{shock}" stroke-width="3.6" stroke-linejoin="round" stroke-linecap="round"/></svg>'''

def biplane_inlet(fg=NAVY, shock=SHOCK, bg=None, flow=ACC):
    b=f'<rect width="64" height="64" rx="14" fill="{bg}"/>' if bg else ''
    fl=''.join(f'<line x1="3" y1="{y}" x2="10" y2="{y}" stroke="{flow}" stroke-width="2.4" stroke-linecap="round"/>' for y in (27,32,37)) if flow else ''
    return f'''<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">{b}{fl}
<polygon points="12,12 60,12 36,22.5" fill="{fg}"/><polygon points="12,52 60,52 36,41.5" fill="{fg}"/>
<line x1="13.5" y1="13.8" x2="36" y2="41.5" stroke="{shock}" stroke-width="3.4" stroke-linecap="round"/>
<line x1="13.5" y1="50.2" x2="36" y2="22.5" stroke="{shock}" stroke-width="3.4" stroke-linecap="round"/></svg>'''

def badge(fg=NAVY, shock=SHOCK, bg=None):
    b=f'<rect width="64" height="64" rx="14" fill="{bg}"/>' if bg else ''
    ring=f'<circle cx="32" cy="32" r="29" fill="none" stroke="{fg}" stroke-width="3"/>'
    up='M10,17 C22,18 30,22 38,27 L52,27 L52,22 C42,17 28,13 14,12 Z'
    lo='M10,47 C22,46 30,42 38,37 L52,37 L52,42 C42,47 28,51 14,52 Z'
    return f'''<svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg">{b}{ring}
<path d="{up}" fill="{fg}"/><path d="{lo}" fill="{fg}"/>
<polyline points="38,27.5 30,32 38,36.5" fill="none" stroke="{shock}" stroke-width="3.4" stroke-linejoin="round" stroke-linecap="round"/>
<polyline points="11,18 30,32 11,46" fill="none" stroke="{shock}" stroke-width="2.6" stroke-linejoin="round" opacity=".55"/></svg>'''

# ---------------- Concorde-style intake hero (Busemann design at M 2.02) ----------------
g=1.4
th1,th2=10.5566,11.3499; b1=39.5228; b2abs=th1+51.6881; dd=th1+th2
Mn_=1.2854988; M1,M2=1.63831,1.22575
def AoA(M): return (1/M)*((2/(g+1))*(1+(g-1)/2*M*M))**((g+1)/(2*(g-1)))
def p0(Mn): return (((g+1)*Mn**2/((g-1)*Mn**2+2))**(g/(g-1)))*(((g+1)/(2*g*Mn**2-(g-1)))**(1/(g-1)))
hc=100.0
LIP=np.array([hc/math.tan(math.radians(b1)),hc]); LE=np.array([0.,0.])
a=math.radians(th1); r1=np.array([math.cos(a),math.sin(a)]); s2=np.array([math.cos(math.radians(b2abs)),math.sin(math.radians(b2abs))])
A=np.array([[r1[0],-s2[0]],[r1[1],-s2[1]]]); s,t=np.linalg.solve(A,LIP); C=s*r1
u=np.array([math.cos(math.radians(dd)),math.sin(math.radians(dd))]); nrm=np.array([-u[1],u[0]])
ht=hc*AoA(M2)/AoA(2.02)/(p0(Mn_)**2)
FOOT=LIP-ht*nrm
print('lip',LIP,'corner',C,'ht',ht,'foot',FOOT)
def inter(p,r,a,b):
    sv=b-a; M=np.array([[r[0],-sv[0]],[r[1],-sv[1]]]); tt,_=np.linalg.solve(M,a-p); return p+tt*r
def bez(p0_,p1,p2,p3,n=40):
    ts=np.linspace(0,1,n)[:,None]; return ((1-ts)**3*p0_+3*(1-ts)**2*ts*p1+3*(1-ts)*ts**2*p2+ts**3*p3)
# subsonic diffuser: walls bend back to horizontal and diverge to the engine face
EF_X=FOOT[0]+205
lo0=FOOT; lo3=np.array([EF_X,FOOT[1]+48]); lo=bez(lo0,lo0+60*u,lo3-np.array([90,0]),lo3)
hi0=LIP; hi3=np.array([EF_X,FOOT[1]+48+ht*1.7]); hi=bez(hi0,hi0+60*u,hi3-np.array([90,0]),hi3)
def streamline(y0,x0):
    p=np.array([x0,y0]); pts=[p]
    q=inter(p,np.array([1,0]),LE,LIP); pts.append(q)
    q2=inter(q,r1,C,LIP); pts.append(q2)
    q3=inter(q2,u,FOOT,LIP); pts.append(q3)
    f=np.linalg.norm(q3-FOOT)/ht
    for k in range(1,len(lo)): pts.append(lo[k]*(1-f)+hi[k]*f)
    return pts

