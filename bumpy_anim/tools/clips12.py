import numpy as np, cv2, json, os
from PIL import Image
from engine2 import *

C={}
def add(name,keys,dur,fps=60,loop=False,contact='bottom',hold=False,note='',phys=False,blink=None,kind='misc'):
    n=max(2,round(dur*fps)); C[name]=dict(keys=keys,n=n,dur=n/fps,fps=fps,loop=loop,contact=contact,hold=hold,note=note,phys=phys,blink=blink,kind=kind)
CALM='calm'
FALLPOSE=dict(psi=270,k=1.0,wmin=1.0,tip=0.,hair=0.,lookx=0.,looky=4.,slidex=0.)
SQ=dict(sy=.45,sytop=.73,bulge=.35,cut=.075,flatp=.7,g=1)           # max squash on the surface (same in contact_* and first key of every flight_*)

def contact(phi):
    return [K(0,phi=phi,g=0,face=CALM,**FALLPOSE),
            K(2,phi=phi,sy=.82,sytop=.94,bulge=.08,face=CALM,g=.5),
            K(4.5,phi=phi,sy=.58,sytop=.8,bulge=.26,cut=.06,flatp=.7,face=CALM,g=1),
            K(7.5,phi=phi,sy=.47,sytop=.74,bulge=.33,cut=.072,flatp=.7,face=CALM,g=1),
            K(10,phi=phi,face=CALM,**SQ)]
add('contact_feet',contact(0),.10,fps=140,hold=True,kind='contact',phys=True,note='TOUCH on the feet: round -> squash on the surface. Play from the moment of the accepted touch, hold last frame for the dwell (0.10 s)')
add('contact_head',contact(180),.10,fps=140,hold=True,kind='contact',phys=True,note='TOUCH on the head (upside down): round -> squash with flat crown. Same timing (0.10 s)')

def flight(p0,dphi,lx,flip,lean=0.,inplace=False,slide=8):
    f=lambda x:p0+dphi*x
    up=90 if inplace else 64
    sl=0
    P=[(1.0,.03),(2.2,.12),(4.5,.50),(7.2,.88),(9.2,1.0)] if flip=='late' else [(1.0,.06),(2.2,.55),(3.6,1.0),(5.0,1.0),(9.2,1.0)]
    ph=dict(P)
    return [
     K(0,phi=p0,face=CALM,**SQ),
     K(.5,phi=p0,sy=1.12,sytop=1.05,bulge=-.09,face=CALM,g=.6),
     K(1.0,phi=f(ph[1.0])+lean*.6,psi=up,k=1.2,wmin=.9,tip=.35,hair=3,lookx=lx*.7,looky=-4,slidex=sl*.4,face=CALM),
     K(2.2,phi=f(ph[2.2])+lean,psi=up,k=1.05,wmin=.98,hair=2,lookx=lx,looky=-4,slidex=sl*.85,face=CALM),
     K(4.5,phi=f(4.5/9.2*1.0 if flip=='late' else 1.0) if False else f(.5 if flip=='late' else 1.0)+lean*.4,k=1.0,wmin=1.0,lookx=lx,looky=0,slidex=sl,face=CALM),
     K(7.2,phi=f(.88 if flip=='late' else 1.0),psi=270,k=1.035,wmin=.99,hair=-2,lookx=lx*.5,looky=3,slidex=sl*.5,face=CALM),
     K(9.2,phi=f(1.0),face=CALM,**{**FALLPOSE,'lookx':lx*.2,'slidex':sl*.2}),
     K(10,phi=f(1.0),face=CALM,**FALLPOSE)]
BL=(3.6,6.9)
D=.52
fl=[('flight_up',0,0,0,'late',0,True,'in place, feet->feet (round ball). Next contact: contact_feet'),
    ('flight_feet_to_head',0,180,7,'late',8,False,'side jump from the feet, rotation completes exactly at touch -> lands on the HEAD (3009 frames 1-9). Next contact: contact_head'),
    ('flight_head_hop',180,180,0,'early',0,True,'in place from the head: flips onto the feet before the apex (3009 frames 10-14). Next contact: contact_feet'),
    ('flight_head_side',180,180,7,'late',6,False,'side jump from the head, same rotation direction continues (180->360); at mid-flight the ball is turned ~90 deg (like flight_feet_to_head), rotation completes exactly at touch. Next contact: contact_feet')]
