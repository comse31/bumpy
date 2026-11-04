import numpy as np, cv2, json, os
from PIL import Image
from engine2 import *

C={}
def add(name,keys,dur,fps=60,loop=False,contact='bottom',hold=False,note='',phys=False,blink=None):
    n=max(2,round(dur*fps)); C[name]=dict(keys=keys,n=n,dur=n/fps,fps=fps,loop=loop,contact=contact,hold=hold,note=note,phys=phys,blink=blink)

CALM='calm'
FALLPOSE=dict(psi=270,k=1.12,wmin=.96,tip=0.,hair=0.,lookx=0.,looky=5.,slidex=0.)   # identical LAST pose of every flight clip
def beat(p0,dphi,lx,cutv=.06,lean=0.,ly_up=-4,inplace=False,slide=8):
    """ONE FULL BEAT. Frame 1 == last frame of the previous clip. The ground blend g is spread over several frames (no vertical pop).
    The first ~4 frames (contact squash) are IDENTICAL in every beat clip (so the code may still pick hop_flip / second_jump
    inside this window without any visible seam). The flip is complete BEFORE the apex."""
    f=lambda x:p0+dphi*x
    SH=dict(k=1.12,wmin=.96,tip=0.)
    up=90 if inplace else 64
    ap=90 if inplace else 15
    sl=0 if inplace else slide
    return [
     K(0,phi=p0,sy=1.0,g=0,face=CALM,**FALLPOSE),
     K(.35,phi=p0,sy=.72,sytop=.88,bulge=.16,face=CALM,g=.7),
     K(.75,phi=p0,sy=.52,sytop=.77,bulge=.29,cut=cutv,flatp=.7,face=CALM,g=1),
     K(1.1,phi=p0,sy=.5,sytop=.76,bulge=.3,cut=cutv+.01,flatp=.7,face=CALM,g=1),
     K(1.7,phi=f(.06)+lean*.5,psi=up,hair=4,lookx=lx*.7,looky=ly_up,slidex=sl*.4,face=CALM,g=.5,**SH),
     K(3.0,phi=f(.58)+lean,psi=up-(0 if inplace else 6),hair=3,lookx=lx,looky=ly_up,slidex=sl*.85,face=CALM,**SH),
     K(4.2,phi=f(1.0)+lean*.3,psi=ap,hair=0,lookx=lx,looky=0,slidex=sl,face=CALM,**SH),
     K(5.4,phi=f(1.0),psi=ap,lookx=lx*.7,looky=2,slidex=sl*.7,face=CALM,**SH),
     K(6.9,phi=f(1.0),face=CALM,**{**FALLPOSE,'lookx':lx*.25,'slidex':sl*.25,'hair':-2}),
     K(8.4,phi=f(1.0),face=CALM,**FALLPOSE),
     K(10,phi=f(1.0),face=CALM,**FALLPOSE)]
add('beat_up',beat(0,0,0,inplace=True),.8,note='in-place bounce, one full beat (contact squash -> flight -> fall). Replaces jump_up+fall+landing in rhythmic play',phys=True)
add('beat_up_blink',beat(0,0,0,inplace=True),.8,note='same as beat_up with a blink in the middle of the fall; play at random every 2-5 s instead of beat_up',phys=True,blink=(5.4,9.2))
add('jump_head',beat(0,180,7,lean=10),.6,note='upright contact -> lateral flight, flips EARLY, falls head-down; the next beat starts on the head (hop_flip)',phys=True)
add('hop_flip',beat(180,180,0,cutv=.06,inplace=True),.6,note='starts from squash ON THE HEAD (flat crown), hops in place and CONTINUES the same rotation direction as the previous flip (180->360), ends falling feet-down',phys=True)
add('second_jump',beat(180,180,7,cutv=.06,lean=8),.6,note='from head squash -> lateral flight, CONTINUES the same rotation direction (180->360); ends falling feet-down',phys=True)

def land(phi,cutv=.05,hairs=4):
    return [
     K(0,phi=phi,psi=-90,k=1.2,tip=-.5,face=CALM),
     K(1.2,phi=phi,sy=.85,sytop=.95,bulge=.08,face=CALM,g=1,hair=hairs),
     K(3,phi=phi,sy=.56,sytop=.8,bulge=.26,cut=cutv,flatp=.7,face=CALM,g=1),
     K(5,phi=phi,sy=1.08,sytop=1.03,bulge=-.05,face=CALM,g=1),
     K(7,phi=phi,sy=.96,sytop=.985,bulge=.025,face=CALM,g=1),
     K(9,phi=phi,sy=1.015,sytop=1.0,bulge=-.008,face=CALM,g=1),
     K(11,phi=phi,face=CALM,g=1)]

