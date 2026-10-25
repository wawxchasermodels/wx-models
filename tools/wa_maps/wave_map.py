#!/usr/bin/env python3
"""Significant wave height maps (ECMWF WAM open data): Washington waters and Vancouver Island (metric).
Data: ECMWF open data (CC BY 4.0), NOAA (public domain). Basemap: U.S. Census, Natural Earth (public domain), GSHHG (NOAA, LGPL). Places: GeoNames (CC BY 4.0), Census Gazetteer (public domain).
Part of wx-models (MIT). Renders a static JPEG; no branding."""
""\
\
\
\
\
\
\
\

import argparse, datetime as dt, json, math, os, sys, tempfile
from zoneinfo import ZoneInfo
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import precip_map as PM
PT, UTC = ZoneInfo("America/Los_Angeles"), dt.timezone.utc
BASE = "https://data.ecmwf.int/forecasts/%s/%02dz/ifs/0p1/wave/%s-%dh-wave-fc-sfc"
CROP = (44.0, 50.5, -129.5, -120.5)
FT = 3.28084
W, H = 1600, 1800
FRAME = (-127.25, 45.45, -121.85, 49.40)
TOP_BAND, BOT_BAND = 150, 70
TAG = "[ECMWF WAM 0.1°]"

EDGES = list(range(0, 12)) + list(range(12, 31, 2)) + [999]
_ANCH = [(0, (40, 70, 150)), (2, (40, 120, 200)), (4, (40, 175, 210)), (6, (50, 190, 140)), (8, (110, 200, 70)), (10, (200, 220, 60)),
         (12, (245, 200, 50)), (14, (245, 150, 40)), (16, (235, 95, 35)), (18, (210, 40, 40)), (20, (170, 25, 60)), (22, (200, 40, 150)),
         (24, (160, 60, 200)), (26, (120, 80, 220)), (28, (175, 150, 235)), (30, (240, 235, 255))]
def _col(v):
    for (a, ca), (b, cb) in zip(_ANCH, _ANCH[1:]):
        if v <= b: t = (v - a) / (b - a); return tuple(int(round(ca[i] + (cb[i] - ca[i]) * t)) for i in range(3))
    return _ANCH[-1][1]
COLS = [_col(e) for e in EDGES[:-1]]
LABS = [("30+" if e == 30 else str(e)) if (e % 2 == 0 and e <= 12) or e in (16, 20, 25, 30) or e == 0 else "" for e in EDGES[:-1]]
ARROW_STEP, ARROW_MIN, ARROW_MAX, ARROW_FULL, ARROW_W, ARROW_ALPHA, ARROW_HALO = 44, 10, 40, 20.0, 2.0, 0.72, 0.28

SPOTS = [("Neah Bay Buoy", 48.493, -124.727, True, True), ("Cape Elizabeth Buoy", 47.353, -124.731, True, False),
         ("Grays Harbor Bar", 46.86, -124.20, True, True), ("Columbia River Bar", 46.25, -124.15, True, True),
         ("La Push", 47.90, -124.75, True, True), ("Offshore 126W", 47.60, -126.20, True, False), ("Offshore 46.6N", 46.60, -125.90, True, False),
         ("Mid Strait", 48.24, -123.80, True, False), ("New Dungeness Buoy", 48.333, -123.167, True, False), ("Puget Sound", 47.62, -122.44, True, False),
         ("Admiralty Inlet", 48.03, -122.63, True, False), ("Smith Island", 48.32, -122.84, True, False), ("S. Strait of Georgia", 49.02, -123.38, False, False), ("Tillamook Buoy", 45.893, -125.819, False, False)]
TOWNS = [("Neah Bay", 48.368, -124.625), ("Port Angeles", 48.118, -123.430), ("Victoria", 48.428, -123.366), ("Seattle", 47.606, -122.332),
         ("Tacoma", 47.253, -122.444), ("Westport", 46.890, -124.104), ("Ocean Shores", 46.974, -124.156), ("Long Beach", 46.352, -124.054),
         ("Astoria", 46.188, -123.831), ("Nanaimo", 49.166, -123.940), ("Vancouver BC", 49.283, -123.121), ("Forks", 47.950, -124.385),
         ("Aberdeen", 46.975, -123.815), ("Portland", 45.515, -122.678), ("Bellingham", 48.750, -122.479)]

