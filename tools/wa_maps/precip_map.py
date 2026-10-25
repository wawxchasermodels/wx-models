#!/usr/bin/env python3
"""Estimated rain total maps for Washington (ECMWF IFS 0.1 deg, NOAA NBM, NOAA GFS, ECMWF ENS mean / 90th pct) and southern BC (mm).
Data: ECMWF open data (CC BY 4.0), NOAA (public domain). Basemap: U.S. Census, Natural Earth (public domain), GSHHG (NOAA, LGPL). Places: GeoNames (CC BY 4.0), Census Gazetteer (public domain).
Part of wx-models (MIT). Renders a static JPEG; no branding."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from render_core import asset as _asset
""\
\
\
\
\
\
\
\

import argparse, datetime as dt, json, math, os, re, sys, pickle, urllib.request, tempfile
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

UTC = dt.timezone.utc; PT = ZoneInfo("America/Los_Angeles")
BOX = (43.5, 51.2, -127.5, -114.5)
if os.environ.get("PM_BOX"): BOX = tuple(float(x) for x in os.environ["PM_BOX"].split(","))
MPH = 2.236936
ECM = "https://data.ecmwf.int/forecasts"
HRRR = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com"

def _get(url, rng=None, tries=3):
    for k in range(tries):
        try:
            rq = urllib.request.Request(url, headers={"Range": "bytes=%d-%d" % rng} if rng else {})
            with urllib.request.urlopen(rq, timeout=90) as r: return r.read()
        except Exception as e:
            if k == tries - 1: raise
def _ok(url):
    try: _get(url, (0, 0)); return True
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
                info = {k: eccodes.codes_get(g, k) for k in ["shortName", "name", "dataDate", "dataTime", "stepRange", "Ni", "Nj", "gridType"]}
                try: info["number"] = eccodes.codes_get(g, "number")
                except Exception: pass
                Ni, Nj = info["Ni"], info["Nj"]
                v = eccodes.codes_get_values(g).reshape(Nj, Ni)
                la = eccodes.codes_get_array(g, "latitudes").reshape(Nj, Ni); lo = eccodes.codes_get_array(g, "longitudes").reshape(Nj, Ni)
                lo = np.where(lo > 180, lo - 360, lo)
                m = (la > BOX[0]) & (la < BOX[1]) & (lo > BOX[2]) & (lo < BOX[3]); ii, jj = np.where(m)
                s = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1))
                out.append((v[s].copy(), la[s].copy(), lo[s].copy(), info))
    return out

def _window(date, start, end):
    ws = dt.datetime(date.year, date.month, date.day, start, tzinfo=PT).astimezone(UTC)
    we = dt.datetime(date.year, date.month, date.day, end, tzinfo=PT).astimezone(UTC)
    return ws, we

def _to_regular(V, LA, LO):
    if np.allclose(LA, LA[:, :1]) and np.allclose(LO, LO[:1, :]):
        lat1, lon1 = LA[:, 0], LO[0, :]; oi = np.argsort(lat1); oj = np.argsort(lon1)
        return lat1[oi], lon1[oj], V[oi][:, oj]
    from scipy.interpolate import griddata
    lat1 = np.arange(44.0, 50.8, 0.02); lon1 = np.arange(-127.0, -115.0, 0.02)
    LON, LAT = np.meshgrid(lon1, lat1)
    G = griddata((LO.ravel(), LA.ravel()), V.ravel(), (LON, LAT), method="linear")
    G = np.where(np.isfinite(G), G, griddata((LO.ravel(), LA.ravel()), V.ravel(), (LON, LAT), method="nearest"))
    return lat1, lon1, G

IN_PER_M = 39.37008
def run_steps(run):
    ""\

    st = list(range(0, 145, 3))
    if run.hour in (0, 12): st += list(range(150, 361, 6))
    return st

def plan_window(ws, we, run):
    st = run_steps(run); h0 = (ws - run).total_seconds() / 3600; h1 = (we - run).total_seconds() / 3600
    if h1 > st[-1] + 1e-6: raise ValueError("end %s is past run %s range (last step %d h = %s PT)" % (we.astimezone(PT).strftime("%a %m-%d %-I %p"),
                                            run.strftime("%Y%m%d%HZ"), st[-1], (run + dt.timedelta(hours=st[-1])).astimezone(PT).strftime("%a %m-%d %-I %p")))
    if h1 <= 0: raise ValueError("end is at or before run %s start" % run.strftime("%Y%m%d%HZ"))
    s0 = 0 if h0 <= 0 else min(st, key=lambda x: (abs(x - h0), -x))
    s1 = min(st, key=lambda x: (abs(x - h1), x))
    if s1 <= s0: raise ValueError("window too short for this run's steps (start step %d, end step %d)" % (s0, s1))
    note = []
    if h0 <= 0 and h0 < 0: note.append("start is before the run time, using step 0 (run start)")
    if abs(s0 - max(h0, 0)) > 1e-6 and h0 > 0: note.append("start snapped %+g h to step %d" % (s0 - h0, s0))
    if abs(s1 - h1) > 1e-6: note.append("end snapped %+g h to step %d" % (s1 - h1, s1))
    return s0, s1, "; ".join(note)

def step_url(run, stream, st):
    d8, hh = run.strftime("%Y%m%d"), run.hour
    return "%s/%s/%02dz/ifs/0p1/%s/%s%02d0000-%dh-%s-fc-sfc" % (ECM, d8, hh, stream, d8, hh, st, stream)

def pick_run(ws, we, cycle=None, log=print):
    now = dt.datetime.now(UTC)
    if cycle: runs = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)]
    else:
        base = now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0)
        runs = [base - dt.timedelta(hours=6 * k) for k in range(0, 12)]
    why = []
    for run in runs:
        try: s0, s1, note = plan_window(ws, we, run)
        except ValueError as e: why.append(str(e)); continue
        for stream in ("oper", "scda"):
            if all(_ok(step_url(run, stream, x) + ".index") for x in (s0, s1) if x > 0):
                return run, stream, s0, s1, note
        why.append("run %s not published yet (no tp index for steps %d/%d)" % (run.strftime("%Y%m%d%HZ"), s0, s1))
    raise SystemExit("REFUSED: no ECMWF 0.1 deg run covers this window.\n  " + "\n  ".join(why[:6]))

def fetch_tp(run, stream, s0, s1, log=print):
    recs = []
    for st in (s0, s1):
        if st == 0: recs.append(None); continue
        u = step_url(run, stream, st)
        js = [j for j in (json.loads(l) for l in _get(u + ".index").decode().splitlines()) if j.get("param") == "tp" and j.get("type") == "fc"]
        if len(js) != 1: raise SystemExit("tp record count %d in %s" % (len(js), u))
        recs.append((u + ".grib2", js[0]))
    log("ECMWF IFS 0.1 deg run %s stream %s tp steps %d and %d" % (run, stream, s0, s1))
    fl = [None if r is None else _decode(_get(r[0], (r[1]["_offset"], r[1]["_offset"] + r[1]["_length"] - 1)))[0] for r in recs]
    v1, LA, LO, info1 = fl[1]
    v0 = fl[0][0] if fl[0] is not None else np.zeros_like(v1)
    V = np.clip(v1 - v0, 0, None) * IN_PER_M
    lat1, lon1, G = _to_regular(V, LA, LO)
    meta = dict(model="ecmwf", run=run.strftime("%Y%m%d%HZ"), stream=stream, steps=[s0, s1], param="tp (m, accumulated from start)",
                grib_name=info1["name"], gridType=info1["gridType"], Ni_crop=int(G.shape[1]), Nj_crop=int(G.shape[0]),
                dlat=float(abs(lat1[1] - lat1[0])), dlon=float(abs(lon1[1] - lon1[0])), stepRange_end=info1["stepRange"],
                window_utc=[(run + dt.timedelta(hours=s0)).isoformat(), (run + dt.timedelta(hours=s1)).isoformat()],
                resolution="0.1 deg regular lat/lon (ECMWF open data ifs/0p1, from native ~9 km)", source=[r[0] if r else None for r in recs],
                bytes=sum(r[1]["_length"] for r in recs if r), license="CC BY 4.0, Source: ECMWF")
    return G, lat1, lon1, meta

NBM = "https://noaa-nbm-grib2-pds.s3.amazonaws.com"
MODEL_TAG_OVR = None
def _nbm_url(cyc, f): return "%s/blend.%s/%02d/core/blend.t%02dz.core.f%03d.co.grib2" % (NBM, cyc.strftime("%Y%m%d"), cyc.hour, cyc.hour, f)

def pick_nbm(ws, we, cycle=None):
    now = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    cycs = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)] if cycle else [now - dt.timedelta(hours=k) for k in range(0, 25)]
    why = []
    for cyc in cycs:
        h0 = (ws - cyc).total_seconds() / 3600; h1 = (we - cyc).total_seconds() / 3600
        if h1 < 1: continue
        note = []
        s0 = max(0, int(round(h0))); s1 = int(round(h1))
        if h0 < 0: note.append("start is before the NBM run time, using f000 (run start)")
        elif abs(s0 - h0) > 1e-6: note.append("start snapped %+g h" % (s0 - h0))
        if abs(s1 - h1) > 1e-6: note.append("end snapped %+g h" % (s1 - h1))
        if s1 <= s0: continue
        if h0 < 0 and not cycle: why.append("%s starts after the window start" % cyc.strftime("%Y%m%d%HZ")); continue
        if _ok(_nbm_url(cyc, s1) + ".idx"): return cyc, s0, s1, "; ".join(note)
        why.append("NBM %s f%03d not published" % (cyc.strftime("%Y%m%d%HZ"), s1))
    raise SystemExit("REFUSED: no NBM core cycle covers this window.\n  " + "\n  ".join(why[:6]))

def _decode_nbm(blob):
    import eccodes
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf_:
        tf_.write(blob); tf_.flush()
        with open(tf_.name, "rb") as fh:
            g = eccodes.codes_grib_new_from_file(fh)
            info = {k: eccodes.codes_get(g, k) for k in ["shortName", "name", "dataDate", "dataTime", "stepRange", "Ni", "Nj", "gridType"]}
            alt = eccodes.codes_get(g, "alternativeRowScanning"); miss = eccodes.codes_get(g, "missingValue")
            Ni, Nj = info["Ni"], info["Nj"]
            v = eccodes.codes_get_values(g).reshape(Nj, Ni).copy()
            la = eccodes.codes_get_array(g, "latitudes").reshape(Nj, Ni); lo = eccodes.codes_get_array(g, "longitudes").reshape(Nj, Ni)
    if alt: v[1::2] = v[1::2, ::-1]
    lo = np.where(lo > 180, lo - 360, lo)
    m = (la > BOX[0]) & (la < BOX[1]) & (lo > BOX[2]) & (lo < BOX[3]); ii, jj = np.where(m)
    s = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1))
    v = v[s]; nmiss = int(np.sum(v == miss)); v = np.where(v == miss, 0.0, v)
    return v, la[s].copy(), lo[s].copy(), dict(info, alternativeRowScanning=int(alt), n_missing=nmiss)

def fetch_nbm(cyc, h0, h1, log=print):
    from concurrent.futures import ThreadPoolExecutor
    idx = {}
    def gidx(f):
        if f not in idx:
            try: idx[f] = _get(_nbm_url(cyc, f) + ".idx").decode().splitlines()
            except Exception: idx[f] = []
        return idx[f]
    def rec(f, a):
        L = gidx(f)
        for i, l in enumerate(L):
            if re.search(r":APCP:surface:%d-%d hour acc fcst:$" % (a, f), l):
                return (_nbm_url(cyc, f), int(l.split(":")[1]), int(L[i + 1].split(":")[1]) - 1 if i + 1 < len(L) else None, l)
        return None
    with ThreadPoolExecutor(12) as ex: list(ex.map(gidx, range(h0 + 1, h1 + 1)))
    plan = []; h = h0
    while h < h1:

        r = rec(h + 6, h) if (h % 6 == 0 and h + 6 <= h1) else None
        r = r or rec(h + 1, h)
        if not r:
            for n in (6, 3):
                if h + n <= h1 and (r := rec(h + n, h)): break
        if not r: raise SystemExit("NBM %s: no APCP record covering hour %d-%d" % (cyc.strftime("%Y%m%d%HZ"), h, h + 1))
        a_, f_ = map(int, re.search(r"APCP:surface:(\d+)-(\d+) hour", r[3]).groups()); plan.append(r); h = f_
    def dl(r): return _get(r[0], (r[1], r[2] if r[2] is not None else r[1] + 50_000_000))
    with ThreadPoolExecutor(12) as ex: blobs = list(ex.map(dl, plan))
    tot = None; nmiss = 0
    for b in blobs:
        v, LA, LO, info = _decode_nbm(b); tot = v if tot is None else tot + v; nmiss = max(nmiss, info["n_missing"])
    log("NBM core %s f%03d-f%03d: %d APCP records" % (cyc.strftime("%Y%m%d%HZ"), h0, h1, len(plan)))
    V = np.clip(tot, 0, None) / 25.4
    lat1, lon1, G = _to_regular(V, LA, LO)
    meta = dict(model="nbm", run=cyc.strftime("%Y%m%d%HZ"), fhr=[h0, h1], n_records=len(plan), records=[r[3] for r in plan],
                param="APCP:surface (kg m-2 = mm), sum of 6 h records (whole 6-hourly blocks) + 1 h records at the window edges",
                window_utc=[(cyc + dt.timedelta(hours=h0)).isoformat(), (cyc + dt.timedelta(hours=h1)).isoformat()], max_missing_points_in_crop=nmiss,
                resolution="NBM core CONUS 2.5 km Lambert, regridded (linear) to 0.02 deg", source=_nbm_url(cyc, h1), license="NOAA, public domain")
    return G, lat1, lon1, meta

def fetch_hrrr(date, start, end, cycle=None, log=print, uv=False):
    ws, we = _window(date, start, end)
    now = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    cycles = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)] if cycle else [now - dt.timedelta(hours=k) for k in range(0, 12)]
    for cyc in cycles:
        f_end = int((we - cyc).total_seconds() // 3600)
        if f_end > (48 if cyc.hour % 6 == 0 else 18): continue
        base = "%s/hrrr.%s/conus/hrrr.t%02dz.wrfsfcf%%02d.grib2" % (HRRR, cyc.strftime("%Y%m%d"), cyc.hour)
        if not _ok((base % f_end) + ".idx"): continue
        f0 = max(0, int((ws - cyc).total_seconds() // 3600))
        fhs = list(range(f0, f_end + 1)); stack = []; recs = []; usum = vsum = None; nuv = 0; uvinfo = {}
        for f in fhs:
            u = base % f; lines = _get(u + ".idx").decode().splitlines()
            for i, l in enumerate(lines):
                if ":GUST:surface:" in l:
                    a = int(l.split(":")[1]); b = int(lines[i + 1].split(":")[1]) - 1
                    v, la, lo, info = _decode(_get(u, (a, b)))[0]; stack.append(v); recs.append(l); break
            if uv:
                got = {}
                for i, l in enumerate(lines):
                    for key in (":UGRD:10 m above ground:", ":VGRD:10 m above ground:"):
                        if key in l and ("hour fcst" in l or ":anl:" in l) and "max" not in l and "ave" not in l:
                            got[key] = (int(l.split(":")[1]), int(lines[i + 1].split(":")[1]) - 1, l)
                if len(got) != 2: break
                U, la2, lo2, rel, lov, latin, _ = _decode_uv(_get(u, got[":UGRD:10 m above ground:"][:2]))
                V, _, _, _, _, _, _ = _decode_uv(_get(u, got[":VGRD:10 m above ground:"][:2]))
                m_ = (la2 > BOX[0]) & (la2 < BOX[1]) & (lo2 > BOX[2]) & (lo2 < BOX[3]); ii, jj = np.where(m_)
                sl = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1)); U, V, la2, lo2 = U[sl], V[sl], la2[sl], lo2[sl]
                if rel:
                    lv = lov - 360 if lov > 180 else lov
                    ang = np.deg2rad(math.sin(math.radians(latin)) * (lo2 - lv)); c_, s_ = np.cos(ang), np.sin(ang)
                    U, V = c_ * U + s_ * V, -s_ * U + c_ * V
                usum = U if usum is None else usum + U; vsum = V if vsum is None else vsum + V; nuv += 1
                uvinfo = dict(uvRelativeToGrid=int(rel), LoV=lov, Latin1=latin); recs += [g_[2] for g_ in got.values()]
        if len(stack) != len(fhs): log("HRRR %s missing GUST records, skip" % cyc); continue
        if uv and nuv != len(fhs): log("HRRR %s missing UGRD/VGRD records, skip" % cyc); continue
        log("HRRR cycle %s f%02d-f%02d (%d hourly GUST)" % (cyc, fhs[0], fhs[-1], len(stack)))
        lat1, lon1, G = _to_regular(np.max(stack, 0) * MPH, la, lo)
        meta = dict(model="hrrr", run=cyc.strftime("%Y%m%d%HZ"), fhr=[fhs[0], fhs[-1]], records=recs, param="GUST:surface (instantaneous, hourly)",
                    valid_utc=[(cyc + dt.timedelta(hours=fhs[0])).isoformat(), (cyc + dt.timedelta(hours=fhs[-1])).isoformat()],
                    window_utc=[ws.isoformat(), we.isoformat()], resolution="3 km Lambert, regridded to 0.02 deg", source=base % fhs[0], license="NOAA, public domain")
        if uv:
            _, _, UE = _to_regular(usum / nuv, la2, lo2); _, _, VE = _to_regular(vsum / nuv, la2, lo2)
            meta.update(wind="vector mean of %d hourly UGRD/VGRD 10 m (earth-relative), direction only; arrow length = window max gust" % nuv, **uvinfo)
            return G, lat1, lon1, meta, UE, VE
        return G, lat1, lon1, meta
    raise SystemExit("no HRRR cycle reaches the window end")

def _decode_uv(blob):
    import eccodes
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf_:
        tf_.write(blob); tf_.flush()
        with open(tf_.name, "rb") as fh:
            g = eccodes.codes_grib_new_from_file(fh)
            Ni, Nj = eccodes.codes_get(g, "Nx"), eccodes.codes_get(g, "Ny")
            v = eccodes.codes_get_values(g).reshape(Nj, Ni)
            la = eccodes.codes_get_array(g, "latitudes").reshape(Nj, Ni); lo = eccodes.codes_get_array(g, "longitudes").reshape(Nj, Ni)
            rel = eccodes.codes_get(g, "uvRelativeToGrid"); lov = eccodes.codes_get(g, "LoVInDegrees"); lat1 = eccodes.codes_get(g, "Latin1InDegrees")
            sn = eccodes.codes_get(g, "shortName")
    lo = np.where(lo > 180, lo - 360, lo)
    return v, la, lo, rel, lov, lat1, sn

def fetch_hrrr_valid(valid, cycle=None, log=print):
    ""\

    now = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    cycles = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)] if cycle else [now - dt.timedelta(hours=k) for k in range(0, 12)]
    for cyc in cycles:
        f = int((valid - cyc).total_seconds() // 3600)
        if f < 0 or f > (48 if cyc.hour % 6 == 0 else 18): continue
        u = "%s/hrrr.%s/conus/hrrr.t%02dz.wrfsfcf%02d.grib2" % (HRRR, cyc.strftime("%Y%m%d"), cyc.hour, f)
        if not _ok(u + ".idx"): continue
        lines = _get(u + ".idx").decode().splitlines(); got = {}
        for i, l in enumerate(lines):
            for key in (":GUST:surface:", ":UGRD:10 m above ground:", ":VGRD:10 m above ground:"):
                if key in l and "hour fcst" in l and "max" not in l and "ave" not in l:
                    a = int(l.split(":")[1]); b = int(lines[i + 1].split(":")[1]) - 1; got[key] = (a, b, l)
        if len(got) != 3: log("HRRR %s f%02d missing GUST/UGRD/VGRD, skip" % (cyc, f)); continue
        log("HRRR cycle %s f%02d valid %s" % (cyc, f, valid))
        g, la, lo, info = _decode(_get(u, got[":GUST:surface:"][:2]))[0]
        U, la2, lo2, rel, lov, latin, _ = _decode_uv(_get(u, got[":UGRD:10 m above ground:"][:2]))
        V, _, _, rel2, _, _, _ = _decode_uv(_get(u, got[":VGRD:10 m above ground:"][:2]))
        m = (la2 > BOX[0]) & (la2 < BOX[1]) & (lo2 > BOX[2]) & (lo2 < BOX[3]); ii, jj = np.where(m)
        sl = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1)); U, V, la2, lo2 = U[sl], V[sl], la2[sl], lo2[sl]
        if rel:
            lv = lov - 360 if lov > 180 else lov
            ang = np.deg2rad(math.sin(math.radians(latin)) * (lo2 - lv)); c_, s_ = np.cos(ang), np.sin(ang)
            U, V = c_ * U + s_ * V, -s_ * U + c_ * V
        lat1, lon1, G = _to_regular(g * MPH, la, lo)
        _, _, UE = _to_regular(U, la2, lo2); _, _, VE = _to_regular(V, la2, lo2)
        meta = dict(model="hrrr", run=cyc.strftime("%Y%m%d%HZ"), fhr=[f, f], records=[v[2] for v in got.values()],
                    param="GUST:surface (instantaneous at the valid hour)", wind="UGRD/VGRD 10 m, rotated grid->earth" if rel else "UGRD/VGRD 10 m (earth-relative in file)",
                    uvRelativeToGrid=int(rel), LoV=lov, Latin1=latin, valid_utc=[valid.isoformat(), valid.isoformat()],
                    resolution="3 km Lambert, regridded to 0.02 deg", source=u, license="NOAA, public domain")
        return G, lat1, lon1, meta, UE, VE
    raise SystemExit("no HRRR cycle reaches the valid hour")

W, H = 2400, 1600
PASSES = {"Snoqualmie Pass": (-121.4136, 47.4245), "Stevens Pass": (-121.0854, 47.7465), "White Pass": (-121.3911, 46.6383),
          "Chinook Pass": (-121.5156, 46.8714), "Blewett Pass": (-120.5786, 47.3348), "Sherman Pass": (-118.4636, 48.6055),
          "Loup Loup Pass": (-119.9026, 48.3926), "Washington Pass": (-120.6545, 48.5253)}
CORE = ["Bellingham", "Seattle", "Spokane", "Vancouver", "Tacoma", "Olympia", "Everett", "Mount Vernon", "Oak Harbor",
        "Wenatchee", "Yakima", "Kennewick", "Walla Walla", "Ellensburg"]
BACK = ["Cle Elum", "Leavenworth", "Port Townsend", "Winthrop", "Toppenish", "Oroville", "Republic", "Quincy", "Stevenson",
        "Pullman", "Moses Lake", "Omak", "Colville", "Aberdeen",
        "Port Angeles", "Longview",
        "White Salmon", "Goldendale", "Forks", "Ocean Shores", "Long Beach", "Centralia", "Shelton", "Chelan", "Newport", "Cheney", "Davenport", "Ritzville", "Odessa",
        "Ephrata", "Othello", "Sunnyside", "Prosser", "Dayton", "Clarkston", "Colfax", "Grand Coulee", "Raymond", "Packwood"]

EXTRA = ["Richland", "Pasco", "Anacortes", "Sequim", "Lynden", "Arlington", "Monroe", "North Bend", "Enumclaw", "Puyallup", "Bremerton", "Poulsbo",
         "Hoquiam", "Westport", "Neah Bay", "Chehalis", "Morton", "Ashford", "Eatonville", "Montesano", "Elma", "Ilwaco", "Cathlamet", "Castle Rock",
         "Woodland", "Battle Ground", "Camas", "Carson", "Trout Lake", "Bingen", "Glenwood", "Roosevelt", "Bickleton", "Twisp", "Tonasket", "Brewster",
         "Pateros", "Okanogan", "Coulee City", "Wilbur", "Waterville", "Entiat", "Cashmere", "Roslyn", "Kittitas", "Naches", "Selah", "Wapato",
         "Grandview", "Granger", "Benton City", "Mattawa", "Royal City", "Warden", "Soap Lake", "George", "Connell", "Mesa", "Kahlotus", "Washtucna",
         "Lind", "Sprague", "Harrington", "Almira", "Creston", "Reardan", "Medical Lake", "Deer Park", "Chewelah", "Kettle Falls", "Northport", "Ione",
         "Metaline Falls", "Curlew", "Inchelium", "Keller", "Nespelem", "Loomis", "Waitsburg", "Pomeroy", "Asotin", "Tekoa", "Rosalia", "St. John",
         "Oakesdale", "Palouse", "Endicott", "Concrete", "Darrington", "Sedro-Woolley", "Coupeville", "Friday Harbor", "Skykomish", "Gold Bar",
         "Langley", "Kingston", "Port Orchard", "Spokane Valley"]

WEST_KEEP = ["Lynden", "Friday Harbor", "Neah Bay", "Poulsbo", "Bremerton", "Enumclaw", "Morton", "Castle Rock", "Cathlamet", "Darrington", "Battle Ground"]
WEST = ["Marysville", "Arlington", "Lake Stevens", "Snohomish", "Monroe", "Sultan", "Gold Bar", "Granite Falls", "Duvall", "Woodinville", "Redmond",
        "Bellevue", "Issaquah", "North Bend", "Snoqualmie", "Renton", "Kent", "Auburn", "Maple Valley", "Black Diamond", "Buckley", "Bonney Lake",
        "Puyallup", "Orting", "Eatonville", "Yelm", "Sedro-Woolley", "Concrete", "Lynnwood", "Gig Harbor",
        "Burlington", "Stanwood", "Ferndale", "Blaine", "Sumas", "Anacortes", "Coupeville", "Langley", "Silverdale", "Port Orchard", "Kingston",
        "Belfair", "Quilcene", "Brinnon", "Hoodsport", "Sequim", "Clallam Bay", "Amanda Park", "Hoquiam", "Westport", "Elma", "McCleary", "Tenino",
        "Rochester", "Chehalis", "Winlock", "Toledo", "Pe Ell", "Kelso", "Kalama", "Woodland", "Ridgefield", "Camas", "Washougal", "Ilwaco",
        "South Bend", "Naselle", "Ocean Park", "Mossyrock", "Ashford", "Carnation", "Fall City", "Federal Way", "Lakewood", "DuPont", "Edmonds",
        "Mukilteo", "Bainbridge Island"]
EXTRA = [t for t in EXTRA if t not in WEST and t not in WEST_KEEP]
OPTIONAL = set(WEST_KEEP) | set(WEST) | set(EXTRA)
TOWNS = CORE + list(PASSES) + BACK + WEST_KEEP + WEST + EXTRA

import town_pop as TP
OPTIONAL = {t for t in OPTIONAL if TP.tier(t)[0] >= 3}

TOWNS += [t for t in TP.always_list() if t not in TOWNS]
TOWNS += [t for t in sorted(TP.SOFT, key=lambda t: -TP.pop(t)) if t not in TOWNS]; OPTIONAL |= TP.SOFT
_BIG = sorted([t for t in TOWNS if TP.always(t, t in PASSES)], key=lambda t: -TP.pop(t))
ORDER = _BIG + list(PASSES) + ["Oak Harbor"] + \
        sorted([t for t in TOWNS if t not in OPTIONAL and t not in PASSES and t not in _BIG and t != "Oak Harbor"], key=lambda t: -TP.pop(t)) + \
        sorted([t for t in TOWNS if t in OPTIONAL], key=lambda t: -TP.pop(t))

WEST = [t for t in WEST if t not in TP.DROP]; WEST_KEEP = [t for t in WEST_KEEP if t not in TP.DROP]
TOWNS = [t for t in TOWNS if t not in TP.DROP]; TOWNS += [t for t in TP.REQUESTED if t not in TOWNS]
OPTIONAL = {t for t in OPTIONAL if t not in TP.REQUESTED and t not in TP.DROP}
_HEAD = sorted([t for t in TOWNS if (t in TP.MUST or t in TP.LOCKED) and t != "Oak Harbor"], key=lambda t: -TP.pop(t))
_REQ = sorted(TP.REQUESTED, key=lambda t: -TP.pop(t))
ORDER = _HEAD + list(PASSES) + ["Oak Harbor"] + _REQ + [t for t in ORDER if t not in _HEAD and t not in PASSES and t != "Oak Harbor" and t not in _REQ and t not in TP.DROP]

DBG = {}
FLIP = set()
NO_CORNER = False
def render(TF, LAT1, LON1, title, subtitle, out_path, model_line, src, sub_title=None, UV=None):
    kind = 'gust'
    LO, LA = np.meshgrid(LON1, LAT1)
    from PIL import Image, ImageDraw, ImageFilter
    import render_core as R
    from save_final import save_final
    from shapely.geometry import box as sbox
    from shapely import contains_xy
    import pyproj
    R.W, R.H = W, H
    y0, x0 = LAT1[0], LON1[0]; dy = (LAT1[-1] - y0) / (len(LAT1) - 1); dx = (LON1[-1] - x0) / (len(LON1) - 1)
    def sample(lon, lat):
        x, y = lon, lat; fi = (y - y0) / dy; fj = (x - x0) / dx
        i0 = np.clip(np.floor(fi).astype(int), 0, TF.shape[0] - 2); j0 = np.clip(np.floor(fj).astype(int), 0, TF.shape[1] - 2)
        ti = np.clip(fi - i0, 0, 1); tj = np.clip(fj - j0, 0, 1)
        return (TF[i0, j0] * (1 - ti) * (1 - tj) + TF[i0 + 1, j0] * ti * (1 - tj) + TF[i0, j0 + 1] * (1 - ti) * tj + TF[i0 + 1, j0 + 1] * ti * tj)
    P = R.frame(sbox(*FRAME_BOX), box_w=FRAME_W, box_h=FRAME_BH, cy=FRAME_CY)
    lo0, la0, lo1, la1 = P.bounds_ll()
    import forecast_base as FB
    im = FB.dark_base(R, P, 1.0)
    wa = [g for p_, g in pickle.load(open(R.BM + "/cb_2023_us_state_500k.pkl", "rb")) if p_.get("STUSPS") == "WA"][0]

    EDGES = PEDGES; LOB, HIB = 0, len(PCOLS)
    COLS = PCOLS
    assert len(COLS) == len(EDGES) - 1
    S = 3; WS, HS = W * S, H * S
    xs = P.x0 + (np.arange(WS) + 0.5) / (P.k * S); ys = P.y0 + (np.arange(HS) + 0.5) / (P.k * S)
    lonr, _ = R.px2ll(xs, np.zeros_like(xs)); _, latr = R.px2ll(np.zeros_like(ys), ys)
    V = np.empty((HS, WS), np.float32); VALID = np.zeros((HS, WS), bool) if FILL_NEIGHBORS else None
    for r0 in range(0, HS, 600):
        LON, LAT = lonr[None, :], latr[r0:r0 + 600, None]; V[r0:r0 + 600] = sample(LON, LAT)
        if FILL_NEIGHBORS:
            fi_ = (LAT - y0) / dy; fj_ = (LON - x0) / dx
            VALID[r0:r0 + 600] = (fi_ >= 0) & (fi_ <= TF.shape[0] - 1) & (fj_ >= 0) & (fj_ <= TF.shape[1] - 1) & np.isfinite(V[r0:r0 + 600])
    del LON, LAT
    idx = np.clip(np.searchsorted(np.array(EDGES, np.float32), V, side='right') - 1, -1, len(COLS) - 1).astype(np.int16)
    DRY = idx < 0; idx = np.maximum(idx, 0)
    rgb = np.array(COLS, np.uint8)[idx]
    wm = Image.new("L", (WS, HS), 0); dw = ImageDraw.Draw(wm)
    for pg in R.polys(wa): dw.polygon([(x * S, y * S) for x, y in P.ring(pg.exterior.coords)], fill=255)
    wam = np.asarray(wm) > 127
    fm = wam
    if FILL_NEIGHBORS:
        import region_maps as RM; fm = RM.fill_mask(R, Image, WS, HS, wam, VALID); del VALID
    alpha = np.where(fm & ~DRY, 255, 0).astype(np.uint8)
    idx = np.where(DRY, -1, idx)

    cidx = np.where(DRY, -1, np.searchsorted(np.array(CEDGES, np.float32), V, side='right')).astype(np.int16)
    e = (cidx[:, 1:] != cidx[:, :-1]); ev = (cidx[1:, :] != cidx[:-1, :]); idx = np.maximum(idx, 0); del DRY, cidx
    edge = np.zeros_like(idx, bool); edge[:, 1:] |= e; edge[1:, :] |= ev
    from scipy.ndimage import binary_dilation
    edge = binary_dilation(edge, iterations=1) & fm
    rgba = np.dstack([rgb, alpha])
    rgba[edge] = (rgba[edge].astype(int) * [0.55, 0.55, 0.55, 1]).astype(np.uint8)
    ov = Image.fromarray(rgba, "RGBA").resize((W, H), Image.LANCZOS)
    _a = ov.getchannel("A"); ov = ov.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2)).convert("RGBA"); ov.putalpha(_a)
    im.alpha_composite(ov); del rgba, V, idx
    if NEIGHBOR_DIM:
        dim = Image.fromarray(np.where(np.asarray(wm.resize((W, H), Image.BILINEAR)) > 127, 0, NEIGHBOR_DIM).astype(np.uint8))
        im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [dim]))
    R.draw_borders_on_top(im, P, 1.0, Image.new("L", (W, H), 120))

    t1, b0 = TOP_FADE, H - BOT_FADE; al = np.zeros(H, np.uint8)
    for y in range(H):
        if y < t1: al[y] = int(170 * 0.5 * (1 + math.cos(math.pi * y / t1)))
        elif y >= b0: al[y] = int(150 * 0.5 * (1 - math.cos(math.pi * (y - b0) / (H - b0))))
    fade = Image.new("RGBA", (W, H), (0, 0, 0, 0)); fade.putalpha(Image.fromarray(np.repeat(al[:, None], W, 1), "L")); im.alpha_composite(fade)
    d = ImageDraw.Draw(im)
    BAR_Y = None
    if TOP_BAR:
        import region_maps as RM; BAR_Y = int(round(RM.bar_bottom(P, lo0, lo1))) - 2
        if not VSCALE: d.rectangle((0, 0, W, BAR_Y), fill=(0, 0, 0))
    pts = dict(PASSES)
    for l in open(_asset("2023_Gaz_place_national.txt"), encoding="latin-1"):
        c = l.rstrip("\n").split("\t")
        if c[0] != "WA": continue
        for suf in (" city", " town", " CDP"):
            nm = c[3][:-len(suf)]
            if c[3].endswith(suf) and nm in TOWNS and not (suf == " CDP" and nm in pts): pts[nm] = (float(c[11]), float(c[10]))
    if REGION:
        pts.update({k: v for k, v in TP.REGION_POINTS.items() if k in TOWNS and k not in pts})
        bx_ = TP.REGION_LABEL[REGION]
        pts = {k: v for k, v in pts.items() if bx_[0] <= v[0] <= bx_[2] and bx_[1] <= v[1] <= bx_[3]}

    REAL = {k: (v if k in PASSES else TP.real_point(k, v)) for k, v in pts.items()}
    WHITE, ICE, HOT, INK = (255, 255, 255), (150, 220, 255), (255, 72, 60), (14, 16, 22)
    GOLD = (255, 196, 64)
    def val_color(t):
        return WHITE

    im_rgb_title = []
    def centered(path, txt, size, y, fill, wg=None, off=6, maxw=W - 600, draw=True):
        while size > 10:
            fo = R.font(path, size, wg)
            if d.textlength(txt, font=fo) <= maxw: break
            size -= 2
        tw = d.textlength(txt, font=fo); x = (W - tw) / 2
        if draw: d.text((x + off, y + off), txt, font=fo, fill=(0, 0, 0)); d.text((x, y), txt, font=fo, fill=fill)
        return size, (x, y, x + tw, y + size * 1.15)
    TCOL = (255, 255, 255)
    def header(f, draw):
        S_ = lambda px: max(10, int(round(px * f)))
        sz, tb = centered(R.IMPACT, title, S_(TITLE_PX), TITLE_Y, TCOL, off=7, draw=draw, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}))
        if REGION_SUB:
            _, tb2 = centered(R.MONT, REGION_SUB, S_(RSUB_PX), int(tb[3]) + 2, TCOL, wg=800, off=4, draw=draw); tb = (min(tb[0], tb2[0]), tb[1], max(tb[2], tb2[2]), tb2[3])
        if WIN_LINE:
            _, tb3 = centered(R.MONT, WIN_LINE, S_(WIN_PX), int(tb[3]) + 0, TCOL, wg=800, off=4, draw=draw); tb = (min(tb[0], tb3[0]), tb[1], max(tb[2], tb3[2]), tb3[3])
        if sub_title:
            _, sb = centered(R.MONT, sub_title, S_(GSUB_PX), SUB_Y if not (REGION_SUB or WIN_LINE) else int(tb[3]) + 4, TCOL, wg=700, off=3, draw=draw)
            tb = (min(tb[0], sb[0]), tb[1], max(tb[2], sb[2]), sb[3])
        return sz, tb

    _ft20 = R.font(R.MONT, 20, 700); _tick_h = SCALE_BH + 6 + _ft20.getbbox("0")[3] + 3
    _, tb_orig = header(1.0, False); by0_orig = max(SCALE_Y, int(tb_orig[3]) + 8); HDR_F = 1.0
    if BAR_Y and by0_orig + _tick_h > BAR_Y - 8:
        for HDR_F in (0.95, 0.92, 0.89, 0.86, 0.83, 0.80, 0.77, 0.74, 0.71):
            _, tb_ = header(HDR_F, False)
            if int(tb_[3]) + 8 + _tick_h <= BAR_Y - 8: break
    BAR_D = None
    if VSCALE:
        _, tt_ = centered(R.IMPACT, title, TITLE_PX, TITLE_Y, TCOL, off=7, draw=False, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}))
        import region_maps as RM
        TS = RM.top_scale_geom(W, int(tt_[3]), (CORNER_PAD or int(W * 0.015)) + (CORNER_S or int(W * 0.075)))
        BAR_D = TS[2] + SCALE_BH + 6 + 26
        RM.top_fade(im, W, BAR_D); d = ImageDraw.Draw(im)
        sz, tt_ = centered(R.IMPACT, title, TITLE_PX, TITLE_Y, TCOL, off=7, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}))
        tb = tb_orig; HDR_F = 1.0
    else: sz, tb = header(HDR_F, True)

    _lp, _ls = (CORNER_PAD or int(W * 0.015)), (CORNER_S or int(W * 0.075))
    if globals().get("WEST_TIGHT") and VSCALE: tb = tt_
    placed = [tb, (0, 0, _lp + _ls + 10, _lp + _ls + 10)]
    MODEL_TAG = MODEL_TAG_OVR or "[ECMWF 9 km]"

    fmt_ = R.font(R.MONT, 32, 700); mtw_ = d.textlength(MODEL_TAG, font=fmt_)
    d.text((W - 34, 30), MODEL_TAG, font=fmt_, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK, anchor="ra")
    placed.append((W - 34 - mtw_ - 12, 18, W, 30 + 32 + 16))
    KO_TB = tb; KO_BAR = (0, 0, W, BAR_Y + 4) if BAR_Y else None
    if BAR_Y: placed.append(KO_BAR)
    bx0, bx1, by0, bh = SCALE_X0, SCALE_X1, (max(SCALE_Y, int(tb[3]) + 8) if HDR_F == 1.0 else int(tb[3]) + 8), SCALE_BH
    tx_ = lambda t: bx0 + (bx1 - bx0) * (t - LOB) / (HIB - LOB)
    fT = R.font(R.MONT, 26, 800); lt = "Inches"; ltw = d.textlength(lt, font=fT)
    if VSCALE: bx0, bx1, by0 = TS
    if True:
      d.text(((bx0, by0 - 36) if VSCALE else (bx0 - 18 - ltw, by0 + bh / 2 - 16)), lt, font=fT, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK)
      d.rectangle((bx0 - 2, by0 - 2, bx1 + 2, by0 + bh + 2), fill=INK)
      for i_, c in enumerate(COLS): d.rectangle((round(tx_(i_)), by0, round(tx_(i_ + 1)), by0 + bh), fill=c)
    ft = R.font(R.MONT, 20, 700); _last = -1e9
    for t in range(0, len(COLS)):
        lab = PLABS[t]
        if not lab: continue
        xx = round(tx_(t)); lw = d.textlength(lab, font=ft)
        if xx - lw / 2 < _last + 6: continue
        d.line((xx, by0 + bh, xx, by0 + bh + 5), fill=(255, 255, 255), width=2)
        d.text((xx - lw / 2, by0 + bh + 6), lab, font=ft, fill=(255, 255, 255), stroke_width=3, stroke_fill=INK); _last = xx + lw / 2
    KO_LEG = (SCALE_X0 - 24 - ltw, by0_orig - 8, SCALE_X1 + 30, by0_orig + bh + 34); placed.append(KO_LEG)
    if globals().get("WEST_TIGHT") and VSCALE: placed[-1] = KO_LEG = (bx0 - 10, by0 - 40, bx1 + 10, BAR_D)

    inwa = contains_xy(wa, LO, LA)
    if REGION: inwa &= (LO >= lo0) & (LO <= lo1) & (LA >= la0) & (LA <= la1)
    tw_ = TF[inwa]

    SUM_R, SUM_B = W - 30, H - 30
    sum_box = (SUM_R - SUM_MAXW - 10, SUM_B - SUM2_PX - SUM_GAP - SUM1_PX - 14, W, H)
    placed.append(sum_box)

    DATE_L, DATE_B = 30, H - 30; fdate = R.font(R.MONT, SUM2_PX, 800); fs = R.font(R.MONT, 22, 600)
    fmod = R.font(R.MONT, MODEL_PX, 700)
    date_w = max(d.textlength(subtitle, font=fdate), d.textlength(model_line, font=fmod)); MOD_B = DATE_B - SUM2_PX - 10; CRED_Y = MOD_B - MODEL_PX - 34

    placed.append((0, DATE_B - SUM2_PX - 4, DATE_L + d.textlength(subtitle, font=fdate) + 12, H))
    placed.append((0, MOD_B - MODEL_PX - 4, DATE_L + d.textlength(model_line, font=fmod) + 12, MOD_B + 10))
    placed.append((0, CRED_Y - 8, DATE_L + d.textlength(src, font=fs) + 12, MOD_B - MODEL_PX - 4))

    fl = R.font(R.MONT, NAME_PX, 700); fv = R.font(R.MONT, VAL_PX, 800)
    NA = fl.getbbox("Ag")[3]; VH = fv.getbbox("0")[3]; GAP = -2
    th0 = NA + GAP + VH + 2
    marks = {}
    for name in TOWNS:
        if name in pts and name not in OPTIONAL:
            x, y = P(*pts[name]); marks[name] = (x - 1, y - 1, x + 1, y + 1)
    base_placed = list(placed)
    def place(excl):
        rx = {marks[n] for n in excl if n in marks and n not in OPTIONAL}
        placed = [p for p in base_placed if p not in rx]
        vals = {}; skipped = []; lay = {}
        def hits_of(bb, me):
            return [p for p in placed if p != me and not (bb[2] < p[0] or bb[0] > p[2] or bb[3] < p[1] or bb[1] > p[3])]

        prer = {}
        for name in [n for n in WEST_KEEP if n in ('Poulsbo', 'Bremerton', 'Enumclaw')] + WEST[:N_CORRIDOR]:
            if True: continue
            if name in excl: continue
            if name not in pts: continue
            x, y = P(*pts[name]); mk = (x - 1, y - 1, x + 1, y + 1)
            if not hits_of((mk[0] - 12, mk[1] - 12, mk[2] + 12, mk[3] + 12), None): prer[name] = mk; placed.append(mk)
        dropped = set()
        def free(bb, me): return not hits_of(bb, me)
        def inside(bb): return bb[0] >= 16 and bb[2] <= W - 16 and bb[1] >= 16 and bb[3] <= H - 12

        FT = {}
        for t_, npx, vpx, swt, rrt in [(i + 1,) + tuple(x[1:]) for i, x in enumerate(TIERS_OVR or TP.TIERS)]:
            f1_ = R.font(R.MONT, npx, 700); f2_ = R.font(R.MONT, vpx, 800); na_ = f1_.getbbox("Ag")[3]
            FT[t_] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, swt, rrt)
        f1_ = R.font(R.MONT, 20, 700); f2_ = R.font(R.MONT, 23, 800); na_ = f1_.getbbox("Ag")[3]
        FT[5] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 3, 6)
        f1_ = R.font(R.MONT, TIERS_OVR[1][1] - 1 if TIERS_OVR else 31, 700); f2_ = R.font(R.MONT, TIERS_OVR[1][2] if TIERS_OVR else 35, 800); na_ = f1_.getbbox("Ag")[3]
        FT[6] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 4, 9)
        f1_ = R.font(R.MONT, TP.TINY_PX[0], 700); f2_ = R.font(R.MONT, TP.TINY_PX[1], 800); na_ = f1_.getbbox("Ag")[3]
        FT[7] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 3, 5)
        if REGION:
            _NM = [n_ for n_ in TOWNS if n_ in pts]
            _xy = np.array([P(*pts[n_]) for n_ in _NM] or [(-999, -999)], float); _PX, _PY = _xy[:, 0], _xy[:, 1]
        def boxes(c):
            out_ = []
            for tx, ty in c["cands"]:
                bb = (tx - BXP, ty - 1, tx + c["tw"] + BXP, ty + c["th"] + 1)
                if inside(bb): out_.append((tx, ty, bb))
            if REGION and out_:
                pr_ = RPAD_PX; me_ = (c["x"], c["y"])
                def cov(bb):
                    m_ = (_PX >= bb[0] - pr_) & (_PX <= bb[2] + pr_) & (_PY >= bb[1] - pr_) & (_PY <= bb[3] + pr_)
                    return int(m_.sum()) - int(bb[0] - pr_ <= me_[0] <= bb[2] + pr_ and bb[1] - pr_ <= me_[1] <= bb[3] + pr_)
                pin_ = out_[:1] if (c.get("name") in TP.PREF and out_[0][:2] == tuple(c["cands"][0])) else []
                out_ = pin_ + sorted(out_[len(pin_):], key=lambda q: cov(q[2]))
            for q in out_: yield q
        for name in ORDER:
            if name not in pts: skipped.append(name + " (no point)"); continue
            if name in excl and name not in OPTIONAL: skipped.append(name + " (no room)"); continue
            lo, la = pts[name]; x, y = P(lo, la)
            vlo, vla = pts[name] if name in PASSES else TP.value_point(name, pts[name])

            val = float(sample(np.array(vlo), np.array(vla)))
            if not (30 < x < W - 30 and 30 < y < H - 30): skipped.append(name + " (off map)"); continue
            mk = (x - 1, y - 1, x + 1, y + 1)
            tr = TP.tier(name, name in PASSES)[0]
            if name in TP.TINY: tr = 7
            if tr == 2 and CORR_SHRINK: tr = 6
            f1, f2, na, th, swt, rrt = FT[tr]
            small = name in WEST and not REGION
            if name in dropped: skipped.append(name + " (made room)"); continue
            if name in prer: pass
            elif name in OPTIONAL:
                pad = 12 if small else (RPAD_PX if REGION else 22)
                if not free((mk[0] - pad, mk[1] - pad, mk[2] + pad, mk[3] + pad), None): skipped.append(name); continue
                placed.append(mk); marks[name] = mk
            t2_ = "%.2f" % val; wn = d.textlength(name, font=f1); wv = d.textlength(t2_, font=f2); tw = max(wn, wv)

            g = rrt + 4
            cands = [(x - tw / 2, y - g - th), (x - tw / 2, y + g)]
            if name in FLIP: cands = cands[::-1]
            if name in TP.LOCKED: cands = [(x - tw / 2, y - g - th) if TP.LOCKED[name] == "above" else (x - tw / 2, y + g)]
            cands = [(x - tw / 2 + dx_, y - th / 2 + dy_) for dx_, dy_ in TP.nudges(name)]
            if name in TP.LEADER: cands = [(x + TP.LEADER[name][0] + a_ - tw / 2, y + TP.LEADER[name][1] + b_ - th / 2) for a_, b_ in ((0, 0), (0, -8), (0, 8), (10, 0), (10, -8), (10, 8), (20, 0), (-10, 0))]
            if name in TP.MUST_WIDE: cands += sorted([(x - tw / 2 + dx_, y - th / 2 + dy_) for dx_ in range(-140, 141, 8) for dy_ in range(-140, 141, 8)], key=lambda q: math.hypot(q[0] + tw / 2 - x, q[1] + th / 2 - y))
            if name in getattr(TP, "SMALL", ()): cands = sorted([(x - tw / 2 + dx_, y - th / 2 + dy_) for dx_ in range(-20, 161, 4) for dy_ in range(-30, 41, 3)], key=lambda q: math.hypot(q[0] + tw / 2 - x - 65, q[1] + th / 2 - y - 10))
            c = dict(x=x, y=y, tw=tw, th=th, t2=t2_, val=val, cands=cands, mk=mk, small=small, f1=f1, f2=f2, na=na, tier=tr, sw=swt, rr=rrt, name=name)
            if name in TP.LEADER: c["lead"] = True
            def near_other(bb):
                oth = [v for k, v in marks.items() if k != name and k not in OPTIONAL] + [v["mk"] for k, v in lay.items()]
                return any(bb[0] - 14 < (m[0] + m[2]) / 2 < bb[2] + 14 and bb[1] - 14 < (m[1] + m[3]) / 2 < bb[3] + 14 for m in oth)
            def rdist(bb, m):
                cx_, cy_ = (m[0] + m[2]) / 2, (m[1] + m[3]) / 2
                return math.hypot(max(bb[0] - cx_, 0, cx_ - bb[2]), max(bb[1] - cy_, 0, cy_ - bb[3]))
            def ambiguous(bb): return False
            def _ambiguous_old(bb):
                own = rdist(bb, mk)
                oth = [v for k, v in marks.items() if k != name] + [v for k, v in prer.items() if k != name] + [v["mk"] for k, v in lay.items()]
                return any(rdist(bb, m) < own + 4 for m in oth if m != mk)
            _swap = []
            if name in getattr(TP, "SMALL", ()):
                for k_, v_ in lay.items():
                    bx0, by0, bx1, by1 = v_["bb"]; ny_ = v_["ty"] + v_["na"] + 4
                    wv_ = d.textlength(v_["t2"], font=v_["f2"]); cx_ = (bx0 + bx1) / 2
                    if v_["bb"] in placed and ny_ < by1:
                        placed.remove(v_["bb"]); t1_ = (bx0, by0, bx1, ny_); t2b = (cx_ - wv_ / 2 - 6, ny_, cx_ + wv_ / 2 + 6, by1)
                        placed.extend([t1_, t2b]); _swap.append((v_["bb"], t1_, t2b))
            got = next(((tx, ty, bb) for tx, ty, bb in boxes(c) if free(bb, mk) and not (small and near_other(bb)) and not ambiguous(bb)), None)
            for o_, t1_, t2b in _swap: placed.remove(t1_); placed.remove(t2b); placed.append(o_)
            if not got and name not in OPTIONAL:
                got = next(((tx, ty, bb) for tx, ty, bb in boxes(c) if free(bb, mk) and not (small and near_other(bb))), None)
            if not got and name not in OPTIONAL:
                labs = {v["bb"]: k for k, v in lay.items()}
                for tx, ty, bb in boxes(c):
                    hs = hits_of(bb, mk)
                    if len(hs) != 1 or hs[0] not in labs: continue
                    other = labs[hs[0]]; oc = lay[other]; placed.remove(hs[0]); placed.append(bb)
                    alt = next(((tx2, ty2, bb2) for tx2, ty2, bb2 in boxes(oc) if free(bb2, oc["mk"])), None)
                    placed.remove(bb)
                    if alt:
                        oc.update(tx=alt[0], ty=alt[1], bb=alt[2]); placed.append(alt[2]); got = (tx, ty, bb); break
                    if other in OPTIONAL:
                        del lay[other]; del vals[other]; placed.remove(oc["mk"]); skipped.append(other + " (made room)"); got = (tx, ty, bb); break
                    placed.append(hs[0])
            if not got and name not in OPTIONAL:
                rev = {v: k for k, v in prer.items() if k not in lay and k not in dropped}; best = None
                for tx, ty, bb in boxes(c):
                    hs = hits_of(bb, mk)
                    if hs and all(h in rev for h in hs) and (best is None or len(hs) < len(best[3])): best = (tx, ty, bb, hs)
                if best:
                    for h in best[3]: placed.remove(h); dropped.add(rev[h])
                    got = best[:3]
            if not got and not (PASS_OPT and name in PASSES) and (TP.always(name, name in PASSES) or name in PASSES or name == "Oak Harbor" or name in TP.REQUESTED):

                labs = {v["bb"]: k for k, v in lay.items() if k in OPTIONAL}; mks = {v["mk"]: k for k, v in lay.items() if k in OPTIONAL}
                if name in TP.REQUESTED:
                    _gv = [k for k in lay if k not in OPTIONAL and k not in TP.MUST and k not in TP.LOCKED and k not in TP.REQUESTED
                           and k not in PASSES and k != "Oak Harbor" and TP.pop(k) < TP.pop(name)]
                    labs.update({lay[k]["bb"]: k for k in _gv}); mks.update({lay[k]["mk"]: k for k in _gv})
                rev = {v: k for k, v in prer.items() if k not in lay and k not in dropped}

                rev.update({marks[k]: k for k in marks if k not in lay and k != name and k not in PASSES and k != "Oak Harbor"
                            and k not in TP.MUST and k not in TP.LOCKED and (k not in TP.REQUESTED or name in TP.LOCKED or name in TP.MUST) and (TP.pop(k) < TP.pop(name) or ((name in PASSES or name == "Oak Harbor") and not TP.always(k))) and marks[k] in placed
                            })
                best = None
                if 5 not in FT:
                    f1_ = R.font(R.MONT, 20, 700); f2_ = R.font(R.MONT, 23, 800); na_ = f1_.getbbox("Ag")[3]
                    FT[5] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 3, 6)
                for shrink in (0,):
                    trs = tr; f1s, f2s, nas, ths, sws, rrs = FT[trs]
                    wns = max(d.textlength(name, font=f1s), d.textlength(t2_, font=f2s))
                    near = [(x - wns / 2, y - 10 - ths), (x - wns / 2, y + 10)]
                    if name in TP.LOCKED: near = near[:1] if TP.LOCKED[name] == "above" else near[1:]
                    near = [(x - wns / 2 + dx_, y - ths / 2 + dy_) for dx_, dy_ in TP.nudges(name)]
                    if name in TP.LEADER: near = [(x + TP.LEADER[name][0] + a_ - wns / 2, y + TP.LEADER[name][1] + b_ - ths / 2) for a_, b_ in ((0, 0), (0, -8), (0, 8), (10, 0), (10, -8), (10, 8), (20, 0), (-10, 0))]
                    lead = []
                    for rad in ():
                        for k in range(24):
                            a = 2 * math.pi * k / 24; cx_, cy_ = x + rad * math.cos(a), y + rad * math.sin(a)
                            lead.append((cx_ - wns / 2, cy_ - ths / 2))
                    for li, (tx, ty) in enumerate(near + lead):
                        bb = (tx - BXP, ty - 1, tx + wns + BXP, ty + ths + 1)
                        if not inside(bb): continue
                        hs = hits_of(bb, mk)
                        if li >= len(near):
                            px_ = min(max(x, bb[0]), bb[2]); py_ = min(max(y, bb[1]), bb[3])
                            pts_ = [(x + (px_ - x) * t / 10, y + (py_ - y) * t / 10) for t in range(2, 10)]
                            if any(q != mk and not (q[0] <= x <= q[2] and q[1] <= y <= q[3]) and q[0] <= u <= q[2] and q[1] <= v <= q[3] for q in placed for u, v in pts_): continue
                        if not all(h in labs or h in mks or h in rev for h in hs): DBG.setdefault(name, set()).update(k for k, v in lay.items() if v['bb'] in hs or v['mk'] in hs); continue
                        cost = 100 * len(hs) + shrink * 25 + (0 if li < len(near) else 60 + (li - len(near)) // 24 * 20)
                        if best is None or cost < best[0]: best = (cost, tx, ty, bb, hs, trs, wns, ths, li >= len(near))
                    if best and best[0] < 40: break
                if best:
                    _, tx, ty, bb, hs, trs, wns, ths, isl = best
                    for h in hs:
                        if h in rev and rev[h] in TP.REQUESTED and name in TP.LOCKED: continue
                        if h in rev: placed.remove(h); dropped.add(rev[h]); continue
                        o = labs.get(h) or mks.get(h)
                        if o in lay:
                            oc = lay.pop(o); vals.pop(o, None); skipped.append(o + " (made room)")
                            for q in (oc["bb"], oc["mk"]):
                                if q in placed: placed.remove(q)
                    f1s, f2s, nas, ths_, sws, rrs = FT[trs]
                    c.update(tw=wns, th=ths, f1=f1s, f2=f2s, na=nas, sw=sws, lead=isl or name in TP.LEADER)
                    got = (tx, ty, bb)
            if not got:
                skipped.append(name)
                if name in OPTIONAL: placed.remove(mk)
                continue
            c.update(tx=got[0], ty=got[1], bb=got[2]); placed.append(got[2]); lay[name] = c; vals[name] = round(val, 2)
        return lay, vals, skipped, prer

    allbest = None
    import itertools
    FLIPS = [set(c_) for r_ in range(4) for c_ in itertools.combinations([n_ for n_ in ("Seattle", "Tacoma", "Everett", "Kennewick", "Spokane") if n_ not in TP.LOCKED], r_)]
    for FLIP_ in FLIPS:
      FLIP.clear(); FLIP.update(FLIP_)
      for CORR_SHRINK in (0, 1):
          excl = set(); best = None
          for _ in range(6):
              lay, vals, skipped, prer = place(excl)
              sc_ = len(lay) + 10 * sum(TP.tier(n)[0] <= 2 for n in lay) + 1000 * sum(TP.always(n) for n in lay) + 3000 * sum(n in TP.REQUESTED for n in lay)
              if best is None or sc_ > best[3]: best = (lay, vals, skipped, sc_)
              nx = excl | {n for n in prer if n not in lay} | {n for n in marks if n not in OPTIONAL and n not in lay and n not in PASSES and not TP.always(n)}
              if nx == excl: break
              excl = nx
          nal = 3000 * sum(n in TP.REQUESTED for n in best[0]) + 1000 * sum(TP.always(n) for n in best[0]) + 500 * ("Oak Harbor" in best[0]) + 100 * sum(n in best[0] for n in PASSES) + len(best[0])
          if allbest is None or nal > allbest[0]: allbest = (nal, best, set(FLIP_))
    lay, vals, skipped = allbest[1][:3]; FLIP.clear(); FLIP.update(allbest[2])
    if os.environ.get("REALANCHOR", "1") != "0":
        import region_maps as RM; _rp = {n: P(*REAL[n]) for n in lay}; _in = lambda bb: bb[0] >= 16 and bb[2] <= W - 16 and bb[1] >= 16 and bb[3] <= H - 12; _AL = RM.wa_allowed(R, P, W, H, wa)
        _ab = np.pad((~_AL).astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        def _in(bb, _f=_in):
            x0, y0, x1, y1 = max(0, int(math.floor(bb[0]))), max(0, int(math.floor(bb[1]))), min(W, int(math.ceil(bb[2]))), min(H, int(math.ceil(bb[3])))
            return _f(bb) and _ab[y1, x1] - _ab[y0, x1] - _ab[y1, x0] + _ab[y0, x0] == 0
        def _in_vec(B, _W=W, _H=H):
            B = np.asarray(B, float).reshape(-1, 4); r = (B[:, 0] >= 16) & (B[:, 2] <= _W - 16) & (B[:, 1] >= 16) & (B[:, 3] <= _H - 12)
            k = np.nonzero(r)[0]
            if len(k):
                Bk = B[k]; x0 = np.maximum(0, np.floor(Bk[:, 0]).astype(int)); y0 = np.maximum(0, np.floor(Bk[:, 1]).astype(int))
                x1 = np.minimum(_W, np.ceil(Bk[:, 2]).astype(int)); y1 = np.minimum(_H, np.ceil(Bk[:, 3]).astype(int))
                r[k] = (_ab[y1, x1] - _ab[y0, x1] - _ab[y1, x0] + _ab[y0, x0]) == 0
            return r
        _in.vec = _in_vec
        if os.environ.get("VEC_CHECK"):
            _sc = _in
            def _in(bb, _sc=_sc): return _sc(bb)
            def _chk(B, _sc=_sc):
                r = _in_vec(B); assert all(bool(a) == bool(_sc(tuple(b))) for a, b in zip(r, np.asarray(B, float).reshape(-1, 4))), "vec mismatch"; return r
            _in.vec = _chk
        TIGHT_L = float(os.environ.get("TIGHT_L") or (40 if REGION else 35))
        _prot = set(TP.MUST) | {"Oak Harbor", "Everett"} | set(TP.REQUESTED) | set(TP.REGION_REQUESTED.get(REGION, []) if REGION else [])
        _prot |= {n_ for n_ in lay if TP.always(n_)}
        _prot |= set(TP.TIGHT_PROTECT.get(REGION, []))
        _prio = sorted(lay, key=lambda n: -(5000 if n in PASSES else TP.pop(n)))
        _in0 = lambda bb: bb[0] >= 16 and bb[2] <= W - 16 and bb[1] >= 16 and bb[3] <= H - 12
        _in0.vec = lambda B: (B[:, 0] >= 16) & (B[:, 2] <= W - 16) & (B[:, 1] >= 16) & (B[:, 3] <= H - 12)
        RM.relax(lay, _rp, base_placed, _in0); RM.relax_push(lay, _rp, base_placed, _in0)
        _pf = lambda n: 5000 if n in PASSES else TP.pop(n)
        TIGHT_DROPPED, TIGHT_EXC = (RM.regreedy if os.environ.get("TIGHT_ALGO", "v2") == "v3" else RM.tighten)(lay, _rp, base_placed, _in, TIGHT_L, _prot, _pf, first=TP.TIGHT_FIRST)
        for n_ in TIGHT_DROPPED: vals.pop(n_, None)
        RM.relax(lay, _rp, base_placed, _in); RM.relax_push(lay, _rp, base_placed, _in, maxd=TIGHT_L)
        _d2 = RM.fix_outliers(lay, _rp, base_placed, _in, TIGHT_L, _prot, _pf)
        _d2 += RM.tighten(lay, _rp, base_placed, _in, TIGHT_L, _prot, _pf, first=TP.TIGHT_FIRST)[0]
        for n_ in _d2: vals.pop(n_, None)
        TIGHT_DROPPED += _d2
        RM.relax(lay, _rp, base_placed, _in); RM.relax_push(lay, _rp, base_placed, _in, maxd=TIGHT_L)
        for n_, c_ in lay.items(): c_["x"], c_["y"] = _rp[n_]
        TIGHT_EXC = {n_: round(math.hypot((c_["bb"][0] + c_["bb"][2]) / 2 - c_["x"], (c_["bb"][1] + c_["bb"][3]) / 2 - c_["y"])) for n_, c_ in lay.items()}
        TIGHT_EXC = {n_: v_ for n_, v_ in TIGHT_EXC.items() if v_ > TIGHT_L + 0.5}
        if os.environ.get("TDBG_TIGHT"): print("TIGHT L=%g dropped=%s exceptions=%s" % (TIGHT_L, TIGHT_DROPPED, TIGHT_EXC), file=sys.stderr)
        pass
    if os.environ.get("ADUMP"):
        json.dump({n: dict(pt=P(*REAL[n]), census=P(*pts[n]), bb=c["bb"], tx=c["tx"], ty=c["ty"], tw=c["tw"], th=c["th"], val=c["val"], t2=c["t2"], ll=REAL[n], f1=c["f1"].size, f2=c["f2"].size) for n, c in lay.items()}, open(os.environ["ADUMP"], "w"), default=float)

    _sz = sorted([(TP.pop(n), c["f1"].size, c["f2"].size, n) for n, c in lay.items() if n not in PASSES and n not in getattr(TP, "SMALL", ()) and n not in TP.TINY], key=lambda t: -t[0])
    for i_ in range(1, len(_sz)):
        if _sz[i_][1] > min(t[1] for t in _sz[:i_]) or _sz[i_][2] > min(t[2] for t in _sz[:i_]):
            raise AssertionError("label size not monotonic with population: %s" % _sz[i_][3])
    NB_KEEP = base_placed; VLEG = None
    if VSCALE:
        import region_maps as RM
        _old = [KO_TB, KO_BAR, KO_LEG]; _base = [p_ for p_ in base_placed if p_ not in _old] + [(0, 0, W, BAR_D + 4), tt_]
        NB_KEEP = _base
    NB_VALS = {}
    if NEIGHBOR_TOWNS:
        import region_maps as RM
        NB_VALS = RM.add_neighbor_labels(REGION, lay, NB_KEEP, P, W, H, d, R, TIERS_OVR or TP.TIERS, lambda lo_, la_: float(sample(np.array(lo_), np.array(la_))),
                                         lambda v_: "%.2f" % v_, BXP, GAP, [P(*v_) for v_ in pts.values()])
    arrow_info = None
    if UV is not None:
        UE, VE = UV; S2 = 3; ov2 = Image.new("L", (W * S2, H * S2), 0); da = ImageDraw.Draw(ov2)
        def samp(F, lon, lat):
            fi = (lat - y0) / dy; fj = (lon - x0) / dx; i = int(round(min(max(fi, 0), F.shape[0] - 1))); j = int(round(min(max(fj, 0), F.shape[1] - 1))); return float(F[i, j])
        wmask = np.asarray(wm.resize((W, H), Image.NEAREST)) > 127
        keep_out = [v["bb"] for v in lay.values()] + [v["mk"] for v in lay.values()] + list(base_placed) + list(marks.values())
        STEP = ARROW_STEP; n = 0; ndot = 0; arrows = []
        for r_, gy in enumerate(range(int(STEP * 0.6) + 200, H - 30, STEP)):
            for gx in range(int(STEP * (0.5 if r_ % 2 else 1.0)), W - 16, STEP):
                if not wmask[gy, gx]: continue
                lon, lat = R.px2ll(np.array([P.x0 + gx / P.k]), np.array([P.y0 + gy / P.k])); lon, lat = float(lon[0]), float(lat[0])
                ue, ve = samp(UE, lon, lat), samp(VE, lon, lat); sp = math.hypot(ue, ve)
                gst = float(sample(np.array(lon), np.array(lat)))
                if gst < ARROW_CALM or sp < 0.3:
                    bb = (gx - 4, gy - 4, gx + 4, gy + 4)
                    if any(not (bb[2] < p[0] or bb[0] > p[2] or bb[3] < p[1] or bb[1] > p[3]) for p in keep_out): continue
                    da.ellipse(((gx - 1.6) * S2, (gy - 1.6) * S2, (gx + 1.6) * S2, (gy + 1.6) * S2), fill=255); ndot += 1; continue
                e = 0.02; x2, y2 = P(lon + ue / sp * e / math.cos(math.radians(lat)), lat + ve / sp * e)
                ddx, ddy = x2 - gx, y2 - gy; dn = math.hypot(ddx, ddy); ddx, ddy = ddx / dn, ddy / dn
                ln = ARROW_MIN + (ARROW_MAX - ARROW_MIN) * min(max(gst, 0) / ARROW_FULL, 1.0)
                hx, hy = gx + ddx * ln / 2, gy + ddy * ln / 2; tx0, ty0 = gx - ddx * ln / 2, gy - ddy * ln / 2
                bb = (min(hx, tx0) - 4, min(hy, ty0) - 4, max(hx, tx0) + 4, max(hy, ty0) + 4)
                if any(not (bb[2] < p[0] or bb[0] > p[2] or bb[3] < p[1] or bb[1] > p[3]) for p in keep_out): continue
                if not (wmask[int(min(max(hy, 0), H - 1)), int(min(max(hx, 0), W - 1))] and wmask[int(min(max(ty0, 0), H - 1)), int(min(max(tx0, 0), W - 1))]): continue
                px, py = -ddy, ddx; hl = min(7.0, ln * 0.45); hw = hl * 0.55
                bx_, by_ = hx - ddx * hl * 0.8, hy - ddy * hl * 0.8
                da.line((tx0 * S2, ty0 * S2, bx_ * S2, by_ * S2), fill=255, width=int(ARROW_W * S2))
                da.polygon([(hx * S2, hy * S2), ((hx - ddx * hl + px * hw) * S2, (hy - ddy * hl + py * hw) * S2),
                            ((hx - ddx * hl - px * hw) * S2, (hy - ddy * hl - py * hw) * S2)], fill=255)
                n += 1; arrows.append((gx, gy, round(lon, 3), round(lat, 3), round(ue, 1), round(ve, 1), round(gst), round(ln, 1)))
        mk_ = ov2.resize((W, H), Image.LANCZOS)
        if ARROW_HALO:
            from PIL import ImageFilter as _IF
            halo = mk_.filter(_IF.MaxFilter(3)).point(lambda q: int(q * ARROW_HALO))
            im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 255)] * 3 + [halo]))
        im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [mk_.point(lambda q: int(q * ARROW_ALPHA))])); d = ImageDraw.Draw(im)
        arrow_info = dict(n=n, dots=ndot, step=STEP, length_px=[ARROW_MIN, ARROW_MAX], full_at_mph=ARROW_FULL, length_field="GUST:surface mph", alpha=ARROW_ALPHA)
    for name, c in lay.items():
        if not c.get("lead"): continue
        x, y = c["x"], c["y"]; bx0_, by0_, bx1_, by1_ = c["bb"]; by1_ = min(by1_, c["ty"] + c["na"] + 2)
        px_ = min(max(x, bx0_), bx1_); py_ = min(max(y, by0_), by1_)
        d.line((x, y, px_, py_), fill=INK, width=6); d.line((x, y, px_, py_), fill=(255, 255, 255), width=2)
        if name in TP.LEADER: d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 255, 255), outline=INK, width=3)
    for name, c in lay.items():
        x, y, tx, ty, tw = c["x"], c["y"], c["tx"], c["ty"], c["tw"]
        if name in PASSES:
            pass
        else:
            pass
        cx = tx + tw / 2
        sw = c["sw"]
        pass

        an = "mt"
        if not c.get("lead") and tx + tw <= x - 4: cx, an = tx + tw, "rt"
        elif not c.get("lead") and tx >= x + 4 and name not in getattr(TP, "SMALL", ()): cx, an = tx, "lt"
        _vu = TP.REGION_VAL_UNDER.get(REGION, {}).get(name) if REGION else None
        if _vu:
            d.text((tx, ty), name, font=c["f1"], fill=WHITE, stroke_width=sw, stroke_fill=INK, anchor="lt")
            d.text((tx + d.textlength(_vu, font=c["f1"]) / 2, ty + c["na"] + GAP), c["t2"], font=c["f2"], fill=val_color(c["val"]), stroke_width=sw + 1, stroke_fill=INK, anchor="mt")
            continue
        d.text((cx, ty), name, font=c["f1"], fill=WHITE, stroke_width=sw, stroke_fill=INK, anchor=an)
        d.text((cx, ty + c["na"] + GAP), c["t2"], font=c["f2"], fill=val_color(c["val"]), stroke_width=sw + 1, stroke_fill=INK, anchor=an)
    for name, c in lay.items():
        if name in TP.LEADER: d.ellipse((c["x"] - 6, c["y"] - 6, c["x"] + 6, c["y"] + 6), fill=(255, 255, 255), outline=INK, width=3)
    im = im.convert("RGB"); d = ImageDraw.Draw(im)
    lowlands = [vals[k] for k in ("Seattle", "Tacoma", "Olympia", "Vancouver", "Bellingham", "Everett", "Mount Vernon", "Aberdeen", "Port Angeles", "Longview", "Ocean Shores", "Long Beach", "Forks", "Oak Harbor") if k in vals]
    east = [vals[k] for k in ("Spokane", "Yakima", "Wenatchee", "Ellensburg", "Moses Lake", "Kennewick", "Walla Walla", "Pullman", "Omak", "Colville", "Goldendale", "Ritzville") if k in vals]
    _r = lambda g: ("%.2f in" % g[0]) if min(g) == max(g) else "%.2f to %.2f in" % (min(g), max(g))
    l1 = "West side %s, east side %s" % (_r(lowlands), _r(east)) if not REGION else None
    if REGION:
        rng = lambda ks: [vals[k] for k in ks if k in vals]
        if REGION == "west": g1, g2, n1, n2 = rng(("Seattle", "Tacoma", "Everett", "Bellevue", "Olympia", "Bellingham", "Federal Way", "Mount Vernon")), \
            rng(("Aberdeen", "Ocean Shores", "Westport", "Long Beach", "Forks", "Neah Bay", "Raymond", "Ilwaco", "La Push")), "Puget Sound", "coast"
        else: g1, g2, n1, n2 = rng(("Spokane", "Spokane Valley", "Cheney", "Deer Park", "Medical Lake", "Airway Heights", "Liberty Lake")), \
            rng(("Moses Lake", "Ephrata", "Othello", "Quincy", "Kennewick", "Pasco", "Richland", "Ritzville")), "Spokane area", "Columbia Basin"
        f_ = lambda g: ("%.2f in" % g[0]) if min(g) == max(g) else "%.2f to %.2f in" % (min(g), max(g))
        l1 = ", ".join("%s %s" % (n, f_(g)) for n, g in ((n1, g1), (n2, g2)) if g); l1 = l1[0].upper() + l1[1:]

    tv = {k: v for k, v in vals.items() if k not in PASSES}
    import region_maps as RM
    _fit2 = lambda t_: d.textlength(t_, font=R.font(R.MONT, SUM2_PX, 800)) <= SUM_MAXW
    l2 = extreme_line2(tv, TP.pop, "Wettest", " in", _fit2)
    def fit(txt, px):
        while px > 20 and d.textlength(txt, font=R.font(R.MONT, px, 800)) > SUM_MAXW: px -= 2
        return R.font(R.MONT, px, 800)
    for txt, px, col, yb in ((l2, SUM2_PX, TCOL, SUM_B), (l1, SUM1_PX, (255, 255, 255), SUM_B - SUM2_PX - SUM_GAP)):
        d.text((SUM_R, yb), txt, font=fit(txt, px), fill=col, stroke_width=4, stroke_fill=INK, anchor="rs")
    d.text((DATE_L, DATE_B), subtitle, font=fdate, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK, anchor="ls")
    d.text((DATE_L, MOD_B), model_line, font=fmod, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK, anchor="ls")
    if not src.startswith("Data: NOAA"): R.subtle_credit(im, d, (DATE_L, CRED_Y), src, fs)
    base = im.convert("RGBA")
    out = save_final(base, out_path, quality=97)
    imax = np.unravel_index(np.argmax(np.where(inwa, TF, -999)), TF.shape)
    return {"out": out, "size": [W, H], "wa_min": round(float(tw_.min()), 1), "wa_max": round(float(tw_.max()), 1),
            "wa_max_at": [round(float(LA[imax]), 3), round(float(LO[imax]), 3)], "wa_p99": round(float(np.percentile(tw_, 99)), 1), "towns": vals, "skipped": skipped,
            "n_labels": len(vals), "neighbor_towns": NB_VALS, "header_scale": HDR_F, "bar_y": BAR_Y, "bar_drawn": BAR_D, "top_scale": list(TS) if VSCALE else None, "arrows": arrow_info, "passes": {k: vals[k] for k in PASSES if k in vals}, "title": title, "subtitle": subtitle, "model_line": model_line, "l1": l1, "l2": l2}

def extreme_line2(tv, popf, word, unit, fits):
    v = max(tv.values()); t = sorted([k for k, x in tv.items() if x == v], key=lambda k: -popf(k)); num = "%.2f%s" % (v, unit)
    if len(t) == 1: return "%s town: %s %s" % (word, t[0], num)
    opts = ["%s towns: %s %s" % (word, ", ".join(t), num)] if len(t) <= 3 else []
    for k in range(min(3, len(t) - 1), 0, -1): opts.append("%s towns: %s +%d more %s" % (word, ", ".join(t[:k]), len(t) - k, num))
    for o in opts:
        if fits(o): return o
    return opts[-1]

PEDGES = [0.01] + [round(0.1 * k, 2) for k in range(1, 41)] + [round(4 + 0.5 * k, 2) for k in range(1, 17)] + [1e9]
_VANCH = [(0.01, (215, 245, 205)), (0.10, (180, 232, 165)), (0.30, (130, 208, 110)), (0.50, (75, 178, 78)), (0.70, (35, 138, 55)), (0.90, (15, 95, 42)),
          (1.00, (250, 240, 150)), (1.25, (250, 225, 60)), (1.50, (250, 200, 50)), (1.75, (250, 175, 45)), (2.25, (245, 135, 40)), (2.75, (235, 100, 35)),
          (3.00, (220, 50, 40)), (3.30, (190, 30, 35)), (3.60, (155, 18, 35)), (3.90, (120, 10, 40)),
          (4.00, (225, 65, 175)), (5.50, (170, 50, 195)), (7.00, (110, 40, 160)), (8.50, (150, 115, 215)), (10.0, (190, 170, 235)), (11.5, (230, 222, 250)), (12.0, (255, 255, 255))]
def _rain_col(v):
    if v <= _VANCH[0][0]: return _VANCH[0][1]
    if v >= _VANCH[-1][0]: return _VANCH[-1][1]
    for (a, ca), (b, cb) in zip(_VANCH, _VANCH[1:]):
        if a <= v <= b:
            t = (v - a) / (b - a); return tuple(int(round(ca[c] + (cb[c] - ca[c]) * t)) for c in range(3))
PCOLS = [_rain_col(e) for e in PEDGES[:-1]]
CEDGES = [round(0.5 * k, 2) for k in range(1, 25)]
def _plab(e):
    if e >= 1e8 or e < 0.5: return ""
    if e <= 4.0 + 1e-9: return ("%g" % e) if abs(e * 2 - round(e * 2)) < 1e-9 else ""
    return ("%d" % e) if abs(e - round(e)) < 1e-9 else ""
PLABS = [_plab(e) for e in PEDGES[:-1]]; PLABS[-1] = "12+"
assert len(PCOLS) == 57 and len(PLABS) == 57
FRAME_W, FRAME_CY = 0.84, 0.56
TOP_FADE, BOT_FADE = 260, 190
TITLE_PX, SUB_PX, TITLE_Y, SUB_Y = 86, 46, 6, 134
SCALE_X0, SCALE_X1, SCALE_Y, SCALE_BH = 420, 1980, 182, 18
WIN_LINE = None; WIN_PX = 36
SUM1_PX, SUM2_PX, SUM_MAXW, SUM_GAP = 44, 38, 1000, 12
NAME_PX, VAL_PX = 28, 33
SMALL_NAME_PX, SMALL_VAL_PX = 23, 27
GSUB_PX, MODEL_PX = 30, 30
ARROW_STEP, ARROW_MIN, ARROW_MAX, ARROW_FULL, ARROW_CALM, ARROW_W, ARROW_ALPHA, ARROW_HALO = 42, 8, 40, 40, 3, 2.0, 0.72, 0.28
FRAME_BOX, FRAME_BH = (-124.80, 45.54, -116.91, 49.0), 1.0
BXP = 3; RPAD_PX = 12; FILL_NEIGHBORS = False; TOP_BAR = False; PASS_OPT = False
REGION = None; REGION_SUB = None; TITLE_MAXW = None; CORNER_S = CORNER_PAD = None; TIERS_OVR = None; RSUB_PX = 44
N_CORRIDOR = 30

NEIGHBOR_DIM = 0
VSCALE = False
NEIGHBOR_TOWNS = True

def configure_region(region, neighbor_towns=False):
    ""\

    wide = region == 'west_wide'; region = 'west' if wide else region
    g = globals()
    import region_maps as RM
    RM.set_nudges(region)
    g.update(REGION=region, REGION_SUB=TP.REGION_NAME[region], W=1600, H=2400, FRAME_BOX=TP.REGION_BOX[region], FRAME_W=0.96,
             FRAME_BH=(2400 - 290 - 125) / 2400, FRAME_CY=(290 + 2400 - 125) / 2 / 2400, TOP_FADE=1, BOT_FADE=200, TITLE_PX=96, TITLE_Y=8,
             TITLE_MAXW=1600 - 2 * 300, CORNER_S=180, CORNER_PAD=24, SCALE_X0=250, SCALE_X1=1440, SCALE_Y=242, SCALE_BH=18, GSUB_PX=30,
             BXP=int(os.environ.get("RBXP", "7")), RPAD_PX=int(os.environ.get("RPAD", "12")), SUM1_PX=36, SUM2_PX=32, SUM_MAXW=980, SUM_GAP=10,
             MODEL_PX=26, TIERS_OVR=TP.REGION_TIERS, FILL_NEIGHBORS=True, TOP_BAR=True)
    if neighbor_towns:
        g.update(NEIGHBOR_TOWNS=True)
    RM.towns(g, region)
    if region == 'west' and not wide: RM.west_tight(g)

BC_W, BC_H = 1600, 1560
BC_BOX = (-126.25, 47.95, -120.50, 51.45)
BC_CROP = (47.0, 52.3, -127.5, -119.5)
BC_TOPB, BC_BOTB = 40, 40
BC_TITLE_PX = 46
BC_LATE = ("Cypress Mountain", "Mount Seymour")
BC_GSHHS = True
BC_PEAKS = []
BC_FEATURES = ()
BC_TOWNS_FIRST = False
BC_WINDOW = None
BC_LAYOUT = "top"
BC_T3 = None

MM_EDGES = [0.25, 2, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 120, 140, 160, 180, 200, 250, 300, 1e9]
MM_COLS = [_rain_col(e / 25.0) for e in MM_EDGES[:-1]]
MM_LABS = [""] + ["%g" % e for e in MM_EDGES[1:-2]] + ["300+"]
assert len(MM_COLS) == len(MM_LABS) == len(MM_EDGES) - 1
def MMFMT(v): return "%d mm" % round(max(v, 0))

BC_PASSES = [("Coquihalla Summit", -121.095, 49.594), ("Allison Pass", -120.855, 49.124), ("Duffey Lake Summit", -122.490, 50.370),
             ("Cypress Mountain", -123.204, 49.396), ("Mount Seymour", -122.948, 49.366), ("Mt Washington", -125.297, 49.746)]
BC_TOWNS = [("Vancouver", -123.1207, 49.2827, 1), ("Surrey", -122.8490, 49.1913, 2), ("Victoria", -123.3656, 48.4284, 2), ("Abbotsford", -122.3045, 49.0504, 2),
            ("Nanaimo", -123.9401, 49.1659, 2), ("Chilliwack", -121.9515, 49.1579, 2), ("Hope", -121.4420, 49.3830, 3), ("Squamish", -123.1558, 49.7016, 3),
            ("Whistler", -122.9574, 50.1163, 3), ("Pemberton", -122.8027, 50.3192, 3), ("Port Alberni", -124.8055, 49.2339, 3), ("Courtenay", -124.9936, 49.6866, 3),
            ("Campbell River", -125.2475, 50.0244, 3), ("Powell River", -124.5247, 49.8352, 3), ("Sechelt", -123.7545, 49.4741, 3), ("Duncan", -123.7079, 48.7787, 3),
            ("Tofino", -125.9066, 49.1530, 3), ("Ucluelet", -125.5466, 48.9420, 3), ("Richmond", -123.1336, 49.1666, 2), ("Coquitlam", -122.7932, 49.2838, 2),
            ("North Vancouver", -123.0724, 49.3200, 3), ("Maple Ridge", -122.6019, 49.2193, 3), ("Langley", -122.6600, 49.1044, 3), ("Mission", -122.3089, 49.1330, 3),
            ("Harrison Hot Springs", -121.7850, 49.3000, 3), ("Boston Bar", -121.4440, 49.8655, 3), ("Lillooet", -121.9364, 50.6864, 3), ("Merritt", -120.7862, 50.1113, 3),
            ("Lytton", -121.5824, 50.2316, 3), ("Yale", -121.4310, 49.5617, 3), ("Agassiz", -121.7690, 49.2380, 3), ("Gibsons", -123.5050, 49.4000, 3),
            ("Parksville", -124.3120, 49.3190, 3), ("Qualicum Beach", -124.4430, 49.3480, 3), ("Ladysmith", -123.8180, 48.9975, 3), ("Sooke", -123.7262, 48.3740, 3),
            ("Lake Cowichan", -124.0540, 48.8250, 3), ("Port Renfrew", -124.4210, 48.5550, 3), ("Bamfield", -125.1360, 48.8330, 3), ("Gold River", -126.0510, 49.7770, 3),
            ("Princeton", -120.5062, 49.4590, 3), ("Manning Park", -120.7850, 49.0650, 3), ("Gold Bridge", -122.8380, 50.8530, 3), ("Sayward", -125.9600, 50.3830, 3)]
BC_US = [("Bellingham", -122.4787, 48.7519), ("Port Angeles", -123.4307, 48.1181), ("Mount Vernon", -122.3341, 48.4212), ("Neah Bay", -124.6250, 48.3680),
         ("Forks", -124.3855, 47.9504), ("Sequim", -123.1018, 48.0795), ("Anacortes", -122.6127, 48.5126), ("Lynden", -122.4521, 48.9465), ("Concrete", -121.7515, 48.5390)]
METRO = ("Vancouver", "Surrey", "Richmond", "Coquitlam", "North Vancouver", "Maple Ridge", "Langley")
FVALLEY = ("Abbotsford", "Chilliwack", "Mission", "Agassiz", "Harrison Hot Springs", "Hope")

LM = dict(BC_W=2400, BC_H=1200, BC_BOX=(-123.40, 48.89, -121.30, 49.53), BC_CROP=(48.0, 50.6, -124.6, -120.2), BC_TOPB=0, BC_BOTB=0, BC_LAYOUT="bottom",
    BC_PASSES=[("Cypress Mountain", -123.204, 49.396), ("Grouse Mountain", -123.081, 49.380), ("Mount Seymour", -122.948, 49.366),
               ("Golden Ears", -122.5074, 49.3629), ("Cheam Peak", -121.683, 49.181), ("Chilliwack Lake", -121.420, 49.080), ("Sumas Mountain", -122.1859, 49.0830)],
    BC_LATE=("Cypress Mountain", "Grouse Mountain", "Mount Seymour", "Sumas Mountain"), BC_T3=(22, 26),
    BC_TOWNS_FIRST=True, BC_FEATURES=("Buntzen Lake", "Pitt Lake", "Alouette Lake", "Stave Lake", "Harrison Lake", "Hayward Lake"),
    BC_PEAKS=[("Mount Judge Howay", -122.3218, 49.5072)],
    BC_TOWNS=[("Vancouver", -123.1207, 49.2827, 1), ("Surrey", -122.8490, 49.1913, 2), ("Burnaby", -122.9805, 49.2488, 2), ("Richmond", -123.1336, 49.1666, 2),
              ("Abbotsford", -122.3045, 49.0504, 2), ("Coquitlam", -122.7932, 49.2838, 2), ("Chilliwack", -121.9515, 49.1579, 2),
              ("North Vancouver", -123.0724, 49.3200, 2.5), ("West Vancouver", -123.1600, 49.3280, 2.5), ("New Westminster", -122.9110, 49.2057, 2.5),
              ("Delta (Ladner)", -123.0820, 49.0897, 3), ("Tsawwassen", -123.0830, 49.0170, 3), ("White Rock", -122.8026, 49.0253, 3), ("Langley", -122.6600, 49.1044, 3),
              ("Port Coquitlam", -122.7811, 49.2628, 3), ("Port Moody", -122.8317, 49.2830, 2.5), ("Pitt Meadows", -122.6890, 49.2210, 3), ("Maple Ridge", -122.6019, 49.2193, 2.5),
              ("Mission", -122.3089, 49.1330, 3), ("Aldergrove", -122.4710, 49.0580, 3), ("Sardis", -121.9590, 49.1280, 3), ("Agassiz", -121.7690, 49.2380, 3),
              ("Harrison Hot Springs", -121.7850, 49.3000, 3), ("Rosedale", -121.8020, 49.1790, 3), ("Cultus Lake", -121.9840, 49.0640, 3), ("Lions Bay", -123.2370, 49.4560, 3),
              ("Deroche", -122.0700, 49.1890, 3), ("Dewdney", -122.1960, 49.1620, 3), ("Hatzic", -122.2420, 49.1530, 3), ("Hope", -121.4420, 49.3830, 3),
              ("Fort Langley", -122.5800, 49.1680, 3), ("Cloverdale", -122.7240, 49.1050, 3), ("Steveston", -123.1830, 49.1250, 3), ("Yarrow", -122.0590, 49.0790, 3),
              ("Harrison Mills", -121.9400, 49.2400, 3), ("Popkum", -121.7500, 49.1900, 3), ("Stave Falls", -122.3600, 49.2300, 3), ("Whonnock", -122.4700, 49.1700, 3),
              ("Deep Cove", -122.9500, 49.3290, 3), ("Belcarra", -122.9250, 49.3130, 3), ("Anmore", -122.8570, 49.3140, 3), ("Walnut Grove", -122.6400, 49.1700, 3),
              ("Lake Errock", -122.0000, 49.2150, 3), ("Ruby Creek", -121.6100, 49.3500, 3),
              ("Lynn Valley", -123.0310, 49.3410, 3), ("Horseshoe Bay", -123.2740, 49.3750, 3), ("Bowen Island", -123.3350, 49.3800, 3),
              ("Buntzen Lake", -122.8650, 49.3550, 3), ("Pitt Lake", -122.5300, 49.3700, 3), ("Alouette Lake", -122.4500, 49.3300, 3),
              ("Stave Lake", -122.3000, 49.3600, 3), ("Harrison Lake", -121.8300, 49.4200, 3), ("Chehalis", -121.9200, 49.2700, 3),
              ("Hayward Lake", -122.3500, 49.2050, 3), ("Bridal Falls", -121.7400, 49.1830, 3),
              ("Hemlock Valley", -121.9193, 49.3830, 3), ("Burke Mountain", -122.7561, 49.2936, 3), ("Brunswick Beach", -123.2434, 49.4721, 3), ("Anvil Island", -123.3049, 49.5141, 3),
              ("Bear Creek", -121.7526, 49.5330, 3), ("Squeah", -121.4192, 49.4997, 3), ("Choate", -121.4192, 49.4664, 3), ("Williams Landing", -122.5193, 49.4330, 3),
              ("Silver Creek", -121.4656, 49.3604, 3), ("Floods", -121.5173, 49.3646, 3), ("Haig", -121.4500, 49.4000, 3)],
    BC_US=[],
    METRO=("Vancouver", "Burnaby", "Surrey", "Richmond", "Coquitlam", "North Vancouver", "New Westminster", "Delta (Ladner)", "Langley", "Maple Ridge", "Port Coquitlam"),
    FVALLEY=("Abbotsford", "Chilliwack", "Mission", "Agassiz", "Harrison Hot Springs", "Sardis", "Aldergrove", "Rosedale", "Hope"))

def render_bc(TF_in, LAT1, LON1, title, subtitle, out_path, model_line, src):
    TF = TF_in * 25.4
    Wd, Hd = BC_W, BC_H
    from PIL import Image, ImageDraw, ImageFilter
    import render_core as R
    from save_final import save_final
    from shapely.geometry import box as sbox
    import forecast_base as FB, region_maps as RM
    R.W, R.H = Wd, Hd
    y0, x0 = LAT1[0], LON1[0]; dy = (LAT1[-1] - y0) / (len(LAT1) - 1); dx = (LON1[-1] - x0) / (len(LON1) - 1)
    def sample(lon, lat):
        fi = (lat - y0) / dy; fj = (lon - x0) / dx
        i0 = np.clip(np.floor(fi).astype(int), 0, TF.shape[0] - 2); j0 = np.clip(np.floor(fj).astype(int), 0, TF.shape[1] - 2)
        ti = np.clip(fi - i0, 0, 1); tj = np.clip(fj - j0, 0, 1)
        return (TF[i0, j0] * (1 - ti) * (1 - tj) + TF[i0 + 1, j0] * ti * (1 - tj) + TF[i0, j0 + 1] * (1 - ti) * tj + TF[i0 + 1, j0 + 1] * ti * tj)
    TOPB, BOTB = BC_TOPB, BC_BOTB
    P = R.frame(sbox(*BC_BOX), box_w=1.0, box_h=(Hd - TOPB - BOTB) / Hd, cy=0.5)
    lo0, la0, lo1, la1 = P.bounds_ll()
    im = FB.dark_base(R, P, 1.0)
    if BC_GSHHS:

        gh = pickle.load(open(_asset("gshhs_h_bc_clip.pkl"), "rb"))
        gm = Image.new("L", (Wd, Hd), 0); dg = ImageDraw.Draw(gm); vb = sbox(lo0 - 0.2, la0 - 0.2, lo1 + 0.2, la1 + 0.2)
        for lv, fill in (("L1", 255), ("L2", 0)):
            for g in gh[lv]:
                if g.intersects(vb): R._fill(dg, P, g.intersection(vb)) if fill else [dg.polygon(R._np_ring(P, pg.exterior.coords), fill=0) for pg in R.polys(g.intersection(vb))]
        old = np.asarray(R.LAND_MASK) > 127; new = np.asarray(gm) > 127
        arr = np.array(im); arr[new & ~old] = R.LAND + (255,); arr[~new & old] = R.WATER + (255,); im = Image.fromarray(arr, "RGBA")
        R.LAND_MASK = gm
    S = 3; WS, HS = Wd * S, Hd * S
    xs = P.x0 + (np.arange(WS) + 0.5) / (P.k * S); ys = P.y0 + (np.arange(HS) + 0.5) / (P.k * S)
    lonr, _ = R.px2ll(xs, np.zeros_like(xs)); _, latr = R.px2ll(np.zeros_like(ys), ys)
    V = np.empty((HS, WS), np.float32); VALID = np.zeros((HS, WS), bool)
    for r0 in range(0, HS, 600):
        LON, LAT = lonr[None, :], latr[r0:r0 + 600, None]; V[r0:r0 + 600] = sample(LON, LAT)
        fi_ = (LAT - y0) / dy; fj_ = (LON - x0) / dx
        VALID[r0:r0 + 600] = (fi_ >= 0) & (fi_ <= TF.shape[0] - 1) & (fj_ >= 0) & (fj_ <= TF.shape[1] - 1) & np.isfinite(V[r0:r0 + 600])
    EDGES, COLS = MM_EDGES, MM_COLS
    idx = np.clip(np.searchsorted(np.array(EDGES, np.float32), V, side='right') - 1, -1, len(COLS) - 1).astype(np.int16)
    DRY = idx < 0; idx = np.maximum(idx, 0); rgb = np.array(COLS, np.uint8)[idx]
    fm = RM.fill_mask(R, Image, WS, HS, np.zeros((HS, WS), bool), VALID); del VALID
    alpha = np.where(fm & ~DRY, 255, 0).astype(np.uint8)
    idx = np.where(DRY, -1, idx); e = (idx[:, 1:] != idx[:, :-1]); ev = (idx[1:, :] != idx[:-1, :]); del DRY
    edge = np.zeros(idx.shape, bool); edge[:, 1:] |= e; edge[1:, :] |= ev
    from scipy.ndimage import binary_dilation
    edge = binary_dilation(edge, iterations=1) & fm
    rgba = np.dstack([rgb, alpha]); rgba[edge] = (rgba[edge].astype(int) * [0.55, 0.55, 0.55, 1]).astype(np.uint8)
    ov = Image.fromarray(rgba, "RGBA").resize((Wd, Hd), Image.LANCZOS)
    _a = ov.getchannel("A"); ov = ov.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2)).convert("RGBA"); ov.putalpha(_a)
    im.alpha_composite(ov); del rgba, V, idx, edge
    R.draw_borders_on_top(im, P, 1.0, Image.new("L", (Wd, Hd), 120))
    if BC_LAYOUT == "bottom":
        INK, WHITE = (14, 16, 22), (255, 255, 255)
        yb49 = int(round(P(-122.5, 49.0)[1]))
        by0 = Hd - 92; bh = 18; bx0, bx1 = 60, Wd - 60
        f0 = yb49 + 3
        al = np.zeros(Hd, np.uint8)
        for y in range(f0, Hd): al[y] = int(round(150 * min(1.0, (y - f0) / 40.0)))
        fade = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0)); fade.putalpha(Image.fromarray(np.repeat(al[:, None], Wd, 1), "L")); im.alpha_composite(fade)
        d = ImageDraw.Draw(im)
        TT = title + " (mm)"; tpx = 30
        while d.textlength(TT, font=R.font(R.MONT, tpx + 1, 800)) <= 0.49 * Wd: tpx += 1
        fTi = R.font(R.MONT, tpx, 800); tb = d.textbbox((Wd / 2, yb49 + 8), TT, font=fTi, anchor="mt")
        TX = Wd - 28; TYt = yb49 + 8 - (tb[1] - (yb49 + 8)) + 12
        BIG_BOX = d.textbbox((TX, TYt), TT, font=fTi, anchor="rt", stroke_width=5)
        base_y = TYt + fTi.getmetrics()[0]
        dpx = int(tpx * 0.78); fDt = R.font(R.MONT, dpx, 700)
        if BC_WINDOW:
            hr_ = lambda t: "%d %s" % ((t.hour % 12) or 12, "AM" if t.hour < 12 else "PM")
            dd_ = lambda t: "%s %s %d, %s" % (t.strftime("%a"), t.strftime("%b"), t.day, hr_(t))
            DT = "%s to %s" % (dd_(BC_WINDOW[0]), dd_(BC_WINDOW[1]))
            while dpx > 20 and d.textlength(DT, font=R.font(R.MONT, dpx, 700)) > BIG_BOX[0] - 60 - 40: dpx -= 1
            fDt = R.font(R.MONT, dpx, 700)
            d.text((BIG_BOX[0] - 60, base_y), DT, font=fDt, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="rs")

        d.text((TX, base_y), TT, font=fDt, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="rs")
        TITLE_BOX = d.textbbox((TX, base_y), TT, font=fDt, anchor="rs", stroke_width=4)
        fT = R.font(R.MONT, 24, 800); d.text((bx0, by0 - 32), "mm", font=fT, fill=WHITE, stroke_width=4, stroke_fill=INK)
        d.rectangle((bx0 - 2, by0 - 2, bx1 + 2, by0 + bh + 2), fill=INK)
        txs = lambda t: bx0 + (bx1 - bx0) * t / len(COLS)
        for i_, c in enumerate(COLS): d.rectangle((round(txs(i_)), by0, round(txs(i_ + 1)), by0 + bh), fill=c)
        ft = R.font(R.MONT, 20, 700); last = -1e9
        for t, lab in enumerate(MM_LABS):
            if not lab: continue
            xx = round(txs(t)); lw = d.textlength(lab, font=ft)
            if xx - lw / 2 < last + 6 or xx + lw / 2 > Wd - 8: continue
            d.line((xx, by0 + bh, xx, by0 + bh + 5), fill=WHITE, width=2)
            d.text((xx - lw / 2, by0 + bh + 6), lab, font=ft, fill=WHITE, stroke_width=3, stroke_fill=INK); last = xx + lw / 2
        placed = [(0, yb49 + 4, Wd, Hd)]
        SUM1, SUM2, SUMW = 20, 20, 1100; SUM_R, SUM_B = Wd - 30, Hd - 12
        fdate = R.font(R.MONT, 19, 700); fmod = fdate; fs = R.font(R.MONT, 18, 600)
        DATE_L, DATE_B = 30, Hd - 12; MOD_B = None
        subtitle = "%s  |  %s  |  %s" % (model_line, subtitle, src); model_line = ""; src = ""; CRED_Y = None
        date_w = d.textlength(subtitle, font=fdate)
        sumw = min(SUMW, SUM_R - (DATE_L + date_w) - 40)
        top_bot = 0
    else:

        b0 = Hd - 200; al = np.zeros(Hd, np.uint8)
        for y in range(b0, Hd): al[y] = int(150 * 0.5 * (1 - math.cos(math.pi * (y - b0) / (Hd - b0))))
        fade = Image.new("RGBA", (Wd, Hd), (0, 0, 0, 0)); fade.putalpha(Image.fromarray(np.repeat(al[:, None], Wd, 1), "L")); im.alpha_composite(fade)
        d = ImageDraw.Draw(im)

        INK, WHITE = (14, 16, 22), (255, 255, 255)
        TPX, TY = BC_TITLE_PX, 8; fmt_ = R.font(R.MONT, 32, 700); MT = "[ECMWF 9 km]"; mtw = d.textlength(MT, font=fmt_)
        while d.textlength(title, font=R.font(R.IMPACT, TPX)) > Wd - 2 * (mtw + 60): TPX -= 2
        ft_t = R.font(R.IMPACT, TPX); tw = d.textlength(title, font=ft_t); tbot = TY + TPX * 1.15
        bx0, bx1, by0 = 50, Wd - 50, int(tbot) + 40; bh = 18
        top_bot = by0 + bh + 6 + 26
        RM.top_fade(im, Wd, top_bot); d = ImageDraw.Draw(im)
        tx = (Wd - tw) / 2; d.text((tx + 7, TY + 7), title, font=ft_t, fill=(0, 0, 0)); d.text((tx, TY), title, font=ft_t, fill=WHITE)
        d.text((Wd - 34, 30), MT, font=fmt_, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="ra")
        fT = R.font(R.MONT, 26, 800); d.text((bx0, by0 - 36), "mm", font=fT, fill=WHITE, stroke_width=4, stroke_fill=INK)
        d.rectangle((bx0 - 2, by0 - 2, bx1 + 2, by0 + bh + 2), fill=INK)
        txs = lambda t: bx0 + (bx1 - bx0) * t / len(COLS)
        for i_, c in enumerate(COLS): d.rectangle((round(txs(i_)), by0, round(txs(i_ + 1)), by0 + bh), fill=c)
        ft = R.font(R.MONT, 20, 700); last = -1e9
        for t, lab in enumerate(MM_LABS):
            if not lab: continue
            xx = round(txs(t)); lw = d.textlength(lab, font=ft)
            if xx - lw / 2 < last + 6 or xx + lw / 2 > Wd - 8: continue
            d.line((xx, by0 + bh, xx, by0 + bh + 5), fill=WHITE, width=2)
            d.text((xx - lw / 2, by0 + bh + 6), lab, font=ft, fill=WHITE, stroke_width=3, stroke_fill=INK); last = xx + lw / 2
        placed = [(0, 0, Wd, top_bot + 6)]

        SUM1, SUM2, SUMW = 36, 32, 900
        SUM_R, SUM_B = Wd - 30, Hd - 30
        fdate = R.font(R.MONT, SUM2, 800); fmod = R.font(R.MONT, 26, 700); fs = R.font(R.MONT, 22, 600)
        DATE_L, DATE_B = 30, Hd - 30; MOD_B = DATE_B - SUM2 - 10; CRED_Y = MOD_B - fmod.size - 34
        date_w = max(d.textlength(subtitle, font=fdate), d.textlength(model_line, font=fmod))
        placed.append((0, CRED_Y - 8, DATE_L + max(date_w, d.textlength(src, font=fs)) + 12, Hd))
        sumw = min(SUMW, SUM_R - (DATE_L + date_w) - 40)
        placed.append((SUM_R - sumw - 10, SUM_B - SUM2 - 10 - SUM1 - 14, Wd, Hd))

    def hit(bb): return any(not (bb[2] < p[0] or bb[0] > p[2] or bb[3] < p[1] or bb[1] > p[3]) for p in placed)
    def inside(bb): return bb[0] >= 14 and bb[2] <= Wd - 14 and bb[1] >= 14 and bb[3] <= Hd - 12
    T = TP.REGION_TIERS
    FONTS = {"P": (R.font(R.MONT, 26, 800), R.font(R.MONT, 31, 800), 4), 1: (R.font(R.MONT, T[0][1], 700), R.font(R.MONT, T[0][2], 800), 5),
             2: (R.font(R.MONT, T[1][1], 700), R.font(R.MONT, T[1][2], 800), 4), 3: (R.font(R.MONT, T[2][1], 700), R.font(R.MONT, T[2][2], 800), 4),
             "U": (R.font(R.MONT, T[3][1], 700), R.font(R.MONT, T[3][2], 800), 3)}
    if BC_T3: FONTS[3] = (R.font(R.MONT, BC_T3[0], 700), R.font(R.MONT, BC_T3[1], 800), 4)
    FONTS[2.5] = FONTS[3]
    lay = []; vals = {}; skipped = []
    marks = []
    for nm, lo, la in ([] if BC_TOWNS_FIRST else BC_PASSES):
        x, y = P(lo, la)
        if 20 < x < Wd - 20 and top_bot < y < Hd - 20: marks.append((x - 9, y - 9, x + 9, y + 9))
    placed += marks
    FONTS["Q"] = (R.font(R.MONT, 21, 800), R.font(R.MONT, 24, 800), 4)
    ring = [(0, 0)] + [(round(r * math.cos(a * math.pi / 8)), round(r * 0.8 * math.sin(a * math.pi / 8))) for r in (12, 22, 32, 44) for a in range(16)]
    ring_w = [(round(r * math.cos(a * math.pi / 8)), round(r * 0.8 * math.sin(a * math.pi / 8))) for r in (56, 68) for a in range(16)]
    def put(nm, lo, la, kind):
        x, y = P(lo, la)
        if not (20 < x < Wd - 20 and 20 < y < Hd - 20): skipped.append(nm + " (off map)"); return
        v = float(sample(np.array(lo), np.array(la))); t2 = MMFMT(v)
        f1, f2, sw = FONTS[kind]; na = f1.getbbox("Ag")[3]; th = na - 2 + f2.getbbox("0")[3] + 2
        tw_ = max(d.textlength(nm, font=f1), d.textlength(t2, font=f2))
        mk = None
        if kind in ("P", "Q") and BC_TOWNS_FIRST:
            mk = (x - 9, y - 9, x + 9, y + 9)
            if hit(mk): skipped.append(nm); return
            placed.append(mk)
        if kind in ("P", "Q"):
            g = 14; base_ = [(x - tw_ / 2, y - g - th), (x - tw_ / 2, y + g), (x + g, y - th / 2), (x - g - tw_, y - th / 2)]
            cands = base_ + [(cx + a_, cy + b_) for cx, cy in base_ for a_, b_ in ring[1:]]
        else: cands = [(x - tw_ / 2 + a_, y - th / 2 + b_) for a_, b_ in (ring + ring_w if kind in (1, 2, 2.5) else ring)]
        for tx_, ty_ in cands:
            bb = (tx_ - 6, ty_ - 1, tx_ + tw_ + 6, ty_ + th + 1)
            if inside(bb) and not hit(bb):
                placed.append(bb); lay.append((nm, x, y, tx_, ty_, tw_, na, t2, f1, f2, sw, kind)); vals[nm] = (round(v, 1), kind); return
        if mk: placed.remove(mk)
        skipped.append(nm)

    tw_ = lambda t: [q for q in BC_TOWNS if q[3] == t]
    if BC_TOWNS_FIRST:
        for t in (1, 2, 2.5, 3):
            for nm, lo, la, k in tw_(t):
                if nm not in BC_FEATURES: put(nm, lo, la, k)
        for nm, lo, la in [q for q in BC_PASSES if q[0] not in BC_LATE] + [q for q in BC_PASSES if q[0] in BC_LATE]: put(nm, lo, la, "P")
        for nm, lo, la, k in [q for q in BC_TOWNS if q[0] in BC_FEATURES]: put(nm, lo, la, k)
        for nm, lo, la in BC_PEAKS: put(nm, lo, la, "Q")
    else:
      for nm, lo, la, k in tw_(1): put(nm, lo, la, k)
    for nm, lo, la in ([] if BC_TOWNS_FIRST else BC_PASSES):
        if nm not in BC_LATE: put(nm, lo, la, "P")
    for nm, lo, la, k in ([] if BC_TOWNS_FIRST else tw_(2)): put(nm, lo, la, k)
    for nm, lo, la, k in ([] if BC_TOWNS_FIRST else tw_(2.5)): put(nm, lo, la, k)
    for nm, lo, la in ([] if BC_TOWNS_FIRST else BC_PASSES):
        if nm in BC_LATE: put(nm, lo, la, "P")
    for nm, lo, la, k in ([] if BC_TOWNS_FIRST else tw_(3)): put(nm, lo, la, k)
    for nm, lo, la in BC_US: put(nm, lo, la, "U")
    for nm, x, y, tx_, ty_, tw_, na, t2, f1, f2, sw, kind in lay:
        if kind in ("P", "Q"): d.polygon([(x, y - 8), (x - 8, y + 6), (x + 8, y + 6)], fill=(255, 255, 255), outline=INK, width=3)
        cx = tx_ + tw_ / 2
        d.text((cx, ty_), nm, font=f1, fill=(255, 236, 150) if kind in ("P", "Q") else ((215, 218, 225) if kind == "U" else WHITE), stroke_width=sw, stroke_fill=INK, anchor="mt")
        d.text((cx, ty_ + na - 2), t2, font=f2, fill=WHITE, stroke_width=sw + 1, stroke_fill=INK, anchor="mt")

    rg = lambda g: ("n/a" if not g else ("%d mm" % round(g[0])) if round(min(g)) == round(max(g)) else "%d to %d mm" % (round(min(g)), round(max(g))))
    mv = [vals[k][0] for k in METRO if k in vals]; fv = [vals[k][0] for k in FVALLEY if k in vals]
    l1 = "Metro Vancouver %s, Fraser Valley %s" % (rg(mv), rg(fv))
    bcv = {k: v for k, (v, kind) in vals.items() if kind != "U"}
    top = max(bcv, key=bcv.get) if bcv else None
    l2 = ("Wettest: %s %d mm" % (top, round(bcv[top]))) if top else ""
    def fit(txt, px):
        while px > 20 and d.textlength(txt, font=R.font(R.MONT, px, 800)) > sumw: px -= 2
        return R.font(R.MONT, px, 800)
    im = im.convert("RGB"); d = ImageDraw.Draw(im)
    if MOD_B is None:
        l12 = l1 + "  |  " + l2 if l2 else l1
        d.text((SUM_R, SUM_B), l12, font=fit(l12, SUM2), fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="rs")
        d.text((DATE_L, DATE_B), subtitle, font=fdate, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="ls")
    else:
      d.text((SUM_R, SUM_B), l2, font=fit(l2, SUM2), fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="rs")
      d.text((SUM_R, SUM_B - SUM2 - 10), l1, font=fit(l1, SUM1), fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="rs")
      d.text((DATE_L, DATE_B), subtitle, font=fdate, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="ls")
      d.text((DATE_L, MOD_B), model_line, font=fmod, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="ls")
    if src: R.subtle_credit(im, d, (DATE_L, CRED_Y), src, fs)
    out = save_final(im.convert("RGBA"), out_path, quality=97)
    LO, LA = np.meshgrid(LON1, LAT1); inb = (LO >= lo0) & (LO <= lo1) & (LA >= la0) & (LA <= la1) & (LA >= 49.0)
    imax = np.unravel_index(np.argmax(np.where(inb, TF, -999)), TF.shape)
    return {"out": out, "size": [Wd, Hd], "region": "bc", "bounds_ll": [lo0, la0, lo1, la1], "bc_grid_max_mm": round(float(TF[inb].max()), 1),
            "bc_grid_max_at": [round(float(LA[imax]), 2), round(float(LO[imax]), 2)], "values_mm": {k: v for k, (v, kind) in vals.items()},
            "passes": {k: v for k, (v, kind) in vals.items() if kind == "P"}, "skipped": skipped, "n_labels": len(vals), "title": title,
            "subtitle": subtitle, "model_line": model_line, "l1": l1, "l2": l2, "wa_max": None, "wa_min": None, "wa_max_at": None, "wa_p99": None}

def _hr(h): return "%d %s" % (h % 12 or 12, "AM" if h % 24 < 12 else "PM")

def _pt(txt):
    m = re.fullmatch(r"\s*(\d{4}-\d{2}-\d{2})[ T](\d{1,2})(?::00)?\s*", txt)
    if not m or not 0 <= int(m.group(2)) <= 23: raise SystemExit("bad time %r, use \"YYYY-MM-DD HH\" (PT, hour 0-23)" % txt)
    d_ = dt.date.fromisoformat(m.group(1)); return dt.datetime(d_.year, d_.month, d_.day, int(m.group(2)), tzinfo=PT)

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", help='window start "YYYY-MM-DD HH" PT (default: --end minus --hours)')
    ap.add_argument("--end", help='window end "YYYY-MM-DD HH" PT, or just an hour 0-23 together with --date (default 17)')
    ap.add_argument("--date", help="old style: PT date the window ENDS on (with --end HOUR and --hours)")
    ap.add_argument("--hours", type=int, default=24, help="window length when --start is not given (any length, e.g. 6, 12, 24, 48, 72)")
    ap.add_argument("--cycle", help="force a run YYYYMMDDHH (UTC); default = newest published run that covers the window")
    ap.add_argument("--out"); ap.add_argument("--refresh", action="store_true", help="re-download even if this run's data is cached (newest run is always checked)")
    ap.add_argument("--title", help='default "Estimated <N>HR Rain Totals" (N = actual window hours)'); ap.add_argument("--no-corner", action="store_true")
    ap.add_argument("--source", choices=["ecmwf", "nbm", "hrrr", "gfs", "eps", "eps90"], default="ecmwf", help="QPF model: ECMWF IFS 0.1 deg (default), NOAA NBM core 2.5 km (1 h APCP summed), NOAA GFS 0.25 deg, ECMWF ensemble mean (eps) or 90th percentile (eps90)")
    ap.add_argument("--region", choices=["west", "east", "west_wide", "bc", "lowermainland"], help="vertical 1600x2400 regional map (not test-rendered yet)")
    ap.add_argument("--top-scale", action="store_true", help="--region maps: old header (region/window/model lines) and horizontal scale in a tall top bar")
    ap.add_argument("--no-neighbor-towns", action="store_true", help="turn OFF the default OR/ID/BC reference town labels (and the frame/bar move north on --region; full-state fill back to off)")
    ap.add_argument("--fill-neighbors", action="store_true"); ap.add_argument("--no-fill-neighbors", action="store_true")
    a = ap.parse_args(argv)
    global NO_CORNER, FILL_NEIGHBORS, WIN_LINE, NEIGHBOR_TOWNS; NO_CORNER = a.no_corner
    NEIGHBOR_TOWNS = not a.no_neighbor_towns
    if NEIGHBOR_TOWNS: FILL_NEIGHBORS = True
    BC = a.region in ("bc", "lowermainland")
    if a.region == "lowermainland": globals().update(LM)
    if BC: NO_CORNER = True; os.environ["PM_BOX"] = ",".join(map(str, BC_CROP))
    if a.region and not BC: configure_region(a.region, NEIGHBOR_TOWNS)
    global VSCALE; VSCALE = bool(a.region) and not a.top_scale and not BC
    if a.fill_neighbors: FILL_NEIGHBORS = True
    if a.no_fill_neighbors: FILL_NEIGHBORS = False

    if a.end and not re.fullmatch(r"\d{1,2}", a.end.strip()): we_l = _pt(a.end)
    else:
        if not a.date: raise SystemExit("give --end \"YYYY-MM-DD HH\" (PT) or --date YYYY-MM-DD [--end HOUR]")
        d_ = dt.date.fromisoformat(a.date); h_ = int(a.end) if a.end else 17
        if not 0 <= h_ <= 23: raise SystemExit("--end hour must be 0-23")
        we_l = dt.datetime(d_.year, d_.month, d_.day, h_, tzinfo=PT)
    ws_l = _pt(a.start) if a.start else (we_l.astimezone(UTC) - dt.timedelta(hours=a.hours)).astimezone(PT)
    if ws_l >= we_l: raise SystemExit("REFUSED: window start must be before the end")
    if a.source == "nbm": return main_nbm(a, ws_l, we_l, BC)
    if a.source == "hrrr": return main_hrrr(a, ws_l, we_l, BC)
    if a.source in ("gfs", "eps", "eps90"): return main_extra(a, ws_l, we_l, BC)
    run, stream, s0, s1, note = pick_run(ws_l.astimezone(UTC), we_l.astimezone(UTC), a.cycle)
    ws_a = (run + dt.timedelta(hours=s0)).astimezone(PT); we_a = (run + dt.timedelta(hours=s1)).astimezone(PT); hrs = s1 - s0
    print("requested %s to %s PT; using run %s %s steps %d-%d = %s to %s PT (%d h)%s" % (ws_l.strftime("%a %m-%d %H:00"), we_l.strftime("%a %m-%d %H:00"),
          run.strftime("%Y%m%d%HZ"), stream, s0, s1, ws_a.strftime("%a %m-%d %H:00"), we_a.strftime("%a %m-%d %H:00"), hrs, ("; " + note) if note else ""))
    out = a.out or "out/precip_ecmwf_%s_%s" % (we_a.strftime("%a").lower(), we_a.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True)
    npz = os.path.join(out, "ecmwf_tp_%s_s%03d-%03d%s.npz" % (run.strftime("%Y%m%d%HZ"), s0, s1, ("_" + a.region) if BC else "")); metaf = npz.replace(".npz", "_meta.json")
    if a.refresh or not os.path.exists(npz):
        import subprocess
        subprocess.run([sys.executable, os.path.abspath(__file__), "--_fetch", run.strftime("%Y%m%d%H"), stream, str(s0), str(s1), npz, metaf], check=True)
    else: print("cached:", npz)
    z = np.load(npz); meta = json.load(open(metaf)); rl = run.astimezone(PT)
    d3 = lambda t: t.strftime("%a"); long_ = hrs > 6 * 24
    tt = lambda t: "%s %s" % (_hr(t.hour), d3(t)) + (" %d-%d" % (t.month, t.day) if long_ else "")
    WIN_LINE = "%s to %s" % (tt(ws_a), tt(we_a))
    sub = "%d hr total %s %s %d-%d to %s %s %d-%d" % (hrs, _hr(ws_a.hour), d3(ws_a), ws_a.month, ws_a.day, _hr(we_a.hour), d3(we_a), we_a.month, we_a.day)
    model_line = "ECMWF IFS 9 km, %02dZ run (%s PT %d-%d)" % (run.hour, _hr(rl.hour), rl.month, rl.day)
    title = a.title or "Estimated %dHR Rain Totals" % hrs
    if BC: globals()["BC_WINDOW"] = (ws_a, we_a)
    if BC: r = render_bc(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "final.jpg"), model_line, "Data: ECMWF (CC BY 4.0)")
    else: r = render(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "final.jpg"), model_line, "Data: ECMWF (CC BY 4.0)", sub_title="European (ECMWF) 9 km")
    r.update(meta=meta, window_line=WIN_LINE, requested_pt=[ws_l.isoformat(), we_l.isoformat()], used_pt=[ws_a.isoformat(), we_a.isoformat()], snap_note=note)
    json.dump(r, open(os.path.join(out, "run.json"), "w"), indent=1, default=str)
    print(json.dumps({k: r[k] for k in ("out", "wa_min", "wa_max", "wa_max_at", "wa_p99", "n_labels", "l1", "l2", "model_line", "title", "window_line", "subtitle")}, default=str))
    return r

def main_nbm(a, ws_l, we_l, BC):
    global WIN_LINE, MODEL_TAG_OVR
    if BC: raise SystemExit("--source nbm: NBM is CONUS-only; use it for WA regions (not bc/lowermainland)")
    cyc, h0, h1, note = pick_nbm(ws_l.astimezone(UTC), we_l.astimezone(UTC), a.cycle)
    ws_a = (cyc + dt.timedelta(hours=h0)).astimezone(PT); we_a = (cyc + dt.timedelta(hours=h1)).astimezone(PT); hrs = h1 - h0
    print("requested %s to %s PT; using NBM %s f%03d-f%03d = %s to %s PT (%d h)%s" % (ws_l.strftime("%a %m-%d %H:00"), we_l.strftime("%a %m-%d %H:00"),
          cyc.strftime("%Y%m%d%HZ"), h0, h1, ws_a.strftime("%a %m-%d %H:00"), we_a.strftime("%a %m-%d %H:00"), hrs, ("; " + note) if note else ""))
    out = a.out or "out/precip_nbm_%s_%s" % (we_a.strftime("%a").lower(), we_a.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True)
    npz = os.path.join(out, "nbm_apcp_%s_f%03d-%03d.npz" % (cyc.strftime("%Y%m%d%HZ"), h0, h1)); metaf = npz.replace(".npz", "_meta.json")
    if a.refresh or not os.path.exists(npz):
        import subprocess
        subprocess.run([sys.executable, os.path.abspath(__file__), "--_fetch_nbm", cyc.strftime("%Y%m%d%H"), str(h0), str(h1), npz, metaf], check=True)
    else: print("cached:", npz)
    z = np.load(npz); meta = json.load(open(metaf)); rl = cyc.astimezone(PT)
    d3 = lambda t: t.strftime("%a"); long_ = hrs > 6 * 24
    tt = lambda t: "%s %s" % (_hr(t.hour), d3(t)) + (" %d-%d" % (t.month, t.day) if long_ else "")
    WIN_LINE = "%s to %s" % (tt(ws_a), tt(we_a))
    sub = "%d hr total %s %s %d-%d to %s %s %d-%d" % (hrs, _hr(ws_a.hour), d3(ws_a), ws_a.month, ws_a.day, _hr(we_a.hour), d3(we_a), we_a.month, we_a.day)
    model_line = "NBM 2.5 km, %02dZ run (%s PT %d-%d)" % (cyc.hour, _hr(rl.hour), rl.month, rl.day)
    title = a.title or "Estimated %dHR Rain Totals" % hrs
    MODEL_TAG_OVR = "[NBM 2.5 km]"
    r = render(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "final.jpg"), model_line, "Data: NOAA NBM (public domain)", sub_title="National Blend of Models (NBM)")
    r.update(meta=meta, window_line=WIN_LINE, requested_pt=[ws_l.isoformat(), we_l.isoformat()], used_pt=[ws_a.isoformat(), we_a.isoformat()], snap_note=note)
    json.dump(r, open(os.path.join(out, "run.json"), "w"), indent=1, default=str)
    print(json.dumps({k: r[k] for k in ("out", "wa_min", "wa_max", "wa_max_at", "wa_p99", "n_labels", "l1", "l2", "model_line", "title", "window_line", "subtitle")}, default=str))
    return r

def _hrrr_url(cyc, f): return "%s/hrrr.%s/conus/hrrr.t%02dz.wrfsfcf%02d.grib2" % (HRRR, cyc.strftime("%Y%m%d"), cyc.hour, f)

def pick_hrrr(ws, we, cycle=None):
    now = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    cycles = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)] if cycle else [now - dt.timedelta(hours=k) for k in range(0, 13)]
    why = []
    for cyc in cycles:
        h1 = int(round((we - cyc).total_seconds() / 3600)); h0 = int(round((ws - cyc).total_seconds() / 3600)); note = []
        if h0 < 0: note.append("start is before the HRRR run time, using f00 (run start)"); h0 = 0
        mx = 48 if cyc.hour % 6 == 0 else 18
        if h1 > mx or h1 <= h0: why.append("HRRR %s: window end f%02d beyond its %d h range" % (cyc.strftime("%Y%m%d%HZ"), h1, mx)); continue
        if _ok(_hrrr_url(cyc, h1) + ".idx"): return cyc, h0, h1, "; ".join(note)
        why.append("HRRR %s f%02d not published" % (cyc.strftime("%Y%m%d%HZ"), h1))
    raise SystemExit("REFUSED: no HRRR cycle covers this window.\n  " + "\n  ".join(why[:8]))

def fetch_hrrr_apcp(cyc, h0, h1, log=print):
    def run_total(f):
        u = _hrrr_url(cyc, f); L = _get(u + ".idx").decode().splitlines()
        for i, l in enumerate(L):
            if ":APCP:surface:0-%d hour acc fcst:" % f in l or (f % 24 == 0 and ":APCP:surface:0-%d day acc fcst:" % (f // 24) in l):
                a = int(l.split(":")[1]); b = int(L[i + 1].split(":")[1]) - 1 if i + 1 < len(L) else None
                v, la, lo, info = _decode(_get(u, (a, b if b is not None else a + 50_000_000)))[0]
                return v, la, lo, l
        raise SystemExit("HRRR %s f%02d: no APCP 0-%d h run-total record" % (cyc.strftime("%Y%m%d%HZ"), f, f))
    v1, la, lo, r1 = run_total(h1); recs = [r1]
    if h0 > 0:
        v0, _, _, r0 = run_total(h0); v1 = v1 - v0; recs.append(r0)
    v1 = np.clip(v1, 0, None) / 25.4
    lat1, lon1, G = _to_regular(v1, la, lo); G = np.clip(G, 0, None)
    log("HRRR %s APCP f%02d-f%02d" % (cyc.strftime("%Y%m%d%HZ"), h0, h1))
    meta = dict(model="hrrr", run=cyc.strftime("%Y%m%d%HZ"), fhr=[h0, h1], records=recs, param="APCP:surface run-total accumulation (liquid equivalent), end minus start",
                valid_utc=[(cyc + dt.timedelta(hours=h0)).isoformat(), (cyc + dt.timedelta(hours=h1)).isoformat()],
                resolution="HRRR 3 km Lambert, regridded (linear) to 0.02 deg", source=_hrrr_url(cyc, h1), license="NOAA, public domain")
    return G, lat1, lon1, meta

def main_hrrr(a, ws_l, we_l, BC):
    global WIN_LINE, MODEL_TAG_OVR
    if BC: raise SystemExit("--source hrrr: use it for WA regions (not bc/lowermainland)")
    cyc, h0, h1, note = pick_hrrr(ws_l.astimezone(UTC), we_l.astimezone(UTC), a.cycle)
    ws_a = (cyc + dt.timedelta(hours=h0)).astimezone(PT); we_a = (cyc + dt.timedelta(hours=h1)).astimezone(PT); hrs = h1 - h0
    print("requested %s to %s PT; using HRRR %s f%02d-f%02d = %s to %s PT (%d h)%s" % (ws_l.strftime("%a %m-%d %H:00"), we_l.strftime("%a %m-%d %H:00"),
          cyc.strftime("%Y%m%d%HZ"), h0, h1, ws_a.strftime("%a %m-%d %H:00"), we_a.strftime("%a %m-%d %H:00"), hrs, ("; " + note) if note else ""))
    out = a.out or "out/precip_hrrr_%s_%s" % (we_a.strftime("%a").lower(), we_a.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True)
    npz = os.path.join(out, "hrrr_apcp_%s_f%02d-%02d.npz" % (cyc.strftime("%Y%m%d%HZ"), h0, h1)); metaf = npz.replace(".npz", "_meta.json")
    if a.refresh or not os.path.exists(npz):
        import subprocess
        subprocess.run([sys.executable, os.path.abspath(__file__), "--_fetch_hrrr", cyc.strftime("%Y%m%d%H"), str(h0), str(h1), npz, metaf], check=True)
    else: print("cached:", npz)
    z = np.load(npz); meta = json.load(open(metaf)); rl = cyc.astimezone(PT)
    d3 = lambda t: t.strftime("%a")
    tt = lambda t: "%s %s" % (_hr(t.hour), d3(t))
    WIN_LINE = "%s to %s" % (tt(ws_a), tt(we_a))
    sub = "%d hr total %s %s %d-%d to %s %s %d-%d" % (hrs, _hr(ws_a.hour), d3(ws_a), ws_a.month, ws_a.day, _hr(we_a.hour), d3(we_a), we_a.month, we_a.day)
    model_line = "HRRR 3 km, %02dZ run (%s PT %d-%d)" % (cyc.hour, _hr(rl.hour), rl.month, rl.day)
    title = a.title or "Estimated %dHR Rain Totals" % hrs
    MODEL_TAG_OVR = "[HRRR 3 km]"
    r = render(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "final.jpg"), model_line, "Data: NOAA HRRR (public domain)", sub_title="HRRR 3 km")
    r.update(meta=meta, window_line=WIN_LINE, requested_pt=[ws_l.isoformat(), we_l.isoformat()], used_pt=[ws_a.isoformat(), we_a.isoformat()], snap_note=note)
    json.dump(r, open(os.path.join(out, "run.json"), "w"), indent=1, default=str)
    print(json.dumps({k: r[k] for k in ("out", "wa_min", "wa_max", "wa_max_at", "wa_p99", "n_labels", "l1", "l2", "model_line", "title", "window_line", "subtitle")}, default=str))
    return r

def main_extra(a, ws_l, we_l, BC):
    global WIN_LINE, MODEL_TAG_OVR
    import extra_sources as XS
    L = XS.LABELS[a.source]
    cyc, h0, h1 = XS.pick(a.source, ws_l.astimezone(UTC), we_l.astimezone(UTC), a.cycle)
    ws_a = (cyc + dt.timedelta(hours=h0)).astimezone(PT); we_a = (cyc + dt.timedelta(hours=h1)).astimezone(PT); hrs = h1 - h0
    out = a.out or "out/precip_%s_%s" % (a.source, we_a.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True)
    z, meta = XS.load("rain", a.source, cyc, h0, h1, os.path.join(os.environ.get("WX_CACHE") or os.path.dirname(os.path.abspath(__file__)), "xs_cache"), refresh=a.refresh)
    rl = cyc.astimezone(PT); d3 = lambda t: t.strftime("%a"); long_ = hrs > 6 * 24
    tt = lambda t: "%s %s" % (_hr(t.hour), d3(t)) + (" %d-%d" % (t.month, t.day) if long_ else "")
    WIN_LINE = "%s to %s" % (tt(ws_a), tt(we_a))
    sub = "%d hr total %s %s %d-%d to %s %s %d-%d" % (hrs, _hr(ws_a.hour), d3(ws_a), ws_a.month, ws_a.day, _hr(we_a.hour), d3(we_a), we_a.month, we_a.day)
    model_line = "%s, %02dZ run (%s PT %d-%d)" % (L["res"], cyc.hour, _hr(rl.hour), rl.month, rl.day)
    title = a.title or ("Estimated %dHR Rain (90th Pct)" % hrs if a.source == "eps90" else "Estimated %dHR Rain Totals" % hrs)
    MODEL_TAG_OVR = L["tag"]
    if BC: globals()["BC_WINDOW"] = (ws_a, we_a)
    if BC: r = render_bc(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "final.jpg"), model_line, "" if L["src"].startswith("Data: NOAA") else L["src"])
    else: r = render(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "final.jpg"), model_line, L["src"], sub_title=L["sub"])
    r.update(meta=meta, window_line=WIN_LINE, requested_pt=[ws_l.isoformat(), we_l.isoformat()], used_pt=[ws_a.isoformat(), we_a.isoformat()])
    json.dump(r, open(os.path.join(out, "run.json"), "w"), indent=1, default=str)
    print(json.dumps({k: r[k] for k in ("out", "wa_min", "wa_max", "n_labels", "model_line", "title", "window_line", "subtitle")}, default=str))
    return r

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--_fetch_hrrr":
        cy, h0, h1, npz, metaf = sys.argv[2:7]
        G, lat1, lon1, meta = fetch_hrrr_apcp(dt.datetime.strptime(cy, "%Y%m%d%H").replace(tzinfo=UTC), int(h0), int(h1))
        np.savez_compressed(npz, g=G.astype(np.float32), lat=lat1, lon=lon1); json.dump(meta, open(metaf, "w"), indent=1, default=str)
        os._exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--_fetch_nbm":
        cy, h0, h1, npz, metaf = sys.argv[2:7]
        G, lat1, lon1, meta = fetch_nbm(dt.datetime.strptime(cy, "%Y%m%d%H").replace(tzinfo=UTC), int(h0), int(h1))
        np.savez_compressed(npz, g=G.astype(np.float32), lat=lat1, lon=lon1); json.dump(meta, open(metaf, "w"), indent=1, default=str)
        os._exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "--_fetch":
        cy, stream, s0, s1, npz, metaf = sys.argv[2:8]
        G, lat1, lon1, meta = fetch_tp(dt.datetime.strptime(cy, "%Y%m%d%H").replace(tzinfo=UTC), stream, int(s0), int(s1))
        np.savez_compressed(npz, g=G.astype(np.float32), lat=lat1, lon=lon1); json.dump(meta, open(metaf, "w"), indent=1, default=str)
        os._exit(0)
    else:
        main()
