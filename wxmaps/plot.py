"""Draw one chart plate. Wide is 1600×900, reel is 900×1600."""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import patheffects
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from PIL import Image

from wxmaps.attribution import ecmwf_plate_credit, noaa_plate_credit
from wxmaps.brand import site_name
from wxmaps.derive import Payload
from wxmaps.geo import cities, visible
from wxmaps.models import REGIONS
from wxmaps.palette import PTYPE_COLORS, SCALES

PACIFIC = ZoneInfo("America/Los_Angeles")
DAYS = "Mon Tue Wed Thu Fri Sat Sun".split()
PAPER = "#d4c8b4"
FRAME = "#c9bba6"
INK = "#241c16"
BRASS = "#9a6232"
VERMILION = "#d24b2e"
WATER = "#a7bfc6"
HALO = "#f6f3ec"

_FONTS: dict[str, matplotlib.font_manager.FontProperties] | None = None


def _instance(src: Path, location: dict[str, float]) -> Path:
    """Bake one named instance into a temp file. The repo keeps the upstream font."""
    import tempfile

    from fontTools.ttLib import TTFont
    from fontTools.varLib.instancer import instantiateVariableFont

    dest = Path(tempfile.gettempdir()) / "wxmaps-fonts" / f"{src.stem}-{'-'.join(str(int(v)) for v in location.values())}.ttf"
    if not dest.exists() or dest.stat().st_mtime < src.stat().st_mtime:
        dest.parent.mkdir(parents=True, exist_ok=True)
        instantiateVariableFont(TTFont(src), location, inplace=False).save(dest)
    return dest


def fonts() -> dict[str, matplotlib.font_manager.FontProperties]:
    global _FONTS
    if _FONTS is None:
        from matplotlib import font_manager as fm

        root = Path(__file__).resolve().parents[1] / "web" / "fonts"
        ui = _instance(root / "Outfit-Variable.ttf", {"wght": 460})
        display = _instance(
            root / "Fraunces-Variable.ttf",
            {"wght": 560, "opsz": 72, "SOFT": 20, "WONK": 1},
        )
        mono = root / "IBMPlexMono-Regular.ttf"
        _FONTS = {
            "ui": fm.FontProperties(fname=str(ui)),
            "display": fm.FontProperties(fname=str(display)),
            "mono": fm.FontProperties(fname=str(mono)),
        }
    return _FONTS


def _clock(dt: datetime) -> str:
    """Local Pacific clock first, then the Z hour. Example: Tue 11 AM PDT / 18Z."""
    loc = dt.astimezone(PACIFIC)
    hour = loc.hour
    h12 = hour % 12 or 12
    ampm = "AM" if hour < 12 else "PM"
    tz = loc.tzname() or "PT"
    zulu = dt.astimezone(timezone.utc)
    return f"{DAYS[loc.weekday()]} {h12} {ampm} {tz} / {zulu:%H}Z"


def _geo_aspect(west: float, east: float, south: float, north: float) -> float:
    cos = max(float(np.cos(np.deg2rad((south + north) / 2.0))), 0.25)
    return ((east - west) * cos) / max(north - south, 0.05)


def _coverage(payload: Payload) -> tuple[float, float, float, float]:
    if payload.regular:
        return (
            float(np.min(payload.lons)),
            float(np.max(payload.lons)),
            float(np.min(payload.lats)),
            float(np.max(payload.lats)),
        )
    finite = np.isfinite(payload.lats) & np.isfinite(payload.lons)
    lons = payload.lons[finite]
    lats = payload.lats[finite]
    return float(np.min(lons)), float(np.max(lons)), float(np.min(lats)), float(np.max(lats))


# Leftover aspect error inside this band is absorbed by a slight stretch so the
# plate stays full-bleed. Beyond it, the long side is trimmed.
_STRETCH = 1.06


