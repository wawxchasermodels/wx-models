#!/usr/bin/env python3
"""Pass height correction for the Washington tab maps (Benjamin 10-24-26 10:32 PM PT).

Temperature at a pass label = model value + 3.5 F per 1000 ft x (model ground height at the pass - real summit elevation).
Only temperature products (nbm_map.py lows / highs) use it; gusts, rain, snow and waves never do, towns never do.
Model ground heights are static terrain files in assets/ (built once with --build; public data, no keys):
  NBM  : URMA 2.5 km analysis HGT:surface (NOAA, public domain) - the NDFD 2.5 km grid NBM is downscaled to.
  EPS  : ECMWF IFS 0.25 deg open data step-0 surface geopotential / g (CC BY 4.0) - the ENS shares the IFS 9 km orography.
Summit elevations: WSDOT MountainPass feed, checked against USGS 3DEP (town_pop.PASS_ELEV_FT).
PASS_HEIGHT_CORR=0 turns it off.
"""
import os, sys, json, urllib.request
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
FILES = {"nbm": os.path.join(HERE, "assets", "terrain_ndfd2p5_wa.npz"), "eps": os.path.join(HERE, "assets", "terrain_ecmwf0p25_wa.npz")}
LAPSE_T_F_PER_FT = 3.5 / 1000.0
BOX = (43.5, 51.2, -127.5, -114.5)   # same crop as nbm_map.crop()
_cache = {}


def enabled():
    return os.environ.get("PASS_HEIGHT_CORR", "1") != "0"


def ground_ft(source, lon, lat):
    """Model ground height (ft) at (lon, lat): bilinear on the 0.25 deg grid, nearest point on the 2.5 km grid. None if no file."""
    f = FILES.get(source)
    if not f or not os.path.exists(f): return None
    if source not in _cache: z = np.load(f); _cache[source] = (z["lat"], z["lon"], z["zft"])
    la, lo, Z = _cache[source]
    if la.ndim == 2:
        d = (la - lat) ** 2 + ((lo - lon) * np.cos(np.deg2rad(lat))) ** 2; k = np.unravel_index(np.argmin(d), d.shape)
        return float(Z[k]) if d[k] < 0.03 ** 2 else None
    i = np.searchsorted(la, lat) - 1; j = np.searchsorted(lo, lon) - 1
    y = (lat - la[i]) / (la[i + 1] - la[i]); x = (lon - lo[j]) / (lo[j + 1] - lo[j])
    return float(Z[i, j] * (1 - x) * (1 - y) + Z[i, j + 1] * x * (1 - y) + Z[i + 1, j] * (1 - x) * y + Z[i + 1, j + 1] * x * y)


def corrected(source, name, value, lon, lat):
    """value corrected to the real summit of pass `name`, or the value unchanged (no file, unknown pass, switch off)."""
    import town_pop as TP
    el = TP.PASS_ELEV_FT.get(name)
    if not enabled() or el is None: return value
    g = ground_ft(source, lon, lat)
    return value if g is None else value + LAPSE_T_F_PER_FT * (g - el)


def _get(url, rng=None):
    rq = urllib.request.Request(url, headers={"User-Agent": "wx-models", **({"Range": "bytes=%d-%s" % rng} if rng else {})})
    with urllib.request.urlopen(rq, timeout=120) as r: return r.read()


def build(day="20261024"):
    import eccodes as ec
    u = f"https://noaa-urma-pds.s3.amazonaws.com/urma2p5.{day}/urma2p5.t12z.2dvaranl_ndfd.grb2_wexp"
    idx = _get(u + ".idx").decode().splitlines(); a, b = int(idx[0].split(":")[1]), int(idx[1].split(":")[1]) - 1
    g = ec.codes_new_from_message(_get(u, (a, b))); ni, nj = ec.codes_get(g, "Nx"), ec.codes_get(g, "Ny")
    v = ec.codes_get_values(g).reshape(nj, ni); la = ec.codes_get_array(g, "latitudes").reshape(nj, ni)
    lo = ec.codes_get_array(g, "longitudes").reshape(nj, ni); ec.codes_release(g); lo = np.where(lo > 180, lo - 360, lo)
    m = (la > BOX[0]) & (la < BOX[1]) & (lo > BOX[2]) & (lo < BOX[3]); ii, jj = np.where(m)
    s = (slice(ii.min(), ii.max() + 1), slice(jj.min(), jj.max() + 1))
    np.savez_compressed(FILES["nbm"], lat=la[s].astype("f4"), lon=lo[s].astype("f4"), zft=(v[s] * 3.28084).astype("f4"), src=u)
    e = f"https://data.ecmwf.int/forecasts/{day}/12z/ifs/0p25/oper/{day}120000-0h-oper-fc"
    r = next(json.loads(l) for l in _get(e + ".index").decode().splitlines() if json.loads(l)["param"] == "z")
    g = ec.codes_new_from_message(_get(e + ".grib2", (r["_offset"], r["_offset"] + r["_length"] - 1)))
    ni, nj = ec.codes_get(g, "Ni"), ec.codes_get(g, "Nj"); la0 = ec.codes_get(g, "latitudeOfFirstGridPointInDegrees")
    lo0 = ec.codes_get(g, "longitudeOfFirstGridPointInDegrees"); d = ec.codes_get(g, "iDirectionIncrementInDegrees")
    z = ec.codes_get_values(g).reshape(nj, ni) / 9.80665 * 3.28084; ec.codes_release(g)
    lat = la0 - d * np.arange(nj); lon = (lo0 + d * np.arange(ni) + 180) % 360 - 180; o = np.argsort(lon); lon, z = lon[o], z[:, o]
    lat, z = lat[::-1], z[::-1]
    sl = (lat > BOX[0]) & (lat < BOX[1]); so = (lon > BOX[2]) & (lon < BOX[3])
    np.savez_compressed(FILES["eps"], lat=lat[sl].astype("f8"), lon=lon[so].astype("f8"), zft=z[np.ix_(sl, so)].astype("f4"), src=e)
    print("built", {k: os.path.getsize(f) for k, f in FILES.items()})


if __name__ == "__main__":
    if "--build" in sys.argv: build()
    sys.stdout.flush(); os._exit(0)
