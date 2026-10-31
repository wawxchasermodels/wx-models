"""WA Maps quick slice (10-31-26, Benjamin 12:35 PM): extra kit pieces for precipitation / snowfall totals from several models.
Reuses the Phase 1 kit (same base, frame, town label layout); adds per view:
  lut_<m>.bin    float32 (fi, fj) into model m's fast crop every `stride` map px (from the NBM LUT: NBM grid -> lon/lat -> model grid)
  lab_<m>.json   [[fi, fj], ...] sample point of every value label in low.json, on model m's grid
  plain_overlay.png  low_overlay.png without the temperature scale and the [NBM 2.5 km] tag (both drawn by the page per product)
  titles/precip.png, titles/snow.png  Impact titles rasterized here (the font itself is never served)
  python3 build_totals_kit.py <site/wamaps/kit>"""
import sys, os, json
import numpy as np, pyproj
from PIL import Image, ImageDraw, ImageFont
KIT = sys.argv[1]
G = dict(proj4="+ellps=sphere +a=6371200.0 +b=6371200.0 +proj=lcc +lon_0=-95.0 +lat_0=25.0 +x_0=0.0 +y_0=0.0 +lat_1=25.0 +lat_2=25.0 +no_defs",
         gx0=-3271151.6058371696, gy0=-263793.73346456443, d=2539.7029999983497)   # NBM 2.5 km (as in build_kit.py /tmp/nbm_grid.json)
NBM_CROP = [820, 1486, 42, 847]
nbm = pyproj.Proj(G["proj4"])
def nbm_ll(fi, fj):
    x = (np.asarray(fj) + NBM_CROP[2]) * G["d"] + G["gx0"]; y = (np.asarray(fi) + NBM_CROP[0]) * G["d"] + G["gy0"]
    return nbm(x, y, inverse=True)
# HRRR 3 km: sphere 6371229 m, LCC 38.5/38.5, lon0 -97.5, first point 21.138123 N 237.280472 E (row 0 = south, like the encoder)
hr = pyproj.Proj("+proj=lcc +lat_0=38.5 +lon_0=-97.5 +lat_1=38.5 +lat_2=38.5 +a=6371229 +b=6371229 +x_0=0 +y_0=0 +no_defs")
hx0, hy0 = hr(237.280472 - 360, 21.138123)
MODELS = {   # model -> (lon, lat) -> (image row, column) on the fast crop
    "hrrr": lambda lo, la: (lambda x, y: ((y - hy0) / 3000.0 - 584, (x - hx0) / 3000.0 - 0))(*hr(lo, la)),
    "ifs9": lambda lo, la: ((90.0 - la) / 0.1 - 310, np.mod(lo, 360.0) / 0.1 - 2150),
    "ifs":  lambda lo, la: ((90.0 - la) / 0.25 - 8, np.mod(lo, 360.0) / 0.25 - 600),
}
IMPACT = "/workspace/usa_alerts/impact.ttf"
for view in ("full", "west", "east"):
    d = f"{KIT}/{view}"; K = json.load(open(f"{d}/low.json")); nx, ny = K["nx"], K["ny"]
    L = np.fromfile(f"{d}/lut.bin", "<f4").reshape(ny, nx, 2); lon, lat = nbm_ll(L[..., 0], L[..., 1])
    lab = np.array([[q["fi"], q["fj"]] for q in K["labels"]]); llo, lla = nbm_ll(lab[:, 0], lab[:, 1])
    for m, f in MODELS.items():
        fi, fj = f(lon, lat); np.stack([fi, fj], -1).astype("<f4").tofile(f"{d}/lut_{m}.bin")
        a, b = f(llo, lla); json.dump([[round(float(x), 2), round(float(y), 2)] for x, y in zip(a, b)], open(f"{d}/lab_{m}.json", "w"), separators=(",", ":"))
    # plain overlay: in the scale / tag boxes, each row gets the row's own background (median of the overlay across the clean columns)
    o = np.asarray(Image.open(f"{d}/low_overlay.png")).copy(); H, W = o.shape[:2]
    rgb = o[:300, :, :3].astype(int); sat = (rgb.max(-1) - rgb.min(-1) > 60) & (o[:300, :, 3] > 40)
    sat[:100] = False; sat[:, :215] = False   # tag rows / logo columns
    ys, xs = np.nonzero(sat)
    bx0, bx1, by0, by1 = xs.min(), xs.max(), ys.min(), ys.max()
    if W > H:   # full state: scale centered under the title, clean columns both sides
        boxes = [(bx0 - 260, bx1 + 60, by0 - 50, by1 + 52, np.r_[260:bx0 - 300, bx1 + 100:W - 560])]
    else:       # portrait: scale runs to the right edge (label and "32" above it); the far right column is clean below the tag
        boxes = [(215, W, by0 - 45, by1 + 40, np.r_[W - 8:W - 2])]
    boxes.append((W - 520, W, 0, 96, np.r_[W - 600:W - 540]))
    for x0, x1, y0, y1, ref in boxes:
        for y in range(y0, y1):
            o[y, x0:x1] = np.median(o[y, ref], axis=0).astype(np.uint8)
    boxes = [b[:4] for b in boxes]
    Image.fromarray(o, "RGBA").save(f"{d}/plain_overlay.png", optimize=True)
    K2 = dict(scale=dict(x0=int(bx0), x1=int(bx1), y0=int(by0), y1=int(by1)), boxes=[list(map(int, b)) for b in boxes])
    # Impact titles at the size / position of the Phase 1 title (found by matching the rasterized Saturday low title)
    t = np.asarray(Image.open(f"{d}/titles/low_Saturday.png"))[..., 3]; tys, txs = np.nonzero(t > 128)
    tw = txs.max() - txs.min(); top = tys.min(); size = 40
    while size < 200:
        fo = ImageFont.truetype(IMPACT, size); bb = ImageDraw.Draw(Image.new("L", (10, 10))).textbbox((0, 0), "Saturday Predicted Low Temps", font=fo)
        if bb[2] - bb[0] >= tw - 8: break   # (shadow adds 8 px)
        size += 1
    for key, txt in (("precip", "Total Precipitation"), ("snow", "Total Snowfall")):
        fo = ImageFont.truetype(IMPACT, size); im = Image.new("RGBA", (W, t.shape[0]), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
        bb = dd.textbbox((0, 0), txt, font=fo); x = (W - (bb[2] - bb[0])) / 2 - bb[0]; y = top - bb[1]
        dd.text((x + 8, y + 8), txt, font=fo, fill=(0, 0, 0)); dd.text((x, y), txt, font=fo, fill=(255, 255, 255))
        im.save(f"{d}/titles/{key}.png", optimize=True)
    K2["title_px"] = size; json.dump(K2, open(f"{d}/totals.json", "w"))
    print(view, "scale box", K2["scale"], "title px", size)
