#!/usr/bin/env python3
"""ECMWF AIFS (AI model) upper-air/surface products: 500 mb height anomaly + heights, and MSLP isobars with H/L. North America,
Pacific NW and Pacific NW tight (MSLP and MSLP + wind only) views. The same renderers draw the two GFS maps (gfs_maps.py).

AIFS: ECMWF open data aifs-single 0.25 deg (CC BY 4.0). Climatology: NCEP/NCAR Reanalysis 1 monthly long-term
mean 1991-2020, 500 mb geopotential height (NOAA PSL, public domain), linearly interpolated in time to the valid
date and bilinearly to 0.25 deg. Basemap: Natural Earth (public domain). NOT scheduled; run by hand:
  python tools/forecast/aifs_maps.py [--cycle YYYYMMDDHH] [--hours 240] [--every 6] [--views na,pnw,pnwt]
Writes $SITE_BATCH (default .site_batch)/<cycle>/aifs500/step/<view>/<valid>/final.jpg + site_frame.json.
"""
import sys, argparse, datetime as dt, json, os, urllib.request
from zoneinfo import ZoneInfo
import numpy as np, eccodes as ec
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm, ListedColormap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house_style as HS
import cartopy.crs as ccrs, cartopy.feature as cf
import fastgeo  # noqa: F401  speed_build_v1: faster contour/contourf/barbs/quiver (WX_FASTGEO=0 = off)
from scipy.interpolate import RegularGridInterpolator

PT = ZoneInfo("America/Los_Angeles")
ROOT = os.environ.get("SITE_BATCH", ".site_batch")
CLIM = f"{ROOT}/clim/ncep_hgt500_mon_ltm_1991_2020.npz"
BASE = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/aifs-single/0p25/oper/{d}{h:02d}0000-{s}h-oper-fc"
CREDIT = ("AIFS: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int.  "
          "Climatology: NCEP/NCAR Reanalysis 1991-2020 mean, NOAA PSL.  Basemap: Natural Earth.")
# Scales, palettes, marker sizes and key labels come from house_style.py (shared by every model; see STYLE_RULES.md).
LEVELS, ANOM_TICKS, CMAP = HS.ANOM_LEVELS, HS.ANOM_TICKS, HS.anom_cmap()
MSLP_LEVELS, MSLP_TICKS, MSLP_CMAP = HS.MSLP_LEVELS, HS.MSLP_TICKS, HS.mslp_cmap()
VIEWS = {
    # North America view (10-24-26): centered on the Pacific Northwest and reaching out over the NE Pacific (Gulf of Alaska, Hawaii)
    # while keeping CONUS through Maine. Same 9,000 x 6,700 km frame as before (was central_longitude=-100, x -4.6e6..4.4e6).
    "na": dict(label="North America", size=(16, 12),
               proj=ccrs.LambertConformal(central_longitude=-120, central_latitude=48, standard_parallels=(35, 60)),
               extent=(-4.67e6, 4.33e6, -3.3e6, 3.4e6), cint=6),
    "pnw": dict(label="Pacific Northwest", size=(16, 10.5), proj=ccrs.Mercator(central_longitude=-130),
                ll=(-160, -103, 37, 61), cint=3),
    # Pacific NW tight: same frame as temp_maps / ens_maps (Mercator 138 W-113.5 W, 40.5-54.5 N)
    "pnwt": dict(label="Pacific NW tight", size=(16, 10.5), proj=ccrs.Mercator(central_longitude=-126),
                 ll=(-138.0, -113.5, 40.5, 54.5), cint=3),
}
NO_PNWT = ("z500",)   # AIFS 500 mb anomaly stays na/pnw (Benjamin 10-24-26: tight view on SLP + SLP/wind only)
# Who drew the map: header name, sidecar model, credit line. "gfs" is used by gfs_maps.py (NOAA, public domain).
SRC = {"aifs": dict(name="ECMWF AIFS", site="AIFS", data="AIFS: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int."),
       "gfs": dict(name="NOAA GFS 0.25\u00b0", site="GFS", data="Data: NOAA GFS (public domain).")}


def get(url, rng=None):
    h = {"User-Agent": "wx-models (personal, not scheduled)"}
    if rng: h["Range"] = "bytes=%d-%d" % rng
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=90) as r:
        return r.read()


def latest_cycle():
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 36):
        c = now - dt.timedelta(hours=b)
        if c.hour % 6: continue
        try:
            get(BASE.format(d=f"{c:%Y%m%d}", h=c.hour, s=240) + ".index", (0, 10)); return c
        except Exception: pass
    raise SystemExit("no AIFS run found")


