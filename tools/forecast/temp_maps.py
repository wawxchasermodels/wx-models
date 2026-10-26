#!/usr/bin/env python3
"""Menu products: 2 m Temperature and 850 mb Temperature + Wind, for ECMWF IFS (open data 0.1 deg, from native ~9 km)
and ECMWF AIFS (0.25 deg). Views: North America, Pacific NW, Pacific NW tight (2 m maps only), Washington
(AIFS 850 mb has no WA view: upper-air rule).

Methods (standard): 2 m temperature is the model's 2 m air temperature (K -> F), filled on the shared house_style
temperature scale with the 32 F line dashed. 850 mb: temperature (K -> C) on the same palette (equal temperatures look
equal across products), 0 C line dashed, 850 mb geopotential height contours every 3 dam, wind barbs in kt thinned in
projection space. Data: ECMWF open data, CC BY 4.0. Basemap: Natural Earth (public domain). NOT scheduled; run by hand:
  python temp_maps.py --model ifs|aifs [--cycle YYYYMMDDHH] [--hours 240] [--every 12] [--views na,pnw,wa] [--products t2m,t850]
2 m anomaly (--products t2manom, ECMWF 9 km and AIFS): model 2 m temperature minus the NCEP/NCAR Reanalysis 1991-2020
6-hourly mean for that date and hour (NOAA PSL, public domain; build it with make_clim_t2m.py), interpolated in time and
space and moved from reanalysis terrain to model terrain with a 6.5 C/km lapse rate. In deg F.
850 mb anomaly (--products t850anom, ECMWF 9 km and AIFS; GFS via gfs_maps.py, ensemble means via ens_maps.py): 850 mb
temperature minus the NCEP/NCAR Reanalysis 1991-2020 monthly mean at 850 mb (make_clim_t850.py), in deg C. North America + Pacific NW.
Writes $SITE_BATCH/<cycle>/<t2m|t850|t2manom|t850anom>-<model>/step/<view>/<valid>/final.jpg + site_frame.json (model "ECMWF 9 km" or "AIFS").
"""
import sys, argparse, datetime as dt, json, os, urllib.request, urllib.error
from zoneinfo import ZoneInfo
import numpy as np, eccodes as ec
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.transforms
from matplotlib.colors import BoundaryNorm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house_style as HS
import cartopy.crs as ccrs, cartopy.feature as cf
import fastgeo  # noqa: F401  speed_build_v1: faster contour/contourf/barbs/quiver (WX_FASTGEO=0 = off)
from scipy.ndimage import gaussian_filter

PT = ZoneInfo("America/Los_Angeles")
ROOT = os.environ.get("SITE_BATCH", ".site_batch")
E = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/"
MODELS = {
    "ifs": dict(site="ECMWF 9 km", name="ECMWF IFS", res="0.1\u00b0",
                url={"sfc": E + "ifs/0p1/oper/{d}{h:02d}0000-{s}h-oper-fc-sfc", "pl": E + "ifs/0p1/oper/{d}{h:02d}0000-{s}h-oper-fc-pl"}),
    "aifs": dict(site="AIFS", name="ECMWF AIFS", res="0.25\u00b0",
                 url={"sfc": E + "aifs-single/0p25/oper/{d}{h:02d}0000-{s}h-oper-fc", "pl": E + "aifs-single/0p25/oper/{d}{h:02d}0000-{s}h-oper-fc"}),
}
HRRR = "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfsfcf{s:02d}.grib2"
RRFS = "https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.{d}/{h:02d}/rrfs.t{h:02d}z.2dfld.3km.f{s:03d}.conus.grib2"
# High-res (NOAA, public domain: no credit line needed). HRRR wrfsfc has 2 m and 850 mb fields; RRFS 2dfld only 2 m.
HIRES = {
    "hrrr": dict(site="HRRR", name="NOAA HRRR", res="3 km", url=HRRR, hours=48, products=("t2m", "t850"), lov=-97.5, latin=38.5),
    "rrfs": dict(site="RRFS", name="NOAA RRFS", res="3 km", url=RRFS, hours=84, products=("t2m",), lov=-97.5, latin=38.5),
}
MODELS.update({k: dict(site=v["site"], name=v["name"], res=v["res"]) for k, v in HIRES.items()})
CREDIT = "{name}: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int.  Basemap: Natural Earth."
CREDIT_NOAA = "Basemap: Natural Earth."
VIEWS = {   # same NA / PNW frames as the AIFS upper-air maps, plus a Washington frame
    "na": dict(label="North America", size=(16, 12),
               proj=ccrs.LambertConformal(central_longitude=-120, central_latitude=48, standard_parallels=(35, 60)),
               extent=(-4.67e6, 4.33e6, -3.3e6, 3.4e6), box=(-210, -5, 5, 88)),
    "pnw": dict(label="Pacific Northwest", size=(16, 10.5), proj=ccrs.Mercator(central_longitude=-130), ll=(-160, -103, 37, 61), box=(-165, -98, 32, 66)),
    "wa": dict(label="Washington", size=(16, 10.5), proj=ccrs.LambertConformal(central_longitude=-120.5, central_latitude=47.3, standard_parallels=(45, 49)),
               ll=(-125.0, -116.6, 45.3, 49.25), box=(-127, -114.5, 44.3, 50.3)),
}
# High-res Pacific NW frame: the part of the PNW the 3 km CONUS grids cover (their NW corner is near 48N 134W).
VIEWS["pnwhr"] = dict(label="Pacific NW (high-res)", size=(16, 11.2), proj=ccrs.LambertConformal(central_longitude=-120, central_latitude=45.5,
                      standard_parallels=(42, 49)), ll=(-126.8, -111.0, 40.6, 49.4), box=(-130, -108, 39.5, 51))
# "Pacific NW tight" (pnwt): Washington, Vancouver Island and the near Pacific (first built for the ensemble maps, 10-24-26).
# Global models only (the 3 km grids stop short of its NW corner). Used by the ground-level maps; upper air stays na/pnw.
VIEWS["pnwt"] = dict(label="Pacific NW tight", size=(16, 10.5), proj=ccrs.Mercator(central_longitude=-126),
                     ll=(-138.0, -113.5, 40.5, 54.5), box=(-145, -106, 36, 59))
