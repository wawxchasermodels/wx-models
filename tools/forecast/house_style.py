#!/usr/bin/env python3
"""Shared look for the wx-models forecast charts (AIFS maps, meteograms).

Charcoal canvas, Montserrat type (SIL OFL, committed in tools/wa_maps/assets/fonts), a header with the product
name, the valid time in PT as the second-largest line, and a forecast-hour badge on the right; the map sits in a
thin framed panel under a wide color key that sits directly below the header; coastlines and borders are dark lines on a light
halo and contour labels carry halos, so they stay readable over any fill. Part of wx-models (MIT)."""
import os
import matplotlib.patheffects as pe
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_SRC = os.environ.get("WX_FONT_BODY", os.path.normpath(os.path.join(HERE, "..", "wa_maps", "assets", "fonts", "Montserrat.ttf")))
CACHE = os.path.join(os.environ.get("WX_CACHE", os.path.join(os.path.expanduser("~"), ".cache", "wx-models")), "fonts")

BG = "#15171c"        # canvas
PANEL_EDGE = "#7d828c"
INK = "#f4f2ee"
MUTED = "#a7abb3"
ACCENT = "#ffc970"    # valid time
BADGE = "#262931"
COAST_DARK, COAST_HALO = "#121317", (1, 1, 1, 0.55)

_fp = {}


def font(weight=500, size=12):
    """FontProperties for a static Montserrat instance (made once from the variable font with fontTools)."""
    if weight not in _fp:
        path = os.path.join(CACHE, f"Montserrat-w{weight}.ttf")
        if not os.path.exists(path):
            from fontTools.ttLib import TTFont
            from fontTools.varLib.instancer import instantiateVariableFont
            os.makedirs(CACHE, exist_ok=True)
            f = instantiateVariableFont(TTFont(FONT_SRC), {"wght": weight})
            f["name"].setName(f"Montserrat W{weight}", 1, 3, 1, 0x409)
            f.save(path)
        font_manager.fontManager.addfont(path)
        _fp[weight] = path
    return font_manager.FontProperties(fname=_fp[weight], size=size)


def use_for_plots():
    """Montserrat as the default matplotlib font (tick labels, legends, axis labels)."""
    import matplotlib as mpl
    font(500); font(700)
    name = font_manager.FontProperties(fname=_fp[500]).get_name()
    mpl.rcParams["font.family"] = name


def halo(color="white", width=3.0):
    return [pe.withStroke(linewidth=width, foreground=color)]


def header(fig, title, valid, sub, badge_top, badge_bottom, top=0.985, h=0.095):
    """Header: accent rule + title, valid time line, small run line; forecast-hour badge at the right."""
    W, H = fig.get_size_inches()
    fig.patches.append(FancyBboxPatch((0.012, top - h + 0.008), 0.0045, h - 0.016, boxstyle="square,pad=0",
                                      transform=fig.transFigure, color=ACCENT, zorder=5))
    x = 0.024
    fig.text(x, top - 0.004, title, color=INK, fontproperties=font(800, 25), va="top")
    fig.text(x, top - 0.040 * 12 / H, valid, color=ACCENT, fontproperties=font(700, 18), va="top")
    fig.text(x, top - 0.068 * 12 / H, sub, color=MUTED, fontproperties=font(500, 12.5), va="top")
    bw, bh = 0.118, h - 0.012
    fig.patches.append(FancyBboxPatch((0.988 - bw, top - bh), bw, bh, boxstyle="round,pad=0,rounding_size=0.012",
                                      transform=fig.transFigure, facecolor=BADGE, edgecolor=PANEL_EDGE, lw=1.0, zorder=5,
                                      mutation_aspect=W / H))
    fig.text(0.988 - bw / 2, top - bh * 0.40, badge_top, color=INK, fontproperties=font(800, 26), ha="center", va="center", zorder=6)
    fig.text(0.988 - bw / 2, top - bh * 0.80, badge_bottom, color=MUTED, fontproperties=font(600, 10.5), ha="center", va="center", zorder=6)


def frame(ax):
    """Thin light frame around the map panel."""
    for s in ax.spines.values():
        s.set_edgecolor(PANEL_EDGE); s.set_linewidth(1.1)
    if hasattr(ax, "outline_patch"):
        ax.outline_patch.set_edgecolor(PANEL_EDGE)


