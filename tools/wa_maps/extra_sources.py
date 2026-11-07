#!/usr/bin/env python3
"""Data fetchers for the extra map models: NOAA NBM (snow, gusts), NOAA GFS 0.25 deg, ECMWF ENS 0.25 deg (mean, 90th pct).
Data: ECMWF open data (CC BY 4.0), NOAA (public domain). Basemap: U.S. Census, Natural Earth (public domain), GSHHG (NOAA, LGPL). Places: GeoNames (CC BY 4.0), Census Gazetteer (public domain).
Part of wx-models (MIT). Renders a static JPEG; no branding."""
""\
\
\
\
\
\
\
\
\
\
\

import datetime as dt, json, os, re, tempfile, time, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np

UTC = dt.timezone.utc
BOX = (43.5, 51.2, -127.5, -114.5)
if os.environ.get("PM_BOX"): BOX = tuple(float(x) for x in os.environ["PM_BOX"].split(","))
IN_PER_M, MPH = 39.37008, 2.236936
GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
NBM = "https://noaa-nbm-grib2-pds.s3.amazonaws.com"
ENS = "https://data.ecmwf.int/forecasts"
KU_LEVELS = [1000, 925, 850, 700, 600, 500]

def _get(url, rng=None, tries=4):
    for k in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Range": "bytes=%d-%s" % (rng[0], "" if rng[1] is None else rng[1])} if rng else {})
            with urllib.request.urlopen(req, timeout=120) as r: return r.read()
        except Exception:
            if k == tries - 1: raise
            time.sleep(2 * (k + 1))

def _ok(url):
    try: urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=30); return True
    except Exception: return False

def _decode(blob):
    import eccodes
    out = []
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf_:
        tf_.write(blob); tf_.flush()
        with open(tf_.name, "rb") as fh:
            while True:
                g = eccodes.codes_grib_new_from_file(fh)
                if g is None: break
                info = {k: eccodes.codes_get(g, k) for k in ["shortName", "stepRange", "Ni", "Nj"]}
                try: info["number"] = eccodes.codes_get(g, "number")
                except Exception: pass
                try: alt = eccodes.codes_get(g, "alternativeRowScanning")
                except Exception: alt = 0
                Ni, Nj = info["Ni"], info["Nj"]
                v = eccodes.codes_get_values(g).reshape(Nj, Ni).copy()
                if alt: v[1::2] = v[1::2, ::-1]
                la = eccodes.codes_get_array(g, "latitudes").reshape(Nj, Ni); lo = eccodes.codes_get_array(g, "longitudes").reshape(Nj, Ni)
                lo = np.where(lo > 180, lo - 360, lo)
                m = (la > BOX[0]) & (la < BOX[1]) & (lo > BOX[2]) & (lo < BOX[3]); ii, jj = np.where(m)
                s = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1))
                v = np.where(v > 9e20, np.nan, v)
                out.append((v[s], la[s].copy(), lo[s].copy(), info))
    return out

def regular(V, LA, LO):
    if np.allclose(LA, LA[:, :1]) and np.allclose(LO, LO[:1, :]):
        lat1, lon1 = LA[:, 0], LO[0, :]; oi = np.argsort(lat1); oj = np.argsort(lon1)
        return lat1[oi], lon1[oj], V[oi][:, oj]
    from scipy.interpolate import griddata
    lat1 = np.arange(BOX[0] + 0.5, BOX[1] - 0.4, 0.02); lon1 = np.arange(BOX[2] + 0.5, BOX[3] - 0.5, 0.02)
    LON, LAT = np.meshgrid(lon1, lat1); ok = np.isfinite(V)
    G = griddata((LO[ok], LA[ok]), V[ok], (LON, LAT), method="linear")
    return lat1, lon1, G

def _idx_recs(url):
    L = _get(url + ".idx").decode().splitlines()
    return [(int(l.split(":")[1]), int(L[i + 1].split(":")[1]) - 1 if i + 1 < len(L) else None, ":".join(l.split(":")[3:])) for i, l in enumerate(L)]

def _find(recs, pat):
    r = [x for x in recs if re.fullmatch(pat, x[2])]
    return r[0] if r else None

def _pull(url, rec):
    return _decode(_get(url, rec[:2]))[0]

