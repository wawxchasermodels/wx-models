#!/usr/bin/env python3
"""Dark grey self-drawn basemap shared by the forecast maps (Census + Natural Earth, public domain).
Data: ECMWF open data (CC BY 4.0), NOAA (public domain). Basemap: U.S. Census, Natural Earth (public domain), GSHHG (NOAA, LGPL). Places: GeoNames (CC BY 4.0), Census Gazetteer (public domain).
Part of wx-models (MIT). Renders a static JPEG; no branding."""
""\
\
\
\

from PIL import Image, ImageDraw
import numpy as np
from shapely.geometry import box as sbox

def dark_base(R, P, sc=1.0):
    W, H = R.W, R.H
    lo0, la0, lo1, la1 = P.bounds_ll(); m = 0.3
    bb = sbox(lo0 - m, la0 - m, lo1 + m, la1 + m)
    tol = 0.45 * 360 / 256 / P.k
    prep = lambda g: g.intersection(bb).simplify(tol, preserve_topology=False)
    im = Image.new("RGBA", (W, H), R.WATER + (255,))
    land = Image.new("L", (W, H), 0); dl = ImageDraw.Draw(land)
    for p, g in R.in_frame("ne_10m_admin_0_countries", bb):
        if p["ADM0_A3"] != "USA": R._fill(dl, P, prep(g))
    cg = [prep(g) for _, g in R.in_frame("cb_2023_us_county_500k", bb)]
    for g in cg: R._fill(dl, P, g)
    lk = Image.new("L", (W, H), 0); dk = ImageDraw.Draw(lk)
    for p, g in R.in_frame("ne_10m_lakes", bb): R._fill(dk, P, prep(g))
    land = Image.fromarray(np.minimum(np.array(land), 255 - np.array(lk)))
    im.paste(R.LAND + (255,), (0, 0), land)
    R.LAND_MASK = land
    d = ImageDraw.Draw(im)
    R.BORDERS.clear(); R.BORDERS['county'] = cg; R.BORDERS['state'] = []
    cw = max(2, int(round(2.2 * sc)))
    for g in cg:
        for ln in R._lines(g): d.line(R._np_ring(P, ln.coords), fill=R.COUNTY_LN + (255,), width=cw)
    for name, w in (("ne_10m_admin_1_states_provinces_lines", 4.2), ("ne_10m_admin_0_boundary_lines_land", 3.6)):
        for p, g in R.in_frame(name, bb):
            for ln in R._lines(prep(g)):
                if len(ln.coords) > 1:
                    d.line(R._np_ring(P, ln.coords), fill=R.STATE_LN + (255,), width=max(2, int(round(w * sc))), joint="curve")
                    R.BORDERS['state'].append(ln)
    return im
