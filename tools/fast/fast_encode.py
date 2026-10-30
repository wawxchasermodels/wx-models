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
GLOBAL_VIEWS = ("puget", "wa", "wwa", "ewa", "passes", "newa", "lm", "bc", "pnwt", "pnw", "na")
MODELS = {   # grid "lcc" = HRRR 3 km, "ll" = 0.25 deg global (lat 90 -> -90, lon rolled to 0..360)
    "hrrr": dict(grid="lcc", views=("puget", "wa", "wwa", "ewa", "passes", "newa", "lm", "pnwhr"), cycles=(0, 6, 12, 18), steps=list(range(1, 49)), keep=2),
    # 06/18Z added 10-29-26 7:24 PM (Benjamin). Checked on data.ecmwf.int / NOAA 10-29 18Z: GFS 06/18Z go to 384 h like 00/12Z;
    # ECMWF 0.25 06/18Z only to 144 h (3-hourly); AIFS 06/18Z to 360 h (6-hourly) like 00/12Z.
    # RRFS (NOAA, 3 km CONUS, operational since 2026): 00/06/12/18Z hourly to 48 h then 3-hourly to 84 h (stage 3, 10-30-26)
    "rrfs": dict(grid="lcc", views=("puget", "wa", "wwa", "ewa", "passes", "newa", "lm", "pnwhr"), cycles=(0, 6, 12, 18), steps=list(range(1, 49)) + list(range(51, 85, 3)), keep=2),
    # NBM (NOAA National Blend, 2.5 km CONUS NDFD grid): 00/06/12/18Z, hourly to 36 h then 3-hourly to 168 h (stage 3, 10-30-26)
    "nbm":  dict(grid="lcc", views=("puget", "wa", "wwa", "ewa", "passes", "newa", "lm", "pnwhr"), cycles=(0, 6, 12, 18), steps=list(range(1, 37)) + list(range(39, 169, 3)), keep=2,
                 lcc=dict(central_longitude=-95.0, central_latitude=25.0, standard_parallels=(25.0, 25.0)), radius=6371200.0),
    "gfs":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 6, 12, 18), steps=list(range(3, 361, 3)), keep=2),
    "ifs":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 6, 12, 18), steps=list(range(3, 145, 3)) + list(range(150, 361, 6)),
                 steps_short=list(range(3, 145, 3)), short_cycles=(6, 18), keep=2, keep_long=True),
    "aifs": dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 6, 12, 18), steps=list(range(6, 361, 6)), keep=2),
    # ECMWF ENS (EPS) 0.25 open data, 50 perturbed members (no control in the open files), 00/12Z to 360 h. Mean/spread/probability
    # computed here from the members (the open em/es file only appears once the whole run is out). 10-30-26 (Benjamin's saved order).
    "eps":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 12), steps=list(range(6, 361, 6)), keep=2, grid_from="ifs"),
    # AIFS ensemble (stage 4): 50 members, 00/12Z, 6-hourly to 360 h; 2 m temp + 500 mb height (z / g), same products as "eps"
    "aens": dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 12), steps=list(range(6, 361, 6)), keep=2, grid_from="ifs"),
}
MINFO = {"aens": dict(name="ECMWF AIFS Ensemble", site="AIFS ENS", res="0.25\u00b0 \u00b7 50 members", credit_as="aifs"),
         "nbm": dict(name="NOAA NBM", site="NBM", res="2.5 km", noaa=True),
         "eps": dict(name="ECMWF Ensemble", site="ECMWF EPS", res="0.25\u00b0 \u00b7 50 members", credit_as="ifs")}
def minfo(m):
    import menu_maps as M
    return MINFO.get(m) or M.MODELS[m]
EPS_URL = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-ef"
AENS_URL = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/aifs-ens/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-pf"
ENS_SRC = {"eps": (EPS_URL, "gh", 1.0), "aens": (AENS_URL, "z", 1 / 9.80665)}   # 500 mb height: IFS ENS gh (m), AIFS ENS z (m2/s2)

NBM_URL = "https://noaa-nbm-grib2-pds.s3.amazonaws.com/blend.{d}/{h:02d}/core/blend.t{h:02d}z.core.f{s:03d}.co.grib2"
class NbmReader:
    """NBM core step: exact idx-line lookups ("VAR:level:time:extra") with HTTP ranges. Values on the NDFD 2.5 km Lambert grid,
    row 0 = south (like HRRR)."""
    def __init__(self, c, s):
        import temp_maps as TM
        self.c, self.s, self.bytes = c, s, 0; self.url = NBM_URL.format(d=f"{c:%Y%m%d}", h=c.hour, s=s)
        self.idx = TM.get(self.url + ".idx").decode().splitlines()
    def get(self, var_level, tdesc, extra="", latlon=False):
        import temp_maps as TM, eccodes as ec
        for k, l in enumerate(self.idx):
            p = l.split(":")
            if len(p) > 6 and f"{p[3]}:{p[4]}" == var_level and p[5] == tdesc and p[6] == extra:
                a = int(p[1]); b = int(self.idx[k + 1].split(":")[1]) - 1 if k + 1 < len(self.idx) else a + 40_000_000
                blob = TM.get(self.url, (a, b)); self.bytes += len(blob); g = ec.codes_new_from_message(blob)
                nx, ny = ec.codes_get(g, "Nx"), ec.codes_get(g, "Ny"); v = ec.codes_get_values(g).reshape(ny, nx)
                alt = ec.codes_get(g, "alternativeRowScanning") == 1   # NDFD grids: every other row runs east to west
                fix = (lambda a: np.concatenate([a[:1], a[1:]], 0)) if not alt else (lambda a: np.where((np.arange(ny) % 2 == 1)[:, None], a[:, ::-1], a))
                v = fix(np.where(v > 9e20, np.nan, v))
                if latlon:
                    la = ec.codes_get_array(g, "latitudes").reshape(ny, nx); lo = ec.codes_get_array(g, "longitudes").reshape(ny, nx)   # eccodes gives these in natural order
                    ec.codes_release(g); return la, np.where(lo > 180, lo - 360, lo), v
                ec.codes_release(g); return v
        raise KeyError(f"{var_level} {tdesc} {extra}")
def _nbm(var_level, tdesc, conv, every=1, extra=""):
    def g(R, m):
        if R.s % every: raise KeyError(var_level)
        return conv(R.get(var_level, tdesc(R.s), extra))
    return g
NBM_FIELDS = {
    "t2m":  (_nbm("TMP:2 m above ground", lambda s: f"{s} hour fcst", lambda k: (k - 273.15) * 1.8 + 32), "F"),
    "gust": (_nbm("GUST:10 m above ground", lambda s: f"{s} hour fcst", lambda v: v * 2.23694), "mph"),
    "tcc":  (_nbm("TCDC:surface", lambda s: f"{s} hour fcst", lambda v: np.clip(v, 0, 100)), "%"),
    "nq1":  (_nbm("APCP:surface", lambda s: f"{s - 1}-{s} hour acc fcst", lambda v: np.clip(v, 0, None) / 25.4), "in"),
    "nq6":  (_nbm("APCP:surface", lambda s: f"{s - 6}-{s} hour acc fcst", lambda v: np.clip(v, 0, None) / 25.4, every=6), "in"),
    "ns6":  (_nbm("ASNOW:surface", lambda s: f"{s - 6}-{s} hour acc fcst", lambda v: np.clip(v, 0, None) / 0.0254, every=6), "in"),
    "tstm": (_nbm("TSTM:surface", lambda s: f"{s - 3}-{s} hour acc fcst", lambda v: np.clip(v, 0, 100), every=3, extra="probability forecast"), "%"),
    "maxt": (_nbm("TMAX:2 m above ground", lambda s: f"{s - 12}-{s} hour max fcst", lambda k: (k - 273.15) * 1.8 + 32), "F"),   # 12 h periods end 00Z (max) / 12Z (min)
    "mint": (_nbm("TMIN:2 m above ground", lambda s: f"{s - 12}-{s} hour min fcst", lambda k: (k - 273.15) * 1.8 + 32), "F"),   # 12 h periods end 00Z (max) / 12Z (min)
}

class _NoSt:
    def field(self, *a, **k): raise StopIteration
# Stage 4 extras (10-30): per-step member params beyond 2 m temp + 500 mb height. name: (param, level, kind, scale, offset)
#   kind "ms": mean (+ sd); "p90": mean + 90th percentile; "pc": mean + chance >= threshold. Memory: one param's member stack at a time.
ENS_EXTRA = {"tp": ("tp", None, "p90", 39.3701, 0), "sf": ("sf", None, "p90", 393.701, 0), "10fg": ("10fg", None, "p90", 2.23694, 0),
             "msl": ("msl", None, "ms", 0.01, 0), "t850": ("t", "850", "ms", 1.0, -273.15), "mucape": ("mucape", None, "pc", 1.0, 0),
             # old site "EPS lows / highs" = ENS mean of member extremes: 2 m max/min over the last 3 h (to 144 h) or 6 h (after), deg F
             "mx2t": (("mx2t3", "mx2t6"), None, "m", 1.8, -459.67), "mn2t": (("mn2t3", "mn2t6"), None, "m", 1.8, -459.67)}
