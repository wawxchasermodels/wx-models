# Meteogram split (optional)

The meteogram charts can live on a second Cloudflare Pages project. That keeps the main site well under the 20,000-file
limit of a free Pages project.

Switch: set the repo variable `METEO_SPLIT=1`.

With the switch on, the deploy job does four things:
- builds the manifest with chart links `m/<model>/<town>/<chart>.png` (still relative)
- moves `web/forecast/meteograms/` into its own folder and deploys it to the meteogram project (`METEO_PROJECT`, default `wx-forecast-meteograms`)
- deploys the main site with `functions/m/[[path]].js`. That function serves `/m/...` on the main hostname and fetches
  each chart from the meteogram project with an Access service credential.

Main Pages project settings:
- `METEO_HOST`: the meteogram project's hostname
- `METEO_ACCESS_ID` and `METEO_ACCESS_SECRET`: the service credential, stored as secrets

The meteogram project's Access application needs a **Service Auth** policy that allows that credential.

Merge back into one site: delete `METEO_SPLIT`. Links go back to `meteograms/...` and everything deploys to the main project.
