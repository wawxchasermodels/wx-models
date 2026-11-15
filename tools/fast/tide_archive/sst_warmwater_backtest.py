#!/usr/bin/env python3
"""Backtest Conditional v2 (IB from AIFS ENS mean MSL + SST term + fade, optional STOFS wind)
against the current STOFS Conditional (archive r[]) for 3-72 h leads.

Inputs (already cached unless noted):
  /tmp/tide_arch/<st>/2026-10.json, 2026-11.json
  /tmp/sst_work/coops/{air_pressure,water_level,predictions,water_temperature}_*
  /tmp/sst_work/oisst_nrt_stations.json
  /tmp/sst_work/gfs_pressure_stations.json   # STOFS forcing pressure (GFS)
  /tmp/sst_work/aifs_ens_msl/<YYYYMMDDHH>.json  # AIFS ENS mean (or fallback) at stations
  /tmp/sst_work/stofs_anom/<YYYYMMDDHH>.json    # cwl minus cwl.noanomaly, ft, hourly
"""
from __future__ import annotations
import json, math, os, sys, glob, datetime as dt
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cond_v2 as C

ARCH = "/tmp/tide_arch"
COOPS = "/tmp/sst_work/coops"
AIFS = "/tmp/sst_work/aifs_ens_msl"
OISST = "/tmp/sst_work/oisst_nrt_stations.json"
GFS = "/tmp/sst_work/gfs_pressure_stations.json"
OUT = "/tmp/sst_work/backtest_v2.json"
ANOM_DIR = "/tmp/sst_work/stofs_anom"
HR = 3600_000
LEAD_MIN, LEAD_MAX = 3, 72
# AIFS ENS open data is typically first on AWS around T+5h46m-5h52m; require init+6h
# before an issue may use that cycle (hindcast honesty).
AIFS_READY_MIN = 6 * 60
COEF = os.path.join(HERE, "sst_coef.json")
OISST_BOX = "/tmp/sst_work/oisst_nrt_box.json"
# OISST NRT is typically 1-2 days late; only use days whose 12Z file is at least 36 h old at issue time
OISST_LATENCY_H = 36

STATIONS = {
    "9439040": ("Astoria, OR", 46.207306, -123.7683),
    "9440910": ("Toke Point, WA", 46.7075, -123.96694),
    "9441102": ("Westport, WA", 46.90431, -124.10508),
    "9442396": ("La Push, WA", 47.912838, -124.63574),
    "9443090": ("Neah Bay, WA", 48.370724, -124.601585),
    "9444090": ("Port Angeles, WA", 48.125, -123.44),
    "9444900": ("Port Townsend, WA", 48.11122, -122.759674),
    "9449880": ("Friday Harbor, WA", 48.545277, -123.0125),
    "9449424": ("Cherry Point, WA", 48.862717, -122.75858),
    "9447130": ("Seattle, WA", 47.60264, -122.3393),
    "9446484": ("Tacoma, WA", 47.2667, -122.4133),
}
# in-situ water temp: own sensor, or mapped neighbor, or OISST (west-walked Seattle/Tacoma must not use OISST)
SST_OWN = {"9441102", "9442396", "9443090", "9444090", "9444900", "9446484"}
SST_MAP = {"9440910": "9441102", "9447130": "9446484", "9449880": "9444900"}  # Toke->Westport, Seattle->Tacoma, FH->PT
SALT = {
    "9439040": 25.0,
    "9440910": 32.2, "9441102": 32.2, "9442396": 32.2, "9443090": 32.2,
    "9444090": 31.0, "9444900": 31.0, "9449880": 31.0, "9449424": 31.0,
    "9447130": 30.0, "9446484": 30.0,
}
# Astoria has no CO-OPS air_pressure; fall back to Toke then Westport
P_FALLBACK = {"9439040": ["9440910", "9441102"]}

def ms_utc(s):
    if isinstance(s, (int, float)):
        return int(s)
    s = str(s).replace("Z", "")
    if "T" not in s:
        return int(s)
    fmt = "%Y-%m-%dT%H:%M:%S" if s.count(":") == 2 and s[-3] == ":" else "%Y-%m-%dT%H:%M"
    if "." in s:
        fmt = "%Y-%m-%dT%H:%M:%S.%f"
    return int(dt.datetime.strptime(s[:26], fmt).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)