SMOOTH = {"na": 1.2, "pnw": 0.8, "wa": 0.0, "pnwhr": 0.0, "pnwt": 0.6}
HIRES_VIEWS = ("pnwhr", "wa")
HS.BARBS_ACROSS.setdefault("pnwhr", 20)   # same density as the global PNW frame
BELOW_GROUND = "#8d9096"   # 850 mb maps: flat gray where the ground is above the 850 mb surface (surface pressure < 850 mb)
CLIM_T2M = f"{ROOT}/clim/ncep_t2m_6h_ltm_1991_2020.npz"
CREDIT_CLIM = "  Climatology: NCEP/NCAR Reanalysis 1991-2020, NOAA PSL."
LAPSE = 0.0065   # C per m, standard atmosphere
# 2 m anomaly key: deg F, -30..+30 in 1 F bins; colors from the 500 mb anomaly family (1 F drawn like 15 m) so both
# anomaly products read the same way: blues/greens/grays below normal, oranges/reds/purples above.
T2A_LEVELS = np.arange(-30, 31, 1)
T2A_TICKS = list(range(-30, 31, 5))


def t2a_cmap():
    return HS.cmap([HS._anom_color(15.0 * x) for x in (T2A_LEVELS[:-1] + T2A_LEVELS[1:]) / 2.0], HS.ANOM_UNDER, HS.ANOM_OVER)


def clim_t2m(valid, LA, LO, zmodel):
    """Normal 2 m temperature (C) at the valid time on the model grid, moved to model terrain (zmodel, m)."""
    from scipy.interpolate import RegularGridInterpolator
    z = np.load(CLIM_T2M); T, zs, cl, co = z["t2m"].astype("f4"), z["zs"], z["lat"], z["lon"]
    # PSL stamps each 6-hourly 2 m value with the start time of the 0-6 h reanalysis forecast it comes from, so the value
    # stamped T is valid at T+6 h. Checked against ECMWF: this alignment removes a false 25 F day/night swing in the anomaly.
    v = (valid - dt.timedelta(hours=6)).astimezone(dt.timezone.utc).replace(tzinfo=None)
    doy = v.timetuple().tm_yday   # leap years: Feb 29 uses Feb 28, later days shift back one to the same calendar day
    if doy > 59 and v.year % 4 == 0 and (v.year % 100 or v.year % 400 == 0): doy -= 1
    x = (doy - 1) * 4 + (v.hour + v.minute / 60) / 6.0; i0 = int(np.floor(x)) % 1460; w = x - np.floor(x)
    f = (1 - w) * T[i0] + w * T[(i0 + 1) % 1460]
    pts = np.stack([np.asarray(LA, float), np.asarray(LO, float) % 360], -1)
    it = lambda a: RegularGridInterpolator((cl[::-1], co), a[::-1], bounds_error=False, fill_value=None)(pts)
    return it(f) - LAPSE * (zmodel - it(zs))


DL = {"sec": 0.0, "bytes": 0}   # download timer (speed_build_v1): wall seconds spent inside get(), read by menu_maps' step timer
GRIB_CACHE = os.environ.get("WX_GRIB_CACHE")   # optional local byte-range cache (tests / benchmarks); unset on the runners


def get(url, rng=None):
    import time as _t, hashlib
    t0 = _t.perf_counter()
    try:
        if not GRIB_CACHE: return _get(url, rng)
        k = os.path.join(GRIB_CACHE, hashlib.sha1(f"{url}|{rng}".encode()).hexdigest())
        if os.path.exists(k): return open(k, "rb").read()
        b = _get(url, rng); os.makedirs(GRIB_CACHE, exist_ok=True); open(k + ".tmp", "wb").write(b); os.replace(k + ".tmp", k); return b
    finally:
        DL["sec"] += _t.perf_counter() - t0


def _get(url, rng=None):
    h = {"User-Agent": "wx-models (personal, not scheduled)"}
    if rng: h["Range"] = "bytes=%d-%d" % rng
    for k in range(4):   # open data servers drop the odd connection; retry with a short backoff
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500 or k == 3: raise
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if k == 3: raise
        __import__("time").sleep(5 * (k + 1))


def latest_cycle(m):
    if m in HIRES:   # menu_v2: high-res long runs 00/06/12/18Z
        now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
        for b in range(0, 30):
            c = now - dt.timedelta(hours=b)
            if c.hour % 6: continue
            if os.environ.get("WX_CYCLE_HOUR") and c.hour != int(os.environ["WX_CYCLE_HOUR"]): continue   # scheduled run: 12Z only
            try:
                get(HIRES[m]["url"].format(d=f"{c:%Y%m%d}", h=c.hour, s=HIRES[m]["hours"]) + ".idx", (0, 10)); return c
            except Exception: pass
        raise SystemExit("no long run found")
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 48):
        c = now - dt.timedelta(hours=b)
        if c.hour % 12: continue   # menu_v2: globals 00Z + 12Z only
        if os.environ.get("WX_CYCLE_HOUR") and c.hour != int(os.environ["WX_CYCLE_HOUR"]): continue   # scheduled run: 12Z only
        try:
            get(MODELS[m]["url"]["sfc"].format(d=f"{c:%Y%m%d}", h=c.hour, s=240) + ".index", (0, 10)); return c
        except Exception: pass
    raise SystemExit("no run found")


class Step:
    """Reads only the GRIB messages needed for one step, with HTTP range requests (index lookups cached per file)."""
    def __init__(self, m, c, s):
        self.m, self.c, self.s, self.idx, self.bytes = m, c, s, {}, 0

    def field(self, param, lev=None, kind="sfc"):
        base = MODELS[self.m]["url"][kind].format(d=f"{self.c:%Y%m%d}", h=self.c.hour, s=self.s)
        if base not in self.idx:
            self.idx[base] = [json.loads(l) for l in get(base + ".index").decode().splitlines()]
        r = next(x for x in self.idx[base] if x["param"] == param and (x.get("levtype") == "sfc" if lev is None else x.get("levelist") == str(lev)))
        g = ec.codes_new_from_message(get(base + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1))); self.bytes += r["_length"]
        ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
        la0, lo0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
        d = ec.codes_get(g, "iDirectionIncrementInDegrees")
        v = ec.codes_get_values(g).reshape(nj, ni); ec.codes_release(g)
        lat = la0 - d * np.arange(nj); lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180
        o = np.argsort(lon)
        return lat, lon[o], v[:, o]


