#!/usr/bin/env python3
"""Offline checks for payload ids, adopt/hold rules, secret sealing, and seen sync.

No network. Live dry-run is `ALERT_RELAY_DRY_RUN=1 python3 alert_relay/relay.py`.
"""
import base64
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "logic"))
sys.path.insert(0, ROOT)
os.environ["ALERT_RELAY"] = "1"
os.environ.setdefault("ALERT_RELAY_BASE", tempfile.mkdtemp(prefix="alert-relay-self-"))

import heartbeat
import payload_seen
import sent_index
import box_sync_seen
import setup_secrets
import watch
import watch_quiet
from nacl.public import PrivateKey, SealedBox

PT = ZoneInfo("America/Los_Angeles")
fails = 0


def check(name, cond):
    global fails
    if cond:
        print("ok", name)
    else:
        fails += 1
        print("FAIL", name)


def pt(hour, day=23):
    return datetime(2026, 10, day, hour, tzinfo=PT)


def test_payload_id():
    tick = "2026-10-23T12:00:00+00:00"
    a = payload_seen.compute_id("u", ["b", "a"], tick)
    b = payload_seen.compute_id("u", ["a", "b"], tick)
    c = payload_seen.compute_id("u", ["a", "b"], "2026-10-23T12:00:01+00:00")
    check("payload id stable for the same ids and tick", a == b and a.startswith("u-") and len(a) == 18)
    check("payload id changes when the tick changes", a != c)
    state = {}
    first = payload_seen.stable_id(state, "q", ["x", "y"], tick)
    second = payload_seen.stable_id(state, "q", ["y", "x"], "2026-10-23T13:00:00+00:00")
    check("inflight payload id is reused", first == second == state["inflight_payload"]["payload_id"])
    payload_seen.clear_inflight(state)
    third = payload_seen.stable_id(state, "q", ["x", "y"], "2026-10-23T13:00:00+00:00")
    check("cleared inflight gets a new id", third != first)


def test_heartbeat():
    now = datetime(2026, 10, 23, 18, tzinfo=timezone.utc)
    state, age, _stamp = heartbeat.status(None, 600, now)
    check("missing heartbeat", state == "missing" and age is None)
    fresh = (now - timedelta(minutes=3)).isoformat()
    state, age, _stamp = heartbeat.status(fresh, 600, now)
    check("fresh heartbeat", state == "fresh" and 170 < age < 190)
    stale = (now - timedelta(minutes=11)).isoformat()
    state, _age, _stamp = heartbeat.status(stale, 600, now)
    check("stale urgent heartbeat at 11 min", state == "stale")
    state, _age, _stamp = heartbeat.status(stale, 12 * 60, now)
    check("11 min is still fresh for quiet", state == "fresh")
    future = (now + timedelta(hours=2)).isoformat()
    state, _age, _stamp = heartbeat.status(future, 600, now)
    check("far-future heartbeat is stale", state == "stale")


def test_hold_and_classify():
    check("USA hold at 9 PM PT", watch_quiet.overnight_held("USA", pt(21)))
    check("USA hold at 1 AM PT", watch_quiet.overnight_held("USA", pt(1)))
    check("USA open at 2 AM PT", not watch_quiet.overnight_held("USA", pt(2)))
    check("WA hold at 3 AM PT", watch_quiet.overnight_held("WA", pt(3)))
    check("WA open at 5 AM PT", not watch_quiet.overnight_held("WA", pt(5)))
    check("urgent overnight matches USA window", watch.in_overnight(pt(1)) and not watch.in_overnight(pt(3)))
    check("WA SVR hold is wider", watch.wa_hold(pt(3)) and not watch.wa_hold(pt(6)))
    feature = {"properties": {
        "id": "urn:oid:test-tor", "event": "Tornado Warning", "messageType": "Alert", "status": "Actual",
        "headline": "Tornado Warning",
        "description": "TORNADO EMERGENCY for Dallas.",
        "geocode": {"UGC": ["TXC113"], "SAME": ["048113"]},
        "areaDesc": "Dallas, TX",
        "parameters": {"tornadoDamageThreat": ["CATASTROPHIC"], "VTEC": ["/O.NEW.KFWD.TO.W.0001.000000T0000Z-000000T0000Z/"]},
        "sent": "2026-10-23T18:00:00+00:00",
    }}
    got = watch.classify(feature)
    check("catastrophic tornado classifies", got == ("USA", "Tornado Emergency", True))
    svr = {"properties": {
        "id": "urn:oid:test-svr", "event": "Severe Thunderstorm Warning", "messageType": "Alert", "status": "Actual",
        "geocode": {"UGC": ["WAC033"]}, "areaDesc": "King, WA", "parameters": {},
        "description": "", "headline": "Severe Thunderstorm Warning",
    }}
    check("WA SVR still classifies without census data", watch.classify(svr) == ("WA", watch.WA_SVR_REASON, False))
    check("tornado is cap exempt", watch.cap_exempt({"event": "Tornado Warning", "reason": "Tornado Emergency"}))
    held = watch._urgent_held_at_issue({"reason": watch.WA_SVR_REASON}, pt(22))
    life = watch._urgent_held_at_issue({"reason": "Tornado Emergency"}, pt(22))
    check("WA SVR issued at 10 PM was held", held and not life)