add('jump_head_blink',beat(0,180,7,lean=10),.6,note='jump_head with a blink in the fall; use instead of jump_head when the blink timer is due',phys=True,blink=(5.4,9.2))
add('hop_flip_blink',beat(180,180,0,cutv=.06,inplace=True),.6,note='hop_flip with a blink in the fall',phys=True,blink=(5.4,9.2))
add('second_jump_blink',beat(180,180,7,cutv=.06,lean=8),.6,note='second_jump with a blink in the fall',phys=True,blink=(5.4,9.2))

add('landing',land(0),.233,note='FINAL landing / stop only (not for rhythmic bounce)')
add('land_head',land(180,cutv=.06,hairs=0),.233,note='FINAL landing upside down / stop only')

add('idle',[K(0,face=CALM,g=1),K(6,sy=.972,sytop=.985,bulge=.03,phi=1.2,hair=4,face=CALM,g=1),
            K(12,sy=1,phi=0,face=CALM,g=1),K(18,sy=.982,bulge=.02,phi=-1.2,hair=-4,face=CALM,g=1),
            K(24,face=CALM,g=1)],1.667,fps=12,loop=True,note='breathing, no blink')
add('turn_rl',[K(0,lookx=7,face=CALM,g=1),K(4,sy=.97,bulge=.02,lookx=0,face=CALM,g=1),K(8,lookx=-7,face=CALM,g=1)],.4,fps=30,hold=True,note='glance/turn from looking right to looking left (mirror for left->right)')
add('blink',[K(0,face=CALM,g=1),K(1,face=CALM,g=1)],.333,fps=30,note='random every 1.5-3.5 s over idle; eyelid closes and opens (visible transition)')
add('high_jump',[K(0,sy=.64,sytop=.85,bulge=.22,face=CALM,g=1),
     K(2,psi=90,k=1.42,wmin=.82,tip=.6,face=CALM),K(6,psi=90,k=1.32,wmin=.86,tip=.55,face=CALM),
     K(11,psi=90,k=1.24,wmin=.88,tip=.5,face=CALM),K(15,psi=90,k=1.2,wmin=.9,tip=.5,face=CALM)],.5,fps=60,hold=True,note='launch; hold last frame while rising; then fall',phys=True)
add('fall',[K(0,psi=-90,k=1.2,wmin=.9,tip=-.5,hair=5,face=CALM),K(3,psi=-90,k=1.25,hair=8),
            K(6,psi=-90,k=1.22,hair=5),K(9,psi=-90,k=1.25,hair=2),K(12,psi=-90,k=1.2,hair=5)],.4,fps=30,loop=True,note='calm face')

def hit(phi,contact,end_phi,face='blink'):
    """a body part hits a surface. Frame 1 = common approach pose (g=0, no pop), squash is on frames 2-4, rebound, ends in the common falling pose.
    contact 'top' = ceiling, 'right' = right wall (left wall = mirror, scale.x=-1)."""
    ap=270 if contact=='top' else 0                 # stretch axis of the approach (vertical for a ceiling, horizontal for a wall)
    re_=270 if contact=='top' else 180
    FP=dict(FALLPOSE); FP['psi']=ap; FP['looky']=0
    return [
     K(0,phi=phi,g=0,face=CALM,**FP),
     K(.3,phi=phi,sy=.74,sytop=.9,bulge=.15,g=.6,face=CALM),
     K(.7,phi=phi,sy=.52,sytop=.77,bulge=.29,cut=.06,flatp=.7,face=face,g=1),
     K(1.1,phi=phi,sy=.5,sytop=.76,bulge=.3,cut=.07,flatp=.65,face=face,g=1),
     K(1.9,phi=phi,sy=1.08,sytop=1.03,bulge=-.06,face=CALM,g=1),
     K(2.9,phi=phi,sy=.97,sytop=.99,bulge=.02,face=CALM,g=.4),
     K(4.3,phi=(phi+end_phi)/2,psi=re_,k=1.12,wmin=.96,tip=0,looky=3,face=CALM),
     K(6,phi=end_phi,face=CALM,**FALLPOSE),
     K(8,phi=end_phi,face=CALM,**FALLPOSE)]
add('head_hit_top',hit(0,'top',0),.333,contact='top',note='ceiling, HEAD first (upright). ends upright')
add('feet_hit_top',hit(180,'top',180),.333,contact='top',note='ceiling, FEET first (ball is upside down). ends upside down')
add('head_hit_side',hit(90,'right',0),.333,contact='right',note='right wall, HEAD first (phi 90). ends upright. left wall = mirror')
add('feet_hit_side',hit(270,'right',360),.333,contact='right',note='right wall, FEET first (phi 270). ends upright. left wall = mirror')
add('body_hit_side',hit(0,'right',0),.333,contact='right',note='right wall, SIDE of the upright ball (phi 0). ends upright. left = mirror')
add('body_hit_side_inv',hit(180,'right',180),.333,contact='right',note='right wall, side of the UPSIDE-DOWN ball (phi 180). ends upside down. left = mirror')
add('hurt',[K(0,face=CALM,g=1),K(1.5,sy=.7,sytop=.86,bulge=.2,cut=.04,flatp=.7,face='worried',g=1,shear=.05),
 K(3,sy=1.1,sytop=1.04,bulge=-.05,phi=-5,face='worried',g=1,shear=-.05),
 K(5,sy=.92,sytop=.97,bulge=.05,phi=5,face='dizzy',g=1,shear=.05),
 K(7,sy=1.03,phi=-4,face='dizzy',g=1,shear=-.04),K(9,sy=.97,phi=3,face='dizzy',g=1,shear=.03),
 K(11,sy=1.0,phi=-2,face='worried',g=1,shear=-.02),K(13,phi=0,face=CALM,g=1)],.467,fps=30)
