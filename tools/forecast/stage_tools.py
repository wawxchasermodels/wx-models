#!/usr/bin/env python3
"""Staged forecast builds: plan a stage, collect carried products, write site state, and poll for new data.

Four stages per 00Z/12Z cycle publish each model group as soon as its data is out:
  s1 HRRR | s2 RRFS + GFS | s3 AIFS + EPS/AIFS ENS maps + EPS meteograms | s4 ECMWF 9 km (IFS 0.1 deg)
Two-run models (10-25-26, Benjamin: "Keep 2 hrrr runs at any given time, have a toggle", then the same for AIFS): HRRR and
AIFS keep their two newest runs on the site. The state's `hrrr_prev` / `aifs_prev` groups carry the run before the current
one, and the deploy keeps the two newest cycles of every HRRR / AIFS product; every other product keeps only its newest.
Their 18Z runs add no deploys: they ride along with the first stage run after their data is out (RIDERS), normally
HRRR 18Z (f48 out about 19:47 UTC) with the 12Z s3 run and AIFS 18Z (240 h out about 00:55 UTC) with the 00Z s1 run.
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
import argparse
import time, datetime as dt, fnmatch, glob, json, os, re, shutil, subprocess, sys, tempfile, urllib.request

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
            "ifs": ["mslp-maps", "temp-maps", "menu-ifs-*", "menu-reuse-ifs"],
            # 10-26-26 (Benjamin 6:59 AM): ECMWF 9 km 06Z/18Z runs to 144 h for five products only (IFSX_DIRS), a rider
            "ifsx": ["ifsx-maps"]}
GROUP_METEO = {"hrrr": "hrrr", "rrfs": "rrfs", "ens": "eps"}   # meteogram source carried with each group
# two-run models (10-25-26): the run before the current one, carried as its own group (maps only, no meteograms)
PREV = {"hrrr": "hrrr_prev", "aifs": "aifs_prev"}
KEEP_RUNS = {"hrrr": 2, "aifs": 2, "ifs": 2}   # cycles kept on the site per two-run model (every other product: 1)
AIFS_DIRS = {"aifs500", "aifsmslp", "aifswind"}
# ECMWF 9 km products that also get the 06Z/18Z run (to 144 h) as a second run on the toggle; every other ECMWF product
# keeps only its newest 00Z/12Z run. The site keeps the newest 00Z/12Z run of these plus the newest 06Z/18Z run when
# that one is at most 6 h older than it (so a stale off-hour run never lingers).
IFSX_DIRS = {"aifs500-ifs", "t850-ifs", "t850anom-ifs", "aifswind-ifs", "gust10-ifs"}   # aifs_maps.py folders (no model suffix); other AIFS folders end in -aifs
CYCLE_HOURS = {s_: (0, 12) for s_ in STAGES}   # stage cycles; AIFS 18Z comes in as a rider below
CYCLE_HOURS["s1"] = (0, 6, 12, 18)   # HRRR 18Z (10-25-26) and 06Z (10-26-26, Benjamin 6:51 AM) are their own s1 runs, maps only


def run_model(prod):
    """Two-run model of a product folder (<cycle>/<prod>/...), or None."""
    if prod.endswith("-hrrr"):
        return "hrrr"
    if prod.endswith("-aifs") or prod in AIFS_DIRS:
        return "aifs"
    if prod in IFSX_DIRS:
        return "ifs"
    return None


# 18Z riders: rendered inside whichever stage run comes first after their last file is out (never in the stage that owns
# the group). No extra deploys. AIFS 06Z is left out (Benjamin: 00Z/12Z/18Z); HRRR 06Z is its own s1 run (CYCLE_HOURS).
RIDERS = {"aifs": {"hours": (18,), "ready": ["https://data.ecmwf.int/forecasts/{d}/{h:02d}z/aifs-single/0p25/oper/{d}{h:02d}0000-240h-oper-fc.index"],
                   "products": "aifs,temps,menu", "menu": "aifs"},
          # ECMWF 9 km 06Z/18Z to 144 h (out about 14:27 / 02:27 UTC): rides with the 12Z s2 / 00Z s2 run as a rule
          "ifsx": {"hours": (6, 18), "ready": ["https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p1/oper/{d}{h:02d}0000-144h-oper-fc-sfc.index",
                                               "https://data.ecmwf.int/forecasts/{d}/{h:02d}z/ifs/0p1/oper/{d}{h:02d}0000-144h-oper-fc-pl.index"],
                   "products": "ifsx", "menu": ""}}
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
BACKUP = {"10 2,8,14,20 * * *": "s1", "50 4,16 * * *": "s2", "0 8,20 * * *": "s3", "50 9,21 * * *": "s4"}
FULL_CRON = "50 21 * * *"
MIN_FRACTION = 0.85
MAX_TRIES = 2   # poller: stop re-dispatching a stage/cycle after this many finished runs that did not publish it
METEO_DEPLOY = {"s1", "s3"}   # stages that deploy the meteogram project (s2 skipped 10-26-26 to save 2 deploys a day)
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


def cycles_back(stage, now=None, back=3):
    """The last `back` cycles this stage accepts (CYCLE_HOURS), newest first."""
    now = (now or dt.datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
    out, c = [], now
    while len(out) < back:
        if c.hour in CYCLE_HOURS[stage]:
            out.append(c)
        c -= dt.timedelta(hours=1)
    return out


def ready_cycle(stage, now=None, back=3, check=None):
    """Newest accepted cycle (00Z/12Z; s1 also 06Z/18Z) whose last files for this stage are all out (checks the last `back`)."""
    check = check or exists
    for c in cycles_back(stage, now, back):
        if all(check(u.format(d=f"{c:%Y%m%d}", h=c.hour)) for u in READY[stage]):
            return f"{c:%Y%m%d%H}"
    return ""


def riders_due(stage, st, now=None, check=None):
    """{group: 18Z cycle} for the two-run models whose newest 18Z run is out and newer than the one the site holds."""
    check = check or exists
    now = (now or dt.datetime.now(UTC)).replace(minute=0, second=0, microsecond=0)
    due = {}
    for g, r in RIDERS.items():
        if g in GROUPS[stage]:
            continue
        have = ((st.get("groups") or {}).get(g) or {}).get("cycle", "")
        cands = sorted((day.replace(hour=h) for day in (now, now - dt.timedelta(days=1), now - dt.timedelta(days=2))
                        for h in r["hours"]), reverse=True)
        for c in [c for c in cands if c <= now][:2]:
            cyc = f"{c:%Y%m%d%H}"
            if cyc <= have:
                break
            if all(check(u.format(d=f"{c:%Y%m%d}", h=c.hour)) for u in r["ready"]):
                due[g] = cyc; break
    return due


def cycle_ok(stage, cycle):
    return bool(re.fullmatch(r"\d{10}", cycle or "")) and int(cycle[-2:]) in CYCLE_HOURS[stage]


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


def rotate_prev(st, prev, g, new_cycle):
    """Two-run groups (PREV): when group g moves to a new cycle, its old record becomes g's previous run (maps only).
    A rerun of the same cycle keeps the previous run as it was. st = new state (changed in place), prev = old state."""
    pg = PREV.get(g)
    if not pg:
        return
    old = (prev.get("groups") or {}).get(g) or {}
    keep = (prev.get("groups") or {}).get(pg)
    if old.get("items") and old.get("cycle") and old.get("cycle") != new_cycle:
        st["groups"][pg] = {"items": old["items"], "meteo": [], "cycle": old["cycle"], "at": old.get("at", "")}
        print(f"{pg}: now {old['cycle']} (was {g})")
    elif keep and keep.get("cycle") and keep.get("cycle") != new_cycle:
        st["groups"][pg] = keep
    else:
        st["groups"].pop(pg, None)


def run_artifacts(run_id):
    r = sh("gh", "api", f"repos/{repo()}/actions/runs/{run_id}/artifacts?per_page=100")
    return {a["name"] for a in json.loads(r.stdout).get("artifacts", []) if not a.get("expired")}


# ---------------------------------------------------------------------------------------------------------- plan
def staged_live(st, now=None, hours=36):
    """True when the last deploy was a stage run within `hours` (staged builds are running)."""
    try:
        t = dt.datetime.fromisoformat(st.get("updated", ""))
    except ValueError:
        return False
    return st.get("stage") in STAGES and (now or dt.datetime.now(UTC)) - t < dt.timedelta(hours=hours)


def cmd_plan(a):
    stage = a.stage or BACKUP.get(a.schedule, "all")   # schedule: backup stage cron, or the 21:50 full build
    if stage == "all":
        go = "true"
        if a.event == "schedule":
            # the 21:50 full build is pinned to 12Z: once staged builds run (the last deploy was a stage run in the last 36 h)
            # it would redraw HRRR at 12Z over the 18Z run and reseed the site state, so the fallback stands down by itself
            _, st = latest_state()
            if st and staged_live(st):
                print(f"::notice::staged builds are live (last deploy {st.get('stage')} {st.get('updated')}); "
                      "the 21:50 full-build fallback does nothing")
                go = "false"
        out(stage="all", go=go, cycle="", pin="12" if a.event == "schedule" else "", products=os.environ.get("PRODUCTS", "") if go == "true" else "",
            menu_models="", meteo_srcs="[]", carry="[]", min_files="0", prev_state="{}", stage_patterns="",
            riders={}, hrrr_cycle="", aifs_cycle="", ifsx_cycle="", menu_cycles={}, meteo_deploy="false")
        return
    if stage not in STAGES:
        sys.exit(f"unknown stage {stage}")
    cycle = a.cycle or ready_cycle(stage)
    if not cycle_ok(stage, cycle):
        hrs = "/".join(f"{h:02d}Z" for h in CYCLE_HOURS[stage])
        print(f"::notice::{stage}: no complete {hrs} run found yet (or cycle {cycle!r} is not one of them); nothing to do")
        out(stage=stage, go="false", cycle="", pin="", products="", menu_models="", meteo_srcs="[]", carry="[]", min_files="0",
            prev_state="{}", stage_patterns="", riders={}, hrrr_cycle="", aifs_cycle="", ifsx_cycle="", menu_cycles={}, meteo_deploy="false")
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
    riders = riders_due(stage, st) if go == "true" else {}
    if riders:
        print(f"riders (18Z runs of two-run models, no extra deploy): {riders}")
    groups = GROUPS[stage] + list(riders)
    pats = "{" + ",".join(p for g in groups for p in PATTERNS[g]) + "}"
    prods = ",".join(dict.fromkeys(",".join([PRODUCTS[stage]] + [RIDERS[g]["products"] for g in riders]).split(",")))
    menus = ",".join(dict.fromkeys(m for m in [MENU[stage]] + [RIDERS[g]["menu"] for g in riders] if m))
    meteo = METEO[stage] if go == "true" else []
    if stage == "s1" and cycle[-2:] in ("06", "18"):
        meteo = []   # HRRR 06Z/18Z: maps only, no meteogram-project deploy (keeps deploys under the Pages limit; 00Z/12Z redo them)
    out(stage=stage, go=go, cycle=cycle, pin=cycle[-2:], products=prods if go == "true" else "", menu_models=menus,
        meteo_srcs=meteo, carry=carry, min_files=str(min_files), prev_state=st, stage_patterns=pats,
        riders=riders, hrrr_cycle=riders.get("hrrr", ""), aifs_cycle=riders.get("aifs", ""), ifsx_cycle=riders.get("ifsx", ""),
        menu_cycles={g: c for g, c in riders.items() if RIDERS.get(g, {}).get("menu")},
        # 10-26-26 (Benjamin 6:59 AM): no meteogram-project deploy on s2 (RRFS). Its new RRFS charts are recorded in the
        # site state and go live with the next meteogram deploy (s3 / s1 00Z-12Z); until then s2 keeps the carried ones.
        meteo_deploy="true" if meteo and stage in METEO_DEPLOY else "false")


# ------------------------------------------------------------------------------------------------------- collect
def merge_tree(src, dst):
    for root, _, files in os.walk(src):
        rel = os.path.relpath(root, src); os.makedirs(os.path.join(dst, rel), exist_ok=True)
        for f in files:
            shutil.move(os.path.join(root, f), os.path.join(dst, rel, f))   # move, not copy: keeps runner disk use low


def prune_old_cycles(batch):
    """Keep only the newest cycle of each product dir (<cycle>/<product>/...), so carried and new runs never mix.
    Two-run models (KEEP_RUNS: HRRR, AIFS): keep the two newest cycles of that model as a whole (one shared pair for all
    its products, so the run toggle never offers a third run); a product missing from the newest run keeps its older one."""
    dirs = []
    for d in glob.glob(f"{batch}/*/*/"):
        cyc, prod = d.rstrip("/").split("/")[-2:]
        if re.fullmatch(r"\d{10}", cyc):
            dirs.append((d, cyc, prod))
    newest, model_cycles = {}, {}
    for d, cyc, prod in dirs:
        newest[prod] = max(cyc, newest.get(prod, ""))
        mdl = run_model(prod)
        if mdl:
            model_cycles.setdefault(mdl, set()).add(cyc)
    keep = {suf: set(sorted(cs, reverse=True)[:KEEP_RUNS[suf]]) for suf, cs in model_cycles.items()}
    if "ifs" in model_cycles:   # ECMWF: newest 00Z/12Z run + the newest 06Z/18Z run if it is at most 6 h older than that
        cs = model_cycles["ifs"]; main = max([c for c in cs if c[-2:] in ("00", "12")] or [""]); off = max([c for c in cs if c[-2:] in ("06", "18")] or [""])
        keep["ifs"] = {main} if main else set()
        if off and (not main or dt.datetime.strptime(off, "%Y%m%d%H") >= dt.datetime.strptime(main, "%Y%m%d%H") - dt.timedelta(hours=6)):
            keep["ifs"].add(off)
    n = 0
    for d, cyc, prod in dirs:
        mdl = run_model(prod)
        if (cyc not in keep[mdl]) if mdl else (cyc != newest[prod]):
            shutil.rmtree(d); n += 1
    for suf, cs in keep.items():
        print(f"two-run model {suf}: keeping cycles {sorted(cs, reverse=True)}")
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
        if kind == "maps":
            shutil.rmtree(d, ignore_errors=True)   # merged into the batch; free the disk before the next download
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
        # two-run HRRR: a full build deploys one HRRR run and carries nothing, so no previous run is recorded; the next s1
        # run makes it the previous run (rotate_prev)
        st["stages"] = {s_: a.cycle for s_ in STAGES}
    else:
        prev_copy = json.loads(json.dumps(prev))
        st = prev; st.pop("seeded_from", None)
        riders = json.loads(a.riders or "{}")
        for g, gcyc in [(g, a.cycle) for g in GROUPS[a.stage]] + list(riders.items()):   # riders: 18Z runs of two-run models
            old = st["groups"].get(g, {"items": [], "meteo": []})
            items = [[run_id, p] if match(p) else None for p in PATTERNS[g]]
            items = [i for i in items if i] + [i for i in old["items"] if not match(i[1])]   # failed jobs: keep the older run
            meteo = old.get("meteo", [])
            src = GROUP_METEO.get(g)
            if src in METEO[a.stage] and match(f"meteo-{src}"):
                meteo = [[run_id, f"meteo-{src}"]]
            if any(i[0] == run_id for i in items):
                rotate_prev(st, prev_copy, g, gcyc)   # two-run groups: the old run becomes the previous run
            else:
                gcyc = old.get("cycle", "")   # nothing new from this run (failed job): the group keeps its cycle
            st["groups"][g] = {"items": items, "meteo": meteo, "cycle": gcyc, "at": now}
            print(f"{g}: new {[i[1] for i in items if i[0] == run_id]}, kept {[i for i in items if i[0] != run_id]}")
        st.setdefault("stages", {})[a.stage] = a.cycle
    st.update(files_main=int(a.files_main or 0), files_meteo=int(a.files_meteo or 0), updated=now, run_id=run_id, stage=a.stage)
    json.dump(st, open(a.out, "w"), indent=1)
    print(json.dumps({k: v for k, v in st.items() if k != "groups"}))
    for g, r in st["groups"].items():
        print(f"  {g}: runs {sorted({i[0] for i in r['items'] + r['meteo']})} cycle {r.get('cycle')}")


# ---------------------------------------------------------------------------------------------------------- poll
def poll_once(a):
    r = sh("gh", "run", "list", "-R", repo(), "-w", "forecast-site.yml", "-L", "40", "--json", "status,displayTitle,databaseId")
    runs = json.loads(r.stdout)
    busy = [x for x in runs if x["status"] in ("queued", "in_progress", "waiting", "pending", "requested")]
    if busy:
        print(f"forecast-site busy ({busy[0]['displayTitle']}, run {busy[0]['databaseId']}); next poll will check again")
        return "busy"
    _, st = latest_state()
    if not st:
        print("::warning::no site-state artifact; poller waits for a full build"); return "nothing"
    due = []
    for s in STAGES:
        c = ready_cycle(s)
        pub = st.get("stages", {}).get(s, "")
        print(f"{s}: newest ready {c or '-'}; published {pub or '-'}")
        tries = sum(1 for x in runs if x["displayTitle"] == f"Forecast site {s} {c}" and x["status"] == "completed")
        if c and c > pub and tries >= MAX_TRIES:
            print(f"::warning::{s} {c} already tried {tries} times without publishing; skipped (backup cron or a manual run can retry)")
        elif c and c > pub:
            due.append((c, STAGES.index(s), s))
    if not due:
        print("nothing new"); return "nothing"
    c, _, s = min(due)
    print(f"dispatch {s} for {c}")
    if a.dry_run:
        print("dry run: not dispatching"); return "dispatched"
    sh("gh", "workflow", "run", "forecast-site.yml", "-R", repo(), "--ref", a.ref, "-f", f"stage={s}", "-f", f"cycle={c}")
    return "dispatched"


def cmd_poll(a):
    """GitHub runs the */10 schedule late (30-45 min apart on 10-26-26), so one poll keeps checking every 2 min for up
    to --wait-min minutes (while nothing is new, or while a stage run is going) and starts the next stage the moment it
    is due. Stops after one dispatch."""
    end = time.time() + 60 * a.wait_min
    while True:
        res = poll_once(a)
        if res == "dispatched" or time.time() + 120 > end:
            return
        print(f"{dt.datetime.now(UTC):%H:%M} UTC: {res}; checking again in 2 min", flush=True)
        time.sleep(120)


def main():
    ap = argparse.ArgumentParser(); sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("plan"); p.add_argument("--stage", default=""); p.add_argument("--cycle", default="")
    p.add_argument("--event", default=""); p.add_argument("--schedule", default=""); p.add_argument("--seed-run", default="")
    p = sp.add_parser("collect"); p.add_argument("--carry", default="[]"); p.add_argument("--batch", default=".site_batch")
    p.add_argument("--meteo-cur", default=""); p.add_argument("--meteo-dst", default="web/forecast/meteograms")
    p = sp.add_parser("state"); p.add_argument("--stage", required=True); p.add_argument("--cycle", default="")
    p.add_argument("--prev-state", default="{}"); p.add_argument("--files-main", default="0"); p.add_argument("--files-meteo", default="0")
    p.add_argument("--riders", default="{}")
    p.add_argument("--out", default="site-state.json")
    p = sp.add_parser("poll"); p.add_argument("--dry-run", action="store_true"); p.add_argument("--ref", default="main")
    p.add_argument("--wait-min", type=float, default=0, help="keep checking every 2 min for this long (scheduled polls: 45)")
    a = ap.parse_args()
    {"plan": cmd_plan, "collect": cmd_collect, "state": cmd_state, "poll": cmd_poll}[a.cmd](a)


if __name__ == "__main__":
    main()
