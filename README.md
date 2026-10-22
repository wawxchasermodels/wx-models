# WX Models

A private desk for model charts. GitHub Actions downloads public ECMWF and NOAA GRIB fields, draws the maps, and publishes a static site to Cloudflare Pages. After the one-time setup below, nobody has to press anything.

The name on the masthead comes from `brand.json`. Change `siteName` and `tagline` there. The maps and the page pick the new name up on the next build.

## What gets drawn

| Model in the picker | Data | Grid |
| --- | --- | --- |
| ECMWF IFS 9 km | ECMWF open data, `ifs`, resolution `0p1` | 0.1° (about 9 km). 00/12Z through 240 h, 06/18Z through 90 h. |
| HRRR | NOAA HRRR CONUS | Native grid, hourly. 00/06/12/18Z through 48 h, other hours through 18 h. |
| ECMWF AIFS (AI) | ECMWF open data, `aifs-single` | 0.25° only, 00/06/12/18Z through 240 h, every 6 h. |
| GFS | NOAA GFS 0.25° | Through 240 h. |

IFS charts use the 0.1° files only. Those files show up about two hours after the 0.25° files. The schedule waits. If the 0.1° index is missing, that cycle is skipped. It is not replaced with 0.25°.

Fields, where the file actually contains them: 2 m temperature, 2 m dewpoint, 10 m wind, 10 m gust, mean sea-level pressure with precip type, radar or precipitation rate, total precipitation, snowfall (10:1 from snow-water equivalent, or snow depth on GFS), MUCAPE on IFS and surface CAPE on the NOAA models, 500 mb height and absolute vorticity, 850 mb temperature.

Temperatures at or below 32°F are blue, darker as they get colder. The first step above 32°F leaves blue.

Each hour is drawn twice: a 16:9 landscape plate and a 9:16 reel. The page shows both, locked to the same model, field, run, and hour. Drag to pan, scroll or pinch to zoom, double-click to reset. The address bar keeps a link to the current frame.

## One-time setup

You need a GitHub login for this repository, a Cloudflare login, and the email address you want to use as the lock on the site.

### 1. Cloudflare Pages project