def load_ms_dict(path):
    j = json.load(open(path))
    if isinstance(j, dict) and "data" in j:
        out = {}
        for p in j["data"]:
            try:
                out[ms_utc(p["t"] if "t" in p else p)] = float(p["v"])
            except Exception:
                pass
        return out
    return {int(k): float(v) for k, v in j.items()}

def interp(series, t):
    """series: sorted list of (t_ms, v) or dict ms->v."""
    if isinstance(series, dict):
        if t in series:
            return series[t]
        keys = getattr(series, "_sorted", None)
        if keys is None:
            keys = sorted(series)
            series._sorted = keys  # type: ignore
        pts = keys
        get = lambda k: series[k]
    else:
        pts = series
        get = lambda p: p[1]
        # pts is list of pairs
        if not pts:
            return None
        if t < pts[0][0] or t > pts[-1][0]:
            return None
        lo, hi = 0, len(pts) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if pts[mid][0] <= t:
                lo = mid
            else:
                hi = mid
        a, b = pts[lo], pts[hi]
        if b[0] == a[0]:
            return a[1]
        return a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0])
    if not pts:
        return None
    # dict path
    if t < pts[0] or t > pts[-1]:
        return None
    lo, hi = 0, len(pts) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if pts[mid] <= t:
            lo = mid
        else:
            hi = mid
    a, b = pts[lo], pts[hi]
    va, vb = get(a), get(b)
    if b == a:
        return va
    return va + (vb - va) * (t - a) / (b - a)

def load_coops_product(product, st):
    files = sorted(glob.glob(os.path.join(COOPS, f"{product}_{st}_*.json")))
    out = {}
    for f in files:
        # prefer the recent/short window and the long clim separately
        d = load_ms_dict(f)
        out.update(d)
    return out

def doy(ms):
    d = dt.datetime.fromtimestamp(ms / 1000.0, dt.timezone.utc)
    return int(d.strftime("%j"))

def build_clim(wt_hist):
    """DOY climatology in deg C from a deg-F hourly dict (2021-2025 files)."""
    buckets = defaultdict(list)
    for t, f in wt_hist.items():
        year = dt.datetime.fromtimestamp(t / 1000.0, dt.timezone.utc).year
        if year < 2021 or year > 2025:
            continue
        buckets[doy(t)].append((f - 32.0) / 1.8)
    return {d: sum(v) / len(v) for d, v in buckets.items() if v}

def pick_aifs(issue_ms, cache):
    """Newest AIFS cycle with init+AIFS_READY_MIN <= issue and a cycle file on disk."""
    t = dt.datetime.fromtimestamp(issue_ms / 1000.0, dt.timezone.utc)
    # walk back up to 8 cycles
    # floor to 6h
    cand = t.replace(minute=0, second=0, microsecond=0)
    cand -= dt.timedelta(hours=cand.hour % 6)
    for _ in range(8):
        ready = cand + dt.timedelta(minutes=AIFS_READY_MIN)
        if ready <= t:
            cid = cand.strftime("%Y%m%d%H")
            rec = cache.get(cid)
            # only use a cycle that already has the 0 and 72 h members (full 3-72 h interpolation)
            steps = (rec or {}).get("steps") or {}
            if rec and "0" in steps and "72" in steps and len(steps) >= 13:
                return cid, rec
        cand -= dt.timedelta(hours=6)
    return None, None

