#!/usr/bin/env python3
"""Steric / warm-water-depth study (Benjamin t3090u, 2026-11-15). MOCK. Same issues, leads and scoring as
sst_stofsfree_backtest.py (which gives the 0.199 ft baseline); adds candidate terms on top of the STOFS-free default:

  free      baseline STOFS-free default (must reproduce backtest_stofsfree.json "free")
  dsst30    W evaluated hour by hour inside the 5-day offset window (k * 30-day SSTA at each hour) -> net term
            k*(S30 now - mean S30 over window), faded in over 12 h so the line still starts on the newest obs
  dsstd     same with daily SSTA (k*(newest daily SSTA - mean daily SSTA over window)) -> faster SST changes
  seas      seasonal (annual+semiannual) climatology of the non-pressure residual, 2019-01..2026-09 (no Oct/Nov 2026
            leakage); term = H(t) - mean H over window, start pinned to obs
  sla       offshore altimetry sea level anomaly change (NOAA CoastWatch blended SSH, public): SLA now - mean SLA
            over window, x fitted gain, faded in
  hc        depth-weighted: dsstd scaled by MLD(month)/MLD(Nov) - identical to dsstd in a Nov-only backtest (reported
            for completeness)

Original header follows.

Head-to-head 3-72 h backtest:

  c1         current Conditional (STOFS swl + 12 h fade + 30-day offset)
  off_fixed  fixed STOFS-backbone default (c1 + version D SST + faded AIFS-GFS IB swap, no wind)
  on_fixed   fixed STOFS-backbone wind-on (off_fixed + wind_comp)
  free       NEW STOFS-free default: official + AIFS/obs IB + k*SSTA + 5-day unexplained offset + 12 h leftover
  free_on    NEW STOFS-free + wind only
"""
from __future__ import annotations
import json, math, os, sys, glob, datetime as dt
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cond_v2 as C
import sst_warmwater_backtest as B

HIRES = "/tmp/sst_work/hires"
SSTA = os.path.join(HIRES, "ssta_series.json")
OUT = os.path.join(HERE, "backtest_steric_depth.json")
SEAS = os.path.join(HERE, "steric_study", "seasonal_harmonics.json")
SLA = os.path.join(HERE, "steric_study", "sla_station.json")
HR = 3600_000
DAY = 24 * HR
LEAD_MIN, LEAD_MAX = 3, 72
MODES = ("c1", "off_fixed", "on_fixed", "free", "free_on", "official", "dsst30", "dsstd", "seas", "sla", "seas_dsstd")
NEW = ("dsst30", "dsstd", "seas", "sla", "seas_dsstd")

def ssta_at(bundle, sid, issue_ms):
    ser = (bundle.get("ssta") or {}).get(sid) or {}
    if not ser:
        return None
    latent = int(bundle.get("latent_d") or 2)
    cutoff = dt.datetime.fromtimestamp(issue_ms/1000, dt.timezone.utc).date() - dt.timedelta(days=latent)
    # 30-day mean of available anomalies ending at cutoff
    days = []
    d = cutoff
    for _ in range(40):
        key = d.isoformat()
        if key in ser:
            days.append(ser[key])
            if len(days) >= 30:
                break
        d -= dt.timedelta(days=1)
    if len(days) < 5:
        # latest single day
        keys = [k for k in ser if k <= cutoff.isoformat()]
        if not keys:
            return None
        return ser[max(keys)], 1
    return sum(days[:30])/min(30, len(days)), len(days)

def s30_on(ser, day, latent):
    d = day - dt.timedelta(days=latent); vals = []
    for _ in range(40):
        v = ser.get(d.isoformat())
        if v is not None:
            vals.append(v)
            if len(vals) >= 30: break
        d -= dt.timedelta(days=1)
    return sum(vals)/len(vals) if len(vals) >= 5 else None

def daily_on(ser, day, latent):
    d = day - dt.timedelta(days=latent)
    for _ in range(5):
        v = ser.get(d.isoformat())
        if v is not None: return v
        d -= dt.timedelta(days=1)
    return None

def harm(h, t_ms):
    if not h: return 0.0
    w = 2*math.pi*((t_ms/86400000.0) % 365.2425)/365.2425
    return h["a1"]*math.cos(w) + h["b1"]*math.sin(w) + h["a2"]*math.cos(2*w) + h["b2"]*math.sin(2*w)

def window_term(fn, T0):
    """value now minus hourly mean over the 5-day offset window [T0-5d, T0] (the window offset5 averages)."""
    t = T0 - 5*DAY; vs = []
    while t <= T0:
        v = fn(t)
        if v is not None: vs.append(v)
        t += HR
    now = fn(T0)
    if now is None or not vs: return None
    return now - sum(vs)/len(vs)