def field(c, step, param="gh", lev="500"):
    base = BASE.format(d=f"{c:%Y%m%d}", h=c.hour, s=step)
    r = next(json.loads(l) for l in get(base + ".index").decode().splitlines()
             if f'"param": "{param}"' in l and (lev is None or f'"levelist": "{lev}"' in l))
    g = ec.codes_new_from_message(get(base + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1)))
    ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
    la0, lo0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
    d = ec.codes_get(g, "iDirectionIncrementInDegrees")
    v = ec.codes_get_values(g).reshape(nj, ni); ec.codes_release(g)
    lat = la0 - d * np.arange(nj); lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180
    o = np.argsort(lon)
    return lat, lon[o], v[:, o], r["_length"]


def z500(c, step):
    lat, lon, v, n = field(c, step)
    return lat, lon, v / 10.0, n  # gpm -> dam


def clim_at(valid, lat, lon):
    z = np.load(CLIM); h, cl, co = z["hgt"], z["lat"], z["lon"]
    # monthly means centred on the 15th; linear weight between neighbouring months
    m = valid.month - 1; mid = valid.replace(day=15, hour=0, minute=0, second=0)
    m2 = (m + (1 if valid >= mid else -1)) % 12
    w = abs((valid - mid).total_seconds()) / (30.4 * 86400)
    f = (1 - w) * h[m] + w * h[m2]
    f = np.concatenate([f, f[:, :1]], 1); co = np.append(co, 360.0)
    it = RegularGridInterpolator((cl[::-1], co), f[::-1] / 10.0)
    LA, LO = np.meshgrid(lat, lon % 360, indexing="ij")
    return it(np.stack([LA, LO], -1))


def render(c, step, lat, lon, z, anom, vid, out, src="aifs"):
    V = VIEWS[vid]; SR = SRC[src]; valid = c + dt.timedelta(hours=step); vl = valid.astimezone(PT)
    fig = plt.figure(figsize=V["size"], dpi=150); fig.patch.set_facecolor(HS.BG)
    key_y, top = HS.layout(fig)
    ax = fig.add_axes([0.024, 0.045, 0.952, top - 0.045], projection=V["proj"])
    if "extent" in V: ax.set_extent(V["extent"], crs=V["proj"])
    else: ax.set_extent(V["ll"], crs=ccrs.PlateCarree())
    # work in 0-360 longitudes so the North America frame can reach past the dateline
    l360 = lon % 360; o = np.argsort(l360); l360 = l360[o]; anom = anom[:, o]; z = z[:, o]
    sl = (lat > 0) & (lat < 88) if vid == "na" else (lat > 25) & (lat < 72)
    so = (l360 > 120) & (l360 < 355) if vid == "na" else (l360 > 180) & (l360 < 275)
    LA, LO = lat[sl], l360[so]; A = anom[np.ix_(sl, so)] * 10.0; Z = z[np.ix_(sl, so)]  # anomaly dam -> m
    pc = ccrs.PlateCarree()
    cs = ax.contourf(LO, LA, A, levels=LEVELS, cmap=CMAP, norm=BoundaryNorm(LEVELS, CMAP.N), extend="both", transform=pc)
    HS.outlines(ax, cf)
    ci = V["cint"]
    hc = ax.contour(LO, LA, Z, levels=np.arange(480, 612, ci), colors="#101114", linewidths=1.25, transform=pc, zorder=4)
    for t in ax.clabel(hc, fmt="%d", inline=True, inline_spacing=6):
        t.set_fontproperties(HS.font(700, 10)); t.set_path_effects(HS.halo("white", 3.2))
    ax.gridlines(color="#00000026", lw=0.5, linestyle=":")
    HS.frame(ax)
    vis = A[np.isfinite(A)]
    HS.header(fig, "500 mb Height Anomaly", f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT",
              f"{SR['name']} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {V['label']}  \u00b7  heights every {ci} dam  \u00b7  {vis.min():+.0f} to {vis.max():+.0f} m in view",
              f"F+{step}", f"{valid:%HZ %a}".upper())
    HS.hbar(fig, cs, ANOM_TICKS, "Anomaly (m)", key_y, signed=True)
    HS.credit(fig, CREDIT if src == "aifs" else SR["data"] + "  Climatology: NCEP/NCAR Reanalysis 1991-2020 mean, NOAA PSL.  Basemap: Natural Earth.")
    os.makedirs(out, exist_ok=True)
    fig.savefig(f"{out}/final.png", facecolor=fig.get_facecolor()); plt.close(fig)
    from PIL import Image
    Image.open(f"{out}/final.png").convert("RGB").save(f"{out}/final.jpg", quality=90); os.remove(f"{out}/final.png")
    json.dump({"tab": "aifs500", "period": "step", "view": vid, "model": SR["site"], "cycle": f"{c:%Y%m%d%H}",
               "start_pt": vl.isoformat(), "end_pt": vl.isoformat()}, open(f"{out}/site_frame.json", "w"))


