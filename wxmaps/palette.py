"""Stepped color scales.

The hues follow familiar meteorological reading order (cold blues, mild greens,
hot reds, radar greens-to-magentas) with original hex values. Freezing
temperature, including 32°F itself, stays in the blue family and gets darker
as it gets colder. The first step above 32°F leaves blue.
"""

from __future__ import annotations

import numpy as np
from matplotlib.colors import ListedColormap, Normalize


class Scale:
    def __init__(self, edges: list[float], colors: list[str], unit: str, callout: float | None = None):
        if len(colors) != len(edges) - 1:
            raise ValueError("colors must be one shorter than edges")
        self.edges = [float(v) for v in edges]
        self.colors = list(colors)
        self.unit = unit
        self.callout = callout

    def index_for(self, value: float) -> int:
        """Right-closed bins: (edge[i], edge[i+1]]."""
        idx = int(np.searchsorted(self.edges, value, side="left") - 1)
        return int(np.clip(idx, 0, len(self.colors) - 1))

    def hex_for(self, value: float) -> str:
        return self.colors[self.index_for(value)]

    def colormap(self) -> ListedColormap:
        cmap = ListedColormap(self.colors, name="wx")
        cmap.set_bad("#9eb4bc")
        return cmap

    def norm(self) -> Normalize:
        return _RightClosed(self.edges)


class _RightClosed(Normalize):
    def __init__(self, edges: list[float]):
        self.edges = np.asarray(edges, dtype=float)
        super().__init__(vmin=float(edges[0]), vmax=float(edges[-1]), clip=False)

    def __call__(self, value, clip=None):
        v = np.asarray(value, dtype=float)
        idx = np.searchsorted(self.edges, v, side="left") - 1
        idx = np.clip(idx, 0, len(self.edges) - 2)
        n = len(self.edges) - 1
        scaled = (idx + 0.5) / n
        return np.ma.masked_where(~np.isfinite(v), scaled)


def _scale(edges, colors, unit, callout=None) -> Scale:
    return Scale(edges, colors, unit, callout)


def _mix(a: str, b: str, t: float) -> str:
    a = a.lstrip("#")
    b = b.lstrip("#")
    parts = []
    for i in (0, 2, 4):
        av = int(a[i : i + 2], 16)
        bv = int(b[i : i + 2], 16)
        parts.append(int(round(av + (bv - av) * t)))
    return "#{:02x}{:02x}{:02x}".format(*parts)


def _paint(stops: list[tuple[float, str]], temps: list[float]) -> list[str]:
    colors = []
    for temp in temps:
        if temp <= stops[0][0]:
            colors.append(stops[0][1])
            continue
        if temp >= stops[-1][0]:
            colors.append(stops[-1][1])
            continue
        for (left, color_a), (right, color_b) in zip(stops, stops[1:]):
            if left <= temp <= right:
                span = right - left or 1.0
                colors.append(_mix(color_a, color_b, (temp - left) / span))
                break
    return colors


def _stepped(start: float, stop: float, step: float) -> list[float]:
    count = int(round((stop - start) / step))
    return [round(start + i * step, 4) for i in range(count + 1)]


# Right-closed 4°F bins. 32°F is the top of the light-blue bin. 36°F is teal.
_TEMP_EDGES = _stepped(-48, 120, 4)
TEMP_F = _scale(
    _TEMP_EDGES,
    _paint(
        [
            (-48, "#050a16"),
            (-32, "#0c1c46"),
            (-16, "#163672"),
            (0, "#1c4e98"),
            (16, "#3b7cbe"),
            (28, "#8ec4ea"),
            (32, "#c5e6f8"),
            (36, "#1f8f86"),
            (48, "#3aaa55"),
            (60, "#c6c24a"),
            (72, "#e6a02f"),
            (84, "#e36a1c"),
            (96, "#d63a2f"),
            (108, "#a61d45"),
            (120, "#4a1038"),
        ],
        _TEMP_EDGES[1:],
    ),
    "°F",
    callout=32,
)