def offset5(obs, pred, p_obs_fn, W, t0, ib_fallback):
    s = e = 0.0
    n = 0
    t = t0 - 5*DAY
    while t <= t0:
        o = B.interp(obs, t)
        p = B.interp(pred, t)
        if o is not None and p is not None:
            ib = C.ib_ft(p_obs_fn(t))
            if ib is None:
                ib = ib_fallback
            if ib is not None:
                s += (o - p) - ib - W
                n += 1
        t += HR
    return (s/n) if n else 0.0, n

def main():
    if not os.path.exists(SSTA):
        print("missing", SSTA, "- run sst_source_compare.py first")
        return 1
    bundle = json.load(open(SSTA))
    k_map = bundle.get("k") or {}
    aifs_cache = B.load_all_aifs()
    anom_cache = B.load_anom_cache()
    gfs = json.load(open(B.GFS))
    gfs_pts = {}
    for sid, rec in gfs.items():
        gfs_pts[sid] = [(B.ms_utc(t), float(p)) for t, p in zip(rec["time"], rec["pressure_msl"]) if p is not None]

    obs, pred, air = {}, {}, {}
    all_issues = {}
    for sid in B.STATIONS:
        wl = B.load_coops_product("water_level", sid)
        pr = B.load_coops_product("predictions", sid)
        obs[sid] = sorted((t, v) for t, v in wl.items())
        pred[sid] = sorted((t, v) for t, v in pr.items())
        files = glob.glob(os.path.join(B.COOPS, f"air_pressure_{sid}_*.json"))
        d = {}
        for f in files:
            d.update(B.load_ms_dict(f))
        air[sid] = d
        issues = []
        for fn in sorted(glob.glob(f"{B.ARCH}/{sid}/2026-1*.json")):
            issues.extend(json.load(open(fn)).get("issues") or [])
        all_issues[sid] = issues

    aifs_hourly, aifs_sources = {}, {}
    complete = []
    for cid, rec in aifs_cache.items():
        st = rec.get("steps") or {}
        if "0" in st and "72" in st and len(st) >= 13:
            complete.append(cid)
            ser, srcs = B.aifs_series(rec)
            aifs_hourly[cid] = ser
            aifs_sources[cid] = srcs
    print(f"complete AIFS cycles: {len(complete)}", flush=True)

    def p_obs(sid, t):
        return B.interp([(k, v) for k, v in sorted((air.get(sid) or {}).items())], t) if air.get(sid) else None
    # faster: dict interp for air
    def p_obs(sid, t):
        d = air.get(sid) or {}
        if not d:
            return None
        if t in d:
            return d[t]
        keys = sorted(d)
        if t < keys[0] or t > keys[-1]:
            return None
        lo, hi = 0, len(keys)-1
        while hi-lo > 1:
            mid = (lo+hi)//2
            if keys[mid] <= t: lo = mid
            else: hi = mid
        a, b = keys[lo], keys[hi]
        if b == a: return d[a]
        return d[a] + (d[b]-d[a])*(t-a)/(b-a)

    def p_gfs(sid, t):
        return B.interp(gfs_pts.get(sid) or [], t)
    def p_aifs(cid, sid, t):
        return B.interp(aifs_hourly.get(cid, {}).get(sid) or [], t)

    # version D for the fixed-backbone rows (same as previous backtest)
    coef = json.load(open(B.COEF))["stations"] if os.path.exists(B.COEF) else {}
    box = json.load(open(B.OISST_BOX)) if os.path.exists(B.OISST_BOX) else {"days":[], "grid":{}}

    def sst_D(sid, issue_ms):
        c = coef.get(sid)
        if not c: return {"adj_ft": 0.0}
        k = c["k_ft_per_c"]
        pix = [(round(p[0], 3), round(p[1], 3)) for p in c["pix"]]
        cutoff = issue_ms - B.OISST_LATENCY_H * HR
        ser = []
        for d in box.get("days") or []:
            t = B.ms_utc(d + "T12:00:00Z")
            if t > cutoff: break
            g = (box.get("grid") or {}).get(d) or {}
            vs = [g[f"{la},{lo}"] for la, lo in pix if f"{la},{lo}" in g]
            if vs: ser.append((d, t, sum(vs)/len(vs)))
        if len(ser) < 7:
            return {"adj_ft": 0.0}
        m = lambda a: sum(x[2] for x in a)/len(a)
        return {"adj_ft": k * (m(ser[-2:]) - m(ser[-7:-2]))}

    seas_h = json.load(open(SEAS)) if os.path.exists(SEAS) else {}
    sla_d = json.load(open(SLA)) if os.path.exists(SLA) else {}
    sla_gain = (sla_d.get("gain") or {})
    stats = {sid: {m: {"ae": 0.0, "be": 0.0, "n": 0, "peaks": []} for m in MODES} for sid in B.STATIONS}
    identity_n = identity_fail = 0
    used = {sid: 0 for sid in B.STATIONS}
    used_free = 0

    for sid in B.STATIONS:
        for iss in all_issues[sid]:
            if iss.get("method") != "stofs":
                continue
            r = iss.get("r") or []
            if len(r) < LEAD_MAX+1:
                continue
            T0 = iss["t"]
            cid, rec = B.pick_aifs(T0, aifs_cache)
            if not cid or cid not in aifs_hourly:
                continue
            rNow = iss["rNow"]
            bias = iss.get("bias") or 0.0
            rsNow = rNow - bias
            cyc = str(iss.get("cycle") or "")
            a_rec = anom_cache.get(cyc)
            ib_now_obs = C.ib_ft(p_obs(sid, T0))
            if ib_now_obs is None:
                ib_now_obs = C.ib_ft(p_aifs(cid, sid, T0))
            if ib_now_obs is None:
                continue
            p_g0 = p_gfs(sid, T0)
            ib_g0 = C.ib_ft(p_g0)
            d0 = C.d_ib(ib_now_obs, ib_g0)
            anom0 = B.anom_at(a_rec, sid, T0)
            w0 = (rsNow - anom0 - ib_g0) if (anom0 is not None and ib_g0 is not None) else None
            adj = sst_D(sid, T0)["adj_ft"]

            got = ssta_at(bundle, sid, T0)
            if not got:
                continue
            ssta, _n = got
            k = float(k_map.get(sid) or 0.0)
            W = k * ssta
            off5, n5 = offset5(obs[sid], pred[sid], lambda t, sid=sid: p_obs(sid, t), W, T0, ib_now_obs)
            left = C.leftover_free(rNow, ib_now_obs, W, off5)

            used[sid] += 1
            used_free += 1
            ser = (bundle.get("ssta") or {}).get(sid) or {}
            lat = int(bundle.get("latent_d") or 2)
            dday = lambda t: dt.datetime.fromtimestamp(t/1000, dt.timezone.utc).date()
            e30 = window_term(lambda t: s30_on(ser, dday(t), lat), T0)
            ed = window_term(lambda t: daily_on(ser, dday(t), lat), T0)
            X_dsst30 = k*e30 if e30 is not None else 0.0
            X_dsstd = k*ed if ed is not None else 0.0
            hs = seas_h.get(sid)
            Hbar = None
            if hs:
                tt = T0 - 5*DAY; acc = []
                while tt <= T0:
                    acc.append(harm(hs, tt)); tt += HR
                Hbar = sum(acc)/len(acc)
            sser = (sla_d.get("sla") or {}).get(sid) or {}
            esla = window_term(lambda t: daily_on(sser, dday(t), 2), T0) if sser else None
            X_sla = float(sla_gain.get(sid, 0.0))*esla if esla is not None else 0.0
            pred_win = [(t, v) for t, v in pred[sid] if T0 + LEAD_MIN*HR - 2*HR <= t <= T0 + LEAD_MAX*HR + 2*HR]
            obs_win = [(t, v) for t, v in obs[sid] if T0 + LEAD_MIN*HR - 2*HR <= t <= T0 + LEAD_MAX*HR + 2*HR]

            hourly = {m: {} for m in MODES}
            for kk in range(0, LEAD_MAX+1):
                t = T0 + kk*HR
                if kk == 0 or t <= T0:
                    p_ib = p_obs(sid, t)
                    ib = C.ib_ft(p_ib) if p_ib is not None else C.ib_ft(p_aifs(cid, sid, t))
                else:
                    ib = C.ib_ft(p_aifs(cid, sid, t))
                if ib is None:
                    continue
                if kk >= len(r):
                    continue
                dt_h = kk
                rs = r[kk] - bias * C.fade(dt_h)
                ib_g = C.ib_ft(p_gfs(sid, t))
                WtD = C.W_D(adj, dt_h)
                anom = B.anom_at(a_rec, sid, t)
                of, onf, wc_fix = C.resid_pair(rs, rNow, rsNow, dt_h, WtD, ib, ib_g, anom, d0, w0)
                w_t = (rs - anom - ib_g) if (anom is not None and ib_g is not None) else None
                fr_off, fr_on, wc_fr = C.resid_free_pair(ib, W, off5, left, dt_h, w_t, w0)
                identity_n += 1
                if abs((fr_on - fr_off) - wc_fr) > 1e-9 or abs((onf - of) - wc_fix) > 1e-9:
                    identity_fail += 1
                hourly["c1"][kk] = r[kk]
                hourly["off_fixed"][kk] = of
                hourly["on_fixed"][kk] = onf
                hourly["free"][kk] = fr_off
                hourly["free_on"][kk] = fr_on
                hourly["official"][kk] = 0.0
                fin = 1.0 - C.fade(dt_h)
                sea = ((harm(hs, t) - Hbar) - (harm(hs, T0) - Hbar)*C.fade(dt_h)) if hs else 0.0
                hourly["dsst30"][kk] = fr_off + X_dsst30*fin
                hourly["dsstd"][kk] = fr_off + X_dsstd*fin
                hourly["seas"][kk] = fr_off + sea
                hourly["sla"][kk] = fr_off + X_sla*fin
                hourly["seas_dsstd"][kk] = fr_off + sea + X_dsstd*fin
                if LEAD_MIN <= kk <= LEAD_MAX:
                    o = B.interp(obs[sid], t)
                    p = B.interp(pred[sid], t)
                    if o is None or p is None:
                        continue
                    for name in MODES:
                        err = (p + hourly[name][kk]) - o
                        stt = stats[sid][name]
                        stt["ae"] += abs(err)
                        stt["be"] += err
                        stt["n"] += 1

            if pred_win and obs_win:
                def resid_at(kind, t):
                    k = (t - T0)/HR
                    if k < 0 or k > LEAD_MAX:
                        return None
                    k0 = int(math.floor(k))
                    k1 = min(LEAD_MAX, k0+1)
                    a, b_ = hourly[kind].get(k0), hourly[kind].get(k1)
                    if a is None or b_ is None:
                        return a if a is not None else b_
                    if k1 == k0:
                        return a
                    return a + (b_ - a)*(k-k0)
                t0w, t1w = T0 + LEAD_MIN*HR, T0 + LEAD_MAX*HR
                for kind in ("c1", "off_fixed", "on_fixed", "free", "free_on") + NEW:
                    fcst = []
                    for t, pv in pred_win:
                        rr = resid_at(kind, t)
                        if rr is None: continue
                        fcst.append((t, pv+rr))
                    pk = B.peak_miss(pred_win, obs_win, fcst, t0w, t1w)
                    if pk:
                        stats[sid][kind]["peaks"].append(pk["cond"])
                        if kind == "c1":
                            stats[sid]["official"]["peaks"].append(pk["off"])

    def summarize(stt):
        n, peaks = stt["n"], stt["peaks"]
        return {"n": n, "mae": (stt["ae"]/n) if n else None, "bias": (stt["be"]/n) if n else None,
                "n_peaks": len(peaks),
                "peak_miss": (sum(peaks)/len(peaks)) if peaks else None,
                "peak_mae": (sum(abs(x) for x in peaks)/len(peaks)) if peaks else None}

    table = {sid: {m: summarize(stats[sid][m]) for m in MODES} for sid in B.STATIONS}
    overall = {}
    for m in MODES:
        ae=be=n=0; peaks=[]
        for sid in B.STATIONS:
            ae += stats[sid][m]["ae"]; be += stats[sid][m]["be"]; n += stats[sid][m]["n"]
            peaks.extend(stats[sid][m]["peaks"])
        overall[m] = summarize({"ae":ae,"be":be,"n":n,"peaks":peaks})

    out = {"leads_h":[LEAD_MIN,LEAD_MAX], "aifs_complete": complete, "issues_used": used,
           "identity_n": identity_n, "identity_fail": identity_fail,
           "per_station": table, "overall": overall}
    json.dump(out, open(OUT, "w"), indent=2)
    def fmt(x,d=3):
        return "   n/a" if x is None else f"{x:7.{d}f}"
    print("\nOverall 3-72 h  (MAE ft, bias ft, peak-high miss ft, peak |miss| ft, n, n_peaks)")
    labels = [
        ("c1", "current Conditional (STOFS)"),
        ("off_fixed", "fixed STOFS-backbone default"),
        ("on_fixed", "fixed wind-on (STOFS backbone)"),
        ("free", "NEW STOFS-free default"),
        ("free_on", "NEW STOFS-free + wind"),
        ("official", "official prediction"),
        ("dsst30", "free + SST30 change since window"),
        ("dsstd", "free + daily SST change since window"),
        ("seas", "free + seasonal residual drift"),
        ("sla", "free + offshore altimetry SLA change"),
        ("seas_dsstd", "free + seasonal + daily SST change"),
    ]
    for m, lab in labels:
        o = overall[m]
        print(f"  {lab:36s}  MAE {fmt(o['mae'])}  bias {fmt(o['bias'])}  peak {fmt(o['peak_miss'])}  |peak| {fmt(o['peak_mae'])}  n={o['n']}  peaks={o['n_peaks']}")
    print(f"\nIdentity checks: {identity_n} hours, fails {identity_fail}")
    print(f"Wrote {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
