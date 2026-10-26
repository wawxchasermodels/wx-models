#!/usr/bin/env python3
"""Maximum wind gust maps for Washington (ECMWF IFS, ECMWF ENS mean, NOAA HRRR, NOAA NBM, NOAA GFS).
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

def fetch_ecmwf(model, date, start, end, cycle=None, log=print):
    ws, we = _window(date, start, end)
    now = dt.datetime.now(UTC)
    if cycle: runs = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)]
    else:
        base = now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0)
        runs = [base - dt.timedelta(hours=6 * k) for k in range(0, 8)]
    for run in runs:
        # 10fg is the max gust over (previous output step, step]: 3 h apart to 144 h, 6 h apart after. Pick every interval that
        # overlaps the window; a single hour (start == end) takes the one interval containing it.
        grid = list(range(3, 145, 3)) + list(range(150, 361, 6)); prev = dict(zip(grid, [0] + grid[:-1]))
        t = lambda h: run + dt.timedelta(hours=h)
        if we > ws: steps = [s for s in grid if t(prev[s]) < we and t(s) > ws]
        else: steps = [s for s in grid if t(prev[s]) < ws <= t(s)]
        if not steps: continue
        d8, hh = run.strftime("%Y%m%d"), run.hour
        streams = (["oper", "scda"] if model == "ecmwf" else ["enfo"])
        for stream in streams:
            typ = "ef" if stream == "enfo" else "fc"
            urls = ["%s/%s/%02dz/ifs/0p25/%s/%s%02d0000-%dh-%s-%s" % (ECM, d8, hh, stream, d8, hh, s, stream, typ) for s in steps]
            try: idxs = [_get(u + ".index").decode().splitlines() for u in urls]
            except Exception: continue
            want = "pf" if model == "eps" else "fc"
            recs = []
            for u, lines in zip(urls, idxs):
                for l in lines:
                    j = json.loads(l)
                    if j.get("param") == "10fg" and j.get("type") == want: recs.append((u + ".grib2", j))
            nmem = 50 if model == "eps" else 1
            if len(recs) != nmem * len(steps): log("run %s %s: %d of %d 10fg records, skip" % (run, stream, len(recs), nmem * len(steps))); continue
            log("ECMWF %s run %s stream %s steps %s, %d records" % (model, run, stream, steps, len(recs)))
            with ThreadPoolExecutor(8) as ex:
                blobs = list(ex.map(lambda r: _get(r[0], (r[1]["_offset"], r[1]["_offset"] + r[1]["_length"] - 1)), recs))
            fields = []; infos = []
            for b in blobs:
                for v, la, lo, info in _decode(b): fields.append((info.get("number", 0), v)); infos.append(info)
            LA, LO = la, lo
            if model == "eps":
                by = {}
                for n, v in fields: by.setdefault(n, []).append(v)
                assert len(by) == 50 and all(len(x) == len(steps) for x in by.values())
                memmax = np.array([np.max(x, 0) for x in by.values()])
                V = memmax.mean(0); extra = dict(members=len(by), member_max_of_window_then_mean=True)
            else:
                V = np.max([v for _, v in fields], 0); extra = {}
            lat1, lon1, G = _to_regular(V * MPH, LA, LO)
            meta = dict(model=model, run=run.strftime("%Y%m%d%HZ"), stream=stream, steps=steps, param="10fg",
                        stepRanges=sorted({i["stepRange"] for i in infos}, key=lambda s: int(s.split("-")[0])), grib_name=infos[0]["name"],
                        window_utc=[ws.isoformat(), we.isoformat()], resolution="0.25 deg regular lat/lon (open data)",
                        source=urls[0].rsplit("/", 1)[0], license="CC BY 4.0, Source: ECMWF", **extra)
            return G, lat1, lon1, meta
    raise SystemExit("no ECMWF run has all 10fg steps for the window")

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
          "Chinook Pass": (-121.5156, 46.8714), "Blewett Pass": (-120.5786, 47.3348), "Sherman Pass": (-118.4636, 48.6055)}   # Washington Pass and Loup Loup Pass removed 10-25-26 (Benjamin)
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

    EDGES = list(range(0, 60, 5)) + [60, 70, 80, 200]; LOB, HIB = 0, 80
    COLS = [(70, 95, 160), (55, 125, 190), (40, 160, 205), (40, 180, 160), (60, 185, 95), (130, 200, 60),
            (200, 215, 60), (245, 220, 55), (250, 180, 45), (245, 135, 40), (230, 80, 40), (205, 35, 45),
            (200, 40, 150), (175, 60, 210), (225, 150, 245)]
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
    idx = np.clip(np.searchsorted(np.array(EDGES, np.float32), np.floor(V + 0.5), side='right') - 1, 0, len(COLS) - 1).astype(np.int16)
    rgb = np.array(COLS, np.uint8)[idx]
    wm = Image.new("L", (WS, HS), 0); dw = ImageDraw.Draw(wm)
    for pg in R.polys(wa): dw.polygon([(x * S, y * S) for x, y in P.ring(pg.exterior.coords)], fill=255)
    wam = np.asarray(wm) > 127
    fm = wam
    if FILL_NEIGHBORS:
        import region_maps as RM; fm = RM.fill_mask(R, Image, WS, HS, wam, VALID); del VALID
    alpha = np.where(fm, 255, 0).astype(np.uint8)
    e = (idx[:, 1:] != idx[:, :-1]); ev = (idx[1:, :] != idx[:-1, :])
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
        return HOT if t >= 58 else GOLD if t >= 40 else WHITE

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
    def _hdr(draw):
        sz, tb = centered(R.IMPACT, title, TITLE_PX, TITLE_Y, TCOL, off=7, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}), draw=draw)
        if REGION_SUB:
            _, tb2 = centered(R.MONT, REGION_SUB, RSUB_PX, int(tb[3]) + 2, TCOL, wg=800, off=4, draw=draw); tb = (min(tb[0], tb2[0]), tb[1], max(tb[2], tb2[2]), tb2[3])
        if sub_title:
            _, sb = centered(R.MONT, sub_title, GSUB_PX, SUB_Y if not REGION_SUB else int(tb[3]) + 4, TCOL, wg=700, off=3, draw=draw)
            tb = (min(tb[0], sb[0]), tb[1], max(tb[2], sb[2]), sb[3])
        return sz, tb
    BAR_D = None; tt_ = None
    if VSCALE:
        _, tb = _hdr(False)
        _, tt_ = centered(R.IMPACT, title, TITLE_PX, TITLE_Y, TCOL, off=7, draw=False, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}))
        import region_maps as RM
        TS = RM.top_scale_geom(W, int(tt_[3]), (CORNER_PAD or int(W * 0.015)) + (CORNER_S or int(W * 0.075)))
        BAR_D = TS[2] + SCALE_BH + 6 + 26
        RM.top_fade(im, W, BAR_D); d = ImageDraw.Draw(im)
        sz, tt_ = centered(R.IMPACT, title, TITLE_PX, TITLE_Y, TCOL, off=7, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}))
    else: sz, tb = _hdr(True)

    _lp, _ls = (CORNER_PAD or int(W * 0.015)), (CORNER_S or int(W * 0.075))
    if globals().get("WEST_TIGHT") and VSCALE: tb = tt_
    placed = [tb, (0, 0, _lp + _ls + 10, _lp + _ls + 10)]
    MODEL_TAG = "[HRRR 3 km]" if model_line.startswith("HRRR") else "[ECMWF Ensemble Mean]" if "ENS" in model_line else "[ECMWF IFS]"
    if model_line.startswith("NBM"): MODEL_TAG = "[NBM 2.5 km]"
    elif model_line.startswith("GFS"): MODEL_TAG = "[GFS 0.25\u00b0]"

    fmt_ = R.font(R.MONT, 32, 700); mtw_ = d.textlength(MODEL_TAG, font=fmt_)
    d.text((W - 34, 30), MODEL_TAG, font=fmt_, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK, anchor="ra")
    placed.append((W - 34 - mtw_ - 12, 18, W, 30 + 32 + 16))
    KO_TB = tb; KO_BAR = (0, 0, W, BAR_Y + 4) if BAR_Y else None
    if BAR_Y: placed.append(KO_BAR)
    bx0, bx1, by0, bh = SCALE_X0, SCALE_X1, SCALE_Y, SCALE_BH
    if VSCALE: bx0, bx1, by0 = TS
    _dl = d
    tx_ = lambda t: bx0 + (bx1 - bx0) * (t - LOB) / (HIB - LOB)
    fT = R.font(R.MONT, 26, 800); lt = "Gust mph"; ltw = d.textlength(lt, font=fT)
    _dl.text(((bx0, by0 - 36) if VSCALE else (bx0 - 18 - ltw, by0 + bh / 2 - 16)), lt, font=fT, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK)
    _dl.rectangle((bx0 - 2, by0 - 2, bx1 + 2, by0 + bh + 2), fill=INK)
    for (e0, e1), c in zip(zip(EDGES, EDGES[1:]), COLS): _dl.rectangle((round(tx_(e0)), by0, round(tx_(min(e1, HIB))), by0 + bh), fill=c)
    ft = R.font(R.MONT, 21, 700)
    for t in range(0, 81, 10):
        xx = round(tx_(t)); _dl.line((xx, by0 + bh, xx, by0 + bh + 5), fill=(255, 255, 255), width=2)
        lab = str(t) + ("+" if t == 80 else ""); lw = d.textlength(lab, font=ft)
        _dl.text((xx - lw / 2, by0 + bh + 6), lab, font=ft, fill=(255, 255, 255), stroke_width=3, stroke_fill=INK)
    KO_LEG = (SCALE_X0 - 24 - ltw, SCALE_Y - 8, SCALE_X1 + 30, SCALE_Y + bh + 34); placed.append(KO_LEG)
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
            t2_ = "%d" % round(val); wn = d.textlength(name, font=f1); wv = d.textlength(t2_, font=f2); tw = max(wn, wv)

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
            c.update(tx=got[0], ty=got[1], bb=got[2]); placed.append(got[2]); lay[name] = c; vals[name] = round(val)
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
        _labs = [("%d+" % e_ if e_ == 80 else str(e_)) if e_ % 10 == 0 else "" for e_ in EDGES[:-1]]
        NB_KEEP = _base
    NB_VALS = {}
    if NEIGHBOR_TOWNS:
        import region_maps as RM
        NB_VALS = RM.add_neighbor_labels(REGION, lay, NB_KEEP, P, W, H, d, R, TIERS_OVR or TP.TIERS, lambda lo_, la_: float(sample(np.array(lo_), np.array(la_))),
                                         lambda v_: "%d" % round(v_), BXP, GAP, [P(*v_) for v_ in pts.values()])
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
            d.text((tx + d.textlength(_vu, font=c["f1"]) / 2, ty + c["na"] + GAP), c["t2"], font=c["f2"], fill=val_color(round(c["val"])), stroke_width=sw + 1, stroke_fill=INK, anchor="mt")
            continue
        d.text((cx, ty), name, font=c["f1"], fill=WHITE, stroke_width=sw, stroke_fill=INK, anchor=an)
        d.text((cx, ty + c["na"] + GAP), c["t2"], font=c["f2"], fill=val_color(round(c["val"])), stroke_width=sw + 1, stroke_fill=INK, anchor=an)
    for name, c in lay.items():
        if name in TP.LEADER: d.ellipse((c["x"] - 6, c["y"] - 6, c["x"] + 6, c["y"] + 6), fill=(255, 255, 255), outline=INK, width=3)
    im = im.convert("RGB"); d = ImageDraw.Draw(im)
    lowlands = [vals[k] for k in ("Seattle", "Tacoma", "Olympia", "Vancouver", "Bellingham", "Everett", "Mount Vernon", "Aberdeen", "Port Angeles", "Longview", "Ocean Shores", "Long Beach", "Forks", "Oak Harbor") if k in vals]
    east = [vals[k] for k in ("Spokane", "Yakima", "Wenatchee", "Ellensburg", "Moses Lake", "Kennewick", "Walla Walla", "Pullman", "Omak", "Colville", "Goldendale", "Ritzville") if k in vals]
    l1 = "West side %d to %d mph, east side %d to %d mph" % (min(lowlands), max(lowlands), min(east), max(east)) if not REGION else None
    if REGION:
        rng = lambda ks: [vals[k] for k in ks if k in vals]
        if REGION == "west": g1, g2, n1, n2 = rng(("Seattle", "Tacoma", "Everett", "Bellevue", "Olympia", "Bellingham", "Federal Way", "Mount Vernon")), \
            rng(("Aberdeen", "Ocean Shores", "Westport", "Long Beach", "Forks", "Neah Bay", "Raymond", "Ilwaco", "La Push")), "Puget Sound", "coast"
        else: g1, g2, n1, n2 = rng(("Spokane", "Spokane Valley", "Cheney", "Deer Park", "Medical Lake", "Airway Heights", "Liberty Lake")), \
            rng(("Moses Lake", "Ephrata", "Othello", "Quincy", "Kennewick", "Pasco", "Richland", "Ritzville")), "Spokane area", "Columbia Basin"
        f_ = lambda g: ("%d mph" % g[0]) if min(g) == max(g) else "%d to %d mph" % (min(g), max(g))
        l1 = ", ".join("%s %s" % (n, f_(g)) for n, g in ((n1, g1), (n2, g2)) if g); l1 = l1[0].upper() + l1[1:]

    tv = {k: v for k, v in vals.items() if k not in PASSES}
    import region_maps as RM
    _fit2 = lambda t_: d.textlength(t_, font=R.font(R.MONT, SUM2_PX, 800)) <= SUM_MAXW
    l2 = RM.extreme_line(tv, TP.pop, "Windiest", False, " mph", _fit2)
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
            "n_labels": len(vals), "neighbor_towns": NB_VALS, "top_scale": list(TS) if VSCALE else None, "bar_drawn": BAR_D, "arrows": arrow_info, "passes": {k: vals[k] for k in PASSES if k in vals}, "title": title, "subtitle": subtitle, "model_line": model_line, "l1": l1, "l2": l2}

FRAME_W, FRAME_CY = 0.84, 0.56
TOP_FADE, BOT_FADE = 260, 190
TITLE_PX, SUB_PX, TITLE_Y, SUB_Y = 100, 46, 6, 134
SCALE_X0, SCALE_X1, SCALE_Y, SCALE_BH = 760, 1760, 182, 18
SUM1_PX, SUM2_PX, SUM_MAXW, SUM_GAP = 44, 38, 1000, 12
NAME_PX, VAL_PX = 28, 33
SMALL_NAME_PX, SMALL_VAL_PX = 23, 27
GSUB_PX, MODEL_PX = 34, 30
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

INFO = {"ecmwf": dict(sub="European Model (ECMWF IFS)", src="Data: ECMWF (CC BY 4.0)", res="ECMWF IFS 0.25°"),
        "hrrr": dict(sub="HRRR Model", src="Data: NOAA", res="HRRR 3 km"),
        "eps": dict(sub="European Ensemble Mean (ECMWF ENS)", src="Data: ECMWF (CC BY 4.0)", res="ECMWF ENS 50-member mean, 0.25°"),
        "nbm": dict(sub="National Blend of Models (NBM)", src="Data: NOAA NBM (public domain)", res="NBM 2.5 km"),
        "gfs": dict(sub="American Model (GFS)", src="Data: NOAA", res="GFS 0.25°")}

def _hr(h): return "%d %s" % (h % 12 or 12, "AM" if h % 24 < 12 else "PM")

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", choices=["ecmwf", "hrrr", "eps", "nbm", "gfs", "all"], default="all")
    ap.add_argument("--date", required=True); ap.add_argument("--start", type=int, default=14); ap.add_argument("--end", type=int, default=23)
    ap.add_argument("--cycle"); ap.add_argument("--out"); ap.add_argument("--refresh", action="store_true"); ap.add_argument("--title")
    ap.add_argument("--valid", type=int, help="single valid hour (local PT, 0-23 on --date) instead of a max window; hrrr only")
    ap.add_argument("--arrows", action="store_true", help="draw 10 m wind direction arrows (hrrr: --valid hour, or --start/--end window = vector-mean direction)")
    ap.add_argument("--no-corner", action="store_true", help="no-op (kept for command compatibility)")
    ap.add_argument("--region", choices=["west", "east", "west_wide"], help="vertical 1600x2400 regional map (Western / Eastern Washington) with more towns")
    ap.add_argument("--top-scale", action="store_true", help="--region maps: old header (region/model lines) and horizontal scale in a tall top bar")
    ap.add_argument("--no-neighbor-towns", action="store_true", help="turn OFF the default OR/ID/BC reference town labels (and the frame/bar move north on --region; full-state fill back to off)")
    ap.add_argument("--fill-neighbors", action="store_true", help="also draw gust colors over Oregon/Idaho/BC land (default off on the full-state map, on with --region)")
    ap.add_argument("--no-fill-neighbors", action="store_true", help="--region maps: leave neighbor land blank")
    a = ap.parse_args(argv)
    global NO_CORNER; NO_CORNER = a.no_corner
    global FILL_NEIGHBORS, NEIGHBOR_TOWNS, VSCALE
    VSCALE = bool(a.region) and not a.top_scale
    NEIGHBOR_TOWNS = not a.no_neighbor_towns
    if NEIGHBOR_TOWNS: FILL_NEIGHBORS = True
    if a.region: configure_region(a.region, NEIGHBOR_TOWNS)
    if a.fill_neighbors: FILL_NEIGHBORS = True
    if a.no_fill_neighbors: FILL_NEIGHBORS = False
    date = dt.date.fromisoformat(a.date)
    out = a.out or "out/gusts_%s_%s" % (date.strftime("%a").lower(), date.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True); res = {}
    if a.valid is not None:
        assert a.model == "hrrr", "--valid is HRRR only for now"
        vl = dt.datetime(date.year, date.month, date.day, a.valid, tzinfo=PT); vu = vl.astimezone(UTC)
        npz = os.path.join(out, "hrrr_valid%s_wa.npz" % vu.strftime("%Y%m%d%HZ")); metaf = npz.replace(".npz", "_meta.json")
        if a.refresh or a.cycle or not os.path.exists(npz):
            import subprocess
            subprocess.run([sys.executable, os.path.abspath(__file__), "--_fetchvalid", vu.isoformat(), a.cycle or "", npz, metaf], check=True)
        z = np.load(npz); meta = json.load(open(metaf))
        run = dt.datetime.strptime(meta["run"], "%Y%m%d%HZ").replace(tzinfo=UTC); rl = run.astimezone(PT)
        title = a.title or "%s %s Predicted Wind Gusts" % (date.strftime("%A"), _hr(a.valid))
        sub = "Valid %s %s %s %d-%d" % (_hr(a.valid), vl.tzname(), date.strftime("%A"), date.month, date.day)
        model_line = "%s, %02dZ run %d-%d (%s PT)" % (INFO["hrrr"]["res"], run.hour, rl.month, rl.day, _hr(rl.hour))
        r = render(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "hrrr_final.jpg"), model_line, INFO["hrrr"]["src"], sub_title=INFO["hrrr"]["sub"],
                   UV=(z["u"], z["v"]) if a.arrows else None)
        r["meta"] = meta; json.dump(r, open(os.path.join(out, "hrrr_run.json"), "w"), indent=1, default=str)
        print(json.dumps({k: r[k] for k in ("out", "wa_min", "wa_max", "wa_max_at", "wa_p99", "n_labels", "arrows", "l1", "l2", "model_line")}, default=str))
        return {"hrrr": r}
    for m in (["ecmwf", "hrrr", "eps"] if a.model == "all" else [a.model]):
        npz = os.path.join(out, "%s_gust_wa.npz" % m); metaf = os.path.join(out, "%s_meta.json" % m)
        want_uv = a.arrows and m == "hrrr"
        if a.refresh or a.cycle or not os.path.exists(npz) or (want_uv and "u" not in np.load(npz).files):
            import subprocess
            subprocess.run([sys.executable, os.path.abspath(__file__), "--_fetch", m, a.date, str(a.start), str(a.end), a.cycle or "", npz, metaf] + (["uv"] if want_uv else []), check=True)
        z = np.load(npz); meta = json.load(open(metaf))
        run = dt.datetime.strptime(meta["run"], "%Y%m%d%HZ").replace(tzinfo=UTC); rl = run.astimezone(PT)
        title = a.title or "%s Predicted Max Wind Gusts" % date.strftime("%A")
        sub = "Max gusts %s to %s %s %d-%d" % (_hr(a.start), _hr(a.end), date.strftime("%A"), date.month, date.day)
        if a.start == a.end and m in ("ecmwf", "eps") and meta.get("steps"):   # single hour: say which 3 h / 6 h max it really is
            g = list(range(3, 145, 3)) + list(range(150, 361, 6)); s0 = meta["steps"][0]
            w0 = (run + dt.timedelta(hours=([0] + g)[g.index(s0)])).astimezone(PT); w1 = (run + dt.timedelta(hours=meta["steps"][-1])).astimezone(PT)
            sub = "Max gusts %s to %s %s %d-%d" % (_hr(w0.hour), _hr(w1.hour), w1.strftime("%A"), w1.month, w1.day)
        model_line = "%s, %02dZ run %d-%d (%s PT)" % (INFO[m]["res"], run.hour, rl.month, rl.day, _hr(rl.hour))
        r = render(z["g"], z["lat"], z["lon"], title, sub, os.path.join(out, "%s_final.jpg" % m), model_line, INFO[m]["src"], sub_title=INFO[m]["sub"],
                   **({"UV": (z["u"], z["v"])} if want_uv else {}))
        r["meta"] = meta; res[m] = r
        json.dump(r, open(os.path.join(out, "%s_run.json" % m), "w"), indent=1, default=str)
        print(json.dumps({k: r[k] for k in ("out", "wa_min", "wa_max", "wa_max_at", "wa_p99", "n_labels", "l1", "l2", "model_line")}, default=str))
    return res

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--_fetchvalid":
        vs, cy, npz, metaf = sys.argv[2:6]
        G, lat1, lon1, meta, UE, VE = fetch_hrrr_valid(dt.datetime.fromisoformat(vs), cy or None)
        np.savez_compressed(npz, g=G.astype(np.float32), u=UE.astype(np.float32), v=VE.astype(np.float32), lat=lat1, lon=lon1)
        json.dump(meta, open(metaf, "w"), indent=1, default=str)
        os._exit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "--_fetch":
        m, ds, s, e, cy, npz, metaf = sys.argv[2:9]
        d_ = dt.date.fromisoformat(ds)
        uvw = len(sys.argv) > 9 and sys.argv[9] == "uv"
        if m in ("nbm", "gfs"):
            import extra_sources as XS
            ws_, we_ = _window(d_, int(s), int(e)); cyc_, h0_, h1_ = XS.pick(m, ws_, we_, cy or None)
            r_ = XS.fetch("gust", m, cyc_, h0_, h1_)
        else:
            r_ = fetch_hrrr(d_, int(s), int(e), cy or None, uv=uvw) if m == "hrrr" else fetch_ecmwf(m, d_, int(s), int(e), cy or None)
        G, lat1, lon1, meta = r_[:4]
        ex_ = dict(u=r_[4].astype(np.float32), v=r_[5].astype(np.float32)) if len(r_) > 4 else {}
        np.savez_compressed(npz, g=G.astype(np.float32), lat=lat1, lon=lon1, **ex_); json.dump(meta, open(metaf, "w"), indent=1, default=str)
        os._exit(0)
    else:
        main()
