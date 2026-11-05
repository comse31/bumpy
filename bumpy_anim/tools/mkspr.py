import cv2, numpy as np, pickle
from PIL import Image
R=125; S=512; C=(256,256)
def load(n): return np.array(Image.open('/mnt/user-data/uploads/'+n).convert('RGB'))
def charmask(im):
    f=im.astype(np.float32)+1; r,g,b=f[...,0],f[...,1],f[...,2]
    bg=(b/r>0.36)&(g/r<0.32)&(r>90)
    return ~bg
def comps(mask,n):
    m=cv2.morphologyEx(mask.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    m=cv2.morphologyEx(m,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    nl,lab,st,_=cv2.connectedComponentsWithStats(m)
    cs=sorted([(st[i,4],i) for i in range(1,nl) if st[i,4]>8000],reverse=True)[:n]
    out=[(st[i,0],st[i,1],st[i,2],st[i,3],lab==i) for a,i in cs]
    out.sort(key=lambda t:(round((t[1]+t[3]/2)/340),t[0])); return out
def sprite(im,mask,comp):
    lab=comp[4]; region=cv2.dilate(lab.astype(np.uint8),np.ones((11,11),np.uint8))
    m=((region>0)&mask).astype(np.uint8)
    inv=(1-m).astype(np.uint8); pad=np.zeros((m.shape[0]+2,m.shape[1]+2),np.uint8); cv2.floodFill(inv,pad,(0,0),2)
    filled=(inv!=2).astype(np.uint8)
    ys,xs=np.where(filled>0); bottom=ys.max()
    rows=np.arange(ys.min(),bottom+1); w=np.array([(filled[r]>0).sum() for r in rows])
    sel=rows[w>=w.max()*0.97]; xr=np.where(filled[int(sel.mean())]>0)[0]
    cx=(xr.min()+xr.max())/2; r=(xr.max()-xr.min()+1)/2; cy=bottom-r
    a=cv2.GaussianBlur(filled.astype(np.float32),(0,0),0.7)
    img=im.astype(np.float32).copy()
    band=(cv2.dilate(filled,np.ones((3,3),np.uint8))-cv2.erode(filled,np.ones((3,3),np.uint8),iterations=2))>0
    img[...,2]=np.where(band,np.minimum(img[...,2],img[...,0]*0.35),img[...,2])
    s=R/r; M=np.array([[s,0,C[0]-s*cx],[0,s,C[1]-s*cy]],np.float32)
    pm=np.dstack([img*a[...,None],a*255])
    out=cv2.warpAffine(pm,M,(S,S),flags=cv2.INTER_AREA if s<1 else cv2.INTER_CUBIC,borderValue=0)
    al=np.clip(out[...,3],0,255)/255
    col=np.clip(out[...,:3]/np.maximum(al[...,None],1e-3),0,255)
    return np.dstack([col,al*255]).astype(np.uint8),(cx,cy,r)
sp={}
b=load('blink.jpg'); mb=charmask(b); cb=comps(mb,6); print('blink comps',len(cb))
for n,c in zip(['calm','blink','blink2','look','side','dead'],cb): sp[n],info=sprite(b,mb,c); print(n,info)
f=load('faces.jpg'); mf=charmask(f); cf=comps(mf,6); print('faces comps',len(cf))
for n,c in zip(['worried','dizzy','laughing','happy','surprised','happy2'],cf): sp[n],info=sprite(f,mf,c); print(n,info)
sp['laughing2']=sp['laughing']
pickle.dump(sp,open('sprites.pkl','wb'))
names=list(sp); W=np.zeros((2*256,6*256,3),np.uint8); W[:]=(200,205,215)
for i,n in enumerate(names[:12]):
    t=cv2.resize(sp[n],(256,256),interpolation=cv2.INTER_AREA); a=t[...,3:4]/255.; r_,c_=divmod(i,6)
    reg=W[r_*256:(r_+1)*256,c_*256:(c_+1)*256]; reg[:]=(t[...,:3]*a+reg*(1-a)).astype(np.uint8)
    cv2.putText(W,n,(c_*256+4,r_*256+16),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,0,0),1)
Image.fromarray(W).save('faces_check.png')
