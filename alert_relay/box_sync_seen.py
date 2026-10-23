#!/usr/bin/env python3
"""Merge alerts the relay already POSTed into the box watcher seen files.

Call once at watcher startup, before the poll loop. Payload ids are NOT a
sufficient dedupe across the two senders: both compute
prefix + sha1(sorted item ids + tick of the first attempt), and the tick
differs, so the receiver's payload_id check does not see a box resend as the
relay's send. Item ids are stable. This helper copies those ids into the
local seen stores so the box does not POST them again.

It only updates files that already exist. Creating seen.json would turn off
the watcher's first-run seed. A pause/resume always has the files; a brand-new
install does not, and there is nothing local to protect.

  # watch.py and watch_quiet.py, once, before the loop (or in __main__ before run()):
  try: import box_sync_seen; box_sync_seen.sync()
  except Exception: pass

sync() never raises. Exit 0 from the CLI either way.

Env:
  BOX_WATCH_BASE     default /workspace/urgent_watch
  GITHUB_REPOSITORY  default wawxchasermodels/wx-models
  ALERT_RELAY_SENT_FILE   optional local sent.json (tests). Otherwise the
                          public contents API on branch relay-state, then raw.
No token is required for a public repository. GITHUB_RELAY_TOKEN is sent only
when ALERT_RELAY_SENT_USE_TOKEN=1 (not needed for this public repo).
"""
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import constants


def _base():
    return os.environ.get("BOX_WATCH_BASE") or "/workspace/urgent_watch"


def _repo():
    return os.environ.get("GITHUB_REPOSITORY") or os.environ.get("ALERT_RELAY_REPO") or constants.DEFAULT_REPO


def _load(path, default):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception:
        return default


