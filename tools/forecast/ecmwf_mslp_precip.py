#!/usr/bin/env python3
"""ECMWF 9 km MSLP + precipitation: sea-level pressure isobars (every 4 mb, labeled) with H/L centers over
precipitation accumulated in the period ending at the valid time (3 h to 72 h, then 6 h), shaded by type.

Methods (standard): QPF = tp(step) - tp(step - period), inches liquid equivalent. Type from the snowfall share of
the same period, sf / tp (>= 70 % snow, 30-70 % mix, else rain); hatched where the instantaneous ptype at the valid time
is freezing rain (3), ice pellets (8) or freezing drizzle (12). MSLP smoothed lightly before contouring. --model aifs: ECMWF AIFS 0.25 deg, 6 h periods, no ptype (no hatching). Data: ECMWF
IFS open data 0.1 deg (from the native ~9 km grid), CC BY 4.0. Basemap: Natural Earth. NOT scheduled; run by hand:
  python ecmwf_mslp_precip.py [--cycle YYYYMMDDHH] [--steps 6,24,48] | [--plan]   (--plan = 3 h to 72 h, then 6 h to 240 h)
Writes $SITE_BATCH/<cycle>/mslpprecip/qpf/<view>/<valid>/final.jpg + site_frame.json (model "ECMWF 9 km").
"""
import sys, argparse, datetime as dt, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import BoundaryNorm
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import house_style as HS
import temp_maps as TM          # shared: ECMWF range-request reader, NA / PNW / WA frames, crop, save
import cartopy.crs as ccrs, cartopy.feature as cf
import fastgeo  # noqa: F401  speed_build_v1: faster contour/contourf/barbs/quiver (WX_FASTGEO=0 = off)
from scipy.ndimage import gaussian_filter

PT = TM.PT
ICE_CODES = (3, 8, 12)
MM_PER_IN = 25.4


def period(step, model="ifs"):
    return 6 if model == "aifs" else (3 if step <= 72 else 6)   # AIFS open data is 6-hourly


def plan_steps():
    return list(range(3, 73, 3)) + list(range(78, 241, 6))


