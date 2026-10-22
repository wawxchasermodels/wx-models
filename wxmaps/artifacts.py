"""Pick the newest rendered runs out of GitHub Actions artifact metadata."""

from __future__ import annotations

import re
from collections import defaultdict

FRAME_RE = re.compile(r"^frames-(ecmwf|hrrr|aifs|gfs)-(\d{10})-c(\d+)$")
SEAL_RE = re.compile(r"^seal-(ecmwf|hrrr|aifs|gfs)-(\d{10})$")


def choose_frames(artifacts: list[dict], keep: int = 2) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for item in artifacts:
        if item.get("expired"):
            continue
        match = FRAME_RE.match(item.get("name", ""))
        if not match:
            continue
        groups[(match.group(1), match.group(2))].append(item)
    by_model: dict[str, list[str]] = defaultdict(list)
    for model, init in groups:
        by_model[model].append(init)
    chosen: list[dict] = []
    for model, inits in by_model.items():
        for init in sorted(set(inits), reverse=True)[:keep]:
            chosen.extend(groups[(model, init)])
    return chosen


def sealed_inits(artifacts: list[dict], model: str) -> set[str]:
    found = set()
    for item in artifacts:
        if item.get("expired"):
            continue
        match = SEAL_RE.match(item.get("name", ""))
        if match and match.group(1) == model:
            found.add(match.group(2))
    return found


def chunk_ids(artifacts: list[dict], model: str, init: str) -> set[str]:
    found = set()
    prefix = f"frames-{model}-{init}-c"
    for item in artifacts:
        if item.get("expired"):
            continue
        name = item.get("name", "")
        if name.startswith(prefix):
            match = FRAME_RE.match(name)
            if match:
                found.add(match.group(3))
    return found