def _save(path, data):
    tmp = path + ".tmp.relay-sync"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def fetch_sent():
    local = os.environ.get("ALERT_RELAY_SENT_FILE")
    if local:
        return _load(local, None)
    repo = _repo()
    token = os.environ.get("GITHUB_RELAY_TOKEN") if os.environ.get("ALERT_RELAY_SENT_USE_TOKEN") == "1" else ""
    url = "https://api.github.com/repos/%s/contents/%s?ref=%s" % (repo, constants.STATE_PATH, constants.STATE_BRANCH)
    headers = {
        "Accept": "application/vnd.github.raw",
        "User-Agent": "wx-models-alert-relay",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        if isinstance(doc, dict) and doc.get("version") == 1:
            return doc
    except Exception:
        pass
    raw = "https://raw.githubusercontent.com/%s/%s/%s" % (repo, constants.STATE_BRANCH, constants.STATE_PATH)
    try:
        req = urllib.request.Request(raw, headers={"User-Agent": "wx-models-alert-relay"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            doc = json.loads(resp.read().decode("utf-8"))
        if isinstance(doc, dict) and doc.get("version") == 1:
            return doc
    except Exception:
        return None
    return None


def _merge_map(path, incoming, label, counts):
    if not incoming or not os.path.exists(path):
        return
    cur = _load(path, {})
    if not isinstance(cur, dict):
        return
    added = 0
    for key, value in incoming.items():
        if key not in cur:
            cur[key] = value
            added += 1
    if added:
        _save(path, cur)
    counts[label] = added


def _merge_spc(path, posted, counts):
    if not posted or not os.path.exists(path):
        return
    doc = _load(path, None)
    if not isinstance(doc, dict):
        return
    box_posted = doc.setdefault("posted", {})
    fired = list(doc.get("fired") or [])
    added = 0
    for key, rec in posted.items():
        ranks = {k: int(v) for k, v in (rec.get("ranks") or {}).items()}
        prev = box_posted.get(key)
        if prev is None:
            box_posted[key] = {"ranks": ranks, "max_rank": max(ranks.values()) if ranks else -1,
                               "ids": list(rec.get("ids") or []), "seeded": False, "at": rec.get("at")}
            added += 1
        else:
            old = {k: int(v) for k, v in (prev.get("ranks") or {}).items()}
            for state, rank in ranks.items():
                if rank > old.get(state, -1):
                    old[state] = rank
                    added += 1
            ids = list(prev.get("ids") or [])
            for ident in rec.get("ids") or []:
                if ident not in ids:
                    ids.append(ident)
            prev["ranks"] = old
            prev["max_rank"] = max(old.values()) if old else -1
            prev["ids"] = ids[-40:]
            box_posted[key] = prev
        for ident in rec.get("ids") or []:
            if ident not in fired:
                fired.append(ident)
    doc["posted"] = box_posted
    doc["fired"] = fired[-40:]
    if doc.get("schema") != 2:
        doc["schema"] = 2
    _save(path, doc)
    counts["spc"] = added


def _merge_hurricanes(path, storms, counts):
    if not storms or not os.path.exists(path):
        return
    doc = _load(path, None)
    if not isinstance(doc, dict):
        return
    box = doc.setdefault("storms", {})
    added = 0
    for sid, rec in storms.items():
        prev = dict(box.get(sid) or {})
        woken = int(rec.get("woken") or 0)
        if woken > int(prev.get("woken") or 0) or sid not in box:
            prev["woken"] = max(woken, int(prev.get("woken") or 0))
            added += 1
        prev["seeded"] = False if woken else prev.get("seeded", False)
        if rec.get("first_woken_at") and not prev.get("first_woken_at"):
            prev["first_woken_at"] = rec["first_woken_at"]
        if rec.get("second_woken_at"):
            prev["second_woken_at"] = rec["second_woken_at"]
        if rec.get("name"):
            prev["name"] = rec["name"]
        if rec.get("basin"):
            prev["basin"] = rec["basin"]
        box[sid] = prev
    doc["storms"] = box
    _save(path, doc)
    counts["hurricanes"] = added


def _merge_passes(path, snap, counts):
    if not snap or not isinstance(snap, dict) or not snap.get("passes"):
        return
    if not os.path.exists(path):
        return
    doc = _load(path, None)
    if not isinstance(doc, dict):
        return
    box_at = str(doc.get("last_poll") or "")
    relay_at = str(snap.get("at") or "")
    if box_at and relay_at and box_at >= relay_at:
        counts["passes"] = 0
        return
    doc["passes"] = snap["passes"]
    doc["last_poll"] = relay_at or doc.get("last_poll")
    doc["last_changes"] = []
    _save(path, doc)
    counts["passes"] = len(snap["passes"])


def _merge_gov(path, feeds, counts):
    if not feeds or not os.path.exists(path):
        return
    doc = _load(path, {})
    if not isinstance(doc, dict):
        return
    cur = doc.setdefault("feeds", {})
    added = 0
    for key, value in feeds.items():
        if key not in cur:
            cur[key] = value
            added += 1
    if added:
        _save(path, doc)
    counts["gov"] = added


def apply_sent(sent, base=None):
    """Merge into existing box files. Returns a count dict. Does not create seen files."""
    base = base or _base()
    counts = {}
    if not isinstance(sent, dict):
        return counts
    urgent = sent.get("urgent") or {}
    quiet = sent.get("quiet") or {}
    _merge_map(os.path.join(base, "seen.json"), urgent.get("keys") or {}, "urgent", counts)
    _merge_map(os.path.join(base, "seen_quiet.json"), quiet.get("seen") or {}, "quiet", counts)
    _merge_map(os.path.join(base, "seen_quakes_quiet.json"), quiet.get("quakes") or {}, "quakes", counts)
    _merge_spc(os.path.join(base, "spc_quiet_state.json"), quiet.get("spc_posted") or {}, counts)
    _merge_hurricanes(os.path.join(base, "hurricanes_quiet_state.json"), quiet.get("hurricanes") or {}, counts)
    _merge_passes(os.path.join(base, "passes_quiet_state.json"), quiet.get("pass_snapshot"), counts)
    _merge_gov(os.path.join(base, "gov_imagery_seen.json"), quiet.get("gov_feeds") or {}, counts)
    return counts


def sync():
    """Fetch sent.json and merge. Never raises. Returns True if the fetch worked."""
    try:
        sent = fetch_sent()
        if not sent:
            sys.stderr.write("alert-relay sync: no sent index yet\n")
            return False
        counts = apply_sent(sent)
        if not counts:
            sys.stderr.write("alert-relay sync: nothing merged (no local seen files yet, or index empty)\n")
        else:
            sys.stderr.write("alert-relay sync: " + " ".join("%s+%s" % (k, v) for k, v in sorted(counts.items())) + "\n")
        return True
    except Exception as exc:
        sys.stderr.write("alert-relay sync failed (%s); watcher continues\n" % type(exc).__name__)
        return False


def main(argv):
    if argv and argv[0] in ("-h", "--help"):
        sys.stderr.write(__doc__.strip() + "\n")
        return 0
    sync()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
