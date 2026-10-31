#!/usr/bin/env python3
"""ECMWF social-media model graphics (starter set, 10-31-2026; scope: SOCIAL_PRODUCTS_SCOPE_20261031.md).

  python3 make_social.py --out DIR [--run 2026103100] [--prods z500anom,t2ma,t850a,mslpqpf] [--views na,pnw]
                         [--hours 72,144] [--aspects h,v] [--logo TEXT] [--base http://.../d/]

Reads the fast site's own ECMWF IFS 0.25 data (manifest -> run.json -> 8-bit field PNGs, monthly climatology PNGs) from
--base (the site's /d/ data path or a mirror of it), decodes them exactly like viewer.js (getField / climMonth / climAt /
blur), so the anomaly numbers match the site, then draws 3840x2160 (h) and 2160x3840 (v) frames: dark base, bright
diverging fills, white contours, H/L, Montserrat header, color bar, model tag, credit and logo slot. Writes
<out>/<run>/<prod>_<view>_f<hhh>_<h|v>.png. Nothing is uploaded or posted.
Style notes adapted from the Video Editing Bot NARR maps (frame / regrid-to-pixels / overlays), copied, not imported."""
import argparse, io, json, os, sys, datetime as dt, urllib.request
from zoneinfo import ZoneInfo
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.colors as mcolors
from matplotlib import font_manager as fm, patheffects as pe
from matplotlib.patches import FancyBboxPatch
import cartopy.crs as ccrs, cartopy.feature as cf
from scipy.ndimage import gaussian_filter, map_coordinates, maximum_filter, minimum_filter
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
PT = ZoneInfo("America/Los_Angeles")
CACHE = os.environ.get("SOCIAL_CACHE", "/tmp/social_cache")

# ------------------------------------------------------------------ fonts (Montserrat, OFL; static weights cut from the variable font)
def fonts():
    d = os.path.join(CACHE, "fonts"); os.makedirs(d, exist_ok=True)
    src = "/usr/share/fonts/truetype/sand-box/google/Montserrat/Montserrat-VariableFont_wght.ttf"
    out = {}
    for n, w in (("ExtraBold", 800), ("Bold", 700), ("SemiBold", 600), ("Medium", 500)):
        p = os.path.join(d, f"Montserrat-{n}.ttf")
        if not os.path.exists(p):
            from fontTools.ttLib import TTFont
            from fontTools.varLib import instancer
            instancer.instantiateVariableFont(TTFont(src), {"wght": w}).save(p)
        out[n] = fm.FontProperties(fname=p)
    return out

# ------------------------------------------------------------------ data (same decode as viewer.js)
class Data:
    def __init__(self, base):
        self.base = base.rstrip("/") + "/"; self.man = self.json("manifest.json"); self.mem = {}
    def raw(self, path):
        p = os.path.join(CACHE, "d", path.split("?")[0])
        if not os.path.exists(p) or path.endswith(".json"):
            b = urllib.request.urlopen(self.base + path, timeout=60).read()
            os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(b)
        return open(p, "rb").read()
    def json(self, path): return json.loads(self.raw(path))
    def png(self, path):
        if path not in self.mem: self.mem[path] = np.asarray(Image.open(io.BytesIO(self.raw(path))).convert("RGBA")).astype(np.float64)
        return self.mem[path]
    def run(self, run): return self.json(f"runs/ifs/{run}/run.json")
    def field(self, R, name, f):                       # viewer.js getField
        st = next(s for s in R["steps"] if s["f"] == f); rg = st["ranges"][name]; pk = (st.get("packs") or {}).get(name)
        file, ch = (pk[0], pk[1]) if pk else (name, 0)
        px = self.png(f"{R['base']}/" + R["file"].replace("{name}", file).replace("{f:03d}", f"{f:03d}"))[:, :, ch]
        lo, hi = rg[0], rg[1]
        if len(rg) > 2 and rg[2] == 2: q = px / 255; return (lo + q * q * (hi - lo)).astype(np.float32)
        return (lo + px * ((hi - lo) / 255)).astype(np.float32)
    def clim_month(self, varn, k):                    # viewer.js climMonth (16-bit R*256+G)
        C = self.man["models"]["ifs"]["clim"][varn]; I = self.png(C["files"][k]); lo, hi = C["ranges"][k]
        return (lo + (I[:, :, 0] * 256 + I[:, :, 1]) / 65535 * (hi - lo)).astype(np.float32)
    def clim_at(self, varn, valid):                    # viewer.js climAt (months blended; t2m also between 00/06/12/18Z)
        C = self.man["models"]["ifs"]["clim"][varn]; v = valid.astimezone(dt.timezone.utc); mo = v.month - 1
        mid = dt.datetime(v.year, mo + 1, 15, tzinfo=dt.timezone.utc)
        m2 = (mo + (1 if v >= mid else -1) + 12) % 12; w = min(1.0, abs((v - mid).total_seconds()) / (30.4 * 86400))
        parts = [(mo, 1 - w), (m2, w)]
        if C.get("hours"):
            hx = (v.hour + v.minute / 60) / 6; h0 = int(np.floor(hx)) % 4; h1 = (h0 + 1) % 4; wh = hx - np.floor(hx)
            parts = [q for k, wk in parts for q in ((k * 4 + h0, wk * (1 - wh)), (k * 4 + h1, wk * wh))]
        o = None
        for k, wk in parts:
            if wk <= 1e-6: continue
            a = self.clim_month(varn, k) * np.float32(wk); o = a if o is None else o + a
        return o

