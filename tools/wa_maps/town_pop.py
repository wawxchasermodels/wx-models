#!/usr/bin/env python3
"""Town lists, label priorities and populations (GeoNames, CC BY 4.0) for the forecast maps.
Data: ECMWF open data (CC BY 4.0), NOAA (public domain). Basemap: U.S. Census, Natural Earth (public domain), GSHHG (NOAA, LGPL). Places: GeoNames (CC BY 4.0), Census Gazetteer (public domain).
Part of wx-models (MIT). Renders a static JPEG; no branding."""
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
from render_core import asset as _asset
""\
\
\
\
\
\
\

import os
SRC = _asset("us_places_geonames.tsv")
TIERS = [(150000, 38, 39, 5, 10), (50000, 32, 35, 4, 9),
         (10000, 28, 33, 4, 8), (0, 23, 27, 3, 6)]
_pop = None
def pops():
    global _pop
    if _pop is None:
        _pop = {}
        for l in open(SRC, encoding="utf-8"):
            c = l.rstrip("\n").split("\t")
            if len(c) >= 5 and c[3] == "WA" and c[4].isdigit() and not c[5].startswith("PPLS"):
                _pop[c[0]] = max(_pop.get(c[0], 0), int(c[4]))
    return _pop
def pop(name): return pops().get(name, 0)
def tier(name, is_pass=False):
    p = 0 if (is_pass or name in globals().get("SMALL", ())) else pop(name)
    for i, (lo, n, v, s, r) in enumerate(TIERS):
        if p >= lo: return (i + 1, n, v, s, r)

ALWAYS_MIN = 50000
NOT_CITIES = {"South Hill", "City of Sammamish", "Parkland", "East Hill-Meridian"}

SOFT = {"Shoreline", "Sammamish", "Burien"}
def always(name, is_pass=False): return (not is_pass) and pop(name) >= ALWAYS_MIN and name not in SOFT and name not in NOT_CITIES
def always_list(): return sorted([n for n, p in pops().items() if p >= ALWAYS_MIN and n not in NOT_CITIES and n not in SOFT], key=lambda n: -pop(n))

MUST = {"Seattle", "Spokane", "Tacoma", "Vancouver", "Bellevue"}

REQUESTED = ["Olympia", "Federal Way", "Mount Vernon", "Ellensburg", "Arlington", "Monroe", "Enumclaw", "Friday Harbor"]
LOCKED = {"Seattle": "above", "Tacoma": "below", "Everett": "above", "Oak Harbor": "above", "Bellevue": "below"}
DROP = {"Gold Bar", "La Conner", "Yacolt", "Amboy"}

import math as _m
NUDGE = [(0, 0)] + [(round(r * _m.cos(a * _m.pi / 6)), round(r * 0.8 * _m.sin(a * _m.pi / 6))) for r in (10, 18, 26, 34, 44) for a in range(12)]

PREF = {"Seattle": (-10, -38), "Bellevue": (14, 38), "Tacoma": (0, 68), "Federal Way": (-60, 7), "Everett": (0, -10), "Kent": (20, 10)}
def nudges(name):
    px, py = PREF.get(name, (0, 0))
    return ([(px, py)] if (px, py) != (0, 0) else []) + sorted(NUDGE, key=lambda t: (t[0] - px) ** 2 + (t[1] - py) ** 2)

LEADER = {}
TINY = set(); TINY_PX = (17, 19)
SMALL = set()

REGION_BOX = {"west": (-124.78, 45.56, -121.0, 49.0),
              "east": (-121.05, 45.54, -116.91, 49.0)}
REGION_LABEL = {"west": (-125.0, 45.4, -121.0, 49.1), "east": (-121.0, 45.4, -116.80, 49.1)}
REGION_TOWNS = {
    "west": ["Neah Bay", "La Push", "Sekiu", "Clallam Bay", "Joyce", "Carlsborg", "Port Hadlock", "Quilcene", "Brinnon", "Hoodsport",
             "Union", "Allyn", "Belfair", "Seabeck", "Silverdale", "Kingston", "Hansville", "Vashon", "Point Roberts", "Birch Bay", "Maple Falls",
             "Glacier", "Rockport", "Marblemount", "Amanda Park", "Neilton", "Humptulips", "Taholah", "Moclips", "Copalis Beach", "Ocean City",
             "Satsop", "Grayland", "Tokeland", "Bay Center", "Ocean Park", "Chinook", "Naselle", "Grays River", "Rosburg", "Skamokawa Valley",
             "Cougar", "Amboy", "Packwood", "Randle", "Mineral", "Elbe", "Ashford"],
    "east": ["Mazama", "Plain", "Peshastin", "Manson", "Malott", "Methow", "Loomis", "Conconully", "Riverside", "Curlew", "Danville", "Orient",
             "Inchelium", "Keller", "Addy", "Valley", "Clayton", "Loon Lake", "Four Lakes", "Ronald", "Easton", "Thorp", "Vantage", "Beverly",
             "Desert Aire", "Basin City", "White Swan", "Cowiche", "Gleed", "Nile", "Tampico"],
}
REGION_POINTS = {"La Push": (-124.6366, 47.9076), "Mazama": (-120.4040, 48.5926), "Plain": (-120.6587, 47.7637),
                 "Peshastin": (-120.6046, 47.5715), "Randle": (-121.9568, 46.5357), "Joyce": (-123.7310, 48.1370),
                 "Port Hadlock": (-122.7914, 48.0328),
                 "Verlot": (-121.78, 48.09)}