1. Sign in at [dash.cloudflare.com](https://dash.cloudflare.com).
2. Open **Workers & Pages**, then **Create**, then **Pages**, then **Connect to Git** is not required. Choose **Direct Upload** / create a project.
3. Name the project `wx-models`. That matches `pagesProject` in `brand.json`. If you pick another name, change `pagesProject` to the same name.
4. Finish the empty project. The first GitHub run will upload the real site.

### 2. API token and account id

1. On the Cloudflare dashboard, open the account home. The **Account ID** is on the right. Copy it.
2. Open **My Profile → API Tokens → Create Token**.
3. Use the **Edit Cloudflare Workers** template, or build a custom token with **Account / Cloudflare Pages / Edit** and **Account / Account Settings / Read**.
4. Limit the token to your account. Create it and copy the token once. Cloudflare will not show it again.

### 3. GitHub secrets

In this repository on GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret | Value |
| --- | --- |
| `CLOUDFLARE_API_TOKEN` | the token from the previous step |
| `CLOUDFLARE_ACCOUNT_ID` | the account id |

Optional variables live under **Variables**, not secrets. Leave them empty unless you want to shorten a schedule. Examples: `ECMWF_LONG_MAX_HOUR` = `144`, `GFS_MAX_HOUR` = `120`, `HRRR_EXTENDED_HOUR` = `18`. Set `WX_ENABLE_GFS` to `0` to pause GFS. The same pattern works for `WX_ENABLE_ECMWF`, `WX_ENABLE_HRRR`, and `WX_ENABLE_AIFS`.

### 4. Lock the site with email codes

The Pages address looks like `https://wx-models.pages.dev`. Until you add Access, anyone who can guess that address can open it. Do this before the first forecast you care about:

1. In the Cloudflare dashboard, open **Zero Trust**.
2. The first visit asks you to pick a team name. Any short name is fine. The free plan covers a small number of users.
3. Open **Access → Applications → Add an application → Self-hosted**.
4. Name it `WX Models`. Application domain: `wx-models.pages.dev` (and your own domain too, if you attach one).
5. Add a policy named `Owner`. Action: **Allow**. Include rule: **Emails**, and type your email address. You can add more emails later.
6. Session duration: 24 hours is a reasonable start.
7. Identity: enable **One-time PIN**. That emails a code. You do not need a second login product.
8. Save.

Visit the site in a private window. Cloudflare should ask for your email, send a code, and only then show the charts. Repeat the application for any `*.pages.dev` preview hostname if you later turn previews on. This project deploys straight to the production project, so the one hostname is the one that matters.

### 5. Let the schedules run

The workflows are already in the repository:

- `ECMWF IFS 9 km` checks twice per cycle, late enough for the 0.1° files.
- `HRRR` checks once an hour.
- `ECMWF AIFS` and `GFS` check twice per cycle.

You can also open **Actions**, pick a workflow, and press **Run workflow**. Leave the boxes blank for the newest finished run.

A finished run uploads the charts and publishes the site. The two newest runs of each model stay on the site. Older images are dropped.

Changing `brand.json` does not redraw old images. The next publish uses the new name on the page. New maps pick it up as they are drawn.

## If a run is red

- **plan** says `no complete run`: the model has not finished publishing that cycle yet. The next scheduled check tries again. IFS will keep waiting for 0.1° rather than drawing 0.25°.
- **Require Cloudflare secrets** failed: the two secrets from step 3 are missing.
- **Publish to Cloudflare Pages** failed with a project error: the Pages project name and `brand.json` `pagesProject` do not match, or the token cannot edit Pages.
- A single forecast hour failed to download: that hour is skipped and the rest of the chunk continues. If the whole chunk fails, the cycle is not sealed and the next run tries the missing hours.

## Privacy of this public repository

The code in this repository is public. The website is private only after the Access policy in step 4 is on.

GitHub stores the rendered frames as Actions artifacts for two days so the deploy job can collect them. On a public repository, anyone who can open the Actions tab can download those artifacts. The charts are made from data you are allowed to redistribute (see the licenses below), but they are not secret while the artifact exists. If the pictures themselves must stay private, make the repository private. The Access lock does not hide Actions artifacts.

## Licenses and attribution

You may use these maps commercially. Every data source, font, and library below allows commercial use. Nothing in the site is GPL, AGPL, or a non-commercial (NC) license. The maps do not use proprietary map tiles.

ECMWF’s licence is Creative Commons Attribution 4.0. Commercial use is allowed. The licence asks for credit, a link to the deed, and a note that the charts were modified, in any reasonable manner. ECMWF also asks for its copyright line, www.ecmwf.int, and its liability statement to be attached to the use of the data. That full notice is in the site footer, which is how these charts are published. Each ECMWF image also carries one line so the credit survives if the picture is saved on its own:

`Source: ECMWF open data, CC BY 4.0. Modified.`

Do not crop that line off. NOAA images say the model data is public domain. The footer names the Census and Natural Earth basemap as well.

### Data

| Source | What we use | License |
| --- | --- | --- |
| ECMWF | IFS 0.1° open data and AIFS Single 0.25° open data | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Copyright European Centre for Medium-Range Weather Forecasts. |
| NOAA | HRRR and GFS GRIB2 from the AWS open-data buckets | Public domain, United States government work. |
| U.S. Census Bureau | TIGER/Line 2023 cartographic state and county boundaries, 1:5,000,000, simplified into `basemap/states.json` and `basemap/counties.json` | Public domain. |
| Natural Earth | 10 m coastline, simplified into `basemap/coast.json`, and 10 m populated places in `basemap/cities.json` | Public domain. |

### Fonts

Outfit, Fraunces, and IBM Plex Mono ship unmodified under the SIL Open Font License 1.1. The license files are `web/fonts/OFL-Outfit.txt`, `web/fonts/OFL-Fraunces.txt`, and `web/fonts/OFL-IBMPlexMono.txt`. Outfit and Fraunces are the upstream variable fonts. IBM Plex Mono is the upstream regular and medium cuts. You can use them in a commercial product. You may not sell the font files by themselves. A modified version may not keep the reserved names Outfit, Fraunces, or IBM Plex.

### Code in this repository

The Python and the page are under the MIT license in `LICENSE`.

### Libraries the build installs

| Package | License |
| --- | --- |
| ecmwf-opendata | Apache-2.0 |
| requests | Apache-2.0 |
| numpy | BSD-3-Clause |
| eccodes (Python bindings and the ECMWF ecCodes library they ship) | Apache-2.0 |
| matplotlib | Matplotlib License, BSD-style |
| Pillow | MIT-CMU, historically HPND |
| pytest (tests only) | MIT |
| pyshp (basemap rebuild only) | MIT |

Transitive packages of those libraries are the same class of permissive license (Apache-2.0, BSD, MIT, PSF, HPND). The page itself is plain HTML, CSS, and JavaScript with no third-party scripts. GitHub’s `actions/checkout`, `actions/setup-python`, and `actions/upload-artifact` are MIT. `cloudflare/wrangler-action` is MIT.

The renderer does not use pygrib, CDO, NCO, Cartopy, GEOS, or any map-tile SDK.

### What was changed from the model files

Temperatures may be converted to °F, wind speed to mph, and precipitation to inches. Wind barbs are drawn in knots. Snowfall marked 10:1 is snow-water equivalent multiplied by ten. Absolute vorticity at 500 mb is the model’s relative vorticity plus the Coriolis parameter when the file does not already contain absolute vorticity. HRRR wind components are rotated from the Lambert grid to east and north. Coast, state, and county lines are drawn on top from the public-domain files above.

## Rebuild the basemap lines

Only needed if you replace the linework. Download the Census 2023 5m state and county shapefiles and Natural Earth `ne_10m_coastline` into `/tmp/basemap-src/{state,county,coast}/`, then:

```bash
pip install -r requirements-dev.txt
python scripts/build_basemap.py /tmp/basemap-src
```

## Run a chart on your own computer

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m wxmaps demo --models ecmwf,hrrr --store tmp/demo-store --dest tmp/demo-dist
.venv/bin/python -m http.server 8765 --directory tmp/demo-dist
```

Open `http://127.0.0.1:8765`. Tests:

```bash
.venv/bin/python -m pytest -q
```
