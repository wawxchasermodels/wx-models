# Warm water, depth, and sea level: research check on the tide Conditional line (Nov 15, 2026)

Asked by Benjamin at 2:45 AM PT, Nov 15. Mock study only. Nothing deployed and the live line is unchanged.
Branch `tide-steric-depth-mock-20261115`, worktree `/workspace/wx-models-site/tide_steric_depth_mock_20261115`.

## Bottom line

**No change to the calculation.** The research says warm water raises sea level by thermal expansion,
and the size depends on how thick the warm layer is. It also says that on the Washington coast, short-term
sea level swings come mostly from wind, pressure and coastal waves, not from warming. Our line already takes
the slow warm-water level from the gauges themselves, through the 5-day held offset. I tested four ways of
adding a depth- or warm-water-aware term, on the same 23-run backtest and on a 2023 to 2026 year-round test.
None gave a real gain. Two made it worse.

## Papers and reports read

1. **Gill, A.E. & Niiler, P.P. (1973).** "The theory of the seasonal variability in the ocean." *Deep-Sea Research* 20, 141-177. https://doi.org/10.1016/0011-7471(73)90049-1.
   Seasonal sea level splits into steric height (heating and freshening) and wind-driven parts. Near the surface, the steric rise from heating is the heat flux × α / (ρ c_p). This is the standard formula used by Stammer (1997, JGR) and later work.
2. **Widlansky, M.J., Long, X. & Schloesser, F. (2020).** "Increase in sea level variability with ocean warming associated with the nonlinear thermal expansion of seawater." *Communications Earth & Environment* 1, 9. https://www.nature.com/articles/s43247-020-0008-8.
   The expansion coefficient α grows with temperature. About 2 °C of upper-ocean warming raises α by about 5%, and seasonal to interannual sea level variability by 4-10%. Equation of state reference: TEOS-10 manual (IOC/SCOR/IAPSO 2010), https://www.teos-10.org/pubs/old_TEOS-10_manuals/TEOS-10_Manual_20th_August_2010.pdf.
3. **Komar, P.D., Allan, J.C. & Ruggiero, P. (2011).** "Sea Level Variations along the U.S. Pacific Northwest Coast: Tectonic and Climate Controls." *Journal of Coastal Research* 27(5), 808-823. https://doi.org/10.2112/JCOASTRES-D-10-00116.1 (PDF: https://www.pccharbormasters.org/wp-content/uploads/2016/10/Sea-Level-PNW-Coast.pdf).
   - PNW monthly sea level runs about 0.2 m higher in winter than summer (Yaquina Bay example). In 1982-83 and 1997-98 the winter level was about 0.5 m above the previous summer.
   - The cause is warm winter water and no summer upwelling, plus winter northward winds piling water against the coast through Coriolis. Both effects get stronger in El Niño.
4. **Wang, H., Liu, K., Lin, P. & Yin, X. (2019).** "Record-low coastal sea levels in the Northeast Pacific during the winter of 2013-2014." *Scientific Reports* 9, 3774. https://doi.org/10.1038/s41598-019-40397-w.
   - During the start of the Blob, coastal sea level north of 40°N was a record low of −107 mm, even though the offshore water was warm.
   - The cause was offshore Ekman transport from the high-pressure ridge. Steric change was only about −18 mm (17%).
   - Offshore, the warm Blob water raised steric sea level by about 20 mm, out of a 26 mm total.
   - Takeaway: near the coast, warm SST does not guarantee high water.
5. **Gentemann, C.L., Fewings, M.R. & García-Reyes, M. (2017).** "Satellite sea surface temperatures along the West Coast of the United States during the 2014-2016 northeast Pacific marine heat wave." *GRL* 44, 312-319. https://doi.org/10.1002/2016GL071039.
   Coastal SST anomalies during the heat wave peaked at 6.2 °C off Southern California. They lasted through 2016 and eased only during spring upwelling winds.
6. **Chelton, D.B. & Davis, R.E. (1982).** "Monthly Mean Sea-Level Variability Along the West Coast of North America." *J. Phys. Oceanogr.* 12, 757-784. https://doi.org/10.1175/1520-0485(1982)012<0757:MMSLVA>2.0.CO;2.
   North of San Francisco, 50-60% of monthly sea level variance is the inverse-barometer response to local pressure. El Niño signals travel north at about 40 cm/s.
7. **Enfield, D.B. & Allen, J.S. (1980).** "On the Structure and Dynamics of Monthly Mean Sea Level Anomalies along the Pacific Coast of North and South America." *J. Phys. Oceanogr.* 10, 557-578. https://doi.org/10.1175/1520-0485(1980)010<0557:OTSADO>2.0.CO;2.
   El Niño sea level anomalies travel up the coast at 180 ± 100 km/day, or 60-100 km/day at subannual frequencies. Between Neah Bay and San Francisco, sea level follows alongshore wind stress.
