"""Build the static site from rendered frames. Keeps the newest runs only."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from wxmaps.attribution import footer_html
from wxmaps.brand import ROOT, load
from wxmaps.models import REGIONS


def assemble(store: Path, dest: Path, keep: int = 2) -> dict:
    frames_root = store
    # Accept either store/frames/... or store/{model}/...
    if (store / "frames").is_dir() and not any((store / name).is_dir() for name in ("ecmwf", "hrrr", "aifs", "gfs")):
        frames_root = store / "frames"
    manifest = _manifest(frames_root, keep)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    web = ROOT / "web"
    for item in web.iterdir():
        target = dest / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    _stamp_html(dest / "index.html")
    kept = {(model, run["init"]) for model, body in manifest["models"].items() for run in body["runs"]}
    out_frames = dest / "frames"
    if frames_root.exists():
        for model_dir in frames_root.iterdir():
            if not model_dir.is_dir():
                continue
            for init_dir in model_dir.iterdir():
                if (model_dir.name, init_dir.name) not in kept:
                    continue
                for path in init_dir.rglob("*.webp"):
                    rel = path.relative_to(frames_root)
                    target = out_frames / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
    (dest / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (dest / "brand.json").write_text(json.dumps(load(), indent=2), encoding="utf-8")
    return manifest


def _stamp_html(path: Path) -> None:
    brand = load()
    year = datetime.now(timezone.utc).year
    text = path.read_text(encoding="utf-8")
    text = text.replace("__SITE_NAME__", brand["siteName"])
    text = text.replace("__TAGLINE__", brand["tagline"])
    text = text.replace("__FOOTER__", footer_html(year))
    path.write_text(text, encoding="utf-8")


def _manifest(frames_root: Path, keep: int) -> dict:
    models: dict = {}
    if frames_root.exists():
        for model_dir in sorted(frames_root.iterdir()):
            if not model_dir.is_dir() or model_dir.name.startswith("."):
                continue
            runs = []
            for init_dir in sorted(model_dir.iterdir(), reverse=True):
                if not init_dir.is_dir():
                    continue
                fields: dict = {}
                label = model_dir.name
                attribution = "noaa"
                for chunk in init_dir.glob("_chunk_*.json"):
                    data = json.loads(chunk.read_text(encoding="utf-8"))
                    label = data.get("model_label", label)
                    attribution = data.get("attribution", attribution)
                    for field_id, meta in data.get("fields", {}).items():
                        slot = fields.setdefault(
                            field_id,
                            {"label": meta.get("label", field_id), "unit": meta.get("unit", ""), "hours": []},
                        )
                        for hour in meta.get("hours", []):
                            if hour not in slot["hours"]:
                                slot["hours"].append(int(hour))
                for meta in fields.values():
                    meta["hours"].sort()
                fields = {k: v for k, v in fields.items() if v["hours"]}
                if not fields:
                    continue
                runs.append({"init": init_dir.name, "fields": fields})
            runs = runs[:keep]
            if runs:
                models[model_dir.name] = {
                    "label": label,
                    "attribution": attribution,
                    "runs": runs,
                }
    order = ["ecmwf", "hrrr", "aifs", "gfs"]
    models = {key: models[key] for key in order if key in models} | {
        key: value for key, value in models.items() if key not in order
    }
    return {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "siteName": load()["siteName"],
        "regions": {key: {"label": value["label"]} for key, value in REGIONS.items()},
        "aspects": {"wide": {"label": "Wide", "ratio": "16:9"}, "reel": {"label": "Reel", "ratio": "9:16"}},
        "models": models,
    }
