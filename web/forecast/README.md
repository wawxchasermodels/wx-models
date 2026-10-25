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
