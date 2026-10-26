# Forecast map style rules

These rules apply to every model product: AIFS, GFS, GEFS, ECMWF/EPS, HRRR, RRFS and any model added later.
`house_style.py` is the single source of truth. Import scales from it and never redefine a palette or bin set in a model script.

## 500 mb height anomaly
- Units are meters. The range is -450 to +450 m in 12 m bins (75 colors), with extend arrows beyond ±450.
- The neutral near-white band covers -18 to +18 m.
- Color order from negative to positive: light gray > darker gray > dark green > green > light green > indigo/purple > blue > light blue > neutral > pale yellow > yellow > gold/orange > orange-red > red > crimson > magenta > pink > mauve/light purple.
- The colors come from interpolating the 36 m anchor colors (`ANOM_ANCHORS`) within each color family, so green never blends into purple.
- Use `HS.ANOM_LEVELS`, `HS.anom_cmap()` and `HS.ANOM_TICKS`. Key labels go every 72 m from each end, plus 0.

## Sea-level pressure (MSLP)
- The range is 900 to 1060 mb in 2 mb bins (80 colors), with extend arrows at both ends.
- Palette from low to high: near-black violet (900) > dark magenta > deep purple > purples and blues > teal > saturated greens (1000-1012) > pale neutral (about 1016) > yellow > orange > red > dark red (1060).
- Use `HS.MSLP_LEVELS`, `HS.mslp_cmap()` and `HS.MSLP_TICKS`. Key labels go every 10 mb.
- Isobars are black and labeled, with 2 mb spacing on regional views and 4 mb on continental views.
- The MSLP map has no thickness lines (no 1000-500 mb dashed contours). It shows only the pressure fill, isobars and H/L centers.

## H / L pressure centers
- H is `HS.H_COLOR` (blue) and L is `HS.L_COLOR` (red).
- Letter size is `HS.HL_SIZE` (16 pt) with a white halo. The central-pressure label is `HS.HL_VALUE_SIZE` (6 pt), placed `HS.HL_VALUE_OFFSET` points below the letter.
- Detection uses `HS.find_centers`: a neighborhood extremum within `HS.HL_RADIUS_KM` (800 km NA, 400 km PNW), at least `HS.HL_PROMINENCE_MB` (3 or 2 mb) above or below the median of the ring at that radius. A center up to `HS.HL_EDGE_KM` outside the frame is pinned to the edge.
- Isobar labels inside a marker's box are removed with `HS.clear_labels_near`.

## Layout (all products)
- `HS.header`: the title, a valid-time line in PT, a run/view detail line, and an F+hour badge.
- `HS.hbar`: a horizontal color key under the header. Tick labels are `HS.BAR_LABEL_SIZE` (15 pt) bold, and must not crowd at phone width (375 px).
- `HS.outlines`: crisp coastlines and borders. `HS.credit`: a one-line attribution at the bottom left.
- No logos and no watermark. Do not copy palettes, title bars or fonts from other weather sites.

## Adding a new model or product
- Import `house_style as HS` and reuse the scale constants above.
- If a new kind of scale is needed, add it to `house_style.py` and document it here first.

## Wind maps (10 m wind, every model)
- Fill is 10 m wind speed in mph, 0 to 100 in 2 mph bins (50 colors), with an extend arrow above 100 (pale orchid). Use `HS.WIND_LEVELS`, `HS.wind_cmap()` and `HS.WIND_TICKS` (key labels every 10 mph).
- Palette from calm to strong: near-white/slate > pale steel blue > teal-blue > sea green > lime > yellow > amber > orange > red > rose > plum > violet > deep indigo. This is an original palette; do not swap in another site's wind colors.
- Barbs are in knots and the subtitle says "barbs in kt". Thin them in projection space with `regrid_shape`, using about `HS.BARBS_ACROSS[view]` barbs across the frame (20 PNW, 24 NA, so fewer per area on continental views). Barb color, length and line width come from `HS.BARB_*`.
- Isobars (every 2 mb regional, 4 mb continental) are dark lines on a thin white halo (`HS.ISOBAR_*`) with labels. H/L markers follow the H/L rules above. No thickness lines.
- The large horizontal color key goes under the header (`HS.hbar`).