def blur(a, s): return gaussian_filter(a.astype(np.float32), s, mode="reflect", truncate=4.0)

# ------------------------------------------------------------------ color scales (bright on dark)
NEG = [(0.0, "#2b0757"), (0.25, "#5a2fd6"), (0.5, "#1f6bff"), (0.78, "#2fd0ff"), (1.0, "#b8f1ff")]
POS = [(0.0, "#fff4a3"), (0.25, "#ffcf3a"), (0.5, "#ff8a1f"), (0.75, "#ef2330"), (1.0, "#ff46d6")]
def diverging(levels, neutral):
    """one color per band; |center| < neutral -> transparent (the dark base shows through)"""
    neg = mcolors.LinearSegmentedColormap.from_list("n", NEG); pos = mcolors.LinearSegmentedColormap.from_list("p", POS)
    top = max(abs(levels[0]), abs(levels[-1])); cols = []
    for a, b in zip(levels[:-1], levels[1:]):
        c = (a + b) / 2
        if abs(c) < neutral: cols.append((0, 0, 0, 0))
        elif c < 0: cols.append(neg(1 - min(1, (-c - neutral) / (top - neutral)) ))
        else: cols.append(pos(min(1, (c - neutral) / (top - neutral))))
    return cols, NEG[0][1], POS[-1][1]

