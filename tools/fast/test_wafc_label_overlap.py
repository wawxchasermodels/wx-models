#!/usr/bin/env python3
"""Fail if a wafc decimal-total value would overlap its town name or any other label.

Renders each view's plain overlay plus sample values placed with the same
metrics as wamaps.js (scanNameBoxes + decimalValueY + resolveDecimalTotals +
~2.5 CSS-px gap at a 1920-wide fit, scaled with DPR). Exits 1 on any
intersection so ship.sh can refuse the deploy.

Keep the scan / gap / 0.968 ascender / OTHER_INK constants in sync with wamaps.js.
"""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
KIT = HERE / "site" / "wamaps" / "kit"
MS_ASC = 0.968
OTHER_INK = 8
DESC_RE = re.compile(r"[gjpqy]")
CASES = (("precip", "10.75"), ("precip", "0.99"), ("snow", "12.5"), ("snod", "8.4"), ("kuchera", "6.2"))


def label_gap(W, H, dpr=1.0):
    fit = min(1920 / W, (1080 - 48) / H)
    return (2.5 * dpr) / (fit * dpr)


def montserrat_800():
    out = Path("/tmp/Montserrat-800-wafc.ttf")
    if not out.exists():
        src = "/usr/share/fonts/truetype/sand-box/google/Montserrat/Montserrat-VariableFont_wght.ttf"
        from fontTools.ttLib import TTFont
        from fontTools.varLib import instancer
        instancer.instantiateVariableFont(TTFont(src), {"wght": 800}).save(str(out))
    return str(out)


def font_at(size):
    return ImageFont.truetype(montserrat_800(), int(size))