REGION_NAME = {"west": "Western Washington", "east": "Eastern Washington"}

REGION_TIERS = [(150000, 34, 36, 5, 10), (50000, 29, 32, 4, 9), (10000, 25, 29, 4, 8), (0, 21, 24, 3, 6)]

REGION_DROP = {"west": {"Gold Bar", "La Conner", "Yacolt", "Amboy"}, "east": {"Gold Bar", "La Conner", "Yacolt", "Amboy", "Kent", "Granite Falls", "Lake Stevens"}}
REGION_REQUESTED = {"west": ["Kent", "Lake Stevens", "North Bend", "Granite Falls", "Verlot", "Duvall"]}
REGION_PREF = {"west": {"Marysville": (-40, 0), "Lake Stevens": (64, 20), "Arlington": (0, -12), "Granite Falls": (40, 4),
                        "Darrington": (24, -24), "Verlot": (16, -50)}}
REGION_PASSES_OPTIONAL = {"west"}
REGION_FIRST = {}

_geo = None
def geo_pts():
    global _geo
    if _geo is None:
        _geo = {}
        for l in open(SRC, encoding="utf-8"):
            c = l.rstrip("\n").split("\t")
            if len(c) >= 5 and c[3] == "WA" and not (len(c) > 5 and c[5].startswith("PPLS")):
                try: _geo.setdefault(c[0], []).append((float(c[2]), float(c[1])))
                except ValueError: pass
    return _geo
def real_point(name, census):
    g = geo_pts().get(name)
    if not g: return census
    km = lambda q: _m.hypot((q[0] - census[0]) * 111.32 * _m.cos(_m.radians(census[1])), (q[1] - census[1]) * 110.57)
    best = min(g, key=km)
    return best if km(best) <= 20 else census
REGION_VAL_UNDER = {"west": {"Lake Stevens": "Lake"}}
TIGHT_FIRST = ["Friday Harbor", "Oak Harbor"]
TIGHT_PROTECT = {None: ["Port Angeles", "Bremerton", "Longview"], "west": ["Bremerton", "Longview", "Burien", "Duvall", "Battle Ground"]}
MUST_WIDE = {"Vancouver"}

OFFICIAL_PIN = {
    "Seattle": ("SEA", -122.3144, 47.4447), "Port Angeles": ("CLM", -123.5066, 48.1220), "Spokane": ("GEG", -117.5280, 47.6216),
    "Yakima": ("YKM", -120.5441, 46.5682), "Wenatchee": ("EAT", -120.2070, 47.3990), "Olympia": ("OLM", -122.9033, 46.9733),
    "Bellingham": ("BLI", -122.5375, 48.7927), "Pasco": ("PSC", -119.1190, 46.2647), "Walla Walla": ("ALW", -118.2890, 46.0948),
    "Moses Lake": ("MWH", -119.3191, 47.2086), "Vancouver": ("VUO", -122.6565, 45.6204), "Everett": ("PAE", -122.2816, 47.9070),
    "Pullman": ("PUW", -117.1096, 46.7439), "Ellensburg": ("ELN", -120.5307, 47.0330), "Omak": ("OMK", -119.5181, 48.4644),
    "Aberdeen": ("HQM", -123.9366, 46.9712),

    "Spokane Valley": ("SFF", -117.3226, 47.6828),
    "Deer Park": ("DEW", -117.4211, 47.9689),
    "Clarkston": ("LWS", -117.0154, 46.3745),
    "Tacoma": ("TIW", -122.5761, 47.2675)}

def value_point(name, census):
    p = OFFICIAL_PIN.get(name)
    return (p[1], p[2]) if p else real_point(name, census)
