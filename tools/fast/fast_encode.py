#!/usr/bin/env python3
"""Fast-style data for the browser-drawn viewer (any model): per step and per FIELD one 8-bit grayscale PNG on the model grid
(cropped to the views), value = lo + px/255*(hi-lo) with lo/hi per step in run.json. Static per (model, view): LUT (panel px ->
fractional grid row/col + north angle), towns slots; per view: base + towns layers; per (model, product, view): color key.
Colors, levels, titles and layout come from house_style / temp_maps / menu_maps (read-only, imported from tools/forecast).

  fast_encode.py static --model hrrr [--out D]            layers, LUTs, keys, model entry in manifest.json
  fast_encode.py steps  --model hrrr --cycle 2026102918 --steps 1-48 [--only-missing] [--out D] [--workers 4]
"""
import os, sys, json, argparse, datetime as dt, time, glob
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.environ.get("WX_FORECAST_TOOLS"), os.path.join(HERE, "..", "forecast"), "/workspace/wx-models-site/live_main/tools/forecast"):
    if p and os.path.exists(os.path.join(p, "menu_maps.py")): sys.path.insert(0, os.path.abspath(p)); break

DPI = 100; STRIDE = 8
HRRR_LCC = dict(central_longitude=-97.5, central_latitude=38.5, standard_parallels=(38.5, 38.5))
GLOBAL_VIEWS = ("puget", "wa", "wwa", "ewa", "passes", "pnwt", "pnw", "na")
MODELS = {   # grid "lcc" = HRRR 3 km, "ll" = 0.25 deg global (lat 90 -> -90, lon rolled to 0..360)
    "hrrr": dict(grid="lcc", views=("puget", "wa", "wwa", "ewa", "passes", "pnwhr"), cycles=(0, 6, 12, 18), steps=list(range(1, 49)), keep=2),
    # 06/18Z added 10-29-26 7:24 PM (Benjamin). Checked on data.ecmwf.int / NOAA 10-29 18Z: GFS 06/18Z go to 384 h like 00/12Z;
    # ECMWF 0.25 06/18Z only to 144 h (3-hourly); AIFS 06/18Z to 360 h (6-hourly) like 00/12Z.
    # RRFS (NOAA, 3 km CONUS, operational since 2026): 00/06/12/18Z hourly to 48 h then 3-hourly to 84 h (stage 3, 10-30-26)
    "rrfs": dict(grid="lcc", views=("puget", "wa", "wwa", "ewa", "passes", "pnwhr"), cycles=(0, 6, 12, 18), steps=list(range(1, 49)) + list(range(51, 85, 3)), keep=2),
    "gfs":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 6, 12, 18), steps=list(range(3, 361, 3)), keep=2),
    "ifs":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 6, 12, 18), steps=list(range(3, 145, 3)) + list(range(150, 361, 6)),
                 steps_short=list(range(3, 145, 3)), short_cycles=(6, 18), keep=2, keep_long=True),
    "aifs": dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 6, 12, 18), steps=list(range(6, 361, 6)), keep=2),
    # ECMWF ENS (EPS) 0.25 open data, 50 perturbed members (no control in the open files), 00/12Z to 360 h. Mean/spread/probability
    # computed here from the members (the open em/es file only appears once the whole run is out). 10-30-26 (Benjamin's saved order).
    "eps":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 12), steps=list(range(6, 361, 6)), keep=2, grid_from="ifs"),
}
MINFO = {"eps": dict(name="ECMWF Ensemble", site="ECMWF EPS", res="0.25\u00b0 \u00b7 50 members", credit_as="ifs")}
def minfo(m):
    import menu_maps as M
    return MINFO.get(m) or M.MODELS[m]
EPS_URL = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-ef"

class _NoSt:
    def field(self, *a, **k): raise StopIteration
class EpsReader:
    """ECMWF ENS step: downloads the 50 member messages of 2t and 500 mb gh (HTTP ranges, ~36 MB) and keeps running sums only
    (memory stays at a few full grids). f() returns the ensemble mean like menu_maps.Reader.f; extra() the spread/probability."""
    st = _NoSt()
    def __init__(self, c, s):
        import temp_maps as TM, eccodes as ec
        from concurrent.futures import ThreadPoolExecutor
        self.c, self.s, self.bytes = c, s, 0
        base = EPS_URL.format(d=f"{c:%Y%m%d}", h=c.hour, s=s)
        idx = [json.loads(l) for l in TM.get(base + ".index").decode().splitlines()]
        want = [x for x in idx if x.get("type") in ("pf", "cf") and (x["param"] == "2t" or (x["param"] == "gh" and x.get("levelist") == "500"))]
        acc = {}
        def fetch(x): return x["param"], TM.get(base + ".grib2", (x["_offset"], x["_offset"] + x["_length"] - 1))
        with ThreadPoolExecutor(8) as ex:
            for par, blob in ex.map(fetch, want):
                self.bytes += len(blob); g = ec.codes_new_from_message(blob)
                ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
                la0, lo0, d = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "iDirectionIncrementInDegrees")
                v = ec.codes_get_values(g).reshape(nj, ni).astype(np.float64); ec.codes_release(g)
                if not hasattr(self, "lat"):
                    self.lat = la0 - d * np.arange(nj); lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180; self.o = np.argsort(lon); self.lon = lon[self.o]
                v = v[:, self.o]
                a = acc.setdefault(par, dict(n=0, s=np.zeros_like(v), q=np.zeros_like(v), c=np.zeros_like(v)))
                a["n"] += 1; a["s"] += v; a["q"] += v * v
                if par == "2t": a["c"] += v <= 273.15
        if len(acc) < 2 or min(a["n"] for a in acc.values()) < 40: raise RuntimeError(f"eps f{s}: only {[(k, a['n']) for k, a in acc.items()]} members")
        self.n = acc["2t"]["n"]; self.A = acc
    def _mean(self, p): a = self.A[p]; return a["s"] / a["n"]
    def _sd(self, p): a = self.A[p]; mu = a["s"] / a["n"]; return np.sqrt(np.clip(a["q"] / a["n"] - mu * mu, 0, None))
    def f(self, name):
        if name == "t2m": return self.lat, self.lon, self._mean("2t")
        if name == "Z:500": return self.lat, self.lon, self._mean("gh")
        raise KeyError(name)
    def extra(self, name):
        if name == "t2sd": return self._sd("2t") * 1.8
        if name == "p32": return self.A["2t"]["c"] / self.n * 100.0
        if name == "z5sd": return self._sd("gh")
        raise KeyError(name)
def _ens(name):
    def g(R, m):
        if m != "eps": raise KeyError(name)
        return R.extra(name)
    return g

def steps_for(m, hour):
    """Forecast hours a cycle of model m carries (ECMWF 0.25 06/18Z stop at 144 h)."""
    MD = MODELS[m]
    return MD["steps_short"] if hour in MD.get("short_cycles", ()) else MD["steps"]
NOAA = ("hrrr", "gfs", "rrfs")

def _patch_models(M):
    """In-memory only (live tools untouched): RRFS pressure-level fields come from its prslev file."""
    if "rrfs" in M.MODELS and "prs" not in M.MODELS["rrfs"]: M.MODELS["rrfs"]["prs"] = M.MODELS["rrfs"]["url"].replace(".2dfld.", ".prslev.")

def _f(key, conv): return lambda R, m: conv(np.asarray(R.f(key)[2], float))
def _raw(key, conv):
    def g(R, m):
        if m not in NOAA: raise KeyError(key)
        return conv(np.asarray(R._idx(key, R.url)[2], float))
    return g
def _apcp(R, m):
    if m in NOAA: return np.asarray(R.acc0("APCP:surface")[2], float) / 25.4
    tp = np.asarray(R.f("tp")[2], float); return tp * 1000 / 25.4 if m == "ifs" else tp / 25.4
def _refc(R, m):
    if m not in ("hrrr", "rrfs"): raise KeyError("refc")
    k = "REFC:entire atmosphere" + (" (considered as a single layer)" if m == "rrfs" else "")
    return np.clip(np.asarray(R._idx(k, R.url)[2], float), -10, 80)
def _ltng(R, m):
    if m == "hrrr": return np.clip(np.asarray(R._idx("LTNG:entire atmosphere", R.url)[2], float), 0, None)
    if m == "rrfs": return np.clip(np.asarray(R._idx("LTNG:entire atmosphere", R.url, (f"{R.s - 1}-{R.s} hour max fcst",))[2], float), 0, None)   # hourly max
    raise KeyError("ltng")
def _asnow(R, m):
    if m not in ("hrrr", "rrfs"): raise KeyError("asnow")
    return np.asarray(R.acc0("ASNOW:surface")[2], float) / 0.0254
def _tcc(R, m):
    t = np.asarray(R.f("tcc")[2], float); return np.clip(t * 100.0 if np.nanmax(t) <= 1.01 else t, 0, 100)
def _ir(R, m):
    b = np.asarray(R.f("ir")[2], float) - 273.15; return np.clip(np.where(b > 60, np.nan, b), -100, 60)

