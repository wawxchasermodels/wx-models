#!/usr/bin/env python3
"""Always-on WA short-fuse path for the GitHub alert relay.

Runs on every relay tick, even while box heartbeats are still fresh. Polls
api.weather.gov for active Washington Tornado Warnings, Tornado Emergencies,
and thunderstorm or waterspout Special Weather Statements, then POSTs the
same urgent/quiet webhook bodies the box watchers use. Payload ids are
tick-free (payload_seen.stable_item_id) so the receiver's handled-id registry
drops a duplicate wake. This module never posts to social networks.

A health-check wake (ALERT_RELAY_TEST_WAKE=1) POSTs an empty-alert body with
a stable payload_id and test/post=false flags; it does not send real alerts.
"""
import json
import logging
import os
import re
from datetime import datetime, timezone

import constants
import net
import payload_seen

log = logging.getLogger("alert_relay.wa_life_safety")

NWS_URL = "https://api.weather.gov/alerts/active?area=WA"
EVENTS = {"Tornado Warning", "Tornado Emergency", "Special Weather Statement"}
WATERSPOUT_RE = re.compile(r"\bWATERSPOUTS?\b", re.I)
TSTM_RE = re.compile(
    r"\b(THUNDERSTORMS?|TSTM|LANDSPOUTS?|FUNNELS?(?:\s+CLOUDS?)?|HAIL|TORNADOES?|TORNADOS?)\b",
    re.I,
)
FOG_RE = re.compile(r"\bFOG\b", re.I)
FRESH_GRACE_SEC = 90
STALE_GRACE_SEC = 0
SEEN_NAME = "wa_life_safety_seen.json"
HEALTH_KEY = "alert-relay-health"


def health_payload_id():
    return payload_seen.stable_item_id("u", [HEALTH_KEY])


def health_body():
    pid = health_payload_id()
    return {
        "source": "alert-relay-health",
        "kind": "health",
        "test": True,
        "post": False,
        "payload_id": pid,
        "alerts": [],
        "items": [],
    }


def _text(props):
    return " ".join(str(props.get(k) or "") for k in ("headline", "description", "instruction", "event"))


def is_wa_area(props):
    """Washington land or adjacent marine zones from UGC / SAME / zone URLs."""
    geo = props.get("geocode") or {}
    for u in geo.get("UGC") or []:
        uu = str(u).upper()
        if uu.startswith(("WAC", "WAZ", "WAS", "PZZ1", "PZZ2", "PZZ5")):
            return True
    if any(str(s).startswith("053") for s in geo.get("SAME") or []):
        return True
    for z in props.get("affectedZones") or []:
        if re.search(r"/(WA)[CZ]\d{3}$", str(z)) or re.search(r"/(PZZ)(1\d{2}|2\d{2}|5\d{2})$", str(z)):
            return True
    return False


def classify_life_safety(props):
    """Return 'urgent', 'quiet', or None for one NWS properties object."""
    ev = props.get("event") or ""
    if ev not in EVENTS:
        return None
    if (props.get("messageType") or "Alert") != "Alert":
        return None
    if (props.get("status") or "Actual") != "Actual":
        return None
    if not is_wa_area(props):
        return None
    if ev in ("Tornado Warning", "Tornado Emergency"):
        return "urgent"
    text = _text(props)
    if WATERSPOUT_RE.search(text):
        return "urgent"
    if TSTM_RE.search(text):
        return "quiet"
    return None


def _parse_time(raw):
    from adopt import parse_time
    return parse_time(raw or "")


def _load(path, default):
    try:
        with open(path) as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else default
    except Exception:
        return default