def aifs_series(rec):
    """Hourly-interpolated hPa at each station from 6-hourly steps. Returns {sid: [(t_ms, hPa), ...]} plus source notes."""
    init = ms_utc(rec["init"])
    steps = rec["steps"]
    hs = sorted(int(k) for k in steps)
    out = {sid: [] for sid in STATIONS}
    sources = {}
    for sid in STATIONS:
        pts = []
        for h in hs:
            st = steps[str(h)]
            v = (st.get("msl_hpa") or {}).get(sid)
            if v is None:
                continue
            pts.append((init + h * HR, float(v), st.get("source") or "aifs-ens-mean"))
        # interpolate hourly between first and last
        hourly = []
        if len(pts) == 1:
            hourly = [(pts[0][0], pts[0][1])]
        elif len(pts) >= 2:
            t = pts[0][0]
            i = 0
            while t <= pts[-1][0]:
                while i + 1 < len(pts) and pts[i + 1][0] < t:
                    i += 1
                if t == pts[i][0] or i + 1 >= len(pts):
                    # exact or clamp at end
                    if t <= pts[-1][0]:
                        # linear if between
                        if t == pts[i][0]:
                            hourly.append((t, pts[i][1]))
                        else:
                            a, b = pts[i], pts[-1]
                            if b[0] == a[0]:
                                hourly.append((t, a[1]))
                            else:
                                hourly.append((t, a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0])))
                else:
                    a, b = pts[i], pts[i + 1]
                    if t < a[0]:
                        t += HR
                        continue
                    if b[0] == a[0]:
                        hourly.append((t, a[1]))
                    else:
                        hourly.append((t, a[1] + (b[1] - a[1]) * (t - a[0]) / (b[0] - a[0])))
                t += HR
        out[sid] = hourly
        sources[sid] = list({p[2] for p in pts})
    return out, sources

def extremes(pts, t0, t1):
    out = []
    for i in range(2, len(pts) - 2):
        t, v = pts[i]
        if t < t0 or t > t1:
            continue
        hi = v >= pts[i - 1][1] and v > pts[i + 1][1] and v >= pts[i - 2][1] and v > pts[i + 2][1]
        lo = v <= pts[i - 1][1] and v < pts[i + 1][1] and v <= pts[i - 2][1] and v < pts[i + 2][1]
        if hi or lo:
            last = out[-1] if out else None
            if last and t - last["t"] < 3 * HR and last["hi"] == hi:
                if (hi and v > last["v"]) or (lo and v < last["v"]):
                    out[-1] = {"t": t, "v": v, "hi": hi}
            else:
                out.append({"t": t, "v": v, "hi": hi})
    return out

def peak_miss(pred, obs, fcst, t0, t1):
    """fcst and pred/obs are lists of (t,v) 6-min; miss = forecast-obs at the highest observed high."""
    pm = {t: v for t, v in pred}
    om = obs
    vm = {t: v for t, v in fcst}
    pk = None
    for e in extremes(pred, t0, t1):
        if not e["hi"]:
            continue
        oM, oT, pM, vM, vOk, cnt = None, 0, -1e9, -1e9, 0, 0
        for t, v in om:
            if t < e["t"] - 90 * 60000:
                continue
            if t > e["t"] + 90 * 60000:
                break
            cnt += 1
            if oM is None or v > oM:
                oM, oT = v, t
        t = e["t"] - 90 * 60000
        while t <= e["t"] + 90 * 60000:
            p = pm.get(t)
            if p is not None and p > pM:
                pM = p
            v = vm.get(t)
            if v is not None:
                vOk += 1
                if v > vM:
                    vM = v
            t += 6 * 60000
        if oM is None or cnt < 20 or vOk < 25:
            continue
        if pk is None or oM > pk["obs"]:
            pk = {"t": oT, "obs": oM, "cond": vM - oM, "off": pM - oM}
    return pk

def load_all_aifs():
    cache = {}
    if not os.path.isdir(AIFS):
        return cache
    for fn in os.listdir(AIFS):
        if not fn.endswith(".json"):
            continue
        try:
            j = json.load(open(os.path.join(AIFS, fn)))
            cache[j["cycle"]] = j
        except Exception:
            pass
    return cache

