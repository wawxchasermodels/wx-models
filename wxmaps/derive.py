"""Turn a clipped GRIB bag into chart payloads."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from wxmaps.grib import Bag, Msg, to_earth

MS_TO_MPH = 2.2369362920544
MS_TO_KT = 1.9438444924406
M_TO_IN = 39.37007874015748
G = 9.80665
OMEGA = 7.2921159e-5


@dataclass
class Payload:
    field_id: str
    title: str
    unit: str
    subtitle: str
    scale: str | None
    values: np.ndarray | None
    u: np.ndarray | None
    v: np.ndarray | None
    contours: np.ndarray | None
    contour_kind: str
    categories: np.ndarray | None
    mask_below: float | None
    lats: np.ndarray
    lons: np.ndarray
    regular: bool
    lov: float | None = None
    latin1: float | None = None
    latin2: float | None = None

    def clip(self, west: float, east: float, south: float, north: float) -> "Payload":
        if self.regular:
            lat_i = np.where((self.lats >= south) & (self.lats <= north))[0]
            lon_i = np.where((self.lons >= west) & (self.lons <= east))[0]
            if len(lat_i) < 2 or len(lon_i) < 2:
                raise ValueError("region clip missed the grid")
            rs, re = int(lat_i[0]), int(lat_i[-1]) + 1
            cs, ce = int(lon_i[0]), int(lon_i[-1]) + 1
            sl = np.s_[rs:re, cs:ce]
            return Payload(
                self.field_id, self.title, self.unit, self.subtitle, self.scale,
                None if self.values is None else self.values[sl],
                None if self.u is None else self.u[sl],
                None if self.v is None else self.v[sl],
                None if self.contours is None else self.contours[sl],
                self.contour_kind,
                None if self.categories is None else self.categories[sl],
                self.mask_below,
            self.lats[rs:re],
            self.lons[cs:ce],
            True,
            self.lov,
            self.latin1,
            self.latin2,
        )
        row = np.where(np.any((self.lats >= south) & (self.lats <= north), axis=1))[0]
        col = np.where(np.any((self.lons >= west) & (self.lons <= east), axis=0))[0]
        if len(row) < 2 or len(col) < 2:
            raise ValueError("region clip missed the grid")
        rs, re = int(row[0]), int(row[-1]) + 1
        cs, ce = int(col[0]), int(col[-1]) + 1
        sl = np.s_[rs:re, cs:ce]
        return Payload(
            self.field_id, self.title, self.unit, self.subtitle, self.scale,
            None if self.values is None else self.values[sl],
            None if self.u is None else self.u[sl],
            None if self.v is None else self.v[sl],
            None if self.contours is None else self.contours[sl],
            self.contour_kind,
            None if self.categories is None else self.categories[sl],
            self.mask_below,
            self.lats[sl],
            self.lons[sl],
            False,
            self.lov,
            self.latin1,
            self.latin2,
        )


def _span(step_range: str) -> tuple[int, int] | None:
    if "-" not in step_range:
        return None
    left, right = step_range.split("-", 1)
    try:
        return int(left), int(right)
    except ValueError:
        return None


def _usable(msg: Msg | None) -> bool:
    if msg is None:
        return False
    finite = msg.values[np.isfinite(msg.values)]
    if finite.size < 10:
        return False
    return float(np.nanmax(finite) - np.nanmin(finite)) > 1e-5


def _find_total(bag: Bag, shorts: set[str], hour: int) -> Msg | None:
    exact = bag.find(shorts, accum=(0, hour))
    if _usable(exact):
        return exact
    for msg in bag.messages:
        if msg.short.lower() not in shorts or not _usable(msg):
            continue
        span = _span(msg.step_range)
        if span == (0, hour):
            return msg
    if hour == 0:
        return None
    return None


def _water_inches(msg: Msg) -> np.ndarray:
    units = msg.units.lower().replace(" ", "")
    values = msg.values.astype(np.float32)
    if "kg" in units or units in {"mm", "kgm**-2", "kgm-2"}:
        return values / 25.4
    return values * np.float32(M_TO_IN)


def _fahrenheit(msg: Msg) -> np.ndarray:
    units = msg.units.lower()
    values = msg.values.astype(np.float32)
    if units.startswith("k"):
        return (values - np.float32(273.15)) * np.float32(9.0 / 5.0) + np.float32(32.0)
    if "c" in units:
        return values * np.float32(9.0 / 5.0) + np.float32(32.0)
    return values


def _hpa(msg: Msg) -> np.ndarray:
    values = msg.values.astype(np.float32)
    sample = values[np.isfinite(values)]
    if sample.size and np.nanmedian(sample) > 2000:
        return values / np.float32(100.0)
    return values


def _height_m(msg: Msg) -> np.ndarray:
    values = msg.values.astype(np.float32)
    if "s**-2" in msg.units.lower() or "s-2" in msg.units.lower():
        return values / np.float32(G)
    return values


def _ptype_codes(bag: Bag) -> np.ndarray | None:
    raw = bag.find({"ptype"})
    if _usable(raw) or (raw is not None and np.isfinite(raw.values).any()):
        codes = np.rint(raw.values).astype(np.int16)
        cat = np.zeros(codes.shape, dtype=np.int16)
        cat[np.isin(codes, [1, 2, 11])] = 1
        cat[np.isin(codes, [5, 6])] = 2
        cat[np.isin(codes, [7, 8, 9])] = 3
        cat[np.isin(codes, [3, 12])] = 4
        if np.any(cat > 0):
            return cat
    shape = bag.messages[0].values.shape
    snow = bag.find({"csnow"})
    rain = bag.find({"crain"})
    frz = bag.find({"cfrzr"})
    ice = bag.find({"cicep"})
    if not any(m is not None for m in (snow, rain, frz, ice)):
        return None
    cat = np.zeros(shape, dtype=np.int16)
    if rain is not None:
        cat[rain.values > 0.5] = 1
    if snow is not None:
        cat[snow.values > 0.5] = 2
    if snow is not None and rain is not None:
        cat[(snow.values > 0.5) & (rain.values > 0.5)] = 3
    if ice is not None:
        cat[ice.values > 0.5] = 3
    if frz is not None:
        cat[frz.values > 0.5] = 4
    return cat


def _abs_vorticity(bag: Bag) -> np.ndarray | None:
    vo = bag.find({"vo", "absv"}, level=500)
    if vo is not None and _usable(vo):
        if vo.short.lower() == "vo" and bag.regular:
            lat = np.deg2rad(bag.lats)
            f = (2 * OMEGA * np.sin(lat)).astype(np.float32)
            return vo.values + f[:, None]
        return vo.values
    if not bag.regular:
        return None
    u = bag.find({"u"}, level=500)
    v = bag.find({"v"}, level=500)
    if not (_usable(u) and _usable(v)):
        return None
    uu, vv = u.values, v.values
    if u.uv_grid:
        uu, vv = to_earth(uu, vv, bag.lons, bag)
    lat = np.deg2rad(bag.lats.astype(np.float64))
    lon = np.deg2rad(bag.lons.astype(np.float64))
    dlat = np.gradient(lat)
    dlon = np.gradient(lon)
    radius = 6371000.0
    du_dy = np.gradient(uu.astype(np.float64), axis=0) / (radius * dlat[:, None])
    dv_dx = np.gradient(vv.astype(np.float64), axis=1) / (radius * np.cos(lat)[:, None] * dlon[None, :])
    f = 2 * OMEGA * np.sin(lat)
    return (dv_dx - du_dy + f[:, None]).astype(np.float32)


def _base(bag: Bag, **kwargs) -> Payload:
    defaults = {
        "u": None,
        "v": None,
        "contours": None,
        "contour_kind": "none",
        "categories": None,
        "mask_below": None,
        "values": None,
    }
    defaults.update(kwargs)
    return Payload(
        lats=bag.lats,
        lons=bag.lons,
        regular=bag.regular,
        lov=bag.lov,
        latin1=bag.latin1,
        latin2=bag.latin2,
        **defaults,
    )


def build_payloads(bag: Bag, model_id: str, hour: int) -> list[Payload]:
    if not bag.messages:
        return []
    out: list[Payload] = []

    t2 = bag.find({"2t"}, level=2)
    if _usable(t2):
        out.append(_base(
            bag, field_id="t2m", title="2 m temperature", unit="°F",
            subtitle="32°F is the light-blue step", scale="temp_f", values=_fahrenheit(t2),
        ))
    d2 = bag.find({"2d"}, level=2)
    if _usable(d2):
        out.append(_base(
            bag, field_id="d2m", title="2 m dewpoint", unit="°F",
            subtitle="Same freezing rule as temperature", scale="temp_f", values=_fahrenheit(d2),
        ))

    u10 = bag.find({"10u"}, level=10)
    v10 = bag.find({"10v"}, level=10)
    if _usable(u10) and _usable(v10):
        speed = np.hypot(u10.values, v10.values) * np.float32(MS_TO_MPH)
        ue, ve = u10.values, v10.values
        if u10.uv_grid or v10.uv_grid:
            ue, ve = to_earth(ue, ve, bag.lons, bag)
        out.append(_base(
            bag, field_id="wind10", title="10 m wind", unit="mph",
            subtitle="Shading is speed. Barbs are earth-relative, in knots.",
            scale="wind_mph", values=speed,
            u=ue * np.float32(MS_TO_KT), v=ve * np.float32(MS_TO_KT),
        ))

    gust = None
    for short in ("10fg", "10fg3", "10fg6", "gust"):
        gust = bag.find({short})
        if _usable(gust):
            break
    if _usable(gust):
        note = "Maximum since the previous saved step." if model_id in {"ecmwf", "aifs"} else "Surface gust."
        out.append(_base(
            bag, field_id="gust10", title="10 m gust", unit="mph", subtitle=note,
            scale="wind_mph", values=gust.values * np.float32(MS_TO_MPH),
        ))

    msl = None
    for short in ("msl", "prmsl", "mslma"):
        msl = bag.find({short})
        if _usable(msl):
            break
    categories = _ptype_codes(bag)
    if _usable(msl):
        title = "MSLP and precip type" if categories is not None else "Mean sea-level pressure"
        note = "Contours every 4 hPa."
        if categories is not None:
            note += " Color is precip type: green rain, blue snow, pink mix, magenta freezing rain."
        out.append(_base(
            bag, field_id="mslp", title=title, unit="hPa", subtitle=note,
            scale=None, contours=_hpa(msl), contour_kind="mslp", categories=categories,
        ))

    refc = bag.find({"refc"})
    if _usable(refc):
        out.append(_base(
            bag, field_id="radar", title="Composite reflectivity", unit="dBZ",
            subtitle="Values under 5 dBZ are left blank.",
            scale="refc", values=refc.values, mask_below=5,
        ))
    else:
        rate = bag.find({"tprate", "prate"}, instant_hour=hour)
        if rate is None:
            rate = bag.find({"tprate", "prate"})
        if _usable(rate) and "-" not in rate.step_range:
            out.append(_base(
                bag, field_id="radar", title="Precipitation rate", unit="in/h",
                subtitle="Instantaneous rate.",
                scale="rate_in", values=rate.values * np.float32(3600.0 / 25.4), mask_below=0.01,
            ))

    total = _find_total(bag, {"tp", "apcp"}, hour)
    if total is not None:
        out.append(_base(
            bag, field_id="precip", title="Total precipitation", unit="in",
            subtitle="Accumulated since the model run started.",
            scale="precip_in", values=_water_inches(total), mask_below=0.01,
        ))
    elif hour == 0:
        shape = bag.messages[0].values.shape
        out.append(_base(
            bag, field_id="precip", title="Total precipitation", unit="in",
            subtitle="Accumulated since the model run started.",
            scale="precip_in", values=np.zeros(shape, dtype=np.float32), mask_below=0.01,
        ))

    if model_id == "gfs":
        depth = bag.find({"sde", "snod"})
        if _usable(depth):
            out.append(_base(
                bag, field_id="snow", title="Snow depth", unit="in",
                subtitle="Model snow depth on the ground, not a 10:1 accumulation.",
                scale="snow_in", values=_water_inches(depth) if "kg" in depth.units.lower() else depth.values * np.float32(M_TO_IN),
                mask_below=0.1,
            ))
    else:
        snow = _find_total(bag, {"sf", "weasd", "sdwe"}, hour)
        if snow is not None:
            out.append(_base(
                bag, field_id="snow", title="Snowfall", unit="in",
                subtitle="10:1 ratio from accumulated snow-water equivalent.",
                scale="snow_in", values=_water_inches(snow) * np.float32(10.0), mask_below=0.1,
            ))
        elif hour == 0:
            shape = bag.messages[0].values.shape
            out.append(_base(
                bag, field_id="snow", title="Snowfall", unit="in",
                subtitle="10:1 ratio from accumulated snow-water equivalent.",
                scale="snow_in", values=np.zeros(shape, dtype=np.float32), mask_below=0.1,
            ))

    if model_id == "ecmwf":
        cape = bag.find({"mucape"})
        cape_title = "MUCAPE"
        cape_note = "Most-unstable CAPE. The open data does not include surface-based CAPE."
    else:
        cape = bag.find({"cape"}, level=0)
        cape_title = "SBCAPE"
        cape_note = "Surface-based CAPE."
    if model_id != "aifs" and _usable(cape):
        out.append(_base(
            bag, field_id="cape", title=cape_title, unit="J/kg", subtitle=cape_note,
            scale="cape", values=cape.values, mask_below=100,
        ))

    gh = bag.find({"gh"}, level=500)
    if not _usable(gh):
        gh = bag.find({"z"}, level=500)
    vort = _abs_vorticity(bag)
    if _usable(gh) and vort is not None and np.isfinite(vort).sum() > 10:
        out.append(_base(
            bag, field_id="h500", title="500 mb height and vorticity", unit="1e-5/s",
            subtitle="Fill is absolute vorticity. Contours are height in decameters. The 540 line is marked.",
            scale="vort", values=vort * np.float32(1e5),
            contours=_height_m(gh), contour_kind="height",
        ))

    t850 = bag.find({"t"}, level=850)
    if _usable(t850):
        out.append(_base(
            bag, field_id="t850", title="850 mb temperature", unit="°F",
            subtitle="32°F is the light-blue step, the same rule as the surface.",
            scale="temp_f", values=_fahrenheit(t850),
        ))
    return out
