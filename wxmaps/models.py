"""Model catalog. IFS is 0.1° only. AIFS stays on its native 0.25° grid."""

from __future__ import annotations

from dataclasses import dataclass


REGIONS = {
    "us": {
        "label": "United States",
        "west": -128.0,
        "east": -65.0,
        "south": 23.2,
        "north": 50.6,
    },
    "wa": {
        "label": "Washington",
        "west": -125.35,
        "east": -116.55,
        "south": 45.35,
        "north": 49.15,
    },
}

# Window used to clip global grids before plotting. Covers both regions plus a margin.
WINDOW = {"west": -134.0, "east": -58.0, "south": 16.0, "north": 58.0}

ASPECTS = ("wide", "reel")


@dataclass(frozen=True)
class Model:
    id: str
    label: str
    kind: str  # ecmwf | hrrr | gfs
    attribution: str  # ecmwf | noaa
    ecmwf_model: str | None = None
    resol: str | None = None


MODELS: dict[str, Model] = {
    "ecmwf": Model(
        "ecmwf",
        "ECMWF IFS 9 km",
        "ecmwf",
        "ecmwf",
        ecmwf_model="ifs",
        resol="0p1",
    ),
    "hrrr": Model("hrrr", "HRRR", "hrrr", "noaa"),
    "aifs": Model(
        "aifs",
        "ECMWF AIFS (AI)",
        "ecmwf",
        "ecmwf",
        ecmwf_model="aifs-single",
        resol="0p25",
    ),
    "gfs": Model("gfs", "GFS", "gfs", "noaa"),
}


def get_model(model_id: str) -> Model:
    if model_id not in MODELS:
        raise KeyError(model_id)
    return MODELS[model_id]