_WIND_EDGES = [0, 3, 6, 9, 12, 15, 18, 21, 25, 30, 35, 40, 50, 60, 75]
WIND_MPH = _scale(
    _WIND_EDGES,
    _paint(
        [
            (0, "#e6e2d6"),
            (12, "#6fba72"),
            (21, "#e6c14a"),
            (35, "#d2542c"),
            (50, "#7c2a86"),
            (75, "#2a0c28"),
        ],
        _WIND_EDGES[1:],
    ),
    "mph",
)

_REFC_EDGES = _stepped(5, 75, 2.5)
REFLECTIVITY = _scale(
    _REFC_EDGES,
    _paint(
        [
            (5, "#d7f2e4"),
            (20, "#1f8a45"),
            (35, "#ddd24a"),
            (50, "#d04538"),
            (62, "#c43d86"),
            (75, "#f7eef8"),
        ],
        _REFC_EDGES[1:],
    ),
    "dBZ",
)

_PRECIP_EDGES = [0.01, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, 4, 5, 7, 10]
PRECIP_IN = _scale(
    _PRECIP_EDGES,
    _paint(
        [
            (0.01, "#e5f6d8"),
            (0.5, "#2f8f3e"),
            (1.25, "#d6cf4a"),
            (3, "#c4373a"),
            (7, "#d47ac4"),
            (10, "#f7eef8"),
        ],
        _PRECIP_EDGES[1:],
    ),
    "in",
)

_SNOW_EDGES = [0.1, 0.5, 1, 1.5, 2, 3, 4, 5, 6, 8, 10, 12, 16, 20, 28, 36]
SNOW_IN = _scale(
    _SNOW_EDGES,
    _paint(
        [
            (0.1, "#f7fbff"),
            (2, "#6ea8dc"),
            (6, "#243e86"),
            (16, "#8a5aa8"),
            (36, "#f3e8f8"),
        ],
        _SNOW_EDGES[1:],
    ),
    "in",
)

_CAPE_EDGES = [50, 100, 250, 500, 750, 1000, 1500, 2000, 2500, 3000, 4000, 5000, 6500]
CAPE = _scale(
    _CAPE_EDGES,
    _paint(
        [
            (50, "#f4f0c8"),
            (500, "#e6a33a"),
            (1500, "#c4373a"),
            (3000, "#5c1d6e"),
            (6500, "#1a0a18"),
        ],
        _CAPE_EDGES[1:],
    ),
    "J/kg",
)

_VORT_EDGES = [0, 2, 4, 6, 8, 10, 12, 16, 20, 24, 28, 36, 48]
VORT = _scale(
    _VORT_EDGES,
    _paint(
        [
            (0, "#f3f1ea"),
            (8, "#f0d36a"),
            (16, "#e08a34"),
            (28, "#b4233a"),
            (48, "#3e1438"),
        ],
        _VORT_EDGES[1:],
    ),
    "1e-5/s",
)

_RATE_EDGES = [0.01, 0.02, 0.05, 0.08, 0.12, 0.18, 0.25, 0.35, 0.5, 0.7, 1, 1.5, 2]
RATE_IN = _scale(
    _RATE_EDGES,
    _paint(
        [
            (0.01, "#e7f6dc"),
            (0.18, "#2f8f45"),
            (0.5, "#e6a33a"),
            (1, "#c4373a"),
            (2, "#f3e4f6"),
        ],
        _RATE_EDGES[1:],
    ),
    "in/h",
)

PTYPE_COLORS = {
    1: "#2f8f4e",  # rain
    2: "#2f62c4",  # snow
    3: "#e48ab8",  # mix / ice pellets
    4: "#c2185b",  # freezing rain
}

SCALES = {
    "temp_f": TEMP_F,
    "wind_mph": WIND_MPH,
    "refc": REFLECTIVITY,
    "precip_in": PRECIP_IN,
    "snow_in": SNOW_IN,
    "cape": CAPE,
    "vort": VORT,
    "rate_in": RATE_IN,
}
