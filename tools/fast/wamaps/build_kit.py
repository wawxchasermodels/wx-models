"""WA Maps kit builder (Phase 1, 10-31-26): static layers + label layout for the client-drawn NBM state-view temp maps.
Runs the REAL nbm_map.render() (locked style, /workspace/wa_extras) with hooks, so base, borders, fade, scale, logo, model tag and
town names come out pixel-identical; only the data fill, the numbers, title, summary and date line are drawn by the browser.
  ecmwf_venv/bin/python build_kit.py <npz with tf/lats/lons> <kind low|high> <view full|west|east> <outdir>
Layers: base.png (dark base, under the data), overlay.png (RGBA: borders, fade, scale, model tag, names, logo; extracted from a
black and a white run), mask.png (where the data is drawn), lut.bin (float32 fi,fj into the fast NBM crop every STRIDE px),
titles/*.png (Impact title per weekday, rasterized here), kit.json (value label positions, sample points, summary config)."""
import sys, os, json, math
sys.path.insert(0, "/workspace/wa_extras"); sys.path.insert(0, "/workspace/mapgen")
os.chdir("/workspace/wa_extras")
import numpy as np
from PIL import Image, ImageDraw
npz, kind, view, out = sys.argv[1:5]
os.makedirs(out + "/titles", exist_ok=True)
import nbm_map as NM
import render_alert_map as R, forecast_base as FB, save_final as SF, town_pop as TP, region_maps as RM
G = json.load(open("/tmp/nbm_grid.json")); CROP = [820, 1486, 42, 847]; STRIDE = 8
# same globals as nbm_map.main() with default flags
NM.SOURCE = "nbm"; NM.VSCALE = view != "full"; NM.NEIGHBOR_TOWNS = True; NM.FILL_NEIGHBORS = True
if view != "full": NM.configure_region(view, True)
z = np.load(npz); TF, LA, LO = z["tf"], z["lats"], z["lons"]
TITLE = "Saturday Predicted %s Temps" % ("Low" if kind == "low" else "High")
SUB = "WAMAPS_SUBTITLE"
# ---- hooks
_font = R.font
def font(path, size, wg=None):
    f = _font(path, size, wg); f._key = (path, int(size), wg); return f
R.font = font
REC = []; STATE = {}
_text = ImageDraw.ImageDraw.text
NB_NAMES = {n for v in RM.NEIGHBOR_TOWNS.values() for n, *_ in v}
def text(self, xy, txt, *a, **k):
    f = k.get("font"); key = getattr(f, "_key", None)
    op = dict(t=str(txt), x=float(xy[0]), y=float(xy[1]), anchor=k.get("anchor") or "la", font=key and [os.path.basename(key[0]), key[1], key[2]],
              fill=list(k.get("fill")) if isinstance(k.get("fill"), tuple) else k.get("fill"), sw=k.get("stroke_width", 0))
    prev = STATE.get("prev")
    num = op["t"].lstrip("-").isdigit()
    dyn = op["t"] == TITLE or op["t"] == SUB or op["anchor"] in ("rs", "ls") or (num and prev and prev.get("kind") == "name")
    op["kind"] = "title" if op["t"] == TITLE else "date" if op["t"] == SUB else "summary" if op["anchor"] == "rs" else "value" if dyn else \
        ("name" if (op["t"] in NM.TOWNS or op["t"] in NB_NAMES or op["t"] in NM.PASSES) else "static")
    STATE["prev"] = op
    if STATE.get("record"): REC.append(op)
    if not dyn: return _text(self, xy, txt, *a, **k)
ImageDraw.ImageDraw.text = text
_base = FB.dark_base
def dark_base(*a, **k):
    im = _base(*a, **k); STATE["base"] = im.copy(); return im
FB.dark_base = dark_base
_bt = R.draw_borders_on_top
def borders(im, *a, **k):
    STATE["withdata"] = im.copy(); im.paste(STATE["bg"] + (255,), (0, 0, im.width, im.height)); return _bt(im, *a, **k)
R.draw_borders_on_top = borders
_fm = RM.fill_mask
def fill_mask(*a, **k):
    m = _fm(*a, **k); STATE["fm"] = m; return m
RM.fill_mask = fill_mask
def save_final(im, path, quality=None):
    STATE["final"] = im.copy(); return path
SF.save_final = save_final
# ---- two runs (black / white under everything drawn after the data) -> overlay with alpha
runs = {}
for bg in ((0, 0, 0), (255, 255, 255)):
    STATE.update(bg=bg, record=bg == (0, 0, 0), prev=None); res = NM.render(TF, LA, LO, kind, TITLE, SUB, "/tmp/wamaps_kit_dummy.jpg")
    runs[bg] = np.asarray(STATE["final"].convert("RGB")).astype(np.float32)
