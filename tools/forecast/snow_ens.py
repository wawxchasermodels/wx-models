"""Ensemble snow-total meteogram (10-25-26, Benjamin): our own layout on the site's dark theme.

Top: one row per ENS member (1 at top), the run-total snow (10:1) printed in each 12 h column on the site's own
"glacier to ember" ramp, a CTRL row on top, then MEAN and the chance of reaching 1 / 3 / 6 / 12 inches.
Bottom: the 10-90% and 25-75% member ranges, mean, median and (when the file has it) the control run, on the same
columns as the grid. Drawn with PIL (grid) + matplotlib (bottom chart pasted in), one PNG per town.

snow_ens_png(path, title, sub, credit, T, steps, A, Ac=None)
  T, steps : valid times (UTC datetimes) and forecast hours of each row of A
  A        : (steps, members) run-total snow in inches, step 0 = 0
  Ac       : (steps,) control-run total or None
"""
import io
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageDraw
import house_style as HS
import member_grid as MG_
from meteograms import PT

BG, PANEL, GRID, INK, MUTED, ACCENT = MG_.BG, MG_.PANEL, MG_.GRID, MG_.INK, MG_.MUTED, MG_.ACCENT
font, ink_for = MG_.font, MG_.ink_for
hx = lambda c: "#%02x%02x%02x" % c   # matplotlib wants hex / 0-1 colours
# Site's own snow ramp (deep teal -> mint -> straw -> amber -> brick -> wine). Inches of snow, run total.
LEVELS = [0.1, 0.5, 1, 2, 3, 4, 6, 8, 10, 12, 15, 18, 24, 30, 36]
COLORS = ["#24414f", "#2b5d6b", "#2f7a80", "#33988c", "#4fb38a", "#82c97f", "#b6da75", "#e3e46b",
          "#f3cf57", "#f6ad45", "#f08a3a", "#e46536", "#cc4436", "#a82d3f", "#7d2140"]
THRESH = [1, 3, 6, 12]
BAND = "#4fb3a0"


def _hex(h): h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def fill(v):
    if not np.isfinite(v) or v < LEVELS[0]: return PANEL
    return _hex(COLORS[min(int(np.searchsorted(LEVELS, v, side="right")) - 1, len(COLORS) - 1)])


def fmt(v):
    if not np.isfinite(v) or v < LEVELS[0]: return ""
    return f"{v:.1f}" if v < 9.95 else f"{v:.0f}"


