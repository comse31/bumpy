import cv2, numpy as np, glob
from PIL import Image
U='/mnt/user-data/uploads/'
R=125; S=512; C=(256,256); SPILL='blue'   # source canvas: ball radius 125, ball centre (256,256)

def load(pat): return np.array(Image.open(glob.glob(U+pat)[0]).convert('RGB'))

def bg_mask_blue(im):
    f=im.astype(np.int32); bd=f[...,2]-np.maximum(f[...,0],f[...,1])
    return bd<45   # True = character
def bg_mask_magenta(im):
    f=im.astype(np.int32)
    # background magenta/pink: blue channel high relative to green and red high; character red has low blue
    return ~((f[...,2]>0.45*f[...,0]) & (f[...,1]<0.35*f[...,0]) & (f[...,0]>110) | (f[...,0]<200)&(f[...,2]>0.5*f[...,0])&(f[...,1]<60))

def components(mask, n):
    m=cv2.morphologyEx(mask.astype(np.uint8),cv2.MORPH_CLOSE,np.ones((9,9),np.uint8))
    nl,lab,st,_=cv2.connectedComponentsWithStats(m)
    comps=[(st[i,4],i) for i in range(1,nl) if st[i,4]>8000]
    comps=sorted(comps,reverse=True)[:n]
    out=[]
    for a,i in comps:
        x,y,w,h=st[i,:4]; out.append((x,y,w,h,(lab==i)))
    # order row-major by centre
    out.sort(key=lambda t:(round((t[1]+t[3]/2)/300), t[0]))
    return out

ORIGMASK=None
def make_sprite(im, comp):
    x,y,w,h,lab=comp
    region=cv2.dilate(lab.astype(np.uint8),np.ones((11,11),np.uint8))
    m=(region>0)&ORIGMASK
    m=m.astype(np.uint8)
    # fill holes = areas not connected to the image border
    inv=(1-m).astype(np.uint8)
    ff=inv.copy(); h_,w_=ff.shape
    pad=np.zeros((h_+2,w_+2),np.uint8)
    cv2.floodFill(ff,pad,(0,0),2)
    filled=((ff!=2)).astype(np.uint8)
    # ball circle: widest row
    ys,xs=np.where(filled>0)
    bottom=ys.max()
    rowsw=np.array([ (filled[r]>0).sum() for r in range(ys.min(),bottom+1)])
    rows=np.arange(ys.min(),bottom+1)
    mx=rowsw.max(); sel=rows[rowsw>=mx*0.97]
    xr=np.where(filled[int(sel.mean())]>0)[0]
    cx=(xr.min()+xr.max())/2.0; r=(xr.max()-xr.min()+1)/2.0
    cy=bottom-r
    # soft alpha
    a=cv2.GaussianBlur(filled.astype(np.float32),(0,0),0.7)
    interior=cv2.erode(filled,np.ones((3,3),np.uint8))
    img=im.astype(np.float32).copy()
    band=(cv2.dilate(filled,np.ones((3,3),np.uint8),iterations=1)-cv2.erode(filled,np.ones((3,3),np.uint8),iterations=2))>0
    if SPILL=='blue':
        img[...,2]=np.where(band,np.minimum(img[...,2],np.maximum(img[...,0],img[...,1])*0.6),img[...,2])
    else:
        img[...,2]=np.where(band,np.minimum(img[...,2],img[...,0]*0.35),img[...,2])
        img[...,0]=np.where(band,np.minimum(img[...,0],235),img[...,0])
    # transform to canonical canvas
    s=R/r
    M=np.array([[s,0,C[0]-s*cx],[0,s,C[1]-s*cy]],np.float32)
    rgba=np.dstack([img.astype(np.float32),a*255])
    pm=rgba.copy(); pm[...,:3]*=a[...,None]/1.0
    out=cv2.warpAffine(pm,M,(S,S),flags=cv2.INTER_AREA if s<1 else cv2.INTER_CUBIC,borderValue=0)
    al=np.clip(out[...,3],0,255)/255.0
    col=np.where(al[...,None]>1e-3,out[...,:3]/np.maximum(al[...,None],1e-3)/1.0,0)
    # un-premultiply (we premultiplied by a, in 0..1 space)
    col=np.clip(out[...,:3]/np.maximum(al[...,None],1e-3),0,255)
    return np.dstack([col,al*255]).astype(np.uint8), r

def build():
    global SPILL, ORIGMASK
    SPILL='blue'
    sheet=load('gemini-2_5-flash-image_Use_the_attached_approved*')
    global ORIGMASK
    ORIGMASK=bg_mask_blue(sheet)
    comps=components(ORIGMASK,9)
    names=['happy','worried','scared','laughing','dizzy','blink','laughing2','calm','surprised']
    sp={}
    for n,c in zip(names,comps): sp[n]=make_sprite(sheet,c)[0]
    SPILL='magenta'
    sheet2=load('gemini-2_5-flash-image_Bumpy_game_art_style*')
    ORIGMASK=bg_mask_magenta(sheet2)
    comps2=components(ORIGMASK,6)
    n2=['m_base','m_blink1','m_blink2','m_look','m_side','dead']
    for n,c in zip(n2,comps2): sp[n]=make_sprite(sheet2,c)[0]
    return sp
if __name__=='__main__':
    sp=build()
    print(len(sp),list(sp))
    names=list(sp)
    cols=5; rows=(len(names)+cols-1)//cols
    W=np.zeros((rows*S//2,cols*S//2,3),np.uint8); W[:]=(200,205,215)
    for i,n in enumerate(names):
        t=cv2.resize(sp[n],(S//2,S//2),interpolation=cv2.INTER_AREA)
        a=t[...,3:4]/255.
        r_,c_=divmod(i,cols)
        W[r_*S//2:(r_+1)*S//2,c_*S//2:(c_+1)*S//2]=(t[...,:3]*a+W[r_*S//2:(r_+1)*S//2,c_*S//2:(c_+1)*S//2]*(1-a)).astype(np.uint8)
        cv2.putText(W,n,(c_*S//2+5,r_*S//2+18),cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,0,0),1)
    Image.fromarray(W).save('faces_check.png')
    import pickle; pickle.dump(sp,open('sprites.pkl','wb'))
