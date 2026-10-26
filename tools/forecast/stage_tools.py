#!/usr/bin/env python3
"""Staged forecast builds: plan a stage, collect carried products, write site state, and poll for new data.

Four stages per 00Z/12Z cycle publish each model group as soon as its data is out:
  s1 HRRR | s2 RRFS + GFS | s3 AIFS + EPS/AIFS ENS maps + EPS meteograms | s4 ECMWF 9 km (IFS 0.1 deg)
Each stage renders only its groups, then deploys the whole site with the other groups carried forward from the
artifacts of the runs that last built them. Which run built which group is kept in a small `site-state` artifact
(JSON) uploaded after every successful deploy; the newest one is found through the artifacts API.

Subcommands:
  plan     (forecast-site.yml plan job)   -> GITHUB_OUTPUT: go, stage, cycle, pin, menu_models, meteo_srcs, carry, min_files
  collect  (forecast-deploy.yml)          -> downloads carried artifacts into .site_batch and merges meteogram parts
  state    (forecast-site.yml state job)  -> writes the new site-state.json
  poll     (forecast-poll.yml)            -> dispatches the next stage whose models have a new, unpublished run
Needs GH_TOKEN (actions: read; poll dispatch needs actions: write) and GITHUB_REPOSITORY.
"""
import argparse, datetime as dt, fnmatch, glob, json, os, re, shutil, subprocess, sys, tempfile, urllib.request

UTC = dt.timezone.utc
STAGES = ("s1", "s2", "s3", "s4")
GROUPS = {"s1": ["hrrr"], "s2": ["rrfs", "gfs"], "s3": ["aifs", "ens"], "s4": ["ifs"]}
MENU = {"s1": "hrrr", "s2": "rrfs", "s3": "aifs", "s4": "ifs"}
METEO = {"s1": ["hrrr"], "s2": ["rrfs"], "s3": ["eps"], "s4": []}
# artifact names per group; the same jobs make them in full builds and stage runs
PATTERNS = {"hrrr": ["hires-hrrr-maps", "menu-hrrr-*", "menu-reuse-hrrr"],
            "rrfs": ["hires-rrfs-maps", "menu-rrfs-*", "menu-reuse-rrfs"],
            "gfs": ["gfs-maps"],
            "aifs": ["aifs-maps", "temp-maps", "menu-aifs-*", "menu-reuse-aifs"],
            "ens": ["ens-*"],
            "ifs": ["mslp-maps", "temp-maps", "menu-ifs-*", "menu-reuse-ifs"]}
GROUP_METEO = {"hrrr": "hrrr", "rrfs": "rrfs", "ens": "eps"}   # meteogram source carried with each group
E = "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/"
READY = {   # last file of each stage's models; a stage is ready for cycle c when every one answers
    "s1": ["https://noaa-hrrr-bdp-pds.s3.amazonaws.com/hrrr.{d}/conus/hrrr.t{h:02d}z.wrfsfcf48.grib2.idx"],
    "s2": ["https://noaa-rrfs-ops-pds.s3.amazonaws.com/rrfs.{d}/{h:02d}/rrfs.t{h:02d}z.2dfld.3km.f084.conus.grib2.idx",
           "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.{d}/{h:02d}/atmos/gfs.t{h:02d}z.pgrb2.0p25.f240.idx"],
    "s3": [E + "aifs-single/0p25/oper/{d}{h:02d}0000-240h-oper-fc.index",
           E + "ifs/0p25/enfo/{d}{h:02d}0000-240h-enfo-ef.index",
           E + "aifs-ens/0p25/enfo/{d}{h:02d}0000-240h-enfo-pf.index"],
    "s4": [E + "ifs/0p1/oper/{d}{h:02d}0000-240h-oper-fc-sfc.index"],
}
# backup crons (UTC) -> stage; they publish only if the poller has not already done it
BACKUP = {"0 2,14 * * *": "s1", "50 4,16 * * *": "s2", "50 7,19 * * *": "s3", "50 9,21 * * *": "s4"}
FULL_CRON = "50 21 * * *"
MIN_FRACTION = 0.85
PRODUCTS = {"s1": "hrrr,menu", "s2": "rrfs,gfs,menu", "s3": "aifs,temps,menu,ens", "s4": "mslp,temps,menu"}


