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

## Layers (added 2026-10-25, sample for review; toggle chips under the view buttons, any combination)
- Chips: Station plot (default on), High, Low, Peak gust, Wind chill / heat index, MSLP. Each chip carries a dark badge with a
  sample number in that layer's map colour, so the chips are the legend (still no legend box on the map). Choice is kept in
  localStorage `obsLayers`; a link can force it with `#t=obs&v=pnw&l=plot,hi,lo`.
- Colours: High `#ff8a6e`, Low `#7f97ff`, Peak gust `#ffd23f`, Wind chill `#c9a2ff`, Heat index `#ffa94d`, MSLP `#7fe0b5`.
  Station plot colours are unchanged.
- Layout: left column = High, current temp, Low, current gust (top to bottom); right column = MSLP, wind chill / heat index,
  peak gust. Each column slides below/above a barb in its way and only as a last resort swaps sides. Station plot alone is
  exactly the original layout. With 3+ numbers at a station the numbers drop to 11.5 px x Z.
- Barbs only with Station plot. A station is drawn only if it has something for an active layer.
- "Today" = since local midnight at the station. US: IEM daily summary (station's own local calendar day; values hidden
  just after midnight until the station's day rolls over). Canada: built in the browser from hourly SWOB reports after local
  midnight (zone from the climate-ID province, NE BC and the SE Kootenays on Mountain time, Saskatchewan CST); needs at least
  60% of the hourly reports so far, fetched only while High/Low/Peak gust is on (~13k reports, ~0.5 MB gzipped, then 3-hour
  top-ups each refresh). The current reading is folded into high/low; a current gust above the peak raises the peak.
- Peak gust: US max gust reported today (no number when no gust was reported; tap shows max sustained); Canada max of hourly
  peak wind / 10-min gust. Shown at 10 mph or more.
- Wind chill / heat index: NWS formulas on the current ob. Wind chill at 50 F or colder with wind over 3 mph; heat index at
  80 F or warmer (Rothfusz with NWS adjustments). Nothing shown where neither applies.
- MSLP: station value in whole hPa (tap for tenths) plus isobars every 4 hPa (2 hPa zoomed in, k > 1.2) from a two-pass
  Barnes analysis (130 / 80 km) with two light 3x3 smoothing passes, masked where no station is within 110 km or fewer than
  3 within 220 km; Canadian stations above 1500 m are left out of the analysis. Isobar labels are placed first and reserved.
- QC: range checks plus neighbour checks (high/low 30 F, peak gust >50 mph vs a third of neighbours, pressure 8 hPa).

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