def outlines(ax, cf, res="50m", states=True):
    """Coastlines and borders: dark line over a soft light halo, readable over dark and light fills."""
    feats = [(cf.NaturalEarthFeature("physical", "coastline", res), 1.0),
             (cf.NaturalEarthFeature("cultural", "admin_0_boundary_lines_land", res), 0.9)]
    if states:
        feats.append((cf.NaturalEarthFeature("cultural", "admin_1_states_provinces_lines", res), 0.5))
    for f, lw in feats:
        ax.add_feature(f, facecolor="none", edgecolor=COAST_HALO, lw=lw + 1.4, zorder=3)
    for f, lw in feats:
        ax.add_feature(f, facecolor="none", edgecolor=COAST_DARK, lw=lw, zorder=3.1)


def vbar(fig, mappable, ticks, title, rect=(0.052, 0.095, 0.022, 0.72), note=None):
    """Tall vertical color key on the LEFT of the map (labels outside, on its left), one label per bin edge."""
    cax = fig.add_axes(list(rect))
    cb = fig.colorbar(mappable, cax=cax, orientation="vertical", ticks=ticks, extendfrac=0.035)
    cb.outline.set_edgecolor(PANEL_EDGE); cb.outline.set_linewidth(1.0)
    cax.yaxis.set_ticks_position("left"); cax.yaxis.set_label_position("left")
    cax.tick_params(colors=INK, length=5, width=1, pad=4)
    cax.set_yticklabels([f"{t:+d}" if t else "0" for t in ticks], fontproperties=font(700, 12.5))
    fig.text(rect[0] + rect[2] / 2, rect[1] + rect[3] + 0.028, title, color=INK, fontproperties=font(700, 13),
             ha="center", va="bottom")
    if note:
        fig.text(rect[0] + rect[2] / 2, rect[1] - 0.030, note, color=MUTED, fontproperties=font(600, 10.5), ha="center", va="top")
    return cb


def credit(fig, text, y=0.012):
    fig.text(0.024, y, text, color=MUTED, fontproperties=font(500, 9.5), va="bottom")


def layout(fig, key=True):
    """Figure fractions (key_y, map_top) for: header, then (optionally) the color key band, then the map."""
    H = fig.get_size_inches()[1]
    header_bottom = 0.985 - 1.16 / H
    if not key:
        return None, header_bottom - 0.10 / H
    key_y = header_bottom - 0.16 / H - 0.27 / H
    return key_y, key_y - 0.50 / H


def hbar(fig, mappable, ticks, title, y, x0=0.150, x1=0.976, signed=False):
    """Wide horizontal color key directly under the header: units title on its left, a label on every bin edge below."""
    H = fig.get_size_inches()[1]; h = 0.27 / H
    cax = fig.add_axes([x0, y, x1 - x0, h])
    cb = fig.colorbar(mappable, cax=cax, orientation="horizontal", ticks=ticks, extendfrac=0.022)
    cb.outline.set_edgecolor(PANEL_EDGE); cb.outline.set_linewidth(1.0)
    cax.tick_params(colors=INK, length=5, width=1, pad=3)
    cax.set_xticklabels([(f"{t:+d}" if t else "0") if signed else f"{t:d}" for t in ticks], fontproperties=font(700, BAR_LABEL_SIZE))
    fig.text(0.024, y + h / 2, title, color=INK, fontproperties=font(700, 13.5), ha="left", va="center")
    return cb


# ---------------------------------------------------------------------------------------------------------------
# Shared scales: the single source of truth for every model (AIFS, GFS, GEFS, EPS, HRRR, RRFS ...). See STYLE_RULES.md.
# ---------------------------------------------------------------------------------------------------------------
import numpy as _np


def smooth(vals, anchor_vals, anchor_cols):
    """Linear RGB interpolation of anchor colors at the given values (clamped at the ends)."""
    from matplotlib.colors import to_rgb, to_hex
    A = _np.array([to_rgb(c) for c in anchor_cols])
    return [to_hex([_np.interp(v, anchor_vals, A[:, k]) for k in range(3)]) for v in vals]


