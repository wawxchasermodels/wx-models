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
GLOBAL_VIEWS = ("wa", "wwa", "ewa", "passes", "pnwt", "pnw", "na")
MODELS = {   # grid "lcc" = HRRR 3 km, "ll" = 0.25 deg global (lat 90 -> -90, lon rolled to 0..360)
    "hrrr": dict(grid="lcc", views=("wa", "wwa", "ewa", "passes", "pnwhr"), cycles=(0, 6, 12, 18), steps=list(range(1, 49)), keep=2),
    "gfs":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 12), steps=list(range(3, 361, 3)), keep=2),
    "ifs":  dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 12), steps=list(range(3, 145, 3)) + list(range(150, 361, 6)), keep=2),
    "aifs": dict(grid="ll", views=GLOBAL_VIEWS, cycles=(0, 12), steps=list(range(6, 361, 6)), keep=2),
}
NOAA = ("hrrr", "gfs")

def _f(key, conv): return lambda R, m: conv(np.asarray(R.f(key)[2], float))
def _raw(key, conv):
    def g(R, m):
        if m not in NOAA: raise KeyError(key)
        return conv(np.asarray(R._idx(key, R.url)[2], float))
    return g
def _apcp(R, m):
    if m in NOAA: return np.asarray(R.acc0("APCP:surface")[2], float) / 25.4
    tp = np.asarray(R.f("tp")[2], float); return tp * 1000 / 25.4 if m == "ifs" else tp / 25.4
def _asnow(R, m):
    if m != "hrrr": raise KeyError("asnow")
    return np.asarray(R.acc0("ASNOW:surface")[2], float) / 0.0254
def _tcc(R, m):
    t = np.asarray(R.f("tcc")[2], float); return np.clip(t * 100.0 if np.nanmax(t) <= 1.01 else t, 0, 100)
def _ir(R, m):
    b = np.asarray(R.f("ir")[2], float) - 273.15; return np.clip(np.where(b > 60, np.nan, b), -100, 60)

FIELDS = {   # name: (getter, units)
    "t2m":  (_f("t2m", lambda k: (k - 273.15) * 1.8 + 32), "F"),
    "gust": (_f("gust", lambda v: v * 2.23694), "mph"),
    "mslp": (_f("msl", lambda p: p / 100.0), "mb"),
    "u10":  (_f("u10", lambda v: v * 1.94384), "kt"),
    "v10":  (_f("v10", lambda v: v * 1.94384), "kt"),
    "t850": (_f("T:850", lambda k: k - 273.15), "C"),
    "t700": (_f("T:700", lambda k: k - 273.15), "C"),
    "tcc":  (_tcc, "%"),
    "vis":  (_f("vis", lambda w: np.clip(w / 1609.34, 0, 10)), "mi"),
    "ir":   (_ir, "C"),
    "refc": (_raw("REFC:entire atmosphere", lambda d: np.clip(d, -10, 80)), "dBZ"),
    "frz":  (_raw("HGT:0C isotherm", lambda z: np.clip(z * 3.28084, 0, 20000)), "ft"),
    "apcp": (_apcp, "in"),
    "asnow": (_asnow, "in"),
}

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
    i0, i1, j0, j1 = crop; t = time.time(); ranges, sizes = {}, {}
    try: R = M.Reader(m, c, s)
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
        ranges[name] = rng(a)
        p = f"{out}/single/{name}_f{s:03d}.png"
        Image.fromarray(q8(a, *ranges[name]), "L").save(p, optimize=True); sizes[name] = os.path.getsize(p)
    return s, sizes, ranges, getattr(R, "bytes", 0), time.time() - t

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
    TM.VIEWS.setdefault("passes", dict(label="Cascade Passes", size=(16, 15), proj=lcc(-121.2), ll=(-123.9, -118.5, 46.2, 49.05), box=(-125, -117.5, 45.4, 49.8)))
WA_LIKE = ("wa", "wwa", "ewa", "passes")

def model_grid(m):
    """(la2d, lo2d, orog_ft or None, kind) on the model's own grid (lo2d in -180..180 for lcc, 0..360 for ll)."""
    import menu_maps as M
    c = latest_published(m) or (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=12)).replace(hour=0, minute=0, second=0, microsecond=0)
    R = M.Reader(m, c, MODELS[m]["steps"][0]); la, lo, _ = R.f("t2m"); la, lo = np.asarray(la, float), np.asarray(lo, float)
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
            TM.WA_TOWNS = [t for t in keepT if ins(t[1], t[2])]; TM.WA_PASSES = {k: v for k, v in keepP.items() if ins(v[1], v[2])}
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
    prods = {
        "t2m": dict(title="2 m Temperature", fields=["t2m"], key="Temp (\u00b0F)", ticks=HS.TEMP_TICKS, **table(HS.TEMP_LEVELS, CM["t2m"], "both"),
                    freeze=32, extra="32\u00b0F line dashed  \u00b7  {lo} to {hi}\u00b0F in view", pct=[0.5, 99.5]),
        "gust10": dict(title="10 m Wind Gusts", fields=["gust"], key="Gust (mph)", ticks=HS.WIND_TICKS, **table(HS.WIND_LEVELS, CM["gust10"], "max"),
                       extra=M.gust_note(m) + "  \u00b7  up to {hi} mph in view", pct=[1, 99.9]),
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
    }
    prods["vis"]["over"] = None
    for k in ("qpf", "snow", "refc"): prods[k]["min_show"] = prods[k]["levels"][0]   # blank below the first level (like the site)
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
            HS.credit(fig, TM.CREDIT_NOAA if (pid == "t2m" and m in NOAA) else M.credit(m))
            sizes[f"key_{m}_{pid}_{vid}"] = save(fig, f"{out}/{fn}")
        P["ticks"] = [float(t) for t in tk0]
    mp = f"{out}/manifest.json"; man = json.load(open(mp)) if os.path.exists(mp) else {}
    man.update(dpi=DPI, style=dict(BG=HS.BG, INK=HS.INK, MUTED=HS.MUTED, ACCENT=HS.ACCENT))
    man.setdefault("models", {})[m] = dict(name=M.MODELS[m]["name"], site=M.MODELS[m]["site"], res=M.MODELS[m]["res"], grid=MD["grid"],
                                          crop=[i0, i1, j0, j1], views=views, products=prods)
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
        meta[s] = dict(f=s, valid=v.isoformat(), valid_line=f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT", badge=[f"F+{s}", f"{v:%HZ %a}".upper()], ranges=ranges)
    # progressive: publish only the unbroken run of steps from the first one (no holes in the slider)
    ordered = []; 
    for s in want:
        if s in meta: ordered.append(meta[s])
        else: break
    fields = sorted({k for s_ in ordered for k in s_["ranges"]})
    MM = M.MODELS[m]
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
        want = MODELS[a.model]["steps"] if not a.steps else (lambda x, y: [s for s in MODELS[a.model]["steps"] if x <= s <= y])(*map(int, a.steps.split("-")))
        run, new = steps(a.model, a.cycle, want, a.out, a.workers)
        print(f"{a.model} {a.cycle}: +{len(new)} steps, {len(run['steps'])}/{run['expected']} published, complete={run['complete']}", flush=True)
    sys.stdout.flush(); os._exit(0)

if __name__ == "__main__": main()