SPAG_LEVELS = (5520, 5760)   # 552 / 576 dam member lines (trough / ridge)
class EpsReader:
    """ECMWF ENS / AIFS ENS step: downloads the 50 member messages (HTTP ranges) and keeps running sums for 2 m temp and 500 mb
    height, plus (stage 4 extras) precip / snow / gust mean + 90th percentile, MSLP and 850 mb temp means, MUCAPE chance >= 500,
    member low centres and 500 mb member lines (spaghetti) on the model's cropped grid. f() = ensemble mean, extra() = the rest."""
    st = _NoSt()
    def __init__(self, c, s, kind="eps", crop=None):
        import temp_maps as TM, eccodes as ec
        from concurrent.futures import ThreadPoolExecutor
        self.c, self.s, self.bytes, self.crop = c, s, 0, crop
        url, zp, zs = ENS_SRC[kind]; base = url.format(d=f"{c:%Y%m%d}", h=c.hour, s=s)
        idx = [json.loads(l) for l in TM.get(base + ".index").decode().splitlines()]
        mem = [x for x in idx if x.get("type") in ("pf", "cf")]
        def fetch(x): return x, TM.get(base + ".grib2", (x["_offset"], x["_offset"] + x["_length"] - 1))
        def decode(blob):
            self.bytes += len(blob); g = ec.codes_new_from_message(blob)
            ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
            la0, lo0, d = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "iDirectionIncrementInDegrees")
            v = ec.codes_get_values(g).reshape(nj, ni).astype(np.float64); ec.codes_release(g)
            if not hasattr(self, "lat"):
                self.lat = la0 - d * np.arange(nj); lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180; self.o = np.argsort(lon); self.lon = lon[self.o]
            return v[:, self.o]
        acc = {}; self.X = {}
        core = [x for x in mem if x["param"] == "2t" or (x["param"] == zp and x.get("levelist") == "500")]
        gh_members = []
        with ThreadPoolExecutor(8) as ex:
            for x, blob in ex.map(fetch, core):
                par = "gh" if x["param"] == zp else x["param"]; v = decode(blob) * (zs if par == "gh" else 1.0)
                a = acc.setdefault(par, dict(n=0, s=np.zeros_like(v), q=np.zeros_like(v), c=np.zeros_like(v)))
                a["n"] += 1; a["s"] += v; a["q"] += v * v
                if par == "2t": a["c"] += v <= 273.15
                if par == "gh" and crop: gh_members.append(self._crop(v).astype(np.float32))
            if len(acc) < 2 or min(a["n"] for a in acc.values()) < 40: raise RuntimeError(f"eps f{s}: only {[(k, a['n']) for k, a in acc.items()]} members")
            self.n = acc["2t"]["n"]; self.A = acc
            if not crop: return
            # extras: one param at a time (cropped member stacks, float32)
            for name, (par, lev, kind_, sc, off) in ENS_EXTRA.items():
                xs = [x for x in mem if x["param"] in (par if isinstance(par, tuple) else (par,)) and (lev is None or x.get("levelist") == lev)]
                if len(xs) < 40: continue
                if kind == "aens" and name in ("tp", "sf"): sc = sc / 1000.0   # AIFS ENS precip / snow water come in kg/m2 (mm), IFS ENS in m
                try: st = np.stack([self._crop(decode(blob) * sc + off).astype(np.float32) for x, blob in ex.map(fetch, xs)])
                except Exception as e: print(f"{kind} f{s:03d} {name}: {str(e)[:100]}", flush=True); continue
                if name in ("tp", "sf"): st = np.clip(st, 0, None)
                self.X[name] = st.mean(0)
                if kind_ == "p90": self.X[name + "90"] = np.percentile(st, 90, axis=0)
                if kind_ == "pc": self.X[name + "p"] = (st >= 500).mean(0) * 100
                if name == "msl": self.lows, self.X["lowp"] = self._lows(st)
                del st
        if gh_members: self.spag = self._spag(np.stack(gh_members)); del gh_members
    def _crop(self, v):
        i0, i1, j0, j1 = self.crop; return roll_ll(v)[i0:i1, j0:j1]
    def _lows(self, st):
        """Member low centres (local MSLP minima at least 2 mb below their 5-deg surroundings) + share of members with a centre
        within ~300 km of each point (%). Positions are cropped-grid (row, col) like the town slots."""
        from scipy.ndimage import gaussian_filter, minimum_filter, uniform_filter, binary_dilation
        lows, dens = [], np.zeros(st.shape[1:], np.float32)
        yy, xx = np.mgrid[-12:13, -24:25]; disk = (yy / 12.0) ** 2 + (xx / 24.0) ** 2 <= 1   # 3 deg lat x 6 deg lon (~300 km at 50N)
        for k, p in enumerate(st):
            g = gaussian_filter(p.astype(float), 1.5)
            mn = (g == minimum_filter(g, size=21, mode="nearest")) & (uniform_filter(g, size=21, mode="nearest") - g >= 2.0) & (g < 1008)
            mn[:3] = mn[-3:] = False; mn[:, :3] = mn[:, -3:] = False
            r, c = np.nonzero(mn)
            for i, j in zip(r, c): lows.append([int(k), int(i), int(j), round(float(p[i, j]), 1)])
            if len(r): dens += binary_dilation(mn, structure=disk)
        return lows, dens / len(st) * 100
    def _spag(self, gh):
        """500 mb member lines at SPAG_LEVELS, on a 2x coarser grid, simplified; vertices as (row, col) * 10 integers."""
        import contourpy
        from scipy.ndimage import gaussian_filter
        out = {str(L): [] for L in SPAG_LEVELS}
        for k, z in enumerate(gh):
            zc = gaussian_filter(z.astype(float), 1.0)[::2, ::2]
            gen = contourpy.contour_generator(z=zc, line_type="Separate")
            for L in SPAG_LEVELS:
                for ln in gen.lines(L):
                    ln = _rdp(ln, 0.35)
                    if len(ln) < 3: continue
                    out[str(L)].append([k] + [int(round(v * 20)) for xy in ln for v in (xy[1], xy[0])])   # (row, col) on the full grid * 10
        return out
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
    def cropped(self, name):   # already on the cropped grid (no roll / crop in step_job)
        if name not in self.X: raise KeyError(name)
        return self.X[name]
