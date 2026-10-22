"""Render a slice of forecast hours for one model run."""

from __future__ import annotations

import json
from pathlib import Path

from wxmaps.derive import build_payloads
from wxmaps.fetch import init_key, load_hour, parse_init
from wxmaps.models import ASPECTS, REGIONS, get_model
from wxmaps.plot import render_plate


def render_hours(
    model_id: str,
    init: str,
    hours: list[int],
    source: str,
    out_dir: Path,
    chunk: str,
    fields: set[str] | None = None,
    regions: list[str] | None = None,
    aspects: list[str] | None = None,
) -> dict:
    model = get_model(model_id)
    when = parse_init(init)
    regions = regions or list(REGIONS)
    aspects = aspects or list(ASPECTS)
    field_hours: dict[str, dict] = {}
    written = 0
    for hour in hours:
        print(f"render {model_id} {init} f{int(hour):03d}", flush=True)
        try:
            bag = load_hour(model_id, when, int(hour), source)
        except Exception as exc:
            print(f"  download failed f{int(hour):03d}: {exc}")
            continue
        if bag is None:
            print(f"  no data f{int(hour):03d}")
            continue
        try:
            payloads = build_payloads(bag, model_id, int(hour))
        except Exception as exc:
            print(f"  derive failed f{int(hour):03d}: {exc}")
            continue
        names = sorted({p.short for p in bag.messages})
        print("  messages:", ", ".join(names))
        for payload in payloads:
            if fields and payload.field_id not in fields:
                continue
            meta = field_hours.setdefault(
                payload.field_id,
                {"label": payload.title, "unit": payload.unit, "hours": []},
            )
            drew = False
            for region in regions:
                for aspect in aspects:
                    dest = (
                        out_dir
                        / model_id
                        / init
                        / payload.field_id
                        / region
                        / aspect
                        / f"f{int(hour):03d}.webp"
                    )
                    try:
                        render_plate(
                            payload,
                            region,
                            aspect,
                            when,
                            int(hour),
                            model.label,
                            model.attribution,
                            dest,
                        )
                    except Exception as exc:
                        print(f"  plate failed {payload.field_id} {region} {aspect}: {exc}")
                        continue
                    drew = True
                    written += 1
            if drew and int(hour) not in meta["hours"]:
                meta["hours"].append(int(hour))
    record = {
        "model": model_id,
        "init": init_key(when),
        "model_label": model.label,
        "attribution": model.attribution,
        "chunk": chunk,
        "fields": field_hours,
    }
    if written:
        marker = out_dir / model_id / init / f"_chunk_{chunk}.json"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"wrote {written} images")
    return {"written": written, "record": record}
