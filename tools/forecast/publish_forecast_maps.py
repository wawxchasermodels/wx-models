#!/usr/bin/env python3
"""Gather the latest forecast maps + meteograms into the viewer's manifest.json.

  python tools/forecast/publish_forecast_maps.py --batch-root .site_batch --no-adhoc
      # rebuild $SITE_DIR/manifest.json + $SITE_DIR/maps/ (default web/forecast); the workflow's deploy job uploads it

Sources:
  * $SITE_BATCH/<cycle>/<tab>/<period>/<view>/<valid>/final.jpg  (render_forecast_batch.py, aifs_maps.py,
    temp_maps.py, with site_frame.json sidecars) -- exact tab/period/view/model.
  * optional hand-made {precip,snow,wave,gusts,nbm}_*/ *final.jpg folders under $WX_EXTRAS (classified from the
    folder name + run.json); skipped when unset or with --no-adhoc.
  * $SITE_DIR/meteograms/made.json (meteograms.py).
Only frames whose window ends within --max-age-hours of now (default 36) are kept; for each tab/period/view
the newest run wins. Images are written as web JPEGs (long side 1600 px) under forecast/maps/.
No secrets live here; uploading is done by the workflow, not by this script.
"""
import argparse, datetime as dt, glob, hashlib, json, os, re, shutil, subprocess, sys
from zoneinfo import ZoneInfo
from PIL import Image

PT = ZoneInfo("America/Los_Angeles")
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("SITE_DIR", os.path.normpath(os.path.join(HERE, "..", "..", "web", "forecast")))
EXTRAS = os.environ.get("WX_EXTRAS", "")

# One switch for where meteogram charts live (file-count plan A7): METEO_BASE unset or "meteograms/" = inside this site
# (merged, the default); METEO_BASE="m/" = on the second Pages project, reached through the same-origin /m/ proxy function
# (web/meteo-proxy/functions/m/[[path]].js). Links stay relative, so merging back is just unsetting METEO_BASE.
METEO_BASE = os.environ.get("METEO_BASE", "meteograms/")


def meteo_src(src):
    return METEO_BASE + src[len("meteograms/"):] if src.startswith("meteograms/") else src


def run_label(model, cycle):
    """'EPS 00Z run 10-23 (5 PM PT)': the run's UTC hour plus its PT start, same as the chart and map headers (B9)."""
    c = dt.datetime.strptime(cycle[:10], "%Y%m%d%H").replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo("America/Los_Angeles"))
    return f"{model} {cycle[8:10]}Z run {c:%-m-%-d} ({c:%-I %p} PT)"


P_ACC_RAIN = [("1h", "1-hour (HRRR)"), ("step", "Each 3 h step"), ("6h", "6-hour"), ("12h", "12-hour"), ("24h", "24-hour"),
              ("48h", "48-hour"), ("total", "Total from start")]
P_ACC = [("step", "Each 3 h step"), ("6h", "6-hour"), ("12h", "12-hour"), ("24h", "24-hour"),
         ("48h", "48-hour"), ("total", "Total from start")]
