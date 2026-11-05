import cv2, numpy as np, pickle, math
from scipy.interpolate import PchipInterpolator
SP=pickle.load(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'sprites.pkl'),'rb'))
R=125; SC=(256,256)
import os
F=int(os.environ.get('BUMPY_F','160')); SS=2; RC=F*SS; Q=F/208.0
O=(F/2*SS,103*Q*SS)
S=104*Q*SS/2/R
GROUND=155*Q*SS
WALLX=(104+52)*Q*SS
CEILY=37*Q*SS
CEILB=51*Q*SS
def _mk_body():
    H=512; ys,xs=np.mgrid[0:H,0:H].astype(np.float32); r=np.sqrt((xs-SC[0])**2+(ys-SC[1])**2)
    a=np.clip(R+0.7-r,0,1)*255
    return np.dstack([np.full((H,H,3),255,np.uint8),a.astype(np.uint8)])
SP['_body']=_mk_body()
import look as _look; _look.SP['_body']=SP['_body']
DEF=dict(anch=.3,phi=0.,psi=90.,k=1.,wmin=.8,tip=0.,sy=1.,sytop=1.,bulge=0.,shear=0.,hair=0.,cut=0.,flatp=1.3,g=0.,lookx=0.,looky=0.,lid=0.,slidex=0.,slidey=0.,turn=0.)


_cache={}
def _sm(a,b,x): 
    t=np.clip((x-a)/(b-a),0,1); return t*t*(3-2*t)
