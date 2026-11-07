"""Fold successful relay deliveries into the public sent.json document.

The box reads this file. It lists only alerts the relay POSTed, not alerts it
adopted or seeded. Item ids are what the receiver and the box watchers dedupe on.
"""
import json
import os
from datetime import datetime, timedelta, timezone

from adopt import parse_time

RISK_RANK = {"TSTM": 0, "MRGL": 1, "SLGT": 2, "ENH": 3, "MDT": 4, "HIGH": 5}
KEEP_DAYS = 7
GOV_KEEP_DAYS = 30
MAX_PAYLOAD_IDS = 100


def empty():
    return {
        "version": 1,
        "updated": None,
        "urgent": {"keys": {}, "payload_ids": []},
        "quiet": {
            "seen": {},
            "quakes": {},
            "spc_posted": {},
            "hurricanes": {},
            "gov_feeds": {},
            "pass_snapshot": None,
            "payload_ids": [],
        },
    }


def _storm_id(item):
    parts = str(item.get("id") or "").split(":")
    if len(parts) >= 2 and parts[0] == "nhc":
        return parts[1]
    return None


def _append_pid(bucket, pid):
    if not pid:
        return
    ids = [x for x in (bucket.get("payload_ids") or []) if x != pid]
    ids.append(pid)
    bucket["payload_ids"] = ids[-MAX_PAYLOAD_IDS:]


def fold(sent, records):
    sent = sent or empty()
    urgent = sent.setdefault("urgent", empty()["urgent"])
    quiet = sent.setdefault("quiet", empty()["quiet"])
    urgent.setdefault("keys", {})
    quiet.setdefault("seen", {})
    quiet.setdefault("quakes", {})
    quiet.setdefault("spc_posted", {})
    quiet.setdefault("hurricanes", {})
    quiet.setdefault("gov_feeds", {})
    for rec in records:
        at = rec.get("at")
        channel = rec.get("channel")
        if channel == "urgent":
            for item in rec.get("items") or []:
                keys = item.get("keys") or ([item["id"]] if item.get("id") else [])
                for key in keys:
                    if key:
                        urgent["keys"][str(key)] = at
            _append_pid(urgent, rec.get("payload_id"))
            continue
        if channel != "quiet":
            continue
        for item in rec.get("items") or []:
            kind = item.get("kind")
            if kind == "earthquake":
                if item.get("id"):
                    quiet["quakes"][item["id"]] = at
            elif kind == "spc-outlook":
                _fold_spc(quiet, item, at)
            elif kind == "hurricane-cone":
                _fold_hurricane(quiet, item, at)
            elif kind == "mountain-pass":
                pass  # snapshot attached by the caller via set_pass_snapshot
            elif kind == "gov_imagery":
                for sub in item.get("items") or []:
                    if sub.get("key"):
                        quiet["gov_feeds"][sub["key"]] = at
            elif kind == "batch":
                fold(sent, [{"at": at, "channel": "quiet", "payload_id": rec.get("payload_id"),
                             "items": item.get("items") or []}])
            else:
                page = item.get("page")
                for ident in item.get("ids") or ([item["id"]] if item.get("id") else []):
                    if ident and page:
                        quiet["seen"]["%s|%s" % (ident, page)] = at
        _append_pid(quiet, rec.get("payload_id"))
    return sent


def _fold_spc(quiet, item, at):
    day = item.get("day")
    page = item.get("page")
    outlook = item.get("outlook_date")
    if not (day and page and outlook):
        return
    key = "%s:d%s:%s" % (page, day, outlook)
    prev = quiet["spc_posted"].get(key) or {"ranks": {}, "ids": []}
    ranks = {k: int(v) for k, v in (prev.get("ranks") or {}).items()}
    for risk, states in (item.get("states_by_risk") or {}).items():
        rank = RISK_RANK.get(risk)
        if rank is None:
            continue
        for state in states or []:
            ranks[state] = max(ranks.get(state, -1), rank)
    ids = list(prev.get("ids") or [])
    if item.get("id") and item["id"] not in ids:
        ids.append(item["id"])
    quiet["spc_posted"][key] = {"ranks": ranks, "ids": ids[-40:], "at": at, "max_rank": max(ranks.values()) if ranks else -1}


def _fold_hurricane(quiet, item, at):
    sid = _storm_id(item)
    if not sid:
        return
    prev = dict(quiet["hurricanes"].get(sid) or {})
    woken = 2 if item.get("second") else 1
    if woken >= int(prev.get("woken") or 0):
        prev["woken"] = woken
    prev["seeded"] = False
    prev["name"] = item.get("storm") or prev.get("name")
    prev["basin"] = item.get("basin") or prev.get("basin")
    if item.get("second"):
        prev["second_woken_at"] = at
    else:
        prev["first_woken_at"] = prev.get("first_woken_at") or at
    quiet["hurricanes"][sid] = prev