## Temperature maps (2 m temperature and 850 mb temperature, every model)
- 2 m temperature fill is in deg F, -40 to 120 in 2 F bins (80 colors), extend arrows both ends. Use `HS.TEMP_LEVELS`, `HS.temp_cmap()` and `HS.TEMP_TICKS` (key labels every 10 F).
- Palette from cold to hot: pale lilac > violet > indigo > royal blue > sky blue > icy pale blue just below freezing, then a hard break at 32 F to forest green > green > yellow-green > yellow > amber > orange > red > dark crimson > wine, and orchid / pale pink for extreme heat. This is an original palette; do not swap in another site's temperature colors.
- 32 F is a bin edge, and the 32 F line is drawn dashed in deep navy on a thin white halo (`HS.FREEZE_*`).
- 850 mb temperature fill is in deg C, -40 to +30 in 1 C bins (`HS.T850_LEVELS`, `HS.t850_cmap()`, `HS.T850_TICKS` every 5 C, signed). Its colors are the 2 m palette at the same temperature converted to F (`HS.temp_color`), so equal temperatures look the same on both products and 0 C sits on the same break. The 0 C line is dashed like the 32 F line.
- 850 mb maps add geopotential height contours every 3 dam (isobar line style, `HS.ISOBAR_*`, labeled in dam) and wind barbs in knots thinned with `HS.BARBS_ACROSS[view]` (Washington view 18). Subtitle says "barbs in kt".
- Views: North America, Pacific NW and Washington. Upper-air products from AIFS get no Washington view.

## Rain / QPF totals (every model: ECMWF, HRRR, NBM, GFS, ENS; WA and BC views)
- Inches. Under 0.01 no fill; 0.01-0.10 one pale shade; a new color every 0.10 in from 0.10 to 4.00 (40 steps: pale greens > greens > dark green at 0.9, light yellow from 1.0 > yellows > oranges > reds > deep red at 3.9); then every 0.50 in from 4 to 12 (pink-magenta > purples > lavender) and 12+ white. 57 colors.
- Use `HS.RAIN_LEVELS`, `HS.rain_cmap()`, `HS.rain_color()` and `HS.RAIN_TICKS` (key labels every 0.5 in to 4, every 1 in above). `tools/wa_maps/precip_map.py` uses the identical colors (PEDGES/PCOLS).
- Contour lines on the fill only every 0.5 in (plus the 0.01 dry edge), not at every 0.10 step.
- BC metric maps (mm): same colors at the same depth, 25 mm = 1 in.

## MSLP + precipitation (ECMWF 9 km; NA, PNW, WA)
- Fill is precipitation accumulated over the period ending at the valid time, in inches liquid equivalent: 3 h periods to 72 h, 6 h after that (the open-data step). The subtitle and the viewer label name the period.
- Rain uses the rain scale above (`HS.rain_cmap()`, key to `HS.QPF_RAIN_MAX` = 4 in). Snow and mix use `HS.snow_cmap()` / `HS.mix_cmap()` on `HS.PTYPE_LEVELS` (0.01 to 2 in, keys `HS.PTYPE_TICKS`): snow pale ice blue > sky blue > royal blue > deep indigo; mix pale lilac-pink > orchid > plum. Original ramps.
- Type: snowfall share of the period total (`sf` / `tp`): at least `HS.SNOW_SHARE` (70 %) is snow, `HS.MIX_SHARE` (30 %) to 70 % is mix, the rest rain. Where the model's instantaneous precipitation type at the valid time is freezing rain, freezing drizzle or ice pellets, the fill is hatched (`HS.ICE_HATCH`).
- Isobars every 4 mb in every view (dark, labeled), H/L markers per the H/L rules (`HS.HL_*`, Washington view 250 km / 1.5 mb). No thickness lines.
- No pressure fill: land and sea get a quiet tint (`HS.QPF_LAND`, `HS.QPF_SEA`) so the precip shades read clearly.
- Three short keys side by side under the header: Rain, Mix, Snow.