add('death',[K(0,face=CALM,g=1),K(2,sy=.78,sytop=.9,bulge=.12,face='worried',g=1),
 K(5,psi=90,k=1.26,wmin=.88,tip=.5,face='dizzy'),K(11,psi=90,k=1.08,phi=220,face='dizzy'),
 K(14,phi=320,face='dead'),K(15,phi=360,sy=.8,sytop=.92,bulge=.1,face='dead',g=1),
 K(16.5,phi=360,sy=.5,sytop=.72,bulge=.3,cut=.04,flatp=.7,face='dead',g=1),
 K(19,phi=360,sy=.78,sytop=.9,bulge=.12,face='dead',g=1),
 K(22,phi=360,sy=.36,sytop=.6,bulge=.5,face='dead',g=1),K(23,phi=360,sy=.3,sytop=.55,bulge=.6,face='dead',g=1)],.667,fps=30,hold=True)
add('win',[K(0,face=CALM,g=1),K(3,sy=.74,sytop=.9,bulge=.15,face='happy',g=1),
 K(6,psi=90,k=1.3,wmin=.86,tip=.5,face='laughing'),K(10,psi=90,k=1.1,phi=180,face='laughing2'),
 K(13,psi=90,k=1.2,phi=330,face='laughing2'),K(15,phi=360,sy=.76,sytop=.9,bulge=.14,face='laughing',g=1),
 K(18,psi=90,k=1.18,phi=360,face='happy'),K(20,phi=360,face='happy'),
 K(21.5,phi=360,sy=.84,sytop=.94,bulge=.07,face='laughing',g=1),K(23,phi=360,face='happy',g=1)],.667,fps=30,note='the ONLY clip with a big smile (exit from the level)')
add('collect',[K(0,face=CALM,g=1),K(1.5,sy=.8,sytop=.93,bulge=.11,face=CALM,g=1),
 K(4,psi=90,k=1.24,wmin=.88,tip=.5,face='laughing'),K(6.5,psi=90,k=1.06,face='laughing'),
 K(9,sy=.92,sytop=.97,bulge=.05,face='happy',g=1),K(11,face=CALM,g=1)],.3,fps=30)

def lid_profile(u):
    """u in 0..1 over a blink window -> (face, lid)"""
    if u<.18: return CALM,.35
    if u<.30: return CALM,.65
    if u<.70: return 'blink',0
    if u<.82: return CALM,.65
    return CALM,.35

def build(name):
    c=C[name]; prm=params(c['keys'],c['n'],c['loop'])
    T=c['keys'][-1][0]; fr=[]
    for i,p in enumerate(prm):
        p=dict(p); face=p.pop('face'); lid=0.0
        t=i/(c['n']-1)*T if not c['loop'] else i/c['n']*T
        if c['blink'] and c['blink'][0]<=t<c['blink'][1]:
            face,lid=lid_profile((t-c['blink'][0])/(c['blink'][1]-c['blink'][0]))
        if name=='blink':
            u=i/(c['n']-1); u=0 if u<.1 else (u-.1)/.8 if u<.9 else 1
            if 0<u<1: face,lid=lid_profile(u)
            else: face,lid=CALM,0
        p['lid']=lid
        fr.append(frame(face,contact=c['contact'],**p))
    return fr

def sheet(frames, cols, path):
    rows=(len(frames)+cols-1)//cols
    W=np.zeros((rows*F,cols*F,3),np.uint8); W[:]=(200,205,215)
    for i,f in enumerate(frames):
        r,c=divmod(i,cols); a=f[...,3:4]/255.
        reg=W[r*F:(r+1)*F,c*F:(c+1)*F]; reg[:]=(f[...,:3]*a+reg*(1-a)).astype(np.uint8)
        cv2.line(W,(c*F,r*F+int(155*Q)),(c*F+F,r*F+int(155*Q)),(150,155,170),1)
        cv2.putText(W,str(i+1),(c*F+4,r*F+14),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,0,0),1)
    Image.fromarray(W).save(path)

if __name__=='__main__':
    os.makedirs('out10',exist_ok=True)
    tot=0
    for nm in C:
        fr=build(nm); sheet(fr,10,f'out10/{nm}_sheet.png'); tot+=len(fr); print(nm,len(fr))
    print('total',tot)