def _ec(*params):   # ECMWF sfc param under any of its names (10fg is 10fg3 at 93-144 h, 10fg6 elsewhere on some runs)
    def g(R, m):
        if m in NOAA: raise KeyError(params[0])
        for p in params:
            try: return np.asarray(R.st.field(p)[2], float)
            except StopIteration: continue
        raise KeyError(params[0])
    return g
def _gust(R, m):
    if m == "ifs": return _ec("10fg", "10fg3", "10fg6")(R, m) * 2.23694
    return np.asarray(R.f("gust")[2], float) * 2.23694
def _mucape(R, m):   # ECMWF mucape; GFS/HRRR/RRFS most-unstable parcel = CAPE 255-0 mb above ground
    if m in NOAA: return np.asarray(R._idx("CAPE:255-0 mb above ground", R.url)[2], float)
    if m != "ifs": raise KeyError("mucape")
    return _ec("mucape")(R, m)
def _ltgp(R, m):
    """ECMWF lightning-potential PROXY (not flash density): convective precip in the last 6 h (3 h at F+3), in inches,
    kept only where MUCAPE >= 100 J/kg. ECMWF open data has no lightning field (checked 10-29-26)."""
    if m != "ifs": raise KeyError("ltgp")
    import temp_maps as TM
    cp = _ec("cp")(R, m); s0 = R.s - 6
    if s0 > 0:
        try: cp = cp - np.asarray(TM.Step(m, R.c, s0).field("cp")[2], float)
        except Exception as e: raise RuntimeError(f"cp f{s0}: {e}")
    return np.where(_ec("mucape")(R, m) >= 100, np.clip(cp, 0, None) * 1000 / 25.4, 0.0)

def _dsnod(R, m):
    """HRRR snow depth change since the run started (in): model snow depth now minus at F+0, so melt and settling count
    (Benjamin 10-26: melt-aware snow depth change for the Cascade pass view)."""
    if m not in ("hrrr", "rrfs"): raise KeyError("dsnod")
    import menu_maps as M
    a = np.asarray(R._idx("SNOD:surface", R.url)[2], float)
    R0 = M.Reader(m, R.c, 0); b = np.asarray(R0._idx("SNOD:surface", R0.url)[2], float)
    return np.clip((a - b) * 39.3701, -60, 60)

FIELDS = {   # name: (getter, units)
    "t2m":  (_f("t2m", lambda k: (k - 273.15) * 1.8 + 32), "F"),
    "gust": (_gust, "mph"),
    "mslp": (_f("msl", lambda p: p / 100.0), "mb"),
    "u10":  (_f("u10", lambda v: v * 1.94384), "kt"),
    "v10":  (_f("v10", lambda v: v * 1.94384), "kt"),
    "t850": (_f("T:850", lambda k: k - 273.15), "C"),
    "t700": (_f("T:700", lambda k: k - 273.15), "C"),
    "tcc":  (_tcc, "%"),
    "vis":  (_f("vis", lambda w: np.clip(w / 1609.34, 0, 10)), "mi"),
    "ir":   (_ir, "C"),
    "refc": (_refc, "dBZ"),
    "frz":  (_raw("HGT:0C isotherm", lambda z: np.clip(z * 3.28084, 0, 20000)), "ft"),
    "apcp": (_apcp, "in"),
    "asnow": (_asnow, "in"),
    # stage 1 (Benjamin 10-29-26 7:36 PM): instability + lightning
    "mucape": (_mucape, "J/kg"),
    "sbcape": (_raw("CAPE:surface", lambda v: v), "J/kg"),
    "ltng": (_ltng, "fl/km2/5min"),
    "ltgp": (_ltgp, "in"),
    # 10-30 (Benjamin): 500 mb wind (AIFS and every model), 250 mb jet, 500 mb heights (for the height anomaly)
    "u500": (_f("U:500", lambda v: v * 1.94384), "kt"), "v500": (_f("V:500", lambda v: v * 1.94384), "kt"), "z500": (_f("Z:500", lambda z: z), "m"),
    "u250": (_f("U:250", lambda v: v * 1.94384), "kt"), "v250": (_f("V:250", lambda v: v * 1.94384), "kt"), "z250": (_f("Z:250", lambda z: z), "m"),
    "dsnod": (_dsnod, "in"),
    # ECMWF ENS (model "eps" only)
    "t2sd": (_ens("t2sd"), "F"), "p32": (_ens("p32"), "%"), "z5sd": (_ens("z5sd"), "m"),
}
# Packing (R2 write budget): fields used together share one RGB PNG (one channel each). A field not in a pack is its own
# grayscale PNG. run.json "packs" maps field -> [file name, channel]; the viewer reads either layout.
PACKS = {"wind": ("mslp", "u10", "v10"), "aloft": ("t850", "t700", "frz"), "accum": ("apcp", "asnow", "ltgp"),
         "conv": ("mucape", "sbcape", "ltng"), "sky": ("tcc", "vis", "ir"), "w500": ("u500", "v500", "z500"), "w250": ("u250", "v250", "z250"),
         "e2t": ("t2m", "t2sd", "p32"), "e500": ("z500", "z5sd")}

def q8(a, lo, hi): return np.clip(np.rint((a - lo) / (hi - lo) * 255), 0, 255).astype(np.uint8)
def rng(a):
    lo, hi = float(np.floor(np.nanmin(a))), float(np.ceil(np.nanmax(a))); return lo, max(hi, lo + 1)

def roll_ll(v):   # 0.25 deg global: lon -180..179.75 -> 0..359.75
    return np.roll(v, -720, axis=1) if v.shape[1] == 1440 else v

