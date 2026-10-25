# Asset licenses (all usable commercially)

| File | Source | License |
|---|---|---|
| basemap/cb_2023_us_county_500k.pkl, basemap/cb_2023_us_state_500k.pkl | US Census Bureau cartographic boundary files 2023 (500k) | Public domain (US Government work) |
| basemap/tl_2024_us_primaryroads.pkl, prisec_53.pkl | US Census Bureau TIGER/Line 2024 primary / primary+secondary roads (WA) | Public domain (US Government work) |
| basemap/ne_10m_*.pkl | Natural Earth 1:10m countries, lakes, state/province lines, land boundaries | Public domain |
| 2023_Gaz_place_national.txt (WA rows) | US Census Bureau 2023 Gazetteer, places | Public domain (US Government work) |
| gshhs_h_bc_clip.pkl | GSHHG high-resolution shoreline (NOAA NCEI), clipped to BC / WA waters | LGPL-3.0 (data); attribution: Wessel & Smith, GSHHG |
| us_places_geonames.tsv (WA rows) | GeoNames populated places | CC BY 4.0, credit "GeoNames" (shown on the maps) |
| shields/*.svg | Official MUTCD M1-1 / M1-4 route markers from Wikimedia Commons; each file's `.license.json` records the PD-USGov-MUTCD check | Public domain |
| fonts/Montserrat.ttf | Montserrat, The Montserrat Project Authors | SIL Open Font License 1.1 |

Not committed: the title font Impact (Microsoft core fonts, installed on the runner by the workflow through
`ttf-mscorefonts-installer`; set `WX_FONT_TITLE` to use another path).
Basemap pickles hold only the features that intersect lon -140..-100, lat 38..60 (whole features, uncut).
Model data (fetched at run time, not stored): ECMWF open data (CC BY 4.0), NOAA NBM / HRRR (public domain).
