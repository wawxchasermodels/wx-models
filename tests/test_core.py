"""Pure tests for schedules, color rules, and inventory selection."""

from __future__ import annotations

import colorsys

import pytest

from wxmaps.artifacts import choose_frames, sealed_inits
from wxmaps.noaa_idx import IdxRow, Selector, is_instant, is_run_total, parse_idx, select_rows
from wxmaps.palette import TEMP_F
from wxmaps.steps import forecast_hours


def _rgb(hex_color: str) -> tuple[float, float, float]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _lum(hex_color: str) -> float:
    r, g, b = _rgb(hex_color)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _blue(hex_color: str) -> bool:
    r, g, b = _rgb(hex_color)
    return b > r + 0.04 and b > g + 0.02 and colorsys.rgb_to_hsv(r, g, b)[0] > 0.45


def test_freezing_is_blue_and_darkens_as_it_gets_colder():
    freezing = [value for value in (-40, -20, -10, 0, 10, 20, 32) ]
    colors = [TEMP_F.hex_for(value) for value in freezing]
    assert all(_blue(color) for color in colors)
    lums = [_lum(color) for color in colors]
    assert lums == sorted(lums)
    assert not _blue(TEMP_F.hex_for(32.1))
    assert not _blue(TEMP_F.hex_for(42))
    assert TEMP_F.hex_for(32) != TEMP_F.hex_for(33)


def test_ecmwf_hours_follow_open_data_caps():
    long = forecast_hours("ecmwf", 12, {})
    assert long[0] == 0
    assert 3 in long and 144 in long and 150 in long and 240 in long
    assert 1 not in long and 147 not in long and 360 not in long
    short = forecast_hours("ecmwf", 18, {})
    assert short[-1] == 90
    assert 144 not in short
    assert all(hour % 3 == 0 for hour in short)


def test_aifs_is_six_hourly_and_hrrr_extension_is_only_on_synoptic_cycles():
    aifs = forecast_hours("aifs", 6, {})
    assert aifs[1] - aifs[0] == 6
    assert 240 in aifs and 241 not in aifs
    assert forecast_hours("hrrr", 0, {})[-1] == 48
    assert forecast_hours("hrrr", 3, {})[-1] == 18
    gfs = forecast_hours("gfs", 0, {"GFS_MAX_HOUR": "240"})
    assert 120 in gfs and 123 not in gfs and 126 in gfs and 240 in gfs


def test_idx_picks_run_total_not_the_one_hour_bucket_or_the_wrong_level():
    text = "\n".join(
        [
            "1:0:d=2026102118:TMP:2 mb:24 hour fcst:",
            "2:10:d=2026102118:TMP:2 m above ground:24 hour fcst:",
            "3:20:d=2026102118:APCP:surface:18-24 hour acc fcst:",
            "4:30:d=2026102118:APCP:surface:0-1 day acc fcst:",
            "5:40:d=2026102118:PRATE:surface:18-24 hour ave fcst:",
            "6:50:d=2026102118:PRATE:surface:24 hour fcst:",
            "7:60:d=2026102118:CAPE:180-0 mb above ground:24 hour fcst:",
            "8:70:d=2026102118:CAPE:surface:24 hour fcst:",
        ]
    )
    rows = parse_idx(text)
    chosen = select_rows(
        rows,
        [
            Selector("TMP", "2 m above ground", "instant"),
            Selector("APCP", "surface", "total"),
            Selector("PRATE", "surface", "instant"),
            Selector("CAPE", "surface", "instant"),
        ],
        24,
    )
    assert [row.start for row in chosen] == [10, 30, 50, 70]
    assert is_run_total("0-1 day acc fcst", 24)
    assert not is_run_total("18-24 hour acc fcst", 24)
    assert is_instant("anl", 0)
    assert not is_instant("0-6 hour acc fcst", 6)


def test_artifact_selection_keeps_two_newest_runs_per_model():
    artifacts = [
        {"name": "frames-ecmwf-2026102112-c00", "id": 1},
        {"name": "frames-ecmwf-2026102112-c01", "id": 2},
        {"name": "frames-ecmwf-2026102100-c00", "id": 3},
        {"name": "frames-ecmwf-2026102012-c00", "id": 4},
        {"name": "frames-hrrr-2026102204-c00", "id": 5},
        {"name": "dry-ecmwf-2026102112-c00", "id": 6},
        {"name": "seal-hrrr-2026102204", "id": 7},
        {"name": "frames-hrrr-2026102203-c00", "id": 8, "expired": True},
    ]
    names = sorted(item["name"] for item in choose_frames(artifacts, keep=2))
    assert names == [
        "frames-ecmwf-2026102100-c00",
        "frames-ecmwf-2026102112-c00",
        "frames-ecmwf-2026102112-c01",
        "frames-hrrr-2026102204-c00",
    ]
    assert sealed_inits(artifacts, "hrrr") == {"2026102204"}


def test_payload_builder_keeps_the_field_values():
    import numpy as np

    from wxmaps.derive import _base
    from wxmaps.grib import Bag

    bag = Bag(True, np.array([47.0, 46.0]), np.array([-124.0, -123.0]), [])
    values = np.arange(4, dtype=np.float32).reshape(2, 2)
    payload = _base(
        bag,
        field_id="t2m",
        title="2 m temperature",
        unit="°F",
        subtitle="sample",
        scale="temp_f",
        values=values,
    )
    assert payload.values is values