def step_job(args):
    m, c_str, s, crop, out = args
    import menu_maps as M
    from PIL import Image
    c = dt.datetime.strptime(c_str, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
    i0, i1, j0, j1 = crop; t = time.time(); ranges, sizes, q = {}, {}, {}
    _patch_models(M)
    try: R = EpsReader(c, s) if m == "eps" else M.Reader(m, c, s)
    except Exception as e: return s, None, str(e), 0, 0
    for name, (get, units) in FIELDS.items():
        try: a = get(R, m)
        except (KeyError, StopIteration): continue
        except Exception as e:
            if name == "t2m" or "404" in str(e): return s, None, f"{name}: {e}", 0, time.time() - t   # step (or its prs file) not out yet: retry next pass
            print(f"{m} f{s:03d} {name}: {str(e)[:120]}", flush=True); continue
        if MODELS[m]["grid"] == "ll": a = roll_ll(a)
        a = a[i0:i1, j0:j1]
        if not np.isfinite(a).any(): continue
        if name == "ir":
            from scipy.ndimage import gaussian_filter
            bad = ~np.isfinite(a)
            if bad.any():
                w = gaussian_filter((~bad).astype(float), 1.5); a = np.where(bad, gaussian_filter(np.where(bad, 0, a), 1.5) / np.maximum(w, 1e-6), a)
        a = np.where(np.isfinite(a), a, np.nanmin(a))
        ranges[name] = rng(a); q[name] = q8(a, *ranges[name])
    packs = {}
    for pk, names in PACKS.items():
        got = [n for n in names if n in q]
        if len(got) < 2: continue
        ch = np.zeros(q[got[0]].shape + (3,), np.uint8)
        for k, n in enumerate(names):
            if n in q: ch[..., k] = q.pop(n); packs[n] = [pk, k]
        p = f"{out}/single/{pk}_f{s:03d}.png"; Image.fromarray(ch, "RGB").save(p, optimize=True); sizes[pk] = os.path.getsize(p)
    for name, a8 in q.items():
        p = f"{out}/single/{name}_f{s:03d}.png"; Image.fromarray(a8, "L").save(p, optimize=True); sizes[name] = os.path.getsize(p)
    ranges["_packs"] = packs
    return s, sizes, ranges, getattr(R, "bytes", 0), time.time() - t

# ------------------------------------------------------------------------------------------------ climatology
CLIM_NPZ = {"z500": ("ncep_hgt500_mon_ltm_1991_2020.npz", "hgt"), "t850": ("ncep_t850_mon_ltm_1991_2020.npz", "t850"),
            "t2m": ("ncep_t2m_6h_ltm_1991_2020.npz", "t2m")}
CLIM_UNITS = {"z500": "m", "t850": "C", "t2m": "F"}
def _clim_src(fn):
    return next(p for p in (os.environ.get("WX_CLIM_DIR", ""), os.path.join(HERE, "clim"), "/workspace/wx-models-site/fast_deploy/clim")
                if p and os.path.exists(os.path.join(p, fn)))
def clim_static(m, out, LA, LO, var="z500", oro_m=None):
    """1991-2020 NCEP/NCAR R1 normals of `var` on the model's cropped grid (LA, LO 2-D, any grid kind), one 16-bit-in-RGB PNG
    per slot (value = lo + (R*256+G)/65535*(hi-lo)). z500, t850: 12 monthly means (the viewer blends the two months around the
    valid time like aifs_maps.clim_at). t2m: 12 months x 4 valid hours (00/06/12/18Z) from the 6-hourly normals (PSL stamp + 6 h,
    as temp_maps.clim_t2m), moved to model terrain with 6.5 C/km like temp_maps.clim_t2m, in F; the viewer blends months and hours."""
    from PIL import Image
    from scipy.interpolate import RegularGridInterpolator
    fn, key = CLIM_NPZ[var]; z = np.load(os.path.join(_clim_src(fn), fn)); h, cl, co = z[key].astype("f4"), z["lat"], z["lon"]
    pts = np.stack([np.asarray(LA, float), np.asarray(LO, float) % 360], -1)
    wrap = co[-1] - co[0] > 350
    def it(f):
        if wrap: f = np.concatenate([f, f[:, :1]], 1); xs = np.append(co, co[0] + 360.0)
        else: xs = co
        return RegularGridInterpolator((cl[::-1], xs), f[::-1], bounds_error=False, fill_value=None)(pts)
    slots = []
    if var == "t2m":
        vt = dt.datetime(2001, 1, 1) + dt.timedelta(hours=6) + np.arange(h.shape[0]) * dt.timedelta(hours=6)   # valid times (non-leap year)
        mon = np.array([t.month for t in vt]); hr = np.array([t.hour for t in vt])
        zfix = None if oro_m is None else -0.0065 * (oro_m - it(z["zs"]))
        for k in range(12):
            for hh in (0, 6, 12, 18):
                c = it(h[(mon == k + 1) & (hr == hh)].mean(0))
                if zfix is not None: c = c + zfix
                slots.append(c * 1.8 + 32)
    else: slots = [it(h[k]) for k in range(12)]
    files, ranges = [], []
    for k, a in enumerate(slots):
        lo, hi = float(np.floor(a.min())), float(np.ceil(a.max())); hi = max(hi, lo + 1)
        q = np.clip(np.rint((a - lo) / (hi - lo) * 65535), 0, 65535).astype(np.uint32)
        rgb = np.zeros(a.shape + (3,), np.uint8); rgb[..., 0] = q >> 8; rgb[..., 1] = q & 255
        f_ = f"static/clim_{var}_{m}_{k:02d}.png"; Image.fromarray(rgb, "RGB").save(f"{out}/{f_}", optimize=True)
        files.append(f_); ranges.append([lo, hi])
    d = dict(files=files, ranges=ranges, units=CLIM_UNITS[var], source="NCEP/NCAR Reanalysis 1 1991-2020 (NOAA PSL)")
    if var == "t2m": d["hours"] = [0, 6, 12, 18]
    return d

# ------------------------------------------------------------------------------------------------ static
def extra_views(TM, ccrs):
    lcc = lambda lon: ccrs.LambertConformal(central_longitude=lon, central_latitude=47.3, standard_parallels=(45, 49))
    TM.VIEWS.setdefault("wwa", dict(label="Western Washington", size=(16, 15), proj=lcc(-122.6), ll=(-126.0, -119.2, 45.5, 49.15), box=(-127.5, -117.5, 44.5, 50.2)))
    TM.VIEWS.setdefault("ewa", dict(label="Eastern Washington", size=(16, 15), proj=lcc(-118.6), ll=(-122.0, -115.2, 45.45, 49.15), box=(-123.5, -113.5, 44.5, 50.2)))
    # Benjamin 10-29-26 7:11 PM: fast site's "Pacific NW (high-res)" frame moved ~100 mi northwest, same zoom/size
    # (live site unchanged: this only edits the in-memory copy used by the fast encoder). 100 mi = 161 km: +71 mi N, +71 mi W at 46 N.
    if not TM.VIEWS["pnwhr"].get("fast_shift"):
        dlat, dlon = 113.8 / 111.2, -113.8 / (111.2 * np.cos(np.radians(46.0)))
        V0 = TM.VIEWS["pnwhr"]; l0, l1, a0, a1 = V0["ll"]; b0, b1, c0, c1 = V0["box"]
        TM.VIEWS["pnwhr"] = dict(V0, proj=ccrs.LambertConformal(central_longitude=-120 + dlon, central_latitude=45.5 + dlat, standard_parallels=(42, 49)),
                                 ll=(l0 + dlon, l1 + dlon, a0 + dlat, a1 + dlat), box=(b0 + dlon, b1 + dlon, c0 + dlat, c1 + dlat), fast_shift=True)
    # Puget Sound close-up (Benjamin's saved order 10-29): Olympia to Everett, Olympics' east slopes to the Cascade foothills
    TM.VIEWS.setdefault("puget", dict(label="Puget Sound", size=(16, 15), proj=lcc(-122.45), ll=(-123.65, -121.25, 46.95, 48.25), box=(-124.3, -120.6, 46.5, 48.7)))
    TM.VIEWS.setdefault("passes", dict(label="Cascade Passes", size=(16, 15), proj=lcc(-121.2), ll=(-123.9, -118.5, 46.2, 49.05), box=(-125, -117.5, 45.4, 49.8)))
WA_LIKE = ("wa", "wwa", "ewa", "passes", "puget")
# Extra towns for the zoomed Western / Eastern Washington frames (Benjamin 10-29-26 7:26 PM: "more town labels").
# Appended after the site's own WA_TOWNS, so the site's placement code keeps its towns first and drops extras that collide.
EXTRA_TOWNS = {
    "puget": [("Lynnwood", 47.821, -122.315, "r"), ("Edmonds", 47.811, -122.377, "l"), ("Mukilteo", 47.945, -122.304, "l"),
              ("Marysville", 48.052, -122.177, "r"), ("Lake Stevens", 48.015, -122.064, "r"), ("Snohomish", 47.913, -122.098, "r"),
              ("Bothell", 47.762, -122.205, "r"), ("Kirkland", 47.681, -122.209, "l"), ("Redmond", 47.674, -122.121, "r"),
              ("Bellevue", 47.610, -122.201, "r"), ("Issaquah", 47.530, -122.033, "r"), ("Renton", 47.483, -122.217, "r"),
              ("Kent", 47.381, -122.235, "r"), ("Federal Way", 47.322, -122.313, "l"), ("Auburn", 47.307, -122.228, "r"),
              ("Puyallup", 47.185, -122.293, "r"), ("Lakewood", 47.172, -122.518, "l"), ("Gig Harbor", 47.329, -122.580, "l"),
              ("Port Orchard", 47.540, -122.636, "l"), ("Bremerton", 47.567, -122.633, "l"), ("Poulsbo", 47.736, -122.646, "l"),
              ("Kingston", 47.799, -122.498, "r"), ("Bainbridge Is.", 47.626, -122.521, "r"), ("Lacey", 47.034, -122.823, "r"),
              ("Yelm", 46.942, -122.606, "r"), ("Enumclaw", 47.204, -121.991, "r"), ("North Bend", 47.496, -121.787, "r"),
              ("Duvall", 47.742, -121.986, "r"), ("Monroe", 47.856, -121.971, "r"), ("Granite Falls", 48.084, -121.968, "r"),
              ("Belfair", 47.451, -122.827, "l"), ("Quilcene", 47.823, -122.876, "r"), ("Stanwood", 48.241, -122.370, "r"),
              ("Coupeville", 48.220, -122.686, "l"), ("Port Ludlow", 47.925, -122.684, "r")],
    "wwa": [("Lynden", 48.946, -122.452, "r"), ("Ferndale", 48.847, -122.591, "l"), ("Anacortes", 48.512, -122.613, "l"),
            ("Burlington", 48.476, -122.325, "r"), ("Sedro-Woolley", 48.504, -122.236, "r"), ("Concrete", 48.539, -121.749, "r"),
            ("Darrington", 48.255, -121.602, "r"), ("Coupeville", 48.220, -122.686, "l"), ("Friday Harbor", 48.534, -123.017, "l"),
            ("Sequim", 48.080, -123.102, "r"), ("Marysville", 48.052, -122.177, "r"), ("Granite Falls", 48.084, -121.968, "r"),
            ("Monroe", 47.856, -121.971, "r"), ("Skykomish", 47.709, -121.360, "r"), ("Bellevue", 47.610, -122.201, "r"),
            ("North Bend", 47.496, -121.787, "r"), ("Renton", 47.483, -122.217, "r"), ("Bremerton", 47.567, -122.633, "l"),
            ("Poulsbo", 47.736, -122.646, "l"), ("Enumclaw", 47.204, -121.991, "r"), ("Puyallup", 47.185, -122.293, "r"),
            ("Eatonville", 46.867, -122.266, "r"), ("Centralia", 46.716, -122.954, "l"), ("Morton", 46.558, -122.275, "r"),
            ("Packwood", 46.607, -121.672, "r"), ("Ocean Shores", 46.974, -124.156, "r"), ("Westport", 46.890, -124.104, "r"),
            ("Montesano", 46.981, -123.603, "r"), ("Raymond", 46.686, -123.733, "r"), ("Kelso", 46.147, -122.908, "l"),
            ("Battle Ground", 45.781, -122.533, "r"), ("Camas", 45.587, -122.400, "r"), ("Stevenson", 45.696, -121.884, "r"),
            ("Hoquiam", 46.981, -123.889, "l"), ("Quilcene", 47.823, -122.876, "r"), ("Ashford", 46.758, -122.031, "r")],
    "ewa": [("Chelan", 47.841, -120.016, "r"), ("Leavenworth", 47.596, -120.661, "l"), ("Cashmere", 47.522, -120.470, "r"),
            ("Quincy", 47.234, -119.852, "r"), ("Ephrata", 47.318, -119.553, "r"), ("Grand Coulee", 47.939, -118.997, "r"),
            ("Brewster", 48.096, -119.781, "r"), ("Tonasket", 48.705, -119.440, "r"), ("Republic", 48.648, -118.738, "r"),
            ("Kettle Falls", 48.611, -118.056, "r"), ("Newport", 48.180, -117.043, "r"), ("Deer Park", 47.954, -117.477, "r"),
            ("Davenport", 47.654, -118.150, "r"), ("Odessa", 47.333, -118.692, "r"), ("Ritzville", 47.127, -118.380, "r"),
            ("Cheney", 47.487, -117.576, "l"), ("Othello", 46.826, -119.175, "r"), ("Connell", 46.663, -118.861, "r"),
            ("Colfax", 46.880, -117.364, "r"), ("Dayton", 46.319, -117.972, "r"), ("Clarkston", 46.416, -117.045, "r"),
            ("Prosser", 46.207, -119.769, "l"), ("Sunnyside", 46.324, -120.008, "r"), ("Toppenish", 46.377, -120.308, "l"),
            ("Goldendale", 45.821, -120.822, "r"), ("Cle Elum", 47.195, -120.939, "r"), ("Coeur d'Alene", 47.678, -116.780, "r"),
            ("Sandpoint", 48.277, -116.553, "r"), ("Moscow", 46.732, -117.000, "r"), ("Hermiston", 45.840, -119.289, "r")],
}

def model_grid(m):
    """(la2d, lo2d, orog_ft or None, kind) on the model's own grid (lo2d in -180..180 for lcc, 0..360 for ll)."""
    import menu_maps as M
    if MODELS[m].get("grid_from"):   # same 0.25 grid as another model
        la, lo, oro = model_grid(MODELS[m]["grid_from"]); return la, lo, oro
    _patch_models(M)
    c = latest_published(m) or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)).replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(4):   # the newest cycle may not be posted yet: fall back one cycle at a time
        try: R = M.Reader(m, c, MODELS[m]["steps"][0]); la, lo, _ = R.f("t2m"); break
        except Exception:
            c -= dt.timedelta(hours=6)
            while c.hour not in MODELS[m]["cycles"]: c -= dt.timedelta(hours=6)
    la, lo = np.asarray(la, float), np.asarray(lo, float)
    try: oro = np.asarray(R.f("orog")[2], float) * 3.28084
    except Exception: oro = None
    if MODELS[m]["grid"] == "ll":
        lo = np.mod(roll_ll(lo[None, :])[0], 360); la, lo = np.meshgrid(la, lo, indexing="ij")
        if oro is not None: oro = roll_ll(oro)
    return la, lo, oro

