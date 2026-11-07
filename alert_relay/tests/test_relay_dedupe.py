#!/usr/bin/env python3
"""Offline tests for the 11-03-26 relay dedupe (Benjamin t2237u). No network, no POSTs.

Covers: new alert, same alert repeated, updated/upgraded alert (new version), cancellation,
missing / corrupt state files, several alerts in one run, publish timing (after each channel),
publish failure / retry, no re-commit when nothing changed, dry-run publishes nothing.

Run:  python3 alert_relay/tests/test_relay_dedupe.py
"""
import copy
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "logic"))
sys.path.insert(0, ROOT)
BASE = tempfile.mkdtemp(prefix="relay-dedupe-test-")
os.environ["ALERT_RELAY"] = "1"
os.environ["ALERT_RELAY_BASE"] = BASE
for k in ("GITHUB_TOKEN", "GITHUB_RELAY_TOKEN", "URGENT_WEBHOOK_URL", "URGENT_WEBHOOK_AUTH",
          "QUIET_WEBHOOK_URL", "QUIET_WEBHOOK_AUTH", "ALERT_RELAY_DRY_RUN"):
    os.environ.pop(k, None)

import box_sync_seen   # noqa: E402
import delivered       # noqa: E402
import github_api      # noqa: E402
import relay           # noqa: E402
import sent_index      # noqa: E402
import watch           # noqa: E402
import watch_quiet     # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(("ok   " if cond else "FAIL ") + name + ("" if cond else "  -> %s" % detail))
    if not cond:
        FAILS.append(name)


def load_fx(name):
    with open(os.path.join(HERE, "fixtures", name)) as fh:
        return json.load(fh)


# ---------- recorded alerts ----------
SMW = load_fx("smw_ksew_20261031.json")["features"]
SMW_0619 = [f for f in SMW if f["properties"]["sent"].startswith("2026-10-31T06:19")][0]   # Alert, VTEC NEW 0001
SMW_0757 = [f for f in SMW if f["properties"]["sent"].startswith("2026-10-31T07:57")][0]   # Alert, VTEC NEW 0002 (new event)
TOR_CAN = load_fx("tor_kind_cancel_20261015.json")                                         # recorded Cancel, KIND TO.W.0081


def tor_alert_and_update():
    """PDS Alert + Tornado Emergency Update built from the recorded KIND Cancel (same office/ETN, its referenced id)."""
    can = TOR_CAN["properties"]
    root_id = can["references"][0]["identifier"]
    alert = copy.deepcopy(TOR_CAN)
    p = alert["properties"]
    p.update({"id": root_id, "messageType": "Alert", "sent": "2026-10-15T19:41:00-04:00",
              "expires": "2026-10-15T20:15:00-04:00", "references": [], "status": "Actual"})
    p["parameters"] = dict(p["parameters"], VTEC=["/O.NEW.KIND.TO.W.0081.261015T2341Z-261016T0015Z/"],
                           NWSheadline=["TORNADO WARNING"], tornadoDetection=["OBSERVED"],
                           tornadoDamageThreat=["CONSIDERABLE"])
    p["description"] = "At 741 PM EDT, a severe thunderstorm capable of producing a tornado was located near Wheatland."
    p["headline"] = "Tornado Warning issued October 15 at 7:41PM EDT until October 15 at 8:15PM EDT"
    alert["id"] = root_id
    upd = copy.deepcopy(alert)
    q = upd["properties"]
    q.update({"id": root_id.replace(".001.1", ".002.1"), "messageType": "Update", "sent": "2026-10-15T19:52:00-04:00",
              "references": [{"identifier": root_id, "sent": "2026-10-15T19:41:00-04:00"}]})
    q["parameters"] = dict(q["parameters"], VTEC=["/O.CON.KIND.TO.W.0081.000000T0000Z-261016T0015Z/"],
                           tornadoDetection=["OBSERVED"], tornadoDamageThreat=["CATASTROPHIC"])
    q["description"] = "TORNADO EMERGENCY. At 752 PM EDT, a confirmed large and destructive tornado was located near Wheatland."
    upd["id"] = q["id"]
    return alert, upd


