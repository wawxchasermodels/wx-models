# GFS products archive (10-24-26, before the GFS trim)

Benjamin (8:44 PM PT 10-24-26): keep only two GFS maps on the site (500 mb Height Anomaly and Sea-Level Pressure, both made by
`tools/forecast/gfs_maps.py`), and save everything else so GFS products can be added back later. The combined
"MSLP + 500 mb Height" product (`mslp500`) was dropped on every model at the same time.

Nothing here runs. The files are reference copies.

| File | What it holds |
|---|---|
| `full_copies/menu_maps.py` | the whole menu renderer as it was (GFS in 25 products, `mslp500` on IFS/GFS/AIFS/HRRR) |
| `full_copies/render_forecast_batch.py` | the Washington-tab batch with GFS in Rain, BC rain, Snow, Gusts, Lows, Highs |
| `full_copies/publish_forecast_maps.py` | the manifest builder with GFS in the tab model lists and the `mslp500` tab |
| `full_copies/forecast-site.yml.txt` | the workflow with GFS in the menu matrix (`menu_models`) and `mslp500` in tier B |
| `menu_products_gfs.py.txt` | just the PRODUCTS lines that listed `"gfs"`, plus the `prod_mslp500` function and its entry |
| `wa_tab_models.py.txt` | the old `MODELS` dict of render_forecast_batch.py |
| `publish_tabs_with_gfs.py.txt` | the old publisher lines that named GFS or `mslp500` |
| `workflow_gfs_lines.yml.txt` | the old workflow lines for the GFS menu jobs and frame tiers |

## How to add a GFS product back
1. **A menu map** (e.g. GFS 10 m gusts): in `tools/forecast/menu_maps.py` PRODUCTS, add `"gfs"` to that product's models
   tuple (the old tuple is in `menu_products_gfs.py.txt`). The GFS reader, field names, Kuchera levels and freezing-rain
   rules were never removed. In `tools/forecast/publish_forecast_maps.py` TABS, add `"GFS"` to that tab's `models` list.
   In `.github/workflows/forecast-site.yml`, add `gfs` back to the `menu_models` default and to the plan step's fallback
   list (GFS picks its own latest 00Z/12Z run: run menu_maps.py for gfs without `--cycle`, as the old workflow did).
2. **A Washington tab** (Rain, Snow, Gusts, Lows, Highs, BC rain): put `"gfs"` back in that tab's list in
   `render_forecast_batch.py` MODELS (old dict in `wa_tab_models.py.txt`) and `"GFS"` in the publisher tab's models.
   The wa_maps scripts still accept `--source gfs` / `--model gfs`.
3. **MSLP + 500 mb Height**: paste `prod_mslp500` back from `menu_products_gfs.py.txt` (the function is also still in
   menu_maps.py, unused), add its PRODUCTS entry, its publisher TABS entry and MENU line, `mslp500` in workflow TIER_B,
   and `"mslp500"` in forecast.js INSTANT_TABS.
4. **Count first.** The main Pages project must stay under 20,000 files. Run
   `WX_PYTHON=<venv python> python3 plan/plan_calc.py v5` (box: /workspace/wx-models-site/plan) or
   `python tools/forecast/menu_maps.py --model gfs --every 6 --views na,pnw,pnwt,wa --products <list> --count`.
   At the 10-24-26 build the site was about 18,634 files; old GFS menu maps were about 2,400 and the GFS Washington
   tabs about 2,200 at 240 h.