class HiresStep:
    """NOAA HRRR / RRFS: one GRIB2 record per request via the .idx byte ranges (AWS open data, public domain)."""
    def __init__(self, m, c, s):
        self.m, self.c, self.s, self.bytes = m, c, s, 0
        self.url = HIRES[m]["url"].format(d=f"{c:%Y%m%d}", h=c.hour, s=s); self.idx = None

    def field(self, var, lev):
        if self.idx is None: self.idx = get(self.url + ".idx").decode().splitlines()
        key = f":{var}:{lev}:"
        for k, l in enumerate(self.idx):
            if key in l and ("anl" in l or l.rstrip(":").endswith("fcst")):
                a = int(l.split(":")[1]); b = int(self.idx[k + 1].split(":")[1]) - 1 if k + 1 < len(self.idx) else None
                blob = get(self.url, (a, b if b is not None else a + 40_000_000)); self.bytes += len(blob)
                g = ec.codes_new_from_message(blob)
                v = ec.codes_get_values(g); ni, nj = ec.codes_get(g, "Nx"), ec.codes_get(g, "Ny")
                la = ec.codes_get_array(g, "latitudes"); lo = ec.codes_get_array(g, "longitudes"); ec.codes_release(g)
                lo = np.where(lo > 180, lo - 360, lo)
                return la.reshape(nj, ni), lo.reshape(nj, ni), v.reshape(nj, ni)
        raise StopIteration(f"{var} {lev} not in {self.url}")


def earth_relative(u, v, lon, m):
    """Grid-relative Lambert winds -> east/north components (NCEP convention, rotation sin(latin) * (lon - lov))."""
    a = np.deg2rad(np.sin(np.deg2rad(HIRES[m]["latin"])) * (lon - HIRES[m]["lov"]))
    return np.cos(a) * u + np.sin(a) * v, -np.sin(a) * u + np.cos(a) * v


def cut(lat, lon, arrs, vid):
    """Crop to the view's lon/lat box (0-360 longitudes so the NA frame can reach past the dateline).
    2-D lat/lon (high-res Lambert grids): crop to the rows/columns that touch the box; contour on the 2-D coordinates."""
    b = VIEWS[vid]["box"]
    if np.ndim(lat) == 2:
        m = (lat >= b[2]) & (lat <= b[3]) & (lon >= b[0]) & (lon <= b[1]); ii, jj = np.where(m)
        s_ = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1))
        return lat[s_], lon[s_], [a[s_] for a in arrs]
    l360 = lon % 360; o = np.argsort(l360); l360 = l360[o]
    sl = (lat >= b[2]) & (lat <= b[3]); so = (l360 >= b[0] % 360) & (l360 <= b[1] % 360)
    return lat[sl], l360[so], [a[:, o][np.ix_(sl, so)] for a in arrs]


# Washington view: a few reference towns (dot + name), spread so they don't pile up. "r" = name right of the dot, "l" = left.
WA_TOWNS = [
    ("Bellingham", 48.75, -122.48, "r"), ("Port Angeles", 48.12, -123.43, "l"), ("Forks", 47.95, -124.39, "r"),
    ("Everett", 47.98, -122.20, "r"), ("Seattle", 47.61, -122.33, "r"), ("Tacoma", 47.25, -122.44, "r"),
    ("Olympia", 47.04, -122.90, "r"), ("Aberdeen", 46.98, -123.82, "l"), ("Longview", 46.14, -122.94, "r"),
    ("Vancouver", 45.64, -122.66, "r"), ("Omak", 48.41, -119.53, "r"), ("Wenatchee", 47.42, -120.31, "r"),
    ("Ellensburg", 46.99, -120.55, "r"), ("Yakima", 46.60, -120.51, "r"), ("Tri-Cities", 46.23, -119.15, "r"),
    ("Walla Walla", 46.06, -118.34, "r"), ("Moses Lake", 47.13, -119.28, "r"), ("Colville", 48.55, -117.91, "r"),
    ("Spokane", 47.66, -117.43, "l"), ("Pullman", 46.73, -117.18, "l"),
]


# Where each town's NUMBER is read from the model (the label stays at the town). Same official-station pins as
# tools/wa_maps/town_pop.py OFFICIAL_PIN (house rule: Seattle = SEA, Tacoma = TIW, Port Angeles = CLM, ...); towns without
# a pin are read at the town point. Tri-Cities uses Pasco (PSC).
TOWN_PIN = {"Seattle": (47.4447, -122.3144), "Port Angeles": (48.1220, -123.5066), "Spokane": (47.6216, -117.5280),
            "Yakima": (46.5682, -120.5441), "Wenatchee": (47.3990, -120.2070), "Olympia": (46.9733, -122.9033),
            "Bellingham": (48.7927, -122.5375), "Tri-Cities": (46.2647, -119.1190), "Walla Walla": (46.0948, -118.2890),
            "Moses Lake": (47.2086, -119.3191), "Vancouver": (45.6204, -122.6565), "Everett": (47.9070, -122.2816),
            "Pullman": (46.7439, -117.1096), "Ellensburg": (47.0330, -120.5307), "Omak": (48.4644, -119.5181),
            "Aberdeen": (46.9712, -123.9366), "Tacoma": (47.2675, -122.5761)}
TOWN_NUM_COLOR, TOWN_NUM_SIZE, TOWN_NUM_HALO = "#0d0f13", 10.5, 3.0   # bold dark number on a white halo (reads on any fill)

# Mountain passes on the Washington view (Benjamin 10-24-26 10:22 PM: "main mountain pass locations on the Washington view").
# Coordinates are NOT new: the first 8 are the Washington Snow tab table (tools/wa_maps/snow_map.py PASSES, same in gust_map,
# nbm_map, precip_map); Cayuse, Satus, Wauconda and Disautel are the WSDOT MountainPass API points the pass watcher follows
# (wsdot.com/Travel/Real-time/Service/api/MountainPass, read 10-24-26). Elevation (ft) = WSDOT's summit elevation, kept to
# report how far the model's smoothed terrain sits below the real pass. Stampede Pass is in neither list, so it is not shown.
# name: (label, lat, lon, elev_ft), in placement priority order (main I-90 / US 2 / US 12 crossings first)
WA_PASSES = {
    "Snoqualmie Pass": ("Snoqualmie", 47.4245, -121.4136, 3022), "Stevens Pass": ("Stevens", 47.7465, -121.0854, 4061),
    "White Pass": ("White", 46.6383, -121.3911, 4500), "Chinook Pass": ("Chinook", 46.8714, -121.5156, 5430),
    "Blewett Pass": ("Blewett", 47.3348, -120.5786, 4102), "Washington Pass": ("Washington Pass", 48.5253, -120.6545, 5477),
    "Loup Loup Pass": ("Loup Loup", 48.3926, -119.9026, 4020), "Sherman Pass": ("Sherman", 48.6055, -118.4636, 5575),
    "Cayuse Pass": ("Cayuse", 46.8656, -121.5361, 4675), "Satus Pass": ("Satus", 45.9847, -120.6536, 3107),
    "Wauconda Pass": ("Wauconda", 48.7262, -118.9595, 4310), "Disautel Pass": ("Disautel", 48.2818, -119.1434, 3252),
}
# Pass height correction (Benjamin 10-24-26 10:32 PM): value + rate * (model ground at the pass - real summit), ft.
# Temperature and feels-like 3.5 F per 1000 ft (between the 5.4 F dry and ~3 F moist rates); dewpoint 1 F per 1000 ft (dewpoint
# falls much more slowly with height than temperature). Gusts, precip, snow and visibility are never corrected; towns never.
# Summit elevations: WSDOT MountainPass feed, checked 10-24-26 against USGS 3DEP (epqs.nationalmap.gov) within 60 ft at the
# table points, except Sherman: the Snow-tab point sits ~1.2 km east of the summit (3DEP 5,233 ft there; 5,612 ft at WSDOT's
# point), so the correction still targets the 5,575 ft summit. PASS_HEIGHT_CORR=0 turns it off.
LAPSE_T_F_PER_FT, LAPSE_TD_F_PER_FT = 3.5 / 1000.0, 1.0 / 1000.0
_OROG = {}


