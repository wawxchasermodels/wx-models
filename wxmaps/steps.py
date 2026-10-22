"""Forecast-hour schedules. Limits are environment overrides."""

from __future__ import annotations

import os


def _env(env: dict | None, key: str, default: str) -> str:
    src = os.environ if env is None else env
    value = src.get(key)
    if value is None or str(value).strip() == "":
        return default
    return str(value)


def forecast_hours(model: str, cycle: int, env: dict | None = None) -> list[int]:
    """Hours to render for one cycle. ECMWF 0.1° follows the open-data step list, capped."""
    cycle = int(cycle)
    if model == "ecmwf":
        long_max = int(_env(env, "ECMWF_LONG_MAX_HOUR", "240"))
        short_max = int(_env(env, "ECMWF_SHORT_MAX_HOUR", "90"))
        if cycle in (0, 12):
            hours = list(range(0, min(144, long_max) + 1, 3))
            if long_max > 144:
                hours += list(range(150, long_max + 1, 6))
            return hours
        return list(range(0, short_max + 1, 3))
    if model == "aifs":
        mx = int(_env(env, "AIFS_MAX_HOUR", "240"))
        return list(range(0, mx + 1, 6))
    if model == "hrrr":
        short = int(_env(env, "HRRR_SHORT_HOUR", "18"))
        extended = int(_env(env, "HRRR_EXTENDED_HOUR", "48"))
        if cycle in (0, 6, 12, 18) and extended > short:
            return list(range(0, extended + 1))
        return list(range(0, short + 1))
    if model == "gfs":
        mx = int(_env(env, "GFS_MAX_HOUR", "240"))
        first = min(mx, 120)
        hours = list(range(0, first + 1, 3))
        if mx > 120:
            hours += list(range(126, mx + 1, 6))
        return hours
    raise KeyError(model)


def chunk_hours(hours: list[int], size: int) -> list[list[int]]:
    size = max(1, int(size))
    return [hours[i : i + size] for i in range(0, len(hours), size)]


def chunk_size(model: str, env: dict | None = None) -> int:
    override = _env(env, "HOURS_PER_CHUNK", "")
    if override:
        return max(1, int(override))
    return {"ecmwf": 4, "hrrr": 6, "aifs": 8, "gfs": 6}.get(model, 6)
