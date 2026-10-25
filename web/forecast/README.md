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
The full build runs on a timer once a day (cron `10 9 * * *` UTC = 2:10 AM PDT, 1:10 AM PST), publishing in 4 priority
waves (5 Pages deploys per run, about 155 a month). The afternoon build runs only on request: Actions > Forecast site >
Run workflow, branch `main`, leave every input at its default (the defaults are the full build), Run workflow. Start it
after 2:10 PM PDT (1:10 PM PST) so it uses the 12Z ECMWF run. Each manual run adds 5 deploys. Smaller manual runs: change
the `products` input (for example `aifs`, `hrrr`, `ens`, `menu`, `wa,temps,mslp`, `eps`), but note every deploy replaces the
whole site, so a partial run shows only its own products until the next full run.

To stop the timer, comment out the `schedule:` block in `.github/workflows/forecast-site.yml` or disable the
workflow in the Actions tab.

Needs repo secrets `CF_PAGES_KEY` and `CLOUDFLARE_ACCOUNT_ID`, and optionally the repo variables
`METEO_SPLIT` and `METEO_PROJECT`.
