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
The full build runs on a timer twice a day (cron `10 9,21 * * *` UTC = 2:10 AM / 2:10 PM PDT, 1:10 AM / 1:10 PM PST),
publishing in 4 priority waves (about 310 Pages deploys a month). Manual runs: Actions > Forecast site > Run workflow,
with the `products` input (for example `aifs`, `hrrr`, `ens`, `menu`, `wa,temps,mslp`, `eps`).

To stop the timer, comment out the `schedule:` block in `.github/workflows/forecast-site.yml` or disable the
workflow in the Actions tab.

Needs repo secrets `CF_PAGES_KEY` and `CLOUDFLARE_ACCOUNT_ID`, and optionally the repo variables
`METEO_SPLIT` and `METEO_PROJECT`.