def fit_window(
    focus: tuple[float, float, float, float],
    target: float,
    limit: tuple[float, float, float, float],
    north_bias: bool = False,
) -> tuple[float, float, float, float]:
    """Match the frame by extending past the region, then trimming the long side.

    A grid that still cannot reach the frame is narrowed until the leftover
    mismatch is small enough to stretch away. `north_bias` puts almost all of
    the extra latitude north of the focus and only a slight step south.
    """
    west, east, south, north = focus
    for _ in range(8):
        aspect = _geo_aspect(west, east, south, north)
        cos = max(float(np.cos(np.deg2rad((south + north) / 2.0))), 0.25)
        if aspect < target * 0.99:
            need = target * (north - south) / cos
            pad = (need - (east - west)) / 2.0
            west -= pad
            east += pad
        elif aspect > target * 1.01:
            need = (east - west) * cos / target
            extra = need - (north - south)
            if north_bias:
                south_extra = min(0.40, max(0.2, extra * 0.12))
                south -= south_extra
                north += extra - south_extra
            else:
                pad = extra / 2.0
                south -= pad
                north += pad
        else:
            break
    lw, le, ls, ln = limit
    west, east = max(west, lw), min(east, le)
    south, north = max(south, ls), min(north, ln)
    if east - west < 0.5 or north - south < 0.5:
        return focus
    aspect = _geo_aspect(west, east, south, north)
    cos = max(float(np.cos(np.deg2rad((south + north) / 2.0))), 0.25)
    if aspect > target * _STRETCH:
        need = (target * _STRETCH) * (north - south) / cos
        mid = (focus[0] + focus[1]) / 2.0
        west = max(lw, mid - need / 2.0)
        east = min(le, west + need)
        if east - west < need - 0.05:
            west = max(lw, east - need)
    elif aspect < target / _STRETCH:
        need = (east - west) * cos / (target / _STRETCH)
        mid = (focus[2] + focus[3]) / 2.0
        south = max(ls, mid - need / 2.0)
        north = min(ln, south + need)
        if north - south < need - 0.05:
            south = max(ls, north - need)
    return west, east, south, north


def _axes_rect(view_aspect: float, target: float, fig_w: float, fig_h: float, header: float, footer: float):
    avail_h = 1.0 - header - footer
    if 0.90 <= view_aspect / target <= 1.10:
        return 0.0, footer, 1.0, avail_h
    if view_aspect > target:
        axes_w = 1.0
        axes_h = (axes_w * fig_w) / (view_aspect * fig_h)
        axes_h = min(axes_h, avail_h)
    else:
        axes_h = avail_h
        axes_w = axes_h * view_aspect * fig_h / fig_w
        axes_w = min(axes_w, 1.0)
    x = (1.0 - axes_w) / 2.0
    y = footer + (avail_h - axes_h) / 2.0
    return x, y, axes_w, axes_h


def _colorbar(fig, rect, scale_name: str) -> None:
    """Colored strip between the unit/32° row and the tick labels.

    The strip is a figure artist above the footer band. An axes here sits under
    that band, which is why a patch drawn inside the axes never showed.
    """
    scale = SCALES[scale_name]
    x0, y0, width, height = rect
    n = len(scale.colors)
    swatch = width / max(n, 1)
    for i, color in enumerate(scale.colors):
        fig.add_artist(
            Rectangle(
                (x0 + i * swatch, y0),
                swatch,
                height,
                transform=fig.transFigure,
                facecolor=color,
                edgecolor="none",
                linewidth=0,
                zorder=7,
            )
        )
    slot = (width * fig.get_figwidth() * fig.dpi) / max(n, 1)
    stride = max(1, int(np.ceil(40.0 / max(slot, 1.0))))
    call = None
    if scale.callout is not None:
        hits = [i for i, edge in enumerate(scale.edges) if abs(edge - scale.callout) < 1e-6]
        call = hits[0] if hits else None
    for i, edge in enumerate(scale.edges):
        keep = i == 0 or i == len(scale.edges) - 1 or i % stride == 0 or i == call
        if not keep:
            continue
        if call is not None and i != call and abs(i - call) * slot < 36:
            continue
        cx = x0 + (i / n) * width
        if i == call:
            mark = f"{_tick(edge)}°" if scale.unit == "°F" else _tick(edge)
            fig.add_artist(
                Line2D(
                    [cx, cx],
                    [y0, y0 + height],
                    transform=fig.transFigure,
                    color="#10233f",
                    lw=1.15,
                    solid_capstyle="butt",
                    zorder=7.2,
                )
            )
            fig.text(
                cx,
                y0 + height + 0.006,
                mark,
                ha="center",
                va="bottom",
                fontsize=9,
                color="#10233f",
                fontproperties=fonts()["display"],
                zorder=8,
            )
            continue
        fig.text(
            cx,
            y0 - 0.008,
            _tick(edge),
            ha="center",
            va="top",
            fontsize=7.5,
            color=INK,
            fontproperties=fonts()["mono"],
            zorder=8,
        )
    fig.text(
        x0 + width,
        y0 + height + 0.006,
        scale.unit,
        ha="right",
        va="bottom",
        fontsize=8,
        color=INK,
        fontproperties=fonts()["ui"],
        zorder=8,
    )


