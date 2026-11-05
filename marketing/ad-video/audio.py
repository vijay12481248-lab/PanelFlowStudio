"""Synthesizes the ad soundtrack (cinematic build, hits on scene cuts). Usage: python audio.py out.wav"""
import sys, numpy as np
from scipy.signal import butter, lfilter
from scipy.io import wavfile
SR=44100; DUR=34.0; N=int(SR*DUR); rng=np.random.default_rng(3)
t=np.arange(N)/SR; L=np.zeros(N); R=np.zeros(N)
def env(n,a,d): x=np.arange(n)/SR; return np.minimum(x/a,1)*np.exp(-x/d)
def add(sig,at,pan=0.0,g=1.0):
    i=int(at*SR); sig=sig[:max(0,N-i)]; 
    if i>=N: return
    L[i:i+len(sig)]+=sig*g*(1-max(pan,0)); R[i:i+len(sig)]+=sig*g*(1+min(pan,0))
def lp(x,f): b,a=butter(2,f/(SR/2)); return lfilter(b,a,x)
def hp(x,f): b,a=butter(2,f/(SR/2),'high'); return lfilter(b,a,x)
mid=lambda n:440*2**((n-69)/12)
BPM=100; beat=60/BPM
# pad: Am F C G, 2 bars (4.8s) each
chords=[[57,60,64],[53,57,60],[48,52,55],[55,59,62]]
for k in range(int(DUR/4.8)+1):
    at=k*4.8; n=int(SR*5.6); x=np.arange(n)/SR; c=chords[k%4]; s=np.zeros(n)
    for nt in c:
        for det in (-.15,.15):
            f=mid(nt+12)*2**(det/12)
            s+=sum(np.sin(2*np.pi*f*h*x)/h**1.4 for h in (1,2,3,4))
    e=np.minimum(x/1.6,1)*np.minimum((5.6-x)/1.6,1)
    g=.045*np.interp(at,[0,9,20,29],[.7,1,1.25,1.4])
    add(lp(s,2400)*e,at,0,g)
# sub bass root, from 9s
for k in range(int(DUR/4.8)+1):
    at=k*4.8
    if at<8: continue
    n=int(SR*4.8); x=np.arange(n)/SR; add(np.sin(2*np.pi*mid(chords[k%4][0]-12)*x)*np.minimum(x/.2,1)*np.minimum((4.8-x)/.4,1),at,0,.22)
# arpeggio plucks from 4.2s
for i in range(int(4.2/(beat/4)),int(29.4/(beat/4))):
    at=i*beat/4; c=chords[int(at/4.8)%4]; nt=c[i%3]+12*(1+(i//3)%2)
    n=int(SR*.5); x=np.arange(n)/SR; s=np.sin(2*np.pi*mid(nt)*x)+.4*np.sin(2*np.pi*mid(nt)*2*x)
    add(s*np.exp(-x/.12)*(1-np.exp(-x/.004)),at,np.sin(i)*.5,.05*(.5 if at<9 else 1))
# kick + hats + clap
for i in range(int(9/beat),int(29.4/beat)):
    at=i*beat; n=int(SR*.4); x=np.arange(n)/SR
    ph=2*np.pi*np.cumsum(45+90*np.exp(-x/.04))/SR; add(np.sin(ph)*np.exp(-x/.16),at,0,.55)
    if i%2==1 and at>13: add(lp(rng.normal(0,1,n),3500)*hp(np.exp(-x/.07),1)*.5,at,0,.25)
for i in range(int(14.5/(beat/2)),int(29.4/(beat/2))):
    at=i*beat/2; n=int(SR*.06); add(hp(rng.normal(0,1,n),7000)*np.exp(-np.arange(n)/SR/.015),at,.3,.12)
def riser(at,dur,g=.35):
    n=int(SR*dur); x=np.arange(n)/SR; z=rng.normal(0,1,n); out=np.zeros(n); 
    for lo,hi in zip(np.linspace(300,6000,12)[:-1],np.linspace(300,6000,12)[1:]): pass
    s=hp(z,1500)*(x/dur)**2; add(s,at,0,g)
def hit(at,g=.7):
    n=int(SR*2.5); x=np.arange(n)/SR
    ph=2*np.pi*np.cumsum(38+120*np.exp(-x/.07))/SR; b=np.sin(ph)*np.exp(-x/.55)
    add(b+lp(rng.normal(0,1,n),1800)*np.exp(-x/.35)*.5,at,0,g)
def whoosh(at,dur=.7,g=.3):
    n=int(SR*dur); x=np.arange(n)/SR; z=rng.normal(0,1,n); s=hp(lp(z,5000),600)*np.sin(np.pi*x/dur)**2; add(s,at,0,g)
riser(3.0,1.3);hit(4.2,.35);whoosh(5.9);whoosh(6.0,1.0,.25);riser(8.0,1.0);hit(9.0,.6)
for i in range(5): add(np.sin(2*np.pi*mid(81+i*2)*np.arange(int(SR*.4))/SR)*np.exp(-np.arange(int(SR*.4))/SR/.12),9.9+i*.7,0,.06)
riser(13.4,1.1);hit(14.5,.55);whoosh(14.4);riser(19.5,1.0);hit(20.5,.5);whoosh(20.4)
riser(24.0,.9,.25);add(rng.normal(0,1,int(SR*.05))*np.exp(-np.arange(int(SR*.05))/SR/.01)*0.3,25.5)
whoosh(25.85);riser(27.8,1.5,.3);hit(29.4,.95)
# final shimmer chord
n=int(SR*5); x=np.arange(n)/SR
for nt in (57,64,69,72,76): add(np.sin(2*np.pi*mid(nt)*x)*np.minimum(x/.05,1)*np.exp(-x/2.2),29.4,np.random.uniform(-.4,.4),.07)
fade=np.clip((DUR-t)/1.2,0,1)*np.clip(t/.3,0,1)
out=np.stack([L*fade,R*fade],1); out=np.tanh(out*1.1); out/=np.abs(out).max()/0.89
wavfile.write(sys.argv[1],SR,(out*32767).astype(np.int16))
