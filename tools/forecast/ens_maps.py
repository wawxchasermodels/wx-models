"""Ensemble low centers and 500 mb heights for ECMWF ENS (IFS, 50 members) and ECMWF AIFS ENS (50 members).

Data: ECMWF open data (CC BY 4.0), 0.25 deg perturbed members. IFS ENS: the enfo "ef" files (msl, gh 500).
AIFS ENS: the aifs-ens enfo "pf" files (msl, z 500 geopotential). Each member field is fetched with HTTP range requests
from the .index byte offsets (adjacent records coalesced), first from ECMWF's AWS open-data mirror, then from ECMWF.

Products (6 h frames):
  elows  Low centers: every member's sea-level pressure lows (dots colored by central pressure), the chance a low center
         passes within R km (fill), thin mean isobars, and the ensemble-mean lows marked L with member count and pressure range.
  e500   500 mb heights: ensemble-mean heights (black, every 6 dam), spread (fill, 1 std dev in dam), and each member's
         552 dam (blue) and 576 dam (red) line ("spaghetti").
Writes ROOT/<cycle>/<tab>-<src>/step/<view>/<valid>/final.jpg + site_frame.json like menu_maps.py.

usage: ens_maps.py eps|aifsens [--cycle YYYYMMDDHH] (--steps 48,96 | --hours 240) [--products elows,e500] [--views na,pnw,pnwt] [--e500-views na,pnw,pnwt]
"""
import sys, argparse, datetime as dt, json, os, urllib.request
from concurrent.futures import ThreadPoolExecutor
import numpy as np, eccodes as ec
import matplotlib, matplotlib.lines as mlines, matplotlib.patches
from matplotlib.colors import ListedColormap, BoundaryNorm
import menu_maps as MM
import temp_maps as TM
import house_style as HS
import cartopy.crs as ccrs, cartopy.feature as cf
import fastgeo  # noqa: F401  speed_build_v1: faster contour/contourf/barbs/quiver (WX_FASTGEO=0 = off)
from scipy.ndimage import gaussian_filter

PT, ROOT, get = TM.PT, TM.ROOT, TM.get
SRC = {
    "eps": dict(site="EPS", name="ECMWF ENS", path="ifs", kind="ef", z500=("gh", "500"), zfac=0.1,
                credit=TM.CREDIT.format(name="ECMWF ENS"), last=360),
    "aifsens": dict(site="AIFS ENS", name="ECMWF AIFS ENS", path="aifs-ens", kind="pf", z500=("z", "500"), zfac=0.1 / 9.80665,
                    credit=TM.CREDIT.format(name="ECMWF AIFS ENS"), last=360),
}
HOST = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/{p}/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-{k}"
MIRROR = "https://ecmwf-forecasts.s3.eu-central-1.amazonaws.com/{d}/{h:02d}z/{p}/0p25/enfo/{d}{h:02d}0000-{s}h-enfo-{k}"
LAT0, LAT1, LON0 = 5.0, 88.0, 145.0          # crop (0-360 longitudes) that holds every view box
VIEWS = ("na", "pnw", "pnwt")
# "Pacific NW tight" (ensemble maps only): Washington, Vancouver Island and the near Pacific, centered near western WA
# with the coast and offshore waters in view; tighter than the Pacific Northwest frame.
TM.VIEWS.setdefault("pnwt", dict(label="Pacific NW tight", size=(16, 10.5), proj=ccrs.Mercator(central_longitude=-126),
                                 ll=(-138.0, -113.5, 40.5, 54.5), box=(-145, -106, 36, 59)))
TM.SMOOTH.setdefault("pnwt", 0.6)
for _d, _v in ((HS.HL_RADIUS_KM, 300), (HS.HL_PROMINENCE_MB, 1.5), (HS.HL_EDGE_KM, 300), (HS.BARBS_ACROSS, 20)): _d.setdefault("pnwt", _v)