def _save(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
        fh.write("\n")
    os.replace(tmp, path)


def _mark_watcher_seen(base, kind, alert_id, now_iso):
    """So a later full urgent/quiet tick in this same run does not re-wake."""
    name = "seen.json" if kind == "urgent" else "seen_quiet.json"
    path = os.path.join(base, name)
    doc = _load(path, {})
    doc[alert_id] = now_iso
    if kind != "urgent":
        doc[alert_id + "|WA"] = now_iso
    _save(path, doc)


def _grace_sec(heartbeat_state):
    return FRESH_GRACE_SEC if heartbeat_state == "fresh" else STALE_GRACE_SEC


def _expired(props, now):
    exp = _parse_time(props.get("expires") or "")
    return bool(exp and exp < now)


def _too_new(props, now, grace):
    if grace <= 0:
        return False
    sent = _parse_time(props.get("sent") or "")
    if sent is None:
        return False
    return (now - sent).total_seconds() < grace


def select_alerts(features, now, urgent_hb, quiet_hb, already):
    """Return a list of {kind, id, event, feature, reason} to wake."""
    out = []
    for feat in features or []:
        props = feat.get("properties") or {}
        if not props.get("id"):
            props["id"] = feat.get("id")
        kind = classify_life_safety(props)
        if not kind:
            continue
        alert_id = props["id"]
        if alert_id in already or (kind != "urgent" and (alert_id + "|WA") in already):
            continue
        if _expired(props, now):
            continue
        hb = urgent_hb if kind == "urgent" else quiet_hb
        if _too_new(props, now, _grace_sec(hb)):
            continue
        ev = props.get("event") or ""
        if kind == "urgent" and ev == "Special Weather Statement":
            reason = "Washington waterspout Special Weather Statement"
        elif kind == "urgent":
            reason = "Washington Tornado Warning" if ev == "Tornado Warning" else "Washington Tornado Emergency"
        else:
            reason = "new WA land alert: %s" % ev
        out.append({"kind": kind, "id": alert_id, "event": ev, "feature": feat, "reason": reason, "props": props})
    return out


def _item(kind, rec):
    import watch
    import watch_quiet
    feat = rec["feature"]
    if kind == "urgent":
        item = watch.alert_item(feat, "WA", rec["reason"])
        item["_keys"] = [rec["id"]]
        watch._tag_wa_ask(item, "WA", rec["props"])
        return item
    return watch_quiet.item_for(feat, "WA", rec["reason"])


def _quiet_key(item):
    """Match watch_quiet._batch_key for a single WA alert so payload ids line up."""
    return "alert:%s|%s" % (item.get("id"), item.get("page") or "WA")


def _body(kind, item, now):
    import watch
    if kind == "urgent":
        pid = payload_seen.stable_item_id("u", [item.get("id")])
        public = watch.public([item]) if hasattr(watch, "public") else [item]
        return {"source": "urgent_watch", "alerts": public, "payload_id": pid}, pid
    import watch_quiet
    pid = payload_seen.stable_item_id("q", [_quiet_key(item)])
    return watch_quiet.batch_body([item], pid, now), pid


def _post(kind, body):
    prefix = "URGENT" if kind == "urgent" else "QUIET"
    url = os.environ.get(prefix + "_WEBHOOK_URL") or ""
    auth = os.environ.get(prefix + "_WEBHOOK_AUTH") or ""
    if not url or not auth:
        raise RuntimeError("%s webhook secrets missing" % prefix.lower())
    import watch
    headers = {
        "Authorization": watch.auth_header(auth),
        "Content-Type": "application/json",
        "User-Agent": watch.USER_AGENT,
    }
    return net.Session().post(url, json=body, headers=headers, timeout=30).status_code


def _fetch(user_agent):
    session = net.Session()
    resp = session.get(NWS_URL, headers={"User-Agent": user_agent, "Accept": "application/geo+json"}, timeout=20)
    resp.raise_for_status()
    return resp.json().get("features") or []


def run(base, now=None, urgent_hb="stale", quiet_hb="stale", dry=False, test_wake=False):
    """Poll and maybe wake. Returns a JSON-safe report dict. Never raises."""
    now = now or datetime.now(timezone.utc)
    report = {"action": "ran", "dry_run": dry, "test_wake": test_wake, "sent": [], "skipped": []}
    try:
        if test_wake:
            body = health_body()
            report["health_payload_id"] = body["payload_id"]
            report["health_body"] = body
            if dry:
                report["action"] = "would_health_wake"
                log.info("dry-run: would POST health wake payload_id=%s (no alerts)", body["payload_id"])
                return report
            code = _post("urgent", body)
            report["health_http"] = code
            if code and 200 <= code < 300:
                report["action"] = "health_wake"
                log.info("health wake payload_id=%s -> HTTP %s (no alerts, post=false)", body["payload_id"], code)
            else:
                report["action"] = "health_wake_failed"
                log.warning("health wake HTTP %s", code)
            return report

        seen_path = os.path.join(base, SEEN_NAME)
        already = _load(seen_path, {})
        import watch
        features = _fetch(watch.USER_AGENT)
        recs = select_alerts(features, now, urgent_hb, quiet_hb, already)
        report["active_considered"] = len(recs)
        if not recs:
            report["action"] = "nothing_to_send"
            return report

        sent_doc = already
        now_iso = now.isoformat()
        for rec in recs:
            item = _item(rec["kind"], rec)
            body, pid = _body(rec["kind"], item, now)
            entry = {"id": rec["id"], "event": rec["event"], "kind": rec["kind"], "payload_id": pid}
            if dry:
                entry["would_post"] = True
                report["sent"].append(entry)
                log.info("dry-run: would wake %s %s payload_id=%s", rec["kind"], rec["event"], pid)
                continue
            try:
                code = _post(rec["kind"], body)
            except Exception as exc:
                log.warning("WA life-safety POST failed (%s) for %s; will retry next run", type(exc).__name__, rec["event"])
                report["skipped"].append({**entry, "error": type(exc).__name__})
                continue
            entry["http"] = code
            if code and 200 <= code < 300:
                sent_doc[rec["id"]] = now_iso
                if rec["kind"] != "urgent":
                    sent_doc[rec["id"] + "|WA"] = now_iso
                _mark_watcher_seen(base, rec["kind"], rec["id"], now_iso)
                report["sent"].append(entry)
                log.info("WA life-safety wake %s %s payload_id=%s -> HTTP %s", rec["kind"], rec["event"], pid, code)
            else:
                log.warning("WA life-safety HTTP %s for %s; will retry next run", code, rec["event"])
                report["skipped"].append(entry)
        if not dry:
            _save(seen_path, sent_doc)
        if report["sent"] and not dry:
            report["action"] = "sent"
        elif report["sent"] and dry:
            report["action"] = "would_send"
        elif report["skipped"]:
            report["action"] = "retry"
        else:
            report["action"] = "nothing_to_send"
        return report
    except Exception as exc:
        log.warning("WA life-safety path failed (%s); full relay continues", type(exc).__name__)
        report["action"] = "error"
        report["error"] = type(exc).__name__
        return report
