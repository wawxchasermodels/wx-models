"""Decide whether a box heartbeat is fresh, stale, or missing."""
from datetime import datetime, timezone

from adopt import parse_time


def status(raw, max_age_sec, now=None):
    """Return (state, age_seconds, timestamp).

    state is "missing", "fresh", or "stale". A timestamp more than 10 minutes
    in the future is stale so a bad clock cannot silence the relay forever.
    """
    now = now or datetime.now(timezone.utc)
    if raw is None or not str(raw).strip():
        return "missing", None, None
    stamp = parse_time(str(raw).strip())
    if stamp is None:
        return "missing", None, None
    age = (now - stamp).total_seconds()
    if age < -600:
        return "stale", age, stamp
    if age < max_age_sec:
        return "fresh", age, stamp
    return "stale", age, stamp
