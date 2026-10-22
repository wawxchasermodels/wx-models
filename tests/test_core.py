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
    from wxmaps.attribution import ecmwf_map_credit, footer_html, noaa_map_credit

    credit = ecmwf_map_credit(2026)
    assert "Source: ECMWF open data, CC BY 4.0" in credit
    assert "CC BY 4.0" in credit
    assert "Modified from ECMWF open data" in credit
    page = footer_html(2026)
    assert "Source: ECMWF open data, CC BY 4.0" in page
    assert "public domain" in noaa_map_credit()
    assert "TIGER" in noaa_map_credit()


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
