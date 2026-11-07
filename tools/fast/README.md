# Fast-style maps (hidden preview page)

Browser-drawn maps from small data images in Cloudflare R2 (bucket `wx-models-data`), shown on the hidden page
https://fast.wx-forecast-maps.pages.dev (preview branch `fast` of Pages project wx-forecast-maps, behind Cloudflare Access).
Nothing here touches the live site: the live workflows (forecast-*.yml) never read this folder, and the fast page is a
preview deployment (production stays on branch main).

- `fast_encode.py` per model: `static` (base/towns layers, LUTs, color keys, manifest; run on the box) and `steps`
  (one 8-bit PNG per field per hour). Models: HRRR (00/06/12/18Z f01-f48), GFS, ECMWF 0.25, AIFS (00/12Z, to 360 h).
- `fast_cycle.py` one publishing pass (the `fast-models` workflow runs it every 15 min): new hours -> R2, run.json lists
  the unbroken hours from the start (progressive), manifest keeps the newest 2 runs per model, older runs are deleted.
  R2 also expires `runs/` after 3 days.
- `publish_static.py` uploads the static layers + manifest models (keeps the runs lists in R2).
- `site/` viewer, `functions/d/[[path]].js` the Pages Function serving `/d/*` from R2. Deploy: `build_fast_page.sh` then
  `wrangler pages deploy public --project-name=wx-forecast-maps --branch=fast`.
