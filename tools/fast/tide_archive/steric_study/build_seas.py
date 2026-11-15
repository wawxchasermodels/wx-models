import json, math, sys, os, datetime as dt
sys.path.insert(0, "/workspace/wx-models-site/tide_steric_depth_mock_20261115/tools/fast/tide_archive")
import cond_v2 as C
import numpy as np
ST=["9439040","9440910","9441102","9442396","9443090","9444090","9444900","9449880","9449424","9447130","9446484"]
FB={"9439040":"9440910","9447130":"9446484","9443090":"9442396"}
def load(st):
    h=json.load(open(f"hist/{st}.json")); r=json.load(open(f"/tmp/sst_work/hires/residuals/{st}.json"))
    obs=dict(h["hourly_height"]); obs.update(r["obs"]); pred=dict(h["predictions"]); pred.update(r["pred"])
    pr=dict(h["air_pressure"]); 
    if os.path.exists(f"press/{st}.json"): pr.update(json.load(open(f"press/{st}.json")))
    return obs,pred,pr
out={}
for st in ST:
    obs,pred,pr=load(st)
    if st in FB:
        _,_,pf=load(FB[st]); pf.update(pr); pr=pf
    day={}
    for t,o in obs.items():
        if t[:10]>"2026-09-30": continue
        p=pred.get(t); pa=pr.get(t)
        if p is None or pa is None: continue
        ib=C.ib_ft(pa)
        if ib is None: continue
        day.setdefault(t[:10],[]).append(o-p-ib)
    d=[(k,sum(v)/len(v)) for k,v in day.items() if len(v)>=18]
    T=np.array([dt.datetime.fromisoformat(k+"T12:00:00+00:00").timestamp()*1000 for k,_ in d]); y=np.array([v for _,v in d])
    w=2*np.pi*((T/86400000.0)%365.2425)/365.2425
    yr=np.array([int(k[:4]) for k,_ in d])
    cols=[np.cos(w),np.sin(w),np.cos(2*w),np.sin(2*w)]+[(yr==Y).astype(float) for Y in sorted(set(yr))]  # yearly means absorb trend/ENSO
    A=np.vstack(cols).T; c,*_=np.linalg.lstsq(A,y,rcond=None)
    amp1=math.hypot(c[0],c[1]); 
    # value and slope on Nov 7
    wn=2*math.pi*((dt.datetime(2026,11,7,tzinfo=dt.timezone.utc).timestamp()/86400)%365.2425)/365.2425
    slope=(-c[0]*math.sin(wn)+c[1]*math.cos(wn)+2*(-c[2]*math.sin(2*wn)+c[3]*math.cos(2*wn)))*2*math.pi/365.2425
    out[st]={"a1":c[0],"b1":c[1],"a2":c[2],"b2":c[3],"n_days":len(d),"first":min(k for k,_ in d),"amp_annual_ft":amp1,"slope_ft_per_day_nov7":slope}
    print(st,len(d),min(k for k,_ in d),"annual amp %.3f ft  semi %.3f  Nov7 slope %.4f ft/day"%(amp1,math.hypot(c[2],c[3]),slope))
json.dump(out,open("seasonal_harmonics.json","w"),indent=1)
