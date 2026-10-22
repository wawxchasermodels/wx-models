"""Decide which forecast hours still need images."""

from __future__ import annotations

import json
import os

import requests

from wxmaps.artifacts import chunk_ids, sealed_inits
from wxmaps.fetch import init_key, latest_ready, parse_init
from wxmaps.steps import chunk_hours, chunk_size, forecast_hours


def _artifacts() -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not token or not repo:
        return []
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{repo}/actions/artifacts?per_page=100"
    found: list[dict] = []
    while url:
        resp = requests.get(url, headers=headers, timeout=60)
        if resp.status_code != 200:
            print(f"artifact list failed: {resp.status_code}")
            return found
        body = resp.json()
        found.extend(body.get("artifacts", []))
        url = resp.links.get("next", {}).get("url")
    return found


def make_plan(model: str) -> dict:
    enabled = os.environ.get(f"WX_ENABLE_{model.upper()}", "1") not in {"0", "false", "False"}
    if not enabled:
        return _empty(model, "disabled")
    force = os.environ.get("WX_FORCE", "") in {"1", "true", "True"}
    dry = os.environ.get("WX_DRY_RUN", "") in {"1", "true", "True"}
    requested_init = os.environ.get("WX_INIT", "").strip()
    requested_hours = os.environ.get("WX_HOURS", "").strip()
    arts = [] if force or dry or not os.environ.get("GITHUB_TOKEN") else _artifacts()

    if requested_init:
        when = parse_init(requested_init)
        source = "aws" if model in {"ecmwf", "aifs"} else "noaa"
        if model in {"ecmwf", "aifs"}:
            from wxmaps.fetch import ecmwf_ready
            from wxmaps.models import get_model

            source_name = ecmwf_ready(get_model(model), when)
            if not source_name:
                return _empty(model, "requested run is not complete at the required resolution")
            source = source_name
        else:
            from wxmaps.fetch import noaa_ready

            if not noaa_ready(model, when):
                return _empty(model, "requested NOAA run is not complete")
        init = init_key(when)
        hours = forecast_hours(model, when.hour)
    else:
        ready = latest_ready(model)
        if not ready:
            return _empty(model, "no complete run")
        when, source = ready
        init = init_key(when)
        hours = forecast_hours(model, when.hour)

    if requested_hours:
        hours = [int(part) for part in requested_hours.split(",") if part.strip()]
    if dry and not requested_hours:
        hours = hours[:2]

    if not force and not dry and init in sealed_inits(arts, model):
        return _empty(model, f"{init} already sealed")

    pieces = chunk_hours(hours, chunk_size(model))
    existing = set() if force or dry else chunk_ids(arts, model, init)
    include = []
    pending = []
    for index, group in enumerate(pieces):
        chunk = f"{index:02d}"
        if chunk in existing:
            continue
        pending.append(chunk)
        include.append(
            {
                "model": model,
                "init": init,
                "source": source,
                "chunk": chunk,
                "hours": ",".join(str(h) for h in group),
            }
        )
    all_ids = [f"{index:02d}" for index in range(len(pieces))]
    if not include:
        return {
            "has_work": "true",
            "seal_only": "true",
            "model": model,
            "init": init,
            "source": source,
            "include": json.dumps([{"model": model, "init": init, "source": source, "chunk": "00", "hours": "0"}]),
            "chunk_ids": json.dumps(all_ids),
            "reason": "chunks already uploaded",
        }
    return {
        "has_work": "true",
        "seal_only": "false",
        "model": model,
        "init": init,
        "source": source,
        "include": json.dumps(include),
        "chunk_ids": json.dumps(all_ids),
        "reason": f"{len(include)} chunk(s) for {init}",
    }


def _empty(model: str, reason: str) -> dict:
    return {
        "has_work": "false",
        "seal_only": "false",
        "model": model,
        "init": "",
        "source": "",
        "include": json.dumps([{"model": model, "init": "none", "source": "aws", "chunk": "00", "hours": "0"}]),
        "chunk_ids": "[]",
        "reason": reason,
    }