for nm,p0,dp,lx,flip,lean,inp,note in fl:
    for suf,bl in (('',None),('_blink',BL)):
        add(nm+suf,flight(p0,dp,lx,flip,lean=lean,inplace=inp),D,fps=66,kind='flight',phys=True,blink=bl,note=note+(' (with a quick blink, 0.17 s)' if bl else ''))

def land(phi,cutv=.08,hairs=4):
    return [K(0,phi=phi,psi=-90,k=1.2,tip=-.5,face=CALM),
     K(1.2,phi=phi,sy=.85,sytop=.95,bulge=.08,face=CALM,g=1,hair=hairs),
     K(2.8,phi=phi,sy=.5,sytop=.74,bulge=.32,cut=cutv-.01,flatp=.7,face=CALM,g=1),
     K(4,phi=phi,sy=.4,sytop=.68,bulge=.4,cut=cutv,flatp=.7,face=CALM,g=1),
     K(5.2,phi=phi,sy=.4,sytop=.68,bulge=.4,cut=cutv,flatp=.7,face=CALM,g=1),
     K(7,phi=phi,sy=1.14,sytop=1.06,bulge=-.1,face=CALM,g=1),
     K(9,phi=phi,sy=.9,sytop=.96,bulge=.07,face=CALM,g=1),
     K(11,phi=phi,sy=1.04,sytop=1.01,bulge=-.02,face=CALM,g=1),
     K(13,phi=phi,sy=.985,bulge=.008,face=CALM,g=1),
     K(15,phi=phi,face=CALM,g=1)]
add('landing',land(0),.3,fps=60,kind='stop',note='HEAVY landing after a long fall: ball is clearly flattened onto the floor, then rebounds and settles. Not for rhythmic bounce')
add('land_head',land(180,cutv=.09,hairs=0),.3,fps=60,kind='stop',note='HEAVY landing upside down after a long fall')

add('idle',[K(0,face=CALM,g=1),K(6,sy=.972,sytop=.985,bulge=.03,phi=1.2,hair=4,face=CALM,g=1),K(12,sy=1,phi=0,face=CALM,g=1),K(18,sy=.982,bulge=.02,phi=-1.2,hair=-4,face=CALM,g=1),K(24,face=CALM,g=1)],1.667,fps=14,loop=True,kind='idle',note='breathing, no blink')
# 2D half-turn: face features slide inside the flat outline (no sphere / no 3D)
add('turn_in',[K(0,face=CALM,g=1),K(3,lookx=3.5,face=CALM,g=1),K(6,lookx=7,face=CALM,g=1)],.12,fps=75,hold=True,kind='turn',note='2D: eyes look to the RIGHT (half-turn, flat, no 3D) (mirror for left). Replaces nothing in physics')
add('turn_out',[K(0,lookx=7,face=CALM,g=1),K(3,lookx=3,face=CALM,g=1),K(6,face=CALM,g=1)],.12,fps=75,hold=True,kind='turn',note='2D: from half-turn right back to front')
add('turn_rl',[K(0,lookx=7,face=CALM,g=1),K(3,lookx=2,sy=.985,face=CALM,g=1),K(5,sy=.975,bulge=.02,face=CALM,g=1),K(7,lookx=-2,sy=.985,face=CALM,g=1),K(10,lookx=-7,face=CALM,g=1)],.2,fps=75,hold=True,kind='turn',note='2D: from facing right to facing left through the front (mirror for left->right)')
add('half_turn_loop',[K(0,lookx=7,face=CALM,g=1),K(3,lookx=7,sy=.985,bulge=.015,phi=1,face=CALM,g=1),K(6,lookx=7,face=CALM,g=1),K(9,lookx=7,sy=.988,bulge=.012,phi=-1,face=CALM,g=1),K(12,lookx=7,face=CALM,g=1)],1.0,fps=18,loop=True,kind='turn',note='2D half-turn loop (looking RIGHT); mirror for left')