def model_orog(key, loader):
    """Model terrain height (ft) as (lat, lon, z), cached per (model, cycle); loader() returns (lat, lon, metres)."""
    if key not in _OROG:
        la, lo, z = loader(); _OROG[key] = (la, lo, np.asarray(z, float) * 3.28084)
    return _OROG[key]


def hires_orog(st):
    """HRRR / RRFS surface height from the same step file (HGT:surface)."""
    return model_orog((st.m, st.c), lambda: st.field("HGT", "surface"))


def ecmwf_orog(m, c):
    """ECMWF IFS / AIFS surface geopotential (step-0 file only) -> height."""
    def ld():
        la, lo, z = Step(m, c, 0).field("z"); return la, lo, z / 9.80665
    return model_orog((m, c), ld)


PASS_COLOR, PASS_NAME_SIZE, PASS_NUM_SIZE = "#3b2a5c", 8.0, 9.5   # deep plum, small italic name: reads as "not a town"


def town_values(LA, LO, F, pts):
    """Model value at each (lat, lon) point. Regular lat/lon grids (ECMWF): bilinear. 2-D Lambert grids (HRRR/RRFS 3 km):
    nearest grid point. NaN where the point is off the grid or touches a missing value."""
    F = np.asarray(F, float); out = []
    if np.ndim(LA) == 2:
        from scipy.spatial import cKDTree
        la, lo = np.asarray(LA, float), np.asarray(LO, float)
        lo = (lo + 180) % 360 - 180; k = np.cos(np.deg2rad(np.nanmean(la)))
        tree = cKDTree(np.column_stack([la.ravel(), lo.ravel() * k]))
        for pla, plo in pts:
            d, i = tree.query([pla, ((plo + 180) % 360 - 180) * k])
            out.append(F.ravel()[i] if d < 0.06 else np.nan)   # 0.06 deg ~ 6 km: farther means off the 3 km grid
        return np.array(out)
    from scipy.interpolate import RegularGridInterpolator
    la, lo = np.asarray(LA, float), np.asarray(LO, float) % 360
    if la[0] > la[-1]: la, F = la[::-1], F[::-1]
    o = np.argsort(lo, kind="stable"); lo, F = lo[o], F[:, o]   # full-globe grids wrap at 0/360: sort
    it = RegularGridInterpolator((la, lo), F, bounds_error=False, fill_value=np.nan)
    return it(np.array([[pla, plo % 360] for pla, plo in pts]))


# number formats per product: return None to leave a town without a number
def fmt_int(v): return None if not np.isfinite(v) else str(int(round(v)))
def fmt_signed(v): return None if not np.isfinite(v) else ("0" if round(v) == 0 else f"{v:+.0f}")
def fmt_in2(v): return None if not np.isfinite(v) else f"{max(v, 0):.2f}"                          # rain / ice, inches
def fmt_in1(v): return None if not np.isfinite(v) else ("0" if v < 0.05 else f"{v:.1f}")          # snow, inches
def fmt_vis(v):                                                                                     # visibility, miles
    if not np.isfinite(v): return None
    if v >= 7: return "7+"   # the map leaves 7 mi and more blank
    return f"{v:.1f}" if v < 3 else f"{v:.0f}"


def _hits(bb, others, pad=1.5):
    return any(bb.x0 - pad < o.x1 and o.x0 < bb.x1 + pad and bb.y0 - pad < o.y1 and o.y0 < bb.y1 + pad for o in others)


def towns(ax, vid, field=None, fmt=fmt_int, pass_corr=None):
    """Town dots and names on the Washington view only (dark text on a white halo, like the contour labels).
    field = (LA, LO, F) in the map's units adds the model value after each name ("Seattle 54"), read at the town's official
    station pin (bilinear on lat/lon grids, nearest point on 3 km grids). Numbers never overlap a name, another number or the
    frame edge: a number that would is moved under its name, and dropped (logged) if it still collides. Returns the text artists
    (so isobar labels can be cleared around them) and stores the sampled values on ax.town_values for checks."""
    if vid != "wa": return []
    pc = ccrs.PlateCarree(); tr = pc._as_mpl_transform(ax); arts, names = [], []
    for name, la, lo, side in WA_TOWNS:
        ax.plot(lo, la, "o", ms=3.6, mfc="#1b1d22", mec="white", mew=1.0, transform=pc, zorder=7)
        names.append(ax.annotate(name, (lo, la), xycoords=tr, xytext=(5 if side == "r" else -5, 0), textcoords="offset points",
                                 ha="left" if side == "r" else "right", va="center", color="#1b1d22", fontproperties=HS.font(600, 9.5),
                                 path_effects=HS.halo("white", 2.6), zorder=7))
    arts += names
    if field is None or os.environ.get("TOWN_NUMBERS", "1") == "0": return arts   # TOWN_NUMBERS=0 turns the numbers off
    vals = town_values(*field, [TOWN_PIN.get(n, (la, lo)) for n, la, lo, _ in WA_TOWNS])
    ax.town_values = {t[0]: float(v) for t, v in zip(WA_TOWNS, vals)}
    fig = ax.figure; r = fig.canvas.get_renderer(); pt = 72.0 / fig.dpi; axbb = ax.get_window_extent(r)
    nums = [None] * len(WA_TOWNS)
    for k, ((name, la, lo, side), v) in enumerate(zip(WA_TOWNS, vals)):
        s = fmt(v)
        if s is None: continue
        nums[k] = ax.annotate(s, (lo, la), xycoords=tr, xytext=(0, 0), textcoords="offset points", ha="left", va="center",
                              color=TOWN_NUM_COLOR, fontproperties=HS.font(800, TOWN_NUM_SIZE),
                              path_effects=HS.halo("white", TOWN_NUM_HALO), zorder=7.5)
    # inline first: "Name 54" right of the dot, "Name 54 •" left of it (the name slides left to make room)
    for k, (name, la, lo, side) in enumerate(WA_TOWNS):
        n = nums[k]
        if n is None: continue
        nw = names[k].get_window_extent(r).width * pt; vw = n.get_window_extent(r).width * pt
        if side == "r": n.xyann = (5 + nw + 3.5, 0)
        else: n.xyann = (-5 - vw, 0); names[k].xyann = (-5 - vw - 3.5, 0)
    nb = [t.get_window_extent(r) for t in names]
    for k, n in enumerate(nums):
        if n is None: continue
        others = [b for j, b in enumerate(nb) if j != k] + [nums[j].get_window_extent(r) for j in range(len(nums)) if j != k and nums[j] is not None]
        bb = n.get_window_extent(r)
        ok = not _hits(bb, others) and axbb.contains(bb.x0, bb.y0) and axbb.contains(bb.x1, bb.y1)
        if not ok:   # fallback: centered under the name, name back next to its dot
            side = WA_TOWNS[k][3]; names[k].xyann = (5 if side == "r" else -5, 0); nb[k] = names[k].get_window_extent(r)
            n.set_ha("center"); n.xyann = ((nb[k].x0 + nb[k].x1) / 2 * pt - (tr.transform((WA_TOWNS[k][2], WA_TOWNS[k][1]))[0]) * pt, -11)
            bb = n.get_window_extent(r)
            if _hits(bb, others) or not (axbb.contains(bb.x0, bb.y0) and axbb.contains(bb.x1, bb.y1)):
                print(f"town number dropped (no room): {WA_TOWNS[k][0]} {n.get_text()}", flush=True); n.remove(); nums[k] = None; continue
        arts.append(n)
    if os.environ.get("PASS_LABELS", "1") != "0":
        arts += pass_labels(ax, field, fmt, nb + [n.get_window_extent(r) for n in nums if n is not None], r, pt, axbb, pass_corr)
    return arts


