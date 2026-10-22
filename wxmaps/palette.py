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
        cmap.set_bad("#efeae0")
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


# Bins are right-closed. 32°F is the top of a blue bin. 42°F is teal, not blue.
TEMP_F = _scale(
    [-80, -40, -20, -10, 0, 10, 20, 32, 42, 52, 62, 72, 82, 92, 102, 112, 125],
    [
        "#06102a",
        "#0c1d4d",
        "#16357a",
        "#1f4e9e",
        "#2d6ec4",
        "#4a96d6",
        "#8ecae6",
        "#2a9d8f",
        "#6aab45",
        "#c6c24a",
        "#e6a02f",
        "#e36a1c",
        "#d63a2f",
        "#a61d45",
        "#7a1a6d",
        "#451033",
    ],
    "°F",
    callout=32,
)

WIND_MPH = _scale(
    [0, 5, 10, 15, 20, 25, 30, 40, 50, 65, 85],
    [
        "#e6e2d6",
        "#b7d4c6",
        "#6fba72",
        "#c3c85a",
        "#e6c14a",
        "#e28a34",
        "#d2542c",
        "#b4233a",
        "#7c2a86",
        "#3e1458",
    ],
    "mph",
)

REFLECTIVITY = _scale(
    [5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75],
    [
        "#d7f2e4",
        "#8fd7a4",
        "#3eae62",
        "#1f8a45",
        "#86c04a",
        "#ddd24a",
        "#e6ad3a",
        "#e07a2c",
        "#d04538",
        "#b42348",
        "#c43d86",
        "#e184c4",
        "#f2d4ef",
        "#f7eef8",
    ],
    "dBZ",
)

PRECIP_IN = _scale(
    [0.01, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 6, 8, 12],
    [
        "#e5f6d8",
        "#b7e39a",
        "#6fbe55",
        "#2f8f3e",
        "#1f6e4a",
        "#d6cf4a",
        "#e6a33a",
        "#d4652c",
        "#c4373a",
        "#8d2f86",
        "#d47ac4",
        "#f3e4f2",
    ],
    "in",
)

SNOW_IN = _scale(
    [0.1, 0.5, 1, 2, 3, 4, 6, 8, 12, 18, 24, 36],
    [
        "#f7fbff",
        "#d6e8f7",
        "#a9cfee",
        "#6ea8dc",
        "#3d7ec4",
        "#2a5ea8",
        "#243e86",
        "#3d3480",
        "#62408a",
        "#8a5aa8",
        "#c9b6de",
    ],
    "in",
)

CAPE = _scale(
    [100, 250, 500, 1000, 1500, 2000, 3000, 4500, 6000],
    [
        "#f4f0c8",
        "#e6d15a",
        "#e6a33a",
        "#d4652c",
        "#c4373a",
        "#8d2a6a",
        "#5c1d6e",
        "#2c1038",
    ],
    "J/kg",
)

VORT = _scale(
    [0, 4, 8, 12, 16, 20, 24, 32, 40, 56],
    [
        "#f3f1ea",
        "#f7e7b0",
        "#f0d36a",
        "#e6b04a",
        "#e08a34",
        "#d25a2c",
        "#b4233a",
        "#7c2458",
        "#3e1438",
    ],
    "1e-5/s",
)

RATE_IN = _scale(
    [0.01, 0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 1, 1.5, 2],
    [
        "#e7f6dc",
        "#b4e09a",
        "#62b85a",
        "#2f8f45",
        "#d6cf4a",
        "#e6a33a",
        "#d4652c",
        "#c4373a",
        "#f0d0ea",
    ],
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