def evaluate(features, seen, now, tracker=None):
    tracker = tracker or watch.LevelTracker({}, fetch=False)
    send, held = watch.evaluate(copy.deepcopy(features), seen, set(), now, False, tracker)
    return send + held, tracker


def deliver_urgent(base, items, at=None):
    """What watch.run does after a 2xx in the relay: delivered.note with the item keys."""
    delivered.note(base, "urgent", "u-test%012d" % len(items), [
        {"id": i["id"], "keys": list(i["_keys"]), "event": i["event"], "scope": i["scope"],
         "reason": i["reason"], "sent": i["sent"]} for i in items])


def fresh_dir(tag):
    d = os.path.join(BASE, tag)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d)
    return d


def box_dir_with_real_files(tag):
    """Copies of the live box seen files (read-only source), so merge format is the real one."""
    d = fresh_dir(tag)
    for name in ("seen.json", "seen_quiet.json", "spc_quiet_state.json", "passes_quiet_state.json", "seen_quakes_quiet.json"):
        src = os.path.join("/workspace/urgent_watch", name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(d, name))
        else:
            with open(os.path.join(d, name), "w") as fh:
                json.dump({}, fh)
    return d


# ---------- scenario tests (dedupe keys) ----------
def test_new_then_same_alert():
    now = datetime(2026, 10, 31, 13, 25, tzinfo=timezone.utc)   # 6:25 AM PT, SMW 0001 active
    seen = {}
    out, _ = evaluate([SMW_0619], seen, now)
    check("new alert: relay would send the 06:19 SMW", len(out) == 1, out)
    relay_dir = fresh_dir("r1")
    deliver_urgent(relay_dir, out)
    sent, changed = relay.fold_new_deliveries(relay_dir, sent_index.empty())
    check("delivery folded into sent.json", changed and out[0]["id"] in sent["urgent"]["keys"])
    # box wakes: resync merges the relay keys, the same alert is no longer new for the box
    box = box_dir_with_real_files("b1")
    box_sync_seen.apply_sent(sent, base=box)
    box_seen = json.load(open(os.path.join(box, "seen.json")))
    out2, _ = evaluate([SMW_0619], box_seen, now)
    check("same alert again: box does not re-send after resync", out2 == [], out2)
    # relay with an evicted cache: rehydrate from sent.json also blocks the repeat
    r2 = fresh_dir("r2")
    with open(os.path.join(r2, "seen.json"), "w") as fh:
        json.dump({}, fh)
    relay.rehydrate(sent, r2)
    out3, _ = evaluate([SMW_0619], json.load(open(os.path.join(r2, "seen.json"))), now)
    check("same alert again: relay with evicted cache + sent.json does not re-send", out3 == [], out3)


def test_genuinely_new_alert_still_sends():
    now = datetime(2026, 10, 31, 15, 0, tzinfo=timezone.utc)   # 8:00 AM PT, both SMWs in the feed
    first, _ = evaluate([SMW_0619], {}, datetime(2026, 10, 31, 13, 25, tzinfo=timezone.utc))
    relay_dir = fresh_dir("r3")
    deliver_urgent(relay_dir, first)
    sent, _ = relay.fold_new_deliveries(relay_dir, sent_index.empty())
    box = box_dir_with_real_files("b3")
    box_sync_seen.apply_sent(sent, base=box)
    out, _ = evaluate([SMW_0619, SMW_0757], json.load(open(os.path.join(box, "seen.json"))), now)
    ids = [i["id"] for i in out]
    check("new alert after a relay send is still sent (07:57 SMW, new VTEC event)",
          ids == [SMW_0757["properties"]["id"]], ids)


