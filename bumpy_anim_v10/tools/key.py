import cv2, numpy as np, glob
from PIL import Image
U='/mnt/user-data/uploads/'
def key_blue(path, crop=None):
    im=np.array(Image.open(path).convert('RGB')).astype(np.float32)
    if crop: x0,y0,x1,y1=crop; im=im[y0:y1,x0:x1]
    h,w,_=im.shape
    corners=np.concatenate([im[:6,:6].reshape(-1,3),im[:6,-6:].reshape(-1,3),im[-6:,:6].reshape(-1,3),im[-6:,-6:].reshape(-1,3)])
    bg=np.median(corners,axis=0)
    # blue-ness: bg is (~0,~30,~220); character is red/green/white/brown -> blue channel not dominant
    d=np.linalg.norm(im-bg,axis=2)
    bd=im[...,2]-np.maximum(im[...,0],im[...,1])   # blue dominance
    bgdom=bg[2]-max(bg[0],bg[1])
    a=np.clip((1-(bd/ max(bgdom,1)))*1.6-0.1,0,1)   # 0 where fully blue-dominant
    a=np.where(d<25,0,a)
    # despill
    out=im.copy()
    spill=np.clip(im[...,2]-np.maximum(im[...,0],im[...,1])*1.0,0,None)*(a<0.999)
    out[...,2]=np.minimum(im[...,2],np.maximum(im[...,0],im[...,1])+3)
    rgba=np.dstack([out,a*255]).astype(np.uint8)
    return rgba
if __name__=='__main__':
    p=glob.glob(U+'gpt-image-2_5-flare*')[0]
    r=key_blue(p)
    Image.fromarray(r).save('p1_keyed.png')
    bg=np.full(r.shape[:2]+(3,),(200,205,215),np.uint8)
    a=r[...,3:4]/255.
    comp=(r[...,:3]*a+bg*(1-a)).astype(np.uint8)
    Image.fromarray(comp).save('p1_check.png')
    ys,xs=np.where(r[...,3]>128); print(xs.min(),xs.max(),ys.min(),ys.max())
