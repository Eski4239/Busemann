"""Renders welcome_hero.png (1040x660) and welcome_hero_520.png: temperature field T/T_inf of the
welcome-image intake, smoothed to look like a CFD frame, with schlieren-style shock glow and air streaks."""
import numpy as np, math, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Polygon
import matplotlib.patheffects as pe
from matplotlib.collections import LineCollection
from scipy.ndimage import gaussian_filter
import os
exec(open(os.path.join(os.path.dirname(__file__),"hero_geometry.py")).read())   # geometry: LE, C, LIP, FOOT, lo, hi, streamline, u, r1, ht, EF_X
g=1.4
def Tjump(Mn): return (2*g*Mn**2-(g-1))*((g-1)*Mn**2+2)/((g+1)**2*Mn**2)
T1=Tjump(Mn_); T2=T1*Tjump(Mn_); T3=T2*Tjump(M2)          # T/T_inf behind shock 1, 2, terminal
T0r=1+(g-1)/2*2.02**2; Tface=T0r/(1+(g-1)/2*0.45**2)
print("T/Tinf:",T1,T2,T3,Tface)
W,H=1040,660; sx=2.0; ox=224; oy=124             # pixels per mm (2x of the 520x330 layout)
def P(pts): return np.array([[ox+p[0]*sx, oy+p[1]*sx] for p in pts])
yy,xx=np.mgrid[0:H,0:W]; pts=np.c_[xx.ravel()+.5,yy.ravel()+.5]
def inside(poly): return Path(P(poly)).contains_points(pts).reshape(H,W)
big=-200
reg0=inside([(big,0),LE,LIP,(big,100)]); reg1=inside([LE,C,LIP]); reg2=inside([C,FOOT,LIP])
duct_poly=[FOOT]+list(lo)+list(hi[::-1])+[LIP]; regd=inside(duct_poly)
cowl_ext=list(bez(LIP,LIP+np.array([50,22]),hi[-1]+np.array([-120,40]),hi[-1]+np.array([0,30])))
ext_poly=[(big,100)]+cowl_ext+[hi[-1]+np.array([400,30]),(EF_X+400,400),(big,400)]
ext=inside(ext_poly)
T=np.full((H,W),np.nan)
T[ext]=1.0; T[reg0]=1.0; T[reg1]=T1; T[reg2]=T2
# duct: rises from T3 at the terminal shock to Tface at the engine face (progressive diffusion)
dx=(xx-(ox+FOOT[0]*sx))/((EF_X-FOOT[0])*sx); f=np.clip(dx,0,1)**.8
T[regd]=(T3+(Tface-T3)*f)[regd]
fluid=~np.isnan(T); Tf=np.where(fluid,T,1.0)
Tb=gaussian_filter(Tf,2.2)                         # CFD-like smearing of the jumps
# subtle boundary-layer warming near walls
from scipy.ndimage import distance_transform_edt
dist=distance_transform_edt(fluid)
Tb=Tb+0.10*np.exp(-dist/7.0)*fluid
cmap=LinearSegmentedColormap.from_list("heat",["#0E2A47","#1D4E89","#2F7FC1","#5FB0D9","#E9C46A","#F4A261","#E76F51","#FFE8D6"])
norm=(Tb-0.95)/(Tface+0.12-0.95)
rgb=cmap(np.clip(norm,0,1))[...,:3]
bg=np.array([11,18,32])/255
sky=np.dstack([np.linspace(.04,.09,H)[:,None]*np.ones((H,W))*k for k in (1.0,1.45,2.3)])
img=np.where(fluid[...,None],rgb,sky)
# vignette + fade into the upstream dark
vx=np.clip((xx/W)/0.22,0,1)[...,None]; img=img*(0.45+0.55*vx)
fig=plt.figure(figsize=(W/100,H/100),dpi=100); ax=fig.add_axes([0,0,1,1]); ax.set_xlim(0,W); ax.set_ylim(H,0); ax.axis("off")
ax.imshow(img,extent=(0,W,H,0),interpolation="bilinear")
# shocks: schlieren-like glow
def glow(poly,c,w,dash=None):
    p=P(poly)
    for lw,a in ((w*7,.06),(w*4,.12),(w*2,.25)): ax.plot(p[:,0],p[:,1],color=c,lw=lw,alpha=a,solid_capstyle="round")
    ax.plot(p[:,0],p[:,1],color="#FFF4E0",lw=w*.8,alpha=.95,dashes=dash or (None,None))