def _rdp(P, eps):
    """Ramer-Douglas-Peucker line simplification (iterative)."""
    P = np.asarray(P); n = len(P)
    if n < 3: return P
    keep = np.zeros(n, bool); keep[0] = keep[-1] = True; stack = [(0, n - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1: continue
        d = P[b] - P[a]; L = np.hypot(*d) or 1e-9; seg = P[a + 1:b] - P[a]
        dist = np.abs(seg[:, 0] * d[1] - seg[:, 1] * d[0]) / L; k = int(np.argmax(dist))
        if dist[k] > eps: keep[a + 1 + k] = True; stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return P[keep]
def _ens(name):
    def g(R, m):
        if m not in ("eps", "aens"): raise KeyError(name)
        return R.extra(name)
    return g
class Cropped(np.ndarray): pass   # marker: getter already returned the model's cropped grid
def _ensc(src):
    def g(R, m):
        if m not in ("eps", "aens"): raise KeyError(src)
        return np.asarray(R.cropped(src)).view(Cropped)
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
    if m == "ifs": return np.clip(_ec("sf")(R, m), 0, None) * 393.701   # ECMWF snowfall (m water) at 10:1, run total
    if m not in ("hrrr", "rrfs"): raise KeyError("asnow")
    return np.asarray(R.acc0("ASNOW:surface")[2], float) / 0.0254
def _prev_step(m, c, s):
    st = [0] + [x for x in steps_for(m, c.hour) if x < s]; return st[-1]
def _inc(R, m, what):
    """Water (in) that fell in this output interval: run total now minus at the previous step. what: "tp" (all precip) or "sf" (ECMWF snow water)."""
    k = f"_inc_{what}"
    if k in R.cache: return R.cache[k]
    import menu_maps as M, temp_maps as TM
    s0 = _prev_step(m, R.c, R.s)
    if m in NOAA:
        now = np.asarray(R.acc0("APCP:surface")[2], float) / 25.4
        prev = 0.0 if s0 == 0 else np.asarray(M.Reader(m, R.c, s0).acc0("APCP:surface")[2], float) / 25.4
    else:
        now = np.asarray(R.st.field(what)[2], float) * 39.3701
        prev = 0.0 if s0 == 0 else np.asarray(TM.Step(m, R.c, s0).field(what)[2], float) * 39.3701
    R.cache[k] = r = np.clip(now - prev, 0, None); return r
def _tmax_col(R, m):   # warmest of 2 m, 925, 850, 700 and 500 mb (K), for the Kuchera ratio
    t = np.asarray(R.f("t2m")[2], float)
    for lev in (925, 850, 700, 500): t = np.maximum(t, np.asarray(R.f(f"T:{lev}")[2], float))
    return t
def _kinc(R, m):
    """Kuchera snowfall (in) in this output interval: snow water x ratio, ratio = 12 + (271.16 - Tmax) (x2 below 271.16 K), Tmax =
    warmest of 2 m / 925 / 850 / 700 / 500 mb. Snow water: ECMWF sf; NOAA precip where the categorical snow flag is set.
    (old site: Kuchera snow; Benjamin: Kuchera for the Cascade passes)"""
    if m not in ("hrrr", "rrfs", "gfs", "ifs"): raise KeyError("kinc")
    if m == "ifs": swe = _inc(R, m, "sf")
    else: swe = _inc(R, m, "tp") * (np.asarray(R._idx(M_NO("csnow"), R.url)[2], float) > 0.5)
    tm = _tmax_col(R, m); d = 271.16 - tm
    ratio = np.clip(np.where(d > 0, 12 + 2 * d, 12 + d), 0, 40)
    return swe * ratio
def _fzinc(R, m):
    """Freezing rain (in of water) in this output interval: precip where the type is freezing rain / drizzle."""
    if m not in ("hrrr", "rrfs", "gfs", "ifs"): raise KeyError("fzinc")
    if m in NOAA: fz = np.asarray(R._idx(M_NO("cfrzr"), R.url)[2], float) > 0.5
    else: fz = np.isin(np.rint(np.asarray(R.f("ptype")[2], float)), (3, 12))
    return _inc(R, m, "tp") * fz
WAVE_URL = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p25/wave/{d}{h:02d}0000-{s}h-wave-fc"
def _wave(R, m):
    """ECMWF IFS wave model (WAM, open data 0.25 deg; the old site's 0.1 deg wave files are no longer published): significant wave
    height (ft), mean wave direction as a unit vector pointing where the waves travel, mean period (s). Land = swh -0.5 (drawn as land)."""
    if m != "ifs": raise KeyError("wave")
    if "_wave" in R.cache: return R.cache["_wave"]
    import temp_maps as TM, eccodes as ec
    base = WAVE_URL.format(d=f"{R.c:%Y%m%d}", h=R.c.hour, s=R.s)
    try: idx = [json.loads(l) for l in TM.get(base + ".index").decode().splitlines()]
    except Exception as e:
        if "404" in str(e): raise KeyError("wave")
        raise
    out = {}
    for par in ("swh", "mwd", "mwp"):
        r = next((x for x in idx if x["param"] == par), None)
        if r is None: raise KeyError("wave")
        g = ec.codes_new_from_message(TM.get(base + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1)))
        ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj"); lo0 = ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
        d = ec.codes_get(g, "iDirectionIncrementInDegrees"); mv = ec.codes_get(g, "missingValue")
        v = ec.codes_get_values(g).reshape(nj, ni).astype(float); ec.codes_release(g)
        v[v == mv] = np.nan; lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180; out[par] = v[:, np.argsort(lon)]
    sea = np.isfinite(out["swh"]); th = np.radians(np.nan_to_num(out["mwd"]))   # mwd = direction waves come FROM (deg, meteorological)
    R.cache["_wave"] = r = dict(swh=np.where(sea, out["swh"] * 3.28084, -0.5), wdu=np.where(sea, -np.sin(th), 0.0), wdv=np.where(sea, -np.cos(th), 0.0),
                                mwp=np.where(sea, np.nan_to_num(out["mwp"]), 0.0))
    return r
IVT_P = (1000, 925, 850, 700, 600, 500, 400, 300)
def _ivt(R, m):
    """Integrated vapor transport (kg/m/s), east and north parts: (1/g) * integral of q*V dp, 1000-300 mb, trapezoid over the
    standard levels; levels below ground (surface pressure) dropped. Same formula as the old site's IVT map (ifs, aifs; + gfs)."""
    if m not in ("ifs", "aifs", "gfs"): raise KeyError("ivt")
    if "_ivt" in R.cache: return R.cache["_ivt"]
    try: sp = np.asarray(R.f("sp")[2], float)
    except KeyError: sp = None
    qu, qv = [], []
    for lev in IVT_P:
        q = np.asarray(R.f(f"Q:{lev}")[2], float); u = np.asarray(R.f(f"U:{lev}")[2], float); v = np.asarray(R.f(f"V:{lev}")[2], float)
        ok = 1.0 if sp is None else (sp >= lev * 100.0)
        qu.append(q * u * ok); qv.append(q * v * ok)
    P = np.array(IVT_P, float) * 100.0
    iu = sum((qu[k] + qu[k + 1]) / 2 * (P[k] - P[k + 1]) for k in range(len(P) - 1)) / 9.80665
    iv = sum((qv[k] + qv[k + 1]) / 2 * (P[k] - P[k + 1]) for k in range(len(P) - 1)) / 9.80665
    R.cache["_ivt"] = r = (iu, iv); return r
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

PRT_EDGES = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.4)   # in/h rate bins 1..8 (bin 8 = 0.4+)
def _prt(R, m):
    """Precip type + rate in one categorical byte: 0 = none, type * 16 + rate bin (1-8); types 0 rain, 1 snow, 2 sleet / mix,
    3 freezing rain. ECMWF: ptype + tprate. NOAA: categorical CRAIN/CSNOW/CICEP/CFRZR + PRATE. (old site: MSLP + precip type)"""
    if m in ("aifs", "nbm", "eps", "aens"): raise KeyError("prt")
    rate = np.asarray(R.f("prate")[2], float) * 3600 / 25.4   # kg m-2 s-1 -> in/h
    if m in NOAA:
        g = lambda k: np.asarray(R._idx(M_NO(k), R.url)[2], float) > 0.5
        typ = np.where(g("cfrzr"), 3, np.where(g("cicep"), 2, np.where(g("csnow"), 1, 0)))
    else:   # ECMWF ptype: 1 rain, 3 freezing rain, 5 snow, 6 wet snow, 7 rain/snow mix, 8 ice pellets, 12 freezing drizzle
        p = np.rint(np.asarray(R.f("ptype")[2], float))
        typ = np.select([np.isin(p, (3, 12)), np.isin(p, (7, 8)), np.isin(p, (5, 6))], [3, 2, 1], 0)
    b = np.digitize(rate, PRT_EDGES) + 1
    return np.where(rate >= PRT_EDGES[0], typ * 16 + b, 0).astype(float)
def M_NO(k):
    import menu_maps as M
    return M.NO[k]

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
    # 10-30 parity with the old site (global models first): levels, dewpoint, PW, precip type, 1000 mb height (thickness)
    "u850": (_f("U:850", lambda v: v * 1.94384), "kt"), "v850": (_f("V:850", lambda v: v * 1.94384), "kt"),
    "u925": (_f("U:925", lambda v: v * 1.94384), "kt"), "v925": (_f("V:925", lambda v: v * 1.94384), "kt"), "t925": (_f("T:925", lambda k: k - 273.15), "C"),
    "u700": (_f("U:700", lambda v: v * 1.94384), "kt"), "v700": (_f("V:700", lambda v: v * 1.94384), "kt"), "t500": (_f("T:500", lambda k: k - 273.15), "C"),
    "u300": (_f("U:300", lambda v: v * 1.94384), "kt"), "v300": (_f("V:300", lambda v: v * 1.94384), "kt"), "t300": (_f("T:300", lambda k: k - 273.15), "C"),
    "z1000": (_f("Z:1000", lambda z: z), "m"),
    "d2m": (_f("td2m", lambda k: (k - 273.15) * 1.8 + 32), "F"),
    "pw": (_f("pwat", lambda v: v / 25.4), "in"),
    "prt": (_prt, "code"),
    "kinc": (_kinc, "in"), "fzinc": (_fzinc, "in"),
    "swh": (lambda R, m: _wave(R, m)["swh"], "ft"), "wdu": (lambda R, m: _wave(R, m)["wdu"], "1"), "wdv": (lambda R, m: _wave(R, m)["wdv"], "1"),
    "ivtu": (lambda R, m: _ivt(R, m)[0], "kg/m/s"), "ivtv": (lambda R, m: _ivt(R, m)[1], "kg/m/s"),
    # ECMWF ENS (model "eps" only)
    "t2sd": (_ens("t2sd"), "F"), "p32": (_ens("p32"), "%"), "z5sd": (_ens("z5sd"), "m"),
}
# ensemble-only fields (stage 4 extras): means reuse the deterministic names so the shared products / meteograms work
ENS_FIELDS = {"apcp": (_ensc("tp"), "in"), "apcp90": (_ensc("tp90"), "in"), "asnow": (_ensc("sf"), "in"), "asnow90": (_ensc("sf90"), "in"),
              "gust": (_ensc("10fg"), "mph"), "gust90": (_ensc("10fg90"), "mph"), "mslp": (_ensc("msl"), "mb"), "t850": (_ensc("t850"), "C"),
              "mucape": (_ensc("mucape"), "J/kg"), "pcape": (_ensc("mucapep"), "%"), "lowp": (_ensc("lowp"), "%"),
              "maxt": (_ensc("mx2t"), "F"), "mint": (_ensc("mn2t"), "F")}
# Packing (R2 write budget): fields used together share one RGB PNG (one channel each). A field not in a pack is its own
# grayscale PNG. run.json "packs" maps field -> [file name, channel]; the viewer reads either layout.
PACKS = {"wind": ("mslp", "u10", "v10"), "aloft": ("t850", "t700", "frz"), "accum": ("apcp", "asnow", "ltgp"),
         "conv": ("mucape", "sbcape", "ltng"), "sky": ("tcc", "vis", "ir"), "w500": ("u500", "v500", "z500"), "w250": ("u250", "v250", "z250"),
         "e2t": ("t2m", "t2sd", "p32"), "e500": ("z500", "z5sd"), "eqp": ("apcp", "apcp90", "asnow"), "eqs": ("asnow90", "gust", "gust90"),
         "emsl": ("mslp", "t850", "lowp"), "ecape": ("mucape", "pcape"),
         "w850": ("u850", "v850", "t925"), "w925": ("u925", "v925", "z1000"), "w700": ("u700", "v700", "t500"), "w300": ("u300", "v300", "t300"),
         "etx": ("maxt", "mint"), "moist": ("d2m", "pw", "prt"), "kfz": ("kinc", "fzinc"), "ivt": ("ivtu", "ivtv"), "wave": ("swh", "wdu", "wdv"),
         "nbm1": ("t2m", "gust", "tcc"), "nbm2": ("nq1", "nq6", "ns6"), "nbm3": ("tstm", "maxt", "mint")}

