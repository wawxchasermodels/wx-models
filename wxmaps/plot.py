"""Draw one chart plate. Wide is 1600×900, reel is 900×1600."""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
import matplotlib.colors
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from PIL import Image

from wxmaps.attribution import ecmwf_map_credit, noaa_map_credit
from wxmaps.brand import site_name
from wxmaps.derive import Payload
from wxmaps.geo import visible
from wxmaps.models import REGIONS
from wxmaps.palette import PTYPE_COLORS, SCALES

PACIFIC = ZoneInfo("America/Los_Angeles")
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
PAPER = "#f4efe6"
INK = "#241c16"
BRASS = "#9a6232"
VERMILION = "#d24b2e"
WATER = "#d5e0e4"

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


def _stamp(dt: datetime) -> str:
    loc = dt.astimezone(PACIFIC)
    return (
        f"{dt.day:02d} {MONTHS[dt.month - 1]} {dt:%H:%M}Z"
        f"   {loc:%H:%M} {loc.tzname() or 'PT'}"
    )


def _map_box(fig_w: float, fig_h: float, west, east, south, north, header: float, footer: float) -> tuple[float, float, float, float]:
    cos = np.cos(np.deg2rad((south + north) / 2.0))
    geo = ((east - west) * cos) / max(north - south, 0.1)
    avail_w = 0.92
    avail_h = 1.0 - header - footer
    axes_w = avail_w
    axes_h = axes_w * fig_w / (geo * fig_h)
    if axes_h > avail_h:
        axes_h = avail_h
        axes_w = axes_h * geo * fig_h / fig_w
    x = (1.0 - axes_w) / 2.0
    y = footer + (avail_h - axes_h) / 2.0
    return x, y, axes_w, axes_h


def _colorbar(fig, rect, scale_name: str, vertical: bool = False) -> None:
    scale = SCALES[scale_name]
    ax = fig.add_axes(rect)
    ax.set_axis_off()
    n = len(scale.colors)
    if vertical:
        ax.set_xlim(0, 1)
        ax.set_ylim(0, n)
        for i, color in enumerate(scale.colors):
            ax.add_patch(Rectangle((0, i), 1, 1, facecolor=color, edgecolor="none"))
        for i, edge in enumerate(scale.edges):
            weight = "medium" if scale.callout is not None and edge == scale.callout else "normal"
            ax.text(1.15, i, _tick(edge), ha="left", va="center", fontsize=6.5, color=INK, fontproperties=fonts()["mono"], fontweight=weight, clip_on=False)
    else:
        ax.set_xlim(0, n)
        ax.set_ylim(0, 1)
        for i, color in enumerate(scale.colors):
            ax.add_patch(Rectangle((i, 0), 1, 1, facecolor=color, edgecolor="none"))
        for i, edge in enumerate(scale.edges):
            label = _tick(edge)
            if scale.callout is not None and edge == scale.callout:
                label = f"{label}°" if scale.unit == "°F" else label
                ax.add_line(Line2D([i, i], [0, 1], color="#10233f", lw=1.15, solid_capstyle="butt"))
                ax.text(i, 1.55, label, ha="center", va="bottom", fontsize=8, color="#10233f", fontproperties=fonts()["display"], clip_on=False)
            else:
                ax.text(i, -0.45, label, ha="center", va="top", fontsize=6.5, color=INK, fontproperties=fonts()["mono"], clip_on=False)
    ax.text(
        0.0 if not vertical else 0.0,
        1.55 if not vertical else n + 0.4,
        scale.unit,
        ha="left",
        va="bottom",
        fontsize=8,
        color=INK,
        fontproperties=fonts()["ui"],
        clip_on=False,
    )


def _tick(value: float) -> str:
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return f"{value:g}"


