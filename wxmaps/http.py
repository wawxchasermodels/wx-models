"""Small HTTP helper with retries. Used for NOAA files and index checks."""

from __future__ import annotations

import time

import requests

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "wx-models/1.0 (personal model charts)"


def request(method: str, url: str, *, timeout: int = 90, retries: int = 4, **kwargs) -> requests.Response:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            resp = SESSION.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in {429, 500, 502, 503, 504} and attempt + 1 < retries:
                time.sleep(2 + attempt * 2)
                continue
            return resp
        except requests.RequestException as exc:
            last = exc
            if attempt + 1 < retries:
                time.sleep(2 + attempt * 2)
                continue
            raise
    if last:
        raise last
    raise RuntimeError(f"request failed for {url}")


def head_ok(url: str) -> bool:
    try:
        resp = request("HEAD", url, timeout=25, retries=2)
    except requests.RequestException:
        return False
    return resp.status_code == 200


def content_length(url: str) -> int | None:
    try:
        resp = request("HEAD", url, timeout=25, retries=2)
    except requests.RequestException:
        return None
    if resp.status_code != 200:
        return None
    raw = resp.headers.get("Content-Length")
    return int(raw) if raw and raw.isdigit() else None


def get_range(url: str, start: int, end: int | None) -> bytes:
    span = f"{start}-" if end is None else f"{start}-{end}"
    resp = request("GET", url, timeout=180, retries=3, headers={"Range": f"bytes={span}"})
    if resp.status_code not in {200, 206}:
        resp.raise_for_status()
    if end is not None and resp.status_code == 200:
        expected = end - start + 1
        if len(resp.content) > expected + 64:
            raise RuntimeError(f"server ignored a byte range for {url}")
    return resp.content