def frame_ax(V, vid, key=True):
    fig = plt.figure(figsize=V["size"], dpi=150); fig.patch.set_facecolor(HS.BG)
    key_y, top = HS.layout(fig, key)
    ax = fig.add_axes([0.024, 0.045, 0.952, top - 0.045], projection=V["proj"])
    if "extent" in V: ax.set_extent(V["extent"], crs=V["proj"])
    else: ax.set_extent(V["ll"], crs=ccrs.PlateCarree())
    return fig, ax, key_y


def render_mslp(c, step, lat, lon, p, vid, out, wind=None, src="aifs"):
    """Filled sea-level pressure (house_style scale) with dark labeled isobars and H/L centers with central pressure.
    No thickness lines on this map (see STYLE_RULES.md). With wind=(u10, v10) in m/s on the same grid: the
    'MSLP + 10 m Wind' product instead (10 m wind speed fill in mph, haloed isobars, barbs in kt, same H/L rules)."""
    from scipy.ndimage import maximum_filter, minimum_filter, gaussian_filter, uniform_filter
    V = VIEWS[vid]; SR = SRC[src]; valid = c + dt.timedelta(hours=step); vl = valid.astimezone(PT)
    l360 = lon % 360; o = np.argsort(l360); l360 = l360[o]; p = p[:, o] / 100.0
    sl = (lat > 0) & (lat < 88) if vid == "na" else (lat > 25) & (lat < 72)
    so = (l360 > 120) & (l360 < 355) if vid == "na" else (l360 > 180) & (l360 < 275)
    LA, LO = lat[sl], l360[so]; P = p[np.ix_(sl, so)]
    fig, ax, key_y = frame_ax(V, vid); pc = ccrs.PlateCarree()
    Ps = gaussian_filter(P, 1.5)
    if wind is None:
        fill = ax.contourf(LO, LA, Ps, levels=MSLP_LEVELS, cmap=MSLP_CMAP, norm=BoundaryNorm(MSLP_LEVELS, MSLP_CMAP.N), extend="both", transform=pc)
    else:
        U = wind[0][:, o][np.ix_(sl, so)]; Vw = wind[1][:, o][np.ix_(sl, so)]
        spd = gaussian_filter(np.hypot(U, Vw) * 2.23694, 1.0)  # m/s -> mph
        wc = HS.wind_cmap()
        fill = ax.contourf(LO, LA, spd, levels=HS.WIND_LEVELS, cmap=wc, norm=BoundaryNorm(HS.WIND_LEVELS, wc.N), extend="max", transform=pc)
    HS.outlines(ax, cf)
    ci = 4 if vid == "na" else 2
    clabels = []
    cs = ax.contour(LO, LA, Ps, levels=np.arange(880, 1080, ci), colors=HS.ISOBAR_COLOR, linewidths=HS.ISOBAR_LW, transform=pc, zorder=4)
    if wind is not None:
        cs.set(path_effects=HS.halo("white", HS.ISOBAR_HALO))
        fw, fh = fig.get_size_inches() * ax.get_position().size; nx = HS.BARBS_ACROSS[vid]; ny = max(4, round(nx * fh / fw))
        ax.barbs(LO, LA, U * 1.94384, Vw * 1.94384, transform=pc, regrid_shape=(nx, ny), length=HS.BARB_LENGTH, color=HS.BARB_COLOR,
                 linewidth=HS.BARB_LW, zorder=5)
    # Isobar labels sit on a white halo (not cut into the line) so any near an H/L marker can be removed cleanly.
    labels = ax.clabel(cs, fmt="%d", inline=False); clabels += labels
    for t in labels:
        t.set_fontproperties(HS.font(700, 10)); t.set_path_effects(HS.halo("white", 3.2))
    # H / L centers: neighborhood extrema over HS.HL_RADIUS_KM with a prominence test (house_style.find_centers)
    S = gaussian_filter(P, 3 if vid == "na" else 2)
    x0, x1, y0, y1 = ax.get_extent(V["proj"]); mx, my = 0.02 * (x1 - x0), 0.04 * (y1 - y0)
    XY = {}

    def inside(i, j):
        x, y = V["proj"].transform_point(LO[j], LA[i], pc)
        cx, cy = min(max(x, x0 + mx), x1 - mx), min(max(y, y0 + my), y1 - my); XY[i, j] = (cx, cy)
        if (cx, cy) == (x, y):
            return True
        clo, cla = pc.transform_point(cx, cy, V["proj"])  # center outside the frame: pin to the edge if it is close
        return HS.km_between(LA[i], LO[j], cla, clo) <= HS.HL_EDGE_KM[vid]

    markers = []
    for i, j, ch in HS.find_centers(S, LA, LO, HS.HL_RADIUS_KM[vid], HS.HL_PROMINENCE_MB[vid], inside):
        x, y = XY[i, j]; col = HS.H_COLOR if ch == "H" else HS.L_COLOR
        win = P[max(0, i - 3):i + 4, max(0, j - 3):j + 4]; val = win.max() if ch == "H" else win.min()
        markers.append(ax.text(x, y, ch, color=col, fontproperties=HS.font(900, HS.HL_SIZE), ha="center", va="center",
                               transform=V["proj"], path_effects=HS.halo("white", HS.HL_HALO), zorder=6))
        markers.append(ax.annotate(f"{val:.0f}", (x, y), xycoords=V["proj"]._as_mpl_transform(ax), xytext=(0, HS.HL_VALUE_OFFSET),
                                   textcoords="offset points", color=col, fontproperties=HS.font(800, HS.HL_VALUE_SIZE), ha="center",
                                   va="center", path_effects=HS.halo("white", HS.HL_VALUE_HALO), zorder=6))
    HS.frame(ax)
    HS.header(fig, "Sea-Level Pressure" if wind is None else "MSLP + 10 m Wind", f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT",
              f"{SR['name']} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {V['label']}  \u00b7  isobars every {ci} mb"
              + ("" if wind is None else "  \u00b7  barbs in kt"),
              f"F+{step}", f"{valid:%HZ %a}".upper())
    if wind is None: HS.hbar(fig, fill, MSLP_TICKS, "Pressure (mb)", key_y)
    else: HS.hbar(fig, fill, HS.WIND_TICKS, "10 m wind (mph)", key_y)
    HS.credit(fig, SR["data"] + "  Basemap: Natural Earth.")
    HS.clear_labels_near(fig, clabels, markers)
    os.makedirs(out, exist_ok=True)
    fig.savefig(f"{out}/final.png", facecolor=fig.get_facecolor()); plt.close(fig)
    from PIL import Image
    Image.open(f"{out}/final.png").convert("RGB").save(f"{out}/final.jpg", quality=90); os.remove(f"{out}/final.png")
    json.dump({"tab": "aifsmslp" if wind is None else "aifswind", "period": "step", "view": vid, "model": SR["site"], "cycle": f"{c:%Y%m%d%H}",
               "start_pt": vl.isoformat(), "end_pt": vl.isoformat()}, open(f"{out}/site_frame.json", "w"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle"); ap.add_argument("--hours", type=int, default=240); ap.add_argument("--every", type=int, default=6)
    ap.add_argument("--views", default="na,pnw,pnwt")
    ap.add_argument("--products", default="z500,mslp,wind")
    a = ap.parse_args()
    c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else latest_cycle()
    tot = 0
    for s in range(0, a.hours + 1, a.every):
        vt = f"{c + dt.timedelta(hours=s):%Y%m%d%H}"
        if "z500" in a.products:
            lat, lon, z, n = z500(c, s); tot += n
            an = z - clim_at(c + dt.timedelta(hours=s), lat, lon)
            for v in a.views.split(","):
                if v == "pnwt" and "z500" in NO_PNWT: continue
                out = f"{ROOT}/{c:%Y%m%d%H}/aifs500/step/{v}/{vt}"
                render(c, s, lat, lon, z, an, v, out); print("ok", out, flush=True)
        msl = None   # speedup (10-23-26): the MSLP field is fetched once per step and reused by the wind product
        if "mslp" in a.products:
            msl = field(c, s, "msl", None); lat, lon, p, n = msl; tot += n
            for v in a.views.split(","):
                out = f"{ROOT}/{c:%Y%m%d%H}/aifsmslp/step/{v}/{vt}"
                render_mslp(c, s, lat, lon, p, v, out); print("ok", out, flush=True)
        if "wind" in a.products:
            if msl is None: msl = field(c, s, "msl", None); tot += msl[3]
            lat, lon, p, n = msl
            _, _, u, n1 = field(c, s, "10u", None); _, _, w, n2 = field(c, s, "10v", None); tot += n1 + n2
            for v in a.views.split(","):
                out = f"{ROOT}/{c:%Y%m%d%H}/aifswind/step/{v}/{vt}"
                render_mslp(c, s, lat, lon, p, v, out, wind=(u, w)); print("ok", out, flush=True)
    print(f"AIFS {c:%Y%m%d%H}Z downloaded {tot/1e6:.1f} MB")
    # eccodes/cartopy can crash in interpreter teardown (double free, exit 134) after all files are written:
    # flush and leave without running native destructors.
    sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
