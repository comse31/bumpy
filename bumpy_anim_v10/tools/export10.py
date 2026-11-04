import numpy as np, cv2, json, os, shutil
from PIL import Image
from clips10 import *
OUT='/mnt/user-data/outputs/bumpy_anim_v10'
shutil.rmtree(OUT,ignore_errors=True)
for d in ['frames','sheets','gif','tools']: os.makedirs(f'{OUT}/{d}')
meta={}; rep=[]; allfr={}
for nm,c in C.items():
    fr=build(nm); allfr[nm]=fr; n=len(fr)
    d=f'{OUT}/frames/{nm}'; os.makedirs(d)
    for i,f in enumerate(fr): Image.fromarray(f).save(f'{d}/{nm}_{i+1:02d}.png')
    Image.fromarray(np.concatenate(fr,axis=1)).save(f'{OUT}/sheets/{nm}.png')
    probs=[]
    bg=np.full(fr[0].shape[:2]+(3,),200,np.float32)
    comp=lambda x:(x[...,:3]*(x[...,3:4]/255.)+bg*(1-x[...,3:4]/255.))
    for i,f in enumerate(fr):
        a=f[...,3]
        if a[0].max()>10 or a[-1].max()>10 or a[:,0].max()>10 or a[:,-1].max()>10: probs.append(f'{i+1}:edge-clip')
        if i>0 and np.abs(comp(f)-comp(fr[i-1])).mean()/255*100<0.05: probs.append(f'{i+1}:repeat')
    rep.append((nm,n,probs))
    g=[]
    for f in fr:
        b=np.full(f.shape[:2]+(3,),(200,205,215),np.float32); a=f[...,3:4]/255.
        g.append(Image.fromarray((f[...,:3]*a+b*(1-a)).astype(np.uint8)).resize((96,96),Image.LANCZOS))
    dur=int(round(1000*c['dur']/n))
    g[0].save(f'{OUT}/gif/{nm}_96.gif',save_all=True,append_images=g[1:],duration=dur,loop=0,disposal=2)
    meta[nm]={'frames':n,'duration_sec':round(c['dur'],4),'fps':c['fps'],'loop':c['loop'],'hold_last_frame':c['hold'],'physics_bound':c['phys'],
              'contact':c['contact'],'frame_size':[F,F],'pivot':[F/2,round(155*Q,1)],'ball_diameter_px':round(104*Q,1),'ball_center':[F/2,round(103*Q,1)],'note':c['note'],'phi_deg':[round(p['phi'],1) for p in params(c['keys'],c['n'],c['loop'])]}

# ---- shadow: 5 levels (0 = on the ground: small, sharp, dark ... 4 = high: big, diffuse, faint). No motion arcs (not wanted).
from PIL import ImageDraw, ImageFilter
os.makedirs(OUT+'/fx',exist_ok=True)
for lv in range(9):
    S4=4; W_,H_=192*S4,64*S4
    im=Image.new('RGBA',(W_,H_),(0,0,0,0)); d=ImageDraw.Draw(im)
    rx=(34+4.5*lv)*S4; ry=(8+1.3*lv)*S4; a=int(125-11*lv)           # subtle: max alpha ~0.49, fading to ~0.15
    d.ellipse((W_/2-rx,H_/2-ry,W_/2+rx,H_/2+ry),fill=(18,8,28,a))
    im=im.filter(ImageFilter.GaussianBlur((1.2+2.6*lv)*S4/2)).resize((192,64),Image.LANCZOS)
    im.save(f'{OUT}/fx/shadow_{lv}.png')
json.dump(meta,open(OUT+'/animations.json','w'),ensure_ascii=False,indent=1)
for f in ['engine2.py','clips10.py','look.py','faces.py','export10.py','key.py']: shutil.copy(f,OUT+'/tools/'+f)
rows=[]
for nm,fr in allfr.items():
    ff=[cv2.resize(f,(64,64),interpolation=cv2.INTER_AREA) for f in fr]
    for i in range(0,len(ff),24):
        ch=ff[i:i+24]; ch=ch+[np.zeros((64,64,4),np.uint8)]*(24-len(ch))
        st=np.concatenate(ch,axis=1); b=np.full(st.shape[:2]+(3,),(200,205,215),np.float32); a=st[...,3:4]/255.
        img=(st[...,:3]*a+b*(1-a)).astype(np.uint8)
        if i==0: cv2.putText(img,nm,(4,12),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,0,0),1)
        rows.append(img)
Image.fromarray(np.concatenate(rows,axis=0)).save(OUT+'/overview.png')
print(sum(len(f) for f in allfr.values()),'frames')
for r in rep: print(r)
