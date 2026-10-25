#!/usr/bin/env python3
"""Menu products for the forecast site, one renderer for every model (menu_v2):
  gust10    10 m Wind Gusts            peakgust  Peak Gust So Far (run max)
  feels     Feels-Like Temp            t925/t700/t500/t300  Temp + Barbs at that level
  td2m      2 m Dewpoint               mslpptype MSLP + P-Type (instant)      (+ precip, snow, aloft, sky products below)
Models: ifs (ECMWF 9 km open data), aifs (ECMWF AIFS), hrrr, rrfs (NOAA 3 km). GFS has no menu products since 10-24-26
(only gfs_maps.py: 500 mb anomaly + sea-level pressure); the Reader below still serves GFS for gfs_maps.py.
Methods are standard and written next to each product. NOAA data: public domain. ECMWF: CC BY 4.0.
NOT scheduled; run by hand:
  python menu_maps.py --model ifs|aifs|hrrr|rrfs [--cycle YYYYMMDDHH] [--steps 3,6 | --hours 72 --every 6]
                      [--products gust10,peakgust,...] [--views na,pnw,pnwt,wa] [--count]
  --count: print how many map files the run would write (no downloads, no renders).
Writes $SITE_BATCH/<cycle>/<product>-<model>/step/<view>/<valid>/final.jpg + site_frame.json.
"""
import sys, argparse, datetime as dt, json, os, threading, time, traceback, warnings
import numpy as np, eccodes as ec
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house_style as HS
import temp_maps as TM
import cartopy.crs as ccrs, cartopy.feature as cf
from scipy.ndimage import gaussian_filter, binary_dilation

PT, ROOT, get = TM.PT, TM.ROOT, TM.get
MPH, KT = 2.23694, 1.94384
GFS = "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{d}/{h:02d}/atmos/gfs.t{h:02d}z.pgrb2.0p25.f{s:03d}"
MODELS = {
    "ifs": dict(site="ECMWF 9 km", name="ECMWF IFS", res="0.1\u00b0", kind="ecmwf"),
    "aifs": dict(site="AIFS", name="ECMWF AIFS", res="0.25\u00b0", kind="ecmwf"),
    "gfs": dict(site="GFS", name="NOAA GFS", res="0.25\u00b0", kind="idx", url=GFS),
    "hrrr": dict(site="HRRR", name="NOAA HRRR", res="3 km", kind="idx", url=TM.HRRR, lambert=True,
                 prs=TM.HRRR.replace("wrfsfcf", "wrfprsf")),   # pressure levels (25 mb spacing) live in the prs file
    "rrfs": dict(site="RRFS", name="NOAA RRFS", res="3 km", kind="idx", url=TM.RRFS, lambert=True),
}
HIRES = ("hrrr", "rrfs")
# canonical field -> (ECMWF param, level, kind) and (NOAA idx "VAR:level")
EC = {"gust": ("10fg", None, "sfc"), "t2m": ("2t", None, "sfc"), "td2m": ("2d", None, "sfc"), "u10": ("10u", None, "sfc"),
      "v10": ("10v", None, "sfc"), "msl": ("msl", None, "sfc"), "sp": ("sp", None, "sfc"), "ptype": ("ptype", None, "sfc"),
      "prate": ("tprate", None, "sfc"), "sf": ("sf", None, "sfc"), "tp": ("tp", None, "sfc"), "pwat": ("tcwv", None, "sfc"), "tcc": ("tcc", None, "sfc")}
NO = {"gust": "GUST:surface", "t2m": "TMP:2 m above ground", "td2m": "DPT:2 m above ground", "u10": "UGRD:10 m above ground",
      "v10": "VGRD:10 m above ground", "msl": "PRMSL:mean sea level", "sp": "PRES:surface", "prate": "PRATE:surface",
      "pwat": "PWAT:entire atmosphere (considered as a single layer)", "orog": "HGT:surface", "crain": "CRAIN:surface", "csnow": "CSNOW:surface", "cfrzr": "CFRZR:surface", "cicep": "CICEP:surface"}
NO_HIRES_MSL = "MSLMA:mean sea level"
NO_BY = {"tcc": {"gfs": "TCDC:entire atmosphere", "hrrr": "TCDC:entire atmosphere", "rrfs": "TCDC:entire atmosphere (considered as a single layer)"},
         "vis": {"gfs": "VIS:surface", "hrrr": "VIS:surface", "rrfs": "VIS:surface"},
         "ir": {"hrrr": "SBT124:top of atmosphere", "rrfs": "SBTA1613:top of atmosphere"}}   # 10.7 um GOES imager ch4 / ABI band 13
LEVELS = (1000, 925, 850, 700, 500, 300, 250)


