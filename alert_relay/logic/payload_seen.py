#!/usr/bin/env python3
"""Stable webhook payload ids + handled-id registry (10-21-26 audit fix).

Watchers (watch.py prefix "u-", watch_quiet.py prefix "q-") stamp every webhook
POST with payload_id = prefix + sha1(sorted item ids + tick of FIRST attempt).
If a POST fails or times out, the SAME items keep the SAME payload_id on the
resend (state["inflight_payload"]), so a woken routine can drop a duplicate.

Routine usage (first thing after a wake):
  python3 /workspace/urgent_watch/payload_seen.py PAYLOAD_ID
    exit 0 = new, now recorded -> handle the wake
    exit 3 = already handled   -> ignore this wake (duplicate resend)
    exit 1 = usage / error
  python3 payload_seen.py --check PAYLOAD_ID   same exit codes, records nothing
Registry: /workspace/urgent_watch/handled_payload_ids.json {"ids": {id: iso}}
(pruned after 7 days). No secrets are read or written.
"""
import contextlib, fcntl, hashlib, json, os, sys
from datetime import datetime, timedelta, timezone

HANDLED_FILE = os.environ.get("PAYLOAD_SEEN_FILE") or "/workspace/urgent_watch/handled_payload_ids.json"
KEEP_DAYS = 7


def compute_id(prefix, item_keys, tick_iso):
    key = sorted({str(k) for k in item_keys})
    h = hashlib.sha1(json.dumps([key, tick_iso]).encode()).hexdigest()[:16]
    return "%s-%s" % (prefix, h)


def stable_id(state, prefix, item_keys, tick_iso):
    """Same item set as the last undelivered POST -> same id; else a new id
    (recorded as in-flight until clear_inflight() after a 2xx)."""
    key = sorted({str(k) for k in item_keys})
    inf = state.get("inflight_payload") or {}
    if inf.get("ids") == key and inf.get("payload_id"):
        inf["attempts"] = int(inf.get("attempts") or 1) + 1
        return inf["payload_id"]
    pid = compute_id(prefix, key, tick_iso)
    state["inflight_payload"] = {"payload_id": pid, "ids": key, "tick": tick_iso, "attempts": 1}
    return pid


def clear_inflight(state):
    state.pop("inflight_payload", None)


@contextlib.contextmanager
def _locked(path):
    with open(path + ".lock", "a+") as lf:
        fcntl.flock(lf.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lf.fileno(), fcntl.LOCK_UN)


def _load(path):
    try:
        with open(path) as f:
            d = json.load(f)
        return d if isinstance(d, dict) and isinstance(d.get("ids"), dict) else {"ids": {}}
    except Exception:
        return {"ids": {}}


def seen_or_record(pid, record=True, path=HANDLED_FILE):
    """Return True if pid was already handled; otherwise record it (unless record=False) and return False."""
    now = datetime.now(timezone.utc)
    with _locked(path):
        d = _load(path)
        cut = now - timedelta(days=KEEP_DAYS)
        ids = {}
        for k, v in d["ids"].items():
            try:
                if datetime.fromisoformat(v) > cut:
                    ids[k] = v
            except Exception:
                pass
        if pid in ids:
            return True
        if record:
            ids[pid] = now.isoformat()
            tmp = path + ".tmp.%d" % os.getpid()
            with open(tmp, "w") as f:
                json.dump({"ids": ids}, f, indent=1)
            os.replace(tmp, path)
        return False


def main(argv):
    args = [a for a in argv if a != "--check"]
    if len(args) != 1 or not args[0].strip() or args[0].startswith("-"):
        print(__doc__.strip(), file=sys.stderr)
        return 1
    pid = args[0].strip()
    already = seen_or_record(pid, record="--check" not in argv)
    print(json.dumps({"payload_id": pid, "status": "already_handled" if already else ("new" if "--check" in argv else "new_recorded")}))
    return 3 if already else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
