import cv2, numpy as np, pickle, math
SP=pickle.load(open('/home/claude/w/sprites.pkl','rb'))
R=125; SC=(256,256)
_ic={}
def eyes_info(face):
    if face in _ic: return _ic[face]
    s=SP[face]; rgb=s[...,:3].astype(np.int32); a=s[...,3]
    g=(rgb[...,1]>rgb[...,0]+25)&(rgb[...,1]>rgb[...,2]+5)&(a>200)
    g=cv2.morphologyEx(g.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((3,3),np.uint8))
    n,lab,st,_=cv2.connectedComponentsWithStats(g)
    comps=sorted([(st[i,4],i) for i in range(1,n) if st[i,4]>60],reverse=True)[:2]
    eyes=[]
    for area,i in comps:
        m=(lab==i).astype(np.uint8)
        cnt,_=cv2.findContours(m,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
        f=np.zeros_like(m); cv2.drawContours(f,cnt,-1,1,-1)      # iris incl. pupil and highlight
        f=cv2.dilate(f,np.ones((3,3),np.uint8))
        # eye white region: white-ish or iris, around the iris
        white=((rgb.min(axis=2)>150)&(a>200)).astype(np.uint8)|f
        white=cv2.morphologyEx(white,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        n2,lab2,_,_=cv2.connectedComponentsWithStats(white)
        ys,xs=np.where(f>0); cy,cx=int(ys.mean()),int(xs.mean())
        reg=(lab2==lab2[cy,cx]).astype(np.uint8)
        cnt2,_=cv2.findContours(reg,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_NONE)
        reg2=np.zeros_like(reg); cv2.drawContours(reg2,cnt2,-1,1,-1)
        inner=cv2.erode(reg2,np.ones((5,5),np.uint8))
        wcol=np.median(rgb[(white>0)&(f==0)&(rgb.min(axis=2)>150)],axis=0) if ((white>0)&(f==0)).any() else np.array([245,245,240])
        eyes.append(dict(iris=f,inner=inner,wcol=wcol,cx=cx,cy=cy))
    _ic[face]=eyes; return eyes

def move_irises(face, dx, dy, lid=0.0, maxs=7.0):
    """returns RGBA uint8 sprite with irises shifted inside the whites (2D, no 3D)."""
    s=SP[face].copy()
    if abs(dx)<0.05 and abs(dy)<0.05 and lid<0.02: return s
    eyes=eyes_info(face)
    if not eyes: return s
    rgb=s[...,:3].astype(np.float32); out=rgb.copy()
    for e in eyes:
        f=e['iris']; inner=e['inner']
        # vacate: paint white where the iris was
        fm=cv2.dilate(f,np.ones((3,3),np.uint8))>0
        out[fm]=e['wcol']
    for e in eyes:
        f=e['iris'].astype(np.float32)
        M=np.float32([[1,0,dx],[0,1,dy]])
        fs=cv2.warpAffine(f,M,(512,512),flags=cv2.INTER_LINEAR)
        cs=cv2.warpAffine(rgb,M,(512,512),flags=cv2.INTER_LINEAR)
        fs=cv2.GaussianBlur(fs,(0,0),0.6)*e['inner']
        out=out*(1-fs[...,None])+cs*fs[...,None]
    if lid>0.02:
        for e in eyes:
            inner=e['inner']>0
            ys,xs=np.where(inner)
            if len(ys)==0: continue
            top,bot=ys.min(),ys.max(); yl=top+lid*(bot-top)
            yy=np.arange(512)[:,None]*np.ones((1,512))
            reg=inner&(yy<yl)
            ring=(cv2.dilate(inner.astype(np.uint8),np.ones((13,13),np.uint8))>0)&~(cv2.dilate(inner.astype(np.uint8),np.ones((5,5),np.uint8))>0)&(rgb[...,0]>200)&(rgb[...,1]<90)
            skin=np.median(rgb[ring],axis=0) if ring.any() else np.array([245,40,35])
            out[reg]=skin
            edge=inner&(yy>=yl-1.5)&(yy<yl+1.0)
            out[edge]=np.array([120,22,22])
    s[...,:3]=np.clip(out,0,255).astype(np.uint8)
    return s
if __name__=='__main__':
    from PIL import Image
    fr=[]
    for dx,dy in [(0,0),(7,0),(-7,0),(0,-6),(6,5)]:
        s=move_irises('calm',dx,dy)
        bg=np.full((512,512,3),(200,205,215),np.float32); a=s[...,3:4]/255.
        fr.append(cv2.resize(((s[...,:3]*a+bg*(1-a))).astype(np.uint8),(256,256),interpolation=cv2.INTER_AREA))
    Image.fromarray(np.concatenate(fr,axis=1)).save('/home/claude/w/out3/look_test.png')
    print([ (e['cx'],e['cy']) for e in eyes_info('calm')])


def _sm(a,b,x):
    t=np.clip((x-a)/(b-a),0,1); return t*t*(3-2*t)
def slide_face(sprite, dx, dy):
    """2D 'turn toward': the face features slide inside the ball outline by (dx,dy) source px (flat, no projection)."""
    if abs(dx)<0.3 and abs(dy)<0.3: return sprite
    a=sprite[...,3:4].astype(np.float32)/255.
    pm=np.concatenate([sprite[...,:3].astype(np.float32)*a,sprite[...,3:4].astype(np.float32)],axis=2)
    H=512; ys,xs=np.mgrid[0:H,0:H].astype(np.float32); X=xs-SC[0]; Y=ys-SC[1]
    r=np.sqrt(X*X+Y*Y)
    k_=np.where(r>0.9*R,0.88*R/np.maximum(r,1e-6),1.0)
    clean=cv2.remap(pm,(X*k_+SC[0]).astype(np.float32),(Y*k_+SC[1]).astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    shifted=cv2.remap(clean,(X-dx+SC[0]).astype(np.float32),(Y-dy+SC[1]).astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
    w=_sm(0.86*R,0.95*R,r)[...,None]
    body=shifted*(1-w)+pm*w
    circ=np.clip(R+0.7-r,0,1)[...,None]
    base=np.concatenate([body[...,:3]*circ,255*circ],axis=2)
    hmask=((_sm(0.97*R,1.03*R,r)*(r>0.97*R)))[...,None]
    hair=cv2.warpAffine(pm*hmask,np.float32([[1,0,0.5*dx],[0,1,0.5*dy]]),(H,H),flags=cv2.INTER_LINEAR)
    ba=base[...,3:4]/255.
    out=base+hair*(1-ba)
    al=np.clip(out[...,3:4],0,255)/255.
    rgb=np.where(al>1e-3,out[...,:3]/np.maximum(al,1e-3),0)
    return np.dstack([np.clip(rgb,0,255),np.clip(out[...,3:4],0,255)]).astype(np.uint8)