REGION = None; UNIT = "ft"; OFFBOX = (46.25, 48.40, -127.2, -124.9)
VI = dict(W=1600, H=1600, FRAME=(-126.30, 47.98, -122.80, 50.22), OFFBOX=(48.30, 50.10, -126.30, -125.30),
          SPOTS=[("Sentry Shoal Buoy", 49.910, -124.990, True, False), ("Central Strait of Georgia", 49.500, -124.550, True, False),
                 ("Halibut Bank Buoy", 49.340, -123.730, True, False), ("Off Nanaimo", 49.110, -123.770, True, False),
                 ("Haro Strait", 48.560, -123.215, True, False), ("Race Rocks", 48.300, -123.530, True, False),
                 ("Mid Strait (Juan de Fuca)", 48.330, -124.100, True, False), ("Neah Bay Buoy", 48.493, -124.727, True, True),
                 ("La Perouse Bank Buoy", 48.830, -126.000, True, True), ("Amphitrite Point", 48.900, -125.570, True, True)],
          TOWNS=[("Campbell River", 50.0244, -125.2475), ("Courtenay", 49.6866, -124.9936), ("Tofino", 49.1530, -125.9066), ("Ucluelet", 48.9420, -125.5466),
                 ("Port Alberni", 49.2339, -124.8055), ("Nanaimo", 49.1659, -123.9401), ("Vancouver", 49.2827, -123.1207), ("Richmond", 49.1666, -123.1336),
                 ("Whistler", 50.1163, -122.9574), ("Squamish", 49.7016, -123.1558), ("Victoria", 48.4284, -123.3656), ("Sooke", 48.3740, -123.7262),
                 ("Port Angeles", 48.118, -123.430), ("Neah Bay", 48.368, -124.625)])

M_EDGES = [round(0.25 * k, 2) for k in range(0, 16)] + [round(4 + 0.5 * k, 1) for k in range(0, 9)] + [999]
def _mlab(e):
    if e >= 8: return "8+"
    if e < 4 and abs(e * 2 - round(e * 2)) < 1e-9: return "%g" % e
    return "%d" % e if abs(e - round(e)) < 1e-9 else ""

def step_url(run, st): return BASE % (run.strftime("%Y%m%d"), run.hour, run.strftime("%Y%m%d%H0000"), st)

def decode(blob):
    import eccodes
    with tempfile.NamedTemporaryFile(suffix=".grib2") as t:
        t.write(blob); t.flush()
        with open(t.name, "rb") as fh:
            g = eccodes.codes_grib_new_from_file(fh)
            Ni, Nj = eccodes.codes_get(g, "Ni"), eccodes.codes_get(g, "Nj"); mv = eccodes.codes_get(g, "missingValue")
            la0 = eccodes.codes_get(g, "latitudeOfFirstGridPointInDegrees"); lo0 = eccodes.codes_get(g, "longitudeOfFirstGridPointInDegrees")
            dd = eccodes.codes_get(g, "iDirectionIncrementInDegrees"); v = eccodes.codes_get_values(g).reshape(Nj, Ni)
    lat = la0 - dd * np.arange(Nj); lon = lo0 + dd * np.arange(Ni); lon = np.where(lon >= 180, lon - 360, lon)
    v = np.where(v == mv, np.nan, v)
    oi = np.where((lat >= CROP[0]) & (lat <= CROP[1]))[0]; oj = np.where((lon >= CROP[2]) & (lon <= CROP[3]))[0]
    lat1, lon1, G = lat[oi], lon[oj], v[np.ix_(oi, oj)]
    a = np.argsort(lat1); b = np.argsort(lon1)
    return lat1[a], lon1[b], G[a][:, b]

