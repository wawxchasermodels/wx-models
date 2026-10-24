"""One Lambert conformal for every Washington plate.

Centered near 120.5°W with standard parallels 45°N and 49°N, so the state
has the same shape on ECMWF, AIFS, HRRR, and GFS.
"""

from __future__ import annotations

import numpy as np

LON0 = -120.5
LAT0 = 47.0
LAT1 = 45.0
LAT2 = 49.0
RADIUS = 6371229.0
# Keeps the Pacific shore and the Idaho line off the edge of the frame.
MARGIN_M = 26000.0


class Lambert:
    def __init__(self, lon0: float, lat0: float, lat1: float, lat2: float, radius: float = RADIUS):
        self.lon0 = float(lon0)
        self.lat0 = float(lat0)
        self.lat1 = float(lat1)
        self.lat2 = float(lat2)
        self.radius = float(radius)
        phi1 = np.deg2rad(self.lat1)
        phi2 = np.deg2rad(self.lat2)
        phi0 = np.deg2rad(self.lat0)
        if abs(self.lat1 - self.lat2) < 1e-6:
            n = float(np.sin(phi1))
        else:
            n = float(
                np.log(np.cos(phi1) / np.cos(phi2))
                / np.log(np.tan(np.pi / 4 + phi2 / 2) / np.tan(np.pi / 4 + phi1 / 2))
            )
        factor = float(np.cos(phi1) * np.tan(np.pi / 4 + phi1 / 2) ** n / n)
        self.n = n
        self.factor = factor
        self.rho0 = float(radius * factor / np.tan(np.pi / 4 + phi0 / 2) ** n)

    def forward(self, lon, lat):
        lon = np.asarray(lon, dtype=np.float64)
        lat = np.asarray(lat, dtype=np.float64)
        rho = self.radius * self.factor / np.tan(np.pi / 4 + np.deg2rad(lat) / 2.0) ** self.n
        theta = self.n * np.deg2rad(lon - self.lon0)
        return rho * np.sin(theta), self.rho0 - rho * np.cos(theta)

    def inverse(self, x, y):
        x = np.asarray(x, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64)
        dy = self.rho0 - y
        rho = np.sign(self.n) * np.hypot(x, dy)
        theta = np.arctan2(x, dy)
        lon = self.lon0 + np.rad2deg(theta / self.n)
        lat = np.rad2deg(2.0 * np.arctan((self.radius * self.factor / rho) ** (1.0 / self.n)) - np.pi / 2.0)
        return lon, lat


WA = Lambert(LON0, LAT0, LAT1, LAT2)


def state_extent() -> tuple[float, float, float, float]:
    """Projected box around the state, plus a small margin."""
    from wxmaps.models import REGIONS

    box = REGIONS["wa"]
    west, east, south, north = box["west"], box["east"], box["south"], box["north"]
    edge_lon = np.linspace(west, east, 60)
    edge_lat = np.linspace(south, north, 30)
    lons = np.concatenate([edge_lon, edge_lon, np.full(30, west), np.full(30, east)])
    lats = np.concatenate([np.full(60, south), np.full(60, north), edge_lat, edge_lat])
    x, y = WA.forward(lons, lats)
    return (
        float(np.min(x)) - MARGIN_M,
        float(np.max(x)) + MARGIN_M,
        float(np.min(y)) - MARGIN_M,
        float(np.max(y)) + MARGIN_M,
    )


def wa_view(target: float) -> tuple[float, float, float, float]:
    """Window in Lambert metres. The state box stays centered; the short side grows."""
    x0, x1, y0, y1 = state_extent()
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    width = x1 - x0
    height = y1 - y0
    if width / max(height, 1.0) > target:
        height = width / target
    else:
        width = height * target
    return cx - width / 2.0, cx + width / 2.0, cy - height / 2.0, cy + height / 2.0


def view_lonlat(xmin: float, xmax: float, ymin: float, ymax: float, pad: float = 0.35):
    xs = np.linspace(xmin, xmax, 28)
    ys = np.linspace(ymin, ymax, 28)
    grid_x = np.concatenate([xs, xs, np.full(28, xmin), np.full(28, xmax)])
    grid_y = np.concatenate([np.full(28, ymin), np.full(28, ymax), ys, ys])
    lon, lat = WA.inverse(grid_x, grid_y)
    return float(np.min(lon)) - pad, float(np.max(lon)) + pad, float(np.min(lat)) - pad, float(np.max(lat)) + pad


def _orient(values: np.ndarray, lats: np.ndarray, lons: np.ndarray):
    if lats[0] > lats[-1]:
        lats = lats[::-1]
        values = values[::-1, :]
    if lons[0] > lons[-1]:
        lons = lons[::-1]
        values = values[:, ::-1]
    return values, lats, lons


