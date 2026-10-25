#!/usr/bin/env python3
"""Small drawing core for the Washington forecast maps: web-mercator projection, basemap layers, borders, fonts and
route shields. Public-domain / openly licensed inputs only (see assets/LICENSES.md). Part of wx-models (MIT)."""
import json, math, os, pickle
import numpy as np, shapely
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from shapely.geometry import LineString

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.environ.get("WX_ASSETS", os.path.join(HERE, "assets"))
CACHE = os.environ.get("WX_CACHE", "cache")


def asset(name):
    return os.path.join(ASSETS, name)


def _first(*paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return paths[-1]


# Title font: Impact from the Microsoft core fonts package (installed at build time, never committed),
# or any path in WX_FONT_TITLE. Body font: Montserrat (SIL OFL 1.1, committed).
IMPACT = _first(os.environ.get("WX_FONT_TITLE"), asset("fonts/Impact.ttf"),
                "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf", "/usr/share/fonts/truetype/msttcorefonts/impact.ttf")
MONT = os.environ.get("WX_FONT_BODY", asset("fonts/Montserrat.ttf"))

W = H = 2160
LAND_MASK = None


def polys(g):
    if g.is_empty: return []
    if g.geom_type == "Polygon": return [g]
    return [p for part in getattr(g, "geoms", []) for p in polys(part)]


def ll2px(lon, lat):
    x = (lon + 180) / 360 * 256
    y = (1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * 256
    return x, y


def px2ll(x, y):
    lon = x / 256 * 360 - 180
    lat = np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * y / 256))))
    return lon, lat


class Proj:
    def __init__(s, x0, y0, k): s.x0, s.y0, s.k = x0, y0, k
    def __call__(s, lon, lat):
        x, y = ll2px(lon, lat); return (x - s.x0) * s.k, (y - s.y0) * s.k
    def ring(s, coords): return [s(lo, la) for lo, la in coords]
    def bounds_ll(s):
        lo0, la1 = px2ll(s.x0, s.y0); lo1, la0 = px2ll(s.x0 + W / s.k, s.y0 + H / s.k)
        return float(lo0), float(la0), float(lo1), float(la1)


def frame(geom, box_w=0.80, box_h=0.52, cy=0.50, min_span_deg=0.0):
    lo0, la0, lo1, la1 = geom.bounds
    (xa, ya), (xb, yb) = ll2px(lo0, la1), ll2px(lo1, la0)
    k = min(W * box_w / (xb - xa), H * box_h / (yb - ya))
    if min_span_deg: k = min(k, W / (min_span_deg * 256 / 360))
    cx0, cy0 = (xa + xb) / 2, (ya + yb) / 2
    return Proj(cx0 - W / 2 / k, cy0 - H * cy / k, k)


CREDIT_ALPHA = 0.38
CREDIT_HALO_ALPHA = 0.30
CREDIT_SIZE = 22


def subtle_credit(im, d, xy, text, f):
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
    dl.text(xy, text, font=f, fill=(255, 255, 255, int(255 * CREDIT_ALPHA)), stroke_width=1, stroke_fill=(0, 0, 0, int(255 * CREDIT_HALO_ALPHA)))
    if im.mode == "RGBA": im.alpha_composite(lay)
    else: im.paste(lay, (0, 0), lay)


BM = asset("basemap")
LAND, WATER = (62, 64, 68), (29, 30, 34)
COUNTY_LN, STATE_LN, NATION_LN = (104, 108, 117), (178, 183, 196), (190, 195, 206)
BORDERS = {}
_bm = {}


def layer(name):
    if name not in _bm:
        rows = pickle.load(open(os.path.join(BM, name + ".pkl"), "rb"))
        _bm[name] = (rows, np.array([g for _, g in rows], dtype=object))
    return _bm[name]


def in_frame(name, bb):
    rows, geoms = layer(name)
    return [rows[i] for i in np.nonzero(shapely.intersects(geoms, bb))[0]]


def _np_ring(P, coords):
    a = np.asarray(coords, dtype=float)
    x = (a[:, 0] + 180) / 360 * 256
    lat = np.radians(np.clip(a[:, 1], -85, 85))
    y = (1 - np.log(np.tan(lat) + 1 / np.cos(lat)) / np.pi) / 2 * 256
    return list(zip(((x - P.x0) * P.k).tolist(), ((y - P.y0) * P.k).tolist()))


def _fill(mask_draw, P, g):
    for pg in polys(g):
        mask_draw.polygon(_np_ring(P, pg.exterior.coords), fill=255)
        for h in pg.interiors: mask_draw.polygon(_np_ring(P, h.coords), fill=0)


def _lines(g):
    if g.is_empty: return []
    t = g.geom_type
    if t == "LineString": return [g]
    if t == "LinearRing": return [LineString(g.coords)]
    if t == "Polygon": return [LineString(g.exterior.coords)] + [LineString(h.coords) for h in g.interiors]
    return [l for part in getattr(g, "geoms", []) for l in _lines(part)]


