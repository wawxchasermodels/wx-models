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
The WA shard job is off (repo variable `WA_SHARDS=off`); Washington precip now comes from the menu's Precip total
(Washington view for ECMWF 9 km, HRRR, RRFS; Pacific NW tight for ECMWF). Restore steps: `RESTORE_WA_SHARDS.md`.