## High-resolution models on the temperature maps (HRRR, RRFS)
- HRRR (3 km, 48 h) gets 2 m temperature and 850 mb temperature + wind. RRFS (3 km, 84 h) gets 2 m temperature only, because its 850 mb fields are not in the 2D file.
- Same colors, contours and barb rules as the temperature section above. On 3 km grids the 850 mb temperature is smoothed lightly (sigma 1) and the heights more strongly (sigma 7) so the contours aren't noisy over terrain.
- Views: "Pacific NW (high-res)" (a tighter PNW frame that stays inside the 3 km grid, barbs `HS.BARBS_ACROSS["pnwhr"]` = 20) and Washington. No North America view. Grid-relative Lambert winds are rotated to earth-relative before plotting.
- Credit line: "Basemap: Natural Earth." (NOAA data needs no credit).

## 2 m temperature anomaly (ECMWF 9 km and AIFS; NA, PNW, WA)
- Anomaly = model 2 m temperature minus the NCEP/NCAR Reanalysis 1991-2020 normal for that date and hour (6-hourly mean, 15-day smoothed, built by `make_clim_t2m.py`), interpolated to the valid time and moved from reanalysis terrain to model terrain at 6.5 C/km. PSL stamps each value 6 h before the time it is valid; the code accounts for that.
- Fill is deg F, -30 to +30 in 1 F bins with extend arrows; colors are the 500 mb anomaly family (1 F drawn like 15 m), key labels every 5 F, signed. No zero line (the white bin marks it).
- The anomaly is smoothed to at least sigma 1 grid point because the normal is ~200 km wide. Subtitle says "vs 1991-2020 normal for the date and hour". Credit adds "Climatology: NCEP/NCAR Reanalysis 1991-2020, NOAA PSL."

