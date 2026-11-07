# Washington forecast maps

Static JPEG maps of Washington: rain (`precip_map.py`, `--source ecmwf|nbm`), Kuchera snow (`snow_map.py`),
wind gusts (`gust_map.py`), NBM lows / highs (`nbm_map.py`) and waves (`wave_map.py`).
`render_core.py` holds the projection, basemap, border, font and shield helpers; `region_maps.py`,
`town_pop.py` and `forecast_base.py` hold the shared regional framing and town rules.

    pip install -r tools/requirements.txt
    python tools/wa_maps/precip_map.py --region west --start "2026-10-23 19" --end "2026-10-25 18" --out out/rain_west

Environment: `WX_ASSETS` (default `tools/wa_maps/assets`), `WX_CACHE` (default `cache`),
`WX_FONT_TITLE` (default the Microsoft core fonts Impact path), `WX_FONT_BODY` (default the committed Montserrat).
Asset sources and licenses: `assets/LICENSES.md`. Batch runs: `tools/forecast/render_forecast_batch.py`.
