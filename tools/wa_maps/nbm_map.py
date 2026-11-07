#!/usr/bin/env python3
"""Predicted low / high temperature maps for Washington (NOAA NBM, NOAA GFS, ECMWF ENS mean).
Data: ECMWF open data (CC BY 4.0), NOAA (public domain). Basemap: U.S. Census, Natural Earth (public domain), GSHHG (NOAA, LGPL). Places: GeoNames (CC BY 4.0), Census Gazetteer (public domain).
Part of wx-models (MIT). Renders a static JPEG; no branding."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from render_core import asset as _asset
""\
\
\
\
\
\
\
\
\
\
\
\

import argparse, datetime as dt, json, math, os, re, sys, pickle, urllib.request
from zoneinfo import ZoneInfo
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BUCKET = "https://noaa-nbm-grib2-pds.s3.amazonaws.com"
UTC = dt.timezone.utc; PT = ZoneInfo("America/Los_Angeles")

def _get(url, rng=None):
    rq = urllib.request.Request(url, headers={"Range": "bytes=%d-%s" % rng} if rng else {})
    with urllib.request.urlopen(rq, timeout=60) as r: return r.read()

def _idx(cyc, fhr):
    url = "%s/blend.%s/%02d/core/blend.t%02dz.core.f%03d.co.grib2" % (BUCKET, cyc.strftime("%Y%m%d"), cyc.hour, cyc.hour, fhr)
    try: return url, _get(url + ".idx").decode().splitlines()
    except Exception: return url, None

def _find(lines, pat):
    rx = re.compile(pat)
    for i, l in enumerate(lines):
        if rx.search(l):
            start = int(l.split(":")[1]); end = int(lines[i + 1].split(":")[1]) - 1 if i + 1 < len(lines) else ""
            return start, end, l
    return None

def crop(grib_bytes):
    import eccodes, tempfile
    with tempfile.NamedTemporaryFile(suffix=".grib2") as tf_:
        tf_.write(grib_bytes); tf_.flush()
        with open(tf_.name, "rb") as fh: g = eccodes.codes_grib_new_from_file(fh)
    info = {k: eccodes.codes_get(g, k) for k in ["shortName", "name", "dataDate", "dataTime", "stepRange", "validityDate", "validityTime", "Ni", "Nj", "gridType"]}
    alt = eccodes.codes_get(g, "alternativeRowScanning")
    v = eccodes.codes_get_values(g); lats = eccodes.codes_get_array(g, "latitudes"); lons = eccodes.codes_get_array(g, "longitudes")

    Ni, Nj = info["Ni"], info["Nj"]; v = v.reshape(Nj, Ni).copy()
    if alt: v[1::2] = v[1::2, ::-1]
    lats = lats.reshape(Nj, Ni); lons = lons.reshape(Nj, Ni); lons = np.where(lons > 180, lons - 360, lons)
    m = (lats > 43.5) & (lats < 51.2) & (lons > -127.5) & (lons < -114.5); ii, jj = np.where(m)
    s = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1))
    return (v[s] - 273.15) * 9 / 5 + 32, lats[s], lons[s], info

MODEL_TAG_OVR = SRC_OVR = None
LOW_H0, LOW_H1 = 4, 8
LOW_SNAPSHOT = bool(os.environ.get("LOW_SNAPSHOT"))

def fetch(kind, date, hour=14, cycle=None, log=print):
    if kind == "high": vt = dt.datetime(date.year, date.month, date.day, tzinfo=UTC) + dt.timedelta(days=1)
    else: vt = dt.datetime(date.year, date.month, date.day, hour, tzinfo=UTC)
    if kind == "low" and not LOW_SNAPSHOT: vt = dt.datetime(date.year, date.month, date.day, LOW_H1, tzinfo=PT).astimezone(UTC)
    now = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    cycles = [dt.datetime.strptime(cycle, "%Y%m%d%H").replace(tzinfo=UTC)] if cycle else [now - dt.timedelta(hours=h) for h in range(0, 31)]
    for cyc in cycles:
        fhr = int((vt - cyc).total_seconds() // 3600)
        if fhr < 1: continue
        url, lines = _idx(cyc, fhr)
        if not lines: continue
        if kind == "high":
            hit = _find(lines, r":TMAX:2 m above ground:%d-%d hour max fcst:$" % (fhr - 12, fhr))
            if hit:
                tf, la, lo, info = crop(_get(url, hit[:2]))
                return tf, la, lo, dict(cycle=cyc.strftime("%Y%m%d%HZ"), fhr=fhr, record=hit[2], file=url, method="TMAX 12 h max", grib=info)

            stack, recs = [], []
            for f in range(fhr - 6, fhr + 1):
                u2, l2 = _idx(cyc, f)
                h2 = l2 and _find(l2, r":TMP:2 m above ground:%d hour fcst:$" % f)
                if h2: tf, la, lo, info = crop(_get(u2, h2[:2])); stack.append(tf); recs.append(h2[2])
            if stack:
                log("WARNING: no TMAX record in %s f%03d; FALLBACK max of hourly TMP 2 m 18Z-00Z (%d records)" % (cyc, fhr, len(stack)))
                return np.max(stack, 0), la, lo, dict(cycle=cyc.strftime("%Y%m%d%HZ"), fhr=fhr, record=recs, method="FALLBACK max hourly TMP 18Z-00Z", grib=info)
        elif LOW_SNAPSHOT:
            hit = _find(lines, r":TMP:2 m above ground:%d hour fcst:$" % fhr)
            if hit:
                tf, la, lo, info = crop(_get(url, hit[:2]))
                return tf, la, lo, dict(cycle=cyc.strftime("%Y%m%d%HZ"), fhr=fhr, record=hit[2], file=url, method="hourly TMP", grib=info)
        else:
            vts = [dt.datetime(date.year, date.month, date.day, h, tzinfo=PT).astimezone(UTC) for h in range(LOW_H0, LOW_H1 + 1)]
            fh = [int((v - cyc).total_seconds() // 3600) for v in vts]
            if min(fh) < 1: continue
            got = []
            for f in fh:
                u2, l2 = (url, lines) if f == fhr else _idx(cyc, f)
                h2 = l2 and _find(l2, r":TMP:2 m above ground:%d hour fcst:$" % f)
                if not h2: got = None; break
                got.append((u2, h2))
            if not got: continue
            stack = []
            for u2, h2 in got:
                tf, la, lo, info = crop(_get(u2, h2[:2])); stack.append(tf)
            stack = np.array(stack)
            return stack.min(0), la, lo, dict(cycle=cyc.strftime("%Y%m%d%HZ"), fhr=fh, valid_utc=[v.strftime("%Y-%m-%d %HZ") for v in vts],
                                              record=[h2[2] for _, h2 in got], file=[u2 for u2, _ in got], method="min of hourly TMP 2 m, %d AM to %d AM PT (%d records)" % (LOW_H0, LOW_H1, len(got)),
                                              grib=info, hourly=stack)
    raise SystemExit("No NBM cycle in the last 30 h has the %s record for %s" % (kind, vt))

W, H = 2400, 1600
PASSES = {"Snoqualmie Pass": (-121.4136, 47.4245), "Stevens Pass": (-121.0854, 47.7465), "White Pass": (-121.3911, 46.6383),
          "Chinook Pass": (-121.5156, 46.8714), "Blewett Pass": (-120.5786, 47.3348), "Sherman Pass": (-118.4636, 48.6055)}   # Washington Pass and Loup Loup Pass removed 10-25-26 (Benjamin)
CORE = ["Bellingham", "Seattle", "Spokane", "Vancouver", "Tacoma", "Olympia", "Everett", "Mount Vernon", "Oak Harbor",
        "Wenatchee", "Yakima", "Kennewick", "Walla Walla", "Ellensburg"]
BACK = ["Cle Elum", "Leavenworth", "Port Townsend", "Winthrop", "Toppenish", "Oroville", "Republic", "Quincy", "Stevenson",
        "Pullman", "Moses Lake", "Omak", "Colville", "Aberdeen",
        "Port Angeles", "Longview",
        "White Salmon", "Goldendale", "Forks", "Ocean Shores", "Long Beach", "Centralia", "Shelton", "Chelan", "Newport", "Cheney", "Davenport", "Ritzville", "Odessa",
        "Ephrata", "Othello", "Sunnyside", "Prosser", "Dayton", "Clarkston", "Colfax", "Grand Coulee", "Raymond", "Packwood"]

EXTRA = ["Richland", "Pasco", "Anacortes", "Sequim", "Lynden", "Arlington", "Monroe", "North Bend", "Enumclaw", "Puyallup", "Bremerton", "Poulsbo",
         "Hoquiam", "Westport", "Neah Bay", "Chehalis", "Morton", "Ashford", "Eatonville", "Montesano", "Elma", "Ilwaco", "Cathlamet", "Castle Rock",
         "Woodland", "Battle Ground", "Camas", "Carson", "Trout Lake", "Bingen", "Glenwood", "Roosevelt", "Bickleton", "Twisp", "Tonasket", "Brewster",
         "Pateros", "Okanogan", "Coulee City", "Wilbur", "Waterville", "Entiat", "Cashmere", "Roslyn", "Kittitas", "Naches", "Selah", "Wapato",
         "Grandview", "Granger", "Benton City", "Mattawa", "Royal City", "Warden", "Soap Lake", "George", "Connell", "Mesa", "Kahlotus", "Washtucna",
         "Lind", "Sprague", "Harrington", "Almira", "Creston", "Reardan", "Medical Lake", "Deer Park", "Chewelah", "Kettle Falls", "Northport", "Ione",
         "Metaline Falls", "Curlew", "Inchelium", "Keller", "Nespelem", "Loomis", "Waitsburg", "Pomeroy", "Asotin", "Tekoa", "Rosalia", "St. John",
         "Oakesdale", "Palouse", "Endicott", "Concrete", "Darrington", "Sedro-Woolley", "Coupeville", "Friday Harbor", "Skykomish", "Gold Bar",
         "Langley", "Kingston", "Port Orchard", "Spokane Valley"]

WEST_KEEP = ["Lynden", "Friday Harbor", "Neah Bay", "Poulsbo", "Bremerton", "Enumclaw", "Morton", "Castle Rock", "Cathlamet", "Darrington", "Battle Ground"]
WEST = ["Marysville", "Arlington", "Lake Stevens", "Snohomish", "Monroe", "Sultan", "Gold Bar", "Granite Falls", "Duvall", "Woodinville", "Redmond",
        "Bellevue", "Issaquah", "North Bend", "Snoqualmie", "Renton", "Kent", "Auburn", "Maple Valley", "Black Diamond", "Buckley", "Bonney Lake",
        "Puyallup", "Orting", "Eatonville", "Yelm", "Sedro-Woolley", "Concrete", "Lynnwood", "Gig Harbor",
        "Burlington", "Stanwood", "Ferndale", "Blaine", "Sumas", "Anacortes", "Coupeville", "Langley", "Silverdale", "Port Orchard", "Kingston",
        "Belfair", "Quilcene", "Brinnon", "Hoodsport", "Sequim", "Clallam Bay", "Amanda Park", "Hoquiam", "Westport", "Elma", "McCleary", "Tenino",
        "Rochester", "Chehalis", "Winlock", "Toledo", "Pe Ell", "Kelso", "Kalama", "Woodland", "Ridgefield", "Camas", "Washougal", "Ilwaco",
        "South Bend", "Naselle", "Ocean Park", "Mossyrock", "Ashford", "Carnation", "Fall City", "Federal Way", "Lakewood", "DuPont", "Edmonds",
        "Mukilteo", "Bainbridge Island"]
EXTRA = [t for t in EXTRA if t not in WEST and t not in WEST_KEEP]
OPTIONAL = set(WEST_KEEP) | set(WEST) | set(EXTRA)
TOWNS = CORE + list(PASSES) + BACK + WEST_KEEP + WEST + EXTRA

import town_pop as TP
OPTIONAL = {t for t in OPTIONAL if TP.tier(t)[0] >= 3}

TOWNS += [t for t in TP.always_list() if t not in TOWNS]
TOWNS += [t for t in sorted(TP.SOFT, key=lambda t: -TP.pop(t)) if t not in TOWNS]; OPTIONAL |= TP.SOFT
_BIG = sorted([t for t in TOWNS if TP.always(t, t in PASSES)], key=lambda t: -TP.pop(t))
ORDER = _BIG + list(PASSES) + ["Oak Harbor"] + \
        sorted([t for t in TOWNS if t not in OPTIONAL and t not in PASSES and t not in _BIG and t != "Oak Harbor"], key=lambda t: -TP.pop(t)) + \
        sorted([t for t in TOWNS if t in OPTIONAL], key=lambda t: -TP.pop(t))

WEST = [t for t in WEST if t not in TP.DROP]; WEST_KEEP = [t for t in WEST_KEEP if t not in TP.DROP]
TOWNS = [t for t in TOWNS if t not in TP.DROP]; TOWNS += [t for t in TP.REQUESTED if t not in TOWNS]
OPTIONAL = {t for t in OPTIONAL if t not in TP.REQUESTED and t not in TP.DROP}
_HEAD = sorted([t for t in TOWNS if (t in TP.MUST or t in TP.LOCKED) and t != "Oak Harbor"], key=lambda t: -TP.pop(t))
_REQ = sorted(TP.REQUESTED, key=lambda t: -TP.pop(t))
ORDER = _HEAD + list(PASSES) + ["Oak Harbor"] + _REQ + [t for t in ORDER if t not in _HEAD and t not in PASSES and t != "Oak Harbor" and t not in _REQ and t not in TP.DROP]

DBG = {}
FLIP = set()
NO_CORNER = False
SOURCE = "nbm"
def render(TF, LA, LO, kind, title, subtitle, out_path):
    from PIL import Image, ImageDraw, ImageFilter
    import render_core as R
    from save_final import save_final
    from shapely.geometry import box as sbox
    from shapely import contains_xy
    import pyproj
    R.W, R.H = W, H
    lcc = pyproj.Proj(proj="lcc", lat_1=25, lat_2=25, lat_0=25, lon_0=265, R=6371200)
    gx, gy = lcc(LO, LA); x0, y0 = gx[0, 0], gy[0, 0]; dx = (gx[0, -1] - x0) / (gx.shape[1] - 1); dy = (gy[-1, 0] - y0) / (gy.shape[0] - 1)
    def sample(lon, lat):
        x, y = lcc(lon, lat); fi = (y - y0) / dy; fj = (x - x0) / dx
        i0 = np.clip(np.floor(fi).astype(int), 0, TF.shape[0] - 2); j0 = np.clip(np.floor(fj).astype(int), 0, TF.shape[1] - 2)
        ti = np.clip(fi - i0, 0, 1); tj = np.clip(fj - j0, 0, 1)
        return (TF[i0, j0] * (1 - ti) * (1 - tj) + TF[i0 + 1, j0] * ti * (1 - tj) + TF[i0, j0 + 1] * (1 - ti) * tj + TF[i0 + 1, j0 + 1] * ti * tj)
    P = R.frame(sbox(*FRAME_BOX), box_w=FRAME_W, box_h=FRAME_BH, cy=FRAME_CY)
    lo0, la0, lo1, la1 = P.bounds_ll()
    import forecast_base as FB
    im = FB.dark_base(R, P, 1.0)
    wa = [g for p_, g in pickle.load(open(R.BM + "/cb_2023_us_state_500k.pkl", "rb")) if p_.get("STUSPS") == "WA"][0]

    EDGES = list(range(0, 32, 4)) + list(range(32, 70, 2)) + list(range(70, 111, 5)); LOB, HIB = 0, 110
    ANCH = [(0, (95, 20, 125)), (8, (135, 60, 195)), (16, (85, 75, 220)), (24, (40, 95, 215)), (31.9, (30, 115, 220)),
            (32, (220, 245, 255)), (34, (150, 225, 250)), (36, (90, 205, 225)), (39, (55, 185, 170)), (42, (40, 165, 100)),
            (46, (90, 190, 60)), (50, (150, 210, 60)), (54, (200, 225, 70)), (58, (235, 235, 85)), (63, (250, 222, 75)),
            (67.9, (250, 205, 65)), (68, (250, 160, 50)), (72, (245, 130, 45)), (78, (235, 95, 40)), (85, (215, 45, 35)),
            (95, (170, 15, 30)), (110, (110, 0, 20))]
    def pal(t):
        for (a, ca), (b, cb) in zip(ANCH, ANCH[1:]):
            if t <= b: f = (t - a) / (b - a); return tuple(int(round(ca[k] + (cb[k] - ca[k]) * f)) for k in range(3))
        return ANCH[-1][1]
    COLS = [pal((e0 + e1) / 2) for e0, e1 in zip(EDGES, EDGES[1:])]
    I32 = EDGES.index(32)
    COLS = [tuple(min(255, int(c * (1.0 if (i - I32) % 2 == 0 else 0.9))) for c in col) for i, col in enumerate(COLS)]
    S = 3; WS, HS = W * S, H * S
    xs = P.x0 + (np.arange(WS) + 0.5) / (P.k * S); ys = P.y0 + (np.arange(HS) + 0.5) / (P.k * S)
    lonr, _ = R.px2ll(xs, np.zeros_like(xs)); _, latr = R.px2ll(np.zeros_like(ys), ys)
    V = np.empty((HS, WS), np.float32); VALID = np.zeros((HS, WS), bool) if FILL_NEIGHBORS else None
    for r0 in range(0, HS, 600):
        LON, LAT = np.meshgrid(lonr, latr[r0:r0 + 600]); V[r0:r0 + 600] = sample(LON, LAT)
        if FILL_NEIGHBORS:
            gx_, gy_ = lcc(LON, LAT); fi_ = (gy_ - y0) / dy; fj_ = (gx_ - x0) / dx
            VALID[r0:r0 + 600] = (fi_ >= 0) & (fi_ <= TF.shape[0] - 1) & (fj_ >= 0) & (fj_ <= TF.shape[1] - 1) & np.isfinite(V[r0:r0 + 600])
    del LON, LAT
    idx = np.clip(np.searchsorted(np.array(EDGES, np.float32), np.floor(V + 0.5), side='right') - 1, 0, len(COLS) - 1).astype(np.int16)
    rgb = np.array(COLS, np.uint8)[idx]
    wm = Image.new("L", (WS, HS), 0); dw = ImageDraw.Draw(wm)
    for pg in R.polys(wa): dw.polygon([(x * S, y * S) for x, y in P.ring(pg.exterior.coords)], fill=255)
    wam = np.asarray(wm) > 127
    fm = wam
    if FILL_NEIGHBORS:
        import region_maps as RM; fm = RM.fill_mask(R, Image, WS, HS, wam, VALID); del VALID
    alpha = np.where(fm, 255, 0).astype(np.uint8)
    e = (idx[:, 1:] != idx[:, :-1]); ev = (idx[1:, :] != idx[:-1, :])
    edge = np.zeros_like(idx, bool); edge[:, 1:] |= e; edge[1:, :] |= ev
    c32 = (V >= 31.5)
    f32 = np.zeros_like(edge); f32[:, 1:] |= c32[:, 1:] != c32[:, :-1]; f32[1:, :] |= c32[1:, :] != c32[:-1, :]
    from scipy.ndimage import binary_dilation
    f32 = binary_dilation(f32, iterations=2) & fm; edge = binary_dilation(edge, iterations=1) & fm & ~f32
    rgba = np.dstack([rgb, alpha])
    rgba[edge] = (rgba[edge].astype(int) * [0.55, 0.55, 0.55, 1]).astype(np.uint8)
    rgba[f32] = (255, 255, 255, 235)
    ov = Image.fromarray(rgba, "RGBA").resize((W, H), Image.LANCZOS)
    _a = ov.getchannel("A"); ov = ov.convert("RGB").filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=2)).convert("RGBA"); ov.putalpha(_a)
    im.alpha_composite(ov); del rgba, V, idx
    if NEIGHBOR_DIM:
        dim = Image.fromarray(np.where(np.asarray(wm.resize((W, H), Image.BILINEAR)) > 127, 0, NEIGHBOR_DIM).astype(np.uint8))
        im.alpha_composite(Image.merge("RGBA", [Image.new("L", (W, H), 0)] * 3 + [dim]))
    R.draw_borders_on_top(im, P, 1.0, Image.new("L", (W, H), 120))

    t1, b0 = TOP_FADE, H - BOT_FADE; al = np.zeros(H, np.uint8)
    for y in range(H):
        if y < t1: al[y] = int(170 * 0.5 * (1 + math.cos(math.pi * y / t1)))
        elif y >= b0: al[y] = int(150 * 0.5 * (1 - math.cos(math.pi * (y - b0) / (H - b0))))
    fade = Image.new("RGBA", (W, H), (0, 0, 0, 0)); fade.putalpha(Image.fromarray(np.repeat(al[:, None], W, 1), "L")); im.alpha_composite(fade)
    d = ImageDraw.Draw(im)
    BAR_Y = None
    if TOP_BAR:
        import region_maps as RM; BAR_Y = int(round(RM.bar_bottom(P, lo0, lo1))) - 2
        if not VSCALE: d.rectangle((0, 0, W, BAR_Y), fill=(0, 0, 0))
    pts = dict(PASSES)
    for l in open(_asset("2023_Gaz_place_national.txt"), encoding="latin-1"):
        c = l.rstrip("\n").split("\t")
        if c[0] != "WA": continue
        for suf in (" city", " town", " CDP"):
            nm = c[3][:-len(suf)]
            if c[3].endswith(suf) and nm in TOWNS and not (suf == " CDP" and nm in pts): pts[nm] = (float(c[11]), float(c[10]))
    if REGION:
        pts.update({k: v for k, v in TP.REGION_POINTS.items() if k in TOWNS and k not in pts})
        bx_ = TP.REGION_LABEL[REGION]
        pts = {k: v for k, v in pts.items() if bx_[0] <= v[0] <= bx_[2] and bx_[1] <= v[1] <= bx_[3] and (SHOW_PASSES or k not in PASSES)}
    if PTS_FILTER is not None: pts = {k: v for k, v in pts.items() if PTS_FILTER(k)}

    REAL = {k: (v if k in PASSES else TP.real_point(k, v)) for k, v in pts.items()}
    WHITE, ICE, HOT, INK = (255, 255, 255), (150, 220, 255), (255, 72, 60), (14, 16, 22)
    def val_color(t):
        return ICE if t <= 32 else HOT if t > 85 else WHITE

    im_rgb_title = []
    def centered(path, txt, size, y, fill, wg=None, off=6, maxw=W - 600, draw=True):
        while size > 10:
            fo = R.font(path, size, wg)
            if d.textlength(txt, font=fo) <= maxw: break
            size -= 2
        tw = d.textlength(txt, font=fo); x = (W - tw) / 2
        if draw: d.text((x + off, y + off), txt, font=fo, fill=(0, 0, 0)); d.text((x, y), txt, font=fo, fill=fill)
        return size, (x, y, x + tw, y + size * 1.15)
    TCOL = (255, 255, 255)
    def _hdr(draw):
        sz, tb = centered(R.IMPACT, title, TITLE_PX, 14, TCOL, off=8, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}), draw=draw)
        if REGION_SUB:
            _, tb2 = centered(R.MONT, REGION_SUB, SUB_PX, int(tb[3]) + 2, TCOL, wg=800, off=4, draw=draw); tb = (min(tb[0], tb2[0]), tb[1], max(tb[2], tb2[2]), tb2[3])
        return sz, tb
    BAR_D = None; tt_ = None
    if VSCALE:
        _, tb = _hdr(False)
        _, tt_ = centered(R.IMPACT, title, TITLE_PX, 14, TCOL, off=8, draw=False, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}))
        import region_maps as RM
        TS = RM.top_scale_geom(W, int(tt_[3]), (CORNER_PAD or int(W * 0.015)) + (CORNER_S or int(W * 0.075)))
        BAR_D = TS[2] + SCALE_BH + 6 + 26
        RM.top_fade(im, W, BAR_D); d = ImageDraw.Draw(im)
        sz, tt_ = centered(R.IMPACT, title, TITLE_PX, 14, TCOL, off=8, **({"maxw": TITLE_MAXW} if TITLE_MAXW else {}))
    else: sz, tb = _hdr(True)

    _lp, _ls = (CORNER_PAD or int(W * 0.015)), (CORNER_S or int(W * 0.075))
    if globals().get("WEST_TIGHT") and VSCALE: tb = tt_
    placed = [tb, (0, 0, _lp + _ls + 10, _lp + _ls + 10)]
    MODEL_TAG = MODEL_TAG_OVR or "[NBM 2.5 km]"

    fmt_ = R.font(R.MONT, 32, 700); mtw_ = d.textlength(MODEL_TAG, font=fmt_)
    d.text((W - 34, 30), MODEL_TAG, font=fmt_, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK, anchor="ra")
    placed.append((W - 34 - mtw_ - 12, 18, W, 30 + 32 + 16))
    KO_TB = tb; KO_BAR = (0, 0, W, BAR_Y + 4) if BAR_Y else None
    if BAR_Y: placed.append(KO_BAR)
    bx0, bx1, by0, bh = SCALE_X0, SCALE_X1, SCALE_Y, SCALE_BH
    if VSCALE: bx0, bx1, by0 = TS
    _dl = d
    tx_ = lambda t: bx0 + (bx1 - bx0) * (t - LOB) / (HIB - LOB)
    fT = R.font(R.MONT, 26, 800); lt = "Temp °F"; ltw = d.textlength(lt, font=fT)
    _dl.text(((bx0, by0 - 36) if VSCALE else (bx0 - 18 - ltw, by0 + bh / 2 - 16)), lt, font=fT, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK)
    _dl.rectangle((bx0 - 2, by0 - 2, bx1 + 2, by0 + bh + 2), fill=INK)
    for (e0, e1), c in zip(zip(EDGES, EDGES[1:]), COLS): _dl.rectangle((round(tx_(e0)), by0, round(tx_(e1)), by0 + bh), fill=c)
    ft = R.font(R.MONT, 21, 700)
    for t in range(0, 111, 5):
        xx = round(tx_(t)); _dl.line((xx, by0 + bh, xx, by0 + bh + 5), fill=(255, 255, 255), width=2)
        lab = str(t); lw = d.textlength(lab, font=ft)
        _dl.text((xx - lw / 2, by0 + bh + 6), lab, font=ft, fill=(255, 255, 255), stroke_width=3, stroke_fill=INK)
    x32 = round(tx_(32)); f32f = R.font(R.MONT, 23, 800); lw = d.textlength("32", font=f32f)
    _dl.line((x32, by0 - 6, x32, by0 + bh), fill=(255, 255, 255), width=3)
    _dl.text((x32 - lw / 2, by0 - 31), "32", font=f32f, fill=(255, 255, 255), stroke_width=3, stroke_fill=INK)
    KO_LEG = (SCALE_X0 - 24 - ltw, SCALE_Y - 34, SCALE_X1 + 20, SCALE_Y + bh + 34); placed.append(KO_LEG)
    if globals().get("WEST_TIGHT") and VSCALE: placed[-1] = KO_LEG = (bx0 - 10, by0 - 40, bx1 + 10, BAR_D)

    inwa = contains_xy(wa, LO, LA)
    if REGION: inwa &= (LO >= lo0) & (LO <= lo1) & (LA >= la0) & (LA <= la1)
    tw_ = TF[inwa]

    SUM_R, SUM_B = W - 30, H - 30
    sum_box = (SUM_R - SUM_MAXW - 10, SUM_B - SUM2_PX - SUM_GAP - SUM1_PX - 14, W, H)
    placed.append(sum_box)

    DATE_L, DATE_B = 30, H - 30; fdate = R.font(R.MONT, SUM2_PX, 800); fs = R.font(R.MONT, 22, 600); src = SRC_OVR or "Data: NOAA National Blend of Models"
    date_w = d.textlength(subtitle, font=fdate); CRED_Y = DATE_B - SUM2_PX - 34
    placed.append((0, CRED_Y - 8, DATE_L + max(date_w, d.textlength(src, font=fs)) + 12, H))

    fl = R.font(R.MONT, NAME_PX, 700); fv = R.font(R.MONT, VAL_PX, 800)
    NA = fl.getbbox("Ag")[3]; VH = fv.getbbox("0")[3]; GAP = -2
    th0 = NA + GAP + VH + 2
    marks = {}
    for name in TOWNS:
        if name in pts and name not in OPTIONAL:
            x, y = P(*pts[name]); marks[name] = (x - 1, y - 1, x + 1, y + 1)
    base_placed = list(placed)
    def place(excl):
        rx = {marks[n] for n in excl if n in marks and n not in OPTIONAL}
        placed = [p for p in base_placed if p not in rx]
        vals = {}; skipped = []; lay = {}
        def hits_of(bb, me):
            return [p for p in placed if p != me and not (bb[2] < p[0] or bb[0] > p[2] or bb[3] < p[1] or bb[1] > p[3])]

        prer = {}
        for name in [n for n in WEST_KEEP if n in ('Poulsbo', 'Bremerton', 'Enumclaw')] + WEST[:N_CORRIDOR]:
            if True: continue
            if name in excl: continue
            if name not in pts: continue
            x, y = P(*pts[name]); mk = (x - 1, y - 1, x + 1, y + 1)
            if not hits_of((mk[0] - 12, mk[1] - 12, mk[2] + 12, mk[3] + 12), None): prer[name] = mk; placed.append(mk)
        dropped = set()
        if REGION:
            _NM = [n_ for n_ in TOWNS if n_ in pts]
            _xy = np.array([P(*pts[n_]) for n_ in _NM] or [(-999, -999)], float); _PX, _PY = _xy[:, 0], _xy[:, 1]
        def free(bb, me): return not hits_of(bb, me)
        def inside(bb): return bb[0] >= 16 and bb[2] <= W - 16 and bb[1] >= 16 and bb[3] <= H - 12

        FT = {}
        for t_, npx, vpx, swt, rrt in [(i + 1,) + tuple(x[1:]) for i, x in enumerate(TIERS_OVR or TP.TIERS)]:
            f1_ = R.font(R.MONT, npx, 700); f2_ = R.font(R.MONT, vpx, 800); na_ = f1_.getbbox("Ag")[3]
            FT[t_] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, swt, rrt)
        f1_ = R.font(R.MONT, 20, 700); f2_ = R.font(R.MONT, 23, 800); na_ = f1_.getbbox("Ag")[3]
        FT[5] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 3, 6)
        f1_ = R.font(R.MONT, TIERS_OVR[1][1] - 1 if TIERS_OVR else 31, 700); f2_ = R.font(R.MONT, TIERS_OVR[1][2] if TIERS_OVR else 35, 800); na_ = f1_.getbbox("Ag")[3]
        FT[6] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 4, 9)
        f1_ = R.font(R.MONT, TP.TINY_PX[0], 700); f2_ = R.font(R.MONT, TP.TINY_PX[1], 800); na_ = f1_.getbbox("Ag")[3]
        FT[7] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 3, 5)
        def boxes(c):
            out_ = []
            for tx, ty in c["cands"]:
                bb = (tx - BXP, ty - 1, tx + c["tw"] + BXP, ty + c["th"] + 1)
                if inside(bb): out_.append((tx, ty, bb))
            if REGION and out_:
                pr_ = RPAD_PX; me_ = (c["x"], c["y"])
                def cov(bb):
                    m_ = (_PX >= bb[0] - pr_) & (_PX <= bb[2] + pr_) & (_PY >= bb[1] - pr_) & (_PY <= bb[3] + pr_)
                    return int(m_.sum()) - int(bb[0] - pr_ <= me_[0] <= bb[2] + pr_ and bb[1] - pr_ <= me_[1] <= bb[3] + pr_)
                pin_ = out_[:1] if (c.get("name") in TP.PREF and out_[0][:2] == tuple(c["cands"][0])) else []
                out_ = pin_ + sorted(out_[len(pin_):], key=lambda q: cov(q[2]))
            for q in out_: yield q
        for name in ORDER:
            if name not in pts: skipped.append(name + " (no point)"); continue
            if name in excl and name not in OPTIONAL: skipped.append(name + " (no room)"); continue
            lo, la = pts[name]; x, y = P(lo, la)
            vlo, vla = pts[name] if name in PASSES else TP.value_point(name, pts[name])

            val = float(VALUE_OVR[name]) if VALUE_OVR is not None and name in VALUE_OVR else float(sample(np.array(vlo), np.array(vla)))
            if name in PASSES and not (VALUE_OVR is not None and name in VALUE_OVR):   # pass height correction (pass_terrain.py)
                import pass_terrain as PTC; val = PTC.corrected(SOURCE, name, val, vlo, vla)
            if not (30 < x < W - 30 and 30 < y < H - 30): skipped.append(name + " (off map)"); continue
            mk = (x - 1, y - 1, x + 1, y + 1)
            tr = TP.tier(name, name in PASSES)[0]
            if name in TP.TINY: tr = 7
            if tr == 2 and CORR_SHRINK: tr = 6
            f1, f2, na, th, swt, rrt = FT[tr]
            small = name in WEST and not REGION
            if name in dropped: skipped.append(name + " (made room)"); continue
            if name in prer: pass
            elif name in OPTIONAL:
                pad = 12 if small else (RPAD_PX if REGION else 22)
                if not free((mk[0] - pad, mk[1] - pad, mk[2] + pad, mk[3] + pad), None):
                    if os.environ.get("TDBG") and name in os.environ["TDBG"].split(","): print("PADBLOCK", name, [k for k, v in lay.items() if v["bb"] in hits_of((mk[0] - pad, mk[1] - pad, mk[2] + pad, mk[3] + pad), None)], file=sys.stderr)
                    skipped.append(name); continue
                placed.append(mk); marks[name] = mk
            t2_ = "%d" % round(val); wn = d.textlength(name, font=f1); wv = d.textlength(t2_, font=f2); tw = max(wn, wv)

            g = rrt + 4
            cands = [(x - tw / 2, y - g - th), (x - tw / 2, y + g)]
            if name in FLIP: cands = cands[::-1]
            if name in TP.LOCKED: cands = [(x - tw / 2, y - g - th) if TP.LOCKED[name] == "above" else (x - tw / 2, y + g)]
            cands = [(x - tw / 2 + dx_, y - th / 2 + dy_) for dx_, dy_ in TP.nudges(name)]
            if name in TP.LEADER: cands = [(x + TP.LEADER[name][0] + a_ - tw / 2, y + TP.LEADER[name][1] + b_ - th / 2) for a_, b_ in ((0, 0), (0, -8), (0, 8), (10, 0), (10, -8), (10, 8), (20, 0), (-10, 0))]
            if name in TP.MUST_WIDE: cands += sorted([(x - tw / 2 + dx_, y - th / 2 + dy_) for dx_ in range(-140, 141, 8) for dy_ in range(-140, 141, 8)], key=lambda q: math.hypot(q[0] + tw / 2 - x, q[1] + th / 2 - y))
            if name in getattr(TP, "SMALL", ()): cands = sorted([(x - tw / 2 + dx_, y - th / 2 + dy_) for dx_ in range(-20, 161, 4) for dy_ in range(-30, 41, 3)], key=lambda q: math.hypot(q[0] + tw / 2 - x - 65, q[1] + th / 2 - y - 10))
            c = dict(x=x, y=y, tw=tw, th=th, t2=t2_, val=val, cands=cands, mk=mk, small=small, f1=f1, f2=f2, na=na, tier=tr, sw=swt, rr=rrt, name=name)
            if name in TP.LEADER: c["lead"] = True
            def near_other(bb):
                oth = [v for k, v in marks.items() if k != name and k not in OPTIONAL] + [v["mk"] for k, v in lay.items()]
                return any(bb[0] - 14 < (m[0] + m[2]) / 2 < bb[2] + 14 and bb[1] - 14 < (m[1] + m[3]) / 2 < bb[3] + 14 for m in oth)
            def rdist(bb, m):
                cx_, cy_ = (m[0] + m[2]) / 2, (m[1] + m[3]) / 2
                return math.hypot(max(bb[0] - cx_, 0, cx_ - bb[2]), max(bb[1] - cy_, 0, cy_ - bb[3]))
            def ambiguous(bb): return False
            def _ambiguous_old(bb):
                own = rdist(bb, mk)
                oth = [v for k, v in marks.items() if k != name] + [v for k, v in prer.items() if k != name] + [v["mk"] for k, v in lay.items()]
                return any(rdist(bb, m) < own + 4 for m in oth if m != mk)
            _swap = []
            if name in getattr(TP, "SMALL", ()):
                for k_, v_ in lay.items():
                    bx0, by0, bx1, by1 = v_["bb"]; ny_ = v_["ty"] + v_["na"] + 4
                    wv_ = d.textlength(v_["t2"], font=v_["f2"]); cx_ = (bx0 + bx1) / 2
                    if v_["bb"] in placed and ny_ < by1:
                        placed.remove(v_["bb"]); t1_ = (bx0, by0, bx1, ny_); t2b = (cx_ - wv_ / 2 - 6, ny_, cx_ + wv_ / 2 + 6, by1)
                        placed.extend([t1_, t2b]); _swap.append((v_["bb"], t1_, t2b))
            got = next(((tx, ty, bb) for tx, ty, bb in boxes(c) if free(bb, mk) and not (small and near_other(bb)) and not ambiguous(bb)), None)
            for o_, t1_, t2b in _swap: placed.remove(t1_); placed.remove(t2b); placed.append(o_)
            if not got and name not in OPTIONAL:
                got = next(((tx, ty, bb) for tx, ty, bb in boxes(c) if free(bb, mk) and not (small and near_other(bb))), None)
            if not got and name not in OPTIONAL:
                labs = {v["bb"]: k for k, v in lay.items()}
                for tx, ty, bb in boxes(c):
                    hs = hits_of(bb, mk)
                    if len(hs) != 1 or hs[0] not in labs: continue
                    other = labs[hs[0]]; oc = lay[other]; placed.remove(hs[0]); placed.append(bb)
                    alt = next(((tx2, ty2, bb2) for tx2, ty2, bb2 in boxes(oc) if free(bb2, oc["mk"])), None)
                    placed.remove(bb)
                    if alt:
                        oc.update(tx=alt[0], ty=alt[1], bb=alt[2]); placed.append(alt[2]); got = (tx, ty, bb); break
                    if other in OPTIONAL:
                        del lay[other]; del vals[other]; placed.remove(oc["mk"]); skipped.append(other + " (made room)"); got = (tx, ty, bb); break
                    placed.append(hs[0])
            if not got and name not in OPTIONAL:
                rev = {v: k for k, v in prer.items() if k not in lay and k not in dropped}; best = None
                for tx, ty, bb in boxes(c):
                    hs = hits_of(bb, mk)
                    if hs and all(h in rev for h in hs) and (best is None or len(hs) < len(best[3])): best = (tx, ty, bb, hs)
                if best:
                    for h in best[3]: placed.remove(h); dropped.add(rev[h])
                    got = best[:3]
            if not got and not (PASS_OPT and name in PASSES) and (TP.always(name, name in PASSES) or name in PASSES or name == "Oak Harbor" or name in TP.REQUESTED):

                labs = {v["bb"]: k for k, v in lay.items() if k in OPTIONAL}; mks = {v["mk"]: k for k, v in lay.items() if k in OPTIONAL}
                if name in TP.REQUESTED:
                    _gv = [k for k in lay if k not in OPTIONAL and k not in TP.MUST and k not in TP.LOCKED and k not in TP.REQUESTED
                           and k not in PASSES and k != "Oak Harbor" and TP.pop(k) < TP.pop(name)]
                    labs.update({lay[k]["bb"]: k for k in _gv}); mks.update({lay[k]["mk"]: k for k in _gv})
                rev = {v: k for k, v in prer.items() if k not in lay and k not in dropped}

                rev.update({marks[k]: k for k in marks if k not in lay and k != name and k not in PASSES and k != "Oak Harbor"
                            and k not in TP.MUST and k not in TP.LOCKED and (k not in TP.REQUESTED or name in TP.LOCKED or name in TP.MUST) and (TP.pop(k) < TP.pop(name) or ((name in PASSES or name == "Oak Harbor") and not TP.always(k))) and marks[k] in placed
                            })
                best = None
                if 5 not in FT:
                    f1_ = R.font(R.MONT, 20, 700); f2_ = R.font(R.MONT, 23, 800); na_ = f1_.getbbox("Ag")[3]
                    FT[5] = (f1_, f2_, na_, na_ + GAP + f2_.getbbox("0")[3] + 2, 3, 6)
                for shrink in (0,):
                    trs = tr; f1s, f2s, nas, ths, sws, rrs = FT[trs]
                    wns = max(d.textlength(name, font=f1s), d.textlength(t2_, font=f2s))
                    near = [(x - wns / 2, y - 10 - ths), (x - wns / 2, y + 10)]
                    if name in TP.LOCKED: near = near[:1] if TP.LOCKED[name] == "above" else near[1:]
                    near = [(x - wns / 2 + dx_, y - ths / 2 + dy_) for dx_, dy_ in TP.nudges(name)]
                    if name in TP.LEADER: near = [(x + TP.LEADER[name][0] + a_ - wns / 2, y + TP.LEADER[name][1] + b_ - ths / 2) for a_, b_ in ((0, 0), (0, -8), (0, 8), (10, 0), (10, -8), (10, 8), (20, 0), (-10, 0))]
                    lead = []
                    for rad in ():
                        for k in range(24):
                            a = 2 * math.pi * k / 24; cx_, cy_ = x + rad * math.cos(a), y + rad * math.sin(a)
                            lead.append((cx_ - wns / 2, cy_ - ths / 2))
                    for li, (tx, ty) in enumerate(near + lead):
                        bb = (tx - BXP, ty - 1, tx + wns + BXP, ty + ths + 1)
                        if not inside(bb): continue
                        hs = hits_of(bb, mk)
                        if li >= len(near):
                            px_ = min(max(x, bb[0]), bb[2]); py_ = min(max(y, bb[1]), bb[3])
                            pts_ = [(x + (px_ - x) * t / 10, y + (py_ - y) * t / 10) for t in range(2, 10)]
                            if any(q != mk and not (q[0] <= x <= q[2] and q[1] <= y <= q[3]) and q[0] <= u <= q[2] and q[1] <= v <= q[3] for q in placed for u, v in pts_): continue
                        if os.environ.get("TDBG") and name in os.environ["TDBG"].split(","): print("DBG", name, li, [(k, m) for k, m in marks.items() if m in hs] + [(k, v["bb"]) for k, v in lay.items() if v["bb"] in hs or v["mk"] in hs] + [(k, v) for k, v in prer.items() if v in hs], [h for h in hs if not (h in labs or h in mks or h in rev)], file=sys.stderr)
                        if not all(h in labs or h in mks or h in rev for h in hs): DBG.setdefault(name, set()).update(k for k, v in lay.items() if v['bb'] in hs or v['mk'] in hs); continue
                        cost = 100 * len(hs) + shrink * 25 + (0 if li < len(near) else 60 + (li - len(near)) // 24 * 20)
                        if best is None or cost < best[0]: best = (cost, tx, ty, bb, hs, trs, wns, ths, li >= len(near))
                    if best and best[0] < 40: break
                if best:
                    _, tx, ty, bb, hs, trs, wns, ths, isl = best
                    for h in hs:
                        if h in rev and rev[h] in TP.REQUESTED and name in TP.LOCKED: continue
                        if h in rev: placed.remove(h); dropped.add(rev[h]); continue
                        o = labs.get(h) or mks.get(h)
                        if o in lay:
                            oc = lay.pop(o); vals.pop(o, None); skipped.append(o + " (made room)")
                            for q in (oc["bb"], oc["mk"]):
                                if q in placed: placed.remove(q)
                    f1s, f2s, nas, ths_, sws, rrs = FT[trs]
                    c.update(tw=wns, th=ths, f1=f1s, f2=f2s, na=nas, sw=sws, lead=isl or name in TP.LEADER)
                    got = (tx, ty, bb)
            if not got and os.environ.get("TDBG") and name in os.environ["TDBG"].split(","): print("NOGOT", name, file=sys.stderr)
            if not got:
                skipped.append(name)
                if name in OPTIONAL: placed.remove(mk)
                continue
            c.update(tx=got[0], ty=got[1], bb=got[2]); placed.append(got[2]); lay[name] = c; vals[name] = round(val)
            if os.environ.get("TDBG") and name in os.environ["TDBG"].split(","): print("PLACED", name, [round(v) for v in got[2]], file=sys.stderr)
        return lay, vals, skipped, prer

    allbest = None
    import itertools
    FLIPS = [set(c_) for r_ in range(4) for c_ in itertools.combinations([n_ for n_ in ("Seattle", "Tacoma", "Everett", "Kennewick", "Spokane") if n_ not in TP.LOCKED], r_)]
    for FLIP_ in FLIPS:
      FLIP.clear(); FLIP.update(FLIP_)
      for CORR_SHRINK in (0, 1):
          excl = set(); best = None
          for _ in range(6):
              lay, vals, skipped, prer = place(excl)
              sc_ = len(lay) + 10 * sum(TP.tier(n)[0] <= 2 for n in lay) + 1000 * sum(TP.always(n) for n in lay) + 3000 * sum(n in TP.REQUESTED for n in lay)
              if best is None or sc_ > best[3]: best = (lay, vals, skipped, sc_)
              nx = excl | {n for n in prer if n not in lay} | {n for n in marks if n not in OPTIONAL and n not in lay and n not in PASSES and not TP.always(n)}
              if nx == excl: break
              excl = nx
          nal = 3000 * sum(n in TP.REQUESTED for n in best[0]) + 1000 * sum(TP.always(n) for n in best[0]) + 500 * ("Oak Harbor" in best[0]) + 100 * sum(n in best[0] for n in PASSES) + len(best[0])
          if allbest is None or nal > allbest[0]: allbest = (nal, best, set(FLIP_))
    lay, vals, skipped = allbest[1][:3]; FLIP.clear(); FLIP.update(allbest[2])
    if os.environ.get("REALANCHOR", "1") != "0":
        import region_maps as RM; _rp = {n: P(*REAL[n]) for n in lay}; _in = lambda bb: bb[0] >= 16 and bb[2] <= W - 16 and bb[1] >= 16 and bb[3] <= H - 12; _AL = RM.wa_allowed(R, P, W, H, wa)
        if os.environ.get("ALDUMP"): Image.fromarray((_AL * 255).astype(np.uint8)).save(os.environ["ALDUMP"])
        _ab = np.pad((~_AL).astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        def _in(bb, _f=_in):
            x0, y0, x1, y1 = max(0, int(math.floor(bb[0]))), max(0, int(math.floor(bb[1]))), min(W, int(math.ceil(bb[2]))), min(H, int(math.ceil(bb[3])))
            return _f(bb) and _ab[y1, x1] - _ab[y0, x1] - _ab[y1, x0] + _ab[y0, x0] == 0
        def _in_vec(B, _W=W, _H=H):
            B = np.asarray(B, float).reshape(-1, 4); r = (B[:, 0] >= 16) & (B[:, 2] <= _W - 16) & (B[:, 1] >= 16) & (B[:, 3] <= _H - 12)
            k = np.nonzero(r)[0]
            if len(k):
                Bk = B[k]; x0 = np.maximum(0, np.floor(Bk[:, 0]).astype(int)); y0 = np.maximum(0, np.floor(Bk[:, 1]).astype(int))
                x1 = np.minimum(_W, np.ceil(Bk[:, 2]).astype(int)); y1 = np.minimum(_H, np.ceil(Bk[:, 3]).astype(int))
                r[k] = (_ab[y1, x1] - _ab[y0, x1] - _ab[y1, x0] + _ab[y0, x0]) == 0
            return r
        _in.vec = _in_vec
        if os.environ.get("VEC_CHECK"):
            _sc = _in
            def _in(bb, _sc=_sc): return _sc(bb)
            def _chk(B, _sc=_sc):
                r = _in_vec(B); assert all(bool(a) == bool(_sc(tuple(b))) for a, b in zip(r, np.asarray(B, float).reshape(-1, 4))), "vec mismatch"; return r
            _in.vec = _chk
        TIGHT_L = float(os.environ.get("TIGHT_L") or (40 if REGION else 35))
        _prot = set(TP.MUST) | {"Oak Harbor", "Everett"} | set(TP.REQUESTED) | set(TP.REGION_REQUESTED.get(REGION, []) if REGION else [])
        _prot |= {n_ for n_ in lay if TP.always(n_)}
        _prot |= set(TP.TIGHT_PROTECT.get(REGION, []))
        _prio = sorted(lay, key=lambda n: -(5000 if n in PASSES else TP.pop(n)))
        _in0 = lambda bb: bb[0] >= 16 and bb[2] <= W - 16 and bb[1] >= 16 and bb[3] <= H - 12
        _in0.vec = lambda B: (B[:, 0] >= 16) & (B[:, 2] <= W - 16) & (B[:, 1] >= 16) & (B[:, 3] <= H - 12)
        RM.relax(lay, _rp, base_placed, _in0); RM.relax_push(lay, _rp, base_placed, _in0)
        _pf = lambda n: 5000 if n in PASSES else TP.pop(n)
        TIGHT_DROPPED, TIGHT_EXC = (RM.regreedy if os.environ.get("TIGHT_ALGO", "v2") == "v3" else RM.tighten)(lay, _rp, base_placed, _in, TIGHT_L, _prot, _pf, first=TP.TIGHT_FIRST)
        for n_ in TIGHT_DROPPED: vals.pop(n_, None)
        RM.relax(lay, _rp, base_placed, _in); RM.relax_push(lay, _rp, base_placed, _in, maxd=TIGHT_L)
        _d2 = RM.fix_outliers(lay, _rp, base_placed, _in, TIGHT_L, _prot, _pf)
        _d2 += RM.tighten(lay, _rp, base_placed, _in, TIGHT_L, _prot, _pf, first=TP.TIGHT_FIRST)[0]
        for n_ in _d2: vals.pop(n_, None)
        TIGHT_DROPPED += _d2
        RM.relax(lay, _rp, base_placed, _in); RM.relax_push(lay, _rp, base_placed, _in, maxd=TIGHT_L)
        for n_, c_ in lay.items(): c_["x"], c_["y"] = _rp[n_]
        TIGHT_EXC = {n_: round(math.hypot((c_["bb"][0] + c_["bb"][2]) / 2 - c_["x"], (c_["bb"][1] + c_["bb"][3]) / 2 - c_["y"])) for n_, c_ in lay.items()}
        TIGHT_EXC = {n_: v_ for n_, v_ in TIGHT_EXC.items() if v_ > TIGHT_L + 0.5}
        if os.environ.get("TDBG_TIGHT"): print("TIGHT L=%g dropped=%s exceptions=%s" % (TIGHT_L, TIGHT_DROPPED, TIGHT_EXC), file=sys.stderr)
        pass
    if os.environ.get("ADUMP"):
        json.dump({n: dict(pt=P(*REAL[n]), census=P(*pts[n]), bb=c["bb"], tx=c["tx"], ty=c["ty"], tw=c["tw"], th=c["th"], val=c["val"], t2=c["t2"], ll=REAL[n], f1=c["f1"].size, f2=c["f2"].size) for n, c in lay.items()}, open(os.environ["ADUMP"], "w"), default=float)
    if os.environ.get("TDUMP"): print("DUMP", {n: (tuple(round(v) for v in marks[n]) if n in marks else None, tuple(round(v) for v in lay[n]["bb"]) if n in lay else None) for n in ["Seattle","Tacoma","Everett","Oak Harbor","Bellevue","Federal Way","Mount Vernon","Arlington","Monroe","Enumclaw","Marysville","Burlington","Darrington","Concrete","Bellingham","Anacortes","Stanwood","Lake Stevens","Granite Falls","Auburn","Kent"]}, file=sys.stderr)

    _sz = sorted([(TP.pop(n), c["f1"].size, c["f2"].size, n) for n, c in lay.items() if n not in PASSES and n not in getattr(TP, "SMALL", ()) and n not in TP.TINY], key=lambda t: -t[0])
    for i_ in range(1, len(_sz)):
        if _sz[i_][1] > min(t[1] for t in _sz[:i_]) or _sz[i_][2] > min(t[2] for t in _sz[:i_]):
            raise AssertionError("label size not monotonic with population: %s" % _sz[i_][3])
    NB_KEEP = base_placed; VLEG = None
    if VSCALE:
        import region_maps as RM
        _old = [KO_TB, KO_BAR, KO_LEG]; _base = [p_ for p_ in base_placed if p_ not in _old] + [(0, 0, W, BAR_D + 4), tt_]
        _labs = [str(e_) if (e_ % 10 == 0 or e_ == 32) else "" for e_ in EDGES[:-1]]
        NB_KEEP = _base
    NB_VALS = {}
    if NEIGHBOR_TOWNS:
        import region_maps as RM
        NB_VALS = RM.add_neighbor_labels(REGION, lay, NB_KEEP, P, W, H, d, R, TIERS_OVR or TP.TIERS, lambda lo_, la_: float(sample(np.array(lo_), np.array(la_))),
                                         lambda v_: "%d" % round(v_), BXP, GAP, [P(*v_) for v_ in pts.values()])
    for name, c in lay.items():
        if not c.get("lead"): continue
        x, y = c["x"], c["y"]; bx0_, by0_, bx1_, by1_ = c["bb"]; by1_ = min(by1_, c["ty"] + c["na"] + 2)
        px_ = min(max(x, bx0_), bx1_); py_ = min(max(y, by0_), by1_)
        d.line((x, y, px_, py_), fill=INK, width=6); d.line((x, y, px_, py_), fill=(255, 255, 255), width=2)
        if name in TP.LEADER: d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 255, 255), outline=INK, width=3)
    for name, c in lay.items():
        x, y, tx, ty, tw = c["x"], c["y"], c["tx"], c["ty"], c["tw"]
        if name in PASSES:
            pass
        else:
            pass
        cx = tx + tw / 2
        sw = c["sw"]
        pass

        an = "mt"
        if not c.get("lead") and tx + tw <= x - 4: cx, an = tx + tw, "rt"
        elif not c.get("lead") and tx >= x + 4 and name not in getattr(TP, "SMALL", ()): cx, an = tx, "lt"
        _vu = TP.REGION_VAL_UNDER.get(REGION, {}).get(name) if REGION else None
        if _vu:
            d.text((tx, ty), name, font=c["f1"], fill=WHITE, stroke_width=sw, stroke_fill=INK, anchor="lt")
            d.text((tx + d.textlength(_vu, font=c["f1"]) / 2, ty + c["na"] + GAP), c["t2"], font=c["f2"], fill=val_color(round(c["val"])), stroke_width=sw + 1, stroke_fill=INK, anchor="mt")
            continue
        d.text((cx, ty), name, font=c["f1"], fill=WHITE, stroke_width=sw, stroke_fill=INK, anchor=an)
        d.text((cx, ty + c["na"] + GAP), c["t2"], font=c["f2"], fill=val_color(round(c["val"])), stroke_width=sw + 1, stroke_fill=INK, anchor=an)
    for name, c in lay.items():
        if name in TP.LEADER: d.ellipse((c["x"] - 6, c["y"] - 6, c["x"] + 6, c["y"] + 6), fill=(255, 255, 255), outline=INK, width=3)
    im = im.convert("RGB"); d = ImageDraw.Draw(im)
    if SUMMARY_OVR is not None: lowlands = east = [0]
    else: lowlands = [vals[k] for k in ("Seattle", "Tacoma", "Olympia", "Vancouver", "Bellingham", "Aberdeen") if k in vals]
    if SUMMARY_OVR is None: east = [vals[k] for k in ("Spokane", "Yakima", "Wenatchee", "Ellensburg", "Moses Lake", "Kennewick", "Walla Walla", "Pullman", "Omak", "Colville", "Goldendale") if k in vals]
    l1 = "West side %d to %d, east side %d to %d" % (min(lowlands), max(lowlands), min(east), max(east)) if not REGION else None
    if REGION:
        rng = lambda ks: [vals[k] for k in ks if k in vals]
        if REGION == "west": g1, g2, n1, n2 = rng(("Seattle", "Tacoma", "Everett", "Bellevue", "Olympia", "Bellingham", "Federal Way", "Mount Vernon")), \
            rng(("Aberdeen", "Ocean Shores", "Westport", "Long Beach", "Forks", "Neah Bay", "Raymond", "Ilwaco", "La Push")), "Puget Sound", "coast"
        else: g1, g2, n1, n2 = rng(("Spokane", "Spokane Valley", "Cheney", "Deer Park", "Medical Lake", "Airway Heights", "Liberty Lake")), \
            rng(("Moses Lake", "Ephrata", "Othello", "Quincy", "Kennewick", "Pasco", "Richland", "Ritzville")), "Spokane area", "Columbia Basin"
        f_ = lambda g: ("%d" % g[0]) if min(g) == max(g) else "%d to %d" % (min(g), max(g))
        l1 = ", ".join("%s %s" % (n, f_(g)) for n, g in ((n1, g1), (n2, g2)) if g)
        l1 = l1[:1].upper() + l1[1:]

    tv = {k: v for k, v in vals.items() if k not in PASSES}
    import region_maps as RM
    _fit2 = lambda t_: d.textlength(t_, font=R.font(R.MONT, SUM2_PX, 800)) <= SUM_MAXW
    l2 = RM.extreme_line(tv, TP.pop, "Warmest" if kind == "high" else "Coldest", kind != "high", "", _fit2)
    if SUMMARY_OVR is not None: l1, l2 = SUMMARY_OVR(tv, _fit2)
    def fit(txt, px):
        while px > 20 and d.textlength(txt, font=R.font(R.MONT, px, 800)) > SUM_MAXW: px -= 2
        return R.font(R.MONT, px, 800)
    for txt, px, col, yb in ((l2, SUM2_PX, TCOL, SUM_B), (l1, SUM1_PX, (255, 255, 255), SUM_B - SUM2_PX - SUM_GAP)):
        d.text((SUM_R, yb), txt, font=fit(txt, px), fill=col, stroke_width=4, stroke_fill=INK, anchor="rs")
    d.text((DATE_L, DATE_B), subtitle, font=fdate, fill=(255, 255, 255), stroke_width=4, stroke_fill=INK, anchor="ls")
    if SRC_OVR and not SRC_OVR.startswith("Data: NOAA"): R.subtle_credit(im, d, (DATE_L, CRED_Y), src, fs)
    pass
    base = im.convert("RGBA")
    out = save_final(base, out_path, quality=97)
    imax = np.unravel_index(np.argmax(np.where(inwa, TF, -999)), TF.shape)
    return {"out": out, "size": [W, H], "wa_min": round(float(tw_.min()), 1), "wa_max": round(float(tw_.max()), 1),
            "wa_max_at": [round(float(LA[imax]), 3), round(float(LO[imax]), 3)], "towns": vals, "skipped": skipped,
            "n_labels": len(vals), "neighbor_towns": NB_VALS, "top_scale": list(TS) if VSCALE else None, "bar_drawn": BAR_D, "passes": {k: vals[k] for k in PASSES if k in vals}, "title": title, "subtitle": subtitle, "l1": l1, "l2": l2}

FRAME_W, FRAME_CY = 0.84, 0.56
TOP_FADE, BOT_FADE = 260, 190
TITLE_PX, SUB_PX = 112, 46
SCALE_X0, SCALE_X1, SCALE_Y, SCALE_BH = 700, 1820, 172, 18
SUM1_PX, SUM2_PX, SUM_MAXW, SUM_GAP = 44, 38, 1000, 12
NAME_PX, VAL_PX = 28, 33
SMALL_NAME_PX, SMALL_VAL_PX = 23, 27
FRAME_BOX, FRAME_BH = (-124.80, 45.54, -116.91, 49.0), 1.0
BXP = 3
RPAD_PX = int(os.environ.get("RPAD", "12"))
FILL_NEIGHBORS = False
TOP_BAR = False
PASS_OPT = False
REGION = None; REGION_SUB = None; TITLE_MAXW = None; CORNER_S = CORNER_PAD = None; TIERS_OVR = None; SHOW_PASSES = True
N_CORRIDOR = 30

NEIGHBOR_DIM = 0
VSCALE = False
PTS_FILTER = VALUE_OVR = SUMMARY_OVR = None
NEIGHBOR_TOWNS = True

def configure_region(region, neighbor_towns=False):
    ""\
\

    wide = region == 'west_wide'; region = 'west' if wide else region
    g = globals()
    import region_maps as RM
    RM.set_nudges(region)
    g.update(REGION=region, REGION_SUB=TP.REGION_NAME[region], W=1600, H=2400, FRAME_BOX=TP.REGION_BOX[region], FRAME_W=0.96,
             FRAME_BH=(2400 - 290 - 125) / 2400, FRAME_CY=(290 + 2400 - 125) / 2 / 2400, TOP_FADE=1, BOT_FADE=170, TITLE_PX=100, SUB_PX=44,
             TITLE_MAXW=1600 - 2 * 290, CORNER_S=180, CORNER_PAD=24, SCALE_X0=240, SCALE_X1=1440, SCALE_Y=226, SCALE_BH=18,
             BXP=int(os.environ.get("RBXP", "7")), SUM1_PX=38, SUM2_PX=32, SUM_MAXW=980, SUM_GAP=10, TIERS_OVR=TP.REGION_TIERS, SHOW_PASSES=True,
             FILL_NEIGHBORS=True, TOP_BAR=True)
    if neighbor_towns:
        g.update(NEIGHBOR_TOWNS=True)
    RM.towns(g, region)
    if region == 'west' and not wide: RM.west_tight(g)

def labels(kind, date, hour):
    day = date.strftime("%A"); md = "%d-%d" % (date.month, date.day)
    if kind == "high": return "%s Predicted High Temps" % day, "Afternoon highs %s %s" % (day, md)
    if not LOW_SNAPSHOT:
        return "%s Predicted Low Temps" % day, "Coldest Temps %d AM to %d AM %s %s" % (LOW_H0, LOW_H1, day, md)
    lt = dt.datetime(date.year, date.month, date.day, hour, tzinfo=UTC).astimezone(PT)
    part = "Morning" if lt.hour < 12 else "Afternoon" if lt.hour < 17 else "Evening"
    return "%s Predicted Low Temps" % lt.strftime("%A"), "%d %s %s %d-%d" % (lt.hour % 12 or 12, "AM" if lt.hour < 12 else "PM", lt.strftime("%A"), lt.month, lt.day)

def main(argv=None, defaults=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", choices=["low", "high"], default="high")
    ap.add_argument("--source", choices=["nbm", "gfs", "eps"], default="nbm", help="nbm (default), gfs (6 h TMAX/TMIN records) or eps (ECMWF ENS mean of member extremes)")
    ap.add_argument("--date", help="target local date YYYY-MM-DD")
    ap.add_argument("--hour", type=int, default=14, help="UTC hour for --kind low (14 = 7 AM PDT / 6 AM PST)")
    ap.add_argument("--cycle", help="NBM cycle YYYYMMDDHH (default newest that has the record)")
    ap.add_argument("--out", help="output folder")
    ap.add_argument("--npz", help="use this cropped data file instead of downloading")
    ap.add_argument("--refresh", action="store_true", help="re-download even if the out folder already has data")
    ap.add_argument("--title"); ap.add_argument("--subtitle")
    if defaults: ap.set_defaults(**defaults)
    ap.add_argument("--no-corner", action="store_true", help="no-op (kept for command compatibility)")
    ap.add_argument("--region", choices=["west", "east", "west_wide"], help="vertical 1600x2400 regional map (Western / Eastern Washington) with more towns")
    ap.add_argument("--top-scale", action="store_true", help="--region maps: old header (region/model lines) and horizontal scale in a tall top bar")
    ap.add_argument("--no-neighbor-towns", action="store_true", help="turn OFF the default OR/ID/BC reference town labels (and the frame/bar move north on --region; full-state fill back to off)")
    ap.add_argument("--fill-neighbors", action="store_true", help="also draw the data over Oregon/Idaho/BC land (default off on the full-state map, on with --region)")
    ap.add_argument("--no-fill-neighbors", action="store_true", help="--region maps: leave neighbor land blank")
    a = ap.parse_args(argv)
    global SOURCE; SOURCE = a.source   # pass height correction picks the terrain file by source
    global FILL_NEIGHBORS, NEIGHBOR_TOWNS, VSCALE
    VSCALE = bool(a.region) and not a.top_scale
    NEIGHBOR_TOWNS = not a.no_neighbor_towns
    if NEIGHBOR_TOWNS: FILL_NEIGHBORS = True
    if a.region: configure_region(a.region, NEIGHBOR_TOWNS)
    if a.fill_neighbors: FILL_NEIGHBORS = True
    if a.no_fill_neighbors: FILL_NEIGHBORS = False
    global NO_CORNER; NO_CORNER = a.no_corner
    if not a.date: ap.error("--date is required")
    date = dt.date.fromisoformat(a.date)
    out = a.out or "out/nbm_%ss_%s_%s" % (a.kind, date.strftime("%a").lower(), date.strftime("%Y%m%d"))
    os.makedirs(out, exist_ok=True)
    if a.source != "nbm": return main_extra(a, date, out)
    npz = a.npz or os.path.join(out, "nbm_%s_wa.npz" % a.kind); metaf = os.path.join(out, "nbm_%s_meta.json" % a.kind)
    meta = json.load(open(metaf)) if os.path.exists(metaf) else {}
    if a.npz or (os.path.exists(npz) and not a.refresh and not a.cycle):
        z = np.load(npz); TF, LA, LO = z["tf"], z["lats"], z["lons"]; meta.setdefault("source", "cached " + npz)
    else:
        import subprocess
        subprocess.run([sys.executable, os.path.abspath(__file__), "--_fetch", a.kind, a.date, str(a.hour), a.cycle or "", npz, metaf], check=True)
        z = np.load(npz); TF, LA, LO = z["tf"], z["lats"], z["lons"]; meta = json.load(open(metaf))
    t, st = labels(a.kind, date, a.hour)
    res = render(TF, LA, LO, a.kind, a.title or t, a.subtitle or st, os.path.join(out, "final.jpg"))
    res["nbm"] = meta; print(json.dumps(res, default=str)); return res

def main_extra(a, date, out):
    global MODEL_TAG_OVR, SRC_OVR
    import extra_sources as XS
    L = XS.LABELS[a.source]
    if a.cycle: cyc = dt.datetime.strptime(a.cycle, "%Y%m%d%H").replace(tzinfo=UTC)
    else:
        now = dt.datetime.now(UTC).replace(minute=0, second=0, microsecond=0); cyc = now - dt.timedelta(hours=now.hour % 6 + 6)
    z, meta = XS.load(a.kind, a.source, cyc, 0, 0, os.path.join(os.environ.get("WX_CACHE") or os.path.dirname(os.path.abspath(__file__)), "xs_cache"), date=date, refresh=a.refresh)
    LON, LAT = np.meshgrid(z["lon"], z["lat"])
    MODEL_TAG_OVR, SRC_OVR = L["tag"], L["src"]
    t, st = labels(a.kind, date, a.hour)
    res = render(z["g"], LAT, LON, a.kind, a.title or t, a.subtitle or st, os.path.join(out, "final.jpg"))
    res[a.source] = meta; print(json.dumps(res, default=str)); return res

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--_fetch":
        k, ds, hr, cy, npz, metaf = sys.argv[2:8]
        TF, LA, LO, meta = fetch(k, dt.date.fromisoformat(ds), int(hr), cy or None)
        hourly = meta.pop("hourly", None)
        np.savez_compressed(npz, tf=TF, lats=LA, lons=LO, **({"hourly": hourly} if hourly is not None else {})); json.dump(meta, open(metaf, "w"), indent=1, default=str)
    else:
        main()
