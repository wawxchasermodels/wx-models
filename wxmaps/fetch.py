"""Download only the GRIB messages each chart needs."""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wxmaps.grib import Bag, clip_bag, merge_bags, read_grib
from wxmaps.http import content_length, get_range, head_ok, request
from wxmaps.models import WINDOW, Model, get_model
from wxmaps.noaa_idx import (
    GFS_SEL,
    HRRR_PRS,
    HRRR_SFC,
    byte_ranges,
    parse_idx,
    select_rows,
)
from wxmaps.steps import forecast_hours

SFC_PARAMS = ["2t", "2d", "10u", "10v", "10fg", "msl", "tp", "sf", "mucape", "ptype", "tprate"]
PL_PARAMS = ["gh", "t", "vo", "u", "v"]
PL_LEVELS = [500, 850]


def sources() -> list[str]:
    raw = os.environ.get("ECMWF_SOURCES", "aws,ecmwf,google")
    return [part.strip() for part in raw.split(",") if part.strip()]


def init_key(when: datetime) -> str:
    return when.astimezone(timezone.utc).strftime("%Y%m%d%H")


def parse_init(key: str) -> datetime:
    return datetime.strptime(key, "%Y%m%d%H").replace(tzinfo=timezone.utc)


def candidate_inits(model: str, now: datetime | None = None) -> list[datetime]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    step = 1 if model == "hrrr" else 6
    lookback = 30 if model == "hrrr" else 48
    floored = now.replace(minute=0, second=0, microsecond=0)
    floored = floored.replace(hour=(floored.hour // step) * step)
    if floored > now:
        floored -= timedelta(hours=step)
    found: list[datetime] = []
    cursor = floored
    while (now - cursor).total_seconds() <= lookback * 3600 and len(found) < 16:
        found.append(cursor)
        cursor -= timedelta(hours=step)
    return found


def _client(model: Model, source: str):
    from ecmwf.opendata import Client

    if model.id == "ecmwf" and model.resol != "0p1":
        raise RuntimeError("IFS charts use the 0.1 degree open data only")
    return Client(
        source=source,
        model=model.ecmwf_model,
        resol=model.resol,
        maximum_retries=4,
        retry_after=8,
        use_server_retry_after=False,
    )


def _index_urls(client, model: Model, when: datetime, hour: int) -> list[str]:
    levtypes = ["sfc", "pl"] if model.resol == "0p1" else [None]
    urls: list[str] = []
    for levtype in levtypes:
        request_body = {
            "date": when.strftime("%Y-%m-%d"),
            "time": when.hour,
            "step": int(hour),
            "stream": "oper",
            "type": "fc",
        }
        if levtype:
            request_body["levtype"] = levtype
        result = client._get_urls(request_body, use_index=False)
        for url in result.urls:
            if model.id == "ecmwf" and "/0p25/" in url:
                raise RuntimeError("refusing to fall back from IFS 0.1 degree to 0.25 degree")
            if model.id == "ecmwf" and "/0p1/" not in url:
                raise RuntimeError(f"IFS url is not 0.1 degree: {url}")
            if model.id == "aifs" and "/0p1/" in url:
                raise RuntimeError("AIFS is published at 0.25 degree only")
            base, _ext = os.path.splitext(url)
            urls.append(base + ".index")
    return urls


def ecmwf_ready(model: Model, when: datetime) -> str | None:
    hour = forecast_hours(model.id, when.hour)[-1]
    for source in sources():
        try:
            client = _client(model, source)
            urls = _index_urls(client, model, when, hour)
        except Exception as exc:
            print(f"  {model.id} {init_key(when)} {source}: {exc}")
            continue
        if urls and all(head_ok(url) for url in urls):
            return source
    return None


def noaa_ready(model_id: str, when: datetime) -> bool:
    hour = forecast_hours(model_id, when.hour)[-1]
    if model_id == "hrrr":
        return head_ok(_hrrr_url(when, hour, "sfc") + ".idx") and head_ok(_hrrr_url(when, hour, "prs") + ".idx")
    if model_id == "gfs":
        return head_ok(_gfs_url(when, hour) + ".idx")
    return False


def latest_ready(model_id: str, now: datetime | None = None) -> tuple[datetime, str] | None:
    model = get_model(model_id)
    for when in candidate_inits(model_id, now):
        if model.kind == "ecmwf":
            source = ecmwf_ready(model, when)
            if source:
                return when, source
        elif noaa_ready(model_id, when):
            return when, "noaa"
    return None


def load_hour(model_id: str, when: datetime, hour: int, source: str) -> Bag | None:
    model = get_model(model_id)
    if model.kind == "ecmwf":
        bag = _load_ecmwf(model, when, hour, source)
    elif model_id == "hrrr":
        bag = _load_noaa(_hrrr_parts(when, hour))
    elif model_id == "gfs":
        bag = _load_noaa([(_gfs_url(when, hour), GFS_SEL, hour)])
    else:
        raise KeyError(model_id)
    if bag is None:
        return None
    win = WINDOW
    return clip_bag(bag, win["west"], win["east"], win["south"], win["north"])


def _pull(client, target: Path, params: list[str], **request_body) -> bool:
    if target.exists():
        target.unlink()
    try:
        client.retrieve(target=str(target), param=params, **request_body)
    except Exception as exc:
        print(f"  skip {params}: {exc}")
        return False
    return target.exists() and target.stat().st_size > 200


def _load_ecmwf(model: Model, when: datetime, hour: int, source: str) -> Bag | None:
    client = _client(model, source)
    # Confirm this hour's 0.1° (or AIFS 0.25°) index exists. Never substitute a coarser IFS grid.
    if not all(head_ok(url) for url in _index_urls(client, model, when, hour)):
        print(f"  missing index for {model.id} {init_key(when)} f{hour:03d} on {source}")
        return None
    common = {
        "date": when.strftime("%Y-%m-%d"),
        "time": when.hour,
        "step": int(hour),
        "stream": "oper",
        "type": "fc",
    }
    with tempfile.TemporaryDirectory(prefix="wxgrib-") as tmp:
        root = Path(tmp)
        bags: list[Bag | None] = []
        sfc = root / "sfc.grib2"
        if _pull(client, sfc, SFC_PARAMS, levtype="sfc", **common):
            bags.append(read_grib(str(sfc)))
        else:
            core = root / "sfc-core.grib2"
            if not _pull(client, core, ["2t", "2d", "10u", "10v", "msl", "tp"], levtype="sfc", **common):
                return None
            bags.append(read_grib(str(core)))
            for param in ("10fg", "10fg3", "sf", "mucape", "ptype", "tprate"):
                piece = root / f"{param}.grib2"
                if _pull(client, piece, [param], levtype="sfc", **common):
                    bags.append(read_grib(str(piece)))
        pl = root / "pl.grib2"
        if _pull(client, pl, PL_PARAMS, levtype="pl", levelist=PL_LEVELS, **common):
            bags.append(read_grib(str(pl)))
        else:
            for params in (["z", "t", "u", "v", "vo"], ["z", "t", "u", "v"], ["gh", "t"]):
                piece = root / "pl-fallback.grib2"
                if _pull(client, piece, params, levtype="pl", levelist=PL_LEVELS, **common):
                    bags.append(read_grib(str(piece)))
                    break
    return merge_bags([bag for bag in bags if bag])


def _hrrr_url(when: datetime, hour: int, kind: str) -> str:
    stem = "wrfsfc" if kind == "sfc" else "wrfprs"
    return (
        "https://noaa-hrrr-bdp-pds.s3.amazonaws.com/"
        f"hrrr.{when:%Y%m%d}/conus/hrrr.t{when:%H}z.{stem}f{hour:02d}.grib2"
    )


def _gfs_url(when: datetime, hour: int) -> str:
    return (
        "https://noaa-gfs-bdp-pds.s3.amazonaws.com/"
        f"gfs.{when:%Y%m%d}/{when:%H}/atmos/gfs.t{when:%H}z.pgrb2.0p25.f{hour:03d}"
    )


def _hrrr_parts(when: datetime, hour: int):
    return [
        (_hrrr_url(when, hour, "sfc"), HRRR_SFC, hour),
        (_hrrr_url(when, hour, "prs"), HRRR_PRS, hour),
    ]


def _load_noaa(parts: list[tuple[str, list, int]]) -> Bag | None:
    with tempfile.TemporaryDirectory(prefix="wxgrib-") as tmp:
        path = Path(tmp) / "slice.grib2"
        with path.open("wb") as handle:
            for url, selectors, hour in parts:
                idx_resp = request("GET", url + ".idx", timeout=60, retries=3)
                if idx_resp.status_code != 200:
                    print(f"  no idx {url}")
                    continue
                rows = parse_idx(idx_resp.text)
                chosen = select_rows(rows, selectors, hour)
                if not chosen:
                    print(f"  no matching messages in {url}")
                    continue
                size = content_length(url)
                for start, end in byte_ranges(rows, chosen, size):
                    handle.write(get_range(url, start, end))
        if path.stat().st_size < 1000:
            return None
        return read_grib(str(path))
