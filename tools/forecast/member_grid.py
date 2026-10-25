"""Member-grid meteogram (10-25-26, Benjamin): one row per ensemble member with the value printed for every time column,
the control run as its own labelled row, and the ensemble mean as the last row. Drawn with PIL (fast, crisp numbers).

grid_png(path, title, sub, credit, cols, ctrl, M, fmt, cmap, unit, note)
  cols : list of (line1, line2) column header labels (e.g. ("Sun", "5 PM"))
  ctrl : control-run values per column (or None)
  M    : array (members, columns), member 1 first
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import house_style as HS

BG, PANEL, GRID, INK, MUTED, ACCENT = (21, 23, 28), (32, 35, 42), (58, 62, 70), (244, 242, 238), (167, 171, 179), (255, 201, 112)
CTRL_INK = (255, 201, 112)   # control row: accent colour + outline
_F = {}


def font(w, s):
    k = (w, s)
    if k not in _F:
        HS.font(w); _F[k] = ImageFont.truetype(HS._fp[w], s)
    return _F[k]


def _hex(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def shade(v, levels, colors):
    """Light cell fill for a value: the band colour mixed 55% into the panel so numbers stay readable."""
    if not np.isfinite(v): return PANEL
    i = int(np.searchsorted(levels, v, side="right")) - 1
    if i < 0: return PANEL
    c = _hex(colors[min(i, len(colors) - 1)])
    return tuple(int(PANEL[k] * 0.45 + c[k] * 0.55) for k in range(3))


def ink_for(bg):
    return (15, 16, 20) if (0.299 * bg[0] + 0.587 * bg[1] + 0.114 * bg[2]) > 150 else INK


def grid_png(path, title, sub, credit, cols, ctrl, M, fmt, levels, colors, unit, note, legend="", ctrl_label="CTRL", mean_label="MEAN"):
    """ctrl=None still draws the CTRL row, marked as not available, so the layout never changes."""
    nm, nc = M.shape
    cw = max(38, 9 + 8 * max(len(fmt(v)) for v in np.r_[M.ravel(), [0.0]] if np.isfinite(v)))
    if nc <= 14: cw = max(cw, int(max(font(700, 12).getlength(a) for a, _ in cols)) + 12)   # daily / 24 h grids: one day per column
    rh, lw, top, hh = 19, 74, 136, 40
    need = max(font(800, 28).getlength(title), font(700, 14).getlength(legend), font(500, 14).getlength(note), font(500, 13).getlength(credit)) + 56
    W = int(max(lw + nc * cw + 24, need)); rows = nm + 1 + 1
    H = top + hh + rows * rh + 10 + 8 + 48
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    d.rectangle([14, 16, 19, 116], fill=ACCENT)
    d.text((28, 12), title, font=font(800, 28), fill=INK)
    d.text((28, 52), sub, font=font(600, 16), fill=ACCENT)
    d.text((28, 78), note, font=font(500, 14), fill=MUTED)
    d.text((28, 100), legend, font=font(700, 14), fill=CTRL_INK)
    x0, y0 = lw, top
    fh = font(700, 12); fn = font(600, 12); fb = font(800, 12)
    for j, (a, b) in enumerate(cols):   # header: day on top, time below; a thin divider at each new day
        cx = x0 + j * cw + cw / 2
        run_ = 1
        while j + run_ < nc and cols[j + run_][0] == a: run_ += 1
        first = j == 0 or cols[j - 1][0] != a
        if first and (run_ * cw >= fh.getlength(a) + 6 or not b): d.text((x0 + j * cw + 3, y0 + 2), a, font=fh, fill=INK, anchor="la")
        d.text((cx, y0 + 20), b, font=font(500, 11), fill=MUTED, anchor="ma")
    d.text((lw - 8, y0 + 20), unit, font=font(700, 12), fill=ACCENT, anchor="ra")
    y = y0 + hh

    def row(label, vals, y, lab_fill, bold=False, outline=None):
        d.text((lw - 8, y + rh / 2), label, font=fb if bold else fn, fill=lab_fill, anchor="rm")
        for j, v in enumerate(vals):
            x = x0 + j * cw; bg = shade(v, levels, colors)
            d.rectangle([x, y, x + cw - 1, y + rh - 1], fill=bg)
            if np.isfinite(v): d.text((x + cw / 2, y + rh / 2), fmt(v), font=fb if bold else fn, fill=ink_for(bg), anchor="mm")
        if outline: d.rectangle([x0, y, x0 + nc * cw - 1, y + rh - 1], outline=outline, width=2)
        for j in range(1, nc):   # day dividers
            if cols[j][0] != cols[j - 1][0]: d.line([x0 + j * cw, y, x0 + j * cw, y + rh - 1], fill=GRID, width=1)
    if ctrl is not None:
        row(ctrl_label, ctrl, y, CTRL_INK, True, CTRL_INK)
    else:
        d.text((lw - 8, y + rh / 2), ctrl_label, font=fb, fill=CTRL_INK, anchor="rm")
        d.rectangle([x0, y, x0 + nc * cw - 1, y + rh - 1], fill=PANEL, outline=CTRL_INK, width=2)
        d.text((x0 + 10, y + rh / 2), "control run (member 0): not in this run's ECMWF open-data file", font=fn, fill=MUTED, anchor="lm")
    y += rh
    for m in range(nm):
        row(str(m + 1), M[m], y, MUTED); y += rh
        if (m + 1) % 10 == 0 and m + 1 < nm: d.line([x0, y - 1, x0 + nc * cw - 1, y - 1], fill=BG, width=2)   # every 10 rows, easier counting
    y += 8; d.line([x0, y - 5, x0 + nc * cw - 1, y - 5], fill=INK, width=2)
    allv = np.vstack([M] + ([np.asarray(ctrl, float)[None]] if ctrl is not None else []))
    mean = np.array([np.nanmean(c) if np.isfinite(c).any() else np.nan for c in allv.T])
    row(mean_label, mean, y, INK, True, INK); y += rh
    d.text((28, H - 30), credit, font=font(500, 13), fill=MUTED)
    im.save(path, optimize=True)
    return mean