SQRT_FIELDS = {"apcp", "asnow", "apcp90", "asnow90", "nq1", "nq6", "ns6", "ltgp", "kinc", "fzinc"}
def q8(a, lo, hi): return np.clip(np.rint((a - lo) / (hi - lo) * 255), 0, 255).astype(np.uint8)
def rng(a):
    lo, hi = float(np.floor(np.nanmin(a))), float(np.ceil(np.nanmax(a))); return lo, max(hi, lo + 1)

def roll_ll(v):   # 0.25 deg global: lon -180..179.75 -> 0..359.75
    return np.roll(v, -720, axis=1) if v.shape[1] == 1440 else v

PT_FIELDS = ("t2m", "d2m", "pw", "kinc", "fzinc", "gust", "u10", "v10", "mslp", "apcp", "asnow", "tcc", "frz", "dsnod", "refc", "t850", "mucape",
             "nq1", "nq6", "ns6", "tstm", "maxt", "mint", "t2sd", "p32")
def town_points(man, m):
    """Every town / pass slot of the model's views (deduped by name, A-Z): meteogram and Pass Forecaster sample points."""
    pts = {}
    for vid, V in man["models"][m]["views"].items():
        for t in V.get("towns", []):
            if t["name"] not in pts: pts[t["name"]] = dict(n=t["name"], k=t["kind"], fi=t["fi"], fj=t["fj"], **({"c": round(t["t2m_corr"], 2)} if "t2m_corr" in t else {}))
    return sorted(pts.values(), key=lambda p: (p["n"].lower()))
def sample_pts(a, P):
    """Bilinear sample of a cropped grid at fractional (fi, fj) points (nearest grid point already applied for 3 km grids)."""
    fi = np.clip(np.array([p["fi"] for p in P], float), 0, a.shape[0] - 1.001); fj = np.clip(np.array([p["fj"] for p in P], float), 0, a.shape[1] - 1.001)
    i, j = np.floor(fi).astype(int), np.floor(fj).astype(int); di, dj = fi - i, fj - j
    v = a[i, j] * (1 - di) * (1 - dj) + a[i + 1, j] * di * (1 - dj) + a[i, j + 1] * (1 - di) * dj + a[i + 1, j + 1] * di * dj
    return [None if not np.isfinite(x) else round(float(x), 2) for x in v]