## 850 mb maps: ground above 850 mb
- Where surface pressure is below 850 mb (lightly smoothed), the 850 mb level is underground and the model values there are extrapolated. Those areas get a flat gray (`BELOW_GROUND` #8d9096) with no temperature fill, no height lines and no barbs. Subtitle adds "gray = ground above 850 mb". Applies to every model and view (ECMWF 9 km, AIFS, HRRR).

## Town labels (Washington view of the temperature, anomaly, 850 mb and MSLP + precip maps)
- 20 fixed reference towns (`temp_maps.WA_TOWNS`): small dark dot with a white edge, name in Montserrat 600 9.5 pt, dark text on a white halo (same look as contour labels). Each town has a fixed side (name right or left of the dot) chosen so neighbors don't touch. Washington view only; NA and PNW views stay unlabeled.

## Moisture and wind maps (menu_maps.py)
- Precipitable water: inches, 0.05 in bins to 2.6, brown (dry) > tan > green > teal > blue > purple > pink; finest where cool-season PNW values sit (0.2-1.2 in). PNW view.
- PW anomaly: model PW minus the NCEP/NCAR 1991-2020 daily normal (15-day smoothed), moved to model terrain with a 2.3 km water-vapor scale height so mountains don't show up as fake dry spots. Wide anomaly palette at +/-1.5 in (same color families as the 2 m anomaly). NA and PNW.
- IVT: (1/g) times the integral of q*V from 1000 to 300 mb (8 standard levels, levels under ground dropped). Fill from 100 kg/m/s (gray below 250, yellow-orange-red-purple above), arrows only where IVT is 250 or more. NA and PNW.
- 850 mb wind: the house wind palette in kt, barbs, heights every 3 dam, gray where the ground is above 850 mb. 250 mb wind: its own jet palette from 50 to 200 kt (nothing below 50), heights every 12 dam, barbs.
- 1000-500 mb thickness: temperature-palette fill, thin wine-red lines every 6 dam with small labels, 540 drawn bold blue with a white halo and labeled, black isobars every 4 mb with H/L.
- Precip total: 6 h, 24 h and run-total periods from the model's running total, the house rain scale (starts at 0.01 in, 0.10 in steps), land/sea tint like the snow totals. PNW view.

## Sky, fog and visibility maps (menu_maps.py)
- Total cloud cover: percent, 5 % bins, sky blue (clear) to slate gray (overcast), no white band. PNW view. All five models.
- Simulated IR: HRRR 10.7 um (GOES imager ch4 field) and RRFS ABI band 13. Warm ground light gray, low/mid cloud darker gray, colors from -32 C down (cyan > blue > green > yellow > orange > red > magenta > white at -90). Missing pixels are filled from neighbors. PNW high-res view.
- Visibility: miles, fill only under 7 mi, pale yellow > orange > red > magenta > purple for dense fog under 1/4 mi. HRRR, RRFS (GFS removed 10-24-26; ECMWF open data has no visibility). High-res: WA.
- Fog risk index (our own, labeled "not a model fog forecast"): saturation term 1 at 0 F dewpoint depression to 0 at 5 F, times calm term 1 at 3 mph or less to 0 at 15 mph; blended 60/40 with a model-visibility term where the model has visibility; damped to as low as 25 % where rain is falling harder than about 0.08 in/h. Shown from 20 to 100 in pale-to-navy gray-blues.

## European Ensemble key list (eps_maps.py)
- 50 perturbed ENS members, 0.25 deg. "Spread" is one standard deviation across members, drawn as labeled purple lines (#5b2a86, white halo) over the mean fill: 2 m temp in F, 850 mb in C, 500 mb in dam. MSLP is the other way round: spread is the fill (cream > orange > red > plum, mb) under black mean isobars with H/L.
- Mean maps reuse the deterministic palettes (2 m temp, 850 mb, 500 mb heights, gusts); anomaly maps reuse the wide anomaly palette and the same 1991-2020 NCEP/NCAR normals as the single-model anomalies.
- Chance maps: share of members past the threshold, 10 % bins from 10 to 100, pale lavender > teal > green > yellow-green > gold > red > wine; blank under 10 %. Washington view lightly smoothed (0.25 deg cells). Thresholds: freeze 32 F Oct-Apr / heat 90 F May-Sep at the valid time; gusts 45 and 58 mph in the 6 h ending at the valid time; 24 h precip 1 and 2 in; 24 h snow 1 and 6 in at 10:1.
- Header says "ECMWF ENS 0.25 deg 50 members"; credit is the ECMWF CC BY 4.0 line, plus the NOAA PSL climatology note on anomaly maps.
- (10-24-26) The European Ensemble map section above is shelved by decision: no ensemble map jobs and no menu section. The rules stay here only for reference if it comes back.

## Ensemble low centers and 500 mb heights (ens_maps.py; ECMWF ENS and AIFS ENS)
- Both: 50 perturbed members, 0.25 deg, frames every 6 h, North America and Pacific NW views; the low-centers map also has a
  "Pacific NW tight" view (pnwt: Mercator centered at 126 W, 138 W to 113.5 W and 40.5 N to 54.5 N, so Washington, Vancouver
  Island and the near Pacific with the coast and offshore waters in view). Tight-view low detection: radius 300 km, prominence
  1.2 mb, strike radius 250 km, smoothing 0.6; same left box, dot scale and legend as the other views. The 500 mb map draws
  the same frame too (on since 10-24-26; ens_maps.py --e500-views na,pnw turns it off). Header names the ensemble; credit is ECMWF CC BY 4.0.
- Low centers: blue fill = chance (% of members) of a low center within 500 km (NA) / 300 km (PNW) / 250 km (PNW tight); 12 blue steps
  (5, 10, 15, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100 %), light to deep blue, clear below 5 %. Top (max) color, near-navy #0a1442, with
  its own swatch 'within 25 km' at the right end of the key: a low center within 25 km in at least 5 members (the core of the cluster).
  Dots = each member's sea-level pressure lows, colored by central pressure: gray 1004+, gold 996-1003, orange 988-995, red 980-987,
  magenta 970-979, purple 950-969, indigo 920-949, near-black under 920; deepest on top.
  Dots carry no numbers. Narrow left box (cream, 0.092 of the figure width) right against the map's left edge (gap about
  8 px), top and bottom level with the map; the map slides left so box + map start at the title margin. One column, type
  1.3x the first narrow box (values 11.7 pt, heading 13.6 pt, means 15 pt): 'Lows (mb)', 'in view · 50 mem.'; 'Mean (red L)'
  = the mean-field lows in view (up to 4, deepest first, two per row) in red black bold; '10 strongest' then '10 weakest',
  each row = dot color, pressure, '#member'. Member numbers are the ECMWF ensemble numbers of the 50 perturbed members
  (1-50, EPS and AIFS ENS; no control run); in the box only, this replaces the earlier 'no member numbers' rule. No
  locations. Row spacing 0.28 in, shrinks only when the rows would not fit the map height (PNW views).
  Thin gray isobars = ensemble mean every 4 mb. Red L = lows of the mean field, with the mean central pressure under it (11 pt black bold).
  Lows over ground above 1000 m are skipped (sea-level reduction artifacts). Detection: closed minimum, at least 4 mb (NA) / 1.5 mb (PNW) below the ring median.
- 500 mb: tan-to-plum fill = spread (1 std dev, dam, 1-30, 80 % opacity), black = mean every 6 dam, thin blue/red = each member's 552 / 576 dam line.

## Pacific NW tight view on ground-level maps, GFS trim, frame steps (10-24-26, Benjamin 8:44 PM PT)
- The "Pacific NW tight" frame (pnwt, defined once in temp_maps.VIEWS and aifs_maps.VIEWS, H/L and barb settings in house_style)
  is used on the ground-level products of the global models only: gusts, peak gust, feels-like, dewpoint, cloud cover, fog risk
  (IFS; feels-like and cloud cover also AIFS), 2 m temp and 2 m anomaly (IFS, AIFS), AIFS sea-level pressure and MSLP + 10 m wind,
  and both GFS maps. Never on HRRR/RRFS (their grids stop short of its NW corner) and never on upper-air maps.
- Color-key titles shrink (13.5 pt down to 9.5 pt) so they always end before the color bar; the run/notes line under the valid time
  shrinks (12.5 pt down to 9.5 pt) so it never runs under the forecast-hour badge. Keep notes short anyway.
- GFS: only "500 mb Height Anomaly" and "Sea-Level Pressure" (gfs_maps.py, same renderers and scales as the AIFS maps, shown as a
  GFS pill on those tabs; credit "Data: NOAA GFS (public domain)" plus the NCEP/NCAR climatology on the anomaly). All other GFS
  products and the MSLP + 500 mb Height combo are archived in archive/gfs_products_20261024/.
- Frames: IFS and AIFS every 6 h to 240 h on every menu map, the temps job and the AIFS maps; HRRR hourly to 48 h, RRFS hourly to 84 h.

## Town numbers on Washington-view maps (prototype 10-24-26, branch citynum-proto, not live)
- Washington ("wa") view only, the same 20 WA_TOWNS labels; no new towns. Number follows the name: "Seattle 54" (right-side
  labels) or "Port Angeles 44 •" (left-side labels, the name slides left). Bold 800 weight, 10.5 pt, #0d0f13 on a 3.0 white halo.
- Value read at the town's official station pin (same table as wa_maps/town_pop.py OFFICIAL_PIN), else the town point:
  bilinear on ECMWF lat/lon grids, nearest point on HRRR/RRFS 3 km grids. Same units as the map's key.
- Formats: temps/dewpoint/gusts whole numbers; anomaly signed; rain/ice 2 decimals; snow 1 decimal (0 under 0.05);
  visibility 1 decimal under 3 mi, whole miles to 7, "7+" at 7 mi and more (blank on the map).
- A number that would overlap a name, another number or the frame moves under its name; if still blocked it is dropped (logged).
  Isobar labels that touch a number are removed. TOWN_NUMBERS=0 turns every number off.
- Mountain passes (added 10-24-26 10:22 PM request): on the same Washington-view maps that carry town numbers, 12 passes from
  temp_maps.WA_PASSES (Snow tab table + WSDOT pass-watcher points; Stampede not in either list). Small plum (#3b2a5c) triangle,
  8 pt italic name without "Pass", bold 9.5 pt value. Placed after towns: right, left, above, below;
  label dropped (triangle kept, logged) if it cannot clear every town label/number/dot. Value = model at the pass point, no
  terrain correction. PASS_LABELS=0 turns passes off.
- Pass height correction (Benjamin 10-24-26 10:32 PM): pass values on temperature and feels-like maps = model value + 3.5 F per
  1000 ft x (model ground at the pass - real summit); dewpoint uses 1 F per 1000 ft (dewpoint drops far more slowly with height).
  Model ground = the model's own terrain (ECMWF step-0 geopotential, HRRR/RRFS HGT:surface), cached once per run. Summits =
  WSDOT elevations (checked vs USGS 3DEP). Never applied to gusts, precip, snow, ice or visibility, and never to towns.
  PASS_HEIGHT_CORR=0 turns it off. Washington tab maps: same rule in tools/wa_maps/pass_terrain.py (nbm_map.py lows/highs only;
  NBM terrain = URMA 2.5 km HGT, EPS terrain = ECMWF 0.25 deg z, static files in tools/wa_maps/assets/terrain_*.npz).

## Town labels v2 (Benjamin 10-25-26 9:46 PM; branch town-labels, not live)
- Washington view: 34 towns (`temp_maps.WA_TOWNS`). Added: Victoria BC, Mount Vernon, Oak Harbor, Port Townsend, Arlington, Sumas,
  Neah Bay, Long Beach, Cannon Beach OR, Chehalis, Shelton, Winthrop, Oroville, Pendleton OR (Forks was already there). They get
  the same numbers as the other towns (read at the town point; no official-station pin).
- Placement: list order = priority. Each "Name 54" group tries its preferred side (r/l/a/b), then the other sides and four
  diagonal nudges, and must clear every town dot, every label already placed and the frame. Then the number under the name;
  then name only (number dropped, logged); a name with no room at all is dropped (logged). Passes are placed after towns.
- Passes removed: Washington Pass, Loup Loup Pass (also from the Washington tab maps in tools/wa_maps) and Cayuse Pass.
- Pacific NW views (pnwhr, pnwt): dot + name only, no numbers. Cities from Natural Earth populated places
  (web/forecast/obs/basemap.json "places", metro population). Order: tier 1 (250k+), then the WA towns above that fall in the
  frame, then tier 2 (60k+) and tier 3 (15k+ pnwhr, 20k+ pnwt) by population; at most 60 (pnwhr) / 55 (pnwt) tried; labels
  without room are skipped and counted in the log. Duplicate names in a frame keep the bigger place. REGION_TOWNS=0 = off.
- NA and the big PNW frame (upper air) stay without towns. Labels only: no new views or files.
- Pacific NW numbers (Benjamin 10-25-26 10:08 PM, "dropping more towns is fine"): on pnwhr / pnwt maps that carry town numbers
  on the Washington view (gusts, feels-like, 2 m temp / anomaly, dewpoint, 10 m wind, precip, snow, ice, visibility), each city
  gets the same number in the same format ("Seattle 54", bold 9.5 pt), read at the city point (bilinear on ECMWF lat/lon grids,
  nearest 3 km point on HRRR / RRFS). Same priority order; "Name 54" inline, then the number under the name; if neither fits
  the city is dropped (never name only; logged with the drop list). Missing value (off grid) = name only (logged). Upper-air
  frames stay names only. Typical: pnwhr 52-53 of 60 placed, pnwt 35-38 of 55. TOWN_NUMBERS=0 turns numbers off everywhere.
- HRRR / RRFS nearest-point KD-tree cached per cropped grid (temp_maps._grid_tree), built once in menu_maps.prewarm.
