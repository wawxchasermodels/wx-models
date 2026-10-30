#!/usr/bin/env python3
"""Read-only GitHub Actions timing check for wawxchasermodels/wx-models (box only; changes nothing).
  python3 gh_run_timing.py [--workflow fast-models.yml] [--runs 15] [--all-workflows]
Shows, in Pacific time: when each run was queued, how long it waited to start, how long it ran, its result, and per-job
durations (slowest first) plus the gap between scheduled runs (GitHub throttles cron). Token: $GH_DEPLOY_KEY (never printed)."""
import os, sys, json, argparse, urllib.request, datetime as dt
from zoneinfo import ZoneInfo
PT = ZoneInfo("America/Los_Angeles"); REPO = "wawxchasermodels/wx-models"
def api(path):
    rq = urllib.request.Request(f"https://api.github.com/repos/{REPO}/{path}", headers={"Authorization": "Bearer " + os.environ["GH_DEPLOY_KEY"],
                                "Accept": "application/vnd.github+json"})
    for k in range(4):   # GitHub drops a connection now and then
        try: return json.load(urllib.request.urlopen(rq, timeout=30))
        except OSError:
            if k == 3: raise
            import time; time.sleep(2 * (k + 1))
t = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None
fmt = lambda d: d.astimezone(PT).strftime("%a %-I:%M %p PT") if d else "-"
mins = lambda a, b: f"{(b - a).total_seconds() / 60:5.1f} min" if a and b else "   -    "
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--workflow", default="fast-models.yml"); ap.add_argument("--runs", type=int, default=15)
    ap.add_argument("--all-workflows", action="store_true"); a = ap.parse_args()
    path = "actions/runs" if a.all_workflows else f"actions/workflows/{a.workflow}/runs"
    runs = api(f"{path}?per_page={a.runs}")["workflow_runs"]
    print(f"{'queued':<20} {'event':<18} {'wait':>9} {'ran':>9}  result      sha      workflow")
    sched = []
    for r in runs:
        c, s, u = t(r["created_at"]), t(r.get("run_started_at")), t(r["updated_at"])
        done = r["status"] == "completed"
        print(f"{fmt(c):<20} {r['event']:<18} {mins(c, s):>9} {mins(s, u) if done else '  running':>9}  {(r['conclusion'] or r['status']):<11} {r['head_sha'][:7]}  {r['name']}")
        if r["event"] == "schedule": sched.append(c)
        if r is runs[0] or (done and r["conclusion"] != "success"):
            for j in sorted(api(f"actions/runs/{r['id']}/jobs?per_page=50")["jobs"], key=lambda j: -((t(j["completed_at"]) or dt.datetime.now(dt.timezone.utc)) - (t(j["started_at"]) or t(j["created_at"]))).total_seconds()):
                print(f"{'':<22}- {j['name']:<22} {mins(t(j['started_at']), t(j['completed_at'])) if j['completed_at'] else '  running':>9}  {j['conclusion'] or j['status']}")
    if len(sched) > 1:
        gaps = [(a_ - b_).total_seconds() / 60 for a_, b_ in zip(sched, sched[1:])]
        print(f"\nscheduled runs: {len(sched)}, gap between them {min(gaps):.0f}-{max(gaps):.0f} min (cron asks for 15)")
if __name__ == "__main__": main()
