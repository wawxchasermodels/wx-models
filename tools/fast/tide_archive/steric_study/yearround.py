"""Year-round daily test (2019-2026, gauges only, observed pressure = perfect-pressure case) of whether slow steric terms
improve the held 5-day non-pressure residual persistence that the STOFS-free line uses, at leads 1-9 days.
Train 2019-01..2022-12, test 2023-01..2026-09."""
import json, math, sys, os, datetime as dt
import numpy as np
sys.path.insert(0, "/workspace/wx-models-site/tide_steric_depth_mock_20261115/tools/fast/tide_archive")
import cond_v2 as C
ST=["9439040","9440910","9441102","9442396","9443090","9444090","9444900","9449880","9449424","9447130","9446484"]
FB={"9439040":"9440910","9447130":"9446484","9443090":"9442396"}
B=json.load(open("/tmp/sst_work/hires/ssta_series.json")); K=B["k"]
def load(st):
    h=json.load(open(f"hist/{st}.json")); r=json.load(open(f"/tmp/sst_work/hires/residuals/{st}.json"))
    obs=dict(h["hourly_height"]); obs.update(r["obs"]); pred=dict(h["predictions"]); pred.update(r["pred"])
    pr=dict(h["air_pressure"])
    if os.path.exists(f"press/{st}.json"): pr.update(json.load(open(f"press/{st}.json")))
    return obs,pred,pr
def harmfit(days, y):
    T=np.array([dt.date.fromisoformat(d).toordinal() for d in days],float); w=2*np.pi*(T%365.2425)/365.2425
    yr=np.array([int(d[:4]) for d in days])
    A=np.vstack([np.cos(w),np.sin(w),np.cos(2*w),np.sin(2*w)]+[(yr==Y).astype(float) for Y in sorted(set(yr))]).T
    c,*_=np.linalg.lstsq(A,np.array(y),rcond=None); return c[:4]
def H(c,d):
    w=2*math.pi*(d.toordinal()%365.2425)/365.2425
    return c[0]*math.cos(w)+c[1]*math.sin(w)+c[2]*math.cos(2*w)+c[3]*math.sin(2*w)
LEADS=[1,2,3,5,7,9]
res={}; agg={}
for st in ST:
    obs,pred,pr=load(st)
    if st in FB:
        _,_,pf=load(FB[st]); pf.update(pr); pr=pf
    day={}
    for t,o in obs.items():
        p=pred.get(t); pa=pr.get(t)
        if p is None or pa is None: continue
        ib=C.ib_ft(pa)
        if ib is None: continue
        day.setdefault(t[:10],[]).append(o-p-ib)
    r={dt.date.fromisoformat(k):sum(v)/len(v) for k,v in day.items() if len(v)>=18}
    tr=sorted(d for d in r if d.year<=2022)
    c=harmfit([d.isoformat() for d in tr],[r[d] for d in tr])
    S={dt.date.fromisoformat(k):v for k,v in B["ssta"].get(st,{}).items()}
    k=float(K.get(st,0))
    rows=[]
    for D in sorted(r):
        win=[D-dt.timedelta(i) for i in range(5)]
        if not all(w in r for w in win): continue
        P0=sum(r[w] for w in win)/5
        Hbar=sum(H(c,w) for w in win)/5
        sw=[S.get(w-dt.timedelta(2)) for w in win]
        dS=(sw[0]-sum(sw)/5) if all(x is not None for x in sw) else None
        for L in LEADS:
            Tg=D+dt.timedelta(L)
            if Tg not in r: continue
            rows.append((D,L,r[Tg],P0,H(c,Tg)-Hbar,dS))
    # seasonal-k / gain for dS fitted on train by month (depth proxy): target r-P0 vs dS
    g={}
    for m in range(1,13):
        X=[(row[5],row[2]-row[3]) for row in rows if row[0].year<=2022 and row[0].month==m and row[5] is not None and row[1]==3]
        if len(X)>30:
            x=np.array([a for a,_ in X]); y=np.array([b for _,b in X]); g[m]=float((x*y).sum()/(x*x).sum())
    out={}
    for L in LEADS:
        te=[row for row in rows if row[0].year>=2023 and row[1]==L and row[5] is not None]
        e=lambda f: float(np.mean([abs(f(row)-row[2]) for row in te]))
        out[L]={"n":len(te),
          "persist":e(lambda q:q[3]),
          "seas":e(lambda q:q[3]+q[4]),
          "dsst_k":e(lambda q:q[3]+k*q[5]),
          "dsst_gain_month":e(lambda q:q[3]+g.get(q[0].month,0)*q[5])}
        for kk,v in out[L].items():
            if kk!="n": agg.setdefault(L,{}).setdefault(kk,[]).append((v,len(te)))
    res[st]={"leads":out,"gain_by_month":g,"k":k}
    print(st, " ".join(f"L{L}: P{out[L]['persist']:.3f} S{out[L]['seas']:.3f} K{out[L]['dsst_k']:.3f} G{out[L]['dsst_gain_month']:.3f}" for L in (1,3,9)), " gains", {m:round(v,2) for m,v in g.items()})
summ={L:{m:sum(v*n for v,n in vs)/sum(n for _,n in vs) for m,vs in d.items()} for L,d in agg.items()}
print("ALL", json.dumps({L:{m:round(v,4) for m,v in d.items()} for L,d in summ.items()}))
json.dump({"stations":res,"overall":summ,"note":__doc__},open("yearround.json","w"),indent=1)