def test_sent_roundtrip():
    now = datetime.now(timezone.utc).isoformat()
    sent = sent_index.fold(sent_index.empty(), [{
        "at": now, "channel": "urgent", "payload_id": "u-aaaaaaaaaaaaaaaa",
        "items": [{"id": "urn:oid:1", "keys": ["urn:oid:1", "urn:oid:1|L3"], "sent": now}],
    }, {
        "at": now, "channel": "quiet", "payload_id": "q-bbbbbbbbbbbbbbbb",
        "items": [
            {"id": "urn:oid:2", "ids": ["urn:oid:2"], "page": "WA", "event": "Wind Advisory", "sent": now},
            {"kind": "earthquake", "id": "us1000", "page": "WA", "time": now},
            {"kind": "spc-outlook", "id": "spc:d1:2026-10-23T16:00:00Z:USA:ENH", "page": "USA", "day": 1,
             "outlook_date": "2026-10-23", "states_by_risk": {"ENH": ["TX"], "SLGT": ["OK"]}},
            {"kind": "hurricane-cone", "id": "nhc:AL092026:2026-10-23", "storm": "AL092026 Test", "basin": "AL", "second": False},
            {"kind": "gov_imagery", "id": "govimg:abc", "items": [{"key": "feed:abc"}]},
        ],
    }])
    sent_index.set_pass_snapshot(sent, {"Snoqualmie Pass": {"status": "closed"}}, now)
    base = tempfile.mkdtemp(prefix="alert-relay-box-")
    for name, seed in (
        ("seen.json", {"urn:oid:old": now}),
        ("seen_quiet.json", {}),
        ("seen_quakes_quiet.json", {}),
        ("spc_quiet_state.json", {"schema": 2, "posted": {}, "fired": [], "days": {}}),
        ("hurricanes_quiet_state.json", {"storms": {}}),
        ("passes_quiet_state.json", {"passes": {"Snoqualmie Pass": {"status": "open"}}, "last_poll": "2000-01-01T00:00:00+00:00"}),
        ("gov_imagery_seen.json", {"feeds": {}}),
    ):
        with open(os.path.join(base, name), "w") as fh:
            json.dump(seed, fh)
    counts = box_sync_seen.apply_sent(sent, base)
    seen = json.load(open(os.path.join(base, "seen.json")))
    quiet = json.load(open(os.path.join(base, "seen_quiet.json")))
    spc = json.load(open(os.path.join(base, "spc_quiet_state.json")))
    storms = json.load(open(os.path.join(base, "hurricanes_quiet_state.json")))
    passes = json.load(open(os.path.join(base, "passes_quiet_state.json")))
    check("sync added urgent keys and kept the old one", "urn:oid:1" in seen and "urn:oid:1|L3" in seen and "urn:oid:old" in seen)
    check("sync added quiet and quake ids", quiet.get("urn:oid:2|WA") == now and counts.get("quiet") == 1)
    check("sync merged SPC ranks", spc["posted"]["USA:d1:2026-10-23"]["ranks"]["TX"] == 3)
    check("sync set hurricane woken", storms["storms"]["AL092026"]["woken"] == 1)
    check("sync replaced older pass snapshot", passes["passes"]["Snoqualmie Pass"]["status"] == "closed")
    empty_base = tempfile.mkdtemp(prefix="alert-relay-empty-")
    box_sync_seen.apply_sent(sent, empty_base)
    check("sync does not create a missing seen file", not os.path.exists(os.path.join(empty_base, "seen.json")))
    other = sent_index.fold(sent_index.empty(), [{
        "at": now, "channel": "hurricane-nope", "items": [],
    }])
    merged = sent_index.union_sent(sent, other)
    check("union keeps urgent keys", "urn:oid:1" in merged["urgent"]["keys"])


def test_seal():
    secret = PrivateKey.generate()
    public = base64.b64encode(bytes(secret.public_key)).decode("ascii")
    token = "Bearer unit-test-secret"
    encrypted = setup_secrets.seal(public, token)
    opened = SealedBox(secret).decrypt(base64.b64decode(encrypted))
    check("sealed box roundtrip", opened == token.encode("utf-8") and token not in encrypted)


def test_adopt():
    import adopt
    before = datetime(2026, 10, 23, 20, tzinfo=timezone.utc)
    items = [
        {"id": "old", "sent": "2026-10-23T18:00:00+00:00"},
        {"id": "new", "sent": "2026-10-23T21:00:00+00:00"},
        {"id": "held", "sent": "2026-10-23T19:00:00+00:00"},
    ]
    def held(item, _sent):
        return item["id"] == "held"
    adopted, keep = adopt.partition(items, before, held, lambda item: adopt.parse_time(item["sent"]))
    check("adopt keeps outage and held items", [i["id"] for i in adopted] == ["old"] and {i["id"] for i in keep} == {"new", "held"})


if __name__ == "__main__":
    test_payload_id()
    test_heartbeat()
    test_hold_and_classify()
    test_sent_roundtrip()
    test_seal()
    test_adopt()
    if fails:
        print("%d failed" % fails)
        sys.exit(1)
    print("all offline checks passed")