WA_VIEWS = [("full", "Full state"), ("west", "Western WA"), ("east", "Eastern WA")]
# Shown under the model pills: source, finest step, licence/credit (NOAA data is public domain, no credit needed).
MODEL_NOTES = {
    "ECMWF 9 km": "ECMWF IFS open data 0.1\u00b0. Menu maps every 6 h to 240 h; Washington tabs 3 h steps to 144 h, then 6 h. Data: ECMWF, CC BY 4.0.",
    "NBM": "NOAA National Blend of Models, 2.5 km. Finest step 1 h to 36 h; site steps are 3 h. Public domain.",
    "GFS": "NOAA GFS 0.25\u00b0, 00Z/12Z runs. On this site: 500 mb anomaly and sea-level pressure only, every 6 h to 240 h. Public domain.",
    "EPS mean": "ECMWF ensemble mean of 50 members, 0.25\u00b0. 3 h steps to 144 h, then 6 h. Snow uses a 10:1 ratio. Data: ECMWF, CC BY 4.0.",
    "EPS 90th pct": "90th percentile of the 50 ECMWF ensemble members: a high-end amount only 1 in 10 members exceeds. Data: ECMWF, CC BY 4.0.",
    "HRRR": "NOAA HRRR 3 km, hourly steps to 48 h. Public domain.",
    "RRFS": "NOAA RRFS 3 km, hourly steps to 84 h. Public domain.",
    "AIFS": "ECMWF AIFS machine-learning model, 0.25\u00b0, 6 h steps (open data to 360 h; site frames every 6 h to 240 h). Data: ECMWF, CC BY 4.0.",
    "EPS": "ECMWF IFS ensemble (ENS), 50 members, 0.25\u00b0. Frames every 6 h to 240 h. Data: ECMWF, CC BY 4.0.",
    "AIFS ENS": "ECMWF AIFS machine-learning ensemble, 50 members, 0.25\u00b0, 6 h steps (open data to 360 h; site frames to 240 h). Data: ECMWF, CC BY 4.0.",
}
# Menu v2 (plan/menu_v2.md): each tab sits in a dropdown section (group) under a sub-heading. Order inside TABS = order in the menu.
MENU = {
    "rain": ("wa", "Washington", "Rain & snow"), "snow": ("wa", "Washington", "Rain & snow"), "bcrain": ("wa", "Washington", "British Columbia"),
    "gusts": ("wa", "Washington", "Wind"), "lows": ("wa", "Washington", "Temperature"), "highs": ("wa", "Washington", "Temperature"),
    "waves": ("wa", "Washington", "Coast"),
    "gust10": ("ground", "Ground level", "Wind"), "peakgust": ("ground", "Ground level", "Wind"),
    "feels": ("ground", "Ground level", "Temperature"), "td2m": ("ground", "Ground level", "Humidity"),
    "t925": ("aloft", "Aloft", "Temperature & barbs"), "t700": ("aloft", "Aloft", "Temperature & barbs"),
    "t500": ("aloft", "Aloft", "Temperature & barbs"), "t300": ("aloft", "Aloft", "Temperature & barbs"),
    "mslpptype": ("combo", "Combo maps", "Pressure + precip"),
    "snowkuch": ("precip", "Precip & snow", "Snow & ice"), "snow10": ("precip", "Precip & snow", "Snow & ice"),
    "snowk24": ("precip", "Precip & snow", "Snow & ice"), "snowrate": ("precip", "Precip & snow", "Snow & ice"),
    "frzr": ("precip", "Precip & snow", "Snow & ice"), "qpf": ("precip", "Precip & snow", "Precip"),
    "ivt": ("aloft", "Aloft", "Moisture transport"), "pw": ("aloft", "Aloft", "Moisture transport"), "pwanom": ("aloft", "Aloft", "Moisture transport"),
    "tcc": ("ground", "Ground level", "Sky, fog & visibility"), "ir": ("ground", "Ground level", "Sky, fog & visibility"),
    "vis": ("ground", "Ground level", "Sky, fog & visibility"), "fog": ("ground", "Ground level", "Sky, fog & visibility"),
    "w850": ("aloft", "Aloft", "Jet & winds"), "w250": ("aloft", "Aloft", "Jet & winds"), "thick": ("aloft", "Aloft", "Heights & thickness"),
    "t2m": ("ground", "Ground level", "Temperature"), "t2manom": ("ground", "Ground level", "Temperature"), "aifsmslp": ("ground", "Ground level", "Pressure"),
    "t850": ("aloft", "Aloft", "Temperature & barbs"), "aifs500": ("aloft", "Aloft", "Heights & thickness"),
    "mslpprecip": ("combo", "Combo maps", "Pressure + precip"), "aifswind": ("combo", "Combo maps", "Pressure + wind"),
    "elows": ("combo", "Combo maps", "Ensembles"), "e500": ("combo", "Combo maps", "Ensembles"),
}
SECTION_ORDER = ["wa", "ground", "precip", "aloft", "combo"]
TABS = [  # order = tab order on the site; most used first
    {"id": "rain", "label": "Rain", "models": ["ECMWF 9 km", "NBM", "EPS mean", "EPS 90th pct", "HRRR", "RRFS"], "periods": P_ACC_RAIN, "views": WA_VIEWS},
    {"id": "snow", "label": "Snow", "models": ["ECMWF 9 km", "NBM", "EPS mean", "EPS 90th pct"], "periods": P_ACC,
     "views": WA_VIEWS + [("cascades", "Cascades"), ("northeast", "NE WA mountains")]},
    {"id": "gusts", "label": "Wind gusts", "models": ["ECMWF 9 km", "NBM", "EPS mean", "HRRR", "RRFS"], "periods": [("step", "Each step"), ("max6h", "6-hour max"),
                                                      ("max12h", "12-hour max"), ("max24h", "24-hour max")], "views": WA_VIEWS},
    {"id": "lows", "label": "Lows", "models": ["NBM", "EPS mean"], "periods": [("daily", "Daily low")], "views": WA_VIEWS},
    {"id": "highs", "label": "Highs", "models": ["NBM", "EPS mean"], "periods": [("daily", "Daily high")], "views": WA_VIEWS},
    {"id": "t2m", "label": "2 m temp", "models": ["ECMWF 9 km", "AIFS", "HRRR", "RRFS"], "periods": [("step", "Each step")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "t2manom", "label": "2 m temp anomaly", "models": ["ECMWF 9 km", "AIFS"], "periods": [("step", "Each step")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("wa", "Washington")]},
    {"id": "feels", "label": "Feels-like temp", "models": ["ECMWF 9 km", "AIFS", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "t850", "label": "850 mb temp + wind", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "gust10", "label": "10 m wind gusts", "models": ["ECMWF 9 km", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "peakgust", "label": "Peak gust so far", "models": ["ECMWF 9 km", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "td2m", "label": "2 m dewpoint", "models": ["ECMWF 9 km", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "t925", "label": "925 mb temp + wind", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "t700", "label": "700 mb temp + wind", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "t500", "label": "500 mb temp + wind", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "t300", "label": "300 mb temp + wind", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "mslpptype", "label": "MSLP + precip type", "models": ["ECMWF 9 km", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "snowkuch", "label": "Snow total (Kuchera)", "models": ["ECMWF 9 km", "HRRR"], "periods": [("1h", "1 h (HRRR/RRFS)"), ("6h", "6 h"), ("12h", "12 h"), ("24h", "24 h"), ("48h", "48 h"), ("total", "Run total")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "snow10", "label": "Snow total (10:1)", "models": ["ECMWF 9 km", "HRRR", "RRFS"], "periods": [("1h", "1 h (HRRR/RRFS)"), ("6h", "6 h"), ("12h", "12 h"), ("24h", "24 h"), ("48h", "48 h"), ("total", "Run total")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "snowk24", "label": "24 h snow (Kuchera)", "models": ["ECMWF 9 km", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "snowrate", "label": "1 h snowfall rate", "models": ["HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "frzr", "label": "Freezing rain total", "models": ["ECMWF 9 km", "HRRR", "RRFS"], "periods": [("1h", "1 h (HRRR/RRFS)"), ("6h", "6 h"), ("12h", "12 h"), ("24h", "24 h"), ("48h", "48 h"), ("total", "Run total")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "tcc", "label": "Total cloud cover", "models": ["ECMWF 9 km", "AIFS", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "ir", "label": "Simulated IR satellite", "models": ["HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "vis", "label": "Visibility", "models": ["HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "fog", "label": "Fog risk index", "models": ["ECMWF 9 km", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight"), ("pnwhr", "Pacific NW (high-res)"), ("wa", "Washington")]},
    {"id": "qpf", "label": "Precip total", "models": ["ECMWF 9 km", "AIFS", "HRRR", "RRFS"], "periods": [("1h", "1 h (HRRR/RRFS)"), ("6h", "6 h"), ("12h", "12 h"), ("24h", "24 h"), ("48h", "48 h"), ("total", "Run total")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)")]},
    {"id": "ivt", "label": "IVT (vapor transport)", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)")]},
    {"id": "pwanom", "label": "PW anomaly", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)")]},
    {"id": "pw", "label": "Precipitable water", "models": ["ECMWF 9 km", "AIFS", "HRRR", "RRFS"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)")]},
    {"id": "w250", "label": "250 mb wind (jet)", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)")]},
    {"id": "w850", "label": "850 mb wind + barbs", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)")]},
    {"id": "thick", "label": "1000-500 mb thickness", "models": ["ECMWF 9 km", "AIFS", "HRRR"], "periods": [("step", "Each step")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwhr", "Pacific NW (high-res)")]},
    {"id": "waves", "label": "Waves", "periods": [("step", "Each step"), ("max24h", "24-hour max wave")],
     "views": [("full", "WA coast and Sound"), ("vi", "Vancouver Island (metric)")]},
    {"id": "bcrain", "label": "BC rain", "models": ["ECMWF 9 km", "EPS mean", "EPS 90th pct"], "periods": P_ACC, "views": [("bc", "Southern BC"), ("lowermainland", "Lower Mainland")]},
    {"id": "aifs500", "label": "500 mb anomaly", "models": ["AIFS", "GFS"], "periods": [("step", "Every 6 h")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight")]},
    {"id": "aifsmslp", "label": "Sea-level pressure", "models": ["AIFS", "GFS"], "periods": [("step", "Every 6 h")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight")]},
    {"id": "mslpprecip", "label": "MSLP + precip", "models": ["ECMWF 9 km"],
     "periods": [("qpf", "3 h to 72 h, then 6 h")], "views": [("na", "North America"), ("pnw", "Pacific NW"), ("wa", "Washington")]},
    {"id": "aifswind", "label": "MSLP + 10 m wind", "periods": [("step", "Every 6 h")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight")]},
    {"id": "elows", "label": "Ensemble low centers", "models": ["EPS", "AIFS ENS"], "periods": [("step", "Every 6 h")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight")]},
    {"id": "e500", "label": "Ensemble 500 mb heights", "models": ["EPS", "AIFS ENS"], "periods": [("step", "Every 6 h")],
     "views": [("na", "North America"), ("pnw", "Pacific NW"), ("pnwt", "Pacific NW tight")]},
]

TOWNS = [("seattle", "Seattle (SeaTac)"), ("tacoma", "Tacoma (Narrows)"), ("everett", "Everett (Paine Field)"), ("arlington", "Arlington"), ("bellingham", "Bellingham"), ("olympia", "Olympia"), ("vancouver", "Vancouver WA (Pearson)"), ("portangeles", "Port Angeles"), ("forks", "Forks (Quillayute)"), ("aberdeen", "Aberdeen (Hoquiam)"), ("oceanshores", "Ocean Shores"), ("spokane", "Spokane"), ("yakima", "Yakima"), ("wenatchee", "Wenatchee (Pangborn)"), ("kennewick", "Tri-Cities (Pasco)"), ("wallawalla", "Walla Walla"), ("moseslake", "Moses Lake"), ("ellensburg", "Ellensburg"), ("pullman", "Pullman"), ("omak", "Omak"), ("snoqualmie", "Snoqualmie Pass"), ("stevens", "Stevens Pass")]
D = "doable"
EPS = [  # id, label, status, note  (ECMWF ENS open data 0.25 deg, 50 members, CC BY 4.0)
    ("eps_daily_hilo", "Daily High/Low Temp", D, "mx2t3/mn2t3 (3 h max/min 2 m temp)"),
    ("eps_qpf_plume", "Total QPF Plume", D, "tp"),
    ("eps_snow_plume", "Total Snow Plume", D, "sf (snow water) x ratio"),
    ("eps_spread_maxmin", "Spread: Max/Min Temp", D, "mx2t3/mn2t3 percentiles"),
    ("eps_tmax_members", "Member View & Mean: Max Temp", D, "mx2t3"),
    ("eps_tmin_members", "Member View & Mean: Min Temp", D, "mn2t3"),
    ("eps_t2m_members", "Member View & Mean: 2m Temp", D, "2t"),
    ("eps_qpf24_members", "Member View & Mean: 24-Hour QPF", D, "tp"),
    ("eps_qpf_members", "Member View & Mean: Total QPF", D, "tp"),
    ("eps_snow24_members", "Member View & Mean: 24-Hour Snow", D, "sf"),
    ("eps_snow_members", "Member View & Mean: Total Snow", D, "sf"),
    ("eps_tcc_members", "Member View & Mean: Cloud Cover", D, "tcc"),
    ("eps_gust_members", "Member View & Mean: 6-hr Max Gust", D, "10fg"),
    ("eps_mucape_members", "Member View & Mean: MUCAPE", D, "mucape"),
    ("eps_pwat_members", "Member View & Mean: PWAT", D, "tcwv"),
    ("eps_mr_t2m", "Multi-run: 2m Temperature", D, "2t, cached past runs"),
    ("eps_mr_tmax6", "Multi-run: 6-h Max Temperature", D, "mx2t3 pairs"),
    ("eps_mr_tmin6", "Multi-run: 6-h Min Temperature", D, "mn2t3 pairs"),
    ("eps_mr_qpf6", "Multi-run: 6-Hour QPF", D, "tp"),
    ("eps_mr_snow6", "Multi-run: 6-Hour Snow", D, "sf"),
    ("eps_mr_qpf24", "Multi-run: 24-Hour QPF", D, "tp"),
    ("eps_mr_snow24", "Multi-run: 24-Hour Snow", D, "sf"),
    ("eps_mr_qpf", "Multi-run: Total QPF", D, "tp"),
    ("eps_mr_snow", "Multi-run: Total Snow", D, "sf"),
    ("eps_spread_qpf", "Spread: Total QPF", D, "tp percentiles"),
    ("eps_z500_t850", "500hPa Height and 850hPa Temp", D, "gh 500, t 850"),
]
HRRR = [  # NOAA HRRR, public domain (AWS open data / NOMADS)
    ("hrrr_surface_summary", "Surface Summary", D, "wrfsfc 2 m T/Td, gust, wind, APCP, cloud"),
    ("hrrr_smoke_xsec_low", "Low Level Smoke X-Sec", D, "wrfnat MASSDEN on native levels"),
    ("hrrr_multirun_t2m", "Multi-run 2m Temperature", D, "wrfsfc TMP 2 m"),
    ("hrrr_multirun_qpf6", "Multi-run 6-Hour QPF", D, "APCP"),
    ("hrrr_multirun_snow6", "Multi-run 6-Hour Snow", D, "ASNOW / WEASD"),
    ("hrrr_multirun_qpf", "Multi-run Total QPF", D, "APCP"),
    ("hrrr_multirun_snow", "Multi-run Total Snow", D, "ASNOW"),
    ("hrrr_smoke_xsec", "Smoke X-Sec", D, "wrfnat MASSDEN"),
    ("hrrr_winter_summary", "Winter Weather Summary", D, "ptype flags, ASNOW, APCP, 2 m T"),
    ("hrrr_winter_thermal", "Winter Thermal Environment", D, "wrfprs T/RH profile, wet bulb"),
    ("hrrr_temp_xsec", "Temp X-Sec", D, "wrfprs TMP 40 levels"),
    ("hrrr_temp_xsec_low", "Low Level Temp X-Sec", D, "wrfprs TMP 1000-700 mb"),
    ("hrrr_rh_xsec", "Rel. Humidity X-Sec", D, "wrfprs RH 40 levels"),
]


NA = "not available free"
RRFS = [  # NOAA RRFS v1 operational (public domain), AWS noaa-rrfs-ops-pds / NOMADS rrfs/v1.0; 00/06/12/18Z to 84 h
    ("rrfs_surface_summary", "Surface Summary", D, "2dfld 2 m T/Td, gust, wind, APCP, cloud"),
    ("rrfs_smoke_xsec_low", "Low Level Smoke X-Sec", NA, "operational RRFS only outputs smoke at 8 m and column total; no smoke on levels"),
    ("rrfs_multirun_t2m", "Multi-run 2m Temperature", D, "2dfld TMP 2 m"),
    ("rrfs_multirun_qpf6", "Multi-run 6-Hour QPF", D, "APCP"),
    ("rrfs_multirun_snow6", "Multi-run 6-Hour Snow", D, "ASNOW"),
    ("rrfs_multirun_qpf", "Multi-run Total QPF", D, "APCP"),
    ("rrfs_multirun_snow", "Multi-run Total Snow", D, "ASNOW"),
    ("rrfs_smoke_xsec", "Smoke X-Sec", NA, "no smoke on vertical levels in operational output"),
    ("rrfs_smoke_sfc", "Near-Surface Smoke", D, "MASSDEN 8 m, COLMD"),
    ("rrfs_winter_summary", "Winter Weather Summary", D, "CRAIN/CSNOW/CFRZR/CICEP, ASNOW, APCP"),
    ("rrfs_winter_thermal", "Winter Thermal Environment", D, "prslev T/RH"),
    ("rrfs_temp_xsec", "Temp X-Sec", D, "prslev TMP 45 levels"),
    ("rrfs_temp_xsec_low", "Low Level Temp X-Sec", D, "prslev TMP 1000-700 mb"),
    ("rrfs_rh_xsec", "Rel. Humidity X-Sec", D, "prslev RH"),
]


def pt(s):
    return dt.datetime.fromisoformat(s).astimezone(PT)


def init_iso(info):
    """Model run (init) time as ISO UTC, so the viewer can show the forecast hour. None if unknown."""
    c = str(info.get("cycle", ""))
    if re.fullmatch(r"\d{10}", c):
        return dt.datetime.strptime(c, "%Y%m%d%H").replace(tzinfo=dt.timezone.utc).isoformat()
    m = re.search(r"(\d{2})Z run (\d{1,2})-(\d{1,2})", info.get("run", ""))
    if m:
        e = info["end"]; t = dt.datetime(e.year, int(m[2]), int(m[3]), int(m[1]), tzinfo=dt.timezone.utc)
        if t > e.astimezone(dt.timezone.utc) + dt.timedelta(days=1): t = t.replace(year=e.year - 1)
        return t.isoformat()
    return None


def label(s, e, period):
    f = lambda t: t.strftime("%a %-I %p").replace(" 12 PM", " Noon")
    if period == "daily":
        return s.strftime("%A %-m-%-d")
    if period == "step" or s == e:
        return f"Valid {f(e)} {e:%-m-%-d}"
    return f"{f(s)} to {f(e)} {e:%-m-%-d}"


def classify_adhoc(d, fn):
    """Best effort for hand-made page maps: returns dict(tab, period, view, start, end, run) or None."""
    name = os.path.basename(d)
    rj = os.path.join(d, fn.replace("final.jpg", "run.json"))
    r = json.load(open(rj)) if os.path.exists(rj) else {}
    view = "full"
    for v in ("west", "east", "cascades", "northeast"):
        if re.search(rf"_{v}(_|$)", name):
            view = v
    if name.startswith("precip_"):
        tab = "bcrain" if ("_bc_" in name or "lowermainland" in name) else "rain"
        if tab == "bcrain":
            view = "lowermainland" if "lowermainland" in name else "bc"
        if "used_pt" not in r:
            return None
        s, e = map(pt, r["used_pt"]); h = round((e - s).total_seconds() / 3600)
        period = {3: "step", 6: "6h", 12: "12h", 24: "24h", 48: "48h"}.get(h, "total")
        return dict(tab=tab, period=period, view=view, start=s, end=e, run=r.get("model_line", ""))
    if name.startswith("snow_") and "cache" not in name:
        if "used_pt" not in r:
            return None
        s, e = map(pt, r["used_pt"]); h = round((e - s).total_seconds() / 3600)
        return dict(tab="snow", period={6: "6h", 12: "12h", 24: "24h", 48: "48h"}.get(h, "total"),
                    view=r.get("region") or view, start=s, end=e, run=r.get("model_line", ""))
    if name.startswith("wave_") and "valid_pt" in r:
        e = pt(r["valid_pt"])
        return dict(tab="waves", period="max24h" if "hmax" in name else "step",
                    view="vi" if "_vi_" in name else "full", start=e, end=e, run=r.get("model_line", ""))
    if name.startswith("nbm_") and r.get("title"):
        kind = "lows" if "Low" in r["title"] else "highs" if "High" in r["title"] else None
        m = re.search(r"(\d{8})", name)
        if not kind or not m:
            return None
        day = dt.datetime.strptime(m.group(1), "%Y%m%d").replace(tzinfo=PT)
        return dict(tab=kind, period="daily", view=view, start=day, end=day + dt.timedelta(hours=23), run="NBM")
    return None  # gust folders vary too much by hand; use render_forecast_batch.py for gusts


def web_jpg(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    im = Image.open(src).convert("RGB"); im.thumbnail((1600, 1600)); im.save(dst, "JPEG", quality=86, optimize=True)
    return im.size


def _web_jpg(args):
    return web_jpg(*args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-age-hours", type=float, default=36)
    ap.add_argument("--batch-root", default=os.environ.get("SITE_BATCH", ".site_batch"))
    ap.add_argument("--no-adhoc", action="store_true", help="skip hand-made folders under $WX_EXTRAS (always skipped if unset)")
    a = ap.parse_args()
    now = dt.datetime.now(PT); cutoff = now - dt.timedelta(hours=a.max_age_hours)
    found = []  # (key, mtime, info, path)
    for sf in glob.glob(f"{a.batch_root}/*/*/*/*/*/site_frame.json"):
        j = json.load(open(sf)); d = os.path.dirname(sf)
        info = dict(tab=j["tab"], period=j["period"], view=j["view"], start=pt(j["start_pt"]), end=pt(j["end_pt"]),
                    run=run_label(j["model"], j["cycle"]), cycle=j["cycle"],
                    model={"ECMWF": "ECMWF 9 km"}.get(j["model"], j["model"]))
        found.append((info, os.path.getmtime(f"{d}/final.jpg"), f"{d}/final.jpg"))
    for f in ([] if a.no_adhoc else glob.glob(f"{EXTRAS}/*/*final.jpg") if EXTRAS else []):
        d = os.path.dirname(f)
        if "site_batch" in d:
            continue
        info = classify_adhoc(d, os.path.basename(f))
        if info:
            info["cycle"] = "adhoc"
            ml = info.get("run", "")
            info["model"] = "HRRR" if "HRRR" in ml else "NBM" if ml == "NBM" else "ECMWF 9 km"
            found.append((info, os.path.getmtime(f), f))
    # newest run wins per tab/period/view/end time
    best = {}
    for info, mt, p in found:
        if info["end"] < cutoff:
            continue
        k = (info["tab"], info["period"], info["view"], info["end"].isoformat(), info.get("model", ""))
        if k not in best or mt > best[k][1]:
            best[k] = (info, mt, p)
    maps_dir = os.path.join(SITE, "maps")
    shutil.rmtree(maps_dir, ignore_errors=True)
    tabs_out = []; todo = []   # (frame, (src, dst)): web copies are made in parallel below (speed: one process per core)
    for t in TABS:
        frames = {}
        for (tab, period, view, _, _m), (info, mt, p) in sorted(best.items(), key=lambda kv: kv[0]):
            if tab != t["id"]:
                continue
            if view not in {i for i, _ in t["views"]} or period not in {i for i, _ in t["periods"]}:
                continue   # a view/period the menu does not offer (e.g. a test render): never ship it
            h = hashlib.sha1(f"{p}{mt}".encode()).hexdigest()[:10]
            rel = f"maps/{tab}/{period}/{view}/{info['end']:%Y%m%d%H}_{h}.jpg"  # hash keeps models apart
            fr = {"src": rel, "label": label(info["start"], info["end"], period), "run": info["run"],
                  "model": info.get("model", ""), "start": info["start"].isoformat(), "end": info["end"].isoformat(),
                  "init": init_iso(info), "w": 0, "h": 0}
            todo.append((fr, (p, os.path.join(SITE, rel))))
            frames.setdefault(f"{period}/{view}", []).append(fr)
        for v in frames.values():
            v.sort(key=lambda fr: fr["end"])
        extra = {k: t[k] for k in ("models",) if k in t}
        if t["id"] in MENU: extra.update(group=MENU[t["id"]][0], groupLabel=MENU[t["id"]][1], sub=MENU[t["id"]][2])
        tabs_out.append({**extra, "id": t["id"], "label": t["label"],
                         "periods": [{"id": i, "label": l} for i, l in t["periods"]],
                         "views": [{"id": i, "label": l} for i, l in t["views"]], "frames": frames})
    from concurrent.futures import ProcessPoolExecutor
    n = int(os.environ.get("PUBLISH_JOBS", os.cpu_count() or 1))
    if n > 1 and len(todo) > 50:
        with ProcessPoolExecutor(n) as ex:
            sizes = list(ex.map(_web_jpg, [j for _, j in todo], chunksize=32))
    else:
        sizes = [web_jpg(*j) for _, j in todo]
    for (fr, _), wh in zip(todo, sizes):
        fr["w"], fr["h"] = wh
    print(f"web copies: {len(todo)} images, {n} processes", flush=True)
    tabs_out.sort(key=lambda t: SECTION_ORDER.index(t["group"]) if t.get("group") in SECTION_ORDER else 99)
    made_p = os.path.join(SITE, "meteograms", "made.json")
    made = json.load(open(made_p)) if os.path.exists(made_p) else {}

    def sec(sid, label, credit, prods):
        out = []
        for pid, pl, st, note in prods:
            imgs = {town: {"src": meteo_src(v[pid]["src"]), "run": run_label(sid.upper(), v[pid]["run"])}
                    for town, v in made.get(sid, {}).items() if pid in v}
            out.append({"id": pid, "label": pl, "status": st, "note": note, "images": imgs})
        return {"id": sid, "label": label, "credit": credit, "products": out}

    manifest = {
        "generated": now.isoformat(timespec="minutes"),
        "generated_label": now.strftime("%-I:%M %p PT %-m-%-d-%y"),
        "tabs": tabs_out,
        "modelNotes": MODEL_NOTES,
        "meteograms": {"towns": [{"id": i, "label": l} for i, l in TOWNS],
                       "sections": [sec("eps", "ECMWF EPS", "ECMWF open data, CC BY 4.0", EPS),
                                    sec("hrrr", "HRRR", "NOAA HRRR, public domain", HRRR),
                                    sec("rrfs", "RRFS", "NOAA RRFS, public domain", RRFS)]},
    }
    json.dump(manifest, open(os.path.join(SITE, "manifest.json"), "w"), indent=1)
    n = sum(len(v) for t in tabs_out for v in t["frames"].values())
    print(f"manifest: {n} map frames, {sum(len(p['images']) for s in manifest['meteograms']['sections'] for p in s['products'])} meteograms")

if __name__ == "__main__":
    main()