def render(c, step, per, lat, lon, P, Q, frac, ice, vid, out, model="ifs"):
    M = {"ifs": ("ECMWF IFS 0.1\u00b0", "ECMWF IFS", "ECMWF 9 km"), "aifs": ("ECMWF AIFS 0.25\u00b0", "ECMWF AIFS", "AIFS")}[model]
    V = TM.VIEWS[vid]; pc = ccrs.PlateCarree()
    LA, LO, (P, Q, frac, ice) = TM.cut(lat, lon, [P, Q, frac, ice], vid)
    fig, ax, key_y = TM.frame(vid)
    r = "10m" if vid == "wa" else "50m"     # quiet land / sea tint under the precip (no pressure fill on this product)
    ax.add_feature(cf.NaturalEarthFeature("physical", "ocean", r), facecolor=HS.QPF_SEA, edgecolor="none", zorder=1)
    ax.add_feature(cf.NaturalEarthFeature("physical", "land", r), facecolor=HS.QPF_LAND, edgecolor="none", zorder=1)
    sm = {"na": 1.0, "pnw": 0.7, "wa": 0.0}[vid]
    Qs = gaussian_filter(Q, sm) if sm else Q
    wet = Qs >= 0.01
    rain = np.where(wet & (frac < HS.MIX_SHARE), Qs, np.nan)
    mix = np.where(wet & (frac >= HS.MIX_SHARE) & (frac < HS.SNOW_SHARE), Qs, np.nan)
    snow = np.where(wet & (frac >= HS.SNOW_SHARE), Qs, np.nan)
    rl = HS.RAIN_LEVELS[HS.RAIN_LEVELS <= HS.QPF_RAIN_MAX]; rc = HS.cmap(HS.RAIN_COLORS[:len(rl) - 1], (0, 0, 0, 0), HS.rain_color(HS.QPF_RAIN_MAX))
    fr = ax.contourf(LO, LA, rain, levels=rl, cmap=rc, norm=BoundaryNorm(rl, rc.N), extend="max", transform=pc, zorder=2)
    mc, sc = HS.mix_cmap(), HS.snow_cmap(); L = HS.PTYPE_LEVELS
    fm = ax.contourf(LO, LA, mix, levels=L, cmap=mc, norm=BoundaryNorm(L, mc.N), extend="max", transform=pc, zorder=2)
    fs = ax.contourf(LO, LA, snow, levels=L, cmap=sc, norm=BoundaryNorm(L, sc.N), extend="max", transform=pc, zorder=2)
    icem = ((ice > 0.5) & wet).astype(float)
    if icem.any():
        matplotlib.rcParams["hatch.color"] = HS.ICE_HATCH_COLOR
        ax.contourf(LO, LA, icem, levels=[0.5, 1.5], colors="none", hatches=[HS.ICE_HATCH], transform=pc, zorder=3)
    HS.outlines(ax, cf, res="10m" if vid == "wa" else "50m")
    # isobars every 4 mb, labels on a white halo; H/L centers (house_style rules)
    Ps = gaussian_filter(P, 1.5 if vid != "wa" else 3.0)
    CLO, CLA, CP = LO, LA, Ps
    if vid == "wa":   # label positions are picked along the whole line: crop to the frame so labels land in view
        kx = (((LO + 180) % 360 - 180) > -125.2) & (((LO + 180) % 360 - 180) < -116.4); ky = (LA > 45.2) & (LA < 49.4)
        CLO, CLA, CP = LO[kx], LA[ky], Ps[np.ix_(ky, kx)]
    cs = ax.contour(CLO, CLA, CP, levels=np.arange(880, 1080, 4), colors=HS.ISOBAR_COLOR, linewidths=HS.ISOBAR_LW, transform=pc, zorder=4)
    clabels = ax.clabel(cs, fmt="%d", inline=False)
    for t in clabels:
        t.set_fontproperties(HS.font(700, 10)); t.set_path_effects(HS.halo("white", 3.2))
    S = gaussian_filter(P, {"na": 3, "pnw": 2, "wa": 2}[vid])
    x0, x1, y0, y1 = ax.get_extent(V["proj"]); mx, my = 0.02 * (x1 - x0), 0.04 * (y1 - y0); XY = {}

    def inside(i, j):
        x, y = V["proj"].transform_point(LO[j], LA[i], pc)
        cx, cy = min(max(x, x0 + mx), x1 - mx), min(max(y, y0 + my), y1 - my); XY[i, j] = (cx, cy)
        if (cx, cy) == (x, y):
            return True
        clo, cla = pc.transform_point(cx, cy, V["proj"])
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
    town_arts = TM.towns(ax, vid, (LA, LO, Q), TM.fmt_in2)   # town numbers: precip in the period, inches (all types)
    HS.frame(ax)
    valid = c + dt.timedelta(hours=step); vl = valid.astimezone(PT); sl = (valid - dt.timedelta(hours=per)).astimezone(PT)
    f = lambda t: f"{t:%a %-I %p}"
    HS.header(fig, "MSLP + Precipitation", f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT",
              f"{M[0]} {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {V['label']}  \u00b7  {per}-h precip {f(sl)} to {f(vl)} PT"
              f"  \u00b7  isobars every 4 mb" + ("  \u00b7  hatched: freezing rain / sleet" if model == "ifs" else "  \u00b7  no freezing-rain data (AIFS)"), f"F+{step}", f"{valid:%HZ %a}".upper())
    # three short keys: rain | mix | snow (inches liquid equivalent over the period)
    cb = HS.hbar(fig, fr, [1, 2, 3, 4], f"{per}-h precip (in)", key_y, x0=0.175, x1=0.565)
    cb.set_ticks([0.5, 1, 2, 3, 4]); cb.ax.set_xticklabels(["0.5", "1", "2", "3", "4"], fontproperties=HS.font(700, HS.BAR_LABEL_SIZE))
    for m, x0_, x1_, nm in ((fm, 0.59, 0.775, "MIX"), (fs, 0.80, 0.976, "SNOW"), (None, 0.175, 0.565, "RAIN")):
        if m is not None:
            H = fig.get_size_inches()[1]; cax = fig.add_axes([x0_, key_y, x1_ - x0_, 0.27 / H])
            b = fig.colorbar(m, cax=cax, orientation="horizontal", ticks=HS.PTYPE_TICKS, extendfrac=0.04)
            b.outline.set_edgecolor(HS.PANEL_EDGE); cax.tick_params(colors=HS.INK, length=5, width=1, pad=3)
            cax.set_xticklabels(["0.1", "0.5", "1", "2"], fontproperties=HS.font(700, HS.BAR_LABEL_SIZE))
        cax_ = fig.axes[-1] if m is not None else cb.ax
        cax_.text(0.012, 0.5, nm, transform=cax_.transAxes, ha="left", va="center", color="#15171c", fontproperties=HS.font(800, 10), zorder=9)
    HS.credit(fig, f"{M[1]}: ECMWF open data, CC BY 4.0. Modified. \u00a9 ECMWF, www.ecmwf.int.  Basemap: Natural Earth.")
    HS.clear_labels_near(fig, clabels, markers + town_arts)
    TM.save(fig, out, {"tab": "mslpprecip", "period": "qpf", "view": vid, "model": M[2], "cycle": f"{c:%Y%m%d%H}",
                       "start_pt": sl.isoformat(), "end_pt": vl.isoformat()})


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--cycle"); ap.add_argument("--steps", help="comma list of forecast hours")
    ap.add_argument("--plan", action="store_true", help="3 h to 72 h, then 6 h to 240 h"); ap.add_argument("--views", default="na,pnw,wa"); ap.add_argument("--model", default="ifs", choices=["ifs", "aifs"])
    a = ap.parse_args()
    c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else TM.latest_cycle(a.model)
    steps = plan_steps() if a.plan or not a.steps else [int(x) for x in a.steps.split(",")]
    tot = 0
    for s in steps:
        per = period(s, a.model); st = TM.Step(a.model, c, s); st0 = TM.Step(a.model, c, s - per)
        try:
            lat, lon, msl = st.field("msl"); _, _, tp1 = st.field("tp"); _, _, sf1 = st.field("sf")
            if a.model == "ifs": _, _, pt = st.field("ptype")
            else: pt = np.zeros_like(msl)   # AIFS open data has no precipitation-type field: no ice hatching
            if s - per > 0:
                _, _, tp0 = st0.field("tp"); _, _, sf0 = st0.field("sf")
            else:
                tp0 = sf0 = 0.0
        except StopIteration:
            print(f"step {s}: field missing, skipped", flush=True); continue
        dtp = np.maximum(tp1 - tp0, 0.0); dsf = np.maximum(sf1 - sf0, 0.0)     # m water equivalent
        Q = dtp * (1.0 if a.model == "aifs" else 1000.0) / MM_PER_IN   # AIFS tp/sf are kg m-2 (mm); IFS tp/sf are m
        frac = np.where(dtp > 1e-5, np.clip(dsf / np.maximum(dtp, 1e-9), 0, 1), 0.0)
        ice = np.isin(np.rint(pt).astype(int), ICE_CODES).astype(float)
        vt = f"{c + dt.timedelta(hours=s):%Y%m%d%H}"
        for v in a.views.split(","):
            out = f"{TM.ROOT}/{c:%Y%m%d%H}/mslpprecip" + ("-aifs" if a.model == "aifs" else "") + f"/qpf/{v}/{vt}"
            render(c, s, per, lat, lon, msl / 100.0, Q, frac, ice, v, out, a.model); print("ok", out, flush=True)
        tot += st.bytes + st0.bytes
    print(f"{a.model.upper()} {c:%Y%m%d%H}Z MSLP+precip downloaded {tot/1e6:.1f} MB")
    sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