def test_update_new_version_still_sends():
    alert, upd = tor_alert_and_update()
    now = datetime(2026, 10, 15, 23, 55, tzinfo=timezone.utc)
    out, tracker = evaluate([alert], {}, datetime(2026, 10, 15, 23, 45, tzinfo=timezone.utc))
    check("PDS tornado warning (recorded KIND event) is sent first", len(out) == 1, out)
    relay_dir = fresh_dir("r4")
    deliver_urgent(relay_dir, out)
    sent, _ = relay.fold_new_deliveries(relay_dir, sent_index.empty())
    box = box_dir_with_real_files("b4")
    box_sync_seen.apply_sent(sent, base=box)
    box_seen = json.load(open(os.path.join(box, "seen.json")))
    out2, _ = evaluate([alert, upd], box_seen, now, tracker)
    ids = [i["id"] for i in out2]
    check("upgraded Update (new id, PDS -> Tornado Emergency) is NOT dropped", ids == [upd["properties"]["id"]],
          [(i["id"][-8:], i["reason"]) for i in out2])
    check("the already-sent original is not re-sent", alert["properties"]["id"] not in ids)


def test_cancel_not_blocked_by_dedupe():
    alert, _upd = tor_alert_and_update()
    out, _ = evaluate([alert], {}, datetime(2026, 10, 15, 23, 45, tzinfo=timezone.utc))
    relay_dir = fresh_dir("r5")
    deliver_urgent(relay_dir, out)
    sent, _ = relay.fold_new_deliveries(relay_dir, sent_index.empty())
    can_id = TOR_CAN["properties"]["id"]
    keys = set(sent["urgent"]["keys"])
    check("cancellation id is never in the dedupe index (different id)", can_id not in keys
          and not any(k.startswith(can_id) for k in keys))
    # The dedupe index does not change what the watcher does with a Cancel: same result with and without it.
    box = box_dir_with_real_files("b5")
    box_sync_seen.apply_sent(sent, base=box)
    a, _ = evaluate([TOR_CAN], {}, datetime(2026, 10, 15, 23, 59, tzinfo=timezone.utc))
    b, _ = evaluate([TOR_CAN], json.load(open(os.path.join(box, "seen.json"))), datetime(2026, 10, 15, 23, 59, tzinfo=timezone.utc))
    check("cancel handling identical with or without the relay index", [i["id"] for i in a] == [i["id"] for i in b], (a, b))


def test_quiet_spc_echo_replay():
    """Replay of the 11-02 2:32 AM PT echo: relay sent USA SPC D1 SLGT, the woken box sent it again 1 min later."""
    r = fresh_dir("r_spc")
    item = {"source": "quiet-watch", "kind": "spc-outlook", "page": "USA", "day": 1, "risk": "SLGT",
            "id": "spc:d1:2026-11-02T06:00:00+00:00:USA:SLGT", "outlook_date": "2026-11-02",
            "states": ["AR", "KS", "MO", "OK", "TX"], "states_by_risk": {"SLGT": ["AR", "KS", "MO", "OK", "TX"]}}
    wsw = {"source": "quiet-watch", "id": "urn:oid:2.49.0.1.840.0.test-wsw.001.1", "page": "WA", "event": "Winter Storm Warning"}
    delivered.note(r, "quiet", "q-50cc02fbe9531abe", [item, wsw])
    sent, _ = relay.fold_new_deliveries(r, sent_index.empty())
    box = box_dir_with_real_files("b_spc")
    with open(os.path.join(box, "spc_quiet_state.json"), "w") as fh:   # the live file already has 11-02 ENH
        json.dump({"schema": 2, "days": {}, "posted": {}, "fired": []}, fh)
    box_sync_seen.apply_sent(sent, base=box)
    st = json.load(open(os.path.join(box, "spc_quiet_state.json")))
    rec = (st.get("posted") or {}).get("USA:d1:2026-11-02") or {}
    check("SPC outlook the relay sent is marked posted on the box (no echo)",
          all(rec.get("ranks", {}).get(x, -1) >= 2 for x in ("AR", "KS", "MO", "OK", "TX")), rec)
    check("upgrade (ENH) after a relay SLGT is still a new rank for the box",
          all(rec.get("ranks", {}).get(x, -1) < 3 for x in ("AR", "KS", "MO", "OK", "TX")))
    qs = json.load(open(os.path.join(box, "seen_quiet.json")))
    check("quiet alert the relay sent is in the box quiet seen file", wsw["id"] + "|WA" in qs)