def scan_name_box(a, L):
    H, W = a.shape[:2]
    fs = L["font"][1]
    name, name_sw = L["name"], max(0, L["sw"] - 1)
    nw = 0.62 * fs * max(1, len(name)) + 2 * name_sw + 8
    x0 = int(np.floor(L["x"] - nw / 2)); x1 = int(np.ceil(L["x"] + nw / 2))
    y0 = int(np.floor(L["y"] - fs * 1.7)); y1 = int(np.ceil(L["y"] + max(8, 0.32 * fs)))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(W, x1), min(H, y1)
    crop = a[y0:y1, x0:x1]
    white = (crop[..., 0] > 180) & (crop[..., 3] > 160)
    counts = white.sum(1)
    thresh = max(10, int(0.12 * (x1 - x0)))
    rows = np.where(counts >= thresh)[0]
    if len(rows) == 0:
        rows = np.where(counts >= max(4, thresh // 2))[0]
    if len(rows) == 0:
        return None
    runs, s, p = [], int(rows[0]), int(rows[0])
    for r in rows[1:]:
        r = int(r)
        if r > p + 2:
            runs.append((s, p)); s = r
        p = r
    runs.append((s, p))
    ey = (L["y"] - 0.5 * fs) - y0
    def score(run):
        cy = (run[0] + run[1]) / 2
        h = run[1] - run[0] + 1
        return abs(cy - ey) + (0 if 0.4 * fs <= h <= 1.45 * fs else 40)
    runs.sort(key=score)
    r0, r1 = runs[0]
    if DESC_RE.search(name):
        lim = min(white.shape[0] - 1, r1 + int(round(0.38 * fs)))
        r = r1 + 1
        while r <= lim:
            if counts[r] >= 2:
                r1 = r
            elif counts[r] == 0 and r + 1 <= lim and counts[r + 1] >= 2:
                pass
            else:
                break
            r += 1
    band = white[r0:r1 + 1]
    cols = np.where(band.any(0))[0]
    if len(cols) == 0:
        return None
    bx0 = max(0, x0 + int(cols[0]) - name_sw)
    by0 = max(0, y0 + int(r0) - name_sw)
    bx1 = min(W - 1, x0 + int(cols[-1]) + name_sw)
    by1 = min(H - 1, y0 + int(r1) + name_sw)
    ink = (a[by0:by1 + 1, bx0:bx1 + 1, 0] > 180) & (a[by0:by1 + 1, bx0:bx1 + 1, 3] > 160)
    return (bx0, by0, bx1, by1), ink


def text_ink(txt, size, sw):
    # Pillow 13 getbbox default/'la' is not baseline-relative; 'ls' matches JS measureText + stroke pad.
    bb = font_at(size).getbbox(txt, stroke_width=sw, anchor="ls")
    return {"ascent": -bb[1], "descent": bb[3], "left": -bb[0], "right": bb[2]}


def decimal_value_y(L, name_bottom, gap, ink):
    return name_bottom + gap + ink["ascent"] - MS_ASC * L["font"][1]


def value_box(L, vy, ink):
    yb = vy + MS_ASC * L["font"][1]
    x = L["x"]
    return (x - ink["left"], yb - ink["ascent"], x + ink["right"], yb + ink["descent"])


def hits(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def count_value_name_ink(L, vy, txt, ink, nbo, mask):
    vb = value_box(L, vy, ink)
    if not hits(vb, nbo):
        return 0
    x0, y0 = int(np.floor(vb[0])), int(np.floor(vb[1]))
    x1, y1 = int(np.ceil(vb[2])), int(np.ceil(vb[3]))
    w, h = max(1, x1 - x0), max(1, y1 - y0)
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    yb = vy + MS_ASC * L["font"][1] - y0
    d.text((L["x"] - x0, yb), txt, font=font_at(L["font"][1]), fill=(255, 255, 255, 255),
           stroke_width=L["sw"], stroke_fill=(14, 16, 22, 255), anchor="ms")
    vm = np.array(im)[..., 3] > 40
    nx0, ny0, nx1, ny1 = nbo
    ix0, iy0 = max(x0, nx0), max(y0, ny0)
    ix1, iy1 = min(x1 - 1, nx1), min(y1 - 1, ny1)
    if ix0 > ix1 or iy0 > iy1:
        return 0
    return int((vm[iy0 - y0:iy1 - y0 + 1, ix0 - x0:ix1 - x0 + 1] & mask[iy0 - ny0:iy1 - ny0 + 1, ix0 - nx0:ix1 - nx0 + 1]).sum())


def resolve_vy(L, nb, ink, gap, i, names, txt):
    desired = decimal_value_y(L, nb[3], gap, ink)
    min_y = decimal_value_y(L, nb[3], 0, ink)
    def hits_other(vy):
        for j, (_nj, nbo, mask) in enumerate(names):
            if j == i:
                continue
            if count_value_name_ink(L, vy, txt, ink, nbo, mask) > OTHER_INK:
                return True
        return False
    if not hits_other(desired):
        return desired
    vy = desired - 0.5
    while vy >= min_y:
        if not hits_other(vy):
            return vy
        vy -= 0.5
    return desired  # unfixable side clip: keep the measured gap


def draw_value(im, L, vy, txt):
    d = ImageDraw.Draw(im)
    yb = vy + MS_ASC * L["font"][1]
    d.text((L["x"], yb), txt, font=font_at(L["font"][1]), fill=(255, 255, 255, 255),
           stroke_width=L["sw"], stroke_fill=(14, 16, 22, 255), anchor="ms")


def check_view(view, txt):
    K = json.loads((KIT / view / "low.json").read_text())
    over = Image.open(KIT / view / "plain_overlay.png").convert("RGBA")
    a = np.array(over)
    H, W = a.shape[:2]
    gap = label_gap(K["W"], K["H"])
    names, missing = [], []
    raw = []
    for L in K["labels"]:
        scanned = scan_name_box(a, L)
        if scanned is None:
            missing.append(L["name"]); continue
        nb, mask = scanned
        raw.append((L, nb, mask))
        names.append((L["name"], nb, mask))
    errs = [f"{view}: could not measure name '{n}'" for n in missing]
    placed = []
    for i, (L, nb, mask) in enumerate(raw):
        ink = text_ink(txt, L["font"][1], L["sw"])
        vy = resolve_vy(L, nb, ink, gap, i, names, txt)
        vb = value_box(L, vy, ink)
        placed.append((L, vy, ink, vb, nb, mask))
        if hits(vb, nb):
            errs.append(f"{view}: {L['name']} value {tuple(round(x, 1) for x in vb)} overlaps its name {tuple(round(x, 1) for x in nb)}")

    # test render: draw every value, then require no ink overlap with own name,
    # other names, or other values (OTHER_INK fringe allowed only vs other names,
    # matching resolveDecimalTotals).
    val_im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for L, vy, ink, vb, nb, mask in placed:
        draw_value(val_im, L, vy, txt)
    va = np.array(val_im)
    val_mask = va[..., 3] > 40

    for i, (L, vy, ink, vb, nb, mask) in enumerate(placed):
        nx0, ny0, nx1, ny1 = nb
        ix0 = max(int(np.floor(vb[0])), nx0); iy0 = max(int(np.floor(vb[1])), ny0)
        ix1 = min(int(np.ceil(vb[2])) - 1, nx1); iy1 = min(int(np.ceil(vb[3])) - 1, ny1)
        if ix0 <= ix1 and iy0 <= iy1:
            pix = int((val_mask[iy0:iy1 + 1, ix0:ix1 + 1] & mask[iy0 - ny0:iy1 - ny0 + 1, ix0 - nx0:ix1 - nx0 + 1]).sum())
            if pix:
                errs.append(f"{view}: {L['name']} value ink overlaps its name ({pix} px)")
        for j, (nj, nbo, nmask) in enumerate(names):
            if j == i:
                continue
            ox0, oy0, ox1, oy1 = nbo
            ix0 = max(int(np.floor(vb[0])), ox0); iy0 = max(int(np.floor(vb[1])), oy0)
            ix1 = min(int(np.ceil(vb[2])) - 1, ox1); iy1 = min(int(np.ceil(vb[3])) - 1, oy1)
            if ix0 > ix1 or iy0 > iy1:
                continue
            pix = int((val_mask[iy0:iy1 + 1, ix0:ix1 + 1] & nmask[iy0 - oy0:iy1 - oy0 + 1, ix0 - ox0:ix1 - ox0 + 1]).sum())
            if pix > OTHER_INK:
                errs.append(f"{view}: {L['name']} value overlaps name '{nj}' ({pix} px)")
        for j in range(i + 1, len(placed)):
            Lj, vyj, inkj, vbj, nbj, maskj = placed[j]
            if not hits(vb, vbj):
                continue
            xx0 = max(int(np.floor(vb[0])), int(np.floor(vbj[0])))
            yy0 = max(int(np.floor(vb[1])), int(np.floor(vbj[1])))
            xx1 = min(int(np.ceil(vb[2])) - 1, int(np.ceil(vbj[2])) - 1)
            yy1 = min(int(np.ceil(vb[3])) - 1, int(np.ceil(vbj[3])) - 1)
            if xx0 > xx1 or yy0 > yy1:
                continue
            pix = int(val_mask[yy0:yy1 + 1, xx0:xx1 + 1].sum())
            if pix > OTHER_INK:
                errs.append(f"{view}: {L['name']} value overlaps value '{Lj['name']}' ({pix} px)")
    return errs, over, placed, gap, K


def render_debug(im, placed, txt, path):
    out = im.copy()
    for L, vy, ink, vb, nb, mask in placed:
        draw_value(out, L, vy, txt)
    out.save(path)


def main():
    if not KIT.is_dir():
        print("test_wafc_label_overlap: missing", KIT, file=sys.stderr); return 2
    js = (HERE / "site" / "wamaps.js").read_text()
    for needle in ("function scanNameBoxes", "function decimalValueY", "function labelGap",
                   "function resolveDecimalTotals", "function valueBox", "DEC_TOTALS", "OTHER_INK"):
        if needle not in js:
            print("test_wafc_label_overlap: wamaps.js missing", needle, file=sys.stderr); return 1
    if "L.y - Math.round((L.font[1] || 32) * 0.5)" in js:
        print("test_wafc_label_overlap: stale font-fraction shift still present", file=sys.stderr); return 1
    all_err = []
    first_fail_render = None
    n = 0
    for view in ("full", "west", "east"):
        for kind, txt in CASES:
            errs, im, placed, gap, K = check_view(view, txt)
            n += 1
            if errs and first_fail_render is None:
                out = Path("/tmp/wafc_label_overlap_fail.png")
                render_debug(im, placed, txt, out)
                first_fail_render = (view, kind, txt, str(out))
            all_err.extend(f"[{kind} '{txt}'] {e}" for e in errs)
    if all_err:
        print(f"test_wafc_label_overlap: FAIL {len(all_err)} overlap(s) in {n} renders", file=sys.stderr)
        for e in all_err[:40]:
            print(" ", e, file=sys.stderr)
        if len(all_err) > 40:
            print(f"  ... +{len(all_err) - 40} more", file=sys.stderr)
        if first_fail_render:
            print("  debug render", first_fail_render, file=sys.stderr)
        return 1
    print(f"test_wafc_label_overlap: ok ({n} renders, 3 views, no overlaps)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