def load_anom_cache():
    cache = {}
    if not os.path.isdir(ANOM_DIR):
        return cache
    for fn in glob.glob(os.path.join(ANOM_DIR, "*.json")):
        try:
            rec = json.load(open(fn))
        except Exception:
            continue
        cid = rec.get("cycle") or os.path.basename(fn)[:10]
        init = rec.get("init")
        if not init:
            continue
        s = str(init).replace("Z", "")
        try:
            init_ms = int(dt.datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
        except ValueError:
            continue
        rec = dict(rec)
        rec["_init_ms"] = init_ms
        cache[str(cid)] = rec
    return cache

def anom_at(rec, sid, t_ms):
    if not rec:
        return None
    hourly = ((rec.get("stations") or {}).get(sid) or {}).get("hourly") or {}
    if not hourly:
        return None
    h = (t_ms - rec["_init_ms"]) / HR
    h0 = int(math.floor(h))
    h1 = h0 + 1
    def get(k):
        v = hourly.get(str(k), hourly.get(k))
        return None if v is None else float(v)
    a, b = get(h0), get(h1)
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None or h1 == h0:
        return a
    return a + (b - a) * (h - h0)

def main():
    aifs_cache = load_all_aifs()
    print(f"AIFS cycles on disk: {len(aifs_cache)}", flush=True)
    oisst = json.load(open(OISST))
    gfs = json.load(open(GFS))
    gfs_pts = {}
    for sid, rec in gfs.items():
        gfs_pts[sid] = [(ms_utc(t), float(p)) for t, p in zip(rec["time"], rec["pressure_msl"]) if p is not None]

    # CO-OPS caches
    obs = {}
    pred = {}
    air = {}
    wt_recent = {}
    wt_clim = {}
    for sid in STATIONS:
        wl = load_coops_product("water_level", sid)
        pr = load_coops_product("predictions", sid)
        obs[sid] = sorted((t, v) for t, v in wl.items())
        pred[sid] = sorted((t, v) for t, v in pr.items())
        # air pressure: may be missing
        files = glob.glob(os.path.join(COOPS, f"air_pressure_{sid}_*.json"))
        if files:
            d = {}
            for f in files:
                d.update(load_ms_dict(f))
            air[sid] = d
        # water temp
        files = glob.glob(os.path.join(COOPS, f"water_temperature_{sid}_*.json"))
        if files:
            # split hist vs recent by year
            hist, rec = {}, {}
            for f in files:
                d = load_ms_dict(f)
                for t, v in d.items():
                    year = dt.datetime.fromtimestamp(t / 1000.0, dt.timezone.utc).year
                    if year <= 2025:
                        hist[t] = v
                    else:
                        rec[t] = v
            if hist:
                wt_clim[sid] = build_clim(hist)
            if rec:
                wt_recent[sid] = rec

    # Version D SST (reuse sst_coef.json + OISST pixels from the steric study; do not add k*SSTA_30)
    coef = json.load(open(COEF))["stations"]
    box = json.load(open(OISST_BOX))
    box_grid = box["grid"]

    def sst_D(sid, issue_ms):
        c = coef.get(sid)
        if not c:
            return None
        k = c["k_ft_per_c"]
        pix = [(round(p[0], 3), round(p[1], 3)) for p in c["pix"]]
        cutoff = issue_ms - OISST_LATENCY_H * HR
        ser = []
        for d in box["days"]:
            # daily field is typically 12Z
            t = ms_utc(d + "T12:00:00Z")
            if t > cutoff:
                break
            g = box_grid.get(d) or {}
            vs = [g[f"{la},{lo}"] for la, lo in pix if f"{la},{lo}" in g]
            if vs:
                ser.append((d, t, sum(vs) / len(vs)))
        if len(ser) < 7:
            return None
        m = lambda a: sum(x[2] for x in a) / len(a)
        s30, rec, prior = m(ser[-30:]), m(ser[-2:]), m(ser[-7:-2])
        d_c = rec - prior
        adj = k * d_c
        return dict(ssta30_c=s30, d_c=d_c, T=rec, k=k, steric_ft=k * s30, adj_ft=adj,
                    src="oisst-D", last_day=ser[-1][0])

    print("version D SST ready, coef stations", len(coef), flush=True)

    # Load issues
    all_issues = {}
    for sid in STATIONS:
        issues = []
        for fn in sorted(glob.glob(os.path.join(ARCH, sid, "2026-1*.json"))):
            issues.extend(json.load(open(fn)).get("issues") or [])
        issues.sort(key=lambda i: i["t"])
        all_issues[sid] = issues

    # cache interpolated AIFS per cycle
    aifs_hourly = {}
    aifs_sources = {}
    for cid, rec in aifs_cache.items():
        ser, srcs = aifs_series(rec)
        aifs_hourly[cid] = ser
        aifs_sources[cid] = srcs

    def p_obs(sid, t):
        series = air.get(sid)
        if not series:
            for fb in P_FALLBACK.get(sid, []):
                series = air.get(fb)
                if series:
                    break
        if not series:
            return None
        return interp(series, t)

    def p_gfs(sid, t):
        return interp(gfs_pts.get(sid) or [], t)

    def p_aifs(cid, sid, t):
        return interp(aifs_hourly.get(cid, {}).get(sid) or [], t)

    leftover = {}
    issues_used = {sid: 0 for sid in STATIONS}
    identity_fail = 0
    identity_n = 0
    anom_cache = load_anom_cache()
    anom_issues = 0
    anom_missing = 0
    diag = {"dIB": 0.0, "dIB_n": 0, "fade_mismatch": 0.0, "fade_n": 0, "anom": 0.0, "anom_n": 0, "wind_only": 0.0, "wind_n": 0, "old_on_minus_c1": 0.0, "fixed_on_minus_c1": 0.0, "cmp_n": 0}
    # Score
    stats = {sid: {m: {"ae": 0.0, "be": 0.0, "n": 0, "peaks": []} for m in ("c1", "off", "on", "on_old", "official")} for sid in STATIONS}
    # also identity accumulator
    sst_report = {}
    run_ids = defaultdict(int)
    fallback_n = 0
    ens_n = 0

    for sid in STATIONS:
        last_sst = None
        for iss in all_issues[sid]:
            T0 = iss["t"]
            r = iss.get("r") or []
            if len(r) < LEAD_MAX + 1 or iss.get("method") != "stofs":
                continue
            cid, rec = pick_aifs(T0, aifs_cache)
            if not cid:
                continue
            run_ids[cid] += 1
            sst = sst_D(sid, T0)
            if not sst:
                continue
            last_sst = sst
            adj = sst["adj_ft"]
            ib_now_obs = C.ib_ft(p_obs(sid, T0))
            # if no obs P at issue, use AIFS at issue (noted as forecast even at t0)
            used_obs_p0 = ib_now_obs is not None
            if ib_now_obs is None:
                ib_now_obs = C.ib_ft(p_aifs(cid, sid, T0))
            if ib_now_obs is None:
                continue
            rNow = iss["rNow"]
            bias = iss.get("bias") or 0.0
            rsNow = rNow - bias
            cyc = str(iss.get("cycle") or "")
            a_rec = anom_cache.get(cyc)
            if a_rec:
                anom_issues += 1
            else:
                anom_missing += 1
            p_g0 = p_gfs(sid, T0)
            ib_g0 = C.ib_ft(p_g0)
            d0 = C.d_ib(ib_now_obs, ib_g0)
            anom0 = anom_at(a_rec, sid, T0)
            w0 = (rsNow - anom0 - ib_g0) if (anom0 is not None and ib_g0 is not None) else None
            issues_used[sid] += 1

            # peak-high window: issue+3h to issue+72h, need 6-min official+obs+forecast
            # we'll collect hourly first for MAE, and build 6-min forecast series for peaks
            pred_win = [(t, v) for t, v in pred[sid] if T0 + LEAD_MIN * HR - 2 * HR <= t <= T0 + LEAD_MAX * HR + 2 * HR]
            obs_win = [(t, v) for t, v in obs[sid] if T0 + LEAD_MIN * HR - 2 * HR <= t <= T0 + LEAD_MAX * HR + 2 * HR]

            fc_off_6, fc_on_6, fc_c1_6 = [], [], []

            for k in range(LEAD_MIN, LEAD_MAX + 1):
                t = T0 + k * HR
                o = interp(obs[sid], t)
                p = interp(pred[sid], t)
                if o is None or p is None:
                    continue
                # pressures
                if k == 0 or t <= T0:
                    p_ib = p_obs(sid, t)
                    ib = C.ib_ft(p_ib) if p_ib is not None else C.ib_ft(p_aifs(cid, sid, t))
                else:
                    ib = C.ib_ft(p_aifs(cid, sid, t))
                if ib is None:
                    continue
                srcs = aifs_sources.get(cid, {}).get(sid) or ["aifs-ens-mean"]
                if any(s != "aifs-ens-mean" for s in srcs):
                    fallback_n += 1
                else:
                    ens_n += 1
                # STOFS 3h-mean surge recovered from c1 residual
                # r_c1(t) = rs(t) + bias * exp(-dt/12)  during the STOFS window
                dt_h = k
                rs = r[k] - bias * C.fade(dt_h)
                p_sto = p_gfs(sid, t)
                ib_g = C.ib_ft(p_sto)
                Wt = C.W_D(adj, dt_h)
                anom = anom_at(a_rec, sid, t)
                off, on, wind = C.resid_pair(rs, rNow, rsNow, dt_h, Wt, ib, ib_g, anom, d0, w0)
                wind_old = C.wind_component(rs, p_sto)
                on_old = C.resid_on(ib, Wt, rNow, ib_now_obs, 0.0, dt_h, wind_old)
                identity_n += 1
                if abs((on - off) - wind) > 1e-9:
                    identity_fail += 1
                r_c1 = r[k]
                r_obs = o - p
                if ib is not None and ib_g is not None:
                    diag["dIB"] += (ib - ib_g); diag["dIB_n"] += 1
                if ib_now_obs is not None:
                    diag["fade_mismatch"] += (rsNow - ib_now_obs) * C.fade(dt_h); diag["fade_n"] += 1
                if anom is not None:
                    diag["anom"] += anom; diag["anom_n"] += 1
                if anom is not None and ib_g is not None:
                    diag["wind_only"] += (rs - anom - ib_g); diag["wind_n"] += 1
                diag["old_on_minus_c1"] += (on_old - r_c1)
                diag["fixed_on_minus_c1"] += (on - r_c1)
                diag["cmp_n"] += 1
                for name, resid in (("c1", r_c1), ("off", off), ("on", on), ("on_old", on_old), ("official", 0.0)):
                    err = (p + resid) - o
                    stt = stats[sid][name]
                    stt["ae"] += abs(err)
                    stt["be"] += err
                    stt["n"] += 1

            # peak-high: build 6-min forecast = official + residual(t)
            if pred_win and obs_win:
                def resid_at(kind, t):
                    k = (t - T0) / HR
                    if k < 0 or k > LEAD_MAX:
                        return None
                    # interpolate residual between hours
                    k0 = int(math.floor(k))
                    k1 = min(LEAD_MAX, k0 + 1)
                    def R(kk):
                        if kk < 0 or kk >= len(r):
                            return None
                        if kind == "c1":
                            return r[kk]
                        if kind == "official":
                            return 0.0
                        tt = T0 + kk * HR
                        if tt <= T0:
                            p_ib = p_obs(sid, tt)
                            ib = C.ib_ft(p_ib) if p_ib is not None else C.ib_ft(p_aifs(cid, sid, tt))
                        else:
                            ib = C.ib_ft(p_aifs(cid, sid, tt))
                        if ib is None:
                            return None
                        rs = r[kk] - bias * C.fade(kk)
                        ib_g = C.ib_ft(p_gfs(sid, tt))
                        Wt = C.W_D(adj, kk)
                        anom = anom_at(a_rec, sid, tt)
                        off, on, _wc = C.resid_pair(rs, rNow, rsNow, kk, Wt, ib, ib_g, anom, d0, w0)
                        if kind == "off":
                            return off
                        if kind == "on_old":
                            return C.resid_on(ib, Wt, rNow, ib_now_obs, 0.0, kk, C.wind_component(rs, p_gfs(sid, tt)))
                        return on
                    a, b = R(k0), R(k1)
                    if a is None or b is None:
                        return a if a is not None else b
                    if k1 == k0:
                        return a
                    return a + (b - a) * (k - k0)

                t0w, t1w = T0 + LEAD_MIN * HR, T0 + LEAD_MAX * HR
                for kind in ("c1", "off", "on", "on_old"):
                    fcst = []
                    for t, pv in pred_win:
                        rr = resid_at(kind, t)
                        if rr is None:
                            continue
                        fcst.append((t, pv + rr))
                    pk = peak_miss(pred_win, obs_win, fcst, t0w, t1w)
                    if pk:
                        stats[sid][kind]["peaks"].append(pk["cond"])
                        if kind == "c1":
                            stats[sid]["official"]["peaks"].append(pk["off"])

        if last_sst:
            sst_report[sid] = dict(last_sst, n_issues=issues_used[sid])

    def summarize(stt):
        n = stt["n"]
        peaks = stt["peaks"]
        return {
            "n": n,
            "mae": (stt["ae"] / n) if n else None,
            "bias": (stt["be"] / n) if n else None,
            "n_peaks": len(peaks),
            "peak_miss": (sum(peaks) / len(peaks)) if peaks else None,
            "peak_mae": (sum(abs(x) for x in peaks) / len(peaks)) if peaks else None,
        }

    table = {sid: {m: summarize(stats[sid][m]) for m in stats[sid]} for sid in STATIONS}

    # overall (pool hours)
    overall = {}
    for m in ("c1", "off", "on", "on_old", "official"):
        ae = be = n = 0
        peaks = []
        for sid in STATIONS:
            ae += stats[sid][m]["ae"]; be += stats[sid][m]["be"]; n += stats[sid][m]["n"]
            peaks.extend(stats[sid][m]["peaks"])
        overall[m] = {
            "n": n,
            "mae": (ae / n) if n else None,
            "bias": (be / n) if n else None,
            "n_peaks": len(peaks),
            "peak_miss": (sum(peaks) / len(peaks)) if peaks else None,
            "peak_mae": (sum(abs(x) for x in peaks) / len(peaks)) if peaks else None,
        }

    # baked clim for the JS (in-situ DOY deg C, and H_eff)
    baked = {"sst_method": "D", "k_ft_per_c": {s: (coef.get(s) or {}).get("k_ft_per_c") for s in STATIONS}}

    out = {
        "leads_h": [LEAD_MIN, LEAD_MAX],
        "aifs_cycles_on_disk": sorted(aifs_cache),
        "aifs_run_issue_counts": dict(run_ids),
        "aifs_hourly_points_ens": ens_n,
        "aifs_hourly_points_fallback": fallback_n,
        "identity_n": identity_n,
        "identity_fail": identity_fail,
        "issues_used": issues_used,
        "anom_issues": anom_issues,
        "anom_missing": anom_missing,
        "anom_cycles_on_disk": len(anom_cache),
        "diag": {k: (diag[k] / diag["dIB_n"] if k == "dIB" and diag["dIB_n"] else
                     diag[k] / diag["fade_n"] if k == "fade_mismatch" and diag["fade_n"] else
                     diag[k] / diag["anom_n"] if k == "anom" and diag["anom_n"] else
                     diag[k] / diag["wind_n"] if k == "wind_only" and diag["wind_n"] else
                     diag[k] / diag["cmp_n"] if k in ("old_on_minus_c1", "fixed_on_minus_c1") and diag["cmp_n"] else
                     diag[k]) for k in diag},
        "sst": sst_report,
        "per_station": table,
        "overall": overall,
        "baked": baked,
    }
    json.dump(out, open(OUT, "w"), indent=2)
    # print a compact table
    def fmt(x, d=3):
        return "   n/a" if x is None else f"{x:7.{d}f}"
    print("\nOverall 3-72 h  (MAE ft, bias ft, peak-high miss ft, peak |miss| ft, n, n_peaks)")
    for m, lab in (("c1", "current Conditional (STOFS)"), ("off", "v2 default (fixed, wind OFF)"),
                   ("on_old", "v2 wind-on (before fix)"), ("on", "v2 wind-on fixed"),
                   ("official", "official prediction")):
        o = overall[m]
        print(f"  {lab:32s}  MAE {fmt(o['mae'])}  bias {fmt(o['bias'])}  peak {fmt(o['peak_miss'])}  |peak| {fmt(o['peak_mae'])}  n={o['n']}  peaks={o['n_peaks']}")
    print(f"\nIdentity checks: {identity_n} hours, fails {identity_fail}")
    print(f"Anom coverage: {anom_issues} issues with extract, {anom_missing} missing, {len(anom_cache)} cycles on disk")
    d = out["diag"]
    print(f"Diag means (ft): dIB={d['dIB']:+.4f}  fade_mismatch={d['fade_mismatch']:+.4f}  anom={d['anom']:+.4f}  wind_only={d['wind_only']:+.4f}  old_on-c1={d['old_on_minus_c1']:+.4f}  fixed_on-c1={d['fixed_on_minus_c1']:+.4f}")
    print(f"Wrote {OUT}")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