def lid_profile(u):
    if u<.18: return CALM,.35
    if u<.30: return CALM,.65
    if u<.70: return 'blink',0
    if u<.82: return CALM,.65
    return CALM,.35
add('blink',[K(0,face=CALM,g=1),K(1,face=CALM,g=1)],.16,fps=75,kind='blink',note='fast blink 0.16 s over idle; random every 1.5-3.5 s')
HSQ=dict(sy=.38,sytop=.66,bulge=.42,cut=.09,flatp=.7,g=1)        # deep squash of the high jump (same in anticipation_high and first key of high_jump)
add('anticipation',[K(0,face=CALM,g=1),K(2,sy=.9,sytop=.97,bulge=.04,face=CALM,g=1),K(5,sy=.62,sytop=.83,bulge=.2,cut=.05,flatp=.7,face=CALM,g=1),K(8,sy=.49,sytop=.75,bulge=.32,cut=.07,flatp=.7,face=CALM,g=1),K(10,face=CALM,**SQ)],.16,fps=90,hold=True,kind='anticipation',note='squat from rest (idle) before the first jump; last frame == first frame of any flight_*; hold until launch')
add('anticipation_high',[K(0,face=CALM,g=1),K(2,sy=.92,sytop=.98,bulge=.03,looky=-3,face=CALM,g=1),K(5,sy=.6,sytop=.8,bulge=.24,cut=.06,flatp=.7,face=CALM,g=1),K(8,sy=.42,sytop=.7,bulge=.38,cut=.085,flatp=.7,face=CALM,g=1),K(10,face=CALM,**HSQ)],.22,fps=90,hold=True,kind='anticipation',note='deep squat before the HIGH jump; last frame == first frame of high_jump')
add('high_jump',[K(0,face=CALM,**HSQ),K(.5,sy=1.15,sytop=1.06,bulge=-.1,face=CALM,g=.6),K(1.3,psi=90,k=1.5,wmin=.78,tip=.65,hair=4,looky=-5,face=CALM),K(3.5,psi=90,k=1.38,wmin=.82,tip=.55,hair=3,looky=-4,face=CALM),K(6.5,psi=90,k=1.2,wmin=.92,tip=.3,hair=2,looky=-2,face=CALM),K(10,psi=90,k=1.08,wmin=.97,tip=0,hair=0,looky=0,face=CALM)],.5,fps=90,hold=True,kind='flight',phys=True,note='starts from deep squash (after anticipation_high), big stretch, relaxes to round; hold last frame while rising; then fall')
add('fall',[K(0,psi=-90,k=1.08,wmin=.97,tip=0,hair=3,looky=4,face=CALM),K(3,psi=-90,k=1.11,hair=5),K(6,psi=-90,k=1.08,hair=3),K(9,psi=-90,k=1.11,hair=1),K(12,psi=-90,k=1.08,hair=3)],.4,fps=30,loop=True,kind='flight',note='slightly stretched along the fall, hair flutters, calm face')

add('fall_surprise_in',[K(0,psi=-90,k=1.08,wmin=.97,hair=3,looky=4,face=CALM),K(2,psi=-90,k=1.14,wmin=.95,hair=6,looky=5,face='surprised'),K(5,psi=-90,k=1.1,hair=5,looky=5,face='surprised')],.12,fps=75,hold=True,kind='flight',note='start of a LONG / unexpected fall (over a pit, from a height): calm -> surprised (open mouth, wide eyes), slight stretch. Then fall_surprised')
add('fall_surprised',[K(0,psi=-90,k=1.1,wmin=.96,hair=5,looky=5,face='surprised'),K(3,psi=-90,k=1.14,hair=7,face='surprised'),K(6,psi=-90,k=1.1,hair=5,face='surprised'),K(9,psi=-90,k=1.14,hair=3,face='surprised'),K(12,psi=-90,k=1.1,hair=5,face='surprised')],.4,fps=30,loop=True,kind='flight',note='loop of a long fall with the surprised face. Landing after it: landing (soft squash)')

