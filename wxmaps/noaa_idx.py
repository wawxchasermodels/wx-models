"""Parse NOAA wgrib-style .idx inventories and choose byte ranges."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class IdxRow:
    start: int
    name: str
    level: str
    ftime: str


@dataclass(frozen=True)
class Selector:
    name: str
    level: str
    mode: str  # instant | total


_HOUR_ACC = re.compile(r"(\d+)\s*-\s*(\d+)\s+hour", re.IGNORECASE)
_DAY_ACC = re.compile(r"(\d+)\s*-\s*(\d+)\s+day", re.IGNORECASE)


def parse_idx(text: str) -> list[IdxRow]:
    rows: list[IdxRow] = []
    for line in text.splitlines():
        parts = line.strip().split(":")
        if len(parts) < 6:
            continue
        try:
            start = int(parts[1])
        except ValueError:
            continue
        rows.append(IdxRow(start, parts[3], parts[4], parts[5]))
    rows.sort(key=lambda r: r.start)
    return rows


def accum_span(ftime: str) -> tuple[int, int] | None:
    """Return (start_hour, end_hour) for an accumulation record, else None."""
    low = ftime.lower()
    if "acc" not in low or "ave" in low:
        return None
    match = _HOUR_ACC.search(low)
    if match:
        return int(match.group(1)), int(match.group(2))
    match = _DAY_ACC.search(low)
    if match:
        return int(match.group(1)) * 24, int(match.group(2)) * 24
    return None


def is_instant(ftime: str, hour: int) -> bool:
    low = ftime.lower()
    if any(tok in low for tok in ("acc", "ave", "max", "min")):
        return False
    if hour == 0 and ("anl" in low or "0 hour" in low):
        return True
    return f"{int(hour)} hour" in low


def is_run_total(ftime: str, hour: int) -> bool:
    span = accum_span(ftime)
    return span == (0, int(hour))


def select_rows(rows: list[IdxRow], selectors: list[Selector], hour: int) -> list[IdxRow]:
    chosen: list[IdxRow] = []
    for sel in selectors:
        if sel.mode == "total" and int(hour) == 0:
            continue
        hits = [
            row
            for row in rows
            if row.name == sel.name
            and row.level == sel.level
            and (is_run_total(row.ftime, hour) if sel.mode == "total" else is_instant(row.ftime, hour))
        ]
        if hits:
            chosen.append(hits[0])
    return chosen


def byte_ranges(rows: list[IdxRow], chosen: list[IdxRow], file_size: int | None) -> list[tuple[int, int | None]]:
    """Inclusive ranges. The last message uses file_size-1, or an open end if size is unknown."""
    starts = [row.start for row in rows]
    ranges: list[tuple[int, int | None]] = []
    for row in chosen:
        idx = starts.index(row.start)
        if idx + 1 < len(starts):
            end = starts[idx + 1] - 1
        elif file_size:
            end = file_size - 1
        else:
            end = None
        if end is None or end >= row.start:
            ranges.append((row.start, end))
    return ranges


HRRR_SFC = [
    Selector("TMP", "2 m above ground", "instant"),
    Selector("DPT", "2 m above ground", "instant"),
    Selector("UGRD", "10 m above ground", "instant"),
    Selector("VGRD", "10 m above ground", "instant"),
    Selector("GUST", "surface", "instant"),
    Selector("MSLMA", "mean sea level", "instant"),
    Selector("REFC", "entire atmosphere", "instant"),
    Selector("APCP", "surface", "total"),
    Selector("WEASD", "surface", "total"),
    Selector("CAPE", "surface", "instant"),
    Selector("CSNOW", "surface", "instant"),
    Selector("CRAIN", "surface", "instant"),
    Selector("CFRZR", "surface", "instant"),
    Selector("CICEP", "surface", "instant"),
    Selector("HGT", "500 mb", "instant"),
    Selector("TMP", "850 mb", "instant"),
]

HRRR_PRS = [Selector("ABSV", "500 mb", "instant")]

GFS_SEL = [
    Selector("TMP", "2 m above ground", "instant"),
    Selector("DPT", "2 m above ground", "instant"),
    Selector("UGRD", "10 m above ground", "instant"),
    Selector("VGRD", "10 m above ground", "instant"),
    Selector("GUST", "surface", "instant"),
    Selector("PRMSL", "mean sea level", "instant"),
    Selector("PRATE", "surface", "instant"),
    Selector("APCP", "surface", "total"),
    Selector("CAPE", "surface", "instant"),
    Selector("CSNOW", "surface", "instant"),
    Selector("CRAIN", "surface", "instant"),
    Selector("CFRZR", "surface", "instant"),
    Selector("CICEP", "surface", "instant"),
    Selector("HGT", "500 mb", "instant"),
    Selector("ABSV", "500 mb", "instant"),
    Selector("TMP", "850 mb", "instant"),
    Selector("SNOD", "surface", "instant"),
]