def pass_labels(ax, field, fmt, taken, r, pt, axbb, pass_corr=None):
    """pass_corr = (rate F/ft, (lat, lon, model ground ft)) height-corrects the values to the real summit (temps / dewpoint only)."""
    """Small plum triangle + italic name + bold value at each mountain pass (Washington view, maps with town numbers only).
    Value = model at the pass point, NOT corrected to the real summit height (3 km / 9 km terrain is lower and smoother).
    Tries right, left, above, below the triangle; a pass that cannot clear every town label, number and other pass is dropped (logged)."""
    pc = ccrs.PlateCarree(); tr = pc._as_mpl_transform(ax); arts = []
    vals = town_values(*field, [(la, lo) for _, la, lo, _ in WA_PASSES.values()])
    ax.pass_raw = {k: float(v) for k, v in zip(WA_PASSES, vals)}
    if pass_corr is not None and os.environ.get("PASS_HEIGHT_CORR", "1") != "0":
        rate, oro = pass_corr
        zm = town_values(*oro, [(la, lo) for _, la, lo, _ in WA_PASSES.values()])
        ax.pass_model_ft = {k: float(z) for k, z in zip(WA_PASSES, zm)}
        vals = np.array([v + rate * (z - el) if np.isfinite(z) else v for v, z, (_, _, _, el) in zip(vals, zm, WA_PASSES.values())])
    ax.pass_values = {k: float(v) for k, v in zip(WA_PASSES, vals)}
    taken = list(taken)
    for (name, la, lo, side), _ in zip(WA_TOWNS, range(len(WA_TOWNS))):   # town dots are off limits too
        x, y = tr.transform((lo, la)); taken.append(matplotlib.transforms.Bbox([[x - 4, y - 4], [x + 4, y + 4]]))
    for (key, (lab, la, lo, el)), v in zip(WA_PASSES.items(), vals):
        x, y = tr.transform((lo, la))
        if not axbb.contains(x, y): continue
        mk = ax.plot(lo, la, "^", ms=4.6, mfc=PASS_COLOR, mec="white", mew=0.9, transform=pc, zorder=7.2)[0]
        taken.append(matplotlib.transforms.Bbox([[x - 4, y - 4], [x + 4, y + 4]]))
        s_ = fmt(v)
        tn = ax.annotate(lab, (lo, la), xycoords=tr, xytext=(0, 0), textcoords="offset points", ha="left", va="center",
                         color=PASS_COLOR, fontproperties=HS.font(600, PASS_NAME_SIZE), style="italic",
                         path_effects=HS.halo("white", 2.4), zorder=7.2)
        tv = None if s_ is None else ax.annotate(s_, (lo, la), xycoords=tr, xytext=(0, 0), textcoords="offset points", ha="left",
                                                 va="center", color=TOWN_NUM_COLOR, fontproperties=HS.font(800, PASS_NUM_SIZE),
                                                 path_effects=HS.halo("white", TOWN_NUM_HALO), zorder=7.4)
        nw = tn.get_window_extent(r).width * pt; vw = 0 if tv is None else tv.get_window_extent(r).width * pt + 3
        ok = False
        for gx, gy in ((6, 0), (-6 - nw - vw, 0), (-(nw + vw) / 2, 9), (-(nw + vw) / 2, -9)):
            tn.xyann = (gx, gy)
            if tv is not None: tv.xyann = (gx + nw + 3, gy)
            bbs = [tn.get_window_extent(r)] + ([tv.get_window_extent(r)] if tv is not None else [])
            if not any(_hits(b, taken) for b in bbs) and all(axbb.contains(b.x0, b.y0) and axbb.contains(b.x1, b.y1) for b in bbs):
                ok = True; break
        if not ok:   # keep the triangle (location still shown), drop the label
            print(f"pass label dropped (no room): {key} {s_}", flush=True); tn.remove()
            if tv is not None: tv.remove()
            continue
        taken += bbs; arts += [tn] + ([tv] if tv is not None else [])
    return arts


def frame(vid):
    V = VIEWS[vid]
    fig = plt.figure(figsize=V["size"], dpi=150); fig.patch.set_facecolor(HS.BG)
    key_y, top = HS.layout(fig)
    ax = fig.add_axes([0.024, 0.045, 0.952, top - 0.045], projection=V["proj"])
    if "extent" in V: ax.set_extent(V["extent"], crs=V["proj"])
    else: ax.set_extent(V["ll"], crs=ccrs.PlateCarree())
    return fig, ax, key_y


def freeze_line(ax, LO, LA, F, level):
    pc = ccrs.PlateCarree()
    cs = ax.contour(LO, LA, F, levels=[level], colors=HS.FREEZE_COLOR, linewidths=HS.FREEZE_LW, linestyles="dashed", transform=pc, zorder=4)
    cs.set(path_effects=HS.halo("white", 3.0))


