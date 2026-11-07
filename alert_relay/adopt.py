"""Split items the live box already had a chance to deliver.

payload_id hashes include the first-attempt timestamp, so a relay resend and a
box resend do not share a payload id. Item ids are stable. On takeover the
relay still must not re-POST alerts the box issued while its heartbeat was
fresh, except alerts issued inside an overnight hold (the box deliberately
did not send those).
"""
from datetime import datetime, timezone


def parse_time(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def partition(items, adopt_before, issued_during_hold, time_of):
    """Return (adopt, keep). adopt = box was alive and would have sent them."""
    if adopt_before is None:
        return [], list(items)
    if adopt_before.tzinfo is None:
        adopt_before = adopt_before.replace(tzinfo=timezone.utc)
    adopt, keep = [], []
    for item in items:
        sent = time_of(item)
        if sent is not None and sent < adopt_before and not issued_during_hold(item, sent):
            adopt.append(item)
        else:
            keep.append(item)
    return adopt, keep