# ---------- fail-open ----------
def test_missing_and_corrupt_state():
    now = datetime(2026, 10, 31, 13, 25, tzinfo=timezone.utc)
    r = fresh_dir("r6")
    with open(os.path.join(r, "sent.json"), "w") as fh:
        fh.write("{not json")
    s = sent_index.load(os.path.join(r, "sent.json"))
    check("corrupt sent.json loads as empty (fail-open)", s == sent_index.empty())
    relay.rehydrate(s, r)
    check("empty index creates no seen file (cold-start seed rule kept)", not os.path.exists(os.path.join(r, "seen.json")))
    out, _ = evaluate([SMW_0619], {}, now)
    check("with no state the alert is sent, not dropped", len(out) == 1)
    # corrupt / wrong-version remote index: box fetch returns None, merge is a no-op, box still sends
    box = box_dir_with_real_files("b6")
    before = open(os.path.join(box, "seen.json")).read()
    import io
    import urllib.request as _ur
    real_urlopen = _ur.urlopen
    for body in ("{not json", json.dumps({"version": 99, "urgent": {"keys": {"x": "y"}}})):
        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        # the live path (contents API, then raw) with a bad body; no network is touched
        _ur.urlopen = lambda req, timeout=20, _b=body: _Resp(_b.encode())
        os.environ["BOX_WATCH_BASE"] = box
        try:
            doc = box_sync_seen.fetch_sent()
            box_sync_seen.sync()
        finally:
            _ur.urlopen = real_urlopen
            os.environ.pop("BOX_WATCH_BASE", None)
        check("bad remote index (%s) is ignored by the box" % ("corrupt" if body.startswith("{not") else "wrong version"),
              doc is None and open(os.path.join(box, "seen.json")).read() == before)
    # box seen file missing: sync never creates it
    nobox = fresh_dir("b6b")
    box_sync_seen.apply_sent({"version": 1, "urgent": {"keys": {"k": "2026-11-03T00:00:00+00:00"}}, "quiet": {}}, base=nobox)
    check("missing box seen file is not created by sync", not os.path.exists(os.path.join(nobox, "seen.json")))
    # corrupt delivery log lines are skipped, good lines kept
    r7 = fresh_dir("r7")
    with open(os.path.join(r7, "relay_delivered.jsonl"), "w") as fh:
        fh.write("garbage\n")
        fh.write(json.dumps({"at": "2026-11-03T00:00:00+00:00", "channel": "urgent", "payload_id": "u-x",
                             "items": [{"id": "A", "keys": ["A", "A|L1"]}]}) + "\n")
    s7, ch = relay.fold_new_deliveries(r7, sent_index.empty())
    check("corrupt delivery line skipped, valid one folded", ch and "A|L1" in s7["urgent"]["keys"])


def test_bounded_state():
    old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    new = datetime.now(timezone.utc).isoformat()
    s = sent_index.empty()
    s["urgent"]["keys"] = {"old": old, "new": new}
    s["quiet"]["seen"] = {"o|USA": old, "n|WA": new}
    s = sent_index.prune(s)
    check("index pruned after 7 days (bounded)", list(s["urgent"]["keys"]) == ["new"] and list(s["quiet"]["seen"]) == ["n|WA"])