class Ens:
    """Member fields for one ensemble run, cached per (param, level, step)."""
    def __init__(self, src, c):
        self.src, self.S, self.c, self.cache, self.bytes, self.mirror_ok = src, SRC[src], c, {}, 0, True

    def url(self, s, host=HOST): return host.format(d=f"{self.c:%Y%m%d}", h=self.c.hour, p=self.S["path"], s=s, k=self.S["kind"])

    def get(self, s, want):
        miss = [w for w in want if (w, s) not in self.cache]
        if miss:
            idx = [json.loads(l) for l in get(self.url(s) + ".index").decode().splitlines()]
            recs = sorted([r for r in idx if r.get("type") == "pf" and any(r["param"] == p and r.get("levelist") == l for p, l in miss)],
                          key=lambda r: r["_offset"])
            groups = []
            for r in recs:
                a, b = r["_offset"], r["_offset"] + r["_length"] - 1
                if groups and a == groups[-1][1] + 1: groups[-1][1] = b
                else: groups.append([a, b])

            def fetch(ab):
                if self.mirror_ok:   # the mirror answers 503 "Slow Down" when busy; then stay on ECMWF's own server
                    try:
                        rq = urllib.request.Request(self.url(s, MIRROR) + ".grib2", headers={"Range": "bytes=%d-%d" % tuple(ab), "User-Agent": "wx-models (personal)"})
                        with urllib.request.urlopen(rq, timeout=60) as r: return r.read()
                    except Exception: self.mirror_ok = False
                return get(self.url(s) + ".grib2", tuple(ab))
            with ThreadPoolExecutor(8) as ex: blobs = list(ex.map(fetch, groups))
            got = {}
            for blob in blobs:
                self.bytes += len(blob); off = 0
                while True:
                    i = blob.find(b"GRIB", off)
                    if i < 0: break
                    L = int.from_bytes(blob[i + 8:i + 16], "big"); g = ec.codes_new_from_message(blob[i:i + L])
                    sn = ec.codes_get(g, "shortName"); lev = str(ec.codes_get(g, "level")) if ec.codes_get(g, "typeOfLevel") == "isobaricInhPa" else None
                    num = ec.codes_get(g, "number"); ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj")
                    la0, lo0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees"), ec.codes_get(g, "longitudeOfFirstGridPointInDegrees")
                    d = ec.codes_get(g, "iDirectionIncrementInDegrees"); v = ec.codes_get_values(g).reshape(nj, ni).astype("f4"); ec.codes_release(g)
                    lat = la0 - d * np.arange(nj); lon = (lo0 + d * np.arange(ni)) % 360; o = np.argsort(lon); lon = lon[o]
                    sl = (lat >= LAT0) & (lat <= LAT1); so = lon >= LON0
                    self.lat, self.lon = lat[sl], lon[so]
                    got.setdefault((sn, lev), {})[num] = v[:, o][np.ix_(sl, so)]
                    off = i + L
            for k, d_ in got.items(): self.cache[(k, s)] = np.stack([d_[n] for n in sorted(d_)])
            for w in miss:
                if (w, s) not in self.cache: raise KeyError(f"{w} step {s}")
        return [self.cache[(w, s)] for w in want]

    def drop(self, s):
        for k in [k for k in self.cache if k[1] <= s]: del self.cache[k]


_OROG = {}
def orog(E):
    """Terrain height (m) on the 0.25 deg crop, from deterministic AIFS step-0 surface geopotential (same grid)."""
    if "z" not in _OROG:
        for back in (0, 6, 12, 18, 24):
            try: la, lo, z = TM.Step("aifs", E.c - dt.timedelta(hours=back), 0).field("z"); break
            except Exception: continue
        lon = lo % 360; o = np.argsort(lon); lon = lon[o]; z = z[:, o] / 9.80665
        _OROG["z"] = z[np.ix_((la >= LAT0) & (la <= LAT1), lon >= LON0)]
    return _OROG["z"]


