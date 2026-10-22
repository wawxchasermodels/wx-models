"""Public-domain linework: Census TIGER/Line and Natural Earth."""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np

from wxmaps.brand import ROOT


@lru_cache(maxsize=8)
def lines(name: str) -> tuple[list[np.ndarray], list[tuple[float, float, float, float]]]:
    path = ROOT / "basemap" / f"{name}.json"
    if not path.exists():
        return [], []
    raw = json.loads(path.read_text(encoding="utf-8"))
    series = [np.asarray(line, dtype=np.float32) for line in raw["lines"] if len(line) >= 2]
    boxes = []
    for line in series:
        boxes.append(
            (
                float(line[:, 0].min()),
                float(line[:, 0].max()),
                float(line[:, 1].min()),
                float(line[:, 1].max()),
            )
        )
    return series, boxes


@lru_cache(maxsize=1)
def cities(region: str) -> tuple[tuple[str, float, float], ...]:
    path = ROOT / "basemap" / "cities.json"
    if not path.exists():
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get(region) or []
    return tuple((str(row["name"]), float(row["lon"]), float(row["lat"])) for row in rows)


def visible(name: str, west: float, east: float, south: float, north: float) -> list[np.ndarray]:
    series, boxes = lines(name)
    kept = []
    for line, (w, e, s, n) in zip(series, boxes):
        if e < west or w > east or n < south or s > north:
            continue
        kept.append(line)
    return kept
