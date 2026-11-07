# Forecast maps site

The viewer (`index.html`, `forecast.js`, `forecast.css`) and the `manifest.json` written by
`tools/forecast/publish_forecast_maps.py`. Map frames and meteogram charts are rendered by the
GitHub Actions workflow `.github/workflows/forecast-site.yml` and uploaded straight to Cloudflare Pages.
Images never enter this repository.

## Deploy targets
- `wx-forecast-maps` (Cloudflare Pages, direct upload): the viewer, every map frame and the manifest,
  plus the `/m/` Pages Function from `web/meteo-proxy/`.
- `wx-forecast-meteograms` (Cloudflare Pages, direct upload): meteogram charts, used when the repo
  variable `METEO_SPLIT=1`. Without it everything goes to one project.

Both projects sit behind Cloudflare Access.

## Turning it on
The full build runs on a timer once a day from the 12Z model runs: cron `50 21 * * *` UTC = 2:50 PM PDT, 1:50 PM PST
(from Nov 1). The limit is the ECMWF IFS 0.1 deg run, whose 240 h file lands about 21:34 UTC (HRRR 12Z is done about
13:50, RRFS 15:30-16:20, GFS 16:40, AIFS 18:55, EPS 19:40). Scheduled runs set `WX_CYCLE_HOUR=12`, so every model uses 12Z.
It publishes in 4 priority waves (5 Pages deploys per run, about 155 a month). Extra builds run only on request: Actions >
Forecast site > Run workflow, branch `main`, leave every input at its default (the defaults are the full build), Run
workflow. A manual run uses the newest cycle of each model (no 12Z pin). Each manual run adds 5 deploys. Smaller manual runs: change
the `products` input (for example `aifs`, `hrrr`, `ens`, `menu`, `wa,temps,mslp`, `eps`), but note every deploy replaces the
whole site, so a partial run shows only its own products until the next full run.

To stop the timer, comment out the `schedule:` block in `.github/workflows/forecast-site.yml` or disable the
workflow in the Actions tab.

Needs repo secrets `CF_PAGES_KEY` and `CLOUDFLARE_ACCOUNT_ID`, and optionally the repo variables
`METEO_SPLIT` and `METEO_PROJECT`.

## Added 10-25-26 (PR #15)
- EPS member grids (meteograms, same product ids): 6 h max gust, daily high, daily low, 24 h QPF and total QPF are
  tables with one row per member (1 at top, 50 at bottom), a CTRL row on top for the control run (member 0; the ECMWF
  open-data ENS files currently carry only the 50 perturbed members, so the row says "not available" until they add it)
  and a MEAN row at the bottom. Drawn by `tools/forecast/member_grid.py`.
- ENS fields that ECMWF renames by step (10fg3 at 93-144 h, mx2t6/mn2t6 after 144 h) are now read under their base names.
- Menu: Aloft > Jet & winds > "500 mb wind" (w500: speed + barbs, no heights; ECMWF 9 km, AIFS, HRRR; about 208 files).
- Menu: Ground level > Pressure > "Sea-level pressure" now has an ECMWF 9 km pill (H/L centers, every 6 h to 240 h,
  NA / PNW / PNW tight; `gfs_maps.py --model ifs` in the mslp job, wave 1; about 123 files).

## Washington map shards archived (10-25-26)
The WA shard job is off (it runs only when the repo variable `WA_SHARDS` is `on`; unset = off); Washington precip now comes from the menu's Precip total
(Washington view for ECMWF 9 km, HRRR, RRFS; Pacific NW tight for ECMWF). Restore steps: `RESTORE_WA_SHARDS.md`.

## ECMWF IFS on 0.25° open data (10-26-26)

Benjamin 10-26-26 12:53 PM: "swap all the ECMWF 9km products over to that". Every ECMWF IFS product (menu maps, temps,
500 mb anomaly, SLP, MSLP + 10 m wind, MSLP + precip, and the 06Z/18Z `ifsx` second run) now reads
`data.ecmwf.int/forecasts/<d>/<hh>z/ifs/0p25/oper/<d><hh>0000-<step>h-oper-fc.grib2` (surface and pressure levels in one
file per step) instead of `ifs/0p1/oper/...-fc-sfc` / `-fc-pl`. Same parameters, same steps (3 h to 144 h, then 6 h; 10 m
gust on the 06Z/18Z runs still to 90 h), so no product was dropped and the file count is unchanged.
- s4 is ready when `ifs/0p25/oper/...-240h-oper-fc.index` answers (about 07:40 / 19:40 UTC, 1.5-2 h before 0.1°);
  the ifsx rider checks `...-144h-oper-fc.index`. Backup cron s4 moved from `50 9,21` to `30 8,20` (UTC).
- Site pill renamed "ECMWF 9 km" -> "ECMWF 0.25°" (`ECMWF_SITE` in publish_forecast_maps.py). Frames still carried from
  old 9 km runs join the new pill (`ECMWF_ALIAS`) until they roll off; their corner tags still say 9 km.
  If 9 km products come back as their own pill, remove "ECMWF 9 km" from `ECMWF_ALIAS`.