def hit(phi,contact,end_phi,face='blink',start=None,light=False):
    a,b,c_,d_=(.76,.91,.14,.03) if light else (.52,.77,.29,.06)
    st=phi if start is None else start
    re_=270 if contact=='top' else 180
    d=0 if start is None else .6
    return [K(0,phi=st,g=0,face=CALM,**FALLPOSE),
     *([K(d,phi=phi,g=.3,face=CALM,**FALLPOSE)] if d else []),
     K(d+.3,phi=phi,sy=.74,sytop=.9,bulge=.15,g=.7,face=CALM),
     K(d+.6,phi=phi,sy=a,sytop=b,bulge=c_,cut=d_,flatp=.7,face=face,g=1),
     K(d+1.0,phi=phi,sy=a-.02,sytop=b-.01,bulge=c_+.01,cut=d_+.01,flatp=.65,face=face,g=1),
     K(d+1.35,phi=phi,sy=a-.02,sytop=b-.01,bulge=c_+.01,cut=d_+.01,flatp=.65,face=face,g=1),
     K(d+1.6,phi=phi,sy=1.08,sytop=1.03,bulge=-.06,face=CALM,g=.8),
     K(d+2.6,phi=(phi+end_phi)/2,psi=re_,k=1.08,wmin=.97,tip=0,looky=3,face=CALM),
     K(d+4.5,phi=end_phi,face=CALM,**FALLPOSE),
     K(d+6,phi=end_phi,face=CALM,**FALLPOSE)]
add('head_hit_top',hit(0,'top',0,light=True),.4,fps=50,contact='top',kind='hit',note='ceiling, HEAD first (upright). ends upright')
add('feet_hit_top',hit(180,'top',180,light=True),.4,fps=50,contact='top',kind='hit',note='ceiling, FEET first (upside down). ends upside down')
add('head_hit_side_up',hit(90,'right',0,start=0),.35,fps=50,contact='right',kind='hit',note='right wall, was UPRIGHT, hits with HEAD. ends upright. left wall = mirror')
add('feet_hit_side_up',hit(270,'right',360,start=360),.35,fps=50,contact='right',kind='hit',note='right wall, was UPRIGHT, hits with FEET. ends upright. left wall = mirror')
add('head_hit_side_inv',hit(90,'right',0,start=180),.35,fps=50,contact='right',kind='hit',note='right wall, was UPSIDE DOWN, hits with HEAD. ends upright')
add('feet_hit_side_inv',hit(270,'right',360,start=180),.35,fps=50,contact='right',kind='hit',note='right wall, was UPSIDE DOWN, hits with FEET. ends upright')
add('hurt',[K(0,face=CALM,g=1),K(1.5,sy=.7,sytop=.86,bulge=.2,cut=.04,flatp=.7,face='worried',g=1,shear=.05),K(3,sy=1.1,sytop=1.04,bulge=-.05,phi=-5,face='worried',g=1,shear=-.05),K(5,sy=.92,sytop=.97,bulge=.05,phi=5,face='dizzy',g=1,shear=.05),K(7,sy=1.03,phi=-4,face='dizzy',g=1,shear=-.04),K(9,sy=.97,phi=3,face='dizzy',g=1,shear=.03),K(11,sy=1.0,phi=-2,face='worried',g=1,shear=-.02),K(13,phi=0,face=CALM,g=1)],.467,fps=36,kind='event')
add('death',[K(0,face=CALM,g=1),K(2,sy=.78,sytop=.9,bulge=.12,face='worried',g=1),K(5,psi=90,k=1.26,wmin=.88,tip=.5,face='dizzy'),K(11,psi=90,k=1.08,phi=220,face='dizzy'),K(14,phi=320,face='dead'),K(15,phi=360,sy=.8,sytop=.92,bulge=.1,face='dead',g=1),K(16.5,phi=360,sy=.5,sytop=.72,bulge=.3,cut=.04,flatp=.7,face='dead',g=1),K(19,phi=360,sy=.78,sytop=.9,bulge=.12,face='dead',g=1),K(22,phi=360,sy=.36,sytop=.6,bulge=.5,face='dead',g=1),K(23,phi=360,sy=.3,sytop=.55,bulge=.6,face='dead',g=1)],.667,fps=36,hold=True,kind='event')
add('win',[K(0,face=CALM,g=1),K(3,sy=.74,sytop=.9,bulge=.15,face='happy',g=1),K(6,psi=90,k=1.3,wmin=.86,tip=.5,face='laughing'),K(10,psi=90,k=1.1,phi=180,face='laughing2'),K(13,psi=90,k=1.2,phi=330,face='laughing2'),K(15,phi=360,sy=.76,sytop=.9,bulge=.14,face='laughing',g=1),K(18,psi=90,k=1.18,phi=360,face='happy'),K(20,phi=360,face='happy'),K(21.5,phi=360,sy=.84,sytop=.94,bulge=.07,face='laughing',g=1),K(23,phi=360,face='happy',g=1)],.667,fps=36,kind='event',note='the ONLY clip with a big smile (exit from the level)')
add('collect',[K(0,face=CALM,g=1),K(1.5,sy=.8,sytop=.93,bulge=.11,face=CALM,g=1),K(4,psi=90,k=1.24,wmin=.88,tip=.5,face='laughing'),K(6.5,psi=90,k=1.06,face='laughing'),K(9,sy=.92,sytop=.97,bulge=.05,face='happy',g=1),K(11,face=CALM,g=1)],.3,fps=60,kind='event')

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
def sheet(frames,cols,path):
    rows=(len(frames)+cols-1)//cols
    W=np.zeros((rows*F,cols*F,3),np.uint8); W[:]=(200,205,215)
    for i,f in enumerate(frames):
        r,c=divmod(i,cols); a=f[...,3:4]/255.
        reg=W[r*F:(r+1)*F,c*F:(c+1)*F]; reg[:]=(f[...,:3]*a+reg*(1-a)).astype(np.uint8)
        cv2.line(W,(c*F,r*F+int(155*Q)),(c*F+F,r*F+int(155*Q)),(150,155,170),1)
        cv2.putText(W,str(i+1),(c*F+4,r*F+14),cv2.FONT_HERSHEY_SIMPLEX,0.4,(0,0,0),1)
    Image.fromarray(W).save(path)
