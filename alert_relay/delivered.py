"""Append-only log of webhook bodies the relay actually POSTed.

Shadow / adopt / seed records stay in the watcher seen files and are NOT
written here. box_sync_seen.py only merges this log (via sent.json), so the
box does not treat "the relay noticed it" as "the relay delivered it".
"""
import json
import os
from datetime import datetime, timezone


def note(base, channel, payload_id, items):
    path = os.path.join(base, "relay_delivered.jsonl")
    rec = {
        "at": datetime.now(timezone.utc).isoformat(),
        "channel": channel,
        "payload_id": payload_id,
        "items": items,
    }
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")
