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
Writes $SITE_BATCH/<cycle>/<t2m|t850|t2manom>-<model>/step/<view>/<valid>/final.jpg + site_frame.json (model "ECMWF 9 km" or "AIFS").
"""
import sys, argparse, datetime as dt, json, os, urllib.request, urllib.error
from zoneinfo import ZoneInfo
import numpy as np, eccodes as ec
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house_style as HS
import cartopy.crs as ccrs, cartopy.feature as cf
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
            try:
                get(HIRES[m]["url"].format(d=f"{c:%Y%m%d}", h=c.hour, s=HIRES[m]["hours"]) + ".idx", (0, 10)); return c
            except Exception: pass
        raise SystemExit("no long run found")
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 48):
        c = now - dt.timedelta(hours=b)
        if c.hour % 12: continue   # menu_v2: globals 00Z + 12Z only
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


def towns(ax, vid):
    """Town dots and names on the Washington view only (dark text on a white halo, like the contour labels)."""
    if vid != "wa": return
    pc = ccrs.PlateCarree()
    for name, la, lo, side in WA_TOWNS:
        ax.plot(lo, la, "o", ms=3.6, mfc="#1b1d22", mec="white", mew=1.0, transform=pc, zorder=7)
        ax.annotate(name, (lo, la), xycoords=pc._as_mpl_transform(ax), xytext=(5 if side == "r" else -5, 0), textcoords="offset points",
                    ha="left" if side == "r" else "right", va="center", color="#1b1d22", fontproperties=HS.font(600, 9.5),
                    path_effects=HS.halo("white", 2.6), zorder=7)


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


def render_t2m(m, c, step, lat, lon, t2k, vid, out):
    LA, LO, (T,) = cut(lat, lon, [t2k], vid)
    F = (T - 273.15) * 1.8 + 32
    if SMOOTH[vid]: F = gaussian_filter(F, SMOOTH[vid])
    fig, ax, key_y = frame(vid); pc = ccrs.PlateCarree(); cm = HS.temp_cmap()
    fill = ax.contourf(LO, LA, F, levels=HS.TEMP_LEVELS, cmap=cm, norm=BoundaryNorm(HS.TEMP_LEVELS, cm.N), extend="both", transform=pc)
    HS.outlines(ax, cf, res="10m" if vid == "wa" else "50m")
    freeze_line(ax, LO, LA, F, 32)
    towns(ax, vid)
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
    towns(ax, vid)
    HS.frame(ax)
    lo, hi = np.nanpercentile(A, [0.5, 99.5])
    vl = header(fig, m, c, step, vid, "2 m Temperature Anomaly",
                f"vs 1991-2020 normal for the date and hour  \u00b7  {lo:+.0f} to {hi:+.0f}\u00b0F in view")
    HS.credit(fig, CREDIT.format(name=MODELS[m]["name"]) + CREDIT_CLIM)
    HS.hbar(fig, fill, T2A_TICKS, "Anomaly (\u00b0F)", key_y, signed=True)
    save(fig, out, {"tab": "t2manom", "period": "step", "view": vid, "model": MODELS[m]["site"], "cycle": f"{c:%Y%m%d%H}",
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
                    for v in views:
                        out = f"{ROOT}/{c:%Y%m%d%H}/t2m-{a.model}/step/{v}/{vt}"; render_t2m(a.model, c, s, lat, lon, t2, v, out); print("ok", out, flush=True)
                if "t850" in a.products and "t850" in HIRES[a.model]["products"]:
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
            if "t2m" in a.products.split(","):
                lat, lon, t2 = st.field("2t")
                for v in a.views.split(","):
                    out = f"{ROOT}/{c:%Y%m%d%H}/t2m-{a.model}/step/{v}/{vt}"; render_t2m(a.model, c, s, lat, lon, t2, v, out); print("ok", out, flush=True)
            if "t850" in a.products:
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
