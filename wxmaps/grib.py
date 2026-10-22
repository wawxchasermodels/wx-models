"""Read GRIB2 messages with eccodes and clip them to a lon/lat window."""

from __future__ import annotations

from dataclasses import dataclass, field

import eccodes
import numpy as np


@dataclass
class Msg:
    short: str
    name: str
    units: str
    type_of_level: str
    level: float
    step_range: str
    uv_grid: bool
    values: np.ndarray


@dataclass
class Bag:
    regular: bool
    lats: np.ndarray
    lons: np.ndarray
    messages: list[Msg] = field(default_factory=list)
    lov: float | None = None
    latin1: float | None = None
    latin2: float | None = None

    def find(
        self,
        shorts: set[str],
        *,
        level: float | None = None,
        accum: tuple[int, int] | None = None,
        instant_hour: int | None = None,
    ) -> Msg | None:
        hits: list[Msg] = []
        for msg in self.messages:
            if msg.short.lower() not in shorts:
                continue
            if level is not None and abs(msg.level - level) > 0.2:
                continue
            span = _span(msg.step_range)
            if accum is not None:
                if span != accum:
                    continue
            elif instant_hour is not None:
                if span is not None:
                    continue
                if msg.step_range not in {str(int(instant_hour)), f"{int(instant_hour)}"}:
                    # analysis is sometimes "0"
                    if not (instant_hour == 0 and msg.step_range in {"0", "0-0"}):
                        continue
            hits.append(msg)
        if not hits:
            return None
        # Prefer geopotential height in metres over geopotential.
        hits.sort(key=lambda m: 0 if m.units.lower() in {"gpm", "m"} else 1)
        return hits[0]


def _span(step_range: str) -> tuple[int, int] | None:
    if "-" not in step_range:
        return None
    left, right = step_range.split("-", 1)
    try:
        return int(left), int(right)
    except ValueError:
        return None


def _get(gid, key, default=None):
    try:
        return eccodes.codes_get(gid, key)
    except Exception:
        return default


def _values(gid) -> np.ndarray:
    vals = np.asarray(eccodes.codes_get_values(gid), dtype=np.float32)
    missing = _get(gid, "missingValue")
    if missing is not None:
        vals = np.where(vals == np.float32(missing), np.nan, vals)
    vals[np.abs(vals) > 1.0e19] = np.nan
    return vals


def _regular_coords(gid) -> tuple[np.ndarray, np.ndarray]:
    ni = int(eccodes.codes_get(gid, "Ni"))
    nj = int(eccodes.codes_get(gid, "Nj"))
    lon0 = float(eccodes.codes_get(gid, "longitudeOfFirstGridPointInDegrees"))
    lat0 = float(eccodes.codes_get(gid, "latitudeOfFirstGridPointInDegrees"))
    dlon = abs(float(eccodes.codes_get(gid, "iDirectionIncrementInDegrees")))
    dlat = abs(float(eccodes.codes_get(gid, "jDirectionIncrementInDegrees")))
    if int(_get(gid, "iScansNegatively", 0)):
        dlon = -dlon
    raw = lon0 + np.arange(ni, dtype=np.float64) * dlon
    lons = (raw + 180.0) % 360.0 - 180.0
    if int(_get(gid, "jScansPositively", 0)):
        lats = lat0 + np.arange(nj, dtype=np.float64) * dlat
    else:
        lats = lat0 - np.arange(nj, dtype=np.float64) * dlat
    return lats, lons


def _lambert_coords(gid) -> tuple[np.ndarray, np.ndarray]:
    ni = int(eccodes.codes_get(gid, "Ni"))
    nj = int(eccodes.codes_get(gid, "Nj"))
    lats = np.asarray(eccodes.codes_get_array(gid, "latitudes"), dtype=np.float32).reshape(nj, ni)
    lons = np.asarray(eccodes.codes_get_array(gid, "longitudes"), dtype=np.float32).reshape(nj, ni)
    lons = np.where(lons > 180.0, lons - 360.0, lons).astype(np.float32)
    return lats, lons