- Map headers read "ECMWF IFS 0.25°"; WA snow/rain/gust corner tag "[ECMWF 0.25°]".
- gfs_maps.py IFS smoothing (500 mb heights, MSLP) is scaled to the grid spacing so it keeps the same ground distance.
- Climatology/anomaly normals are interpolated onto whatever grid the GRIB has, so they needed no change.
- Rollback: `git revert <sha>` (plain push). The 0.1° URLs and the 21:34 UTC timing come back with it.

## Staged builds (10-25-26, PR #19)
Each 00Z/12Z cycle is published in five stages, each as soon as its models are out (times are UTC, from the
Last-Modified of each model's last file). Order (10-26-26, Benjamin: "have the main global runs and high res runs before
any ensemble or meteograms"): every deterministic global and high-res stage deploys before the ensembles and meteograms.

| Stage | Products | Data ready (UTC) |
|---|---|---|
| s1 | HRRR temps, HRRR menu maps | about 01:47 / 13:47 |
| s2 | RRFS temps/menu, GFS 500 mb + SLP | about 04:38 / 16:37 (GFS f240) |
| s3 | AIFS maps/temps/menu | about 06:55 / 18:55 |
| s4 | ECMWF IFS 0.25° MSLP/precip, SLP, temps, menu (0.1° / 9 km until 10-26-26) | about 07:40 / 19:40 (0.25° f240) |
| s5 | EPS + AIFS ENS lows, EPS/HRRR/RRFS meteograms (last) | after s4 of the same cycle (EPS out about 07:40 / 19:40) |

Before 10-26-26 there were four stages: s3 also held the ensembles and EPS meteograms, s1 deployed the HRRR meteograms and
s2 rendered the RRFS ones. `site-state` written by the old layout still works: until the first s5 run, s5 counts as
published at the ensemble group's cycle (`published()` in `stage_tools.py`), so nothing is redone or skipped.
- **Catch-up (10-26-26).** If a stage deploys but one of its groups failed (GFS 12Z on 10-26: NOAA files not found yet),
  the next stage run of the same cycle re-renders that group once its data is out (`CATCHUP`, GFS for now). No extra deploy.

How it works:
- **Triggers (live 10-25-26).** `forecast-poll.yml` runs every 10 min. When no Forecast site run is going, it starts the first stage whose models have a newer complete run than the site (`stage=sN cycle=YYYYMMDDHH`). Same-cycle stages start in order s1..s5, and s5 waits until s4 has published that cycle (or s4 failed twice). Backup crons in `forecast-site.yml` (`10 2,8,14,20`, `50 4,16`, `0 8,20`, `50 9,21`, `40 10,22` UTC) start a stage only if it has not been published yet (the s5 backup does not wait for s4).
- **What each stage does.** A stage renders only its own groups. Its single deploy contains the whole site: its new products laid over every group carried forward from the run that last built it. Only the newest cycle of each product is kept.
- **Site state.** The `site-state` artifact (30 days) says which run holds each group. Map artifacts are kept 3 days. If the state or a carried artifact is gone, the stage stops before deploying. A full build (`stage=all`) reseeds everything.
- **Safety check.** There is no deploy if the main site would have fewer than 85% of the last deploy's files, or more than 19,500.
- **Deploys (10-26-26 reorder).** 5 main deploys (s1-s5) plus 1 meteogram-project deploy (s5) per 00Z/12Z cycle, plus 1 main deploy each for HRRR 06Z and 18Z: still 14 a day, about 420-434 a month. Meteograms now update twice a day (s5, about 22:10 / 10:10 UTC) instead of with s1/s3. Earlier history: 4 main deploys plus 3 meteogram-project deploys (s1-s3) per 00Z/12Z cycle, plus 1 main deploy each for HRRR 06Z and 18Z (s1, maps only). 10-26-26: no meteogram-project deploy on s2 (RRFS charts go live with the next s3/s1 meteogram deploy), so 4 main + 2 meteogram deploys per 00Z/12Z cycle + 2 maps-only: 14 a day, about 420-434 a month (Pages Free limit: 500). HRRR keeps the newest two of 00/06/12/18Z. ECMWF 9 km 06Z/18Z (to 144 h; gusts to 90 h) rides along with the next stage run for five products (500 mb anomaly, MSLP + 10 m wind, 850 mb temp/wind, 850 mb anomaly, 10 m gusts) as a second run on the toggle (about +335 files). The poller stops re-dispatching a stage/cycle after 2 finished runs that did not publish it.
- **HRRR 18Z** is its own s1 run (f48 out about 19:47 UTC); AIFS 18Z still rides along with the next stage run (normally HRRR 00Z).
- **Manual runs.** Actions > Forecast site > Run workflow with `stage=s1`..`s5` (optional `cycle`, `dry_run`). Default `stage=all` is the old full build, unchanged.

### Two runs of HRRR and AIFS (10-25-26, PR "two-run HRRR + AIFS")
- **What the site shows.** The two newest HRRR runs (00Z/12Z/18Z long runs) and the two newest ECMWF AIFS single runs
  (00Z/12Z/18Z; 06Z is not used). Under the model pills a **Run** toggle (e.g. `12Z | 18Z`) appears only for HRRR/AIFS and
  only on tabs that have both runs. It opens on the newest run and keeps the same valid time when you switch.
  Link parameter `r=1` opens the previous run.
- **Rolling.** HRRR goes 00Z+12Z, then 12Z+18Z, then 18Z+00Z. AIFS goes 12Z+18Z, then 18Z+00Z, then 00Z+12Z. When a new run is
  deployed, the older of the two drops off. The state's `hrrr_prev` / `aifs_prev` groups carry the previous run, and the deploy
  keeps the two newest cycles of every HRRR/AIFS product folder (`*-hrrr`, `*-aifs`, `aifs500`, `aifsmslp`, `aifswind`).
- **18Z runs add no deploys and no crons.** Each one rides along with the first stage run after its data is out
  (`RIDERS` in `stage_tools.py`):
  - HRRR 18Z (f48 out about 19:47 UTC) is its own s1 run since 10-25-26 (this rider line is history).
  - AIFS 18Z (240 h out about 00:55 UTC) rides with the 00Z s1 run.
  - Riders draw maps only. HRRR multi-run meteograms already read the 18Z run themselves.
- **Full builds** show one run of each model. The next stage run brings back the second run.
- **The 21:50 UTC full-build cron** is pinned to 12Z. It now stands down by itself whenever the last deploy was a stage run in
  the last 36 h, so it can never redraw HRRR/AIFS at 12Z over an 18Z run or reseed the site state.
- **Files.** A second run adds about 2,270 HRRR and 1,970 AIFS files (with the 850 mb anomaly and MSLP + wind PR). That puts the
  main site near 15,000 of the 19,500 stop line. That only works while the WA map shards stay off.

Rollback to the once-a-day full build:
1. Comment out the `schedule:` block in `.github/workflows/forecast-poll.yml`, or disable "Forecast poll" in the Actions tab.
2. In `forecast-site.yml`, comment out the five staged backup crons and make sure `- cron: "50 21 * * *"` is active.
3. Optional: run Forecast site with the default inputs (`stage=all`) once. That rebuilds the whole site from one run and reseeds the site state.
No secrets, tokens or Cloudflare settings change in either direction. The staged code stays in place and is inert without its triggers.

## 850 mb temp anomaly + MSLP/10 m wind pills (10-25-26)
- Menu: Aloft > Temperature & barbs > "850 mb temp anomaly" (tab `t850anom`): ECMWF 9 km, AIFS, GFS, EPS mean, AIFS ENS mean;
  North America + Pacific NW; every 6 h to 240 h. 850 mb temperature minus the NCEP/NCAR Reanalysis 1 monthly long-term mean
  1991-2020 at 850 mb (NOAA PSL; `make_clim_t850.py`, cache `forecast-clim-t850-v1`), interpolated to the valid date like the
  500 mb anomaly. Deg C, -20..+20 in 1 C bins on the house anomaly palette; ground above 850 mb gray; 850 mb heights every 3 dam
  (not on the ensemble means: no member heights fetched). Ensemble means: average of the 50 perturbed members' 850 mb
  temperature (+50 fields a step). Jobs: temps (IFS, AIFS), gfs (GFS), ens (EPS, AIFS ENS). About 410 files.
- Menu: Combo maps > "MSLP + 10 m wind" (tab `aifswind`) now has ECMWF 9 km (`gfs_maps.py --model ifs --products wind`,
  mslp job; NA / PNW / PNW tight, same renderer as AIFS) and HRRR / RRFS pills (`menu_maps.py` product `aifswind`, tier B;
  Pacific NW high-res + Washington, hourly; isobars every 4 mb, no H/L on 3 km grids, Washington town/pass numbers = wind mph).
  About 390 files.
- Fixes: the mslp job now restores the 500 mb climatology (needed by the ECMWF 9 km 500 mb anomaly from PR #20); RRFS
  sea-level pressure is read from MSLET (the RRFS 2dfld file has no MSLMA, so RRFS MSLP + P-type had no frames).

## Total snow member meteogram (10-25-26, sample for review)
- `eps_snow_members` (Member View & Mean: Total Snow) is now our own ensemble snow chart (`tools/forecast/snow_ens.py`), same
  product id and file, so no new files: a grid with one row per ENS member (1 at top), the run-total snow at 10:1 printed in each
  12 h column on the site's teal-to-wine snow ramp, a CTRL row (control run; the open-data ENS file has snowfall for the 50 members
  only, so it says "not available" until ECMWF adds it), a MEAN row and the % of members at or above 1 / 3 / 6 / 12 in; under it a
  spread chart on the same columns (10-90% and 25-75% member ranges, median, mean, control when present).
- Source: ECMWF ENS open data 0.25 deg, `sf` (snowfall, m of water equivalent) x 10 = 10:1 snow. Runs to 360 h (`METEO_SNOW_HOURS`,
  default 360): the EPS meteogram job still runs other charts to 240 h and fetches only `sf` for 246-360 h (about 20 extra steps,
  about 9 MB each).
