#!/usr/bin/env python3
"""Publish the box watcher heartbeat as GitHub Actions repository variables.

Chosen mechanism: one variable per channel (ALERT_RELAY_HB_URGENT,
ALERT_RELAY_HB_QUIET), updated with the fine-grained PAT in GITHUB_RELAY_TOKEN.
A variable write does not create a commit. Two variables avoid a
read-modify-write race between the 30s urgent loop and the 5-min quiet loop.

The relay treats a timestamp younger than 10 minutes (urgent) or 12 minutes
(quiet) as "watcher alive" and POSTs nothing for that channel.

Wiring (failure-tolerant; beat() never raises). Copy this file to
/workspace/urgent_watch/ so the watchers' import path finds it.

  # watch.py, inside the poll loop (once per iteration is fine; writes are throttled):
  try: import box_heartbeat; box_heartbeat.beat("urgent")
  except Exception: pass

  # watch_quiet.py, inside the master loop:
  try: import box_heartbeat; box_heartbeat.beat("quiet")
  except Exception: pass

Env:
  GITHUB_RELAY_TOKEN   fine-grained PAT, this repo only, Variables: Read and write
  GITHUB_REPOSITORY    optional, default wawxchasermodels/wx-models
  ALERT_RELAY_HB_STAMP_DIR   optional throttle stamps, default /tmp

CLI: python3 box_heartbeat.py urgent|quiet|both
Exit 0 even when the update fails, so a shell wrapper cannot kill a watcher.
The import API returns True/False and never raises.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import constants
import github_api

CHANNELS = {"urgent": constants.HB_VAR_URGENT, "quiet": constants.HB_VAR_QUIET}


def _repo():
    return os.environ.get("GITHUB_REPOSITORY") or os.environ.get("ALERT_RELAY_REPO") or constants.DEFAULT_REPO


def _stamp_path(channel):
    base = os.environ.get("ALERT_RELAY_HB_STAMP_DIR") or "/tmp"
    return os.path.join(base, "alert-relay-hb-%s" % channel)


def _recently_sent(channel, now):
    try:
        with open(_stamp_path(channel)) as fh:
            last = fh.read().strip()
        then = datetime.fromisoformat(last)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        return (now - then).total_seconds() < constants.HB_MIN_INTERVAL_SEC[channel]
    except Exception:
        return False


def _remember(channel, stamp):
    path = _stamp_path(channel)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            fh.write(stamp)
        os.replace(tmp, path)
    except Exception:
        pass


def _beat_one(channel):
    token = os.environ.get("GITHUB_RELAY_TOKEN") or ""
    if not token:
        sys.stderr.write("alert-relay heartbeat %s skipped (GITHUB_RELAY_TOKEN unset)\n" % channel)
        return False
    now = datetime.now(timezone.utc)
    if _recently_sent(channel, now):
        return True
    stamp = now.isoformat()
    code = github_api.upsert_variable(_repo(), CHANNELS[channel], stamp, token)
    if code in (201, 204):
        _remember(channel, stamp)
        sys.stderr.write("alert-relay heartbeat %s ok\n" % channel)
        return True
    sys.stderr.write("alert-relay heartbeat %s failed (http %s)\n" % (channel, code))
    return False


def beat(channel):
    """Update one channel or 'both'. Never raises."""
    try:
        if channel == "both":
            return _beat_one("urgent") and _beat_one("quiet")
        if channel not in CHANNELS:
            sys.stderr.write("alert-relay heartbeat unknown channel\n")
            return False
        return _beat_one(channel)
    except Exception as exc:
        sys.stderr.write("alert-relay heartbeat %s failed (%s)\n" % (channel, type(exc).__name__))
        return False


def main(argv):
    if len(argv) != 1 or argv[0] not in ("urgent", "quiet", "both"):
        sys.stderr.write("usage: box_heartbeat.py urgent|quiet|both\n")
        return 0
    beat(argv[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