# 500 mb height anomaly, meters: -450..+450, 12 m bins (75), neutral -18..+18, extend arrows beyond.
# Color order: gray > green > indigo/purple > blue toward zero; pale yellow > yellow > orange > red > crimson > magenta
# > pink > mauve/light purple at the top. Anchors are 36 m bin colors; interpolation stays inside each color family.
ANOM_ANCHORS = [
    "#d6d6d8", "#b4b4b8", "#8f9095",                          # -450..-342 grays
    "#1f5e2c", "#2f7d3a", "#4f9e4c", "#80c06e", "#b5dc9c",    # -342..-162 greens
    "#6a4fae", "#3f3fb8", "#3570d6", "#87b9ee",               # -162..-18 indigo, blue, light blue
    "#f7f7f5",                                                # -18..+18 neutral
    "#fdf2b0", "#fbe066", "#f6bf37", "#f19435", "#e9612c",    # +18..+198 pale yellow to orange-red
    "#d9332b", "#b8172f", "#c41a63", "#d6338f",               # +198..+342 red, crimson, magenta
    "#e070b6", "#cf94c9", "#c3aed8",                          # +342..+450 pink, mauve, light purple
]
ANOM_LEVELS = _np.arange(-450, 451, 12)
ANOM_UNDER, ANOM_OVER = "#ececee", "#ddd0ea"
ANOM_TICKS = [-450, -378, -306, -234, -162, -90, 0, 90, 162, 234, 306, 378, 450]  # every 72 m from each end + 0
_NEG_V, _POS_V = _np.arange(-432, -35, 36), _np.arange(36, 433, 36)
_FAM = [(0, 3), (3, 8), (8, 12)]