def snow_ens_png(path, title, sub, credit, T, steps, A, Ac=None, every=12):
    steps = list(steps); A = np.asarray(A, float)
    ci = [i for i, s in enumerate(steps) if s and s % every == 0]          # grid columns: every 12 h
    nc, nm = len(ci), A.shape[1]
    G = A[ci].T                                                            # (members, columns)
    gc = None if Ac is None or not np.isfinite(np.asarray(Ac, float)[ci]).any() else np.asarray(Ac, float)[ci]
    allv = G if gc is None else np.vstack([G, gc[None]])
    mean = np.nanmean(allv, 0)
    prob = [100 * np.mean(allv >= t, 0) for t in THRESH]
    lt = [T[i].astimezone(PT) for i in ci]
    cw, rh, lw = 40, 18, 86
    top, hh = 150, 38
    W = lw + nc * cw + 26
    chart_h = 330
    rows = 1 + nm + 1 + len(THRESH)
    gy0 = top + hh
    gy1 = gy0 + rows * rh + 3 * 6
    H = gy1 + 24 + chart_h + 44
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    # header (left accent rule, title, run line, notes) and a horizontal colour key at the right
    d.rectangle([14, 16, 19, 128], fill=ACCENT)
    d.text((28, 12), title, font=font(800, 28), fill=INK)
    d.text((28, 52), sub, font=font(600, 16), fill=ACCENT)
    d.text((28, 78), "Run-total snow at 10:1 from each member's snowfall (water equivalent x 10), inches, every 12 h", font=font(500, 14), fill=MUTED)
    d.text((28, 100), f"CTRL = control run  \u00b7  rows 1-{nm} = members  \u00b7  MEAN = ensemble mean  \u00b7  \u2265 rows = % of members at or above",
           font=font(700, 13), fill=ACCENT)
    kx, ky, kw = W - 22 - len(LEVELS) * 30, 124, 30
    for k, (lv, col) in enumerate(zip(LEVELS, COLORS)):
        d.rectangle([kx + k * kw, ky, kx + (k + 1) * kw - 2, ky + 12], fill=_hex(col))
        d.text((kx + k * kw, ky - 3), (f"{lv:g}" if lv >= 1 else f"{lv:.1f}".lstrip("0")), font=font(600, 11), fill=MUTED, anchor="lb")
    d.text((kx - 6, ky + 6), "in", font=font(700, 12), fill=ACCENT, anchor="rm")
    x0 = lw
    # column headers: PT day once per day, local time under each column
    for j, t in enumerate(lt):
        run_ = sum(1 for u in lt[j:] if u.date() == t.date())
        if (j == 0 or lt[j - 1].date() != t.date()) and run_ * cw >= font(700, 12).getlength(f"{t:%a %-m/%-d}") + 4:
            d.text((x0 + j * cw + 3, top + 2), f"{t:%a %-m/%-d}", font=font(700, 12), fill=INK)
        d.text((x0 + j * cw + cw / 2, top + 20), f"{t:%-I%p}".lower(), font=font(500, 11), fill=MUTED, anchor="ma")
    d.text((lw - 8, top + 20), "inches", font=font(700, 12), fill=ACCENT, anchor="ra")
    newday = [j for j in range(1, nc) if lt[j].date() != lt[j - 1].date()]

    def row(label, vals, y, lab, bold=False, outline=None, txt=fmt, col=fill):
        d.text((lw - 8, y + rh / 2), label, font=font(800 if bold else 600, 12), fill=lab, anchor="rm")
        for j, v in enumerate(vals):
            x = x0 + j * cw; bg = col(v)
            d.rectangle([x + 1, y + 1, x + cw - 2, y + rh - 2], fill=bg)   # 1 px gutters: tiles, not a solid band
            s = txt(v)
            if s: d.text((x + cw / 2, y + rh / 2), s, font=font(800 if bold else 600, 11), fill=ink_for(bg), anchor="mm")
        if outline: d.rectangle([x0, y, x0 + nc * cw - 1, y + rh - 1], outline=outline, width=2)
        for j in newday: d.line([x0 + j * cw, y, x0 + j * cw, y + rh - 1], fill=INK if bold else GRID, width=1)

    y = gy0
    if gc is not None: row("CTRL", gc, y, ACCENT, True, ACCENT)
    else:
        d.text((lw - 8, y + rh / 2), "CTRL", font=font(800, 12), fill=ACCENT, anchor="rm")
        d.rectangle([x0, y, x0 + nc * cw - 1, y + rh - 1], fill=PANEL, outline=ACCENT, width=2)
        d.text((x0 + 10, y + rh / 2), "control run: not in this run's ECMWF open-data file (snowfall is published for the 50 members only)",
               font=font(600, 11), fill=MUTED, anchor="lm")
    y += rh + 6
    for m in range(nm):
        row(f"{m + 1}", G[m], y, MUTED); y += rh
        if (m + 1) % 10 == 0 and m + 1 < nm: d.line([x0, y, x0 + nc * cw - 1, y], fill=BG, width=3)
    y += 6
    row("MEAN", mean, y, INK, True, INK); y += rh + 6
    pcol = lambda p: PANEL if not p else tuple(int(PANEL[k] + (_hex("#9fb4ff")[k] - PANEL[k]) * (0.25 + 0.75 * p / 100)) for k in range(3))
    for t_, p in zip(THRESH, prob):
        row(f"\u2265 {t_} in", p, y, "#b8c6ff", False, None, lambda v: f"{v:.0f}%" if v else "", pcol); y += rh

    # bottom chart on the same columns (x = column index; 6 h steps fall between columns)
    xs = np.array([(s - every) / every for s in steps])
    k = xs >= -1
    q = np.nanpercentile(A, [10, 25, 50, 75, 90], 1)
    dpi = 100
    fig = plt.figure(figsize=(W / dpi, chart_h / dpi), dpi=dpi); fig.patch.set_facecolor(hx(BG))
    ax = fig.add_axes([(x0 - cw / 2) / W, 0.13, ((nc + 0.5) * cw) / W, 0.80]); ax.set_facecolor(hx(PANEL))   # x = column index, columns line up with the grid
    ax.fill_between(xs[k], q[0][k], q[4][k], color=BAND, alpha=0.22, lw=0, label="10-90% of members")
    ax.fill_between(xs[k], q[1][k], q[3][k], color=BAND, alpha=0.45, lw=0, label="25-75%")
    ax.plot(xs[k], q[2][k], color=BAND, lw=2, label=f"Median  {q[2][-1]:.1f} in")
    mu = np.nanmean(A, 1)
    ax.plot(xs[k], mu[k], color=hx(INK), lw=2.6, label=f"Mean  {mu[-1]:.1f} in")
    if gc is not None:
        ac = np.asarray(Ac, float); ax.plot(xs[k], ac[k], color=hx(ACCENT), lw=2, ls=(0, (5, 3)), label=f"Control  {ac[-1]:.1f} in")
    ax.plot(xs[k], q[4][k], color=BAND, lw=0.8, alpha=0.8)
    ax.set_xlim(-1.0, nc - 0.5)
    ax.set_ylim(0, max(1.0, float(np.nanmax(q[4])) * 1.12))
    for j in newday: ax.axvline(j - 0.5, color=hx(GRID), lw=0.8)
    ax.grid(axis="y", color=hx(GRID), lw=0.7)
    tj = ([0] if (newday[0] if newday else nc) >= 2 else []) + newday
    ax.set_xticks([j - 0.5 for j in tj]); ax.set_xticklabels([f"{lt[j]:%a %-d}" for j in tj], ha="left")
    ax.tick_params(colors=hx(MUTED), labelsize=9, length=0)
    for lab in ax.get_xticklabels(): lab.set_fontproperties(HS.font(600, 9))
    for s_ in ax.spines.values(): s_.set_color(hx(GRID))
    ax.set_ylabel("inches (10:1)", color=hx(INK), fontproperties=HS.font(600, 10))
    ax.legend(loc="upper left", facecolor=hx(BG), edgecolor=hx(GRID), labelcolor=hx(INK), fontsize=9, ncol=5, frameon=True)
    buf = io.BytesIO(); fig.savefig(buf, format="png", facecolor=hx(BG)); plt.close(fig); buf.seek(0)
    ch = Image.open(buf).convert("RGB")
    d.text((28, gy1 + 4), "Member spread", font=font(800, 15), fill=INK)
    im.paste(ch, (0, gy1 + 24))
    d.text((28, H - 30), credit, font=font(500, 13), fill=MUTED)
    im.save(path, optimize=True)
    return mean