def _tick(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:g}"


def _stroke(ax, name: str, west, east, south, north, color: str, lw: float, zorder: int) -> None:
    picked = visible(name, west, east, south, north)
    if not picked:
        return
    ax.add_collection(
        LineCollection(picked, colors=color, linewidths=lw, zorder=zorder, capstyle="round", joinstyle="round")
    )


def _borders(ax, region: str, west, east, south, north) -> None:
    # A light halo under a dark stroke stays readable on navy, yellow, and red.
    if region == "wa":
        _stroke(ax, "counties", west, east, south, north, HALO, 1.15, 5)
        _stroke(ax, "counties", west, east, south, north, "#3d362e", 0.45, 6)
    _stroke(ax, "coast", west, east, south, north, HALO, 2.5, 6)
    _stroke(ax, "coast", west, east, south, north, "#101820", 1.25, 7)
    _stroke(ax, "states", west, east, south, north, HALO, 3.2, 8)
    _stroke(ax, "states", west, east, south, north, "#140f0c", 1.45, 9)


def render_plate(
    payload: Payload,
    region: str,
    aspect: str,
    init: datetime,
    hour: int,
    model_label: str,
    attribution: str,
    dest: Path,
) -> None:
    bounds = REGIONS[region]
    focus = (bounds["west"], bounds["east"], bounds["south"], bounds["north"])
    wide = aspect == "wide"
    fig_w, fig_h = (16.0, 9.0) if wide else (9.0, 16.0)
    header = 0.132 if wide else 0.172
    footer = 0.138 if wide else 0.100
    target = (1.0 * fig_w) / ((1.0 - header - footer) * fig_h)
    lambert = (not payload.regular) and payload.lov is not None and payload.latin1 is not None
    north_bias = region == "wa" and not wide
    if lambert:
        c0, c1, r0, r1 = _index_window(payload.lats, payload.lons, focus, target, north_bias=north_bias)
        plate = payload
        index_aspect = (c1 - c0) / max(r1 - r0, 1)
        # Stretch a little to stay full-bleed. A much taller reel (Washington on
        # HRRR, which runs out of grid over southern BC) keeps its true shape.
        if 0.82 <= index_aspect / target <= 1.22:
            mx, my, mw, mh = 0.0, footer, 1.0, 1.0 - header - footer
        else:
            mx, my, mw, mh = _axes_rect(index_aspect, target, fig_w, fig_h, header, footer)
    else:
        west, east, south, north = fit_window(focus, target, _coverage(payload), north_bias=north_bias)
        try:
            plate = payload.clip(west - 0.4, east + 0.4, south - 0.4, north + 0.4)
        except ValueError:
            plate = payload.clip(west, east, south, north)
        view_aspect = _geo_aspect(west, east, south, north)
        mx, my, mw, mh = _axes_rect(view_aspect, target, fig_w, fig_h, header, footer)
    dpi = 100
    if lambert:
        dpi = max(
            100,
            int(np.ceil((c1 - c0) / max(mw * fig_w, 0.1))),
            int(np.ceil((r1 - r0) / max(mh * fig_h, 0.1))),
        )
        dpi = min(dpi, 170)
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=dpi, facecolor=FRAME)
    ax = fig.add_axes((mx, my, mw, mh), facecolor=WATER)
    ax.set_axis_off()
    ax.patch.set_visible(True)
    if lambert:
        out_w = int(round(mw * fig_w * dpi))
        out_h = int(round(mh * fig_h * dpi))
        _paint_lambert(ax, plate, region, wide, c0, c1, r0, r1, out_w, out_h)
    else:
        ax.set_xlim(west, east)
        ax.set_ylim(south, north)
        values = None if plate.values is None else plate.values.astype(np.float32, copy=True)
        if values is not None and plate.mask_below is not None:
            values = np.where(values < plate.mask_below, np.nan, values)
        if plate.categories is not None:
            cat = np.ma.masked_where(plate.categories < 1, plate.categories)
            cmap = matplotlib.colors.ListedColormap(
                [PTYPE_COLORS[1], PTYPE_COLORS[2], PTYPE_COLORS[3], PTYPE_COLORS[4]]
            )
            cmap.set_bad(WATER)
            norm = matplotlib.colors.BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5], cmap.N)
            _shade(ax, plate, cat, cmap, norm)
        if values is not None and plate.scale:
            scale = SCALES[plate.scale]
            _shade(ax, plate, np.ma.masked_invalid(values), scale.colormap(), scale.norm())
        _borders(ax, region, west, east, south, north)
        if plate.contours is not None and plate.contour_kind == "mslp":
            levels = _span_levels(plate.contours, 4)
            if levels.size:
                cs = ax.contour(
                    *_contour_args(plate, plate.contours),
                    levels=levels,
                    colors="#3d2b22",
                    linewidths=0.7,
                    zorder=6,
                )
                ax.clabel(cs, levels[::2], fmt="%d", fontsize=7, colors="#3d2b22")
        if plate.contours is not None and plate.contour_kind == "height":
            levels = _span_levels(plate.contours, 60)
            if levels.size:
                cs = ax.contour(
                    *_contour_args(plate, plate.contours),
                    levels=levels,
                    colors="#2c261f",
                    linewidths=0.55,
                    zorder=6,
                )
                ax.clabel(cs, fmt=lambda v: f"{int(round(v / 10.0))}", fontsize=7)
            if np.nanmin(plate.contours) <= 5400 <= np.nanmax(plate.contours):
                mark = ax.contour(
                    *_contour_args(plate, plate.contours),
                    levels=[5400],
                    colors=VERMILION,
                    linewidths=1.35,
                    zorder=7,
                )
                ax.clabel(mark, fmt=lambda v: "540", fontsize=8)
        if plate.scale == "temp_f" and values is not None and np.nanmin(values) <= 32 <= np.nanmax(values):
            freeze = ax.contour(
                *_contour_args(plate, values),
                levels=[32],
                colors="#10233f",
                linewidths=1.15,
                linestyles="solid",
                zorder=7,
            )
            ax.clabel(freeze, fmt=lambda v: "32°", fontsize=8)
        if plate.u is not None and plate.v is not None:
            _barbs(ax, plate)
        ax.set_xlim(west, east)
        ax.set_ylim(south, north)
        _label_cities(ax, region, wide, west, east, south, north, lambda lon, lat: (lon, lat))

    _chrome(fig, header, footer)
    _masthead(fig, wide, model_label, plate, init, hour, region, header)
    if plate.scale and plate.values is not None:
        bar_w = min(mw, 0.92)
        bar_x = mx + (mw - bar_w) / 2.0
        bar_h = 0.026 if wide else 0.016
        bar_y = 0.062 if wide else 0.048
        _colorbar(fig, (bar_x, bar_y, bar_w, bar_h), plate.scale)
    elif plate.categories is not None:
        _ptype_key(fig, mx, mw, wide)

    credit = ecmwf_plate_credit() if attribution == "ecmwf" else noaa_plate_credit()
    fig.text(
        0.018,
        0.012,
        credit,
        ha="left",
        va="bottom",
        fontsize=9 if wide else 8,
        color="#3c342c",
        fontproperties=fonts()["mono"],
        zorder=8,
    )

    dest.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi)
    quality = 78 if dpi > 110 else 82
    plt.close(fig)
    buf.seek(0)
    image = Image.open(buf).convert("RGB")
    image.save(dest, "WEBP", quality=quality, method=4)


