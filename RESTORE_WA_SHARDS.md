# Restoring the Washington map shards

Archived 10-25-26 (Benjamin): the `wa-maps` shard job (Washington tabs Rain, Snow, Wind gusts, Lows, Highs, Waves,
BC rain; about 7,500 site files and 2 h of the run) no longer runs. Nothing was deleted:

* `tools/wa_maps/`, `tools/forecast/render_forecast_batch.py` and the `wa-maps` job in `.github/workflows/forecast-site.yml`
  are unchanged; the job only has an extra condition `vars.WA_SHARDS == 'on'` (the variable is unset, so the job is skipped).
* The tab definitions (TABS/MENU in `tools/forecast/publish_forecast_maps.py`) are unchanged; Washington tabs with no maps
  are simply left out of the manifest, so the "Washington" menu group comes back by itself when maps exist again.
* Replacement on the site: Precip total (menu "Precip & snow > Precip") has Washington views for ECMWF 9 km, HRRR and
  RRFS, plus Pacific NW tight for ECMWF.
* One-off WA maps are made on the box with the saved scripts (wa-forecast-map skill), not by site runs.

## Put them back (pick one)

1. Switch on (no code change; the next run, scheduled or manual, renders and publishes them). Either
   GitHub > repo Settings > Secrets and variables > Actions > Variables > New repository variable `WA_SHARDS` = `on`, or

       gh variable set WA_SHARDS -R wawxchasermodels/wx-models --body on

   (needs a token with the Variables permission; the deploy key used by the bot does not have it). To switch off
   again: delete the variable or set it to `off`. Check the file count first: with the shards the main site is about
   17,900 files (stop line 19,500, Pages limit 20,000).

2. Undo the whole change (also removes the new Washington precip views), as a PR:

       git fetch origin && git checkout -b restore-wa-shards origin/main
       git revert -m 1 <merge commit of the "Archive WA map shards" PR>
       git push origin restore-wa-shards && gh pr create --fill && gh pr merge --merge

3. Run once right away after step 1: Actions > Forecast site > Run workflow on `main` with the default inputs
   (the default `products` list includes `wa`). About 2.5 h and 5 Pages deploys.