def product(D, R, prod, f):
    st = next(s for s in R["steps"] if s["f"] == f); valid = dt.datetime.fromisoformat(st["valid"])
    if prod == "z500anom":
        z = D.field(R, "z500", f); a = blur(z - D.clim_at("z500", valid), 1.0)          # m, exactly the site's fill
        lv = list(np.arange(-30, 30.1, 3)); cols, un, ov = diverging(lv, 1.5)
        return dict(title="500 mb Height Anomaly", value=a, show=a / 10, unit="dam", key="500 mb height anomaly (dam) vs 1991-2020",
                    levels=lv, colors=cols, under=un, over=ov, ticks=list(range(-30, 31, 6)),
                    cont=blur(z * 0.1, 1.5), cint=6, clab="{:.0f}", cstyle="solid", valid=valid)
    if prod == "t2ma":
        t = D.field(R, "t2m", f); a = t - D.clim_at("t2m", valid)
        lv = list(np.arange(-30, 30.1, 2)); cols, un, ov = diverging(lv, 1.0)
        return dict(title="2 m Temperature Anomaly", value=a, show=a, unit="°F", key="2 m temperature anomaly (°F) vs 1991-2020",
                    levels=lv, colors=cols, under=un, over=ov, ticks=list(range(-30, 31, 10)), valid=valid)
    if prod == "t850a":
        t = D.field(R, "t850", f); a = t - D.clim_at("t850", valid)
        lv = list(np.arange(-15, 15.1, 1.5)); cols, un, ov = diverging(lv, 0.75)
        return dict(title="850 mb Temperature Anomaly", value=a, show=a, unit="°C", key="850 mb temperature anomaly (°C) vs 1991-2020",
                    levels=lv, colors=cols, under=un, over=ov, ticks=[-15, -9, -3, 3, 9, 15],
                    cont=blur(t, 1.0), cint=5, clab="{:.0f}°", cstyle="dashed", zero=True, valid=valid)
    if prod == "mslpqpf":
        P = D.man["models"]["ifs"]["products"]["mslpqpf"]
        a = D.field(R, "apcp", f); b = D.field(R, "apcp", f - 6) if f > 6 else 0 * a; q = np.maximum(0, a - b)   # 6 h precip (in)
        m = D.field(R, "mslp", f)
        lv = [0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
        ramp = mcolors.LinearSegmentedColormap.from_list("q", ["#1d8f3a", "#3fd34c", "#c8f53a", "#ffe13a", "#ff9a1f", "#ff3d2e", "#e2187a", "#b44dff", "#e7c8ff"])
        cols = [ramp(i / (len(lv) - 2)) for i in range(len(lv) - 1)]
        return dict(title="Pressure + 6 h Precipitation", value=m, value2=q, show=q, unit="in", key="6 h precipitation (in)  ·  isobars every 4 mb",
                    levels=lv, colors=cols, under=(0, 0, 0, 0), over="#ffffff", ticks=[0.05, 0.1, 0.3, 0.5, 1.0, 2.0, 3.0], tickfmt="{:g}",
                    cont=blur(m, 1.0), cint=4, clab="{:.0f}", cstyle="solid", hl=blur(m, 2.0), valid=valid)
    raise SystemExit(f"unknown product {prod}")

# ------------------------------------------------------------------ frames
W_, H_ = {"h": (3840, 2160), "v": (2160, 3840)}, None
VIEWS = {   # center (lon, lat), half-width of the frame (m), LCC parallels, label, towns
    "na":  dict(c={"h": (-108, 44.5), "v": (-117, 46.0)}, half={"h": 4.4e6, "v": 2.25e6}, lon0=-110, sp=(33, 55), label="North America & NE Pacific",
                towns=["Seattle", "Portland", "San Francisco", "Los Angeles", "Denver", "Phoenix", "Salt Lake City", "Vancouver", "Calgary",
                       "Anchorage", "Dallas", "Chicago", "Minneapolis", "Boise", "Las Vegas"], ms=14, fs=44),
    "pnw": dict(c={"h": (-121.3, 46.4), "v": (-121.0, 46.6)}, half={"h": 0.98e6, "v": 0.56e6}, lon0=-121, sp=(42, 50), label="Pacific Northwest",
                towns=["Seattle", "Portland", "Spokane", "Vancouver", "Victoria", "Bellingham", "Yakima", "Tri-Cities", "Wenatchee", "Boise", "Eugene",
                       "Medford", "Bend", "Olympia", "Pendleton", "Kelowna"], ms=16, fs=50),
}
TOWNS = {"Seattle": (-122.33, 47.61), "Portland": (-122.68, 45.52), "Spokane": (-117.43, 47.66), "San Francisco": (-122.42, 37.77),
         "Los Angeles": (-118.24, 34.05), "Denver": (-104.99, 39.74), "Phoenix": (-112.07, 33.45), "Salt Lake City": (-111.89, 40.76),
         "Vancouver": (-123.12, 49.28), "Calgary": (-114.07, 51.05), "Anchorage": (-149.9, 61.22), "Dallas": (-96.8, 32.78), "Chicago": (-87.63, 41.88),
         "Minneapolis": (-93.27, 44.98), "Boise": (-116.2, 43.62), "Las Vegas": (-115.14, 36.17), "Victoria": (-123.37, 48.43),
         "Bellingham": (-122.48, 48.75), "Yakima": (-120.51, 46.6), "Tri-Cities": (-119.17, 46.23), "Wenatchee": (-120.31, 47.42),
         "Eugene": (-123.09, 44.05), "Medford": (-122.87, 42.33), "Bend": (-121.31, 44.06), "Olympia": (-122.9, 47.04),
         "Pendleton": (-118.79, 45.67), "Kelowna": (-119.5, 49.89)}
PC = ccrs.PlateCarree()
CROP = (8, 600)   # ECMWF 0.25 crop origin (row, col) of the global 90N..90S / 0..359.75E grid; row 0 = 88N (north up)

_geo = {}
def geometry(view, k):
    if (view, k) in _geo: return _geo[(view, k)]
    V = VIEWS[view]; W, H = W_[k]
    proj = ccrs.LambertConformal(central_longitude=V["lon0"], central_latitude=47, standard_parallels=V["sp"])
    cx, cy = proj.transform_point(*V["c"][k], PC); hx = V["half"][k]; hy = hx * H / W
    ext = (cx - hx, cx + hx, cy - hy, cy + hy)
    s = 2   # field sampled every 2 output px, drawn with bilinear smoothing (fills are smooth; lines are vectors)
    xs = np.linspace(ext[0], ext[1], W // s); ys = np.linspace(ext[3], ext[2], H // s)
    X, Y = np.meshgrid(xs, ys); ll = PC.transform_points(proj, X, Y)
    rows = (88.0 - ll[..., 1]) / 0.25; cols = ((ll[..., 0] % 360) - 150.0) / 0.25
    _geo[(view, k)] = g = dict(proj=proj, ext=ext, X=X, Y=Y, rows=rows, cols=cols); return g

def sample(a, g, smooth):
    b = gaussian_filter(a.astype(np.float64), smooth) if smooth else a
    return map_coordinates(b, [g["rows"], g["cols"]], order=3, mode="nearest")

def to_rgba(v, P):
    lv = P["levels"]; idx = np.digitize(v, lv) - 1; n = len(lv) - 1
    tab = np.array([mcolors.to_rgba(c) for c in P["colors"]] + [mcolors.to_rgba(P["under"]), mcolors.to_rgba(P["over"])])
    idx = np.where(v < lv[0], n, np.where(v >= lv[-1], n + 1, np.clip(idx, 0, n - 1)))
    out = tab[idx]; out[..., 3] *= 0.9; return out

BG, LAND, LINE = "#0b0f16", "#151b24", "#c9d3df"

def text(fig, W, H, x, y, s, f, px, color="#fff", ha="left", va="baseline", stroke=0, **kw):
    t = fig.text(x / W, 1 - y / H, s, fontproperties=f, fontsize=px * 72 / 200, color=color, ha=ha, va=va, **kw)
    if stroke: t.set_path_effects([pe.withStroke(linewidth=stroke, foreground="#000000c0")])
    return t

def text_w(fig, t):
    r = fig.canvas.get_renderer(); return t.get_window_extent(r).width

def band(fig, y0, y1, H, top):
    ax = fig.add_axes([0, 1 - y1 / H, 1, (y1 - y0) / H], zorder=5); ax.axis("off")
    n = 256; a = np.linspace(0, 1, n) ** 1.3; a = a[::-1] if top else a
    g = np.zeros((n, 1, 4)); g[..., 0:3] = 0.03; g[:, 0, 3] = a * 0.88
    ax.imshow(g, aspect="auto", extent=(0, 1, 0, 1), origin="upper", interpolation="bilinear")

def wrap(fig, s, f, px, maxw, W, H):
    words, lines, cur = s.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip(); probe = text(fig, W, H, 0, -9999, t, f, px); wd = text_w(fig, probe); probe.remove()
        if wd > maxw and cur: lines.append(cur); cur = w
        else: cur = t
    return lines + [cur]

def render(D, R, run, prod, view, f, k, out, F, logo=""):
    P = product(D, R, prod, f); g = geometry(view, k); V = VIEWS[view]; W, H = W_[k]
    fig = plt.figure(figsize=(W / 200, H / 200), dpi=200, facecolor=BG)
    ax = fig.add_axes([0, 0, 1, 1], projection=g["proj"]); ax.set_facecolor(BG); ax.set_extent(g["ext"], crs=g["proj"])
    sc = "10m" if view == "pnw" else "50m"
    ax.add_feature(cf.NaturalEarthFeature("physical", "land", sc), facecolor=LAND, edgecolor="none", zorder=0)
    smooth = 0.8 if view == "pnw" else 0.4
    fill = sample(P["show"], g, smooth)
    ax.imshow(to_rgba(fill, P), extent=g["ext"], transform=g["proj"], origin="upper", interpolation="bilinear", zorder=2)
    lw = 1.9 if k == "h" else 1.7
    ax.add_feature(cf.NaturalEarthFeature("physical", "coastline", sc), facecolor="none", edgecolor=LINE, linewidth=lw, zorder=6)
    ax.add_feature(cf.NaturalEarthFeature("cultural", "admin_0_boundary_lines_land", sc), facecolor="none", edgecolor=LINE, linewidth=lw * 0.9, zorder=6)
    ax.add_feature(cf.NaturalEarthFeature("cultural", "admin_1_states_provinces_lines", "50m"), facecolor="none", edgecolor="#9aa6b5", linewidth=lw * 0.55, alpha=0.85, zorder=6)
    if "cont" in P:   # white contours with labels (heights / isobars / isotherms)
        c = sample(P["cont"], g, smooth); lo = np.floor(np.nanmin(c) / P["cint"]) * P["cint"]; hi = np.ceil(np.nanmax(c) / P["cint"]) * P["cint"]
        lv = np.arange(lo, hi + P["cint"], P["cint"])
        if P.get("zero"): lv = lv[lv != 0]
        cs = ax.contour(g["X"], g["Y"], c, levels=lv, colors="white", linewidths=lw * 1.15, linestyles=P["cstyle"], transform=g["proj"], zorder=7, alpha=0.95)
        for a_ in cs.collections if hasattr(cs, "collections") else [cs]:
            a_.set_path_effects([pe.withStroke(linewidth=lw * 3.2, foreground="#00000080")])
        lab = ax.clabel(cs, fmt=lambda v: P["clab"].format(v), fontsize=(34 if k == "h" else 32) * 72 / 200, inline=True, inline_spacing=8)
        for t in lab: t.set_fontproperties(F["Bold"]); t.set_fontsize((34 if k == "h" else 32) * 72 / 200); t.set_color("white"); t.set_path_effects([pe.withStroke(linewidth=4, foreground="#000000b0")])
        if P.get("zero"):   # 0 °C at 850 mb: the snow-level-ish line, heavier
            z = ax.contour(g["X"], g["Y"], c, levels=[0], colors="#7fe3ff", linewidths=lw * 2.0, transform=g["proj"], zorder=7)
    if "hl" in P: hl(ax, g, P, view, k, F)
    # towns
    for n in V["towns"]:
        lon, lat = TOWNS[n]; x, y = g["proj"].transform_point(lon, lat, PC); e = g["ext"]
        mx, my = (e[1] - e[0]) * 0.03, (e[3] - e[2]) * 0.03
        if not (e[0] + mx < x < e[1] - mx and e[2] + my < y < e[3] - my): continue
        ax.plot(x, y, "o", ms=V["ms"] * 72 / 200 * 2, mfc="white", mec="black", mew=1.4, transform=g["proj"], zorder=9)
        ax.text(x, y, "  " + n, transform=g["proj"], fontproperties=F["Bold"], fontsize=V["fs"] * 72 / 200, color="white", va="center", zorder=9,
                path_effects=[pe.withStroke(linewidth=5, foreground="#000000c0")])
    header(fig, P, R, run, f, k, W, H, F)
    footer(fig, P, view, k, W, H, F, logo)
    os.makedirs(os.path.dirname(out), exist_ok=True); fig.savefig(out, dpi=200, facecolor=BG); plt.close(fig)
    return P

def hl(ax, g, P, view, k, F):
    a = P["hl"]; size = 25 if view == "na" else 13; mx = maximum_filter(a, size, mode="nearest"); mn = minimum_filter(a, size, mode="nearest")
    e = g["ext"]; W, H = W_[k]
    for kind, mask, col in (("H", (a == mx) & (mx - minimum_filter(a, size * 2, mode="nearest") > 8), "#4d9bff"),
                            ("L", (a == mn) & (maximum_filter(a, size * 2, mode="nearest") - mn > 8), "#ff3b3b")):
        cand = sorted(zip(*np.nonzero(mask)), key=lambda ij: a[ij] if kind == "L" else -a[ij]); keep = []
        for i, j in cand:   # one marker per centre (flat tops give several equal cells); strongest first, >= `size` cells apart
            if any((i - p) ** 2 + (j - q) ** 2 < size * size for p, q in keep): continue
            keep.append((i, j))
        for i, j in keep:
            lat = 88.0 - (i + 0) * 0.25; lon = 150.0 + j * 0.25
            x, y = g["proj"].transform_point(lon if lon <= 180 else lon - 360, lat, PC)
            fx, fy = (x - e[0]) / (e[1] - e[0]), (e[3] - y) / (e[3] - e[2])   # 0..1 across / down the frame
            top, bot = (0.30, 0.80) if k == "v" else (0.28, 0.76)
            if not (0.04 < fx < 0.96 and top < fy < bot): continue
            ax.text(x, y, kind, transform=g["proj"], fontproperties=F["ExtraBold"], fontsize=(120 if k == "h" else 110) * 72 / 200, color=col,
                    ha="center", va="center", zorder=10, path_effects=[pe.withStroke(linewidth=7, foreground="#000000d0")])
            ax.text(x, y, f"\n\n{a[i, j]:.0f}", transform=g["proj"], fontproperties=F["Bold"], fontsize=44 * 72 / 200, color="white",
                    ha="center", va="center", zorder=10, path_effects=[pe.withStroke(linewidth=5, foreground="#000000d0")])

def header(fig, P, R, run, f, k, W, H, F):
    v = k == "v"; x = 110; top = 270 if v else 100
    band(fig, 0, (1150 if v else 640), H, True)
    pill_px = 58 if v else 54; ph = pill_px * 1.55
    t = text(fig, W, H, x + 28, top + ph * 0.70, "ECMWF", F["ExtraBold"], pill_px, zorder=8); pw = text_w(fig, t) + 56
    fig.add_artist(FancyBboxPatch((x / W, 1 - (top + ph) / H), pw / W, ph / H, boxstyle="round,pad=0,rounding_size=0.008", transform=fig.transFigure,
                                  facecolor="#2f8cff", edgecolor="none", zorder=7))
    init = dt.datetime.strptime(run, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc)
    text(fig, W, H, x + pw + 28, top + ph * 0.70, f"IFS 0.25°  ·  {init:%H}Z {init:%a %b} {init.day} run", F["SemiBold"], pill_px * 0.92, color="#c3cad6", zorder=8)
    tpx = 172 if v else 150; y = top + ph + 40 + tpx * 0.78
    lines = wrap(fig, P["title"].upper(), F["ExtraBold"], tpx, W - 2 * x - (0 if v else 900), W, H)
    for i, s in enumerate(lines): text(fig, W, H, x, y + i * tpx * 1.02, s, F["ExtraBold"], tpx, stroke=6, zorder=8)
    y += (len(lines) - 1) * tpx * 1.02 + tpx * 0.62 + 30
    vl = P["valid"].astimezone(PT); vz = P["valid"].astimezone(dt.timezone.utc)
    h12 = vl.strftime("%I").lstrip("0"); s = f"{vl:%a %b} {vl.day}  ·  {h12} {vl:%p} {vl.tzname()}  ({vz:%H}Z)"
    text(fig, W, H, x, y + 70, s, F["Bold"], 80 if v else 74, color="#ffc24d", stroke=5, zorder=8)
    # F+ / day badge (top right)
    bp = 60 if v else 58; bt = f"F+{f}"; t = text(fig, W, H, W - x - 34, top + ph * 0.70, bt, F["ExtraBold"], bp, ha="right", zorder=9); bw = text_w(fig, t) + 68
    fig.add_artist(FancyBboxPatch(((W - x - bw) / W, 1 - (top + ph) / H), bw / W, ph / H, boxstyle="round,pad=0,rounding_size=0.008", transform=fig.transFigure,
                                  facecolor="#111316e0", edgecolor="#ffffff70", linewidth=2, zorder=8))
    d = f // 24
    text(fig, W, H, W - x, top + ph + 70, f"DAY {d}" if f % 24 == 0 else f"DAY {d + 1}", F["Bold"], 50, color="#c3cad6", ha="right", zorder=9)

def footer(fig, P, view, k, W, H, F, logo):
    v = k == "v"; x = 110
    if v: y_cred, y_tick, bar_h, y_bar, y_key = H - 440, H - 500, 74, H - 650, H - 690
    else: y_cred, y_tick, bar_h, y_bar, y_key = H - 70, H - 120, 64, H - 262, H - 296
    band(fig, (H - 1250 if v else H - 620), H, H, False)
    bw = W - 2 * x if v else 2300
    ax = fig.add_axes([x / W, 1 - (y_bar + bar_h) / H, bw / W, bar_h / H], zorder=8)
    n = len(P["levels"]) - 1
    tab = [mcolors.to_rgba(c) for c in P["colors"]]
    img = np.array([[tab[i] if tab[i][3] > 0 else (0.18, 0.2, 0.24, 1.0) for i in range(n)]])
    ax.imshow(img, aspect="auto", extent=(0, n, 0, 1), interpolation="nearest"); ax.set_xlim(0, n); ax.set_ylim(0, 1)
    for s in ax.spines.values(): s.set_edgecolor("#ffffffa0"); s.set_linewidth(2)
    ax.set_yticks([]); ax.set_xticks([])
    lv = P["levels"]
    def pos(t):
        i = int(np.clip(np.searchsorted(lv, t, side="right") - 1, 0, n - 1)); return i + (t - lv[i]) / (lv[i + 1] - lv[i])
    fmt = P.get("tickfmt", "{:+g}")
    for t in P["ticks"]:
        px = x + pos(t) * bw / n
        s = fmt.format(t) if t != 0 else "0"
        text(fig, W, H, px, y_tick, s.replace("-", "−"), F["Bold"], 56 if v else 52, ha="center", stroke=4, zorder=9)
        fig.add_artist(plt.Line2D([px / W] * 2, [1 - (y_bar + bar_h) / H, 1 - (y_bar + bar_h + 14) / H], color="#ffffffd0", lw=2.5, transform=fig.transFigure, zorder=9))
    text(fig, W, H, x, y_key, P["key"], F["Bold"], 50 if v else 48, color="#e9ecf1", stroke=4, zorder=9)
    cred = f"Data: ECMWF open data (CC-BY-4.0)  ·  {VIEWS[view]['label']}"
    if v: text(fig, W, H, x, y_cred, cred, F["Medium"], 40, color="#c3cad6", zorder=9)
    else: text(fig, W, H, W - x, y_cred, cred, F["Medium"], 40, color="#c3cad6", ha="right", zorder=9)
    # logo slot (text, or a dashed placeholder box until the page's logo file is supplied)
    lx1, ly = W - x, (y_key - 30 if v else H - 250)
    if logo: text(fig, W, H, lx1, ly + 40, logo, F["ExtraBold"], 84, ha="right", stroke=5, zorder=9)
    else:
        bwid, bht = 520, 150
        fig.add_artist(FancyBboxPatch(((lx1 - bwid) / W, 1 - (ly + 30) / H), bwid / W, bht / H, boxstyle="round,pad=0,rounding_size=0.01", transform=fig.transFigure,
                                      facecolor="none", edgecolor="#ffffff80", linewidth=2.5, linestyle=(0, (6, 4)), zorder=9))
        text(fig, W, H, lx1 - bwid / 2, ly + 30 - bht / 2 + 18, "LOGO", F["Bold"], 54, color="#ffffffa0", ha="center", zorder=9)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("WX_DATA_BASE", "http://localhost:8779/d/"))
    ap.add_argument("--run", default=""); ap.add_argument("--out", required=True)
    ap.add_argument("--prods", default="z500anom,t2ma,t850a,mslpqpf"); ap.add_argument("--views", default="na,pnw")
    ap.add_argument("--hours", default="72,144"); ap.add_argument("--aspects", default="h,v"); ap.add_argument("--logo", default="")
    ap.add_argument("--skip-existing", action="store_true")
    a = ap.parse_args(); D = Data(a.base); F = fonts()
    runs = D.man["runs"]["ifs"]; run = a.run or next(r for r in reversed(runs) if r[-2:] in ("00", "12"))
    R = D.run(run); done = []; have = {s_["f"] for s_ in R["steps"]}
    for prod in a.prods.split(","):
        for view in a.views.split(","):
            for f in map(int, a.hours.split(",")):
                for k in a.aspects.split(","):
                    p = os.path.join(a.out, run, f"{prod}_{view}_f{f:03d}_{k}.png")
                    if f not in have: continue                      # run still coming in (or shorter 06/18Z run)
                    if a.skip_existing and os.path.exists(p): continue
                    render(D, R, run, prod, view, f, k, p, F, a.logo)
                    done.append(p); print(p, flush=True)
    return done

if __name__ == "__main__":
    main()