def _index_window(
    lats: np.ndarray,
    lons: np.ndarray,
    focus: tuple[float, float, float, float],
    target: float,
    stretch: float = 1.18,
    north_bias: bool = False,
) -> tuple[int, int, int, int]:
    """Column/row window on an equal-dx Lambert grid, matched to the frame.

    Cells are square in the projection, so the frame aspect is columns/rows.
    The window keeps the focus when it fits, then trims the long side.
    `north_bias` spends extra rows on the north side and only a slight step south.
    """
    nj, ni = lats.shape
    west, east, south, north = focus
    hit = (lats >= south) & (lats <= north) & (lons >= west) & (lons <= east)
    cols = np.where(hit.any(axis=0))[0]
    if north_bias and len(cols) >= 2:
        sample = lats[:, int(cols[len(cols) // 2])]
        rows = np.where((sample >= south - 0.05) & (sample <= north + 0.15))[0]
    else:
        rows = np.where(hit.any(axis=1))[0]
    if len(rows) < 2 or len(cols) < 2:
        return 0, ni, 0, nj
    r0, r1 = int(rows[0]), int(rows[-1]) + 1
    c0, c1 = int(cols[0]), int(cols[-1]) + 1

    def _clamp_cols(c0, c1, need):
        c0 = int(c0)
        c1 = int(c0 + need)
        if c0 < 0:
            c1 -= c0
            c0 = 0
        if c1 > ni:
            c0 -= c1 - ni
            c1 = ni
        return max(0, c0), c1

    def _clamp_rows(r0, r1, need):
        r0 = int(r0)
        r1 = int(r0 + need)
        if r0 < 0:
            r1 -= r0
            r0 = 0
        if r1 > nj:
            r0 -= r1 - nj
            r1 = nj
        return max(0, r0), r1

    grew_south = False
    for _ in range(4):
        aspect = (c1 - c0) / max(r1 - r0, 1)
        if aspect < target * 0.99 and (c1 - c0) < ni:
            need = min(ni, int(np.ceil(target * (r1 - r0))))
            mid = (c0 + c1) / 2.0
            c0, c1 = _clamp_cols(mid - need / 2.0, c1, need)
        elif aspect > target * 1.01 and (r1 - r0) < nj:
            need = min(nj, int(np.ceil((c1 - c0) / target)))
            if north_bias:
                extra = max(0, need - (r1 - r0))
                span = max(int(rows[-1]) - int(rows[0]), 1)
                deg_per_row = max(north - south, 0.2) / span
                south_rows = 0 if grew_south else min(extra, max(4, int(round(0.30 / deg_per_row))))
                grew_south = True
                new_r0 = max(0, r0 - south_rows)
                new_r1 = min(nj, r1 + extra - south_rows)
                r0, r1 = new_r0, new_r1
                if r1 >= nj:
                    break
            else:
                mid = (r0 + r1) / 2.0
                r0, r1 = _clamp_rows(mid - need / 2.0, r1, need)
        else:
            break
    aspect = (c1 - c0) / max(r1 - r0, 1)
    # A north-biased reel keeps the state's width even if the grid runs out of
    # British Columbia before the frame is perfectly tall.
    if aspect > target * stretch and not north_bias:
        need = max(2, int(round((r1 - r0) * target * stretch)))
        need = min(need, c1 - c0)
        mid = (int(cols[0]) + int(cols[-1]) + 1) / 2.0
        c0, c1 = _clamp_cols(mid - need / 2.0, c1, need)
    elif aspect < target / stretch:
        need = max(2, int(round((c1 - c0) / (target / stretch))))
        need = min(need, r1 - r0)
        mid = (int(rows[0]) + int(rows[-1]) + 1) / 2.0
        r0, r1 = _clamp_rows(mid - need / 2.0, r1, need)
    return c0, c1, r0, r1


def _lambert_indexer(plate: Payload):
    """Map lon/lat to column/row. HRRR rows increase northward and columns eastward."""
    latin = plate.latin1 if plate.latin1 is not None else 38.5
    latin2 = plate.latin1 if plate.latin2 is None else plate.latin2
    lov = plate.lov if plate.lov is not None else -97.5
    if lov > 180.0:
        lov -= 360.0
    lat1 = np.deg2rad(latin)
    lat2 = np.deg2rad(latin2)
    if abs(latin - latin2) < 1e-3:
        n = float(np.sin(lat1))
    else:
        n = float(np.log(np.cos(lat1) / np.cos(lat2)) / np.log(np.tan(np.pi / 4 + lat2 / 2) / np.tan(np.pi / 4 + lat1 / 2)))
    radius = 6371229.0
    factor = np.cos(lat1) * np.tan(np.pi / 4 + lat1 / 2) ** n / n

    def xy(lon, lat):
        lon = np.asarray(lon, dtype=np.float64)
        lat = np.asarray(lat, dtype=np.float64)
        rho = radius * factor / np.tan(np.pi / 4 + np.deg2rad(lat) / 2) ** n
        theta = n * np.deg2rad((lon - lov + 180.0) % 360.0 - 180.0)
        return rho * np.sin(theta), -rho * np.cos(theta)

    x00, y00 = xy(plate.lons[0, 0], plate.lats[0, 0])
    x10, y10 = xy(plate.lons[0, 1], plate.lats[0, 1])
    x01, y01 = xy(plate.lons[1, 0], plate.lats[1, 0])
    dx = float(x10 - x00) or 3000.0
    dy = float(y01 - y00) or 3000.0

    def to_rc(lon, lat):
        x, y = xy(lon, lat)
        return (x - x00) / dx, (y - y00) / dy

    return to_rc


def _upsample(values: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
    """Bilinear in data space, then the discrete colormap. No grid points are dropped."""
    src_h, src_w = values.shape
    out_h = max(out_h, src_h)
    out_w = max(out_w, src_w)
    if (src_h, src_w) == (out_h, out_w):
        return values
    finite = np.isfinite(values)
    filled = np.where(finite, values, 0.0).astype(np.float32)
    field = np.asarray(
        Image.fromarray(filled, mode="F").resize((out_w, out_h), Image.Resampling.BILINEAR),
        dtype=np.float32,
    )
    mask = np.asarray(
        Image.fromarray((finite.astype(np.uint8) * 255), mode="L").resize((out_w, out_h), Image.Resampling.NEAREST)
    )
    return np.where(mask > 127, field, np.nan)


def _label_cities(ax, region: str, wide: bool, west, east, south, north, to_xy) -> None:
    """A short public-domain city list. Labels nudge apart when metros sit close together."""
    face = fonts()["ui"]
    halo = [patheffects.withStroke(linewidth=2.6, foreground=HALO)]
    placed: list[tuple[float, float]] = []
    size = 6.5 if wide else 7.5
    for name, lon, lat in cities(region):
        if lon < west or lon > east or lat < south or lat > north:
            continue
        x, y = to_xy(lon, lat)
        px, py = ax.transData.transform((float(x), float(y)))
        for _ in range(4):
            if not any(abs(px - ox) < 58 and abs(py - oy) < 15 for ox, oy in placed):
                break
            py += 15
        placed.append((px, py))
        x, y = ax.transData.inverted().transform((px, py))
        ax.text(
            x,
            y,
            name,
            ha="center",
            va="center",
            fontsize=size,
            color=INK,
            fontproperties=face,
            path_effects=halo,
            zorder=9,
            clip_on=True,
        )


def _paint_lambert(ax, plate: Payload, region: str, wide: bool, c0: int, c1: int, r0: int, r1: int, out_w: int, out_h: int) -> None:
    """Draw a Lambert grid in its own square cells so the mesh fills the axes."""
    sl = np.s_[r0:r1, c0:c1]
    view_lons = plate.lons[sl]
    view_lats = plate.lats[sl]
    west = float(np.min(view_lons)) - 0.6
    east = float(np.max(view_lons)) + 0.6
    south = float(np.min(view_lats)) - 0.4
    north = float(np.max(view_lats)) + 0.4
    to_rc = _lambert_indexer(plate)

    def stroke(name, color, lw, zorder):
        picked = visible(name, west, east, south, north)
        if not picked:
            return
        segs = []
        for line in picked:
            col, row = to_rc(line[:, 0], line[:, 1])
            segs.append(np.column_stack([col, row]))
        ax.add_collection(LineCollection(segs, colors=color, linewidths=lw, zorder=zorder, capstyle="round", joinstyle="round"))

    values = None if plate.values is None else plate.values[sl].astype(np.float32, copy=True)
    if values is not None and plate.mask_below is not None:
        values = np.where(values < plate.mask_below, np.nan, values)
    extent = (c0, c1, r0, r1)
    if plate.categories is not None:
        cat = np.ma.masked_where(plate.categories[sl] < 1, plate.categories[sl])
        cmap = matplotlib.colors.ListedColormap([PTYPE_COLORS[1], PTYPE_COLORS[2], PTYPE_COLORS[3], PTYPE_COLORS[4]])
        cmap.set_bad(WATER)
        norm = matplotlib.colors.BoundaryNorm([0.5, 1.5, 2.5, 3.5, 4.5], cmap.N)
        ax.imshow(cat, origin="lower", extent=extent, cmap=cmap, norm=norm, interpolation="nearest", aspect="auto", zorder=2)
    if values is not None and plate.scale:
        scale = SCALES[plate.scale]
        shown = _upsample(values, out_h, out_w)
        ax.imshow(
            np.ma.masked_invalid(shown),
            origin="lower",
            extent=extent,
            cmap=scale.colormap(),
            norm=scale.norm(),
            interpolation="nearest",
            aspect="auto",
            zorder=2,
        )
    if region == "wa":
        stroke("counties", HALO, 1.15, 5)
        stroke("counties", "#3d362e", 0.45, 6)
    stroke("coast", HALO, 2.5, 6)
    stroke("coast", "#101820", 1.25, 7)
    stroke("states", HALO, 3.2, 8)
    stroke("states", "#140f0c", 1.45, 9)

    xx = np.arange(c0, c1) + 0.5
    yy = np.arange(r0, r1) + 0.5

    if plate.contours is not None and plate.contour_kind == "mslp":
        field = plate.contours[sl]
        levels = _span_levels(field, 4)
        if levels.size:
            cs = ax.contour(xx, yy, field, levels=levels, colors="#3d2b22", linewidths=0.7, zorder=6)
            ax.clabel(cs, levels[::2], fmt="%d", fontsize=7, colors="#3d2b22")
    if plate.contours is not None and plate.contour_kind == "height":
        field = plate.contours[sl]
        levels = _span_levels(field, 60)
        if levels.size:
            cs = ax.contour(xx, yy, field, levels=levels, colors="#2c261f", linewidths=0.55, zorder=6)
            ax.clabel(cs, fmt=lambda v: f"{int(round(v / 10.0))}", fontsize=7)
        if np.nanmin(field) <= 5400 <= np.nanmax(field):
            mark = ax.contour(xx, yy, field, levels=[5400], colors=VERMILION, linewidths=1.35, zorder=7)
            ax.clabel(mark, fmt=lambda v: "540", fontsize=8)
    if plate.scale == "temp_f" and values is not None and np.nanmin(values) <= 32 <= np.nanmax(values):
        freeze = ax.contour(xx, yy, values, levels=[32], colors="#10233f", linewidths=1.15, zorder=7)
        ax.clabel(freeze, fmt=lambda v: "32°", fontsize=8)
    if plate.u is not None and plate.v is not None:
        step_r = max(8, (r1 - r0) // 14)
        step_c = max(8, (c1 - c0) // 18)
        uu = plate.u[r0:r1:step_r, c0:c1:step_c]
        vv = plate.v[r0:r1:step_r, c0:c1:step_c]
        speed = np.hypot(uu, vv)
        ax.barbs(
            xx[::step_c],
            yy[::step_r],
            np.where(speed < 1, np.nan, uu),
            np.where(speed < 1, np.nan, vv),
            length=5.0,
            linewidth=0.35,
            color=INK,
            zorder=8,
            sizes={"emptybarb": 0.1, "spacing": 0.16, "height": 0.36, "width": 0.2},
        )
    ax.set_xlim(c0, c1)
    ax.set_ylim(r0, r1)
    _label_cities(ax, region, wide, west, east, south, north, lambda lon, lat: to_rc(lon, lat))


def _shade(ax, plate: Payload, data, cmap, norm) -> None:
    if plate.regular:
        lats = plate.lats
        lons = plate.lons
        dlat = float(lats[1] - lats[0]) if len(lats) > 1 else 0.1
        dlon = float(lons[1] - lons[0]) if len(lons) > 1 else 0.1
        south = min(lats[0], lats[-1]) - abs(dlat) / 2
        north = max(lats[0], lats[-1]) + abs(dlat) / 2
        west = min(lons[0], lons[-1]) - abs(dlon) / 2
        east = max(lons[0], lons[-1]) + abs(dlon) / 2
        origin = "upper" if lats[0] > lats[-1] else "lower"
        ax.imshow(
            data,
            origin=origin,
            extent=(west, east, south, north),
            cmap=cmap,
            norm=norm,
            interpolation="nearest",
            aspect="auto",
            zorder=2,
        )
        return
    step = 2 if data.shape[1] > 800 else 1
    ax.pcolormesh(
        plate.lons[::step, ::step],
        plate.lats[::step, ::step],
        data[::step, ::step],
        cmap=cmap,
        norm=norm,
        shading="nearest",
        zorder=2,
    )


def _contour_args(plate: Payload, values: np.ndarray):
    if plate.regular:
        return plate.lons, plate.lats, values
    step = 2 if values.shape[1] > 800 else 1
    return plate.lons[::step, ::step], plate.lats[::step, ::step], values[::step, ::step]


def _span_levels(values: np.ndarray, step: float) -> np.ndarray:
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.array([])
    lo = np.floor(float(np.min(finite)) / step) * step
    hi = np.ceil(float(np.max(finite)) / step) * step
    if hi <= lo:
        return np.array([])
    return np.arange(lo, hi + step * 0.5, step)


def _barbs(ax, plate: Payload) -> None:
    speed = np.hypot(plate.u, plate.v)
    if plate.regular:
        step_x = max(1, plate.lons.size // 18)
        step_y = max(1, plate.lats.size // 12)
        uu = np.where(speed < 1, np.nan, plate.u)[::step_y, ::step_x]
        vv = np.where(speed < 1, np.nan, plate.v)[::step_y, ::step_x]
        ax.barbs(
            plate.lons[::step_x],
            plate.lats[::step_y],
            uu,
            vv,
            length=5.2,
            linewidth=0.4,
            color=INK,
            zorder=8,
            sizes={"emptybarb": 0.12, "spacing": 0.18, "height": 0.38, "width": 0.22},
        )
        return
    step = max(8, plate.values.shape[1] // 18) if plate.values is not None else 24
    ax.barbs(
        plate.lons[::step, ::step],
        plate.lats[::step, ::step],
        np.where(speed < 1, np.nan, plate.u)[::step, ::step],
        np.where(speed < 1, np.nan, plate.v)[::step, ::step],
        length=5.0,
        linewidth=0.35,
        color=INK,
        zorder=8,
        sizes={"emptybarb": 0.1, "spacing": 0.16, "height": 0.36, "width": 0.2},
    )


def _chrome(fig, header: float, footer: float) -> None:
    fig.add_artist(Rectangle((0, 1.0 - header), 1.0, header, transform=fig.transFigure, facecolor=FRAME, edgecolor="none", zorder=5))
    fig.add_artist(Rectangle((0, 0), 1.0, footer, transform=fig.transFigure, facecolor=FRAME, edgecolor="none", zorder=5))
    fig.add_artist(Rectangle((0, 1.0 - header), 0.006, header, transform=fig.transFigure, facecolor=VERMILION, edgecolor="none", zorder=6))
    fig.add_artist(Line2D([0, 1], [1.0 - header, 1.0 - header], transform=fig.transFigure, color=BRASS, lw=1.05, zorder=6))


def _masthead(fig, wide: bool, model_label: str, plate: Payload, init: datetime, hour: int, region: str, header: float) -> None:
    face = fonts()
    valid = init + timedelta(hours=hour)
    region_label = REGIONS[region]["label"]
    fig.text(0.02, 0.978, site_name(), fontproperties=face["ui"], fontsize=11 if wide else 13, color=INK, va="top", zorder=7)
    fig.text(0.985, 0.978, f"+{hour:03d} h", fontproperties=face["mono"], fontsize=15 if wide else 17, color=VERMILION, va="top", ha="right", zorder=7)
    if wide:
        fig.text(0.20, 0.978, model_label, fontproperties=face["mono"], fontsize=10, color=BRASS, va="top", zorder=7)
        fig.text(0.02, 0.938, plate.title, fontproperties=face["display"], fontsize=20, color=INK, va="top", zorder=7)
        fig.text(0.02, 0.892, f"{plate.subtitle}   ·   {region_label}", fontproperties=face["ui"], fontsize=8.5, color="#4e483f", va="top", zorder=7)
        fig.text(0.985, 0.938, f"Init {_clock(init)}", fontproperties=face["mono"], fontsize=8.5, color=INK, va="top", ha="right", zorder=7)
        fig.text(0.985, 0.908, f"Valid {_clock(valid)}", fontproperties=face["mono"], fontsize=8.5, color=INK, va="top", ha="right", zorder=7)
    else:
        fig.text(0.02, 0.948, model_label, fontproperties=face["mono"], fontsize=10, color=BRASS, va="top", zorder=7)
        fig.text(0.02, 0.918, plate.title, fontproperties=face["display"], fontsize=18, color=INK, va="top", zorder=7)
        fig.text(0.02, 0.888, f"{plate.subtitle}   ·   {region_label}", fontproperties=face["ui"], fontsize=8.5, color="#4e483f", va="top", zorder=7)
        fig.text(0.02, 0.862, f"Init {_clock(init)}", fontproperties=face["mono"], fontsize=8, color=INK, va="top", zorder=7)
        fig.text(0.02, 0.840, f"Valid {_clock(valid)}", fontproperties=face["mono"], fontsize=8, color=INK, va="top", zorder=7)
    _ = header


def _ptype_key(fig, mx, mw, wide: bool) -> None:
    labels = [(1, "rain"), (2, "snow"), (3, "mix"), (4, "freezing")]
    y = 0.07 if wide else 0.085
    x = mx
    for code, label in labels:
        fig.add_artist(Rectangle((x, y), 0.016, 0.014, transform=fig.transFigure, facecolor=PTYPE_COLORS[code], edgecolor="none"))
        fig.text(x + 0.02, y + 0.007, label, fontproperties=fonts()["ui"], fontsize=8, color=INK, va="center")
        x += 0.12