def set_pass_snapshot(sent, snapshot, at):
    if snapshot:
        sent.setdefault("quiet", empty()["quiet"])["pass_snapshot"] = {"at": at, "passes": snapshot}


def prune(sent, now=None):
    now = now or datetime.now(timezone.utc)
    sent = sent or empty()

    def keep(mapping, days):
        cut = now - timedelta(days=days)
        out = {}
        for key, value in (mapping or {}).items():
            ts = parse_time(value if isinstance(value, str) else (value or {}).get("at"))
            if ts is None or ts > cut:
                out[key] = value
        return out

    sent["urgent"]["keys"] = keep(sent.get("urgent", {}).get("keys"), KEEP_DAYS)
    quiet = sent.setdefault("quiet", empty()["quiet"])
    quiet["seen"] = keep(quiet.get("seen"), KEEP_DAYS)
    quiet["quakes"] = keep(quiet.get("quakes"), KEEP_DAYS)
    quiet["gov_feeds"] = keep(quiet.get("gov_feeds"), GOV_KEEP_DAYS)
    sent["updated"] = now.isoformat()
    return sent


def load(path):
    try:
        with open(path) as fh:
            doc = json.load(fh)
        if isinstance(doc, dict) and doc.get("version") == 1:
            return doc
    except Exception:
        pass
    return empty()


def save(path, doc):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(doc, fh, indent=1, sort_keys=True)
        fh.write("\n")
    os.replace(tmp, path)


def read_jsonl(path):
    rows = []
    try:
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return rows


def _uniq(seq):
    out = []
    for item in seq:
        if item not in out:
            out.append(item)
    return out


def union_sent(a, b):
    """Combine two sent indexes without dropping ids from either."""
    if not a or a.get("version") != 1:
        return b or empty()
    if not b or b.get("version") != 1:
        return a
    out = empty()
    out["urgent"]["keys"] = dict((a.get("urgent") or {}).get("keys") or {})
    out["urgent"]["keys"].update((b.get("urgent") or {}).get("keys") or {})
    out["urgent"]["payload_ids"] = _uniq(
        list((a.get("urgent") or {}).get("payload_ids") or []) + list((b.get("urgent") or {}).get("payload_ids") or [])
    )[-MAX_PAYLOAD_IDS:]
    qa, qb = a.get("quiet") or {}, b.get("quiet") or {}
    out["quiet"]["seen"] = dict(qa.get("seen") or {})
    out["quiet"]["seen"].update(qb.get("seen") or {})
    out["quiet"]["quakes"] = dict(qa.get("quakes") or {})
    out["quiet"]["quakes"].update(qb.get("quakes") or {})
    out["quiet"]["gov_feeds"] = dict(qa.get("gov_feeds") or {})
    out["quiet"]["gov_feeds"].update(qb.get("gov_feeds") or {})
    out["quiet"]["payload_ids"] = _uniq(list(qa.get("payload_ids") or []) + list(qb.get("payload_ids") or []))[-MAX_PAYLOAD_IDS:]
    posted = {}
    for src in (qa.get("spc_posted") or {}, qb.get("spc_posted") or {}):
        for key, rec in src.items():
            prev = posted.get(key) or {"ranks": {}, "ids": []}
            ranks = {k: int(v) for k, v in (prev.get("ranks") or {}).items()}
            for state, rank in (rec.get("ranks") or {}).items():
                ranks[state] = max(ranks.get(state, -1), int(rank))
            ids = _uniq(list(prev.get("ids") or []) + list(rec.get("ids") or []))
            posted[key] = {"ranks": ranks, "ids": ids[-40:], "at": rec.get("at") or prev.get("at"),
                           "max_rank": max(ranks.values()) if ranks else -1}
    out["quiet"]["spc_posted"] = posted
    storms = {}
    for src in (qa.get("hurricanes") or {}, qb.get("hurricanes") or {}):
        for sid, rec in src.items():
            prev = dict(storms.get(sid) or {})
            if int(rec.get("woken") or 0) >= int(prev.get("woken") or 0):
                prev.update(rec)
                prev["woken"] = max(int(rec.get("woken") or 0), int(storms.get(sid, {}).get("woken") or 0))
            else:
                for field in ("name", "basin", "first_woken_at", "second_woken_at"):
                    if rec.get(field) and not prev.get(field):
                        prev[field] = rec[field]
            storms[sid] = prev
    out["quiet"]["hurricanes"] = storms
    snaps = [s for s in (qa.get("pass_snapshot"), qb.get("pass_snapshot")) if isinstance(s, dict) and s.get("passes")]
    snaps.sort(key=lambda s: str(s.get("at") or ""))
    out["quiet"]["pass_snapshot"] = snaps[-1] if snaps else None
    times = [t for t in (a.get("updated"), b.get("updated")) if t]
    out["updated"] = max(times) if times else None
    return out


def canonical(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":"))