def step_job(args):
    m, c_str, s, crop, out, P = args if len(args) == 6 else (*args, None)
    ptv = {}
    import menu_maps as M
    from PIL import Image
    c = dt.datetime.strptime(c_str, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
    i0, i1, j0, j1 = crop; t = time.time(); ranges, sizes, q = {}, {}, {}
    _patch_models(M)
    try: R = EpsReader(c, s, m, crop) if m in ("eps", "aens") else NbmReader(c, s) if m == "nbm" else M.Reader(m, c, s)
    except Exception as e: return s, None, str(e), 0, 0
    for name, (get, units) in (NBM_FIELDS if m == "nbm" else dict(FIELDS, **ENS_FIELDS) if m in ("eps", "aens") else FIELDS).items():
        try: a = get(R, m)
        except (KeyError, StopIteration): continue
        except Exception as e:
            if name == "t2m" or "404" in str(e): return s, None, f"{name}: {e}", 0, time.time() - t   # step (or its prs file) not out yet: retry next pass
            print(f"{m} f{s:03d} {name}: {str(e)[:120]}", flush=True); continue
        if isinstance(a, Cropped): a = np.asarray(a, float)
        else:
            if MODELS[m]["grid"] == "ll": a = roll_ll(a)
            a = a[i0:i1, j0:j1]
        if not np.isfinite(a).any(): continue
        if name == "ir":
            from scipy.ndimage import gaussian_filter
            bad = ~np.isfinite(a)
            if bad.any():
                w = gaussian_filter((~bad).astype(float), 1.5); a = np.where(bad, gaussian_filter(np.where(bad, 0, a), 1.5) / np.maximum(w, 1e-6), a)
        if P and name in PT_FIELDS: ptv[name] = sample_pts(a, P)
        a = np.where(np.isfinite(a), a, np.nanmin(a))
        if name == "prt": ranges[name] = [0.0, 255.0]; q[name] = np.clip(a, 0, 255).astype(np.uint8); continue
        if name in SQRT_FIELDS:   # precip totals: square-root steps (fine for light amounts); viewer decodes lo + (q/255)^2 (hi - lo)
            lo_, hi_ = rng(a); ranges[name] = [lo_, hi_, 2]; q[name] = q8(np.sqrt(np.clip((a - lo_) / (hi_ - lo_), 0, 1)), 0, 1); continue
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
    if getattr(R, "lows", None) is not None or getattr(R, "spag", None):   # ensemble member low centres + 500 mb member lines
        p = f"{out}/single/ens_f{s:03d}.json"; json.dump(dict(n=R.n, lows=getattr(R, "lows", []), spag=getattr(R, "spag", {})), open(p, "w"), separators=(",", ":"))
        sizes["ens"] = os.path.getsize(p)
    if ptv:   # town / pass values for meteograms (one small JSON per step, order = run.json "points")
        p = f"{out}/single/pts_f{s:03d}.json"; json.dump(ptv, open(p, "w"), separators=(",", ":")); sizes["pts"] = os.path.getsize(p)
    return s, sizes, ranges, getattr(R, "bytes", 0), time.time() - t

# ------------------------------------------------------------------------------------------------ climatology
CLIM_NPZ = {"z500": ("ncep_hgt500_mon_ltm_1991_2020.npz", "hgt"), "t850": ("ncep_t850_mon_ltm_1991_2020.npz", "t850"),
            "t2m": ("ncep_t2m_6h_ltm_1991_2020.npz", "t2m"), "pr": ("precip_mon_ltm_1991_2020.npz", "pr"),
            "pw": ("ncep_pw_mon_ltm_1991_2020.npz", "pw")}
CLIM_UNITS = {"z500": "m", "t850": "C", "t2m": "F", "pr": "mm/day", "pw": "in"}
CLIM_SOURCE = {"pr": "PRISM 1991-2020 normals (US, 4 km) + CPC Global Unified Gauge 1991-2020 (land, 0.5 deg) + GPCP v2.3 1991-2020 (ocean, 2.5 deg); "
                     "built by clim/src/build_precip_clim.py"}
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
    if not wrap:   # regional source (precip): hold edge values outside it instead of extrapolating
        pts[..., 0] = np.clip(pts[..., 0], cl.min(), cl.max()); pts[..., 1] = np.clip(pts[..., 1], co.min(), co.max())
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
    elif var == "pw":   # moved to model terrain with a 2.3 km water-vapor scale height (as the old site's PW anomaly)
        zf = 1.0 if oro_m is None else np.exp(-(oro_m - it(z["zs"])) / 2300.0)
        slots = [it(h[k]) * zf for k in range(12)]
    else: slots = [it(h[k]) for k in range(12)]
    files, ranges = [], []
    for k, a in enumerate(slots):
        lo, hi = float(np.floor(a.min())), float(np.ceil(a.max())); hi = max(hi, lo + 1)
        q = np.clip(np.rint((a - lo) / (hi - lo) * 65535), 0, 65535).astype(np.uint32)
        rgb = np.zeros(a.shape + (3,), np.uint8); rgb[..., 0] = q >> 8; rgb[..., 1] = q & 255
        f_ = f"static/clim_{var}_{m}_{k:02d}.png"; Image.fromarray(rgb, "RGB").save(f"{out}/{f_}", optimize=True)
        files.append(f_); ranges.append([lo, hi])
    d = dict(files=files, ranges=ranges, units=CLIM_UNITS[var], source=CLIM_SOURCE.get(var, "NCEP/NCAR Reanalysis 1 1991-2020 (NOAA PSL)"))
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
    # Old-site parity (10-30-26): Southern BC + Lower Mainland (old "BC rain" tab), NE WA mountains (old snow tab)
    lcb = lambda lon, lat: ccrs.LambertConformal(central_longitude=lon, central_latitude=lat, standard_parallels=(lat - 2, lat + 2))
    TM.VIEWS.setdefault("bc", dict(label="Southern BC", size=(16, 15), proj=lcb(-123.4, 49.7), ll=(-126.25, -120.5, 47.95, 51.45), box=(-128.0, -118.8, 47.0, 52.4)))
    TM.VIEWS.setdefault("lm", dict(label="Lower Mainland", size=(16, 9.5), proj=lcb(-122.35, 49.2), ll=(-123.45, -121.25, 48.86, 49.6), box=(-124.3, -120.4, 48.5, 49.95)))
    TM.VIEWS.setdefault("newa", dict(label="NE WA mountains", size=(16, 11.5), proj=lcb(-118.55, 48.3), ll=(-120.15, -116.95, 47.6, 49.0), box=(-121.0, -116.1, 47.2, 49.4)))
    TM.VIEWS.setdefault("passes", dict(label="Cascade Passes", size=(16, 15), proj=lcc(-121.2), ll=(-123.9, -118.5, 46.2, 49.05), box=(-125, -117.5, 45.4, 49.8)))
WA_LIKE = ("wa", "wwa", "ewa", "passes", "puget", "bc", "lm", "newa")
# Southern BC / Lower Mainland towns (old site's precip_map.py BC lists, lat-lon order), placed ahead of the WA towns
_BC = [("Vancouver", 49.2827, -123.1207), ("Victoria", 48.4284, -123.3656), ("Abbotsford", 49.0504, -122.3045), ("Nanaimo", 49.1659, -123.9401),
       ("Chilliwack", 49.1579, -121.9515), ("Hope", 49.383, -121.442), ("Squamish", 49.7016, -123.1558), ("Whistler", 50.1163, -122.9574),
       ("Pemberton", 50.3192, -122.8027), ("Port Alberni", 49.2339, -124.8055), ("Courtenay", 49.6866, -124.9936), ("Campbell River", 50.0244, -125.2475),
       ("Powell River", 49.8352, -124.5247), ("Sechelt", 49.4741, -123.7545), ("Duncan", 48.7787, -123.7079), ("Tofino", 49.153, -125.9066),
       ("Ucluelet", 48.942, -125.5466), ("Lillooet", 50.6864, -121.9364), ("Merritt", 50.1113, -120.7862), ("Lytton", 50.2316, -121.5824),
       ("Boston Bar", 49.8655, -121.444), ("Princeton", 49.459, -120.5062), ("Manning Park", 49.065, -120.785), ("Parksville", 49.319, -124.312),
       ("Port Renfrew", 48.555, -124.421), ("Gold River", 49.777, -126.051), ("Sooke", 48.374, -123.7262), ("Gold Bridge", 50.853, -122.838)]
_LM = [("Vancouver", 49.2827, -123.1207), ("Surrey", 49.1913, -122.849), ("Burnaby", 49.2488, -122.9805), ("Richmond", 49.1666, -123.1336),
       ("Abbotsford", 49.0504, -122.3045), ("Coquitlam", 49.2838, -122.7932), ("Chilliwack", 49.1579, -121.9515), ("North Vancouver", 49.32, -123.0724),
       ("New Westminster", 49.2057, -122.911), ("Delta (Ladner)", 49.0897, -123.082), ("Tsawwassen", 49.017, -123.083), ("White Rock", 49.0253, -122.8026),
       ("Langley", 49.1044, -122.66), ("Port Moody", 49.283, -122.8317), ("Maple Ridge", 49.2193, -122.6019), ("Mission", 49.133, -122.3089),
       ("Harrison Hot Springs", 49.3, -121.785), ("Agassiz", 49.238, -121.769), ("Hope", 49.383, -121.442), ("Squamish", 49.7016, -123.1558),
       ("Gibsons", 49.4, -123.505), ("Bellingham", 48.75, -122.48), ("Lynden", 48.946, -122.452), ("Point Roberts", 48.985, -123.068)]
BC_PASSES_FAST = {"Coquihalla Summit": ("Coquihalla", 49.594, -121.095, 4081), "Allison Pass": ("Allison", 49.124, -120.855, 4403),
                  "Duffey Lake Summit": ("Duffey", 50.37, -122.49, 4199)}
TOWN_SETS = {"bc": [(n, a, o, "r") for n, a, o in _BC], "lm": [(n, a, o, "r") for n, a, o in _LM],
             "newa": [("Colville", 48.546, -117.905, "r"), ("Chewelah", 48.276, -117.715, "r"), ("Metaline Falls", 48.862, -117.366, "r"),
                      ("Ione", 48.742, -117.418, "r"), ("Northport", 48.917, -117.781, "r"), ("Omak", 48.411, -119.528, "r"),
                      ("Okanogan", 48.361, -119.583, "l"), ("Oroville", 48.939, -119.435, "r"), ("Twisp", 48.364, -120.122, "r"),
                      ("Inchelium", 48.296, -118.199, "r"), ("Springdale", 48.058, -117.742, "r"), ("Usk", 48.311, -117.284, "r"),
                      ("Coulee Dam", 47.965, -118.976, "r"), ("Nespelem", 48.167, -118.973, "r"), ("Spokane", 47.66, -117.43, "r")]}
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
    if m == "nbm":
        c = latest_published(m)
        for _ in range(6):
            try: la, lo, _v = NbmReader(c, 1).get("TMP:2 m above ground", "1 hour fcst", latlon=True); return la, lo, None
            except Exception: c -= dt.timedelta(hours=6)
        raise RuntimeError("no NBM run found")
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
        rad = MD.get("radius", 6371229.0)
        hp = ccrs.LambertConformal(globe=ccrs.Globe(ellipse="sphere", semimajor_axis=rad, semiminor_axis=rad), **MD.get("lcc", HRRR_LCC))
        g = hp.transform_points(pc, lo, la); gx0, gy0 = g[0, 0, 0], g[0, 0, 1]
        d = 3000.0 if "lcc" not in MD else float(np.hypot(g[0, 1, 0] - gx0, g[0, 1, 1] - gy0))   # grid spacing (NBM 2539.7 m)
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
            first = TOWN_SETS.get(vid, []); names = {t[0] for t in first}
            TM.WA_TOWNS = [t for t in first + [t for t in keepT if t[0] not in names] + EXTRA_TOWNS.get(vid, []) if ins(t[1], t[2])]
            TM.WA_PASSES = {k: v for k, v in {**keepP, **(BC_PASSES_FAST if vid in ("bc", "lm") else {})}.items() if ins(v[1], v[2])}
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
    PA_L = [-4, -3, -2, -1.5, -1, -0.5, -0.25, -0.1, 0.1, 0.25, 0.5, 1, 1.5, 2, 3, 4]
    PA_C = ["#543005", "#7f4a10", "#a6611a", "#c58a3c", "#dfc27d", "#ecdcb6", "#f6efe0", "#f5f5f5", "#e3f2e1", "#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#005a32"]
    PP_L = [0, 10, 25, 50, 75, 90, 110, 125, 150, 200, 300, 400]
    PP_C = ["#7f4a10", "#a6611a", "#c58a3c", "#dfc27d", "#f1e3c0", "#f5f5f5", "#c7e9c0", "#a1d99b", "#41ab5d", "#1f78b4", "#3a4fb0"]
    CM.update(qpfa=HS.cmap(PA_C, "#3d2004", "#00391f"), qpfpct=HS.cmap(PP_C, PP_C[0], "#5b2a9c"))
    FZ_L = [0.01, 0.05, 0.1, 0.15, 0.25, 0.35, 0.5, 0.75, 1.0, 1.5]
    CM.update(kuchera=CM["snow"], kuch24=CM["snow"], fzra=M.ramp(FZ_L, [(0.01, "#f3e6fb"), (0.1, "#c49de3"), (0.25, "#8e59c8"), (0.5, "#c51b7d"), (1.0, "#6d0f46"), (1.5, "#2b0f1f")]))
    T5_L = list(range(-50, 1, 1)); T3_L = list(range(-70, -19, 1)); W8_L = list(range(10, 91, 5)); TH_L = list(range(498, 601, 3)); SLP_L = list(range(960, 1051, 2))
    PW_L = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5]; PWA_L = [-1.2, -1, -0.8, -0.6, -0.4, -0.2, -0.1, 0.1, 0.2, 0.4, 0.6, 0.8, 1, 1.2]
    PT_L = []; PT_C = []
    PT_ANCH = [["#c7e9c0", "#a1d99b", "#74c476", "#41ab5d", "#238b45", "#f2e34b", "#f4a43a", "#e2462f"],     # rain
               ["#deebf7", "#c6dbef", "#9ecae1", "#6baed6", "#4292c6", "#2171b5", "#08519c", "#08306b"],     # snow
               ["#fde0ef", "#fbb4d9", "#f78ac4", "#f064b0", "#de3a9a", "#c51b7d", "#9b1563", "#6d0f46"],     # sleet / mix
               ["#efe1f6", "#dcc0ee", "#c49de3", "#a97bd6", "#8e59c8", "#7438b5", "#5a1f9a", "#3f0d73"]]     # freezing rain
    for t_ in range(4):
        for b_ in range(8): PT_L.append(t_ * 16 + b_ + 0.5); PT_C.append(PT_ANCH[t_][b_])
        if t_ < 3: PT_L.append(t_ * 16 + 8.5); PT_C.append("#f4f5f7")
    PT_L.append(3 * 16 + 8.5)
    PT_L = sorted(set(PT_L)); PT_C = PT_C[:len(PT_L) - 1]
    CM.update(t500w=M.ramp(T5_L, [(-50, "#2b0f52"), (-40, "#3b4cc0"), (-30, "#6baed6"), (-20, "#c6dbef"), (-12, "#fdd49e"), (-5, "#fc8d59"), (0, "#b30000")]),
              t300w=M.ramp(T3_L, [(-70, "#2b0f52"), (-60, "#3b4cc0"), (-50, "#6baed6"), (-42, "#c6dbef"), (-35, "#fdd49e"), (-28, "#fc8d59"), (-20, "#b30000")]),
              w850=M.ramp(W8_L, [(10, "#e8f1fb"), (25, "#8fbfe8"), (40, "#3b82d1"), (55, "#f2e34b"), (70, "#e2462f"), (90, "#8c1450")]),
              thick=M.ramp(TH_L, [(498, "#2b0f52"), (516, "#3b4cc0"), (528, "#6baed6"), (540, "#e8f1fb"), (552, "#fdd49e"), (570, "#fc8d59"), (600, "#b30000")]),
              slp=M.ramp(SLP_L, [(960, "#5b2a9c"), (980, "#3b82d1"), (1000, "#c6dbef"), (1012, "#f4f5f7"), (1024, "#fdd49e"), (1036, "#fc8d59"), (1050, "#b30000")]),
              pw=M.ramp(PW_L, [(0.1, "#f6efe0"), (0.4, "#c7e9c0"), (0.75, "#41ab5d"), (1.0, "#2171b5"), (1.5, "#7438b5"), (2.5, "#c51b7d")]),
              pwa=HS.cmap(["#7f4a10", "#a6611a", "#c58a3c", "#dfc27d", "#ecdcb6", "#f6efe0", "#f5f5f5", "#e3f2e1", "#c7e9c0", "#74c476", "#238b45", "#2171b5", "#3a4fb0"],
                          "#543005", "#5b2a9c"),
              ptype=HS.cmap(PT_C, PT_C[0], PT_C[-1]))
    IVT_L = [100, 150, 250, 300, 400, 500, 600, 700, 800, 1000, 1200, 1500]
    CM["ivt"] = M.ramp(IVT_L, [(100, "#e4e6ea"), (250, "#f7e28a"), (400, "#f3a64c"), (600, "#e0503a"), (800, "#b0245c"), (1200, "#6a2a8f"), (1500, "#c9a7e6")])
    WV_L = [0, 1, 2, 3, 4, 5, 6, 8, 10, 12, 14, 16, 18, 20, 24, 28, 32, 40]
    CM["waves"] = M.ramp(WV_L, [(0, "#283c96"), (2, "#2878c8"), (4, "#28afd2"), (6, "#32be8c"), (8, "#6ec846"), (10, "#c8dc3c"), (14, "#f0b432"),
                                (20, "#e6642d"), (28, "#c82846"), (40, "#8c1e78")])
    CM["wavemax"] = CM["waves"]
    FOG_L = list(range(20, 101, 10))
    CM["fog"] = M.ramp(FOG_L, [(20, "#e6e8eb"), (40, "#b9c4cf"), (60, "#7f95ab"), (80, "#4f6a8a"), (100, "#2c3f5f")])
    CM.update(d2m=CM["t2m"], feels=CM["t2m"], gustmax=CM["gust10"], t925w=CM["t850"], t850w=CM["t850"], t700w=CM["t700"])
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
                         towns="names", clim="z500", only=("gfs", "ifs", "aifs", "eps", "aens")),
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
        # 10-30 (Benjamin 1:05 PM): precipitation anomaly vs 1991-2020 normals for the same days (see CLIM_SOURCE["pr"])
        "qpfa": dict(title="Precipitation Anomaly", fields=["apcp"], fill="panom", anom="pr", clim="pr", key="Departure from normal (in)",
                     ticks=[-3, -2, -1, -0.5, -0.25, 0.25, 0.5, 1, 2, 3], tickfmt=True, **table(PA_L, CM["qpfa"], "both"),
                     extra="precip since the run started minus the 1991-2020 normal for those days  \u00b7  {lo} to {hi} in in view",
                     pct=[0.5, 99.5], dec=2, fmt="in2", towns="names", only=("hrrr", "rrfs", "gfs", "ifs", "aifs", "eps", "aens")),
        "qpfpct": dict(title="Precipitation, Percent of Normal", fields=["apcp"], fill="ppct", anom="pr", clim="pr", key="Percent of normal (%)",
                       ticks=[0, 25, 50, 75, 100, 150, 200, 300, 400], tickfmt=True, **table(PP_L, CM["qpfpct"], "max"),
                       extra="precip since the run started as a share of the 1991-2020 normal for those days (from 48 h on; normal floored at 0.05 in)  \u00b7  up to {hi}% in view",
                       pct=[0.5, 99.5], towns="names", only=("hrrr", "rrfs", "gfs", "ifs", "aifs", "eps", "aens")),
        "kuchera": dict(title="Snowfall Total (Kuchera)", fields=["kinc"], window=9999, sofar=True, wsum=True, wfield="kinc", fill="window", key="Snow (in)",
                        ticks=[0.1, 1, 3, 6, 10, 15, 24, 36, 48], tickfmt=True, **table(M.SNOW_LEVELS, CM["snow"], "max"),
                        extra="snow water x Kuchera ratio (warmest of 2 m to 500 mb)  \u00b7  since the run started  \u00b7  max {hi} in in view",
                        pct=[0, 100], dec=1, fmt="in1", only=("hrrr", "rrfs", "gfs", "ifs")),
        "kuch24": dict(title="24 h Snowfall (Kuchera)", fields=["kinc"], window=24, wsum=True, wfield="kinc", fill="window", key="Snow (in)",
                       ticks=[0.1, 1, 3, 6, 10, 15, 24], tickfmt=True, **table(M.SNOW_LEVELS, CM["snow"], "max"),
                       extra="Kuchera snow in the 24 h ending at the valid time  \u00b7  max {hi} in in view", pct=[0, 100], dec=1, fmt="in1",
                       only=("hrrr", "rrfs", "gfs", "ifs")),
        "fzra": dict(title="Freezing Rain Total", fields=["fzinc"], window=9999, sofar=True, wsum=True, wfield="fzinc", fill="window", key="Ice (in, liquid)",
                     ticks=[0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 1], tickfmt=True, **table(FZ_L, CM["fzra"], "max"),
                     extra="precip that fell as freezing rain / drizzle since the run started (liquid amount)  \u00b7  max {hi} in in view",
                     pct=[0, 100], dec=2, fmt="in2", only=("hrrr", "rrfs", "gfs", "ifs")),
        # 10-30 parity with the old site's model menus (global models; HRRR/RRFS get them too where the fields exist)
        "ivt": dict(title="Integrated Vapor Transport (IVT)", fields=["ivtu", "ivtv"], fill="wspd", wind=["ivtu", "ivtv"], spd_mult=1.0, spd_sigma=1.0, key="IVT (kg/m/s)",
                    ticks=[150, 250, 400, 600, 800, 1000, 1200], tickfmt=True, **table(IVT_L, CM["ivt"], "max"),
                    barbs=dict(u="ivtu", v="ivtv", color="#1b1d22", length=HS.BARB_LENGTH, lw=1.0, arrows=True, min=250, ref=1000),
                    extra="water vapor carried by the wind, 1000-300 mb  ·  arrows where IVT is 250 or more  ·  up to {hi} in view", pct=[1, 99.9],
                    towns="none", only=("gfs", "ifs", "aifs")),
        "waves": dict(title="Significant Wave Height", fields=["swh", "wdu", "wdv"], key="Wave height (ft)", ticks=[0, 2, 4, 6, 8, 10, 14, 20, 28, 40],
                      tickfmt=True, **table(WV_L, CM["waves"], "max"),
                      barbs=dict(u="wdu", v="wdv", color="#1b1d22", length=HS.BARB_LENGTH, lw=1.0, arrows=True, min=0.5, ref=1, fixed=True),
                      extra="ECMWF wave model (WAM 0.25\u00b0)  \u00b7  arrows = mean wave direction  \u00b7  up to {hi} ft in view", pct=[0, 99.9],
                      only=("ifs",)),
        "wavemax": dict(title="Estimated Max Wave Height", fields=["swh"], fill="hmax", key="Max wave (ft)", ticks=[0, 4, 8, 14, 20, 28, 40], tickfmt=True,
                        **table(WV_L, CM["wavemax"], "max"), extra="1.86 x significant height (largest of ~1000 waves, Rayleigh; as the old site)"
                        "  \u00b7  up to {hi} ft in view", pct=[0, 99.9], only=("ifs",)),
        "fog": dict(title="Fog Risk Index", fields=["t2m", "d2m", "u10", "v10"], fill="fog", key="Fog risk", ticks=[20, 40, 60, 80, 100], tickfmt=True,
                    **table(FOG_L, CM["fog"], "neither"), extra="our index: dewpoint spread + light wind (+ model visibility on HRRR/RRFS), damped in rain"
                    "  ·  not a model fog forecast", pct=[0, 100], only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "d2m": dict(title="2 m Dewpoint", fields=["d2m"], key="Dewpoint (\u00b0F)", ticks=HS.TEMP_TICKS, **table(HS.TEMP_LEVELS, CM["t2m"], "both"),
                    extra="{lo} to {hi}\u00b0F in view", pct=[0.5, 99.5], only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "feels": dict(title="Feels-Like Temperature", fields=["t2m", "d2m", "u10", "v10"], fill="feels", key="Feels like (\u00b0F)", ticks=HS.TEMP_TICKS,
                      **table(HS.TEMP_LEVELS, CM["t2m"], "both"), freeze=32,
                      extra="wind chill at 50\u00b0F and below, heat index at 80\u00b0F and above (NWS formulas)  \u00b7  {lo} to {hi}\u00b0F in view", pct=[0.5, 99.5],
                      only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "gustmax": dict(title="Peak Wind Gust So Far", fields=["gust"], window=9999, sofar=True, wmax=True, wfield="gust", fill="window", key="Gust (mph)",
                        ticks=HS.WIND_TICKS, **table(HS.WIND_LEVELS, CM["gust10"], "max"),
                        extra="highest gust at any hour since the run started  \u00b7  up to {hi} mph in view", pct=[1, 99.9], only=("hrrr", "rrfs", "gfs", "ifs")),
        "t925w": dict(title="925 mb Temperature + Wind", fields=["t925", "u925", "v925"], fill="t925", key="925 mb temp (\u00b0C)", ticks=HS.T850_TICKS, tickfmt=True,
                      **table(HS.T850_LEVELS, CM["t850"], "both"), freeze=0, barbs=dict(u="u925", v="v925", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                      extra="0\u00b0C line dashed  \u00b7  barbs in kt  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "t850w": dict(title="850 mb Temperature + Wind", fields=["t850", "u850", "v850"], fill="t850", key="850 mb temp (\u00b0C)", ticks=HS.T850_TICKS, tickfmt=True,
                      **table(HS.T850_LEVELS, CM["t850"], "both"), freeze=0, barbs=dict(u="u850", v="v850", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                      extra="0\u00b0C line dashed  \u00b7  barbs in kt  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "t700w": dict(title="700 mb Temperature + Wind", fields=["t700", "u700", "v700"], fill="t700", key="700 mb temp (\u00b0C)", ticks=HS.T850_TICKS, tickfmt=True,
                      **table(HS.T850_LEVELS, CM["t700"], "both"), freeze=0, barbs=dict(u="u700", v="v700", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                      extra="0\u00b0C line dashed  \u00b7  barbs in kt  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "t500w": dict(title="500 mb Temperature + Wind", fields=["t500", "u500", "v500"], fill="t500", key="500 mb temp (\u00b0C)", ticks=list(range(-50, 1, 5)), tickfmt=True,
                      **table(T5_L, CM["t500w"], "both"), barbs=dict(u="u500", v="v500", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                      extra="barbs in kt  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "t300w": dict(title="300 mb Temperature + Wind", fields=["t300", "u300", "v300"], fill="t300", key="300 mb temp (\u00b0C)", ticks=list(range(-70, -19, 5)), tickfmt=True,
                      **table(T3_L, CM["t300w"], "both"), barbs=dict(u="u300", v="v300", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                      extra="barbs in kt  \u00b7  {lo} to {hi}\u00b0C in view", pct=[0.5, 99.5], towns="none", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "w850": dict(title="850 mb Wind", fields=["u850", "v850"], fill="wspd", wind=["u850", "v850"], spd_mult=1.0, spd_sigma=1.0, key="Wind (kt)", ticks=[10, 20, 30, 40, 50, 60, 70, 80],
                     tickfmt=True, **table(W8_L, CM["w850"], "max"), barbs=dict(u="u850", v="v850", color=HS.BARB_COLOR, length=HS.BARB_LENGTH, lw=HS.BARB_LW),
                     extra="barbs in kt  \u00b7  up to {hi} kt in view", pct=[1, 99.9], towns="none", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "thick": dict(title="1000-500 mb Thickness + MSLP", fields=["z500", "z1000", "mslp"], fill="thick", key="Thickness (dam)", ticks=list(range(498, 601, 12)), tickfmt=True,
                      **table(TH_L, CM["thick"], "both"), freeze=540,
                      isobars=dict(field="mslp", every=4, sigma=6.0 if m == "hrrr" else 1.0, color=HS.ISOBAR_COLOR, lw=HS.ISOBAR_LW, halo=HS.ISOBAR_HALO),
                      extra="540 dam line dashed (rain/snow rule of thumb)  \u00b7  isobars every 4 mb  \u00b7  {lo} to {hi} dam in view", pct=[0.5, 99.5], towns="none",
                      only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "slp": dict(title="Sea-Level Pressure", fields=["mslp"], key="MSLP (mb)", ticks=list(range(960, 1051, 10)), tickfmt=True, **table(SLP_L, CM["slp"], "both"),
                    isobars=dict(field="mslp", every=4, sigma=6.0 if m == "hrrr" else 1.0, color=HS.ISOBAR_COLOR, lw=HS.ISOBAR_LW, halo=HS.ISOBAR_HALO), hl=True,
                    extra="isobars every 4 mb  \u00b7  H / L = high and low centers  \u00b7  {lo} to {hi} mb in view", pct=[0.5, 99.5], towns="none",
                    only=("hrrr", "rrfs", "gfs", "ifs", "aifs", "eps", "aens")),
        "pw": dict(title="Precipitable Water", fields=["pw"], key="PW (in)", ticks=[0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5], tickfmt=True, **table(PW_L, CM["pw"], "max"),
                   extra="water in the whole air column  \u00b7  up to {hi} in in view", pct=[0.5, 99.5], dec=2, fmt="in2", only=("hrrr", "rrfs", "gfs", "ifs", "aifs")),
        "pwa": dict(title="Precipitable Water Anomaly", fields=["pw"], fill="anom", anom="pw", clim="pw", key="Anomaly (in)", ticks=[-1, -0.75, -0.5, -0.25, 0, 0.25, 0.5, 0.75, 1],
                    tickfmt=True, **table(PWA_L, CM["pwa"], "both"),
                    extra="vs 1991-2020 NCEP/NCAR monthly normal moved to model terrain  \u00b7  {lo} to {hi} in in view", pct=[0.5, 99.5], dec=2,
                    only=("gfs", "ifs", "aifs")),
        "ptype": dict(title="MSLP + Precipitation Type", fields=["prt", "mslp"], fill="prt", key="Precip type (light to heavy)",
                      ticks=[4.5, 20.5, 36.5, 52.5], tickfmt=True, **table(PT_L, CM["ptype"], "neither"),
                      isobars=dict(field="mslp", every=4, sigma=6.0 if m == "hrrr" else 1.0, color=HS.ISOBAR_COLOR, lw=HS.ISOBAR_LW, halo=HS.ISOBAR_HALO),
                      extra="precip type and rate at the valid time  \u00b7  isobars every 4 mb", pct=[0, 100], towns="names", ticklabels=["Rain", "Snow", "Sleet / mix", "Freezing rain"],
                      only=("hrrr", "rrfs", "gfs", "ifs")),
    }
    ALLP = {k: dict(v) for k, v in prods.items()}   # before the per-model filter (ensemble picks shared products below)
    for v in ALLP.values(): v.pop("only", None)
    prods = {k: v for k, v in prods.items() if m in v.pop("only", (m,))}
    if m == "nbm":   # National Blend: its own period fields (1/6 h precip, 6 h snow, 3 h thunder, 12 h max/min)
        prods = {k: prods[k] for k in ("t2m", "gust10", "tcc")}
        prods["gust10"]["extra"] = "NBM gust at the valid time  \u00b7  up to {hi} mph in view"
        TS_L = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]; TS_A = [(10, "#d9e8c3"), (20, "#9fd27a"), (40, "#f2e34b"), (60, "#f4a43a"), (80, "#e2462f"), (100, "#8c1450")]
        CM.update(nqpf1=CM["qpf"], nqpf6=CM["qpf"], nsnow6=CM["snow"], ntstm=M.ramp(TS_L, TS_A), nmaxt=CM["t2m"], nmint=CM["t2m"])
        prods["nqpf1"] = dict(title="1 h Precipitation", fields=["nq1"], key="Precip (in)", ticks=[0.01, 0.05, 0.1, 0.25, 0.5, 1, 2], tickfmt=True,
                              **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="NBM liquid equivalent in the hour ending at the valid time (to 36 h)  \u00b7  max {hi} in in view",
                              pct=[0, 100], dec=2, fmt="in2")
        prods["nqpf6"] = dict(title="6 h Precipitation", fields=["nq6"], key="Precip (in)", ticks=[0.1, 0.5, 1, 2, 3, 4, 6], tickfmt=True,
                              **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="NBM liquid equivalent in the 6 h ending at the valid time (every 6 h)  \u00b7  max {hi} in in view",
                              pct=[0, 100], dec=2, fmt="in2")
        prods["nsnow6"] = dict(title="6 h Snowfall", fields=["ns6"], key="Snow (in)", ticks=[0.1, 1, 3, 6, 10, 15, 24], tickfmt=True,
                               **table(M.SNOW_LEVELS, CM["snow"], "max"), extra="NBM snowfall in the 6 h ending at the valid time (every 6 h)  \u00b7  max {hi} in in view",
                               pct=[0, 100], dec=1, fmt="in1")
        prods["ntstm"] = dict(title="Thunderstorm Chance (3 h)", fields=["tstm"], key="Chance (%)", ticks=TS_L, tickfmt=True,
                              **table(TS_L, CM["ntstm"], "neither"), extra="NBM chance of thunder in the 3 h ending at the valid time (every 3 h)", pct=[0, 100], towns="names")
        prods["nmaxt"] = dict(title="12 h High Temperature", fields=["maxt"], key="Temp (\u00b0F)", ticks=HS.TEMP_TICKS, **table(HS.TEMP_LEVELS, CM["t2m"], "both"),
                              freeze=32, extra="NBM highest temperature in the 12 h ending at the valid time  \u00b7  {lo} to {hi}\u00b0F in view", pct=[0.5, 99.5])
        prods["nmint"] = dict(title="12 h Low Temperature", fields=["mint"], key="Temp (\u00b0F)", ticks=HS.TEMP_TICKS, **table(HS.TEMP_LEVELS, CM["t2m"], "both"),
                              freeze=32, extra="NBM lowest temperature in the 12 h ending at the valid time  \u00b7  {lo} to {hi}\u00b0F in view", pct=[0.5, 99.5])
    if m in ("eps", "aens"):   # ensemble: mean versions of the shared products plus spread / probability maps
        prods = {k: ALLP[k] for k in ("t2m", "t2ma", "z500anom", "t850a", "qpf", "qpf6", "qpf24", "qpf48", "mslpqpf", "gust10", "mucape", "qpfa", "qpfpct")
                 if k not in ("mucape", "gust10") or m == "eps"}   # AIFS ENS open data has no gust or CAPE
        for k in ("t850a", "qpf", "qpf6", "qpf24", "qpf48", "mslpqpf", "gust10", "mucape", "qpfa", "qpfpct"):
            if k in prods: prods[k]["title"] += " (ens. mean)"; prods[k]["extra"] = "mean of 50 members  \u00b7  " + prods[k]["extra"]
        if m == "eps": prods["gust10"]["extra"] = "mean of 50 members' max gust in the 6 h ending at the valid time  \u00b7  up to {hi} mph in view"
        if m == "eps": prods["mucape"]["extra"] = "mean of 50 members  \u00b7  blank under 100 J/kg  \u00b7  up to {hi} J/kg in view"
        CM.update(eqpf90=CM["qpf"], esnow=CM["snow"], esnow90=CM["snow"], egust90=CM["gust10"], epcape=None, elows=None, spag=None)
        prods["eqpf90"] = dict(title="Precipitation Total, 90th Percentile", fields=["apcp90"], key="Precip (in)", ticks=[0.1, 0.5, 1, 2, 3, 4, 6, 8, 10, 12], tickfmt=True,
                               **table(HS.RAIN_LEVELS, CM["qpf"], "max"), extra="reasonable high end: 5 of 50 members are wetter  \u00b7  since the run started  \u00b7  max {hi} in in view",
                               pct=[0, 100], dec=2, fmt="in2", accum=True)
        prods["esnow"] = dict(title="Snowfall Total (ens. mean, 10:1)", fields=["asnow"], key="Snow (in)", ticks=[0.1, 1, 3, 6, 10, 15, 24, 36, 48], tickfmt=True,
                              **table(M.SNOW_LEVELS, CM["snow"], "max"), extra="mean of 50 members' snowfall water x 10  \u00b7  since the run started  \u00b7  max {hi} in in view",
                              pct=[0, 100], dec=1, fmt="in1", accum=True)
        prods["esnow90"] = dict(prods["esnow"], title="Snowfall Total, 90th Percentile (10:1)", fields=["asnow90"],
                                extra="reasonable high end: 5 of 50 members are snowier  \u00b7  10:1  \u00b7  since the run started  \u00b7  max {hi} in in view")
        if m == "eps": prods["egust90"] = dict(title="Wind Gusts, 90th Percentile", fields=["gust90"], key="Gust (mph)", ticks=HS.WIND_TICKS, **table(HS.WIND_LEVELS, CM["gust10"], "max"),
                                extra="5 of 50 members gust higher (max in the 6 h ending at the valid time)  \u00b7  up to {hi} mph in view", pct=[1, 99.9])
        PC_L = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]; CM["epcape"] = M.ramp(PC_L, [(10, "#d9e8c3"), (30, "#f2e34b"), (50, "#f4a43a"), (70, "#e2462f"), (100, "#8c1450")])
        if m == "eps":
            prods["epcape"] = dict(title="Chance of MUCAPE 500+ J/kg", fields=["pcape"], key="Chance (%)", ticks=PC_L, tickfmt=True, **table(PC_L, CM["epcape"], "neither"),
                                   extra="share of the 50 members with most-unstable CAPE of 500 J/kg or more", pct=[0, 100], towns="names")
        LP_L = [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        CM["elows"] = M.ramp(LP_L, [(5, "#eef3fb"), (20, "#bcd3f0"), (40, "#7fa7e0"), (60, "#e8a0c8"), (80, "#c2357a"), (100, "#6b0f3f")])
        prods["elows"] = dict(title="Ensemble Low Centers", fields=["lowp", "mslp"], fill="lowp", key="Low within ~300 km (%)", ticks=[5, 10, 20, 40, 60, 80, 100], tickfmt=True,
                              **table(LP_L, CM["elows"], "neither"),
                              isobars=dict(field="mslp", every=4, sigma=1.0, color=HS.ISOBAR_COLOR, lw=HS.ISOBAR_LW, halo=HS.ISOBAR_HALO),
                              lows=True, extra="dots = member lows (darker = deeper)  \u00b7  colors = % of members with a low nearby  \u00b7  lines = mean MSLP",
                              pct=[0, 100], towns="names")
        prods["elows"]["under"] = "#f4f5f7"
        prods["spag"] = dict(title="500 mb Spaghetti (552 / 576 dam)", fields=["z500", "z5sd"], fill="z5sd", key="Spread (m)", ticks=[0, 20, 40, 60, 80, 100, 120, 140, 160],
                             tickfmt=True, **table(list(range(0, 161, 10)), M.ramp(list(range(0, 161, 10)), [(0, "#ffffff"), (60, "#e9e9e9"), (160, "#a9a9a9")]), "max"),
                             spag=True, extra="blue = each member's 552 dam line, red = 576 dam  \u00b7  black = ensemble mean  \u00b7  gray = spread",
                             pct=[0.5, 99.5], towns="names")
        CM["spag"] = M.ramp(list(range(0, 161, 10)), [(0, "#ffffff"), (60, "#e9e9e9"), (160, "#a9a9a9")])
        if m == "eps":   # old site's "EPS lows / highs" (WA tabs): mean of the members' 2 m max / min, worst of the 24 h ending at the valid time
            CM.update(ehigh=CM["t2m"], elow=CM["t2m"])
            prods["ehigh"] = dict(title="24 h High Temperature (ens. mean)", fields=["maxt"], window=24, wmax=True, wfield="maxt", fill="window", key="Temp (\u00b0F)",
                                  ticks=HS.TEMP_TICKS, **table(HS.TEMP_LEVELS, CM["t2m"], "both"), freeze=32,
                                  extra="mean of 50 members' 2 m max (3 h / 6 h periods), highest in the 24 h ending at the valid time  \u00b7  {lo} to {hi}\u00b0F in view",
                                  pct=[0.5, 99.5])
            prods["elow"] = dict(prods["ehigh"], title="24 h Low Temperature (ens. mean)", fields=["mint"], wmax=False, wmin=True, wfield="mint",
                                 extra="mean of 50 members' 2 m min (3 h / 6 h periods), lowest in the 24 h ending at the valid time  \u00b7  {lo} to {hi}\u00b0F in view")
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
    for k, v in (("eqpf90", None), ("esnow", None), ("esnow90", None), ("epcape", 10)):
        if k in prods: prods[k]["min_show"] = v if v is not None else prods[k]["levels"][0]
    for k in ("w500", "w250"):
        if k in prods: prods[k]["under"] = "#f4f5f7"   # light below the first level so barbs and height lines stay readable
    if "mslpqpf" in prods: prods["mslpqpf"]["under"] = "#f4f5f7"
    if "w850" in prods: prods["w850"]["under"] = "#f4f5f7"   # light below 10 kt (was black)   # light background so the dark isobars read (no blanking)
    if "ntstm" in prods: prods["ntstm"]["min_show"] = 10
    for k in ("waves", "wavemax"):   # land (swh -0.5) drawn in the basemap land tone
        if k in prods: prods[k]["under"] = "#ece8df"
    for k in ("fog", "ivt"):   # light below the first level (old site: clear over the light basemap)
        if k in prods: prods[k]["under"] = "#f4f5f7"
    if "ptype" in prods: prods["ptype"]["under"] = "#f4f5f7"
    for k in ("nqpf1", "nqpf6", "nsnow6"):
        if k in prods: prods[k]["min_show"] = prods[k]["levels"][0]
    if m == "ifs" and "snow" in prods: prods["snow"]["extra"] = "ECMWF snowfall water x 10 (10:1)  \u00b7  since the run started  \u00b7  max {hi} in in view"
    for k in ("kuchera", "kuch24", "fzra"):
        if k in prods: prods[k]["min_show"] = prods[k]["levels"][0]
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
                cb.ax.set_xticklabels(P.get("ticklabels") or [f"{t:g}" for t in P["ticks"]], fontproperties=HS.font(700, 13))
            else: HS.hbar(fig, cs, tk0, P["key"], ky)
            HS.credit(fig, TM.CREDIT_NOAA if (pid == "t2m" and m in NOAA) else (M.credit(m) if m in M.MODELS else M.credit("gfs") if minfo(m).get("noaa") else TM.CREDIT.format(name=minfo(m)["name"])))
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
        P = town_points(man, m)
        for s, sizes, ranges, nb, tt in ex.map(step_job, [(m, cycle, s, crop, rd, P) for s in todo]):
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
               complete=len(ordered) == len(want), expected=len(want), file="single/{name}_f{f:03d}.png",
               points=[{k: v for k, v in p_.items() if k in ("n", "k", "c")} for p_ in town_points(man, m)], pts_file="single/pts_f{f:03d}.json")
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
