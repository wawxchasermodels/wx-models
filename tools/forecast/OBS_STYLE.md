# Observations tab: locked style (approved 2026-10-24)

The Observations map is a self-contained module: `web/forecast/obs/obs.js`, `obs.css`, `basemap.json`.
It builds its own markup inside `<div id="obs-root">`, so it works as a tab on the forecast site or as a standalone page
(`<link rel="stylesheet" href="obs.css"><div id="obs-root"></div><script src="obs.js"></script><script>Obs.show()</script>`).
Rebuild the basemap with `python tools/forecast/obs_basemap.py`.

## Station plot
- Temperature: white `#ffffff`; light blue `#8fd3ff` at 32 °F or below (rounded value). No "F" suffix.
- Gust (mph, shown at 10 mph or more): pink `#ff5ec4`. No "G" suffix.
- Temperature over gust, both to the LEFT of the station circle; they slide below/above a barb that points left, and only
  as a last resort move to the right.
- All numbers: dark outline (`rgba(9,14,22,.92)`) plus a soft drop shadow, on the live map and in the downloaded image.
- Wind barbs: light gray-cyan `#cfe3ee` with a dark casing, standard convention (staff points to where the wind comes
  from, feathers on the clockwise / northern-hemisphere side, half = 5 kt, full = 10 kt, pennant = 50 kt, circle = calm),
  rotated for grid convergence. Checked against matplotlib/MetPy (`qa/qa_barbs.py`).
- Markers are 1.5x the original size (constant `Z = 1.5` in obs.js scales text, circle, barb and spacing together).
- No legend box on the map. Meaning is explained in the hint text, the credits and the tap-for-details box.

## Map
- Dark slate land `#343c47`, deep navy water `#0e1825`, coast `#62788b`, faint state/province lines, warm-gray
  international border (dashed through water: Juan de Fuca, Haro Strait, Boundary Pass, Boundary Bay).
- One Lambert conformal projection per preset view (Pacific NW, West + Western Canada, Vancouver Island + Puget Sound).
  Long straight lines are densified to 0.1 degree so the 49th parallel curves correctly.
- Labels: Natural Earth cities (big ones placed before station plots) and GeoNames towns (smaller, dimmer, by population,
  more as you zoom in, capped per screen, placed after stations). A town hidden under its own airport plot is written
  just below that plot. Faint state/province names.
- Declutter: every plot reserves exact rectangles (numbers, circle, barb strokes) with zoom-dependent spacing; nothing
  overlaps, nothing leaves the map, nothing sits under the zoom buttons. Airports first, then official, then partners.

## Data (live, fetched by the browser; both sources send CORS "*", no keys)
- Canada: Environment and Climate Change Canada, MSC GeoMet OGC API `swob-realtime` (Open Government Licence - Canada).
  Hourly reports over a 95-minute query window plus the last 12 minutes of minutely reports, newest per station.
- US: NOAA/NWS ASOS and AWOS via the Iowa Environmental Mesonet currents API (WA OR ID MT CA NV UT WY AZ CO NM AK).
- Reports older than 90 minutes are dropped. Range checks, ECCC QA flags and a neighbour check (100 km median)
  hide bad values. Refresh every 10 minutes while the tab is open.

## Credits (required, on the page and in the downloaded image)
ECCC (Open Government Licence - Canada, "Contains information licensed under the Open Government Licence - Canada"),
NOAA/NWS via IEM, Natural Earth (public domain), GeoNames (CC BY 4.0).