def save(fig, out, meta):
    os.makedirs(out, exist_ok=True)
    from PIL import Image
    if os.environ.get("MENU_FASTSAVE", "1") != "0":   # speed_build_v1: raw pixels straight to JPEG (same pixels, no PNG round trip)
        import io
        b = io.BytesIO(); fig.savefig(b, format="rgba", facecolor=fig.get_facecolor()); w, h = fig.canvas.get_width_height(physical=True)
        plt.close(fig); Image.frombuffer("RGBA", (w, h), b.getbuffer(), "raw", "RGBA", 0, 1).convert("RGB").save(f"{out}/final.jpg", quality=90)
    else:
        fig.savefig(f"{out}/final.png", facecolor=fig.get_facecolor()); plt.close(fig)
        Image.open(f"{out}/final.png").convert("RGB").save(f"{out}/final.jpg", quality=90); os.remove(f"{out}/final.png")
    json.dump(meta, open(f"{out}/site_frame.json", "w"))


def header(fig, m, c, step, vid, title, extra):
    valid = c + dt.timedelta(hours=step); vl = valid.astimezone(PT); M = MODELS[m]
    HS.header(fig, title, f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT",
              f"{M['name']} {M['res']} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {VIEWS[vid]['label']}  \u00b7  {extra}",
              f"F+{step}", f"{valid:%HZ %a}".upper())
    HS.credit(fig, CREDIT_NOAA if m in HIRES else CREDIT.format(name=M["name"]))
    return vl


def render_t2m(m, c, step, lat, lon, t2k, vid, out, orog=None):
    LA, LO, (T,) = cut(lat, lon, [t2k], vid)
    F = (T - 273.15) * 1.8 + 32
    if SMOOTH[vid]: F = gaussian_filter(F, SMOOTH[vid])
    fig, ax, key_y = frame(vid); pc = ccrs.PlateCarree(); cm = HS.temp_cmap()
    fill = ax.contourf(LO, LA, F, levels=HS.TEMP_LEVELS, cmap=cm, norm=BoundaryNorm(HS.TEMP_LEVELS, cm.N), extend="both", transform=pc)
    HS.outlines(ax, cf, res="10m" if vid == "wa" else "50m")
    freeze_line(ax, LO, LA, F, 32)
    towns(ax, vid, (LA, LO, F), pass_corr=(LAPSE_T_F_PER_FT, orog) if orog is not None else None)   # town + pass numbers, F
    HS.frame(ax)
    lo, hi = np.nanpercentile(F, [0.5, 99.5])
    vl = header(fig, m, c, step, vid, "2 m Temperature", f"32\u00b0F line dashed  \u00b7  {lo:.0f} to {hi:.0f}\u00b0F in view")
    HS.hbar(fig, fill, HS.TEMP_TICKS, "Temp (\u00b0F)", key_y)
    save(fig, out, {"tab": "t2m", "period": "step", "view": vid, "model": MODELS[m]["site"], "cycle": f"{c:%Y%m%d%H}",
                    "start_pt": vl.isoformat(), "end_pt": vl.isoformat()})


def render_t850(m, c, step, lat, lon, tk, gh, u, v, vid, out, sp=None):
    if sp is None: sp = np.full_like(tk, 1.0e5)
    LA, LO, (T, Z, U, Vw, SP) = cut(lat, lon, [tk, gh, u, v, sp], vid)
    C = T - 273.15; Z = Z / 10.0  # gpm -> dam
    hires = np.ndim(LA) == 2   # 3 km grids: smooth the height lines to about 20-25 km so terrain noise does not clutter them
    if SMOOTH[vid]: C = gaussian_filter(C, SMOOTH[vid])
    if hires: C = gaussian_filter(C, 1.0)
    Zs = gaussian_filter(Z, 7.0 if hires else 1.5 if vid != "wa" else 2.5)
    # 850 mb values under the ground are extrapolated by the model, not real air: blank them (temps, heights, barbs).
    under = gaussian_filter(SP, 1.0 if not hires else 2.0) < 85000.0
    C, Zs, U, Vw = (np.where(under, np.nan, a) for a in (C, Zs, U, Vw))
    fig, ax, key_y = frame(vid); pc = ccrs.PlateCarree(); cm = HS.t850_cmap()
    if under.any():
        # drawn under the temperature fill and a little wider, so the fill's own blank edge never leaves a white seam
        from scipy.ndimage import binary_dilation
        ax.contourf(LO, LA, binary_dilation(under, iterations=2).astype(float), levels=[0.5, 1.5], colors=[BELOW_GROUND],
                    transform=pc, zorder=0.5)
    fill = ax.contourf(LO, LA, C, levels=HS.T850_LEVELS, cmap=cm, norm=BoundaryNorm(HS.T850_LEVELS, cm.N), extend="both", transform=pc)
    HS.outlines(ax, cf, res="10m" if vid == "wa" else "50m")
    freeze_line(ax, LO, LA, C, 0)
    hc = ax.contour(LO, LA, Zs, levels=np.arange(90, 180, 3), colors=HS.ISOBAR_COLOR, linewidths=HS.ISOBAR_LW, transform=pc, zorder=4)
    hc.set(path_effects=HS.halo("white", HS.ISOBAR_HALO))
    for t in ax.clabel(hc, fmt="%d", inline=True, inline_spacing=6):
        t.set_fontproperties(HS.font(700, 10)); t.set_path_effects(HS.halo("white", 3.2))
    fig_w, fig_h = fig.get_size_inches() * ax.get_position().size; nx = HS.BARBS_ACROSS[vid]; ny = max(4, round(nx * fig_h / fig_w))
    ax.barbs(LO, LA, U * 1.94384, Vw * 1.94384, transform=pc, regrid_shape=(nx, ny), length=HS.BARB_LENGTH, color=HS.BARB_COLOR,
             linewidth=HS.BARB_LW, zorder=5)
    towns(ax, vid)
    HS.frame(ax)
    vl = header(fig, m, c, step, vid, "850 mb Temperature + Wind", "0\u00b0C line dashed  \u00b7  heights every 3 dam  \u00b7  barbs in kt  \u00b7  gray = ground above 850 mb")
    HS.hbar(fig, fill, HS.T850_TICKS, "Temp (\u00b0C)", key_y, signed=True)
    save(fig, out, {"tab": "t850", "period": "step", "view": vid, "model": MODELS[m]["site"], "cycle": f"{c:%Y%m%d%H}",
                    "start_pt": vl.isoformat(), "end_pt": vl.isoformat()})