# ---------- publish behaviour ----------
class FakeGitHub:
    def __init__(self, put_codes=None):
        self.put_codes = list(put_codes or [])
        self.files = {}
        self.calls = []

    def install(self):
        github_api.ensure_branch = lambda repo, b, f, t: self.calls.append("ensure") or True
        github_api.get_contents_sha = lambda repo, p, ref, t: self.calls.append("sha") or ("sha1" if p in self.files else None)
        github_api.put_contents = self._put
        github_api.get_raw_file = lambda repo, p, ref, t="": (200, self.files[p]) if p in self.files else (404, None)

    def _put(self, repo, path, branch, msg, content, sha, token):
        self.calls.append("put")
        code = self.put_codes.pop(0) if self.put_codes else 201
        if code in (200, 201):
            self.files[path] = content.decode("utf-8")
        return code, {}


def test_publish_retry_and_idempotence():
    os.environ["ALERT_RELAY_PUBLISH"] = "1"
    os.environ["GITHUB_TOKEN"] = "test-token-not-real"
    gh = FakeGitHub(put_codes=[409, 201])
    gh.install()
    r = fresh_dir("r8")
    deliver_urgent(r, [{"id": "A", "_keys": ["A"], "event": "Tornado Warning", "scope": "USA", "reason": "x", "sent": None}])
    sent, remote = relay.flush_deliveries(r, sent_index.empty(), None)
    check("409 conflict retried once, then published", gh.calls.count("put") == 2 and "sent.json" in gh.files, gh.calls)
    gh.calls.clear()
    remote_doc = json.loads(gh.files["sent.json"])
    merged = sent_index.union_sent(sent_index.load(os.path.join(r, "sent.json")), remote_doc)
    relay.flush_deliveries(r, merged, remote_doc)
    check("next run with nothing new does not commit again", "put" not in gh.calls, gh.calls)
    # publish failure: POST already done, index kept locally and published on a later run
    gh2 = FakeGitHub(put_codes=[500])
    gh2.install()
    r9 = fresh_dir("r9")
    deliver_urgent(r9, [{"id": "B", "_keys": ["B"], "event": "Tornado Warning", "scope": "USA", "reason": "x", "sent": None}])
    s9, rem9 = relay.flush_deliveries(r9, sent_index.empty(), None)
    check("publish failure keeps the delivery in the local index", "B" in s9["urgent"]["keys"] and "sent.json" not in gh2.files)
    s9b, _ = relay.flush_deliveries(r9, sent_index.load(os.path.join(r9, "sent.json")), None)
    check("failed publish is retried on the next run", "sent.json" in gh2.files and '"B"' in gh2.files["sent.json"])
    # token missing: logs, does not raise, returns index
    os.environ.pop("GITHUB_TOKEN")
    gh3 = FakeGitHub()
    gh3.install()
    r10 = fresh_dir("r10")
    deliver_urgent(r10, [{"id": "C", "_keys": ["C"], "event": "x", "scope": "USA", "reason": "x", "sent": None}])
    s10, _ = relay.flush_deliveries(r10, sent_index.empty(), None)
    check("no token: nothing published, nothing raised, delivery kept", "C" in s10["urgent"]["keys"] and not gh3.files)
    os.environ["ALERT_RELAY_PUBLISH"] = "0"
    os.environ["GITHUB_TOKEN"] = "test-token-not-real"
    r11 = fresh_dir("r11")
    deliver_urgent(r11, [{"id": "D", "_keys": ["D"], "event": "x", "scope": "USA", "reason": "x", "sent": None}])
    relay.flush_deliveries(r11, sent_index.empty(), None)
    check("dry-run (PUBLISH=0) never publishes", not gh3.files)
    os.environ.pop("GITHUB_TOKEN")