def sh(*cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode:
        sys.exit(f"command failed ({r.returncode}): {' '.join(cmd[:4])} ...\n{r.stderr[-800:]}")
    return r


def repo(): return os.environ["GITHUB_REPOSITORY"]


def out(**kv):
    f = os.environ.get("GITHUB_OUTPUT")
    for k, v in kv.items():
        line = f"{k}={v if isinstance(v, str) else json.dumps(v, separators=(',', ':'))}"
        print(line)
        if f:
            open(f, "a").write(line + "\n")


def exists(url):
    try:
        req = urllib.request.Request(url, headers={"Range": "bytes=0-10", "User-Agent": "wx-models-stage"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status in (200, 206)
    except Exception:
        return False


def ready_cycle(stage, now=None, back=3):
    """Newest 00Z/12Z cycle whose last files for this stage are all out (checks the last `back` cycles)."""
    now = now or dt.datetime.now(UTC)
    c = now.replace(minute=0, second=0, microsecond=0, hour=12 if now.hour >= 12 else 0)
    for _ in range(back):
        if all(exists(u.format(d=f"{c:%Y%m%d}", h=c.hour)) for u in READY[stage]):
            return f"{c:%Y%m%d%H}"
        c -= dt.timedelta(hours=12)
    return ""


def latest_state():
    """(run_id, state dict) of the newest unexpired site-state artifact, or (None, {})."""
    r = sh("gh", "api", f"repos/{repo()}/actions/artifacts?name=site-state&per_page=20", check=False)
    if r.returncode:
        print("::warning::cannot list site-state artifacts:", r.stderr[-300:]); return None, {}
    arts = [a for a in json.loads(r.stdout).get("artifacts", []) if not a.get("expired")]
    arts.sort(key=lambda a: a["created_at"], reverse=True)
    for a in arts:
        rid = str(a["workflow_run"]["id"])
        with tempfile.TemporaryDirectory() as td:
            if sh("gh", "run", "download", rid, "-R", repo(), "-n", "site-state", "-D", td, check=False).returncode == 0:
                f = os.path.join(td, "site-state.json")
                if os.path.exists(f):
                    return rid, json.load(open(f))
    return None, {}


def seed_state(run_id):
    """State that points every group at one full-build run (bootstrap). Items are [run_id, artifact pattern]."""
    rid = str(run_id)
    return {"seeded_from": rid, "files_main": 0, "stages": {},
            "groups": {g: {"items": [[rid, p] for p in PATTERNS[g]],
                           "meteo": [[rid, "meteograms"]] if g in GROUP_METEO else [], "cycle": ""} for g in PATTERNS}}


def run_artifacts(run_id):
    r = sh("gh", "api", f"repos/{repo()}/actions/runs/{run_id}/artifacts?per_page=100")
    return {a["name"] for a in json.loads(r.stdout).get("artifacts", []) if not a.get("expired")}


# ---------------------------------------------------------------------------------------------------------- plan
def cmd_plan(a):
    stage = a.stage or BACKUP.get(a.schedule, "all")   # schedule: backup stage cron, or the 21:50 full build
    if stage == "all":
        out(stage="all", go="true", cycle="", pin="12" if a.event == "schedule" else "", products=os.environ.get("PRODUCTS", ""),
            menu_models="", meteo_srcs="[]", carry="[]", min_files="0", prev_state="{}", stage_patterns="")
        return
    if stage not in STAGES:
        sys.exit(f"unknown stage {stage}")
    cycle = a.cycle or ready_cycle(stage)
    if not re.fullmatch(r"\d{8}(00|12)", cycle or ""):
        print(f"::notice::{stage}: no complete 00Z/12Z run found yet; nothing to do")
        out(stage=stage, go="false", cycle="", pin="", products="", menu_models="", meteo_srcs="[]", carry="[]", min_files="0",
            prev_state="{}", stage_patterns="")
        return
    rid, st = latest_state()
    if a.seed_run:
        rid, st = "seed", seed_state(a.seed_run)
        have = run_artifacts(a.seed_run)
        for rec in st["groups"].values():
            rec["items"] = [i for i in rec["items"] if any(fnmatch.fnmatch(n, i[1]) for n in have)]
        print(f"seeding carried groups from full-build run {a.seed_run}")
    if not st:
        sys.exit("no site-state artifact found: run a full build (stage=all) or pass seed_run=<full build run id>")
    published = st.get("stages", {}).get(stage, "")
    go = "true"
    if a.event == "schedule" and published >= cycle:
        print(f"::notice::{stage} {cycle} already published (state {published}); backup cron does nothing")
        go = "false"
    # every group is carried, the stage's own too (fallback if one of its jobs fails); the new run's artifacts are laid
    # over them in the deploy and only the newest cycle of each product is kept
    carry = [{"group": g, "items": rec["items"], "meteo": rec.get("meteo", [])} for g, rec in st["groups"].items()]
    min_files = int(st.get("files_main", 0) * MIN_FRACTION)
    print(f"stage {stage} cycle {cycle}; carried from state run {rid}: " +
          ", ".join(f"{c['group']}<-{sorted({i[0] for i in c['items']})}" for c in carry) + f"; min main files {min_files}")
    pats = "{" + ",".join(p for g in GROUPS[stage] for p in PATTERNS[g]) + "}"
    out(stage=stage, go=go, cycle=cycle, pin=cycle[-2:], products=PRODUCTS[stage] if go == "true" else "", menu_models=MENU[stage],
        meteo_srcs=METEO[stage] if go == "true" else [], carry=carry, min_files=str(min_files), prev_state=st, stage_patterns=pats)


# ------------------------------------------------------------------------------------------------------- collect
def merge_tree(src, dst):
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src); os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            shutil.copy2(os.path.join(root, f), os.path.join(dst, rel, f))


def prune_old_cycles(batch):
    """Keep only the newest cycle of each product dir (<cycle>/<product>/...), so carried and new runs never mix."""
    newest = {}
    for d in glob.glob(f"{batch}/*/*/"):
        cyc, prod = d.rstrip("/").split("/")[-2:]
        if re.fullmatch(r"\d{10}", cyc) and cyc > newest.get(prod, ""):
            newest[prod] = cyc
    n = 0
    for d in glob.glob(f"{batch}/*/*/"):
        cyc, prod = d.rstrip("/").split("/")[-2:]
        if re.fullmatch(r"\d{10}", cyc) and cyc != newest[prod]:
            shutil.rmtree(d); n += 1
    for d in glob.glob(f"{batch}/*/"):
        if not os.listdir(d):
            os.rmdir(d)
    print(f"pruned {n} older-cycle product dirs")


def merge_meteo(parts, dst):
    """Overlay meteogram parts oldest first; made.json is replaced per source by the newer part."""
    os.makedirs(dst, exist_ok=True)
    mf = os.path.join(dst, "made.json"); made = json.load(open(mf)) if os.path.exists(mf) else {}
    for p in parts:
        pm = os.path.join(p, "made.json")
        if not os.path.exists(pm):
            continue
        j = json.load(open(pm))
        for src in j:
            shutil.rmtree(os.path.join(dst, src), ignore_errors=True)
            if os.path.isdir(os.path.join(p, src)):
                merge_tree(os.path.join(p, src), os.path.join(dst, src))
            made[src] = j[src]
            print(f"meteograms {src}: {sum(len(t) for t in j[src].values())} charts from {p}")
    json.dump(made, open(mf, "w"), indent=1)


def cmd_collect(a):
    carry = json.loads(a.carry or "[]")
    batch, work = a.batch, tempfile.mkdtemp(prefix="carry_")
    os.makedirs(batch, exist_ok=True)
    jobs = set()   # (run_id, pattern, kind)
    for c in carry:
        jobs |= {(rid, p, "maps") for rid, p in c["items"]} | {(rid, p, "meteo") for rid, p in c.get("meteo", [])}
    meteo_parts = []
    for rid, p, kind in sorted(jobs, key=lambda j: (int(j[0]), j[1])):
        d = os.path.join(work, kind, rid, re.sub(r"\W", "_", p))
        r = sh("gh", "run", "download", rid, "-R", repo(), "-p", p, "-D", d, check=False)
        if r.returncode and "no valid artifacts" in (r.stderr + r.stdout).lower():
            print(f"::warning::carried artifact {p} not found in run {rid}; skipped (file-count check guards the deploy)")
            continue
        if r.returncode:
            sys.exit(f"cannot download carried artifact {p} from run {rid} (expired?): {r.stderr[-300:]}")
        subs = [os.path.join(d, s) for s in sorted(os.listdir(d))]   # gh -p puts each artifact in its own dir
        for s in subs:
            if kind == "maps":
                merge_tree(s, batch)
            else:
                meteo_parts.append(s)
        print(f"carried {kind} {p} from run {rid}: {len(subs)} artifact(s)")
    if a.meteo_cur and os.path.isdir(a.meteo_cur):
        meteo_parts += [os.path.join(a.meteo_cur, s) for s in sorted(os.listdir(a.meteo_cur))]
    prune_old_cycles(batch)
    if meteo_parts or a.meteo_cur:
        merge_meteo(meteo_parts, a.meteo_dst)
    shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------------------------------------- state
def cmd_state(a):
    run_id, prev = os.environ["GITHUB_RUN_ID"], json.loads(a.prev_state or "{}")
    now = dt.datetime.now(UTC).isoformat(timespec="minutes")
    have = run_artifacts(run_id)
    match = lambda p: any(fnmatch.fnmatch(n, p) for n in have)
    if a.stage == "all":
        st = seed_state(run_id); st.pop("seeded_from")
        for g, rec in st["groups"].items():
            rec["items"] = [i for i in rec["items"] if match(i[1])]
            rec["meteo"] = [i for i in rec["meteo"] if match(i[1])]
            rec["cycle"] = a.cycle
        st["stages"] = {s_: a.cycle for s_ in STAGES}
    else:
        st = prev; st.pop("seeded_from", None)
        for g in GROUPS[a.stage]:
            old = st["groups"].get(g, {"items": [], "meteo": []})
            items = [[run_id, p] if match(p) else None for p in PATTERNS[g]]
            items = [i for i in items if i] + [i for i in old["items"] if not match(i[1])]   # failed jobs: keep the older run
            meteo = old.get("meteo", [])
            src = GROUP_METEO.get(g)
            if src in METEO[a.stage] and match(f"meteo-{src}"):
                meteo = [[run_id, f"meteo-{src}"]]
            st["groups"][g] = {"items": items, "meteo": meteo, "cycle": a.cycle, "at": now}
            print(f"{g}: new {[i[1] for i in items if i[0] == run_id]}, kept {[i for i in items if i[0] != run_id]}")
        st.setdefault("stages", {})[a.stage] = a.cycle
    st.update(files_main=int(a.files_main or 0), files_meteo=int(a.files_meteo or 0), updated=now, run_id=run_id, stage=a.stage)
    json.dump(st, open(a.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in st.items() if k != "groups"}))
    for g, r in st["groups"].items():
        print(f"  {g}: runs {sorted({i[0] for i in r['items'] + r['meteo']})} cycle {r.get('cycle')}")


# ---------------------------------------------------------------------------------------------------------- poll
def cmd_poll(a):
    r = sh("gh", "run", "list", "-R", repo(), "-w", "forecast-site.yml", "-L", "20", "--json", "status,displayTitle,databaseId")
    busy = [x for x in json.loads(r.stdout) if x["status"] in ("queued", "in_progress", "waiting", "pending", "requested")]
    if busy:
        print(f"forecast-site busy ({busy[0]['displayTitle']}, run {busy[0]['databaseId']}); next poll will check again")
        return
    _, st = latest_state()
    if not st:
        print("::warning::no site-state artifact; poller waits for a full build"); return
    due = []
    for s in STAGES:
        c = ready_cycle(s)
        pub = st.get("stages", {}).get(s, "")
        print(f"{s}: newest ready {c or '-'}; published {pub or '-'}")
        if c and c > pub:
            due.append((c, STAGES.index(s), s))
    if not due:
        print("nothing new"); return
    c, _, s = min(due)
    print(f"dispatch {s} for {c}")
    if a.dry_run:
        print("dry run: not dispatching"); return
    sh("gh", "workflow", "run", "forecast-site.yml", "-R", repo(), "--ref", a.ref, "-f", f"stage={s}", "-f", f"cycle={c}")


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("plan"); p.add_argument("--stage", default=""); p.add_argument("--cycle", default="")
    p.add_argument("--event", default=""); p.add_argument("--schedule", default=""); p.add_argument("--seed-run", default="")
    p = sp.add_parser("collect"); p.add_argument("--carry", default="[]"); p.add_argument("--batch", default=".site_batch")
    p.add_argument("--meteo-cur", default=""); p.add_argument("--meteo-dst", default="web/forecast/meteograms")
    p = sp.add_parser("state"); p.add_argument("--stage", required=True); p.add_argument("--cycle", default="")
    p.add_argument("--prev-state", default="{}"); p.add_argument("--files-main", default="0"); p.add_argument("--files-meteo", default="0")
    p.add_argument("--out", default="site-state.json")
    p = sp.add_parser("poll"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--ref", default="main")
    a = ap.parse_args()
    {"plan": cmd_plan, "collect": cmd_collect, "state": cmd_state, "poll": cmd_poll}[a.cmd](a)


if __name__ == "__main__":
    main()