def latest_published(m):
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(4, 60):
        c = now - dt.timedelta(hours=b)
        if c.hour in MODELS[m]["cycles"]: return c

def static(m, out, views_only=None):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs, cartopy.feature as cf
    from matplotlib.colors import BoundaryNorm, to_hex
    import house_style as HS, temp_maps as TM, menu_maps as M
    HS.use_for_plots(); extra_views(TM, ccrs)
    pc = ccrs.PlateCarree(); MD = MODELS[m]; vids = MD["views"]
    la, lo, oro = model_grid(m); ny_, nx_ = la.shape
    if MD["grid"] == "lcc":
        hp = ccrs.LambertConformal(globe=ccrs.Globe(ellipse="sphere", semimajor_axis=6371229, semiminor_axis=6371229), **HRRR_LCC)
        g = hp.transform_points(pc, lo, la); gx0, gy0 = g[0, 0, 0], g[0, 0, 1]; d = 3000.0
        def to_ij(LO_, LA_):
            hh = hp.transform_points(pc, LO_, LA_); return (hh[..., 1] - gy0) / d, (hh[..., 0] - gx0) / d
    else:
        def to_ij(LO_, LA_): return (90.0 - LA_) / 0.25, np.mod(LO_, 360.0) / 0.25
    views, luts = {}, {}
    for vid in vids:
        V = TM.VIEWS[vid]
        fig, ax, ky = TM.frame(vid); fig.set_dpi(DPI); ax.apply_aspect(); fig.canvas.draw()
        W, H = fig.get_size_inches() * DPI; b = ax.get_position()
        px, py, pw, ph = b.x0 * W, (1 - b.y1) * H, b.width * W, b.height * H
        x0, x1, y0, y1 = ax.get_extent(V["proj"])
        nx, ny = int(np.ceil(pw / STRIDE)) + 1, int(np.ceil(ph / STRIDE)) + 1
        gxp = np.arange(nx) * STRIDE; gyp = np.arange(ny) * STRIDE
        PX = x0 + (gxp[None, :] / pw) * (x1 - x0) + 0 * gyp[:, None]; PY = y1 - (gyp[:, None] / ph) * (y1 - y0) + 0 * gxp[None, :]
        ll = pc.transform_points(V["proj"], PX, PY); LO_, LA_ = ll[..., 0], ll[..., 1]
        fi, fj = to_ij(LO_, LA_)
        n2 = V["proj"].transform_points(pc, LO_, np.minimum(LA_ + 0.05, 89.9))
        ang = np.arctan2(-(n2[..., 1] - PY) / (y1 - y0) * ph, (n2[..., 0] - PX) / (x1 - x0) * pw)
        luts[vid] = (fi, fj, ang)
        views[vid] = dict(label=V["label"], fig=[int(round(W)), int(round(H))], size_in=[float(x) for x in fig.get_size_inches()],
                          panel=[px, py, pw, ph], stride=STRIDE, nx=nx, ny=ny, barbs_across=HS.BARBS_ACROSS.get(vid, 20))
        b_ = V["box"]; lob = np.mod(lo, 360) if MD["grid"] == "ll" else lo; bl0, bl1 = (np.mod(b_[0], 360), np.mod(b_[1], 360)) if MD["grid"] == "ll" else (b_[0], b_[1])
        inlon = ((lob >= bl0) & (lob <= bl1)) if bl0 <= bl1 else ((lob >= bl0) | (lob <= bl1))
        mm = (la >= b_[2]) & (la <= b_[3]) & inlon
        ii, jj = np.where(mm); views[vid]["cut_abs"] = [int(ii.min()), int(ii.max() + 1), int(jj.min()), int(jj.max() + 1)]
        plt.close(fig)
    allfi = np.concatenate([l[0].ravel() for l in luts.values()]); allfj = np.concatenate([l[1].ravel() for l in luts.values()])
    ok = np.isfinite(allfi) & (allfi >= 0) & (allfi <= ny_ - 1) & (allfj >= 0) & (allfj <= nx_ - 1)
    i0 = max(0, int(np.floor(allfi[ok].min())) - 3); i1 = min(ny_, int(np.ceil(allfi[ok].max())) + 4)
    j0 = max(0, int(np.floor(allfj[ok].min())) - 3); j1 = min(nx_, int(np.ceil(allfj[ok].max())) + 4)
    for v_ in views.values():
        a_ = v_["cut_abs"]; i0, i1, j0, j1 = min(i0, a_[0]), max(i1, a_[1]), min(j0, a_[2]), max(j1, a_[3])
    mp0 = f"{out}/manifest.json"
    if os.path.exists(mp0):   # keep the published crop when it is a superset (runs already in R2 stay valid)
        oc = json.load(open(mp0)).get("models", {}).get(m, {}).get("crop")
        if oc: i0, i1, j0, j1 = min(i0, oc[0]), max(i1, oc[1]), min(j0, oc[2]), max(j1, oc[3]); print("crop kept/extended from", oc, "->", [i0, i1, j0, j1], flush=True)
    os.makedirs(f"{out}/static", exist_ok=True)
    for vid, (fi, fj, ang) in luts.items():
        np.stack([fi - i0, fj - j0, ang], -1).astype("<f4").tofile(f"{out}/static/lut_{m}_{vid}.bin")
        views[vid]["lut"] = f"static/lut_{m}_{vid}.bin"
    def layer_fig(vid):
        fig, ax, ky = TM.frame(vid); fig.patch.set_alpha(0); ax.patch.set_alpha(0); return fig, ax, ky
    def save(fig, path): fig.savefig(path, dpi=DPI, transparent=True); plt.close(fig); return os.path.getsize(path)
    def town_call(ax, vid, field):
        if vid in WA_LIKE and vid != "wa":   # zoomed Washington frames: the Washington town list, only places inside the frame
            l0, l1, a0, a1 = TM.VIEWS[vid]["ll"]; ins = lambda la_, lo_: a0 + 0.05 <= la_ <= a1 - 0.05 and l0 + 0.05 <= lo_ <= l1 - 0.05
            keepT, keepP = TM.WA_TOWNS, TM.WA_PASSES
            TM.WA_TOWNS = [t for t in keepT + EXTRA_TOWNS.get(vid, []) if ins(t[1], t[2])]; TM.WA_PASSES = {k: v for k, v in keepP.items() if ins(v[1], v[2])}
            try: return TM.towns(ax, "wa", field, lambda v: None if not np.isfinite(v) else "88") or []
            finally: TM.WA_TOWNS, TM.WA_PASSES = keepT, keepP
        return TM.towns(ax, vid, field, lambda v: None if not np.isfinite(v) else "88") or []
    crop_la, crop_lo = la[i0:i1, j0:j1], lo[i0:i1, j0:j1]
    if MD["grid"] == "ll":   # towns are all in the western hemisphere: sample on the part of the crop with lon 180..360 (-180..0, monotonic)
        wcols = np.where(crop_lo[0] >= 180)[0]; tw_la, tw_lo = crop_la[:, wcols], crop_lo[:, wcols] - 360
        tw_la1, tw_lo1 = tw_la[:, 0], tw_lo[0, :]   # town_values wants 1-D axes for regular lat/lon grids (bilinear)
    else: tw_la, tw_lo = crop_la, crop_lo; tw_la1, tw_lo1 = crop_la, crop_lo
    sizes = {}
    for vid in vids:
        if not os.path.exists(f"{out}/static/base_{vid}.png") or views_only:
            fig, ax, ky = layer_fig(vid)
            HS.outlines(ax, cf, res="10m" if vid in WA_LIKE else "50m"); HS.frame(ax)
            nt = len(fig.texts); HS.header(fig, "X", "X", "X", "X", "X")
            for t in fig.texts[nt:]: t.set_visible(False)
            sizes[f"base_{vid}"] = save(fig, f"{out}/static/base_{vid}.png")
        # towns: placement by the site's own code with "88" numbers; the grid point each number reads comes from sampling
        # lat and lon grids at the same pins (exact for both grid kinds), then mapped to fractional row/col
        fig, ax, ky = layer_fig(vid)
        arts = town_call(ax, vid, (tw_la1, tw_lo1, tw_la))
        tv_la = dict(getattr(ax, "town_values", {}) or {}); pr_la = dict(getattr(ax, "pass_raw", {}) or {})
        fig2, ax2, _ = layer_fig(vid); town_call(ax2, vid, (tw_la1, tw_lo1, tw_lo))
        tv_lo = dict(getattr(ax2, "town_values", {}) or {}); pr_lo = dict(getattr(ax2, "pass_raw", {}) or {}); plt.close(fig2)
        lab2key = {v[0]: k for k, v in TM.WA_PASSES.items()}
        fig.canvas.draw(); r = fig.canvas.get_renderer(); Wd, Hd = fig.get_size_inches() * fig.dpi; slots = []; last = None
        for t in arts:
            if t.get_text() != "88": last = t.get_text(); continue
            if not t.get_visible(): continue
            if last in tv_la: pla, plo, kind, el = tv_la[last], tv_lo.get(last), "town", None
            elif last in lab2key and lab2key[last] in pr_la: k_ = lab2key[last]; pla, plo, kind, el = pr_la[k_], pr_lo.get(k_), "pass", TM.WA_PASSES[k_][3]
            else: continue
            if plo is None or not (np.isfinite(pla) and np.isfinite(plo)): continue
            fi_, fj_ = to_ij(np.array([[plo]]), np.array([[pla]])); fi_, fj_ = float(fi_[0, 0]) - i0, float(fj_[0, 0]) - j0
            if MD["grid"] == "lcc": fi_, fj_ = float(round(fi_)), float(round(fj_))   # nearest 3 km point, like the site
            bb = t.get_window_extent(r)
            slot = dict(name=last, kind=kind, x=bb.x0 / Wd, y=1 - (bb.y0 + bb.y1) / 2 / Hd, fi=fi_, fj=fj_, size=t.get_fontsize(), color=t.get_color())
            if kind == "pass" and oro is not None:
                rr, cc = int(round(fi_)) + i0, int(round(fj_)) + j0
                slot["t2m_corr"] = float(TM.LAPSE_T_F_PER_FT * (oro[rr, cc] - el))
            slots.append(slot); t.set_visible(False)
        a_ = views[vid]["cut_abs"]; views[vid]["cut"] = [a_[0] - i0, a_[1] - i0, a_[2] - j0, a_[3] - j0]; del views[vid]["cut_abs"]
        views[vid]["towns"] = slots
        if not os.path.exists(f"{out}/static/towns_{vid}.png") or views_only: sizes[f"towns_{vid}"] = save(fig, f"{out}/static/towns_{vid}.png")
        else: plt.close(fig)
        print(f"{m} {vid}: {len(slots)} town numbers", flush=True)
    # products
    def table(L, cm, ext):
        norm = BoundaryNorm(L, cm.N); mids = (np.asarray(L[:-1], float) + np.asarray(L[1:], float)) / 2
        cols = [to_hex(x) for x in cm(norm(mids))]
        under = to_hex(cm(norm(L[0] - 1e9))) if ext in ("min", "both") else None
        over = to_hex(cm(norm(L[-1] + 1e9))) if ext in ("max", "both") else None
        return dict(levels=[float(x) for x in L], colors=cols, under=under, over=over)
    REFC_L = np.arange(5, 80, 5)
    REFC_C = ["#04e9e7", "#019ff4", "#0300f4", "#02fd02", "#01c501", "#008e00", "#fdf802", "#e5bc00", "#fd9500", "#fd0000", "#d40000", "#bc0000", "#f800fd", "#9854c6"]
    FRZ_L = np.arange(0, 12001, 250); FRZ_A = [(0, "#3b2a7a"), (1000, "#2f63c8"), (2500, "#57c6e0"), (4000, "#9fe0b0"), (5500, "#f4e04d"), (7000, "#f2a33a"), (9000, "#d43f3a"), (12000, "#7d1f3f")]
    CM = {"t2m": HS.temp_cmap(), "gust10": HS.wind_cmap(), "aifswind": HS.wind_cmap(), "t850": HS.t850_cmap(), "t700": HS.t850_cmap(),
          "tcc": M.ramp(M.TCC_LEVELS, M.TCC_ANCH), "ir": M.ramp(M.IR_LEVELS, M.IR_ANCH), "vis": HS.cmap(M.VIS_COLS, M.VIS_COLS[0], (0, 0, 0, 0)),
          "refc": HS.cmap(REFC_C, REFC_C[0], REFC_C[-1]), "frz": M.ramp(FRZ_L, FRZ_A), "snowlvl": M.ramp(FRZ_L, FRZ_A),
          "qpf": HS.rain_cmap(), "snow": M.ramp(M.SNOW_LEVELS, M.SNOW_ANCH)}
    CAPE_L = [100, 250, 500, 750, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
    CAPE_A = [(100, "#d9e8c3"), (250, "#9fd27a"), (500, "#f2e34b"), (1000, "#f4a43a"), (2000, "#e2462f"), (3000, "#b0168e"), (5000, "#5c1a8c")]
    LTNG_L = [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8]
    LTNG_A = [(0.01, "#cfe3f7"), (0.1, "#7fb6ee"), (0.5, "#f2e34b"), (1, "#f4a43a"), (2, "#e2462f"), (8, "#b0168e")]
    LTGP_L = [0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2]
    LTGP_C = ["#e6dcf5", "#c3a6ec", "#9b6fe0", "#f2e34b", "#f4a43a", "#e8692f", "#d43f3a", "#8c1450"]   # 8 bands, no blends
    LTGP_A = [(0.01, "#e6dcf5"), (0.05, "#c3a6ec"), (0.1, "#9b6fe0"), (0.25, "#f2e34b"), (0.5, "#f4a43a"), (1, "#e2462f"), (2, "#8c1450")]
    JET_L = list(M.JET_LEVELS); W5_L = list(M.W500_LEVELS)
    CM.update(qpf1=CM["qpf"], qpf3=CM["qpf"], qpf6=CM["qpf"], qpf12=CM["qpf"], qpf24=CM["qpf"], qpf48=CM["qpf"], mslpqpf=CM["qpf"],
              snow1=CM["snow"], snow6=CM["snow"], gust6=CM["gust10"])
    T8A_L = np.arange(-15, 16, 1)
    CM.update(t2ma=TM.t2a_cmap(), t850a=HS.cmap([HS._anom_color(27.0 * x) for x in (T8A_L[:-1] + T8A_L[1:]) / 2.0], HS.ANOM_UNDER, HS.ANOM_OVER))
    CM.update(w500=M.ramp(M.W500_LEVELS, M.W500_ANCH), w250=M.ramp(M.JET_LEVELS, M.JET_ANCH), z500anom=HS.anom_cmap())
    CM.update(mucape=M.ramp(CAPE_L, CAPE_A), sbcape=M.ramp(CAPE_L, CAPE_A), ltng=M.ramp(LTNG_L, LTNG_A), ltgp=HS.cmap(LTGP_C, LTGP_C[0], LTGP_C[-1]))
    CM["ltng6"] = CM["ltng"]
    DS_L = [-36, -24, -18, -12, -8, -6, -4, -2, -1, -0.5, 0.5, 1, 2, 4, 6, 8, 12, 18, 24, 36]
    DS_C = ["#5c3310", "#7a4a1d", "#94622e", "#ad7c43", "#c4975e", "#d6b07c", "#e4c89c", "#efdcbf", "#f6ece0", "#f4f5f7",
            "#e3eefa", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#3a4fb0", "#5b2a9c", "#3d0f6b"]
    CM["dsnod"] = HS.cmap(DS_C, DS_C[0], DS_C[-1])
    prods = {
        "t2m": dict(title="2 m Temperature", fields=["t2m"], key="Temp (\u00b0F)", ticks=HS.TEMP_TICKS, **table(HS.TEMP_LEVELS, CM["t2m"], "both"),
                    freeze=32, extra="32\u00b0F line dashed  \u00b7  {lo} to {hi}\u00b0F in view", pct=[0.5, 99.5]),
        "gust10": dict(title="10 m Wind Gusts", fields=["gust"], key="Gust (mph)", ticks=HS.WIND_TICKS, **table(HS.WIND_LEVELS, CM["gust10"], "max"),
                       extra=(M.gust_note(m) if m in M.MODELS else "") + "  \u00b7  up to {hi} mph in view", pct=[1, 99.9]),
        "aifswind": dict(title="MSLP + 10 m Wind", fields=["mslp", "u10", "v10"], fill="wspd", key="10 m wind (mph)", ticks=HS.WIND_TICKS,
                         **table(HS.WIND_LEVELS, CM["aifswind"], "max"), spd_sigma=1.5, isobars=dict(every=4, sigma=6.0 if m == "hrrr" else 1.0,
                         color=HS.ISOBAR_COLOR, lw=HS.ISOBAR_LW, halo=HS.ISOBAR_HALO), barbs=dict(color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                         extra="isobars every 4 mb  \u00b7  barbs in kt  \u00b7  up to {hi} mph in view", pct=[0.5, 99.5]),
        "t850": dict(title="850 mb Temperature", fields=["t850"], key="850 mb temp (\u00b0C)", ticks=HS.T850_TICKS, tickfmt=True,
                     **table(HS.T850_LEVELS, CM["t850"], "both"), freeze=0, extra="0\u00b0C line dashed  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none"),
        "t700": dict(title="700 mb Temperature", fields=["t700"], key="700 mb temp (\u00b0C)", ticks=HS.T850_TICKS, tickfmt=True,
                     **table(HS.T850_LEVELS, CM["t700"], "both"), freeze=0, extra="0\u00b0C line dashed  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none"),
        "refc": dict(title="Composite Reflectivity", fields=["refc"], key="Reflectivity (dBZ)", ticks=[5, 15, 25, 35, 45, 55, 65, 75], tickfmt=True,
                     **table(REFC_L, CM["refc"], "max"), extra="simulated radar, strongest echo in the column  \u00b7  up to {hi} dBZ in view", pct=[0, 99.9], towns="names"),
        "qpf": dict(title="Precipitation Total", fields=["apcp"], key="Precip (in)", ticks=[0.1, 0.5, 1, 2, 3, 4, 6, 8, 10, 12], tickfmt=True,
                    **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="since the run started  \u00b7  liquid equivalent  \u00b7  max {hi} in in view",
                    pct=[0, 100], dec=2, fmt="in2", accum=True),
        "snow": dict(title="Snowfall Total", fields=["asnow"], key="Snow (in)", ticks=[0.1, 1, 3, 6, 10, 15, 24, 36, 48], tickfmt=True,
                     **table(M.SNOW_LEVELS, CM["snow"], "max"), extra="HRRR snowfall since the run started (model snow density)  \u00b7  max {hi} in in view",
                     pct=[0, 100], dec=1, fmt="in1", accum=True),
        "frz": dict(title="Freezing Level", fields=["frz"], key="Freezing level (ft)", ticks=[0, 2000, 4000, 6000, 8000, 10000, 12000], tickfmt=True,
                    **table(FRZ_L, CM["frz"], "both"), extra="height of the 0\u00b0C level above sea level  \u00b7  {lo} to {hi} ft in view", pct=[1, 99], fmt="ft100", towns="numbers"),
        "snowlvl": dict(title="Snow Level (estimate)", fields=["frz"], fill="snowlvl", key="Snow level (ft)", ticks=[0, 2000, 4000, 6000, 8000, 10000, 12000], tickfmt=True,
                        **table(FRZ_L, CM["snowlvl"], "both"), extra="estimate: freezing level minus 1,000 ft  \u00b7  {lo} to {hi} ft in view", pct=[1, 99], fmt="ft100", towns="numbers"),
        "tcc": dict(title="Total Cloud Cover", fields=["tcc"], key="Cloud (%)", ticks=[0, 20, 40, 60, 80, 100], tickfmt=True,
                    **table(M.TCC_LEVELS, CM["tcc"], "neither"), extra="all cloud layers combined, percent of sky", pct=[0, 100], towns="names"),
        "vis": dict(title="Surface Visibility", fields=["vis"], key="Visibility (mi)", ticks=M.VIS_LEVELS, tickfmt=True,
                    **table(M.VIS_LEVELS, CM["vis"], "max"), extra="model visibility, miles  \u00b7  blank = 7 mi or more  \u00b7  lowest {lo} mi in view",
                    pct=[0, 100], dec=1, fmt="vis"),
        "ir": dict(title="Simulated IR Satellite", fields=["ir"], key="Tops (\u00b0C)", ticks=[-80, -60, -40, -20, 0, 20, 40], tickfmt=True,
                   **table(M.IR_LEVELS, CM["ir"], "both"), extra="model cloud-top temperature, 10.7 \u00b5m  \u00b7  colors = cold, high tops", pct=[0, 100], towns="names"),
        "mucape": dict(title="Most Unstable CAPE", fields=["mucape"], key="MUCAPE (J/kg)", ticks=CAPE_L, tickfmt=True,
                       **table(CAPE_L, CM["mucape"], "max"), extra=("ECMWF most-unstable CAPE" if m == "ifs" else "most-unstable parcel (lowest 255 mb)") +
                       "  \u00b7  blank under 100 J/kg  \u00b7  up to {hi} J/kg in view", pct=[0, 99.9], only=("ifs", "gfs", "hrrr", "rrfs")),
        "sbcape": dict(title="Surface-Based CAPE", fields=["sbcape"], key="SBCAPE (J/kg)", ticks=CAPE_L, tickfmt=True,
                       **table(CAPE_L, CM["sbcape"], "max"), extra="surface parcel  \u00b7  blank under 100 J/kg  \u00b7  up to {hi} J/kg in view",
                       pct=[0, 99.9], only=("gfs", "hrrr", "rrfs")),
        "ltng": dict(title="Lightning Threat", fields=["ltng"], key="Flashes per km\u00b2 per 5 min", ticks=LTNG_L, tickfmt=True,
                     **table(LTNG_L, CM["ltng"], "max"), extra="model lightning flash density  \u00b7  up to {hi} in view", pct=[0, 99.9], dec=2,
                     towns="names", only=("hrrr", "rrfs")),
        "ltgp": dict(title="Lightning Potential (proxy)", fields=["ltgp"], key="Conv. precip, 6 h (in)", ticks=LTGP_L,
                     tickfmt=True, **table(LTGP_L, CM["ltgp"], "max"),
                     extra="PROXY, not flash density: ECMWF has no free lightning field  \u00b7  6 h convective precip (3 h at F+3) where MUCAPE \u2265 100",
                     pct=[0, 99.9], dec=2, fmt="in2", towns="names", only=("ifs",)),
        "w500": dict(title="500 mb Wind", fields=["u500", "v500", "z500"], fill="wspd", wind=["u500", "v500"], spd_mult=1.0, key="Wind (kt)",
                     ticks=list(range(20, 151, 10)), tickfmt=True, **table(W5_L, CM["w500"], "max"), spd_sigma=2.0 if m == "hrrr" else 0.8,
                     isobars=dict(field="z500", scale=0.1, every=6, sigma=7.0 if m == "hrrr" else 1.5, color="#101114", lw=1.1, halo=2.6),
                     barbs=dict(u="u500", v="v500", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                     extra="speed in kt  \u00b7  shaded from 20 kt  \u00b7  heights every 6 dam  \u00b7  up to {hi} kt in view", pct=[0.5, 99.9], towns="names"),
        "w250": dict(title="250 mb Wind (jet)", fields=["u250", "v250", "z250"], fill="wspd", wind=["u250", "v250"], spd_mult=1.0, key="Wind (kt)",
                     ticks=list(range(50, 201, 25)), tickfmt=True, **table(JET_L, CM["w250"], "max"), spd_sigma=2.0 if m == "hrrr" else 0.8,
                     isobars=dict(field="z250", scale=0.1, every=12, sigma=7.0 if m == "hrrr" else 1.5, color="#101114", lw=1.1, halo=2.6),
                     barbs=dict(u="u250", v="v250", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                     extra="speed in kt  \u00b7  shaded from 50 kt  \u00b7  heights every 12 dam  \u00b7  up to {hi} kt in view", pct=[0.5, 99.9], towns="names"),
        "z500anom": dict(title="500 mb Height Anomaly", fields=["z500"], fill="z500anom", key="Anomaly (m)", ticks=HS.ANOM_TICKS, tickfmt=True,
                         **table(HS.ANOM_LEVELS, CM["z500anom"], "both"),
                         isobars=dict(field="z500", scale=0.1, every=6, sigma=1.5, color="#101114", lw=1.25, halo=2.4),
                         extra="vs 1991-2020 NCEP/NCAR monthly mean  \u00b7  heights every 6 dam  \u00b7  {lo} to {hi} m in view", pct=[0.5, 99.5],
                         towns="names", clim="z500", only=("gfs", "ifs", "aifs", "eps")),
        # stage 2 (browser-only): precip in the last 1/6/24 h and MSLP + 6 h precip (differences of the run total in the browser)
        "qpf1": dict(title="1 h Precipitation", fields=["apcp"], window=1, fill="window", key="Precip (in)", ticks=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2], tickfmt=True,
                     **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="liquid equivalent in the hour ending at the valid time  \u00b7  max {hi} in in view",
                     pct=[0, 100], dec=2, fmt="in2", only=("hrrr", "rrfs")),
        "qpf6": dict(title="6 h Precipitation", fields=["apcp"], window=6, fill="window", key="Precip (in)", ticks=[0.1, 0.5, 1, 2, 3, 4, 6], tickfmt=True,
                     **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="liquid equivalent in the 6 h ending at the valid time  \u00b7  max {hi} in in view",
                     pct=[0, 100], dec=2, fmt="in2", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "qpf24": dict(title="24 h Precipitation", fields=["apcp"], window=24, fill="window", key="Precip (in)", ticks=[0.1, 0.5, 1, 2, 3, 4, 6, 8], tickfmt=True,
                      **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="liquid equivalent in the 24 h ending at the valid time  \u00b7  max {hi} in in view",
                      pct=[0, 100], dec=2, fmt="in2", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "qpf3": dict(title="3 h Precipitation", fields=["apcp"], window=3, fill="window", key="Precip (in)", ticks=[0.1, 0.25, 0.5, 1, 2, 3], tickfmt=True,
                     **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="liquid equivalent in the 3 h ending at the valid time  \u00b7  max {hi} in in view",
                     pct=[0, 100], dec=2, fmt="in2", only=("hrrr", "rrfs", "gfs", "ifs")),
        "qpf12": dict(title="12 h Precipitation", fields=["apcp"], window=12, fill="window", key="Precip (in)", ticks=[0.1, 0.5, 1, 2, 3, 4, 6], tickfmt=True,
                     **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="liquid equivalent in the 12 h ending at the valid time  \u00b7  max {hi} in in view",
                     pct=[0, 100], dec=2, fmt="in2", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "qpf48": dict(title="48 h Precipitation", fields=["apcp"], window=48, fill="window", key="Precip (in)", ticks=[0.1, 0.5, 1, 2, 4, 6, 8, 10], tickfmt=True,
                     **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="liquid equivalent in the 48 h ending at the valid time  \u00b7  max {hi} in in view",
                     pct=[0, 100], dec=2, fmt="in2", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "mslpqpf": dict(title="MSLP + 6 h Precipitation", fields=["apcp", "mslp"], window=6, fill="window", key="6 h precip (in)",
                        ticks=[0.1, 0.5, 1, 2, 3, 4, 6], tickfmt=True, **table(HS.RAIN_LEVELS, CM["qpf"], "max"),
                        isobars=dict(field="mslp", every=4, sigma=6.0 if m == "hrrr" else 1.0, color=HS.ISOBAR_COLOR, lw=HS.ISOBAR_LW, halo=HS.ISOBAR_HALO),
                        extra="isobars every 4 mb  \u00b7  precip in the 6 h ending at the valid time  \u00b7  max {hi} in in view",
                        pct=[0, 100], dec=2, fmt="in2", towns="names", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "snow1": dict(title="1 h Snowfall (rate)", fields=["asnow"], window=1, wfield="asnow", fill="window", key="Snow (in)", ticks=[0.1, 0.5, 1, 2, 3, 4], tickfmt=True,
                      **table(M.SNOW_LEVELS, CM["snow"], "max"), extra="snowfall in the hour ending at the valid time (model snow density)  \u00b7  max {hi} in in view",
                      pct=[0, 100], dec=1, fmt="in1", only=("hrrr", "rrfs")),
        "snow6": dict(title="6 h Snowfall", fields=["asnow"], window=6, wfield="asnow", fill="window", key="Snow (in)", ticks=[0.1, 1, 3, 6, 10, 15, 24], tickfmt=True,
                      **table(M.SNOW_LEVELS, CM["snow"], "max"), extra="snowfall in the 6 h ending at the valid time (model snow density)  \u00b7  max {hi} in in view",
                      pct=[0, 100], dec=1, fmt="in1", only=("hrrr", "rrfs")),
        "gust6": dict(title="6 h Max Wind Gust", fields=["gust"], window=6, wmax=True, wfield="gust", fill="window", key="Gust (mph)", ticks=HS.WIND_TICKS,
                      **table(HS.WIND_LEVELS, CM["gust10"], "max"), extra="highest gust over the model hours in the 6 h ending at the valid time  \u00b7  up to {hi} mph in view",
                      pct=[1, 99.9], only=("hrrr", "rrfs", "gfs", "ifs")),
        "ltng6": dict(title="6 h Max Lightning Threat", fields=["ltng"], window=6, wmax=True, wfield="ltng", fill="window", key="Flashes per km\u00b2 per 5 min",
                      ticks=LTNG_L, tickfmt=True, **table(LTNG_L, CM["ltng"], "max"), extra="highest hourly flash density in the 6 h ending at the valid time  \u00b7  up to {hi} in view",
                      pct=[0, 99.9], dec=2, towns="names", only=("hrrr", "rrfs")),
        "dsnod": dict(title="Snow Depth Change", fields=["dsnod"], key="Change (in)", ticks=[-24, -12, -6, -2, 0, 2, 6, 12, 24], tickfmt=True,
                      **table(DS_L, CM["dsnod"], "both"), extra="snow depth now minus at the start of the run (new snow, melt and settling)  \u00b7  {lo} to {hi} in in view",
                      pct=[0.5, 99.5], dec=1, fmt="in1s", only=("hrrr", "rrfs")),
        # stage 2 (browser-only): anomalies vs 1991-2020 normals (static climatology, value = field - normal in the browser)
        "t2ma": dict(title="2 m Temperature Anomaly", fields=["t2m"], fill="anom", anom="t2m", clim="t2m", key="Anomaly (\u00b0F)", ticks=list(TM.T2A_TICKS),
                     tickfmt=True, **table(TM.T2A_LEVELS, CM["t2ma"], "both"),
                     extra="vs 1991-2020 normal for the date and hour (NCEP/NCAR, adjusted to model terrain)  \u00b7  {lo} to {hi}\u00b0F in view",
                     pct=[0.5, 99.5]),
        "t850a": dict(title="850 mb Temperature Anomaly", fields=["t850"], fill="anom", anom="t850", clim="t850", key="Anomaly (\u00b0C)",
                      ticks=list(range(-15, 16, 3)), tickfmt=True, **table(T8A_L, CM["t850a"], "both"),
                      extra="vs 1991-2020 NCEP/NCAR monthly normal  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none",
                      only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
    }
    prods = {k: v for k, v in prods.items() if m in v.pop("only", (m,))}
    if m == "eps":   # ensemble: mean versions of the shared products plus spread / probability maps
        prods = {k: prods[k] for k in ("t2m", "t2ma", "z500anom")}
        prods["t2ma"]["title"] = "2 m Temperature Anomaly (ens. mean)"
        prods["t2m"]["title"] = "2 m Temperature (ens. mean)"; prods["t2m"]["extra"] = "mean of 50 members  \u00b7  " + prods["t2m"]["extra"]
        prods["z500anom"]["title"] = "500 mb Height Anomaly (ens. mean)"
        SD_L = list(range(0, 13)); SD_A = [(0, "#f7fbff"), (2, "#c6dbef"), (4, "#6baed6"), (6, "#fdd49e"), (8, "#fc8d59"), (12, "#b30000")]
        P_L = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100]; P_A = [(5, "#e8f1fb"), (30, "#8fbfe8"), (50, "#3b82d1"), (70, "#2a4fb0"), (90, "#5b2a9c"), (100, "#2b0f52")]
        Z_L = list(range(0, 161, 10)); Z_A = [(0, "#f7f7f7"), (20, "#d9ecd0"), (40, "#9fd27a"), (60, "#f2e34b"), (90, "#f4a43a"), (120, "#e2462f"), (160, "#8c1450")]
        CM.update(et2sd=M.ramp(SD_L, SD_A), ep32=M.ramp(P_L, P_A), ez500=M.ramp(Z_L, Z_A))
        prods["et2sd"] = dict(title="2 m Temperature Spread", fields=["t2sd"], key="Spread (\u00b0F)", ticks=[0, 2, 4, 6, 8, 10, 12], tickfmt=True,
                              **table(SD_L, CM["et2sd"], "max"), extra="standard deviation of 50 members  \u00b7  higher = less certain  \u00b7  up to {hi}\u00b0F in view",
                              pct=[0.5, 99.5], dec=1)
        prods["ep32"] = dict(title="Chance of Freezing (2 m)", fields=["p32"], key="Freezing (%)", ticks=[5, 10, 20, 30, 50, 70, 90, 100], tickfmt=True,
                             **table(P_L, CM["ep32"], "neither"), extra="share of the 50 members with 2 m temp at or below 32\u00b0F", pct=[0, 100])
        prods["ez500"] = dict(title="500 mb Height Mean + Spread", fields=["z500", "z5sd"], fill="z5sd", key="Spread (m)", ticks=[0, 20, 40, 60, 80, 100, 120, 140, 160],
                              tickfmt=True, **table(Z_L, CM["ez500"], "max"),
                              isobars=dict(field="z500", scale=0.1, every=6, sigma=1.5, color="#101114", lw=1.25, halo=2.4),
                              extra="lines = mean height every 6 dam  \u00b7  colors = spread of 50 members  \u00b7  up to {hi} m in view", pct=[0.5, 99.5], towns="names")
    if "vis" in prods: prods["vis"]["over"] = None
    for k in ("mucape", "sbcape", "ltng", "ltgp"):
        if k in prods: prods[k]["min_show"] = prods[k]["levels"][0]
    if "ep32" in prods: prods["ep32"]["min_show"] = 5
    for k in ("w500", "w250"):
        if k in prods: prods[k]["under"] = "#f4f5f7"   # light below the first level so barbs and height lines stay readable
    if "mslpqpf" in prods: prods["mslpqpf"]["under"] = "#f4f5f7"   # light background so the dark isobars read (no blanking)
    for k in ("qpf", "snow", "refc", "qpf1", "qpf3", "qpf6", "qpf12", "qpf24", "qpf48", "snow1", "snow6", "ltng6"):
        if k in prods: prods[k]["min_show"] = prods[k]["levels"][0]   # blank below the first level (like the site)
    for pid, P in prods.items():
        P.setdefault("fill", P["fields"][0]); tk0 = list(P["ticks"])
        P.update(freeze_color=HS.FREEZE_COLOR, freeze_lw=HS.FREEZE_LW) if "freeze" in P else None
        P["keys"] = {}
        for vid in vids:
            fn = f"static/key_{m}_{pid}_{vid}.png"; P["keys"][vid] = fn
            fig, ax, ky = layer_fig(vid); x0, x1, y0, y1 = ax.get_extent(TM.VIEWS[vid]["proj"])
            X, Y = np.meshgrid([x0, x1], [y0, y1]); L = np.asarray(P["levels"]); cm = CM[pid]
            ext = "both" if P["under"] and P["over"] else "max" if P["over"] else "min" if P["under"] else "neither"
            if pid == "vis": ext = "max"
            cs = ax.contourf(X, Y, np.full((2, 2), np.nan), levels=L, cmap=cm, norm=BoundaryNorm(L, cm.N), extend=ext, transform=ax.projection)
            cs.set_visible(False)
            if P.get("tickfmt"):
                cb = HS.hbar(fig, cs, [], P["key"], ky); cb.set_ticks(P["ticks"])
                cb.ax.set_xticklabels([f"{t:g}" for t in P["ticks"]], fontproperties=HS.font(700, 13))
            else: HS.hbar(fig, cs, tk0, P["key"], ky)
            HS.credit(fig, TM.CREDIT_NOAA if (pid == "t2m" and m in NOAA) else (M.credit(m) if m in M.MODELS else TM.CREDIT.format(name=minfo(m)["name"])))
            sizes[f"key_{m}_{pid}_{vid}"] = save(fig, f"{out}/{fn}")
        P["ticks"] = [float(t) for t in tk0]
    clim = {}
    for var in sorted({P["clim"] for P in prods.values() if P.get("clim")}):
        clim[var] = clim_static(m, out, crop_la, crop_lo, var, None if oro is None else oro[i0:i1, j0:j1] / 3.28084)
    mp = f"{out}/manifest.json"; man = json.load(open(mp)) if os.path.exists(mp) else {}
    man.update(dpi=DPI, style=dict(BG=HS.BG, INK=HS.INK, MUTED=HS.MUTED, ACCENT=HS.ACCENT))
    MI = minfo(m)
    man.setdefault("models", {})[m] = dict(name=MI["name"], site=MI["site"], res=MI["res"], grid=MD["grid"],
                                          crop=[i0, i1, j0, j1], views=views, products=prods, clim=clim)
    man.setdefault("runs", {}).setdefault(m, [])
    json.dump(man, open(mp, "w"), indent=1)
    print(f"{m} static done, crop {[i0, i1, j0, j1]}", flush=True)

# ------------------------------------------------------------------------------------------------ steps
def steps(m, cycle, want, out, workers, only_missing=True, deadline=None):
    import temp_maps as TM, menu_maps as M
    man = json.load(open(f"{out}/manifest.json")); crop = man["models"][m]["crop"]; i0, i1, j0, j1 = crop
    c = dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
    rd = f"{out}/runs/{m}/{cycle}"; os.makedirs(rd + "/single", exist_ok=True)
    rj = f"{rd}/run.json"; run = json.load(open(rj)) if os.path.exists(rj) else None
    have = {s_["f"] for s_ in (run or {}).get("steps", [])}
    todo = [s for s in want if not (only_missing and s in have)]
    from concurrent.futures import ProcessPoolExecutor
    PT = TM.PT; done = {}; new = []
    with ProcessPoolExecutor(workers) as ex:
        for s, sizes, ranges, nb, tt in ex.map(step_job, [(m, cycle, s, crop, rd) for s in todo]):
            if sizes is None or "t2m" not in (ranges or {}): print(f"{m} f{s:03d} not ready ({str(ranges)[:80]})", flush=True); continue
            done[s] = ranges; new.append(s); print(f"{m} f{s:03d} {len(ranges)} fields {sum(sizes.values())/1e3:.0f} KB grib {nb/1e6:.1f} MB {tt:.1f} s", flush=True)
            if deadline and time.time() > deadline: break
    meta = {s_["f"]: s_ for s_ in (run or {}).get("steps", [])}
    for s, ranges in done.items():
        v = c + dt.timedelta(hours=s); vl = v.astimezone(PT)
        pk = ranges.pop("_packs", {})
        meta[s] = dict(f=s, valid=v.isoformat(), valid_line=f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT", badge=[f"F+{s}", f"{v:%HZ %a}".upper()], ranges=ranges)
        if pk: meta[s]["packs"] = pk
    # progressive: publish only the unbroken run of steps from the first one (no holes in the slider)
    ordered = []; 
    for s in want:
        if s in meta: ordered.append(meta[s])
        else: break
    fields = sorted({k for s_ in ordered for k in s_["ranges"]})
    MM = minfo(m)
    run = dict(model=m, cycle=cycle, init=c.isoformat(), base=f"runs/{m}/{cycle}", fields=fields, grid=dict(ny=i1 - i0, nx=j1 - j0),
               runline=f"{MM['name']} {MM['res']} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}", steps=ordered,
               complete=len(ordered) == len(want), expected=len(want), file="single/{name}_f{f:03d}.png")
    json.dump(run, open(rj, "w"), indent=1)
    return run, new

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("cmd", choices=["static", "steps"]); ap.add_argument("--model", required=True)
    ap.add_argument("--cycle"); ap.add_argument("--steps"); ap.add_argument("--out", default=os.path.join(HERE, "data"))
    ap.add_argument("--workers", type=int, default=4); ap.add_argument("--all", action="store_true"); a = ap.parse_args()
    if a.cmd == "static": static(a.model, a.out, views_only=a.all)
    else:
        full = steps_for(a.model, int(a.cycle[8:10]))
        want = full if not a.steps else (lambda x, y: [s for s in full if x <= s <= y])(*map(int, a.steps.split("-")))
        run, new = steps(a.model, a.cycle, want, a.out, a.workers)
        print(f"{a.model} {a.cycle}: +{len(new)} steps, {len(run['steps'])}/{run['expected']} published, complete={run['complete']}", flush=True)
    sys.stdout.flush(); os._exit(0)

if __name__ == "__main__": main()