glow([LE,LIP],"#FFD08A",2.2); glow([C,LIP],"#FFD08A",2.2); glow([LIP,FOOT],"#FFB066",1.8,(4,3))
# air: motion-blurred streaks along streamlines
rng=np.random.default_rng(7)
for y in np.linspace(4,96,17):
    s=np.array(streamline(y,big)); s=P(s)
    seg=np.cumsum(np.r_[0,np.hypot(*np.diff(s,axis=0).T)]); L=seg[-1]
    for k in range(rng.integers(5,9)):
        a0=rng.uniform(0.05,0.95)*L; ln=rng.uniform(26,70)*(1.0 if a0<seg[3] else .55)   # slower in the duct
        tt=np.linspace(a0,min(a0+ln,L),14); xs=np.interp(tt,seg,s[:,0]); ys=np.interp(tt,seg,s[:,1])
        segs=np.stack([np.c_[xs[:-1],ys[:-1]],np.c_[xs[1:],ys[1:]]],axis=1)
        al=(np.arange(len(segs))/len(segs))**2*.55+.02
        ax.add_collection(LineCollection(segs,colors=[(1,1,1,a) for a in al],linewidths=1.5,capstyle="butt",zorder=2))
for y in np.linspace(112,250,9):
    for k in range(rng.integers(3,6)):
        x0=rng.uniform(-110,330); ln=rng.uniform(26,70)
        xs=np.linspace(x0,x0+ln/sx,14); ys=np.full_like(xs,y); seg=P(np.c_[xs,ys])
        segs=np.stack([seg[:-1],seg[1:]],axis=1); al=(np.arange(len(segs))/len(segs))**2*.35+.02
        lc=LineCollection(segs,colors=[(1,1,1,a) for a in al],linewidths=1.3,capstyle="butt",zorder=2)
        ax.add_collection(lc); cp=Polygon(P(ext_poly),closed=True,facecolor="none",edgecolor="none"); ax.add_patch(cp); lc.set_clip_path(cp)
# walls: brushed-metal gradient
def metal(poly,flip=False):
    p=P(poly); patch=Polygon(p,closed=True,facecolor="none",edgecolor="none"); ax.add_patch(patch)
    gy=np.linspace(0,1,256)[:,None]; grad=np.dstack([0.20+0.5*(1-gy if not flip else gy)*np.ones((256,4))]*3)
    grad=np.clip(grad*np.array([0.95,1.0,1.08]),0,1)
    im=ax.imshow(grad,extent=(p[:,0].min(),p[:,0].max(),p[:,1].max(),p[:,1].min()),aspect="auto",zorder=3)
    im.set_clip_path(patch)
    ax.add_patch(Polygon(p,closed=True,facecolor="none",edgecolor="#C9D3E0",lw=1.4,zorder=4))
wl=[np.array(p,float) for p in [(big,-6),(LE[0]-60,-4),LE,C,FOOT]]+list(lo)+[np.array((EF_X+60,lo[-1][1]))]
top=wl+[p+np.array([0,-26]) for p in wl[::-1]]
metal(top,flip=True)
metal([LIP]+list(hi)+[hi[-1]+np.array([60,0]),hi[-1]+np.array([60,30])]+cowl_ext[::-1])
# engine face: fan blades hint
ex=ox+EF_X*sx; y0=oy+lo[-1][1]*sx; y1=oy+hi[-1][1]*sx
ax.add_patch(Polygon([[ex,y0],[ex+30,y0],[ex+30,y1],[ex,y1]],facecolor="#1B2433",edgecolor="#C9D3E0",lw=1.2,zorder=5))
for k in range(1,11):
    yk=y0+(y1-y0)*k/11; ax.plot([ex+4,ex+26],[yk-5,yk+5],color="#8A97AA",lw=2,zorder=6)
ax.plot(ex+15,(y0+y1)/2,"o",color="#5B6B82",ms=9,zorder=7)
fig.savefig("welcome_hero.png",dpi=100,facecolor=bg); 
from PIL import Image; im=Image.open("welcome_hero.png").convert("RGB"); im.resize((520,330),Image.LANCZOS).save("welcome_hero_520.png"); print(im.size)