def stamp(fig, ax, E, s, vid, tab, title, extra):
    c, S = E.c, E.S; HS.frame(ax)
    valid = c + dt.timedelta(hours=s); vl = valid.astimezone(PT)
    HS.header(fig, title, f"Valid {vl:%a %-m-%-d} \u00b7 {vl:%-I %p} PT",
              f"{S['name']} 0.25\u00b0 50 members {c:%HZ} run {c.astimezone(PT):%-m-%-d-%y (%-I %p PT)}  \u00b7  {TM.VIEWS[vid]['label']}  \u00b7  {extra}",
              f"F+{s}", f"{valid:%HZ %a}".upper())
    HS.credit(fig, S["credit"])
    out = f"{ROOT}/{c:%Y%m%d%H}/{tab}-{E.src}/step/{vid}/{valid:%Y%m%d%H}"
    TM.save(fig, out, {"tab": tab, "period": "step", "view": vid, "model": S["site"], "cycle": f"{c:%Y%m%d%H}",
                       "start_pt": vl.isoformat(), "end_pt": vl.isoformat()})
    print("ok", E.src, tab, vid, s, flush=True)


def km_grid(LA, LO, la, lo):
    """Great-circle distance (km) from (la, lo) to every point of the 1-D LA x LO grid."""
    p1, p2 = np.radians(LA)[:, None], np.radians(la); dl = np.radians(LO[None, :] - lo)
    return 6371.0 * np.arccos(np.clip(np.sin(p1) * np.sin(p2) + np.cos(p1) * np.cos(p2) * np.cos(dl), -1, 1))


# ------------------------------------------------------------------------------------------------- low centers
LOW = {"na": dict(r=800, prom=4.0, strike=500, sm=1.2), "pnw": dict(r=400, prom=1.5, strike=300, sm=0.8),
       "pnwt": dict(r=300, prom=1.2, strike=250, sm=0.6)}
MAX_TERRAIN_M = 1000.0   # sea-level pressure over high ground is a reduction artifact (thermal/plateau "lows"); skip those
# chance of a member low within the view's strike radius: 12 blue steps (finer at the low end), light to deep blue
STRIKE_LEVELS = [5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]
STRIKE_ANCH = [(5, "#eef4fa"), (15, "#c9def0"), (30, "#8fbfe2"), (50, "#4f97cf"), (70, "#2a6db5"), (100, "#1d3f8f")]
# top class (the scale's max color): a low within 25 km in at least CORE_MIN members = the core of the ensemble's lows
CORE_KM, CORE_MIN, CORE_COL = 25, 5, "#0a1442"
DOT_BOUNDS = [850, 920, 950, 970, 980, 988, 996, 1004, 1100]
DOT_COLS = ["#0b0010", "#2a2a9e", "#6a1b7a", "#b0186a", "#d7191c", "#ef6c2f", "#f2b134", "#9aa0a6"]
DOT_LABELS = ["under 920", "920-949", "950-969", "970-979", "980-987", "988-995", "996-1003", "1004+"]
# reference places for the low-center list ("near X" when a low is within NEAR_KM); ocean points use their usual names
PLACES = [(n, la, lo) for n, la, lo, _ in TM.WA_TOWNS] + [
    ("Portland OR", 45.52, -122.68), ("Medford", 42.33, -122.87), ("Eureka", 40.80, -124.16), ("San Francisco", 37.77, -122.42),
    ("Los Angeles", 34.05, -118.24), ("Boise", 43.62, -116.20), ("Salt Lake City", 40.76, -111.89), ("Reno", 39.53, -119.81),
    ("Vancouver BC", 49.28, -123.12), ("Victoria", 48.43, -123.37), ("Prince Rupert", 54.32, -130.32), ("Haida Gwaii", 53.25, -132.0),
    ("Juneau", 58.30, -134.42), ("Yakutat", 59.55, -139.73), ("Anchorage", 61.22, -149.90), ("Kodiak", 57.79, -152.41),
    ("Dutch Harbor", 53.89, -166.54), ("Nome", 64.50, -165.41), ("Fairbanks", 64.84, -147.72), ("Whitehorse", 60.72, -135.06),
    ("Edmonton", 53.55, -113.49), ("Calgary", 51.05, -114.07), ("Regina", 50.45, -104.62), ("Winnipeg", 49.90, -97.14),
    ("Yellowknife", 62.45, -114.37), ("Churchill", 58.77, -94.17), ("Iqaluit", 63.75, -68.52), ("Thunder Bay", 48.38, -89.25),
    ("Montreal", 45.50, -73.57), ("Halifax", 44.65, -63.57), ("St. John's", 47.56, -52.71), ("Boston", 42.36, -71.06),
    ("New York", 40.71, -74.01), ("Chicago", 41.88, -87.63), ("Minneapolis", 44.98, -93.27), ("Denver", 39.74, -104.99),
    ("Billings", 45.78, -108.50), ("Great Falls", 47.50, -111.30), ("Kansas City", 39.10, -94.58), ("Dallas", 32.78, -96.80),
    ("Atlanta", 33.75, -84.39), ("Miami", 25.76, -80.19), ("Houston", 29.76, -95.37), ("Phoenix", 33.45, -112.07),
    ("Mexico City", 19.43, -99.13), ("Honolulu", 21.31, -157.86), ("Gulf of Alaska", 56.5, -145.0), ("Bering Sea", 58.0, -175.0),
    ("Hudson Bay", 60.0, -86.0), ("Labrador Sea", 58.0, -55.0),
    ("Bering Sea", 60.5, -178.0), ("Bering Sea", 55.5, -172.0), ("Aleutians", 52.0, -178.0), ("Gulf of Alaska", 58.5, -149.0),
    ("Gulf of Alaska", 54.0, -140.0), ("NE Pacific", 47.0, -135.0), ("NE Pacific", 41.0, -137.0), ("N Pacific", 47.0, -150.0),
    ("N Pacific", 40.0, -155.0), ("N Pacific", 33.0, -147.0), ("N Pacific", 50.0, -165.0), ("N Pacific", 40.0, -170.0),
    ("Beaufort Sea", 73.0, -140.0), ("Arctic Ocean", 80.0, -120.0), ("Baffin Bay", 73.0, -65.0), ("W Atlantic", 38.0, -62.0),
    ("Gulf of Mexico", 25.5, -90.0), ("E Pacific", 22.0, -120.0), ("Siberia", 65.0, 172.0), ("Kamchatka", 56.0, 160.0)]
