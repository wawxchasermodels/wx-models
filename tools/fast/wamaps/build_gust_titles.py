"""Studio / WA Maps gusts (11-04-26, t2310u): Impact titles "<Day> Predicted Max Wind Gusts" (gust_map.py wording) per view,
same size / position as build_totals_kit.py titles (sized to the Phase 1 low title). python3 build_gust_titles.py <site/wamaps/kit>"""
import sys, json, numpy as np
from PIL import Image, ImageDraw, ImageFont
KIT = sys.argv[1]; IMPACT = "/workspace/usa_alerts/impact.ttf"
for view in ("full", "west", "east"):
    d = f"{KIT}/{view}"; size = json.load(open(f"{d}/totals.json"))["title_px"]
    t = np.asarray(Image.open(f"{d}/titles/low_Saturday.png"))[..., 3]; tys, _ = np.nonzero(t > 128); top = tys.min(); W = t.shape[1]
    for day in ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"):
        txt = f"{day} Predicted Max Wind Gusts"; s = size
        while True:   # shrink to fit like gust_map's maxw (W - 600 full state, W - 80 portrait)
            fo = ImageFont.truetype(IMPACT, s); bb = ImageDraw.Draw(Image.new("L", (10, 10))).textbbox((0, 0), txt, font=fo)
            if bb[2] - bb[0] <= (W - 600 if W > t.shape[0] * 1.2 or view == "full" else W - 80) or s < 40: break
            s -= 2
        im = Image.new("RGBA", (W, t.shape[0]), (0, 0, 0, 0)); dd = ImageDraw.Draw(im)
        x = (W - (bb[2] - bb[0])) / 2 - bb[0]; y = top - bb[1]
        dd.text((x + 8, y + 8), txt, font=fo, fill=(0, 0, 0)); dd.text((x, y), txt, font=fo, fill=(255, 255, 255))
        im.save(f"{d}/titles/gust_{day}.png", optimize=True)
    print(view, size, s)