def test_required_ecmwf_credit_is_on_the_map_and_the_page():
    from wxmaps.attribution import ecmwf_map_credit, ecmwf_plate_credit, footer_html, noaa_map_credit, noaa_plate_credit

    assert ecmwf_plate_credit() == "Source: ECMWF open data, CC BY 4.0. Modified."
    full = ecmwf_map_credit(2026)
    assert "Modified from ECMWF open data" in full
    assert "www.ecmwf.int" in full
    assert "liability" in full
    page = footer_html(2026)
    assert "Source: ECMWF open data, CC BY 4.0" in page
    assert "www.ecmwf.int" in page
    assert "TIGER" in page
    assert noaa_plate_credit() == "NOAA model data, public domain."
    assert "TIGER" in noaa_map_credit()


def test_temperature_steps_are_at_most_five_degrees_and_break_at_freezing():
    gaps = [b - a for a, b in zip(TEMP_F.edges, TEMP_F.edges[1:])]
    assert max(gaps) <= 5
    assert 32 in TEMP_F.edges
    assert TEMP_F.hex_for(32) != TEMP_F.hex_for(36)


def test_clock_reads_pacific_with_am_pm():
    from datetime import datetime, timezone

    from wxmaps.plot import _clock

    assert _clock(datetime(2026, 10, 21, 18, tzinfo=timezone.utc)) == "Wed 11 AM PDT / 18Z"


def test_portrait_conus_grid_fills_the_tall_frame():
    from wxmaps.plot import _axes_rect, _geo_aspect, fit_window

    focus = (-128.0, -65.0, 23.2, 50.6)
    window = fit_window(focus, 0.72, (-134.0, -61.0, 21.0, 53.0))
    aspect = _geo_aspect(*window)
    assert 0.64 <= aspect <= 0.82
    assert window[0] >= -134.05
    assert window[1] <= -60.95
    assert _axes_rect(aspect, 0.72, 9.0, 16.0, 0.172, 0.100)[2] == 1.0


def test_wide_conus_grid_fills_without_dropping_the_northern_border():
    from wxmaps.plot import _axes_rect, _geo_aspect, fit_window

    focus = (-128.0, -65.0, 23.2, 50.6)
    target = 16.0 / ((1.0 - 0.132 - 0.138) * 9.0)
    window = fit_window(focus, target, (-134.1, -60.9, 21.1, 52.6))
    aspect = _geo_aspect(*window)
    assert window[2] <= 24.6
    assert window[3] >= 49.4
    x, y, w, h = _axes_rect(aspect, target, 16.0, 9.0, 0.132, 0.138)
    assert (x, w) == (0.0, 1.0)
    assert y == 0.138
    assert h == 1.0 - 0.132 - 0.138


def test_lambert_index_window_fills_a_tall_frame_and_keeps_a_small_region():
    import numpy as np

    from wxmaps.plot import _index_window

    nj, ni = 300, 600
    lats = np.linspace(24.0, 52.0, nj)[:, None] + np.zeros((1, ni))
    lons = np.linspace(-130.0, -60.0, ni)[None, :] + np.zeros((nj, 1))
    focus = (-128.0, -65.0, 23.2, 50.6)
    c0, c1, r0, r1 = _index_window(lats, lons, focus, 0.72)
    aspect = (c1 - c0) / (r1 - r0)
    assert 0.72 / 1.18 - 0.05 <= aspect <= 0.72 * 1.18 + 0.05
    # Washington-sized box can grow inside the grid instead of being cropped away.
    wa = (-125.0, -117.0, 45.5, 49.0)
    c0, c1, r0, r1 = _index_window(lats, lons, wa, 2.4)
    assert c1 - c0 > 40 and r1 - r0 > 20
    aspect = (c1 - c0) / (r1 - r0)
    assert 2.4 / 1.2 <= aspect <= 2.4 * 1.2


def test_wide_frame_extends_past_the_coasts_without_dropping_the_country():
    from wxmaps.plot import fit_window

    focus = (-128.0, -65.0, 23.2, 50.6)
    window = fit_window(focus, 2.28, (-152.0, -42.0, 4.0, 76.0))
    assert window[0] < focus[0] - 2
    assert window[1] > focus[1] + 2
    assert window[2] <= focus[2] + 0.2
    assert window[3] >= focus[3] - 0.2


def test_blank_hour_override_keeps_the_default_schedule():
    hours = forecast_hours("gfs", 0, {"GFS_MAX_HOUR": ""})
    assert 240 in hours


def test_regular_longitude_builder_covers_the_us_without_a_seam():
    import numpy as np

    raw = 180.0 + np.arange(3600) * 0.1
    lons = (raw + 180.0) % 360.0 - 180.0
    assert np.all(np.diff(lons) > 0)
    us = np.where((lons >= -125) & (lons <= -66))[0]
    assert us[-1] - us[0] + 1 == len(us)
    assert len(us) > 500
    greenwich = (np.arange(3600) * 0.1 + 180.0) % 360.0 - 180.0
    window = np.where((greenwich >= -134) & (greenwich <= -58))[0]
    assert window[-1] - window[0] + 1 == len(window)