8. **Hamlington, B.D., Leben, R.R., Kim, K.-Y., Nerem, R.S., Atkinson, L.P. & Thompson, P.R. (2015).** "The effect of the El Niño-Southern Oscillation on U.S. regional and coastal sea level." *JGR Oceans* 120, 3970-3986. https://doi.org/10.1002/2014JC010602.
   ENSO adds up to 20 cm to U.S. West Coast sea level on short time scales.
9. **Zervas, C. (2009).** "Sea Level Variations of the United States 1854-2006." NOAA Technical Report NOS CO-OPS 053. https://www.tidesandcurrents.noaa.gov/publications/Tech_rpt_53.pdf.
   - NOAA derives the seasonal constituents (Sa, Ssa) used in the official predictions from the average seasonal cycle.
   - Once the trend and seasonal cycle are removed, interannual anomalies are defined as a 5-month running mean beyond ±0.1 m.
   - Month-to-month persistence (AR coefficient) is 0.3-0.5 for OR/WA, versus about 0.7 in Southern California.
10. **NOAA PMEL NCTR, "1997-98 El Niño Sea Level"** (web report). https://nctr.pmel.noaa.gov/Sea_level_1997_98/sea_level_1997_98.html.
    - El Niño raises West Coast sea level in two ways. One is a persistent warm layer that reaches well down into the water column. This dominates in Southern California and Hawaii.
    - The other is the response to weather, meaning low pressure and northward winds. This dominates from central California to southern Alaska and peaks in late fall and winter.