def sample_regular(values, lats, lons, qlat, qlon) -> np.ndarray:
    """Bilinear sample of a regular lat/lon grid. Outside and NaN corners stay empty."""
    values = np.asarray(values, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    qlat = np.asarray(qlat, dtype=np.float64)
    qlon = np.asarray(qlon, dtype=np.float64)
    if lats.size < 2 or lons.size < 2:
        return np.full(np.broadcast(qlat, qlon).shape, np.nan)
    values, lats, lons = _orient(values, lats, lons)
    outside = (qlat < lats[0]) | (qlat > lats[-1]) | (qlon < lons[0]) | (qlon > lons[-1])
    i = np.clip(np.searchsorted(lats, qlat, side="right") - 1, 0, lats.size - 2)
    j = np.clip(np.searchsorted(lons, qlon, side="right") - 1, 0, lons.size - 2)
    t = (qlat - lats[i]) / (lats[i + 1] - lats[i])
    s = (qlon - lons[j]) / (lons[j + 1] - lons[j])
    v00 = values[i, j]
    v01 = values[i, j + 1]
    v10 = values[i + 1, j]
    v11 = values[i + 1, j + 1]
    bad = outside | ~(np.isfinite(v00) & np.isfinite(v01) & np.isfinite(v10) & np.isfinite(v11))
    mixed = v00 * (1.0 - t) * (1.0 - s) + v01 * (1.0 - t) * s + v10 * t * (1.0 - s) + v11 * t * s
    return np.where(bad, np.nan, mixed)


def sample_regular_nearest(values, lats, lons, qlat, qlon) -> np.ndarray:
    values = np.asarray(values)
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    qlat = np.asarray(qlat, dtype=np.float64)
    qlon = np.asarray(qlon, dtype=np.float64)
    if lats.size < 2 or lons.size < 2:
        return np.full(np.broadcast(qlat, qlon).shape, np.nan)
    values, lats, lons = _orient(values, lats, lons)
    outside = (qlat < lats[0]) | (qlat > lats[-1]) | (qlon < lons[0]) | (qlon > lons[-1])
    i = np.clip(np.searchsorted(lats, qlat, side="right") - 1, 0, lats.size - 2)
    j = np.clip(np.searchsorted(lons, qlon, side="right") - 1, 0, lons.size - 2)
    t = (qlat - lats[i]) / (lats[i + 1] - lats[i])
    s = (qlon - lons[j]) / (lons[j + 1] - lons[j])
    i = np.where(t >= 0.5, i + 1, i)
    j = np.where(s >= 0.5, j + 1, j)
    picked = values[i, j].astype(np.float64, copy=False)
    return np.where(outside, np.nan, picked)


def sample_index(values, row, col) -> np.ndarray:
    """Bilinear sample in grid-index space. Used for the native HRRR Lambert grid."""
    values = np.asarray(values, dtype=np.float64)
    row = np.asarray(row, dtype=np.float64)
    col = np.asarray(col, dtype=np.float64)
    nj, ni = values.shape
    if nj < 2 or ni < 2:
        return np.full(row.shape, np.nan)
    outside = (row < 0.0) | (col < 0.0) | (row > nj - 1) | (col > ni - 1)
    i = np.clip(np.floor(row).astype(np.int64), 0, max(nj - 2, 0))
    j = np.clip(np.floor(col).astype(np.int64), 0, max(ni - 2, 0))
    t = np.clip(row - i, 0.0, 1.0)
    s = np.clip(col - j, 0.0, 1.0)
    v00 = values[i, j]
    v01 = values[i, j + 1]
    v10 = values[i + 1, j]
    v11 = values[i + 1, j + 1]
    bad = outside | ~(np.isfinite(v00) & np.isfinite(v01) & np.isfinite(v10) & np.isfinite(v11))
    mixed = v00 * (1.0 - t) * (1.0 - s) + v01 * (1.0 - t) * s + v10 * t * (1.0 - s) + v11 * t * s
    return np.where(bad, np.nan, mixed)


def sample_index_nearest(values, row, col) -> np.ndarray:
    values = np.asarray(values)
    row = np.asarray(row, dtype=np.float64)
    col = np.asarray(col, dtype=np.float64)
    nj, ni = values.shape
    i = np.rint(row).astype(np.int64)
    j = np.rint(col).astype(np.int64)
    ok = (i >= 0) & (i < nj) & (j >= 0) & (j < ni)
    out = np.full(row.shape, np.nan, dtype=np.float64)
    if np.any(ok):
        out[ok] = values[i[ok], j[ok]]
    return out