def sphere_turn(face, yaw, pitch):
    """yaw: face turns toward screen-right (deg, ball frame); pitch: face tips downward (deg).
    Face texture is mapped on a sphere (orthographic); the hair is a decal rotated with the head."""
    key=(face,round(yaw,1),round(pitch,1))
    if key in _cache: return _cache[key]
    src=SP[face].astype(np.float32)
    a=src[...,3:4]/255.; pm=np.concatenate([src[...,:3]*a,src[...,3:4]],axis=2)
    H=pm.shape[0]
    ys,xs=np.mgrid[0:H,0:H].astype(np.float32)
    X=xs-SC[0]; Y=ys-SC[1]
    r=np.sqrt(X*X+Y*Y); rc=np.minimum(r,0.985*R)
    # clean texture: replace the outline ring (it must not travel across the sphere) with body colour from just inside
    k_=np.where(r>0.9*R,0.88*R/np.maximum(r,1e-6),1.0)
    pm_clean=cv2.remap(pm,(X*k_+SC[0]).astype(np.float32),(Y*k_+SC[1]).astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    Z=np.sqrt(np.maximum(R*R-rc*rc,0))
    th=math.radians(yaw); al=math.radians(pitch)
    xs1=X*math.cos(th)-Z*math.sin(th); zs1=X*math.sin(th)+Z*math.cos(th); ys1=Y
    ys2=ys1*math.cos(al)-zs1*math.sin(al); zs2=ys1*math.sin(al)+zs1*math.cos(al); xs2=xs1
    # back hemisphere: sample plain body ring at 0.86R along the same direction
    rr=np.sqrt(xs2**2+ys2**2)+1e-6
    back=zs2<0
    sxs=np.where(back,xs2/rr*0.86*R,xs2); sys_=np.where(back,ys2/rr*0.86*R,ys2)
    body=cv2.remap(pm_clean,(sxs+SC[0]).astype(np.float32),(sys_+SC[1]).astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    # keep the original outline ring / silhouette
    w=_sm(0.90*R,0.975*R,r)[...,None]
    body=body*(1-w)+pm*w
    circ=np.clip(R+0.7-r,0,1)
    # hair = everything outside the ball circle
    hmask=(_sm(0.97*R,1.03*R,r)*(r>0.97*R))[...,None]
    hair=pm*hmask
    body=np.dstack([body[...,:3]*circ[...,None],255*circ])  # premultiplied colour, alpha 0..255
    # transform hair as planar decal: [x'';y''] = [[cos th, -sin al sin th],[0, cos al]] [x;y]
    ca=math.cos(al); ca=(1 if ca>=0 else -1)*max(abs(ca),0.12)
    M=np.array([[math.cos(th),-math.sin(al)*math.sin(th)],[0,ca]],np.float32)
    Mi=np.linalg.inv(M)
    hx=Mi[0,0]*X+Mi[0,1]*Y+SC[0]; hy=Mi[1,0]*X+Mi[1,1]*Y+SC[1]
    hair_t=cv2.remap(hair,hx.astype(np.float32),hy.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)
    ha=hair_t[...,3:4]/255.; ba=body[...,3:4]/255.
    if pitch>=0: out=hair_t+body*(1-ha)   # hair in front
    else: out=body+hair_t*(1-ba)          # hair behind the head
    _cache[key]=out
    return out

_pc={}
from look import move_irises, slide_face
def stage1(face, phi, psi, k, wmin, tip, hair, yaw=0., pitch=0., lid=0., sdx=0., sdy=0., sph=0.):
    key=(face,round(yaw*2)/2,round(pitch*2)/2,round(lid*10)/10,round(sdx),round(sdy),round(sph))
    if key not in _pc and abs(sph)>0.3:
        _pc[key]=sphere_turn(face,sph,0.)
    if key not in _pc:
        src=move_irises(face,yaw,pitch,lid)
        src=slide_face(src,sdx,sdy).astype(np.float32)
        a=src[...,3:4]/255.; _pc[key]=np.concatenate([src[...,:3]*a,src[...,3:4]],axis=2)
    pm=_pc[key]
    ys,xs=np.mgrid[0:RC,0:RC].astype(np.float32)
    qx=xs-O[0]; qy=ys-O[1]
    p=math.radians(psi); d=(math.cos(p),-math.sin(p)); n=(math.sin(p),math.cos(p))
    u=qx*d[0]+qy*d[1]; v=qx*n[0]+qy*n[1]
    w0=max(wmin,1/math.sqrt(k)) if k>1 else 1.0
    taper=1.0-tip*0.22*np.clip(u/(R*S*max(k,1)),-1,1)
    us=u/k; vs=v/(w0*taper)
    rx=us*d[0]+vs*n[0]; ry=us*d[1]+vs*n[1]
    ph=math.radians(phi); c,s_=math.cos(ph),math.sin(ph)
    px=c*rx+s_*ry; py=-s_*rx+c*ry
    sx=px/S+SC[0]; sy_=py/S+SC[1]
    if hair:
        t=np.clip((SC[1]-R*0.75-sy_)/(R*0.45),0,1)
        sx=sx+hair*t*t
    return cv2.remap(pm,sx.astype(np.float32),sy_.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)

def stage2(img, sy, sytop, bulge, shear, cut, flatp, contact):
    rk={'bottom':0,'right':-1,'left':1,'top':2}[contact]
    if rk: img=np.ascontiguousarray(np.rot90(img,rk))
    al=img[...,3]/255.
    rows=np.where(al.max(axis=1)>0.15)[0]; yt,yb=rows.min(),rows.max()+1; H=float(yb-yt)
    cols=np.where(al.max(axis=0)>0.15)[0]; cx=(cols.min()+cols.max())/2.0
    tg=np.linspace(0,1,512)
    outd=H*(sy+(sytop-sy)*tg/2)*tg
    ys2=np.arange(RC,dtype=np.float32); dist=yb-ys2
    t_src=np.interp(dist,outd,tg,left=-1,right=2)
    ysrc=yb-t_src*H
    valid=(t_src>=0)&(t_src<=1)
    tn=np.clip(dist/max(outd[-1],1),0,1)
    wf=1.0+bulge*(1-tn)**flatp
    if cut: valid&=(dist>=cut*outd[-1])
    xs=np.arange(RC,dtype=np.float32)[None,:]
    xsrc=cx+(xs-cx)/wf[:,None]-shear*H*np.clip(t_src,0,1)[:,None]
    mapx=np.ascontiguousarray(np.broadcast_to(xsrc,(RC,RC)),dtype=np.float32)
    mapy=np.ascontiguousarray(np.broadcast_to(ysrc[:,None],(RC,RC)),dtype=np.float32)
    out=cv2.remap(img,mapx,mapy,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=0)
    out[~valid]=0
    if rk: out=np.ascontiguousarray(np.rot90(out,-rk))
    return out

def frame(face, contact='bottom', **kw):
    P=dict(DEF); P.update(kw)
    c_,s_=math.cos(math.radians(P['phi'])),math.sin(math.radians(P['phi']))
    # eyes look direction given in SCREEN px (x right, y down, max ~7) -> ball frame
    yaw_b=c_*P['lookx']+s_*P['looky']; pitch_b=-s_*P['lookx']+c_*P['looky']
    img=stage1(face,P['phi'],P['psi'],P['k'],P['wmin'],P['tip'],P['hair'],yaw_b,pitch_b,P['lid'],c_*P['slidex']+s_*P['slidey'],-s_*P['slidex']+c_*P['slidey'],c_*P['turn'])
    if P['sy']!=1 or P['sytop']!=1 or P['bulge'] or P['shear'] or P['cut']:
        img=stage2(img,P['sy'],P['sytop'],P['bulge'],P['shear'],P['cut'],P['flatp'],contact)
    g=float(np.clip(P['g'],0,1))
    if g>0:
        bimg=stage1('_body',P['phi'],P['psi'],P['k'],P['wmin'],P['tip'],0.)
        if P['sy']!=1 or P['sytop']!=1 or P['bulge'] or P['shear'] or P['cut']:
            bimg=stage2(bimg,P['sy'],P['sytop'],P['bulge'],P['shear'],P['cut'],P['flatp'],contact)
        def ext(im):
            al=im[...,3]/255.
            rows=np.where(al.max(axis=1)>0.15)[0]; cols=np.where(al.max(axis=0)>0.15)[0]
            return rows.min(),rows.max()+1,cols.min(),cols.max()+1
        bt,bb,bl,br=ext(bimg); at,ab,al_,ar=ext(img)
        A=P['anch']; dx=dy=0.
        if contact=='bottom': dy=GROUND-(bb+A*(ab-bb))
        elif contact=='top': dy=CEILB-(bt-A*(bt-at))
        elif contact=='right': dx=WALLX-(br+A*(ar-br))
        elif contact=='left': dx=(2*O[0]-WALLX)-(bl-A*(bl-al_))
        img=cv2.warpAffine(img,np.float32([[1,0,g*dx],[0,1,g*dy]]),(RC,RC),flags=cv2.INTER_LINEAR,borderValue=0)
    out=cv2.resize(img,(F,F),interpolation=cv2.INTER_AREA)
    a=np.clip(out[...,3:4],0,255)/255.
    col=np.where(a>1e-3,out[...,:3]/np.maximum(a,1e-3),0)
    return np.dstack([np.clip(col,0,255),a*255]).astype(np.uint8)

def K(t,**d): return (t,d)

def params(keys, n, loop=False):
    """Pchip (C1-continuous) interpolation: velocity never drops to zero between keys -> no stop-go jitter."""
    ts=[k[0] for k in keys]; T=ts[-1]
    full=[]; cur=None
    for t,d in keys:
        base=dict(DEF)
        if cur is not None:
            base['phi']=cur['phi']; base['psi']=cur['psi']; base['face']=cur['face']; base['wmin']=cur['wmin']
        base.update(d); cur=base; full.append(base)
    tt=np.linspace(0,T,n,endpoint=not loop)
    out=[dict() for _ in range(n)]
    for name in DEF:
        ys=np.array([f[name] for f in full],float)
        if name=='psi': ys=np.degrees(np.unwrap(np.radians(ys)))
        f=PchipInterpolator(ts,ys) if len(ts)>2 else (lambda x,ys=ys,ts=ts:np.interp(x,ts,ys))
        v=f(tt)
        for i in range(n): out[i][name]=float(v[i])
    for i,t in enumerate(tt):
        j=max(q for q in range(len(ts)) if ts[q]<=t+1e-9)
        out[i]['face']=full[j]['face']
    return out