def _add_lines(ax, name: str, west, east, south, north, color, lw) -> None:
    picked = visible(name, west, east, south, north)
    if not picked:
        return
    ax.add_collection(LineCollection(picked, colors=color, linewidths=lw, zorder=4))


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
    west, east = bounds["west"], bounds["east"]
    south, north = bounds["south"], bounds["north"]
    plate = payload.clip(west - 0.8, east + 0.8, south - 0.8, north + 0.8)
    wide = aspect == "wide"
    fig_w, fig_h = (16.0, 9.0) if wide else (9.0, 16.0)
    header = 0.145 if wide else 0.19
    footer = 0.23 if wide else 0.22
    fig = plt.figure(figsize=(fig_w, fig_h), dpi=100, facecolor=PAPER)
    mx, my, mw, mh = _map_box(fig_w, fig_h, west, east, south, north, header, footer)
    ax = fig.add_axes((mx, my, mw, mh), facecolor=WATER)
    ax.set_xlim(west, east)
    ax.set_ylim(south, north)
    ax.set_axis_off()

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

    _add_lines(ax, "counties", west, east, south, north, "#8d8478", 0.28)
    _add_lines(ax, "coast", west, east, south, north, "#1c2a33", 0.7)
    _add_lines(ax, "states", west, east, south, north, "#2a241c", 1.05)

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

    if plate.scale == "temp_f" and values is not None:
        if np.nanmin(values) <= 32 <= np.nanmax(values):
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

    _masthead(fig, wide, model_label, plate, init, hour, region)
    if plate.scale and plate.values is not None:
        if wide:
            _colorbar(fig, (mx, 0.108, mw, 0.018), plate.scale)
        else:
            _colorbar(fig, (mx, 0.118, mw, 0.014), plate.scale)
    elif plate.categories is not None:
        _ptype_key(fig, mx, mw, wide)

    credit = ecmwf_map_credit(init.year) if attribution == "ecmwf" else noaa_map_credit()
    _wrapped(fig, credit, 0.016 if wide else 0.012, 100 if wide else 52, 7.0 if wide else 6.4)

    dest.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    image = Image.open(buf).convert("RGB")
    image.save(dest, "WEBP", quality=68, method=4)


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


def _masthead(fig, wide: bool, model_label: str, plate: Payload, init: datetime, hour: int, region: str) -> None:
    face = fonts()
    valid = init + timedelta(hours=hour)
    region_label = REGIONS[region]["label"]
    rule = 0.855 if wide else 0.80
    fig.add_artist(Rectangle((0, rule), 0.008, 1 - rule, transform=fig.transFigure, facecolor=VERMILION, edgecolor="none"))
    fig.add_artist(Line2D([0.03, 0.97], [rule, rule], transform=fig.transFigure, color=BRASS, lw=1.1))
    fig.text(0.028, 0.975, site_name(), fontproperties=face["ui"], fontsize=11 if wide else 13, color=INK, va="top")
    fig.text(0.985, 0.975, f"+{hour:03d} h", fontproperties=face["mono"], fontsize=15 if wide else 18, color=VERMILION, va="top", ha="right")
    if wide:
        fig.text(0.22, 0.975, model_label, fontproperties=face["mono"], fontsize=10, color=BRASS, va="top")
        fig.text(0.028, 0.928, plate.title, fontproperties=face["display"], fontsize=20, color=INK, va="top")
        fig.text(0.028, 0.888, f"{plate.subtitle}   ·   {region_label}", fontproperties=face["ui"], fontsize=8.5, color="#5c564c", va="top")
        fig.text(0.985, 0.930, f"Init  {_stamp(init)}", fontproperties=face["mono"], fontsize=8, color=INK, va="top", ha="right")
        fig.text(0.985, 0.902, f"Valid {_stamp(valid)}", fontproperties=face["mono"], fontsize=8, color=INK, va="top", ha="right")
    else:
        fig.text(0.028, 0.948, model_label, fontproperties=face["mono"], fontsize=10, color=BRASS, va="top")
        fig.text(0.028, 0.912, plate.title, fontproperties=face["display"], fontsize=20, color=INK, va="top")
        fig.text(0.028, 0.872, plate.subtitle, fontproperties=face["ui"], fontsize=8.5, color="#5c564c", va="top")
        fig.text(0.028, 0.848, region_label, fontproperties=face["ui"], fontsize=9, color=INK, va="top")
        fig.text(0.028, 0.828, f"Init  {_stamp(init)}", fontproperties=face["mono"], fontsize=8, color=INK, va="top")
        fig.text(0.028, 0.808, f"Valid {_stamp(valid)}", fontproperties=face["mono"], fontsize=8, color=INK, va="top")


def _ptype_key(fig, mx, mw, wide: bool) -> None:
    labels = [(1, "rain"), (2, "snow"), (3, "mix"), (4, "freezing")]
    y = 0.07 if wide else 0.085
    x = mx
    for code, label in labels:
        fig.add_artist(Rectangle((x, y), 0.016, 0.014, transform=fig.transFigure, facecolor=PTYPE_COLORS[code], edgecolor="none"))
        fig.text(x + 0.02, y + 0.007, label, fontproperties=fonts()["ui"], fontsize=8, color=INK, va="center")
        x += 0.12


def _wrapped(fig, text: str, y: float, width: int, size: float) -> None:
    import textwrap

    block = textwrap.fill(text, width=width)
    fig.text(0.03, y, block, fontproperties=fonts()["mono"], fontsize=size, color="#5e584e", va="bottom", ha="left")