def gfs_url(cyc, f): return "%s/gfs.%s/%02d/atmos/gfs.t%02dz.pgrb2.0p25.f%03d" % (GFS, cyc.strftime("%Y%m%d"), cyc.hour, cyc.hour, f)
def gfs_steps(h1=384): return [h for h in range(0, h1 + 1) if (h <= 120 and h % 3 == 0) or (h > 120 and h % 6 == 0)]

def gfs_window(h0, h1):
    st = gfs_steps(); a = max(s for s in st if s <= max(0, h0)); b = min(s for s in st if s >= h1)
    return a, b

def _gfs_acc(cyc, h):
    if h == 0: return None
    u = gfs_url(cyc, h); R = _idx_recs(u)
    r = _find(R, r"APCP:surface:0-%d hour acc fcst:" % h) or (_find(R, r"APCP:surface:0-%d day acc fcst:" % (h // 24)) if h % 24 == 0 else None)
    if not r: raise SystemExit("GFS %s f%03d: no 0-%d h APCP record" % (cyc, h, h))
    return _pull(u, r)

def fetch_gfs_apcp(cyc, h0, h1):
    b = _gfs_acc(cyc, h1); a = _gfs_acc(cyc, h0)
    v = b[0] - (a[0] if a else 0)
    lat1, lon1, G = regular(np.clip(v, 0, None) / 25.4, b[1], b[2])
    return G, lat1, lon1, dict(model="gfs", run=cyc.strftime("%Y%m%d%HZ"), fhr=[h0, h1], param="APCP 0-h accumulations, differenced",
                                 resolution="GFS 0.25 deg", source=gfs_url(cyc, h1), license="NOAA, public domain")

def kuchera_ratio(tmax):
    r = np.where(tmax > 271.16, 12 + 2 * (271.16 - tmax), 12 + (271.16 - tmax))
    return np.clip(r, 0, None)

def _gfs_ratio_csnow(cyc, f):
    u = gfs_url(cyc, f); R = _idx_recs(u)
    want = [r"TMP:2 m above ground:%s:" % ("anl" if f == 0 else "%d hour fcst" % f), r"PRES:surface:%s:" % ("anl" if f == 0 else "%d hour fcst" % f)]
    want += [r"TMP:%d mb:%s:" % (lv, "anl" if f == 0 else "%d hour fcst" % f) for lv in KU_LEVELS]
    recs = [_find(R, w) for w in want]
    cs = _find(R, r"CSNOW:surface:%d hour fcst:" % f) if f else None
    with ThreadPoolExecutor(8) as ex: F = list(ex.map(lambda r: _pull(u, r), recs + ([cs] if cs else [])))
    t2, sp = F[0][0], F[1][0]; tm = t2.copy()
    for k, lv in enumerate(KU_LEVELS):
        tl = F[2 + k][0]; tm = np.where(sp > lv * 100, np.maximum(tm, tl), tm)
    return kuchera_ratio(tm), (F[-1][0] if cs else None), F[0][1], F[0][2]

def fetch_gfs_kuchera(cyc, h0, h1):
    st = [s for s in gfs_steps() if h0 <= s <= h1]
    acc = {s: (_gfs_acc(cyc, s)[0] if s else 0) for s in st}
    rc = {s: _gfs_ratio_csnow(cyc, s) for s in st}
    tot = 0
    for a, b in zip(st[:-1], st[1:]):
        ra, ca, LA, LO = rc[a]; rb, cb, _, _ = rc[b]
        csn = cb if ca is None else 0.5 * (ca + cb)
        tot = tot + np.clip(acc[b] - acc[a], 0, None) / 25.4 * csn * 0.5 * (ra + rb)
    lat1, lon1, G = regular(tot, LA, LO)
    return G, lat1, lon1, dict(model="gfs", run=cyc.strftime("%Y%m%d%HZ"), fhr=[h0, h1], method="Kuchera",
                                 params="APCP x CSNOW x Kuchera(max of TMP 2 m and %s hPa above ground)" % "/".join(map(str, KU_LEVELS)),
                                 resolution="GFS 0.25 deg", license="NOAA, public domain")

def fetch_gfs_gust(cyc, h0, h1):
    st = [s for s in gfs_steps() if h0 <= s <= h1] or [gfs_window(h0, h0)[1]]
    F = []
    for s in st:
        u = gfs_url(cyc, s); F.append(_pull(u, _find(_idx_recs(u), r"GUST:surface:%s:" % ("anl" if s == 0 else "%d hour fcst" % s))))
    lat1, lon1, G = regular(np.max([f[0] for f in F], 0) * MPH, F[0][1], F[0][2])
    return G, lat1, lon1, dict(model="gfs", run=cyc.strftime("%Y%m%d%HZ"), steps=st, param="GUST:surface (instantaneous at each step), max",
                                 resolution="GFS 0.25 deg", license="NOAA, public domain")

def fetch_gfs_temp(kind, date, cyc):
    d0 = dt.datetime(date.year, date.month, date.day, tzinfo=UTC)
    ends = [d0 + dt.timedelta(hours=18), d0 + dt.timedelta(hours=24)] if kind == "high" else [d0 + dt.timedelta(hours=12), d0 + dt.timedelta(hours=18)]
    var = "TMAX" if kind == "high" else "TMIN"; F = []
    for e in ends:
        f = int((e - cyc).total_seconds() // 3600)
        if f < 6: continue
        u = gfs_url(cyc, f); r = _find(_idx_recs(u), r"%s:2 m above ground:%d-%d hour (max|min) fcst:" % (var, f - 6, f))
        if r: F.append(_pull(u, r))
    if not F: raise SystemExit("GFS %s: no %s records for %s" % (cyc, var, date))
    v = (np.max if kind == "high" else np.min)([f[0] for f in F], 0)
    lat1, lon1, G = regular((v - 273.15) * 9 / 5 + 32, F[0][1], F[0][2])
    return G, lat1, lon1, dict(model="gfs", run=cyc.strftime("%Y%m%d%HZ"), method="%s 6 h records ending %s" % (var, ", ".join("%02dZ" % e.hour for e in ends)),
                                 resolution="GFS 0.25 deg", license="NOAA, public domain")

def nbm_url(cyc, f): return "%s/blend.%s/%02d/core/blend.t%02dz.core.f%03d.co.grib2" % (NBM, cyc.strftime("%Y%m%d"), cyc.hour, cyc.hour, f)

def fetch_nbm_asnow(cyc, h0, h1):
    idx = {}
    def recs(f):
        if f not in idx:
            try: idx[f] = _idx_recs(nbm_url(cyc, f))
            except Exception: idx[f] = []
        return idx[f]
    plan, h = [], h0
    while h < h1:
        for n in (6, 3, 1):
            if h + n > h1: continue
            r = _find(recs(h + n), r"ASNOW:surface:%d-%d hour acc fcst:" % (h, h + n))
            if r: plan.append((h + n, r)); h += n; break
        else: raise SystemExit("NBM %s: no ASNOW record starting at hour %d" % (cyc, h))
    with ThreadPoolExecutor(6) as ex: F = list(ex.map(lambda p: _pull(nbm_url(cyc, p[0]), p[1]), plan))
    tot = np.sum([np.nan_to_num(f[0]) for f in F], 0) * IN_PER_M
    lat1, lon1, G = regular(tot, F[0][1], F[0][2])
    return G, lat1, lon1, dict(model="nbm", run=cyc.strftime("%Y%m%d%HZ"), fhr=[h0, h1], n_records=len(plan), param="ASNOW (m) summed",
                                 resolution="NBM core 2.5 km, regridded to 0.02 deg", license="NOAA, public domain")

def fetch_nbm_gust(cyc, h0, h1):
    fs = [f for f in range(max(1, h0), h1 + 1)] or [max(1, h1)]
    F = []
    for f in fs:
        try: R = _idx_recs(nbm_url(cyc, f))
        except Exception: continue
        r = _find(R, r"GUST:10 m above ground:%d hour fcst:" % f)
        if r: F.append(_pull(nbm_url(cyc, f), r))
    if not F: raise SystemExit("NBM %s: no GUST records in f%03d-f%03d" % (cyc, h0, h1))
    lat1, lon1, G = regular(np.nanmax([f[0] for f in F], 0) * MPH, F[0][1], F[0][2])
    return G, lat1, lon1, dict(model="nbm", run=cyc.strftime("%Y%m%d%HZ"), fhr=[h0, h1], n_records=len(F), param="GUST 10 m (hourly where available), max",
                                 resolution="NBM core 2.5 km, regridded to 0.02 deg", license="NOAA, public domain")

def ens_steps(cyc):
    top = 360 if cyc.hour in (0, 12) else 144
    return [s for s in range(0, top + 1) if (s <= 144 and s % 3 == 0) or (s > 144 and s % 6 == 0)]

def ens_window(cyc, h0, h1):
    st = ens_steps(cyc); return max(s for s in st if s <= max(0, h0)), min(s for s in st if s >= h1)

def ens_base(cyc, s):
    d = cyc.strftime("%Y%m%d")
    return "%s/%s/%02dz/ifs/0p25/enfo/%s%02d0000-%dh-enfo-ef" % (ENS, d, cyc.hour, d, cyc.hour, s)

def ens_members(cyc, s, param):
    b = ens_base(cyc, s)
    js = [j for j in (json.loads(l) for l in _get(b + ".index").decode().splitlines()) if j.get("param") == param and j.get("type") == "pf"]
    if len(js) < 50: raise SystemExit("ENS %s step %d: %d members of %s" % (cyc, s, len(js), param))
    with ThreadPoolExecutor(16) as ex:
        F = list(ex.map(lambda j: _decode(_get(b + ".grib2", (j["_offset"], j["_offset"] + j["_length"] - 1)))[0], js))
    return np.array([f[0] for f in F]), F[0][1], F[0][2]

def _stat(M, stat):
    return np.percentile(M, 90, axis=0) if stat == "p90" else M.mean(0)

def _ens_meta(cyc, stat, **k):
    return dict(model="eps", run=cyc.strftime("%Y%m%d%HZ"), members=50, stat="90th percentile" if stat == "p90" else "mean",
                resolution="ECMWF ENS 0.25 deg", license="CC BY 4.0, Source: ECMWF", **k)

def fetch_ens_tp(cyc, s0, s1, stat="mean"):
    B, LA, LO = ens_members(cyc, s1, "tp")
    A = ens_members(cyc, s0, "tp")[0] if s0 > 0 else 0
    lat1, lon1, G = regular(_stat(np.clip(B - A, 0, None) * IN_PER_M, stat), LA, LO)
    return G, lat1, lon1, _ens_meta(cyc, stat, steps=[s0, s1], param="tp (accumulated) differenced per member")

def fetch_ens_snow(cyc, s0, s1, stat="mean"):
    B, LA, LO = ens_members(cyc, s1, "sf")
    A = ens_members(cyc, s0, "sf")[0] if s0 > 0 else 0
    lat1, lon1, G = regular(_stat(np.clip(B - A, 0, None) * IN_PER_M * 10, stat), LA, LO)
    return G, lat1, lon1, _ens_meta(cyc, stat, steps=[s0, s1], param="sf (m water eq.) x 10, per member", method="10:1")

def fetch_ens_temp(kind, date, cyc):
    d0 = dt.datetime(date.year, date.month, date.day, tzinfo=UTC)
    h_a, h_b = (12, 24) if kind == "high" else (6, 18)
    st = ens_steps(cyc); s_a = int((d0 + dt.timedelta(hours=h_a) - cyc).total_seconds() // 3600); s_b = s_a + (h_b - h_a)
    use = [s for s in st if s_a < s <= s_b]
    if not use: raise SystemExit("ENS %s: no steps for %s %s" % (cyc, kind, date))
    M = []
    for s in use:
        p = ("mx2t%d" if kind == "high" else "mn2t%d") % (3 if s <= 144 else 6)
        X, LA, LO = ens_members(cyc, s, p); M.append(X)
    M = (np.max if kind == "high" else np.min)(np.array(M), 0)
    lat1, lon1, G = regular((M.mean(0) - 273.15) * 9 / 5 + 32, LA, LO)
    return G, lat1, lon1, _ens_meta(cyc, "mean", steps=use, param=("mx2t" if kind == "high" else "mn2t") + " per member, window extreme")

LABELS = {
    "nbm":   dict(tag="[NBM 2.5 km]", sub="National Blend of Models (NBM)", src="Data: NOAA NBM (public domain)", res="NBM 2.5 km"),
    "gfs":   dict(tag="[GFS 0.25\u00b0]", sub="American Model (GFS)", src="Data: NOAA", res="GFS 0.25\u00b0"),
    "eps":   dict(tag="[ECMWF Ensemble Mean]", sub="European Ensemble Mean (ECMWF ENS)", src="Data: ECMWF (CC BY 4.0)", res="ECMWF ENS 50-member mean, 0.25\u00b0"),
    "eps90": dict(tag="[ECMWF Ens 90th %ile]", sub="European Ensemble 90th Percentile (ECMWF ENS)", src="Data: ECMWF (CC BY 4.0)",
                  res="ECMWF ENS 90th percentile of 50 members, 0.25\u00b0"),
}
FINEST_STEP = {"nbm": "1 h to 36 h, then 3 h / 6 h", "gfs": "3 h to 120 h, then 6 h", "eps": "3 h to 144 h, then 6 h", "eps90": "3 h to 144 h, then 6 h"}

def snap(source, cyc, h0, h1):
    if source == "gfs": return gfs_window(h0, h1)
    if source in ("eps", "eps90"): return ens_window(cyc, h0, h1)
    return max(0, h0), h1

def _exists(source, cyc, h):
    if source == "gfs": return _ok(gfs_url(cyc, max(h, 0)) + ".idx")
    if source == "nbm": return _ok(nbm_url(cyc, max(h, 1)) + ".idx")
    return _ok(ens_base(cyc, h) + ".index")

def pick(source, ws, we, cycle=None):
    if cycle: cands = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)]
    else:
        now = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        step = 1 if source == "nbm" else 6
        cands = [now - dt.timedelta(hours=h) for h in range(0, 31) if (now - dt.timedelta(hours=h)).hour % step == 0]
    for cyc in cands:
        h0 = int((ws - cyc).total_seconds() // 3600); h1 = int(-(-(we - cyc).total_seconds() // 3600))
        if h1 < 1: continue
        try: h0, h1 = snap(source, cyc, h0, h1)
        except ValueError: continue
        if cycle or _exists(source, cyc, h1): return cyc, h0, h1
    raise SystemExit("REFUSED: no %s run covers this window" % source.upper())

def fetch(product, source, cyc, h0, h1, date=None):
    stat = "p90" if source == "eps90" else "mean"
    if product == "rain":
        if source == "gfs": return fetch_gfs_apcp(cyc, h0, h1)
        if source in ("eps", "eps90"): return fetch_ens_tp(cyc, h0, h1, stat)
    if product == "snow":
        if source == "gfs": return fetch_gfs_kuchera(cyc, h0, h1)
        if source == "nbm": return fetch_nbm_asnow(cyc, h0, h1)
        if source in ("eps", "eps90"): return fetch_ens_snow(cyc, h0, h1, stat)
    if product == "gust":
        if source == "gfs": return fetch_gfs_gust(cyc, h0, h1)
        if source == "nbm": return fetch_nbm_gust(cyc, h0, h1)
    if product in ("high", "low"):
        if source == "gfs": return fetch_gfs_temp(product, date, cyc)
        if source == "eps": return fetch_ens_temp(product, date, cyc)
    raise SystemExit("no %s source for %s" % (source, product))

def load(product, source, cyc, h0, h1, cache, date=None, refresh=False):
    import subprocess, sys
    os.makedirs(cache, exist_ok=True)
    tag = date.isoformat() if date else "f%03d-%03d" % (h0, h1)
    npz = os.path.join(cache, "%s_%s_%s_%s.npz" % (source, product, cyc.strftime("%Y%m%d%HZ"), tag)); metaf = npz.replace(".npz", "_meta.json")
    if refresh or not os.path.exists(npz):
        subprocess.run([sys.executable, os.path.abspath(__file__), product, source, cyc.strftime("%Y%m%d%H"), str(h0), str(h1), npz, metaf,
                        date.isoformat() if date else ""], check=True)
    return np.load(npz), json.load(open(metaf))

if __name__ == "__main__":
    import sys
    pr, so, cy, h0, h1, npz, metaf, ds = sys.argv[1:9]
    G, lat1, lon1, meta = fetch(pr, so, dt.datetime.strptime(cy, "%Y%m%d%H").replace(tzinfo=UTC), int(h0), int(h1),
                                dt.date.fromisoformat(ds) if ds else None)
    np.savez_compressed(npz, g=np.asarray(G, dtype=np.float32), lat=lat1, lon=lon1); json.dump(meta, open(metaf, "w"), indent=1, default=str)
    sys.stdout.flush(); os._exit(0)