def read_grib(path: str) -> Bag | None:
    messages: list[Msg] = []
    bag: Bag | None = None
    with open(path, "rb") as handle:
        while True:
            gid = eccodes.codes_grib_new_from_file(handle)
            if gid is None:
                break
            try:
                ni = int(_get(gid, "Ni", 0) or 0)
                nj = int(_get(gid, "Nj", 0) or 0)
                vals = _values(gid)
                if ni * nj != vals.size or ni == 0:
                    continue
                vals = vals.reshape(nj, ni)
                if bag is None:
                    grid = str(_get(gid, "gridType", ""))
                    regular = grid == "regular_ll"
                    if regular:
                        lats, lons = _regular_coords(gid)
                    else:
                        lats, lons = _lambert_coords(gid)
                    bag = Bag(
                        regular=regular,
                        lats=lats,
                        lons=lons,
                        lov=_maybe_float(_get(gid, "LoVInDegrees")),
                        latin1=_maybe_float(_get(gid, "Latin1InDegrees")),
                        latin2=_maybe_float(_get(gid, "Latin2InDegrees")),
                    )
                if vals.shape != _grid_shape(bag):
                    continue
                messages.append(
                    Msg(
                        short=str(_get(gid, "shortName", "")),
                        name=str(_get(gid, "name", "")),
                        units=str(_get(gid, "units", "")),
                        type_of_level=str(_get(gid, "typeOfLevel", "")),
                        level=float(_get(gid, "level", 0) or 0),
                        step_range=str(_get(gid, "stepRange", "")),
                        uv_grid=bool(int(_get(gid, "uvRelativeToGrid", 0) or 0)),
                        values=vals,
                    )
                )
            finally:
                eccodes.codes_release(gid)
    if bag is None:
        return None
    bag.messages = messages
    return bag


def _maybe_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _grid_shape(bag: Bag) -> tuple[int, int]:
    if bag.lats.ndim == 1:
        return (bag.lats.shape[0], bag.lons.shape[0])
    return bag.lats.shape


def clip_bag(bag: Bag, west: float, east: float, south: float, north: float) -> Bag:
    if bag.regular:
        lat_i = np.where((bag.lats >= south) & (bag.lats <= north))[0]
        lon_i = np.where((bag.lons >= west) & (bag.lons <= east))[0]
        if len(lat_i) == 0 or len(lon_i) == 0:
            raise ValueError("regular grid does not cover the window")
        if lat_i[-1] - lat_i[0] + 1 != len(lat_i) or lon_i[-1] - lon_i[0] + 1 != len(lon_i):
            raise ValueError("longitude window is not contiguous on this grid")
        rs, re = int(lat_i[0]), int(lat_i[-1]) + 1
        cs, ce = int(lon_i[0]), int(lon_i[-1]) + 1
        lats = bag.lats[rs:re]
        lons = bag.lons[cs:ce]
        messages = [
            Msg(**{**msg.__dict__, "values": msg.values[rs:re, cs:ce]})
            for msg in bag.messages
        ]
        return Bag(True, lats, lons, messages, bag.lov, bag.latin1, bag.latin2)

    row = np.where(np.any((bag.lats >= south) & (bag.lats <= north), axis=1))[0]
    col = np.where(np.any((bag.lons >= west) & (bag.lons <= east), axis=0))[0]
    if len(row) == 0 or len(col) == 0:
        raise ValueError("projected grid does not cover the window")
    rs, re = int(row[0]), int(row[-1]) + 1
    cs, ce = int(col[0]), int(col[-1]) + 1
    messages = [Msg(**{**msg.__dict__, "values": msg.values[rs:re, cs:ce]}) for msg in bag.messages]
    return Bag(
        False,
        bag.lats[rs:re, cs:ce],
        bag.lons[rs:re, cs:ce],
        messages,
        bag.lov,
        bag.latin1,
        bag.latin2,
    )


def merge_bags(bags: list[Bag]) -> Bag | None:
    bags = [b for b in bags if b and b.messages]
    if not bags:
        return None
    base = bags[0]
    messages = list(base.messages)
    for extra in bags[1:]:
        for msg in extra.messages:
            if msg.values.shape == messages[0].values.shape:
                messages.append(msg)
    base.messages = messages
    return base


def to_earth(u: np.ndarray, v: np.ndarray, lons: np.ndarray, bag: Bag) -> tuple[np.ndarray, np.ndarray]:
    """Rotate Lambert grid winds to eastward / northward components."""
    if bag.lov is None or bag.latin1 is None:
        return u, v
    latin2 = bag.latin1 if bag.latin2 is None else bag.latin2
    lat1 = np.deg2rad(bag.latin1)
    lat2 = np.deg2rad(latin2)
    if abs(bag.latin1 - latin2) < 1e-3:
        n = np.sin(lat1)
    else:
        n = np.log(np.cos(lat1) / np.cos(lat2)) / np.log(
            np.tan(np.pi / 4 + lat2 / 2) / np.tan(np.pi / 4 + lat1 / 2)
        )
    angle = n * (np.deg2rad(lons) - np.deg2rad(bag.lov))
    ue = u * np.cos(angle) + v * np.sin(angle)
    ve = -u * np.sin(angle) + v * np.cos(angle)
    return ue.astype(np.float32), ve.astype(np.float32)
