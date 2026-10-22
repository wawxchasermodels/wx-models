"""Site name lives in brand.json at the repository root."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=1)
def load() -> dict:
    path = ROOT / "brand.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("siteName", "WX Models")
    data.setdefault("tagline", "A private desk for model charts")
    data.setdefault("pagesProject", "wx-models")
    return data


def site_name() -> str:
    return str(load()["siteName"])


def tagline() -> str:
    return str(load()["tagline"])


def pages_project() -> str:
    return str(load()["pagesProject"])