NEAR_KM = 400


def where(la, lo):
    lo = ((lo + 180) % 360) - 180
    d = [(np.hypot(la - a, (lo - b) * np.cos(np.radians(la))) * 111.2, n) for n, a, b in PLACES]; km, n = min(d)
    ll = f"{abs(la):.1f}{'N' if la >= 0 else 'S'} {abs(lo):.1f}{'W' if lo < 0 else 'E'}"
    return ll, (n if km <= NEAR_KM else "")


PANEL_W = 0.092   # narrow left list, one column (figure fraction)
PANEL_GAP = 0.0035   # box to map gap, about 8 px at 2400 px wide


def low_panel(fig, ax, strong, weak, means, n):
    """Narrow left box right against the map (10-24-26): ensemble-mean lows in bold, then the 10 strongest and the 10 weakest
    member lows in view in one column, each 'pressure  #member' with its dot color. Type 1.3x the first narrow box; row
    spacing shrinks only if the rows would not fit the map height. Pressures and member numbers only, no locations."""
    b = ax.get_position(); x0 = b.x0 - PANEL_GAP - PANEL_W; W_, H_ = fig.get_size_inches()
    fig.patches.append(matplotlib.patches.FancyBboxPatch((x0, b.y0), PANEL_W, b.y1 - b.y0, boxstyle="round,pad=0,rounding_size=0.004",
                       transform=fig.transFigure, facecolor="#f6f3ec", edgecolor="#c9c4b8", lw=1.0, zorder=0))
    def t(x, y, s, w=600, sz=11.7, col="#1b1d22", ha="left"):
        fig.text(x, y, s, color=col, fontproperties=HS.font(w, sz), ha=ha, va="top")
    ms = means[:4]; mrows = max(1, (len(ms) + 1) // 2)
    need = 1.2 + 1.4 + 1.05 + 1.2 * mrows + 0.4 + 2 * (1.05 + 10) + 0.5   # in rows
    lh = min(0.28, (b.y1 - b.y0) * H_ / (need + 0.5)) / H_               # 1.3x row height (0.28 in), squeezed only when short of room
    y = b.y1 - 0.3 * lh; xl = x0 + 0.007; cw = (PANEL_W - 0.014) / 2
    t(xl, y, "Lows (mb)", 800, 13.6); y -= lh * 1.2
    t(xl, y, f"in view · {n} mem.", 500, 10.0, "#5b5e66"); y -= lh * 1.4
    t(xl, y, "Mean (red L)", 800, 12.0); y -= lh * 1.05
    if not ms: t(xl, y, "none", 500, 11, "#5b5e66"); y -= lh
    for k_, v_ in enumerate(ms):
        t(xl + (k_ % 2) * cw, y, f"{v_:.0f}", 900, 15.0, HS.L_COLOR)
        if k_ % 2 == 1 or k_ == len(ms) - 1: y -= lh * 1.2
    y -= lh * 0.4
    for head, rows in (("10 strongest", strong), ("10 weakest", weak)):
        t(xl, y, head, 800, 12.0); y -= lh * 1.05
        if not rows: t(xl, y, "none", 500, 11, "#5b5e66"); y -= lh
        for p_, m_ in rows:
            col = DOT_COLS[max(0, min(len(DOT_COLS) - 1, int(np.searchsorted(DOT_BOUNDS, p_, "right")) - 1))]
            fig.patches.append(matplotlib.patches.Ellipse((xl + 0.004, y - 0.42 * lh), 0.0062, 0.0062 * W_ / H_, transform=fig.transFigure,
                               facecolor=col, edgecolor="white", lw=0.6, zorder=3))
            t(xl + 0.011, y, f"{p_:.0f}", 800, 11.7); t(xl + 0.011 + 0.030, y, f"#{m_}", 500, 10.6, "#5b5e66"); y -= lh
        y -= lh * 0.5


def lows_of(P, LA, LO, Z, vid, inside_frame):
    k = LOW[vid]; Sm = gaussian_filter(P, k["sm"])
    ok = lambda i, j: Z[i, j] < MAX_TERRAIN_M and inside_frame(i, j)
    out = []
    for i, j, ch in HS.find_centers(Sm, LA, LO, k["r"], k["prom"], ok):
        if ch != "L": continue
        w = P[max(0, i - 2):i + 3, max(0, j - 2):j + 3]; out.append((LA[i], LO[j], float(w.min())))
    return out


def p_lows(E, s, vids):
    (p,) = E.get(s, [("msl", None)]); P = p / 100.0; Zs = orog(E); n = P.shape[0]; pc = ccrs.PlateCarree()
    for v in vids:
        V = TM.VIEWS[v]; k = LOW[v]
        LA, LO, A = TM.cut(E.lat, E.lon, [P[m] for m in range(n)] + [P.mean(0), Zs], v); Z = A[-1]; M = A[-2]; Pm = A[:-2]
        fig, ax, ky = TM.frame(v); bx = ax.get_position(); ax.set_position([PANEL_W + 0.034, bx.y0, 0.976 - PANEL_W - 0.034, bx.height])
        ax.apply_aspect()   # final map box, so "in view" matches what is drawn
        b = ax.get_position()   # slide the map left so the box sits right against it and the pair starts at the title margin
        ax.set_position([0.024 + PANEL_W + PANEL_GAP, b.y0, b.width, b.height]); ax.apply_aspect()
        x0, x1, y0, y1 = ax.get_extent(V["proj"])
        XY = {}
        def inside(i, j):
            if (i, j) not in XY: XY[i, j] = V["proj"].transform_point(LO[j], LA[i], pc)
            x, y = XY[i, j]; return x0 <= x <= x1 and y0 <= y <= y1
        mem = [lows_of(Pm[m], LA, LO, Z, v, inside) for m in range(n)]
        hit = np.zeros((n,) + M.shape, bool); core = np.zeros((n,) + M.shape, bool)
        for m, L in enumerate(mem):
            for la, lo, _ in L:
                d = km_grid(LA, LO, la, lo); hit[m] |= d <= k["strike"]; core[m] |= d <= CORE_KM
        prob = gaussian_filter(100.0 * hit.mean(0), 1.0)
        cm = MM.ramp(STRIKE_LEVELS, STRIKE_ANCH, under=(0, 0, 0, 0))
        f = MM.fill(ax, LO, LA, prob, STRIKE_LEVELS, cm, "neither", 1)
        nc = core.sum(0)
        if nc.max() >= CORE_MIN:
            ax.contourf(LO, LA, nc, levels=[CORE_MIN - 0.5, n + 1], colors=[CORE_COL], transform=pc, zorder=1.6)
        HS.outlines(ax, cf, res="50m")
        iso = ax.contour(LO, LA, gaussian_filter(M, 1.5 if v == "na" else 1.2), levels=np.arange(880, 1080, 4), colors="#4a4d55",
                         linewidths=0.8, transform=pc, zorder=3)
        for t in ax.clabel(iso, fmt="%d", inline=True, inline_spacing=4): t.set_fontproperties(HS.font(600, 8.5)); t.set_color("#4a4d55")
        allL = np.array([x for L in mem for x in L]) if any(mem) else np.zeros((0, 3))
        if len(allL):
            dcm = ListedColormap(DOT_COLS); dn = BoundaryNorm(DOT_BOUNDS, dcm.N)
            o = np.argsort(-allL[:, 2])   # deepest drawn last (on top)
            ax.scatter(allL[o, 1], allL[o, 0], c=allL[o, 2], cmap=dcm, norm=dn, s=26 if v == "na" else 34, edgecolors="white",
                       linewidths=0.7, transform=pc, zorder=5)
        # ensemble-mean lows: red L with the mean central pressure under it, slightly larger and bold
        means = []
        for la, lo, val in lows_of(M, LA, LO, Z, v, inside):
            x, y = V["proj"].transform_point(lo, la, pc)
            tL = ax.text(x, y, "L", color=HS.L_COLOR, fontproperties=HS.font(900, HS.HL_SIZE + 2), ha="center", va="center", transform=V["proj"],
                         path_effects=HS.halo("white", 2.4), zorder=7)
            tv = ax.annotate(f"{val:.0f}", (x, y), xycoords=V["proj"]._as_mpl_transform(ax), xytext=(0, -14), textcoords="offset points",
                             ha="center", va="top", color="#1b1d22", fontproperties=HS.font(900, 11), path_effects=HS.halo("white", 2.4), zorder=7)
            means.append(val)
        # member number = ECMWF ensemble number (perturbed members 1-50; members are stacked in GRIB 'number' order)
        tagged = sorted(((float(x[2]), m + 1) for m, L in enumerate(mem) for x in L), key=lambda r: r[0])
        low_panel(fig, ax, tagged[:10], tagged[::-1][:10], sorted(means), n)
        hd = [mlines.Line2D([], [], ls="", marker="o", ms=7, mfc=col, mec="white", label=lab) for col, lab in zip(DOT_COLS, DOT_LABELS)]
        lg = ax.legend(handles=hd, title="Member low (mb)", loc="lower left", fontsize=8.5, title_fontsize=9, framealpha=0.92,
                       facecolor="white", edgecolor="#c9c4b8", borderpad=0.5, handletextpad=0.3)
        lg.set_zorder(8)
        HS.hbar(fig, f, [5, 10, 20, 30, 50, 70, 90], f"Low within {k['strike']} km (%)", ky, x0=0.215, x1=0.872)
        hh = 0.27 / fig.get_size_inches()[1]; sw = fig.add_axes([0.888, ky, 0.088, hh]); sw.set_facecolor(CORE_COL)
        sw.set_xticks([]); sw.set_yticks([]); [sp.set_edgecolor(HS.PANEL_EDGE) for sp in sw.spines.values()]
        fig.text(0.932, ky - 0.008, f"within {CORE_KM} km", color=HS.INK, fontproperties=HS.font(700, HS.BAR_LABEL_SIZE), ha="center", va="top")
        stamp(fig, ax, E, s, v, "elows", "Ensemble Low Centers",
              "dots = member lows (color = mb), L = mean low (mb)")


# ------------------------------------------------------------------------------------------------- 500 mb heights
SPREAD_LEVELS = [1, 2, 3, 4, 6, 8, 10, 12, 15, 20, 25, 30]
SPREAD_ANCH = [(1, "#f7f2e6"), (3, "#efe0b8"), (6, "#e3bf7f"), (10, "#d38f55"), (15, "#bb5d43"), (20, "#8e3a52"), (30, "#5a2460")]
SPAG = [(552, "#1f5fbf"), (576, "#c62828")]


def p_500(E, s, vids):
    (z,) = E.get(s, [E.S["z500"]]); Z = z * E.S["zfac"]; pc = ccrs.PlateCarree()
    for v in vids:
        LA, LO, A = TM.cut(E.lat, E.lon, [Z.mean(0), Z.std(0)] + [Z[m] for m in range(Z.shape[0])], v)
        M, S, Zm = A[0], A[1], A[2:]
        sm = TM.SMOOTH.get(v, 0) or 0.01
        fig, ax, ky = TM.frame(v); cm = MM.ramp(SPREAD_LEVELS, SPREAD_ANCH, under=(0, 0, 0, 0))
        f = MM.fill(ax, LO, LA, gaussian_filter(S, sm), SPREAD_LEVELS, cm, "max", 1); f.set_alpha(0.8)
        HS.outlines(ax, cf, res="50m")
        for lev, col in SPAG:
            for m in Zm: ax.contour(LO, LA, gaussian_filter(m, sm), levels=[lev], colors=col, linewidths=0.55, alpha=0.75, transform=pc, zorder=3)
        MM.labelled(ax, LO, LA, gaussian_filter(M, sm), np.arange(480, 612, 6), lw=1.5, color="#101114")
        HS.hbar(fig, f, [1, 2, 4, 6, 10, 15, 20, 30], "Spread (dam)", ky)
        stamp(fig, ax, E, s, v, "e500", "500 mb Height: Mean, Spread + Spaghetti",
              "black = mean, fill = spread, thin = members' 552 / 576 dam")


PRODUCTS = {"elows": p_lows, "e500": p_500}


def latest(src):
    now = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0)
    for b in range(0, 48):
        c = now - dt.timedelta(hours=b)
        if c.hour % 12: continue
        try: get(Ens(src, c).url(240) + ".index", (0, 10)); return c
        except Exception: pass
    raise SystemExit(f"no {src} run found")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("src", choices=list(SRC)); ap.add_argument("--cycle"); ap.add_argument("--steps")
    ap.add_argument("--hours", type=int, default=240); ap.add_argument("--products", default=",".join(PRODUCTS)); ap.add_argument("--views", default=",".join(VIEWS))
    # 500 mb maps draw all three frames (tight PNW view switched on 10-24-26); --e500-views na,pnw drops it again (-82 files a run)
    ap.add_argument("--e500-views", default="na,pnw,pnwt")
    a = ap.parse_args()
    c = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc) if a.cycle else latest(a.src)
    steps = [int(x) for x in a.steps.split(",")] if a.steps else list(range(0, a.hours + 1, 6))
    prods = [p for p in a.products.split(",") if p in PRODUCTS]; vids = [v for v in a.views.split(",") if v in VIEWS]; E = Ens(a.src, c)
    for s in steps:
        for p in prods:
            vv = [v for v in vids if p != "e500" or v in a.e500_views.split(",")]
            if not vv: continue
            try: PRODUCTS[p](E, s, vv)
            except KeyError as e: print(f"{a.src} {p} step {s}: missing {e}, skipped", flush=True)
        E.drop(s)
    print(f"{SRC[a.src]['name']} {c:%Y%m%d%H}Z downloaded {E.bytes/1e6:.1f} MB")
    sys.stdout.flush(); sys.stderr.flush(); os._exit(0)
