#!/usr/bin/env python3
"""Offline checks for the always-on WA tornado / SWS relay path. No network."""
import os
import sys
import tempfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "logic"))
sys.path.insert(0, ROOT)
os.environ["ALERT_RELAY"] = "1"
os.environ.setdefault("ALERT_RELAY_BASE", tempfile.mkdtemp(prefix="wa-ls-"))

import payload_seen
import wa_life_safety as wls

fails = 0


def check(name, cond):
    global fails
    if cond:
        print("ok", name)
    else:
        fails += 1
        print("FAIL", name)


def props(**kw):
    ev = kw.get("event", "Tornado Warning")
    ugc = kw.get("ugc", ["WAC033"])
    text = kw.get("text", "A landspout was confirmed near Renton.")
    return {
        "id": kw.get("id", "urn:oid:test:1"),
        "event": ev,
        "messageType": kw.get("messageType", "Alert"),
        "status": kw.get("status", "Actual"),
        "headline": kw.get("headline", ev),
        "description": text,
        "instruction": "",
        "sent": kw.get("sent", "2026-11-26T19:58:00+00:00"),
        "expires": kw.get("expires", "2026-11-26T20:15:00+00:00"),
        "geocode": {"UGC": ugc, "SAME": kw.get("same", ["053033"])},
        "areaDesc": kw.get("area", "Central King County"),
    }


def test_classify():
    check("WA TOR is urgent", wls.classify_life_safety(props()) == "urgent")
    check("WA Tornado Emergency is urgent", wls.classify_life_safety(props(event="Tornado Emergency", text="TORNADO EMERGENCY")) == "urgent")
    check("WA waterspout SWS is urgent", wls.classify_life_safety(props(event="Special Weather Statement", text="WATERSPOUTS ARE POSSIBLE OVER PUGET SOUND", ugc=["PZZ135"])) == "urgent")
    check("WA landspout SWS is urgent (11-26-26 rotation rule)", wls.classify_life_safety(props(event="Special Weather Statement", text="A STRONG THUNDERSTORM near Belfair. LANDSPOUTS possible. Pea size HAIL.")) == "urgent")
    check("WA funnel cloud SVR is urgent", wls.classify_life_safety(props(event="Severe Thunderstorm Warning", text="Funnel clouds are possible with this storm.")) == "urgent")
    check("WA waterspout SMW is urgent", wls.classify_life_safety(props(event="Special Marine Warning", text="Waterspouts possible.", ugc=["PZZ135"])) == "urgent")
    check("WA plain thunderstorm SWS stays quiet", wls.classify_life_safety(props(event="Special Weather Statement", text="A STRONG THUNDERSTORM near Belfair. Pea size HAIL and gusty winds.")) == "quiet")
    check("funneling wind is not rotation", wls.classify_life_safety(props(event="Wind Advisory", text="Winds funneling through the Gorge.")) is None)
    check("fog-only SWS is skipped", wls.classify_life_safety(props(event="Special Weather Statement", text="Dense fog will reduce visibility.")) is None)
    check("gusty-only SWS is skipped", wls.classify_life_safety(props(event="Special Weather Statement", text="Gusty winds this afternoon.")) is None)
    check("OR TOR is skipped", wls.classify_life_safety(props(ugc=["ORC051"], same=["041051"], text="Tornado warning")) is None)
    check("Update is skipped", wls.classify_life_safety(props(messageType="Update")) is None)
    check("Flood Warning is skipped", wls.classify_life_safety(props(event="Flood Warning")) is None)


def test_stable_ids():
    a = payload_seen.stable_item_id("u", ["urn:b", "urn:a"])
    b = payload_seen.stable_item_id("u", ["urn:a", "urn:b"])
    c = payload_seen.stable_item_id("q", ["urn:a", "urn:b"])
    check("stable_item_id ignores key order", a == b and a.startswith("u-") and len(a) == 18)
    check("stable_item_id prefix changes the id", a != c and c.startswith("q-"))
    tick_a = payload_seen.compute_id("u", ["urn:a"], "2026-11-26T19:58:00+00:00")
    tick_b = payload_seen.compute_id("u", ["urn:a"], "2026-11-26T19:58:01+00:00")
    check("legacy compute_id still depends on tick", tick_a != tick_b)
    check("health payload id is stable", wls.health_payload_id() == payload_seen.stable_item_id("u", ["alert-relay-health"]))
    body = wls.health_body()
    check("health body has no alerts and post=false", body["alerts"] == [] and body["post"] is False and body["test"] is True and body["payload_id"] == wls.health_payload_id())


def test_select_and_grace():
    now = datetime(2026, 11, 26, 20, 5, tzinfo=timezone.utc)
    feat = {"properties": props(id="urn:oid:test:tor")}
    # issued 19:58, now 20:05 -> 7 min old, over 90s grace
    recs = wls.select_alerts([feat], now, "fresh", "fresh", {})
    check("fresh hb still sends TOR older than 90s", recs and recs[0]["kind"] == "urgent")
    new_feat = {"properties": props(id="urn:oid:test:new", sent="2026-11-26T20:04:30+00:00")}
    recs = wls.select_alerts([new_feat], now, "fresh", "fresh", {})
    check("fresh hb grants 90s grace", recs == [])
    recs = wls.select_alerts([new_feat], now, "stale", "stale", {})
    check("stale hb uses zero grace", recs and recs[0]["id"] == "urn:oid:test:new")
    recs = wls.select_alerts([feat], now, "stale", "stale", {"urn:oid:test:tor": now.isoformat()})
    check("already-seen id is skipped", recs == [])
    expired = {"properties": props(id="urn:oid:test:old", expires="2026-11-26T20:00:00+00:00")}
    recs = wls.select_alerts([expired], now, "stale", "stale", {})
    check("expired alert is skipped", recs == [])


if __name__ == "__main__":
    test_classify()
    test_stable_ids()
    test_select_and_grace()
    if fails:
        print("%d failed" % fails)
        sys.exit(1)
    print("all wa life-safety checks passed")