def test_union_idempotent():
    s = sent_index.empty()
    s = sent_index.fold(s, [{"at": "2026-11-02T10:32:37+00:00", "channel": "quiet", "payload_id": "q-1", "items": [
        {"kind": "spc-outlook", "id": "spc:d1:x:USA:SLGT", "day": 1, "page": "USA", "outlook_date": "2026-11-02",
         "states_by_risk": {"SLGT": ["AR", "KS"]}},
        {"id": "urn:a", "page": "WA"}]}])
    s = sent_index.prune(s)
    u = sent_index.union_sent(copy.deepcopy(s), copy.deepcopy(s))
    check("union(index, same index) has the same publish fingerprint (no commit storm)",
          relay._publish_fingerprint(u) == relay._publish_fingerprint(s))


# ---------- whole run: several alerts, publish after EACH channel ----------
def test_main_publishes_after_each_channel():
    gh = FakeGitHub()
    gh.install()
    cache = fresh_dir("cache_main")
    order = []
    stale = (datetime.now(timezone.utc) - timedelta(minutes=50)).isoformat()
    env = {"ALERT_RELAY_CACHE_DIR": cache, "ALERT_RELAY_HB_URGENT": stale, "ALERT_RELAY_HB_QUIET": stale,
           "ALERT_RELAY_PUBLISH": "1", "GITHUB_TOKEN": "test-token-not-real", "ALERT_RELAY_DRY_RUN": "false",
           "URGENT_WEBHOOK_URL": "http://127.0.0.1:9/u", "URGENT_WEBHOOK_AUTH": "x",
           "QUIET_WEBHOOK_URL": "http://127.0.0.1:9/q", "QUIET_WEBHOOK_AUTH": "x"}
    saved = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    orig_put = gh._put

    def put(*a, **k):
        order.append("publish")
        return orig_put(*a, **k)
    github_api.put_contents = put

    def fake_urgent(once=False, dry_run=False):
        order.append("urgent POST")
        delivered.note(os.environ["ALERT_RELAY_BASE"], "urgent", "u-aaaa", [
            {"id": "TOR1", "keys": ["TOR1", "TOR1|L1"]}, {"id": "FFW1", "keys": ["FFW1", "FFW1|L3"]}])
        return {"send": []}

    def fake_quiet(once=False, dry_run=False):
        order.append("quiet POST")
        delivered.note(os.environ["ALERT_RELAY_BASE"], "quiet", "q-bbbb", [
            {"id": "WSW1", "page": "WA"}, {"id": "SPS1", "page": "WA"}])
        return {"qualifying": []}
    ou, oq = watch.run, watch_quiet.run
    watch.run, watch_quiet.run = fake_urgent, fake_quiet
    try:
        old_base = os.environ.get("ALERT_RELAY_BASE")
        code = relay.main()
    finally:
        watch.run, watch_quiet.run = ou, oq
        os.environ["ALERT_RELAY_BASE"] = old_base or BASE
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
    check("run exit code 0", code == 0, code)
    check("sent.json published right after the urgent POST, before the quiet tick",
          order[:3] == ["urgent POST", "publish", "quiet POST"], order)
    doc = json.loads(gh.files.get("sent.json") or "{}")
    keys = set((doc.get("urgent") or {}).get("keys") or {})
    seen = set((doc.get("quiet") or {}).get("seen") or {})
    check("all alerts of the run are in the published index (2 urgent, 2 quiet)",
          {"TOR1", "TOR1|L1", "FFW1", "FFW1|L3"} <= keys and {"WSW1|WA", "SPS1|WA"} <= seen, (keys, seen))
    check("no webhook secret or token in sent.json",
          "test-token-not-real" not in json.dumps(doc) and "127.0.0.1" not in json.dumps(doc))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:   # a crash is a failure, not a pass
                import traceback
                traceback.print_exc()
                check(name + " (raised %s)" % type(exc).__name__, False)
    shutil.rmtree(BASE, ignore_errors=True)
    print("\n%d failure(s)" % len(FAILS) if FAILS else "\nall relay dedupe tests passed")
    sys.exit(1 if FAILS else 0)