def _anom_color(m):
    if abs(m) < 18: return ANOM_ANCHORS[12]
    if m > 0: return smooth([m], _POS_V, ANOM_ANCHORS[13:])[0]
    k = min(11, int((m + 450) // 36)); a, b = next(f for f in _FAM if f[0] <= k < f[1])
    return smooth([m], _NEG_V[a:b], ANOM_ANCHORS[a:b])[0]


ANOM_COLORS = [_anom_color(m) for m in (ANOM_LEVELS[:-1] + ANOM_LEVELS[1:]) / 2.0]

# Sea-level pressure, mb: 900..1060, 2 mb bins (80). Near-black violet at 900 > dark magenta > deep purple > purples/blues
# > teal > saturated greens > pale neutral 1012-1018 > yellow > orange > red > dark red at 1060.
MSLP_ANCHORS = [(900, "#140317"), (925, "#33083a"), (945, "#4a0d52"), (960, "#36125f"), (972, "#3b1a5a"), (976, "#4b2580"),
                (980, "#4a3aa6"), (984, "#3f56c2"), (988, "#3a76d0"), (992, "#4596d6"), (996, "#47b0d6"), (1000, "#25b5a3"),
                (1004, "#2fbf6c"), (1008, "#5ccb3a"), (1012, "#b6df63"), (1016, "#ecebd9"), (1020, "#f6e3a1"),
                (1024, "#f5cd6b"), (1028, "#f0ac4b"), (1032, "#e88a3c"), (1036, "#dc6634"), (1040, "#c9432f"),
                (1044, "#a9282f"), (1048, "#7e1a2d"), (1054, "#5c1024"), (1060, "#3f0a18")]
MSLP_LEVELS = _np.arange(900, 1061, 2)
MSLP_COLORS = smooth((MSLP_LEVELS[:-1] + MSLP_LEVELS[1:]) / 2.0, [v for v, _ in MSLP_ANCHORS], [c for _, c in MSLP_ANCHORS])
MSLP_UNDER, MSLP_OVER = "#0a0110", "#2e0711"
MSLP_TICKS = list(range(900, 1061, 10))

# Pressure-center markers (H blue, L red) and their central-pressure label.
HL_SIZE, HL_VALUE_SIZE, HL_VALUE_OFFSET = 16, 6, -12.5   # pt, pt, points below the letter
HL_HALO, HL_VALUE_HALO = 2.0, 1.2
H_COLOR, L_COLOR = "#1747c9", "#d7191c"
BAR_LABEL_SIZE = 15                                      # color key tick labels, pt


def cmap(colors, under, over):
    from matplotlib.colors import ListedColormap
    cm = ListedColormap(colors); cm.set_under(under); cm.set_over(over)
    return cm


def anom_cmap():
    return cmap(ANOM_COLORS, ANOM_UNDER, ANOM_OVER)


def mslp_cmap():
    return cmap(MSLP_COLORS, MSLP_UNDER, MSLP_OVER)

# H / L center detection: neighborhood extremum over a radius (km) per view, with a prominence test against the ring
# at that radius, so flat areas get no labels. Centers may sit near the frame edge as long as the center is in view.
HL_RADIUS_KM = {"na": 800, "pnw": 400}
HL_PROMINENCE_MB = {"na": 3.0, "pnw": 2.0}
HL_EDGE_KM = {"na": 500, "pnw": 450}  # a center just outside the frame (closed isobars reaching into view) is pinned to the edge
HL_LABEL_CLEARANCE = 6   # px of padding around an H/L marker box where isobar labels are removed


def find_centers(S, lat, lon, radius_km, prom, inside):
    """Return [(i, j, 'H'|'L')] on a regular lat/lon grid. S: smoothed field (lat x lon). inside(i, j) -> bool."""
    from scipy.ndimage import maximum_filter, minimum_filter
    dlat = abs(float(lat[1] - lat[0])); dlon = abs(float(lon[1] - lon[0]))
    ry = max(2, int(round(radius_km / (111.2 * dlat))))
    coslat = max(0.25, float(_np.cos(_np.radians(_np.mean(lat)))))
    rx = max(2, int(round(radius_km / (111.2 * dlon * coslat))))
    th = _np.linspace(0, 2 * _np.pi, 48, endpoint=False)
    out = []
    for f, ch, sgn in ((maximum_filter, "H", 1), (minimum_filter, "L", -1)):
        ext = S == f(S, size=(2 * ry + 1, 2 * rx + 1), mode="constant", cval=-sgn * 1e9)
        cand = sorted(zip(*_np.nonzero(ext)), key=lambda ij: -sgn * S[ij])
        placed = []
        for i, j in cand:
            if not inside(i, j):
                continue
            cl = max(0.25, float(_np.cos(_np.radians(lat[i]))))
            ii = _np.round(i + ry * _np.sin(th)).astype(int)
            jj = _np.round(j + rx * coslat / cl * _np.cos(th)).astype(int)
            ok = (ii >= 0) & (ii < S.shape[0]) & (jj >= 0) & (jj < S.shape[1])
            if ok.mean() < 0.6:
                continue                        # too little of the surrounding ring is in the data to call it closed
            ring = S[ii[ok], jj[ok]]
            # prominence: the field must drop (rise) by >= prom from the center to the median of the ring at the radius
            if sgn * (S[i, j] - _np.median(ring)) < prom:
                continue
            if any((i - a) ** 2 / ry ** 2 + (j - b) ** 2 / rx ** 2 < 1 for a, b in placed):
                continue
            placed.append((i, j)); out.append((i, j, ch))
    return out


def km_between(lat1, lon1, lat2, lon2):
    p1, p2, dl = _np.radians(lat1), _np.radians(lat2), _np.radians(lon2 - lon1)
    return 6371.0 * _np.arccos(_np.clip(_np.sin(p1) * _np.sin(p2) + _np.cos(p1) * _np.cos(p2) * _np.cos(dl), -1, 1))


def clear_labels_near(fig, labels, markers, pad=HL_LABEL_CLEARANCE):
    """Remove contour-label texts whose box overlaps any H/L marker artist (letter or central-pressure text)."""
    r = fig.canvas.get_renderer()
    boxes = [m.get_window_extent(r).expanded(1, 1).padded(pad) for m in markers]
    n = 0
    for t in list(labels):
        if t.axes is None:
            continue
        bb = t.get_window_extent(r)
        if any(bb.overlaps(b) for b in boxes):
            t.remove(); n += 1
    return n


# 10 m wind speed (mph), shared by every model's wind maps: 0..100 mph in 2 mph bins (50 colors), extend arrow above 100.
# Calm slate/near-white for light winds, steel blue > teal > sea green > lime > yellow > amber > orange > red > rose > plum
# > violet > deep indigo for strong winds; pale orchid above 100 mph.
WIND_ANCHORS = [(0, "#eef0f2"), (6, "#d3dbe4"), (12, "#a8c3d6"), (18, "#6eaec8"), (24, "#3e9f93"), (30, "#86c241"),
                (36, "#e3d63b"), (42, "#f3a83b"), (50, "#eb692d"), (58, "#d6322b"), (66, "#ae1449"), (75, "#881d7b"),
                (85, "#5a2b9a"), (100, "#2b1c5d")]
WIND_LEVELS = _np.arange(0, 101, 2)
WIND_COLORS = smooth((WIND_LEVELS[:-1] + WIND_LEVELS[1:]) / 2.0, [v for v, _ in WIND_ANCHORS], [c for _, c in WIND_ANCHORS])
WIND_UNDER, WIND_OVER = "#eef0f2", "#f1cdf5"
WIND_TICKS = list(range(0, 101, 10))
# Wind barbs: knots, thinned to about this many barbs across the view width (fewer per area on continental views).
BARBS_ACROSS = {"pnw": 20, "na": 24}
BARB_COLOR, BARB_LENGTH, BARB_LW = "#16181d", 5.6, 0.75
# Isobars over a color fill: dark line on a thin white halo.
ISOBAR_COLOR, ISOBAR_LW, ISOBAR_HALO = "#15171c", 1.15, 2.4


def wind_cmap():
    return cmap(WIND_COLORS, WIND_UNDER, WIND_OVER)

# Temperature (deg F), shared by every 2 m temperature map: -40..120 F in 2 F bins (80 colors), extend arrows both ends.
# Original palette: pale lilac / violet / indigo for extreme cold > royal blue > sky blue > icy pale blue just below
# freezing, then a hard break at 32 F to forest green > green > yellow-green > yellow > amber > orange > red > dark
# crimson > wine, and orchid / pale pink for extreme heat. The 32 F break is a bin edge, so frozen vs not is unambiguous.
TEMP_ANCHORS = [(-40, "#efe2f6"), (-30, "#cfa9e3"), (-20, "#a274cb"), (-10, "#7046ad"), (0, "#43339c"), (10, "#2a58bb"),
                (20, "#3d8fd5"), (27, "#82c5ea"), (31, "#d3eef8"), (33, "#2d8659"), (40, "#4fa957"), (48, "#93c84d"),
                (56, "#dcdc55"), (63, "#f4c64a"), (70, "#f19c3a"), (78, "#e5692e"), (86, "#cf3d2a"), (94, "#a6202f"),
                (102, "#771238"), (110, "#a8468a"), (120, "#e6b2d6")]
TEMP_LEVELS = _np.arange(-40, 121, 2)


def temp_color(f):
    """Color for a temperature in deg F (also used for 850 mb maps in deg C, converted, so equal temps look equal)."""
    return smooth([f], [v for v, _ in TEMP_ANCHORS], [c for _, c in TEMP_ANCHORS])[0]


TEMP_COLORS = [temp_color(v) for v in (TEMP_LEVELS[:-1] + TEMP_LEVELS[1:]) / 2.0]
TEMP_UNDER, TEMP_OVER = "#ffffff", "#f6dcef"
TEMP_TICKS = list(range(-40, 121, 10))
# 850 mb temperature (deg C): -40..+30 C in 1 C bins; colors are TEMP colors at the same temperature in F; 0 C = 32 F break.
T850_LEVELS = _np.arange(-40, 31, 1)
T850_COLORS = [temp_color(c * 1.8 + 32) for c in (T850_LEVELS[:-1] + T850_LEVELS[1:]) / 2.0]
T850_TICKS = list(range(-40, 31, 5))
FREEZE_COLOR, FREEZE_LW = "#0b1f4d", 1.6               # 32 F / 0 C line, dashed, on a thin white halo
BARBS_ACROSS.setdefault("wa", 18)


def temp_cmap():
    return cmap(TEMP_COLORS, TEMP_UNDER, TEMP_OVER)


def t850_cmap():
    return cmap(T850_COLORS, temp_color(-40 * 1.8 + 32), temp_color(30 * 1.8 + 32))


# ---- Rain / QPF totals (inches). Same scale as tools/wa_maps/precip_map.py (PEDGES/PCOLS): under 0.01 no fill,
# 0.01-0.10 pale, a new color every 0.10 in from 0.10 to 4.00 (greens > yellows > oranges > reds), every 0.50 in from 4 to 12, 12+ white.
RAIN_LEVELS = _np.array([0.01] + [round(0.1 * k, 2) for k in range(1, 41)] + [round(4 + 0.5 * k, 2) for k in range(1, 17)])
_RAIN_ANCH = [(0.01, (215, 245, 205)), (0.10, (180, 232, 165)), (0.30, (130, 208, 110)), (0.50, (75, 178, 78)), (0.70, (35, 138, 55)), (0.90, (15, 95, 42)),
              (1.00, (250, 240, 150)), (1.25, (250, 225, 60)), (1.50, (250, 200, 50)), (1.75, (250, 175, 45)), (2.25, (245, 135, 40)), (2.75, (235, 100, 35)),
              (3.00, (220, 50, 40)), (3.30, (190, 30, 35)), (3.60, (155, 18, 35)), (3.90, (120, 10, 40)),
              (4.00, (225, 65, 175)), (5.50, (170, 50, 195)), (7.00, (110, 40, 160)), (8.50, (150, 115, 215)), (10.0, (190, 170, 235)), (11.5, (230, 222, 250)), (12.0, (255, 255, 255))]


def rain_color(v):
    """RGB hex at v inches (linear blend between anchors); bins use the color at their lower edge."""
    a = [x for x, _ in _RAIN_ANCH]; c = _np.array([col for _, col in _RAIN_ANCH], float)
    rgb = [int(round(_np.interp(min(max(v, a[0]), a[-1]), a, c[:, k]))) for k in range(3)]
    return "#%02x%02x%02x" % tuple(rgb)


RAIN_COLORS = [rain_color(v) for v in RAIN_LEVELS[:-1]]
RAIN_OVER = rain_color(12.0)
RAIN_TICKS = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 5, 6, 7, 8, 9, 10, 11, 12]   # key labels every 0.5 in to 4, every 1 in above


def rain_cmap():
    return cmap(RAIN_COLORS, (0, 0, 0, 0), RAIN_OVER)

# ---- MSLP + precipitation (period QPF by precipitation type, inches liquid equivalent). Rain uses the RAIN scale above
# (same colors at the same depth). Snow and mix get their own short original ramps on the same bin edges up to 2 in:
# snow = pale ice blue > sky blue > royal blue > deep indigo; mix = pale lilac-pink > orchid > plum. Freezing rain /
# sleet is hatched over the fill. Type comes from the snowfall share of the period total (>= 70 % snow, 30-70 % mix).
PTYPE_LEVELS = _np.array([0.01, 0.05, 0.10, 0.20, 0.30, 0.50, 0.75, 1.00, 1.50, 2.00])
SNOW_COLORS = smooth(range(9), [0, 3, 6, 8], ["#dcefff", "#7fb9f0", "#2f63c9", "#1d1f7a"])
MIX_COLORS = smooth(range(9), [0, 4, 8], ["#f6dcf2", "#d77fd0", "#7d2a8a"])
PTYPE_TICKS = [0.1, 0.5, 1, 2]
SNOW_SHARE, MIX_SHARE = 0.70, 0.30
ICE_HATCH, ICE_HATCH_COLOR = "////", "#5a0f1e"
QPF_LAND, QPF_SEA = "#f1efea", "#dfe7ee"            # basemap tint under the precip fill
QPF_RAIN_MAX = 4.0                                    # rain key on these maps stops at 4 in (extend arrow above)
HL_RADIUS_KM.setdefault("wa", 250); HL_PROMINENCE_MB.setdefault("wa", 1.5); HL_EDGE_KM.setdefault("wa", 200)


def snow_cmap():
    return cmap(SNOW_COLORS, (0, 0, 0, 0), SNOW_COLORS[-1])


def mix_cmap():
    return cmap(MIX_COLORS, (0, 0, 0, 0), MIX_COLORS[-1])