def draw_borders_on_top(im, P, sc, fm):
    """State and county lines drawn over the data fill so they stay readable."""
    if not BORDERS: return
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); dl = ImageDraw.Draw(lay)
    for g in BORDERS.get('county', []):
        for ln in _lines(g): dl.line(_np_ring(P, ln.coords), fill=(20, 22, 28, 190), width=max(3, int(round(3.0 * sc))))
    mask = Image.fromarray((np.array(lay.split()[3], dtype=np.uint16) * np.array(fm, dtype=np.uint16) // 255).astype(np.uint8))
    lay.putalpha(mask); im.alpha_composite(lay)
    d = ImageDraw.Draw(im)
    for ln in BORDERS.get('state', []):
        pts = _np_ring(P, ln.coords)
        d.line(pts, fill=(16, 18, 24, 255), width=max(4, int(round(7.5 * sc))), joint="curve")
    for ln in BORDERS.get('state', []):
        d.line(_np_ring(P, ln.coords), fill=(232, 235, 242, 255), width=max(2, int(round(3.6 * sc))), joint="curve")


_fc = {}


def font(path, size, wg=None):
    key = (path, int(size), wg)
    if key not in _fc:
        f = ImageFont.truetype(path, int(size))
        if wg is not None:
            try: f.set_variation_by_axes([wg])
            except Exception: pass
        _fc[key] = f
    return _fc[key]


_shield_mem = {}
SHIELDS = asset("shields")


def state_shield_img(num, h):
    """Generic state route marker (MUTCD M1-5 style): white circle (1-2 digits) or rounded rectangle (3 digits)."""
    k = ("State", num, h)
    if k in _shield_mem: return _shield_mem[k]
    ww = h if len(num) <= 2 else int(h * 1.3)
    s = 4; big = Image.new("RGBA", (ww * s, h * s), (0, 0, 0, 0)); bd = ImageDraw.Draw(big)
    bw = max(2, h * s // 22)
    if len(num) <= 2: bd.ellipse((0, 0, ww * s - 1, h * s - 1), fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=bw)
    else: bd.rounded_rectangle((0, 0, ww * s - 1, h * s - 1), radius=h * s // 5, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=bw)
    fs = int(h * s * (0.58 if len(num) <= 2 else 0.52)); f = font(MONT, fs, 800)
    while bd.textlength(num, font=f) > ww * s * 0.80: fs -= 4; f = font(MONT, fs, 800)
    bd.text((ww * s / 2, h * s / 2), num, font=f, fill=(0, 0, 0, 255), anchor="mm")
    sh = big.resize((ww, h), Image.LANCZOS)
    pad = max(5, h // 12)
    out = Image.new("RGBA", (sh.width + 2 * pad, sh.height + 2 * pad), (0, 0, 0, 0))
    a0 = Image.new("L", out.size, 0); a0.paste(sh.getchannel("A"), (pad, pad))
    halo = a0.filter(ImageFilter.MaxFilter(2 * (pad - 1) + 1)).filter(ImageFilter.GaussianBlur(pad / 3))
    out.paste((8, 9, 12, 255), (0, 0), halo.point(lambda v: int(v * .85)))
    out.alpha_composite(sh, (pad, pad))
    _shield_mem[k] = out
    return out


def shield_img(level, num, h):
    """Official MUTCD Interstate (M1-1) / US route (M1-4) marker from the committed public-domain SVGs
    (Wikimedia Commons PD-USGov-MUTCD, see assets/shields/*.license.json). None if no verified file is committed."""
    k = (level, num, h)
    if k in _shield_mem: return _shield_mem[k]
    title = f"I-{num}.svg" if level == "Interstate" else f"US_{num}.svg"
    svg, meta = os.path.join(SHIELDS, title), os.path.join(SHIELDS, title + ".license.json")
    ok = os.path.exists(svg) and os.path.exists(meta) and json.load(open(meta)).get("ok")
    if not ok: _shield_mem[k] = None; return None
    os.makedirs(os.path.join(CACHE, "shields"), exist_ok=True)
    png = os.path.join(CACHE, "shields", f"{title[:-4]}_{h}.png")
    if not os.path.exists(png):
        import cairosvg
        cairosvg.svg2png(url=svg, write_to=png, output_height=h)
    sh = Image.open(png).convert("RGBA")
    pad = max(5, h // 12)
    out = Image.new("RGBA", (sh.width + 2 * pad, sh.height + 2 * pad), (0, 0, 0, 0))
    a0 = Image.new("L", out.size, 0); a0.paste(sh.getchannel("A"), (pad, pad))
    halo = a0.filter(ImageFilter.MaxFilter(2 * (pad - 1) + 1)).filter(ImageFilter.GaussianBlur(pad / 3))
    out.paste((8, 9, 12, 255), (0, 0), halo.point(lambda v: int(v * .85)))
    rim = a0.filter(ImageFilter.MaxFilter(2 * max(1, h // 45) + 1))
    out.paste((175, 178, 186, 255), (0, 0), rim)
    out.alpha_composite(sh, (pad, pad))
    _shield_mem[k] = out
    return out