Also checked: Vinogradov & Ponte (2010, JGR 115, C04021, https://doi.org/10.1029/2009JC005767). Annual sea level amplitude at gauges is usually a bit larger than offshore, and it differs near big river outflows like the Columbia.

## What the physics says, in numbers

- **Thermal expansion.** Sea level rise ≈ α × (temperature anomaly) × (thickness of the warmed layer).
  - Using the seawater equation of state already in our code (cond_v2.alpha_thermal), α is 1.4e-4 /°C at 8 °C, 1.6e-4 at 10 °C and 1.8e-4 at 12 °C. For comparison it is 3.0e-4 at 25 °C (tropical water).
  - So **1 °C of warming over a 50 m layer gives about 0.026 ft**, over 100 m about 0.05 ft, and over 200 m about 0.10 ft, at WA water temperatures.
- **Depth matters most.** A 2 °C surface anomaly only 20 m deep adds about 0.02 ft. The same anomaly through 150 m adds about 0.16 ft. SST alone cannot tell these apart.
- **It is slow.** A heating anomaly of 100 W/m² raises sea level only about 0.34 mm/day, or about 0.008 ft per week. Real steric change over a 3-9 day forecast is at most a few hundredths of a foot.
- **Our fitted k is not pure thermal expansion.** k = 0.048-0.299 ft/°C would need a warm layer 90 to 570 m thick:
  - Cherry Point ≈ 90 m, Seattle ≈ 110 m
  - Toke, La Push, Astoria, Westport ≈ 210-310 m
  - Tacoma, Friday Harbor ≈ 350-380 m
  - Neah Bay, Port Angeles, Port Townsend ≈ 480-570 m

  Those layers are thicker than the shelf and most of the Strait is deep. So k also picks up wind-driven downwelling and coastal waves that happen alongside warm water (Komar 2011, Wang 2019).

## Why the current line is already consistent with this

- The STOFS-free line is: official tide (which already has NOAA's Sa/Ssa seasonal cycle) + pressure effect + W + held 5-day offset + 12 h fade.
- The 5-day offset is the mean of (gauge residual − pressure − W). W is one constant per forecast. So **W cancels exactly**, and the drawn line equals official + pressure + 5-day mean of (gauge residual − pressure) + fade.
- That means the warm-water level, at whatever depth, is already in the line through the gauges themselves. The k × SSTA "warm water" number only splits that offset for the hover text and notes. Changing k, or switching to a depth-weighted version, would not move the line.
- A new term can only help if it predicts a **change** in the slow level after the 5-day window, which is centred about 2.5 days before issue time. That is exactly what I tested.

## What I tested

All tests used the same 23 AIFS runs, 20,416 hours and 374 peak highs, at 3-72 h leads. The script is `tools/fast/tide_archive/steric_depth_backtest.py`. It reproduces the 0.199 baseline exactly, and the wind identity check had 0 failures in 22,341 hours. Every term is pinned so the line still starts on the newest observation.

| Variant | MAE ft | Peak-high miss ft | Bias ft |
|---|---|---|---|
| STOFS-free default (now) | **0.199** | **0.229** | −0.066 |
| + change in 30-day SSTA since the offset window (k × ΔSSTA) | 0.199 | 0.231 | −0.066 |
| + change in daily SSTA since the window | 0.201 | 0.230 | −0.052 |
| + seasonal drift of the non-pressure residual (annual + semiannual fit, 2019-01 to 2026-09 gauges, no Oct/Nov 2026 data) | 0.198 | 0.226 | −0.061 |
| + offshore altimetry sea level change (NOAA CoastWatch blended SSH, public, no login) | 0.243 | 0.243 | −0.005 |
| + seasonal drift + daily SSTA change | 0.200 | 0.227 | −0.048 |

How each variant did by station:

- **Seasonal drift:** ties or edges out the default at every station, by 0.000 to 0.004 ft MAE. Astoria peak is +0.001.
- **Daily SST change:** worse at Westport (+0.017), Tacoma (+0.010), Seattle (+0.008) and Port Angeles (+0.008).
- **Altimetry:** much worse at Neah Bay (0.145 → 0.311) and in Puget Sound. Coastal altimetry is weak within about 20 km of shore, and Puget Sound has no altimetry.

**Depth-weighted (SSTA × mixed-layer depth) and seasonal k.** In a November-only backtest these are just a rescaled version of the SST rows above. So I tested them year-round instead.

**Year-round check.** This used 2019-2026 hourly gauges, observed pressure and daily levels, trained on 2019-2022 and tested on 2023 to Sep 2026. It covers about 13,000 forecast days per lead at 1-9 day leads, which also covers the 9-day window.

| Lead | 5-day persistence (our method) | + seasonal drift | + k × SST change | + monthly-fitted SST gain (depth/seasonal-k proxy) |
|---|---|---|---|---|
| 1 day | 0.154 | 0.154 | 0.162 | 0.157 |
| 3 days | 0.197 | 0.197 | 0.205 | 0.198 |
| 9 days | 0.233 | 0.234 | 0.243 | 0.232 |

- The November gain from seasonal drift (0.001 ft) disappears across the full year. The official tide's Sa/Ssa terms already carry the seasonal cycle. The leftover annual amplitude is only 0.02-0.06 ft at most stations.
- Adding recent SST change makes it worse at every lead.
- The fitted monthly gains for SST change are mostly negative, strongest in Nov-Feb. A recent SST jump tends to come before lower water, not higher. That is the wind and upwelling signal, not warming expansion, which matches Wang (2019) and Komar (2011).

**Data I considered but did not use:**

- **Argo gridded (RG/ISAS):** monthly and offshore only, with no floats on the shelf.
- **HYCOM GOFS 3.1:** no longer produced.
- **RTOFS 3D temperature:** public but heavy, and its signal over a few days would be the slow part that the gauge offset already carries.
- **Copernicus and Earthdata:** need logins, so they were excluded.

**Remote El Niño or coastal-wave signal.** These signals take days to weeks to arrive from the equator, and they show up at our gauges as a slow rise. The 5-day gauge offset tracks that rise. A strong El Niño winter could leave the held offset a few hundredths of a foot behind over 9 days, which is far below the weather noise.

## Recommendation

1. **Keep the calculation as is.** No new term beat the 0.199 ft / 0.229 ft baseline by more than 0.001-0.003 ft, and that small gain did not survive the year-round test.
2. **Optional wording tweak, which does not change the line.** The "warm water" part shown in hover and notes is a statistical split, not pure thermal expansion. A thermal-expansion-only figure (α × SSTA × about 50 m) would be about 0.03-0.05 ft per °C. If Benjamin wants the hover to show only the physical warming part, it could be capped at α × 100 m (about 0.05 ft/°C), with the rest shown under the gauge offset. The total line would stay identical. This would need his OK as a mock.
3. The one real known bias is that peak highs run about 0.18 ft low on average. None of the warm-water terms fixes that (best: 0.176). It is more likely tied to storm surge and wind, which is a separate question from warm water.

## Files

- Backtest: `tools/fast/tide_archive/steric_depth_backtest.py`, result `backtest_steric_depth.json`
- Year-round test and inputs: `tools/fast/tide_archive/steric_study/` (yearround.py, yearround.json, seasonal_harmonics.json, build_seas.py, sla_station.json, fetch scripts)
- Screenshots: none taken. The line is unchanged, so new shots would be identical to the current kink-fix mock.