Ib, Iw = runs[(0, 0, 0)], runs[(255, 255, 255)]
alpha = np.clip(1 - (Iw - Ib).mean(-1) / 255.0, 0, 1)
col = np.where(alpha[..., None] > 1e-3, Ib / np.maximum(alpha[..., None], 1e-3), 0)
ov = np.dstack([np.clip(col, 0, 255), alpha * 255]).astype(np.uint8)
Image.fromarray(ov, "RGBA").save(out + "/overlay.png", optimize=True)
base = STATE["base"].convert("RGB"); base.save(out + "/base.png", optimize=True)
fm = STATE["fm"]   # the exact data mask (3x supersampled) -> soft 1x mask, like the LANCZOS-downsampled alpha
mask = fm.reshape(fm.shape[0] // 3, 3, fm.shape[1] // 3, 3).mean((1, 3))
Image.fromarray(np.round(mask * 255).astype(np.uint8), "L").save(out + "/mask.png", optimize=True)
W, H = NM.W, NM.H
# ---- frame + LUT (image px -> fast NBM crop fi, fj)
from shapely.geometry import box as sbox
R.W, R.H = W, H
P = R.frame(sbox(*NM.FRAME_BOX), box_w=NM.FRAME_W, box_h=NM.FRAME_BH, cy=NM.FRAME_CY)
import pyproj
lcc = pyproj.Proj(G["proj4"])
def ij(lon, lat):
    x, y = lcc(lon, lat); return (np.asarray(y) - G["gy0"]) / G["d"] - CROP[0], (np.asarray(x) - G["gx0"]) / G["d"] - CROP[2]
nx, ny = W // STRIDE + 2, H // STRIDE + 2
xs = P.x0 + (np.arange(nx) * STRIDE + 0.5) / P.k; ys = P.y0 + (np.arange(ny) * STRIDE + 0.5) / P.k
lon, _ = R.px2ll(xs, np.zeros_like(xs)); _, lat = R.px2ll(np.zeros_like(ys), ys)
LON, LAT = np.meshgrid(lon, lat); fi, fj = ij(LON, LAT)
np.stack([fi, fj], -1).astype("<f4").tofile(out + "/lut.bin")
# ---- labels: value ops with their town, sample point and pass correction
pts = dict(NM.PASSES)
for l in open("/workspace/mapgen/data/2023_Gaz_place_national.txt", encoding="latin-1"):
    c = l.rstrip("\n").split("\t")
    if c[0] != "WA": continue
    for suf in (" city", " town", " CDP"):
        nm = c[3][:-len(suf)]
        if c[3].endswith(suf) and nm in NM.TOWNS and not (suf == " CDP" and nm in pts): pts[nm] = (float(c[11]), float(c[10]))
if NM.REGION: pts.update({k: v for k, v in TP.REGION_POINTS.items() if k in NM.TOWNS and k not in pts})
NB = {n: (lo_, la_) for n, lo_, la_, *_ in RM.NEIGHBOR_TOWNS[NM.REGION or "full"]}
import pass_terrain as PTC
labels = []
for k_, op in enumerate(REC):
    if op["kind"] != "value": continue
    name = REC[k_ - 1]["t"]; wa = name not in NB
    if wa: vlo, vla = pts[name] if name in NM.PASSES else TP.value_point(name, pts[name])
    else: vlo, vla = NB[name]
    a, b = ij(vlo, vla); corr = (PTC.corrected("nbm", name, 0.0, vlo, vla) if name in NM.PASSES else 0.0)
    labels.append(dict(name=name, wa=wa, pass_=name in NM.PASSES, pop=TP.pop(name), fi=float(a), fj=float(b), corr=round(float(corr), 3),
                       ref=int(op["t"]), **{k: op[k] for k in ("x", "y", "anchor", "font", "sw")}))
summ = [op for op in REC if op["kind"] == "summary"]; date = [op for op in REC if op["kind"] == "date"]
# ---- titles (Impact, rasterized here: same fit / center / shadow as nbm_map.render)
tops = [op for op in REC if op["kind"] == "title"]
t0 = tops[-1]; d0 = ImageDraw.Draw(Image.new("RGBA", (W, 10)))
maxw = NM.TITLE_MAXW or W - 600
for k2 in ("low", "high"):
    for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
        t = "%s Predicted %s Temps" % (day, "Low" if k2 == "low" else "High"); size = NM.TITLE_PX
        while size > 10:
            fo = _font(R.IMPACT, size)
            if d0.textlength(t, font=fo) <= maxw: break
            size -= 2
        hgt = int(t0["y"] + size * 1.4 + 16); im = Image.new("RGBA", (W, hgt), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
        tw = dd.textlength(t, font=fo); x = (W - tw) / 2
        _text(dd, (x + 8, t0["y"] + 8), t, font=fo, fill=(0, 0, 0)); _text(dd, (x, t0["y"]), t, font=fo, fill=(255, 255, 255))
        im.save(f"{out}/titles/{k2}_{day}.png", optimize=True)
kit = dict(view=view, W=W, H=H, stride=STRIDE, nx=nx, ny=ny, crop=CROP, region=NM.REGION, labels=labels, summary=summ, date=date,
           sum_maxw=NM.SUM_MAXW, sum_px=[NM.SUM1_PX, NM.SUM2_PX], sum_gap=NM.SUM_GAP,
           pops={n: TP.pop(n) for n in NM.TOWNS}, model_tag="[NBM 2.5 km]", built_from=dict(npz=npz, kind=kind, l1=res.get("l1"), l2=res.get("l2"), towns=res.get("towns")),
           static_ops=[op for op in REC if op["kind"] in ("static",)])
json.dump(kit, open(out + "/kit.json", "w"), indent=0)
print(view, kind, "labels", len(labels), "(WA %d, neighbors %d)" % (sum(l["wa"] for l in labels), sum(not l["wa"] for l in labels)), "W,H", W, H, "summary ops", len(summ), "date ops", len(date))