class Reader:
    """One model step. f(name) returns (lat, lon, values) in SI units; 'T:850', 'U:850', 'V:850', 'Z:850' (gpm) for levels.
    Winds come back earth-relative. Raises KeyError when the model does not carry the field."""
    def __init__(self, m, c, s):
        self.m, self.c, self.s, self.cache, self.bytes, self.idxs = m, c, s, {}, 0, {}
        self._locks, self._lk = {}, threading.Lock()   # one lock per field, so prefetch threads never fetch a field twice
        if MODELS[m]["kind"] == "ecmwf": self.st = TM.Step(m, c, s)
        else:
            self.url = MODELS[m]["url"].format(d=f"{c:%Y%m%d}", h=c.hour, s=s)
            self.prs = MODELS[m]["prs"].format(d=f"{c:%Y%m%d}", h=c.hour, s=s) if "prs" in MODELS[m] else self.url

    def _locked(self, name, fn, *a):
        if name in self.cache: return self.cache[name]
        with self._lk: lk = self._locks.setdefault(name, threading.Lock())
        with lk:
            if name in self.cache: return self.cache[name]
            return fn(*a)

    def f(self, name):
        return self._locked(name, self._f, name)

    def _f(self, name):
        if name in self.cache: return self.cache[name]
        M = MODELS[self.m]
        if M["kind"] == "ecmwf":
            if ":" in name:
                v, lev = name.split(":"); r = self.st.field({"T": "t", "U": "u", "V": "v", "Z": "gh", "Q": "q"}[v], int(lev), "pl")
            else:
                if name == "orog":   # model terrain: surface geopotential, only in the step-0 file
                    la_, lo_, zz = TM.Step(self.m, self.c, 0).field("z"); self.cache[name] = r = (la_, lo_, zz / 9.80665); return r
                if name not in EC or (self.m == "aifs" and name in ("gust", "ptype", "prate", "sf")): raise KeyError(name)
                par = "tcw" if (self.m == "aifs" and name == "pwat") else EC[name][0]
                try: r = self.st.field(par)
                except StopIteration: raise KeyError(name)
            self.bytes = self.st.bytes
        else:
            if ":" in name:
                v, lev = name.split(":"); key = f"{ {'T': 'TMP', 'U': 'UGRD', 'V': 'VGRD', 'Z': 'HGT', 'Q': 'SPFH'}[v]}:{lev} mb"
            else:
                key = NO_HIRES_MSL if (name == "msl" and self.m in HIRES) else (NO_BY[name].get(self.m) if name in NO_BY else NO.get(name))
                if key is None: raise KeyError(name)
            src = self.prs if " mb" in key else self.url
            r = self._idx(key, src)
            if M.get("lambert") and name.split(":")[0] in ("u10", "U") :
                vv = self._idx(key.replace("UGRD", "VGRD"), src); u, w = TM.earth_relative(r[2], vv[2], r[1], self.m)
                self.cache[name.replace("u10", "v10").replace("U:", "V:")] = (r[0], r[1], w); r = (r[0], r[1], u)
            elif M.get("lambert") and name.split(":")[0] in ("v10", "V"):
                self.f(name.replace("v10", "u10").replace("V:", "U:")); return self.cache[name]
        self.cache[name] = r
        return r

    def acc0(self, key):
        """NOAA run-total accumulation 'VAR:level' from 0 h to this step (0 at step 0)."""
        n = f"acc0:{key}"
        def go():
            self.cache[n] = self._idx(key, self.url, ("0-%d hour acc fcst" % self.s, "0-%d day acc fcst" % (self.s // 24))); return self.cache[n]
        return self._locked(n, go)

    def ave(self, key):
        """NOAA bucket-average record (e.g. CSNOW over the last output interval)."""
        n = f"ave:{key}"
        def go():
            self.cache[n] = self._idx(key, self.url, "ave"); return self.cache[n]
        return self._locked(n, go)

    def _idx(self, key, url, mode=None):
        with self._lk: lk = self._locks.setdefault("idx:" + url, threading.Lock())
        with lk:
            if url not in self.idxs: self.idxs[url] = get(url + ".idx").decode().splitlines()
        idx = self.idxs[url]
        for k, l in enumerate(idx):
            p = l.split(":")
            ok = (not any(w in p[5] for w in ("ave", "acc", "max", "min"))) if (len(p) > 5 and mode is None) else \
                 (len(p) > 5 and ((mode == "ave" and "ave" in p[5]) or (isinstance(mode, tuple) and p[5] in mode)))
            if len(p) > 5 and f"{p[3]}:{p[4]}" == key and ok:
                a = int(p[1]); b = int(idx[k + 1].split(":")[1]) - 1 if k + 1 < len(idx) else None
                blob = get(url, (a, b if b is not None else a + 40_000_000)); self.bytes += len(blob)
                g = ec.codes_new_from_message(blob); v = ec.codes_get_values(g)
                if ec.codes_get(g, "gridType") == "regular_ll":
                    ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
                    la0, la1 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "latitudeOfLastGridPointInDegrees")
                    lo0, d = ec.codes_get(g, "longitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "iDirectionIncrementInDegrees")
                    ec.codes_release(g); v = v.reshape(nj, ni)
                    lat = np.linspace(la0, la1, nj); lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180; o = np.argsort(lon)
                    return lat, lon[o], v[:, o]
                ni, nj = ec.codes_get(g, "Nx"), ec.codes_get(g, "Ny")
                la = ec.codes_get_array(g, "latitudes"); lo = ec.codes_get_array(g, "longitudes"); ec.codes_release(g)
                lo = np.where(lo > 180, lo - 360, lo)
                return la.reshape(nj, ni), lo.reshape(nj, ni), v.reshape(nj, ni)
        raise KeyError(key)


# ---------------------------------------------------------------------------------------------- scales (site-local)
def ramp(levels, anchors, under=None, over=None):
    mids = (np.asarray(levels[:-1], float) + np.asarray(levels[1:], float)) / 2.0
    cols = HS.smooth(mids, [a for a, _ in anchors], [c for _, c in anchors])
    return HS.cmap(cols, under or anchors[0][1], over or anchors[-1][1])

DEW_LEVELS = np.arange(-20, 82, 2)
DEW_ANCH = [(-20, "#4a2f22"), (0, "#7d5636"), (20, "#b08d5e"), (32, "#ddd0a8"), (40, "#cfe6b0"), (48, "#86c97a"), (55, "#2f9e5b"),
            (60, "#13806a"), (65, "#1b6f9c"), (70, "#2f4fb8"), (75, "#5b36a8"), (80, "#8a2593")]
H500_LEVELS = np.arange(480, 607, 3)
H500_ANCH = [(480, "#2a1f55"), (504, "#3c3f9e"), (522, "#3f74bd"), (538, "#6aaac4"), (552, "#a6d1a0"), (564, "#e9dc8c"),
             (576, "#f2b066"), (588, "#de6f45"), (600, "#9c2f3a")]
RATE_LEVELS = [0.01, 0.02, 0.04, 0.06, 0.1, 0.15, 0.2, 0.3, 0.5, 0.75, 1.0]
FZR_ANCH = [(0.01, "#ffd3c4"), (0.1, "#f2785b"), (0.3, "#c9302c"), (1.0, "#6d0f1f")]
ALOFT = {925: (-40, 30, 3), 850: (-40, 30, 3), 700: (-45, 20, 3), 500: (-55, 0, 6), 300: (-70, -25, 12)}   # C range, height interval dam


def aloft_cmap(lev):
    lo, hi, _ = ALOFT[lev]; L = np.arange(lo, hi + 1, 1)
    if lev in (925, 850, 700):   # same palette as 2 m / 850 maps at the same temperature
        cols = [HS.temp_color(((a + b) / 2) * 1.8 + 32) for a, b in zip(L[:-1], L[1:])]
    else:                         # upper levels: the temperature palette stretched over that level's normal range
        cols = [HS.temp_color(-40 + ((a + b) / 2 - lo) / (hi - lo) * 140) for a, b in zip(L[:-1], L[1:])]
    return L, HS.cmap(cols, HS.temp_color(-45), HS.temp_color(125))


# ---------------------------------------------------------------------------------------------- drawing helpers
def views_for(m, wanted, allowed_global, allowed_hires):
    if m in HIRES:
        w = ["pnwhr" if v == "pnw" else v for v in wanted]; return [v for v in dict.fromkeys(w) if v in allowed_hires]
    return [v for v in wanted if v in allowed_global]


# ---- speed_build_v1 switches (each can be turned off on its own; all on by default)
#   MENU_FASTCONTOUR=0  contour in lon/lat and let Cartopy project every polygon (old, slow)
#   MENU_FASTVEC=0      barbs/arrows thinned by Cartopy's full-grid griddata (old, about 30 s per call on 0.1 deg grids)
FAST_CONTOUR = os.environ.get("MENU_FASTCONTOUR", "1") != "0"
FAST_VEC = os.environ.get("MENU_FASTVEC", "1") != "0"
_XY = {}


def proj_xy(ax, LO, LA):
    proj = getattr(ax, "projection", ax)
    """Grid points in the map's own projection, cached per (projection, grid), so contouring happens in map space
    (Cartopy's transform_first idea) and the grid is projected once per view instead of every polygon every frame."""
    LO, LA = np.asarray(LO), np.asarray(LA)
    k = (id(proj), LO.shape, LA.shape, float(LO.flat[0]), float(LO.flat[-1]), float(LA.flat[0]), float(LA.flat[-1]))
    if k not in _XY:
        lo2, la2 = (LO, LA) if LO.ndim == 2 else np.meshgrid(LO, LA)
        P = proj.transform_points(ccrs.PlateCarree(), lo2.astype(float), la2.astype(float))
        X, Y = P[..., 0], P[..., 1]
        bad = ~np.isfinite(X) | ~np.isfinite(Y)
        if bad.any(): X, Y = np.where(bad, np.nanmax(X), X), np.where(bad, np.nanmax(Y), Y)
        _XY[k] = (X, Y)
    return _XY[k]


def pc_contour(ax, kind, LO, LA, F, **kw):
    """ax.contour / ax.contourf for lon/lat data: fast path in projected space, or the old Cartopy path."""
    f = ax.contourf if kind == "f" else ax.contour
    if FAST_CONTOUR:
        X, Y = proj_xy(ax, LO, LA); return f(X, Y, F, transform=ax.projection, **kw)
    return f(LO, LA, F, transform=ccrs.PlateCarree(), **kw)


def thin_vectors(ax, LO, LA, U, V, nx, ny):
    """Same answer as Cartopy's regrid_shape=(nx, ny) (vectors rotated into the map projection, then linear Delaunay
    interpolation onto an nx x ny grid over the map extent), but each target point is interpolated from a small patch
    of the source grid around it instead of triangulating the whole grid (about 1.7 M points on the NA view) every call.
    Returns map-space X, Y, U, V for ax.barbs / ax.quiver with transform=ax.projection."""
    from scipy.spatial import Delaunay, cKDTree
    proj, pc = ax.projection, ccrs.PlateCarree(); x0, x1, y0, y1 = ax.get_extent(proj); xr, yr = x1 - x0, y1 - y0
    gx, gy = np.meshgrid(np.linspace(0, 1, nx), np.linspace(0, 1, ny)); XT, YT = gx * xr + x0, gy * yr + y0
    LO, LA = np.asarray(LO, float), np.asarray(LA, float)
    ll = pc.transform_points(proj, XT, YT); tlo, tla = ll[..., 0].ravel(), ll[..., 1].ravel()
    if LO.ndim == 1:   # regular lon/lat grid (lon may run 0-360 or past it): nearest row/column by search
        lon_ref = tlo % 360 if LO.max() > 180 else tlo
        jc = np.clip(np.searchsorted(LO, lon_ref), 0, LO.size - 1); ic = np.abs(LA[None, :] - tla[:, None]).argmin(1)
        get_patch = lambda i, j, r=3: np.meshgrid(np.arange(max(0, i - r), min(LA.size, i + r + 1)), np.arange(max(0, j - r), min(LO.size, j + r + 1)), indexing="ij")
        lo_of = lambda ii, jj: LO[jj]; la_of = lambda ii, jj: LA[ii]
    else:              # 2-D (Lambert 3 km) grid: nearest point by a KD-tree built once per grid
        kk = ("kd", LO.shape, float(LO.flat[0]), float(LA.flat[0]))
        if kk not in _XY: _XY[kk] = cKDTree(np.column_stack([LO.ravel(), LA.ravel()]))
        _, n = _XY[kk].query(np.column_stack([tlo, tla])); ic, jc = np.unravel_index(n, LO.shape)
        get_patch = lambda i, j, r=3: np.meshgrid(np.arange(max(0, i - r), min(LO.shape[0], i + r + 1)), np.arange(max(0, j - r), min(LO.shape[1], j + r + 1)), indexing="ij")
        lo_of = lambda ii, jj: LO[ii, jj]; la_of = lambda ii, jj: LA[ii, jj]
    uo = np.full(tlo.size, np.nan); vo = np.full(tlo.size, np.nan)
    for t in range(tlo.size):
        if not (np.isfinite(tlo[t]) and np.isfinite(tla[t])): continue
        ii, jj = get_patch(ic[t], jc[t]); ii, jj = ii.ravel(), jj.ravel()
        plo, pla = lo_of(ii, jj), la_of(ii, jj); pu, pv = np.asarray(U)[ii, jj], np.asarray(V)[ii, jj]
        P = proj.transform_points(pc, plo, pla); ok = np.isfinite(P[:, 0]) & np.isfinite(P[:, 1])
        if ok.sum() < 3: continue
        P = P[ok]; pu, pv, plo, pla = pu[ok], pv[ok], plo[ok], pla[ok]
        fin = np.isfinite(pu) & np.isfinite(pv)
        uu, vv = np.full(pu.shape, np.nan), np.full(pv.shape, np.nan)
        if fin.any(): uu[fin], vv[fin] = proj.transform_vectors(pc, plo[fin], pla[fin], pu[fin], pv[fin])
        pts = np.column_stack([(P[:, 0] - x0) / xr, (P[:, 1] - y0) / yr]); q = np.array([[gx.ravel()[t], gy.ravel()[t]]])
        try: tri = Delaunay(pts)
        except Exception: continue
        sx = int(tri.find_simplex(q)[0])
        if sx < 0: continue
        Tm = tri.transform[sx]; b = Tm[:2] @ (q[0] - Tm[2]); w = np.r_[b, 1 - b.sum()]; vx = tri.simplices[sx]
        uo[t], vo[t] = w @ uu[vx], w @ vv[vx]   # any NaN corner gives NaN, like griddata
    return XT, YT, uo.reshape(XT.shape), vo.reshape(XT.shape)


RASTER_FILL = os.environ.get("MENU_RASTERFILL", "0") == "1"   # part-two prototype (raster_fill.py); off by default


def fill(ax, LO, LA, F, L, cm, ext="both", z=1):
    if RASTER_FILL:
        import raster_fill as RF
        return RF.fill(ax, LO, LA, F, L, cm, ext, z, proj_xy(ax, LO, LA) if np.ndim(LO) == 2 else None)
    return pc_contour(ax, "f", LO, LA, F, levels=L, cmap=cm, norm=BoundaryNorm(L, cm.N), extend=ext, zorder=z)


def freeze_line(ax, LO, LA, F, level):
    cs = pc_contour(ax, "l", LO, LA, F, levels=[level], colors=HS.FREEZE_COLOR, linewidths=HS.FREEZE_LW, linestyles="dashed", zorder=4)
    cs.set(path_effects=HS.halo("white", 3.0))


def labelled(ax, LO, LA, Z, L, lw=None, color=None):
    hc = pc_contour(ax, "l", LO, LA, Z, levels=L, colors=color or HS.ISOBAR_COLOR, linewidths=lw or HS.ISOBAR_LW, zorder=4)
    hc.set(path_effects=HS.halo("white", HS.ISOBAR_HALO))
    lab = ax.clabel(hc, fmt="%d", inline=True, inline_spacing=6)
    for t in lab: t.set_fontproperties(HS.font(700, 10)); t.set_path_effects(HS.halo("white", 3.2))
    return lab


def barbs(fig, ax, LO, LA, U, V, vid):
    fw, fh = fig.get_size_inches() * ax.get_position().size; nx = HS.BARBS_ACROSS.get(vid, 20); ny = max(4, round(nx * fh / fw))
    st = dict(length=HS.BARB_LENGTH, color=HS.BARB_COLOR, linewidth=HS.BARB_LW, zorder=5)
    if FAST_VEC:
        X, Y, u, v = thin_vectors(ax, LO, LA, U * KT, V * KT, nx, ny); ax.barbs(X, Y, u, v, transform=ax.projection, **st)
    else: ax.barbs(LO, LA, U * KT, V * KT, transform=ccrs.PlateCarree(), regrid_shape=(nx, ny), **st)


def isobars_hl(fig, ax, LA, LO, P, vid):
    """Isobars every 4 mb, labeled, plus H/L centers (house_style rules)."""
    pc = ccrs.PlateCarree(); V = TM.VIEWS[vid]; hires = np.ndim(LA) == 2
    Ps = gaussian_filter(P, 6.0 if hires else (1.5 if vid != "wa" else 3.0))
    lab = labelled(ax, LO, LA, Ps, np.arange(880, 1080, 4))
    if hires: return lab, []   # 3 km grids: centers come out noisy; isobars only
    S = gaussian_filter(P, {"na": 3, "pnw": 2, "wa": 2}.get(vid, 2)); x0, x1, y0, y1 = ax.get_extent(V["proj"])
    mx, my = 0.02 * (x1 - x0), 0.04 * (y1 - y0); XY = {}; vk = vid if vid in HS.HL_RADIUS_KM else "pnw"

    def inside(i, j):
        x, y = V["proj"].transform_point(LO[j], LA[i], pc)
        cx, cy = min(max(x, x0 + mx), x1 - mx), min(max(y, y0 + my), y1 - my); XY[i, j] = (cx, cy)
        if (cx, cy) == (x, y): return True
        clo, cla = pc.transform_point(cx, cy, V["proj"]); return HS.km_between(LA[i], LO[j], cla, clo) <= HS.HL_EDGE_KM[vk]
    mk = []
    for i, j, ch in HS.find_centers(S, LA, LO, HS.HL_RADIUS_KM[vk], HS.HL_PROMINENCE_MB[vk], inside):
        x, y = XY[i, j]; col = HS.H_COLOR if ch == "H" else HS.L_COLOR
        w = P[max(0, i - 3):i + 4, max(0, j - 3):j + 4]; val = w.max() if ch == "H" else w.min()
        mk.append(ax.text(x, y, ch, color=col, fontproperties=HS.font(900, HS.HL_SIZE), ha="center", va="center", transform=V["proj"],
                          path_effects=HS.halo("white", HS.HL_HALO), zorder=6))
        mk.append(ax.annotate(f"{val:.0f}", (x, y), xycoords=V["proj"]._as_mpl_transform(ax), xytext=(0, HS.HL_VALUE_OFFSET),
                              textcoords="offset points", color=col, fontproperties=HS.font(800, HS.HL_VALUE_SIZE), ha="center",
                              va="center", path_effects=HS.halo("white", HS.HL_VALUE_HALO), zorder=6))
    return lab, mk


def credit(m):
    if m in ("gfs",) + HIRES: return "Data: NOAA (public domain).  Basemap: Natural Earth."
    return TM.CREDIT.format(name=MODELS[m]["name"])


def finish(fig, ax, m, c, step, vid, out, tab, title, extra, valid_start=None, period="step"):
    TM.towns(ax, vid); HS.frame(ax)
    valid = c + dt.timedelta(hours=step); vl = valid.astimezone(PT); M = MODELS[m]
    when = (f"{valid_start:%a %-I %p} to {vl:%a %-m-%-d %-I %p} PT" if period != "step" and valid_start is not None
            else f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT")
    HS.header(fig, title, when,
              f"{M['name']} {M['res']} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {TM.VIEWS[vid]['label']}  \u00b7  {extra}", f"F+{step}", f"{valid:%HZ %a}".upper())
    HS.credit(fig, credit(m))
    TM.save(fig, out, {"tab": tab, "period": period, "view": vid, "model": M["site"], "cycle": f"{c:%Y%m%d%H}",
                       "start_pt": (valid_start or vl).isoformat(), "end_pt": vl.isoformat()})


def outdir(c, prod, m, vid, step, period="step"):
    return f"{ROOT}/{c:%Y%m%d%H}/{prod}-{m}/{period}/{vid}/{c + dt.timedelta(hours=step):%Y%m%d%H}"


# ---------------------------------------------------------------------------------------------- products
def gust_fill(m, c, step, R, G, vid, out, tab, title, extra, valid_start=None):
    LA, LO, (F,) = TM.cut(GL[0], GL[1], [G * MPH], vid)
    if TM.SMOOTH.get(vid): F = gaussian_filter(F, TM.SMOOTH[vid])
    fig, ax, ky = TM.frame(vid); f = fill(ax, LO, LA, F, HS.WIND_LEVELS, HS.wind_cmap(), "max")
    HS.outlines(ax, cf, res="10m" if vid == "wa" else "50m")
    lo, hi = np.nanpercentile(F, [1, 99.9])
    HS.hbar(fig, f, HS.WIND_TICKS, "Gust (mph)", ky)
    finish(fig, ax, m, c, step, vid, out, tab, title, f"{extra}  \u00b7  up to {hi:.0f} mph in view", valid_start)


GL = [None, None]


def gust_note(m):
    if m in ("ifs",): return "max gust in the prior 3 h (6 h after day 6)"
    return "gust at the valid time"


def prod_gust10(m, c, step, R, vids, ctx):
    la, lo, g = R.f("gust"); GL[:] = [la, lo]
    for v in vids: gust_fill(m, c, step, R, g, v, outdir(c, "gust10", m, v, step), "gust10", "10 m Wind Gusts", gust_note(m)); print("ok", m, "gust10", v, step, flush=True)


def prod_peakgust(m, c, step, R, vids, ctx):
    la, lo, g = R.f("gust"); GL[:] = [la, lo]
    ctx["peak"] = g if ctx.get("peak") is None else np.fmax(ctx["peak"], g)
    if step not in ctx["render"]: return
    note = "highest gust since the run started" + ("" if m in ("ifs", "hrrr", "rrfs") else " (sampled every output step)")
    for v in vids:
        gust_fill(m, c, step, R, ctx["peak"], v, outdir(c, "peakgust", m, v, step), "peakgust", "Peak Gust So Far", note,
                  valid_start=c.astimezone(PT)); print("ok", m, "peakgust", v, step, flush=True)


def feels_like_f(T, Td, W):
    """NWS apparent temperature: wind chill (T <= 50 F and wind >= 3 mph), heat index (T >= 80 F, Rothfusz + NWS adjustments), else T."""
    rh = 100 * np.exp(17.625 * ((Td - 32) / 1.8) / (243.04 + (Td - 32) / 1.8)) / np.exp(17.625 * ((T - 32) / 1.8) / (243.04 + (T - 32) / 1.8))
    rh = np.clip(rh, 1, 100)
    wc = 35.74 + 0.6215 * T - 35.75 * np.power(np.maximum(W, 3), 0.16) + 0.4275 * T * np.power(np.maximum(W, 3), 0.16)
    hs = 0.5 * (T + 61.0 + (T - 68.0) * 1.2 + rh * 0.094)
    hr = (-42.379 + 2.04901523 * T + 10.14333127 * rh - 0.22475541 * T * rh - 6.83783e-3 * T * T - 5.481717e-2 * rh * rh
          + 1.22874e-3 * T * T * rh + 8.5282e-4 * T * rh * rh - 1.99e-6 * T * T * rh * rh)
    hr = np.where((rh < 13) & (T >= 80) & (T <= 112), hr - ((13 - rh) / 4) * np.sqrt(np.clip((17 - np.abs(T - 95)) / 17, 0, None)), hr)
    hr = np.where((rh > 85) & (T >= 80) & (T <= 87), hr + ((rh - 85) / 10) * ((87 - T) / 5), hr)
    hi = np.where((hs + T) / 2 >= 80, hr, hs)
    return np.where((T <= 50) & (W >= 3), wc, np.where(T >= 80, np.maximum(hi, T), T))


def prod_feels(m, c, step, R, vids, ctx):
    la, lo, t = R.f("t2m"); _, _, d = R.f("td2m"); _, _, u = R.f("u10"); _, _, w = R.f("v10")
    T = (t - 273.15) * 1.8 + 32; Td = (d - 273.15) * 1.8 + 32; W = np.hypot(u, w) * MPH
    FL = feels_like_f(T, np.minimum(Td, T), W)
    for v in vids:
        LA, LO, (F,) = TM.cut(la, lo, [FL], v)
        if TM.SMOOTH.get(v): F = gaussian_filter(F, TM.SMOOTH[v])
        fig, ax, ky = TM.frame(v); cm = HS.temp_cmap(); f = fill(ax, LO, LA, F, HS.TEMP_LEVELS, cm)
        HS.outlines(ax, cf, res="10m" if v == "wa" else "50m"); freeze_line(ax, LO, LA, F, 32)
        HS.hbar(fig, f, HS.TEMP_TICKS, "Feels like (\u00b0F)", ky)
        lo_, hi_ = np.nanpercentile(F, [0.5, 99.5])
        finish(fig, ax, m, c, step, v, outdir(c, "feels", m, v, step), "feels", "Feels-Like Temperature",
               f"NWS wind chill / heat index  \u00b7  {lo_:.0f} to {hi_:.0f}\u00b0F in view"); print("ok", m, "feels", v, step, flush=True)


def prod_aloft(lev):
    def run(m, c, step, R, vids, ctx):
        la, lo, t = R.f(f"T:{lev}"); _, _, z = R.f(f"Z:{lev}"); _, _, u = R.f(f"U:{lev}"); _, _, w = R.f(f"V:{lev}")
        try: _, _, sp = R.f("sp")
        except KeyError: sp = np.full_like(t, 1.0e5)
        L, cm = aloft_cmap(lev); lo_, hi_, dz = ALOFT[lev]
        for v in vids:
            LA, LO, (T, Z, U, Vw, SP) = TM.cut(la, lo, [t, z, u, w, sp], v)
            hires = np.ndim(LA) == 2; C = T - 273.15
            if TM.SMOOTH.get(v): C = gaussian_filter(C, TM.SMOOTH[v])
            if hires: C = gaussian_filter(C, 1.0)
            Zs = gaussian_filter(Z / 10.0, 7.0 if hires else (1.5 if v != "wa" else 2.5))
            under = gaussian_filter(SP, 2.0 if hires else 1.0) < lev * 100.0
            C, Zs, U, Vw = (np.where(under, np.nan, a) for a in (C, Zs, U, Vw))
            fig, ax, ky = TM.frame(v)
            if under.any():
                pc_contour(ax, "f", LO, LA, binary_dilation(under, iterations=2 if hires else 1).astype(float), levels=[0.5, 1.5], colors=[TM.BELOW_GROUND],
                           zorder=0.5)
            f = fill(ax, LO, LA, C, L, cm)
            HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
            if lo_ <= 0 <= hi_: freeze_line(ax, LO, LA, C, 0)
            labelled(ax, LO, LA, Zs, np.arange(0, 1300, dz)); barbs(fig, ax, LO, LA, U, Vw, v)
            HS.hbar(fig, f, list(range(lo_, hi_ + 1, 5)), "Temp (\u00b0C)", ky, signed=True)
            finish(fig, ax, m, c, step, v, outdir(c, f"t{lev}", m, v, step), f"t{lev}", f"{lev} mb Temperature + Wind",
                   ("0\u00b0C line dashed  \u00b7  " if lo_ <= 0 <= hi_ else "") + f"heights every {dz} dam  \u00b7  barbs in kt"
                   + ("  \u00b7  gray = ground above %d mb" % lev if lev >= 700 else "")); print("ok", m, f"t{lev}", v, step, flush=True)
    return run


def prod_td2m(m, c, step, R, vids, ctx):
    la, lo, d = R.f("td2m"); cm = ramp(DEW_LEVELS, DEW_ANCH)
    for v in vids:
        LA, LO, (D,) = TM.cut(la, lo, [(d - 273.15) * 1.8 + 32], v)
        if TM.SMOOTH.get(v): D = gaussian_filter(D, TM.SMOOTH[v])
        fig, ax, ky = TM.frame(v); f = fill(ax, LO, LA, D, DEW_LEVELS, cm)
        HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
        HS.hbar(fig, f, list(range(-20, 81, 10)), "Dewpoint (\u00b0F)", ky)
        lo_, hi_ = np.nanpercentile(D, [0.5, 99.5])
        finish(fig, ax, m, c, step, v, outdir(c, "td2m", m, v, step), "td2m", "2 m Dewpoint", f"{lo_:.0f} to {hi_:.0f}\u00b0F in view")
        print("ok", m, "td2m", v, step, flush=True)


def prod_mslp500(m, c, step, R, vids, ctx):
    la, lo, p = R.f("msl"); _, _, z = R.f("Z:500"); cm = ramp(H500_LEVELS, H500_ANCH)
    for v in vids:
        LA, LO, (P, Z) = TM.cut(la, lo, [p / 100.0, z / 10.0], v)
        hires = np.ndim(LA) == 2; Zs = gaussian_filter(Z, 6.0 if hires else 1.0)
        fig, ax, ky = TM.frame(v); f = fill(ax, LO, LA, Zs, H500_LEVELS, cm)
        HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
        lab, mk = isobars_hl(fig, ax, LA, LO, P, v)
        HS.hbar(fig, f, list(range(486, 607, 12)), "500 mb (dam)", ky)
        HS.clear_labels_near(fig, lab, mk)
        finish(fig, ax, m, c, step, v, outdir(c, "mslp500", m, v, step), "mslp500", "MSLP + 500 mb Height",
               "fill = 500 mb height  \u00b7  isobars every 4 mb"); print("ok", m, "mslp500", v, step, flush=True)


def ptype_fields(m, R):
    """Instantaneous precip rate (in/h) and type masks rain / snow / mix (ice pellets or rain-snow) / freezing rain."""
    la, lo, pr = R.f("prate"); rate = pr * 3600 / 25.4
    if MODELS[m]["kind"] == "ecmwf":
        _, _, pt = R.f("ptype"); pt = np.rint(pt)
        rain, frz = np.isin(pt, (1,)), np.isin(pt, (3, 12)); snow = np.isin(pt, (5, 6)); mix = np.isin(pt, (7, 8))
    else:
        cr, cs, cz, ci = (R.f(k)[2] > 0.5 for k in ("crain", "csnow", "cfrzr", "cicep"))
        frz = cz; mix = ~frz & (ci | (cr & cs)); snow = ~frz & ~mix & cs; rain = ~frz & ~mix & ~snow
    return la, lo, rate, {"rain": rain, "snow": snow, "mix": mix, "frz": frz}


def prod_mslpptype(m, c, step, R, vids, ctx):
    la, lo, rate, T = ptype_fields(m, R); _, _, p = R.f("msl")
    L = RATE_LEVELS; tr = [0, 4, 8]
    cmaps = {"rain": ramp(L, [(0.01, "#d4f2c8"), (0.1, "#4fb05a"), (0.3, "#1b7a3a"), (1.0, "#f2d03a")]),
             "mix": ramp(L, [(0.01, "#f6dcf2"), (0.2, "#d77fd0"), (1.0, "#7d2a8a")]),
             "snow": ramp(L, [(0.01, "#dcefff"), (0.1, "#7fb9f0"), (0.3, "#2f63c9"), (1.0, "#1d1f7a")]), "frz": ramp(L, FZR_ANCH)}
    for v in vids:
        arrs = [p / 100.0, rate] + [T[k].astype(float) for k in ("rain", "snow", "mix", "frz")]
        LA, LO, (P, Rr, rn, sn, mx, fz) = TM.cut(la, lo, arrs, v)
        fig, ax, ky = TM.frame(v); r = "10m" if v == "wa" else "50m"
        ax.add_feature(cf.NaturalEarthFeature("physical", "ocean", r), facecolor=HS.QPF_SEA, edgecolor="none", zorder=0.6)
        ax.add_feature(cf.NaturalEarthFeature("physical", "land", r), facecolor=HS.QPF_LAND, edgecolor="none", zorder=0.6)
        fm = {}
        for k, msk in (("rain", rn), ("snow", sn), ("mix", mx), ("frz", fz)):
            fm[k] = fill(ax, LO, LA, np.where((msk > 0.5) & (Rr >= 0.01), Rr, np.nan), L, cmaps[k], "max", 2)
        HS.outlines(ax, cf, res=r)
        lab, mk = isobars_hl(fig, ax, LA, LO, P, v); HS.clear_labels_near(fig, lab, mk)
        H = fig.get_size_inches()[1]
        for i, (k, nm) in enumerate((("rain", "RAIN"), ("snow", "SNOW"), ("mix", "MIX"), ("frz", "FRZ RAIN"))):
            x0 = 0.175 + i * 0.2; cax = fig.add_axes([x0, ky, 0.185, 0.27 / H])
            b = fig.colorbar(fm[k], cax=cax, orientation="horizontal", ticks=[L[t] for t in tr], extendfrac=0.04)
            b.outline.set_edgecolor(HS.PANEL_EDGE); cax.tick_params(colors=HS.INK, length=4, width=1, pad=3)
            cax.set_xticklabels([f"{L[t]:g}" for t in tr], fontproperties=HS.font(700, 11))
            cax.text(0.012, 0.5, nm, transform=cax.transAxes, ha="left", va="center", color="#15171c", fontproperties=HS.font(800, 9), zorder=9)
        fig.text(0.024, ky + 0.135 / H, "Rate (in/h)", color=HS.INK, fontproperties=HS.font(700, 13.5), ha="left", va="center")
        finish(fig, ax, m, c, step, v, outdir(c, "mslpptype", m, v, step), "mslpptype", "MSLP + Precip Type",
               "precip rate and type at the valid time  \u00b7  isobars every 4 mb"); print("ok", m, "mslpptype", v, step, flush=True)


# ---------------------------------------------------------------------------------------------- snow and ice (running totals)
SNOW_LEVELS = [0.1, 0.5, 1, 2, 3, 4, 6, 8, 10, 12, 15, 18, 24, 30, 36, 48]
SNOW_ANCH = [(0.1, "#e3eef9"), (1, "#9cc7ea"), (3, "#4f8fd6"), (6, "#2c4fae"), (10, "#5a2f9e"), (15, "#9b3fb0"), (24, "#d77fc4"),
             (36, "#f2c6dc"), (48, "#fbe9f0")]
FZR_LEVELS = [0.01, 0.05, 0.1, 0.15, 0.25, 0.35, 0.5, 0.75, 1.0]
SRATE_LEVELS = [0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3]
KUCH_LEVELS = {"ifs": (925, 850, 700, 600, 500), "gfs": (925, 850, 700, 500), "hrrr": (925, 850, 700, 500)}


def kuchera_ratio(m, R, t2):
    """Kuchera (2006) ratio from the warmest temperature between the ground and 500 mb (levels under ground skipped):
    12 + 2 (271.16 - Tmax) above 271.16 K, else 12 + (271.16 - Tmax); kept within 0-30."""
    try: _, _, sp = R.f("sp")
    except KeyError: sp = None
    tmax = t2.copy()
    for lev in KUCH_LEVELS[m]:
        t = R.f(f"T:{lev}")[2]
        tmax = np.fmax(tmax, t if sp is None else np.where(sp > lev * 100.0, t, -np.inf))
    r = np.where(tmax > 271.16, 12 + 2 * (271.16 - tmax), 12 + (271.16 - tmax))
    return np.clip(r, 0, 30)


def accumulate(m, c, s, R, ctx, need):
    """Advance the running totals by one native step. Inches. need = set of products asked for."""
    A = ctx.setdefault("acc", {"s10": 0, "kuch": 0, "frz": 0, "k24": [], "prev": {}})
    P = A["prev"]
    if m == "ifs":
        la, lo, sf = R.f("sf"); tp = R.f("tp")[2]; snow_t = sf * 1000 / 25.4; tp_t = tp * 1000 / 25.4
        inc_s = snow_t - P.get("snow", 0); inc_tp = tp_t - P.get("tp", 0); P.update(snow=snow_t, tp=tp_t)
        inc_f = inc_tp * np.isin(np.rint(R.f("ptype")[2]), (3, 12)) if "frzr" in need else 0
    elif m == "gfs":
        la, lo, tp = R.acc0("APCP:surface"); tp_t = tp / 25.4; inc_tp = tp_t - P.get("tp", 0); P.update(tp=tp_t)
        inc_s = inc_tp * R.ave("CSNOW:surface")[2]; inc_f = inc_tp * R.ave("CFRZR:surface")[2] if "frzr" in need else 0
    elif m == "hrrr":
        la, lo, we = R.acc0("WEASD:surface"); we_t = we / 25.4; inc_s = we_t - P.get("we", 0); P.update(we=we_t)
        inc_f = 0
        if "frzr" in need: A["frz_total"] = R.acc0("FRZR:surface")[2] / 25.4
    else:   # rrfs: precip falling while the categorical type says snow / freezing rain at the step
        la, lo, tp = R.acc0("APCP:surface"); tp_t = tp / 25.4; inc_tp = tp_t - P.get("tp", 0); P.update(tp=tp_t)
        inc_s = inc_tp * (R.f("csnow")[2] > 0.5); inc_f = inc_tp * (R.f("cfrzr")[2] > 0.5) if "frzr" in need else 0
    inc_s = np.clip(inc_s, 0, None); A["grid"] = (la, lo)
    A["s10"] = A["s10"] + 10 * inc_s; A["frz"] = A["frz"] + np.clip(inc_f, 0, None)
    if need & {"snowkuch", "snowk24"} and m in KUCH_LEVELS:
        k = inc_s * kuchera_ratio(m, R, R.f("t2m")[2]); A["kuch"] = A["kuch"] + k
        A["k24"] = [(t, x) for t, x in A["k24"] if t > s - 24] + [(s, k)]
    if "snowrate" in need and m in HIRES:
        a = R.acc0("ASNOW:surface")[2] / 0.0254; A["rate"] = np.clip(a - P.get("asnow", 0), 0, None) if s - P.get("asnow_s", -9) == 1 else None
        P.update(asnow=a, asnow_s=s)
    frz = A["frz_total"] if (m == "hrrr" and "frz_total" in A) else A["frz"]
    A.setdefault("hist", {0: {"s10": 0.0, "kuch": 0.0, "frz": 0.0}})[s] = {"s10": A["s10"], "kuch": A["kuch"], "frz": frz}


def acc_windows(m, s):
    """Accumulation choices (A1): 1 h (hourly 3 km models only), 6, 12, 24, 48 h and the run total, ending at step s.
    Windows are back to back from the run start (a 24 h map ends at F+24, F+48, ...), like the WA Rain/Snow tabs; this keeps
    the file count inside the Cloudflare per-deploy cap. The run total is drawn at every rendered step."""
    w = ([("1h", 1)] if m in HIRES else []) + [(f"{h}h", h) for h in (6, 12, 24, 48)]
    return [(p, b) for p, b in w if b < s and s % b == 0] + [("total", s)]


def windowed(m, c, s, vid, prod, key, levels, anch, title, unit, extra):
    """Draw every accumulation window of one running total kept in ctx['acc']['hist'][step][key]."""
    Hh = CTX["acc"]["hist"]; now = Hh[s][key]
    for per, back in acc_windows(m, s):
        if s - back not in Hh and back != s: continue
        F = now if back == s else np.clip(now - Hh[s - back][key], 0, None)
        wtitle = title if per == "total" else f"{back} h " + title.replace(" Total", "")
        total_map(m, c, s, vid, prod, F, levels, anch, wtitle, unit, extra if per == "total" else extra.replace(", since the run started", "").replace(" since the run started", ""),
                  (c + dt.timedelta(hours=s - back)).astimezone(PT), per)


def total_map(m, c, s, vid, prod, F, levels, anch, title, key, extra, start, per="step"):
    LA, LO, (G,) = TM.cut(*ctx_grid(), [F], vid)
    if TM.SMOOTH.get(vid): G = gaussian_filter(G, TM.SMOOTH[vid])
    fig, ax, ky = TM.frame(vid); r = "10m" if vid == "wa" else "50m"
    ax.add_feature(cf.NaturalEarthFeature("physical", "ocean", r), facecolor=HS.QPF_SEA, edgecolor="none", zorder=0.6)
    ax.add_feature(cf.NaturalEarthFeature("physical", "land", r), facecolor=HS.QPF_LAND, edgecolor="none", zorder=0.6)
    cm = ramp(levels, anch, under=(0, 0, 0, 0)); f = fill(ax, LO, LA, np.where(G >= levels[0], G, np.nan), levels, cm, "max", 2)
    HS.outlines(ax, cf, res=r)
    cb = HS.hbar(fig, f, [], key, ky); cb.set_ticks(levels); cb.ax.set_xticklabels([f"{v:g}" for v in levels], fontproperties=HS.font(700, 13))
    hi = np.nanmax(G) if np.isfinite(G).any() else 0
    finish(fig, ax, m, c, s, vid, outdir(c, prod, m, vid, s, per), prod, title, f"{extra}  \u00b7  max {hi:.1f} in in view", valid_start=start, period=per)
    print("ok", m, prod, per, vid, s, flush=True)


CTX = {}
def ctx_grid(): return CTX["acc"]["grid"]


def prod_snow10(m, c, s, R, vids, ctx):
    if s not in ctx["render"]: return
    for v in vids: windowed(m, c, s, v, "snow10", "s10", SNOW_LEVELS, SNOW_ANCH, "Snow Total (10:1)", "Snow (in)",
                            "snow liquid since the run started x 10")


def prod_snowkuch(m, c, s, R, vids, ctx):
    if s not in ctx["render"] or m not in KUCH_LEVELS: return
    for v in vids: windowed(m, c, s, v, "snowkuch", "kuch", SNOW_LEVELS, SNOW_ANCH, "Snow Total (Kuchera)", "Snow (in)",
                            "Kuchera ratio from the warmest layer below 500 mb, since the run started")


def prod_snowk24(m, c, s, R, vids, ctx):
    if s not in ctx["render"] or m not in KUCH_LEVELS or s < 24: return
    F = sum(x for _, x in ctx["acc"]["k24"])
    for v in vids: total_map(m, c, s, v, "snowk24", F, SNOW_LEVELS, SNOW_ANCH, "24 h Snow (Kuchera)", "Snow (in)",
                             "Kuchera snow in the 24 h ending at the valid time", (c + dt.timedelta(hours=s - 24)).astimezone(PT))


def prod_snowrate(m, c, s, R, vids, ctx):
    if s not in ctx["render"]: return
    if m in HIRES:
        F = ctx["acc"].get("rate")
        if F is None: return
        note = "model snowfall in the past hour"
    else:   # GFS: instantaneous precip rate where the categorical type is snow, at 10:1
        la, lo, pr = R.f("prate"); ctx["acc"]["grid"] = (la, lo); F = pr * 3600 / 25.4 * 10 * (R.f("csnow")[2] > 0.5)
        note = "precip rate where type is snow, 10:1, at the valid time"
    for v in vids: total_map(m, c, s, v, "snowrate", F, SRATE_LEVELS, SNOW_ANCH, "1 h Snowfall Rate", "Rate (in/h)", note,
                             (c + dt.timedelta(hours=s - 1)).astimezone(PT))


def prod_frzr(m, c, s, R, vids, ctx):
    if s not in ctx["render"]: return
    note = {"hrrr": "model freezing-rain accumulation", "ifs": "precip in steps typed freezing rain at the step end",
            "gfs": "precip x share of time typed freezing rain", "rrfs": "precip in each hour typed freezing rain at the hour"}[m]
    for v in vids: windowed(m, c, s, v, "frzr", "frz", FZR_LEVELS, FZR_ANCH, "Freezing Rain Total", "Liquid (in)",
                            note + ", since the run started")


ACCUM = {"snow10", "snowkuch", "snowk24", "snowrate", "frzr"}


# ---------------------------------------------------------------------------------------------- moisture and winds (B5)
PW_LEVELS = np.round(np.arange(0, 2.61, 0.05), 2)   # finer where cool-season PNW values live (0.2-1.2 in)
PW_ANCH = [(0, "#6b4a2b"), (0.2, "#b08d5e"), (0.4, "#e3d7a8"), (0.6, "#a8d58f"), (0.8, "#3ea56b"), (1.0, "#1d7f8f"), (1.3, "#2f56b8"),
           (1.7, "#5d38a8"), (2.2, "#c060b8"), (2.6, "#f0b8e0")]
PWA_LEVELS = np.round(np.arange(-1.5, 1.501, 0.05), 2)
IVT_LEVELS = [100, 150, 250, 300, 400, 500, 600, 700, 800, 1000, 1200, 1500]
IVT_ANCH = [(100, "#e4e6ea"), (250, "#f7e28a"), (400, "#f3a64c"), (600, "#e0503a"), (800, "#b0245c"), (1200, "#6a2a8f"), (1500, "#c9a7e6")]
JET_LEVELS = np.arange(50, 201, 5)
JET_ANCH = [(50, "#dfe5ea"), (70, "#8fc4d6"), (90, "#3e9f93"), (110, "#a6c94a"), (130, "#f1cf45"), (150, "#ef8a3a"), (170, "#d43f5a"), (200, "#8a2a9a")]
THK_LEVELS = np.arange(486, 595, 3)
THK_LINE, THK_540 = "#7a1f3d", "#0f3d91"   # thickness lines wine red, 540 bold blue; isobars stay black
IVT_P = (1000, 925, 850, 700, 600, 500, 400, 300)
CLIM_PW = f"{ROOT}/clim/ncep_pw_day_ltm_1991_2020.npz"


def fill_keyed(fig, ax, LO, LA, F, levels, cm, ky, title, ticks, ext="both", z=1, fmt="{:g}"):
    f = fill(ax, LO, LA, F, levels, cm, ext, z)
    cb = HS.hbar(fig, f, [], title, ky); cb.set_ticks(ticks)
    cb.ax.set_xticklabels([fmt.format(t) for t in ticks], fontproperties=HS.font(700, 13)); return f


def prod_pw(m, c, s, R, vids, ctx):
    la, lo, pw = R.f("pwat"); cm = ramp(PW_LEVELS, PW_ANCH)
    for v in vids:
        LA, LO, (F,) = TM.cut(la, lo, [pw / 25.4], v)
        if TM.SMOOTH.get(v): F = gaussian_filter(F, TM.SMOOTH[v])
        fig, ax, ky = TM.frame(v); fill_keyed(fig, ax, LO, LA, F, PW_LEVELS, cm, ky, "PW (in)", [0, 0.5, 1, 1.5, 2, 2.5], "max")
        HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
        finish(fig, ax, m, c, s, v, outdir(c, "pw", m, v, s), "pw", "Precipitable Water", f"total column water vapor  \u00b7  up to {np.nanmax(F):.2f} in in view")
        print("ok", m, "pw", v, s, flush=True)


def pw_normal(valid, LA, LO, zmodel):
    """NCEP/NCAR 1991-2020 daily-mean PW (mm), 15-day smoothed, moved to model terrain with a 2.3 km water-vapor scale height."""
    from scipy.interpolate import RegularGridInterpolator
    z = np.load(CLIM_PW); W, cl, co, zs, zl, zo = z["pw"].astype("f4"), z["lat"], z["lon"], z["zs"], z["zlat"], z["zlon"]
    v = valid.astimezone(dt.timezone.utc); d = v.timetuple().tm_yday
    if d > 59 and v.year % 4 == 0 and (v.year % 100 or v.year % 400 == 0): d -= 1
    x = d - 1 + v.hour / 24.0; i0 = int(x) % 365; w = x - int(x); f = (1 - w) * W[i0] + w * W[(i0 + 1) % 365]
    pts = np.stack([np.asarray(LA, float), np.asarray(LO, float) % 360], -1)
    it = lambda a, la_, lo_: RegularGridInterpolator((la_[::-1], lo_), a[::-1], bounds_error=False, fill_value=None)(pts)
    return it(f, cl, co) * np.exp(-(zmodel - it(zs, zl, zo)) / 2300.0)


def prod_pwanom(m, c, s, R, vids, ctx):
    la, lo, pw = R.f("pwat"); zm = R.f("orog")[2]
    cm = HS.cmap([HS._anom_color(300.0 * x) for x in (PWA_LEVELS[:-1] + PWA_LEVELS[1:]) / 2.0], HS.ANOM_UNDER, HS.ANOM_OVER)
    for v in vids:
        LA, LO, (P, Z) = TM.cut(la, lo, [pw, zm], v)
        if np.ndim(LA) == 1: LA, LO = np.meshgrid(LA, LO, indexing="ij")
        A = gaussian_filter((P - pw_normal(c + dt.timedelta(hours=s), LA, LO, Z)) / 25.4, max(TM.SMOOTH.get(v, 0), 1.0))
        fig, ax, ky = TM.frame(v)
        f = fill(ax, LO, LA, A, PWA_LEVELS, cm)
        cb = HS.hbar(fig, f, [], "Anomaly (in)", ky); tk = [-1.5, -1, -0.5, 0, 0.5, 1, 1.5]; cb.set_ticks(tk)
        cb.ax.set_xticklabels([f"{t:+g}" if t else "0" for t in tk], fontproperties=HS.font(700, 13))
        HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
        finish(fig, ax, m, c, s, v, outdir(c, "pwanom", m, v, s), "pwanom", "Precipitable Water Anomaly", "vs 1991-2020 normal for the date (NCEP/NCAR Reanalysis, NOAA PSL)")
        print("ok", m, "pwanom", v, s, flush=True)


def prod_ivt(m, c, s, R, vids, ctx):
    """IVT = (1/g) * integral of q*V dp from 1000 to 300 mb (trapezoid over the standard levels; levels under ground dropped)."""
    la, lo, _ = R.f("T:850")
    try: sp = R.f("sp")[2]
    except KeyError: sp = None
    qu, qv = [], []
    for lev in IVT_P:
        q = R.f(f"Q:{lev}")[2]; u = R.f(f"U:{lev}")[2]; w = R.f(f"V:{lev}")[2]
        ok = 1.0 if sp is None else (sp >= lev * 100.0)
        qu.append(q * u * ok); qv.append(q * w * ok)
    P = np.array(IVT_P, float) * 100.0
    iu = sum((qu[k] + qu[k + 1]) / 2 * (P[k] - P[k + 1]) for k in range(len(P) - 1)) / 9.80665
    iv = sum((qv[k] + qv[k + 1]) / 2 * (P[k] - P[k + 1]) for k in range(len(P) - 1)) / 9.80665
    cm = ramp(IVT_LEVELS, IVT_ANCH, under=(0, 0, 0, 0))
    for v in vids:
        LA, LO, (U, V_) = TM.cut(la, lo, [iu, iv], v); M = np.hypot(U, V_)
        if TM.SMOOTH.get(v): M = gaussian_filter(M, TM.SMOOTH[v])
        fig, ax, ky = TM.frame(v); fill_keyed(fig, ax, LO, LA, M, IVT_LEVELS, cm, ky, "IVT (kg/m/s)", IVT_LEVELS[1:-1], "max")
        HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
        fw, fh = fig.get_size_inches() * ax.get_position().size; nx = 26; ny = max(4, round(nx * fh / fw))
        Um, Vm = np.where(M >= 250, U, np.nan), np.where(M >= 250, V_, np.nan)
        qs = dict(color="#1b1d22", scale=22000, width=0.0022, zorder=5)
        if FAST_VEC:
            X, Y, u, w_ = thin_vectors(ax, LO, LA, Um, Vm, nx, ny); ax.quiver(X, Y, u, w_, transform=ax.projection, **qs)
        else: ax.quiver(LO, LA, Um, Vm, transform=ccrs.PlateCarree(), regrid_shape=(nx, ny), **qs)
        finish(fig, ax, m, c, s, v, outdir(c, "ivt", m, v, s), "ivt", "Integrated Vapor Transport",
               f"1000-300 mb  \u00b7  arrows where IVT >= 250 (atmospheric-river level)  \u00b7  max {np.nanmax(M):.0f}"); print("ok", m, "ivt", v, s, flush=True)


def prod_wind(lev):
    def run(m, c, s, R, vids, ctx):
        la, lo, u = R.f(f"U:{lev}"); w = R.f(f"V:{lev}")[2]; z = R.f(f"Z:{lev}")[2]
        try: sp = R.f("sp")[2]
        except KeyError: sp = np.full_like(u, 1.0e5)
        if lev == 250: L, cm, tk, dz = JET_LEVELS, ramp(JET_LEVELS, JET_ANCH, under=(0, 0, 0, 0)), list(range(50, 201, 25)), 12
        else: L, cm, tk, dz = HS.WIND_LEVELS, HS.wind_cmap(), HS.WIND_TICKS, 3
        for v in vids:
            LA, LO, (U, V_, Z, SP) = TM.cut(la, lo, [u, w, z, sp], v); hires = np.ndim(LA) == 2
            S = np.hypot(U, V_) * KT; Zs = gaussian_filter(Z / 10.0, 7.0 if hires else 1.5)
            under = gaussian_filter(SP, 2.0 if hires else 1.0) < lev * 100.0
            S, Zs, U, V_ = (np.where(under, np.nan, a) for a in (S, Zs, U, V_))
            fig, ax, ky = TM.frame(v)
            if under.any():
                pc_contour(ax, "f", LO, LA, binary_dilation(under, iterations=2 if hires else 1).astype(float), levels=[0.5, 1.5],
                           colors=[TM.BELOW_GROUND], zorder=0.5)
            f = fill(ax, LO, LA, np.where(S >= L[0], S, np.nan) if lev == 250 else S, L, cm, "max")
            cb = HS.hbar(fig, f, tk, "Wind (kt)", ky)
            HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
            labelled(ax, LO, LA, Zs, np.arange(0, 1300, dz)); barbs(fig, ax, LO, LA, U, V_, v)
            finish(fig, ax, m, c, s, v, outdir(c, f"w{lev}", m, v, s), f"w{lev}", f"{lev} mb Wind",
                   f"speed in kt  \u00b7  heights every {dz} dam  \u00b7  barbs in kt" + ("  \u00b7  gray = ground above 850 mb" if lev == 850 else ""))
            print("ok", m, f"w{lev}", v, s, flush=True)
    return run


def prod_thick(m, c, s, R, vids, ctx):
    la, lo, z5 = R.f("Z:500"); z1 = R.f("Z:1000")[2]; p = R.f("msl")[2]
    cm = HS.cmap([HS.temp_color(-20 + (x - 486) / (594 - 486) * 120) for x in (THK_LEVELS[:-1] + THK_LEVELS[1:]) / 2], HS.temp_color(-30), HS.temp_color(110))
    for v in vids:
        LA, LO, (T, P) = TM.cut(la, lo, [(z5 - z1) / 10.0, p / 100.0], v); hires = np.ndim(LA) == 2
        T = gaussian_filter(T, 5.0 if hires else 1.0)
        fig, ax, ky = TM.frame(v); f = fill(ax, LO, LA, T, THK_LEVELS, cm)
        HS.hbar(fig, f, list(range(492, 595, 12)), "Thickness (dam)", ky)
        HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
        pc = ccrs.PlateCarree()
        th = pc_contour(ax, "l", LO, LA, T, levels=[l for l in range(486, 595, 6) if l != 540], colors=THK_LINE, linewidths=0.9, zorder=3)
        for t in ax.clabel(th, fmt="%d", inline=True, inline_spacing=4): t.set_fontproperties(HS.font(600, 9)); t.set_color(THK_LINE)
        k = pc_contour(ax, "l", LO, LA, T, levels=[540], colors=THK_540, linewidths=3.0, zorder=4)
        k.set(path_effects=HS.halo("white", 5))
        for t in ax.clabel(k, fmt="540", inline=True, inline_spacing=6): t.set_fontproperties(HS.font(900, 13)); t.set_color(THK_540); t.set_path_effects(HS.halo("white", 3.5))
        lab, mk = isobars_hl(fig, ax, LA, LO, P, v); HS.clear_labels_near(fig, lab, mk)
        finish(fig, ax, m, c, s, v, outdir(c, "thick", m, v, s), "thick", "1000-500 mb Thickness",
               "red lines every 6 dam, 540 bold blue  \u00b7  black isobars every 4 mb"); print("ok", m, "thick", v, s, flush=True)


def prod_qpf(m, c, s, R, vids, ctx):
    """Precip totals for 6 h, 24 h and since the run started, from the model's running total (liquid equivalent, inches)."""
    H = ctx.setdefault("tph", {0: 0.0})
    if m == "ifs": la, lo, tp = R.f("tp"); T = tp * 1000 / 25.4
    elif m == "aifs": la, lo, tp = R.f("tp"); T = tp / 25.4
    else: la, lo, tp = R.acc0("APCP:surface"); T = tp / 25.4
    H[s] = T; ctx["qgrid"] = (la, lo)
    if s not in ctx["render"]: return
    for per, back in acc_windows(m, s):
        if s - back not in H: continue
        F = np.clip(T - H[s - back], 0, None)
        for v in vids:
            LA, LO, (G,) = TM.cut(la, lo, [F], v)
            if TM.SMOOTH.get(v): G = gaussian_filter(G, TM.SMOOTH[v])
            fig, ax, ky = TM.frame(v); r = "10m" if v == "wa" else "50m"
            ax.add_feature(cf.NaturalEarthFeature("physical", "ocean", r), facecolor=HS.QPF_SEA, edgecolor="none", zorder=0.6)
            ax.add_feature(cf.NaturalEarthFeature("physical", "land", r), facecolor=HS.QPF_LAND, edgecolor="none", zorder=0.6)
            f = fill(ax, LO, LA, np.where(G >= 0.01, G, np.nan), HS.RAIN_LEVELS, HS.rain_cmap(), "max", 2)
            cb = HS.hbar(fig, f, [], "Precip (in)", ky); tk = [0.1, 0.5, 1, 2, 3, 4, 6, 8, 10, 12]; cb.set_ticks(tk)
            cb.ax.set_xticklabels([f"{t:g}" for t in tk], fontproperties=HS.font(700, 13)); HS.outlines(ax, cf, res=r)
            st = (c + dt.timedelta(hours=s - back)).astimezone(PT)
            out = f"{ROOT}/{c:%Y%m%d%H}/qpf-{m}/{per}/{v}/{c + dt.timedelta(hours=s):%Y%m%d%H}"
            TM.towns(ax, v); HS.frame(ax); valid = c + dt.timedelta(hours=s); vl = valid.astimezone(PT); M = MODELS[m]
            HS.header(fig, "Precipitation Total" if per == "total" else f"{back} h Precipitation", f"{st:%a %-I %p} to {vl:%a %-m-%-d %-I %p} PT",
                      f"{M['name']} {M['res']} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {TM.VIEWS[v]['label']}  \u00b7  {per if per != 'total' else 'since the run started'}  \u00b7  liquid equivalent  \u00b7  max {np.nanmax(G):.2f} in",
                      f"F+{s}", f"{valid:%HZ %a}".upper())
            HS.credit(fig, credit(m))
            TM.save(fig, out, {"tab": "qpf", "period": per, "view": v, "model": M["site"], "cycle": f"{c:%Y%m%d%H}", "start_pt": st.isoformat(), "end_pt": vl.isoformat()})
            print("ok", m, "qpf", per, v, s, flush=True)


ACCUM.add("qpf")


# ---------------------------------------------------------------------------------------------- sky, fog and visibility (B6)
TCC_LEVELS = np.arange(0, 101, 5)
TCC_ANCH = [(0, "#6fa8d6"), (30, "#a3c1d8"), (60, "#bcc0c5"), (85, "#9ba1a9"), (100, "#80868f")]   # sky blue > gray, no white band
IR_LEVELS = np.arange(-90, 42, 2)
IR_ANCH = [(-90, "#ffffff"), (-80, "#e04fd0"), (-72, "#c8242f"), (-64, "#f2a33a"), (-56, "#f4e04d"), (-48, "#3fae5a"), (-40, "#2f63c8"),
           (-32, "#57c6e0"), (-28, "#4c5562"), (-10, "#7b838e"), (10, "#b4b8bd"), (40, "#ecebe6")]
VIS_LEVELS = [0, 0.25, 0.5, 1, 2, 3, 5, 7]
VIS_COLS = ["#5b1d73", "#a1267a", "#d9433b", "#f08a35", "#f5c94a", "#f8e8a6", "#fbf6dc"]
FOG_LEVELS = np.arange(20, 101, 10)
FOG_ANCH = [(20, "#e6e8eb"), (40, "#b9c4cf"), (60, "#7f95ab"), (80, "#4f6a8a"), (100, "#2c3f5f")]


def sky_map(m, c, s, v, prod, title, extra, LA, LO, F, L, cm, key, ticks, ext="neither", fmt="{:g}"):
    fig, ax, ky = TM.frame(v); fill_keyed(fig, ax, LO, LA, F, L, cm, ky, key, ticks, ext, fmt=fmt)
    HS.outlines(ax, cf, res="10m" if v == "wa" else "50m")
    finish(fig, ax, m, c, s, v, outdir(c, prod, m, v, s), prod, title, extra); print("ok", m, prod, v, s, flush=True)


def prod_tcc(m, c, s, R, vids, ctx):
    la, lo, t = R.f("tcc"); t = t * 100.0 if np.nanmax(t) <= 1.01 else t
    for v in vids:
        LA, LO, (F,) = TM.cut(la, lo, [t], v)
        if TM.SMOOTH.get(v): F = gaussian_filter(F, TM.SMOOTH[v])
        sky_map(m, c, s, v, "tcc", "Total Cloud Cover", "all cloud layers combined, percent of sky", LA, LO, np.clip(F, 0, 100),
                TCC_LEVELS, ramp(TCC_LEVELS, TCC_ANCH), "Cloud (%)", [0, 20, 40, 60, 80, 100])


def prod_ir(m, c, s, R, vids, ctx):
    la, lo, b = R.f("ir"); b = b - 273.15; bad = b > 60   # isolated missing pixels (9999 K): fill from the neighbors
    if bad.any():
        w = gaussian_filter((~bad).astype(float), 1.5); b = np.where(bad, gaussian_filter(np.where(bad, 0, b), 1.5) / np.maximum(w, 1e-6), b)
    for v in vids:
        LA, LO, (F,) = TM.cut(la, lo, [b], v)
        sky_map(m, c, s, v, "ir", "Simulated IR Satellite", "model cloud-top temperature, 10.7 \u00b5m  \u00b7  colors = cold, high tops",
                LA, LO, F, IR_LEVELS, ramp(IR_LEVELS, IR_ANCH), "Tops (\u00b0C)", [-80, -60, -40, -20, 0, 20, 40], "both")


def prod_vis(m, c, s, R, vids, ctx):
    la, lo, w = R.f("vis"); mi = w / 1609.34; cm = HS.cmap(VIS_COLS, VIS_COLS[0], (0, 0, 0, 0))
    for v in vids:
        LA, LO, (F,) = TM.cut(la, lo, [mi], v)
        sky_map(m, c, s, v, "vis", "Surface Visibility", f"model visibility, miles  \u00b7  blank = 7 mi or more  \u00b7  lowest {np.nanmin(F):.1f} mi in view",
                LA, LO, F, VIS_LEVELS, cm, "Visibility (mi)", VIS_LEVELS, "max")


def fog_index(m, R):
    """Fog risk 0-100 (our own index, not a model fog field): near-saturation x light wind, blended with model visibility when
    the model has it. Saturation term: 1 at a 0 F dewpoint depression, 0 at 5 F. Wind term: 1 at 3 mph or less, 0 at 15 mph."""
    la, lo, t = R.f("t2m"); td = R.f("td2m")[2]; u = R.f("u10")[2]; w = R.f("v10")[2]
    dep = (t - td) * 1.8; spd = np.hypot(u, w) * MPH
    sat = np.clip((5.0 - dep) / 5.0, 0, 1); calm = np.clip((15.0 - spd) / 12.0, 0, 1); idx = sat * calm
    try:
        vis = R.f("vis")[2] / 1609.34; low = np.clip((5.0 - vis) / 4.5, 0, 1)
        idx = 0.6 * idx + 0.4 * low * sat
    except KeyError: pass
    try:   # steady rain also saturates the air and cuts visibility; that is not fog, so damp the index where it rains harder
        rr = R.f("prate")[2] * 3600 / 25.4; idx = idx * np.clip(1.0 - rr / 0.08, 0.25, 1.0)
    except KeyError: pass
    return la, lo, 100.0 * idx


def prod_fog(m, c, s, R, vids, ctx):
    la, lo, F0 = fog_index(m, R); vis = m in NO_BY["vis"]
    for v in vids:
        LA, LO, (F,) = TM.cut(la, lo, [F0], v)
        if TM.SMOOTH.get(v): F = gaussian_filter(F, TM.SMOOTH[v])
        sky_map(m, c, s, v, "fog", "Fog Risk Index", "our index: dewpoint spread + light wind" + (" + model visibility" if vis else "") + ", damped in rain" +
                "  \u00b7  not a model fog forecast", LA, LO, F, FOG_LEVELS, ramp(FOG_LEVELS, FOG_ANCH, under=(0, 0, 0, 0)), "Fog risk",
                [20, 40, 60, 80, 100], "neither")


G_NAPNW, H_PNW, H_PNWWA, G_ALL, G_PNWWA = ("na", "pnw"), ("pnwhr",), ("pnwhr", "wa"), ("na", "pnw", "wa"), ("pnw", "wa")
# Ground-level products also get the "Pacific NW tight" view (pnwt) on the global models (IFS, AIFS); never on HRRR/RRFS,
# whose 3 km grids stop short of the tight frame's NW corner (Benjamin 10-24-26).
G_NAPNWT, G_ALLT, G_PNWTWA, G_PNWT = ("na", "pnw", "pnwt"), ("na", "pnw", "pnwt", "wa"), ("pnw", "pnwt", "wa"), ("pnw", "pnwt")
# GFS (10-24-26): removed from every menu product; its only maps are the 500 mb anomaly and sea-level pressure (gfs_maps.py).
# The old GFS entries and the dropped mslp500 product are in archive/gfs_products_20261024/ (README there says how to restore).
PRODUCTS = {   # name: (function, models, global views, high-res views)
    "gust10": (prod_gust10, ("ifs", "hrrr", "rrfs"), G_NAPNWT, H_PNWWA),
    "peakgust": (prod_peakgust, ("ifs", "hrrr", "rrfs"), G_ALLT, H_PNWWA),
    "feels": (prod_feels, ("ifs", "aifs", "hrrr", "rrfs"), G_ALLT, H_PNWWA),
    "t925": (prod_aloft(925), ("ifs", "aifs", "hrrr"), G_ALL, H_PNWWA),
    "t700": (prod_aloft(700), ("ifs", "aifs", "hrrr"), G_NAPNW, H_PNW),
    "t500": (prod_aloft(500), ("ifs", "aifs", "hrrr"), G_NAPNW, H_PNW),
    "t300": (prod_aloft(300), ("ifs", "aifs", "hrrr"), G_NAPNW, H_PNW),
    "td2m": (prod_td2m, ("ifs", "hrrr", "rrfs"), G_PNWTWA, H_PNWWA),
    "mslpptype": (prod_mslpptype, ("ifs", "hrrr", "rrfs"), G_PNWWA, ("wa",)),
    "snowkuch": (prod_snowkuch, ("ifs", "hrrr"), ("pnw",), H_PNW),
    "snow10": (prod_snow10, ("ifs", "hrrr", "rrfs"), ("pnw",), H_PNW),
    "snowk24": (prod_snowk24, ("ifs", "hrrr"), G_PNWWA, H_PNWWA),
    "snowrate": (prod_snowrate, ("hrrr", "rrfs"), G_PNWWA, H_PNWWA),
    "frzr": (prod_frzr, ("ifs", "hrrr", "rrfs"), G_PNWWA, H_PNWWA),
    "ivt": (prod_ivt, ("ifs", "aifs", "hrrr"), G_NAPNW, H_PNW),
    "pw": (prod_pw, ("ifs", "aifs", "hrrr", "rrfs"), ("pnw",), H_PNW),
    "pwanom": (prod_pwanom, ("ifs", "aifs", "hrrr"), G_NAPNW, H_PNW),
    "w850": (prod_wind(850), ("ifs", "aifs", "hrrr"), G_NAPNW, H_PNW),
    "w250": (prod_wind(250), ("ifs", "aifs", "hrrr"), G_NAPNW, H_PNW),
    "thick": (prod_thick, ("ifs", "aifs", "hrrr"), ("pnw",), H_PNW),
    "tcc": (prod_tcc, ("ifs", "aifs", "hrrr", "rrfs"), G_PNWT, H_PNW),
    "ir": (prod_ir, ("hrrr", "rrfs"), ("pnw",), H_PNW),
    "vis": (prod_vis, ("hrrr", "rrfs"), G_PNWWA, ("wa",)),   # no visibility field in ECMWF open data, so 3 km models only now
    "fog": (prod_fog, ("ifs", "hrrr", "rrfs"), G_PNWTWA, ("wa",)),
    "qpf": (prod_qpf, ("ifs", "aifs", "hrrr", "rrfs"), ("pnw",), H_PNW),
}
# AIFS upper air: no Washington view (already true: t700-t300 have no WA view); t925 drops WA for AIFS below.


def native_steps(m, hours):
    if m in HIRES: return list(range(1, hours + 1))
    if m == "aifs": return list(range(6, hours + 1, 6))
    return [s for s in list(range(3, 145, 3)) + list(range(150, 241, 6)) if s <= hours]


def latest(m):
    if m != "gfs": return TM.latest_cycle(m)
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 48):
        c = now - dt.timedelta(hours=b)
        if c.hour % 12: continue
        try: get(GFS.format(d=f"{c:%Y%m%d}", h=c.hour, s=240) + ".idx", (0, 10)); return c
        except Exception: pass
    raise SystemExit("no GFS run found")


# ---------------------------------------------------------------------------------------------- run loop (speed_build_v1)
#   MENU_WORKERS=N   frames drawn at once in forked worker processes (default: all cores); 1 = the old one-at-a-time loop
#   MENU_PREFETCH=0  no background download (each step's data is fetched right before it is drawn, old behavior)
#   MENU_AHEAD=2     how many steps the downloader may run ahead of the drawing; MENU_DL_THREADS=4 fields fetched at once
STATEFUL = {"peakgust", "qpf"}   # products whose function also advances a running total (idempotent within a step)


def vids_of(m, p, views):
    fn, _, gv, hv = PRODUCTS[p]; vids = views_for(m, views, gv, hv)
    if m == "aifs" and p.startswith("t") and p not in ("td2m",): vids = [v for v in vids if v != "wa"]
    return vids


def wanted(p, s, render):
    return p == "peakgust" or p in ACCUM or s in render


def snapshot(ctx):
    """Shallow copy of the running totals at this step. Totals are always rebound (never changed in place), so a shallow
    copy of the containers is enough for a worker to draw this step while the main process moves on."""
    z = dict(ctx)
    if "acc" in z:
        A = dict(z["acc"]); A["hist"] = dict(A.get("hist", {})); A["k24"] = list(A.get("k24", [])); A["prev"] = dict(A.get("prev", {})); z["acc"] = A
    if "tph" in z: z["tph"] = dict(z["tph"])
    return z


def warm(m, c, s, R, p, render, need):
    """Fetch (download + decode) every field product p needs at step s into R's cache, on a throwaway context.
    p = None warms the accumulation fields."""
    dummy = {"render": set(render), "peak": None, "acc": {"s10": 0, "kuch": 0, "frz": 0, "k24": [], "prev": {}, "hist": {}}, "tph": {0: 0.0}}
    try:
        if p is None: accumulate(m, c, s, R, dummy, need)
        else: PRODUCTS[p][0](m, c, s, R, [], dummy)
    except Exception: pass   # the real call reports missing fields


def wait_for_data(R):
    """MENU_WAIT_MIN=N: if this hour's file is not published yet, check every 30 s for up to N minutes, then go on (a missing
    hour is skipped like before). Lets a run start on a cycle that is still coming in and draw each hour as it lands."""
    lim = float(os.environ.get("MENU_WAIT_MIN", "0") or 0)
    if lim <= 0: return
    url = R.url + ".idx" if MODELS[R.m]["kind"] != "ecmwf" else \
        TM.MODELS[R.m]["url"]["sfc"].format(d=f"{R.c:%Y%m%d}", h=R.c.hour, s=R.s) + ".index"
    end = time.time() + 60 * lim
    while True:
        try: TM._get(url, (0, 10)); return
        except Exception:
            if time.time() > end: print(f"{R.m} F{R.s}: still not published after {lim:.0f} min, going on", flush=True); return
            time.sleep(30)


class Loader:
    """Background downloader: walks the steps in order, at most AHEAD steps in front of the drawing, and fetches each
    product's fields in parallel threads. Drawing of a product starts the moment its own fields are in."""
    def __init__(self, m, c, steps, render, prods, need):
        self.m, self.c, self.steps, self.render, self.prods, self.need = m, c, steps, render, prods, need
        self.ahead = threading.Semaphore(max(1, int(os.environ.get("MENU_AHEAD", "2"))))
        self.readers, self.ev, self.dl = {}, {}, {}
        for s in steps:
            self.ev[s] = {k: threading.Event() for k in [None] + prods}
        self.nthreads = max(1, int(os.environ.get("MENU_DL_THREADS", "4")))
        self.t = threading.Thread(target=self.run, daemon=True); self.t.start()

    def run(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(self.nthreads) as ex:
            for s in self.steps:
                self.ahead.acquire()
                R = Reader(self.m, self.c, s); self.readers[s] = R; wait_for_data(R)
                t0 = time.perf_counter(); d0 = TM.DL["sec"]
                jobs = ([None] if self.need else []) + [p for p in self.prods if wanted(p, s, self.render)]
                def one(p, s=s, R=R):
                    warm(self.m, self.c, s, R, p, self.render, self.need); self.ev[s][p].set()
                for f in [ex.submit(one, p) for p in jobs]: f.result()
                for e in self.ev[s].values(): e.set()
                self.dl[s] = (TM.DL["sec"] - d0, time.perf_counter() - t0)

    def get(self, s, p):
        self.ev[s][p].wait(); return self.readers[s]

    def done(self, s):
        self.readers.pop(s, None); self.ahead.release()


class Pool:
    """Up to N forked workers; each draws one (product, view) of one step from the parent's data (copy-on-write, no pickling)."""
    def __init__(self, n):
        self.n, self.run, self.fail, self.stepcpu, self.sub = n, {}, 0, {}, {}
        import multiprocessing as mp; self.mp = mp.get_context("fork")

    def submit(self, s, fn, args):
        while len(self.run) >= self.n: self.reap(block=True)
        def child():
            try: fn(*args)
            except KeyError as e: print(f"{args[0]} step {s}: no field {e}, skipped", flush=True)
            except StopIteration as e: print(f"{args[0]} step {s}: {e}, skipped", flush=True)
            except Exception: traceback.print_exc(); sys.stdout.flush(); sys.stderr.flush(); os._exit(1)
            sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)   # fork with the downloader thread alive: workers never download
            pr = self.mp.Process(target=child); pr.start()
        self.run[pr] = (s, time.perf_counter()); self.sub[s] = self.sub.get(s, 0) + 1

    def reap(self, block=False):
        while True:
            for pr in list(self.run):
                if not pr.is_alive():
                    pr.join(); s, t0 = self.run.pop(pr); self.stepcpu.setdefault(s, [0.0, 0])
                    self.stepcpu[s][0] += time.perf_counter() - t0; self.stepcpu[s][1] += 1
                    if pr.exitcode: self.fail += 1
                    block = False
            if not block: return
            time.sleep(0.02)

    def wait_all(self):
        while self.run: self.reap(block=True)


def report(m, P, L, dispatched, final=False):
    """The one-line download vs draw timer, printed once every frame of a step is drawn."""
    for k in sorted(P.stepcpu):
        cpu, n = P.stepcpu[k]
        if k not in dispatched or (n < P.sub.get(k, 0) and not final): continue
        net, data = L.dl.get(k, (0, 0)) if L else (0, 0)
        print(f"timer {m} F{k:03d}: download {net:.1f} s (+decode {max(data - net, 0):.1f} s, in the background), draw {cpu:.1f} s "
              f"in {n} frames ({cpu / max(n, 1):.1f} s each, {P.n} at once)", flush=True); del P.stepcpu[k]


def prewarm(m, R, vids):
    """Fill the per-process caches once in the parent before any worker is forked, so every worker inherits them instead of
    rebuilding them per frame: fonts, Natural Earth outlines (and land/sea fills) projected for each view, each view's
    projected grid and KD-tree. Without this a forked worker pays the 'first frame' cost (about 4-5 s) on every frame."""
    for w in (500, 600, 700, 800, 900): HS.font(w)
    grid = next((v for v in R.cache.values() if isinstance(v, tuple) and len(v) == 3), None)
    for v in vids:
        fig, ax, ky = TM.frame(v); r = "10m" if v == "wa" else "50m"
        ax.add_feature(cf.NaturalEarthFeature("physical", "ocean", r), facecolor=HS.QPF_SEA, edgecolor="none", zorder=0.6)
        ax.add_feature(cf.NaturalEarthFeature("physical", "land", r), facecolor=HS.QPF_LAND, edgecolor="none", zorder=0.6)
        HS.outlines(ax, cf, res=r); TM.towns(ax, v); HS.frame(ax)
        HS.header(fig, "warm", "warm", "warm", "F+0", "00Z"); HS.credit(fig, "warm")
        if grid is not None:
            try:
                LA, LO, _ = TM.cut(grid[0], grid[1], [], v); proj_xy(ax, LO, LA)
                if FAST_VEC and np.ndim(LO) == 2: thin_vectors(ax, LO, LA, np.zeros(LO.shape), np.zeros(LO.shape), 4, 4)
            except Exception: pass
        fig.canvas.draw(); plt.close(fig)


def run_steps(m, c, steps, render, prods, views, ctx):
    need = (ACCUM - {"qpf"}) & set(prods); tot = 0; t_start = time.perf_counter()
    workers = int(os.environ.get("MENU_WORKERS", "0") or 0) or (os.cpu_count() or 1)
    prefetch = os.environ.get("MENU_PREFETCH", "1") != "0"
    if workers <= 1 and not prefetch:   # the old loop, unchanged apart from the timer line
        for s in steps:
            R = Reader(m, c, s); d0 = TM.DL["sec"]; t0 = time.perf_counter()
            if need:
                try: accumulate(m, c, s, R, ctx, need)
                except KeyError as e: print(f"{m} step {s}: accumulation field {e} missing, skipped", flush=True)
            for p in prods:
                if p != "peakgust" and p not in ACCUM and s not in render: continue
                try: PRODUCTS[p][0](m, c, s, R, vids_of(m, p, views), ctx)
                except KeyError as e: print(f"{m} {p} step {s}: no field {e}, skipped", flush=True)
                except StopIteration as e: print(f"{m} {p} step {s}: {e}, skipped", flush=True)
            tot += R.bytes; d = TM.DL["sec"] - d0
            print(f"timer {m} F{s:03d}: download {d:.1f} s, draw {time.perf_counter() - t0 - d:.1f} s", flush=True)
        print(f"{MODELS[m]['name']} {c:%Y%m%d%H}Z downloaded {tot/1e6:.1f} MB in {time.perf_counter() - t_start:.0f} s")
        sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
    L = Loader(m, c, steps, render, prods, need) if prefetch else None
    P = Pool(max(1, workers)); waited = {}; warmed = False
    allv = sorted({v for p in prods for v in vids_of(m, p, views)})
    for s in steps:
        w0 = time.perf_counter()
        R = L.get(s, None) if L else Reader(m, c, s)
        if not warmed and os.environ.get("MENU_PREWARM", "1") != "0":
            if L and not R.cache: R = L.get(s, prods[0]) if wanted(prods[0], s, render) else R
            prewarm(m, R, allv); warmed = True
        if need:
            try: accumulate(m, c, s, R, ctx, need)
            except KeyError as e: print(f"{m} step {s}: accumulation field {e} missing, skipped", flush=True)
        for p in prods:
            if not wanted(p, s, render): continue
            if L: R = L.get(s, p)
            fn = PRODUCTS[p][0]; vids = vids_of(m, p, views)
            try:
                if p in STATEFUL: fn(m, c, s, R, [], ctx)        # advance the running total in the main process
                elif p not in ACCUM and not L: fn(m, c, s, R, [], {"render": set(render), "peak": None})   # fetch here (no loader)
            except KeyError as e: print(f"{m} {p} step {s}: no field {e}, skipped", flush=True); continue
            except StopIteration as e: print(f"{m} {p} step {s}: {e}, skipped", flush=True); continue
            if p in ACCUM - {"qpf"} and s not in render: continue
            if p in STATEFUL and s not in render: continue
            snap = snapshot(ctx)
            def draw(m_, p_, s_, R_, v_, snap_):
                R_._lk, R_._locks = threading.Lock(), {}   # fresh locks after fork (the downloader thread may have held one)
                CTX.clear(); CTX.update(snap_); PRODUCTS[p_][0](m_, c, s_, R_, [v_], CTX)
            for v in vids: P.submit(s, draw, (m, p, s, R, v, snap))
        waited[s] = time.perf_counter() - w0
        tot += R.bytes
        if L: L.done(s)
        P.reap(); report(m, P, L, waited)
    P.wait_all(); report(m, P, L, waited, final=True)
    print(f"{MODELS[m]['name']} {c:%Y%m%d%H}Z downloaded {tot/1e6:.1f} MB in {time.perf_counter() - t_start:.0f} s, {P.fail} worker failures")
    sys.stdout.flush(); sys.stderr.flush(); os._exit(1 if P.fail else 0)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True, choices=list(MODELS)); ap.add_argument("--cycle")
    ap.add_argument("--steps"); ap.add_argument("--hours", type=int, default=240); ap.add_argument("--every", type=int, default=0)
    ap.add_argument("--products", default=",".join(PRODUCTS)); ap.add_argument("--views", default="na,pnw,pnwt,wa")
    ap.add_argument("--count", action="store_true", help="only print the number of map files this run would write")
    a = ap.parse_args(); m = a.model
    if a.count:
        c = dt.datetime(2026, 1, 1, 0, tzinfo=dt.timezone.utc)   # counting needs no real run
    else:
        c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else latest(m)
    maxh = {"hrrr": 48, "rrfs": 84}.get(m, 240)
    if a.steps: render = [int(x) for x in a.steps.split(",")]
    else:
        nat = native_steps(m, min(a.hours, maxh)); render = [s for s in nat if not a.every or s % a.every == 0]
    prods = [p for p in a.products.split(",") if p in PRODUCTS and m in PRODUCTS[p][1]]
    running = "peakgust" in prods or bool(ACCUM & set(prods))
    steps = sorted(set(render) | (set(s for s in native_steps(m, max(render)) if s <= max(render)) if running else set())) if render else []
    if a.count:   # same step / product / view rules as the render loop below, without touching any data
        n = 0; byp = {}
        for p in prods:
            fn, _, gv, hv = PRODUCTS[p]; vids = views_for(m, a.views.split(","), gv, hv)
            if m == "aifs" and p.startswith("t") and p not in ("td2m",): vids = [v for v in vids if v != "wa"]
            k = 0
            for s in render:
                if p in ("snowkuch", "snow10", "frzr", "qpf"): k += len(acc_windows(m, s))
                elif p == "snowk24": k += s >= 24
                elif p == "snowrate": k += (s - 1 in steps) if m in HIRES else 1   # 1 h rate needs the previous hour
                else: k += 1
            byp[p] = k * len(vids); n += k * len(vids)
        print(f"{m} files {n}", json.dumps(byp)); sys.stdout.flush(); os._exit(0)
    ctx = CTX; ctx.update({"render": set(render), "peak": None})
    run_steps(m, c, steps, render, prods, a.views.split(","), ctx)
