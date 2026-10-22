"""Command line for planning, rendering, and assembling the static site."""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import requests

from wxmaps.artifacts import choose_frames
from wxmaps.plan import _artifacts, make_plan


def _emit(plan: dict) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{key}={value}" for key, value in plan.items()]
    text = "\n".join(lines) + "\n"
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text)
    print(text, end="")


def _github_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def cmd_plan(args: argparse.Namespace) -> int:
    plan = make_plan(args.model)
    print(f"plan {args.model}: {plan['reason']}", file=sys.stderr)
    _emit(plan)
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    from wxmaps.render import render_hours

    hours = [int(part) for part in args.hours.split(",") if part.strip()]
    fields = set(args.fields.split(",")) if args.fields else None
    regions = args.regions.split(",") if args.regions else None
    aspects = args.aspects.split(",") if args.aspects else None
    result = render_hours(
        args.model,
        args.init,
        hours,
        args.source,
        Path(args.out),
        args.chunk,
        fields=fields,
        regions=regions,
        aspects=aspects,
    )
    return 0 if result["written"] else 1


def cmd_assemble(args: argparse.Namespace) -> int:
    from wxmaps.assemble import assemble

    manifest = assemble(Path(args.store), Path(args.dest), keep=args.keep)
    print(f"assembled {sum(len(m['runs']) for m in manifest['models'].values())} runs -> {args.dest}")
    return 0


def cmd_seal(args: argparse.Namespace) -> int:
    payload = {
        "model": args.model,
        "init": args.init,
        "chunks": json.loads(args.chunks),
    }
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(path)
    return 0


def cmd_gate(_args: argparse.Namespace) -> int:
    event = os.environ.get("GITHUB_EVENT_NAME", "")
    if event == "workflow_dispatch":
        print("true")
        return 0
    run_id = os.environ.get("TRIGGER_RUN_ID", "")
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not (run_id and repo and token):
        print("false")
        return 0
    resp = requests.get(
        f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs?per_page=100",
        headers=_github_headers(),
        timeout=60,
    )
    if resp.status_code != 200:
        print("false")
        return 0
    ok = any("seal" in job.get("name", "").lower() and job.get("conclusion") == "success" for job in resp.json().get("jobs", []))
    print("true" if ok else "false")
    return 0


def cmd_collect(args: argparse.Namespace) -> int:
    dest = Path(args.dest)
    dest.mkdir(parents=True, exist_ok=True)
    chosen = choose_frames(_artifacts(), keep=args.keep)
    repo = os.environ["GITHUB_REPOSITORY"]
    print(f"downloading {len(chosen)} frame artifacts")
    for item in chosen:
        url = f"https://api.github.com/repos/{repo}/actions/artifacts/{item['id']}/zip"
        resp = requests.get(url, headers=_github_headers(), allow_redirects=False, timeout=60)
        loc = resp.headers.get("Location")
        if not loc:
            raise SystemExit(f"no download url for {item['name']}: {resp.status_code}")
        blob = requests.get(loc, timeout=300)
        blob.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(blob.content)) as archive:
            for info in archive.infolist():
                name = info.filename
                if name.startswith("/") or ".." in Path(name).parts:
                    continue
                archive.extract(info, dest)
        print(f"  {item['name']}")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from wxmaps.assemble import assemble
    from wxmaps.fetch import init_key, latest_ready
    from wxmaps.render import render_hours
    from wxmaps.steps import forecast_hours

    store = Path(args.store)
    wanted = [part.strip() for part in args.models.split(",") if part.strip()]
    summary = []
    for model in wanted:
        ready = latest_ready(model)
        if not ready:
            print(f"demo skip {model}: no complete run")
            summary.append(f"{model}: missing")
            continue
        when, source = ready
        hours = forecast_hours(model, when.hour)
        prefer = {
            "ecmwf": [12, 18],
            "hrrr": [3, 6],
            "aifs": [12, 24],
            "gfs": [12, 24],
        }.get(model, hours[:2])
        use = [hour for hour in prefer if hour in hours] or hours[:2]
        print(f"demo {model} {init_key(when)} hours {use} via {source}")
        result = render_hours(model, init_key(when), use, source, store, chunk="demo")
        summary.append(f"{model}: {result['written']} images from {init_key(when)}")
    manifest = assemble(store, Path(args.dest), keep=2)
    print("DEMO", "; ".join(summary))
    print("models", list(manifest["models"]))
    return 0 if manifest["models"] else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wxmaps")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan")
    plan.add_argument("--model", required=True)
    plan.set_defaults(func=cmd_plan)

    render = sub.add_parser("render")
    render.add_argument("--model", required=True)
    render.add_argument("--init", required=True)
    render.add_argument("--hours", required=True)
    render.add_argument("--source", default="aws")
    render.add_argument("--chunk", default="00")
    render.add_argument("--out", default="frames")
    render.add_argument("--fields", default="")
    render.add_argument("--regions", default="")
    render.add_argument("--aspects", default="")
    render.set_defaults(func=cmd_render)

    built = sub.add_parser("assemble")
    built.add_argument("--store", required=True)
    built.add_argument("--dest", required=True)
    built.add_argument("--keep", type=int, default=2)
    built.set_defaults(func=cmd_assemble)

    seal = sub.add_parser("seal")
    seal.add_argument("--model", required=True)
    seal.add_argument("--init", required=True)
    seal.add_argument("--chunks", required=True)
    seal.add_argument("--out", required=True)
    seal.set_defaults(func=cmd_seal)

    gate = sub.add_parser("gate")
    gate.set_defaults(func=cmd_gate)

    collect = sub.add_parser("collect")
    collect.add_argument("--dest", required=True)
    collect.add_argument("--keep", type=int, default=2)
    collect.set_defaults(func=cmd_collect)

    demo = sub.add_parser("demo")
    demo.add_argument("--models", default="ecmwf,hrrr,aifs,gfs")
    demo.add_argument("--store", default="tmp/demo-store")
    demo.add_argument("--dest", default="tmp/demo-dist")
    demo.set_defaults(func=cmd_demo)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
