# tide-archive (data branch)
Conditional Prediction snapshots for the WX Models Tides viewer, written by `.github/workflows/tide-archive.yml` on `main`
(`tools/fast/tide_archive/`). Every 6 h (02/08/14/20 UTC) one snapshot per station: `v1/<station>/<YYYY-MM>.json`.
`kind: "archive"` = computed live at issue time; `kind: "hindcast"` = reconstructed afterwards (Oct 1 - Nov 14 2026 backfill)
using only observations up to the issue time and the newest STOFS-2D-Global cycle posted by then.
`r` = raw forecast non-tidal residual (ft) at t..t+72 h hourly (what the site shows); `rc`/`cal` and `v1/calib/` = daily
self-calibration computed in the background for evaluation only. Data: NOAA CO-OPS + NOAA STOFS-2D-Global (public domain).