def fetch(run, st, param):
    u = step_url(run, st)
    js = [json.loads(l) for l in PM._get(u + ".index").decode().splitlines()]
    j = [x for x in js if x.get("param") == param]
    if len(j) != 1: raise SystemExit("%s record count %d in %s" % (param, len(j), u))
    j = j[0]; return decode(PM._get(u + ".grib2", (j["_offset"], j["_offset"] + j["_length"] - 1))) + (j["_length"],)

def pick_run(ws, we, cycle=None):
    now = dt.datetime.now(UTC)
    runs = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)] if cycle else \
        [now.replace(hour=now.hour // 6 * 6, minute=0, second=0, microsecond=0) - dt.timedelta(hours=6 * k) for k in range(0, 8)]
    for run in runs:
        s0 = max(0, int(math.ceil((ws - run).total_seconds() / 3600 / 3)) * 3); s1 = int((we - run).total_seconds() // 3600 // 3 * 3)
        mx = 360 if run.hour in (0, 12) else 144
        if s0 > 144: s0 = int(math.ceil(s0 / 6.0)) * 6
        if s1 > 144: s1 = s1 // 6 * 6
        if s1 <= 0 or s1 > mx or s0 > s1: continue
        stl = [x for x in range(s0, s1 + 1, 3) if x <= 144 or x % 6 == 0]
        if PM._ok(step_url(run, s1) + ".index") and PM._ok(step_url(run, s0) + ".index"): return run, stl
    raise SystemExit("REFUSED: no ECMWF 0.1 deg wave run covers this window")

def _hr(h): return "%d %s" % (h % 12 or 12, "AM" if h % 24 < 12 else "PM")

def render(swh_ft, dirn, lat1, lon1, title, valid_l, run, out_path, no_corner=False):
    from PIL import Image, ImageDraw, ImageFilter
    from shapely.geometry import box as sbox
    import render_core as R
    from save_final import save_final
    import forecast_base as FB, region_maps as RM
    R.W, R.H = W, H
    P = R.frame(sbox(*FRAME), box_w=1.0, box_h=(H - TOP_BAND - BOT_BAND) / H, cy=(TOP_BAND + H - BOT_BAND) / 2 / H)
    im = FB.dark_base(R, P, 1.0)
    water = np.asarray(R.LAND_MASK) < 128
    y0, x0 = lat1[0], lon1[0]; dy = lat1[1] - lat1[0]; dx = lon1[1] - lon1[0]
    M = np.isfinite(swh_ft).astype(np.float32); V0 = np.where(M > 0, swh_ft, 0).astype(np.float32)
    def sample(lon, lat, F=V0, Mk=M):
        fi = (lat - y0) / dy; fj = (lon - x0) / dx
        i0 = np.clip(np.floor(fi).astype(int), 0, F.shape[0] - 2); j0 = np.clip(np.floor(fj).astype(int), 0, F.shape[1] - 2)
        ti = np.clip(fi - i0, 0, 1); tj = np.clip(fj - j0, 0, 1)
        w00, w10, w01, w11 = (1 - ti) * (1 - tj), ti * (1 - tj), (1 - ti) * tj, ti * tj
        num = F[i0, j0] * w00 * Mk[i0, j0] + F[i0 + 1, j0] * w10 * Mk[i0 + 1, j0] + F[i0, j0 + 1] * w01 * Mk[i0, j0 + 1] + F[i0 + 1, j0 + 1] * w11 * Mk[i0 + 1, j0 + 1]
        den = w00 * Mk[i0, j0] + w10 * Mk[i0 + 1, j0] + w01 * Mk[i0, j0 + 1] + w11 * Mk[i0 + 1, j0 + 1]
        return np.where(den >= 0.25, num / np.maximum(den, 1e-6), np.nan)
    S = 2; WS, HS = W * S, H * S
    xs = P.x0 + (np.arange(WS) + 0.5) / (P.k * S); ys = P.y0 + (np.arange(HS) + 0.5) / (P.k * S)
    lonr, _ = R.px2ll(xs, np.zeros_like(xs)); _, latr = R.px2ll(np.zeros_like(ys), ys)
    LON, LAT = lonr[None, :], latr[:, None]; Vp = np.broadcast_to(sample(LON, LAT), (HS, WS)); del LON, LAT
    wat = np.asarray(Image.fromarray(water.astype(np.uint8) * 255).resize((WS, HS), Image.NEAREST)) > 127
    ok = np.isfinite(Vp) & wat
    idx = np.clip(np.searchsorted(np.array(EDGES, np.float32), np.nan_to_num(Vp), side="right") - 1, 0, len(COLS) - 1).astype(np.int16)
    rgb = np.array(COLS, np.uint8)[idx]
    ii = np.where(ok, idx, -1); e = np.zeros_like(ok); e[:, 1:] |= ii[:, 1:] != ii[:, :-1]; e[1:, :] |= ii[1:, :] != ii[:-1, :]
    e &= ok & np.roll(ok, 1, 0) & np.roll(ok, 1, 1)
    rgb[e] = (rgb[e].astype(int) * 0.6).astype(np.uint8)
    ov = Image.fromarray(np.dstack([rgb, np.where(ok, 255, 0).astype(np.uint8)]), "RGBA").resize((W, H), Image.LANCZOS)
    im.alpha_composite(ov); del rgb, idx, ii, Vp
    R.draw_borders_on_top(im, P, 1.0, Image.new("L", (W, H), 120))
    INK = (14, 16, 22); WHITE = (255, 255, 255)

    d = ImageDraw.Draw(im)
    TITLE_PX, TITLE_Y, CORNER_S, CORNER_PAD = 96, 8, 180, 24
    fmt_ = R.font(R.MONT, 32, 700); mtw = d.textlength(TAG, font=fmt_)
    ft_t = R.font(R.IMPACT, TITLE_PX); tw = d.textlength(title, font=ft_t)
    while tw > W - 2 * (mtw + 60):
        TITLE_PX -= 2; ft_t = R.font(R.IMPACT, TITLE_PX); tw = d.textlength(title, font=ft_t)
    tbot = TITLE_Y + TITLE_PX * 1.15
    bx0, bx1, by0 = RM.top_scale_geom(W, int(tbot), CORNER_PAD + CORNER_S); bh = 18
    top_bot = by0 + bh + 6 + 26
    RM.top_fade(im, W, top_bot); d = ImageDraw.Draw(im)
    tx = (W - tw) / 2; d.text((tx + 7, TITLE_Y + 7), title, font=ft_t, fill=(0, 0, 0)); d.text((tx, TITLE_Y), title, font=ft_t, fill=WHITE)
    fT = R.font(R.MONT, 26, 800); d.text((bx0, by0 - 36), ("Meters" if UNIT == "m" else "Feet"), font=fT, fill=WHITE, stroke_width=4, stroke_fill=INK)
    n = len(COLS); txb = lambda t: bx0 + (bx1 - bx0) * t / n
    d.rectangle((bx0 - 2, by0 - 2, bx1 + 2, by0 + bh + 2), fill=INK)
    for i, c in enumerate(COLS): d.rectangle((round(txb(i)), by0, round(txb(i + 1)), by0 + bh), fill=c)
    ftk = R.font(R.MONT, 21, 700)
    for i, l in enumerate(LABS):
        if not l: continue
        xx = round(txb(i)); lw = d.textlength(l, font=ftk)
        d.line((xx, by0 + bh, xx, by0 + bh + 5), fill=WHITE, width=2)
        d.text((xx - lw / 2, by0 + bh + 6), l, font=ftk, fill=WHITE, stroke_width=3, stroke_fill=INK)
    d.text((W - 34, 30), TAG, font=fmt_, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="ra")
    keep = [(0, 0, W, top_bot + 6)] + ([] if no_corner else [(0, 0, CORNER_PAD + CORNER_S + 10, CORNER_PAD + CORNER_S + 10)])

    SUM1_PX, SUM2_PX, MODEL_PX = 36, 32, 26
    fdate = R.font(R.MONT, SUM2_PX, 800); fmod = R.font(R.MONT, MODEL_PX, 700); fs = R.font(R.MONT, 22, 600)
    valid_line = "Valid %s %s %d-%d" % (_hr(valid_l.hour), valid_l.strftime("%a"), valid_l.month, valid_l.day)
    rl = run.astimezone(PT); model_line = "ECMWF WAM 0.1°, %02dZ run %d-%d (%s PT)" % (run.hour, rl.month, rl.day, _hr(rl.hour)); src = "Data: ECMWF (CC BY 4.0)"
    DATE_L, DATE_B = 30, H - 30; MOD_B = DATE_B - SUM2_PX - 10; CRED_Y = MOD_B - MODEL_PX - 34
    keep += [(0, CRED_Y - 8, DATE_L + max(d.textlength(valid_line, font=fdate), d.textlength(model_line, font=fmod)) + 12, H)]
    SUM_R, SUM_B, SUM_MAXW = W - 30, H - 30, 820
    keep += [(SUM_R - SUM_MAXW - 10, SUM_B - SUM2_PX - 10 - SUM1_PX - 14, W, H)]

    hit = lambda a, b: not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])
    inside = lambda b: b[0] >= 12 and b[2] <= W - 12 and b[1] >= 12 and b[3] <= H - 12
    labels = []; vals = {}
    fn = R.font(R.MONT, 24, 700); fv = R.font(R.MONT, 34, 800); fto = R.font(R.MONT, 26, 700)
    cand = [(0, 0)] + [(dx_, dy_) for r_ in (24, 44, 64, 84) for dx_, dy_ in ((0, -r_), (0, r_), (r_, 0), (-r_, 0), (r_, -r_), (-r_, -r_), (r_, r_), (-r_, r_))]
    fmtv = (lambda v: "%.1f m" % v) if UNIT == "m" else (lambda v: "<1 ft" if v < 0.5 else "%d ft" % round(v))

    lat_c = (lat1 >= OFFBOX[0]) & (lat1 <= OFFBOX[1]); lon_c = (lon1 >= OFFBOX[2]) & (lon1 <= OFFBOX[3]); sub = swh_ft[np.ix_(lat_c, lon_c)]
    pi, pj = np.unravel_index(np.nanargmax(sub), sub.shape); pk_la, pk_lo = float(lat1[lat_c][pi]), float(lon1[lon_c][pj])
    for name, la, lo, wa, coast in [("Offshore Peak", pk_la, pk_lo, True, False)] + SPOTS:
        v = float(sample(np.array(lo), np.array(la))) if name != "Offshore Peak" else float(sub[pi, pj])
        if not np.isfinite(v): print("spot %s: no model data (land-masked at 0.1 deg)" % name, file=sys.stderr); continue
        x, y = P(lo, la)
        if not (20 < x < W - 20 and 20 < y < H - 20): continue
        t2 = fmtv(v); w_ = max(d.textlength(name, font=fn), d.textlength(t2, font=fv)); h_ = 26 + 36
        for dx_, dy_ in cand:
            bb = (x + dx_ - w_ / 2 - 6, y + dy_ - h_ / 2 - 3, x + dx_ + w_ / 2 + 6, y + dy_ + h_ / 2 + 3)
            if inside(bb) and not any(hit(bb, o) for o in keep + [l_["bb"] for l_ in labels]):
                labels.append(dict(kind="spot", name=name, t2=t2, x=x + dx_, y=y + dy_, bb=bb, px=(x, y))); vals[name] = (v, wa, coast); break
        else: print("spot %s: no room" % name, file=sys.stderr)
    for name, la, lo in TOWNS:
        x, y = P(lo, la)
        if not (20 < x < W - 20 and 20 < y < H - 20): continue
        w_ = d.textlength(name, font=fto); h_ = 30
        for dx_, dy_ in cand:
            bb = (x + dx_ - w_ / 2 - 5, y + dy_ - h_ / 2 - 2, x + dx_ + w_ / 2 + 5, y + dy_ + h_ / 2 + 2)
            if inside(bb) and not any(hit(bb, o) for o in keep + [l_["bb"] for l_ in labels]):
                labels.append(dict(kind="town", name=name, x=x + dx_, y=y + dy_, bb=bb, px=(x, y))); break

    D0 = np.where(np.isfinite(dirn), dirn, 0); Md = np.isfinite(dirn).astype(np.float32)
    S2 = 3; ov2 = Image.new("L", (W * S2, H * S2), 0); da = ImageDraw.Draw(ov2); nar = 0
    kout = keep + [l_["bb"] for l_ in labels]
    def nearest(F, Mk, lon, lat):
        i = int(round((lat - y0) / dy)); j = int(round((lon - x0) / dx))
        if not (0 <= i < F.shape[0] and 0 <= j < F.shape[1]) or not Mk[i, j]: return np.nan
        return float(F[i, j])
    for r_, gy in enumerate(range(top_bot + 20, H - 20, ARROW_STEP)):
        for gx in range(int(ARROW_STEP * (0.5 if r_ % 2 else 1.0)), W - 16, ARROW_STEP):
            if not water[gy, gx]: continue
            lon, lat = R.px2ll(np.array([P.x0 + gx / P.k]), np.array([P.y0 + gy / P.k])); lon, lat = float(lon[0]), float(lat[0])
            hgt = float(sample(np.array(lon), np.array(lat))); fr = nearest(D0, Md, lon, lat)
            if not (np.isfinite(hgt) and np.isfinite(fr)): continue
            to = math.radians((fr + 180) % 360); ue, ve = math.sin(to), math.cos(to)
            e_ = 0.02; x2, y2 = P(lon + ue * e_ / math.cos(math.radians(lat)), lat + ve * e_)
            ddx, ddy = x2 - gx, y2 - gy; dn = math.hypot(ddx, ddy); ddx, ddy = ddx / dn, ddy / dn
            ln = ARROW_MIN + (ARROW_MAX - ARROW_MIN) * min(max(hgt, 0) / ARROW_FULL, 1.0)
            hx, hy = gx + ddx * ln / 2, gy + ddy * ln / 2; tx0, ty0 = gx - ddx * ln / 2, gy - ddy * ln / 2
            bb = (min(hx, tx0) - 4, min(hy, ty0) - 4, max(hx, tx0) + 4, max(hy, ty0) + 4)
            if any(hit(bb, o) for o in kout): continue
            if not (water[int(min(max(hy, 0), H - 1)), int(min(max(hx, 0), W - 1))] and water[int(min(max(ty0, 0), H - 1)), int(min(max(tx0, 0), W - 1))]): continue
            px_, py_ = -ddy, ddx; hl = min(7.0, ln * 0.45); hw = hl * 0.55; bx_, by_ = hx - ddx * hl * 0.8, hy - ddy * hl * 0.8
            da.line((tx0 * S2, ty0 * S2, bx_ * S2, by_ * S2), fill=255, width=int(ARROW_W * S2))
            da.polygon([(hx * S2, hy * S2), ((hx - ddx * hl + px_ * hw) * S2, (hy - ddy * hl + py_ * hw) * S2), ((hx - ddx * hl - px_ * hw) * S2, (hy - ddy * hl - py_ * hw) * S2)], fill=255); nar += 1
    mk_ = ov2.resize((W, H), Image.LANCZOS)
    halo = mk_.filter(ImageFilter.MaxFilter(3)).point(lambda q: int(q * ARROW_HALO))
    im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 255)] * 3 + [halo]))
    im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [mk_.point(lambda q: int(q * ARROW_ALPHA))])); d = ImageDraw.Draw(im)

    for l_ in labels:
        if l_["kind"] == "spot":
            d.text((l_["x"], l_["y"] - 31), l_["name"], font=fn, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="mt")
            d.text((l_["x"], l_["y"] - 5), l_["t2"], font=fv, fill=WHITE, stroke_width=5, stroke_fill=INK, anchor="mt")
        else:
            d.text((l_["x"], l_["y"]), l_["name"], font=fto, fill=(225, 228, 235), stroke_width=4, stroke_fill=INK, anchor="mm")

    offmax = float(np.nanmax(sub))
    if UNIT == "m":
        rg = lambda g: ("%.1f m" % g[0]) if round(min(g), 1) == round(max(g), 1) else "%.1f to %.1f m" % (min(g), max(g))
        st_ = [v for k, (v, wa, c) in vals.items() if k in ("Sentry Shoal Buoy", "Central Strait of Georgia", "Halibut Bank Buoy", "Off Nanaimo")]
        l1 = "Open Pacific up to %.1f m" % offmax + (", Strait of Georgia %s" % rg(st_) if st_ else "")
        wv = {k: v for k, (v, wa, c) in vals.items()}; top = max(wv, key=wv.get); l2 = "Highest: %s %.1f m" % (top, wv[top])
    coast = [v for v, wa, c in vals.values() if wa and c]
    if UNIT != "m": l1 = "Offshore up to %d ft" % round(offmax) + (", coast %s" % (("%d ft" % round(min(coast))) if round(min(coast)) == round(max(coast)) else "%d to %d ft" % (round(min(coast)), round(max(coast)))) if coast else "")
    if UNIT != "m":
        wv = {k: v for k, (v, wa, c) in vals.items() if wa}; top = max(wv, key=wv.get)
        l2 = "Highest: %s %d ft" % (top, round(wv[top]))
    for txt, px, yb in ((l2, SUM2_PX, SUM_B), (l1, SUM1_PX, SUM_B - SUM2_PX - 10)):
        f_ = R.font(R.MONT, px, 800)
        while d.textlength(txt, font=f_) > SUM_MAXW and px > 20: px -= 2; f_ = R.font(R.MONT, px, 800)
        d.text((SUM_R, yb), txt, font=f_, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="rs")
    d.text((DATE_L, DATE_B), valid_line, font=fdate, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="ls")
    d.text((DATE_L, MOD_B), model_line, font=fmod, fill=WHITE, stroke_width=4, stroke_fill=INK, anchor="ls")
    R.subtle_credit(im, d, (DATE_L, CRED_Y), src, fs)
    base = im.convert("RGBA")
    out = save_final(base, out_path, quality=97)
    return dict(out=out, size=[W, H], frame=FRAME, bounds_ll=P.bounds_ll(), valid_line=valid_line, model_line=model_line, l1=l1, l2=l2,
                spots={k: round(v, 1) for k, (v, wa, c) in vals.items()}, offshore_max_ft=round(offmax * (FT if UNIT == "m" else 1), 1), offshore_max_m=round(offmax / (1 if UNIT == "m" else FT), 2), unit=UNIT, arrows=nar,
                labels=[l_["name"] for l_ in labels], offshore_peak_at=[round(pk_la, 2), round(pk_lo, 2)])

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2026-10-24 05"); ap.add_argument("--end", default="2026-10-26 05")
    ap.add_argument("--cycle"); ap.add_argument("--out", default="out/wave_ecmwf_20261024")
    ap.add_argument("--title", default=None); ap.add_argument("--no-corner", action="store_true")
    ap.add_argument("--region", choices=["vi"], help="vi: Vancouver Island / Strait of Georgia / Juan de Fuca zoom, 1600x1600, METRIC")
    ap.add_argument("--hmax", action="store_true", help="estimated max individual wave height = 1.86 x Hs (Rayleigh, ~1000 waves); ECMWF open data has no hmax field")
    a = ap.parse_args(argv)
    global EDGES, COLS, LABS, TAG, W, H, FRAME, OFFBOX, SPOTS, TOWNS, UNIT, REGION, ARROW_FULL, CROP
    if a.region == "vi":
        CROP = (46.5, 51.5, -129.5, -120.5)
        REGION = "vi"; UNIT = "m"; a.no_corner = True
        W, H, FRAME, OFFBOX, SPOTS, TOWNS = VI["W"], VI["H"], VI["FRAME"], VI["OFFBOX"], VI["SPOTS"], VI["TOWNS"]
        EDGES = M_EDGES; COLS = [_col(e * FT) for e in EDGES[:-1]]; LABS = [_mlab(e) for e in EDGES[:-1]]; ARROW_FULL = ARROW_FULL / FT
        if a.out == ap.get_default("out"): a.out = "out/wave_vi_ecmwf_20261024"
    if a.hmax:
        EDGES = list(range(0, 24, 2)) + list(range(24, 61, 4)) + [999]
        COLS = [_col(e / 2.0) for e in EDGES[:-1]]
        LABS = [("60+" if e == 60 else str(e)) if (e % 4 == 0 and e <= 24) or e in (32, 40, 48, 60) else "" for e in EDGES[:-1]]
    if a.title is None: a.title = "Estimated Max Wave Heights" if a.hmax else "Significant Wave Heights"
    ws = PM._pt(a.start).astimezone(UTC); we = PM._pt(a.end).astimezone(UTC)
    run, steps = pick_run(ws, we, a.cycle)
    os.makedirs(a.out, exist_ok=True)
    cache = os.path.join(a.out, "ecmwf_wave_swh_%s_s%03d-%03d.npz" % (run.strftime("%Y%m%d%HZ"), steps[0], steps[-1]))
    if os.path.exists(cache):
        z = np.load(cache); lat1, lon1, SW = z["lat"], z["lon"], z["swh"]; nbytes = int(z["bytes"])
    else:
        SW = []; nbytes = 0
        for st in steps:
            lat1, lon1, g, nb = fetch(run, st, "swh"); SW.append(g); nbytes += nb; print("swh step %d ok" % st)
        SW = np.array(SW, np.float32); np.savez_compressed(cache, lat=lat1, lon=lon1, swh=SW, bytes=nbytes)
    SWf = SW * (1.0 if UNIT == "m" else FT) * (1.86 if a.hmax else 1.0)
    lat_c = (lat1 >= OFFBOX[0]) & (lat1 <= OFFBOX[1]); lon_c = (lon1 >= OFFBOX[2]) & (lon1 <= OFFBOX[3])
    peaks = [float(np.nanmax(s[np.ix_(lat_c, lon_c)])) for s in SWf]
    k = int(np.argmax(peaks)); st = steps[k]; valid = run + dt.timedelta(hours=st); vl = valid.astimezone(PT)
    print("run %s steps %s; offshore max by step (%s): %s; peak step %d = %s PT" % (run.strftime("%Y%m%d%HZ"), steps, UNIT, [round(p, 1) for p in peaks], st, vl.strftime("%a %m-%d %H:00")))
    dcache = os.path.join(a.out, "ecmwf_wave_mwd_%s_s%03d.npz" % (run.strftime("%Y%m%d%HZ"), st))
    if os.path.exists(dcache): dz = np.load(dcache); MWD = dz["mwd"]
    else:
        la_, lo_, MWD, nb = fetch(run, st, "mwd"); nbytes += nb; np.savez_compressed(dcache, mwd=MWD)
    r = render(SWf[k], MWD, lat1, lon1, a.title, vl, run, os.path.join(a.out, "final.jpg"), a.no_corner)
    r.update(run=run.strftime("%Y%m%d%HZ"), steps=steps, peak_step=st, valid_pt=vl.isoformat(), offshore_box=OFFBOX, region=REGION, offshore_max_by_step=dict(zip(steps, [round(p, 1) for p in peaks])),
             source=[step_url(run, s) + ".grib2" for s in steps], resolution="0.1 deg regular lat/lon (ECMWF open data ifs/0p1/wave, IFS wave model)", license="CC BY 4.0, Source: ECMWF",
             bytes_downloaded=nbytes, params="swh (m)" + (" -> ft" if UNIT == "ft" else ", shown in m") + ", mwd (deg from) -> arrows toward")
    json.dump(r, open(os.path.join(a.out, "run.json"), "w"), indent=1, default=str)
    print(json.dumps({k_: r[k_] for k_ in ("out", "valid_line", "model_line", "l1", "l2", "offshore_max_ft", "spots", "labels", "arrows")}, default=str))

if __name__ == "__main__":
    main()