def render_t2manom(m, c, step, lat, lon, t2k, zm, vid, out):
    LA, LO, (T, Zm) = cut(lat, lon, [t2k, zm], vid)
    if np.ndim(LA) == 1: LA, LO = np.meshgrid(LA, LO, indexing="ij")
    valid = c + dt.timedelta(hours=step)
    A = ((T - 273.15) - clim_t2m(valid, LA, LO, Zm)) * 1.8
    A = gaussian_filter(A, max(SMOOTH[vid], 1.0))   # the normal is ~200 km; keep the anomaly from looking sharper than it is
    fig, ax, key_y = frame(vid); pc = ccrs.PlateCarree(); cm = t2a_cmap()
    fill = ax.contourf(LO, LA, A, levels=T2A_LEVELS, cmap=cm, norm=BoundaryNorm(T2A_LEVELS, cm.N), extend="both", transform=pc)
    HS.outlines(ax, cf, res="10m" if vid == "wa" else "50m")
    towns(ax, vid, (LA, LO, A), fmt_signed)   # town numbers: anomaly, F (+/-)
    HS.frame(ax)
    lo, hi = np.nanpercentile(A, [0.5, 99.5])
    vl = header(fig, m, c, step, vid, "2 m Temperature Anomaly",
                f"vs 1991-2020 normal for the date and hour  \u00b7  {lo:+.0f} to {hi:+.0f}\u00b0F in view")
    HS.credit(fig, CREDIT.format(name=MODELS[m]["name"]) + CREDIT_CLIM)
    HS.hbar(fig, fill, T2A_TICKS, "Anomaly (\u00b0F)", key_y, signed=True)
    save(fig, out, {"tab": "t2manom", "period": "step", "view": vid, "model": MODELS[m]["site"], "cycle": f"{c:%Y%m%d%H}",
                    "start_pt": vl.isoformat(), "end_pt": vl.isoformat()})


# 850 mb temperature anomaly (Benjamin 10-25-26 9:24 PM: "850mb temp anomaly added to the global models"): model 850 mb
# temperature minus the NCEP/NCAR Reanalysis 1 monthly long-term mean 1991-2020 at 850 mb (NOAA PSL, public domain; built by
# make_clim_t850.py), linearly interpolated in time to the valid date (months centred on the 15th) and bilinearly in space:
# the same source, period and method as the 500 mb height anomaly. Deg C, -20..+20 in 1 C bins, colors from the 500 mb anomaly
# family (1 C drawn like 22.5 m, so +/-20 C = the +/-450 m ends) so every anomaly product reads the same way. Air under the
# ground (surface pressure < 850 mb) is flat gray like the 850 mb temp map. 850 mb heights every 3 dam when the model has them.
CLIM_T850 = f"{ROOT}/clim/ncep_t850_mon_ltm_1991_2020.npz"
T8A_LEVELS = np.arange(-20, 21, 1)
T8A_TICKS = list(range(-20, 21, 4))
T8A_VIEWS = ("na", "pnw")   # upper-air rule: no tight PNW or Washington frame aloft


def t8a_cmap():
    return HS.cmap([HS._anom_color(22.5 * x) for x in (T8A_LEVELS[:-1] + T8A_LEVELS[1:]) / 2.0], HS.ANOM_UNDER, HS.ANOM_OVER)


def clim_t850(valid, LA, LO):
    """Normal 850 mb temperature (C) for the valid date on the (2-D) LA, LO points."""
    from scipy.interpolate import RegularGridInterpolator
    z = np.load(CLIM_T850); T, cl, co = z["t850"].astype("f4"), z["lat"], z["lon"]
    v = valid.astimezone(dt.timezone.utc); m = v.month - 1; mid = v.replace(day=15, hour=0, minute=0, second=0, microsecond=0)
    m2 = (m + (1 if v >= mid else -1)) % 12; w = min(abs((v - mid).total_seconds()) / (30.4 * 86400), 1.0)
    f = (1 - w) * T[m] + w * T[m2]
    f = np.concatenate([f, f[:, :1]], 1); co = np.append(co, 360.0)
    it = RegularGridInterpolator((cl[::-1], co), f[::-1], bounds_error=False, fill_value=None)
    return it(np.stack([np.asarray(LA, float), np.asarray(LO, float) % 360], -1))


def render_t850anom(c, step, lat, lon, tk, vid, out, who, gh=None, sp=None, orog=None):
    """who = dict(name, res, site, credit[, members]). tk in K on a regular lat/lon grid; gh in gpm (optional);
    sp in Pa (optional) or orog in m (ensembles: ground above ~1,450 m stands in for surface pressure < 850 mb)."""
    arrs = [tk] + [a for a in (gh, sp, orog) if a is not None]
    LA, LO, A = cut(lat, lon, arrs, vid); T = A.pop(0); Z = A.pop(0) if gh is not None else None
    SP = A.pop(0) if sp is not None else None; OR = A.pop(0) if orog is not None else None
    LA2, LO2 = np.meshgrid(LA, LO, indexing="ij"); valid = c + dt.timedelta(hours=step)
    res = abs(float(LA[1] - LA[0])); k = 0.25 / res if res < 0.2 else 1.0   # 0.1 deg grids: same ground smoothing as 0.25 deg
    An = gaussian_filter((T - 273.15) - clim_t850(valid, LA2, LO2), max(SMOOTH[vid], 1.0) * k)   # the normal is 2.5 deg: keep it soft
    under = (gaussian_filter(SP, k) < 85000.0) if SP is not None else (gaussian_filter(OR, 1.0) > 1450.0) if OR is not None else np.zeros(An.shape, bool)
    An = np.where(under, np.nan, An)
    fig, ax, key_y = frame(vid); pc = ccrs.PlateCarree(); cm = t8a_cmap()
    if under.any():
        from scipy.ndimage import binary_dilation
        ax.contourf(LO, LA, binary_dilation(under, iterations=2).astype(float), levels=[0.5, 1.5], colors=[BELOW_GROUND], transform=pc, zorder=0.5)
    fill = ax.contourf(LO, LA, An, levels=T8A_LEVELS, cmap=cm, norm=BoundaryNorm(T8A_LEVELS, cm.N), extend="both", transform=pc)
    HS.outlines(ax, cf, res="50m")
    if Z is not None:
        Zs = np.where(under, np.nan, gaussian_filter(Z / 10.0, 1.5 * k))
        hc = ax.contour(LO, LA, Zs, levels=np.arange(90, 180, 3), colors=HS.ISOBAR_COLOR, linewidths=HS.ISOBAR_LW, transform=pc, zorder=4)
        hc.set(path_effects=HS.halo("white", HS.ISOBAR_HALO))
        for t in ax.clabel(hc, fmt="%d", inline=True, inline_spacing=6):
            t.set_fontproperties(HS.font(700, 10)); t.set_path_effects(HS.halo("white", 3.2))
    HS.frame(ax)
    vl = valid.astimezone(PT); lo, hi = np.nanpercentile(An, [0.5, 99.5])
    run = f"{who['name']} {who['res']}" + (f" {who['members']} members" if who.get("members") else "")
    HS.header(fig, "850 mb Temperature Anomaly" + (" (Ensemble Mean)" if who.get("members") else ""), f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT",
              f"{run} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {VIEWS[vid]['label']}  \u00b7  vs 1991-2020 normal for the date"
              + ("  \u00b7  heights every 3 dam" if Z is not None else "") + f"  \u00b7  {lo:+.0f} to {hi:+.0f}\u00b0C in view  \u00b7  gray = ground above 850 mb",
              f"F+{step}", f"{valid:%HZ %a}".upper())
    HS.credit(fig, who["credit"] + CREDIT_CLIM)
    HS.hbar(fig, fill, T8A_TICKS, "Anomaly (\u00b0C)", key_y, signed=True)
    save(fig, out, {"tab": "t850anom", "period": "step", "view": vid, "model": who["site"], "cycle": f"{c:%Y%m%d%H}",
                    "start_pt": vl.isoformat(), "end_pt": vl.isoformat()})