if __name__=='__main__':
    os.makedirs('out12',exist_ok=True); tot=0
    for nm in C:
        fr=build(nm); sheet(fr,12,f'out12/{nm}_sheet.png'); tot+=len(fr); print(nm,len(fr))
    print('total',tot)

NEXT={'contact_feet':'flight_up | flight_feet_to_head (by input at the end of the dwell)','contact_head':'flight_head_hop | flight_head_side','flight_up':'contact_feet','flight_up_blink':'contact_feet','flight_feet_to_head':'contact_head','flight_feet_to_head_blink':'contact_head','flight_head_hop':'contact_feet','flight_head_hop_blink':'contact_feet','flight_head_side':'contact_feet','flight_head_side_blink':'contact_feet',
 'anticipation':'flight_up | flight_feet_to_head','anticipation_high':'high_jump','high_jump':'fall (hold last frame while rising)','fall':'contact_feet | landing | hurt | death','fall_surprise_in':'fall_surprised','fall_surprised':'landing (soft squash) | hurt | death','landing':'idle (or anticipation if input) - ONLY after a long fall','land_head':'idle (after flip to the feet)','idle':'blink (random 1.5-3.5 s) | anticipation | turn_in','blink':'idle','turn_in':'half_turn_loop','half_turn_loop':'turn_out | turn_rl','turn_out':'idle','turn_rl':'half_turn_loop (mirrored)',
 'head_hit_top':'fall / contact_feet (ends upright)','feet_hit_top':'fall / contact_feet (ends upside down -> contact_head)','head_hit_side_up':'fall','feet_hit_side_up':'fall','head_hit_side_inv':'fall','feet_hit_side_inv':'fall','hurt':'idle','death':'hold last frame','win':'hold / level exit','collect':'previous state'}