def steps(hours, every):
    return list(range(0, hours + 1, every))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="ifs", choices=list(MODELS)); ap.add_argument("--cycle")
    ap.add_argument("--hours", type=int, default=240); ap.add_argument("--every", type=int, default=12)
    ap.add_argument("--steps", help="explicit comma list of forecast hours (overrides --hours/--every)")
    ap.add_argument("--views", default="na,pnw,pnwt,wa"); ap.add_argument("--products", default="t2m,t850")
    a = ap.parse_args()
    c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else latest_cycle(a.model)
    tot = 0
    if a.model in HIRES:
        views = [v for v in dict.fromkeys("pnwhr" if v == "pnw" else v for v in a.views.split(",")) if v in HIRES_VIEWS] or list(HIRES_VIEWS)
        for s in ([int(x) for x in a.steps.split(",")] if a.steps else steps(min(a.hours, HIRES[a.model]["hours"]), a.every)):
            st = HiresStep(a.model, c, s); vt = f"{c + dt.timedelta(hours=s):%Y%m%d%H}"
            try:
                if "t2m" in a.products.split(","):
                    lat, lon, t2 = st.field("TMP", "2 m above ground")
                    try: oro = hires_orog(st) if "wa" in views else None
                    except StopIteration: oro = None
                    for v in views:
                        out = f"{ROOT}/{c:%Y%m%d%H}/t2m-{a.model}/step/{v}/{vt}"; render_t2m(a.model, c, s, lat, lon, t2, v, out, oro); print("ok", out, flush=True)
                if "t850" in a.products.split(",") and "t850" in HIRES[a.model]["products"]:
                    lat, lon, t = st.field("TMP", "850 mb"); _, _, z = st.field("HGT", "850 mb")
                    _, _, u = st.field("UGRD", "850 mb"); _, _, w = st.field("VGRD", "850 mb"); u, w = earth_relative(u, w, lon, a.model)
                    _, _, sp = st.field("PRES", "surface")
                    for v in views:
                        out = f"{ROOT}/{c:%Y%m%d%H}/t850-{a.model}/step/{v}/{vt}"; render_t850(a.model, c, s, lat, lon, t, z, u, w, v, out, sp); print("ok", out, flush=True)
            except StopIteration as e:
                print(f"step {s}: {e}, skipped", flush=True)
            tot += st.bytes
        print(f"{MODELS[a.model]['name']} {c:%Y%m%d%H}Z downloaded {tot/1e6:.1f} MB")
        sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
    zorog = None
    for s in ([int(x) for x in a.steps.split(",")] if a.steps else steps(a.hours, a.every)):
        st = Step(a.model, c, s); vt = f"{c + dt.timedelta(hours=s):%Y%m%d%H}"
        try:
            if "t2manom" in a.products:
                if zorog is None:   # model terrain (surface geopotential) is only in the step-0 file
                    _, _, zorog = Step(a.model, c, 0).field("z"); zorog = zorog / 9.80665
                lat, lon, t2 = st.field("2t")
                for v in a.views.split(","):
                    out = f"{ROOT}/{c:%Y%m%d%H}/t2manom-{a.model}/step/{v}/{vt}"; render_t2manom(a.model, c, s, lat, lon, t2, zorog, v, out); print("ok", out, flush=True)
            if "t850anom" in a.products.split(","):
                lat, lon, t = st.field("t", 850, "pl"); _, _, z = st.field("gh", 850, "pl"); _, _, sp = st.field("sp")
                M_ = MODELS[a.model]; who = dict(name=M_["name"], res=M_["res"], site=M_["site"], credit=CREDIT.format(name=M_["name"]))
                for v in a.views.split(","):
                    if v not in T8A_VIEWS: continue
                    out = f"{ROOT}/{c:%Y%m%d%H}/t850anom-{a.model}/step/{v}/{vt}"; render_t850anom(c, s, lat, lon, t, v, out, who, gh=z, sp=sp); print("ok", out, flush=True)
            if "t2m" in a.products.split(","):
                lat, lon, t2 = st.field("2t")
                try: oro = ecmwf_orog(a.model, c) if "wa" in a.views.split(",") else None
                except StopIteration: oro = None
                for v in a.views.split(","):
                    out = f"{ROOT}/{c:%Y%m%d%H}/t2m-{a.model}/step/{v}/{vt}"; render_t2m(a.model, c, s, lat, lon, t2, v, out, oro); print("ok", out, flush=True)
            if "t850" in a.products.split(","):
                lat, lon, t = st.field("t", 850, "pl"); _, _, z = st.field("gh", 850, "pl")
                _, _, u = st.field("u", 850, "pl"); _, _, w = st.field("v", 850, "pl"); _, _, sp = st.field("sp")
                for v in a.views.split(","):
                    if (a.model == "aifs" and v == "wa") or v == "pnwt": continue   # no WA view for AIFS upper air; no tight view aloft
                    out = f"{ROOT}/{c:%Y%m%d%H}/t850-{a.model}/step/{v}/{vt}"; render_t850(a.model, c, s, lat, lon, t, z, u, w, v, out, sp); print("ok", out, flush=True)
        except StopIteration:
            print(f"step {s}: field missing in this run, skipped", flush=True)
        tot += st.bytes
    print(f"{MODELS[a.model]['name']} {c:%Y%m%d%H}Z downloaded {tot/1e6:.1f} MB")
    sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
